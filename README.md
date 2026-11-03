# question-bank-selection

> 从中文题库站检索、筛选、核验中考题目，产出「学生版 + 答案版 + 清单」三件套。
> 覆盖出卷网、菁优网、二一组卷网三站，全部脚本仅依赖 Python 标准库（`push_lark.py` 额外需要 `lark-cli`）。

## 30 秒上手

```bash
git clone https://github.com/chenwu0409/question-bank-selection.git <你的 skills 目录>/question-bank-selection
```

装到任一按 `SKILL.md` 加载技能的环境（Trae / Claude Code 及同类 Harness）后，对 Agent 说：

```
用 question-bank-selection 帮我找 2 道广东的物理杠杆题
```

技能会先跑 P0 预检（环境 / 账号 / 答案墙 / 滑块 / 地区参数），输出 PASS/FAIL/BLOCKED 全表，再按站点矩阵选站检索。

> **仓库结构说明**：仓库根目录即 skill 载荷（`SKILL.md` 为入口），与 better-skill 的分发约定一致——根目录的 `README.md` / `MANIFEST.json` 是 GitHub 门面文件，`MANIFEST.json` 里 `"entry": "./SKILL.md"` 标明真正入口。安装后**本地**的 `.trae/skills/question-bank-selection/` 不含这两个文件，保持载荷干净。

## 它解决什么

| 痛点 | 本技能的做法 |
|---|---|
| 三个站各有一套检索参数和反爬特征，试错成本高 | 站点矩阵固化成九维对比表 + 各站请求配方，`references/站点矩阵.md` |
| 答案一手性说不清，交付了不敢用 | 每个脚本显式标注「一手 / 半可得 / 非一手」，取不到就写「非一手，需人工核对」，绝不编造 |
| 登录态抓取反复失败 | 固化独立 Chrome + 专用 user-data-dir + CDP 方案，登录态落在 profile 里复用 |
| 让用户点一下然后系统无声卡住 | 用户交接协议 H1–H3：备好窗口 → 说清点哪里 → 自动复验 → 输出 PASS/FAIL → PASS 才继续 |
| 长流程跑飞、悄悄失败 | P0–P9 每步有输入/输出/判定标准/预算；静默失败禁止；超预算 2 倍即停 |

## 三站能力矩阵（实测，2026-11-03）

| 维度 | 出卷网 chujuan.cn | 菁优网 jyeoo.com | 二一组卷网 zujuan.21cnjy.com |
|---|---|---|---|
| 免登录取题干 | ✅ 检索 JSON 直含题干/小问/难度/试卷名/题图 | ⚠️ 详情页游客可得，**列表被登录墙挡死** | ✅ 检索 JSON + SSR 详情 |
| 答案一手性 | ✅ **登录后一手可得**（官方解析图，含分步解答） | ⚠️ 【答案】栏游客可见；**【解答】正文需登录/会员** | ❌ 不可得（`access=false` 登录墙） |
| 抓取方式 | 登录后走 CDP 页面 fetch | 必须 CDP 渲染（静态请求拿不到题链） | requests 直抓 |
| 广东/广州覆盖 | 低（中等题池 69 题仅 5 道广东，7.2%） | 待系统抽样 | **最高**（19 题广东池，含广州荔湾广雅、白云钟落潭） |
| 滑块 | 无 | 无 | 无（3 连发实测零验证） |

**选站规则**：广东/广州新卷 → 二一；需要官方解析全文交叉核对 → 出卷网（登录态）；快速自检答案栏 → 菁优网游客态。

## 依赖

| 项 | 要求 |
|---|---|
| Python | 3.14，**只用标准库**，无需 pip install |
| Chrome / Edge | 仅出卷网登录态与菁优网需要；用 `--remote-debugging-port=9222` 启动 |
| 账号 | 出卷网需登录一次（免费账号即可），登录态存在专用 profile 里复用；二一检索免登录；菁优网游客可读详情页 |
| 沙箱 | 沙箱内启动的 Chrome 会被进程回收 → 需在沙箱外启动，或 `Invoke-WmiMethod -Class Win32_Process -Name Create` |
| lark-cli | 仅 `push_lark.py`（P9-b 飞书入库）需要；凭据由环境外部注入，无需 `auth login`；表落点与 table_id 见 `references/三站检索SOP.md` P9-b（需按自己的 Base 修改脚本头部常量） |

## 目录结构

```
SKILL.md                          # 入口：触发条件、流程摘要、脚本索引、常见坑、实测基线
references/
  三站检索SOP.md                  # P0–P9 全流程、站点矩阵、用户交接协议、预算与退出规则（311 行）
  站点矩阵.md                     # 九维对比、各站请求配方、参数速查、13 条已知限制（93 行）
scripts/                          # 黑盒脚本，只用 --help，不读源码
  preflight.py                    # P0 预检：9 项，输出 PASS/FAIL/BLOCKED
  launch_chrome.py                # 启动专用 Chrome + CDP 9222 + profile 持久化
  cdp_client.py                   # CDP 客户端（标准库 WebSocket）：tabs/eval/nav/shot/text
  search_21cnjy.py                # 二一检索：关键词 × 学科 × 页数 + 广东筛选
  fetch_21cnjy.py                 # 二一详情批量抓取 + 题干/小问/难度解析 + 题图下载
  probe_chujuan.py                # 出卷网登录态复验 + 一手解析图/答案图下载
  probe_jyeoo.py                  # 菁优检索墙判定 + 考点/答案/解答提取 + 题图
  dedupe.py                       # 查重：题干指纹 + 数字/关键词重合
  verify_calc.py                  # 独立验算：分数精确（杠杆/二次函数/面积极值/鞋带）
  build_html.py                   # 清单 JSON → 学生版/答案版 HTML + 零答案泄漏自检
  push_lark.py                    # P9-b 飞书入库：题目库/检索记录/训练任务三表，幂等+回查+题图上传
assets/
  manifest_template.json          # build_html.py 输入格式样例
  lark_manifest_template.json     # push_lark.py 输入格式样例
```

