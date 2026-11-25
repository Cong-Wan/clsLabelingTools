# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.3 / Date: 2026-11-24 / Description: CSV 留档与按标签目录导出 ZIP，共用同一标注快照。本次修正类别目录冲突、单张大文件的 ZIP64 写入和断连清理。

import csv
import io
import json
import logging
import os
import posixpath
import shutil
import stat
import tempfile
import unicodedata
import uuid
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

import auditService
import clientApi
import config
import database

log = logging.getLogger('clsLabelTool')

CSV_COLUMNS = ['relPath', 'absPath', 'label', 'labelIndex', 'annotatorId', 'annotatorName', 'updatedAt']
ZIP_CSV_NAME = 'annotations.csv'       # ZIP 根标注表（与同快照单独导出的 CSV 同字节）
ZIP_MAPPING_NAME = 'archivePaths.csv'  # 兼容/重名调整对照（relPath,label,zipPath；仅存在调整时生成）
ZIP_MISSING_NAME = '缺失文件.txt'       # 源图缺失/打开失败清单（仅存在缺失时生成）
ZIP_NOLABEL_DIR = 'NOLabel'            # 未标注目录（根预留名）
NAME_MAX_BYTES = 255
WIN_INCOMPAT = '<>:"|?*\\/'
_DEVICE_PLAIN = {'con', 'prn', 'aux', 'nul', 'conin$', 'conout$'}

router = APIRouter(prefix='/api', tags=['export'])


def _tsStamp() -> str:
    """留档文件名时间戳（UTC，精确到分钟）。"""
    return database.utcNowIso().replace('-', '').replace('T', '').replace('Z', '').replace(':', '')[:12]


def _loadSnapshot(taskId: str, clientId: str) -> dict:
    """同一短 SQLite 读事务（显式 BEGIN，WAL 下打包期间新标注可正常保存）：
    归属 404 / ready 409 校验、任务标签、标注人、按 itemId 排序的全部数据项。
    事务（连接）结束后才产出 CSV/ZIP，当前包的分类与 CSV 使用同一快照。"""
    with database.readTx() as conn:
        conn.execute('BEGIN')
        task = conn.execute('SELECT status, creatorId, labelsJson FROM tasks WHERE taskId=? AND creatorId=?',
                           (taskId, clientId)).fetchone()
        if task is None:
            raise HTTPException(status_code=404, detail='任务不存在')
        if task['status'] != 'ready':
            raise HTTPException(status_code=409, detail='任务未就绪（仅 ready 可导出）')
        labels = json.loads(task['labelsJson'])
        creatorId = task['creatorId']
        clientRow = conn.execute('SELECT name FROM clients WHERE clientId=?', (creatorId,)).fetchone()
        # annotator=任务创建者；annotatorName 非空（默认名兜底，R3 P2-7）
        annotatorName = clientRow['name'] if clientRow and clientRow['name'] else clientApi.defaultClientName(creatorId)
        rows = conn.execute(
            'SELECT i.relPath, i.absPath, a.label, a.updatedAt '
            'FROM items i LEFT JOIN annotations a ON a.taskId=i.taskId AND a.itemId=i.itemId '
            'WHERE i.taskId=? ORDER BY i.itemId', (taskId,)).fetchall()
    labelIndex = {lb: idx for idx, lb in enumerate(labels)}
    return {'creatorId': creatorId, 'annotatorName': annotatorName, 'labelIndex': labelIndex, 'rows': rows}


