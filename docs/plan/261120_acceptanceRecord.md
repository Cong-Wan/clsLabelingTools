# clsLabelTool 集成验收记录（M7.4）

- Author: wilbur
- Version: 1.0
- Date: 2026-11-20
- Description: 设计 §15 十七条验收逐条记录（方法/证据/结果/待手工/待决策）。自动化项以续跑 worker 复测证据为准（复测覆盖执行计划 M7.1 全部自动化口径；前任 M7 日志仅作参考）。#4 真实 7z 因嵌套压缩包标「待用户决策」。文末附 M7.3 浏览器手工清单与清理记录。

## 环境

- 服务：`bash start.sh` 经 nohup 运行，绑定 `0.0.0.0:8686`，访问地址 **http://10.168.1.71:8686**
- 数据根：`/data_27T_jfs95/wilbur/clsToolData`（uploads/datasets/logs/exports/tmp）；DB：`<project>/data/clsTool.db`
- 服务进程 TMPDIR 已核 = `/data_27T_jfs95/wilbur/clsToolData/tmp`（/proc/PID/environ）
- 验证手段：curl + 原生 Python 脚本（scripts/）+ sqlite3 CLI + node --check；无测试框架

## 逐条结果（17 条）

### #1 一键启动 + 局域网访问 —— 自动 PASS / 部分待手工
- 方法：nohup bash start.sh；ss -tlnp；curl health/静态资源；grep 外部资源；node --check。
- 证据：`LISTEN 0.0.0.0:8686 (uvicorn pid=3077452)`；`/api/health` → `{"status":"ok"}`；`/`、`/css/style.css`、4 个 js 全部 200；`grep -rEn 'https?://' static/` 无匹配（零 CDN）；`node --check` 4 个 js 全部 OK。
- 待手工：另一台机器浏览器访问 http://10.168.1.71:8686。

### #2 路径导入扫描计数 —— PASS
- 方法：POST /api/tasks（sourceType=path，路径=testFixtures/imgDir）→ 轮询终态。
- 证据：status=ready，itemCount=5 = 目录实际图片数（`link.png` 符号链接、`notes.txt` 被跳过）；items 行序=a1.png < b.bmp < b.jpg < sub/img2.png < sub/img10.png（固定自然序键，img2 < img10 数值比较）。

### #3 zip 上传（GBK/重名/原件）—— PASS（含真实 2.1GB 扩展）
- 方法：curl -F 上传 testFixtures/gbk.zip、dup.zip；另上传真实 2.1GB zip 走完整流水线。
- 证据：
  - gbk.zip → ready，relPath=`中文图片/测试照片一.png` 与构造基准精确一致（无乱码）；`uploads/<uid>/gbk.zip` 原件 + `.taskCreated` 标记均在。
  - dup.zip（合法重名 2 成员）→ ready，itemCount=1（去重跳过），任务正常。
  - **真实 2.1GB zip**（20261113潇湘变项目全栈图片标注.zip，2167730881 字节）：上传+拷贝 85s，解压+扫描 746s → ready，itemCount=8292 = zipfile 只读探针（scripts/probeRealArchives.py）图片成员基准；**全量 8292 项 relPath 集合与探针图片成员集合完全一致、无乱码替换符**（scripts/retakeZipFullNames.py）；该包成员名均为 ASCII（包内无 CJK 成员），中文名断言落在压缩包文件名：uploads 原件 `20261113潇湘变项目全栈图片标注.zip` 完整无乱码；抽样 content 200/image/jpeg，与 datasets 解压文件 `cmp` 字节一致。

### #4 7z 上传解压 + 中文断言 —— 待用户决策（嵌套压缩包支持）
- 方法：真实 3.5GB `潇湘站全站巡视（可见光）.7z` 经正常上传流程；只读探针核实成员结构。
- 证据：
  - 上传 144s → 终态 **error「未发现支持的图片文件」**，itemCount=0。
  - 只读探针（libarchive 遍历 7z 中央结构，不解压）：7z 仅 3 成员 = 目录 + `潇湘站全站可见光例行巡视报告 (1).xlsx`（1.38GB）+ `潇湘站全站可见光例行巡视采集文件包.zip`（2.16GB）。
  - **嵌套 zip 只读探针**（scripts/probeNestedZip.py：从 7z 流式读出嵌套 zip 至 tmp 暂存 → zipfile 只读列举 → 删除暂存）：嵌套 zip 共 8292 成员，**前 20 个成员全部为 jpg 图片**（如 `1//2026-11-09/1_RW0049927847154903_20261109073015/CCD/e9215374...jpg`），图片全部在嵌套层。
  - 结论：v1 设计「不递归解压嵌套压缩包」→ 任务 error 为**正确行为**；是否支持嵌套压缩包**待用户决策**。
