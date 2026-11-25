# clsLabelTool 执行计划

- Author: wilbur（flamingo 助理起草）
- Version: 1.1
- Date: 2026-11-20
- Description: 分类数据标注工具实施执行计划。设计依据 261120_clsLabelToolPlan.md v1.4（R5 OK 定稿）。v1.0 初稿；v1.1 按 E1 审核（BLOCK）修复全部 4 P1（GBK 用例构造法、字节护栏验证法、写权限边界、M3 前置顺序）+6 P2（M1 内部顺序、手工/自动分工纠偏、实现落点补全、验证手段细节、自然序分页指引、检查点通道）。供 E2 复审。

---

## 1. 依据与目标

- **设计契约**：`docs/plan/261120_clsLabelToolPlan.md`（v1.4，§18 审核轨迹 R1→R5 闭环）。实施前必须完整读取；任何偏离需上报父会话决策，不得静默改设计。
- **成功判据**：设计 §15 的 17 条验收全部通过（自动化项由实施子代理取证，浏览器交互项由用户按清单手工验收）；服务保持运行可访问；README/start.sh 交付。
- **实施方**：子代理 worker，模型 `101/qwen3.8-pi`，cwd `/home/wanshicong/projects/clsLabelTool`，单一写者。

## 2. 环境事实与前置检查（父会话已核实）

| 项 | 事实 |
|----|------|
| Python | 3.12.3 已装（/usr/bin/python3.12），用户已确认用 3.12；uv 0.12.21（/snap/bin/uv） |
| 包源 | pypi.org / mirrors.aliyun.com 均 200 可达 |
| libarchive | /lib/x86_64-linux-gnu/libarchive.so.13（3.7.2）实存，支持 rar/rar5/7z 读取；**无需 sudo** |
| 系统工具 | 无 unrar/unar/7z 二进制；有 /usr/bin/zip、zipcloak（生成加密 zip 用例）；sqlite3 CLI 可用；node v22.23.2 可用（JS 语法校验） |
| 磁盘 | /home 为 ext4 本机盘但**根盘 99%（剩 12.7GB）**：venv/DB 小体积可放；**一切大文件（fixtures/解压/spool）必须在挂载点**；TMPDIR 必须指向 clsToolData/tmp |
| 挂载点 | /data_27T_jfs95 JuiceFS 剩 4.4T；wilbur 目录 777；clsToolData 尚不存在（启动创建） |
| 端口 | 8000/8080/9000 被占；**默认 8686（空闲）**，CLS_PORT 可覆盖 |
| 真实素材（只读，严禁修改/移动/删除） | `/data_27T_jfs95/wilbur/三跨图片-1.zip`（717MB）、`20261113潇湘变项目全栈图片标注.zip`（2.1GB）、`潇湘站全站巡视（可见光）.7z`（3.5GB）、`UAV_Inspection/杆塔倾斜检测/中台任务-10kV23xx线-20260810-982巡检原始影像.rar`、`Datasets/` 下图片目录 |

前置检查（M1 第一步执行）：`uv --version`、`python3.12 --version`、`ldconfig -p | grep libarchive`、`ss -tln | grep 8686`（空闲）、`df -h /data_27T_jfs95`。任一不符 → contact_supervisor 上报。

## 3. 交付文件清单（小驼峰 + 文件头）

