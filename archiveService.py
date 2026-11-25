# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: zip/7z/rar 统一解压（zip=zipfile+GBK 回退+infolist 预检；7z/rar=libarchive-c file_reader 逐成员；统一：resolve 目标须在解压根内否则跳过记日志/跳目录与非图片/不递归嵌套；成员数按遍历全部累计（含跳过）、字节按实际写出累计，超限中止→护栏专用 errorMsg；每成员前校验任务存在+状态未变；加密/分卷/损坏包装明确 error 文案）

import logging
import os
import threading
import zipfile

import config
import database
import scanService
from libarchive import ffi as laFfi
from libarchive import exception as laException
from libarchive.read import file_reader as laFileReader

log = logging.getLogger('clsLabelTool')

# 护栏专用 errorMsg（E1 P1-2：与损坏/加密文案区分）
GUARD_MSG = '解压中止：实际写出量超过 20GB 或成员数超过 20 万（安全护栏）'
# 损坏/加密/分卷统一文案（设计 §8.2.5：读取失败统一包装为明确 error 文案）
READ_FAIL_MSG = '压缩包损坏、加密或分卷，无法解析（不支持加密/分卷压缩包，请检查文件完整性）'
ZIP_ENCRYPTED_MSG = '压缩包已加密，不支持加密压缩包，请解密后重新上传'


class GuardExceeded(Exception):
    """实际量护栏超限（字节/成员数）。"""


def startExtraction(taskId):
    """启动后台解压线程（任务应已置 status='extracting'）。"""
    threading.Thread(target=extractTask, args=(taskId,), daemon=True, name=f'extract-{taskId[:8]}').start()


def _checkTaskStillExtracting(taskId):
    """每成员（批）前校验：任务存在且状态未变（force 删除/重启即退出）。返回 True 继续。"""
    with database.readTx() as conn:
        row = conn.execute('SELECT status FROM tasks WHERE taskId=?', (taskId,)).fetchone()
    if row is None or row['status'] != 'extracting':
        log.info('解压 %s：任务已删除或状态变更，退出', taskId)
        return False
    return True


def _resolveMemberNameZip(zi):
    """zip 成员名：无 UTF-8 标志（flag_bits&0x800==0）时 cp437→gb18030 回退。"""
    name = zi.filename
    if not (zi.flag_bits & 0x800):
        name = name.encode('cp437').decode('gb18030', errors='replace')
    return name


def _resolveMemberNameLa(entry):
    """libarchive 成员名回退链：
    1) entry.pathname（utf16/utf8 解码成功）→ 直接用；
    2) 名疑似 cp437 映射乱码（全 <0x100 且含非 ASCII）→ cp437→gb18030（回解含 CJK 才采纳，RAR4 预案）；
    3) pathname 为 None（原始字节非 UTF-8）→ 取原始字节按 gb18030 解码。
    """
    name = entry.pathname
    if name is None:
        raw = laFfi.entry_pathname(entry._entry_p)
        if raw:
            return raw.decode('gb18030', errors='replace')
        return 'unknown'
    if any(ord(c) > 0x7f for c in name) and all(ord(c) < 0x100 for c in name):
        try:
            fixed = name.encode('cp437').decode('gb18030')
            if any(0x4e00 <= ord(c) <= 0x9fff for c in fixed):
                return fixed
        except (UnicodeError, LookupError):
            pass
    return name


def _safeTarget(extractRoot, rootReal, memberName):
    """zip-slip 防护：目标路径 resolve 后必须位于解压根内，否则返回 None（跳过记日志）。"""
    target = os.path.realpath(os.path.join(extractRoot, memberName))
    if target != rootReal and not target.startswith(rootReal + os.sep):
        return None
    return target


def _writeMemberData(srcBlocks, target, taskId):
    """逐块写出并累计实际字节数；超 20GB 护栏即中止（R3 P1-1 实际量护栏）。返回写出字节数。"""
    written = 0
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'wb') as dst:
        for block in srcBlocks:
            dst.write(block)
            written += len(block)
            if written > config.MAX_EXTRACT_BYTES:
                raise GuardExceeded()
    return written


def _extractZip(archivePath, extractRoot, taskId):
    """zip 引擎：infolist 预检（快速失败路径）+ 逐成员安全写出 + 实际量护栏。"""
    writtenBytes = 0
    memberCount = 0
    with zipfile.ZipFile(archivePath) as zf:
        infos = zf.infolist()
        # 预检：成员数/声明未压缩总和（仅快速失败，唯一护栏是实际量累计 R3 P1-1）
        if len(infos) > config.MAX_EXTRACT_MEMBERS:
            raise GuardExceeded()
        if sum(i.file_size for i in infos) > config.MAX_EXTRACT_BYTES:
            raise GuardExceeded()
        rootReal = os.path.realpath(extractRoot)
        for zi in infos:
            memberCount += 1  # 成员数按遍历全部累计（含跳过项，R4 P2-a）
            if memberCount > config.MAX_EXTRACT_MEMBERS:
                raise GuardExceeded()
            if not _checkTaskStillExtracting(taskId):
                return
            name = _resolveMemberNameZip(zi)
            if name.endswith('/'):
                continue  # 目录项
            if os.path.splitext(name)[1].lower() not in config.IMAGE_EXTS:
                continue  # 非图片扩展名（嵌套压缩包自然排除）
            target = _safeTarget(extractRoot, rootReal, name)
            if target is None:
                log.warning('解压 %s：跳过越界成员（zip-slip）%r', taskId, name)
                continue
            if os.path.exists(target):
                continue  # 重名成员去重（先写者胜）
            with zf.open(zi) as src:
                writtenBytes += _writeMemberData(_chunks(src), target, taskId)
    log.info('解压 %s（zip）完成：遍历 %d 成员，写出 %d 字节', taskId, memberCount, writtenBytes)


