#!/usr/bin/env python3
"""
merge_sdk.py — 合并多产品 prebuilt tar.gz 为单一发布包

用法:
    python3 merge_sdk.py \
        --base   /data/.../OHOS3/R200X_..._Base-package.tar.gz \
        --merge  /data/.../OHOS4/R200X_..._Base-package.tar.gz \
        --output /data/.../OHOS3/R200X_combined_730_735.tar.gz \
        [--merge-path ohos5/device/shaolingun]

逻辑:
  1. 将 --base tar.gz 完整解压到临时目录
  2. 从 --merge tar.gz 中提取指定路径（默认 ohos5/device/ 下所有 board 子目录）
     并合并到临时目录（已存在的文件以 --merge 包优先覆盖）
  3. 将临时目录重新打包为 --output tar.gz
  4. 清理临时目录

典型场景:
  - transform_sdk.py 分别对 730(OHOS3) 和 735(OHOS4) 运行后
    生成两个各自包含单 board 预编译产物的 tar.gz
  - merge_sdk.py 将它们合并为一个同时支持 730/735 的 tar.gz
"""

import argparse
import os
import shutil
import sys
import tarfile
import tempfile


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--base', required=True,
                   help='基础 tar.gz（730 产品，保留全部内容）')
    p.add_argument('--merge', required=True,
                   help='待合并 tar.gz（735 产品，只取 --merge-path 路径）')
    p.add_argument('--output', required=True,
                   help='输出 tar.gz 路径')
    p.add_argument('--merge-path', default=None,
                   help='从 --merge 包中提取的路径前缀（不填则自动检测 ohos5/device/<board>/ 目录）')
    p.add_argument('--dry-run', action='store_true',
                   help='只打印合并内容，不写文件')
    return p.parse_args()


def detect_board_paths(tf, device_prefix='ohos5/device/'):
    """
    扫描 tar 中 ohos5/device/<board>/ 子目录，
    返回去掉前缀 './' 后以 device_prefix 开头的路径集合。
    """
    boards = set()
    for m in tf.getmembers():
        name = m.name.lstrip('./')
        if name.startswith(device_prefix):
            rest = name[len(device_prefix):]
            if '/' in rest:
                board = rest.split('/')[0]
                if board and board not in ('board', 'soc'):
                    boards.add(device_prefix + board)
    return sorted(boards)


def detect_vendor_paths(tf, vendor_prefix='ohos5/vendor/hisilicon/'):
    """
    扫描 tar 中 ohos5/vendor/hisilicon/<product>/ 子目录，
    返回去掉前缀 './' 后以 vendor_prefix 开头的路径集合。
    """
    products = set()
    for m in tf.getmembers():
        name = m.name.lstrip('./')
        if name.startswith(vendor_prefix):
            rest = name[len(vendor_prefix):]
            if '/' in rest:
                product = rest.split('/')[0]
                if product:
                    products.add(vendor_prefix + product)
    return sorted(products)


def extract_base(base_path, tmpdir):
    print(f'[merge] 解压 base: {base_path}')
    with tarfile.open(base_path, 'r:gz') as tf:
        tf.extractall(tmpdir)
    print('[merge] base 解压完成')


def merge_from(merge_path, tmpdir, merge_paths_filter):
    """
    从 merge tar.gz 中提取指定路径合并到 tmpdir，
    merge_paths_filter 是前缀列表（如 ['ohos5/device/shaolingun']）
    """
    print(f'[merge] 合并 merge: {merge_path}')
    print(f'[merge] 提取路径: {merge_paths_filter}')
    with tarfile.open(merge_path, 'r:gz') as tf:
        members = [
            m for m in tf.getmembers()
            if any(m.name.lstrip('./').startswith(p) for p in merge_paths_filter)
        ]
        print(f'[merge] 匹配文件数: {len(members)}')
        for m in members:
            dest = os.path.join(tmpdir, m.name.lstrip('./'))
            if m.isdir():
                os.makedirs(dest, exist_ok=True)
            elif m.isfile():
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with tf.extractfile(m) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(dest, m.mode)
            elif m.issym():
                if os.path.lexists(dest):
                    os.remove(dest)
                os.symlink(m.linkname, dest)
            elif m.islnk():
                link_src = os.path.join(tmpdir, m.linkname.lstrip('./'))
                if os.path.lexists(dest):
                    os.remove(dest)
                os.link(link_src, dest)
    print('[merge] 合并完成')


def repack(tmpdir, output_path):
    print(f'[merge] 打包输出: {output_path}')
    with tarfile.open(output_path, 'w:gz') as tf:
        for root, dirs, files in os.walk(tmpdir):
            for name in dirs + files:
                abs_path = os.path.join(root, name)
                arcname = './' + os.path.relpath(abs_path, tmpdir)
                tf.add(abs_path, arcname=arcname, recursive=False)
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f'[merge] 完成! 输出大小: {size_mb:.1f} MB  路径: {output_path}')


def main():
    args = parse_args()

    for p in [args.base, args.merge]:
        if not os.path.isfile(p):
            print(f'[ERROR] 文件不存在: {p}')
            sys.exit(1)

    # 自动检测 merge 包中要提取哪些路径
    if args.merge_path:
        merge_paths = [args.merge_path.lstrip('./')]
    else:
        print('[merge] 自动检测 merge 包中的 board 和 vendor 路径...')
        with tarfile.open(args.base, 'r:gz') as btf:
            base_boards   = set(detect_board_paths(btf))
            base_vendors  = set(detect_vendor_paths(btf))
        with tarfile.open(args.merge, 'r:gz') as tf:
            all_boards   = set(detect_board_paths(tf))
            all_vendors  = set(detect_vendor_paths(tf))

        new_boards  = all_boards  - base_boards
        new_vendors = all_vendors - base_vendors

        if not new_boards:
            print(f'[WARN] merge 包中未发现新 board（base 已有: {sorted(base_boards)}），全量合并 ohos5/device/')
            merge_paths = ['ohos5/device/']
        else:
            merge_paths = sorted(new_boards)

        if new_vendors:
            merge_paths += sorted(new_vendors)
            print(f'[merge] 新增 vendor 路径: {sorted(new_vendors)}')
        else:
            print(f'[WARN] merge 包中未发现新 vendor product（base 已有: {sorted(base_vendors)}）')

        print(f'[merge] 将提取: {merge_paths}')

    if args.dry_run:
        print('[dry-run] 不执行实际操作，退出')
        return

    tmpdir = tempfile.mkdtemp(prefix='merge_sdk_', dir=os.path.dirname(args.output))
    try:
        extract_base(args.base, tmpdir)
        merge_from(args.merge, tmpdir, merge_paths)

        # 验证 board 和 vendor 目录都存在
        device_dir = os.path.join(tmpdir, 'ohos5', 'device')
        if os.path.isdir(device_dir):
            boards = [d for d in os.listdir(device_dir)
                      if os.path.isdir(os.path.join(device_dir, d))
                      and d not in ('board', 'soc')]
            print(f'[merge] 验证 ohos5/device/ board 列表: {boards}')
        vendor_dir = os.path.join(tmpdir, 'ohos5', 'vendor', 'hisilicon')
        if os.path.isdir(vendor_dir):
            products = [d for d in os.listdir(vendor_dir)
                        if os.path.isdir(os.path.join(vendor_dir, d))]
            print(f'[merge] 验证 ohos5/vendor/hisilicon/ product 列表: {products}')

        repack(tmpdir, args.output)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print('[merge] 临时目录已清理')


if __name__ == '__main__':
    main()
