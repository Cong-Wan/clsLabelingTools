# clsLabelTool 分类数据标注工具 — 设计方案

- Author: wilbur（flamingo 助理起草）
- Version: 1.4
- Date: 2026-11-20
- Description: 分类数据标注工具完整设计方案。v1.0 初稿；v1.1 修复 R1；v1.2 纳入用户 5 项决定+R2 加固；v1.3 修复 R3（1 P1+7 P2）；v1.4 修复 R4 全部发现（P1-a 清扫误删保留原件→.taskCreated 标记判据；P2-a 成员数计数口径；P2-b 占位文案按过滤区分；P2-c 版本/计数同步）并采纳 BEGIN IMMEDIATE 建议。供 R5 微定向核验。

---

## 1. 背景与目标

为公司局域网环境构建一个**图片分类标注**工具：

- 后端 Python，前端仅 HTML + JS + CSS（无框架、无构建工具）；
- 支持输入服务器本机可读取的绝对路径导入图片数据；
- 支持上传压缩包（**zip / 7z / rar**），压缩包与相关日志保存至 `/data_27T_jfs95/wilbur/clsToolData`；
- 标注前设置好标签映射（数字键↔类别），标注时**按数字键完成标注并自动切换下一张**；
- 标注结果导出 CSV（每个任务导出一份完整 CSV）；
- 标注内容实时保存；
- 不做账号管理，**不同终端的任务互相看不见**：A 在自己电脑建任务标注，B 在自己电脑建任务标注（可以是同一批数据——各自导入同一路径/压缩包，也可以是另一批），互不干扰。

## 2. 需求 → 设计映射

| # | 需求 | 设计落点 |
|---|------|----------|
| R1 | Python 后端 | FastAPI + uvicorn，uv 管理（Python 3.12，用户已确认） |
| R2 | 前端仅 html+js+css | 原生 vanilla SPA，后端托管静态文件；**零 CDN/外部资源** |
| R3 | 公司局域网 | 绑定 `0.0.0.0:8686`，`http://<服务器IP>:8686` 访问（8000/8080/9000 已被占用，8686 空闲，CLS_PORT 可覆盖） |
| R4 | 本机可读绝对路径 | 扫描服务递归扫描目录，按图片扩展名过滤注册 |
| R5 | 上传压缩包 zip/7z/rar | zip→stdlib zipfile；7z/rar→libarchive-c（系统已有 libarchive.so.13，**无需 sudo**）；存 `uploads/`、解压 `datasets/` |
| R6 | 日志在 clsToolData | `logs/`：运行日志（队列+轮转）+ 审计 JSONL（单写线程异步） |
| R7 | 导出 CSV | 每任务一份完整 CSV；`exports/` 留档 + 流式下载；UTF-8 BOM |
| R8 | 实时保存 | 标注**同步写 SQLite 提交后才返回**；审计异步秒级落盘；前端三态指示+失败队列+刷新补传 |
| R9 | 无账号、互相看不见 | 匿名 clientId；**任务列表仅显示本人创建的任务**；所有任务/数据项接口校验归属（非本人→404）；每任务单一标注人（创建者），annotations 主键 (taskId,itemId) |
| R10 | 数字键标注+自动下一张（用户补充） | 标签映射创建时定义（顺序即热键 1-9）；按键→乐观标注→立即自动前进；保存失败可追踪不丢 |

## 3. 设计决定（用户已确认，2026-11-20）

- **D1 数据模态 = 仅图片**：jpg/jpeg/png/bmp/webp/gif。v1 不做文本/音频/视频（v1.1 的文本支持已移除）。
- **D2 单标签分类**：N 选 1，不做多选。
- **D3 压缩格式 = zip + 7z + rar**：zip 用 stdlib；7z/rar 用 `libarchive-c`（pip，ctypes 封装）+ 系统 `libarchive.so.13`（已核实存在，3.7.2，支持 rar/rar5/7z 读取）。**不支持加密压缩包、分卷压缩包**（error 提示/README 限制）；不递归解压嵌套压缩包。
- **D4 任务互相看不见**：任务私有（仅创建者可见可操作）；“B 操作同一批数据”= B 自己导入同一路径/压缩包建自己的任务；各自导出完整 CSV，relPath 一致可在外部合并（README 说明）。**v1 不做跨任务合并导出、不做任务共享**。
- **D5 Python 3.12**（本机已装 3.12.3）。
- **D6 标签映射创建时固定**：创建任务时定义有序类别列表，序号+1 即数字热键（前 9 个）；创建后不可修改（改标签需删除重建，README 说明）；>9 的类别仅点击选择。
- **D7 自动前进**：数字键/点击标注成功后立即切换下一张（当前过滤列表内）；最后一张停留并提示；热键 0=清除标注并停留；←/→ 手动导航始终可用。
- **A5 规模假设**：单任务 ≤ 10 万张；并发 ≤ 10 人；单压缩包 ≤ 10GB；解压总量 ≤ 20GB；成员数 ≤ 20 万。

