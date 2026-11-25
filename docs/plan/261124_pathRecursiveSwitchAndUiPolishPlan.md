# 方案：路径递归开关 + 首页/按钮体系视觉重做

- Author: wilbur
- Version: 1.3
- Date: 2026-11-24
- Description: 用户两项需求：① 路径导入加「包含子文件夹」开关（当前强制递归）；② 任务列表页（首页）与全站按钮体系视觉重做（用户评价「太丑」「按键没用心做」）。含后端小改（DB 加列 + API 透传 + 扫描分支）。零框架零 CDN 零构建约束不变。v1.1 吸收 R1 评审（4 P1 + 5 P2 + 5 P3）。v1.2 吸收 R2 复审：R2-1 输入框选择器补 .src-opt 覆盖 tfPath 新位置；R2-2 .on 同步改两卡写法+初始 on 类；R2-3 补 .btn/.btn-mini 书写顺序约束；R2-4 T3 补空态标记改写；R2-5 A4 补 taskView JS 改动边界。R2 结论：轻量修订，修完核对后直接派发实施（无需第三轮全面复审）。v1.3 实施完成：T1-T7 由实施子代理完成（无功能性偏差），T8 自动验证全过（node --check ×6、import、真实库迁移列校验、三组递归冒烟 4/2/4 项、响应 recursive 字段、静态 200、8687→8686 停机序列执行完毕）；冒烟残留 3 任务+临时文件待用户批准清理；T9 手工验收待用户浏览器确认。

## 1. 需求与现状问题

### 1.1 R1 路径递归开关
现状：`scanService.scanTask` 用 `os.walk` 强制递归全部子目录。用户要求可控。
范围决策：**仅路径导入加开关**；压缩包上传不加（包内目录结构由解压结果决定，不存在"要不要递归"的选择，解压后统一全量登记）。

### 1.2 R2 视觉重做（现状问题清单）
1. 顶栏：深灰条+纯文本 brand，无层次；helpBtn 灰色 mini 块贴边。
2. 创建表单：扁平无分区；原生 radio 裸露；字段标签与输入挤压；创建按钮无层级。
3. 任务卡：信息密度乱（路径长串、meta 挤一行）；三个操作按钮灰/蓝/红混排无主次；状态纯文字+闪烁省略号。
4. 按钮体系（用户点名）：`.btn` 蓝底无 focus 环/无按压反馈；`.btn-mini` 深灰底与 `.btn` 蓝底语义冲突；`.fbtn` 切换态只有背景色变化；`key-badge` 深灰小方块不像键帽；`cnt-badge` 与 key-badge 并排拥挤；`.btn-clear` 淡红无 hover；输入框无统一 focus 样式。
5. 空状态：纯灰字一行。

## 2. 假设与决策（可否决）

- **A1** 递归开关默认**勾选**（= 现状递归行为，向后兼容；老调用方/老脚本不传字段也不变行为）。
- **A2** `recursiveScan` 存 DB（tasks 加列，INTEGER，1=递归）；已存在任务 ALTER 默认 1。**不引入独立配置表/JSON**（一行列最简）。
- **A3** 顶栏改**浅色白底**（下边框+微阴影），高度保持 48px 不变（标注页 `calc(100vh - 48px)` 依赖）。brand 加纯 CSS logo 方块。
- **A4** 视觉重做主要改 CSS + taskView/index.html 的 DOM 结构；**taskView.js 允许本方案 3.4/3.5.4/T3 明示的 JS 改动（含 .on 同步语句、recursive 字段、任务卡重排输出）**；labelView/app/helpView 的既有类名与 DOM **不动**（btn-cat/fbtn/mode-btns/filter-btns/btn-mini/key-badge/cnt-badge 等类名全部沿用，靠样式重做换肤）。helpView 仅改文字（递归说明）。
- **A5** 全站引入 CSS 变量（design tokens）定义在 `:root`，旧散落色值统一替换引用；不做暗色模式、不加动效库、不引入图标库（纯 CSS/内联形状）。
- **A6** 验证与重启序列（吸收 R1 P1-4）：**先停主服务 → 8687 起验证实例（真实库迁移冒烟 + 递归开关冒烟）→ 清理冒烟残留 → 停验证实例 → 重启主服务（新代码）**。原因：双实例共享 DB/DATA_ROOT，第二实例启动会执行 recoverInterruptedTasks（把主服务在途 scanning/extracting 置 error）、sweepOrphanUploads（误删在途上传目录）、audit 双写（main.py:79-82）。停机窗口约几分钟，沿用重启授权。
- **A7** 不动：api.js、labelView.js 逻辑、网格模式交互、帮助弹窗结构、多语言、响应式断点（现有 auto-fill 已自适应）。
- **A8** 上传进度条/表单校验逻辑/轮询/删除确认等**功能行为全部保持不变**，只换皮。

