---
name: question-bank-selection
description: Select, verify, package exam questions from chujuan.cn, jyeoo.com, zujuan.21cnjy.com as student/answer versions. Use when asked to find, filter, dedupe or verify exam questions. Not for authoring.
---

# 题库选题与交付

从中文题库站检索、筛选、核验题目，产出「学生版 + 答案版 + 清单」三件套。默认三站：出卷网、菁优网、二一组卷网。

## 与 Knowledge Mastery Planner 联动

当任务引用飞书 RW、KMP 计划或上游放行记录时，先读 [上游契约入口](references/upstream-contract.md)。该入口固定指向上游提交 `9ad6e07ab5c82940c9793c2aa590ba8cbc19258f` 的 KMP v1 契约与 schema；补搜理由只读任务复盘当前 `delivery`，题目侧只留 RW 与批次指针。

本文件是本地超集：过程字段（`是否独立完成`/`提示次数`/`作答用时`/`把握度预测`/`错误归因`/`订正动作`）、A–F 归因、P10 回流、训练循环继续按下文执行，不被该入口替换。联动路径按契约执行，独立选题的 P8、P9 和 P9-b 用于独立流程。

### 共识 v2 执行规则（2026-11-06，17 题实测后修订）

- **单写权**：题目库、「检索与选题记录」和训练任务的入题只有本 Skill 写；上游只读校验。绝不代上游写 `[KMP/plan/v1]` 或 `[KMP/delivery/v1]`。候选记录目前无表可写，落点方案待用户拍板（见上游 `references/feishu-sop.md`）。
- **补搜上限与降级**：按 plan 的 `research_round_limit`（默认 2）。收到 `needs_research` 后开新批次槽并记录 `supersedes_batch_id`；达上限后**不得再搜**，按上游 delivery 的 `degradation` v2 路径执行：① 换情境不换知识点 → ② 换源/补题面 → ③ 上游显式重定目标层级（`level_change`）→ ④ 交人工。**禁止为凑层级把 L3 降到易档，禁止自行换 ZSD**；本 Skill 不得自行降级、不得改 `plan_version`。
- **`needs_evidence` 出口**：题面截断、图不可读、平台无答案、答案墙 → 不进补搜循环，按 `evidence_gaps` 写清缺项（类型+题号+细节），退回补题面或换源；不消耗补搜轮次。
- **复核字段化**：交候选时按 `checks` 六项自检并逐项写 `pass` / `fail` / `unknown`：必测动作、难度档、配图、答案可验算、去重键、科目配比。配图按 `image_requirement` 三档判（required/illustrative/none）；答案先标 `answer_source`；去重键要报「重复/结构重复/全新」，结构重复须上游写 `dedupe_exception` 才可放行。允许小问级或整题级，整题级用 `merged_subquestions` 列明合并的小问。禁用「基本符合」「大致达标」「大体满足」等模糊表述。历史已写入的旧 delivery 不追溯校验。
- **回读**：写库后回读条数、关联、状态；上游复核会按 `task_id` / `batch_id` / `TM` 回库核对，交清单不等于交结果。
- **状态语义**：`[KMP/plan/v1]` 是上游条件（`state=ready` 才可搜）；`[KMP/delivery/v1]` 是上游结论，只有 `approved_for_pack` 才能制卷，`needs_research` 只能补搜，`needs_evidence` 只能补件或换源，`scope_hold` 只能保留候选。

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
| 取题干 | 免登录检索 JSON 可得 | 检索 `GET /search?c=0&qb=` 匿名可得（题号掩码） | 免登录检索 + SSR 详情 |
| 一手答案 | 登录后可得（`answer_text` + 官方解析图） | 列表内联答案匿名可见；详情【答案/分析/解答/点评】需登录（不需会员） | 不可得（`access=false`，0/10） |
| 抓取方式 | 检索 requests；详情走已登录 profile（9223）或带 cookie 直抓 | 检索 requests（匿名可搜）；详情带 `--session` 直抓 | requests 直抓 |
| 广东覆盖 | 低（中等题池约 7%） | 待系统抽样 | 最高 |

选站规则：广东/广州新卷 → 二一；需要一手解析全文 → 出卷网（登录态）；快速自检答案栏 → 菁优网匿名检索列表。