## 脚本用法

```bash
# P0 预检（每次接任务先跑）
python scripts/preflight.py --root <工作目录>

# 二一检索：物理杠杆 × 广东
python scripts/search_21cnjy.py --kw "杠杆" --kw "杠杆 平衡" --subject phys --pages 2 --gd-only --out pool.json

# 二一详情批量抓取 + 题图
python scripts/fetch_21cnjy.py --qids 65034777,73054382 --out meta.json --figdir figs

# 出卷网：复验登录态 → 抓详情 → 下一手解析图
python scripts/launch_chrome.py --profile ./browser_profile
python scripts/probe_chujuan.py --login-state
python scripts/probe_chujuan.py --qid 41511381 --out meta.json --figdir figs

# 菁优网：详情考点/答案/解答 + 题图
python scripts/probe_jyeoo.py --shoti a101ba79-1514-415d-9e5f-632525b132f8 --figdir figs

# 查重 / 验算 / 生成 HTML
python scripts/dedupe.py --items items.ndjson --candidates pool.json
python scripts/verify_calc.py --case lever --G 2 --n1 3 --L1 2 --L2 3
python scripts/build_html.py --manifest manifest.json --outdir ./out

# P9-b 飞书入库（需 lark-cli；--check 验证连通，--dry-run 预览不落库）
python scripts/push_lark.py --check
python scripts/push_lark.py --manifest lark.json --dry-run
python scripts/push_lark.py --manifest lark.json --out push_result.json
```

每个脚本都支持 `--help`。

## 交付物

1. **清单 Markdown** —— 题号、来源站与链接、难度、知识点、选用理由、备选说明、答案一手性标注
2. **学生版 HTML** —— 零答案零提示；`build_html.py` 内置自检，正文命中「答案/解析/答：/解答」即以退出码 2 拦截
3. **答案版 HTML** —— 含答案、验算过程、非一手警示框
4. **题图目录** —— 本地 PNG，供 HTML 内嵌
5. **入库** —— `items.ndjson` 追加 `TM-0000XX` 记录（题干指纹 + 去重键）
6. **飞书入库（必做）** —— `push_lark.py` 写多维表格三张表（题目库/检索与选题记录/训练任务库）；飞书才是正式题库，items.ndjson 只是本地快照；凭据不可用时明确报告「飞书未入库」

## 硬约束

- **不编造** —— 题目、答案、解析只能来自站点一手内容或独立验算；取不到就标「非一手，需人工核对」
- **不绕付费墙** —— 不改 UA/IP 规避验证、不破解答案接口、不解密他人浏览器 cookie
- **不重复打扰用户** —— 同一交接点失败两次即换降级方案
- **静默失败禁止** —— 任何一步失败输出 FAIL + 原因
- **超预算即停** —— 任一环节超预算 2 倍立刻停下报告，不重试到成功，不自研绕路

## 已知限制

- 内嵌浏览器（Trae 自带）不可用于登录态抓取：标签页属上层 IDE 会话，代理会话报 `Browser operation belongs to an inactive execution round` → 一律用独立 Chrome
- 360 极速浏览器 cookie 读不出（`WinError 32` 独占锁、`esentutl -1032`）→ 不要在 360 上花时间
- 二一 `district_id=19` 对关键词检索不生效 → 改用试卷名正则筛广东地名
- 菁优网静态请求拿不到题链；`/math3/ques/` 是导航页不是题目列表页
- CDP `Runtime.evaluate` 顶层不接受 `return`；标签页渲染进程卡死会永久超时（用 `pick_tab()` 先探测）
- 单次网络超时不等于站点有滑块 → 预检有效样本 ≥2 才下结论
- `lark-cli api --page-all` 输出混入进度行会破坏 JSON 解析 → 分页一律用 `--params '{"page_size":500,"page_token":...}'`（push_lark.py 已内置）
- `lark-cli auth status` 在凭据外部注入环境报 validation 错，不代表凭据坏 → 连通性以 `push_lark.py --check` 为准

完整清单见 `references/站点矩阵.md`。

## 未覆盖项（如实）

- 菁优网**登录后**的完整【解答】正文未取（需在专用 profile 里登录一次）
- 菁优网广东/广州覆盖度未系统抽样
- 出卷网免费账号 vs VIP 的答案可见性差异未比对
- 触发准确率未实测（better-skill 五维标尺里的触发率项）
- `push_lark.py` 正式写入分支未实跑（`--check` 与 `--dry-run` 已验证；正式写入涉及线上数据，需用户批准后实跑一轮）

## 许可

[MIT](LICENSE)