## 3. 详细设计

### 3.1 Design tokens（style.css `:root`，全部新写）
```css
:root {
  /* 色板（slate 冷灰 + 蓝主色，与现有品牌蓝 #2563eb 连续） */
  --c-primary: #2563eb;  --c-primary-600: #1d4ed8;
  --c-primary-50: #eff6ff; --c-primary-100: #dbeafe; --c-primary-200: #bfdbfe;
  --c-bg: #f1f5f9; --c-surface: #ffffff;
  --c-border: #e2e8f0; --c-border-strong: #cbd5e1;
  --c-text: #0f172a; --c-text-2: #475569; --c-text-3: #94a3b8;
  --c-success: #059669; --c-success-bg: #ecfdf5;
  --c-danger: #dc2626;  --c-danger-600: #b91c1c; --c-danger-bg: #fef2f2;
  --c-warn: #d97706;
  /* 形状/阴影/尺寸 */
  --r-sm: 6px; --r-md: 10px; --r-lg: 14px; --r-full: 999px; --r-btn: 8px;
  --c-seg-bg: #e8edf3;
  --shadow-sm: 0 1px 2px rgba(15,23,42,.06);
  --shadow-md: 0 4px 14px rgba(15,23,42,.10);
  --h-btn: 38px; --h-btn-sm: 30px; --h-input: 38px;
  --ring: 0 0 0 3px rgba(37,99,235,.25);
  --mono: ui-monospace, "Cascadia Mono", Consolas, "Courier New", monospace;
}
```

### 3.2 按钮体系重做（类名不变，全部重写样式）
| 类 | 规格 |
|---|---|
| `.btn` | 主按钮：蓝底白字，高 var(--h-btn)、圆角 var(--r-btn)、字重 500、padding 0 18px；hover: --c-primary-600；active: translateY(1px)；focus-visible: var(--ring)；disabled: opacity .45 + not-allowed |
| `.btn-mini` | 次按钮（重做，弃深灰）：白底+1px --c-border-strong、文字 --c-text-2、高 --h-btn-sm、圆角 6px；hover: 边框 --c-primary、文字 --c-primary、背景 --c-primary-50；active/focus-visible/disabled 同主按钮规格 |
| `.btn-ghost` | 三级按钮：--c-primary-50 底、--c-primary 文字、无边框；hover: --c-primary-100 |
| `.btn-danger` | 危险按钮：白底红字红边（描边式，弱化常驻红色块）；hover: 红底白字；disabled 同上 |
| `.fbtn`（含 `.mode-btns` 内） | 分段控件：**容器** `.filter-btns/.mode-btns` 统一背景 var(--c-seg-bg)、padding 3px、圆角 --r-full；`.fbtn` 自身无边框透明底、高 26px、圆角 --r-full、padding 0 12px、色 --c-text-2；`.on`：白底+--shadow-sm+色 --c-primary+字重 500（iOS segmented 风格） |
| `.key-badge` | **键帽化**：白底、1px --c-border-strong 边、border-bottom 3px（3D 键帽）、font-family var(--mono)、字号 12px、圆角 5px、min-width 22px、padding 1px 6px、色 --c-text-2；`.key-more` 灰字无边框（文字「仅点击」）；深底上下文（`.btn-cat.sel`、`.fbtn.on` 不需要）反转为 rgba(255,255,255,.2) 底白字 |
| `.cnt-badge` | 计数胶囊：透明底、色 --c-text-3、font-family var(--mono)、字号 11px、padding 0；`.btn-cat.sel` 内反白 |
| `.btn-cat` | 44px 高、圆角 10px、白底 1px 边、间距 10px 16px；hover: 边框 --c-primary + 背景 --c-primary-50（过渡 .15s）；`.sel`：蓝底白字（key/cnt 反白） |
| `.btn-clear` | 白底红字红边（同 danger 描边式）；hover 红底白字 |
| 输入框（**仅限定文本类**，R2-1 覆盖重构后新位置：`.fld input[type="text"]`（基本信息段，新 DOM 字段容器保留 .fld 类）、`.src-opt input[type="text"]`（#tfPath 在来源卡片内，无 .fld 祖先）、`.label-add input`、`.guide-box input`、`#jumpInput`；**不得**命中 radio/checkbox/file——R1 P1-2） | 高 --h-input、1px --c-border-strong、圆角 var(--r-btn)、padding 0 12px；`:focus-visible`: 边框 --c-primary + box-shadow var(--ring)（替换浏览器默认 outline，仅 :focus-visible 时） |