```
clsLabelTool/
├── pyproject.toml / uv.lock / .python-version   # uv 生成，Python 3.12
├── start.sh                  # cd dirname → mkdir -p TMPDIR → export TMPDIR → uv run uvicorn（§13）
├── README.md                 # 使用/限制/FAQ/nohup 携带 TMPDIR/CSV 外部合并/uv cache clean（§13）
├── main.py                   # FastAPI app + lifespan（启动：建目录→挂载自检→schema→恢复 UPDATE→孤儿清扫；关停：审计 drain）+ 静态托管 + 路由注册 + /api/health（§4/§5/§6）
├── config.py                 # DATA_ROOT/子目录/DB_PATH/IMAGE_EXTS/护栏常量(10GB/20GB/20万/批500/块1MB)/端口（§3 A5/§5）
├── database.py               # 连接助手(WAL/busy_timeout=5000/Row)、initSchema DDL、writeTx 上下文(BEGIN IMMEDIATE)（§6/§10）
├── logUtil.py                # QueueHandler+QueueListener+Rotating(10MB×5)+控制台（§12）
├── auditService.py           # queue.Queue+单写线程+按天 JSONL+sentinel drain+失败控制台告警（§8.3.3/§12）
├── clientApi.py              # GET/PUT /api/client；身份解析依赖（头>cookie>新建；注册默认名；lastSeen）（§7）
├── taskApi.py                # 任务 CRUD+归属校验 404+409/force 级联删+upload 端点(sync def)（§6/§7/§8.2）
├── scanService.py            # 后台路径扫描（自然序插入/批插入同事务校验/OR IGNORE/空集 error）（§8.1）
├── archiveService.py         # zip/7z/rar 统一解压（GBK 回退/zip-slip/实际量护栏/魔数/错误包装/批前校验）（§8.2.5）
├── annotationApi.py          # annotate(写事务复检)+items 分页过滤（§7/§8.3）
├── fileApi.py                # content 图片服务（归属校验+MIME）（§7）
├── exportService.py          # 完整 CSV（BOM/自然序/留档随机后缀/ready 守卫 409）（§8.4）
├── static/index.html         # 页面骨架（M1 先占位，M6 完整；经典脚本按序引入）（§9）
├── static/css/style.css      # 样式，零 CDN（§9）
├── static/js/api.js          # 身份闸门+localStorage 对齐+请求助手+每 itemId 串行队列+待传 map+补传先行+4xx 丢弃+重试（§7/§8.3.4）
├── static/js/app.js          # hash 路由+视图切换+键盘分发（输入框聚焦不拦截）（§9）
├── static/js/taskView.js     # 创建表单(路径/上传+映射编辑器+热键预览)+任务卡片(轮询/进度/error/导出禁用/force 删除)+首访命名引导（§9）
├── static/js/labelView.js    # 标注页全部交互（数字键自动前进/三态/过滤空占位/侧栏分页/顶栏保存指示）（§9）
├── scripts/makeFixtures.py   # 原生合成用例生成（无框架；PNG 用 struct+zlib 手工构造；GBK zip 用 _encodeFilenameFlags 覆写法）
├── scripts/smokeCheck.py     # 原生 API 冒烟核对（urllib+sqlite3+json，无框架）
└── data/clsTool.db           # 运行时生成（本机磁盘）
```

- 每个新建代码文件文件头：`Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: ...`（HTML/CSS/JS 用对应注释语法）；修改已有文件递增小版本并更新 Description。
- scripts/ 下脚本也是代码文件，同样遵守文件头与小驼峰。
- **前端脚本约定（E1 P2-4）**：经典 script（非 ES module）+ 全局命名空间（如 window.clsApi），index.html 按依赖序引入（api.js→app.js→taskView.js→labelView.js）；保证 `node --check` 可校验。

## 4. 实施约束（worker 契约）

1. **单一写者与写边界（E1 P1-3 修正）**：代码/文档只写本 cwd；**运行数据与合成用例只写挂载点 `clsToolData/`（uploads/datasets/logs/exports/tmp/testFixtures）与 `<project>/data/`（DB）**；真实素材只读。不派发子代理；不做 git 操作。
2. **禁止测试框架**（pytest/unittest 等一律不用）；验证 = curl + 原生 Python 脚本 + sqlite3 CLI + node --check。
3. **零 CDN/零外网前端资源**；不装系统包（无 sudo）；依赖仅 fastapi/uvicorn/python-multipart/libarchive-c。
4. **真实用户数据只读**：合成用例一律生成到 `clsToolData/testFixtures/`；真实大包只通过正常上传流程使用（框架 spool+拷贝，不碰原件）。
5. **根盘保护**：大文件全在挂载点；服务启动必须经 start.sh（TMPDIR）；测试用 nohup 启动同样携带 TMPDIR。
6. **服务管理**：测试期间 nohup 后台起停；**停服一律 SIGTERM（kill 默认；严禁 -9，否则 lifespan drain 不触发）**；重启加载新代码；**交付时服务保持运行**，报告访问地址 `http://<服务器IP>:8686`。
7. **检查点汇报（E1 P2-6）**：每完成一个里程碑用 `contact_supervisor(reason=progress_update)` 发简报（变更文件、验证命令与结果、遗留问题）；全部完成后终报（验收记录路径、访问地址、待手工项清单）。
8. **升级规则**：设计偏离/阻塞决策/环境不符 → `contact_supervisor(reason=need_decision)`，不静默改设计。libarchive-c 实际 API 与方案描述有出入时：先写原生探针脚本实测（读真实 7z 首成员名/块），在**保持设计保证（逐成员安全写出/护栏/GBK 回退）不变**的前提下调整实现细节，属实现自由度；若保证无法达成 → 升级。
9. **大文件测试超时**：真实大包解压/上传测试 bash timeout ≥ 900s；失败重试不超过 2 次，仍失败记录并升级。
10. **简洁优先**：不超出设计范围添加功能/抽象/配置项。

