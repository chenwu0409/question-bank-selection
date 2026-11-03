# -*- coding: utf-8 -*-
"""菁优网（jyeoo.com）探查：检索列表渲染 + 详情页 + 答案区提取 + 题图下载。

用法：
  python probe_jyeoo.py --kw 杠杆 --search-only          # 检索页：是否跳登录、命中多少
  python probe_jyeoo.py --shoti a101ba79-1514-415d-9e5f-632525b132f8   # 详情+答案区
  python probe_jyeoo.py --shoti <uuid> --figdir figs       # 顺带下载题图

已知实测（2026-11-03）：
  - 检索页 /ques/search/?keyword= 会跳「用户登录 - 菁优网」，游客拿不到列表；
    列表必须浏览器渲染，静态 requests 拿不到题链。
  - 详情页 /shiti/<uuid> 游客可读：题干 + 全部小问 + 【考点】+【答案】；
    【解答】正文为空（需登录/会员）。
  - 题图 img.jyeoo.net/quiz/images/... 免 Referer 可直接下。

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
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from cdp_client import CDP, new_tab  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')
SITE = 'https://www.jyeoo.com'


def open_tab(url, port=9222, wait=4.0):
    """新开标签页；若渲染进程卡死则换一个新标签页重试一次。"""
    last = None
    for attempt in range(2):
        t = new_tab(url, port)
        cdp = CDP(t['webSocketDebuggerUrl'])
        time.sleep(wait)
        try:
            cdp.js('return 1', timeout=8)
            return cdp
        except Exception as e:
            last = e
            cdp.close()
    raise RuntimeError('新开标签页无响应: %r' % (last,))


def do_search(kw, port=9222):
    url = '%s/ques/search/?keyword=%s' % (SITE, urllib.parse.quote(kw))
    cdp = open_tab(url, port, wait=5.0)
    try:
        v = cdp.js("""(function(){
          const txt = document.body ? document.body.innerText : '';
          const links = [...document.querySelectorAll('a[href]')]
            .map(a => a.href).filter(h => /\\/shiti\\//.test(h));
          return JSON.stringify({
            url: location.href, title: document.title, len: txt.length,
            head: txt.replace(/\\s+/g,' ').slice(0, 240),
            verify: /安全验证|滑动验证|请完成验证/.test(txt),
            login: /请先登录|立即登录|登录后/.test(txt),
            nq: links.length, qlinks: [...new Set(links)].slice(0, 8)
          });
        })()""")
        d = json.loads(v)
        d['search_url'] = url
        d['sec'] = 5.0
        if d['nq'] == 0:
            d['verdict'] = 'WALL'   # 题链 0：游客检索被墙/只出导航页
        elif d['login'] or d['verify']:
            d['verdict'] = 'WALL'
        else:
            d['verdict'] = 'OK'
        return d
    finally:
        cdp.close()


def do_detail(shoti, port=9222, figdir=None):
    url = '%s/shiti/%s' % (SITE, shoti)
    cdp = open_tab(url, port, wait=5.0)
    try:
        v = cdp.js("""(function(){
          function after(label){
            const all = [...document.querySelectorAll('span,div,p,b,i,strong,em,td,font')];
            const hit = all.find(e => e.children.length === 0 && e.textContent.trim() === label);
            if (!hit) return null;
            const p = hit.parentElement;
            return p ? p.innerText.replace(/\\s+/g,' ').slice(0, 1200) : null;
          }
          const txt = document.body.innerText.replace(/\\s+/g,' ');
          const imgs = [...document.querySelectorAll('img')]
            .filter(i => i.naturalWidth > 40)
            .map(i => i.src);
          // 来源试卷：取文本匹配「学年…试卷」的链接（页面上重复出现，取第一个）
          const paperLink = [...document.querySelectorAll('a')]
            .find(a => /\\d{4}-\\d{4}学年/.test(a.textContent||'') && /试卷/.test(a.textContent||''));
          // 解析区（【解答】）是否为空 → 游客被挡
          const sol = after('【解答】');
          const solBody = sol ? sol.replace('【解答】','').trim() : '';
          // 页面级真实登录提示（排除导航栏的"加入会员/立即登录"）
          const needLogin = /登录后.{0,6}查看|查看.{0,4}解析.{0,4}需.{0,4}登录|请先登录|登录即可查看答案|VIP/.test(txt);
          const pub = (txt.match(/发布[:：]\\s*([\\d\\/:\\s]+?)\\s*组卷/) || [])[1] || null;
          const diff = (txt.match(/难度[:：]\\s*([\\d.]+)/) || [])[1] || null;
          return JSON.stringify({
            url: location.href, title: document.title, len: txt.length,
            head: txt.slice(0, 400),
            kaodian: after('【考点】'), answer: after('【答案】'), solution: sol,
            solutionEmpty: solBody.length < 5,
            source: paperLink ? paperLink.textContent.replace(/\\s+/g,' ').trim().slice(0, 200) : null,
            publish: pub, difficulty: diff,
            needLogin: needLogin || solBody.length < 5,
            hasNavLoginOnly: /加入会员/.test(txt),
            verify: /安全验证|滑动验证/.test(txt),
            imgs: [...new Set(imgs)].slice(0, 12),
            svgOrMath: document.querySelectorAll('svg, math, mjx-container').length
          });
        })()""")
        d = json.loads(v)
        d['detail_url'] = url
        if figdir:
            os.makedirs(figdir, exist_ok=True)
            files = []
            for i, u in enumerate(d.get('imgs', [])):
                fn = os.path.join(figdir, '%s_%02d.png' % (shoti[:8], i))
                try:
                    req = urllib.request.Request(u, headers={'User-Agent': UA})
                    data = urllib.request.urlopen(req, timeout=45).read()
                    open(fn, 'wb').write(data)
                    files.append({'url': u, 'file': fn, 'bytes': len(data)})
                except Exception as e:
                    files.append({'url': u, 'file': None, 'err': repr(e)[:70]})
            d['figfiles'] = files
        return d
    finally:
        cdp.close()


def main():
    ap = argparse.ArgumentParser(description='菁优网探查')
    ap.add_argument('--kw', default=None, help='检索关键词')
    ap.add_argument('--shoti', default=None, help='题链 id（/shiti/<id>）')
    ap.add_argument('--search-only', action='store_true')
    ap.add_argument('--figdir', default=None)
    ap.add_argument('--port', type=int, default=9222)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    out = {}
    if args.kw and not args.shoti:
        t0 = time.time()
        d = do_search(args.kw, args.port)
        out['search'] = d
        print('检索 URL:', d['search_url'])
        print('渲染 %.1fs | title=%s | 正文%d字 | 题链%d | 验证页=%s | 需登录=%s | 判定=%s'
              % (time.time() - t0, d['title'], d['len'], d['nq'], d['verify'],
                 d['login'], d['verdict']))
        if d['verdict'] == 'WALL':
            print('→ 游客检索被墙（题链 0）：检索路径需用户先登录，'
                  '或改用详情页直达 /shiti/<uuid>；不要自研绕过')
        print('正文头:', d['head'][:220])
        print('题链样例:', d['qlinks'][:4])
        if d['nq'] and not args.search_only:
            first = d['qlinks'][0].rstrip('/').split('/')[-1]
            print('\n→ 进详情', first)
            dd = do_detail(first, args.port, args.figdir)
            out['detail'] = dd
            print('【考点】:', (dd.get('kaodian') or '无')[:180])
            print('【答案】:', (dd.get('answer') or '无')[:400])
            print('【解答】:', (dd.get('solution') or '无')[:300])
            print('来源:', dd.get('source'))
            print('需登录:', dd['needLogin'])
            if dd.get('figfiles'):
                print('题图:', [(f['file'] or f.get('err')) for f in dd['figfiles']])
    elif args.shoti:
        dd = do_detail(args.shoti, args.port, args.figdir)
        out['detail'] = dd
        print('URL:', dd['detail_url'])
        print('title:', dd['title'], '| 正文', dd['len'], '字')
        print('【考点】:', (dd.get('kaodian') or '无')[:200])
        print('【答案】:', (dd.get('answer') or '无')[:600])
        print('【解答】:', (dd.get('solution') or '无')[:400])
        print('来源:', dd.get('source'))
        print('发布:', dd.get('publish'), '| 难度:', dd.get('difficulty'))
        print('需登录:', dd['needLogin'], '| 解答区为空:', dd.get('solutionEmpty'),
              '| svg/math 节点:', dd.get('svgOrMath'))
        if dd.get('figfiles'):
            print('题图:', [(f['file'] or f.get('err')) for f in dd['figfiles']])
    else:
        print('需要 --kw 或 --shoti 之一')
        return

    if args.out:
        json.dump(out, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('saved', args.out)


if __name__ == '__main__':
    main()
