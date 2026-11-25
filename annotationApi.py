# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.2 / Date: 2026-11-24 / Description: 标注写入与数据项分页。搜索按文件名匹配，支持与标注状态叠加过滤，分页数据与总数使用同一读快照。

import json
import logging
import posixpath

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auditService
import clientApi
import database

log = logging.getLogger('clsLabelTool')


class AnnotateBody(BaseModel):
    itemId: int
    label: str | None = None


router = APIRouter(prefix='/api', tags=['annotate'])


@router.post('/tasks/{taskId}/annotate')
def annotate(taskId: str, body: AnnotateBody, client: dict = Depends(clientApi.resolveClient)):
    """数字键/点击标注（R8 同步实时保存）：同一写事务内复检任务存在+归属+itemId∈任务
    （R3 P2-1，闭合与 force 删除的交错窗口）→ upsert 提交后返回 updatedAt；审计异步入队。
    label=null → 清除标注（删行，action=clear）。"""
    with database.writeTx() as conn:
        task = conn.execute('SELECT labelsJson FROM tasks WHERE taskId=? AND creatorId=?',
                            (taskId, client['clientId'])).fetchone()
        if task is None:
            raise HTTPException(status_code=404, detail='任务不存在')
        item = conn.execute('SELECT itemId FROM items WHERE itemId=? AND taskId=?',
                            (body.itemId, taskId)).fetchone()
        if item is None:
            raise HTTPException(status_code=404, detail='数据项不存在或不属于该任务')
        labels = json.loads(task['labelsJson'])
        if body.label is not None and body.label not in labels:
            raise HTTPException(status_code=400, detail='label 不在任务标签集合内')

        updatedAt = database.utcNowIso()
        if body.label is None:
            conn.execute('DELETE FROM annotations WHERE taskId=? AND itemId=?', (taskId, body.itemId))
        else:
            conn.execute(
                'INSERT INTO annotations(taskId, itemId, label, updatedAt) VALUES(?,?,?,?) '
                'ON CONFLICT(taskId, itemId) DO UPDATE SET label=excluded.label, updatedAt=excluded.updatedAt',
                (taskId, body.itemId, body.label, updatedAt))
    action = 'clear' if body.label is None else 'annotate'
    auditService.enqueue(client['clientId'], action, taskId=taskId, itemId=body.itemId, label=body.label)
    return {'updatedAt': updatedAt}


@router.get('/tasks/{taskId}/items')
def listItems(taskId: str, offset: int = 0, limit: int = 100, filter: str = 'all',
              q: str = '', client: dict = Depends(clientApi.resolveClient)):
    """分页数据项（relPath 自然序=itemId 序，E1 P2-5）；filter=all|unlabeled|labeled；
    q 匹配文件名（含扩展名）的字面子串，空 q 时返回当前过滤条件下的所有文件。"""
    if offset < 0 or limit <= 0 or limit > 1000:
        raise HTTPException(status_code=400, detail='offset/limit 参数非法（0<=offset，1<=limit<=1000）')
    if filter not in ('all', 'unlabeled', 'labeled'):
        raise HTTPException(status_code=400, detail="filter 仅支持 all|unlabeled|labeled")
    if len(q) > 200:
        raise HTTPException(status_code=400, detail='搜索词过长（≤200 字符）')
    with database.readTx() as conn:
        conn.execute('BEGIN')
        task = conn.execute('SELECT taskId FROM tasks WHERE taskId=? AND creatorId=?',
                            (taskId, client['clientId'])).fetchone()
        if task is None:
            raise HTTPException(status_code=404, detail='任务不存在')
        where = 'WHERE i.taskId=?'
        params = [taskId]
        if filter == 'unlabeled':
            where += ' AND a.itemId IS NULL'
        elif filter == 'labeled':
            where += ' AND a.itemId IS NOT NULL'
        if q:
            conn.create_function('fileName', 1, posixpath.basename, deterministic=True)
            esc = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            where += " AND fileName(i.relPath) LIKE ? ESCAPE '\\'"
            params.append('%' + esc + '%')
        total = conn.execute(
            f'SELECT COUNT(*) AS c FROM items i LEFT JOIN annotations a ON a.taskId=i.taskId AND a.itemId=i.itemId {where}',
            tuple(params)).fetchone()['c']
        rows = conn.execute(
            f'SELECT i.itemId, i.relPath, i.absPath, i.sizeBytes, a.label, a.updatedAt '
            f'FROM items i LEFT JOIN annotations a ON a.taskId=i.taskId AND a.itemId=i.itemId '
            f'{where} ORDER BY i.itemId LIMIT ? OFFSET ?',
            tuple(params + [limit, offset])).fetchall()
    return {
        'items': [{'itemId': r['itemId'], 'relPath': r['relPath'], 'absPath': r['absPath'],
                   'sizeBytes': r['sizeBytes'], 'label': r['label'], 'updatedAt': r['updatedAt']}
                  for r in rows],
        'total': total, 'offset': offset, 'limit': limit,
    }