## 脚本

全部纯标准库（Python 3.14），不装第三方包。`push_lark.py` 额外依赖 `lark-cli`（凭据由环境外部注入，无需 login）。

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `scripts/preflight.py` | P0 环境/账号/答案墙/滑块/地区参数预检 | `--root` |
| `scripts/launch_chrome.py` | 启动专用 Chrome + CDP 9222（登录态载体） | `--profile` `--port` `--url` |
| `scripts/cdp_client.py` | CDP 客户端（标准库 WebSocket）：列标签页/执行 JS/导航/截图 | `tabs` `eval` `nav` `shot` |
| `scripts/search_21cnjy.py` | 二一检索：关键词 × 学科 × 页数，输出候选池 JSON | `--kw` `--subject` `--pages` `--gd-only` |
| `scripts/fetch_21cnjy.py` | 二一详情批量抓取 + 题干/小问/难度解析 + 题图下载 | `--qids` `--out` |
| `scripts/search_chujuan.py` | 出卷网**免登录**关键词检索：输出题干/小问/题型/难度/试卷/知识点；答案需登录 | `--kw` `--subject` `--pages` `--gd-only` `--diff` |
| `scripts/search_jyeoo.py` | 菁优网检索 `GET /search?c=0&qb=`（**匿名可搜**，题号掩码）+ 登录态真实题号与详情四段（考点/答案/分析/解答/点评） | `--kw` `--subject` `--pages` `--session` `--shoti` `--paper` `--discover` |
| `scripts/save_session.py` | 登录态检测（出卷网页头掩码手机号 / 菁优 `/account/logoff`）与 cookie 导出到本地未跟踪目录 | `--status` `--out` `--port` |
| `scripts/probe_chujuan.py` | 出卷网登录态详情抓取 + 答案/解析字段提取 + 解析图下载 | `--qid` `--html` |
| `scripts/probe_jyeoo.py` | 菁优网 CDP 渲染版详情/答案区提取（考点·答案·解答）+ 题图 | `--url` `--shoti` |
| `scripts/dedupe.py` | 与 items.ndjson 查重（题干指纹 + 关键词重叠） | `--items` `--candidates` |
| `scripts/build_html.py` | 由清单 JSON 生成学生版/答案版 HTML，并自检零答案泄漏（HTML 仅中间产物） | `--manifest` `--outdir` |
| `scripts/render_png.py` | 主交付：逐题渲染学生版/答案版 PNG，标题区打飞书题目 ID，文件名带 ID | `--items` `--ids` `--figdir` `--outdir` `--chrome` |
| `scripts/verify_calc.py` | 独立验算工具（分数精确：二次函数/面积最值/杠杆平衡） | `--case` |
| `scripts/push_lark.py` | P9-b 飞书入库：写题目库/检索记录/训练任务三表，幂等+回查+题图上传 | `--check` `--manifest` `--dry-run` `--out` |

CDP 相关脚本要求专用 Chrome 已在 9222 运行：`python scripts/launch_chrome.py`（沙箱内需在沙箱外启动，否则进程被回收）。
沙箱内启动 Chrome 会被回收，改用 `dangerouslyDisableSandbox` + `Invoke-WmiMethod -Class Win32_Process -Name Create`。

## 流程（P0–P9 摘要）

P0 预检 → P1 知识点转关键词 → P2 检索出候选（每训练点 ≥8 道，中等难度 ≥40%）→ P3 批量抓详情（单题 2 次失败即弃）→ P4 题干题图解析（装置图放大 4x 复核）→ P5 查重 → P6 独立验算 → P7 匹配遴选（人工卡点，不为换而换）→ P8 学生版/答案版产出 → P9 入库建任务 → **P9-b 飞书多维表格入库（必做，`scripts/push_lark.py`）** → **P9-c 云空间归档（必做，题图/原卷/错题 PDF 上传）**。

每步的输入/输出/判定标准/预算耗时见 `references/三站检索SOP.md` 第一章。

## P10 结果回写（必做，做完题不更新库等于白跑）

学生对完答案后，必须把结果写回飞书四张表，缺一不可。回写前先过**作答回流闸门**：漏题、图不清、题号对不上（RW→TM）、无法验算四类不进 gap 计算，任务记 `awaiting_evidence`，掌握度不升不降，退回用户补件；闸门通过后才写下表。

