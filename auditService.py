# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 审计日志（queue.Queue + 单写线程异步 + 按天 JSONL audit-YYYYMMDD.jsonl + sentinel 关停 drain + 写失败控制台告警）

import json
import logging
import os
import queue
import sys
import threading

import config
import database

log = logging.getLogger('clsLabelTool')

_queue = queue.Queue()
_writerThread = None
_startLock = threading.Lock()

# 事件 action 集合（设计 §12）：annotate/clear/createTask/upload/export/deleteTask/renameClient


def start():
    """启动审计单写线程（幂等）。"""
    global _writerThread
    with _startLock:
        if _writerThread is not None and _writerThread.is_alive():
            return
        _writerThread = threading.Thread(target=_writerLoop, name='auditWriter', daemon=True)
        _writerThread.start()


def stop():
    """关停 drain（R2 新-6）：sentinel + 限时 join(5s)，重启不丢尾部审计。"""
    global _writerThread
    with _startLock:
        if _writerThread is None:
            return
        _queue.put(None)  # sentinel
        thread = _writerThread
        _writerThread = None
    thread.join(timeout=5.0)
    if thread.is_alive():
        print(f'[audit] 警告：审计线程 5s 内未退出（队列积压 {qsize()}），尾部审计可能丢失', file=sys.stderr)


def qsize():
    return _queue.qsize()


def enqueue(clientId, action, taskId=None, itemId=None, label=None, extra=None):
    """异步入队审计事件（挂载故障时仅入队，写失败降级控制台告警，不影响主流程）。"""
    rec = {'ts': database.utcNowIso(), 'clientId': clientId, 'action': action}
    if taskId is not None:
        rec['taskId'] = taskId
    if itemId is not None:
        rec['itemId'] = itemId
    if label is not None:
        rec['label'] = label
    if extra is not None:
        rec['extra'] = extra
    _queue.put(rec)


def _currentAuditPath(tsDay: str) -> str:
    return os.path.join(config.LOGS_DIR, f'audit-{tsDay}.jsonl')


def _writerLoop():
    """单写线程：消费队列，按天切换文件追加 JSONL，无交错；写失败降级控制台告警。"""
    currentDay = None
    fhandle = None
    while True:
        rec = _queue.get()
        if rec is None:  # sentinel → drain 完成
            break
        day = rec['ts'][:10]
        if day != currentDay:
            if fhandle is not None:
                try:
                    fhandle.close()
                except OSError:
                    pass
            try:
                fhandle = open(_currentAuditPath(day), 'a', encoding='utf-8')
                currentDay = day
            except OSError as e:
                # 挂载故障时文件不可达：逐条降级控制台告警（R2 新-6 措辞）
                print(f'[audit] 警告：无法打开审计文件 audit-{day}.jsonl: {e}', file=sys.stderr)
                fhandle = None
                continue
        try:
            fhandle.write(json.dumps(rec, ensure_ascii=False) + '\n')
            fhandle.flush()
        except OSError as e:
            print(f'[audit] 警告：审计写入失败（{rec.get("action")}）: {e}，事件已降级输出控制台', file=sys.stderr)
    if fhandle is not None:
        try:
            fhandle.close()
        except OSError:
            pass
