# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.1 / Date: 2026-11-20 / Description: 客户端身份（X-Client-Id 头 > cookie > 新建 uuid；每次解析均 Set-Cookie 同步 cookie 以便直接链接（导出/图片）走 cookie 身份；注册默认名「标注员-<id前4位>」；lastSeen 更新）+ GET/PUT /api/client

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import auditService
import database

log = logging.getLogger('clsLabelTool')

COOKIE_NAME = 'clientId'
COOKIE_MAX_AGE = 365 * 24 * 3600  # 换浏览器/清缓存=新身份（README 说明）


def defaultClientName(clientId: str) -> str:
    """注册默认名（R3 P2-7）：annotatorName 永不为空。"""
    return f'标注员-{clientId[:4]}'


def resolveClient(request: Request, response: Response) -> dict:
    """身份解析依赖（所有 /api 端点使用）：头 > cookie > 新建 uuid；
    每次均 Set-Cookie 同步（直接链接请求无头时回退 cookie 身份）；未知身份自动注册默认名；lastSeen 更新。"""
    clientId = request.headers.get('X-Client-Id') or request.cookies.get(COOKIE_NAME)
    if not clientId:
        clientId = str(uuid.uuid4())
    response.set_cookie(COOKIE_NAME, clientId, max_age=COOKIE_MAX_AGE, samesite='lax')

    with database.writeTx() as conn:
        row = conn.execute('SELECT clientId, name FROM clients WHERE clientId=?', (clientId,)).fetchone()
        if row is None:
            name = defaultClientName(clientId)
            now = database.utcNowIso()
            conn.execute('INSERT INTO clients(clientId, name, createdAt, lastSeenAt) VALUES(?,?,?,?)',
                         (clientId, name, now, now))
            log.info('注册新客户端 %s（默认名 %s）', clientId, name)
        else:
            name = row['name']
            conn.execute('UPDATE clients SET lastSeenAt=? WHERE clientId=?', (database.utcNowIso(), clientId))
    return {'clientId': clientId, 'name': name}


class ClientNameBody(BaseModel):
    name: str


router = APIRouter(prefix='/api', tags=['client'])


@router.get('/client')
def getClient(client: dict = Depends(resolveClient)):
    """获取/注册当前客户端（身份闸门端点）。"""
    return {'clientId': client['clientId'], 'name': client['name']}


@router.put('/client')
def updateClientName(body: ClientNameBody, client: dict = Depends(resolveClient)):
    """改显示名（trim/非空/≤32 字符）。"""
    name = body.name.strip()
    if not name or len(name) > 32:
        raise HTTPException(status_code=400, detail='名称需为非空且不超过 32 字符')
    with database.writeTx() as conn:
        conn.execute('UPDATE clients SET name=? WHERE clientId=?', (name, client['clientId']))
    auditService.enqueue(client['clientId'], 'renameClient', extra={'name': name})
    return {'clientId': client['clientId'], 'name': name}
