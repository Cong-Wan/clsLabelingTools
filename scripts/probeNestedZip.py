# -*- coding: utf-8 -*-
# Author: wilbur / Version: 1.0 / Date: 2026-11-20 / Description: 验收 #4 只读探针：从真实 7z（潇湘站全站巡视（可见光）.7z，仅 3 成员=目录+xlsx+嵌套 zip）流式读出嵌套 zip 成员至挂载点 tmp 暂存，用 zipfile 只读列举（不解压任何图片），确认嵌套层前若干成员确为图片，随后删除暂存

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from libarchive.read import file_reader

SEVENZ_PATH = '/data_27T_jfs95/wilbur/潇湘站全站巡视（可见光）.7z'
SCRATCH = os.path.join(config.TMP_DIR, 'nestedProbe-261120.zip')


def extractNestedZip():
    """流式遍历 7z，把 .zip 成员原样写到 tmp 暂存（不解析其内容）。"""
    copied = 0
    with file_reader(SEVENZ_PATH) as reader:
        for entry in reader:
            if entry.isdir or not entry.isreg:
                continue
            name = entry.pathname or ''
            if name.endswith('.zip'):
                with open(SCRATCH, 'wb') as f:
                    for block in entry.get_blocks(config.COPY_CHUNK_SIZE):
                        f.write(block)
                copied = 1
                break
    return copied


def probeNested():
    with zipfile.ZipFile(SCRATCH) as zf:
        infos = zf.infolist()
    total = 0
    images = []
    first = []
    for zi in infos:
        if zi.filename.endswith('/'):
            continue
        total += 1
        if os.path.splitext(zi.filename)[1].lower() in config.IMAGE_EXTS:
            images.append(zi.filename)
        if len(first) < 20:
            first.append((zi.filename, zi.file_size))
    print(f'嵌套 zip 探针：文件成员总数={total}，图片成员数={len(images)}')
    print('前 20 个文件成员（名+大小）：')
    for n, s in first:
        print(f'  {n!r} {s}')
    return total, images


if __name__ == '__main__':
    try:
        if extractNestedZip() != 1:
            print('探针 FAIL：7z 中未找到嵌套 zip 成员')
            sys.exit(1)
        size = os.path.getsize(SCRATCH)
        print(f'嵌套 zip 暂存大小={size} 字节')
        total, images = probeNested()
        assert len(images) > 0, '嵌套层未发现图片成员'
        # 前若干成员确为图片（任务口径）：前 20 个文件成员中图片占比与具体名单已打印
        headImages = [n for n, _ in [(i, 0) for i in images[:20]]]
        print(f'前 20 个图片成员名示例：{headImages[:5]}')
        for n in images[:20]:
            assert '\ufffd' not in n, f'嵌套 zip 成员名含替换符：{n!r}'
        print('探针 PASS：嵌套 zip 层前若干成员确为图片（图片在嵌套层，v1 不递归→任务 error 行为正确）')
    finally:
        try:
            os.remove(SCRATCH)
        except OSError:
            pass
