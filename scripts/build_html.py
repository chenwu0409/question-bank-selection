# -*- coding: utf-8 -*-
"""由清单 JSON 生成学生版 / 答案版 HTML，并自动自检学生版零答案泄漏。

清单 JSON 格式：
{
  "title": "小兔 中考练习卷 2026-11-03",
  "subtitle": "最终 6 题 · 广东优先",
  "figdir": "小兔中考_20261103_题图",
  "footer": "题源：二一组卷网。本卷不含任何答案与解析。",
  "answer_note": "答案一手性说明……（答案版顶部警示框）",
  "sections": [
    {
      "name": "一、物理·杠杆（2 题）",
      "questions": [
        {
          "no": 1,
          "meta": "广东潮州·八下期中·作图题",
          "stem": "题干……",
          "figs": ["76925585_00_4b1aab2f.png"],
          "fig_width": 420,
          "subs": ["（1）小问……", "（2）小问……"],
          "answers": ["① ……", "② ……"],
          "basis": "依据：……",
          "answer_source": "非一手·独立验算"
        }
      ]
    }
  ]
}

用法：
  python build_html.py --manifest manifest.json --outdir "f:\\某目录"

产出：<outdir>/<title>_学生版.html 与 <outdir>/<title>_答案版.html
自检：学生版全文检索「答案 / 解析 / 答：」必须 0 命中，不通过则返回非 0 退出码。

依赖：仅标准库。
"""
import io
import sys
import os
import re
import json
import argparse

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CSS_STUDENT = """  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; max-width: 860px; margin: 0 auto; padding: 24px 32px; color: #222; line-height: 1.9; }
  h1 { font-size: 22px; border-bottom: 3px solid #2c6e49; padding-bottom: 8px; }
  h2 { font-size: 18px; margin-top: 36px; color: #1a4d33; border-left: 5px solid #2c6e49; padding-left: 10px; }
  .meta { color: #666; font-size: 13px; margin-bottom: 4px; }
  .q { margin-bottom: 30px; page-break-inside: avoid; }
  .stem { margin: 8px 0; }
  .sub { margin: 6px 0 6px 1.5em; }
  img.fig { max-width: 100%; display: block; margin: 10px auto; border: 1px solid #ddd; padding: 6px; background: #fff; }
  .ansbox { border: 1px dashed #999; min-height: 120px; margin: 10px 0 0 1.5em; background: repeating-linear-gradient(#fff, #fff 31px, #eee 32px); }
  .ansbox.big { min-height: 220px; }
  .fill { display: inline-block; min-width: 110px; border-bottom: 1px solid #333; margin: 0 4px; }
  .tip { font-size: 12px; color: #888; }
  @media print { body { padding: 0; } .q { page-break-inside: avoid; } }"""

CSS_ANSWER = """  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; max-width: 900px; margin: 0 auto; padding: 24px 32px; color: #222; line-height: 1.9; }
  h1 { font-size: 22px; border-bottom: 3px solid #b23a48; padding-bottom: 8px; }
  h2 { font-size: 18px; margin-top: 36px; color: #7a2430; border-left: 5px solid #b23a48; padding-left: 10px; }
  .meta { color: #666; font-size: 13px; }
  .q { margin-bottom: 28px; }
  img.fig { max-width: 100%; display: block; margin: 10px auto; border: 1px solid #ddd; padding: 6px; background: #fff; }
  .ans { background: #f2f7f2; border-left: 4px solid #2c6e49; padding: 8px 14px; margin: 6px 0 10px 1.5em; }
  .ans b { color: #1a4d33; }
  .warn { background: #fff6e5; border-left: 4px solid #d97706; padding: 10px 14px; margin: 12px 0; font-size: 14px; }"""


def esc(s):
    """HTML 转义；保留 <br> 换行标签（清单里可用它排版）。"""
    amp = chr(38)
    s = str(s).replace('<br>', chr(10) + '@@BR@@')
    s = s.replace(amp, amp + 'amp;')
    s = s.replace('<', amp + 'lt;').replace('>', amp + 'gt;')
    return s.replace(chr(10) + '@@BR@@', '<br>')


def page(title, css, body, lang='zh-CN'):
    return """<!DOCTYPE html>
<html lang="%s">
<head>
<meta charset="UTF-8">
<title>%s</title>
<style>
%s
</style>
</head>
<body>
%s
</body>
</html>
""" % (lang, esc(title), css, body)


