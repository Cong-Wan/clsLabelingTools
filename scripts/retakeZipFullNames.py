# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 2.1GB zip 复测全量名称核对（无测试框架）：分页取任务全部 items 的 relPath 集合，与真实 zip 只读探针（zipfile 中央目录）的图片成员名集合做全等比较+无乱码断言

import json
import os
import sys
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

BASE = 'http://127.0.0.1:8686'
TASK_ID = sys.argv[1]
CLIENT = sys.argv[2]
ZIP_PATH = '/data_27T_jfs95/wilbur/20261113潇湘变项目全栈图片标注.zip'


def get(path):
    req = urllib.request.Request(BASE + path)
    req.add_header('X-Client-Id', CLIENT)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))


# 探针基准：zipfile 只读中央目录（与设计同口径：无 UTF-8 标志 → cp437→gb18030 回读）
with zipfile.ZipFile(ZIP_PATH) as zf:
    probeSet = set()
    for zi in zf.infolist():
        if zi.filename.endswith('/'):
            continue
        name = zi.filename
        if not (zi.flag_bits & 0x800):
            name = name.encode('cp437').decode('gb18030', errors='replace')
        if os.path.splitext(name)[1].lower() in config.IMAGE_EXTS:
            probeSet.add(name)

# 工具全量 items（分页 1000）
got = set()
offset = 0
while True:
    d = get(f'/api/tasks/{TASK_ID}/items?limit=1000&offset={offset}')
    for i in d['items']:
        got.add(i['relPath'])
    if offset + 1000 >= d['total']:
        break
    offset += 1000

print(f'探针图片成员集合大小={len(probeSet)}，工具 items 集合大小={len(got)}，total={d["total"]}')
assert len(got) == d['total'] == len(probeSet), '计数不一致'
missing = probeSet - got
extra = got - probeSet
assert not missing and not extra, f'集合差异：缺 {len(missing)} 多 {len(extra)}，示例 missing={list(missing)[:3]} extra={list(extra)[:3]}'
bad = [n for n in got if '\ufffd' in n]
assert not bad, f'乱码替换符: {bad[:5]}'
print('2.1GB zip 全量名称 PASS：8292 项 relPath 集合与真实 zip 只读探针图片成员集合完全一致，无乱码')