## 4. 总体架构

```
浏览器 A ─┐                          ┌─ SQLite（本机磁盘 <project>/data/clsTool.db，WAL）
浏览器 B ─┼─ HTTP/LAN ─ FastAPI ────┤
浏览器 C ─┘   (uvicorn 单进程)       └─ JuiceFS 挂载 /data_27T_jfs95/wilbur/clsToolData
                                        ├─ uploads/   压缩包原件
                                        ├─ datasets/  解压数据
                                        ├─ logs/      运行日志 + 审计日志
                                        ├─ exports/   CSV 留档
                                        └─ tmp/       上传 spool（TMPDIR）
```

关键决策：

1. **单 uvicorn worker**：同步 `def` 端点自动进线程池；DB 毫秒级本机 IO；WAL + busy_timeout=5000 + 每请求短事务。upload 端点**必须 sync def**（GB 级拷贝在线程池执行，不阻塞事件循环）。
2. **SQLite 本机磁盘**：已核实 /home 为 /dev/sda2 ext4；规避 JuiceFS 锁风险。大文件/日志/导出在挂载点。
3. **后台线程 + 状态机**：`extracting → scanning → ready / error`；前端 2s 轮询终态即停。**启动恢复**：`UPDATE tasks SET status='error', errorMsg='服务重启导致中断，请删除后重建' WHERE status IN ('extracting','scanning')`。**启动清扫（R3 P2-4 / R4 P1-a）**：自检后清扫 uploads/ 下**既无对应任务行、又无 `.taskCreated` 标记**的 `<uploadId>` 目录（仅命中拷贝窗口崩溃残留；已删任务的保留原件有标记→不扫；此时尚未接请求，安全），闭合“无孤儿”声明且不违反物理保留契约。
4. **根磁盘护栏**：根盘已用 99%（剩 12.7GB）。**start.sh 先 `mkdir -p` 再 `export TMPDIR=<clsToolData>/tmp`**（R2 新-1：Python tempfile 对无效 TMPDIR 会静默回退 /tmp，必须先建目录）；README 的 nohup 示例同样携带。venv+DB <1GB。
5. **压缩解压双引擎**：zip→zipfile（GBK 文件名回退）；7z/rar→libarchive-c `file_reader` 逐成员读取（成员名/大小/数据块），**手动写出到校验后的目标路径**（zip-slip 防护与 zip 同等待遇）。依赖共 4 个：fastapi、uvicorn、python-multipart、libarchive-c。包源已核实可达。
6. **无测试框架**：curl 冒烟 + 原生脚本 + 手工验收。真实验收素材已就位（§15）。

## 5. 存储布局

```
/data_27T_jfs95/wilbur/clsToolData/
├── uploads/<uploadId>/<原始文件名>.(zip|7z|rar) + .taskCreated 标记
├── datasets/<uploadId>/...
├── logs/app.log                            # QueueHandler+QueueListener+Rotating(10MB×5)
├── logs/audit-YYYYMMDD.jsonl               # 单写线程异步
├── exports/<taskId>_<时间戳>_<4位随机>.csv
└── tmp/                                    # TMPDIR（start.sh mkdir -p）

<project>/data/clsTool.db                   # SQLite WAL，本机磁盘
<project>/static/                           # 前端
```

- 服务启动自动创建各子目录 + 挂载点可写自检（失败则报错退出）。
- 路径型任务数据不复制，只读引用原绝对路径。

## 6. 数据模型（SQLite）

