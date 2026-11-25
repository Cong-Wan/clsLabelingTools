# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 图片内容服务（GET /api/items/{itemId}/content：itemId→任务归属校验 404；原始字节+扩展名 MIME；文件缺失 404）

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

import clientApi
import config
import database

log = logging.getLogger('clsLabelTool')

MIME_BY_EXT = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.bmp': 'image/bmp',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}

router = APIRouter(prefix='/api', tags=['content'])


@router.get('/items/{itemId}/content')
def itemContent(itemId: int, client: dict = Depends(clientApi.resolveClient)):
    """仅图片：原始字节+扩展名 MIME。itemId 不存在或非本人任务 → 404（无任意文件读取、无跨用户访问）。"""
    with database.readTx() as conn:
        row = conn.execute(
            'SELECT i.absPath, t.creatorId FROM items i JOIN tasks t ON t.taskId=i.taskId '
            'WHERE i.itemId=?', (itemId,)).fetchone()
    if row is None or row['creatorId'] != client['clientId']:
        raise HTTPException(status_code=404, detail='数据项不存在')
    if not os.path.isfile(row['absPath']):
        raise HTTPException(status_code=404, detail='文件不存在（源数据可能已被移动）')
    ext = os.path.splitext(row['absPath'])[1].lower()
    mediaType = MIME_BY_EXT.get(ext, 'application/octet-stream')
    return FileResponse(row['absPath'], media_type=mediaType)
