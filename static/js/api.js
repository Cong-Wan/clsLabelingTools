/* Author: wilbur / Version: 1.3 / Date: 2026-11-24 / Description: API 层（身份闸门+localStorage 对齐+请求助手+每 itemId 串行队列+待传 map+补传先行+最新意图覆盖+4xx 终态丢弃+自动重试 1 次+一键重试+保存状态订阅）；v1.1 修复 listItems URL 缺失 /items 段（误请求任务详情接口导致标注页空白/卡加载）；v1.2 listItems 加第 5 参数 q 搜索词透传（非空时 URL 追加 &q=encodeURIComponent）；v1.3 exportUrl 加第 2 参数 format（'zip' 时追加 ?format=zip，其余/缺省维持旧 CSV URL，两处导出菜单共用此唯一链接出口） */
(function () {
  'use strict';

  var LS_CLIENT = 'clsClientId';
  var LS_PENDING = 'clsPendingResend';
  var RETRY_DELAY_MS = 1000;

  var clsApi = {
    identity: null,
    _initPromise: null,
    _itemChains: {},
    _state: { savingCount: 0, lastSavedAt: null, failed: {} },
    _listeners: [],

    /* ---------- 身份闸门 ---------- */
    init: function () {
      if (!this._initPromise) {
        this._initPromise = this._doInit();
      }
      return this._initPromise;
    },

    _doInit: async function () {
      var stored = localStorage.getItem(LS_CLIENT);
      if (stored) {
        // 回访：带存储身份验证（同步显示名）
        var data = await this.request('GET', '/api/client', null, stored);
        this.identity = { clientId: stored, name: data.name };
        return this.identity;
      }
      // 首访：注册（服务端生成 + Set-Cookie + 响应体）
      var fresh = await this.request('GET', '/api/client', null, null);
      var freshId = fresh.clientId;
      // set-if-absent：仅当无双标签先写入者
      if (!localStorage.getItem(LS_CLIENT)) {
        localStorage.setItem(LS_CLIENT, freshId);
      }
      // 复读对齐（R2 新-9：双标签同时首访取先写入者）
      var aligned = localStorage.getItem(LS_CLIENT);
      if (aligned && aligned !== freshId) {
        var data2 = await this.request('GET', '/api/client', null, aligned);
        this.identity = { clientId: aligned, name: data2.name };
        return this.identity;
      }
      this.identity = { clientId: freshId, name: fresh.name };
      return this.identity;
    },

    rename: async function (name) {
      var data = await this.request('PUT', '/api/client', { name: name });
      this.identity.name = data.name;
      return data;
    },

    /* ---------- 请求助手（init 后所有请求带 X-Client-Id） ---------- */
    request: async function (method, path, body, clientIdOverride) {
      var headers = {};
      var id = clientIdOverride || (this.identity ? this.identity.clientId : null);
      if (id) {
        headers['X-Client-Id'] = id;
      }
      var opts = { method: method, headers: headers };
      if (body !== null && body !== undefined) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
      var resp;
      try {
        resp = await fetch(path, opts);
      } catch (e) {
        throw { status: 0, detail: '网络错误（服务不可达）' };
      }
      if (!resp.ok) {
        var detail = '';
        try { detail = (await resp.json()).detail || ''; } catch (e2) { /* 忽略 */ }
        throw { status: resp.status, detail: detail };
      }
      return resp.json();
    },

    /* ---------- 任务 API ---------- */
    createPathTask: function (payload) { return this.request('POST', '/api/tasks', payload); },
    listTasks: function () { return this.request('GET', '/api/tasks'); },
    getTask: function (taskId) { return this.request('GET', '/api/tasks/' + taskId); },
    deleteTask: function (taskId, force) {
      return this.request('DELETE', '/api/tasks/' + taskId + (force ? '?force=true' : ''));
    },
    listItems: function (taskId, offset, limit, filter, q) {
      q = q || '';
      var url = '/api/tasks/' + taskId +
        '/items?offset=' + offset + '&limit=' + limit + '&filter=' + filter;
      if (q) url += '&q=' + encodeURIComponent(q);
      return this.request('GET', url);
    },
    contentUrl: function (itemId) { return '/api/items/' + itemId + '/content'; },
    exportUrl: function (taskId, format) {
      var url = '/api/tasks/' + taskId + '/export';
      return format === 'zip' ? url + '?format=zip' : url;
    },

    /* 压缩包上传（XHR 进度条；100% 后服务器保存中） */
    uploadArchive: function (file, name, labels, onProgress) {
      var self = this;
      return new Promise(function (resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/tasks/upload');
        xhr.setRequestHeader('X-Client-Id', self.identity.clientId);
        xhr.upload.onprogress = function (e) {
          if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
        };
        xhr.onload = function () {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText));
          } else {
            var detail = '';
            try { detail = JSON.parse(xhr.responseText).detail || ''; } catch (e2) { /* 忽略 */ }
            reject({ status: xhr.status, detail: detail || ('HTTP ' + xhr.status) });
          }
        };
        xhr.onerror = function () { reject({ status: 0, detail: '上传网络错误' }); };
        var fd = new FormData();
        fd.append('file', file);
        fd.append('name', name);
        fd.append('labels', JSON.stringify(labels));
        xhr.send(fd);
      });
    },

    /* ---------- 待传队列（localStorage：taskId→itemId→{label,ts}，null 清除同样入队） ---------- */
    _pending: function () {
      try { return JSON.parse(localStorage.getItem(LS_PENDING) || '{}'); } catch (e) { return {}; }
    },
    _savePending: function (map) { localStorage.setItem(LS_PENDING, JSON.stringify(map)); },
    _removePending: function (key) {
      var map = this._pending();
      if (Object.prototype.hasOwnProperty.call(map, key)) {
        delete map[key];
        this._savePending(map);
      }
    },
    pendingItems: function () { return this._pending(); },

    /* 标注入口：先写待传队列（持久化先于请求）→ 每 itemId 串行队列（严格有序，杜绝过期覆盖） */
    annotate: function (taskId, itemId, label) {
      var key = taskId + '/' + itemId;
      var ts = Date.now();
      var map = this._pending();
      // 同项新点击以最新意图覆盖待传记录（ts 比较）
      if (!Object.prototype.hasOwnProperty.call(map, key) || ts >= map[key].ts) {
        map[key] = { label: label, ts: ts };
        this._savePending(map);
      }
      var self = this;
      this._enqueueItem(itemId, function () {
        return self._doAnnotate(taskId, itemId, label, ts);
      });
    },

    _enqueueItem: function (itemId, fn) {
      var key = String(itemId);
      var chain = this._itemChains[key] || Promise.resolve();
      chain = chain.then(fn).catch(function () { /* 串行链不断裂 */ });
      this._itemChains[key] = chain;
      return chain;
    },

    _doAnnotate: async function (taskId, itemId, label, ts) {
      var key = taskId + '/' + itemId;
      this._state.savingCount++;
      this._notify();
      try {
        await this.request('POST', '/api/tasks/' + taskId + '/annotate', { itemId: itemId, label: label });
        this._removePending(key);
        this._state.lastSavedAt = new Date();
        delete this._state.failed[key];
        this._notify();
      } catch (err) {
        if (err.status === 0 || err.status >= 500) {
          // 自动重试 1 次，仍失败入待重试队列（待传记录保留在 localStorage）
          await new Promise(function (r) { setTimeout(r, RETRY_DELAY_MS); });
          try {
            await this.request('POST', '/api/tasks/' + taskId + '/annotate', { itemId: itemId, label: label });
            this._removePending(key);
            this._state.lastSavedAt = new Date();
            delete this._state.failed[key];
          } catch (err2) {
            this._state.failed[key] = true;
          }
          this._notify();
        } else {
          // 4xx 终态失败（任务已删等）→ 丢弃记录 + 提示（R2 新-3b），不永久滞留
          this._removePending(key);
          delete this._state.failed[key];
          if (window.clsNotify) {
            window.clsNotify('保存失败（任务可能已删除）：' + (err.detail || err.status));
          }
          this._notify();
        }
      } finally {
        this._state.savingCount = Math.max(0, this._state.savingCount - 1);
        this._notify();
      }
    },

    /* 页面加载补传（身份闸门后、视图渲染前调用；4xx 由 _doAnnotate 丢弃+提示） */
    flushPending: function () {
      var map = this._pending();
      var self = this;
      Object.keys(map).forEach(function (key) {
        var idx = key.indexOf('/');
        var taskId = key.slice(0, idx);
        var itemId = Number(key.slice(idx + 1));
        var rec = map[key];
        self._enqueueItem(itemId, function () {
          return self._doAnnotate(taskId, itemId, rec.label, rec.ts);
        });
      });
    },

    /* 一键重试（覆盖全部失败项，与过滤无关，R3 P2-2） */
    retryAll: function () {
      var map = this._pending();
      var self = this;
      var keys = Object.keys(this._state.failed).filter(function (k) {
        return Object.prototype.hasOwnProperty.call(map, k);
      });
      if (!keys.length) return;
      this._state.failed = {};
      this._notify();
      keys.forEach(function (key) {
        var idx = key.indexOf('/');
        var taskId = key.slice(0, idx);
        var itemId = Number(key.slice(idx + 1));
        self._enqueueItem(itemId, function () {
          return self._doAnnotate(taskId, itemId, map[key].label, map[key].ts);
        });
      });
    },

    /* 保存状态订阅（顶栏：保存中…/已保存 HH:MM:SS/N 条待重试） */
    onSaveStateChange: function (cb) { this._listeners.push(cb); },
    _notify: function () {
      var failedCount = Object.keys(this._state.failed).length;
      var snap = {
        saving: this._state.savingCount > 0,
        lastSavedAt: this._state.lastSavedAt,
        retryCount: failedCount
      };
      this._listeners.forEach(function (cb) {
        try { cb(snap); } catch (e) { /* 忽略 */ }
      });
    }
  };

  window.clsApi = clsApi;
})();