```sql
clients(clientId TEXT PK, name TEXT DEFAULT '', createdAt TEXT, lastSeenAt TEXT)
tasks(
  taskId TEXT PK, name TEXT, sourceType TEXT,      -- 'path' | 'zip' | '7z' | 'rar'
  sourcePath TEXT, labelsJson TEXT,                -- 有序类别数组，创建后不可变
  status TEXT,                                     -- extracting|scanning|ready|error
  itemCount INTEGER DEFAULT 0, creatorId TEXT, createdAt TEXT, errorMsg TEXT DEFAULT ''
)
items(
  itemId INTEGER PK AUTOINCREMENT, taskId TEXT,
  relPath TEXT, absPath TEXT, sizeBytes INTEGER,
  UNIQUE(taskId, relPath)
)
annotations(
  taskId TEXT, itemId INTEGER, label TEXT, updatedAt TEXT,
  PRIMARY KEY(taskId, itemId)                      -- 任务私有→单一标注人（创建者）
)
-- 索引：items(taskId)；tasks(creatorId)
```

- 清除标注=删行；进度=已标注行数/itemCount。
- **任务归属（D4）**：一切任务级操作校验 `creatorId == 请求clientId`，否则 **404**（不泄露存在性）；content 接口经 itemId→taskId→creatorId 同样校验。
- **删除**：终态（ready/error）可直接删；非终态 DELETE → **409**（提示可强制删除）；**`DELETE ?force=true`（R2 新-2）**：先 `UPDATE status='error'`（后台线程批前“状态未变”校验即退出），再**同事务级联删 tasks/items/annotations 记录**（R3 P2-1，杜绝孤儿行）——卡死任务（如 JuiceFS 挂起）有应用内出路，不必重启服务。删除只删 DB 记录，物理文件保留防误删（README 说明手动清理）。
- **批插入护栏**：每批插入与“任务存在且状态未变”校验**同一事务**（闭合 TOCTOU）；`INSERT OR IGNORE` 处理 relPath 重复（R2 新-7：合法重名成员/GBK 解码撞名），计数跳过并记日志，不使整任务 error。

## 7. API 设计（前缀 `/api`）

