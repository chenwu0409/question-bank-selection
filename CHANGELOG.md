# Changelog

## 1.1.0 — 2026-11-03

补齐 P9-b 飞书入库：此前 SKILL.md 与 references/三站检索SOP.md 只写到 items.ndjson 本地入库，飞书多维表格（正式题库）的入库步骤仅存在于外部文档，按 skill 执行会漏掉。

### 新增

- **scripts/push_lark.py** —— P9-b 飞书入库脚本：写题目库/检索与选题记录/训练任务库三张表；按去重键幂等（已存在即跳过）、自动编号回查（题目ID/任务ID 服务端分配后取回）、知识点/题目/任务一律解析成 record_id 真关联、题图自动补传；`--check` 验四表连通，`--dry-run` 预览不落库；失败输出 FAIL + 原因并退出码非 0。
- **assets/lark_manifest_template.json** —— push_lark.py 输入模板（questions / search_log / tasks 三段）。

### 变更

- **SKILL.md** —— 流程摘要加 P9-b；交付物加第 6 条「飞书入库（必做）」；脚本表加 push_lark.py；常见坑加 2 条 lark-cli 实测坑（`api --page-all` 进度行破坏 JSON、`auth status` 在凭据外部注入环境不可用）；实测基线加 push_lark 行。
- **references/三站检索SOP.md** —— P9 节后补完整 **P9-b 飞书入库** 章节（与主库 SOP 对齐）：落点与四张表 table_id、push_lark.py 用法、手工兜底命令、写入三张表字段清单、入库判定（含「检索与选题记录每轮必填」「凭据不可用要明确报告飞书未入库」）。
- **README.md** —— 目录结构/脚本用法/交付物/依赖/已知限制/未覆盖项同步 push_lark。

### 实测基线（2026-11-03）

`--check` 四表全 PASS（题目库 42 / 训练任务库 35 / 检索与选题记录 0 / 知识点库 118）；`--dry-run` 对已存在题正确判 skip，知识点编号/去重键/任务号全部解析为 record_id，未向飞书写入任何数据。正式写入分支未实跑（涉及线上数据，需用户批准）。

## 1.0.0 — 2026-11-03

初始封装。

### 新增

- **SKILL.md** —— 入口。触发条件、强制规则、三站速查、脚本索引、P0–P9 流程摘要、交付物定义、11 条常见坑、逐脚本实测基线。
- **references/三站检索SOP.md**（311 行）—— 三站统一 SOP：站点矩阵总览、P0–P9 每步的输入/输出/判定标准/预算耗时、用户交接协议 H1–H3、单步预算表与 5 条硬性退出规则、可复用资产清单、三站实测记录（附录 A）、今晚 6 题答案核对状态（附录 B）、skill 打包验收记录（附录 C）。
- **references/站点矩阵.md**（93 行）—— 九维对比表、选站决策、三站请求配方、参数速查、13 条已知限制。
- **scripts/（10 个，纯标准库）**
  - `preflight.py` —— P0 预检：站点可达、CDP 载体、答案墙、滑块频率、地区参数、目录可写、查重基准、CLI 环境，共 9 项，输出 PASS/FAIL/BLOCKED。
  - `launch_chrome.py` —— 启动专用 Chrome（CDP 9222 + 专用 user-data-dir），登录态持久化复用。
  - `cdp_client.py` —— 标准库 WebSocket 实现的 CDP 客户端：tabs / new / eval / nav / shot / text，含死页探测与 IIFE 自动包装。
  - `search_21cnjy.py` —— 二一检索：关键词 × 学科 × 页数，结果落候选池 JSON，支持广东试卷名筛选。
  - `fetch_21cnjy.py` —— 二一详情批量抓取：题干/小问/难度/试卷名解析 + 题图下载 + 答案通道 `access` 标注。
  - `probe_chujuan.py` —— 出卷网登录态复验 + 详情抓取 + 一手解析图与答案图下载。
  - `probe_jyeoo.py` —— 菁优检索墙判定 + 详情考点/答案/解答/来源/难度提取 + 题图下载。
  - `dedupe.py` —— 与 `items.ndjson` 查重，判「全新 / 疑似 / 重复」。
  - `verify_calc.py` —— 分数精确的独立验算：杠杆平衡、一元二次、面积极值、鞋带公式。
  - `build_html.py` —— 清单 JSON → 学生版/答案版 HTML，内置零答案泄漏自检（命中即退出码 2）。
- **assets/manifest_template.json** —— `build_html.py` 输入格式样例。

### 实测基线

全部脚本逐个实跑通过。代表数据：预检 6.7s（FAIL 0 / BLOCKED 2）、二一检索 5.7s 出 4 道广东杠杆题、详情抓取 3.9s、出卷网登录态 PASS 且一手解析图下载成功、菁优详情考点答案可提取而【解答】为空、负样本泄漏自检被拦截。

### 已知未覆盖

菁优网登录后完整【解答】正文、菁优广东覆盖度抽样、出卷网免费 vs VIP 答案可见性差异、触发准确率实测。