## 5. 里程碑 TODO（按序执行，每步验证在该步即可执行——E1 P1-4/P2-1 重排）

### M1 环境骨架（设计 §4/§5/§6/§12/§13）
- [ ] 1.1 前置检查（§2 表）→ 验证：命令输出符合
- [ ] 1.2 `uv init`（Python 3.12，不生成示例代码，若生成则删除示例）→ `uv add fastapi uvicorn python-multipart libarchive-c` → 验证：`uv run python -c "import fastapi, uvicorn, multipart, libarchive"` 成功
- [ ] 1.3 start.sh（cd "$(dirname "$0")" → mkdir -p TMPDIR → export TMPDIR → uv run uvicorn，CLS_PORT 默认 8686）→ 验证：异地目录调用 bash <绝对路径>/start.sh 可起服（此时 main.py 尚未写，先验脚本语法 bash -n，起服验证留 1.7）
- [ ] 1.4 config.py（全部常量）→ 验证：uv run python -c 导入核对常量
- [ ] 1.5 database.py（连接助手/initSchema/writeTx BEGIN IMMEDIATE）→ 验证：原生脚本建库、sqlite3 CLI 查 schema 四表+索引
- [ ] 1.6 logUtil.py（队列日志）→ 验证：原生脚本初始化后 logs/app.log 有记录
- [ ] 1.7 main.py lifespan 启动序列：建目录(uploads/datasets/logs/exports/tmp+data) → 挂载可写自检(写删探针文件，失败退出) → initSchema → 恢复 UPDATE(extracting/scanning→error) → 孤儿清扫(uploads 下无任务行且无 .taskCreated 的目录)；/api/health；**先建 static/index.html 占位文件再挂 StaticFiles（check_dir 缺目录会 RuntimeError，E1 P2-1）**；路由随里程碑注册 → 验证：nohup bash start.sh 起服；curl health 200；ls 目录齐全；curl / 返回占位页
- [ ] 1.8 恢复/清扫原生脚本验证：sqlite3 插入假 extracting 任务行 + 造假 uploads 目录(无标记/有标记各一) → SIGTERM 重启 → 断言：假任务变 error、无标记目录被清、有标记目录保留 → 验证后清理假数据
- [ ] 1.9 **M1 检查点汇报**

### M2 数据层与客户端（§7/§8.3.3/§12）
- [ ] 2.1 clientApi.py：身份解析依赖（X-Client-Id 头 > cookie > 新建 uuid；Set-Cookie；注册 name 空则默认「标注员-<id前4位>」；lastSeen 更新）；GET/PUT /api/client（trim/非空/≤32）→ 验证：curl 带 testA/testB 头 → 各自身份；sqlite3 查默认名；PUT 改名生效；同名重复 GET 幂等
- [ ] 2.2 auditService.py：队列+单写线程+按天 JSONL+sentinel drain；**关停挂钩含 QueueListener.stop() + 写线程 join(5s)（E1 P2-3）**；renameClient 事件入审计 → 验证：curl 改名后秒级内 JSONL 出现对应行；xargs -P 8 并发改名 → **等待秒级 flush 后**每行均可 json.loads（无交错）；**SIGTERM** 停服尾部事件不丢
- [ ] 2.3 **M2 检查点汇报**

