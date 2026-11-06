# -*- coding: utf-8 -*-
"""保存/检查专用 Chrome 的登录态（cookie），供三站检索复用。

用法：
  python save_session.py --port 9223 --status              # 只报登录状态（不落盘）
  python save_session.py --port 9223 --out tmp/session_state.json   # 导出 cookie 到本地文件

说明：
  - 登录由用户本人在有界面的专用 Chrome 里完成，本脚本不代填账号密码、不代点验证码。
  - cookie 文件含敏感信息：只放 tmp/ 或本地未跟踪目录，必须写进 .gitignore，禁止提交。
  - 登录态的主载体是 Chrome 的 --user-data-dir（profile 持久化）；本文件是备份/给 requests 复用。
  - 失效后：重新在专用 Chrome 里登录一次，再跑一次本脚本刷新文件。

依赖：标准库 + 同目录 cdp_client.py。
"""
import io
import sys
import os
import re
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import urllib.request  # noqa: E402
from cdp_client import CDP, tabs, pick_tab  # noqa: E402

SITES = {
    'chujuan': {
        'domain': 'chujuan.cn',
        'url_sub': 'chujuan',
        'login_page': 'https://pass.chujuan.cn/login',
        'probe_js': """(function(){
          const t = document.body ? document.body.innerText : '';
          return JSON.stringify({
            url: location.href, title: document.title,
            phone: (t.match(/1[3-9]\\d(?:\\*{4}|\\d{4})\\d{4}/) || [])[0] || null,
            loginBtn: /登录|注册/.test(t.slice(0, 400)),
            userArea: /充值|我的|退出|个人中心/.test(t)
          });
        })()""",
        'logged_in': lambda d: bool(d.get('phone')) or bool(d.get('userArea')),
    },
    'jyeoo': {
        'domain': 'jyeoo.com',
        'url_sub': 'jyeoo',
        'login_page': 'https://www.jyeoo.com/account/loginform',
        'probe_js': """(function(){
          const t = document.body ? document.body.innerText : '';
          const hasLogout = [...document.querySelectorAll('a')]
            .some(a => /\\/account\\/logoff/.test(a.href || ''));
          return JSON.stringify({
            url: location.href, title: document.title,
            onLoginPage: /\\/account\\/loginform/.test(location.href) || /用户登录/.test(document.title),
            hasLogout: hasLogout,
            userArea: /退出|个人中心|会员中心/.test(t) || hasLogout,
            vip: /VIP|会员/.test(t)
          });
        })()""",
        'logged_in': lambda d: (not d.get('onLoginPage')) and bool(d.get('userArea')),
    },
}


def browser_ws(port):
    v = json.load(urllib.request.urlopen('http://127.0.0.1:%d/json/version' % port, timeout=10))
    return v['webSocketDebuggerUrl']


def all_cookies(port):
    """取全部 cookie。注意：browser 级 target 不支持 Network 域，必须挂在 page target 上。"""
    for t in [x for x in tabs(port) if x.get('type') == 'page']:
        c = CDP(t['webSocketDebuggerUrl'])
        try:
            r = c.call('Network.getAllCookies', {}, timeout=30)
            return r.get('cookies') or []
        except Exception:
            continue
        finally:
            c.close()
    raise RuntimeError('没有可取 cookie 的 page 标签页（专用 Chrome 是否还在运行？）')


def status(port):
    out = {}
    for name, cfg in SITES.items():
        try:
            t = pick_tab(cfg['url_sub'], 0, port, fallback_any=False)
        except Exception:
            out[name] = {'tab': False, 'logged_in': False,
                         'hint': '没有该站标签页；用 cdp_client.py new <login_page> 打开'}
            continue
        c = CDP(t['webSocketDebuggerUrl'])
        try:
            d = json.loads(c.js(cfg['probe_js'], timeout=20))
            d['tab'] = True
            d['logged_in'] = bool(cfg['logged_in'](d))
            out[name] = d
        finally:
            c.close()
    return out


def main():
    ap = argparse.ArgumentParser(description='保存/检查三站登录态')
    ap.add_argument('--port', type=int, default=9223)
    ap.add_argument('--out', default=None, help='cookie 落盘路径（必须在未跟踪目录）')
    ap.add_argument('--domain', action='append', default=None, help='额外域名后缀，可重复')
    ap.add_argument('--status', action='store_true')
    args = ap.parse_args()

    st = status(args.port)
    for name, d in st.items():
        print('%-8s 登录=%s | %s' % (name, 'PASS' if d.get('logged_in') else 'FAIL',
                                 (d.get('url') or d.get('hint') or '')[:80]))
        if name == 'chujuan':
            print('         手机号=%s 用户区=%s 登录按钮=%s'
                  % (d.get('phone'), d.get('userArea'), d.get('loginBtn')))
        else:
            print('         登录页=%s 用户区=%s 退出链=%s 会员提示=%s'
                  % (d.get('onLoginPage'), d.get('userArea'), d.get('hasLogout'), d.get('vip')))
    if args.status:
        return

    domains = [c['domain'] for c in SITES.values()] + (args.domain or [])
    cookies = [c for c in all_cookies(args.port)
               if any(c.get('domain', '').lstrip('.').endswith(dm) for dm in domains)]
    state = {
        'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'port': args.port,
        'cookies': [{
            'name': c.get('name'), 'value': c.get('value'),
            'domain': c.get('domain'), 'path': c.get('path', '/'),
            'expires': c.get('expires'), 'httpOnly': c.get('httpOnly'),
            'secure': c.get('secure'),
        } for c in cookies],
        'origins': [],
    }
    print('\ncookie 条数: %d（域名: %s）' % (
        len(cookies), ', '.join(sorted({c.get('domain') for c in cookies}))))
    for c in cookies:
        e = c.get('expires')
        exp = 'session' if (e in (-1, None)) else time.strftime('%Y-%m-%d %H:%M', time.localtime(e))
        print('  %-28s %-16s 到期 %s' % (c.get('domain'), c.get('name'), exp))
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        print('saved', args.out, '（敏感文件，禁止提交）')


if __name__ == '__main__':
    main()
