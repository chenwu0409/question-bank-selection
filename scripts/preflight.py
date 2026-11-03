# -*- coding: utf-8 -*-
"""P0 环境与账号预检（三站统一，预算 5 分钟）。

用法：
  python preflight.py --root <工作目录> [--probe-qid 41511381] [--probe-kw 杠杆]

输出每项 PASS / FAIL / BLOCKED + 耗时 + 处置建议。
BLOCKED 表示「外部条件限制（登录/付费墙/地区参数不生效）」，不是脚本坏了。

依赖：仅标准库。
"""
import io
import sys
import os
import re
import time
import json
import argparse
import urllib.request
import urllib.parse

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')

SITES = {
    'chujuan': ('https://www.chujuan.cn', '出卷网'),
    'jyeoo': ('https://www.jyeoo.com', '菁优网'),
    '21cnjy': ('https://zujuan.21cnjy.com', '二一组卷网'),
}

GD_RE = re.compile('广东|广州|深圳|佛山|东莞|珠海|中山|惠州|清远|台山|潮州|汕头|汕尾|韶关|'
                   '梅州|揭阳|江门|肇庆|湛江|茂名|阳江|云浮|河源|顺德|南海|番禺|白云|增城|'
                   '花都|南沙|荔湾|黄埔|海珠|越秀|天河')

results = []


def rec(item, status, cost, note):
    results.append({'item': item, 'status': status, 'sec': round(cost, 1), 'note': note})
    print('[%s] %s (%.1fs) -- %s' % (status, item, cost, note))


def get(url, ref=None, timeout=30):
    h = {'User-Agent': UA}
    if ref:
        h['Referer'] = ref
    t = time.time()
    r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)
    return r.read().decode('utf-8', 'ignore'), time.time() - t


def visible_text(html):
    """去掉 script/style 后取可见文本，用于判断是否真的落在验证页（JS 里常含"安全验证"字样，会误报）"""
    t = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S | re.I)
    t = re.sub(r'<style[^>]*>.*?</style>', ' ', t, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', t)
    return re.sub(r'\s+', ' ', t)


VERIFY_MARKERS = ('请完成安全验证', '滑动验证', '拖动滑块', '请完成验证', '安全验证后', '验证码', 'captcha_verify')


def is_verify_page(html):
    t = visible_text(html)
    for m in VERIFY_MARKERS:
        if m in t:
            return True
    return False


def p_site_reach():
    for key, (base, name) in SITES.items():
        t0 = time.time()
        try:
            html, dt = get(base + '/', timeout=25)
            blocked = is_verify_page(html)
            rec('P0.1 站点可达 ' + name, 'BLOCKED' if blocked else 'PASS',
                time.time() - t0,
                'HTTP 200 %.1fs %dKB%s' % (dt, len(html) // 1024,
                                          '，落在验证页（需用户过一次滑块）' if blocked else ''))
        except Exception as e:
            rec('P0.1 站点可达 ' + name, 'FAIL', time.time() - t0,
                '不可达: %s → 请用户检查网络或换时段' % str(e)[:70])


def p_answer_wall(probe_qid):
    """二一详情页 access 字段 = 答案是否开放"""
    t0 = time.time()
    try:
        html, _ = get('https://zujuan.21cnjy.com/question/detail/%s' % probe_qid,
                      ref='https://zujuan.21cnjy.com')
        acc = re.search(r'"access"\s*:\s*(true|false)', html)
        val = acc.group(1) if acc else '未见'
        rec('P0.3 答案墙 二一组卷网', 'PASS' if val == 'true' else 'BLOCKED',
            time.time() - t0,
            'access=%s → 该站答案%s，交付前需声明"独立验算·非一手"' % (
                val, '可得' if val == 'true' else '被登录墙挡住'))
    except Exception as e:
        rec('P0.3 答案墙 二一组卷网', 'FAIL', time.time() - t0, str(e)[:70])


def p_slider(probe_kw):
    """3 连发探测验证频率。单次网络抖动不等于站点有滑块 → 至少 2 次成功才算有效样本。"""
    t0 = time.time()
    hits, block, errs = 0, 0, []
    for i in range(3):
        url = ('https://zujuan.21cnjy.com/question/search?xd=2&chid=6&content=%s&page=1'
               % urllib.parse.quote(probe_kw))
        try:
            html, _ = get(url, ref='https://zujuan.21cnjy.com/question/search', timeout=20)
            if 'SearchQuesResult' in html and len(html) > 20000:
                hits += 1
            elif is_verify_page(html):
                block += 1
        except Exception as e:
            errs.append(repr(e)[:50])
        time.sleep(0.5)

    ok_samples = hits + block
    if ok_samples < 2:
        st = 'FAIL'
        note = '网络异常 %d/3 次（%s）→ 无法判定滑块，先重试预检；不代表站点有验证' % (
            len(errs), (errs[0] if errs else ''))
    elif block == 0:
        st = 'PASS'
        note = '3 连发：正常 %d，疑似验证 %d → 无滑块' % (hits, block)
    else:
        st = 'BLOCKED'
        note = '3 连发：正常 %d，疑似验证 %d → 让用户在浏览器过一次滑块，禁止自研绕过' % (hits, block)
    rec('P0.4 滑块频率', st, time.time() - t0, note)


def p_region(probe_kw):
    t0 = time.time()
    try:
        url = ('https://zujuan.21cnjy.com/question/search?xd=2&chid=6&content=%s&district_id=19&page=1'
               % urllib.parse.quote(probe_kw))
        html, _ = get(url, ref='https://zujuan.21cnjy.com')
        titles = re.findall(r'"paper_title"\s*:\s*"([^"]*)"', html)
        gd = sum(1 for t in titles if GD_RE.search(t))
        if not titles:
            st = 'FAIL'
        elif gd == len(titles):
            st = 'PASS'
        else:
            st = 'BLOCKED'
        rec('P0.5 地区参数 district_id=19', st, time.time() - t0,
            '结果 %d/%d 为广东 → 不生效则改用试卷名本地正则筛选（既定方案）' % (gd, len(titles)))
    except Exception as e:
        rec('P0.5 地区参数 district_id=19', 'FAIL', time.time() - t0, str(e)[:70])


def p_cdp():
    t0 = time.time()
    try:
        v = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json/version', timeout=5))
        rec('P0.2 CDP 登录态载体', 'PASS', time.time() - t0,
            '%s 已运行 → 出卷网/菁优网登录态抓取可用' % v.get('Browser'))
    except Exception as e:
        rec('P0.2 CDP 登录态载体', 'BLOCKED', time.time() - t0,
            'CDP 9222 未就绪 (%s) → 需先跑 launch_chrome.py；沙箱内启动会被回收，'
            '改沙箱外或 WMI 创建进程' % str(e)[:50])


def p_writable(root):
    t0 = time.time()
    try:
        d = os.path.join(root, 'tmp')
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, '.preflight_probe.tmp')
        open(probe, 'w').write('x')
        os.remove(probe)
        rec('P0.7 目录可写', 'PASS', time.time() - t0, '%s 可写可删' % root)
    except Exception as e:
        rec('P0.7 目录可写', 'FAIL', time.time() - t0,
            '%s → 请用户加沙箱白名单' % str(e)[:60])