- 处置：保留 7z 任务（taskId=b0dd14faccd04fc8b56f86ac31c55789）与 uploads 原件（3.5GB）；datasets 目录为空（3 成员均非图片，按设计跳过写出）。
- 临时绕过（已写入 README）：手动解压 7z 一次后，对内层 zip 走「绝对路径导入」（数据集目录）或直接「上传内层 zip」。
- 待手工：前端打开该任务显示 error 占位（不展示标注区/进度条）。

### #5 rar 上传解压 + 中文断言 —— PASS
- 方法：真实 `UAV_Inspection/杆塔倾斜检测/中台任务-10kV23xx线-20260810-982巡检原始影像.rar`（38.7MB）经正常上传流程；libarchive 只读探针建立基准。
- 证据：
  - 上传 1s（本地小文件）→ ready，itemCount=6 = 探针图片成员基准（6 成员全为图片）。
  - relPath 集合与探针逐一精确一致（工具按自然序排列），全部含 CJK、无替换符，例：`中台任务-10kV23xx线-20260810-982巡检原始影像/10k#10杆@@@塔顶位置.JPG`（`@@@` 为原始名称组成部分，非乱码）。
  - 抽样 content：HTTP 200、`image/jpeg`、7561216 字节，与 datasets 解压文件 `cmp` 一致；datasets 中文目录/文件名完整保留。
  - RAR4 中文名由 libarchive 3.7.2 正确解码，未触发 cp437→gb18030 回退（回退逻辑保留为兜底，archiveService._resolveMemberNameLa）。
- 待手工：前端浏览该 6 张图。

### #6 数字键标注（API 层）—— PASS / 交互待手工
- 方法：POST annotate → sqlite3 即时核对 + audit JSONL 核对 + null 清除 + 非法 label。
- 证据：annotate 200 `updatedAt=2026-11-20T14:18:06.588Z`，sqlite3 立即可查同时间戳行（同步落库）；2s 内 audit JSONL 出现同 ts 事件（审计秒级）；label=null → 标注行删除（计数 0）；label 不在标签集 → 400。
- 待手工：数字键 1-9 标注→自动下一张手感；0 清除停留；最后一张停留提示；刷新页面标注不丢。

### #7 隐私（API 层）—— PASS / 双标签待手工
- 方法：双客户端 curl 交叉请求 + 身份解析矩阵。
- 证据：retestB 任务列表为空（不含 retestA 任何任务）；retestB 请求 retestA 的 taskId / items / itemId content / export → 全部 404（不泄露存在性）；X-Client-Id=retestA + cookie clientId=retestB → 解析为 retestA（头>cookie）；无头无 cookie → 新 uuid + Set-Cookie，cookie 复读同一 id（默认名「标注员-<id前4位>」入库）；同头两次请求幂等。
- 待手工：同浏览器双标签同时首访 → UI 显示同一身份。

### #8 同批独立 —— PASS
- 方法：A/B 各自对同一 imgDir 建任务、各自标注、各自导出。
- 证据：两任务均 ready（各 5 项）；A 标「好」、B 标「坏」互不影响；两份 CSV 的 relPath 列完全一致（5 行），label 列各自独立 → 可外部合并。

### #9 CSV 全断言 —— PASS
- 方法：scripts/smokeCheck.py（行数/行序/BOM/列名/annotatorName/标注行数）+ exports 留档核对。
- 证据：两任务 CSV 均 PASS：行数=itemCount、行序=relPath 自然序、头三字节 EF BB BF、列名 `relPath,absPath,label,annotatorId,annotatorName,updatedAt`、annotatorName 非空（默认名兜底「标注员-rete」）、标注行数=DB；exports/ 留档文件存在（`<taskId>_<时间戳>_<4位随机>.csv`）。

### #10 日志无交错 + 关停 drain —— PASS
- 方法：8 路并发 annotate → 等待 flush → 全文件 json.loads；SIGTERM 前 0.3s 入队审计事件 → 重启后核对。
- 证据：8 路并发全部 200；audit-2026-11-20.jsonl 126 行**全部可 json.loads（无交错）**；SIGTERM（uvicorn 进程）后重启，SIGTERM 前 0.3s 入队的标注事件已落盘（ts=2026-11-20T14:57:00.525Z）→ 尾部审计不丢。

