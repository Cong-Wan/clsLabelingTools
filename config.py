# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 全局配置常量（数据根/子目录/DB/图片扩展名/护栏阈值/端口）

import os

# 数据根目录（JuiceFS 挂载点；uploads/datasets/logs/exports/tmp 均在其下）
DATA_ROOT = '/data_27T_jfs95/wilbur/clsToolData'

# 子目录
UPLOADS_DIR = os.path.join(DATA_ROOT, 'uploads')
DATASETS_DIR = os.path.join(DATA_ROOT, 'datasets')
LOGS_DIR = os.path.join(DATA_ROOT, 'logs')
EXPORTS_DIR = os.path.join(DATA_ROOT, 'exports')
TMP_DIR = os.path.join(DATA_ROOT, 'tmp')

# 项目内目录（本机磁盘）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_LOCAL_DIR = os.path.join(PROJECT_ROOT, 'data')
DB_PATH = os.path.join(DATA_LOCAL_DIR, 'clsTool.db')
STATIC_DIR = os.path.join(PROJECT_ROOT, 'static')

# 图片扩展名（D1：仅图片，不区分大小写匹配）
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'}

# 护栏常量（设计 §3 A5 / §11）
MAX_UPLOAD_SIZE = 10 * 1024 ** 3        # 单压缩包 10GB（spool 预检，超 → 413）
MAX_EXTRACT_BYTES = 20 * 1024 ** 3      # 解压实际写出字节护栏 20GB
MAX_EXTRACT_MEMBERS = 200_000           # 解压成员数护栏 20 万（按遍历全部成员累计，含跳过项）
SCAN_BATCH_SIZE = 500                   # 扫描/解压批插入大小
COPY_CHUNK_SIZE = 1024 * 1024           # 上传拷贝块 1MB

# 服务端口（CLS_PORT 可覆盖）
DEFAULT_PORT = int(os.environ.get('CLS_PORT', '8686'))

# 压缩包支持格式
SUPPORTED_ARCHIVE_EXTS = {'.zip', '.7z', '.rar'}