**CSS 书写顺序约束（R2-3）**：`.btn-mini` 规则置于 `.btn` 之后（labelView 工具栏的 `btn btn-mini` 组合——返回/导出/定位/上下页——统一呈现 30px 次按钮形态）；`.btn-ghost/.btn-danger/.btn-clear` 置于 `.btn/.btn-cat` 之后（app.js 引导按钮与 labelView 清除按钮依赖）。

### 3.3 顶栏（index.html 结构 + CSS）
- 结构：`<div class="brand"><span class="brand-logo">标</span><span class="brand-name">clsLabelTool</span><span class="brand-sub">图片分类标注</span></div>`；**保留 `topbar-sep`（flex:1 右推占位，R1 P2-3）**；helpBtn 类改 `btn-mini`（样式已重做）不变 id。
- 样式：白底、border-bottom 1px --c-border、--shadow-sm；brand-logo：24px 蓝底(--c-primary)白字圆角 6px 方块（font-weight 700）；brand-name 700 字重 15px；brand-sub 12px --c-text-3 左边距 8px（窄屏 <900px 隐藏 brand-sub，media query 一条）。
- 顶栏内 `#annotatorSlot .annotator`：胶囊式 --c-primary-50 底 --c-primary 字圆角 --r-full；hover 背景 --c-primary-100（R1 P3-4）。
- **保存指示器配色随浅底重映射（R1 P1-1）**：`.save-saving`→var(--c-warn)、`.save-ok`→var(--c-success)、`.save-failed`→var(--c-danger)。
- **高度严格保持 48px**。

