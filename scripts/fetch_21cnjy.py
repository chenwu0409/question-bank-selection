# -*- coding: utf-8 -*-
"""二一组卷网详情批量抓取：解析题干/小问/难度/试卷名 + 下载题图 + 标注答案通道。

用法：
  python fetch_21cnjy.py --qids 76925585,71542772 --out meta.json --figdir figs

详情页结构：SSR HTML 里 `related_questions:null,...question:` 之后是一个花括号 JSON，
用花括号深度匹配取出，再按字段解析。

答案通道：answer 通道 access=false 表示登录墙 → 该站答案只能标「非一手，需人工核对」。

依赖：仅标准库。
"""
import io
import sys
import os
import re
import json
import time
import hashlib
import argparse
import urllib.request
from html import unescape

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')
BASE = 'https://zujuan.21cnjy.com'
IMG_HOSTS = ('//tikupic', 'https://tikupic', '//math.21cnjy.com', 'https://math.21cnjy.com')


def get(url, ref=None):
    h = {'User-Agent': UA}
    if ref:
        h['Referer'] = ref
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=45) \
        .read().decode('utf-8', 'ignore')


def math_to_text(s):
    def rep(m):
        inner = re.sub(r'<[^>]+>', ' ', m.group(0))
        inner = unescape(inner)
        return ' ' + re.sub(r'\s+', ' ', inner).strip() + ' '
    return re.sub(r'<math[^>]*>.*?</math>', rep, s, flags=re.S)


def strip_tags(s):
    if not s:
        return ''
    s = math_to_text(s)
    s = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', r'[IMG \1]', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = unescape(s)
    return re.sub(r'[ \t]+', ' ', s).strip()


def brace_match(s, start):
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
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
                return i + 1
    return -1


def find_all_imgs(*blobs):
    urls = []
    for b in blobs:
        if not b:
            continue
        urls += re.findall(r'<img[^>]*src="([^"]+)"', b)
    keep = []
    seen = set()
    for u in urls:
        if any(u.startswith(h) for h in IMG_HOSTS) and u not in seen:
            seen.add(u)
            keep.append(u)
    return keep


def download(url, figdir, qid, idx):
    if url.startswith('//'):
        url = 'https:' + url
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    fn = os.path.join(figdir, '%s_%02d_%s.png' % (qid, idx, h))
    if os.path.exists(fn):
        return fn, None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': BASE + '/'})
        data = urllib.request.urlopen(req, timeout=60).read()
        open(fn, 'wb').write(data)
        return fn, None
    except Exception as e:
        return None, repr(e)[:80]


def fetch(qid, figdir=None):
    html = get('%s/question/detail/%s?district_id=19' % (BASE, qid),
               ref=BASE + '/question/search')
    rec = {'qid': qid, 'url': '%s/question/detail/%s' % (BASE, qid),
           'html_bytes': len(html)}
    m = re.search(r'"paper_title"\s*:\s*"([^"]*)"', html)
    rec['paper'] = m.group(1) if m else None
    for k in ('year_name', 'grade_name', 'term_name', 'channel_type_name', 'difficult_index'):
        mm = re.search(r'"%s"\s*:\s*"?([^",}]*)"?' % k, html)
        rec[k] = mm.group(1) if mm else None

    m = re.search(r'related_questions:\s*null,.*?question:\s*', html, re.S)
    if not m:
        rec['err'] = 'no bootstrap question'
        return rec
    st = html.index('{', m.end())
    en = brace_match(html, st)
    try:
        q = json.loads(html[st:en])
    except Exception as e:
        rec['err'] = 'json fail ' + str(e)[:60]
        return rec

    rec['type'] = q.get('channel_type_name')
    rec['diff'] = q.get('difficult_index')
    rec['access'] = q.get('access')
    rec['is_explain'] = q.get('is_explain')
    rec['title'] = strip_tags(q.get('title') or '')
    opts = q.get('options') or []
    rec['options'] = [strip_tags(o.get('content') or '') for o in opts] if opts else None
    rec['subs'] = [{'id': it.get('question_id'),
                    'q': strip_tags(it.get('question_text') or ''),
                    'answer': it.get('answer_text') or it.get('answer') or '',
                    'access': it.get('access')}
                   for it in (q.get('list') or [])]
    rec['answer_text_visible'] = any(s.get('answer') for s in rec['subs'])
    rec['answer_source'] = '平台一手' if rec['answer_text_visible'] else '非一手·需人工核对'
    rec['ansimgs'] = sorted(set(re.findall(r'(//webshot[^"\'\s]+an\.png[^"\'\s]*)', html)))
    rec['eximgs'] = sorted(set(re.findall(r'(//webshot[^"\'\s]+ex\.png[^"\'\s]*)', html)))

    if figdir:
        os.makedirs(figdir, exist_ok=True)
        urls = find_all_imgs(q.get('title') or '',
                             *[it.get('question_text') or '' for it in (q.get('list') or [])])
        files = []
        for i, u in enumerate(urls):
            fn, err = download(u, figdir, qid, i)
            files.append({'url': u, 'file': fn, 'err': err})
        rec['images'] = files
    return rec


def main():
    ap = argparse.ArgumentParser(description='二一组卷网详情批量抓取')
    ap.add_argument('--qids', required=True, help='逗号分隔的题目 id')
    ap.add_argument('--out', default='meta.json')
    ap.add_argument('--figdir', default=None, help='题图下载目录')
    ap.add_argument('--keep-html', default=None, help='同时保存原始 HTML 到该目录')
    args = ap.parse_args()

    qids = [q.strip() for q in args.qids.split(',') if q.strip()]
    out = {}
    t0 = time.time()
    for i, qid in enumerate(qids):
        try:
            rec = fetch(qid, args.figdir)
            out[qid] = rec
            print('=' * 72)
            print(qid, '|', rec.get('type'), '| diff', rec.get('diff'),
                  '| access', rec.get('access'), '| 答案一手:', rec.get('answer_source'))
            print('试卷:', rec.get('paper'))
            print('题干:', rec.get('title', '')[:400])
            for s in rec.get('subs', [])[:8]:
                print('   Q:', s['q'][:200])
                if s.get('answer'):
                    print('   A:', str(s['answer'])[:160])
            if rec.get('images'):
                print('   图:', [(f['file'] or f['err']) for f in rec['images']])
        except Exception as e:
            out[qid] = {'qid': qid, 'err': repr(e)[:120]}
            print(qid, 'FAIL', repr(e)[:120])
        if i + 1 < len(qids):
            time.sleep(0.8)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or '.', exist_ok=True)
    json.dump(out, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\nsaved %s  共 %d 题  用时 %.1fs' % (args.out, len(out), time.time() - t0))
    if args.keep_html:
        os.makedirs(args.keep_html, exist_ok=True)


if __name__ == '__main__':
    main()