clientId：`X-Client-Id` 头优先，其次 cookie；无则生成下发（Set-Cookie+响应体），前端存 localStorage。**身份闸门**：api.js 先 `await GET /api/client` 再放行任何请求；**注册后复读 localStorage 对齐**（R2 新-9：双标签同时首访取先写入者）。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/client` | 获取/注册当前客户端；注册时 name 为空则服务端置默认名「标注员-<id前4位>」（R3 P2-7，annotatorName 永不为空） |
| PUT | `/api/client` | 改显示名（trim/非空/≤32 字符） |
| POST | `/api/tasks` | 路径建任务 `{name, sourceType:'path', path, labels[]}`；路径存在/目录/可读否则 400；labels trim+去重+非空否则 400；后台扫描 |
| POST | `/api/tasks/upload` | multipart：file、name、labels(JSON)。**sync def**；扩展名 .zip/.7z/.rar 否则 400；魔数校验；**spool 尺寸 >10GB → 413 清理不建任务（R2 新-4）**；完整收包后处理（8.2） |
| GET | `/api/tasks` | **仅本人任务**：状态、itemCount、已标注数、errorMsg |
| GET | `/api/tasks/{id}` | 详情+labels+进度+errorMsg（归属校验） |
| DELETE | `/api/tasks/{id}[?force=true]` | 终态直删；非终态 409；force 先置 error 再删（6 节） |
| GET | `/api/tasks/{id}/items?offset&limit&filter=all\|unlabeled\|labeled` | 分页（relPath 自然序），每项带 label；归属校验 |
| GET | `/api/items/{itemId}/content` | **仅图片**：原始字节+扩展名 MIME；itemId 不存在或非本人任务 → 404 |
| POST | `/api/tasks/{id}/annotate` | `{itemId, label}`；任务归属/itemId∈任务否则 404；label∈labels 或 null 否则 400；**同步 upsert 提交后返回** updatedAt；审计异步入队 |
| GET | `/api/tasks/{id}/export` | **一份完整 CSV**（无 scope 参数，D4）；**仅 ready 可导出，否则 409**（R3 P2-3）；留档+流式下载 |

错误约定：4xx 带 `{detail}`；扫描/解压失败→任务 status=error+errorMsg（不抛 HTTP 错）。

## 8. 关键流程

### 8.1 绝对路径扫描
1. 校验路径存在/目录/可读（400）。
2. 后台线程递归扫描：跳过符号链接，图片扩展名过滤（不区分大小写），relPath 自然排序。
3. 分批 500 插入（同事务存在性校验 + INSERT OR IGNORE + 跳过计数）；更新 itemCount；完成 ready。
4. 0 项 → error“未发现支持的图片文件”。异常 → error+errorMsg。
5. 前端轮询 2s 终态即停。

### 8.2 压缩包上传（zip/7z/rar）
1. 前端 XHR 进度条；100% 后显示“服务器保存中…”。**耗时预期（R2 新-5）**：GB 级包 spool+拷贝≈2×体积写挂载点，分钟级等待属正常；README 注明。
2. 框架完整收包（>1MB spool 到 TMPDIR=挂载点 tmp/）后才进端点。**传输中断：端点不执行、无任务行、框架清理 spool、uploads/ 无孤儿**。
3. 端点（sync def）：扩展名+魔数校验（zip `PK`、7z `37 7A BC AF 27 1C` 完整 6 字节签名、rar `Rar!` 前缀覆盖 RAR4/5，否则 400）→ **spool 尺寸 ≤10GB 预检（否则 413+清理）** → 分块 1MB 拷贝至 `uploads/<uploadId>/<净化文件名>`（去路径分隔符）。拷贝失败：删部分文件+500，不建任务。
4. 拷贝成功 → **在 uploads/<uploadId>/ 写 `.taskCreated` 标记文件（内容 taskId；R4 P1-a，供启动清扫区分拷贝残留与已删任务保留原件）** → 建任务（extracting，sourceType 按格式，sourcePath=datasets/<uploadId>）→ 返回 taskId。
5. 后台解压到 `datasets/<uploadId>/`，**统一逐成员安全写出**：
   - **zip**：zipfile.infolist **预检**成员数 ≤20 万、uncompressed 总和 ≤20GB（仅作快速失败路径）；成员无 UTF-8 标志（flag_bits&0x800==0）时 `name.encode('cp437').decode('gb18030', errors='replace')`；
   - **7z/rar**：libarchive-c `file_reader` 遍历；成员名由 libarchive 解码（**若真实 rar 验收发现 RAR4 中文名乱码，实施期按 zip 同款 cp437→gb18030 思路对输出名回退**）；加密/分卷/损坏读取失败统一包装为明确 error 文案；
   - **统一实际量护栏（R3 P1-1）**：三引擎均**边写出边累计实际字节数与成员数**，超 20GB/20 万即中止→error（zip 中央目录声明值可伪造偏小绕过预检，预检不可作为唯一护栏）；**计数口径（R4 P2-a）：成员数按遍历到的全部成员累计（含跳过项，防 >20 万非图片成员无界遍历）；字节数仅按实际写出累计**；
   - 每成员：目标路径 resolve 后必须位于解压根内（**zip-slip 防护**），否则跳过记日志；跳过目录项与非图片扩展名；不递归嵌套压缩包；
   - 每批前校验任务存在且状态未变（force 删除/重启即退出）。
6. 解压完成 → scanning → 8.1 第 2 步起（含 0 项判定）。失败 → error；已解压部分保留供排查；error 任务可删（物理文件保留）。

### 8.3 实时标注（数字键 + 自动前进 + 失败可追踪）
1. **数字键 1-9 / 点击类别** → 乐观更新 UI → **立即自动前进到下一张**（D7；当前过滤列表内，最后一张停留提示）→ 后台 `POST annotate`。热键 0=清除并停留。
2. 后端：**同一写事务内**复检任务存在+归属+itemId∈任务（R3 P2-1，闭合与 force 删除的交错窗口）→ upsert 提交（updatedAt=UTC ISO）→ 审计入 `queue.Queue` → 返回。标注持久化同步实时（R8）；审计异步。
3. **审计单写线程**：消费队列追加 `audit-YYYYMMDD.jsonl`（按天切换），无交错；写失败降级告警（**挂载故障时文件告警不可达，控制台仍输出**——R2 新-6 措辞）。app.log 经 QueueHandler/QueueListener。**关停 drain（R2 新-6）**：lifespan shutdown 时 QueueListener.stop() + 审计队列 sentinel + 限时 join(5s)，重启不丢尾部审计。队列无界、≤10 人事件小，v1 内存可接受。
4. **前端保存状态机**：
   - 每 itemId 串行请求队列（点击/重试严格按序，杜绝过期覆盖）；不同项并行。
   - 三态：未标注/已标注/**未保存**（乐观未确认）；侧栏状态点+主区展示。
   - 顶栏：保存中…/已保存 HH:MM:SS/**N 条待重试+一键重试**；失败自动重试 1 次，仍失败入待重试队列。
   - **localStorage 补传**：未确认标注写待传队列（taskId→itemId→{label,ts}，null 清除同样入队）；**页面加载：身份闸门→先补传（入队先于视图渲染，R2 新-3a）→渲染**；同项新点击以最新意图覆盖待传记录（ts 比较）；**补传遇 4xx 终态失败（任务已删等）→丢弃记录+提示（R2 新-3b）**，不永久滞留。
5. 自动前进不等待保存确认（速度优先）；失败项三态可追踪，回看/侧栏/一键重试兜底。

### 8.4 CSV 导出（每任务一份完整 CSV，D4）
- 列：`relPath, absPath, label, annotatorId, annotatorName, updatedAt`；annotator=任务创建者。
- 每个 item 一行（未标注 label/updatedAt 空）；**行数=itemCount**；行序 relPath 自然序（**固定排序键：路径按段比较、段内数字按数值**，如 img2<img10；R3 P2-5 使验收可复现）。
- UTF-8 BOM；csv 标准转义；先写 `exports/<taskId>_<时间戳>_<4位随机>.csv` 留档再 StreamingResponse 下载。
- 审计记录导出事件。多人标同一批数据时各自导出，relPath 一致可外部合并（README）。

## 9. 前端设计（vanilla，零 CDN）

```
static/
├── index.html
├── css/style.css
└── js/{api.js, app.js, taskView.js, labelView.js}
```

- hash 路由：`#/tasks`、`#/task/<id>`。
- **初始化**：`await api.init()`（身份注册+localStorage 对齐）→ **补传待传队列** → 渲染视图。
- **任务列表页（仅本人任务，D4）**：
  - 创建表单：名称；来源二选一（绝对路径 / 压缩包上传 zip/7z/rar，进度条+“服务器保存中”+分钟级耗时提示）；**标签映射编辑器**：增删类别、显示序号↔热键映射预览（前 9 个标 1-9）、trim 去重；创建后不可改提示；
  - 任务卡片：名称、来源、状态动画（extracting/scanning 轮询）、总数、进度条、errorMsg 红字、操作（打开/导出/删除 confirm；**导出按钮非 ready 禁用**，R3 P2-3；非终态删除提示 409 并提供**强制删除**选项）。
