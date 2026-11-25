# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 验收 #15 实际量护栏调低阈值法（E1 P1-2）：原生脚本 import 解压服务，把字节护栏阈值临时调小后对正常小 zip 执行完整解压流程，断言中止且 errorMsg=护栏专用文案；验证后清理临时任务行与目录（不影响运行服务）

import os
import shutil
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import archiveService
import config
import database

FIXTURE_ZIP = os.path.join(config.DATA_ROOT, 'testFixtures', 'normal.zip')
UPLOAD_ID = 'guardThresholdRetest'


def main():
    uploadDir = os.path.join(config.UPLOADS_DIR, UPLOAD_ID)
    extractRoot = os.path.join(config.DATASETS_DIR, UPLOAD_ID)
    os.makedirs(uploadDir, exist_ok=True)
    shutil.copyfile(FIXTURE_ZIP, os.path.join(uploadDir, 'normal.zip'))
    with open(os.path.join(uploadDir, '.taskCreated'), 'w', encoding='utf-8') as f:
        f.write(UPLOAD_ID)

    taskId = uuid.uuid4().hex
    with database.writeTx() as conn:
        conn.execute(
            "INSERT INTO tasks(taskId, name, sourceType, sourcePath, labelsJson, status, itemCount, creatorId, createdAt, errorMsg) "
            "VALUES(?, ?, 'zip', ?, ?, 'extracting', 0, ?, ?, '')",
            (taskId, '复测-护栏调低阈值', f'datasets/{UPLOAD_ID}', '[]', 'retestA',
             database.utcNowIso()))

    # 临时调低字节阈值（进程内，不影响运行服务）：normal.zip 首张图片 ~60 字节 > 1 字节即触发
    original = config.MAX_EXTRACT_BYTES
    config.MAX_EXTRACT_BYTES = 1
    try:
        archiveService.extractTask(taskId)  # 同步执行完整流程（内部捕获 GuardExceeded → 置 error）
    finally:
        config.MAX_EXTRACT_BYTES = original

    with sqlite3.connect(config.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT status, errorMsg FROM tasks WHERE taskId=?', (taskId,)).fetchone()
    print(f'护栏调低阈值法结果：status={row["status"]} errorMsg={row["errorMsg"]!r}')
    assert row['status'] == 'error', '应中止为 error'
    assert row['errorMsg'] == archiveService.GUARD_MSG, f'应为护栏专用 errorMsg，实际 {row["errorMsg"]!r}'
    print('护栏 PASS：实际量护栏调低阈值后中止，errorMsg 为护栏专用文案（与损坏/加密文案区分）')

    # 清理临时任务行与目录
    with database.writeTx() as conn:
        conn.execute('DELETE FROM items WHERE taskId=?', (taskId,))
        conn.execute('DELETE FROM annotations WHERE taskId=?', (taskId,))
        conn.execute('DELETE FROM tasks WHERE taskId=?', (taskId,))
    shutil.rmtree(uploadDir, ignore_errors=True)
    shutil.rmtree(extractRoot, ignore_errors=True)
    print('临时数据已清理')
    return 0


if __name__ == '__main__':
    sys.exit(main())