### 3.4 任务页（taskView.js DOM 结构重排 + CSS）
- 页面骨架不变（create-card + list-title + task-grid）；页面背景 --c-bg。
- **创建卡片**：`h2` 加左侧 4px 蓝色竖条（复用 help-body h4 风格）；分三个 `.form-section`（基本信息 / 数据来源 / 标签映射），各含 `.form-section-title`（13px 600 --c-text-2 + 前置小圆点 6px --c-primary-200）；字段间距 16px。
- **来源选择改卡片式（结构重构，消除 label 嵌套，R1 P2-1）**：新增外层容器 `.src-grid`（grid 2 列）；每张卡片改为 `<div class="src-opt">` 包两个并列子元素：① `<label class="src-row">`（内含 radio + 标题文字，不再包裹其他交互元素）；② 路径卡片内 `<label class="rec-opt">` 递归开关（与 ① 同级，非嵌套）。**radio 自定义外观但不隐藏可聚焦性**（R1 P3-3）：appearance:none、16px 圆圈、checked 时内点 8px --c-primary（::after）、:focus-visible 时外环 var(--ring)。卡片选中态由 JS 同步（R2-2 写法，在既有 radio change 监听内替换为一条语句，两种事件语义下均正确）：`root.querySelectorAll('input[name="srcType"]').forEach(function (x) { x.closest('.src-opt').classList.toggle('on', x.checked); })`——注意同步**两卡**（radio change 仅在变为选中一方触发，不能只给触发方加 .on）；**初始 HTML 中 path 卡片写 `class="src-opt on"`**（默认选中不触发 change）。选中态 `.src-opt.on`：边框 --c-primary + 背景 --c-primary-50 + 左上角对勾角标（纯 CSS ::after 8px 蓝色圆含白 ✓）。radio 逻辑钩子（`input[name="srcType"]:checked` 查询、tfPath.disabled/tfFile.hidden 显隐切换）全部不改。`#tfFile`（file input）保留原生外观（R1 P3-4，位于 src-row 同级下方）。
- **递归开关**：path 卡片内（src-row 下方）加 `<label class="rec-opt"><input type="checkbox" id="tfRecursive" checked><span>包含子文件夹（递归扫描全部子目录）</span></label>`，checkbox 同样自定义外观（16px 方框，选中蓝底白 ✓，focus-visible 外环）；tooltip（title）「不勾选则仅扫描该目录第一层的图片文件」。upload 卡片下无此开关。
- **标签编辑器**：label-chip 现代化（白底 1px 边圆角 --r-full、内嵌键帽 key-badge + 名称 + chip-x）；label-add 行内输入（flex: 1）+「添加」改 `.btn-ghost`；错误提示 `.msg` 改红底浅红胶囊（--c-danger-bg 底 + --c-danger 字 + padding 4px 12px 圆角 --r-full），**并加 `.msg:empty { display:none; }`（R1 P1-3，防空胶囊常驻）**。
- **创建按钮**：主按钮加宽（padding 0 28px）+ 字重 600；`create-actions` 右对齐（margin-top 16px）。
- **任务卡**：
  - `.task-head`：名称 700 15px；状态改 **pill 徽章** `.st-pill`（统一：圆角 --r-full、padding 2px 10px、12px 字重 500）：ready=绿字绿底（--c-success-bg/--c-success）+ 前置 6px 绿点；scanning/extracting=蓝底浅+前置 spinner（复用 .spinner 缩到 10px）；error=红底浅红字；**去掉 blink 省略号动画类**（`::after` 删除，spinner 已表达进行中）。
  - `.task-src`：改两行结构：第一行 `srcType` chip（24px 高小标签：路径=--c-primary-50 蓝字；ZIP/7Z/RAR=--c-bg 灰字）+ 递归标注 chip（「含子目录」/「仅根目录」，仅路径任务显示）；第二行路径 `font-family var(--mono)` 12px --c-text-3。
  - `.task-meta`：改为两个小统计块（`.stat`：数字 700 16px --c-text + 标签 11px --c-text-3，分别是「图片 N」「已标注 N」）+ 进度百分比右对齐。
  - 进度条：6px 高、圆角 full、fill 渐变 `linear-gradient(90deg,#2563eb,#06b6d4)`。**作用域声明（R1 P2-5）：该规格通过共享类 `.progress-bar/.progress-fill` 全局生效，含上传进度条与标注页进度条，属换肤范围的一致性变更（非回归）**。
  - `.task-actions`：打开（**仅 `btn`** 主蓝）+ 导出（**仅 `btn-mini`**）+ 删除（**仅 `btn-danger`**，`margin-left:auto` 右推）（R1 P2-2：重写类列表，弃组合类 `btn btn-mini`；并约束 T1 的 CSS 覆写类 .btn-ghost/.btn-danger/.btn-clear 规则必须置于 .btn/.btn-cat 之后——app.js 引导按钮 `btn btn-ghost` 与 labelView `btn-cat btn-clear` 依赖该顺序）。
  - 卡片：hover 上浮（translateY(-2px) + --shadow-md，transition .18s）、1px --c-border 常态。
- **空状态**：`.empty-state`（居中列）：纯 CSS 文件夹插画（两个叠圆角矩形：后层 64px --c-border 前层 56px --c-primary-200，各含一条高光横线）+ 标题 15px 600「还没有任务」+ 副文 13px --c-text-3「在上方创建你的第一个标注任务」。**`.empty-state, .loading { grid-column: 1 / -1; }`（R1 P2-4，grid item 跨满列居中）**。
- **加载态**：`.loading` 前置 spinner。

### 3.5 R1 后端
1. `database.py`（1.0→1.1）：
   - SCHEMA_SQL 的 `CREATE TABLE tasks` 加 `recursiveScan INTEGER DEFAULT 1`（新库）。
   - `initSchema()` 幂等迁移：`PRAGMA table_info(tasks)` 查列，无 `recursiveScan` 则 `ALTER TABLE tasks ADD COLUMN recursiveScan INTEGER DEFAULT 1`（老行自动 1）。封装 `_ensureColumn(conn, table, column, ddl)` 小函数。
   - 评估过：主服务（旧代码）与迁移并发安全——ALTER ADD COLUMN 是瞬时写事务，WAL+busy_timeout 下无风险；旧代码 `SELECT *` 多一列不影响。