- **标注页**：
  - 非 ready 任务：状态/errorMsg 占位视图，**不展示进度条与标注区**（R2 新-10 措辞），禁用标注/导出，可返回列表；处理中态轮询至终态自动刷新；
  - 主展示区：`<img>` 自适应 contain，加载失败兜底提示；
  - 类别按钮栏：热键角标 1-9（前 9 个），>9 仅点击；当前项已选高亮；清除按钮（0）；
  - **数字键标注→自动下一张**（D7）；←/→ 手动；索引跳转（当前过滤列表内序号）；过滤切换（全部/未标注/已标注）；未标注过滤下标注后该项移出并自动前进；**过滤列表清空后显示占位+「查看全部」按钮（R3 P2-2 / R4 P2-b：未标注过滤空=「已全部标注」；已标注过滤空=「暂无已标注项」）**；
  - 进度条：已标注/总数；
  - 侧栏：分页 100，relPath+三态点，点击跳转；
  - 顶栏：任务名、保存指示（N 条待重试/一键重试，**计数与过滤无关、重试覆盖全部失败项**，R3 P2-2）、标注人名（可改）、**导出按钮（单一，完整 CSV，非 ready 禁用）**、返回。
- 输入框聚焦时不拦截键盘。首访引导设置显示名（可跳过；默认名已在注册时入库，见 §7）。

## 10. 并发与独立性模型

- **身份**：clientId=uuid4，cookie+localStorage；换浏览器/清缓存=新身份（README 说明）；双标签首访对齐（7 节）。
- **任务私有（D4）**：列表按 creatorId 过滤；任务/数据项/内容/导出全链路归属校验 404。A/B 互不可见，天然无覆盖冲突；同批数据=各自导入建任务。
- **DB 并发**：WAL+busy_timeout；每请求独立连接短事务；**写事务统一 BEGIN IMMEDIATE**（R4 建议，避免 WAL 读升级写的快照 BUSY 竞态）；后台线程同事务批插入+存在性校验。
- **后台线程生命周期**：启动恢复中间态→error；批前校验；非终态删除 409/force 置 error 即退出。无孤儿、无滞留、卡死有出路。
- **审计并发**：队列+单写线程无交错；关停 drain。

