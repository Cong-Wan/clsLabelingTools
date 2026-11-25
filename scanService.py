# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.1 / Date: 2026-11-24 / Description: 后台路径扫描（recursiveScan 可控递归：默认 1=递归全部子目录跳符号链接；0=仅扫根层不下钻；图片扩展名过滤/固定自然序键：路径按段、段内数字按数值；自然序插入使 itemId 序=自然序；批 500 同事务存在性+状态校验+INSERT OR IGNORE+跳过计数；0 项→error；异常→error）

import logging
import os
import re
import threading

import config
import database

log = logging.getLogger('clsLabelTool')

_segmentSplit = re.compile(r'(\d+)')


def _segmentKey(seg):
    """段内固定自然序键：数字段按数值、文本段按 ASCII 比较（img2 < img10）。"""
    out = []
    for piece in _segmentSplit.split(seg):
        if piece == '':
            continue
        if piece.isdigit():
            out.append((1, int(piece), ''))
        else:
            out.append((0, 0, piece))
    return tuple(out)


def naturalKey(relPath):
    """固定自然序键（R3 P2-5 使验收可复现）：路径按段比较、段内数字按数值。"""
    return tuple(_segmentKey(s) for s in relPath.split('/'))


def startScanTask(taskId):
    """启动后台扫描线程（任务应已置 status='scanning'）。"""
    threading.Thread(target=scanTask, args=(taskId,), daemon=True, name=f'scan-{taskId[:8]}').start()


def scanTask(taskId):
    """后台扫描主流程（设计 §8.1 第 2-4 步）。"""
    try:
        with database.readTx() as conn:
            task = conn.execute('SELECT sourcePath, recursiveScan FROM tasks WHERE taskId=?', (taskId,)).fetchone()
        if task is None or task['sourcePath'] is None:
            return
        baseDir = task['sourcePath']
        recursive = bool(task['recursiveScan'])
        if not os.path.isabs(baseDir):
            baseDir = os.path.join(config.DATA_ROOT, baseDir)

        # 扫描：跳过符号链接；非递归（recursiveScan=0）不下钻仅根层；图片扩展名过滤（不区分大小写），relPath 自然排序
        entries = []
        for root, dirs, files in os.walk(baseDir, followlinks=False):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
            if not recursive:
                dirs[:] = []  # 首轮即 baseDir：清空 dirs 不再下钻 = 仅根层
            for fname in files:
                full = os.path.join(root, fname)
                if os.path.islink(full):
                    continue
                if os.path.splitext(fname)[1].lower() not in config.IMAGE_EXTS:
                    continue
                rel = os.path.relpath(full, baseDir)
                entries.append((naturalKey(rel), rel, full))
        entries.sort(key=lambda t: t[0])

        # 分批 500 插入（同事务存在性+状态校验 + INSERT OR IGNORE + 跳过计数）
        inserted = 0
        skipped = 0
        for i in range(0, len(entries), config.SCAN_BATCH_SIZE):
            batch = entries[i:i + config.SCAN_BATCH_SIZE]
            with database.writeTx() as conn:
                row = conn.execute('SELECT status FROM tasks WHERE taskId=?', (taskId,)).fetchone()
                if row is None or row['status'] != 'scanning':
                    log.info('扫描 %s：任务已删除或状态变更，退出', taskId)
                    return
                for _key, rel, full in batch:
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    cur = conn.execute(
                        'INSERT OR IGNORE INTO items(taskId, relPath, absPath, sizeBytes) VALUES(?,?,?,?)',
                        (taskId, rel, full, size))
                    if cur.rowcount == 0:
                        skipped += 1
                    else:
                        inserted += 1

        # 终态：0 项 → error；否则 ready + itemCount
        with database.writeTx() as conn:
            row = conn.execute('SELECT status FROM tasks WHERE taskId=?', (taskId,)).fetchone()
            if row is None or row['status'] != 'scanning':
                log.info('扫描 %s：任务已删除或状态变更，退出（不置终态）', taskId)
                return
            if inserted == 0:
                conn.execute("UPDATE tasks SET status='error', errorMsg='未发现支持的图片文件' WHERE taskId=?",
                             (taskId,))
                log.warning('扫描 %s：0 项，置 error', taskId)
            else:
                conn.execute("UPDATE tasks SET status='ready', itemCount=? WHERE taskId=?", (inserted, taskId))
                log.info('扫描 %s 完成：%d 项（重名跳过 %d）', taskId, inserted, skipped)
        if skipped:
            log.warning('扫描 %s：跳过 %d 个重复 relPath 成员', taskId, skipped)
    except Exception as e:
        log.exception('扫描 %s 异常', taskId)
        with database.writeTx() as conn:
            conn.execute("UPDATE tasks SET status='error', errorMsg=? WHERE taskId=?",
                         (f'扫描失败：{e}', taskId))
