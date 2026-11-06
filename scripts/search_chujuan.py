# -*- coding: utf-8 -*-
"""出卷网（chujuan.cn）关键词检索：免登录可用，结果在 window.SearchQuesResult JSON。

免登录能拿到：题干（含小问/选项/题图 URL）、题型、难度、试卷名、知识点、来源。
免登录拿不到：答案与解析（字段为空），详情页 302 到 pass.chujuan.cn/login。

用法：
  python search_chujuan.py --kw "杠杆" --kw "杠杆 平衡" --subject phys --pages 2 --out pool.json
  python search_chujuan.py --kw "二次函数" --subject math --gd-only --diff 3

输出：JSON 数组，每条含 qid/学科/难度/题型/试卷名/题干/小问/知识点/题图/URL，
     并带 answer_source=platform_empty（免登录无答案，需登录后另取）。
依赖：仅标准库。
"""
import io
import sys
import os
import re
import json
import time
import argparse
import urllib.request
import urllib.parse
from html import unescape

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')
BASE = 'https://www.chujuan.cn'
CHID = {'math': 3, 'phys': 6, 'chem': 7, 'eng': 4}
GD_RE = re.compile('广东|广州|深圳|佛山|东莞|珠海|中山|惠州|清远|台山|潮州|汕头|汕尾|韶关|'
                   '梅州|揭阳|江门|肇庆|湛江|茂名|阳江|云浮|河源|顺德|南海|番禺|白云|增城|'
                   '花都|南沙|荔湾|黄埔|海珠|越秀|天河')


def get(url, ref=None):
    h = {'User-Agent': UA}
    if ref:
        h['Referer'] = ref
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=45) \
        .read().decode('utf-8', 'ignore')


def extract_json(html, marker):
    i = html.find(marker)
    if i < 0:
        return None, 'anchor_missing'
    j = html.find('{', i)
    depth = 0
    in_str = False
    esc = False
    for k in range(j, min(j + 5_000_000, len(html))):
        c = html[k]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[j:k + 1]), None
                except Exception as e:
                    return None, 'json_error:%r' % (e,)
    return None, 'unbalanced'


def strip_tags(s):
    if not s:
        return ''
    s = re.sub(r'<math[^>]*>.*?</math>', ' [公式] ', s, flags=re.S)
    s = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', r' [图:\1] ', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def search(keyword, subject, page):
    url = '%s/question/search?xd=2&chid=%d&content=%s&page=%d' % (
        BASE, CHID[subject], urllib.parse.quote(keyword), page)
    html = get(url, ref=BASE + '/question/search')
    d, err = extract_json(html, 'window.SearchQuesResult')
    if not d:
        return None, len(html), err
    qs = d.get('questions') or []
    return (qs, d.get('total')), len(html), None


def main():
    ap = argparse.ArgumentParser(description='出卷网免登录检索')
    ap.add_argument('--kw', action='append', required=True, help='检索词，可重复')
    ap.add_argument('--subject', default='phys', choices=list(CHID))
    ap.add_argument('--pages', type=int, default=2)
    ap.add_argument('--gd-only', action='store_true', help='只保留广东试卷名')
    ap.add_argument('--diff', default=None, help='难度过滤，3 表示中等')
    ap.add_argument('--out', default=None, help='候选池 JSON 输出')
    args = ap.parse_args()

    pool = {}
    t0 = time.time()
    for kw in args.kw:
        for page in range(1, args.pages + 1):
            try:
                res, raw, err = search(kw, args.subject, page)
                if res is None:
                    print('%-14s p%d NO_JSON %s raw=%dKB' % (kw[:14], page, err, raw // 1024))
                    break
                qs, total = res
                if not qs:
                    print('%-14s p%d 空页 total=%s' % (kw[:14], page, total))
                    break
                kept = 0
                for q in qs:
                    paper = q.get('paper_title') or ''
                    diff = q.get('difficult_index')
                    if args.diff and str(diff) != str(args.diff):
                        continue
                    if args.gd_only and not GD_RE.search(paper):
                        continue
                    qid = q.get('question_id')
                    if not qid or qid in pool:
                        continue
                    subs = [{'id': s.get('question_id'),
                             'q': strip_tags(s.get('question_text') or s.get('title') or '')[:400]}
                            for s in (q.get('list') or []) if isinstance(s, dict)]
                    imgs = re.findall(r'https?://tikupic[^"\' )]+', q.get('question_text') or '')
                    kept += 1
                    pool[qid] = {
                        'qid': qid,
                        'keyword': kw,
                        'subject': args.subject,
                        'type': q.get('channel_type_name'),
                        'diff': diff,
                        'paper': paper,
                        'title': strip_tags(q.get('title') or '')[:300],
                        'subs': subs,
                        'images': sorted(set(imgs)),
                        'knowledge': strip_tags(str(q.get('knowledge') or ''))[:200] or None,
                        'answer': strip_tags(q.get('answer') or '') or None,
                        'answer_source': 'platform_empty',
                        'detail_access': 'login_required',
                        'url': '%s/question/detail/%s' % (BASE, qid),
                    }
                print('%-14s p%d n=%d kept=%d total=%s' % (kw[:14], page, len(qs), kept, total))
            except Exception as e:
                print('%-14s p%d ERR %s' % (kw[:14], page, repr(e)[:90]))
            time.sleep(0.6)

    out = list(pool.values())
    print('\n候选池 %d 题，用时 %.1fs' % (len(out), time.time() - t0))
    for it in out[:15]:
        print('  ', it['qid'], '|', it['type'], '| diff', it['diff'], '|', it['paper'][:50])
        print('      ', it['title'][:110])
    if out:
        print('\n注意：出卷网免登录只有题干，答案/解析在详情页（需登录）。')
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        json.dump(out, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('saved', args.out)


if __name__ == '__main__':
    main()