## 11. 安全与健壮性

- 内容服务只认注册 itemId + 归属校验 → 无任意文件读取、无跨用户访问。
- zip-slip 防护（zip/7z/rar 统一）、文件名净化、uploadId 隔离、魔数校验、10GB 上传预检（413）、**20GB/20 万成员解压护栏（三引擎实际写出量累计，防声明伪造）**、GBK 文件名回退、加密/分卷/损坏统一明确 error 文案。
- 无认证（用户明确）：README 警示仅限局域网；端口可配（CLS_PORT）。
- 图片损坏浏览器兜底+前端提示。
- 磁盘/写失败：500+日志；前端失败队列刷新不丢。
- 根盘护栏：start.sh mkdir -p + TMPDIR 挂载点；启动自检可写。

## 12. 日志

- `logs/app.log`：QueueHandler+QueueListener+RotatingFileHandler(10MB×5)+控制台；启动/API 异常/扫描/解压/上传事件与耗时。
- `logs/audit-YYYYMMDD.jsonl`：`{ts, clientId, action, taskId, itemId?, label?, extra?}`；action ∈ annotate/clear/createTask/upload/export/deleteTask/renameClient；队列+单写线程异步按天切换；失败降级控制台告警。
- 关停 drain（8.3.3）。

## 13. 部署与运行

- uv init（Python 3.12）；依赖 4 个：fastapi、uvicorn、python-multipart、libarchive-c；uv.lock 锁定。包源已核实（pypi/aliyun 200）。libarchive.so.13 系统已有（3.7.2）。
- `start.sh`：
  ```bash
  cd "$(dirname "$0")"
  mkdir -p /data_27T_jfs95/wilbur/clsToolData/tmp
  export TMPDIR=/data_27T_jfs95/wilbur/clsToolData/tmp
  uv run uvicorn main:app --host 0.0.0.0 --port ${CLS_PORT:-8686}
  ```
- README：启动/局域网访问/使用流程（建任务→设标签映射→数字键标注→导出）/数据日志位置/已知限制（仅图片、单标签、标签创建后不可改、任务互相看不见、同批数据各自导入、CSV 外部合并方式、加密/分卷/嵌套压缩包不支持、换浏览器=新身份、物理文件不随任务删除、GB 级上传分钟级等待、卡死任务可强制删除或重启恢复、根盘紧张提示 uv cache clean、nohup 示例携带 TMPDIR）。
- 不引入 systemd/docker。

## 14. 代码规范（用户强制规则）

- 标识符与文件名**小驼峰**；模块：`main.py, config.py, database.py, logUtil.py, auditService.py, clientApi.py, taskApi.py, annotationApi.py, fileApi.py, scanService.py, archiveService.py, exportService.py`。
- 新建代码文件必须文件头：`Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: ...`；改动递增小版本+Description 说明。
- **禁止任何测试框架**；curl+原生脚本+手工验收。
- 前端：index.html, style.css, api.js, app.js, taskView.js, labelView.js（带文件头注释）。

## 15. 验收标准（v1.4）

**真实素材（已核实存在）**：`/data_27T_jfs95/wilbur/三跨图片-1.zip`（717MB）、`20261113潇湘变项目全栈图片标注.zip`（2.1GB 中文名）、`潇湘站全站巡视（可见光）.7z`（3.5GB 中文名）、`UAV_Inspection/杆塔倾斜检测/中台任务-10kV23xx线-20260810-982巡检原始影像.rar`（真实 rar）、`Datasets/` 下图片目录（路径导入用例）。日常冒烟用合成小 zip（含 GBK 名/重名成员/zip-slip/空包用例），真实大包作为扩展验收（耗时分钟级）。系统已有 `/usr/bin/zip` 与 `zipcloak`（R3 核实），可生成加密 zip 用例；「声明偏小、实际偏大」伪造 zip 用原生脚本改中央目录生成（不引测试框架）。

