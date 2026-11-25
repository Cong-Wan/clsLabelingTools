# clsLabelTool 多张网格标注 + 类别计数 + 热键重映射落地方案

- Author: wilbur（flamingo 助理起草）
- Version: 1.3
- Date: 2026-11-24
- Description: 用户两项新需求+三处细节。v1.0 初稿；v1.1 修复 R1 评审；v1.2 采纳 R2 复审（R2 结论：可进入实施）。v1.3 实施完成：T1-T8 全部完成，T9 自动验证全部通过（node --check ×6、8687 测试实例冒烟：labelCounts=[2,1,0]、CSV labelIndex=0/0/1、静态 200+no-cache，测完已停）；手工验收待用户（主服务重启后）；冒烟残留清理项待用户批准（见文末）。

---

## 1. 需求 → 设计映射

| # | 用户原话 | 设计落点 |
|---|---|---|
| N1 | 标注界面加开关，单张 ↔ 多张标注 | 标注页工具栏模式切换按钮组（单张/多张），localStorage（clsLabelMode）记忆 |
| N2 | 多张=一屏 n×n 图片展示 | 网格铺满主区；列=floor(宽/240) 行=floor(高/240)，各自 clamp 2~6，格子数=列×行（1080p 典型 4×3=12 张）；切换时计算一次 |
| N3 | 鼠标拖动多选 | 橡皮筋框选：框内格即选中；Ctrl+拖=并入当前选择 |
| N4 | Win 资源管理器快捷键 | 点击=单选重置；Ctrl+点击=该格翻转；Shift+点击=锚点到该格连选（一维序号区间，含端点）；锚点规则见 3.1（仅无修饰点击与 Shift+点击更新锚点） |
| N5 | 标完的图自动填入新图 | 多张模式数据源=「未标注」队列（固定取队头前 N 张）；批次标注完成后重拉同一窗口→已标项自动被后续未标注项顶替；队列空→「已全部标注」 |
| N6 | 每个类别显示标了多少张 | 任务详情新增 labelCounts（按 labels 顺序的数组）；类别按钮右侧计数徽标；乐观自增+getTask 对齐 |
| D1 | 类别数字从 0 开始 | 前 10 个类别对应键 0-9（第 1 类=0 …第 10 类=9），>10 仅点击；影响键盘分发/角标/编辑器预览/帮助文档 |
| D2 | 清除键设为 d | 单张模式 d=清除当前标注（原 0 键职能）；多张模式 d=清空选择（网格仅展示未标注项，清除标注无意义）；Esc=清空选择（多张） |
| D3 | CSV 加数字类别 | 新增 labelIndex 列（label 在 labels 数组下标，0-based 与热键编号一致；未标注空串），紧跟 label 列后 |

## 2. 关键设计决定与假设（重要，请用户过目，可否决）

- **A1 多张模式数据源锁定「未标注」**：过滤按钮与侧栏在多张模式下隐藏（网格铺满），跳转框隐藏；复查/改标请切回单张模式（filter/分页/侧栏完整保留）。单格不动可切回单张精修。
- **A2 批量标注不新增后端端点**：前端循环调用既有单条 annotate 接口（复用失败重试 1 次、localStorage 补传全套机制）；api.js 按 itemId 分链：同一 itemId 串行去重、**不同 itemId 并行**——批量= N 路并发（网格 clamp 后 N≤36），LAN 可接受；审计日志按条记录不变。
- **A3 网格尺寸视口自适应**，窗口 resize 不自动重排（重进模式即重算）；不做图片缩略图后端（无 PIL 依赖，大图网格首屏可能偏慢，见风险表，留作后续可选项）。
- **A4 计数口径**：以服务器为准（labelCounts）；前端乐观自增仅作即时反馈，保存队列排空（saving→false）后对齐（多张=重拉+对齐；单张=仅 getTask 刷新计数，不重拉列表）。后端未重启（旧接口无 labelCounts）时前端容错为不显示计数，重启后恢复。
- **A5 热键重映射为全局行为**：单张与多张模式一致（0-9 标注）；←/→ 仅单张导航（多张以鼠标为主，箭头不响应）；输入框聚焦守卫与帮助弹窗守卫（弹窗打开屏蔽全部热键）不变。
- **A6 Esc 双监听次序**：帮助弹窗的 Esc 处理器加 e.preventDefault()，app.js 的 Esc 分支先判 e.defaultPrevented，避免「关帮助的同时误清网格选择」。
- **A7 模式记忆为全局**（非按任务）：localStorage 键 clsLabelMode，默认单张。
- **A8 labelIndex 为 0-based**，与热键编号一致（用户把类别编号起点改为 0，CSV 数字列即该编号）。

## 3. 详细设计

