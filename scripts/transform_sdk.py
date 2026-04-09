#!/usr/bin/env python3
"""
transform_sdk.py - 将 OHOS device/vendor 源码树改造为预编译分发模式

用法:
    python3 transform_sdk.py --product mp_hi3781v730 [--ohos-root /home/my/OHOS2/ohos5]
                             [--dry-run] [--skip-pack] [--skip-source-delete] [--skip-kernel]

输出:
    - 改造后的 device/ 和 vendor/ 目录（含预编译二进制，无源码）
    - 重打包的 tar.gz（partner SDK）
    - 改造后的 apply_patches_sdk.sh（partner 版本）
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# =============================================================================
# 常量
# =============================================================================

TRANSFORM_TYPES = {
    'ohos_shared_library': 'ohos_prebuilt_shared_library',
    'ohos_executable':     'ohos_prebuilt_executable',
    'ohos_static_library': 'ohos_prebuilt_static_library',
}

SOURCE_EXTS = {'.c', '.cpp', '.cc', '.S', '.s', '.cxx', '.m', '.mm'}

# 必须保留的源文件（即使在 device/ 下）
KEEP_SOURCE_WHITELIST = {
    'device/board/hisilicon/wudangstick/audio_alsa/vendor_capture.c',
    'device/board/hisilicon/wudangstick/audio_alsa/vendor_render.c',
}

# Phase 6 扫描根内部排除的子路径（相对于 scan_root 的 posix 路径前缀）
# 这些目录下的源文件不会被删除：它们是平台扩展源码，被 foundation/ patches 直接引用，
# 且不会被编译进 vendor 预编译库，必须随 SDK 一起分发给合作伙伴。
# 根因：device/soc/hisilicon/huanglong/vendor/huanglong 是指向外层 vendor/huanglong/ 的
# 符号链接，Python rglob 会跟随进入，若不排除 ohos5_ext/ 则会误删平台扩展源文件。
EXCLUDE_WITHIN_SCAN_ROOT = {
    'ohos/ohos5_ext',
}


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class TargetInfo:
    target_type:       str        # ohos_shared_library / ohos_executable / ohos_static_library
    target_name:       str
    part_name:         str
    subsystem_name:    str        # 可能为空，后续从 out/ 解析
    output_name:       str        # 可能为空
    output_extension:  str        # 可能为空
    install_images:    str        # 原始 GN 列表字符串，如 '["vendor"]'
    public_configs:    str        # 原始 GN 列表字符串，可能为空
    module_install_dir: str       # 可能为空
    build_gn_path:     Path       # BUILD.gn 绝对路径
    scan_root:         str        # 该目标所在的扫描根（用于判断存放位置）

    relative_install_dir: str = ''   # 可能为空

    # 解析 artifact 后填充
    artifact_path:        Optional[Path] = None
    artifact_filename:    str = ''
    prebuilt_dest:        Optional[Path] = None
    prebuilt_source_ref:  str = ''


# =============================================================================
# Phase 1: 读取产品配置
# =============================================================================

def read_product_config(ohos_root: Path, product: str) -> dict:
    config_path = ohos_root / 'vendor' / 'hisilicon' / product / 'config.json'
    if not config_path.exists():
        raise FileNotFoundError(f"产品配置不存在: {config_path}")
    with open(config_path, encoding='utf-8') as f:
        cfg = json.load(f)
    board = cfg['board']
    out_dir = ohos_root / 'out' / board
    return {
        'product':  product,
        'board':    board,
        'out_dir':  out_dir,
        'config':   cfg,
    }


def detect_chip_revision(out_dir: Path) -> str:
    """从 boot 镜像文件名推断 chip_revision（如 boot_d.img → 'd'）。"""
    images_dir = out_dir / 'packages' / 'phone' / 'images'
    if images_dir.exists():
        for f in sorted(images_dir.iterdir()):
            m = re.match(r'boot_([a-z])\.img', f.name)
            if m:
                return m.group(1)
    print("  [WARN] 无法自动检测 chip_revision，使用默认值 'd'")
    return 'd'


# =============================================================================
# Phase 2: 扫描 BUILD.gn 文件
# =============================================================================

def scan_build_gn_files(ohos_root: Path, scan_root: str) -> List[Path]:
    root = ohos_root / scan_root
    if not root.exists():
        print(f"  [WARN] 扫描根不存在，跳过: {root}")
        return []
    return list(root.rglob('BUILD.gn'))


def extract_block(content: str, brace_start: int) -> int:
    """
    从 brace_start（'{'的位置）开始，返回匹配 '}'后的独占结束索引。
    返回 -1 表示未找到。
    """
    depth = 0
    i = brace_start
    in_string = False
    n = len(content)
    while i < n:
        c = content[i]
        # 跳过行注释
        if not in_string and c == '#':
            while i < n and content[i] != '\n':
                i += 1
            continue
        if in_string:
            if c == '\\' and i + 1 < n:
                i += 2
                continue
            if c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i + 1  # 独占结束
        i += 1
    return -1


def _extract_string_field(block: str, field: str) -> Optional[str]:
    m = re.search(rf'(?<!\w){re.escape(field)}\s*=\s*"([^"]*)"', block)
    return m.group(1) if m else None


def _extract_list_field(block: str, field: str) -> Optional[str]:
    """提取列表字段，返回原始字符串如 '["vendor"]' 或 '[chipset_base_dir]'。"""
    # 匹配 field = [ ... ] （可跨行，不嵌套方括号）
    m = re.search(
        rf'(?<!\w){re.escape(field)}\s*=\s*(\[[^\[\]]*\])',
        block, re.DOTALL
    )
    if m:
        # 压缩换行和多余空格
        raw = m.group(1)
        raw = re.sub(r'\s+', ' ', raw).strip()
        return raw
    return None


def parse_build_gn(gn_path: Path, scan_root: str) -> List[TargetInfo]:
    """解析 BUILD.gn，返回需要改造的目标列表。"""
    try:
        content = gn_path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        print(f"  [WARN] 无法读取 {gn_path}: {e}")
        return []

    targets = []
    pattern = re.compile(
        r'(ohos_shared_library|ohos_executable|ohos_static_library)\s*\(\s*"([^"]+)"\s*\)\s*\{'
    )

    for m in pattern.finditer(content):
        target_type = m.group(1)
        target_name = m.group(2)
        brace_pos = content.index('{', m.start())
        block_end = extract_block(content, brace_pos)
        if block_end == -1:
            print(f"  [WARN] 找不到块结束: {target_name} in {gn_path}")
            continue

        block = content[brace_pos:block_end]

        part_name         = _extract_string_field(block, 'part_name') or ''
        subsystem_name    = _extract_string_field(block, 'subsystem_name') or ''
        output_name       = _extract_string_field(block, 'output_name') or ''
        output_extension  = _extract_string_field(block, 'output_extension') or ''
        install_images    = _extract_list_field(block, 'install_images') or ''
        public_configs    = _extract_list_field(block, 'public_configs') or ''
        module_install_dir = _extract_string_field(block, 'module_install_dir') or ''
        relative_install_dir = _extract_string_field(block, 'relative_install_dir') or ''

        if not part_name:
            continue  # 无 part_name 的目标跳过（内部模板等）

        targets.append(TargetInfo(
            target_type=target_type,
            target_name=target_name,
            part_name=part_name,
            subsystem_name=subsystem_name,
            output_name=output_name,
            output_extension=output_extension,
            install_images=install_images,
            public_configs=public_configs,
            module_install_dir=module_install_dir,
            relative_install_dir=relative_install_dir,
            build_gn_path=gn_path,
            scan_root=scan_root,
        ))

    return targets


# =============================================================================
# Phase 3: 定位 out/ 中的产物
# =============================================================================

def compute_filename(target: TargetInfo) -> str:
    """计算目标的输出文件名。"""
    name = target.output_name if target.output_name else target.target_name

    if target.target_type == 'ohos_executable':
        return name

    if target.target_type == 'ohos_static_library':
        if not name.startswith('lib'):
            name = 'lib' + name
        return name + '.a'

    # ohos_shared_library
    if not name.startswith('lib'):
        name = 'lib' + name
    if target.output_extension:
        return f"{name}.{target.output_extension}"
    return f"{name}.z.so"


def find_artifact(target: TargetInfo, out_dir: Path) -> Tuple[Optional[Path], str]:
    """
    在 out/<board>/ 中查找产物。
    返回 (artifact_path, subsystem_name)，未找到返回 (None, '')。
    """
    filename = compute_filename(target)
    target.artifact_filename = filename

    # 如果 subsystem_name 已知，优先直接定位
    if target.subsystem_name:
        candidate = out_dir / target.subsystem_name / target.part_name / filename
        if candidate.exists():
            return candidate, target.subsystem_name

    # 遍历 out/<board>/ 下所有子目录（子系统目录）
    if out_dir.exists():
        for subsystem_dir in sorted(out_dir.iterdir()):
            if not subsystem_dir.is_dir():
                continue
            candidate = subsystem_dir / target.part_name / filename
            if candidate.exists():
                return candidate, subsystem_dir.name

    return None, ''


# =============================================================================
# Phase 4: 计算预编译存放路径
# =============================================================================

def get_prebuilt_dest(target: TargetInfo, ohos_root: Path, board: str,
                      subsystem_name: str, product: str) -> Tuple[Path, str]:
    """
    计算预编译存放路径和 //... 引用。

    device/ 扫描根 → device/<board>/<subsystem>/<part>/<file>
    vendor/ 扫描根 → vendor/hisilicon/<product>/<board>/<subsystem>/<part>/<file>
    """
    if target.scan_root.startswith('device/'):
        dest = (ohos_root / 'device' / board / subsystem_name
                / target.part_name / target.artifact_filename)
        src_ref = (f"//device/${{prebuilt_board_dir}}/{subsystem_name}"
                   f"/{target.part_name}/{target.artifact_filename}")
    else:  # vendor/
        dest = (ohos_root / 'vendor' / 'hisilicon' / product / board
                / subsystem_name / target.part_name / target.artifact_filename)
        src_ref = (f"//vendor/hisilicon/{product}/{board}/{subsystem_name}"
                   f"/{target.part_name}/{target.artifact_filename}")

    return dest, src_ref


# =============================================================================
# Phase 5: 改写 BUILD.gn
# =============================================================================

def generate_prebuilt_block(target: TargetInfo, src_ref: str) -> str:
    """生成 ohos_prebuilt_* GN 目标块。"""
    ptype = TRANSFORM_TYPES[target.target_type]
    lines = [f'{ptype}("{target.target_name}") {{']
    lines.append(f'  source = "{src_ref}"')
    if ptype == 'ohos_prebuilt_executable':
        lines.append('  install_enable = true')
    if target.install_images:
        lines.append(f'  install_images = {target.install_images}')
    if target.module_install_dir:
        lines.append(f'  module_install_dir = "{target.module_install_dir}"')
    if target.relative_install_dir:
        lines.append(f'  relative_install_dir = "{target.relative_install_dir}"')
    # ohos_prebuilt_shared_library 不支持 output_extension / output_name
    # （模板只转发 output 字段用于重命名，其他扩展名/名称字段均无效）
    if target.output_extension and ptype != 'ohos_prebuilt_shared_library':
        lines.append(f'  output_extension = "{target.output_extension}"')
    if target.output_name and ptype != 'ohos_prebuilt_shared_library':
        lines.append(f'  output_name = "{target.output_name}"')
    if target.public_configs:
        lines.append(f'  public_configs = {target.public_configs}')
    lines.append(f'  part_name = "{target.part_name}"')
    if target.subsystem_name:
        lines.append(f'  subsystem_name = "{target.subsystem_name}"')
    lines.append('}')
    return '\n'.join(lines)


def rewrite_build_gn(gn_path: Path,
                     transforms: Dict[str, Tuple['TargetInfo', str]],
                     dry_run: bool = False):
    """
    就地改写 BUILD.gn，将已有产物的源码编译目标替换为 ohos_prebuilt_*。
    同一文件中无产物的 source-compiled 目标也一并移除（其源文件会被 Phase 6 删除）。
    config(){} 块完整保留。
    """
    content = gn_path.read_text(encoding='utf-8', errors='replace')

    pattern = re.compile(
        r'(ohos_shared_library|ohos_executable|ohos_static_library)\s*\(\s*"([^"]+)"\s*\)\s*\{'
    )

    replacements = []
    for m in pattern.finditer(content):
        target_name = m.group(2)
        brace_pos = content.index('{', m.start())
        block_end = extract_block(content, brace_pos)
        if block_end == -1:
            continue

        if target_name in transforms:
            # 有产物：转为 ohos_prebuilt_*
            target_info, src_ref = transforms[target_name]
            new_block = generate_prebuilt_block(target_info, src_ref)
        else:
            # 无产物但同文件有 prebuilt 目标：移除此目标（源文件将被删除）
            new_block = f'# {m.group(1)}("{target_name}") removed (no artifact, sources deleted)'

        replacements.append((m.start(), block_end, new_block))

    if not replacements:
        return

    # 逆序替换以保持位置有效
    new_content = content
    for start, end, new_block in sorted(replacements, key=lambda x: x[0], reverse=True):
        new_content = new_content[:start] + new_block + new_content[end:]

    if new_content != content:
        if not dry_run:
            gn_path.write_text(new_content, encoding='utf-8')
        print(f"    [GN] {gn_path.relative_to(gn_path.parents[4]) if len(gn_path.parts) > 4 else gn_path}")


# =============================================================================
# Phase 5.5: 清理扫描根下所有残留的 source-compiled 目标
# =============================================================================

def cleanup_remaining_source_targets(ohos_root: Path, scan_roots: List[str],
                                     dry_run: bool = False) -> int:
    """
    Phase 6 会删除 scan roots 下的所有源文件。
    此函数在 Phase 6 之前，将所有 BUILD.gn 中残留的
    ohos_shared_library / ohos_executable / ohos_static_library 目标替换为注释，
    防止 partner 编译时因源文件不存在而报错。
    已被 rewrite_build_gn 处理过的文件不会被重复修改。
    """
    count = 0
    pattern = re.compile(
        r'(ohos_shared_library|ohos_executable|ohos_static_library)\s*\(\s*"([^"]+)"\s*\)\s*\{'
    )

    for scan_root in scan_roots:
        root = ohos_root / scan_root
        if not root.exists():
            continue
        for gn_path in root.rglob('BUILD.gn'):
            content = gn_path.read_text(encoding='utf-8', errors='replace')
            if not pattern.search(content):
                continue  # 没有残留 source 目标

            # 只处理已有 ohos_prebuilt_ 目标的文件（说明 Phase 4/5 已部分转换）
            # 未转换的文件（如当前产品不包含的组件）保留原样，避免破坏其他产品的编译
            if 'ohos_prebuilt_' not in content:
                continue

            replacements = []
            for m in pattern.finditer(content):
                target_name = m.group(2)
                target_type = m.group(1)
                brace_pos = content.index('{', m.start())
                block_end = extract_block(content, brace_pos)
                if block_end == -1:
                    continue
                comment = f'# {target_type}("{target_name}") removed (sources deleted by transform_sdk.py)'
                replacements.append((m.start(), block_end, comment))

            if not replacements:
                continue

            new_content = content
            for start, end, comment in sorted(replacements, key=lambda x: x[0], reverse=True):
                new_content = new_content[:start] + comment + new_content[end:]

            if new_content != content:
                if not dry_run:
                    gn_path.write_text(new_content, encoding='utf-8')
                count += len(replacements)

    return count



def cleanup_unused_file_scope_vars(ohos_root: Path, scan_roots: List[str],
                                   dry_run: bool = False) -> int:
    """
    移除已删除目标留下的孤立文件级变量赋值（如 hdf_hdi_service_path = ...）。
    当 cleanup_remaining_source_targets 移除了使用某变量的目标后，
    该变量可能在 BUILD.gn 中变成未引用状态，导致 GN 报 "Assignment had no effect"。

    策略：对于每个 BUILD.gn，找出文件顶部（第一个 group/target 定义之前）的
    简单赋值行（格式: var = "..."），若该变量名（$var 形式）在文件剩余内容中
    未被引用，则删除该行。
    """
    # 只清理已被 cleanup_remaining_source_targets 修改过的文件（含注释标记）
    REMOVED_MARKER = 'removed (sources deleted by transform_sdk.py)'
    VAR_ASSIGN = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"[^"]*"\s*$')

    count = 0
    for scan_root in scan_roots:
        root = ohos_root / scan_root
        if not root.exists():
            continue
        for gn_path in root.rglob('BUILD.gn'):
            text = gn_path.read_text(encoding='utf-8', errors='replace')
            if REMOVED_MARKER not in text:
                continue  # 该文件未被 Phase 5.5 处理，跳过

            lines = text.splitlines(keepends=True)
            lines_to_remove = set()

            # 跟踪花括号深度，只处理文件顶层（depth=0）的变量赋值
            depth = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                # 更新深度（跳过注释行）
                if not stripped.startswith('#'):
                    depth += stripped.count('{') - stripped.count('}')
                # 只处理顶层（depth == 0）赋值，target block 内的属性不动
                if depth != 0:
                    continue
                m = VAR_ASSIGN.match(stripped)
                if not m:
                    continue
                var_name = m.group(1)
                # 跳过常见的有效顶级变量
                if var_name in ('import',):
                    continue
                # 检查 $var_name 是否在文件其余部分出现
                rest = ''.join(lines[i+1:])
                if '$' + var_name not in rest and var_name + '(' not in rest:
                    lines_to_remove.add(i)
                    count += 1

            if not lines_to_remove:
                continue

            new_lines = [l for i, l in enumerate(lines) if i not in lines_to_remove]
            new_text = ''.join(new_lines)
            if not dry_run:
                gn_path.write_text(new_text, encoding='utf-8')

    return count


# =============================================================================

# =============================================================================
# Phase 5.5.2: cleanup_group_deps_to_removed_targets
# =============================================================================

def cleanup_group_deps_to_removed_targets(ohos_root, scan_roots, dry_run=False):
    # Remove deps in group() blocks that reference deleted source targets.
    # Deleted targets appear as: # ohos_shared_library("name") removed ...
    removed_marker = re.compile(
        r'^#\s+(?:ohos_shared_library|ohos_executable|ohos_static_library)\s*\("([^"]+)"\)\s+removed'
    )
    group_block = re.compile(r'group\s*\(\s*"[^"]+"\s*\)\s*\{')

    count = 0
    for scan_root in scan_roots:
        root = ohos_root / scan_root
        if not root.exists():
            continue
        for gn_path in root.rglob('BUILD.gn'):
            text = gn_path.read_text(encoding='utf-8', errors='replace')
            removed_names = set()
            for line in text.splitlines():
                m = removed_marker.match(line.strip())
                if m:
                    removed_names.add(m.group(1))
            if not removed_names:
                continue
            lines = text.splitlines(keepends=True)
            removed_indices = set()
            i = 0
            while i < len(lines):
                if group_block.search(lines[i]):
                    j, depth = i + 1, 1
                    while j < len(lines) and depth > 0:
                        m2 = re.match(r'\s*":([\w@.+-]+)",?\s*$', lines[j])
                        if m2 and m2.group(1) in removed_names:
                            removed_indices.add(j)
                        depth += lines[j].count('{') - lines[j].count('}')
                        j += 1
                i += 1
            if removed_indices:
                new_lines = [l for idx, l in enumerate(lines) if idx not in removed_indices]
                if not dry_run:
                    gn_path.write_text(''.join(new_lines), encoding='utf-8')
                try:
                    rel = gn_path.relative_to(ohos_root)
                except ValueError:
                    rel = gn_path
                print(f'    [GROUP] 清理 {len(removed_indices)} 处 dep 引用: {rel}')
                count += len(removed_indices)
    return count

# Phase 5.6: 清理 bundle.json 中对已删除 target 的 test 引用
# =============================================================================

def cleanup_bundle_json_test_refs(ohos_root: Path, scan_roots: List[str],
                                   removed_targets: List['TargetInfo'],
                                   dry_run: bool = False) -> int:
    """
    清理扫描根下 bundle.json 文件中对已删除 source target 的 test 引用。

    当 transform 把某个 source target 注释掉（无产物），bundle.json 的
    sub_component.test 数组仍残留对它的引用，导致 GN 报"找不到目标"。

    removed_targets: Phase 3 中未找到产物（skipped）的 TargetInfo 列表。
    返回清理的引用数量。
    """
    # 构建已删除 target 的 GN label 集合（格式：//path/to/dir:target_name）
    removed_labels: set = set()
    for t in removed_targets:
        try:
            gn_dir = t.build_gn_path.parent.relative_to(ohos_root).as_posix()
        except ValueError:
            # 通过符号链接访问到 ohos_root 外的路径，解析真实路径后重新计算
            real_dir = t.build_gn_path.parent.resolve()
            try:
                # 外层 vendor/ 相对于 ohos_root.parent
                gn_dir_full = real_dir.relative_to(ohos_root.parent).as_posix()
                # 去掉 'ohos5/' 前缀（若有），使 label 与 BUILD.gn 内部一致
                if gn_dir_full.startswith('ohos5/'):
                    gn_dir = gn_dir_full[len('ohos5/'):]
                else:
                    gn_dir = gn_dir_full
            except ValueError:
                continue
        removed_labels.add(f'//{gn_dir}:{t.target_name}')

    # 补充：从 BUILD.gn 文件中扫描被 Phase 5.5 移除的 target
    # (这些 target 有 "removed" 注释但不在 skipped 列表里，因为是 Phase 5.5 处理的)
    import re as _re
    REMOVED_MARKER_56 = _re.compile(
        r'^\s*#\s+(?:ohos_shared_library|ohos_executable|ohos_static_library|ohos_prebuilt_shared_library)\s*\("([^"]+)"\)\s+removed'
    )
    for scan_root in scan_roots:
        root = ohos_root / scan_root
        if not root.exists():
            continue
        for gn_path in root.rglob('BUILD.gn'):
            try:
                gn_dir = gn_path.parent.relative_to(ohos_root).as_posix()
            except ValueError:
                continue
            for line in gn_path.read_text(encoding='utf-8', errors='replace').splitlines():
                m56 = REMOVED_MARKER_56.match(line.strip())
                if m56:
                    removed_labels.add(f'//{gn_dir}:{m56.group(1)}')

    if not removed_labels:
        return 0

    count = 0
    for scan_root in scan_roots:
        root = ohos_root / scan_root
        if not root.exists():
            continue
        for bundle_path in root.rglob('bundle.json'):
            try:
                text = bundle_path.read_text(encoding='utf-8')
                data = json.loads(text)
            except Exception:
                continue

            modified = False
            # bundle.json 格式：component.build.test 是 label 列表
            build_section = data.get('component', {}).get('build', {})
            test_list = build_section.get('test', [])
            if test_list:
                new_test = [lbl for lbl in test_list if lbl not in removed_labels]
                if len(new_test) != len(test_list):
                    build_section['test'] = new_test
                    modified = True
                    count += len(test_list) - len(new_test)

            if modified:
                try:
                    rel = bundle_path.relative_to(ohos_root)
                except ValueError:
                    rel = bundle_path
                print(f"    [BUNDLE] 清理 test 引用: {rel}")
                if not dry_run:
                    bundle_path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8'
                    )

    return count


# =============================================================================
# Phase 5.7: 修正 deps_guard 白名单（预编译 HDI 模块）
# =============================================================================

def fixup_depsgard_hdi_whitelist(ohos_root, dry_run=False):
    """
    将已知的预编译 HDI driver 模块添加到 deps_guard 的 NO-Depends-On-HDI 白名单。

    背景：部分模块在 HCS device_info 中被标记为 hdi_service，但其 BUILD.gn 使用
    ohos_prebuilt_shared_library（不支持 shlib_type 属性）。
    在增量编译场景（out/ 目录已有上一轮产物）中，deps_guard 会因此报 [NOT ALLOWED]。
    将其加入白名单可跳过该检查。
    """
    import json as _json

    WHITELIST_ENTRIES = [
        "libdisplay_hwgraphics_driver_1.0.z.so",
    ]

    whitelist_path = (
        ohos_root
        / 'developtools/integration_verification/tools/deps_guard'
        / 'rules/NO-Depends-On-HDI/whitelist.json'
    )

    if not whitelist_path.exists():
        print(f"    [FIXUP] 白名单文件不存在，跳过: {whitelist_path}")
        return 0

    data = _json.loads(whitelist_path.read_text(encoding='utf-8'))
    added = 0
    for entry in WHITELIST_ENTRIES:
        if entry not in data:
            data.append(entry)
            added += 1
            print(f"    [FIXUP] 已加入白名单: {entry}")
        else:
            print(f"    [FIXUP] 已在白名单中，跳过: {entry}")

    if added > 0 and not dry_run:
        whitelist_path.write_text(
            _json.dumps(data, indent="	", ensure_ascii=False),
            encoding='utf-8'
        )

    return added


# =============================================================================
# Phase 6: 删除源文件
# =============================================================================

def delete_source_files(ohos_root: Path, scan_roots: List[str],
                        dry_run: bool = False) -> int:
    """
    删除扫描根下的 C/C++ 源文件。
    - KEEP_SOURCE_WHITELIST 中的文件保留
    - EXCLUDE_WITHIN_SCAN_ROOT 中的子目录保留（平台扩展源码）
    注意：scan_root 本身可能是符号链接（如 device/soc/hisilicon/huanglong/vendor/huanglong
    → 外层 vendor/huanglong/），rglob 会跟随进入，通过 rel_to_root 做子目录排除。
    返回删除数量。
    """
    count = 0
    for scan_root in scan_roots:
        root = ohos_root / scan_root
        if not root.exists():
            continue
        for f in root.rglob('*'):
            if not f.is_file() or f.suffix not in SOURCE_EXTS:
                continue

            # 相对于 scan_root 的路径，用于 EXCLUDE_WITHIN_SCAN_ROOT 检查
            try:
                rel_to_root = f.relative_to(root).as_posix()
            except ValueError:
                continue
            if any(rel_to_root == exc or rel_to_root.startswith(exc + '/')
                   for exc in EXCLUDE_WITHIN_SCAN_ROOT):
                continue

            # 如果同目录的 BUILD.gn 没有 ohos_prebuilt_ 目标（未被 Phase 4/5 转换），
            # 说明此组件不属于当前产品，保留其源文件（供其他产品编译使用）
            build_gn = f.parent / 'BUILD.gn'
            if build_gn.exists():
                bgn_text = build_gn.read_text(encoding='utf-8', errors='replace')
                if 'ohos_prebuilt_' not in bgn_text and 'removed (sources deleted by transform_sdk.py)' not in bgn_text:
                    continue

            # 相对于 ohos_root 的路径，用于 KEEP_SOURCE_WHITELIST 检查
            try:
                rel = f.relative_to(ohos_root).as_posix()
            except ValueError:
                # 通过符号链接访问到 ohos_root 外的路径，用真实绝对路径做字符串拼接
                rel = f.resolve().as_posix()
            if rel in KEEP_SOURCE_WHITELIST:
                continue

            if not dry_run:
                f.unlink()
            count += 1
    return count




# =============================================================================
# Phase 5.9: 修复 ohos_prebuilt_* 中 source 引用 //out/ 路径
# =============================================================================

def fix_prebuilt_out_source_paths(ohos_root, scan_roots, board, dry_run=False):
    # 扫描 ohos_prebuilt_* 目标中 source = "//out/..." 路径，
    # 将对应文件已经拷贝到 device/ 的引用更新为 //device/... 路径。
    import re as _re
    source_pat = _re.compile(r'(source\s*=\s*"//out/)([^"]+)(")')
    count = 0
    for scan_root in scan_roots:
        root = ohos_root / scan_root
        if not root.exists():
            continue
        for gn_path in root.rglob('BUILD.gn'):
            text = gn_path.read_text(encoding='utf-8', errors='replace')
            if '//out/' not in text:
                continue
            new_text = text
            for m in source_pat.finditer(text):
                raw_path = m.group(2)
                resolved = raw_path.replace('${soc_name}', board).replace('$soc_name', board)
                device_file = ohos_root / 'device' / resolved
                if device_file.exists():
                    old = m.group(0)
                    new = m.group(1).replace('//out/', '//device/') + resolved + m.group(3)
                    new_text = new_text.replace(old, new, 1)
                    count += 1
                    print(f'    [OUT->DEVICE] {gn_path.name}: {resolved}')
                else:
                    # 尝试从 out/ 拷贝
                    src_file = ohos_root / 'out' / resolved
                    if src_file.exists() and not dry_run:
                        device_file.parent.mkdir(parents=True, exist_ok=True)
                        import shutil as _shutil
                        _shutil.copy2(src_file, device_file)
                        old = m.group(0)
                        new = m.group(1).replace('//out/', '//device/') + resolved + m.group(3)
                        new_text = new_text.replace(old, new, 1)
                        count += 1
                        print(f'    [COPY] {src_file.name} -> device/{resolved}')
            if new_text != text and not dry_run:
                gn_path.write_text(new_text, encoding='utf-8')
    return count

# =============================================================================
# Phase 7: Kernel & Bootloader
# =============================================================================

def handle_kernel_bootloader(ohos_root: Path, board: str, chip_revision: str,
                              out_dir: Path, dry_run: bool = False):
    """拷贝内核镜像、ko 模块、bootloader 镜像；改写构建脚本。"""
    rev = chip_revision
    images_dir = out_dir / 'packages' / 'phone' / 'images'
    kernel_prebuilt  = ohos_root / 'device' / board / 'kernel'
    bootloader_prebuilt = ohos_root / 'device' / board / 'bootloader'

    # --- 内核镜像 ---
    for img in [f'boot_{rev}.img', f'dtbo_{rev}.img']:
        src = images_dir / img
        if src.exists():
            dest = kernel_prebuilt / img
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            print(f"    [KERNEL] {img}")
        else:
            print(f"    [WARN] 内核镜像未找到: {src}")

    # --- ko 模块（保留相对路径，以便 build_kernel.sh 恢复到 KERNEL_OBJ_D）---
    ko_obj_dir = out_dir / 'obj' / f'KERNEL_OBJ_{rev.upper()}'
    if ko_obj_dir.exists():
        ko_modules_dest = kernel_prebuilt / 'modules'
        for ko in ko_obj_dir.rglob('*.ko'):
            rel = ko.relative_to(ko_obj_dir)
            dest_ko = ko_modules_dest / rel
            if not dry_run:
                dest_ko.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ko, dest_ko)
        print(f"    [KERNEL] ko 模块已拷贝到 device/{board}/kernel/modules/")
    else:
        print(f"    [WARN] KERNEL_OBJ 目录未找到: {ko_obj_dir}")

    # --- bootloader 镜像 ---
    for bin_name in [f'fastboot_{rev}.bin', f'slaveboot_{rev}.bin', f'sbl_{rev}.bin']:
        src = images_dir / bin_name
        if src.exists():
            dest = bootloader_prebuilt / bin_name
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            print(f"    [BOOT] {bin_name}")
        else:
            print(f"    [WARN] bootloader 镜像未找到: {src}")
    # programmer_d.bin（无版本后缀，按存在与否拷贝）
    src = images_dir / 'programmer_d.bin'
    if src.exists():
        dest = bootloader_prebuilt / 'programmer_d.bin'
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        print(f"    [BOOT] programmer_d.bin")
    else:
        print(f"    [INFO] programmer_d.bin 不存在，本产品跳过")

    # --- 改写构建脚本 ---
    _rewrite_build_kernel_sh(ohos_root, board, rev, dry_run)
    _rewrite_build_bootloader_sh(ohos_root, board, rev, dry_run)


def _rewrite_build_kernel_sh(ohos_root: Path, board: str, rev: str, dry_run: bool):
    """将 build_kernel.sh 替换为从预编译目录拷贝的版本。"""
    kernel_sh = (ohos_root / 'device/soc/hisilicon/huanglong/vendor/huanglong'
                 '/linux/scripts/ohos/build_kernel.sh')
    if not kernel_sh.exists():
        print(f"    [WARN] build_kernel.sh 未找到，跳过")
        return

    # 参数接口与原脚本相同：$1=root_dir(绝对) $2=root_build_dir(相对root_dir) $3=PRODUCT_TYPE $4=CHIP_VERSION $5=CHIP_REVISION
    # 注意：ninja从out/目录执行脚本，$2是相对路径，必须与$1拼接才能得到正确绝对路径
    new_script = f'''#!/bin/bash
# Prebuilt kernel script (generated by transform_sdk.py)
# 参数接口与原 build_kernel.sh 相同，直接拷贝预编译产物
set -euo pipefail

TOP=$(dirname $0)/../../../../../../../../../
TOP=$(cd "$TOP" && pwd)

# $1=root_dir(绝对路径), $2=root_build_dir(相对于root_dir，如 out/wudangstick)
# ninja从out/目录执行，$2是相对路径，需与$1拼接得到绝对路径
OUT_ROOT="${{1%/}}/$2"
CHIP_REVISION=${{{5}:-{rev}}}

# 从 out 路径动态解析 board（如 out/wudangstick → wudangstick），支持多产品共用同一脚本
BOARD=$(basename "$2")
PREBUILT_DIR="$TOP/device/$BOARD/kernel"
KO_SRC_DIR="$PREBUILT_DIR/modules"

echo "[PREBUILT] Copying kernel images from $PREBUILT_DIR"
mkdir -p "$OUT_ROOT/packages/phone/images"
mkdir -p "$OUT_ROOT/obj/KERNEL_OBJ_${{CHIP_REVISION^^}}"

# 拷贝内核镜像
cp "$PREBUILT_DIR/boot_${{CHIP_REVISION}}.img"  "$OUT_ROOT/packages/phone/images/"
cp "$PREBUILT_DIR/dtbo_${{CHIP_REVISION}}.img"  "$OUT_ROOT/packages/phone/images/"

# 恢复 ko 模块（保持 KERNEL_OBJ_D 相对路径结构）
if [ -d "$KO_SRC_DIR" ]; then
    echo "[PREBUILT] Restoring ko modules to KERNEL_OBJ_${{CHIP_REVISION^^}}"
    KO_DEST="$OUT_ROOT/obj/KERNEL_OBJ_${{CHIP_REVISION^^}}"
    find "$KO_SRC_DIR" -name "*.ko" | while read ko; do
        rel="${{ko#$KO_SRC_DIR/}}"
        dest="$KO_DEST/$rel"
        mkdir -p "$(dirname "$dest")"
        cp "$ko" "$dest"
    done
fi

echo "[PREBUILT] build_kernel done."
'''
    if not dry_run:
        kernel_sh.write_text(new_script, encoding='utf-8')
        kernel_sh.chmod(0o755)
    print(f"    [KERNEL] build_kernel.sh 已改写为预编译版本")


def _rewrite_build_bootloader_sh(ohos_root: Path, board: str, rev: str, dry_run: bool):
    """将 build_bootloader.sh 替换为从预编译目录拷贝的版本。"""
    boot_sh = (ohos_root / 'device/soc/hisilicon/huanglong/vendor/huanglong'
               '/bootloader/build/build_bootloader.sh')
    if not boot_sh.exists():
        print(f"    [WARN] build_bootloader.sh 未找到，跳过")
        return

    # 参数接口：$1=TOP $2=PRODUCT_OUT $3=CHIP_VERSION $4=CHIP_REVISION
    new_script = f'''#!/bin/bash
# Prebuilt bootloader script (generated by transform_sdk.py)
# 参数接口与原 build_bootloader.sh 相同
set -euo pipefail

TOP=$1
PRODUCT_OUT=$2
CHIP_REVISION=${{{4}:-{rev}}}

# 从 PRODUCT_OUT 路径动态解析 board（如 out/wudangstick → wudangstick），支持多产品共用同一脚本
BOARD=$(basename "$PRODUCT_OUT")
PREBUILT_DIR="$TOP/device/$BOARD/bootloader"
DEST_DIR="$TOP/$PRODUCT_OUT/packages/phone/images"

echo "[PREBUILT] Copying bootloader images from $PREBUILT_DIR"
mkdir -p "$DEST_DIR"

for img in fastboot_${{CHIP_REVISION}}.bin slaveboot_${{CHIP_REVISION}}.bin sbl_${{CHIP_REVISION}}.bin programmer_${{CHIP_REVISION}}.bin; do
    if [ -f "$PREBUILT_DIR/$img" ]; then
        cp "$PREBUILT_DIR/$img" "$DEST_DIR/"
        echo "[PREBUILT] Copied $img"
    fi
done

echo "[PREBUILT] build_bootloader done."
'''
    if not dry_run:
        boot_sh.write_text(new_script, encoding='utf-8')
        boot_sh.chmod(0o755)
    print(f"    [BOOT] build_bootloader.sh 已改写为预编译版本")



# =============================================================================
# Phase 5.10: 修复 rtkbt_wifi 缺少 libbt_vendor 依赖
# =============================================================================

def fix_rtkbt_wifi_libbt_vendor(ohos_root: Path, product: str, dry_run: bool = False) -> bool:
    """
    transform 后 rtkbt_wifi group 的 libbt_vendor_rtk 被移除。
    支持两种场景：
      - 735: bluetooth/BUILD.gn 有 ohos_prebuilt_shared_library("libbt_vendor")
      - 730: wifi_firmware/BUILD.gn 有 ohos_prebuilt_etc("libbt_vendor")
    将对应 dep 加入 rtkbt_wifi group。
    """
    rtkbt_gn = ohos_root / 'vendor' / 'hisilicon' / product / 'rtkbt_wifi' / 'BUILD.gn'
    if not rtkbt_gn.exists():
        return False

    # 确定 dep 来源（优先 bluetooth，其次 wifi_firmware）
    dep_to_add = None
    bt_gn = ohos_root / 'vendor' / 'hisilicon' / product / 'bluetooth' / 'BUILD.gn'
    wf_gn = ohos_root / 'vendor' / 'hisilicon' / product / 'wifi_firmware' / 'BUILD.gn'
    if bt_gn.exists():
        bt_content = bt_gn.read_text()
        if 'ohos_prebuilt_shared_library("libbt_vendor")' in bt_content:
            dep_to_add = '    "//vendor/hisilicon/' + product + '/bluetooth:libbt_vendor",'
    if dep_to_add is None and wf_gn.exists():
        wf_content = wf_gn.read_text()
        if ('ohos_prebuilt_etc("libbt_vendor")' in wf_content or
                'ohos_prebuilt_shared_library("libbt_vendor")' in wf_content):
            dep_to_add = '    "//vendor/hisilicon/' + product + '/wifi_firmware:libbt_vendor",'
    if dep_to_add is None:
        print("    [SKIP] rtkbt_wifi: 未找到 libbt_vendor prebuilt 目标，跳过")
        return False

    rtkbt_content = rtkbt_gn.read_text()
    if dep_to_add in rtkbt_content:
        return False  # 已修复

    old_tail = '    ":rtl8822c_fw",' + chr(10) + '  ]' + chr(10) + '}'
    new_tail = '    ":rtl8822c_fw",' + chr(10) + dep_to_add + chr(10) + '  ]' + chr(10) + '}'
    if old_tail not in rtkbt_content:
        print("    [WARN] rtkbt_wifi BUILD.gn 结构与预期不符，跳过 Fix3")
        return False

    if not dry_run:
        rtkbt_gn.write_text(rtkbt_content.replace(old_tail, new_tail, 1))
        print(f"    [FIX] rtkbt_wifi: 已添加 {dep_to_add.strip()}")
    else:
        print(f"    [FIX] rtkbt_wifi: 将添加 {dep_to_add.strip()} (dry-run)")
    return True



# =============================================================================
# Phase 8.5: 修复 display_composer_model 缺少 libdisplay_utils_vendor dep
# =============================================================================

def fix_display_composer_deps(ohos_root: Path, dry_run: bool = False) -> bool:
    """
    display/source/BUILD.gn 中 display_composer_model group 缺少
    :libdisplay_utils_vendor dep（prebuilt 不在 dep chain 中）。
    该文件位于 symlink 目录，不能用 git apply，直接修改。
    """
    target = (ohos_root / 'device' / 'soc' / 'hisilicon' / 'huanglong' / 'vendor'
              / 'huanglong' / 'ohos' / 'hardware' / 'graphics' / 'display' / 'source' / 'BUILD.gn')
    if not target.exists():
        print('    [SKIP] display BUILD.gn 不存在，跳过')
        return False

    text = target.read_text()
    dep_line = '    ":libdisplay_utils_vendor",'
    if dep_line in text:
        print('    [SKIP] display_composer_model 已含 libdisplay_utils_vendor dep')
        return False

    NL = chr(10)
    old = (
        'group("display_composer_model") {' + NL
        + '  deps = [' + NL
        + '    ":libdisplay_composer_vdi_impl",' + NL
        + '    ":display_composer_vendor",' + NL
        + '    ":display_gfx",' + NL
        + '    ":display_vgu",' + NL
        + '  ]' + NL + '}'
    )
    new = (
        'group("display_composer_model") {' + NL
        + '  deps = [' + NL
        + '    ":libdisplay_composer_vdi_impl",' + NL
        + '    ":display_composer_vendor",' + NL
        + '    ":display_gfx",' + NL
        + '    ":display_vgu",' + NL
        + '    ":libdisplay_utils_vendor",' + NL
        + '  ]' + NL + '}'
    )
    if old not in text:
        print('    [WARN] display_composer_model group 结构与预期不符，跳过')
        return False
    if not dry_run:
        target.write_text(text.replace(old, new, 1))
        print('    [FIX] display_composer_model: 已添加 :libdisplay_utils_vendor dep')
    else:
        print('    [FIX] display_composer_model: 将添加 :libdisplay_utils_vendor dep (dry-run)')
    return True


def pre_apply_device_patches(ohos_root: Path, common_patch_dir: Path,
                              dry_run: bool = False):
    """
    将 custom-ohos-patch/device/ 下的所有 patch 预应用到 ohos_root，
    以便打包进 tar.gz。已应用的跳过。
    """
    device_patch_dir = common_patch_dir / 'custom-ohos-patch' / 'device'
    if not device_patch_dir.exists():
        print("    [PATCH] 无 device/ 自定义补丁，跳过")
        return

    patch_files = sorted(device_patch_dir.rglob('*.patch'))
    applied = skipped = failed = 0

    for patch_file in patch_files:
        # 计算 --directory 参数：patch 相对于 device_patch_dir 的父目录，
        # 前面加上 "device/" （即最终目标是 ohos_root/device/soc/hisilicon/...）
        rel_parent = patch_file.parent.relative_to(device_patch_dir)
        directory  = str(Path('device') / rel_parent) if str(rel_parent) != '.' else 'device'

        base_cmd = ['git', 'apply', f'--directory={directory}']

        # 检查是否已应用（reverse check）
        check_rev = subprocess.run(
            base_cmd + ['--check', '-R', str(patch_file)],
            cwd=str(ohos_root), capture_output=True
        )
        if check_rev.returncode == 0:
            skipped += 1
            continue  # 已应用，跳过

        # 检查是否可应用（forward check）
        check_fwd = subprocess.run(
            base_cmd + ['--check', str(patch_file)],
            cwd=str(ohos_root), capture_output=True
        )
        if check_fwd.returncode != 0:
            # 正向和反向检查都失败，说明内容已以不同方式合并到源码
            skipped += 1
            continue

        if not dry_run:
            result = subprocess.run(
                base_cmd + ['--whitespace=nowarn', str(patch_file)],
                cwd=str(ohos_root), capture_output=True
            )
            if result.returncode != 0:
                print(f"    [WARN] 应用失败: {patch_file.name}: {result.stderr.decode()}")
                failed += 1
            else:
                print(f"    [PATCH] 已应用: {patch_file.name}")
                applied += 1
        else:
            print(f"    [PATCH] 将应用: {patch_file.name}")
            applied += 1

    print(f"    [PATCH] 已应用 {applied}，已跳过 {skipped}，失败 {failed}")


# =============================================================================
# Phase 8.6: 修复 libuapi_frontend 缺少 frontend_config.ini dep
# =============================================================================

def fix_frontend_config_dep(ohos_root: Path, dry_run: bool = False) -> bool:
    """
    uapi/frontend/source/BUILD.gn 中 ohos_prebuilt_shared_library("libuapi_frontend")
    在 prebuilt 模式下没有对 frontend_config.ini 的 dep。
    源码编译时 GN 会自动生成 order-only dep，prebuilt 则不会。
    直接在 BUILD.gn 中添加 deps = [":frontend_config.ini"]。
    该文件位于 symlink 目录，不能用 git apply，直接修改。
    """
    target = (ohos_root / 'device' / 'soc' / 'hisilicon' / 'huanglong' / 'vendor'
              / 'huanglong' / 'uapi' / 'frontend' / 'source' / 'BUILD.gn')
    if not target.exists():
        print('    [SKIP] frontend source BUILD.gn 不存在，跳过')
        return False

    text = target.read_text()
    # Check if already fixed
    if '"frontend_config.ini"' in text and 'deps' in text.split('ohos_prebuilt_shared_library("libuapi_frontend")')[1].split('}')[0] if 'ohos_prebuilt_shared_library("libuapi_frontend")' in text else False:
        print('    [SKIP] libuapi_frontend 已含 frontend_config.ini dep')
        return False

    NL = chr(10)
    # Match the libuapi_frontend block and add deps
    old = (
        'ohos_prebuilt_shared_library("libuapi_frontend") {' + NL
        + '  source = "//device/${prebuilt_board_dir}/huanglong_products/device_soc_huanglong/libuapi_frontend.so"' + NL
        + '  install_images = [ "vendor", ]' + NL
        + '  public_configs = [ ":libuapi_frontend_config", ]' + NL
        + '  part_name = "device_soc_huanglong"' + NL
        + '  subsystem_name = "huanglong_products"' + NL
        + '}'
    )
    new = (
        'ohos_prebuilt_shared_library("libuapi_frontend") {' + NL
        + '  source = "//device/${prebuilt_board_dir}/huanglong_products/device_soc_huanglong/libuapi_frontend.so"' + NL
        + '  install_images = [ "vendor", ]' + NL
        + '  public_configs = [ ":libuapi_frontend_config", ]' + NL
        + '  deps = [ ":frontend_config.ini" ]' + NL
        + '  part_name = "device_soc_huanglong"' + NL
        + '  subsystem_name = "huanglong_products"' + NL
        + '}'
    )
    if old not in text:
        print('    [WARN] libuapi_frontend 块结构与预期不符，跳过 (可能已是源码编译或结构不同)')
        return False
    if not dry_run:
        target.write_text(text.replace(old, new, 1))
        print('    [FIX] libuapi_frontend: 已添加 deps = [":frontend_config.ini"]')
    else:
        print('    [FIX] libuapi_frontend: 将添加 deps (dry-run)')
    return True


# =============================================================================
# Phase 5.11: TEE/secure_c 平台库改造为预编译拷贝
# =============================================================================

def convert_platform_libs_to_prebuilt(ohos_root: Path, out_dir: Path,
                                      dry_run: bool = False) -> int:
    """
    将 vendor/platform/ 下仍以源码方式编译的平台库改造为预编译拷贝：

    1. libteec_vendor:
       - 产物: out/<board>/huanglong_products/libteec_vendor/{libteec_vendor.so,teecd,tlogcat}
       - 目标: vendor/huanglong/binary/platform/libteec_vendor/ohos3.2/{lib64/,bin64/}
       - 创建 BUILD.gn（ohos_prebuilt_shared_library + ohos_prebuilt_executable）
       - 修改 product.gni: source:libteec_vendor → prebuilt_part.gni 中的引用

    2. secure_c:
       - 产物: out/<board>/huanglong_products/libuapi_securec/libuapi_securec.so
       - 目标: vendor/huanglong/binary/platform/secure_c/ohos3.2/lib64/
       - 创建 BUILD.gn + part.gni
       - 修改 product.gni: $securec_lib → prebuilt 引用

    3. pdmtool:
       - 产物: out/<board>/huanglong_products/pdmtool/pdmtool
       - 修改 vendor/tools/board/huanglong/pdm/BUILD.gn 为 ohos_prebuilt_executable

    返回已处理的模块数量。
    """
    count = 0

    # ---------- 读取 product.gni（通过 os 变量确定子目录） ----------
    # os 变量从 product.gni 读取，用于确定 binary 目录名
    # 默认 ohos3.2（主流 OHOS5 版本）
    os_name = 'ohos3.2'
    product_gni_candidates = list(ohos_root.glob('vendor/hisilicon/*/product.gni'))
    for pg in product_gni_candidates:
        m = re.search(r'^os\s*=\s*"([^"]+)"', pg.read_text(), re.MULTILINE)
        if m:
            os_name = m.group(1)
            break

    binary_platform_dir = ohos_root / 'device' / 'soc' / 'hisilicon' / 'huanglong' / 'vendor' / 'huanglong' / 'binary' / 'platform'

    # ===== 1. libteec_vendor =====
    src_dir = out_dir / 'huanglong_products' / 'libteec_vendor'
    so_src  = src_dir / 'libteec_vendor.so'
    teecd_src   = src_dir / 'teecd'
    tlogcat_src = src_dir / 'tlogcat'

    if so_src.exists() and teecd_src.exists():
        dest_base = binary_platform_dir / 'libteec_vendor' / os_name
        lib64_dir = dest_base / 'lib64'
        bin64_dir = dest_base / 'bin64'

        if not dry_run:
            lib64_dir.mkdir(parents=True, exist_ok=True)
            bin64_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(so_src,      lib64_dir / 'libteec_vendor.so')
            shutil.copy2(teecd_src,   bin64_dir / 'teecd')
            shutil.copy2(tlogcat_src, bin64_dir / 'tlogcat')

            build_gn = dest_base / 'BUILD.gn'
            build_gn.write_text(
                'import("//build/ohos.gni")\n'
                'import("//vendor/${product_company}/${product_name}/product.gni")\n\n'
                'ohos_prebuilt_shared_library("libteec_vendor") {\n'
                '  part_name = "libteec_vendor"\n'
                '  install_images = [ "vendor" ]\n'
                '  source = "lib64/libteec_vendor.so"\n'
                '}\n\n'
                'ohos_prebuilt_executable("teecd") {\n'
                '  part_name = "libteec_vendor"\n'
                '  install_enable = true\n'
                '  install_images = [ "vendor" ]\n'
                '  source = "bin64/teecd"\n'
                '}\n\n'
                'ohos_prebuilt_executable("tlogcat") {\n'
                '  part_name = "libteec_vendor"\n'
                '  install_enable = true\n'
                '  install_images = [ "vendor" ]\n'
                '  source = "bin64/tlogcat"\n'
                '}\n'
            )

        # 修改 product.gni：将 source:libteec_vendor → prebuilt_part.gni 中的路径
        for pg in product_gni_candidates:
            text = pg.read_text()
            old = f'"$sdk_dir/vendor/platform/libteec_vendor/source:libteec_vendor"'
            new = f'"$sdk_dir/vendor/huanglong/binary/platform/libteec_vendor/{os_name}:libteec_vendor"'
            if old in text and new not in text:
                if not dry_run:
                    pg.write_text(text.replace(old, new, 1))
                print(f'    [FIX] libteec_vendor: product.gni → prebuilt ({pg.name})')

        print(f'    [OK] libteec_vendor: .so + teecd + tlogcat → binary/platform/libteec_vendor/{os_name}/')
        count += 1
    else:
        print(f'    [SKIP] libteec_vendor: 产物不存在，跳过 ({so_src})')

    # ===== 2. secure_c (libuapi_securec) =====
    sec_so_src = out_dir / 'huanglong_products' / 'libuapi_securec' / 'libuapi_securec.so'

    if sec_so_src.exists():
        dest_base = binary_platform_dir / 'secure_c' / os_name
        lib64_dir = dest_base / 'lib64'

        if not dry_run:
            lib64_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sec_so_src, lib64_dir / 'libuapi_securec.so')

            build_gn = dest_base / 'BUILD.gn'
            build_gn.write_text(
                'import("//build/ohos.gni")\n'
                'import("//vendor/${product_company}/${product_name}/product.gni")\n\n'
                'ohos_prebuilt_shared_library("libuapi_securec") {\n'
                '  part_name = "libuapi_securec"\n'
                '  install_images = [ "vendor" ]\n'
                '  source = "lib64/libuapi_securec.so"\n'
                '}\n'
            )

            part_gni = dest_base.parent / 'part.gni'
            part_gni.write_text(
                'import("//build/ohos.gni")\n'
                'import("//vendor/${product_company}/${product_name}/base.gni")\n\n'
                f'libuapi_securec = "$sdk_dir/vendor/huanglong/binary/platform/secure_c/{os_name}:libuapi_securec"\n'
            )

        # 修改 product.gni：将 securec_lib 改为指向 prebuilt
        for pg in product_gni_candidates:
            text = pg.read_text()
            # securec_lib = "//third_party/bounds_checking_function:libsec_shared"
            old_sec = '= "$securec_lib"'
            new_sec = f'= "$sdk_dir/vendor/huanglong/binary/platform/secure_c/{os_name}:libuapi_securec"'
            # 只改 libuapi_securec 那行
            old_line = f'libuapi_securec = "$securec_lib"'
            new_line = f'libuapi_securec = "$sdk_dir/vendor/huanglong/binary/platform/secure_c/{os_name}:libuapi_securec"'
            if old_line in text and new_line not in text:
                if not dry_run:
                    pg.write_text(text.replace(old_line, new_line, 1))
                print(f'    [FIX] secure_c: product.gni libuapi_securec → prebuilt ({pg.name})')

        print(f'    [OK] secure_c: libuapi_securec.so → binary/platform/secure_c/{os_name}/')
        count += 1
    else:
        print(f'    [SKIP] secure_c: 产物不存在，跳过 ({sec_so_src})')

    # ===== 2b. device/soc/hisilicon/huanglong/bundle.json: secure_c inner_kits =====
    # device bundle.json 中 inner_kits 仍引用 secure_c/source，需改为 prebuilt 路径。
    huanglong_bundle = ohos_root / 'device' / 'soc' / 'hisilicon' / 'huanglong' / 'bundle.json'
    if huanglong_bundle.exists():
        text = huanglong_bundle.read_text()
        old_inner = '"name": "//device/soc/hisilicon/huanglong/vendor/platform/secure_c/source:libuapi_securec"'
        new_inner = f'"name": "//device/soc/hisilicon/huanglong/vendor/huanglong/binary/platform/secure_c/{os_name}:libuapi_securec"'
        if old_inner in text and new_inner not in text:
            if not dry_run:
                huanglong_bundle.write_text(text.replace(old_inner, new_inner, 1))
            print(f'    [FIX] huanglong/bundle.json secure_c inner_kits → prebuilt')
        elif new_inner in text:
            print(f'    [OK] huanglong/bundle.json secure_c inner_kits 已是 prebuilt')

    # ===== 3. pdmtool =====
    pdm_src = out_dir / 'huanglong_products' / 'pdmtool' / 'pdmtool'
    # pdm BUILD.gn 在 outer vendor（ohos_root/../vendor/），不是 ohos5/vendor/
    outer_vendor = ohos_root.parent / 'vendor'
    pdm_gn  = outer_vendor / 'tools' / 'board' / 'huanglong' / 'pdm' / 'BUILD.gn'

    if pdm_src.exists() and pdm_gn.exists():
        text = pdm_gn.read_text()
        if 'ohos_executable("pdmtool")' in text and 'ohos_prebuilt_executable' not in text:
            dest_bin = pdm_gn.parent / 'bin64' / 'pdmtool'
            if not dry_run:
                dest_bin.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pdm_src, dest_bin)
                # 整体替换 BUILD.gn（保留 import 行，替换 ohos_executable 为 prebuilt）
                imports = [l for l in text.splitlines() if l.startswith('import(')]
                new_text = '\n'.join(imports) + '\n\n'
                new_text += (
                    'ohos_prebuilt_executable("pdmtool") {\n'
                    '  part_name = "pdmtool"\n'
                    '  install_enable = true\n'
                    '  install_images = [ "vendor" ]\n'
                    '  source = "bin64/pdmtool"\n'
                    '}\n'
                )
                pdm_gn.write_text(new_text)
            print('    [OK] pdmtool: BUILD.gn → ohos_prebuilt_executable')
            count += 1
        else:
            print('    [SKIP] pdmtool: 已是 prebuilt 或不存在 ohos_executable')
    else:
        print(f'    [SKIP] pdmtool: 产物或 BUILD.gn 不存在')

    # ===== 4. device/soc/hisilicon/huanglong/BUILD.gn: build_teec group =====
    # board patch 会在 BUILD.gn 中添加引用 libteec_vendor/source 的 build_teec group，
    # 需将其改为指向 binary/platform prebuilt 目标。
    huanglong_gn = ohos_root / 'device' / 'soc' / 'hisilicon' / 'huanglong' / 'BUILD.gn'
    if huanglong_gn.exists():
        text = huanglong_gn.read_text()
        old_teec = (
            'group("build_teec") {\n'
            '  deps = [\n'
            '    "$sdk_dir/vendor/platform/libteec_vendor/source:libteec_vendor",\n'
            '    "$sdk_dir/vendor/platform/libteec_vendor/source:teecd",\n'
            '    "$sdk_dir/vendor/platform/libteec_vendor/source:tlogcat",\n'
            '    "$sdk_dir/vendor/platform/libteec_vendor/source:teecd_daemon.cfg",\n'
            '  ]\n'
            '}'
        )
        new_teec = (
            f'group("build_teec") {{\n'
            f'  deps = [\n'
            f'    "$sdk_dir/vendor/huanglong/binary/platform/libteec_vendor/{os_name}:libteec_vendor",\n'
            f'    "$sdk_dir/vendor/huanglong/binary/platform/libteec_vendor/{os_name}:teecd",\n'
            f'    "$sdk_dir/vendor/huanglong/binary/platform/libteec_vendor/{os_name}:tlogcat",\n'
            f'  ]\n'
            f'}}'
        )
        if old_teec in text and new_teec not in text:
            if not dry_run:
                huanglong_gn.write_text(text.replace(old_teec, new_teec, 1))
            print(f'    [FIX] huanglong/BUILD.gn build_teec → prebuilt')
            count += 1
        elif new_teec in text:
            print(f'    [OK] huanglong/BUILD.gn build_teec 已是 prebuilt')
        else:
            print(f'    [SKIP] huanglong/BUILD.gn build_teec pattern not found')

    return count


# =============================================================================
# 生成 partner apply_patches_sdk.sh
# =============================================================================

def generate_partner_apply_patches_sh(common_patch_dir: Path, output_path: Path,
                                      product: str, dry_run: bool = False, extra_products=None):
    """
    生成合作伙伴版 apply_patches_sdk.sh：
    1. 移除 PATCH_CUSTOM_SDK_VENDOR_DIR 相关内容
    2. 移除 apply_custom_sdk_vendor_patches() 函数和调用
    3. apply_custom_ohos_patches() 跳过 device/ 子目录
    4. upgrade_sdk() 额外提取并拷贝 ohos5/vendor/hisilicon/<product>/
    5. apply_other_patches() 跳过覆盖 vendor/hisilicon/<product>（已在 tar.gz 中）
    """
    original_path = common_patch_dir / 'apply_patches_sdk.sh'
    original = original_path.read_text(encoding='utf-8')

    modified = original

    # 0. Partner 脚本使用 git clean -df（不加 -x），保留 .gitignore 目录（如 node_modules）
    modified = modified.replace('git clean -q -dfx;', 'git clean -q -df;')

    # 1. 移除 PATCH_CUSTOM_SDK_VENDOR_DIR 变量定义
    modified = re.sub(
        r'\nPATCH_CUSTOM_SDK_VENDOR_DIR=.*\n',
        '\n',
        modified
    )

    # 2. 移除 check_directories() 中对 PATCH_CUSTOM_SDK_VENDOR_DIR 的检查块
    modified = re.sub(
        r'\n    if \[ ! -d \$PATCH_CUSTOM_SDK_VENDOR_DIR \];.*?fi\n',
        '\n',
        modified,
        flags=re.DOTALL
    )

    # 3. 移除 apply_custom_sdk_vendor_patches() 整个函数
    m = re.search(r'\napply_custom_sdk_vendor_patches\(\)\s*\{', modified)
    if m:
        brace_pos = modified.index('{', m.start() + 1)
        func_end = extract_block(modified, brace_pos)
        if func_end != -1:
            modified = modified[:m.start()] + modified[func_end:]

    # 4. 移除 main() 中的 apply_custom_sdk_vendor_patches 调用
    modified = re.sub(
        r'\n    apply_custom_sdk_vendor_patches\n',
        '\n',
        modified
    )

    # 5. 修改 apply_custom_ohos_patches() 跳过 device/ 子目录
    old_ergodic = '    PATCH_ROOT_PATH=$PATCH_CUSTOM_OHOS_DIR\n    ergodic_patch $PATCH_ROOT_PATH'
    new_ergodic = (
        '    PATCH_ROOT_PATH=$PATCH_CUSTOM_OHOS_DIR\n'
        '    # Partner SDK: device/ 补丁已预集成到 SDK 包中，跳过\n'
        '    for entry in $(ls "$PATCH_CUSTOM_OHOS_DIR"); do\n'
        '        if [ "$entry" = "device" ]; then\n'
        '            log_info "=== 跳过 device/ 补丁（已预集成到 SDK 包）==="\n'
        '            continue\n'
        '        fi\n'
        '        ergodic_patch "$PATCH_CUSTOM_OHOS_DIR/$entry"\n'
        '    done'
    )
    if old_ergodic in modified:
        modified = modified.replace(old_ergodic, new_ergodic)
    else:
        print("    [WARN] apply_custom_ohos_patches 内容与预期不符，请手动检查 partner 脚本")

    # 6. upgrade_sdk(): 额外提取 ohos5/vendor/hisilicon/<product>/ 并拷贝到 ohos5/
    old_tar = (
        f'    tar -zxf $COMMON_PATCH_DIR/$base_pkg -C $COMMON_PATCH_DIR/tmp/ '
        f'"./vendor" "./ohos5/device"\n'
        f'    cp -Rf $COMMON_PATCH_DIR/tmp/vendor/ $OHOS_PATH/../\n'
        f'    cp -Rf $COMMON_PATCH_DIR/tmp/ohos5/device/ $OHOS_PATH/'
    )
    _extra_tar_paths = "".join(
        f' "./ohos5/vendor/hisilicon/{ep}"' for ep in (extra_products or [])
    )
    _extra_cp_cmds = "".join(
        f'\n    cp -Rf $COMMON_PATCH_DIR/tmp/ohos5/vendor/hisilicon/{ep}/'
        f' $OHOS_PATH/vendor/hisilicon/'
        for ep in (extra_products or [])
    )
    new_tar = (
        f'    tar -zxf $COMMON_PATCH_DIR/$base_pkg -C $COMMON_PATCH_DIR/tmp/ '
        f'"./vendor" "./ohos5/device" "./ohos5/vendor/hisilicon/{product}"{_extra_tar_paths}'
        ' "./ohos5/common_patch/custom-ohos-patch/build/0002-fix-patch-idempotency.patch"'
        ' "./ohos5/common_patch/custom-ohos-patch/build/0003-add-prebuilt-board-dir.patch"'
        ' "./ohos5/common_patch/custom-ohos-patch/developtools/global_resource_tool/0001-fix-cstring-include.patch"\n'
        f'    cp -Rf $COMMON_PATCH_DIR/tmp/vendor/ $OHOS_PATH/../\n'
        f'    cp -Rf $COMMON_PATCH_DIR/tmp/ohos5/device/ $OHOS_PATH/\n'
        f'    mkdir -p $OHOS_PATH/vendor/hisilicon\n'
        f'    cp -Rf $COMMON_PATCH_DIR/tmp/ohos5/vendor/hisilicon/{product}/'
        f' $OHOS_PATH/vendor/hisilicon/{_extra_cp_cmds}'
        '\n    # 从 tar.gz 中覆盖 bundled patches（修复合作伙伴仓库中可能缺失的补丁）'
        '\n    mkdir -p $COMMON_PATCH_DIR/custom-ohos-patch/build'
        '\n    cp -f $COMMON_PATCH_DIR/tmp/ohos5/common_patch/custom-ohos-patch/build/0002-fix-patch-idempotency.patch $COMMON_PATCH_DIR/custom-ohos-patch/build/ 2>/dev/null || true'
        '\n    cp -f $COMMON_PATCH_DIR/tmp/ohos5/common_patch/custom-ohos-patch/build/0003-add-prebuilt-board-dir.patch $COMMON_PATCH_DIR/custom-ohos-patch/build/ 2>/dev/null || true'
        '\n    mkdir -p $COMMON_PATCH_DIR/custom-ohos-patch/developtools/global_resource_tool'
        '\n    cp -f $COMMON_PATCH_DIR/tmp/ohos5/common_patch/custom-ohos-patch/developtools/global_resource_tool/0001-fix-cstring-include.patch $COMMON_PATCH_DIR/custom-ohos-patch/developtools/global_resource_tool/ 2>/dev/null || true'
    )
    if old_tar in modified:
        modified = modified.replace(old_tar, new_tar)
    else:
        print("    [WARN] upgrade_sdk tar 命令与预期不符，请手动更新 partner 脚本中的 tar 提取命令")

    # 7. apply_other_patches(): 跳过覆盖 vendor/hisilicon/<product>（已由 tar.gz 提供）
    old_cp_product = (
        f'    cp -Rf $PATCH_OTHER_DIR/vendor_hisilicon/{product} $OHOS_PATH/vendor/hisilicon/'
    )
    new_cp_product = (
        f'    # Partner SDK: {product} BUILD.gn 已预集成到 SDK 包中，跳过（避免覆盖预编译版本）\n'
        f'    # cp -Rf $PATCH_OTHER_DIR/vendor_hisilicon/{product} $OHOS_PATH/vendor/hisilicon/'
    )
    if old_cp_product in modified:
        modified = modified.replace(old_cp_product, new_cp_product)
    else:
        print(f"    [WARN] apply_other_patches 中 {product} 的 cp 命令与预期不符，请手动检查")

    # 7b. 同样跳过额外产品的 cp 命令
    for ep in (extra_products or []):
        old_cp_ep = (
            f'    cp -Rf $PATCH_OTHER_DIR/vendor_hisilicon/{ep} $OHOS_PATH/vendor/hisilicon/'
        )
        new_cp_ep = (
            f'    # Partner SDK: {ep} BUILD.gn 已预集成到 SDK 包中，跳过\n'
            f'    # cp -Rf $PATCH_OTHER_DIR/vendor_hisilicon/{ep} $OHOS_PATH/vendor/hisilicon/'
        )
        if old_cp_ep in modified:
            modified = modified.replace(old_cp_ep, new_cp_ep)
        else:
            print(f"    [WARN] apply_other_patches 中 {ep} 的 cp 命令与预期不符，请手动检查")


    # 8. 插入 fix_depsgard_hdi_whitelist() 函数和调用（修复 deps_guard HDI 白名单）
    whitelist_func = (
        '\n'
        '# 修复 deps_guard HDI 白名单（预编译 HDI 模块在增量编译时误报 NOT ALLOWED）\n'
        'fix_depsgard_hdi_whitelist() {\n'
        '    local WHITELIST="$OHOS_PATH/developtools/integration_verification/tools/deps_guard/rules/NO-Depends-On-HDI/whitelist.json"\n'
        '    if [ ! -f "$WHITELIST" ]; then\n'
        '        log_info "whitelist.json 不存在，跳过 HDI 白名单修复"\n'
        '        return\n'
        '    fi\n'
        '    python3 - "$WHITELIST" << \'PYEOF\'\n'
        'import sys, json\n'
        'path = sys.argv[1]\n'
        'data = json.load(open(path))\n'
        'entries = ["libdisplay_hwgraphics_driver_1.0.z.so"]\n'
        'added = [e for e in entries if e not in data]\n'
        'if added:\n'
        '    data.extend(added)\n'
        '    json.dump(data, open(path, \'w\'), indent=\'\t\')\n'
        '    print("[INFO] HDI whitelist: 已添加", added)\n'
        'else:\n'
        '    print("[INFO] HDI whitelist: 条目已存在，无需修改")\n'
        'PYEOF\n'
        '}\n'
    )
    # 插入在 main() 函数之前
    main_marker = '# 主函数\nmain() {'
    if main_marker in modified:
        modified = modified.replace(main_marker, whitelist_func + '\n' + main_marker)
    else:
        print("    [WARN] main() 标记未找到，跳过白名单函数插入")

    # 在 apply_other_patches 之后、log_info 之前插入调用
    old_end = '    # 应用other patch\n    apply_other_patches\n\n    log_info "=== 所有操作完成 ==="'
    new_end = '    # 应用other patch\n    apply_other_patches\n\n    # 修复 deps_guard 白名单\n    fix_depsgard_hdi_whitelist\n\n    log_info "=== 所有操作完成 ==="'
    if old_end in modified:
        modified = modified.replace(old_end, new_end)
    else:
        print("    [WARN] main() 末尾模式未找到，跳过白名单调用插入")


    # 在文件顶部加注释
    header = (
        '# Partner SDK 版本 (generated by transform_sdk.py)\n'
        '# 变更：移除 custom-sdk-vendor-patch，device/ 补丁已预集成到 SDK 包，\n'
        f'#       {product}/ BUILD.gn 已预集成到 SDK 包（prebuilt 版本）\n'
    )
    modified = modified.replace('#!/bin/bash\n', f'#!/bin/bash\n{header}')

    # 9. Partner 脚本不需要删除 prebuilts/：prebuilts 是固定版本工具链，
    #    删除后重下载会导致 prebuilts_download.py 的 node_modules copy 时序问题
    modified = modified.replace(
        '    rm -Rf "$OHOS_PATH/prebuilts"\n',
        '    # Partner SDK: 保留 prebuilts/，避免 prebuilts_download.py 的 node_modules 时序问题\n',
    )

    # 10. 将注释掉的 prebuilts_download 改为条件检查（首次拉取自动安装）
    modified = modified.replace(
        '    # build/prebuilts_download.sh --pypi-url="http://mirrors.aliyun.com/pypi/simple/" --skip-ssl  # skip: prebuilts already installed\n',
        '    if [ ! -d "$OHOS_PATH/prebuilts/build-tools" ]; then\n'
        '        log_info "prebuilts 未安装，运行 prebuilts_download.sh..."\n'
        '        cd $OHOS_PATH && build/prebuilts_download.sh --pypi-url="http://mirrors.aliyun.com/pypi/simple/" --skip-ssl\n'
        '    fi\n',
    )

    if not dry_run:
        output_path.write_text(modified, encoding='utf-8')
        output_path.chmod(0o755)
    print(f"    [SH] 已生成 partner 脚本: {output_path.name}")


def inject_prebuilt_board_dir(ohos_root: Path, product: str, board: str, dry_run: bool = False):
    """
    向 vendor/hisilicon/<product>/product.gni 注入 prebuilt_board_dir 变量。
    此变量用于 shared device BUILD.gn 中的 source 路径，使同一 BUILD.gn 支持多产品。
    """
    gni_path = ohos_root / 'vendor' / 'hisilicon' / product / 'product.gni'
    if not gni_path.exists():
        print(f"    [WARN] product.gni 不存在，跳过注入: {gni_path}")
        return
    text = gni_path.read_text(encoding='utf-8')
    if 'prebuilt_board_dir' in text:
        print(f"    [OK] prebuilt_board_dir 已存在于 {gni_path.name} ({product})")
        return
    addition = '\nprebuilt_board_dir = "' + board + '"\n'
    if dry_run:
        print(f'    [DRY] 将写入 {gni_path}: prebuilt_board_dir = "{board}"')
        return
    gni_path.write_text(text.rstrip() + addition, encoding='utf-8')
    print(f'    [OK] 已注入 prebuilt_board_dir = "{board}" 到 {product}/product.gni')


# =============================================================================
# Phase 9: 打包 tar.gz
# =============================================================================

def pack_tarball(ohos_root: Path, product: str, output_path: Path, dry_run: bool = False, extra_products=None):
    """
    打包改造后的 device/ 、outer vendor/ 和 vendor/hisilicon/<product>/ 为 partner tar.gz。
    结构：
      ./ohos5/device/                       （改造后的 device 目录）
      ./ohos5/vendor/hisilicon/<product>/   （改造后的产品 vendor 目录，含预编译 BUILD.gn）
      ./vendor/                             （outer vendor，已去源码）
    """
    outer_vendor    = ohos_root.parent / 'vendor'
    device_dir      = ohos_root / 'device'
    product_vendor  = ohos_root / 'vendor' / 'hisilicon' / product

    if dry_run:
        print(f"    [TAR] 将创建: {output_path}")
        print(f"    [TAR]   ./vendor/ (outer vendor)")
        print(f"    [TAR]   ./ohos5/device/")
        print(f"    [TAR]   ./ohos5/vendor/hisilicon/{product}/")
        for ep in (extra_products or []):
            print(f"    [TAR]   ./ohos5/vendor/hisilicon/{ep}/ (extra)")
        return

    print(f"    [TAR] 打包中，目标: {output_path.name} ...")

    # 合作伙伴编译不需要以下源码目录（产物已预编译），打包时排除以缩小体积
    _SOURCE_EXCLUDE_PREFIXES = (
        # u-boot 源码（bootloader 预编译产物在 device/<board>/bootloader/）
        './vendor/open_source/u-boot/',
        # liteos 源码
        './vendor/platform/liteos/liteos-207.0.0-release/',
        # media frameworks 源码（.so 已预编译）
        './vendor/open_source/frameworks/av/',
        # 音频编解码库源码（opus / fdk-aac / alsa-lib/src / alsa-lib/test）
        './vendor/open_source/opus/',
        './vendor/open_source/fdk-aac/',
        './vendor/open_source/alsa-lib/src/',
        './vendor/open_source/alsa-lib/test/',
        # mbedtls 实现源码（保留 include/）
        './vendor/open_source/mbedtls/library/',
        './vendor/open_source/mbedtls/tests/',
        './vendor/open_source/mbedtls/programs/',
        './vendor/open_source/mbedtls/3rdparty/',
        # alsa-lib 工具程序源码（无 BUILD.gn，不参与编译）
        './vendor/open_source/alsa-lib/modules/',
        './vendor/open_source/alsa-lib/alsalisp/',
        './vendor/open_source/alsa-lib/aserver/',
        # display 硬件测试代码（ohos_moduletest，不进设备镜像）
        './vendor/huanglong/ohos/hardware/graphics/display/source/test/',
        # libteec_system 源码（无 BUILD.gn，不参与 OHOS5 编译）
        './vendor/platform/libteec_system/',
        # libteec_vendor/secure_c 源码（Phase 5.11 已改为预编译拷贝，源码不再需要）
        './vendor/platform/libteec_vendor/source/',
        './vendor/platform/secure_c/source/',
        # pdmtool 源码（BUILD.gn 已改为 ohos_prebuilt_executable，源码无引用）
        './vendor/tools/board/huanglong/pdm/pdmtool.c',
        # mkbootargs 源码（目录内无 BUILD.gn，GN 编译不到）
        './vendor/tools/host/huanglong/mkbootargs/mkbootargs.c',
        # graphic hdi_backend 测试代码（不进设备镜像）
        './vendor/huanglong/ohos/ohos5_ext/foundation/graphic/graphic_2d/rosen/modules/composer/hdi_backend/test/',
        # sample/audio cast/ai/aenc 源码（无 bundle.json，不参与编译；binary 已由 ao/ prebuilt 覆盖）
        './vendor/huanglong/sample/audio/cast/',
        './vendor/huanglong/sample/audio/ai/',
        './vendor/huanglong/sample/audio/aenc/',
        './vendor/huanglong/sample/audio/adp_uapi_ext.c',
        './vendor/huanglong/sample/audio/adp_ini_ext.c',
    )
    # GPU driver 目录只删 .c/.cpp，保留 .h（include 头文件）
    _GPU_DRV_PREFIX = './vendor/thirdparty/gpu/drv/'
    _GPU_DRV_SRC_EXTS = {'.c', '.cpp', '.cc', '.cxx'}

    def _tar_filter(tarinfo):
        # 排除 .git 目录
        if '/.git/' in tarinfo.name or tarinfo.name.endswith('/.git'):
            return None
        # 排除 out/ 目录（如果误包含）
        if '/out/' in tarinfo.name:
            return None
        # 排除不需要的源码目录（合作伙伴只需预编译产物）
        for prefix in _SOURCE_EXCLUDE_PREFIXES:
            if tarinfo.name.startswith(prefix):
                return None
        # GPU driver：只排除 .c/.cpp 源文件，保留头文件
        if tarinfo.name.startswith(_GPU_DRV_PREFIX):
            ext = os.path.splitext(tarinfo.name)[1].lower()
            if ext in _GPU_DRV_SRC_EXTS:
                return None
        return tarinfo

    with tarfile.open(output_path, 'w:gz') as tar:
        if outer_vendor.exists():
            tar.add(str(outer_vendor), arcname='./vendor', filter=_tar_filter)
        if device_dir.exists():
            tar.add(str(device_dir), arcname='./ohos5/device', filter=_tar_filter)
        if product_vendor.exists():
            tar.add(str(product_vendor),
                    arcname=f'./ohos5/vendor/hisilicon/{product}',
                    filter=_tar_filter)
        else:
            print(f"    [WARN] 产品 vendor 目录不存在，跳过: {product_vendor}")
        for ep in (extra_products or []):
            ep_vendor = ohos_root / 'vendor' / 'hisilicon' / ep
            if ep_vendor.exists():
                tar.add(str(ep_vendor),
                        arcname=f'./ohos5/vendor/hisilicon/{ep}',
                        filter=_tar_filter)
                print(f"    [TAR] 已添加额外产品: {ep}")
            else:
                print(f"    [WARN] 额外产品 vendor 不存在，跳过: {ep_vendor}")

        # 打包 bundled patches（合作伙伴仓库中可能缺失的修复补丁）
        bundled_patches = [
            'common_patch/custom-ohos-patch/build/0002-fix-patch-idempotency.patch',
            'common_patch/custom-ohos-patch/build/0003-add-prebuilt-board-dir.patch',
            'common_patch/custom-ohos-patch/developtools/global_resource_tool/0001-fix-cstring-include.patch',
        ]
        for rel in bundled_patches:
            patch_file = ohos_root / rel
            if patch_file.exists():
                tar.add(str(patch_file), arcname=f'./ohos5/{rel}')
                print(f"    [TAR] bundled patch: {rel}")
            else:
                print(f"    [WARN] bundled patch 不存在，跳过: {patch_file}")

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"    [TAR] 完成: {output_path.name} ({size_mb:.1f} MB)")


# =============================================================================
# 主流程
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='将 OHOS device/vendor 源码树改造为预编译分发模式'
    )
    parser.add_argument('--product', required=True,
                        help='产品名称，如 mp_hi3781v730')
    parser.add_argument('--ohos-root', default=None,
                        help='ohos5 目录路径（默认：脚本所在目录）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只显示操作，不实际修改文件')
    parser.add_argument('--skip-pack', action='store_true',
                        help='跳过 tar.gz 打包（Phase 9）')
    parser.add_argument('--skip-source-delete', action='store_true',
                        help='跳过源文件删除（Phase 6）')
    parser.add_argument('--skip-kernel', action='store_true',
                        help='跳过 kernel/bootloader 处理（Phase 7）')
    parser.add_argument('--skip-patches', action='store_true',
                        help='跳过预应用 device 补丁（Phase 8）')
    parser.add_argument('--extra-products', nargs='*', default=[],
                        help='额外打包的产品（仅打包其 vendor/hisilicon/<product>/ 目录，需预先存在），'
                             '如 --extra-products mp_hi3781v730')
    args = parser.parse_args()

    # 解析 ohos_root
    if args.ohos_root:
        ohos_root = Path(args.ohos_root).resolve()
    else:
        ohos_root = Path(__file__).parent.resolve()
    if not (ohos_root / 'vendor').exists():
        print(f"[ERROR] ohos_root 无效（找不到 vendor/）: {ohos_root}")
        sys.exit(1)

    product  = args.product
    dry_run  = args.dry_run

    print(f"\n{'='*60}")
    print(f"  OHOS Prebuilt Transform")
    print(f"  Product  : {product}")
    print(f"  Root     : {ohos_root}")
    print(f"  Dry-run  : {dry_run}")
    print(f"{'='*60}")

    # ---- Phase 1 ----
    print("\n[Phase 1] 读取产品配置...")
    cfg = read_product_config(ohos_root, product)
    board    = cfg['board']
    out_dir  = cfg['out_dir']
    if not out_dir.exists():
        print(f"[ERROR] out 目录不存在: {out_dir}，请先完成编译")
        sys.exit(1)
    chip_revision = detect_chip_revision(out_dir)
    print(f"  board={board}, out_dir={out_dir.name}, chip_revision={chip_revision}")

    extra_products = args.extra_products or []

    # 扫描根
    device_scan_roots = [
        'device/soc/hisilicon/huanglong/vendor/huanglong',
        'device/soc/hisilicon/common',
    ]
    vendor_scan_root = f'vendor/hisilicon/{product}'
    extra_vendor_scan_roots = [f"vendor/hisilicon/{ep}" for ep in extra_products]
    all_scan_roots   = device_scan_roots + [vendor_scan_root] + extra_vendor_scan_roots

    # ---- inject prebuilt_board_dir into product.gni ----
    print("\n[inject] 注入 prebuilt_board_dir 变量到 product.gni...")
    inject_prebuilt_board_dir(ohos_root, product, board, dry_run)
    for ep in extra_products:
        try:
            ep_cfg = read_product_config(ohos_root, ep)
            inject_prebuilt_board_dir(ohos_root, ep, ep_cfg['board'], dry_run)
        except FileNotFoundError as e:
            print(f"    [WARN] 额外产品配置不存在，跳过注入: {e}")

    # ---- Phase 2 ----
    print("\n[Phase 2] 扫描 BUILD.gn 文件...")
    all_targets: List[TargetInfo] = []
    for sr in all_scan_roots:
        gn_files = scan_build_gn_files(ohos_root, sr)
        for gf in gn_files:
            all_targets.extend(parse_build_gn(gf, sr))
    print(f"  发现编译目标: {len(all_targets)}")

    # ---- Phase 3 ----
    print("\n[Phase 3] 定位 out/ 中的产物...")
    found:   List[TargetInfo] = []
    skipped: List[TargetInfo] = []
    for t in all_targets:
        artifact, subsystem = find_artifact(t, out_dir)
        if artifact:
            t.artifact_path = artifact
            if not t.subsystem_name:
                t.subsystem_name = subsystem
            found.append(t)
        else:
            skipped.append(t)
    print(f"  找到产物: {len(found)}，跳过（feature 未开启）: {len(skipped)}")

    # ---- Phase 4 + 5 ----
    print("\n[Phase 4] 拷贝产物到预编译存放路径...")
    print("[Phase 5] 改写 BUILD.gn...")

    gn_transforms: Dict[Path, Dict[str, Tuple[TargetInfo, str]]] = {}
    copy_count = 0

    for t in found:
        dest, src_ref = get_prebuilt_dest(t, ohos_root, board, t.subsystem_name, product)
        t.prebuilt_dest       = dest
        t.prebuilt_source_ref = src_ref

        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(t.artifact_path, dest)
        copy_count += 1

        gn_path = t.build_gn_path
        gn_transforms.setdefault(gn_path, {})[t.target_name] = (t, src_ref)

    print(f"  拷贝产物: {copy_count}")
    for gn_path, transforms in gn_transforms.items():
        rewrite_build_gn(gn_path, transforms, dry_run)
    print(f"  改写 BUILD.gn: {len(gn_transforms)} 个文件")

    # ---- Phase 5.5: 清理残留 source 目标 ----
    print("\n[Phase 5.5] 清理残留 source-compiled 目标...")
    cleaned = cleanup_remaining_source_targets(ohos_root, all_scan_roots, dry_run)
    print(f"  已清理残留目标: {cleaned}")

    # ---- Phase 5.5.1: 清理孤立文件级变量赋值 ----
    orphan_vars = cleanup_unused_file_scope_vars(ohos_root, all_scan_roots, dry_run)
    if orphan_vars:
        print(f"  已清理孤立变量赋值: {orphan_vars}")

    # ---- Phase 5.5.2: 清理 group() deps 中对已删除 target 的引用 ----
    group_deps_cleaned = cleanup_group_deps_to_removed_targets(ohos_root, all_scan_roots, dry_run)
    if group_deps_cleaned:
        print(f"  已清理 group() 孤立 dep 引用: {group_deps_cleaned}")

    # ---- Phase 5.6: 清理 bundle.json test 引用 ----
    print("\n[Phase 5.6] 清理 bundle.json test 引用...")
    bundle_cleaned = cleanup_bundle_json_test_refs(ohos_root, all_scan_roots, skipped, dry_run)
    print(f"  已清理 test 引用: {bundle_cleaned}")
    # ---- Phase 5.7: 修正已知预编译目标 shlib_type 缺失 ----
    print("[Phase 5.7] 修正预编译目标 shlib_type...")
    fixup_count = fixup_depsgard_hdi_whitelist(ohos_root, dry_run)
    print(f"  已修正: {fixup_count}")

    # ---- Phase 5.9: 修复 //out/ source 引用 ----
    out_fixed = fix_prebuilt_out_source_paths(ohos_root, all_scan_roots, board, dry_run)
    if out_fixed:
        print(f"  [Phase 5.9] 已修复 //out/ 引用: {out_fixed}")


    # ---- Phase 5.10: 修复 rtkbt_wifi libbt_vendor ----
    print("[Phase 5.10] 修复 rtkbt_wifi libbt_vendor dep...")
    if fix_rtkbt_wifi_libbt_vendor(ohos_root, product, dry_run):
        print("  rtkbt_wifi libbt_vendor dep 已修复")
    else:
        print("  rtkbt_wifi 无需修复或不存在")


    # ---- Phase 6 ----
    if not args.skip_source_delete:
        print("\n[Phase 6] 删除源文件...")
        count = delete_source_files(ohos_root, all_scan_roots, dry_run)
        print(f"  已删除源文件: {count}")
    else:
        print("\n[Phase 6] 已跳过（--skip-source-delete）")

    # ---- Phase 7 ----
    if not args.skip_kernel:
        print("\n[Phase 7] 处理 kernel & bootloader...")
        handle_kernel_bootloader(ohos_root, board, chip_revision, out_dir, dry_run)
    else:
        print("\n[Phase 7] 已跳过（--skip-kernel）")

    # ---- Phase 8 ----
    if not args.skip_patches:
        print("\n[Phase 8] 预应用 device custom patches...")
        common_patch_dir = ohos_root / 'common_patch'
        pre_apply_device_patches(ohos_root, common_patch_dir, dry_run)
    else:
        print("\n[Phase 8] 已跳过（--skip-patches）")

    # ---- Phase 8.5: fix display_composer_model deps ----
    print("[Phase 8.5] fix display_composer_model libdisplay_utils_vendor dep...")
    fix_display_composer_deps(ohos_root, dry_run)

    # ---- Phase 8.6: fix libuapi_frontend -> frontend_config.ini dep ----
    print("[Phase 8.6] fix libuapi_frontend frontend_config.ini dep...")
    fix_frontend_config_dep(ohos_root, dry_run)

    # ---- Phase 5.11: TEE/secure_c 平台库改造为预编译拷贝 ----
    print("\n[Phase 5.11] 将 platform 库改造为预编译拷贝 (libteec_vendor/secure_c/pdmtool)...")
    tee_count = convert_platform_libs_to_prebuilt(ohos_root, out_dir, dry_run)
    print(f"  已处理模块: {tee_count}")

    # 生成 partner apply_patches_sdk.sh
    common_patch_dir = ohos_root / 'common_patch'
    partner_sh = common_patch_dir / 'apply_patches_sdk_partner.sh'
    print("\n[Partner Script] 生成 partner apply_patches_sdk.sh...")
    generate_partner_apply_patches_sh(common_patch_dir, partner_sh, product, dry_run,
                                      extra_products=extra_products)

    # ---- Phase 9 ----
    sdk_basename = 'R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz'
    tar_output   = ohos_root.parent / sdk_basename

    if not args.skip_pack:
        print("\n[Phase 9] 打包 partner tar.gz...")
        pack_tarball(ohos_root, product, tar_output, dry_run,
                     extra_products=extra_products)
    else:
        print("\n[Phase 9] 已跳过（--skip-pack）")

    print(f"\n{'='*60}")
    print("  改造完成！")
    if not args.skip_pack:
        print(f"  Partner SDK   : {tar_output}")
    print(f"  Partner 脚本  : {partner_sh}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
