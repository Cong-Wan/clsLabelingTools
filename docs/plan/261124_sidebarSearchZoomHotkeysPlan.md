# 方案：侧栏常显+搜索/复制/滚轮缩放+热键重映射+favicon

- Author: wilbur
- Version: 1.3
- Date: 2026-11-24
- Description: 七项标注页改动已实施。两轮方案评审后补全按文件名匹配、搜索请求排序、离页清理及连续缩放锚点，并通过隔离数据的 API 与 Firefox 验证，主服务已重启。

## 1. 需求与决策（可否决）

- **A1 网格固定 6 列 × 2 行**（用户明示）：弃用现有视口自适应 `_computeGridSize`（2~6 行列 clamp），固定 `_gridCols=6/_gridRows=2`、窗口 12 张；侧栏 340px 占宽后格子自然变小（1fr 自适应），无需额外缩放逻辑。
- **A2 多张模式侧栏常显**：侧栏数据 = 当前 filter/搜索的分页列表（与单张同一 `this.items`）；网格窗口仍 = 未标注队头 12 张（两套数据并存，各自加载）。**网格模式工具栏补齐过滤按钮/跳转框/序号文本**（它们描述的就是侧栏列表，此前因侧栏隐藏而省略，对应绑定改为两模式共通）。侧栏点击行为分模式：单张=跳转该图；**多张=定位该图并切回单张模式**（复查意图）。**两模式共享 filter/page/pos 列表状态（grid 模式下改过滤/翻页/搜索直接生效），原 `_singleSnapshot` 快照机制删除（共享后冗余，R1 P3-6）**。
- **A3 文件名搜索**。`/items` 的 `q` 参数匹配文件名及扩展名的子串，与标注状态筛选叠加。`%`、`_` 和反斜杠按原字符匹配。输入防抖 300 ms，Enter 立即搜索，重绘时保留正在编辑的内容和光标。
- **A4 复制文件名=basename（带后缀）**，不含子目录路径；**先判 `navigator.clipboard && navigator.clipboard.writeText` 存在才走 Promise 路径（LAN http 下该对象为 undefined，同步抛 TypeError 不能靠 .catch 兼容，R1 P2-2），否则/失败时降级临时 textarea+`document.execCommand('copy')`**；复制成功 toast「已复制 xxx.png」。
- **A5 滚轮缩放**。单张缩放范围为 0.25× 至 8×，多张每格为 0.25× 至 4×。每一步缩放都通过平移保持光标下的图像坐标，双击复位。单张同一图片重绘时保留缩放，多张刷新网格后恢复默认倍率。
- **A6 热键**：R/r=清除（单张清除标注停留/多张清空选择，即原 d 的双语义）；a/A=上一张、d/D=下一张（仅单张，等价 ←/→，多张模式无操作）；←/→ 保留。**双字母键的大小写均受理**（与现有 d/D 口径一致）。
- **A7 favicon**：index.html `<head>` 加 `<link rel="icon">`，内容=内联 SVG data URI（蓝底圆角方块+白「标」字，与顶栏 brand-logo 同视觉），非 ASCII 字符百分号编码。
- **A8 隔离验证**。用独立 SQLite 数据库、合成图片和回环地址启动测试实例，验证完成后仅重启一次主服务。重启前确认无扫描、解压、上传及活动连接。

## 2. 现状代码锚点（实施依据）

- labelView.js（v1.1）：`_computeGridSize`（loadGrid 前调用）；`_renderReady` 中 `sideHtml` 被 `if (!grid)` 包裹、grid 工具栏无 filter/jump/pos；`.side-item` 三态点 `_itemState`→dot-labeled/unsaved/unlabeled；侧栏点击直接 `pos=idx; render()`；`setMode` 含 `_singleSnapshot` 快照恢复（本案删除）；`_catBarHtml` 清除按钮角标 `d`；`onSaveState` grid 分支仅 `loadGrid`；`_bindReady` grid 早退（`if (grid) {_bindGrid; return;}`）后接单张专属绑定段；单张 `#mainImg` 无 wheel/dblclick；grid `_bindGrid` 无 wheel/dblclick；mount 清理仅 `_stopPoll`。
- app.js（v1.2）attachKeyboard：`e.key === 'd' || e.key === 'D'` → clearCurrent。
- api.js（v1.1）`listItems(taskId, offset, limit, filter)`：URL 拼接无 q。
- annotationApi.py（v1.0）`listItems`：`filter` 校验后 `where` 拼接 + total/rows 两条 SQL（参数 `(taskId,)` 与 `(taskId, limit, offset)` 附近，实施时以实际为准）。
- helpView.js（v1.3）②快捷键表含 d 行、③节「d / Esc=清空选择」、⑥节「清除按钮 = d 键」。
- style.css（v1.3）：`.side-pager/.side-item/.dot-*`（三态点）、`.img-stage`、`.grid-cell`（cursor:pointer、overflow:hidden）。
- index.html（v1.3）：`<head>` 无 favicon。

