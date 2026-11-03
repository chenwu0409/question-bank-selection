# -*- coding: utf-8 -*-
"""P9-b 飞书入库：把选题结果写入多维表格三张表（题目库/检索与选题记录/训练任务库）。

用法：
  python push_lark.py --check                        # 只验证 lark-cli 连通与四张表可达
  python push_lark.py --manifest lark_manifest.json --dry-run   # 预览将写入的内容，不落库
  python push_lark.py --manifest lark_manifest.json  # 正式写入 + 回查

幂等：按「去重键」查题目库，已存在则跳过创建（只补传缺失题图），不会重复入库。
题目ID/任务ID 是自动编号字段，由服务端分配；写入后回查取得并打印。
知识点/题目/任务链接一律解析为 record_id 真关联，不写纯文本。
任何一步失败：打印 FAIL + 原因，退出码非 0，不静默跳过。

manifest 格式见 assets/lark_manifest_template.json。依赖：标准库 + lark-cli（凭据外部注入）。
"""
import io
import sys
import os
import json
import time
import argparse
import subprocess

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

APP_TOKEN = 'AWswbQsLQajsaMsvVQmcSyz3nPc'
T_QUESTIONS = 'tblFlwLDZkzQX2Wq'   # 题目库
T_TASKS = 'tblFEVEPllFOztXp'       # 训练任务库
T_SEARCH = 'tblS8boB3Zm90SHg'      # 检索与选题记录
T_KPS = 'tblpUPaolJA7BL70'         # 知识点库

TABLE_NAMES = {T_QUESTIONS: '题目库', T_TASKS: '训练任务库',
               T_SEARCH: '检索与选题记录', T_KPS: '知识点库'}