def _chunks(src):
    """zipfile 文件对象 → 1MB 块生成器。"""
    while True:
        block = src.read(config.COPY_CHUNK_SIZE)
        if not block:
            return
        yield block


def _extractLibarchive(archivePath, extractRoot, taskId):
    """7z/rar 引擎：libarchive-c file_reader 逐成员（成员名/大小/数据块）手动安全写出。"""
    writtenBytes = 0
    memberCount = 0
    rootReal = os.path.realpath(extractRoot)
    with laFileReader(archivePath) as reader:
        for entry in reader:
            memberCount += 1  # 成员数按遍历全部累计（含跳过项，R4 P2-a）
            if memberCount > config.MAX_EXTRACT_MEMBERS:
                raise GuardExceeded()
            if not _checkTaskStillExtracting(taskId):
                return
            if entry.isdir or not entry.isreg:
                continue  # 目录项/符号链接等
            name = _resolveMemberNameLa(entry)
            if os.path.splitext(name)[1].lower() not in config.IMAGE_EXTS:
                continue  # 非图片扩展名（嵌套压缩包自然排除）
            target = _safeTarget(extractRoot, rootReal, name)
            if target is None:
                log.warning('解压 %s：跳过越界成员（zip-slip）%r', taskId, name)
                continue
            if os.path.exists(target):
                continue  # 重名成员去重（先写者胜）
            writtenBytes += _writeMemberData(entry.get_blocks(config.COPY_CHUNK_SIZE), target, taskId)
    log.info('解压 %s（libarchive）完成：遍历 %d 成员，写出 %d 字节', taskId, memberCount, writtenBytes)


def extractTask(taskId):
    """后台解压主流程（设计 §8.2.4-6）：解压 → scanning → 扫描；失败 → error+明确文案。"""
    try:
        with database.readTx() as conn:
            task = conn.execute('SELECT sourceType, sourcePath FROM tasks WHERE taskId=?', (taskId,)).fetchone()
        if task is None or task['sourcePath'] is None:
            return
        sourceType = task['sourceType']
        uploadId = os.path.basename(task['sourcePath'])  # sourcePath = datasets/<uploadId>
        uploadDir = os.path.join(config.UPLOADS_DIR, uploadId)
        archivePath = None
        for fname in os.listdir(uploadDir):
            if fname != '.taskCreated' and os.path.isfile(os.path.join(uploadDir, fname)):
                archivePath = os.path.join(uploadDir, fname)
                break
        if archivePath is None:
            _setTaskError(taskId, '上传原件丢失，无法解压')
            return
        extractRoot = os.path.join(config.DATASETS_DIR, uploadId)
        os.makedirs(extractRoot, exist_ok=True)

        if sourceType == 'zip':
            _extractZip(archivePath, extractRoot, taskId)
        else:
            _extractLibarchive(archivePath, extractRoot, taskId)

        # 解压完成 → scanning → 扫描（8.1 第 2 步起）
        with database.writeTx() as conn:
            row = conn.execute('SELECT status FROM tasks WHERE taskId=?', (taskId,)).fetchone()
            if row is None or row['status'] != 'extracting':
                log.info('解压 %s：任务已删除或状态变更，不进入扫描', taskId)
                return
            conn.execute("UPDATE tasks SET status='scanning' WHERE taskId=?", (taskId,))
        scanService.startScanTask(taskId)
    except GuardExceeded:
        log.warning('解压 %s 触发实际量护栏', taskId)
        _setTaskError(taskId, GUARD_MSG)
    except laException.ArchiveError as e:
        log.exception('解压 %s libarchive 读取失败', taskId)
        _setTaskError(taskId, f'{READ_FAIL_MSG}：{e}')
    except zipfile.BadZipFile as e:
        log.exception('解压 %s zip 解析失败', taskId)
        _setTaskError(taskId, f'压缩包损坏或无法解析：{e}')
    except RuntimeError as e:
        msg = str(e)
        if 'encrypted' in msg.lower():
            log.warning('解压 %s 遇加密压缩包', taskId)
            _setTaskError(taskId, ZIP_ENCRYPTED_MSG)
        else:
            log.exception('解压 %s 运行时错误', taskId)
            _setTaskError(taskId, f'压缩包读取失败：{msg}')
    except Exception as e:
        log.exception('解压 %s 异常', taskId)
        _setTaskError(taskId, f'解压失败：{e}')


def _setTaskError(taskId, msg):
    with database.writeTx() as conn:
        conn.execute("UPDATE tasks SET status='error', errorMsg=? WHERE taskId=?", (msg, taskId))