def _csvBytes(snap: dict) -> bytes:
    """CSV 字节（UTF-8 BOM + QUOTE_MINIMAL 标准转义 + \r\n，行序=relPath 自然序=itemId 序）。
    旧库中不在任务标签列表的已保存标签：保留原名、labelIndex 留空。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    labelIndex = snap['labelIndex']
    for r in snap['rows']:
        label = r['label'] or ''
        labelIdx = labelIndex.get(label, '') if label else ''
        writer.writerow([r['relPath'], r['absPath'], label, labelIdx,
                         snap['creatorId'], snap['annotatorName'], r['updatedAt'] or ''])
    return '\ufeff'.encode('utf-8') + buf.getvalue().encode('utf-8')


def _nameKey(name: str) -> str:
    """重名比较键：Unicode NFC + casefold。"""
    return unicodedata.normalize('NFC', name).casefold()


def _sanitizeSegment(seg: str) -> str:
    """段净化：控制字符（含 DEL/C1）、代理字符与 Windows 不兼容字符 → '_'；
    去掉末尾句点与空格；空名用 '_'。反斜杠是原文件名中的字符，同样替换。"""
    out = []
    for ch in seg:
        if unicodedata.category(ch) in ('Cc', 'Cs') or ch in WIN_INCOMPAT:
            out.append('_')
        else:
            out.append(ch)
    s = ''.join(out).rstrip('. ')
    return s or '_'


def _isWindowsDevice(name: str) -> bool:
    """Windows 设备名：取首个句点前的基名（覆盖 CON.txt 等带扩展名形态及基名尾随句点/空格）；
    COM/LPT 需带单个数字后缀 1-9（含 Windows 保留的超脚本数字 ¹²³ 变体）。"""
    s = name.split('.', 1)[0].casefold().rstrip('. ')
    if s in _DEVICE_PLAIN:
        return True
    return s[:3] in ('com', 'lpt') and len(s) == 4 and s[3] in '123456789¹²³'


def _clipBytes(s: str, budget: int) -> str:
    return s.encode('utf-8')[:max(0, budget)].decode('utf-8', errors='ignore')


class _NamePool:
    """为同一目录中的原始路径段分配兼容且唯一的名称。"""

    def __init__(self, reserved=()):
        self._assigned = {}
        self._used = {_nameKey(name) for name in reserved}

    def allocate(self, original: str, isFile: bool) -> str:
        key = (original, isFile)
        if key in self._assigned:
            return self._assigned[key]
        name = _sanitizeSegment(original)
        if _isWindowsDevice(name):
            name = '_' + name
        stem, ext = posixpath.splitext(name) if isFile else (name, '')
        ext = _clipBytes(ext, 64).rstrip('. ')
        budget = NAME_MAX_BYTES - len(ext.encode('utf-8'))
        number = 1
        while True:
            suffix = f'_{number}' if number > 1 else ''
            prefix = _clipBytes(stem, budget - len(suffix))
            if not ext and not suffix:
                prefix = prefix.rstrip('. ')
            candidate = (prefix or '_') + suffix + ext
            candidateKey = _nameKey(candidate)
            if candidateKey not in self._used:
                self._assigned[key] = candidate
                self._used.add(candidateKey)
                return candidate
            number += 1


def _splitRelPath(relPath: str):
    """relPath 按 POSIX '/' 拆段；绝对路径、空段、'.'/'..' 段 → None（进缺失清单）。
    反斜杠不视为分隔符（原文件名中的字符，净化时替换为 '_'）。"""
    if not relPath or relPath.startswith('/'):
        return None
    segs = relPath.split('/')
    if any(seg == '' or seg == '.' or seg == '..' for seg in segs):
        return None
    return segs


def _mappingBytes(adjusted) -> bytes:
    """archivePaths.csv：relPath,label,zipPath（同主 CSV 的 BOM+标准转义约定）。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['relPath', 'label', 'zipPath'])
    for relPath, label, zipPath in adjusted:
        writer.writerow([relPath, label, zipPath])
    return '\ufeff'.encode('utf-8') + buf.getvalue().encode('utf-8')


def _missingBytes(missing) -> bytes:
    """缺失文件.txt：每行「relPath<TAB>原因」。"""
    lines = [relPath + '\t' + reason for relPath, reason in missing]
    return ('\ufeff' + '\n'.join(lines) + '\n').encode('utf-8')


def _openImage(path, flags):
    return os.open(path, flags | os.O_NONBLOCK | os.O_NOFOLLOW)


