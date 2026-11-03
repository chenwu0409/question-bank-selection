# -*- coding: utf-8 -*-
"""二一组卷网检索：多关键词 × 学科 × 页数，结果在 window.SearchQuesResult JSON。

用法：
  python search_21cnjy.py --kw "杠杆" --kw "杠杆 平衡" --subject phys --pages 2 --gd-only --out pool.json

--gd-only 只保留试卷名命中广东地名的题（district_id 参数对关键词检索不生效，用试卷名正则筛）。

输出：JSON 数组，每条含 qid/学科/难度/题型/试卷名/题干摘要。
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
BASE = 'https://zujuan.21cnjy.com'
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
        return None
    j = html.find('{', i)
    depth = 0
    for k in range(j, min(j + 5_000_000, len(html))):
        c = html[k]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[j:k + 1])
                except Exception:
                    return None
    return None


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
    d = extract_json(html, 'window.SearchQuesResult')
    if not d:
        return None, len(html)
    qs = d.get('questions') or (d.get('data') or {}).get('questions') or []
    total = (d.get('data') or {}).get('total')
    return (qs, total), len(html)


def main():
    ap = argparse.ArgumentParser(description='二一组卷网检索')
    ap.add_argument('--kw', action='append', required=True, help='检索词，可重复')
    ap.add_argument('--subject', default='phys', choices=list(CHID))
    ap.add_argument('--pages', type=int, default=2)
    ap.add_argument('--gd-only', action='store_true', help='只保留广东试卷名')
    ap.add_argument('--diff', default=None, help='难度过滤，如 3 表示中等')
    ap.add_argument('--out', default=None, help='候选池 JSON 输出路径')
    args = ap.parse_args()

    pool = {}
    t0 = time.time()
    for kw in args.kw:
        for page in range(1, args.pages + 1):
            try:
                res, raw = search(kw, args.subject, page)
                if res is None:
                    print('%-14s p%d NO_JSON raw=%dKB' % (kw[:14], page, raw // 1024))
                    break
                qs, total = res
                if not qs:
                    print('%-14s p%d 空页（total=%s）' % (kw[:14], page, total))
                    break
                n_gd = 0
                for q in qs:
                    paper = q.get('paper_title') or ''
                    diff = q.get('difficult_index')
                    if args.diff and str(diff) != str(args.diff):
                        continue
                    if args.gd_only and not GD_RE.search(paper):
                        continue
                    n_gd += 1
                    qid = q.get('question_id')
                    if qid and qid not in pool:
                        pool[qid] = {
                            'qid': qid,
                            'keyword': kw,
                            'subject': args.subject,
                            'type': q.get('channel_type_name') or q.get('question_type'),
                            'diff': diff,
                            'paper': paper,
                            'year': q.get('year_name'),
                            'grade': q.get('grade_name'),
                            'title': strip_tags(q.get('title') or '')[:220],
                            'url': '%s/question/detail/%s' % (BASE, qid),
                        }
                print('%-14s p%d n=%d kept=%d total=%s' % (kw[:14], page, len(qs), n_gd, total))
            except Exception as e:
                print('%-14s p%d ERR %s' % (kw[:14], page, repr(e)[:90]))
            time.sleep(0.6)

    out = list(pool.values())
    print('\n候选池 %d 题，用时 %.1fs' % (len(out), time.time() - t0))
    for it in out[:20]:
        print('  ', it['qid'], '|', it['type'], '| diff', it['diff'], '|', it['paper'][:52])
        print('      ', it['title'][:120])
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        json.dump(out, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('saved', args.out)


if __name__ == '__main__':
    main()
