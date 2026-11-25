# CSV 与 ZIP 导出方案

- Author: wilbur
- Version: 1.2
- Date: 2026-11-24
- Description: CSV 与 ZIP 已实现并上线。两轮方案评审后完成目录兼容、并发打包和临时文件管理。验收复核修正保留标签撞名、单文件 ZIP64 与下载断开清理。

## 1. 导出结果

- 在任务列表和单张、多张标注页打开「导出」，选择「CSV · 标注表」或「ZIP · 图片与标注表」。任务就绪后即可导出当前已保存的结果，包含尚未标注的行和图片。
- CSV 复用原接口 `GET /api/tasks/{taskId}/export`，维持 UTF-8 BOM、原列顺序、自然行序和附件响应。`?format=csv` 返回相同内容，`?format=zip` 下载 ZIP，其他值返回 400。任务归属校验返回 404，未就绪返回 409。
- ZIP 的根目录为 `annotations.csv`，内容与从同一标注快照单独导出的 CSV 一致。图片目录用标签名称，未标注统一放 `NOLabel/`。同类别中保留原数据的子目录，同名图片可同时导出。

```text
annotations.csv
巡检合格/
  cameraA/img01.png
  cameraB/img01.png
需要复查/
  img02.png
NOLabel/
  img03.png
```

- 用原标签和相对路径记录 CSV。只有需要兼容解压或消解重名时才调整 ZIP 内相应的文件夹或文件名，并在根目录 `archivePaths.csv` 记录调整过的 `relPath,label,zipPath`。某张源图消失、打开失败或变为非普通文件时跳过图片，保留主 CSV 该行并用 `缺失文件.txt` 列出路径与原因。

## 2. 后端设计

### 导出快照与 CSV

1. `exportService.py` 在同一个短 SQLite 读事务中检查任务归属和 `ready`，查询任务标签、标注人和按 `itemId` 排序的所有数据项。先结束事务，再写 CSV 或打包 ZIP。打包过程中新的标注可以正常保存，当前包的分类和 CSV 使用同一快照。
2. 从快照生成原有七列 `relPath,absPath,label,labelIndex,annotatorId,annotatorName,updatedAt`。保持 BOM、标准 CSV 转义、原单独 CSV 的媒体类型及 `labelIndex` 规则。先构建标签到索引的映射，旧库中若有不在任务标签列表的已保存标签，保留标签原名并留空索引。ZIP 可按该已保存标签分目录。
3. 单独 CSV 继续写入 `config.EXPORTS_DIR` 并通过 `FileResponse` 下载。使用包含任务 ID、时间戳、UUID 的最终文件名，每个请求使用独立临时文件，同目录 `os.replace` 后返回。生成失败清理本次临时文件。审计保留 `export` 事件和 `file` 属性，补 `format` 和缺失项数量。

### ZIP 成员和名称

1. 标签名称与每个文件路径段分别处理。数据项的 `relPath` 以 POSIX `/` 拆段，绝对路径、空段、`.` 或 `..` 段进入缺失报告。反斜杠是原文件名中的字符，和其他平台不兼容字符一样替换为 `_`。成员路径只由已检查的目录和文件名段用 `/` 拼成。
2. 将控制字符及 Windows 不兼容字符替换为 `_`，去掉末尾句点和空格，空名用 `_`。对 Windows 设备名称（包括带扩展名的 `CON`、`NUL`、`AUX`、`PRN`、`COM1` 至 `COM9` 和 `LPT1` 至 `LPT9`）添加前缀 `_`，同时覆盖设备名的特殊数字后缀。名称段保持在 255 个 UTF-8 字节内，文件截断时保留图片扩展名和用于去重的后缀。
3. 在同一父目录内，用 Unicode NFC 与 `casefold()` 作为重名比较键。根目录预留 `NOLabel`、`annotations.csv`、`archivePaths.csv` 和 `缺失文件.txt`。标签按任务设置顺序分配目录，遇到含保留名在内的冲突时追加 `_2`、`_3` 等后缀。目录和文件共用该父目录的名称集合，原目录重复出现时复用已分配的名字。主 CSV 保存原始标签和路径，对照表记录成功写入且名称发生变化的成员。
4. `zipfile.ZipFile` 使用 `ZIP_STORED` 与 ZIP64。打开本任务已登记的原图，通过文件句柄确认是可读的普通文件，并将实际大小交给 `ZipInfo` 选择 ZIP64，再分块写入。源文件打开失败和无效路径进入缺失清单。读取或写入中途失败则终止本次导出、关闭临时归档。
5. ZIP 只在本次下载期间占用服务器空间。使用 `config.TMP_DIR` 下的 `tempfile.TemporaryFile` 构建完整归档，按块流式返回，带 `Content-Length`、`application/zip` 与附件文件名。生成失败、流结束或响应清理时关闭句柄。ZIP 构建在同步路由工作线程内完成，客户端会在打包后开始下载。大包耗时取决于原图总大小和磁盘速度。

## 3. 前端设计

- `static/js/api.js` 的 `exportUrl(taskId, format)` 是链接生成入口，CSV 使用旧 URL，ZIP 加 `?format=zip`。
- `static/js/app.js` 提供共享的 `exportMenuHtml(taskId, ready)`。用原生 `details/summary` 和两个下载链接渲染菜单。未就绪使用原生 `disabled` 按钮。链接直接走浏览器下载和现有 cookie 身份。点击 ZIP 时用现有通知提示打包，选中链接或点菜单外部时收起菜单。
- `static/js/taskView.js` 任务卡和 `static/js/labelView.js` 工具栏调用同一个生成入口。替换旧按钮时同步移除旧监听，保留任务卡打开和删除、标注页切换及侧栏绑定。
- `static/css/style.css` 沿用次按钮和现有颜色，在打开的菜单上提供足够的层级与可见键盘焦点。任务卡和标注页保持现有布局。
- `static/js/helpView.js` 更新快速上手、就绪状态、工具栏和导出章节。`README.md` 更新简介和导出流程，说明两种格式、目录结构、对照表和缺失报告。导出使用顶栏已经显示保存成功的结果。

## 4. 实施与验证清单

- [x] T1 `exportService.py` 升至 1.3。完成导出快照、CSV 留档、归档命名、ZIP64、流式下载、审计和错误清理。
- [x] T2 `api.js` 升至 1.3，扩展导出链接。`app.js` 升至 1.6，共用菜单，选中链接或 `Esc` 收起后恢复键盘焦点。
- [x] T3 `taskView.js` 和 `labelView.js` 升至 1.4，任务卡、单张与多张标注页均提供导出菜单。
- [x] T4 `style.css` 升至 1.6，完成菜单定位、层级和焦点样式。
- [x] T5 `helpView.js` 升至 1.5，与 `README.md` 同步双格式用法。
- [x] T6 通过全部 JavaScript 语法检查和 Python 导入验证。
- [x] T7 隔离 FastAPI 与 SQLite 验证默认 CSV、显式 CSV、包内 CSV 三者字节一致，ZIP 原图、中文目录、同名图片、设备名、缺失清单、并发导出与 400/404/409 均符合预期。模拟单文件 ZIP64 阈值通过。主动断开 28 MiB HTTP 下载后确认临时文件句柄已关闭。
- [x] T8 Firefox 验证任务卡实际下载 CSV，单张和多张标注页实际下载并解包 ZIP，覆盖 Tab/Enter、焦点样式、未就绪禁用、点外收起与 `Esc` 保留网格选择。
- [x] T9 主服务 8686 已重启。健康接口、导出参数、前端菜单和挂载点的 ZIP 临时目录读写通过检查。