### 3.1 多张模式交互规格

**模式切换**：工具栏 filter-btns 样式按钮组「单张｜多张」。切到多张：计算网格尺寸→加载队头 N 张未标注（快照 {filter, page, pos} 留存）；切回单张：恢复快照三元组（含当前张序号 pos）并重新 loadItems 定位。

**选择语义（Explorer 式）**：

| 操作 | 语义 |
|---|---|
| 点击（无修饰） | 只选该格（重置其他） |
| Ctrl+点击 | 该格选中态翻转 |
| Shift+点击 | 锚点→该格**一维序号区间**（窗口内 min~max 含端点；网格本质是未标注队列，采用队列序号连选而非二维矩形），替换选择 |
| 拖动 | 框内格替换当前选择（拖动中实时高亮预览） |
| Ctrl+拖动 | 框选结果并入当前选择 |
| Shift+拖动 | 忽略 Shift（等同普通拖动） |
| d / Esc | 清空选择 |

锚点规则：**仅无修饰点击与 Shift+点击更新锚点**（Ctrl+点击/拖动不改锚点，与资源管理器一致）。

**批量标注**：选中≥1 张 → 按 0-9 或点类别按钮 → 每张 clsApi.annotate（乐观+队列）→ 类别计数乐观自增 → hint「已标注 N 张 → <类别>」→ 清空选择 → 重拉网格窗口（**不立即 getTask，对齐仅靠 saving→false 路径**，R2 N2：避免双请求竞态；该处请求发出时队列已排空，必为新鲜读）。**若选择为空按键则无操作**（提示「请先选择图片」）。

**自动填新图与落库竞态（R1 P1-1 修复）**：clsApi.annotate 不返回 Promise（串行链内部消化），批量后立即重拉 listItems(unlabeled) 时刚标注项可能尚未落库而重复出现。对策：
1. 重拉窗口后，**渲染时实时读取 clsApi.pendingItems()（本地待传表，沿用现有 _itemState 渲染时读取模式，R2 N7）**，凡 taskId/itemId 命中的项一律不渲染网格格（保存中/失败待重试的项不展示、不可选，避免重复标注；保存失败项由顶栏「N 条待重试+一键重试」兑底）；
2. app.js 现有 onSaveStateChange 回调末尾转发快照给 clsLabelView.onSaveState(snap)（api 支持多订阅者，取转发写法不动 api.js）。onSaveState 内部**加视图守卫（R2 N1）：`clsApp.currentView==='label' && clsApp.currentTaskId===当前 task.taskId`**，否则忽略——防止用户已返回任务列表时重拉顶掉列表页；守卫通过时：多张模式→重拉窗口+getTask 对齐；单张模式→仅 getTask 刷新计数（不重拉列表，R2 N6）；
3. 计数对齐采纳判定（R2 N2）：**请求发出时快照非 saving**才采纳 getTask 的 labelCounts（响应到达时不重复判定，避免在飞旧响应覆盖新值）；单张模式现有「标注后立即 getTask」仅在发出时非 saving 才采纳 counts，其余字段照旧。
4. api.js 零改动。

**网格单元**：黑底 contain 缩略图 + 选中态高亮边框 + hover title=relPath；窗口不足 N 张时空格留白；队列为空显示「已全部标注 + 查看全部入口（切回单张）」；被 pending 剔除的项不占格。工具栏右侧信息：单张=pos-text（x/total）；多张=「未标注 N · 已选 M」；底部进度条（已标注/总数）两种模式均保留。

**实现要点**：mousedown 于 .grid-stage 记录起点/起始格/修饰键并 preventDefault（防图片原生拖拽与文本选择，img draggable=false + user-select:none）；mousemove 画 .rubber-band 绝对定位框并逐格 getBoundingClientRect 相交检测；mouseup 位移<5px 判定为点击语义，否则落实框选。

### 3.2 热键重映射（0-9 / d / Esc / ←→）

| 键 | 单张模式 | 多张模式 |
|---|---|---|
| 0-9 | 标注当前张（第 idx+1 类）+自动前进 | 批量标注全部选中张 |
| d | 清除当前张标注（停留） | 清空选择 |
| Esc | 无操作 | 清空选择（帮助弹窗开着时优先关弹窗） |
| ←/→ | 上一张/下一张 | 不响应 |

派发仍集中在 app.js（输入框聚焦守卫、帮助弹 isOpen 守卫不变）；labelView.hotkey/clearCurrent/onEscape 内部按模式路由，app.js 不感知模式细节。

### 3.3 类别计数