### M3 任务与数据导入（§6/§7/§8.1/§8.2；顺序：fixtures→扫描→任务 API→解压→上传端点，E1 P1-4）
- [ ] 3.1 scripts/makeFixtures.py（合成到 clsToolData/testFixtures/）：
  - 合成图片目录（手工 PNG：struct+zlib 构造最小合法 PNG）；
  - 正常 zip、重名成员 zip、zip-slip 成员 zip(../evil.png)、空包、无图片包；
  - **GBK 中文名 zip（E1 P1-1 修正构造法）**：`zi = zipfile.ZipInfo(placeholder); zi._encodeFilenameFlags = lambda: (期望中文名.encode('gb18030'), 0)` 后 writestr——盘上名字节为 GBK 原字节且 flag=0（zipfile 默认对非 ASCII 名自动置 UTF-8 标志，普通构造法造不出无标志包）；**生成后断言：读回 flag_bits&0x800==0 且 name.encode('cp437').decode('gb18030')==期望中文名**；
  - **声明偏大伪造 zip**（触发 infolist 预检）：struct 改中央目录 file_size 偏大（注意 32 位字段，单成员 >4GB 用多成员累计或 Zip64 extra）；
  - **损坏包**（声明偏小致读取截断 CRC 失败——E1 P1-2：zipfile 按声明尺寸截断，此包只能验“损坏 error 文案”，**不能**验字节护栏）；
  - **加密 zip**：zipcloak CLI 生成，**断言 flag_bits&0x1**；
  → 验证：脚本运行生成全部用例、逐包断言通过
- [ ] 3.2 scanService.py：递归扫描（跳符号链接/图片扩展名过滤/固定自然序键：路径按段、段内数字按数值）；**按自然序插入（itemId 序即自然序，供 items/export ORDER BY itemId 使用，E1 P2-5，禁止改 schema）**；批 500 同事务(存在性+状态校验)+INSERT OR IGNORE+跳过计数；itemCount；0 项→error；异常→error → 验证：**原生脚本直调扫描函数**（合成目录）→ sqlite3 断言数量=实际图片数、itemId 序=自然序、重名去重计数、空目录 error
- [ ] 3.3 taskApi.py：POST /api/tasks（路径校验 400/labels trim 去重非空 400/后台扫描）；GET 列表（仅本人+已标注数）；GET 详情（归属 404）；DELETE（终态直删同事务级联 tasks/items/annotations；非终态 409；force=true 先置 error 再级联删）→ 验证：curl 路径建任务→轮询 ready→计数核对；双客户端互见 404；409/force 行为；删除后 sqlite3 无孤儿行
- [ ] 3.4 archiveService.py：格式分派；zip=zipfile+GBK 回退(flag&0x800==0→cp437→gb18030)+infolist 预检(快速失败)；7z/rar=libarchive-c file_reader（**先写探针脚本实测 API：读真实 7z 首成员名/块**）；统一逐成员：resolve 目标必须在解压根内否则跳过记日志、跳目录/非图片、不递归嵌套；**成员数按遍历全部累计(含跳过)、字节按实际写出累计**，超限中止→error（**护栏专用 errorMsg，与损坏/加密文案区分，E1 P1-2**）；**解压循环每批前校验任务存在+状态未变（E1 P2-3，force 删除即退出）**；加密/分卷/损坏包装明确 error 文案 → 验证：**原生脚本直调解压函数**（先建临时任务行）逐用例断言：GBK 名无乱码/重名去重/zip-slip 跳过任务正常/空包与无图片 error/声明偏大触发预检/损坏包 error 文案/加密包 error 文案；**实际量护栏验证（E1 P1-2 修正法）：原生脚本 import archiveService/config，临时调小字节/成员阈值后解压正常小 zip，断言中止+护栏专用 errorMsg**（验证后恢复阈值）
- [ ] 3.5 upload 端点（sync def）：扩展名+魔数(zip PK/7z 37 7A BC AF 27 1C/rar Rar!)否则 400；spool 尺寸>10GB→413 清理不建任务（代码走查+可行时实测）；分块 1MB 拷贝至 uploads/<uploadId>/<净化名>；拷贝失败删部分+500 不建任务；成功→写 .taskCreated(内容 taskId)→建任务 extracting→后台解压→scanning→ready/error → 验证：curl -F 上传合成包全链路（GBK 包/正常包）；uploads 原件+标记存在；datasets 解压正确；坏魔数 400；非 zip/7z/rar 400
- [ ] 3.6 真实路径导入冒烟：选 Datasets/ 下**小**图片目录 curl 建任务 → 验证：ready+数量核对
- [ ] 3.7 **M3 检查点汇报**