def _writeZip(fout, snap: dict):
    """写入完整归档，返回缺失、改名与写入的图片数量。"""
    rootPool = _NamePool(reserved=(ZIP_NOLABEL_DIR, ZIP_CSV_NAME, ZIP_MAPPING_NAME, ZIP_MISSING_NAME))
    for label in snap['labelIndex']:
        rootPool.allocate(label, False)
    dirPools = {}
    adjusted = []
    missing = []
    written = 0

    with zipfile.ZipFile(fout, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        zf.writestr(ZIP_CSV_NAME, _csvBytes(snap))
        for row in snap['rows']:
            relPath = row['relPath'] or ''
            segs = _splitRelPath(relPath)
            if segs is None:
                missing.append((relPath, '无效的相对路径'))
                continue
            if not row['absPath']:
                missing.append((relPath, '源文件路径为空'))
                continue
            try:
                src = open(row['absPath'], 'rb', opener=_openImage)
            except OSError as e:
                missing.append((relPath, '源文件打开失败：' + str(e)))
                continue
            with src:
                sourceStat = os.fstat(src.fileno())
                if not stat.S_ISREG(sourceStat.st_mode):
                    missing.append((relPath, '源文件不是普通文件'))
                    continue
                label = row['label'] or ''
                parent = rootPool.allocate(label, False) if label else ZIP_NOLABEL_DIR
                for seg in segs[:-1]:
                    pool = dirPools.setdefault(parent, _NamePool())
                    parent += '/' + pool.allocate(seg, False)
                pool = dirPools.setdefault(parent, _NamePool())
                zipPath = parent + '/' + pool.allocate(segs[-1], True)
                member = zipfile.ZipInfo(zipPath)
                member.file_size = sourceStat.st_size
                with zf.open(member, 'w') as dst:
                    shutil.copyfileobj(src, dst, config.COPY_CHUNK_SIZE)
            if zipPath != (label or ZIP_NOLABEL_DIR) + '/' + relPath:
                adjusted.append((relPath, label, zipPath))
            written += 1
        if adjusted:
            zf.writestr(ZIP_MAPPING_NAME, _mappingBytes(adjusted))
        if missing:
            zf.writestr(ZIP_MISSING_NAME, _missingBytes(missing))
    return len(missing), len(adjusted), written


@router.get('/tasks/{taskId}/export')
def exportTask(taskId: str, format: str = 'csv', client: dict = Depends(clientApi.resolveClient)):
    """每任务导出（D4，无 scope 参数）：?format=csv（默认，等价旧无参 URL）返回原 CSV；
    ?format=zip 下载图片+标注表归档；其他值 400。任务归属 404、未就绪 409。"""
    if format not in ('csv', 'zip'):
        raise HTTPException(status_code=400, detail='format 仅支持 csv|zip')
    snap = _loadSnapshot(taskId, client['clientId'])
    if format == 'zip':
        return _exportZip(taskId, client, snap)
    return _exportCsv(taskId, client, snap)


def _exportCsv(taskId: str, client: dict, snap: dict) -> FileResponse:
    """单独 CSV：exports/ 留档（独立临时文件+同目录 os.replace 原子落名）+ FileResponse 附件下载。"""
    data = _csvBytes(snap)
    os.makedirs(config.EXPORTS_DIR, exist_ok=True)
    fname = f'{taskId}_{_tsStamp()}_{uuid.uuid4().hex}.csv'
    finalPath = os.path.join(config.EXPORTS_DIR, fname)
    fd, tmpPath = tempfile.mkstemp(dir=config.EXPORTS_DIR, prefix='.exp-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(tmpPath, finalPath)
    except BaseException:
        try:
            os.unlink(tmpPath)
        except OSError:
            pass
        raise
    auditService.enqueue(client['clientId'], 'export', taskId=taskId,
                         extra={'file': fname, 'format': 'csv', 'missing': 0})
    log.info('导出任务 %s CSV → %s（%d 行）', taskId, fname, len(snap['rows']))
    return FileResponse(finalPath, media_type='text/csv; charset=utf-8', filename=fname)


class _ZipDownload(StreamingResponse):
    """拥有临时 ZIP 的句柄，响应结束或取消时关闭。"""

    def __init__(self, archive, size: int, filename: str):
        self._archive = archive
        chunks = iter(lambda: archive.read(config.COPY_CHUNK_SIZE), b'')
        super().__init__(chunks, media_type='application/zip', headers={
            'Content-Length': str(size),
            'Content-Disposition': f'attachment; filename="{filename}"',
        })

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._archive.close()


def _exportZip(taskId: str, client: dict, snap: dict) -> StreamingResponse:
    tmp = None
    try:
        tmp = tempfile.TemporaryFile(dir=config.TMP_DIR)
        missing, adjusted, writtenCount = _writeZip(tmp, snap)
        size = tmp.seek(0, os.SEEK_END)
        tmp.seek(0)
        fname = f'{taskId}_{_tsStamp()}_{uuid.uuid4().hex}.zip'
        auditService.enqueue(client['clientId'], 'export', taskId=taskId,
                             extra={'file': fname, 'format': 'zip', 'missing': missing})
        log.info('导出任务 %s ZIP → %s（%d 图，%d 调整，%d 缺失）', taskId, fname, writtenCount, adjusted, missing)
        return _ZipDownload(tmp, size, fname)
    except Exception as e:
        if tmp is not None:
            tmp.close()
        log.exception('导出任务 %s ZIP 构建失败', taskId)
        raise HTTPException(status_code=500, detail='生成 ZIP 失败，请检查源图片和服务器可用空间') from e