- 后端 getTask 新增：`labelCounts: number[]`（`SELECT label, COUNT(*) c FROM annotations WHERE taskId=? GROUP BY label` → 按 labels 顺序映射；无标注全 0）。
- 前端：类别按钮（单张 cat-bar 与多张类别栏共用渲染）右侧计数徽标；labelCurrent/labelBatch 乐观自增，clearCurrent 自减；清除按钮角标改为 d（R1 P3-6）。
- 对齐时机（R1 P2-2 修复）：仅当保存队列非 saving（onSaveState 转发的快照）时才采纳 getTask 的 labelCounts 覆盖本地值，避免陈旧读回退；保存失败重试期间乐观值保留，重试成功后由 saving→false 的对齐刷新归正（残余偏差在下次操作/刷新时归正，帮助文档说明）。
- 兼容：`t.labelCounts || []`——后端未重启时不显示计数（不报错）。

### 3.4 CSV labelIndex

- CSV_COLUMNS：`relPath, absPath, label, labelIndex, annotatorId, annotatorName, updatedAt`。
- labelIndex=labels.index(label)（0-based）；未标注空串。导出时实时计算，历史任务零迁移。

### 3.5 文件改动清单

| 文件 | 改动 | 版本 |
|---|---|---|
| static/js/labelView.js | 多张模式全套（状态/加载/渲染/选择/批量标注）+ 计数 + 0-9 对接 + pending 剔除 + onSaveState 对齐 + 清除角标 d | 1.0→1.1 |
| static/js/app.js | 键盘分发 0-9/d/Esc（defaultPrevented 守卫）+ onSaveStateChange 快照转发 clsLabelView.onSaveState | 1.1→1.2 |
| static/js/taskView.js | 编辑器角标/预览/表单提示改 0-9（前 10 类） | 1.1→1.2 |
| static/js/helpView.js | 快捷键表/多张模式节/计数/CSV 列说明 | 1.1→1.2 |
| static/css/style.css | 网格/模式开关/计数徽标/橡皮筋/已选态样式 | 1.1→1.2 |
| taskApi.py | getTask +labelCounts | 1.0→1.1 |
| exportService.py | +labelIndex 列（buildCsv 的 task SELECT 需补查 labelsJson，R1 P3-5） | 1.0→1.1 |
| README.md | 使用流程/快捷键/CSV 列/已知限制（无缩略图） | - |

**不动**：index.html、api.js、main.py、database.py、annotationApi.py（批量=前端循环复用单条接口）；无新文件、无新依赖、无 DB schema 变更。

### 3.6 帮助内容更新口径（helpView.js）

- 快捷键表：0-9=标注（按添加顺序，第 1 类=0）；d=清除（单张）/清空选择（多张）；←/→=单张导航；Esc=多张清空选择。
- 新增「多张批量标注」小节：开关位置、网格含义、点击/Ctrl/Shift（一维序号连选）/拖动选择表、标完自动填新图、数据源=未标注队列（复查请切单张）、保存中项不展示与顶栏重试兑底。
- ⑤ 节「清除按钮 = 数字键 0 的鼠标等价操作」改为「清除按钮 = d 键的鼠标等价操作」（R1 P3-6）。
- 类别计数说明：按钮右侧数字=该类已标张数（保存中为乐观值，失败重试后自动归正）。
- ③ 标签映射：「前 9 个对应 1-9」→「前 10 个对应 0-9（第 1 个=0）」。
- ⑥ CSV：列清单加 labelIndex（数字类别，与热键编号一致）。

## 4. 明确不做

- 不新增批量标注后端端点；不做图片缩略图/后端图片处理（无 PIL，网格加载原图+loading=lazy，大图首屏慢列为已知限制）；
- 多张模式不做已标注项展示/复查/改标（锁定未标注队列，复查切单张）；
- 不做触屏手势；不做窗口 resize 自动重排；箭头键多张模式不导航；
- 不迁移历史数据（labelIndex 导出时计算）；列表接口（任务卡片）不加 labelCounts。

## 5. TODO lists（实施与验证）

- [x] **T1 taskApi.py**（1.0→1.1）：getTask 增加 labelCounts（GROUP BY 映射到 labels 序）；
  验证：✅ 8687 测试实例标注 2A+1B 后 labelCounts=[2,1,0]，labeledCount=3。
- [x] **T2 exportService.py**（1.0→1.1）：CSV_COLUMNS 加 labelIndex，行值=下标或空串；buildCsv 补查 labelsJson；
  验证：✅ 导出表头含 labelIndex；A→0、B→1（与热键编号一致）。
- [x] **T3 labelView.js**（1.0→1.1，最大头）：模式状态+切换持久化（快照 {filter,page,pos}）+网格加载（队头 N 张未标注+pending 渲染时剔除）+渲染（工具栏变体含「未标注 N·已选 M」/类别栏含计数/网格/空态）+选择全套（点击/Ctrl/Shift 一维区间/拖动/d/Esc+锚点规则）+批量标注+乐观计数+onSaveState 对齐刷新+热键路由+清除角标 d；
  验证：✅ `node --check`；服务内容 grep 19 处新能力在位；手工清单待用户。
