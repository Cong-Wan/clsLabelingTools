# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.2 / Date: 2026-11-24 / Description: 任务 CRUD（路径建任务/后台扫描；列表仅本人+已标注数；详情归属 404；删除 终态直删/非终态 409/force 先置 error 再同事务级联删；upload 端点 sync def：扩展名+魔数/10GB 预检 413/分块 1MB 拷贝/.taskCreated 标记/建 extracting 任务/后台解压）；v1.1 详情新增 labelCounts（按 labels 顺序的每类已标计数，GROUP BY label 映射，缺类补 0）；v1.2 路径建任务支持 recursive 开关（TaskCreateBody 默认 True，写 recursiveScan，list/get 响应透出 recursive）

import json
import logging
import os
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import archiveService
import auditService
import clientApi
import config
import database
import scanService

log = logging.getLogger('clsLabelTool')

MAGIC_ZIP = b'PK'
MAGIC_7Z = b'7z\xbc\xaf\x27\x1c'  # 完整 6 字节签名（R3 P2-6）
MAGIC_RAR = b'Rar!'  # 前缀覆盖 RAR4/RAR5（Rar! + 1A 07 00/01 00）


def cleanLabels(labels) -> list:
    """labels trim+去重（保序）+去空+非空校验，否则 400。"""
    if not isinstance(labels, list):
        raise HTTPException(status_code=400, detail='labels 需为字符串数组')
    cleaned = []
    for item in labels:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail='labels 需为字符串数组')
        v = item.strip()
        if v and v not in cleaned:
            cleaned.append(v)
    if not cleaned:
        raise HTTPException(status_code=400, detail='labels 去空后不能为空')
    return cleaned


class TaskCreateBody(BaseModel):
    name: str
    sourceType: str
    path: str
    labels: list
    recursive: bool = True


router = APIRouter(prefix='/api', tags=['tasks'])


def _ownedTaskRow(conn, taskId, clientId):
    return conn.execute('SELECT * FROM tasks WHERE taskId=? AND creatorId=?',
                        (taskId, clientId)).fetchone()