2. `taskApi.py`（1.1→1.2）：
   - `TaskCreateBody` 加 `recursive: bool = True`（Pydantic 默认值，老调用方兼容）。
   - `createPathTask` INSERT 加 `recursiveScan` 列（值 `1 if body.recursive else 0`）。
   - `listTasks` SELECT 加 `t.recursiveScan`，响应加 `'recursive': bool(...)`（任务卡显示用）。
   - `getTask` **SELECT 无需改**（经 `_ownedTaskRow` 的 `SELECT *`，迁移后已含新列，R1 P3-1），仅在响应 dict 加 `'recursive': bool(row['recursiveScan'])`。
3. `scanService.py`（1.0→1.1）：
   - SELECT 加 `recursiveScan`；
   - walk 循环内：`dirs[:] = [d for d in dirs if not os.path.islink(...)]` 后追加 `if not recursive: dirs[:] = []`（首轮迭代即 baseDir，清空 dirs 不再下钻=仅根层；符号链接文件过滤、扩展名过滤、自然序、分批插入全部共用不变）。
   - 非递归 0 图（子目录才有图）→ 沿用现有「未发现支持的图片文件」error 路径，errorMsg 不需特化（提示已足够定位）。
4. 前端 `taskView.js`（1.2→1.3）：
   - `createTask()` path 分支 body 加 `recursive: document.getElementById('tfRecursive').checked`。
   - `renderTasks` 卡片：`srcText` 行按 3.4 规格重排（含 recursive chip：`t.recursive === false` 显示「仅根目录」，true/undefined 显示「含子目录」——undefined 兜底为含，防老响应）。
5. `helpView.js`（1.2→1.3）④节「数据来源」条目：**替换原句「自动递归扫描其中的图片」**（R1 P3-5，防新旧描述并存矛盾），改为：「路径导入可选『包含子文件夹』（默认勾选=递归全部子目录；取消=仅扫描该目录第一层图片，子目录中的图片不会出现）」。
6. `README.md`：创建任务段补开关说明；「已知限制」无需改。

### 3.6 验收（T8）
自动（我来做，**按 A6 停机序列执行**：先停主服务 → 8687 验证实例 → 清理 → 停验证实例 → 重启主服务）：
- `node --check` 全部改动 JS；`uv run python -c import`。
- 8687 验证实例（此时主服务已停，无双实例副作用）：① 启动后 `PRAGMA table_info(tasks)` 含 recursiveScan（真实库迁移幂等，且重复启动不再 ALTER）；② fixtures 目录（根层 2 图 + 子目录 2 图）建任务勾选→4 项、relPath 含子目录；不勾选→仅 2 项根层；③ 不传 recursive 字段（curl 纯 JSON）→ 默认递归 4 项；④ getTask/listTasks 响应含 recursive。冒烟任务与临时文件测完清理（列清单待批准）。
- 主服务重启后 `api/health`。
手工（用户）：首页新视觉、创建表单卡片式来源选择、递归开关、键帽角标、分段控件、任务卡新布局、状态 pill、空状态插画。

## 4. 风险与对策
- **R-a 顶栏浅色**：仅 CSS+index.html 结构，48px 高度不变，标注页布局零影响。
- **R-b 类名不动换肤**：labelView 的 btn-cat/fbtn/mode-btns DOM 与新 CSS 必须对得上——评审重点核对选择器清单与 labelView.js 现有类名一一对应（grid-info、pos-text 等工具栏文本色也纳入 token）。
- **R-c 老库迁移**：幂等、加列默认 1；ALTER 在停机窗口内执行（A6 序列），彻底避开双实例 recover/sweep/audit 副作用（R1 P1-4）；不删任何列（无需回滚，去掉 UI 开关即可回退行为）。
- **R-d segmented 容器**：filter-btns 与 mode-btns 两处容器都要加背景 padding，grid 模式下 mode-btns 在同一 toolbar，宽度不同不冲突（flex 自适应）。
- **R-e src-opt 卡片化（更新）**：卡片为 div，radio 行为 label 不嵌套其他 label；radio 保留可聚焦自定义外观；JS 改动仅为 change 监听内的两卡 .on 同步语句（R2-2 写法）+ 初始 path 卡 `class="src-opt on"`；radio 查询/显隐逻辑全部不改；tfFile 保留原生外观与 hidden 属性切换。
- **R-f**：`status-*` 旧类删除 blink 动画时，确认 taskView 同时输出新 pill 类（JS 一起改，CSS 删旧类）。