1. 一键启动；局域网另一机器可访问。
2. 路径导入图片目录 → 扫描完成、数量=目录实际图片数。
3. zip 上传（合成 GBK 中文小包）→ 解压 relPath 无乱码；uploads 留原件；重名成员去重跳过计数、任务正常。
4. **7z 上传解压可用**（合成小包冒烟 + 真实 3.5GB 包扩展验收）；**中文成员名 relPath 无乱码断言**（R3 P2-5）。
5. **rar 上传解压可用**（真实 rar 包验收；系统无 rar 生成工具，不合成）；**中文成员名 relPath 无乱码断言**（RAR4 名乱码则按 8.2 回退方案修复后复验）。
6. **数字键 1-9 标注→自动下一张**；DB 同步可查、审计秒级可查；刷新不丢；0 清除停留；最后一张停留提示。
7. **隐私**：B 列表看不到 A 的任务；B 直接请求 A 的 taskId/itemId/export → 404；**同浏览器双标签同时首访 → 同一 clientId**（R3 P2-5）。
8. **同批独立**：A/B 各自导入同一路径建任务，独立标注互不影响，各自导出完整 CSV，relPath 一致。
9. CSV：行数=itemCount、行序符合固定自然序键、BOM、Excel 中文无乱码、**annotatorName 非空（默认名兜底）**、exports 留档。
10. app.log+audit JSONL 在挂载点 logs/，JSONL 无交错；关停后尾部审计不丢。
11. 热键/←→/过滤（未标注态自动前进、**清空后占位+查看全部**）/跳转/侧栏分页三态/标签映射预览均可用；**>9 类别仅点击、热键只映射前 9**（R3 P2-5）。
12. **失败链路**：断网点击→未保存态+N 条待重试→恢复一键重试成功；失败期间刷新→加载自动补传成功；补传遇已删任务 4xx→丢弃+提示。
13. **重启恢复**：处理中重启→error+提示，轮询终止，可删除重建。
14. **删除护栏**：非终态 409；force 删除成功且后台线程退出、无孤儿 items；终态删除后 content 404。
15. **边界**：zip-slip 成员跳过任务正常；坏路径 400；空目录/空包/无图片→error 提示；非 zip/7z/rar→400；坏魔数→400；>10GB→413（代码走查+可行时实测）；解压护栏双向验证：**声明偏大伪造 zip 触发预检** + **实际量护栏用临时调低阈值法验证（原生脚本 import 解压服务调小阈值后解压正常小 zip，断言中止+护栏专用 errorMsg；E1 核实 zipfile 按声明尺寸截断读取，「声明偏小伪造」只会触发损坏错误而非字节护栏，故不用该法）**（R3 P1-1）；加密包（zipcloak 生成）→error 明确文案。
16. spool 落挂载点 tmp/（根盘无大临时文件）；传输中断 uploads/ 无孤儿残留；**拷贝窗口重启后启动清扫孤儿 uploads 目录**（R3 P2-4）；**删除任务后重启，uploads 原件仍在（标记保护，R4 P1-a）**。
17. **导出守卫**：extracting/scanning/error 任务 export → 409，前端按钮禁用（R3 P2-3）。

## 16. 风险与取舍

| 风险/取舍 | 说明 | 缓解 |
|-----------|------|------|
| SQLite 本机 vs 挂载点 | 网络 FS 锁风险；/home 已核实 ext4 | DB 本机，大文件在挂载点 |
| 根盘 99% | spool 默认 /tmp 撑爆根盘 | start.sh mkdir+TMPDIR 挂载点 |
| JuiceFS 延迟 | 审计/导出/拷贝慢 | 审计异步降级；标注主流程不依赖挂载 IO；拷贝耗时预期已注明 |
| 声明伪造 zip | 中央目录尺寸可偏小绕过预检 | 三引擎实际写出量累计护栏（R3 P1-1） |
| libarchive rar 覆盖 | 3.7.2 支持 rar/rar5 读取；加密/分卷不支持；RAR4 非 ASCII 名依赖 charset 转换 | 真实 rar 包验收+乱码断言；必要时 cp437→gb18030 回退；明确 error 文案 |
| GB 级上传等待 | spool+拷贝 2×体积 | 进度条+“服务器保存中”+README 预期 |
| 任务私有不可共享 | D4 用户选定最简模型 | 同批各自导入；CSV relPath 一致可外部合并 |
| 标签不可改 | D6 创建时固定 | 删除重建；创建表单映射预览降低出错 |
| 换浏览器=新身份 | 无账号固有 | README 说明 |
| localStorage 补传窗口 | 清缓存丢未确认标注 | 仅影响失败未重试窗口；正常标注同步落库 |
| 单进程吞吐 | ≤10 并发足够 | 超规模再议 |

## 17. TODO 概览（执行计划另档细化）

