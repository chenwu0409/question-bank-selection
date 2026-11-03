# -*- coding: utf-8 -*-
"""CDP 客户端：仅用标准库实现 WebSocket，直连专用 Chrome（--remote-debugging-port=9222）。

子命令：
  tabs                          列出所有可 attach 的标签页
  new <url>                     新建标签页并打开 url
  eval "<js>"                   在指定标签页执行 JS（顶层 return），打印 JSON
  nav <url>                     在指定标签页导航
  shot <path>                   截图保存到 path
  text "<要等的文字>"            等待页面出现该文字，返回 True/False

通用参数：
  --tab <子串>   选中 url 含该子串的标签页（默认第一个 page 标签）
  --port 9222    CDP 端口
  --wait 2500    nav 后等待毫秒

示例：
  python cdp_client.py tabs
  python cdp_client.py --tab chujuan eval "return {title: document.title, url: location.href}"
  python cdp_client.py --tab chujuan eval "return await (async()=>{const r=await fetch('/question/detail/41511381',{credentials:'include'});const t=await r.text();return {s:r.status,len:t.length};})()"
"""
import io
import sys
import json
import time
import socket
import base64
import hashlib
import struct
import re
import argparse
import urllib.request
import urllib.parse

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DEFAULT_PORT = 9222


def host_of(port):
    return 'http://127.0.0.1:%d' % port


def http(path, port=DEFAULT_PORT, method='GET'):
    req = urllib.request.Request(host_of(port) + path, method=method)
    return json.load(urllib.request.urlopen(req, timeout=15))


def tabs(port=DEFAULT_PORT):
    return http('/json', port)


def find_tab(sub=None, index=0, port=DEFAULT_PORT):
    """按 url 子串取标签页（不做响应探测）；找不到返回 None"""
    ts = [t for t in tabs(port) if t.get('type') == 'page']
    if sub:
        for t in ts:
            if sub in (t.get('url') or ''):
                return t
    return ts[index] if ts else None


def pick_tab(sub=None, index=0, port=DEFAULT_PORT, probe=True, fallback_any=True):
    """选标签页；probe=True 时跳过无响应的死页（卡死的渲染进程会让 Runtime.evaluate 永久超时）。

    fallback_any=False 时只在 url 含 sub 的标签页里挑；没有匹配的可用页就抛错，
    避免"在 example.com 上测出登录态 FAIL"这种误判。
    """
    ts = [t for t in tabs(port) if t.get('type') == 'page']
    cands = [t for t in ts if (not sub) or sub in (t.get('url') or '')]
    if fallback_any and sub:
        cands += [t for t in ts if t not in cands]
    if not cands:
        raise RuntimeError('没有可用标签页（匹配 %r）；先跑 launch_chrome.py 启动专用 Chrome' % sub)
    if not probe:
        return cands[index] if index < len(cands) else cands[0]
    for t in cands:
        try:
            c = CDP(t['webSocketDebuggerUrl'])
            try:
                c.js('return 1', timeout=8)
                return t
            finally:
                c.close()
        except Exception:
            continue
    raise RuntimeError('匹配的标签页都无响应（渲染进程卡死）：请关闭对应窗口或重启专用 Chrome')


def new_tab(url, port=DEFAULT_PORT):
    q = urllib.parse.quote(url, safe='')
    try:
        return http('/json/new?' + q, port, method='PUT')
    except Exception:
        return http('/json/new?' + q, port)


def close_tab(tid, port=DEFAULT_PORT):
    try:
        http('/json/close/' + tid, port)
    except Exception:
        pass


def ws_connect(url):
    m = re.match(r'ws://([^:/]+):(\d+)(/.*)', url)
    if not m:
        raise RuntimeError('bad ws url: ' + url)
    host, port, path = m.group(1), int(m.group(2)), m.group(3)
    s = socket.create_connection((host, port), timeout=40)
    key = base64.b64encode(hashlib.sha1(str(id(s)).encode()).digest()[:16]).decode()
    s.sendall(('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
               'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n'
               % (path, host, port, key)).encode())
    resp = b''
    while b'\r\n\r\n' not in resp:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError('handshake closed')
        resp += chunk
    if b'101' not in resp.split(b'\r\n')[0]:
        raise RuntimeError('handshake fail: ' + resp.split(b'\r\n')[0].decode())
    return s