## 5. TODO lists（派发实施子代理执行）

- [x] **T1 style.css**（1.2→1.3，核心）：按 3.1 写 tokens（含 --r-btn/--c-seg-bg）；按 3.2/3.3/3.4 重写按钮/顶栏/任务页/输入/徽章样式；**save 指示器三色映射（P1-1）**；**输入框选择器限定 text/number（P1-2）**；**.msg:empty 隐藏（P1-3）**；**CSS 覆写类 .btn-ghost/.btn-danger/.btn-clear 置于 .btn/.btn-cat 之后（P2-2）**；**保留 topbar-sep（P2-3）**；**.empty-state/.loading 跨满列（P2-4）**；grid/侧栏/help/guide/网格段仅把散落色值换 var() 引用（不改布局规则）；删除 status blink；新增 src-grid/src-opt(.on)/src-row/rec-opt 自定义 radio/checkbox/form-section/st-pill/stat/empty-state 样式；核对 labelView 全部类名都有对应新样式（附清单核对）。
  验证：无遗漏类（grep labelView/taskView/app/helpView 输出类名 ∩ style.css）。
- [x] **T2 index.html**（1.2→1.3）：顶栏 brand 结构 + brand-sub + **保留 topbar-sep** + helpBtn 保持 id；media query 窄屏藏 brand-sub（放 CSS）。
- [x] **T3 taskView.js**（1.2→1.3）：创建表单三段分区（基本信息段字段容器保留 .fld 类）+来源卡片化（div.src-opt > label.src-row + label.rec-opt，radio 查询/显隐逻辑不变，change 监听内改用 R2-2 两卡同步语句+初始 path 卡 class="src-opt on"）+递归 checkbox（id=tfRecursive 默认勾选）+标签编辑器 chip 升级+错误胶囊+create-actions 右对齐；任务卡按 3.4 重排（st-pill/src chip/recursive chip/stat 块/操作行，**按钮类列表按 P2-2 重写为单类**）+ **renderTasks 空分支输出 .empty-state 结构（R2-4）**；createTask path 分支带 recursive 字段。
  验证：`node --check` + 人工对照 DOM 无功能回归（radio 切换显隐、上传进度、轮询、删除 confirm 全保留）。
- [x] **T4 database.py**（1.0→1.1）：DDL 加列 + `_ensureColumn` 幂等迁移。
- [x] **T5 taskApi.py**（1.1→1.2）：TaskCreateBody.recursive、INSERT 列、list/get 返回 recursive。
- [x] **T6 scanService.py**（1.0→1.1）：SELECT 加列 + 非递归分支（walk 不下钻）。
- [x] **T7 helpView.js**（1.2→1.3）+ **README.md**：**替换**④节数据来源原句（P3-5）+ README 创建任务段补开关说明。
  验证：`node --check`。
- [x] **T8 综合验证**（我执行，不派子代理）：见 3.6 自动部分（按 A6 停机序列）。
- [x（重启✅）/⬜（手工验收）] **T9 主服务重启 + 手工验收**：重启沿用授权（A6 序列末步，已完成）；用户浏览器验收待做。

## 6. 实施纪律（给子代理的硬约束）
- 代码风格：IIFE + 'use strict' + var + 字符串拼接 HTML；Python 保持现有风格；**小驼峰**命名；文件头 Author/Version/Date/Description 齐全并按本方案递增版本号。
- 禁止：测试框架、CDN、构建工具、新依赖、暗色模式、改 api.js/labelView.js/app.js（helpView 仅文字）、动 grid 模式交互逻辑。
- 每处改动可追溯到本方案条目；不做方案外的「顺手美化」。
