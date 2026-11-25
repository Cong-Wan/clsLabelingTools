# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.1 / Date: 2026-11-24 / Description: SQLite 连接助手（WAL/busy_timeout/Row）、initSchema DDL、writeTx 短写事务（BEGIN IMMEDIATE）；v1.1 tasks 加 recursiveScan 列（新库 DDL + 老库 _ensureColumn 幂等迁移，1=递归、默认 1 向后兼容）

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config


def utcNowIso():
    """UTC ISO 时间戳（毫秒），全项目统一时间格式。"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS clients(
  clientId TEXT PRIMARY KEY,
  name TEXT DEFAULT '',
  createdAt TEXT,
  lastSeenAt TEXT
);
CREATE TABLE IF NOT EXISTS tasks(
  taskId TEXT PRIMARY KEY,
  name TEXT,
  sourceType TEXT,
  sourcePath TEXT,
  labelsJson TEXT,
  status TEXT,
  itemCount INTEGER DEFAULT 0,
  creatorId TEXT,
  createdAt TEXT,
  errorMsg TEXT DEFAULT '',
  recursiveScan INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS items(
  itemId INTEGER PRIMARY KEY AUTOINCREMENT,
  taskId TEXT,
  relPath TEXT,
  absPath TEXT,
  sizeBytes INTEGER,
  UNIQUE(taskId, relPath)
);
CREATE TABLE IF NOT EXISTS annotations(
  taskId TEXT,
  itemId INTEGER,
  label TEXT,
  updatedAt TEXT,
  PRIMARY KEY(taskId, itemId)
);
CREATE INDEX IF NOT EXISTS idx_items_task ON items(taskId);
CREATE INDEX IF NOT EXISTS idx_tasks_creator ON tasks(creatorId);
"""


def newConnection():
    """每请求/每线程独立短连接；WAL + busy_timeout=5000 + Row 工厂。"""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    return conn


def _ensureColumn(conn, table, column, ddl):
    """幂等加列：PRAGMA table_info 查列，缺失则 ALTER TABLE ADD COLUMN（老行取 DEFAULT 值；ALTER ADD COLUMN 瞬时写事务，WAL+busy_timeout 下无风险）。"""
    cols = [r['name'] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()]
    if column not in cols:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')


def initSchema():
    """启动时建表/建索引（幂等）+ tasks.recursiveScan 老库迁移（幂等，重复启动不再 ALTER）。"""
    conn = newConnection()
    try:
        conn.executescript(SCHEMA_SQL)
        _ensureColumn(conn, 'tasks', 'recursiveScan', 'recursiveScan INTEGER DEFAULT 1')
        conn.commit()
    finally:
        conn.close()


@contextmanager
def writeTx():
    """写事务上下文：BEGIN IMMEDIATE（避免 WAL 读升级写的快照 BUSY 竞态），异常回滚，正常提交。"""
    conn = newConnection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def readTx():
    """读事务上下文（普通连接，用完即关）。"""
    conn = newConnection()
    try:
        yield conn
    finally:
        conn.close()
