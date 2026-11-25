# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 合成用例生成（无测试框架）：图片目录/正常zip/重名zip/zip-slip/空包/无图片包/GBK 中文名zip（_encodeFilenameFlags 覆写+双断言）/声明偏大伪造zip/损坏包/加密zip（zipcloak），输出到 clsToolData/testFixtures/

import os
import struct
import sys
import zipfile
import zlib

FIXTURE_DIR = '/data_27T_jfs95/wilbur/clsToolData/testFixtures'


def makePng(width=4, height=4, rgb=(255, 0, 0)):
    """手工构造最小合法 PNG（struct+zlib，不依赖 PIL）。"""
    sig = b'\x89PNG\r\n\x1a\n'

    def chunk(typ, data):
        c = struct.pack('>I', len(data)) + typ + data
        c += struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)
        return c

    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    raw = b''.join(b'\x00' + bytes(rgb) * width for _ in range(height))
    return sig + ihdr + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def writePng(relPath, rgb=(255, 0, 0)):
    path = os.path.join(FIXTURE_DIR, relPath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(makePng(rgb=rgb))


def buildImageDir():
    """路径导入用例：子目录 + 图片/非图片混排 + 符号链接（应跳过）。"""
    writePng('imgDir/a1.png')
    writePng('imgDir/sub/img2.png', (0, 255, 0))
    writePng('imgDir/sub/img10.png', (0, 0, 255))
    writePng('imgDir/b.jpg')  # 内容为占位字节（扫描只按扩展名；字节比对用 PNG 项）
    writePng('imgDir/b.bmp')
    with open(os.path.join(FIXTURE_DIR, 'imgDir/notes.txt'), 'w') as f:
        f.write('not an image')
    linkPath = os.path.join(FIXTURE_DIR, 'imgDir/link.png')
    if not os.path.islink(linkPath):
        os.symlink('a1.png', linkPath)
    return 5  # a1.png sub/img2.png sub/img10.png b.jpg b.bmp（link.png 符号链接应跳过）


def buildNormalZip():
    path = os.path.join(FIXTURE_DIR, 'normal.zip')
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('pic1.png', makePng())
        zf.writestr('sub/pic2.png', makePng(rgb=(0, 255, 0)))
        zf.writestr('sub/deep/pic3.png', makePng(rgb=(0, 0, 255)))
        zf.writestr('readme.txt', 'hello')
    return path


def buildDupZip():
    path = os.path.join(FIXTURE_DIR, 'dup.zip')
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('dup.png', makePng())
        zf.writestr('dup.png', makePng(rgb=(0, 0, 255)))  # 合法重名成员（应去重跳过计数）
    return path


def buildZipSlipZip():
    path = os.path.join(FIXTURE_DIR, 'zipslip.zip')
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('../evil.png', makePng())  # zip-slip 成员（应跳过，任务正常）
        zf.writestr('good.png', makePng())
    return path


def buildEmptyZip():
    path = os.path.join(FIXTURE_DIR, 'empty.zip')
    with zipfile.ZipFile(path, 'w'):
        pass  # 0 成员（应 error：未发现支持的图片文件）
    return path


def buildNoImageZip():
    path = os.path.join(FIXTURE_DIR, 'noImage.zip')
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('a.txt', 'text')
        zf.writestr('b.pdf', b'%PDF-1.4 fake')
    return path


def buildGbkZip():
    """GBK 中文名 zip（E1 P1-1 修正构造法）：覆写 _encodeFilenameFlags，
    盘上名字节为 GBK 原字节且 UTF-8 标志=0。生成后双断言。
    注：Python 3.12 ZipInfo 为 __slots__（无 __dict__），实例属性赋值报 read-only，
    改用子类覆写同一方法（机制等同，盘上结果一致）。"""
    path = os.path.join(FIXTURE_DIR, 'gbk.zip')
    expected = '中文图片/测试照片一.png'

    class GbkZipInfo(zipfile.ZipInfo):
        """覆写 _encodeFilenameFlags：返回 GBK 原字节 + 标志 0。"""

        def _encodeFilenameFlags(self):
            return (self.filename.encode('gb18030'), 0)

    with zipfile.ZipFile(path, 'w') as zf:
        zi = GbkZipInfo(expected)  # filename 即期望中文名（GBK 原字节写出）
        zf.writestr(zi, makePng())
    # 双断言：读回 flag_bits&0x800==0 且 filename.encode('cp437').decode('gb18030')==期望中文名（3.12 属性为 filename）
    with zipfile.ZipFile(path) as zf:
        zi = zf.infolist()[0]
        assert zi.flag_bits & 0x800 == 0, 'GBK 包断言失败：UTF-8 标志未清零'
        assert zi.filename.encode('cp437').decode('gb18030') == expected, 'GBK 包断言失败：GBK 字节回解不符'
    return path


def _findEocd(data):
    pos = data.rfind(b'PK\x05\x06')
    assert pos >= 0, '未找到 EOCD'
    return pos


def _patchSizes(zipPath, newSize):
    """把中央目录（与本地头）所有成员的压缩/未压缩尺寸字段改为 newSize。"""
    with open(zipPath, 'rb') as f:
        data = bytearray(f.read())
    eocd = _findEocd(data)
    cdStart = int.from_bytes(data[eocd + 16:eocd + 20], 'little')
    pos = cdStart
    patched = 0
    while data[pos:pos + 4] == b'PK\x01\x02':
        fnameLen = int.from_bytes(data[pos + 28:pos + 30], 'little')
        extraLen = int.from_bytes(data[pos + 30:pos + 32], 'little')
        commentLen = int.from_bytes(data[pos + 32:pos + 34], 'little')
        data[pos + 20:pos + 24] = newSize.to_bytes(4, 'little')    # 中央目录压缩尺寸
        data[pos + 24:pos + 28] = newSize.to_bytes(4, 'little')    # 中央目录未压缩尺寸
        # 同步本地头（偏移 18 处中央目录记录内）
        localOff = int.from_bytes(data[pos + 42:pos + 46], 'little')
        assert data[localOff:localOff + 4] == b'PK\x03\x04', '本地头签名不符'
        data[localOff + 18:localOff + 22] = newSize.to_bytes(4, 'little')
        data[localOff + 22:localOff + 26] = newSize.to_bytes(4, 'little')
        pos += 46 + fnameLen + extraLen + commentLen
        patched += 1
    with open(zipPath, 'wb') as f:
        f.write(data)
    return patched


def buildOverdeclaredZip():
    """声明偏大伪造 zip：中央目录/本地头尺寸字段改 4GB×6 成员=24GB（触发 infolist 预检）。
    注意 32 位字段上限，单成员 >4GB 用多成员累计（E1）。"""
    path = os.path.join(FIXTURE_DIR, 'overdeclared.zip')
    with zipfile.ZipFile(path, 'w') as zf:
        for i in range(6):
            zf.writestr(f'big{i}.png', makePng())
    _patchSizes(path, 4_000_000_000)  # 4GB/成员，6 成员累计 24GB > 20GB 护栏
    with zipfile.ZipFile(path) as zf:
        total = sum(i.file_size for i in zf.infolist())
        assert total > 20 * 1024 ** 3, '偏大伪造包断言失败：声明总量未超 20GB'
    return path


def buildCorruptZip():
    """损坏包：声明偏小（10 字节）致 zipfile 按声明尺寸截断读取 → CRC 失败
    （E1 P1-2：此包只验“损坏 error 文案”，不能验字节护栏）。"""
    path = os.path.join(FIXTURE_DIR, 'corrupt.zip')
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('c.png', makePng())
    _patchSizes(path, 10)
    return path


def buildEncryptedZip():
    """加密 zip：PKZIP Traditional 加密（flag_bits&0x1）。
    注：环境内 zipcloak 非 tty 交互挂起不可用，改用原生实现标准 PKZIP 传统加密算法
    （minizip crypt.c 参考实现）：设计保证不变（真实加密包→解压 error 明确文案，断言 flag_bits&0x1）。"""
    path = os.path.join(FIXTURE_DIR, 'encrypted.zip')
    png = makePng()
    plain = os.path.join(FIXTURE_DIR, 'encSrc', 'plain.zip')
    os.makedirs(os.path.dirname(plain), exist_ok=True)
    with zipfile.ZipFile(plain, 'w', compression=zipfile.ZIP_STORED) as zf:
        zf.writestr('plain.png', png)

    password = b'testpass'
    key = [305419896, 591751049, 878082192]

    def keyUpdate(c):
        key[0] = zlib.crc32(bytes([c]), key[0]) & 0xFFFFFFFF
        key[1] = ((key[1] + (key[0] & 0xFF)) * 1347824332 + 1) & 0xFFFFFFFF
        key[2] = zlib.crc32(bytes([(key[1] >> 24) & 0xFF]), key[2]) & 0xFFFFFFFF

    for c in password:
        keyUpdate(c)

    def encByte(c):
        temp = ((key[2] & 0xFFFF) * 1347824332 + 1) & 0xFFFFFFFF
        out = c ^ ((temp >> 8) & 0xFF)
        keyUpdate(c)
        return out

    crc = zlib.crc32(png) & 0xFFFFFFFF
    # 12 字节加密头（6 随机字节 + 高 16 位 CRC）+ 加密数据
    header = os.urandom(6) + ((crc >> 16) & 0xFFFF).to_bytes(2, 'little')
    encData = bytes(encByte(b) for b in (header + png))

    with open(plain, 'rb') as f:
        data = bytearray(f.read())
    # 单成员 stored 包布局：本地头 30+9=39 字节 + png 数据 N 字节 + 中央目录 46+9=55 + EOCD 22
    fnameLen = 9
    localDataStart = 30 + fnameLen
    origDataLen = len(png)
    cdAndEocd = bytes(data[localDataStart + origDataLen:])  # 保留中央目录+EOCD
    data = data[:localDataStart] + bytearray(encData) + bytearray(cdAndEocd)
    data[6:8] = (0x1).to_bytes(2, 'little')  # 本地头 flag_bits |= 0x1（加密）
    data[18:22] = len(encData).to_bytes(4, 'little')  # 本地头压缩尺寸
    # 中央目录记录（新布局中紧随加密数据之后）
    cdStart = localDataStart + len(encData)
    assert data[cdStart:cdStart + 4] == b'PK\x01\x02', '中央目录签名位置不符'
    data[cdStart + 8:cdStart + 10] = (0x1).to_bytes(2, 'little')  # 中央目录 flag_bits
    data[cdStart + 20:cdStart + 24] = len(encData).to_bytes(4, 'little')  # 中央目录压缩尺寸
    eocd = data.rfind(b'PK\x05\x06')
    assert eocd > 0, 'EOCD 丢失'
    data[eocd + 16:eocd + 20] = cdStart.to_bytes(4, 'little')  # EOCD：中央目录起始偏移
    with open(path, 'wb') as f:
        f.write(data)
    with zipfile.ZipFile(path) as zf:
        zi = zf.infolist()[0]
        assert zi.flag_bits & 0x1, '加密包断言失败：加密标志位未置位'
    return path


def main():
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    count = buildImageDir()
    print(f'imgDir: {count} 个图片文件（含子目录；非图片与符号链接不计）')
    for name, fn in [('normal.zip', buildNormalZip), ('dup.zip', buildDupZip),
                     ('zipslip.zip', buildZipSlipZip), ('empty.zip', buildEmptyZip),
                     ('noImage.zip', buildNoImageZip), ('gbk.zip', buildGbkZip),
                     ('overdeclared.zip', buildOverdeclaredZip), ('corrupt.zip', buildCorruptZip),
                     ('encrypted.zip', buildEncryptedZip)]:
        print(name, '->', fn())
    print('fixtures 全部生成完毕')


if __name__ == '__main__':
    sys.exit(main())
