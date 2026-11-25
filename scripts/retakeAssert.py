# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: M7 复测断言助手（无测试框架）：按 taskId 核对任务终态/itemCount/行序/relPath 等，供 bash 复测调用

import json
import sys
import urllib.request

BASE = 'http://127.0.0.1:8686'


def get(path, clientId):
    req = urllib.request.Request(BASE + path)
    req.add_header('X-Client-Id', clientId)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main():
    taskId, clientId = sys.argv[1], sys.argv[2]
    detail = get(f'/api/tasks/{taskId}', clientId)
    itemsResp = get(f'/api/tasks/{taskId}/items?limit=1000', clientId)
    items = itemsResp['items']
    total = itemsResp['total']
    order = [i['relPath'] for i in items]
    print(json.dumps({'status': detail['status'], 'itemCount': detail['itemCount'],
                      'total': total, 'firstOrder': order[:10]}, ensure_ascii=False))
    if '--expect-ready' in sys.argv:
        assert detail['status'] == 'ready', f"状态应 ready，实际 {detail['status']}（{detail['errorMsg']}）"
    if '--expect-count' in sys.argv:
        n = int(sys.argv[sys.argv.index('--expect-count') + 1])
        assert detail['itemCount'] == n == total, f"计数应={n}，实际 itemCount={detail['itemCount']} total={total}"
    if '--expect-order' in sys.argv:
        expect = sys.argv[sys.argv.index('--expect-order') + 1].split('|')
        assert order == expect, f'行序不符: {order} != {expect}'
    if '--expect-first-names' in sys.argv:
        expect = sys.argv[sys.argv.index('--expect-first-names') + 1].split('|')
        assert order[:len(expect)] == expect, f'前 N 项不符: {order[:len(expect)]} != {expect}'
    print('断言 PASS')


if __name__ == '__main__':
    main()
