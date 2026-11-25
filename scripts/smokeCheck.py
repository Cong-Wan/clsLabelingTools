# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 原生 API 冒烟核对（urllib+sqlite3+json，无测试框架）：CSV 全断言（行数=itemCount/行序自然序/BOM/列名/annotatorName 非空）+ exports 留档 + 非 ready 导出 409

import csv
import io
import json
import sqlite3
import sys
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8686'
DB = '/home/wanshicong/projects/clsLabelTool/data/clsTool.db'


def api(method, path, clientId, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('X-Client-Id', clientId)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def checkCsv(taskId):
    """CSV 全断言（设计 §8.4 + 验收 #9）。"""
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        task = conn.execute('SELECT itemCount, creatorId FROM tasks WHERE taskId=?', (taskId,)).fetchone()
        clientName = conn.execute('SELECT name FROM clients WHERE clientId=?', (task['creatorId'],)).fetchone()['name']
        itemRelPaths = [r[0] for r in conn.execute('SELECT relPath FROM items WHERE taskId=? ORDER BY itemId', (taskId,))]
        itemCount = task['itemCount']
    status, raw = api('GET', f'/api/tasks/{taskId}/export', task['creatorId'])
    assert status == 200, f'导出应 200，实际 {status}'
    # BOM 头三字节
    assert raw[:3] == b'\xef\xbb\xbf', 'BOM 缺失'
    text = raw.decode('utf-8-sig')
    rows = list(csv.reader(io.StringIO(text)))
    header, dataRows = rows[0], rows[1:]
    assert header == ['relPath', 'absPath', 'label', 'annotatorId', 'annotatorName', 'updatedAt'], f'列名不符: {header}'
    # 行数 = itemCount
    assert len(dataRows) == itemCount == len(itemRelPaths), f'行数 {len(dataRows)} != itemCount {itemCount}'
    # 行序 = relPath 自然序（= itemId 序）
    gotOrder = [r[0] for r in dataRows]
    assert gotOrder == itemRelPaths, f'行序不符:\n{gotOrder}\n!=\n{itemRelPaths}'
    # annotatorId/annotatorName 非空（默认名兜底）
    for r in dataRows:
        assert r[3] == task['creatorId'], f'annotatorId 不符: {r[3]}'
        assert r[4], 'annotatorName 为空'
    # 未标注行 label/updatedAt 为空；标注行 label 非空
    with sqlite3.connect(DB) as conn:
        labeled = {r[0]: r[1] for r in conn.execute('SELECT itemId, label FROM annotations WHERE taskId=?', (taskId,))}
    labeledCount = len(labeled)
    nonEmptyLabels = sum(1 for r in dataRows if r[2])
    assert nonEmptyLabels == labeledCount, f'标注行数 {nonEmptyLabels} != DB {labeledCount}'
    print(f'CSV PASS：{len(dataRows)} 行 = itemCount，行序自然序，BOM，列名，annotatorName="{clientName or "默认名"}" 非空，标注 {labeledCount} 行')


def checkExportGuard(taskId, expectStatus):
    """导出守卫：非 ready → 409（R3 P2-3）。"""
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        creator = conn.execute('SELECT creatorId FROM tasks WHERE taskId=?', (taskId,)).fetchone()['creatorId']
    status, _ = api('GET', f'/api/tasks/{taskId}/export', creator)
    assert status == expectStatus, f'导出守卫应 {expectStatus}，实际 {status}'
    print(f'导出守卫 PASS：taskId={taskId[:8]}… → {status}')


def main():
    args = sys.argv[1:]
    if not args:
        print('用法: smokeCheck.py <taskId...> [guard409:<taskId>]')
        return 1
    for a in args:
        if a.startswith('guard409:'):
            checkExportGuard(a.split(':', 1)[1], 409)
        else:
            checkCsv(a)
    print('smokeCheck 全部 PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