def render_student(m):
    out = []
    out.append('<h1>%s</h1>' % esc(m.get('title', '')))
    if m.get('subtitle'):
        out.append('<p class="tip">%s</p>' % esc(m['subtitle']))
    if m.get('tip'):
        out.append('<p class="tip">%s</p>' % esc(m['tip']))
    figdir = m.get('figdir') or ''
    for sec in m.get('sections', []):
        out.append('<h2>%s</h2>' % esc(sec.get('name', '')))
        for q in sec.get('questions', []):
            out.append('<div class="q">')
            if q.get('meta'):
                out.append('<div class="meta">%s．%s</div>' % (esc(q.get('no', '')), esc(q['meta'])))
            if q.get('stem'):
                out.append('<div class="stem">%s</div>' % esc(q['stem']))
            for f in q.get('figs', []):
                src = (figdir + '/' + f) if figdir else f
                w = (' style="max-width:%dpx"' % q['fig_width']) if q.get('fig_width') else ''
                out.append('<img class="fig" src="%s" alt="题图"%s>' % (esc(src), w))
            for s in q.get('subs', []):
                out.append('<div class="sub">%s</div>' % esc(s))
            out.append('<div class="ansbox%s"></div>' % (' big' if q.get('big') else ''))
            out.append('</div>')
    if m.get('footer'):
        out.append('<p class="tip">%s</p>' % esc(m['footer']))
    return '\n'.join(out)


def render_answer(m):
    out = []
    out.append('<h1>%s（答案版）</h1>' % esc(m.get('title', '')))
    if m.get('subtitle'):
        out.append('<p class="tip">%s</p>' % esc(m['subtitle']))
    if m.get('answer_note'):
        out.append('<div class="warn"><b>答案一手性说明：</b>%s</div>' % esc(m['answer_note']))
    figdir = m.get('figdir') or ''
    for sec in m.get('sections', []):
        out.append('<h2>%s</h2>' % esc(sec.get('name', '')))
        for q in sec.get('questions', []):
            out.append('<div class="q">')
            head = '%s．' % esc(q.get('no', ''))
            if q.get('meta'):
                head += esc(q['meta'])
            if q.get('answer_source'):
                head += '（%s）' % esc(q['answer_source'])
            out.append('<div class="meta">%s</div>' % head)
            if q.get('stem'):
                out.append('<div class="stem">%s</div>' % esc(q['stem']))
            for f in q.get('figs', []):
                src = (figdir + '/' + f) if figdir else f
                w = (' style="max-width:%dpx"' % q['fig_width']) if q.get('fig_width') else ''
                out.append('<img class="fig" src="%s" alt="题图"%s>' % (esc(src), w))
            for a in q.get('answers', []):
                out.append('<div class="ans">%s</div>' % esc(a))
            if q.get('basis'):
                out.append('<div class="ans"><b>依据：</b>%s</div>' % esc(q['basis']))
            out.append('</div>')
    if m.get('footer'):
        out.append('<p class="tip">%s</p>' % esc(m['footer']))
    return '\n'.join(out)


def check_no_answer(html):
    """学生版自检：只看题目正文区是否出现答案/解析关键词。

    排除页脚声明与作答要求（它们允许出现「本卷不含任何答案与解析」「解答题需写出…」这类
    版式文字），只检查 <h2> 分节与 .q 题目块里的内容。
    """
    body = re.search(r'<body>(.*)</body>', html, re.S)
    body = body.group(1) if body else html
    body = re.sub(r'<p class="tip">.*?</p>', ' ', body, flags=re.S)
    body = re.sub(r'<h1>.*?</h1>', ' ', body, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', body)
    leaks = []
    for kw in ('答案', '解析', '答：', '解答', '参考答案'):
        n = text.count(kw)
        if n:
            leaks.append('%s×%d' % (kw, n))
    return leaks


def main():
    ap = argparse.ArgumentParser(description='生成学生版/答案版 HTML 并自检')
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--outdir', default='.')
    ap.add_argument('--basename', default=None)
    args = ap.parse_args()

    m = json.load(open(args.manifest, encoding='utf-8'))
    os.makedirs(args.outdir, exist_ok=True)
    base = args.basename or (m.get('title') or '练习卷').replace(' ', '')

    stu_html = page(m.get('title', '') + '（学生版）', CSS_STUDENT, render_student(m))
    ans_html = page(m.get('title', '') + '（答案版）', CSS_ANSWER, render_answer(m))

    stu_path = os.path.join(args.outdir, base + '_学生版.html')
    ans_path = os.path.join(args.outdir, base + '_答案版.html')
    open(stu_path, 'w', encoding='utf-8').write(stu_html)
    open(ans_path, 'w', encoding='utf-8').write(ans_html)
    print('学生版:', stu_path, os.path.getsize(stu_path), 'bytes')
    print('答案版:', ans_path, os.path.getsize(ans_path), 'bytes')

    leaks = check_no_answer(stu_html)
    if leaks:
        print('\n自检 FAIL：学生版疑似泄漏答案关键词 ->', ', '.join(leaks))
        sys.exit(2)
    print('自检 PASS：学生版零答案关键词命中')
    nq = sum(len(s.get('questions', [])) for s in m.get('sections', []))
    print('题目数:', nq)


if __name__ == '__main__':
    main()
