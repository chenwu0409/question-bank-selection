# -*- coding: utf-8 -*-
"""查重：把候选题与已入库题目比对，判断「全新 / 疑似 / 重复」。

用法：
  python dedupe.py --items items.ndjson --candidates pool.json [--top 3]
  python dedupe.py --items items.ndjson --text "题干文本……"     # 直接查一段题干

判定规则：
  - 题干归一化后完全相同          → 重复
  - 关键数字+主体词高度重合       → 疑似（需人工看题图）
  - 同卷名 + 同题型 + 相同考点词   → 疑似
  - 数字归一化后题干完全相同       → 结构重复（同一题换数字，含跨站转载）
  - 型号要素集合完全相同且数字不同 → 结构重复（同一题型换数字，如 79m+1m 门与 42m+2m 门）
  - 其余                          → 全新

跨站去重：指纹只保留题干文字，抹掉 HTML 标签、站名水印和空白；数字归一化后再取指纹。
同一题在 21cnjy / 出卷网 / 菁优网重复出现时，按「重复 / 结构重复」拦截，不按新题计。

依赖：仅标准库。
"""
import io
import sys
import os
import re
import json
import argparse
from hashlib import md5

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

NUM_RE = re.compile(r'\d+(?:\.\d+)?')
STOP = set('的了和是在有与及或对为以则若如其中之上下左右前后个多少不无并且')

# 型号要素：同一组要素命中即视为同一题型骨架；数字和措辞可换。
MODEL_MARKERS = {
    '围栏': ('围栏', '篱笆', '栅栏', '墙'),
    '门': ('门',),
    '分割': ('隔', '分割', '分成', '补形', '两部分'),
    '矩形': ('矩形', '长方形', '正方形'),
    '面积': ('面积',),
    '二次函数': ('二次函数', '抛物线'),
    '反比例': ('反比例',),
    '一次函数': ('一次函数', '正比例'),
    '中点': ('中点',),
    '动点': ('动点', '运动'),
    '杠杆': ('杠杆', '力臂', '支点'),
    '电路转换': ('实物图', '电路图'),
    '装置': ('装置', '发生装置', '收集装置'),
    '化合价': ('化合价',),
    '催化剂': ('催化剂',),
    '控制变量': ('控制变量', '对比实验'),
}


def plain(s):
    return re.sub(r'<[^>]+>', ' ', str(s or ''))


def model_set(s):
    text = plain(s)
    return frozenset(name for name, words in MODEL_MARKERS.items()
                     if any(word in text for word in words))


def structural_duplicate(a, b):
    """同题型换数字：要素集合完全相同且至少命中两项。"""
    left, right = model_set(a), model_set(b)
    return len(left) >= 2 and left == right


def normalize(s):
    s = re.sub(r'<[^>]+>', ' ', str(s or ''))
    s = re.sub(r'\s+', '', s)
    return s


def fingerprint(s):
    return md5(normalize(s).encode('utf-8')).hexdigest()[:16]


SITE_NOISE = re.compile('组卷在线|菁优网|二一组卷网|21世纪教育网|试题篮|本题|来源[:：]|www\\.[a-z0-9.]+', re.I)


def numberless(s):
    s = re.sub(r'<[^>]+>', ' ', str(s or ''))
    s = SITE_NOISE.sub('', s)
    s = re.sub(r'\d+(?:\.\d+)?', '#', s)
    return re.sub(r'\s+', '', s)


def numberless_fingerprint(s):
    return md5(numberless(s).encode('utf-8')).hexdigest()[:16]


def numbers(s):
    return set(NUM_RE.findall(str(s or '')))


def keywords(s):
    s = re.sub(r'<[^>]+>', ' ', str(s or ''))
    out = set()
    for w in re.findall(r'[一-鿿]{2,4}', s):
        if w not in STOP:
            out.add(w)
    return out


def load_items(path):
    items = []
    if not os.path.exists(path):
        return items
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items


def item_stem(it):
    return it.get('题干') or it.get('题目名称') or it.get('题目ID') or ''


def compare(cand_stem, items):
    fp = fingerprint(cand_stem)
    nfp = numberless_fingerprint(cand_stem)
    cn = numbers(cand_stem)
    ck = keywords(cand_stem)
    hits = []
    for it in items:
        stem = item_stem(it)
        if not stem:
            continue
        if fingerprint(stem) == fp:
            hits.append((it, '重复', 1.0))
            continue
        if numberless_fingerprint(stem) == nfp and numbers(stem) != cn:
            hits.append((it, '结构重复', 0.95))
            continue
        if structural_duplicate(cand_stem, stem) and numbers(stem) != cn:
            hits.append((it, '结构重复', 0.9))
            continue
        inn = numbers(stem)
        ik = keywords(stem)
        num_j = len(cn & inn) / float(len(cn)) if cn else 0
        kw_j = len(ck & ik) / float(len(ck)) if ck else 0
        score = 0.6 * num_j + 0.4 * kw_j
        if score >= 0.75:
            hits.append((it, '疑似', score))
    hits.sort(key=lambda x: -x[2])
    return hits


def describe(it):
    return '%s | %s | %s' % (
        it.get('题目ID') or it.get('record_id') or '?',
        (it.get('题目来源') or it.get('来源链接') or '')[:50],
        (item_stem(it) or '')[:70])


def main():
    ap = argparse.ArgumentParser(description='题目查重')
    ap.add_argument('--items', default='items.ndjson', help='已入库基准（NDJSON）')
    ap.add_argument('--candidates', default=None, help='候选池 JSON（search_21cnjy.py 输出）')
    ap.add_argument('--text', default=None, help='直接查一段题干')
    ap.add_argument('--top', type=int, default=3)
    args = ap.parse_args()

    items = load_items(args.items)
    print('基准条目 %d 条（%s）\n' % (len(items), args.items))
    if not items:
        print('警告：基准为空，无法承诺查重')

    cands = []
    if args.text:
        cands.append({'qid': 'argv', 'title': args.text, 'paper': ''})
    elif args.candidates:
        cands = json.load(open(args.candidates, encoding='utf-8'))
    else:
        print('需要 --candidates 或 --text')
        return

    for c in cands[:40]:
        stem = c.get('title') or c.get('题干') or ''
        if not stem:
            continue
        hits = compare(stem, items)
        verdict = '全新'
        if hits and hits[0][1] == '重复':
            verdict = '重复'
        elif hits and hits[0][1] == '结构重复':
            verdict = '结构重复'
        elif hits:
            verdict = '疑似'
        print('[%s] %s | %s' % (verdict, c.get('qid'), (c.get('paper') or '')[:44]))
        print('   ', stem[:110])
        for it, kind, score in hits[:args.top]:
            print('    - %s [%s %.2f] %s' % (kind, kind, score, describe(it)))
        print()


if __name__ == '__main__':
    main()
