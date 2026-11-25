#!/usr/bin/env bash
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: clsLabelTool 服务启动脚本（先建挂载点 tmp 再导出 TMPDIR，防根盘打满）
# 先建挂载点 tmp 目录再导出 TMPDIR（Python tempfile 对无效 TMPDIR 会静默回退 /tmp，必须先 mkdir）
cd "$(dirname "$0")"
mkdir -p /data_27T_jfs95/wilbur/clsToolData/tmp
export TMPDIR=/data_27T_jfs95/wilbur/clsToolData/tmp
exec uv run uvicorn main:app --host 0.0.0.0 --port ${CLS_PORT:-8686}
