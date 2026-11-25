# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 运行日志（QueueHandler+QueueListener+RotatingFileHandler 10MB×5+控制台），logs/app.log

import logging
import logging.handlers
import os
import queue

import config

_initialized = False
_listener = None


def setupAppLogging():
    """初始化运行日志：异步队列 → 监听线程 → 滚动文件 + 控制台。幂等。"""
    global _initialized, _listener
    if _initialized:
        return
    os.makedirs(config.LOGS_DIR, exist_ok=True)

    logQueue = queue.Queue()
    queueHandler = logging.handlers.QueueHandler(logQueue)

    _listener = logging.handlers.QueueListener(
        logQueue,
        logging.handlers.RotatingFileHandler(
            os.path.join(config.LOGS_DIR, 'app.log'),
            maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'),
        logging.StreamHandler(),
    )
    _listener.start()

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [queueHandler]
    _initialized = True


def stopLogging():
    """关停时停止 QueueListener（R2 新-6 关停 drain）。"""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


def getLog():
    """取根 logger（setupAppLogging 之后调用）。"""
    return logging.getLogger('clsLabelTool')