## 3. 详细设计

### 3.1 T1 annotationApi.py（1.0→1.1）
`listItems` 加参数 `q: str = ''`：
- 校验：`len(q) > 200` → 400 `'搜索词过长（≤200 字符）'`。
- `q` 非空时用 SQLite 函数 `fileName` 从 `relPath` 取文件名，再用参数化 `LIKE … ESCAPE` 匹配字面子串。总数和分页行在同一读事务查询，旧调用省略 `q` 即可。
- 文件头版本/描述更新。SQLite LIKE 对 ASCII 不区分大小写、中文按码位精确匹配（符合文件名搜索场景，写入帮助文档口径）。

### 3.2 T2 api.js（1.1→1.2）
`listItems: function (taskId, offset, limit, filter, q)`：`q` 默认 `''`，非空时 URL 追加 `&q=' + encodeURIComponent(q)`。其余不动。

### 3.3 T3 labelView.js（1.1→1.3）

1. 两种模式共用 `filter`、`page`、`pos` 和右侧分页列表。网格独立加载排在前面的 12 张未标注图片。过滤、跳转和翻页处理在两种模式中都绑定。
2. 侧栏上方显示搜索框。编辑内容和已发送的搜索词分别保存，只有最近的请求可以写回结果。列表收缩时在加载流程中回退到最后一个有效页。重绘前若搜索框有焦点，重绘后恢复焦点与选区，中文输入组合期间延后重绘。离开任务时清理搜索与单击计时器、停止轮询，废弃已发出的请求结果。
3. 已保存的标注显示标签名，保存中的标注显示待传标签，待传的清除显示「清除中」，未标注保留灰点。保存完成后用服务器数据刷新侧栏与计数。
4. 单击侧栏条目定位图片，多张模式下同时切回单张。单击延迟 500 ms 以容纳双击，双击取消定位并复制带扩展名的文件名。局域网 HTTP 下使用临时文本框触发复制，成功或失败都有反馈。
5. 单张和网格共用滚轮缩放计算。变换原点设在图片左上角，步进倍率为 1.15。根据光标与当前图像矩形的位移更新平移量，同时更新缩放倍率。滚轮作用于单张图片区或鼠标所在的网格格子，双击复位。

### 3.4 T4 app.js（1.2→1.3）
attachKeyboard：`'r'/'R'` → `clsLabelView.clearCurrent()`；`'a'/'A'` → `navigate(-1)`；`'d'/'D'` → `navigate(1)`；删除原 d→clearCurrent 分支。0-9/Esc/←/→ 不变。文件头更新。

### 3.5 T5 helpView.js（1.3→1.4）
- ② 表：d 行改 R 行（单张清除标注（停留）/多张清空选择）；新增 a / d 行（上一张/下一张，仅单张）；←/→ 行改「同 a / d（仅单张）」。
- ③ 多张节：「d / Esc=清空选择」→「R / Esc=清空选择」；**替换「网格大小随窗口自适应」为「网格固定 6×2=12 张」（R1 P2-5）**；补「多张模式右侧同样显示文件列表（可搜索、双击复制文件名、点击某条会定位并切回单张）；滚轮悬停格子可缩放该图（双击复位）」。
- ⑥ 标注页节：「清除」按钮 = R 键；**替换现有三色圆点 bullet（含「按数字键后该图立刻变黄」句，R1 P2-6）**为：「右侧列表：已标注显示标签名胶囊（绿=已保存/黄=保存中，悬停看全名）、未标注灰点、清除中显示「清除中」；上方搜索框按文件名过滤；双击条目复制文件名；单张大图滚轮缩放（双击复位）」。
- 文件头 1.3→1.4。

### 3.6 T6 style.css（1.3→1.4）
- `.side-search`：`padding: 8px 10px; border-bottom: 1px solid var(--c-border);`；输入选择器追加 `.side-search input[type="text"]` 到**基础组与 `:focus-visible` 焦点环组两处**（R1 P3-8 + R2-P3-3，含 `width: 100%`）。
- `.side-lbl`：`display:inline-block; max-width:96px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; border-radius:var(--r-full); padding:1px 8px;` `.st-labeled`：绿 tint（`var(--c-success-bg)` 底/`var(--c-success)` 字/1px 边 `#a7f3d0`）；`.st-unsaved`：黄 tint（`#fef3c7` 底/`var(--c-warn)` 字/1px 边 `#fde68a`）。
- `.img-stage { cursor: zoom-in; }`；`.grid-cell img` 保持；`.dot-labeled/.dot-unsaved` 规则保留（CSS 不删，仅 labelView 不再输出前两者——历史兼容无害）。
- 文件头 1.3→1.4。

