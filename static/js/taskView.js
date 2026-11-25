/* Author: wilbur / Version: 1.4 / Date: 2026-11-24 / Description: 任务列表页（创建表单三段分区：基本信息/数据来源（卡片式二选一，path 卡含「包含子文件夹」递归开关 tfRecursive 默认勾选，请求体带 recursive）/标签映射编辑器增删/序号热键预览（前 10 标 0-9，第 1 个=0）+XHR 进度+100% 后「服务器保存中…（GB 级分钟级）」+创建后不可改提示；任务卡片：st-pill 状态徽章/srcType+递归 chip/统计块/进度条/状态轮询 2s 终态停/errorMsg 红字/打开/导出非 ready 禁用/删除 confirm+非终态 409 提示+强制删除选项/空状态插画；仅本人任务）；v1.1 标签映射表单提示补「逐个输入点添加、按添加顺序分配热键」；v1.2 角标/预览/提示改为 0-9（第 1 个类别=0）；v1.3 表单三段分区+来源卡片化（div.src-opt>label.src-row+label.rec-opt）+递归开关+任务卡重排（pill/chip/stat 块/单类按钮）+空状态+createTask path 分支带 recursive；v1.4 任务卡导出按钮改用 clsApp.exportMenuHtml 共享菜单（CSV/ZIP，未就绪原生 disabled），同步移除原 act-export 监听（打开/删除绑定不变，菜单收起由 app.js 委托） */
(function () {
  'use strict';

  var MAX_LABELS = 50; // 防止误输入（设计未限定，工程上限）

  var clsTaskView = {
    _labels: [],
    _pollTimers: {},

    mount: function () {
      // 清理上一视图残留轮询
      this._clearPolls();
      var root = document.getElementById('viewRoot');
      root.innerHTML =
        '<section class="task-page">' +
        '  <div class="create-card">' +
        '    <h2>创建任务</h2>' +
        '    <div class="form-section">' +
        '      <div class="form-section-title">基本信息</div>' +
        '      <label class="fld">任务名称' +
        '        <input id="tfName" type="text" maxlength="64" placeholder="如：潇湘站巡视图片"></label>' +
        '    </div>' +
        '    <div class="form-section">' +
        '      <div class="form-section-title">数据来源（二选一）</div>' +
        '      <div class="src-grid">' +
        '        <div class="src-opt on">' +
        '          <label class="src-row"><input type="radio" name="srcType" value="path" checked> 服务器绝对路径</label>' +
        '          <input id="tfPath" type="text" placeholder="/data_27T_jfs95/wilbur/Datasets/...">' +
        '          <label class="rec-opt" title="不勾选则仅扫描该目录第一层的图片文件">' +
        '            <input type="checkbox" id="tfRecursive" checked><span>包含子文件夹（递归扫描全部子目录）</span></label>' +
        '        </div>' +
        '        <div class="src-opt">' +
        '          <label class="src-row"><input type="radio" name="srcType" value="upload"> 压缩包上传（.zip / .7z / .rar）</label>' +
        '          <input id="tfFile" type="file" accept=".zip,.7z,.rar" hidden>' +
        '        </div>' +
        '      </div>' +
        '    </div>' +
        '    <div class="form-section">' +
        '      <div class="form-section-title">标签映射</div>' +
        '      <span class="fld-title">逐个输入名称点「添加」；按添加顺序分配热键：前 10 个对应 0-9（第 1 个=0），其余仅点击；创建后不可修改，改标签需删除重建</span>' +
        '      <div id="labelList" class="label-list"></div>' +
        '      <div class="label-add">' +
        '        <input id="tfNewLabel" type="text" maxlength="32" placeholder="输入类别名称">' +
        '        <button id="btnAddLabel" class="btn-ghost">添加</button>' +
        '      </div>' +
        '      <div id="labelPreview" class="label-preview"></div>' +
        '    </div>' +
        '    <div id="uploadBox" class="upload-box" hidden>' +
        '      <div class="progress-bar"><div id="uploadBar" class="progress-fill"></div></div>' +
        '      <span id="uploadText"></span>' +
        '    </div>' +
        '    <div class="create-actions">' +
        '      <button id="btnCreate" class="btn">创建任务</button>' +
        '      <span id="createMsg" class="msg"></span>' +
        '    </div>' +
        '  </div>' +
        '  <h2 class="list-title">我的任务</h2>' +
        '  <div id="taskGrid" class="task-grid"><div class="loading">加载中…</div></div>' +
        '</section>';

      var self = this;
      // 来源切换：显隐钩子（tfPath.disabled/tfFile.hidden）不变 + 两卡 .on 同步
      // （radio change 仅在变为选中一方触发，两卡都要同步，R2-2；初始 path 卡 HTML 已写死 on）
      root.querySelectorAll('input[name="srcType"]').forEach(function (r) {
        r.addEventListener('change', function () {
          var fileInput = root.querySelector('#tfFile');
          var pathInput = root.querySelector('#tfPath');
          if (r.value === 'upload') {
            fileInput.hidden = false;
            pathInput.disabled = true;
          } else {
            fileInput.hidden = true;
            pathInput.disabled = false;
          }
          root.querySelectorAll('input[name="srcType"]').forEach(function (x) {
            x.closest('.src-opt').classList.toggle('on', x.checked);
          });
        });
      });
      root.querySelector('#btnAddLabel').addEventListener('click', function () { self.addLabel(); });
      root.querySelector('#tfNewLabel').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') self.addLabel();
      });
      root.querySelector('#btnCreate').addEventListener('click', function () { self.createTask(); });
      this.renderLabelEditor();
      this.refresh();
    },

    _clearPolls: function () {
      Object.keys(this._pollTimers).forEach(function (k) {
        clearInterval(this._pollTimers[k]);
      }, this);
      this._pollTimers = {};
    },

    /* ---------- 标签映射编辑器 ---------- */
    addLabel: function () {
      var input = document.getElementById('tfNewLabel');
      var v = input.value.trim();
      if (!v) return;
      if (this._labels.includes(v)) {
        this._msg('类别已存在（自动去重）');
        return;
      }
      if (this._labels.length >= MAX_LABELS) {
        this._msg('类别数量过多（上限 ' + MAX_LABELS + '）');
        return;
      }
      this._labels.push(v);
      input.value = '';
      this.renderLabelEditor();
    },

    removeLabel: function (i) {
      this._labels.splice(i, 1);
      this.renderLabelEditor();
    },

    renderLabelEditor: function () {
      var list = document.getElementById('labelList');
      var preview = document.getElementById('labelPreview');
      if (!list) return;
      list.innerHTML = this._labels.map(function (lb, i) {
        var badge = i < 10 ? '<span class="key-badge">' + i + '</span>' : '<span class="key-badge key-more">仅点击</span>';
        return '<span class="label-chip">' + badge + esc2(lb) +
          ' <button class="chip-x" data-i="' + i + '" title="删除">×</button></span>';
      }).join('') || '<span class="muted">尚未添加类别（至少 1 个）</span>';
      list.querySelectorAll('.chip-x').forEach(function (b) {
        b.addEventListener('click', function () {
          clsTaskView.removeLabel(Number(b.getAttribute('data-i')));
        });
      });
      // 序号↔热键映射预览（前 9 个标 1-9，>9 仅点击）
      preview.innerHTML = this._labels.length
        ? this._labels.map(function (lb, i) {
            return '<span class="pv">' + (i < 10 ? i : '·') + '→' + esc2(lb) + '</span>';
          }).join(' ')
        : '';
    },

    collectLabels: function () {
      // trim + 去重（保序）
      var out = [];
      this._labels.forEach(function (v) {
        var t = v.trim();
        if (t && !out.includes(t)) out.push(t);
      });
      return out;
    },

    _msg: function (text) {
      var el = document.getElementById('createMsg');
      if (el) el.textContent = text;
    },

    /* ---------- 创建任务 ---------- */
    createTask: async function () {
      var self = this;
      var nameEl = document.getElementById('tfName');
      var name = nameEl.value.trim();
      if (!name) { this._msg('请填写任务名称'); return; }
      var labels = this.collectLabels();
      if (!labels.length) { this._msg('请至少添加 1 个类别'); return; }
      var srcType = document.querySelector('input[name="srcType"]:checked').value;
      this._msg('');
      var btn = document.getElementById('btnCreate');
      btn.disabled = true;
      try {
        if (srcType === 'path') {
          var path = document.getElementById('tfPath').value.trim();
          if (!path) { this._msg('请填写绝对路径'); btn.disabled = false; return; }
          var recursive = document.getElementById('tfRecursive').checked;
          var r = await clsApi.createPathTask({ name: name, sourceType: 'path', path: path, labels: labels, recursive: recursive });
          location.hash = '#/task/' + r.taskId;
        } else {
          var fileInput = document.getElementById('tfFile');
          if (!fileInput.files.length) { this._msg('请选择压缩包文件'); btn.disabled = false; return; }
          var box = document.getElementById('uploadBox');
          var bar = document.getElementById('uploadBar');
          var text = document.getElementById('uploadText');
          box.hidden = false;
          var file = fileInput.files[0];
          this._msg('上传中（GB 级包上传+保存约需分钟级，请耐心等待）…');
          var up = await clsApi.uploadArchive(file, name, labels, function (pct) {
            bar.style.width = Math.round(pct * 100) + '%';
            if (pct < 1) {
              text.textContent = '上传中 ' + Math.round(pct * 100) + '%';
            } else {
              text.textContent = '上传完成，服务器保存中…（GB 级约需分钟级）';
            }
          });
          this._msg('任务已创建，进入任务页…');
          setTimeout(function () { location.hash = '#/task/' + up.taskId; }, 300);
        }
      } catch (e) {
        this._msg('创建失败：' + (e.detail || e.status));
        btn.disabled = false;
        document.getElementById('uploadBox').hidden = true;
      }
    },

    /* ---------- 任务列表/卡片 ---------- */
    refresh: async function () {
      var grid = document.getElementById('taskGrid');
      if (!grid) return;
      try {
        var data = await clsApi.listTasks();
        this.renderTasks(data.tasks);
      } catch (e) {
        grid.innerHTML = '<div class="loading">加载失败：' + esc2(e.detail || e.status) + '</div>';
      }
    },

    renderTasks: function (tasks) {
      var grid = document.getElementById('taskGrid');
      if (!grid) return;
      if (!tasks.length) {
        grid.innerHTML =
          '<div class="empty-state">' +
          '<div class="empty-art"><i class="back"></i><i class="front"></i></div>' +
          '<div class="empty-title">还没有任务</div>' +
          '<div class="empty-sub">在上方创建你的第一个标注任务</div>' +
          '</div>';
        return;
      }
      var self = this;
      grid.innerHTML = tasks.map(function (t) {
        var statusText = { extracting: '解压中', scanning: '扫描中', ready: '就绪', error: '错误' }[t.status] || t.status;
        var statusCls = 'st-pill st-' + t.status;
        var srcText = t.sourceType === 'path' ? '路径' : t.sourceType.toUpperCase();
        var srcChipCls = t.sourceType === 'path' ? 'src-chip' : 'src-chip-plain';
        // recursive 字段：false=仅根目录；true/undefined（老响应）兜底为含子目录
        var recChip = t.sourceType === 'path'
          ? '<span class="src-chip-plain">' + (t.recursive === false ? '仅根目录' : '含子目录') + '</span>'
          : '';
        var progressPct = Math.round(t.progress * 100);
        var canExport = t.status === 'ready';
        var spinner = (t.status === 'scanning' || t.status === 'extracting') ? '<span class="spinner"></span>' : '';
        return '<div class="task-card" data-id="' + t.taskId + '">' +
          '<div class="task-head"><span class="task-name">' + esc2(t.name) + '</span>' +
          '<span class="' + statusCls + '">' + spinner + statusText + '</span></div>' +
          '<div class="task-src"><span class="' + srcChipCls + '">' + srcText + '</span>' + recChip +
          '<div class="src-path">' + esc2(t.sourcePath) + '</div></div>' +
          '<div class="task-meta">' +
          '<span class="stat"><b>' + t.itemCount + '</b><span>图片</span></span>' +
          '<span class="stat"><b>' + t.labeledCount + '</b><span>已标注</span></span>' +
          '<span class="task-pct">' + progressPct + '%</span>' +
          '</div>' +
          (t.status === 'ready' || t.status === 'error' ?
            '<div class="progress-bar"><div class="progress-fill" style="width:' + progressPct + '%"></div></div>' : '') +
          (t.errorMsg ? '<div class="task-error">' + esc2(t.errorMsg) + '</div>' : '') +
          '<div class="task-actions">' +
          '<button class="btn act-open">打开</button>' +
          clsApp.exportMenuHtml(t.taskId, canExport) +
          '<button class="btn-danger act-del">删除</button>' +
          '</div></div>';
      }).join('');
      grid.querySelectorAll('.task-card').forEach(function (card) {
        var t = tasks.find(function (x) { return x.taskId === card.getAttribute('data-id'); });
        card.querySelector('.act-open').addEventListener('click', function () {
          location.hash = '#/task/' + t.taskId;
        });
        // 导出菜单：渲染自 clsApp.exportMenuHtml，链接/收起交互由 app.js 统一委托（旧 act-export 监听随按钮替换移除）
        card.querySelector('.act-del').addEventListener('click', function () { self.deleteTask(t); });
      });
      // 非终态任务轮询 2s（终态即停）
      tasks.forEach(function (t) {
        if (t.status === 'extracting' || t.status === 'scanning') {
          self.startPoll(t.taskId);
        }
      });
    },

    startPoll: function (taskId) {
      var self = this;
      if (this._pollTimers[taskId]) return;
      this._pollTimers[taskId] = setInterval(async function () {
        var t;
        try {
          t = await clsApi.getTask(taskId);
        } catch (e) {
          return; // 瞬时错误继续轮询
        }
        if (t.status === 'ready' || t.status === 'error') {
          clearInterval(self._pollTimers[taskId]);
          delete self._pollTimers[taskId];
          self.refresh();
        }
      }, 2000);
    },

    deleteTask: async function (t) {
      if (!confirm('删除任务「' + t.name + '」？\n（仅删 DB 记录，uploads/datasets 物理文件保留，可手动清理）')) return;
      try {
        await clsApi.deleteTask(t.taskId, false);
      } catch (e) {
        if (e.status === 409) {
          if (confirm('任务处理中不能直接删除。\n是否强制删除？（将中断后台解压/扫描）')) {
            try {
              await clsApi.deleteTask(t.taskId, true);
            } catch (e2) {
              clsApp.notify('强制删除失败：' + (e2.detail || e2.status));
              return;
            }
          } else {
            return;
          }
        } else {
          clsApp.notify('删除失败：' + (e.detail || e.status));
          return;
        }
      }
      this.refresh();
    }
  };

  // 本地转义（自包含，不依赖加载顺序）
  function esc2(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  window.clsTaskView = clsTaskView;
})();