### M4 标注与内容服务（§7/§8.3）
- [ ] 4.1 annotationApi.py：POST annotate（BEGIN IMMEDIATE 写事务内复检任务存在+归属+itemId∈任务→label∈labels 或 null→upsert/删行→updatedAt UTC ISO→提交→审计入队→返回）；GET items（offset/limit/filter=all|unlabeled|labeled，**ORDER BY itemId（自然序，E1 P2-5）**，带 label）→ 验证：curl 标注后 sqlite3 **立即**有行；审计秒级；null 清除删行；非法 label 400；跨用户 404；filter 计数正确；行序=img2 在 img10 前
- [ ] 4.2 fileApi.py：GET content（itemId→任务归属 404；图片字节+扩展名 MIME）→ 验证：curl --output 与源文件 cmp 字节一致；跨用户 404；不存在 404
- [ ] 4.3 **M4 检查点汇报**

### M5 导出与审计闭环（§8.4/§12）
- [ ] 5.1 exportService.py：GET export（ready 守卫否则 409；列 relPath,absPath,label,annotatorId,annotatorName,updatedAt；每 item 一行未标注空；行数=itemCount；**ORDER BY itemId 自然序（E1 P2-5）**；UTF-8 BOM；csv 标准转义；先写 exports/<taskId>_<ts>_<4位随机>.csv 再 StreamingResponse；审计 export 事件）→ 验证：scripts/smokeCheck.py 核对行数/行序/BOM 头三字节/列名/annotatorName 非空；exports 留档存在；extracting/error 任务 export 409
- [ ] 5.2 并发审计终验：xargs -P 8 并发标注 → **等待秒级 flush** → JSONL 每行可解析、事件数=请求数；**SIGTERM** 停服尾部不丢 → 验证：原生脚本断言
- [ ] 5.3 **M5 检查点汇报**