@router.post('/tasks')
def createPathTask(body: TaskCreateBody, client: dict = Depends(clientApi.resolveClient)):
    """绝对路径建任务：路径存在/目录/可读否则 400；labels 校验；后台扫描。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='任务名称不能为空')
    if body.sourceType != 'path':
        raise HTTPException(status_code=400, detail="sourceType 仅支持 'path'（上传走 /api/tasks/upload）")
    path = body.path.strip()
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=400, detail='路径不存在')
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail='路径不是目录')
    if not os.access(path, os.R_OK):
        raise HTTPException(status_code=400, detail='路径不可读')
    labels = cleanLabels(body.labels)

    taskId = uuid.uuid4().hex
    with database.writeTx() as conn:
        conn.execute(
            'INSERT INTO tasks(taskId, name, sourceType, sourcePath, labelsJson, status, itemCount, recursiveScan, creatorId, createdAt, errorMsg) '
            'VALUES(?,?,?,?,?,\'scanning\',0,?,?,?,\'\')',
            (taskId, name, 'path', path, json.dumps(labels, ensure_ascii=False),
             1 if body.recursive else 0, client['clientId'], database.utcNowIso()))
    auditService.enqueue(client['clientId'], 'createTask', taskId=taskId, extra={'name': name})
    log.info('创建路径任务 %s（%s，%d 标签）', taskId, path, len(labels))
    scanService.startScanTask(taskId)
    return {'taskId': taskId, 'status': 'scanning'}


@router.post('/tasks/upload')
def uploadArchive(file: UploadFile = File(...),
                  name: str = Form(...),
                  labels: str = Form('[]'),
                  client: dict = Depends(clientApi.resolveClient)):
    """压缩包上传（sync def：GB 级拷贝在线程池执行，不阻塞事件循环，R2 新-5）。
    框架已完整收包（>1MB spool 到 TMPDIR=挂载点 tmp/）后才进入本端点。"""
    t0 = time.time()
    try:
        taskName = name.strip()
        if not taskName:
            raise HTTPException(status_code=400, detail='任务名称不能为空')
        labels = cleanLabels(json.loads(labels))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='labels 需为 JSON 字符串数组')

    origName = file.filename or ''
    ext = os.path.splitext(origName)[1].lower()
    if ext not in config.SUPPORTED_ARCHIVE_EXTS:
        raise HTTPException(status_code=400, detail='仅支持 .zip/.7z/.rar 压缩包')

    # 魔数校验（读 spool 前 8 字节）
    fobj = file.file
    fobj.seek(0)
    head = fobj.read(8)
    fobj.seek(0)
    expected = {'zip': MAGIC_ZIP, '7z': MAGIC_7Z, 'rar': MAGIC_RAR}[ext.lstrip('.')]
    if not head.startswith(expected):
        raise HTTPException(status_code=400, detail='文件内容与扩展名不符（魔数校验失败）')

    # spool 尺寸预检：>10GB → 413 清理不建任务（R2 新-4；spool 由框架随请求结束清理）
    fobj.seek(0, os.SEEK_END)
    spoolSize = fobj.tell()
    fobj.seek(0)
    if spoolSize > config.MAX_UPLOAD_SIZE:
        log.warning('上传 %s 超限：spool %d 字节 > 10GB，413 不建任务', origName, spoolSize)
        raise HTTPException(status_code=413, detail='压缩包超过 10GB 限制')

    # 分块 1MB 拷贝至 uploads/<uploadId>/<净化文件名>（去路径分隔符）
    uploadId = uuid.uuid4().hex
    uploadDir = os.path.join(config.UPLOADS_DIR, uploadId)
    os.makedirs(uploadDir, exist_ok=True)
    safeName = os.path.basename(origName) or 'upload'
    destPath = os.path.join(uploadDir, safeName)
    try:
        with open(destPath, 'wb') as dst:
            while True:
                chunk = fobj.read(config.COPY_CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
    except OSError as e:
        # 拷贝失败：删部分文件+500，不建任务
        try:
            os.remove(destPath)
        except OSError:
            pass
        log.exception('上传 %s 拷贝失败', origName)
        raise HTTPException(status_code=500, detail=f'服务器保存失败：{e}')

    # 拷贝成功 → .taskCreated 标记（内容 taskId，R4 P1-a 供启动清扫区分）→ 建任务 extracting → 返回 taskId
    taskId = uuid.uuid4().hex
    try:
        with open(os.path.join(uploadDir, '.taskCreated'), 'w', encoding='utf-8') as f:
            f.write(taskId)
    except OSError as e:
        log.exception('写 .taskCreated 失败（taskId=%s）', taskId)
        raise HTTPException(status_code=500, detail=f'服务器保存失败：{e}')

    sourceType = ext.lstrip('.')
    with database.writeTx() as conn:
        conn.execute(
            'INSERT INTO tasks(taskId, name, sourceType, sourcePath, labelsJson, status, itemCount, creatorId, createdAt, errorMsg) '
            'VALUES(?,?,?,?,?,\'extracting\',0,?,?,\'\')',
            (taskId, taskName, sourceType, f'datasets/{uploadId}',
             json.dumps(labels, ensure_ascii=False), client['clientId'], database.utcNowIso()))
    auditService.enqueue(client['clientId'], 'upload', taskId=taskId,
                         extra={'file': origName, 'size': spoolSize})
    log.info('上传任务 %s 拷贝完成（%s，%d 字节，%.1fs），开始后台解压', taskId, origName, spoolSize, time.time() - t0)
    archiveService.startExtraction(taskId)
    return {'taskId': taskId, 'status': 'extracting'}


@router.get('/tasks')
def listTasks(client: dict = Depends(clientApi.resolveClient)):
    """仅本人任务（D4）：状态、itemCount、已标注数、errorMsg。"""
    with database.readTx() as conn:
        rows = conn.execute(
            'SELECT t.taskId, t.name, t.sourceType, t.sourcePath, t.labelsJson, t.status, t.itemCount, '
            't.recursiveScan, t.createdAt, t.errorMsg, '
            '(SELECT COUNT(*) FROM annotations a WHERE a.taskId=t.taskId) AS labeledCount '
            'FROM tasks t WHERE t.creatorId=? ORDER BY t.createdAt DESC',
            (client['clientId'],)).fetchall()
    out = []
    for r in rows:
        out.append({
            'taskId': r['taskId'], 'name': r['name'], 'sourceType': r['sourceType'],
            'sourcePath': r['sourcePath'], 'labels': json.loads(r['labelsJson']),
            'status': r['status'], 'itemCount': r['itemCount'], 'labeledCount': r['labeledCount'],
            'progress': (r['labeledCount'] / r['itemCount']) if r['itemCount'] else 0,
            'recursive': bool(r['recursiveScan']),
            'errorMsg': r['errorMsg'], 'createdAt': r['createdAt'],
        })
    return {'tasks': out}


@router.get('/tasks/{taskId}')
def getTask(taskId: str, client: dict = Depends(clientApi.resolveClient)):
    """详情+labels+进度+errorMsg（归属校验，非本人→404 不泄露存在性）。"""
    with database.readTx() as conn:
        row = _ownedTaskRow(conn, taskId, client['clientId'])
        if row is None:
            raise HTTPException(status_code=404, detail='任务不存在')
        labeledCount = conn.execute('SELECT COUNT(*) AS c FROM annotations WHERE taskId=?',
                                    (taskId,)).fetchone()['c']
        labelRows = conn.execute(
            'SELECT label, COUNT(*) AS c FROM annotations WHERE taskId=? GROUP BY label',
            (taskId,)).fetchall()
    itemCount = row['itemCount']
    labels = json.loads(row['labelsJson'])
    countsByLabel = {r['label']: r['c'] for r in labelRows}
    return {
        'taskId': row['taskId'], 'name': row['name'], 'sourceType': row['sourceType'],
        'sourcePath': row['sourcePath'], 'labels': labels,
        'labelCounts': [countsByLabel.get(lb, 0) for lb in labels],
        'recursive': bool(row['recursiveScan']),
        'status': row['status'], 'itemCount': itemCount, 'labeledCount': labeledCount,
        'progress': (labeledCount / itemCount) if itemCount else 0,
        'errorMsg': row['errorMsg'], 'createdAt': row['createdAt'],
    }


@router.delete('/tasks/{taskId}')
def deleteTask(taskId: str, force: bool = False, client: dict = Depends(clientApi.resolveClient)):
    """终态直删（同事务级联）；非终态 409（提示可强制删除）；force 先置 error 再同事务级联删。
    删除只删 DB 记录，物理文件保留防误删（README 说明）。"""
    with database.writeTx() as conn:
        row = _ownedTaskRow(conn, taskId, client['clientId'])
        if row is None:
            raise HTTPException(status_code=404, detail='任务不存在')
        status = row['status']
        if not force and status in ('extracting', 'scanning'):
            raise HTTPException(status_code=409, detail='任务处理中不能直接删除，可稍后重试或强制删除（?force=true）')
        if force:
            # 先置 error：后台线程批前“状态未变”校验即退出
            conn.execute("UPDATE tasks SET status='error', errorMsg='强制删除' WHERE taskId=?", (taskId,))
        conn.execute('DELETE FROM annotations WHERE taskId=?', (taskId,))
        conn.execute('DELETE FROM items WHERE taskId=?', (taskId,))
        conn.execute('DELETE FROM tasks WHERE taskId=?', (taskId,))
    auditService.enqueue(client['clientId'], 'deleteTask', taskId=taskId, extra={'force': force})
    log.info('删除任务 %s（force=%s）', taskId, force)
    return {'deleted': True}
