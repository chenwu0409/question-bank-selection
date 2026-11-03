# -*- coding: utf-8 -*-
"""查重：把候选题与已入库题目比对，判断「全新 / 疑似 / 重复」。

用法：
  python dedupe.py --items items.ndjson --candidates pool.json [--top 3]
  python dedupe.py --items items.ndjson --text "题干文本……"     # 直接查一段题干

判定规则：
  - 题干归一化后完全相同          → 重复
  - 关键数字+主体词高度重合       → 疑似（需人工看题图）
  - 同卷名 + 同题型 + 相同考点词   → 疑似
  - 其余                          → 全新

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


def normalize(s):
    s = re.sub(r'<[^>]+>', ' ', str(s or ''))
    s = re.sub(r'\s+', '', s)
    return s


def fingerprint(s):
    return md5(normalize(s).encode('utf-8')).hexdigest()[:16]


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
        elif hits:
            verdict = '疑似'
        print('[%s] %s | %s' % (verdict, c.get('qid'), (c.get('paper') or '')[:44]))
        print('   ', stem[:110])
        for it, kind, score in hits[:args.top]:
            print('    - %s [%s %.2f] %s' % (kind, kind, score, describe(it)))
        print()


if __name__ == '__main__':
    main()