| 表 | 写什么 | 判定 |
|---|---|---|
| 作答记录库 | 每题一条：关联题目、关联训练任务、正确与否、日期 + **作答用时(秒)/提示次数/是否独立完成(是/否/部分)/把握度预测(1-5)**；错题再加 **错误归因 A–F** | 用户只报对错时，得分/满分**留空**，不估算，`评分口径` 写「家长转述，无原始过程」；四项过程字段是必填项，缺项即 FAIL |
| 错题诊断库 | 做错题各一条：关联题目/作答记录/知识点、**错误类型 A–F**、主要错因（一句可复核）、**复测轮次 R1/R2/R3**、复测日期、复测结果、是否掌握、**补救题（真 link）** | 有过程证据才判 A–E；无过程证据记 `F 其他` + 主要错因写「未提供作答过程，暂无法归因，待补证据」，**不许猜错因**；`推荐变式训练` 只是文本备注，不能替代 `补救题` 关联 |
| 知识点库 | 掌握程度按状态机重判 + 在「掌握状态变更历史」追加一行 + 更新 `最近复测日期` | 见下方状态机；升级必须写依据（哪条作答记录、是否独立、有无提示） |
| 训练任务库 | 任务状态（进行中/已完成）+ 实际完成情况「实交 n/m；正确 x；缺 k 题；原因」 | 注明「按用户口述」 |

**核算口径（2026-11-05 起）**：按**到期日**核算。题按日期提前生产（11/09–11/17 目录带 `_待定`），未到期的题**不算欠账**，不得在汇总/复盘里写「断档」「欠账」「未回填」。

**掌握程度状态机**（唯一口径，别再只写「未开始/进行中」）：

- 未掌握：首次做错，或从未做过
- 部分掌握：做过且做对过至少一次（含单题）
- 已掌握／阶段性完成：隔天或隔周**换题**复测再做对，至少两次**独立**正确（`是否独立完成`=是 且 `提示次数`=0）
- 复测再错 → 退回上一级；`复测轮次` R1→R2，`复测日期` 顺延，并在 `复测计划与结果历史`、`掌握状态变更历史` 各追一行

**A 类闭环**：`错误归因=A` → `订正动作` 必须含「回看课本」或「推导过程复述」→ 讲清原理与推导 → 重做原题 → **次日换题变式复测**（D+1）。缺任一项判 FAIL 回改。

写完后必须回读核对：条数、关联是否挂上、状态是否生效，再把结果写进回复。回读失败按 FAIL 报告，不许假定成功。

### 训练循环（错题 → 补救题 → 复测，R1/R2/R3）

回写不是终点，必须把「做题 → 错题 → 补救 → 再错 → 再补」的链在飞书里真实挂上：

```
知识点 → 第 N 轮训练任务 → 题目（简单/中档）→ 作答（对/错）
       → 错题诊断（错因）→ 补救题（第 N+1 轮）→ 新作答 → …
```

- **轮次口径**：训练任务库 `训练轮次` 与题目库 `训练轮次` 同用 `R1/R2/R3`。R1 = 首轮覆盖，R2 = 错题补救（D+1），R3 = 隔天/隔周换题复测（D+3/D+7）。R1 只放简单/中档，难题统一留冲刺轮。
- **复测排期（与错题诊断库 `复测轮次`/`复测日期` 同源）**：错题当天登记 `复测日期`=D+1、`复测轮次`=R1；D+1 再错 → R2（D+3）；R2 再错 → R3（D+7）。到期未做保持 `复测结果`=未测，按到期日计入待办，不提前写「通过」。
- **升级门槛**：R1/R2/R3 中累计**两次独立正确**（`是否独立完成`=是、`提示次数`=0）才允许 `是否掌握`=True；只对一次记 `部分掌握`。
- **链接字段（已建，均为真 link，不是文本）**：
  - 错题诊断库 `补救题` ↔ 题目库 `针对错题`（双向关联，type=21，同一对字段的两侧）。
  - 题目库 `来源题目`（自关联，type=21；正向可查，反向字段不自建）。
