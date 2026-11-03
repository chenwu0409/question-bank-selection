# -*- coding: utf-8 -*-
"""出卷网（chujuan.cn）登录态探查：详情页抓取 + 答案/解析字段提取 + 解析图下载。

前置：专用 Chrome 已启动且用户已登录（登录态在专用 user-data-dir 里）。

用法：
  python probe_chujuan.py --qid 41511381 --out chujuan_meta.json --figdir figs
  python probe_chujuan.py --login-state          # 只复验登录态
  python probe_chujuan.py --probe-wall            # 探测答案墙（免登录 vs 登录态对比）

原理：在已登录页面上下文里 fetch('/question/detail/<qid>', {credentials:'include'}），
登录态自动带上 cookie；解析出的答案图 URL 带 sign，拿到 URL 后无 cookie 也可下载。

依赖：标准库 + 同目录 cdp_client.py；需要 CDP 端口 9222。
"""
import io
import sys
import os
import re
import json
import time
import argparse
import urllib.request
from html import unescape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from cdp_client import CDP, pick_tab, new_tab  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')
SITE = 'https://www.chujuan.cn'


def connect(tab_sub='chujuan', port=9222):
    """挑一个能响应的 chujuan 标签页；没有就新开一个。

    只在 chujuan 标签页里挑（fallback_any=False），避免在别的站上误判登录态。
    """
    try:
        t = pick_tab(tab_sub, 0, port, fallback_any=False)
    except Exception:
        t = None
    if t is None:
        t = new_tab(SITE + '/', port)
        time.sleep(3)
        t = pick_tab(tab_sub, 0, port, fallback_any=False)
    if t is None:
        raise RuntimeError('无法定位可用的 chujuan 标签页，先跑 launch_chrome.py')
    return CDP(t['webSocketDebuggerUrl'])


def login_state(cdp):
    v = cdp.js("""(function(){
      const txt = document.body ? document.body.innerText : '';
      const m = txt.match(/1[3-9]\\d{9}/g) || txt.match(/1[3-9]\\d\\*\\*\\*\\*\\d{4}/g);
      return JSON.stringify({
        url: location.href,
        title: document.title,
        phone: m ? m[0] : null,
        hasLoginBtn: /登录|注册/.test(txt.slice(0, 600)),
        hasUserArea: /充值|我的|退出|个人/.test(txt)
      });
    })()""")
    return json.loads(v)


def fetch_detail(cdp, qid):
    js = """(async function(){
      const r = await fetch('/question/detail/%s', {credentials:'include'});
      const html = await r.text();
      return JSON.stringify({status: r.status, url: r.url, len: html.length, html: html});
    })()""" % qid
    out = cdp.js(js, timeout=90)
    if not out:
        raise RuntimeError('CDP eval 无返回')
    return json.loads(out)


def jval(html, key):
    m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % key, html)
    if not m:
        return None
    try:
        return json.loads('"%s"' % m.group(1))
    except Exception:
        return m.group(1)


def strip_tags(s):
    if not s:
        return ''
    s = re.sub(r'<[^>]+>', ' ', s)
    s = unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def parse_detail(html):
    rec = {'html_bytes': len(html)}
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.S)
    rec['title'] = m.group(1).strip()[:120] if m else None
    rec['login_wall'] = ('用户登录' in html and len(html) < 15000)

    rec['answer'] = jval(html, 'answer')
    rec['answer_text'] = jval(html, 'answer_text')
    rec['answer_json'] = jval(html, 'answer_json')
    rec['explanation'] = jval(html, 'explanation')
    rec['sub_explanation'] = jval(html, 'sub_explanation')

    m = re.search(r'"list"\s*:\s*\[', html)
    subs = []
    if m:
        st = html.index('[', m.start())
        depth = 0
        in_str = False
        esc = False
        for i in range(st, len(html)):
            c = html[i]
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
            elif c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    try:
                        for s in json.loads(html[st:i + 1]):
                            subs.append({
                                'q': strip_tags(s.get('question_text') or s.get('question') or '')[:400],
                                'a': strip_tags(s.get('answer') or '')[:300],
                                'e': strip_tags(s.get('explanation') or '')[:600],
                            })
                    except Exception as e:
                        rec['sub_parse_err'] = str(e)[:60]
                    break
    rec['subs'] = subs

    rec['ansimgs'] = sorted(set(re.findall(r'https?://webshot[^"\'\s]+an\.png[^"\'\s]*', html)))
    rec['eximgs'] = sorted(set(re.findall(r'https?://webshot[^"\'\s]+ex\.png[^"\'\s]*', html)))
    rec['stemimgs'] = sorted(set(re.findall(r'https?://tikupic[^"\'\s]+', html)))
    rec['has_firsthand_analysis'] = bool(rec['eximgs'] or (rec['explanation'] and len(rec['explanation']) > 20))
    rec['answer_source'] = '一手（官方解析图/字段）' if rec['has_firsthand_analysis'] else '未取得'
    return rec


def download(url, figdir, qid, tag):
    os.makedirs(figdir, exist_ok=True)
    fn = os.path.join(figdir, '%s_%s.png' % (qid, tag))
    if os.path.exists(fn):
        return fn, None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': SITE + '/'})
        data = urllib.request.urlopen(req, timeout=60).read()
        open(fn, 'wb').write(data)
        return fn, None
    except Exception as e:
        return None, repr(e)[:80]


def main():
    ap = argparse.ArgumentParser(description='出卷网登录态探查')
    ap.add_argument('--qid', default='41511381')
    ap.add_argument('--out', default='chujuan_meta.json')
    ap.add_argument('--figdir', default=None)
    ap.add_argument('--port', type=int, default=9222)
    ap.add_argument('--login-state', action='store_true', help='只复验登录态')
    ap.add_argument('--probe-wall', action='store_true', help='探测答案墙')
    args = ap.parse_args()

    cdp = connect(port=args.port)
    try:
        if args.login_state:
            st = login_state(cdp)
            print(json.dumps(st, ensure_ascii=False))
            ok = bool(st.get('phone')) and not st.get('hasLoginBtn')
            print('登录态:', 'PASS' if ok else 'FAIL（缺手机号或仍见登录按钮）')
            return

        d = fetch_detail(cdp, args.qid)
        print('status=%s len=%d url=%s' % (d['status'], d['len'], d['url'][:90]))
        rec = parse_detail(d['html'])
        print('title:', rec['title'])
        print('登录墙:', rec['login_wall'])
        print('答案一手性:', rec['answer_source'])
        if rec.get('answer_text'):
            print('answer_text:', strip_tags(rec['answer_text'])[:200])
        if rec.get('explanation'):
            print('explanation:', strip_tags(rec['explanation'])[:400])
        for s in rec['subs'][:4]:
            print('  Q:', s['q'][:160])
            if s['a']:
                print('  A:', s['a'][:160])
            if s['e']:
                print('  E:', s['e'][:300])
        print('解析图:', rec['eximgs'][:3])

        if args.figdir:
            for i, u in enumerate(rec['eximgs'][:4]):
                fn, err = download(u, args.figdir, args.qid, 'ex%d' % i)
                print('  解析图下载:', fn or err)
            for i, u in enumerate(rec['ansimgs'][:4]):
                fn, err = download(u, args.figdir, args.qid, 'an%d' % i)
                print('  答案图下载:', fn or err)

        rec['qid'] = args.qid
        rec['fetch_status'] = d['status']
        json.dump(rec, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('saved', args.out)
    finally:
        cdp.close()


if __name__ == '__main__':
    main()