### M6 前端（§9，零 CDN，经典脚本+全局命名空间）
- [ ] 6.1 api.js：init 闸门（await GET /api/client；localStorage set-if-absent+复读对齐；此后所有请求带 X-Client-Id）；请求助手；每 itemId 串行队列；待传 map（taskId→itemId→{label,ts}，null 同样入队）；**加载补传先于视图渲染**；同项新点击最新意图覆盖；4xx 终态丢弃+提示；自动重试 1 次+一键重试 → 验证：node --check；逻辑走查对照 §8.3.4
- [ ] 6.2 app.js：hash 路由(#/tasks、#/task/<id>)；键盘分发（输入框聚焦不拦截；1-9/0/←→）→ 验证：node --check
- [ ] 6.3 taskView.js：创建表单（路径/上传二选一；XHR 进度+100%后「服务器保存中…」+分钟级提示；标签映射编辑器增删+序号热键预览+创建后不可改提示）；任务卡片（状态动画轮询 2s 终态停/总数/进度条/errorMsg 红字/打开/导出非 ready 禁用/删除 confirm+非终态 409 提示+强制删除选项）；仅本人任务；**首访引导设置显示名（可跳过，默认名已入库，E1 P2-3）** → 验证：node --check；curl 静态 200
- [ ] 6.4 labelView.js：非 ready 占位视图（状态/errorMsg，不展示进度条与标注区，禁用标注/导出，处理中轮询终态自动刷新）；img contain+加载失败提示；类别按钮热键角标（前 9，>9 仅点击）+已选高亮+清除(0)；**数字键/点击→乐观标注→自动前进**（过滤列表内，最后一张停留提示）；←/→；索引跳转（过滤列表内序号）；过滤切换+**空占位按过滤区分文案（未标注空=已全部标注；已标注空=暂无已标注项）+查看全部**；进度条；侧栏分页 100+三态点+点击跳转；顶栏（任务名/保存指示 N 条待重试与过滤无关+一键重试/标注人名可改/导出非 ready 禁用/返回）→ 验证：node --check；逻辑走查对照 §9
- [ ] 6.5 index.html（替换 M1 占位，按序引入 js）+ style.css：骨架+样式；grep 确认无 http(s) 外部资源引用 → 验证：curl 页面与全部静态资源 200；node --check 全 js
- [ ] 6.6 **M6 检查点汇报**

### M7 集成验收（设计 §15 十七条；自动/手工分工按 E1 P2-2 纠偏）
- [ ] 7.1 自动化项逐条执行并取证（curl/原生脚本/sqlite3）：
  - #1 启动+绑定 0.0.0.0:8686（ss+curl；**另一机器实际访问属手工**）
  - #2 路径扫描计数；#3 zip GBK/重名/原件+标记
  - #6 **API 层**：标注同步落库+审计秒级+null 清除（自动前进/0 停留/最后一张提示/刷新不丢属手工）
  - #7 **API 层**：跨用户 taskId/itemId/export 404+头>cookie>新建幂等（双标签 UI 对齐属手工）
  - #8 同批独立（双客户端各自建任务/标注/导出）+CSV relPath 一致
  - #9 CSV 全断言；#10 日志无交错+SIGTERM drain
  - #12 **API 层**：停服→annotate 请求失败→起服→同请求成功；已删任务 annotate→4xx（localStorage 补传/刷新不丢/丢弃提示/三态 UI 属手工）
  - #13 重启恢复；#14 删除护栏+force+后台线程退出+无孤儿
  - #15 边界全集：zip-slip/坏路径 400/空集 error/非支持格式 400/坏魔数 400/413 走查/声明偏大预检/**实际量护栏调低阈值法（护栏专用 errorMsg）**/损坏包文案/加密包文案
  - #16 spool 位置+中断无孤儿+清扫+标记保留（删除任务后重启原件仍在）
  - #17 导出守卫 API 409（按钮禁用属手工）
- [ ] 7.2 真实大包扩展验收（timeout≥900s）：上传 潇湘站全站巡视（可见光）.7z（3.5GB）→ 解压 ready → **中文 relPath 无乱码断言** → 抽样 content 字节核对；上传真实 rar → 同样断言（**若 RAR4 中文名乱码：按设计 §8.2.5 回退方案修复后复验**）；上传 20261113潇湘变项目全栈图片标注.zip（2.1GB 中文名）→ 正常；记录各包耗时/项数
- [ ] 7.3 浏览器手工项清单输出（供用户验收，子代理无法操作浏览器），**列全子项（E1 P2-2）**：
  - #1 另一台机器浏览器访问
  - #6 数字键标注→自动下一张手感；0 清除停留；最后一张停留提示；刷新页面标注不丢
  - #7 同浏览器双标签同时首访→同一身份（UI 显示一致）
  - #11 热键 1-9/←→/过滤切换/未标注态自动前进/清空后占位文案+查看全部/索引跳转/侧栏分页三态点/标签映射预览/>9 类别仅点击
  - #12 断网点击→未保存态+顶栏 N 条待重试→恢复一键重试；失败期间刷新→自动补传；已删任务补传→丢弃+提示
  - #17 非 ready 任务导出按钮禁用态
  - #4/#5 前端图片展示侧（7z/rar 任务打开浏览）
- [ ] 7.4 撰写 `docs/plan/261120_acceptanceRecord.md`：17 条逐条（方法/证据/结果/待手工子项）→ 验证：自动化项全 PASS
- [ ] 7.5 **M7 检查点汇报**

### M8 文档与交付（§13）
- [ ] 8.1 README.md：启动（bash start.sh / nohup 携带 TMPDIR 示例）、局域网访问地址、使用流程（建任务→设映射→数字键标注→导出）、数据/日志位置、全部已知限制（设计 §13 清单）、同批 CSV 外部合并方法、卡死任务 force/重启、uv cache clean、换浏览器=新身份
- [ ] 8.2 清理测试残留：testFixtures 保留（供复验）但假任务/假数据清掉；服务以正式配置保持运行（SIGTERM 旧测试进程后正式起服）
- [ ] 8.3 终报（contact_supervisor progress_update）：变更文件清单、验收记录路径、访问地址、待手工清单、遗留风险
- [ ] 8.4 **M8 终报**

## 6. 验收分工（设计 §15 → 执行方式；E1 P2-2 纠偏：浏览器侧子项一律手工）

| 条 | 内容摘要 | 自动部分（worker） | 手工部分（用户） |
|----|----------|--------------------|------------------|
| 1 | 启动+局域网访问 | ss 绑定+curl | 另一机器浏览器访问 |
| 2 | 路径扫描计数 | 全部 | — |
| 3 | zip GBK/重名/原件 | 全部 | — |
| 4 | 7z 解压+中文断言 | 全部（真实包） | 前端图片展示 |
| 5 | rar 解压+中文断言 | 全部（真实包） | 前端图片展示 |
| 6 | 数字键自动前进+实时保存+刷新不丢 | 同步落库/审计/null 清除 | 自动前进手感/0 停留/末张提示/刷新不丢 |
| 7 | 隐私 404+双标签 | 跨用户 404/身份幂等 | 双标签 UI 对齐 |
| 8 | 同批独立+各自 CSV | 全部 | — |
| 9 | CSV 全断言 | 全部 | — |
| 10 | 日志无交错+drain | 全部 | — |
| 11 | 热键/过滤/跳转/侧栏/>9/空占位 | — | 全部 |
| 12 | 失败链路+补传+4xx 丢弃 | 停服失败/起服成功/已删任务 4xx | 三态 UI/一键重试/刷新补传/丢弃提示 |
| 13 | 重启恢复 | 全部 | — |
| 14 | 删除护栏+force+无孤儿 | 全部 | — |
| 15 | 边界全集 | 全部（413 可走查） | — |
| 16 | spool/中断/清扫/标记保留 | 全部 | — |
| 17 | 导出守卫+按钮禁用 | API 409 | 按钮禁用态 |

## 7. 风险与升级

| 风险 | 应对 |
|------|------|
| libarchive-c API 与方案描述出入 | M3.4 先探针实测；保持设计保证前提下调整实现；保证不达成→升级 |
| RAR4 中文名乱码 | 设计已预案：cp437→gb18030 回退；修复后复验 |
| 真实大包测试耗时/挂载抖动 | timeout≥900s；重试≤2；失败记录升级 |
| 根盘写满 | 大文件全挂载点；监控 df；异常即停升级 |
| 8686 被占（交付前变化） | CLS_PORT 覆盖；升级告知 |
| 前端交互缺陷（手工验收发现） | 用户反馈→父会话派修复（同模型）→复验 |
| GBK 构造法依赖 zipfile 私有方法 | 仅用于 fixture 脚本（非生产代码）；生成后双断言兜底；Python 版本锁定 3.12 |

## 8. 审核记录

| 轮次 | 日期 | 审核方 | 结论 | 处理 |
|------|------|--------|------|------|
| E1 | 2026-11-20 | qwen-token-plan/qwen4-max:xhigh | BLOCK（0 P0/4 P1/6 P2） | v1.1 全部修复：P1-1 GBK 用例改 _encodeFilenameFlags 覆写+双断言；P1-2 字节护栏改调低阈值法+护栏专用 errorMsg+声明偏小归入损坏用例；P1-3 写边界改为代码 cwd/数据挂载点；P1-4 M3 重排 fixtures→扫描→任务 API→解压→上传；P2-1 start.sh 提前+static 占位；P2-2 手工/自动分工纠偏并列全手工子项；P2-3 补批前校验/首访命名/drain 细节；P2-4 经典脚本约定+SIGTERM+flush 等待+加密 flag 断言；P2-5 自然序=插入序 ORDER BY itemId；P2-6 检查点通道 progress_update |
| E2 | 2026-11-20 | qwen-token-plan/qwen4-max:xhigh | **OK**（10 项全 RESOLVED，zipfile 源码级核实覆写构造法，无新 P0/P1） | 执行计划 v1.1 定稿，交 101/qwen3.8-pi 实施 |