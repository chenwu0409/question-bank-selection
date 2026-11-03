# -*- coding: utf-8 -*-
"""启动专用 Chrome（CDP 端口），登录态存在专用 user-data-dir 里，可复用。

用法：
  python launch_chrome.py --profile <profile目录> [--port 9222] [--url https://www.chujuan.cn/]

注意（实测）：
  - 在沙箱内启动，Chrome 会随父 shell 结束被回收（CDP 端口拒绝连接）。
    解决办法：用 WMI 方式创建进程，让它脱离父进程生命周期：
      Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList '<chrome路径>','--remote-debugging-port=9222',...
    或在沙箱外执行本脚本。
  - 内嵌浏览器（Trae 自带）不能用于登录态抓取：标签页属上层 IDE 会话，
    代理会话报 "Browser operation belongs to an inactive execution round"。
"""
import io
import sys
import os
import time
import json
import argparse
import urllib.request
import subprocess

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CANDIDATES = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]


def find_chrome():
    for p in CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def cdp_alive(port):
    try:
        v = json.load(urllib.request.urlopen('http://127.0.0.1:%d/json/version' % port, timeout=4))
        return v.get('Browser')
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description='启动带 CDP 端口的专用 Chrome')
    ap.add_argument('--profile', required=True, help='专用 user-data-dir 目录（持久化登录态）')
    ap.add_argument('--port', type=int, default=9222)
    ap.add_argument('--url', default='https://www.chujuan.cn/')
    ap.add_argument('--chrome', default=None, help='chrome 可执行文件路径（默认自动查找）')
    ap.add_argument('--timeout', type=int, default=30)
    args = ap.parse_args()

    already = cdp_alive(args.port)
    if already:
        print('CDP_ALREADY_UP', already)
        return

    chrome = args.chrome or find_chrome()
    if not chrome:
        print('CHROME_NOT_FOUND: 未找到 Chrome/Edge，请用 --chrome 指定路径')
        return

    os.makedirs(args.profile, exist_ok=True)
    argv = [chrome,
            '--remote-debugging-port=%d' % args.port,
            '--user-data-dir=' + args.profile,
            '--no-first-run',
            '--no-default-browser-check',
            args.url]
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    p = subprocess.Popen(argv, creationflags=flags, close_fds=True)
    print('launched pid', p.pid)

    t0 = time.time()
    while time.time() - t0 < args.timeout:
        time.sleep(1.5)
        b = cdp_alive(args.port)
        if b:
            print('CDP_OK', b, 'after %.1fs' % (time.time() - t0))
            print('profile:', args.profile)
            print('下一步：让用户在这个窗口登录一次，登录态会留在 profile 里复用')
            return
    print('CDP_FAIL: 端口 %d 未就绪。若本进程在沙箱内，Chrome 会被回收，'
          '请改用沙箱外启动或 Invoke-WmiMethod -Class Win32_Process -Name Create' % args.port)


if __name__ == '__main__':
    main()
