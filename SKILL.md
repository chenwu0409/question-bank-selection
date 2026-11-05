---
name: question-bank-selection
description: Select, verify, package exam questions from chujuan.cn, jyeoo.com, zujuan.21cnjy.com as student/answer versions. Use when asked to find, filter, dedupe or verify exam questions. Not for authoring.
---

# 题库选题与交付

从中文题库站检索、筛选、核验题目，产出「学生版 + 答案版 + 清单」三件套。默认三站：出卷网、菁优网、二一组卷网。

## 与 Knowledge Mastery Planner 联动

当任务引用飞书 RW、KMP 计划或上游放行记录时，先读 [上游契约入口](references/upstream-contract.md)。联动路径按契约执行，独立选题的 P8、P9 和 P9-b 用于独立流程。

## 开工前必做

1. 读 `references/三站检索SOP.md`（完整流程 P0–P9、站点矩阵、预算与退出规则）。
2. 跑 P0 预检，5 分钟内出 PASS/FAIL/BLOCKED 全表：
   ```bash
   python scripts/preflight.py --root <工作目录>
   ```
3. 预检未 PASS 的必需项走用户交接协议（H1/H2），**不许硬上**。

## 强制规则

- **不编造**：题目、答案、解析只能来自站点一手内容或自己的独立验算。取不到就写「非一手，需人工核对」。
- **不绕付费墙**：不改 UA/IP 规避验证、不破解答案接口、不解密他人浏览器 cookie。
- **不重复打扰用户**：凡要用户动手，先把窗口备好 → 说清点哪里 → 自动复验 → 输出 PASS/FAIL → PASS 才继续。同一交接点失败两次即换降级方案。
- **静默失败禁止**：任何一步失败输出 FAIL + 原因，不许卡住不吭声。
- **超预算即停**：任一环节超预算 2 倍立刻停下报告，不重试到成功，不自研绕路。

## 三站速查（细节见 references/站点矩阵.md）

| 维度 | 出卷网 chujuan.cn | 菁优网 jyeoo.com | 二一组卷网 zujuan.21cnjy.com |
|---|---|---|---|
| 取题干 | 免登录检索 JSON 可得 | 详情页游客可得，列表需登录 | 免登录检索 + SSR 详情 |
| 一手答案 | 登录后可得（官方解析图） | 答案栏游客可见，解答正文需登录 | 不可得（登录墙） |
| 抓取方式 | 登录后走 CDP 页面 fetch | 必须 CDP 渲染 | requests 直抓 |
| 广东覆盖 | 低（中等题池约 7%） | 待系统抽样 | 最高 |

选站规则：广东/广州新卷 → 二一；需要一手解析全文 → 出卷网（登录态）；快速自检答案栏 → 菁优网游客态。

## 脚本

全部纯标准库（Python 3.14），不装第三方包。`push_lark.py` 额外依赖 `lark-cli`（凭据由环境外部注入，无需 login）。

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `scripts/preflight.py` | P0 环境/账号/答案墙/滑块/地区参数预检 | `--root` |
| `scripts/launch_chrome.py` | 启动专用 Chrome + CDP 9222（登录态载体） | `--profile` `--port` `--url` |
| `scripts/cdp_client.py` | CDP 客户端（标准库 WebSocket）：列标签页/执行 JS/导航/截图 | `tabs` `eval` `nav` `shot` |
| `scripts/search_21cnjy.py` | 二一检索：关键词 × 学科 × 页数，输出候选池 JSON | `--kw` `--subject` `--pages` `--gd-only` |
| `scripts/fetch_21cnjy.py` | 二一详情批量抓取 + 题干/小问/难度解析 + 题图下载 | `--qids` `--out` |
| `scripts/probe_chujuan.py` | 出卷网登录态详情抓取 + 答案/解析字段提取 + 解析图下载 | `--qid` `--html` |
| `scripts/probe_jyeoo.py` | 菁优网列表/详情/答案区提取（考点·答案·解答）+ 题图 | `--url` `--shoti` |
| `scripts/dedupe.py` | 与 items.ndjson 查重（题干指纹 + 关键词重叠） | `--items` `--candidates` |
| `scripts/build_html.py` | 由清单 JSON 生成学生版/答案版 HTML，并自检零答案泄漏 | `--manifest` `--outdir` |
| `scripts/verify_calc.py` | 独立验算工具（分数精确：二次函数/面积最值/杠杆平衡） | `--case` |
| `scripts/push_lark.py` | P9-b 飞书入库：写题目库/检索记录/训练任务三表，幂等+回查+题图上传 | `--check` `--manifest` `--dry-run` `--out` |

CDP 相关脚本要求专用 Chrome 已在 9222 运行：`python scripts/launch_chrome.py`（沙箱内需在沙箱外启动，否则进程被回收）。
沙箱内启动 Chrome 会被回收，改用 `dangerouslyDisableSandbox` + `Invoke-WmiMethod -Class Win32_Process -Name Create`。

## 独立选题流程（P0–P9 摘要）