def p_dedupe_base(root):
    t0 = time.time()
    p = os.path.join(root, 'items.ndjson')
    n = 0
    if os.path.exists(p):
        n = sum(1 for line in open(p, encoding='utf-8') if line.strip())
    rec('P0.8 查重基准 items.ndjson', 'PASS' if n > 0 else 'FAIL', time.time() - t0,
        '%d 行%s' % (n, '' if n > 0 else ' → 缺失则不能承诺查重，请用户从飞书导出'))


def p_cli_env():
    t0 = time.time()
    miss = []
    for m in ('PIL', 'numpy'):
        try:
            __import__(m)
        except Exception:
            miss.append(m)
    rec('P0.9 CLI 环境', 'PASS' if not miss else 'FAIL', time.time() - t0,
        'py %s；缺 %s → 只用标准库（题图复核改用原图 + 人工放大）'
        % (sys.version.split()[0], ','.join(miss) or '无'))


def main():
    ap = argparse.ArgumentParser(description='P0 环境与账号预检')
    ap.add_argument('--root', default=os.getcwd(), help='工作目录（含 items.ndjson / tmp）')
    ap.add_argument('--probe-qid', default='41511381', help='已知可抓的详情页样本')
    ap.add_argument('--probe-kw', default='杠杆 平衡', help='已知可命中的检索词')
    args = ap.parse_args()

    t_all = time.time()
    p_cdp()
    p_site_reach()
    p_answer_wall(args.probe_qid)
    p_slider(args.probe_kw)
    p_region(args.probe_kw)
    p_writable(args.root)
    p_dedupe_base(args.root)
    p_cli_env()

    print('\n== P0.6 模型视觉能力需 Agent 用 Read 实测题图，不在本脚本内 ==')
    bad = [r for r in results if r['status'] == 'FAIL']
    blocked = [r for r in results if r['status'] == 'BLOCKED']
    print('\n== 预检完成，总耗时 %.1fs：FAIL %d 项，BLOCKED %d 项 =='
          % (time.time() - t_all, len(bad), len(blocked)))
    if bad:
        print('FAIL 项必须先处理或按降级方案继续：')
        for r in bad:
            print('  -', r['item'], '::', r['note'])
    if blocked:
        print('BLOCKED 项需在交付物中如实标注：')
        for r in blocked:
            print('  -', r['item'], '::', r['note'])


if __name__ == '__main__':
    main()