### #11 前端交互 —— 全部待手工
- 子项见文末「M7.3 浏览器手工验收清单」。

### #12 失败链路（API 层）—— PASS / UI 待手工
- 方法：停服→annotate→起服→同请求；已删任务 annotate。
- 证据：停服期间 annotate → curl 退出码 7（连接被拒，请求失败）；起服后同一请求 → 200 且 DB 标注行=1；已删任务 annotate → 404（补传遇 4xx 终态丢弃的 API 基础）。
- 待手工：断网点击→未保存态+顶栏 N 条待重试→恢复一键重试；失败期间刷新→自动补传；已删任务补传→丢弃+提示；三态展示。

### #13 重启恢复 —— PASS
- 方法：植入假 extracting 任务行 → SIGTERM 重启 → 核对。
- 证据：重启后 status=error、errorMsg=`服务重启导致中断，请删除后重建`；app.log `启动恢复：置 1 个中间态任务为 error`。

### #14 删除护栏 —— PASS（含真实 in-flight）
- 方法：非终态 DELETE / force / 终态删除 + content 404；**真实 in-flight**：2.1GB zip 解压中 DELETE。
- 证据：
  - 真实 in-flight（2.1GB zip extracting）：DELETE → 409；DELETE ?force=true → 200；app.log `解压 <id>：任务已删除或状态变更，退出` + `…不进入扫描`（后台线程退出）；DB 残留 task/items/annotations = 0/0/0（无孤儿）。
  - 合成假 extracting 行（含 2 items）：DELETE → 409；force → 200；无孤儿。
  - ready 任务删除 → 200（同事务级联）；其后 content → 404、items=0。

### #15 边界全集 —— PASS
- 证据（API 实测，除 413）：
  - zip-slip 成员（`../evil.png`）：任务 ready、items 仅 good.png、datasets 根无 evil.png（越界跳过）。
  - 坏路径 → 400；路径为文件 → 400；非 zip/7z/rar（.txt）→ 400；坏魔数（.zip 内容为文本）→ 400。
  - 空目录路径任务 / 空包 / 无图片包 → 均 error「未发现支持的图片文件」。
  - 声明偏大伪造 zip（24GB）→ error「解压中止：实际写出量超过 20GB 或成员数超过 20 万（安全护栏）」（infolist 预检快速失败）。
  - **实际量护栏调低阈值法**（scripts/retakeGuardThreshold.py：import 解压服务、进程内调小 MAX_EXTRACT_BYTES 后解压正常小 zip）→ 中止且 errorMsg 为护栏专用文案（与损坏/加密文案区分）。
  - 损坏包 → error「压缩包损坏或无法解析：Bad CRC-32 for file 'c.png'」。
  - 加密包（flag_bits&0x1）→ error「压缩包已加密，不支持加密压缩包，请解密后重新上传」。
  - >10GB → 413：**代码走查**（taskApi.py upload 端点 spool 尺寸预检 `spoolSize > MAX_UPLOAD_SIZE → 413 不建任务`），未实测（构造 10GB+ 包不可行）。

### #16 spool / 中断 / 清扫 / 标记保留 —— PASS
- 证据：
  - spool 落挂载点：服务进程 TMPDIR=`clsToolData/tmp`；/tmp 无本工具 spool 残留（>5MB 属主文件中仅他会话的 `.yolo26m-cls.pt.part`，与本工具无关）。
  - 传输中断（真实 717MB zip，3s 断开）：无新增任务行、uploads 目录数不变（17→17）、tmp/ 无 spool 残留（框架清理）。
  - 启动清扫：无任务行且无 `.taskCreated` 标记的孤儿目录 `accSweepOrphanRetest` → 重启后被删（app.log 记录）。
  - 标记保留（R4 P1-a）：删除「验收-重名包」任务后，其 uploads 原件（dup.zip + `.taskCreated`）经两次重启仍在。

### #17 导出守卫 —— API PASS / 按钮禁用待手工
- 证据：7z error 任务 export → 409；假 scanning 任务 export → 409（仅 ready 可导出）。
- 待手工：非 ready 任务导出按钮禁用态。

## 汇总表