- [x] **T4 app.js**（1.1→1.2）：0-9/d/D/Escape 派发（defaultPrevented 守卫）+ onSaveStateChange 转发；
  验证：✅ `node --check` + curl 确认四处在位（35/106/108/112 行）。
- [x] **T5 taskView.js**（1.1→1.2）：角标 i<10 显示 i、预览 0→标签、表单提示「前 10 个对应 0-9（第 1 个=0）」；
  验证：✅ `node --check` + 人工核对。
- [x] **T6 helpView.js**（1.1→1.2）：八节内容（新增③多张批量标注，③→④顺延至⑦→⑧）+热键表 0-9/d/Esc+计数+labelIndex+ESC preventDefault；
  验证：✅ `node --check` + 逐条对照 3.6 口径。
  验证：`node --check` + 逐条对照 3.6。
- [x] **T7 style.css**（1.1→1.2）：mode-btns/grid-stage/grid-cell(.sel/.pre)/cnt-badge/rubber-band 样式；
  验证：人工核对无类名冲突（grid-*/cnt-*/mode-* 前缀全新）。
- [x] **T8 README.md**：使用流程（0-9/d/多张模式/计数）+CSV 列+已知限制（网格加载原图）；
  验证：diff 审读。
- [x（自动）/⬜（手工）] **T9 综合验证**：✅ 全部 JS `node --check`（×6）；✅ `CLS_PORT=8687` 独立测试实例：静态 200+no-cache、labelCounts=[2,1,0]、CSV labelIndex=0/0/1，测完已停（主服务 8686 未受影响）；⬜ 手工验收清单（用户浏览器+主服务重启后）：
  开关切换与记忆 / 网格数量合理 / 五种选择语义 / d 与 Esc 清选择 / 0-9 批量标注+自动填新图（含保存中项不重复出现）/ 单张 0-9-d-箭头-自动前进 / 两种模式类别计数变化 / CSV 含 labelIndex / 帮助内容正确 / 弹窗开着按 0-9-d-Esc 无副作用。

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| 框选与浏览器原生拖图/文本选择冲突 | mousedown preventDefault + img draggable=false + user-select:none |
| 批量 N 张并发 N 请求 | api.js 按 itemId 分链：同项串行去重、异项并行，批量= N 路并发（≤36）；LAN 可接受；失败重试/补传机制复用 |
| 批量落库与重拉窗口竞态（R1 P1-1） | pendingItems 本地剔除 + saving→false 自动重拉；失败项由顶栏重试兑底（见 3.1） |
| 乐观计数陈旧读回退（R1 P2-2） | 仅非 saving 时采纳 getTask 对齐值；失败重试期间保留乐观值，归正时机见 3.3 |
| 乐观计数与 DB 口径漂移（重试中） | 计数以 getTask 对齐为准；帮助文档说明 |
| 用户未重启主服务（前后端错配） | 前端 labelCounts 缺省容错不显示计数；CSV labelIndex 需重启才生效——交付说明写明「重启 bash start.sh」 |
| 0-9 重映射破坏旧肌肉记忆 | 表单提示/帮助/README 全量同步，无遗漏口径 |
| Esc 双监听误清选择 | helpView preventDefault + app.js defaultPrevented 守卫（A6） |
| 大图网格首屏慢（无缩略图） | loading=lazy + contain；已知限制记录，缩略图留作后续决策 |
| 多张批量中切换模式/翻页 | 批量标注为同步循环触发+异步落库，切换仅重渲染不中断队列（api 层与视图解耦） |

## 7. 验收标准

1. 多张模式：开关可切换且记忆；网格铺满主区；点击/Ctrl/Shift（一维序号连选）/拖动/Ctrl+拖动五类选择语义正确；0-9 或点击类别批量标注后选中项不再可选/可见（保存中项被剔除），保存队列排空后新未标注图自动补位；d/Esc 清空选择；队列空显示「已全部标注」。
2. 单张模式：0-9 标注+自动前进、d 清除、←/→ 导航全部正常（0 键不再清除而是标注第 1 类）。
3. 类别按钮显示计数（两种模式），标注后即时+1、对齐后准确。
4. 导出 CSV 含 labelIndex 列且与热键编号一致。
5. 帮助弹窗/表单提示/README 与新热键体系一致；弹窗打开时 0-9/d/←/→/Esc 无副作用。
6. 全部 JS `node --check` 通过；8687 测试实例冒烟通过；用户主服务重启后功能完整。
