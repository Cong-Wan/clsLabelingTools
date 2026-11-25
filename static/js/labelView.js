/* Author: wilbur / Version: 1.5 / Date: 2026-11-24 / Description: 单张与多张标注、标签计数、侧栏、滚轮缩放和导出。本次保留同一文件列表重绘时的滚动位置。 */
(function () {
  'use strict';

  var PAGE_SIZE = 100;
  var GRID_SIZE = 12;
  var LS_LABEL_MODE = 'clsLabelMode';

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function applyZoom(img, zoom) {
    img.style.transform = zoom
      ? 'translate(' + zoom.x + 'px, ' + zoom.y + 'px) scale(' + zoom.scale + ')'
      : '';
  }

  function zoomImage(img, event, zoom, maxScale) {
    if (!img.naturalWidth || !event.deltaY || event.ctrlKey) return zoom;
    event.preventDefault();
    var current = zoom || { scale: 1, x: 0, y: 0 };
    var factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
    var scale = Math.min(maxScale, Math.max(0.25, current.scale * factor));
    if (scale === current.scale) return zoom;
    var rect = img.getBoundingClientRect();
    var shift = 1 - scale / current.scale;
    // 累加位移，使光标下的图像坐标在本次缩放后留在原处。
    var next = {
      scale: scale,
      x: current.x + (event.clientX - rect.left) * shift,
      y: current.y + (event.clientY - rect.top) * shift
    };
    applyZoom(img, next);
    return next;
  }

  var clsLabelView = {
    task: null,
    filter: 'all',
    page: 0,
    items: [],
    total: 0,
    pos: 0,
    hint: '',
    _pollTimer: null,
    _viewId: 0,
    _listRequest: 0,
    _gridRequest: 0,
    _taskRequest: 0,
    _loading: false,

    _mode: 'single',
    _gridItems: [],
    _gridTotal: 0,
    _sel: {},
    _anchor: null,
    _saving: false,
    _labelCounts: [],

    _search: '',
    _searchDraft: '',
    _searchComposing: false,
    _searchTimer: null,
    _sideClickTimer: null,
    _zoomItemId: null,
    _zoom: null,

    mount: async function (taskId) {
      this.unmount();
      var viewId = this._viewId;
      document.getElementById('viewRoot').innerHTML = '<div class="loading">加载中…</div>';
      this.filter = 'all';
      this.page = 0;
      this.pos = 0;
      this.hint = '';
      this.items = [];
      this.total = 0;
      this._sel = {};
      this._anchor = null;
      this._gridItems = [];
      this._gridTotal = 0;
      this._search = '';
      this._searchDraft = '';
      this._zoomItemId = null;
      this._zoom = null;
      this._mode = localStorage.getItem(LS_LABEL_MODE) === 'grid' ? 'grid' : 'single';
      var task;
      try {
        task = await clsApi.getTask(taskId);
      } catch (e) {
        if (viewId === this._viewId) this._renderNotFound(e);
        return;
      }
      if (viewId !== this._viewId) return;
      this.task = task;
      this._labelCounts = (task.labelCounts || []).slice();
      if (task.status === 'ready') {
        await Promise.all([this.loadItems(), this._mode === 'grid' && this.loadGrid()]);
      } else {
        this._startPoll();
      }
      if (viewId === this._viewId) this.render();
    },

    unmount: function () {
      this._viewId++;
      this.task = null;
      this._loading = false;
      this._searchComposing = false;
      this._stopPoll();
      clearTimeout(this._searchTimer);
      clearTimeout(this._sideClickTimer);
      this._searchTimer = null;
      this._sideClickTimer = null;
    },

    _renderNotFound: function (e) {
      document.getElementById('viewRoot').innerHTML =
        '<section class="label-page"><div class="notready">' +
        '<button class="btn" onclick="location.hash=\'#/tasks\'">← 返回任务列表</button>' +
        '<p class="task-error">任务不存在或无权访问：' + esc(e.detail || e.status) + '</p>' +
        '</div></section>';
    },

    _startPoll: function () {
      var self = this;
      var viewId = this._viewId;
      var taskId = this.task.taskId;
      this._stopPoll();
      this._pollTimer = setInterval(async function () {
        var task;
        try {
          task = await clsApi.getTask(taskId);
        } catch (e) {
          return;
        }
        if (viewId !== self._viewId || !self._pollTimer) return;
        self.task = task;
        if (task.status === 'ready' || task.status === 'error') {
          self._stopPoll();
          if (task.status === 'ready') {
            self._labelCounts = (task.labelCounts || []).slice();
            await Promise.all([self.loadItems(), self._mode === 'grid' && self.loadGrid()]);
          }
          if (viewId === self._viewId) self.render();
        }
      }, 2000);
    },

    _stopPoll: function () {
      if (this._pollTimer) {
        clearInterval(this._pollTimer);
        this._pollTimer = null;
      }
    },

    currentItem: function () {
      return this.items[this.pos] || null;
    },

    setHint: function (text) { this.hint = text; },

    /* ---------- 数据加载 ---------- */
    loadItems: async function (background) {
      var viewId = this._viewId;
      var request = ++this._listRequest;
      var taskId = this.task.taskId;
      var filter = this.filter;
      var search = this._search;
      var page = this.page;
      this._loading = !background || this._loading;
      try {
        var data = await clsApi.listItems(taskId, page * PAGE_SIZE, PAGE_SIZE, filter, search);
        if (viewId !== this._viewId || request !== this._listRequest) return false;
        var lastPage = Math.max(0, Math.ceil(data.total / PAGE_SIZE) - 1);
        if (page > lastPage) {
          data = await clsApi.listItems(taskId, lastPage * PAGE_SIZE, PAGE_SIZE, filter, search);
          if (viewId !== this._viewId || request !== this._listRequest) return false;
          this.page = lastPage;
          this.pos = 0;
        }
        this.items = data.items;
        this.total = data.total;
        this.pos = Math.max(0, Math.min(this.pos, this.items.length - 1));
        return true;
      } catch (e) {
        if (viewId !== this._viewId || request !== this._listRequest) return false;
        clsApp.notify('加载文件列表失败：' + (e.detail || e.status));
        if (!this._loading) return false;
        this.items = [];
        this.total = 0;
        this.page = 0;
        this.pos = 0;
        return true;
      } finally {
        if (viewId === this._viewId && request === this._listRequest) this._loading = false;
      }
    },

    /* ---------- 多张模式：固定 6×2 网格窗口，队头未标注 ---------- */
    loadGrid: async function () {
      var viewId = this._viewId;
      var request = ++this._gridRequest;
      var taskId = this.task.taskId;
      var data;
      try {
        data = await clsApi.listItems(taskId, 0, GRID_SIZE, 'unlabeled');
      } catch (e) {
        if (viewId === this._viewId && request === this._gridRequest) {
          clsApp.notify('加载网格失败：' + (e.detail || e.status));
        }
        return false;
      }
      if (viewId !== this._viewId || request !== this._gridRequest) return false;
      var pending = clsApi.pendingItems();
      this._gridItems = data.items.filter(function (it) {
        return !Object.prototype.hasOwnProperty.call(pending, taskId + '/' + it.itemId);
      });
      this._gridTotal = data.total;
      var visible = new Set(this._gridItems.map(function (it) { return it.itemId; }));
      var selection = this._sel;
      Object.keys(selection).forEach(function (id) {
        if (!visible.has(Number(id))) delete selection[id];
      });
      if (!visible.has(this._anchor)) this._anchor = null;
      return true;
    },

    /* ---------- 渲染 ---------- */
    render: function () {
      if (!this.task || this._loading || this._searchComposing) return;
      var root = document.getElementById('viewRoot');
      if (this.task.status !== 'ready') {
        root.innerHTML = this._renderNotReady();
        this._bindNotReady(root);
        return;
      }
      var listKey = JSON.stringify([this.task.taskId, this.filter, this.page, this._search]);
      var previousList = root.querySelector('.side-list');
      var scrollTop = previousList && previousList.dataset.listKey === listKey ? previousList.scrollTop : 0;
      var focused = document.activeElement;
      var selection = focused && focused.id === 'sideSearch'
        ? [focused.selectionStart, focused.selectionEnd, focused.selectionDirection] : null;
      root.innerHTML = this._renderReady();
      this._bindReady(root);
      var sideList = root.querySelector('.side-list');
      sideList.dataset.listKey = listKey;
      sideList.scrollTop = scrollTop;
      if (selection) {
        var search = root.querySelector('#sideSearch');
        search.focus({ preventScroll: true });
        search.setSelectionRange(selection[0], selection[1], selection[2]);
      }
    },

    _renderNotReady: function () {
      var t = this.task;
      var statusText = { extracting: '解压中…', scanning: '扫描中…', error: '错误' }[t.status] || t.status;
      return '<section class="label-page"><div class="notready">' +
        '<div class="notready-bar">' +
        '<button class="btn" data-act="back">← 返回任务列表</button>' +
        '<span class="notready-name">' + esc(t.name) + '</span>' +
        clsApp.exportMenuHtml(t.taskId, false) +
        '</div>' +
        (t.status === 'error'
          ? '<p class="task-error">' + esc(t.errorMsg || '处理失败') + '</p>'
          : '<p class="status-pending"><span class="spinner"></span> ' + statusText + '（处理完成后自动刷新）</p>') +
        '</div></section>';
    },

    _bindNotReady: function (root) {
      root.querySelector('[data-act="back"]').addEventListener('click', function () {
        location.hash = '#/tasks';
      });
      // 导出菜单未就绪态由 clsApp.exportMenuHtml 渲染为原生 disabled 按钮（无监听，R3 P2-3 语义不变）
    },

    _catBarHtml: function (cur) {
      // 类别按钮：热键角标前 10（0-9，第 1 类=0）、>10 仅点击；计数徽标；单张当前项已选高亮
      var t = this.task;
      var counts = this._labelCounts;
      var btns = t.labels.map(function (lb, i) {
        var badge = i < 10 ? '<span class="key-badge">' + i + '</span>' : '';
        var cnt = counts.length ? '<span class="cnt-badge">' + (counts[i] || 0) + '</span>' : '';
        var sel = cur && cur.label === lb ? ' class="btn-cat sel"' : ' class="btn-cat"';
        return '<button' + sel + ' data-label="' + esc(lb) + '">' + badge + esc(lb) + cnt + '</button>';
      }).join('');
      return '<div class="cat-bar">' + btns +
        '<button class="btn-cat btn-clear" data-label="">清除 <span class="key-badge">R</span></button></div>';
    },

    _progressHtml: function () {
      var t = this.task;
      var progressPct = t.itemCount ? Math.round(t.progress * 100) : 0;
      return '<div class="progress-wrap"><div class="progress-bar"><div class="progress-fill" style="width:' + progressPct + '%"></div></div>' +
        '<span class="progress-text">已标注 ' + t.labeledCount + ' / ' + t.itemCount + '（' + progressPct + '%）</span></div>';
    },

    _renderGridMain: function () {
      if (!this._gridItems.length) {
        var message = this._gridTotal ? '等待标注保存后补入新图片' : '已全部标注';
        return '<div class="empty-filter">' +
          '<p class="empty-text">' + message + '</p>' +
          '<button class="btn" data-act="showall">切回单张查看全部</button></div>';
      }
      var self = this;
      var cells = this._gridItems.map(function (it) {
        var sel = self._sel[it.itemId] ? ' grid-sel' : '';
        return '<div class="grid-cell' + sel + '" data-item-id="' + it.itemId + '" title="' + esc(it.relPath) + '">' +
          '<img src="' + clsApi.contentUrl(it.itemId) + '" alt="' + esc(it.relPath) + '" draggable="false" loading="lazy">' +
          '</div>';
      }).join('');
      return '<div id="gridStage" class="grid-stage">' +
        cells + '<div id="rubberBand" class="rubber-band" hidden></div></div>';
    },

    _renderReady: function () {
      var t = this.task;
      var grid = this._mode === 'grid';
      var cur = grid ? null : this.currentItem();

      var modeBtns =
        '<button class="fbtn' + (grid ? '' : ' on') + '" data-mode="single">单张</button>' +
        '<button class="fbtn' + (grid ? ' on' : '') + '" data-mode="grid">多张</button>';

      // 主区
      var mainHtml;
      if (grid) {
        mainHtml = this._renderGridMain() + this._catBarHtml(null) + this._progressHtml() +
          (this.hint ? '<div class="hint">' + esc(this.hint) + '</div>' : '');
      } else if (!this.items.length) {
        var emptyText = this._search ? '未找到匹配的文件' : '暂无数据项';
        if (!this._search && this.filter === 'unlabeled') emptyText = '已全部标注';
        if (!this._search && this.filter === 'labeled') emptyText = '暂无已标注项';
        mainHtml = '<div class="empty-filter">' +
          '<p class="empty-text">' + emptyText + '</p>' +
          '<button class="btn" data-act="showall">查看全部</button></div>';
      } else if (!cur) {
        mainHtml = '<div class="empty-filter"><p class="empty-text">暂无数据项</p></div>';
      } else {
        mainHtml =
          '<div class="img-stage">' +
          '<img id="mainImg" src="' + clsApi.contentUrl(cur.itemId) + '" alt="' + esc(cur.relPath) + '" draggable="false">' +
          '<div id="imgFallback" class="img-fallback" hidden>图片加载失败（文件可能损坏或已被移动）</div>' +
          '</div>' +
          '<div class="img-path" title="' + esc(cur.relPath) + '">' + esc(cur.relPath) + '</div>' +
          this._catBarHtml(cur) + this._progressHtml() +
          (this.hint ? '<div class="hint">' + esc(this.hint) + '</div>' : '');
      }

      // 工具栏中段：两模式共通（过滤/跳转/序号均描述侧栏列表）；多张追加未标注/已选信息
      var toolbarMid =
        '<div class="mode-btns">' + modeBtns + '</div>' +
        '<div class="filter-btns">' +
        '<button class="fbtn' + (this.filter === 'all' ? ' on' : '') + '" data-filter="all">全部</button>' +
        '<button class="fbtn' + (this.filter === 'unlabeled' ? ' on' : '') + '" data-filter="unlabeled">未标注</button>' +
        '<button class="fbtn' + (this.filter === 'labeled' ? ' on' : '') + '" data-filter="labeled">已标注</button>' +
        '</div>' +
        '<span class="jump-box">跳转 <input id="jumpInput" type="number" min="1" max="' + this.total + '" placeholder="' +
        (this.items.length ? (this.pos + 1) : '') + '"> <button class="btn btn-mini" data-act="jump">定位</button>' +
        ' <span class="muted">（当前过滤列表内序号，共 ' + this.total + '）</span></span>' +
        '<span class="pos-text">' + (this.items.length ? (this.pos + 1) : 0) + ' / ' + this.total + '</span>' +
        (grid ? '<span class="grid-info">未标注 ' + this._gridTotal + ' · 已选 ' + Object.keys(this._sel).length + '</span>' : '');

      // 侧栏（两模式常显：数据=当前 filter/搜索的分页列表，与网格未标注窗口两套并存）
      var pending = clsApi.pendingItems();
      var tid = t.taskId;
      var sideRows = this.items.map(function (it, i) {
        var rec = pending[tid + '/' + it.itemId];
        var stateHtml = '<span class="dot-unlabeled" aria-label="未标注"></span>';
        if (rec || it.label != null) {
          var labelClass = rec ? 'st-unsaved' : 'st-labeled';
          var label = rec ? rec.label : it.label;
          var labelText = esc(label == null ? '清除中' : label);
          stateHtml = '<span class="side-lbl ' + labelClass + '" title="' + labelText + '">' + labelText + '</span>';
        }
        var active = i === clsLabelView.pos ? ' side-active' : '';
        return '<li class="side-item' + active + '" data-idx="' + i + '">' +
          stateHtml +
          '<span class="side-path" title="' + esc(it.relPath) + '">' + esc(it.relPath) + '</span></li>';
      }).join('');
      var totalPages = Math.max(1, Math.ceil(this.total / PAGE_SIZE));
      var sideHtml = '<aside class="label-sidebar">' +
        '<div class="side-search"><input id="sideSearch" type="text" maxlength="200" aria-label="按文件名搜索" placeholder="按文件名搜索" value="' + esc(this._searchDraft) + '"></div>' +
        '<div class="side-pager">' +
        '<button class="btn btn-mini" data-act="prevpage" ' + (this.page <= 0 ? 'disabled' : '') + '>上一页</button>' +
        '<span class="page-no">' + (this.page + 1) + ' / ' + totalPages + '</span>' +
        '<button class="btn btn-mini" data-act="nextpage" ' + (this.page >= totalPages - 1 ? 'disabled' : '') + '>下一页</button>' +
        '</div>' +
        '<ul class="side-list">' + (sideRows || '<li class="side-item muted">' + (this._search ? '未找到匹配的文件' : '暂无文件') + '</li>') + '</ul>' +
        '</aside>';

      return '<section class="label-page label-ready">' +
        '<div class="label-toolbar">' +
        '<button class="btn btn-mini" data-act="back">← 返回</button>' +
        '<span class="lbl-task-name">' + esc(t.name) + '</span>' +
        toolbarMid +
        clsApp.exportMenuHtml(t.taskId, true) +
        '</div>' +
        '<div class="label-body">' +
        '<div class="label-main">' + mainHtml + '</div>' +
        sideHtml +
        '</div></section>';
    },

    _bindReady: function (root) {
      var self = this;
      root.querySelectorAll('[data-act="back"]').forEach(function (b) {
        b.addEventListener('click', function () { location.hash = '#/tasks'; });
      });
      // 导出菜单：渲染自 clsApp.exportMenuHtml，链接/收起交互由 app.js 统一委托（旧 data-act=export 监听随按钮替换移除）
      // 模式开关（单张/多张）
      root.querySelectorAll('[data-mode]').forEach(function (b) {
        b.addEventListener('click', function () { self.setMode(b.getAttribute('data-mode')); });
      });
      // 类别按钮：单张=标注当前项（清除=R 语义）；多张=批量标注选中项（清除=清空选择）
      root.querySelectorAll('.btn-cat').forEach(function (b) {
        b.addEventListener('click', function () {
          var lb = b.getAttribute('data-label');
          if (self._mode === 'grid') {
            if (lb === '') self.clearCurrent();
            else self.gridLabel(lb);
          } else {
            self.labelCurrent(lb === '' ? null : lb);
          }
        });
      });
      var showall = root.querySelector('[data-act="showall"]');
      if (showall) {
        showall.addEventListener('click', function () {
          if (self._mode === 'grid') self.setMode('single');
          self.setFilter('all', true);
        });
      }
      root.querySelectorAll('.fbtn[data-filter]').forEach(function (b) {
        b.addEventListener('click', function () { self.setFilter(b.getAttribute('data-filter')); });
      });
      root.querySelector('[data-act="jump"]').addEventListener('click', function () { self.doJump(); });
      root.querySelector('#jumpInput').addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.isComposing) self.doJump();
      });
      root.querySelector('[data-act="prevpage"]').addEventListener('click', function () { self.gotoPage(self.page - 1); });
      root.querySelector('[data-act="nextpage"]').addEventListener('click', function () { self.gotoPage(self.page + 1); });
      var searchInput = root.querySelector('#sideSearch');
      function queueSearch() {
        self._searchDraft = searchInput.value;
        clearTimeout(self._searchTimer);
        self._searchTimer = setTimeout(function () { self._applySearch(); }, 300);
      }
      searchInput.addEventListener('compositionstart', function () {
        self._searchComposing = true;
        clearTimeout(self._searchTimer);
      });
      searchInput.addEventListener('compositionend', function () {
        self._searchComposing = false;
        queueSearch();
      });
      searchInput.addEventListener('input', function (e) {
        if (!e.isComposing && !self._searchComposing) queueSearch();
      });
      searchInput.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' || e.isComposing || self._searchComposing) return;
        self._searchDraft = searchInput.value;
        self._applySearch();
      });
      root.querySelectorAll('.side-item[data-idx]').forEach(function (li) {
        var idx = Number(li.getAttribute('data-idx'));
        var path = self.items[idx].relPath;
        li.addEventListener('click', function (e) {
          clearTimeout(self._sideClickTimer);
          if (e.detail > 1) return;
          self._sideClickTimer = setTimeout(function () {
            if (!document.body.contains(li) || self._loading) return;
            self.pos = idx;
            self.setHint('');
            if (self._mode === 'grid') self.setMode('single');
            else self.render();
          }, 500);
        });
        li.addEventListener('dblclick', function () {
          clearTimeout(self._sideClickTimer);
          self._copyText(path.split('/').pop());
        });
      });
      if (this._mode === 'grid') this._bindGrid(root);
      else this._bindSingleImage(root);
    },

    _bindSingleImage: function (root) {
      var img = root.querySelector('#mainImg');
      if (!img) return;
      var self = this;
      var itemId = this.currentItem().itemId;
      if (itemId !== this._zoomItemId) this._zoom = null;
      this._zoomItemId = itemId;
      applyZoom(img, this._zoom);
      img.onerror = function () {
        img.hidden = true;
        root.querySelector('#imgFallback').hidden = false;
      };
      root.querySelector('.img-stage').addEventListener('wheel', function (e) {
        self._zoom = zoomImage(img, e, self._zoom, 8);
      }, { passive: false });
      img.addEventListener('dblclick', function () {
        self._zoom = null;
        applyZoom(img, null);
      });
    },

    /* ---------- 多张模式：选择交互（Explorer 语义） ---------- */
    _bindGrid: function (root) {
      var self = this;
      var stage = root.querySelector('#gridStage');
      if (!stage) return;
      var band = stage.querySelector('#rubberBand');
      var startX = 0, startY = 0, moved = false, ctrlKey = false, startCell = null, dragBase = {};

      function cells() {
        return Array.prototype.slice.call(stage.querySelectorAll('.grid-cell'));
      }
      function bandRect(x0, y0, x1, y1) {
        return { left: Math.min(x0, x1), top: Math.min(y0, y1), right: Math.max(x0, x1), bottom: Math.max(y0, y1) };
      }
      function hits(b) {
        return cells().filter(function (c) {
          var r = c.getBoundingClientRect();
          return !(r.left > b.right || r.right < b.left || r.top > b.bottom || r.bottom < b.top);
        });
      }
      function applyPreview(prevIds) {
        cells().forEach(function (c) {
          c.classList.toggle('grid-pre', !!prevIds[Number(c.getAttribute('data-item-id'))]);
        });
      }

      var onMove = function (e) {
        if (document.getElementById('gridStage') !== stage) { cleanup(); return; }
        if (!(e.buttons & 1)) return;
        var dx = e.clientX - startX, dy = e.clientY - startY;
        if (!moved && Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
        moved = true;
        var b = bandRect(startX, startY, e.clientX, e.clientY);
        if (band) {
          var st = stage.getBoundingClientRect();
          band.hidden = false;
          band.style.left = (b.left - st.left) + 'px';
          band.style.top = (b.top - st.top) + 'px';
          band.style.width = (b.right - b.left) + 'px';
          band.style.height = (b.bottom - b.top) + 'px';
        }
        var prevIds = {};
        hits(b).forEach(function (c) { prevIds[Number(c.getAttribute('data-item-id'))] = true; });
        if (ctrlKey) Object.keys(dragBase).forEach(function (k) { prevIds[k] = true; });
        applyPreview(prevIds);
      };
      var onUp = function (e) {
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
        if (document.getElementById('gridStage') !== stage) return;
        if (band) band.hidden = true;
        if (!moved) {
          // 点击语义：无修饰=单选重置；Ctrl=翻转；Shift=锚点一维区间连选（含端点）
          var cell = startCell;
          if (!cell) {
            self._sel = {};
            self._anchor = null;
          } else {
            var id = Number(cell.getAttribute('data-item-id'));
            if (e.shiftKey && self._anchor != null) {
              var range = self._rangeSel(self._anchor, id);
              if (range) self._sel = range;
              self._anchor = id; // Shift+点击更新锚点
            } else if (e.ctrlKey) {
              if (self._sel[id]) delete self._sel[id];
              else self._sel[id] = true; // Ctrl 不改锚点
            } else {
              self._sel = {};
              self._sel[id] = true;
              self._anchor = id; // 无修饰点击更新锚点
            }
          }
        } else {
          // 框选语义：Ctrl=并入；Shift+拖动忽略（等同普通拖动）；拖动不改锚点
          var b = bandRect(startX, startY, e.clientX, e.clientY);
          var next = ctrlKey ? Object.assign({}, dragBase) : {};
          hits(b).forEach(function (c) { next[Number(c.getAttribute('data-item-id'))] = true; });
          self._sel = next;
        }
        self._applySelToDom();
      };
      var cleanup = function () {
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };

      stage.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        e.preventDefault(); // 阻止原生拖图/文本选择
        startX = e.clientX;
        startY = e.clientY;
        moved = false;
        ctrlKey = e.ctrlKey;
        startCell = e.target.closest ? e.target.closest('.grid-cell') : null;
        dragBase = Object.assign({}, self._sel);
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
      });
      var zoomByImage = new WeakMap();
      stage.addEventListener('wheel', function (e) {
        var cell = e.target.closest('.grid-cell');
        if (!cell) return;
        var img = cell.querySelector('img');
        zoomByImage.set(img, zoomImage(img, e, zoomByImage.get(img), 4));
      }, { passive: false });
      stage.addEventListener('dblclick', function (e) {
        var cell = e.target.closest('.grid-cell');
        if (!cell) return;
        var img = cell.querySelector('img');
        zoomByImage.delete(img);
        applyZoom(img, null);
      });
    },

    _rangeSel: function (a, b) {
      // 锚点→当前格的一维序号区间（含端点）
      var ia = -1, ib = -1;
      this._gridItems.forEach(function (it, i) {
        if (it.itemId === a) ia = i;
        if (it.itemId === b) ib = i;
      });
      if (ia < 0 || ib < 0) return null;
      var out = {};
      var lo = Math.min(ia, ib), hi = Math.max(ia, ib);
      for (var i = lo; i <= hi; i++) out[this._gridItems[i].itemId] = true;
      return out;
    },

    _applySelToDom: function () {
      // 仅更新类名与计数文本，避免整页重渲（防图片闪烁）
      var root = document.getElementById('viewRoot');
      if (!root) return;
      var stage = root.querySelector('#gridStage');
      if (!stage) return;
      var self = this;
      stage.querySelectorAll('.grid-cell').forEach(function (c) {
        c.classList.toggle('grid-sel', !!self._sel[Number(c.getAttribute('data-item-id'))]);
        c.classList.remove('grid-pre');
      });
      var info = root.querySelector('.grid-info');
      if (info) info.textContent = '未标注 ' + this._gridTotal + ' · 已选 ' + Object.keys(this._sel).length;
    },

    setMode: async function (mode) {
      if (mode === this._mode || !this.task || this.task.status !== 'ready') return;
      var viewId = this._viewId;
      this._mode = mode;
      this._sel = {};
      this._anchor = null;
      this.setHint('');
      localStorage.setItem(LS_LABEL_MODE, mode);
      if (mode === 'grid') await this.loadGrid();
      if (viewId === this._viewId && mode === this._mode) this.render();
    },

    /* ---------- 交互 ---------- */
    setFilter: async function (f, resetSearch) {
      if (f === this.filter && !resetSearch) return;
      if (resetSearch) {
        clearTimeout(this._searchTimer);
        this._search = '';
        this._searchDraft = '';
      }
      this.filter = f;
      this.page = 0;
      this.pos = 0;
      this.setHint('');
      if (await this.loadItems()) this.render();
    },

    gotoPage: async function (p) {
      var totalPages = Math.max(1, Math.ceil(this.total / PAGE_SIZE));
      if (this._loading || p < 0 || p >= totalPages) return;
      this.page = p;
      this.pos = 0;
      if (await this.loadItems()) this.render();
    },

    doJump: async function () {
      var input = document.getElementById('jumpInput');
      if (!input || this._loading) return;
      var n = Number(input.value);
      if (!Number.isInteger(n) || n < 1 || n > this.total) {
        clsApp.notify('请输入 1 到 ' + this.total + ' 之间的有效序号');
        return;
      }
      this.page = Math.floor((n - 1) / PAGE_SIZE);
      this.pos = (n - 1) % PAGE_SIZE;
      this.setHint('');
      if (await this.loadItems()) this.render();
    },

    _applySearch: async function () {
      clearTimeout(this._searchTimer);
      this._searchTimer = null;
      if (!this.task || this._searchComposing) return;
      this._search = this._searchDraft;
      this.page = 0;
      this.pos = 0;
      this.setHint('');
      if (await this.loadItems()) this.render();
    },

    /* 双击复制文件名（basename，带后缀）：clipboard 存在才走 Promise（R1 P2-2，LAN http 下可能为 undefined），否则/失败降级临时 textarea+execCommand */
    _copyText: function (name) {
      var ok = function () { clsApp.notify('已复制 ' + name); };
      var fallback = function () {
        var focused = document.activeElement;
        var input = document.createElement('textarea');
        input.value = name;
        input.style.cssText = 'position:fixed;left:0;top:0;opacity:0';
        document.body.appendChild(input);
        var copied = false;
        try {
          input.select();
          copied = document.execCommand('copy');
        } catch (e) {
          copied = false;
        } finally {
          input.remove();
          if (focused && focused.isConnected) focused.focus({ preventScroll: true });
        }
        if (copied) ok();
        else clsApp.notify('复制失败：' + name);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(name).then(ok, fallback);
      } else {
        fallback();
      }
    },

    hotkey: function (labelIndex) {
      var t = this.task;
      if (!t || t.status !== 'ready') return;
      if (labelIndex < 0 || labelIndex >= t.labels.length) return;
      if (this._mode === 'grid') this.gridLabel(t.labels[labelIndex]);
      else this.labelCurrent(t.labels[labelIndex]);
    },

    clearCurrent: function () {
      var t = this.task;
      if (!t || t.status !== 'ready') return;
      if (this._mode === 'grid') {
        // 多张模式：R=清空选择（网格仅展示未标注项，清除标注无意义）
        this._sel = {};
        this._applySelToDom();
        return;
      }
      this.labelCurrent(null);
    },

    onEscape: function () {
      if (this._mode === 'grid' && this.task && this.task.status === 'ready') {
        this._sel = {};
        this._applySelToDom();
      }
    },

    /* 多张批量标注：每张走既有单条接口（乐观+队列+重试），标完重拉窗口（pending 项不渲染） */
    gridLabel: function (label) {
      var t = this.task;
      if (!t || t.status !== 'ready') return;
      var pending = clsApi.pendingItems();
      var selected = this._sel;
      var ids = this._gridItems.filter(function (item) {
        return selected[item.itemId] && !pending[t.taskId + '/' + item.itemId];
      }).map(function (item) { return item.itemId; });
      if (!ids.length) {
        this.setHint('请先选择图片（点击 / 拖动框选 / Shift 连选 / Ctrl 增减）');
        this.render();
        return;
      }
      var idx = t.labels.indexOf(label);
      ids.forEach(function (id) { clsApi.annotate(t.taskId, id, label); });
      if (idx >= 0 && this._labelCounts.length) {
        this._labelCounts[idx] = (this._labelCounts[idx] || 0) + ids.length;
      }
      var annotated = new Set(ids);
      this._gridItems = this._gridItems.filter(function (item) { return !annotated.has(item.itemId); });
      this._sel = {};
      this._anchor = null;
      this.setHint('已标注 ' + ids.length + ' 张 → ' + label);
      this.render();
      this.loadGrid().then(this._renderLoaded.bind(this));
    },

    _renderLoaded: function (loaded) {
      if (loaded) this.render();
    },

    onSaveState: function (snap) {
      var wasSaving = this._saving;
      this._saving = !!snap.saving;
      if (!wasSaving || this._saving || !this.task || this.task.status !== 'ready') return;
      this._refreshTask();
      if (this._mode === 'grid') this.loadGrid().then(this._renderLoaded.bind(this));
      this.loadItems(true).then(this._renderLoaded.bind(this));
    },

    _refreshTask: async function () {
      var viewId = this._viewId;
      var request = ++this._taskRequest;
      var task;
      try {
        task = await clsApi.getTask(this.task.taskId);
      } catch (e) {
        return;
      }
      if (viewId !== this._viewId || request !== this._taskRequest || this._saving) return;
      this.task = task;
      if (Array.isArray(task.labelCounts)) this._labelCounts = task.labelCounts.slice();
      this.render();
    },

    /* 数字键/点击 → 乐观标注 → 立即自动前进（不等待保存确认，速度优先） */
    labelCurrent: function (label) {
      if (this._loading) return;
      var cur = this.currentItem();
      if (!cur) return;
      this._listRequest++; // 保留本地标注，不接受标注前发出的列表响应。
      var t = this.task;
      // 乐观计数（清=旧类-1；标=新类+1；数组仅后端提供 labelCounts 时存在）
      if (this._labelCounts.length) {
        if (cur.label != null) {
          var oi = t.labels.indexOf(cur.label);
          if (oi >= 0) this._labelCounts[oi] = Math.max(0, (this._labelCounts[oi] || 0) - 1);
        }
        if (label != null) {
          var ni = t.labels.indexOf(label);
          if (ni >= 0) this._labelCounts[ni] = (this._labelCounts[ni] || 0) + 1;
        }
      }
      // 乐观更新（未确认态；失败时三态可追踪，回看/侧栏/一键重试兜底）
      cur.label = label;
      clsApi.annotate(this.task.taskId, cur.itemId, label);
      this.setHint('');
      if (label === null) {
        this.setHint('已清除标注（停留当前项）');
        this.render();
      } else if (this.filter === 'unlabeled') {
        this.items.splice(this.pos, 1);
        this.total = Math.max(0, this.total - 1);
        this.pos = Math.max(0, Math.min(this.pos, this.items.length - 1));
        this.render();
      } else {
        this.advance(1);
      }
    },

    /* 上一张、下一张与自动前进共用当前列表。 */
    advance: async function (dir) {
      var next = this.pos + dir;
      if (next >= this.items.length) {
        if ((this.page + 1) * PAGE_SIZE < this.total) {
          this.page++;
          this.pos = 0;
          this.setHint('');
          if (await this.loadItems()) this.render();
        } else {
          this.setHint('已是最后一张（当前过滤列表共 ' + this.total + '）');
          this.render();
        }
        return;
      }
      if (next < 0) {
        if (this.page > 0) {
          this.page--;
          this.pos = PAGE_SIZE - 1;
          this.setHint('');
          if (await this.loadItems()) this.render();
        }
        return;
      }
      this.pos = next;
      this.setHint('');
      this.render();
    },

    navigate: function (dir) {
      if (!this.task || this.task.status !== 'ready' || this._loading || this._mode === 'grid') return;
      this.advance(dir);
    }
  };

  window.clsLabelView = clsLabelView;
})();