| # | 结果 | 备注 |
|---|------|------|
| 1 | 自动 PASS | 待手工：另一机器浏览器 |
| 2 | PASS | |
| 3 | PASS | 含真实 2.1GB zip（8292 项全量名称核对） |
| 4 | **待用户决策（嵌套压缩包支持）** | 7z 图片在嵌套 zip 层；任务与原件已保留 |
| 5 | PASS | 真实 rar 6 项，中文无乱码，content cmp 一致 |
| 6 | API PASS | 交互待手工 |
| 7 | API PASS | 双标签 UI 待手工 |
| 8 | PASS | |
| 9 | PASS | |
| 10 | PASS | 126 行无交错；drain 尾部不丢 |
| 11 | 待手工 | 全部 |
| 12 | API PASS | UI 待手工 |
| 13 | PASS | |
| 14 | PASS | 含真实 in-flight force + 线程退出日志 |
| 15 | PASS | 413 为代码走查 |
| 16 | PASS | |
| 17 | API PASS | 按钮禁用待手工 |

## 待决策项

1. **#4 嵌套压缩包支持**：真实 7z（潇湘站全站巡视（可见光）.7z）图片全部位于嵌套 zip 层（8292 张）。v1 不递归 → 该任务 error。选项：
   - a) 保持 v1 设计（不递归）：用户手动解压 7z 一次后，对内层 zip 走路径导入或直接上传内层 zip（内层 zip 8292 成员全为图片，名称 ASCII，可直接用）；
   - b) v1.1 增加「嵌套压缩包一层递归/提示」能力（需改设计，另走评审）。
   - 证据脚本：scripts/probeNestedZip.py（只读、可复跑）。

## M7.3 浏览器手工验收清单（用户侧）

访问 http://10.168.1.71:8686 。注意任务私有（D4）：复测任务属于 retestA / testA 身份，**新浏览器打开任务列表为空**；如需浏览复测任务，先在浏览器 DevTools → Application → Cookies 设置 `clientId=retestA`（RAR、2.1GB zip）或 `clientId=testA`（7z）后刷新。

1. #1 另一台机器浏览器访问 http://10.168.1.71:8686，页面与 API 正常。
2. #6 标注页手感：数字键 1-9 标注→自动下一张；0 清除并停留；最后一张停留提示；刷新页面标注不丢。
3. #7 同浏览器双标签同时首访（未设 cookie 时）→ 两标签显示同一身份（clientId 一致）。
4. #11 热键 1-9 / ←→ 导航 / 过滤切换（全部/未标注/已标注）/ 未标注态自动前进 / 过滤清空后占位文案（未标注空=「已全部标注」；已标注空=「暂无已标注项」）+「查看全部」按钮 / 索引跳转 / 侧栏分页与三态点 / 创建表单标签映射预览（前 9 个标 1-9）/ >9 类别仅点击。
5. #12 断网（关 Wi-Fi/飞书代理）点击标注 → 未保存态 + 顶栏「N 条待重试」→ 恢复网络一键重试成功；失败期间刷新页面 → 加载自动补传成功；补传遇已删任务 → 丢弃记录+提示。
6. #17 非 ready 任务（处理中/error）导出按钮为禁用态。
7. #4/#5 前端图片展示侧（需按上述设 cookie）：
   - RAR 任务「复测-真实RAR-杆塔倾斜」（retestA）：6 张中文路径图片可浏览、加载正常；
   - 2.1GB zip 任务「复测-真实2.1GB-zip-潇湘变」（retestA）：8292 张可浏览、分页/过滤正常；
   - 7z 任务「验收-真实7z-潇湘站」（testA）：显示 error 占位「未发现支持的图片文件」（嵌套层，待决策项 1）。
8. （可选）新建自己的任务（路径导入或上传）走一遍完整流程：建任务→设标签映射→数字键标注→导出 CSV，确认 CSV 在 Excel 打开中文无乱码。

## 清理记录（M8.2）

- 保留：7z 任务 + uploads 原件（3a8a952af58a4db7a347c212cd2a26d3，3.5GB）+ 空 datasets 目录；真实 RAR 任务（14645c8785c447e6962d5e0c2ea8e38d）；真实 2.1GB zip 任务（2ebbbd3e44cd4c5986e8fe3a3943dac1，8292 张已解压）；testFixtures/ 全部合成用例；logs/（运行日志）；tmp/（TMPDIR）。
- 清除：全部合成/复测任务行（含前任残留「验收-同批-B」、假 extracting 行、护栏调低阈值残留行）及其 uploads/datasets 目录；exports/ 测试 CSV；tmp/probe_nested.zip（前任中断探针残留 1.58GB 部分拷贝）。
- 真实素材（/data_27T_jfs95/wilbur 下 4 个原始包与 Datasets/）零改动。