- M1 骨架：uv 项目（3.12）、4 依赖、目录自检（含 tmp）、config、日志队列+关停 drain、启动恢复 → 验证：启动/目录/恢复
- M2 数据层：schema（私有任务模型）、client API+身份对齐 → 验证：curl 双客户端
- M3 导入：路径扫描（图片过滤/空集/去重）、archiveService（zip GBK/7z/rar libarchive/护栏/zip-slip）、upload（魔数/413/拷贝）、任务 CRUD（归属 404/409/force） → 验证：curl+合成包+真实包
- M4 标注与内容：annotate 同步 upsert、items 分页过滤、图片 content（归属校验） → 验证：curl 写查
- M5 导出与审计：完整 CSV（行序/BOM/留档）、审计单写线程 → 验证：内容核对/无交错
- M6 前端：身份闸门+补传先行、任务页（映射编辑器/状态视图/force 删除）、标注页（数字键自动前进/三态/失败队列/过滤） → 验证：双浏览器隐私+失败链路
- M7 集成验收：§15 十七条逐条 → 验收记录
- M8 文档：README、start.sh、交付说明

## 18. 审核记录

| 轮次 | 日期 | 审核方 | 结论 | 处理 |
|------|------|--------|------|------|
| R1 | 2026-11-20 | qwen-token-plan/qwen4-max:xhigh | BLOCK（7 P1/7 P2） | v1.1 全部修复 |
| R2 | 2026-11-20 | qwen-token-plan/qwen4-max:xhigh | OK with notes（R1 全 RESOLVED；新 10 P2） | v1.2 全部采纳：新-1 start.sh mkdir TMPDIR；新-2 force 删除+同事务校验；新-3 补传先于渲染/最新意图覆盖/4xx 丢弃；新-4 10GB 预检 413；新-5 拷贝耗时+sync def；新-6 关停 drain+告警措辞；新-7 INSERT OR IGNORE 去重计数；新-8 格式已由用户确认 zip/7z/rar；新-9 双标签 localStorage 对齐；新-10 措辞修正 |
| 用户确认 | 2026-11-20 | wilbur | 5 项决定 | D1 仅图片+数字键自动前进；D2 单标签；D3 zip/7z/rar；D4 任务互相看不见+每任务完整 CSV；D5 Python 3.12 → v1.2 全面改写（移除文本支持、私有任务模型、annotations 简化、libarchive 双引擎、自动前进 UX） |
| R3 | 2026-11-20 | qwen-token-plan/qwen4-max:xhigh | OK with notes（D1-D7+R2 全 RESOLVED；新 1 P1/7 P2/2 小项） | v1.3 全部修复：P1-1 三引擎实际写出量累计护栏+双向伪造验收；P2-1 annotate 写事务复检+删除同事务级联；P2-2 空过滤占位+计数与过滤无关；P2-3 export 仅 ready 否则 409+按钮禁用；P2-4 启动清扫孤儿 uploads；P2-5 验收补乱码断言/>9 类别/双标签/自然序键；P2-6 7z 魔数 6 字节；P2-7 注册默认名入库；小项：已标注数措辞+start.sh cd |
| R4 | 2026-11-20 | qwen-token-plan/qwen4-max:xhigh | OK with notes（R3 修复基本到位；清扫判据越界 1 P1 + 3 修复引入小 P2；“修掉即达 OK”） | v1.4 全部修复：P1-a `.taskCreated` 标记+清扫判据「无任务行且无标记」+保留断言；P2-a 成员数含跳过/字节仅写出；P2-b 占位文案按过滤区分；P2-c §15 版本/§17 计数同步；另采纳 BEGIN IMMEDIATE 建议 |
| R5 | 2026-11-20 | qwen-token-plan/qwen4-max:xhigh | **OK**（四项全 RESOLVED，无新 P0/P1） | 方案 v1.4 定稿，进入执行计划阶段 |
| 环境修正 | 2026-11-20 | 父会话实测 | 8000/8080/9000 端口被占，8686 空闲 | 默认端口 8000→8686（CLS_PORT 可覆盖）；node v22.23.2 与 sqlite3 CLI 可用（验证手段） |
| E1 联动澄清 | 2026-11-20 | 执行计划审核（对照 zipfile 源码） | 「声明偏小伪造触发字节护栏」不可达（zipfile 按声明尺寸截断读取） | §15.15 验证方法澄清为调低阈值法；设计保证不变（三引擎实际写出量累计） |