### 3.7 T7 index.html（1.3→1.4）
`<head>` 加：`<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%232563eb'/%3E%3Ctext x='32' y='45' font-size='34' text-anchor='middle' fill='%23fff' font-family='sans-serif' font-weight='700'%3E%E6%A0%87%3C/text%3E%3C/svg%3E">`（「标」=UTF-8 百分号编码）。文件头 1.3→1.4。

### 3.8 T8 README.md
- 使用流程 3：热键段改「`R` 清除（多张=清空选择）、`a`/`d` 上一张/下一张」；补「侧栏：标签名/灰点、搜索、双击复制文件名；滚轮缩放（单张大图/多张格子内）」。
- 已知限制段（现「网格大小随窗口自适应，拉伸窗口后重进多张模式才会重算」）：**替换为固定 6×2 表述并删去重进重算半句（R1 P2-7）**。
- 顺手修正既有口径错误（R1 P3-3）：使用流程 3 中「前 9 个显示 1-9 角标」→「前 10 个对应 0-9（第 1 个=0）」（与本轮同文件改动的文档正确性一并修正，非方案外扩展）。

## 4. 风险与对策
- **R-a 点击与双击**。单击延迟 500 ms，双击取消定位并复制文件名。
- **R-b 搜索焦点**。重绘前搜索框有焦点时才恢复焦点和选区，编辑中的搜索词由独立字段保存。
- **R-c 滚轮 preventDefault**：仅悬停大图/格子时（网格固定 12 格无滚动需求；单张 label-main 滚动在图区外仍可用）。
- **R-d 缩放跨重渲**：itemId 匹配复用，不匹配复位——排空刷新/计数对齐重渲不丢当前图缩放。
- **R-e LIKE 注入/通配**：`\ % _` 全转义 + ESCAPE 子句；q 长度 ≤200 校验。
- **R-f 工具栏拥挤**：label-toolbar 已有 flex-wrap，6 列网格+侧栏下宽度仍足。
- **R-g grid 侧栏两套数据**：侧栏 filter 列表与网格未标注窗口独立（A2），语义在帮助文档写清，避免用户误解「侧栏第一项=网格第一格」。**已知行为（R1 P3-7）：gridLabel 批量标注后侧栏胶囊/计数在排空对齐（saving→false）前有数秒陈旧；grid 格子缩放不跨重渲保留**。
- **R-h 悬停格子滚轮即缩放**，无法滚屏——网格 12 格固定适配视口，无滚屏需求；写入已知行为。
- **R-i 上轮禁改清单**（api.js/labelView.js/app.js）属上案 §6 范围，本案权限以本案 TODO 为准。

## 5. TODO lists
- [x] T1 `annotationApi.py` 支持文件名搜索和分页同一读快照，验证中文、ASCII 大小写、`%`、`_`、反斜杠及标注状态过滤。
- [x] T2 `api.js` 透传 `q`。
- [x] T3 `labelView.js` 实现两模式侧栏、标签名、搜索、复制、滚轮缩放和固定 6×2 网格。
- [x] T4 `app.js` 更新 `R/A/D`，保留方向键与浏览器组合快捷键。
- [x] T5 `helpView.js` 更新使用说明。
- [x] T6 `style.css` 设置侧栏、网格与缩放样式。
- [x] T7 `index.html` 使用「标」字 favicon。
- [x] T8 `README.md` 同步用法。
- [x] T9 通过 JavaScript 语法和 Python 导入检查、隔离 HTTP 接口验证。主服务在 8686 重启，健康检查、`q` 接口参数和 favicon 已生效。
- [x] T10 用 Firefox 检查两模式布局、标签名、搜索与请求乱序、分页、双击复制的 HTTP 降级、连续缩放锚点、快捷键和离页清理。

## 6. 实施纪律
- 沿用项目约束：IIFE+'use strict'+var+字符串拼接、小驼峰、文件头版本递增、零 CDN/零依赖/无测试框架、每处改动可追溯到本方案条目。
- 禁止：动 batch 队列/补传逻辑（api.js 仅 listItems 一处）、动 CSV/导出、动 grid 五类选择语义、方案外顺手美化。