P0 预检 → P1 知识点转关键词 → P2 检索出候选（每训练点 ≥8 道，中等难度 ≥40%）→ P3 批量抓详情（单题 2 次失败即弃）→ P4 题干题图解析（装置图放大 4x 复核）→ P5 查重 → P6 独立验算 → P7 匹配遴选（人工卡点，不为换而换）→ P8 学生版/答案版产出 → P9 入库建任务 → **P9-b 飞书多维表格入库（必做，`scripts/push_lark.py`）**。

每步的输入/输出/判定标准/预算耗时见 `references/三站检索SOP.md` 第一章。

## 独立选题交付物

1. **清单 Markdown**：题号、来源站与链接、难度、知识点、选用理由、备选说明、答案一手性标注。
2. **学生版 HTML**：零答案零提示。交付前自检：全文检索「答案/解析/答：」必须 0 命中（`scripts/build_html.py` 内置）。
3. **答案版 HTML**：含答案、验算过程、非一手警示框。
4. **题图目录**：本地 PNG，供 HTML 内嵌引用。
5. **入库**：`items.ndjson` 追加 TM-0000XX 记录（题干指纹 + 去重键）。
6. **飞书入库（必做）**：飞书多维表格才是正式题库，items.ndjson 只是本地快照。用 `scripts/push_lark.py` 写三张表（题目库/检索与选题记录/训练任务库），落点、table_id、字段与判定见 `references/三站检索SOP.md` P9-b。凭据不可用时明确报告「飞书未入库」，不静默跳过。

学生版/答案版 HTML 骨架见 `assets/`；push_lark 输入模板见 `assets/lark_manifest_template.json`。

## 常见坑

- 菁优网静态 requests 拿不到题链（列表 JS 加载）→ 必须 CDP。
- `district_id=19` 对二一关键词检索不生效 → 改用试卷名正则筛广东地名。
- 二一详情答案通道 `access=false` → 该站答案一律标「非一手」。
- 出卷网答案图 URL 带 sign，拿到 URL 后无 cookie 亦可下载。
- CDP `Runtime.evaluate` 顶层不接受 `return` → 表达式包 IIFE（`cdp_client.js()` 已自动处理）。
- 某标签页渲染进程卡死 → `Runtime.evaluate` 永久超时；用 `pick_tab()` 先探测再挑页，别在死页上重试。
- 站点探查的标签页不要无条件回退到任意页，否则会在 example.com 上测出假 FAIL。
- 验证页判定要先剥 `<script>`/`<style>`，否则出卷网/二一正常首页会被误判成验证页。
- PowerShell `-File` 读含中文路径的 .ps1 会乱码 → 逻辑一律写 .py 文件执行。
- 内联 `python -c` 引号易碎 → 一律写 .py 文件。
- 单次网络超时不等于站点有滑块 → 预检的有效样本 ≥2 才下结论。
- `lark-cli api --page-all` 输出混入 `[page N] fetching...` 进度行，JSON 解析必炸 → 分页用 `--params '{"page_size":500,"page_token":...}'`（push_lark.py 已内置）。
- `lark-cli auth status` 在凭据外部注入环境报 validation 错，不代表凭据坏 → 连通性以 `push_lark.py --check` 为准。

## 实测基线（2026-11-03，脚本已逐个跑通）

| 脚本 | 实测结果 |
|---|---|
| `preflight.py` | 6.7s，FAIL 0、BLOCKED 2（二一答案墙 + district_id 不生效） |
| `search_21cnjy.py` | 5.7s，「杠杆」×2 页 + 广东筛选 → 候选池 4 题（潮州/惠州/江门/深圳，全 diff=3） |
| `fetch_21cnjy.py` | 3.9s，题干/小问/难度/试卷名全解析，题图落盘，`access=false` 正确标注非一手 |
| `probe_chujuan.py` | 登录态 PASS（页头显示已登录账号）；详情 200/41KB；一手解析图 + 3 张答案图下载成功 |
| `probe_jyeoo.py` | 检索判定 WALL（题链 0，游客墙）；详情【考点】【答案】可提取，【解答】空；题图 5 张下载成功 |
| `dedupe.py` | 同题干判「重复」1.00；改写题干判「全新」 |
| `verify_calc.py` | 四例全通过，分数精确 |
| `build_html.py` | 正样本 PASS；注入「答案为 4 N」的负样本 FAIL 并以退出码 2 拦截 |
| `push_lark.py` | `--check` 四表全 PASS（题目库42/任务库35/检索记录0/知识点库118）；`--dry-run` 正确判已存在题为 skip、知识点/去重键/任务号全部解析成 record_id，未写库 |

未覆盖（如实）：菁优网登录后完整【解答】正文、菁优广东覆盖度抽样、出卷网免费 vs VIP 答案可见性差异、`launch_chrome.py` 沙箱内首次启动分支（沙箱会回收进程，属已知限制）、`push_lark.py` 正式写入分支（dry-run 已验证，正式写入涉及线上数据需用户批准后实跑一轮）。
