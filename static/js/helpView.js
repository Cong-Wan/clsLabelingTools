/* Author: wilbur / Version: 1.5 / Date: 2026-11-24 / Description: 帮助弹窗视图（顶栏「使用说明」打开；八节内容：快速上手/快捷键/多张批量标注/创建任务/任务状态/标注页/导出协作/常见问题；×/ESC/点遮罩三路关闭，ESC preventDefault 供 app.js 判 defaultPrevented；遮罩判 e.target===overlay；模块初始化挂一次 ESC 监听；isOpen() 供热键守卫）；v1.1 标签映射细化；v1.2 热键 0-9/d 重映射+新增多张批量标注节+类别计数+CSV labelIndex 说明；v1.3 ④节数据来源改为「包含子文件夹」开关说明（替换原「自动递归扫描」描述，防新旧描述矛盾）；v1.4 ② 表 R/a/d 热键行+③ 节固定 6×2=12+侧栏/滚轮缩放+⑥ 节标签胶囊/搜索/复制/缩放口径替换三色圆点描述；v1.5 ①⑤⑥⑦⑧ 同步 CSV/ZIP 双格式导出（菜单收起、archivePaths 对照、缺失报告、导出用已保存结果口径） */
(function () {
  'use strict';

  var clsHelpView = {
    _open: false,

    isOpen: function () {
      return this._open;
    },

    show: function () {
      if (this._open) return;
      this._open = true;
      var overlay = document.createElement('div');
      overlay.className = 'help-overlay';
      overlay.innerHTML =
        '<div class="help-box">' +
        '<div class="help-head"><h3>使用说明</h3>' +
        '<button id="helpClose" class="help-close" title="关闭（ESC）">×</button></div>' +
        '<div class="help-body">' + this._content() + '</div>' +
        '</div>';
      document.body.appendChild(overlay);
      var self = this;
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) self.close();
      });
      overlay.querySelector('#helpClose').addEventListener('click', function () {
        self.close();
      });
    },

    close: function () {
      if (!this._open) return;
      var overlay = document.querySelector('.help-overlay');
      if (overlay) overlay.remove();
      this._open = false;
    },

    _content: function () {
      return '' +
        '<h4>① 快速上手</h4>' +
        '<ol>' +
        '<li>任务列表页「创建任务」：填写任务名 → 选择数据来源（服务器绝对路径 / 上传压缩包）→ 添加标签类别 → 点「创建任务」。</li>' +
        '<li>等待任务状态变「就绪」（状态会自动更新；大压缩包整个上传+处理过程需分钟级）。</li>' +
        '<li>点「打开」进入标注页：看图 → 按数字键 0-9（或点击类别按钮）→ 自动跳到下一张；也可切到「多张」网格模式批量标注。</li>' +
        '<li>全部标完后点「导出」菜单选「CSV · 标注表」或「ZIP · 图片与标注表」下载结果。</li>' +
        '</ol>' +
        '<h4>② 键盘快捷键（标注页）</h4>' +
        '<table class="help-keys">' +
        '<tr><th>键</th><th>作用</th></tr>' +
        '<tr><td><span class="key-badge">0</span> ~ <span class="key-badge">9</span></td><td>给当前图片（单张）或全部选中图片（多张）打对应类别标签；单张打完自动跳下一张</td></tr>' +
        '<tr><td><span class="key-badge">R</span></td><td>单张：清除当前图片标注（停留）；多张：清空选择</td></tr>' +
        '<tr><td><span class="key-badge">a</span> / <span class="key-badge">d</span></td><td>上一张 / 下一张（仅单张模式）</td></tr>' +
        '<tr><td>← / →</td><td>同 a / d（仅单张）</td></tr>' +
        '<tr><td>Esc</td><td>多张模式：清空选择</td></tr>' +
        '</table>' +
        '<p>每张图只能有<b>一个类别（单标签）</b>——按另一个数字键（或点其他类别按钮）会直接<b>覆盖</b>原标注。光标在输入框（如跳转框）内时快捷键不生效；前 10 个类别对应 0-9（第 1 个=0），第 11 个及之后仅点击。</p>' +
        '<h4>③ 多张批量标注（网格模式）</h4>' +
        '<ul>' +
        '<li>标注页工具栏「单张｜多张」开关切换（选择会被记忆）；多张模式=整屏网格展示排在前面的未标注图片，网格固定 6×2=12 张。</li>' +
        '<li><b>选择</b>：点击=只选该图；<b>Ctrl+点击</b>=增减单图；<b>Shift+点击</b>=从上次点击处连选一段；<b>按住拖动</b>=框选（Ctrl+拖动=追加）；<b>R / Esc</b>=清空选择。工具栏右侧显示「未标注 N · 已选 M」。</li>' +
        '<li><b>标注</b>：选中后按 0-9 或点类别按钮=给全部选中图片打同一类别；标完的图自动被新的未标注图片顶替（保存中的图暂不显示、保存完成后自动补位；保存失败在顶栏显示「N 条待重试」，可一键重试）。</li>' +
        '<li>多张模式右侧同样显示文件列表（可搜索、双击复制文件名、点击某条会定位并切回单张）；滚轮悬停格子可缩放该图（双击复位）。</li>' +
        '<li>多张模式只展示未标注图片，要复查/改标请切回单张模式。</li>' +
        '</ul>' +
        '<h4>④ 创建任务</h4>' +
        '<ul>' +
        '<li><b>任务名称</b>：≤64 字符。</li>' +
        '<li><b>数据来源（二选一）</b>：' +
        '<ul>' +
        '<li><b>服务器绝对路径</b>：服务器本机可读的目录，路径导入可选『包含子文件夹』（默认勾选=递归全部子目录；取消=仅扫描该目录第一层图片，子目录中的图片不会出现），支持 jpg / jpeg / png / bmp / webp / gif。适合数据已在服务器上的情况，无需上传等待（数据量大时扫描在后台进行，稍候即可）。</li>' +
        '<li><b>压缩包上传</b>：支持 .zip / .7z / .rar。进度条走完后还会显示「服务器保存中…」，GB 级大包整个上传+保存过程约需<b>分钟级</b>，属正常等待。限制：单包 ≤10GB；解压后总量 ≤20GB、文件数 ≤20 万；<b>不支持加密包、分卷包；压缩包内的压缩包不会被解压</b>（嵌套包会导致「未发现支持的图片文件」）。</li>' +
        '</ul></li>' +
        '<li><b>标签映射</b>：在「输入类别名称」框里输入一个类别名，点「添加」（或按回车）<b>逐个添加</b>；类别名 ≤32 字符、最多 50 个，同名自动去重，点类别右侧的「×」可删除。<b>数字热键按添加顺序分配：第 1 个添加的对应 0，第 2 个对应 1 … 前 10 个对应数字键 0-9，之后仅点击</b>；删除中间类别后，后面的类别自动补位（热键号随之变化）。<b>创建后不可修改</b>——要改标签必须删除任务重建。</li>' +
        '</ul>' +
        '<h4>⑤ 任务状态</h4>' +
        '<ul>' +
        '<li><b>解压中 / 扫描中</b>：后台处理中，页面自动刷新，完成自动变「就绪」。</li>' +
        '<li><b>就绪</b>：可打开标注、可导出（CSV / ZIP）。</li>' +
        '<li><b>错误</b>：卡片显示红色原因；常见为压缩包不支持（加密 / 分卷 / 嵌套）或路径不存在，删除后重建即可。</li>' +
        '</ul>' +
        '<h4>⑥ 标注页怎么用</h4>' +
        '<ul>' +
        '<li>顶栏工具行：返回 / 模式开关（单张/多张）/ 过滤（全部 / 未标注 / 已标注）/ 序号跳转 / 导出菜单（CSV / ZIP；点链接或点菜单外收起，Esc 关菜单且不清空图像选择）。</li>' +
        '<li>下方类别按钮可直接点击（无需键盘），「清除」按钮 = R 键的鼠标等价操作；<b>类别按钮右侧的数字 = 该类别已标注张数</b>（保存中为即时计数，网络失败重试后自动修正）。</li>' +
        '<li>右侧列表：已标注显示标签名胶囊（绿=已保存/黄=保存中，悬停看全名）、未标注灰点、清除中显示「清除中」；上方搜索框按文件名过滤（英文不区分大小写）；双击条目复制文件名；单张大图滚轮缩放（双击复位）。</li>' +
        '<li>标注后自动前进（在当前过滤列表内顺序，跨页自动加载，最后一张停留提示）；「未标注」过滤下标注后该项移出列表，适合连续快打。</li>' +
        '<li>保存机制：标注后<b>立即自动保存</b>（无需任何手动保存操作），顶栏同步显示「保存中… / 已保存 时间 / N 条待重试」；网络失败自动重试 1 次，仍失败进「N 条待重试」，点「一键重试」或刷新页面自动补传，<b>数据不丢</b>。</li>' +
        '<li>顶栏右上角名字 = 标注人显示名（点击可改），导出 CSV 的 annotatorName 列使用它。</li>' +
        '</ul>' +
        '<h4>⑦ 导出与多人协作</h4>' +
        '<ul>' +
        '<li>「导出」菜单（任务卡与标注页工具栏）仅「就绪」任务可用（未就绪按钮置灰），两种格式：<ul>' +
        '<li><b>CSV · 标注表</b>：浏览器下载完整 CSV（列：relPath, absPath, label, labelIndex, annotatorId, annotatorName, updatedAt；labelIndex=数字类别编号，与热键一致；未标注行 label 与 labelIndex 为空），服务器同步留档。</li>' +
        '<li><b>ZIP · 图片与标注表</b>：根目录 annotations.csv（与同一快照单独导出的 CSV 内容一致）+ 以标签名为目录的原图（未标注统一放 NOLabel/；保留原数据子目录，同名图片可同时导出）。点击后服务器先完整打包（图片不压缩，耗时取决于总量与磁盘速度），完成后浏览器自动开始下载。</li>' +
        '</ul></li>' +
        '<li><b>ZIP 对照表</b>：为兼容解压环境（如 Windows 设备名/不兼容字符）或消解同名而改动的目录/文件名，记录在根目录 archivePaths.csv（relPath,label,zipPath，仅存在调整时生成）；主 CSV 仍保存原始标签与路径，可逐项反查。</li>' +
        '<li><b>ZIP 缺失报告</b>：源图消失、打开失败或非普通文件的行保留在 annotations.csv，图片跳过，路径与原因列在根目录 缺失文件.txt（仅存在缺失时生成）。</li>' +
        '<li>导出内容 = 顶栏显示「已保存」的结果：标注后立即自动保存，保存中/待重试的标注在入库前不会进入导出。</li>' +
        '<li>两人标同一批数据：各自导入同一数据源、各建各的任务，互不可见；两份导出的 relPath 一致，可用 Excel 按 relPath 列 VLOOKUP 合并。</li>' +
        '</ul>' +
        '<h4>⑧ 常见问题</h4>' +
        '<ul>' +
        '<li><b>上传进度 100% 后停在「服务器保存中…」？</b>正常，GB 级包写盘需分钟级。</li>' +
        '<li><b>点了「ZIP · 图片与标注表」后迟迟没开始下载？</b>正常：服务器先把完整包在临时空间构建好（图片不压缩原样存入，GB 级需分钟级），完成后自动开始下载，期间请勿离开或刷新页面。</li>' +
        '<li><b>任务报「未发现支持的图片文件」，图片在压缩包里的压缩包里？</b>先手动解压外层包，再走「绝对路径」导入，或直接上传内层 zip。</li>' +
        '<li><b>换浏览器 / 清缓存后任务不见了？</b>身份绑定浏览器（匿名身份），换浏览器 = 新身份，请回原浏览器操作。</li>' +
        '<li><b>删除任务后磁盘文件还在？</b>删除仅清数据库记录，物理文件保留（防误删），需手动清理。</li>' +
        '<li><b>处理中任务删不掉？</b>页面会二次确认「强制删除」（中断后台处理）。</li>' +
        '<li><b>服务重启后任务变「错误」？</b>中断任务删除后重建即可。</li>' +
        '</ul>';
    }
  };

  // ESC 关闭：模块初始化挂一次（处理器内先判 isOpen，防多次开关叠加监听器）；
  // preventDefault 供 app.js 的 Esc 分支凭 defaultPrevented 跳过，防止关帮助时误清网格选择
  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && clsHelpView.isOpen()) {
      e.preventDefault();
      clsHelpView.close();
    }
  });

  window.clsHelpView = clsHelpView;
})();