def ws_send(s, data):
    payload = data.encode('utf-8')
    hdr = bytearray([0x81])
    n = len(payload)
    mask = b'\x33\x22\x11\x00'
    if n < 126:
        hdr.append(0x80 | n)
    elif n < 65536:
        hdr.append(0x80 | 126)
        hdr += struct.pack('>H', n)
    else:
        hdr.append(0x80 | 127)
        hdr += struct.pack('>Q', n)
    hdr += mask
    s.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def _exact(s, n):
    buf = b''
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c:
            raise RuntimeError('ws closed')
        buf += c
    return buf


def ws_recv(s):
    b1, b2 = _exact(s, 2)
    ln = b2 & 0x7F
    if ln == 126:
        ln = struct.unpack('>H', _exact(s, 2))[0]
    elif ln == 127:
        ln = struct.unpack('>Q', _exact(s, 8))[0]
    payload = _exact(s, ln)
    while not (b1 & 0x80):
        b1, b2 = _exact(s, 2)
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack('>H', _exact(s, 2))[0]
        elif ln == 127:
            ln = struct.unpack('>Q', _exact(s, 8))[0]
        payload += _exact(s, ln)
    return payload


class CDP(object):
    def __init__(self, ws_url):
        self.s = ws_connect(ws_url)
        self.id = 0

    def call(self, method, params=None, timeout=60):
        self.id += 1
        mid = self.id
        ws_send(self.s, json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        t0 = time.time()
        while time.time() - t0 < timeout:
            msg = json.loads(ws_recv(self.s))
            if msg.get('id') == mid:
                if 'error' in msg:
                    raise RuntimeError('%s: %s' % (method, str(msg['error'])[:200]))
                return msg.get('result', {})
        raise RuntimeError('timeout ' + method)

    def js(self, expr, timeout=60):
        # Runtime.evaluate 顶层不接受 return，统一包成 IIFE
        body = expr.strip()
        if body.startswith('return '):
            expr = '(function(){ %s })()' % body
        r = self.call('Runtime.evaluate',
                      {'expression': expr, 'returnByValue': True, 'awaitPromise': True},
                      timeout)
        res = r.get('result', {})
        if res.get('subtype') == 'error':
            raise RuntimeError(res.get('description', '')[:300])
        return res.get('value')

    def nav(self, url, wait_ms=2500):
        self.call('Page.enable')
        self.call('Page.navigate', {'url': url})
        time.sleep(wait_ms / 1000.0)

    def wait_text(self, text, timeout=25):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.js('return document.body && document.body.innerText.includes(%s)'
                           % json.dumps(text)):
                    return True
            except Exception:
                pass
            time.sleep(1.0)
        return False

    def screenshot(self, path):
        r = self.call('Page.captureScreenshot', {'format': 'png'})
        open(path, 'wb').write(base64.b64decode(r['data']))
        return path

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def pick_arg_tab(args):
    return pick_tab(args.tab, args.index, args.port)


def main():
    ap = argparse.ArgumentParser(description='CDP 客户端（标准库实现）')
    ap.add_argument('--tab', default=None, help='选中 url 含该子串的标签页')
    ap.add_argument('--index', type=int, default=0, help='未命中子串时取第几个 page 标签')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--wait', type=int, default=2500, help='nav 后等待毫秒')
    sub = ap.add_subparsers(dest='cmd')

    sub.add_parser('tabs')
    p_new = sub.add_parser('new')
    p_new.add_argument('url')
    p_eval = sub.add_parser('eval')
    p_eval.add_argument('expr')
    p_nav = sub.add_parser('nav')
    p_nav.add_argument('url')
    p_shot = sub.add_parser('shot')
    p_shot.add_argument('path')
    p_text = sub.add_parser('text')
    p_text.add_argument('text')

    args = ap.parse_args()
    if args.cmd == 'tabs':
        for t in tabs(args.port):
            if t.get('type') == 'page':
                print('%-38s %s' % (t.get('title', '')[:38], t.get('url')))
        return

    if args.cmd == 'new':
        t = new_tab(args.url, args.port)
        print(json.dumps({'id': t.get('id'), 'url': t.get('url')}, ensure_ascii=False))
        return

    tab = pick_arg_tab(args)
    cdp = CDP(tab['webSocketDebuggerUrl'])
    try:
        if args.cmd == 'eval':
            v = cdp.js(args.expr)
            print(json.dumps(v, ensure_ascii=False, indent=1))
        elif args.cmd == 'nav':
            cdp.nav(args.url, args.wait)
            print('navigated ->', args.url)
        elif args.cmd == 'shot':
            print('saved', cdp.screenshot(args.path))
        elif args.cmd == 'text':
            print('found' if cdp.wait_text(args.text) else 'NOT_FOUND')
    finally:
        cdp.close()


if __name__ == '__main__':
    main()