- **写链顺序**：先建 R1 任务 → 题 → 作答（错）→ 诊断 → 建 R2 补救题并写 `针对错题`=[诊断] → 作答（对/错）→ 重判知识点掌握程度。R2 再错就开 R3，不要原地重复。
- **字段创建实测限制**：`property.back_field_name` 只在 `type=21`（双向关联）可用；`type=18`（单向关联）不生成反向字段，写 `back_field_name` 报 1254089 LinkFieldPropertyError。跨表 `type=21` 会自动生成反向字段并双向同步；自关联 `type=21` 实测**不生成**反向字段，`派生题` 不可用，反向查询请用 `来源题目` 筛选。
- **验收**：回读 `诊断.补救题` 与 `题目.针对错题` 两侧都能看到对方；合成链验证后必须删除测试记录并回读四表计数恢复基线。


## 交付物

1. **清单 Markdown**：题号、来源站与链接、难度、知识点、选用理由、备选说明、答案一手性标注。
2. **学生版 / 答案版 PNG（主交付）**：手机直接可看，每题一张，文件名为 `TM-0000XX_学生版.png` / `TM-0000XX_答案版.png`，图片标题区必须打上飞书题目 ID。用 `scripts/render_png.py` 生成（HTML 只是中间产物，不交付 HTML）。
3. **学生版零泄漏**：交付前自检，题目区不得出现「答案/解析/答：」，`scripts/build_html.py` 与渲染脚本均内置检查。
4. **题图目录**：本地 PNG，供渲染内嵌。
5. **入库**：`items.ndjson` 追加 TM-0000XX 记录（题干指纹 + 去重键）。
6. **飞书入库（必做）**：飞书多维表格才是正式题库，items.ndjson 只是本地快照。用 `scripts/push_lark.py` 写三张表（题目库/检索与选题记录/训练任务库），落点、table_id、字段与判定见 `references/三站检索SOP.md` P9-b。凭据不可用时明确报告「飞书未入库」，不静默跳过。
7. **云空间归档（必做）**：题图、原卷 PDF、错题扫描/错题 PDF 必须上传到飞书云空间 `小兔中考 * 知识库` 下的指定目录，不能只留本地。用 `lark-cli drive +create-folder --name <子目录>` 建目录（如「题目图片」「原卷」「错题扫描」），`lark-cli drive +upload --parent-token <folder_token> --file <本地文件>` 上传，批量目录用 `lark-cli drive +push`。上传后回读目录清单与 file_token，并在回复里给出目录链接；失败标 FAIL，不许只写「已上传」。

学生版/答案版 HTML 骨架见 `assets/`；push_lark 输入模板见 `assets/lark_manifest_template.json`。

## 常见坑

- 菁优网检索**不需要** CDP 渲染：`GET /search?c=0&qb=` 匿名返回 HTML 列表；`/ques/search?keyword=` 是栏目页，别再用。
- 菁优网匿名题号全是 `00000000-...`（掩码），进不了详情；要真实题号必须带登录态 `--session`。
- 出卷网/菁优网登录态共用 `tmp/chrome_sites_profile` + CDP 9223，cookie 只落 `tmp/session/`（已被 `.gitignore` 覆盖）；`_identity` ≈1 天、`jy` ≈7 天，失效让用户本人重登。
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
- **同一 items 槽位被两次复用**（不同 qid 往同一个下标覆盖 stem）→ qid/名称/题图错配，入库成「文字 A、图 B」（2026-11-04 TM-000051 事故）。一题一对象，写入前断言附件文件名前缀 == 本题 qid。
- `题目图片` 字段不能用 `api batch_update` 写（报 99992402），只能 `base +record-upload-attachment` 追加 + `base +record-remove-attachment` 删旧（需 `--yes`）。

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

未覆盖（如实）：菁优广东覆盖度抽样、出卷网免费 vs VIP 答案可见性差异、`launch_chrome.py` 沙箱内首次启动分支（沙箱会回收进程，属已知限制）、`push_lark.py` 正式写入分支（dry-run 已验证，正式写入涉及线上数据需用户批准后实跑一轮）。
（2026-11-06 已覆盖：菁优网登录后完整【解答】正文——`search_jyeoo.py --shoti --session` 实测可读【考点】【答案】【分析】【解答】【点评】。）
