# -*- coding: utf-8 -*-
"""菁优网（jyeoo.com）检索：免登录可搜题，登录后解锁真实题号与解析。

能力（2026-11-06 实测）：
  - 关键词检索 `GET /search?c=0&qb=<kw>`：匿名可用，10 条/页，含题干、来源、难度、
    填空/选择的内联答案；题号被掩码为 00000000-…，点「解析」会弹登录框。
  - 带登录态（--cookies 或 --session）同一接口返回真实加密题号，可打开详情。
  - 详情 `GET /<subject>/ques/detail/<加密题号>`：匿名回落首页（登录墙）；
    登录后可见【考点】【答案】【分析】【解答】【点评】，未开通会员也可看，下载/组卷要权益。
  - 兜底路径：`/shiti/<uuid>` 游客可读题干+【考点】+【答案】；`/sj/` 试卷页可列题链。

用法：
  python search_jyeoo.py --kw "杠杆"                    # 匿名搜（题号掩码）
  python search_jyeoo.py --kw "探究杠杆平衡条件" --subject phys --pages 2 --out pool.json
  python search_jyeoo.py --kw "杠杆" --session "F:/.../tmp/session/session_state_20261106.json"
  python search_jyeoo.py --shoti <加密题号> --subject phys
  python search_jyeoo.py --paper /sj/<uuid>             # 试卷页列 /shiti 题链
  python search_jyeoo.py --discover 20                  # sitemap 抽 /sj 链接
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
import urllib.error
from html import unescape

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')
BASE = 'https://www.jyeoo.com'
SUBJECT_PATH = {'phys': 'physics', 'math': 'math', 'chem': 'chemistry'}
SHITI_RE = re.compile('/shiti/[0-9a-f-]{36}')
SJ_RE = re.compile('/sj/[0-9a-f-]{36}')


def load_cookie(state_path=None, domain='jyeoo.com'):
    if not state_path:
        return ''
    state = json.load(open(state_path, encoding='utf-8'))
    return '; '.join('%s=%s' % (c['name'], c['value']) for c in state.get('cookies', [])
                     if domain in (c.get('domain') or ''))


def get(url, cookie='', ref=None, data=None):
    h = {'User-Agent': UA, 'Referer': ref or BASE + '/'}
    if cookie:
        h['Cookie'] = cookie
    if data:
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, r.geturl(), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode('utf-8', 'replace')


def strip_tags(s, keep_img=True):
    if not s:
        return ''
    s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', s, flags=re.S | re.I)
    if keep_img:
        s = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', r' [图:\1] ', s, flags=re.I)
    else:
        s = re.sub(r'<img[^>]+>', ' ', s, flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def after_label(txt, label, n=1500):
    i = txt.find(label)
    if i < 0:
        return None
    seg = txt[i + len(label):i + len(label) + n]
    for stop in ('【考点】', '【分析】', '【解答】', '【点评】', '【答案】', '【专题】'):
        j = seg.find(stop)
        if j > 0:
            seg = seg[:j]
    return re.sub(r'\s+', ' ', seg).strip() or None


def parse_results(html):
    """解析 /search 结果块：题号、题号是否掩码、题干、内联答案、难度、来源。"""
    out = []
    for b in re.split(r'<li class="QUES_LI"', html)[1:]:
        fid = (re.search(r'<fieldset[^>]*id="([^"]+)"', b) or [None, None])[1]
        masked = bool(fid) and '00000000-0000-0000-0000-000000000000' == fid
        stem = ''
        m = re.search(r'<div class="pt1"[^>]*>(.*?)</div>', b, re.S)
        if m:
            stem = strip_tags(m.group(1))
        ans = re.findall(r'<div class="sanwser">([^<]{1,60})</div>', b)
        diff = (re.search(r'难度：([^<]{1,6})', b) or [None, None])[1]
        src = (re.search(r'class="ques-source"[^>]*>(.*?)</a>', b, re.S) or [None, None])[1]
        out.append({
            'qid': None if masked else fid,
            'qid_masked': masked,
            'stem': stem[:600],
            'inline_answer': [strip_tags(x) for x in ans][:8],
            'difficulty': diff,
            'source': strip_tags(src or '') or None,
            'analysis_gate': 'openLoginUI()' in b or masked,
        })
    return out


def search_keyword(kw, subject, pages, cookie=''):
    results = []
    for page in range(1, pages + 1):
        q = urllib.parse.urlencode({'c': 0, 's': {'phys': 21, 'math': 19, 'chem': 22}.get(subject, 21),
                                    'qb': kw, 'p': page})
        st, final, html = get(BASE + '/search?' + q, cookie, BASE + '/search')
        isq = re.search(r"isQues = '([^']*)'", html)
        blocks = parse_results(html)
        print('%-12s p%d st=%s isQues=%s 条数=%d 掩码=%s'
              % (kw[:12], page, st, isq.group(1) if isq else '?', len(blocks),
                 blocks[0]['qid_masked'] if blocks else '-'))
        if blocks and blocks[0]['qid_masked']:
            print('   → 题号被掩码（匿名态）：加 --session 或 --cookies 才拿得到真实题号')
        results.extend(blocks)
        time.sleep(2)
    return results


def paper_questions(path, cookie=''):
    url = path if path.startswith('http') else BASE + path
    st, final, txt = get(url, cookie, BASE + '/')
    m = re.search(r'<title[^>]*>(.*?)</title>', txt, re.S)
    links = list(dict.fromkeys(SHITI_RE.findall(txt)))
    return {'mode': 'paper', 'url': url, 'status': st, 'title': strip_tags(m.group(1)) if m else None,
            'count': len(links), 'questions': [BASE + x for x in links]}


def discover(limit, cookie=''):
    st, _, txt = get(BASE + '/sitemap1.xml', cookie, BASE + '/')
    links = list(dict.fromkeys(SJ_RE.findall(txt)))[:limit]
    return {'mode': 'discover', 'status': st, 'count': len(links),
            'papers': [BASE + x for x in links]}


def detail(qid, subject='phys', cookie='', figdir=None):
    url = '%s/%s/ques/detail/%s' % (BASE, SUBJECT_PATH.get(subject, 'physics'), qid)
    st, final, html = get(url, cookie, BASE + '/search')
    txt = strip_tags(html, keep_img=False)
    home_fallback = '专注小学初中高中' in (re.search(r'<title>([^<]*)', html) or [None, ''])[1]
    rec = {
        'mode': 'detail', 'qid': qid, 'url': url, 'status': st,
        'home_fallback': home_fallback,
        'kaodian': after_label(txt, '【考点】', 600),
        'answer': after_label(txt, '【答案】', 600),
        'analysis': after_label(txt, '【分析】', 800),
        'solution': after_label(txt, '【解答】', 1200),
        'review': after_label(txt, '【点评】', 600),
        'difficulty': (re.search(r'难度[：:]\s*([0-9.]+|[一-龥]{1,3})', txt) or [None, None])[1],
        'images': sorted(set(re.findall(r'https?://img\.jyeoo\.net/quiz/images/[^"\' )]+', html))),
    }
    if rec['home_fallback']:
        st2, _, alt = get(BASE + '/shiti/' + qid, cookie, BASE + '/')
        t2 = strip_tags(alt, keep_img=False)
        if '【考点】' in t2:
            rec.update({'url': BASE + '/shiti/' + qid, 'home_fallback': False,
                        'kaodian': after_label(t2, '【考点】', 600),
                        'answer': after_label(t2, '【答案】', 600),
                        'analysis': after_label(t2, '【分析】', 800),
                        'solution': after_label(t2, '【解答】', 1200)})
            html = alt
            rec['images'] = sorted(set(re.findall(r'https?://img\.jyeoo\.net/[^"\' )]+', html)))
    if rec['answer']:
        rec['answer_source'] = 'platform_visible'
    elif rec['home_fallback']:
        rec['answer_source'] = 'login_required'
    else:
        rec['answer_source'] = 'no_answer'
    rec['solution_empty'] = not rec['solution'] or len(rec['solution']) < 5
    if figdir and rec['images']:
        os.makedirs(figdir, exist_ok=True)
        files = []
        for i, u in enumerate(rec['images']):
            fn = os.path.join(figdir, '%s_%02d.png' % (qid[:8], i))
            try:
                req = urllib.request.Request(u, headers={'User-Agent': UA})
                data = urllib.request.urlopen(req, timeout=45).read()
                open(fn, 'wb').write(data)
                files.append({'url': u, 'file': fn, 'bytes': len(data)})
            except Exception as e:
                files.append({'url': u, 'file': None, 'err': repr(e)[:80]})
        rec['figfiles'] = files
    return rec


def main():
    ap = argparse.ArgumentParser(description='菁优网检索（免登录可搜，登录解锁题号与解析）')
    ap.add_argument('--kw', action='append', default=None, help='关键词，可重复')
    ap.add_argument('--subject', default='phys', choices=list(SUBJECT_PATH))
    ap.add_argument('--pages', type=int, default=1)
    ap.add_argument('--session', default=None, help='session_state.json（save_session.py 导出）')
    ap.add_argument('--cookies', default='', help='直接给 cookie 字符串（不推荐，易泄漏）')
    ap.add_argument('--shoti', default=None, help='加密题号（登录态搜索返回的 id）')
    ap.add_argument('--paper', default=None, help='/sj/ 试卷页链接或 uuid')
    ap.add_argument('--discover', type=int, default=0, help='sitemap 抽前 N 条 /sj/')
    ap.add_argument('--figdir', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    cookie = args.cookies or load_cookie(args.session)
    out = {}
    if args.kw:
        items = []
        for kw in args.kw:
            items.extend(search_keyword(kw, args.subject, args.pages, cookie))
        out['items'] = items
        print('\n共 %d 条；可解析题号 %d 条' % (len(items), sum(1 for x in items if x['qid'])))
        for it in items[:6]:
            print('  %s | %s | %s | 难度%s | %s' % (
                it['qid'] or '(掩码)', it['source'], (it['stem'][:70] + '…'), it['difficulty'],
                '/'.join(it['inline_answer'][:3])))
    if args.paper:
        p = args.paper
        if not p.startswith('http') and not p.startswith('/sj/'):
            p = '/sj/' + p
        d = paper_questions(p, cookie)
        out['paper'] = d
        print('试卷页 %s | status=%s | 题链 %d' % (d['url'], d['status'], d['count']))
        for u in d['questions'][:10]:
            print('  ', u)
    if args.discover:
        d = discover(args.discover, cookie)
        out['discover'] = d
        print('sitemap 试卷页 %d 条' % d['count'])
        for u in d['papers'][:5]:
            print('  ', u)
    if args.shoti:
        d = detail(args.shoti, args.subject, cookie, args.figdir)
        out['detail'] = d
        print('URL:', d['url'], '| status=', d['status'], '| 登录墙回退=', d['home_fallback'])
        print('【考点】:', (d['kaodian'] or '无')[:160])
        print('【答案】:', (d['answer'] or '无')[:300])
        print('【解答】:', (d['solution'] or '空/被挡')[:150])
        print('难度:', d['difficulty'], '| 答案来源:', d['answer_source'])
        if d.get('figfiles'):
            print('题图:', [(f['file'] or f.get('err')) for f in d['figfiles']])
    if not any([args.kw, args.paper, args.discover, args.shoti]):
        print('至少给一个：--kw / --shoti / --paper / --discover')
        return
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        json.dump(out, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('saved', args.out)


if __name__ == '__main__':
    main()
