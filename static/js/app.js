/* Author: wilbur / Version: 1.6 / Date: 2026-11-24 / Description: Hash 路由、标注快捷键、保存反馈与共享导出菜单。本次补齐菜单收起后的键盘焦点恢复。 */
(function () {
  'use strict';

  var LS_NAME_GUIDE = 'clsNameGuideShown';

  function fmtTime(d) {
    function p(n) { return n < 10 ? '0' + n : String(n); }
    return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var clsApp = {
    currentView: 'tasks',
    currentTaskId: null,
    _started: false,

    start: async function () {
      if (this._started) return;
      this._started = true;
      // 身份闸门
      await clsApi.init();
      // 补传待传队列（入队先于视图渲染，R2 新-3a）
      clsApi.flushPending();
      // 顶栏
      this.renderAnnotatorName();
      this.renderSaveIndicator({ saving: false, lastSavedAt: null, retryCount: 0 });
      var self = this;
      clsApi.onSaveStateChange(function (snap) {
        self.renderSaveIndicator(snap);
        if (window.clsLabelView) clsLabelView.onSaveState(snap); // 转发标注页：保存队列排空后重拉/对齐
      });
      this.attachKeyboard();
      // 顶栏「使用说明」按钮（视图切换只重渲染 viewRoot，绑定一次即可）
      var helpBtn = document.getElementById('helpBtn');
      if (helpBtn) helpBtn.addEventListener('click', function () { clsHelpView.show(); });
      // 首访引导设置显示名（可跳过；默认名已在注册时入库）
      if (!localStorage.getItem(LS_NAME_GUIDE)) this.showNameGuide();
      // 路由
      window.addEventListener('hashchange', function () { self.route(); });
      this.route();
    },

    route: function () {
      var hash = location.hash || '#/tasks';
      var m = hash.match(/^#\/task\/([A-Za-z0-9_-]+)$/);
      if (m) {
        this.currentView = 'label';
        this.currentTaskId = m[1];
        clsLabelView.mount(m[1]);
      } else {
        if (this.currentView === 'label') clsLabelView.unmount();
        this.currentView = 'tasks';
        this.currentTaskId = null;
        clsTaskView.mount();
      }
    },

    /* 顶栏：标注人名（可改） */
    renderAnnotatorName: function () {
      var slot = document.getElementById('annotatorSlot');
      if (!slot) return;
      var self = this;
      slot.innerHTML = '<span class="annotator" title="点击修改显示名">' +
        esc(clsApi.identity.name) + '</span>';
      slot.querySelector('.annotator').addEventListener('click', function () {
        var name = prompt('设置显示名（≤32 字符）：', clsApi.identity.name);
        if (name === null) return;
        clsApi.rename(name).catch(function (e) {
          self.notify('修改显示名失败：' + (e.detail || e.status));
        });
      });
    },

    /* 顶栏：保存指示（N 条待重试与过滤无关，R3 P2-2） */
    renderSaveIndicator: function (snap) {
      var slot = document.getElementById('saveSlot');
      if (!slot) return;
      if (snap.saving) {
        slot.innerHTML = '<span class="save-saving">保存中…</span>';
      } else if (snap.retryCount > 0) {
        slot.innerHTML = '<span class="save-failed">' + snap.retryCount + ' 条待重试</span>' +
          '<button id="btnRetryAll" class="btn-mini">一键重试</button>';
        slot.querySelector('#btnRetryAll').addEventListener('click', function () {
          clsApi.retryAll();
        });
      } else if (snap.lastSavedAt) {
        slot.innerHTML = '<span class="save-ok">已保存 ' + fmtTime(snap.lastSavedAt) + '</span>';
      } else {
        slot.innerHTML = '';
      }
    },

    /* 共享导出菜单（任务卡 + 标注页工具栏；渲染为 HTML 字符串，交互由下方模块级委托统一处理）。
       details/summary 原生键盘可达（Tab 聚焦/Enter 展开）；未就绪渲染原生 disabled 按钮；
       链接直走浏览器下载（cookie 身份），ZIP 链接点击时先提示打包耗时 */
    exportMenuHtml: function (taskId, ready) {
      if (!ready) {
        return '<button class="btn-mini" disabled title="任务未就绪，不可导出">导出</button>';
      }
      return '<details class="export-menu">' +
        '<summary class="btn-mini export-summary">导出<span class="export-caret">▾</span></summary>' +
        '<div class="export-pop">' +
        '<a href="' + clsApi.exportUrl(taskId) + '" data-format="csv">CSV · 标注表</a>' +
        '<a href="' + clsApi.exportUrl(taskId, 'zip') + '" data-format="zip">ZIP · 图片与标注表</a>' +
        '</div></details>';
    },

    /* 键盘分发：输入框聚焦不拦截；0-9/R·a·d/←/→/Esc 仅在标注页生效 */
    attachKeyboard: function () {
      window.addEventListener('keydown', function (e) {
        if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
        if (window.clsHelpView && clsHelpView.isOpen()) return;
        if (clsApp.currentView !== 'label') return;
        var el = document.activeElement;
        if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ||
                   el.tagName === 'SELECT' || el.isContentEditable)) return;
        if (e.key >= '0' && e.key <= '9') {
          clsLabelView.hotkey(Number(e.key)); // 类别从 0 编号：0=第 1 类 … 9=第 10 类
          e.preventDefault();
        } else if (e.key === 'r' || e.key === 'R') {
          clsLabelView.clearCurrent(); // 单张=清除标注（停留）；多张=清空选择
          e.preventDefault();
        } else if (e.key === 'a' || e.key === 'A') {
          clsLabelView.navigate(-1); // 上一张（仅单张，等价 ←）
          e.preventDefault();
        } else if (e.key === 'd' || e.key === 'D') {
          clsLabelView.navigate(1); // 下一张（仅单张，等价 →）
          e.preventDefault();
        } else if (e.key === 'Escape') {
          clsLabelView.onEscape();
        } else if (e.key === 'ArrowLeft') {
          clsLabelView.navigate(-1);
          e.preventDefault();
        } else if (e.key === 'ArrowRight') {
          clsLabelView.navigate(1);
          e.preventDefault();
        }
      });
    },

    /* 首访命名引导（可跳过） */
    showNameGuide: function () {
      var overlay = document.createElement('div');
      overlay.className = 'guide-overlay';
      overlay.innerHTML =
        '<div class="guide-box">' +
        '<h3>欢迎使用 clsLabelTool</h3>' +
        '<p>当前显示名为「' + esc(clsApi.identity.name) + '」，可立即设置（导出 CSV 的标注人列将使用此名称）。</p>' +
        '<input id="guideNameInput" type="text" maxlength="32" placeholder="输入显示名">' +
        '<div class="guide-btns">' +
        '<button id="guideOk" class="btn">设置</button>' +
        '<button id="guideHelp" class="btn btn-ghost">查看使用说明</button>' +
        '<button id="guideSkip" class="btn btn-ghost">跳过</button>' +
        '</div></div>';
      document.body.appendChild(overlay);
      var self = this;
      var finish = function () {
        localStorage.setItem(LS_NAME_GUIDE, '1');
        overlay.remove();
        self.renderAnnotatorName();
      };
      overlay.querySelector('#guideSkip').addEventListener('click', finish);
      overlay.querySelector('#guideHelp').addEventListener('click', function () {
        finish();
        clsHelpView.show();
      });
      overlay.querySelector('#guideOk').addEventListener('click', function () {
        var v = overlay.querySelector('#guideNameInput').value;
        clsApi.rename(v).then(finish).catch(function (e) {
          self.notify('设置显示名失败：' + (e.detail || e.status));
        });
      });
    },

    /* 轻提示（自动消失） */
    notify: function (msg) {
      var el = document.getElementById('toast');
      if (!el) {
        el = document.createElement('div');
        el.id = 'toast';
        el.className = 'toast';
        document.body.appendChild(el);
      }
      el.textContent = msg;
      el.hidden = false;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(function () { el.hidden = true; }, 4000);
    }
  };

  function closeExportMenu(menu) {
    var hadFocus = menu.contains(document.activeElement);
    menu.open = false;
    if (hadFocus) menu.querySelector('summary').focus();
  }

  document.addEventListener('click', function (e) {
    var target = e.target;
    var link = target && target.closest ? target.closest('.export-pop a') : null;
    var clickedMenu = target && target.closest ? target.closest('.export-menu') : null;
    document.querySelectorAll('.export-menu[open]').forEach(function (menu) {
      if (link || menu !== clickedMenu) closeExportMenu(menu);
    });
    if (link && link.getAttribute('data-format') === 'zip') {
      clsApp.notify('正在打包 ZIP，完成后浏览器会开始下载。');
    }
  });

  window.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || e.defaultPrevented) return;
    var openMenus = document.querySelectorAll('.export-menu[open]');
    if (!openMenus.length) return;
    e.preventDefault();
    openMenus.forEach(closeExportMenu);
  });

  window.clsApp = clsApp;
  window.clsEsc = esc;
  window.clsNotify = function (msg) { clsApp.notify(msg); };
})();