def lark(args_list, timeout=120):
    """跑一条 lark-cli，返回解析后的 JSON dict；失败抛 RuntimeError。"""
    try:
        p = subprocess.run(['lark-cli'] + args_list, capture_output=True,
                           text=True, encoding='utf-8', timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError('lark-cli 不在 PATH → 飞书未入库，请确认 lark 插件已安装')
    out = (p.stdout or '') + (p.stderr or '')
    try:
        d = json.loads(out)
    except Exception:
        raise RuntimeError('lark-cli 输出无法解析: %s' % out[:200])
    if not d.get('ok'):
        err = d.get('error') or {}
        raise RuntimeError('lark-cli 调用失败(%s/%s): %s' % (
            err.get('type'), err.get('subtype'), err.get('message', '')[:200]))
    return d


def list_all_records(tid):
    """手动分页拉全表记录（--page-all 会混入进度行，破坏 JSON 解析，不用）。"""
    items = []
    token = None
    while True:
        params = {'page_size': 500}
        if token:
            params['page_token'] = token
        d = lark(['api', 'GET',
                  '/open-apis/bitable/v1/apps/%s/tables/%s/records' % (APP_TOKEN, tid),
                  '--params', json.dumps(params)])
        data = d['data']
        items += data.get('items') or []
        token = data.get('page_token')
        if not data.get('has_more') or not token:
            break
    return items


def build_index(items, key_field, id_field=None):
    idx = {}
    for it in items:
        k = it['fields'].get(key_field)
        if k is None:
            continue
        idx[str(k)] = it
    return idx


def link_val(record_id):
    return [{'id': record_id}]


def do_check():
    ok = True
    for tid, name in TABLE_NAMES.items():
        t0 = time.time()
        try:
            items = list_all_records(tid)
            print('[PASS] %s 可达，%d 条 (%.1fs)' % (name, len(items), time.time() - t0))
        except Exception as e:
            ok = False
            print('[FAIL] %s: %s → 飞书未入库，先修复凭据/lark-cli' % (name, e))
    return 0 if ok else 1


def resolve_kp_ids(kp_codes, kp_idx):
    ids = []
    for code in kp_codes or []:
        rec = kp_idx.get(str(code))
        if not rec:
            raise RuntimeError('知识点库找不到编号 %s → 先在知识点库补录或用 record_id' % code)
        ids.append(rec['record_id'])
    return ids


def resolve_question_ids(keys, q_idx_by_dedup):
    ids = []
    for k in keys or []:
        rec = q_idx_by_dedup.get(str(k))
        if not rec:
            raise RuntimeError('题目库找不到去重键 %s → 确认该题已入库' % k)
        ids.append(rec['record_id'])
    return ids


def push_questions(manifest, q_idx, kp_idx, dry):
    results = []
    for q in manifest.get('questions', []):
        dedup = str(q.get('去重键') or '').strip()
        if not dedup:
            raise RuntimeError('题目缺少「去重键」字段: %s' % q.get('题目名称', '?'))
        fields = {
            '题目名称': q.get('题目名称', ''),
            '题干': q.get('题干', ''),
            '学科': [q['学科']] if q.get('学科') else None,
            '年级': [q['年级']] if q.get('年级') else None,
            '章节': q.get('章节'),
            '题型': [q['题型']] if q.get('题型') else None,
            '难度': [q['难度']] if q.get('难度') else None,
            '题目来源': q.get('题目来源'),
            '年份': int(q['年份']) if q.get('年份') else None,
            '来源链接': {'link': q['来源链接'], 'text': q.get('来源链接文字') or q['来源链接']}
                        if q.get('来源链接') else None,
            '标准答案': q.get('标准答案'),
            '解题解析': q.get('解题解析'),
            '考查方法': q.get('考查方法'),
            '去重键': dedup,
            '审核状态': [q.get('审核状态', '待审核')],
            '训练状态': [q.get('训练状态', '未用')],
            '风险标记': q.get('风险标记'),
            '审核意见与评估明细': q.get('审核意见与评估明细'),
            '关联知识点': [{'id': r} for r in resolve_kp_ids(q.get('关联知识点'), kp_idx)],
        }
        fields = {k: v for k, v in fields.items() if v not in (None, [], {})}
        existing = q_idx.get(dedup)
        action = 'skipped(已存在)' if existing else 'created'
        if dry:
            print('[DRY] 题目 %s -> %s' % (dedup, json.dumps(fields, ensure_ascii=False)[:300]))
            results.append({'去重键': dedup, 'action': action})
            continue
        if existing:
            print('[SKIP] %s 已在题目库（%s）' % (dedup, existing['fields'].get('题目ID')))
        else:
            lark(['base', '+record-upsert', '--base-token', APP_TOKEN,
                  '--table-id', T_QUESTIONS, '--json', json.dumps(fields, ensure_ascii=False)])
            print('[OK] 写入题目 %s' % dedup)
        results.append({'去重键': dedup, 'action': action})
    if dry:
        return results
    # 统一回查一次：拿自动编号的题目ID、record_id，并补传缺失题图
    fresh = build_index(list_all_records(T_QUESTIONS), '去重键')
    for r in results:
        rec = fresh.get(r['去重键'])
        q = next(x for x in manifest.get('questions', []) if str(x.get('去重键')) == r['去重键'])
        r['题目ID'] = rec['fields'].get('题目ID') if rec else None
        r['record_id'] = rec['record_id'] if rec else None
        imgs = [p for p in (q.get('题目图片') or []) if p]
        have = {a.get('name') for a in (rec['fields'].get('题目图片') or [])} if rec else set()
        todo = [p for p in imgs if os.path.basename(p) not in have]
        if rec and todo:
            args = ['base', '+record-upload-attachment', '--base-token', APP_TOKEN,
                    '--table-id', T_QUESTIONS, '--record-id', rec['record_id'],
                    '--field-id', '题目图片']
            for pth in todo:
                args += ['--file', pth]
            lark(args, timeout=300)
            print('[OK] %s 题图 %d 张已上传' % (r['题目ID'], len(todo)))
    return results


def push_search_log(manifest, q_idx, kp_idx, task_idx, dry):
    s = manifest.get('search_log')
    if not s:
        return None
    fields = {
        '检索批次ID': s.get('检索批次ID') or ('SB-' + time.strftime('%Y%m%d%H%M')),
        '日期': s.get('日期'),
        '训练目标': s.get('训练目标'),
        '检索平台': s.get('检索平台'),
        '原始提示词': s.get('原始提示词'),
        '提示词版本': s.get('提示词版本'),
        '筛选条件': s.get('筛选条件'),
        '结果数量': int(s['结果数量']) if s.get('结果数量') is not None else None,
        '候选题链接与待核实资料': s.get('候选题链接与待核实资料'),
        '每题评估与淘汰原因': s.get('每题评估与淘汰原因'),
        '检索限制': s.get('检索限制'),
        '关联知识点': [{'id': r} for r in resolve_kp_ids(s.get('关联知识点'), kp_idx)],
        '关联训练任务': [{'id': task_idx[t]['record_id']} for t in s.get('关联训练任务', [])
                         if t in task_idx],
        '候选题': [{'id': r} for r in resolve_question_ids(s.get('候选题去重键'), q_idx)],
        '最终入选题': [{'id': r} for r in resolve_question_ids(s.get('最终入选题去重键'), q_idx)],
    }
    fields = {k: v for k, v in fields.items() if v not in (None, [], {})}
    if dry:
        print('[DRY] 检索记录 -> %s' % json.dumps(fields, ensure_ascii=False)[:300])
        return {'检索批次ID': fields.get('检索批次ID'), 'action': 'dry'}
    d = lark(['base', '+record-upsert', '--base-token', APP_TOKEN,
              '--table-id', T_SEARCH, '--json', json.dumps(fields, ensure_ascii=False)])
    print('[OK] 检索与选题记录已写入（%s）' % fields.get('检索批次ID'))
    return {'检索批次ID': fields.get('检索批次ID'), 'action': 'created'}


def push_tasks(manifest, q_idx, kp_idx, dry):
    results = []
    for t in manifest.get('tasks', []):
        fields = {
            '任务名称': t.get('任务名称', ''),
            '训练日期': t.get('训练日期'),
            '学科': [t['学科']] if t.get('学科') else None,
            '训练目标': t.get('训练目标'),
            '计划题量': int(t['计划题量']) if t.get('计划题量') is not None else None,
            '目标正确率': float(t['目标正确率']) if t.get('目标正确率') is not None else None,
            '预计用时(分钟)': int(t['预计用时(分钟)']) if t.get('预计用时(分钟)') is not None else None,
            '任务状态': [t.get('任务状态', '未开始')],
            '优先级与选择理由': t.get('优先级与选择理由'),
            '目标难度与达成标准': t.get('目标难度与达成标准'),
            '完成期限': t.get('完成期限'),
            '关联知识点': [{'id': r} for r in resolve_kp_ids(t.get('关联知识点'), kp_idx)],
            '关联题目': [{'id': r} for r in resolve_question_ids(t.get('关联题目去重键'), q_idx)],
        }
        fields = {k: v for k, v in fields.items() if v not in (None, [], {})}
        if dry:
            print('[DRY] 任务 %s -> %s' % (t.get('任务名称'), json.dumps(fields, ensure_ascii=False)[:300]))
            results.append({'任务名称': t.get('任务名称'), 'action': 'dry'})
            continue
        d = lark(['base', '+record-upsert', '--base-token', APP_TOKEN,
                  '--table-id', T_TASKS, '--json', json.dumps(fields, ensure_ascii=False)])
        print('[OK] 训练任务已写入：%s' % t.get('任务名称'))
        results.append({'任务名称': t.get('任务名称'), 'action': 'created'})
    return results


def main():
    ap = argparse.ArgumentParser(description='P9-b 飞书入库')
    ap.add_argument('--check', action='store_true', help='只验证 lark-cli 与四张表连通')
    ap.add_argument('--manifest', help='入库清单 JSON（格式见 assets/lark_manifest_template.json）')
    ap.add_argument('--dry-run', action='store_true', help='预览将写入内容，不落库')
    ap.add_argument('--out', help='结果 JSON 输出路径（默认打印）')
    args = ap.parse_args()

    if args.check:
        sys.exit(do_check())
    if not args.manifest:
        ap.error('需要 --manifest 或 --check')

    manifest = json.load(open(args.manifest, encoding='utf-8'))
    try:
        qs = list_all_records(T_QUESTIONS)
        kps = list_all_records(T_KPS)
        ts = list_all_records(T_TASKS)
    except Exception as e:
        print('[FAIL] 飞书读取失败 → 飞书未入库: %s' % e)
        sys.exit(1)
    q_idx = build_index(qs, '去重键')
    kp_idx = build_index(kps, '知识点ID')
    task_idx = build_index(ts, '任务ID')

    res = {'questions': push_questions(manifest, q_idx, kp_idx, args.dry_run)}
    # 题目/任务写入后重拉索引，供检索记录的真关联解析（顺序：题目→任务→检索记录）
    res['tasks'] = push_tasks(manifest, q_idx, kp_idx, args.dry_run)
    if not args.dry_run:
        q_idx = build_index(list_all_records(T_QUESTIONS), '去重键')
        task_idx = build_index(list_all_records(T_TASKS), '任务ID')
    res['search_log'] = push_search_log(manifest, q_idx, kp_idx, task_idx, args.dry_run)

    out = json.dumps(res, ensure_ascii=False, indent=1)
    if args.out:
        open(args.out, 'w', encoding='utf-8').write(out)
        print('[OK] 结果已写 %s' % args.out)
    else:
        print(out)
    if args.dry_run:
        print('\n(dry-run：未向飞书写入任何数据)')


if __name__ == '__main__':
    main()
