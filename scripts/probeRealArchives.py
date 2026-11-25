# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.1 / Date: 2026-11-20 / Description: 真实素材只读探针（不解压、不修改）：RAR 与 2.1GB zip 的完整成员列举（图片计数/前 N 成员名/CJK 成员统计/UTF-8 标志），供 M7 复测 #5 与 2.1GB zip 验收的 itemCount 与中文名断言基准。v1.1 修正 CJK 断言口径：成员名不必然含中文（2.1GB zip 图片名为 ASCII），改为统计 CJK 成员数并断言无乱码替换符

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from libarchive.read import file_reader

RAR_PATH = '/data_27T_jfs95/wilbur/UAV_Inspection/杆塔倾斜检测/中台任务-10kV23xx线-20260810-982巡检原始影像.rar'
ZIP_PATH = '/data_27T_jfs95/wilbur/20261113潇湘变项目全栈图片标注.zip'


def probeRar():
    total = 0
    images = []
    cjkCount = 0
    with file_reader(RAR_PATH) as reader:
        for entry in reader:
            if entry.isdir or not entry.isreg:
                continue
            total += 1
            import archiveService
            name = archiveService._resolveMemberNameLa(entry)
            if any(0x4e00 <= ord(c) <= 0x9fff for c in name):
                cjkCount += 1
            if os.path.splitext(name)[1].lower() in config.IMAGE_EXTS:
                images.append(name)
    print(f'RAR 探针：文件成员总数={total}，图片成员数={len(images)}，含 CJK 成员数={cjkCount}')
    print('全部图片成员名：')
    for n in images:
        print(f'  {n!r}')
    return len(images), images


def probeZip():
    import zipfile
    with zipfile.ZipFile(ZIP_PATH) as zf:
        infos = zf.infolist()
    total = 0
    images = []
    cjkCount = 0
    noUtf8Flag = 0
    for zi in infos:
        if zi.filename.endswith('/'):
            continue
        total += 1
        name = zi.filename
        if not (zi.flag_bits & 0x800):
            noUtf8Flag += 1
            name = name.encode('cp437').decode('gb18030', errors='replace')
        if any(0x4e00 <= ord(c) <= 0x9fff for c in name):
            cjkCount += 1
        if os.path.splitext(name)[1].lower() in config.IMAGE_EXTS:
            images.append(name)
    print(f'ZIP 探针：文件成员总数={total}，图片成员数={len(images)}，无 UTF-8 标志成员数={noUtf8Flag}，含 CJK 成员数={cjkCount}')
    print('前 8 个图片成员名（回退解码后）：')
    for n in images[:8]:
        print(f'  {n!r}')
    cjkSamples = [n for n in images if any(0x4e00 <= ord(c) <= 0x9fff for c in n)][:5]
    if cjkSamples:
        print('CJK 图片成员示例：')
        for n in cjkSamples:
            print(f'  {n!r}')
    return len(images), images


if __name__ == '__main__':
    rarCount, rarNames = probeRar()
    zipCount, zipNames = probeZip()
    # 断言：成员名无乱码替换符（cp437 乱码/解码失败的特征）
    for n in rarNames + zipNames:
        assert '\ufffd' not in n, f'探针成员名含替换符（乱码）：{n!r}'
    assert rarCount > 0 and zipCount > 0, '探针未发现图片成员'
    print(f'探针 PASS：RAR 图片基准={rarCount}，ZIP 图片基准={zipCount}，全部成员名无乱码替换符')
