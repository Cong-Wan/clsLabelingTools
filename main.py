# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.5 / Date: 2026-11-23 / Description: FastAPI 应用入口：lifespan（建目录→挂载自检→schema→中间态恢复→孤儿清扫→审计线程启动；关停审计 drain+日志 listener 停止）、/api/health、clientApi+taskApi+annotationApi+fileApi+exportService 路由、静态托管（M5 注册导出路由）；v1.5 静态资源加 Cache-Control: no-cache（强制浏览器每次重验证，防 Safari 启发式缓存旧 JS 导致前端修复不生效）

import logging
import os
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import annotationApi
import auditService
import clientApi
import config
import database
import exportService
import fileApi
import logUtil
import taskApi

log = logging.getLogger('clsLabelTool')


def checkMountWritable():
    """挂载点可写自检：写删探针文件，失败则抛异常（启动退出）。"""
    probePath = os.path.join(config.DATA_ROOT, f'.writeProbe-{os.getpid()}')
    try:
        with open(probePath, 'w', encoding='utf-8') as f:
            f.write('probe')
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        raise RuntimeError(f'挂载点不可写（{config.DATA_ROOT}）: {e}')
    finally:
        try:
            os.remove(probePath)
        except OSError:
            pass


def recoverInterruptedTasks():
    """启动恢复：中间态（extracting/scanning）任务置 error（提示删除后重建）。"""
    with database.writeTx() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status='error', errorMsg='服务重启导致中断，请删除后重建' "
            "WHERE status IN ('extracting','scanning')")
        if cur.rowcount:
            log.warning('启动恢复：置 %d 个中间态任务为 error', cur.rowcount)


def sweepOrphanUploads():
    """启动清扫（R4 P1-a）：uploads/ 下「既无对应任务行、又无 .taskCreated 标记」的目录
    = 拷贝窗口崩溃残留 → 删除；已删任务的保留原件有标记 → 不扫。启动时尚未接请求，安全。"""
    if not os.path.isdir(config.UPLOADS_DIR):
        return
    with database.readTx() as conn:
        rows = conn.execute('SELECT sourcePath FROM tasks').fetchall()
    taskSourcePaths = {r['sourcePath'] for r in rows}
    for entry in os.listdir(config.UPLOADS_DIR):
        full = os.path.join(config.UPLOADS_DIR, entry)
        if not os.path.isdir(full):
            continue
        if f'datasets/{entry}' in taskSourcePaths:
            continue  # 有对应任务行
        if os.path.exists(os.path.join(full, '.taskCreated')):
            continue  # 有标记（已删任务的保留原件）
        log.warning('启动清扫：删除孤儿 uploads 目录 %s（无任务行且无 .taskCreated 标记）', full)
        shutil.rmtree(full, ignore_errors=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动序列：建目录 → 挂载自检 → schema → 恢复 → 清扫 → 审计线程
    for d in (config.UPLOADS_DIR, config.DATASETS_DIR, config.LOGS_DIR,
              config.EXPORTS_DIR, config.TMP_DIR, config.DATA_LOCAL_DIR):
        os.makedirs(d, exist_ok=True)
    checkMountWritable()
    database.initSchema()
    recoverInterruptedTasks()
    sweepOrphanUploads()
    auditService.start()
    log.info('服务启动完成，数据根=%s，DB=%s', config.DATA_ROOT, config.DB_PATH)
    yield
    # 关停 drain（R2 新-6）：审计 sentinel+join(5s) → 日志 QueueListener 停止
    auditService.stop()
    logUtil.stopLogging()
    log.info('服务关停')


def createApp() -> FastAPI:
    logUtil.setupAppLogging()
    app = FastAPI(lifespan=lifespan, title='clsLabelTool')

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    app.include_router(clientApi.router)
    app.include_router(taskApi.router)
    app.include_router(annotationApi.router)
    app.include_router(fileApi.router)
    app.include_router(exportService.router)

    @app.middleware('http')
    async def staticNoCache(request, call_next):
        """静态资源禁启发式缓存（304 重验证仍生效，代价微小）"""
        response = await call_next(request)
        p = request.url.path
        if p == '/' or p == '/index.html' or p == '/favicon.ico' or p.startswith('/js/') or p.startswith('/css/'):
            response.headers['Cache-Control'] = 'no-cache'
        return response

    # 静态托管最后挂载（catch-all 需位于所有 /api 路由之后）
    app.mount('/', StaticFiles(directory=config.STATIC_DIR, html=True), name='static')
    return app


app = createApp()
