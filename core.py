"""Shared filesystem and naming rules for every ManyYasuo module."""

from __future__ import annotations

import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


READY = "ready"
PROTECTED = "protected"
NO_TAG = "no_tag"
ALREADY_NAMED = "already_named"
INVALID = "invalid"
RENAMED = "renamed"
RENAMED_MARKER_KEPT = "renamed_marker_kept"
FAILED = "failed"
PREPROCESSED = "preprocessed"
CANCELLED = "cancelled"

IGNORED_WRAPPER_ENTRIES = {"desktop.ini", ".DS_Store", "Thumbs.db"}


def _is_reparse_point(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _sanitize_marker_text(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip()


@dataclass(frozen=True)
class TagRules:
    tag_prefix: str = "AAA_"
    block_terms: str = "路径, 中文"

    @property
    def normalized_prefix(self) -> str:
        return _sanitize_marker_text(self.tag_prefix)

    @property
    def parsed_block_terms(self) -> tuple[str, ...]:
        return parse_block_terms(self.block_terms)


@dataclass(frozen=True)
class RenameOptions:
    tag_prefix: str = "AAA_"
    block_terms: str = "路径, 中文"

    @property
    def rules(self) -> TagRules:
        return TagRules(self.tag_prefix, self.block_terms)


@dataclass(frozen=True)
class RenamePreview:
    source: Path
    status: str
    message: str
    target: Path | None = None
    marker_relative: Path | None = None
    blocker_relative: Path | None = None
    tag: str = ""
    base_name: str = ""


@dataclass(frozen=True)
class RenameResult:
    source: Path
    status: str
    message: str
    target: Path | None = None
    marker_removed: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status in {RENAMED, RENAMED_MARKER_KEPT}


@dataclass(frozen=True)
class PreprocessOptions:
    file_prefix: str = "HGLIST-"
    tag_prefix: str = "AAA_"
    start_number: str = "0001"
    unwrap_nested: bool = True


@dataclass(frozen=True)
class PreprocessPreview:
    source: Path
    target: Path | None
    status: str
    message: str


@dataclass(frozen=True)
class PreprocessBatch:
    previews: tuple[PreprocessPreview, ...]
    error: str = ""

    @property
    def valid(self) -> bool:
        return not self.error and all(item.status == READY for item in self.previews)


@dataclass(frozen=True)
class PreprocessResult:
    source: Path
    target: Path | None
    status: str
    message: str

    @property
    def succeeded(self) -> bool:
        return self.status == PREPROCESSED


@dataclass(frozen=True)
class CompressionTagDetection:
    tag: str = ""
    origin: str = "none"
    preserved_name: str = ""
    name_tag: str = ""
    marker_tag: str = ""

    @property
    def found(self) -> bool:
        return bool(self.tag)

    @property
    def conflict(self) -> bool:
        folded_name = self.name_tag.strip().casefold()
        folded_marker = self.marker_tag.strip().casefold()
        return bool(folded_name and folded_marker and folded_name != folded_marker)


def parse_block_terms(value: str) -> tuple[str, ...]:
    """Return case-folded terms; all terms must match one filename."""
    return tuple(term.casefold() for term in re.split(r"[,，;；\s]+", value) if term)


def create_tag_marker(root: Path | str, prefix: str, tag: str) -> Path | None:
    """Create the empty marker directory used by all three modules."""
    safe_tag = _sanitize_marker_text(tag)
    if not safe_tag:
        return None
    marker_name = f"{_sanitize_marker_text(prefix)}{safe_tag}"
    marker = Path(root) / marker_name
    marker.mkdir(exist_ok=True)
    return marker


def remove_empty_tag_marker(root: Path | str, prefix: str, tag: str) -> None:
    """Remove an empty marker directory; missing is OK, non-empty raises OSError."""
    safe_tag = _sanitize_marker_text(tag)
    if not safe_tag:
        return
    marker = Path(root) / f"{_sanitize_marker_text(prefix)}{safe_tag}"
    try:
        marker.rmdir()
    except FileNotFoundError:
        return


def find_tag_marker(root: Path | str, prefix: str) -> Path | None:
    """Find a marker breadth-first and stop after the shallowest matching level.

    Directory symlinks and junction-like reparse traversals are skipped to avoid
    cycles.  Within one level, selection is deterministic by name and relative
    path, matching the behavior expected by rename previews and extraction.
    """
    root = Path(root)
    normalized_prefix = _sanitize_marker_text(prefix)
    if not normalized_prefix or not root.is_dir() or _is_reparse_point(root):
        return None

    parents = [root]
    while parents:
        matches: list[Path] = []
        children: list[Path] = []
        for parent in parents:
            try:
                with os.scandir(parent) as entries:
                    for entry in entries:
                        try:
                            if not entry.is_dir(follow_symlinks=False) or _is_reparse_point(Path(entry.path)):
                                continue
                        except OSError:
                            continue
                        path = Path(entry.path)
                        if entry.name.startswith(normalized_prefix) and len(entry.name) > len(normalized_prefix):
                            matches.append(path)
                        else:
                            children.append(path)
            except OSError:
                continue
        if matches:
            return min(
                matches,
                key=lambda path: (
                    path.name.casefold(),
                    str(path.relative_to(root)).casefold(),
                ),
            )
        parents = children
    return None


def extract_marker_tag(marker: Path, prefix: str) -> str:
    normalized_prefix = _sanitize_marker_text(prefix)
    return marker.name[len(normalized_prefix) :].strip()


def find_blocking_file(root: Path | str, terms: tuple[str, ...]) -> Path | None:
    """Find a direct child file whose name contains every term."""
    root = Path(root)
    if not root.is_dir():
        return None
    try:
        first_level = list(root.iterdir())
    except OSError:
        return None
    for path in first_level:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        folded_name = path.name.casefold()
        if all(term in folded_name for term in terms):
            return path
    return None


def sanitize_name(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip().rstrip(".")
    if not value:
        value = "未命名"
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if value.upper() in reserved:
        value = f"_{value}"
    return value[:120]


def find_last_number(value: str) -> str:
    matches = re.findall(r"\d+", value)
    return matches[-1] if matches else ""


def split_numbered_folder_tag(name: str) -> tuple[str, str]:
    """Split `numbered base + tag`, ignoring the app's collision suffix."""
    cleaned = re.sub(r" \(\d+\)$", "", name).strip()
    match = re.match(r"^(.+?\d+)\s+(.+)$", cleaned)
    if match:
        return match.group(1).rstrip(), match.group(2).strip()
    if not re.search(r"\d+", cleaned):
        return "", ""
    return cleaned, ""


def detect_compression_tag(root: str | os.PathLike[str], prefix: str) -> CompressionTagDetection:
    """Detect both marker-directory and trailing-name tags.

    When both are present and differ, the caller must resolve the conflict.
    """
    folder = Path(root)
    base_name, name_tag = split_numbered_folder_tag(folder.name)
    marker = find_tag_marker(folder, prefix)
    marker_tag = extract_marker_tag(marker, prefix) if marker is not None else ""

    preserved = base_name or (
        re.sub(r" \(\d+\)$", "", folder.name).strip()
        if find_last_number(folder.name)
        else ""
    )

    folded_name = name_tag.strip().casefold()
    folded_marker = marker_tag.strip().casefold()
    if folded_marker and folded_name and folded_marker != folded_name:
        return CompressionTagDetection(
            tag="",
            origin="conflict",
            preserved_name=preserved,
            name_tag=name_tag.strip(),
            marker_tag=marker_tag.strip(),
        )
    if folded_marker:
        return CompressionTagDetection(
            tag=marker_tag.strip(),
            origin="marker",
            preserved_name=preserved,
            name_tag=name_tag.strip(),
            marker_tag=marker_tag.strip(),
        )
    if folded_name:
        return CompressionTagDetection(
            tag=name_tag.strip(),
            origin="name",
            preserved_name=preserved,
            name_tag=name_tag.strip(),
            marker_tag="",
        )
    return CompressionTagDetection(preserved_name=preserved)


def is_already_named(original_name: str, tag: str) -> bool:
    without_collision = re.sub(r" \(\d+\)$", "", original_name).strip()
    folded_name = without_collision.casefold()
    folded_tag = tag.strip().casefold()
    return folded_name == folded_tag or folded_name.endswith(f" {folded_tag}")


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def natural_name_key(value: str) -> tuple[int | str, ...]:
    """Return a Windows Explorer style natural sort key for a name."""
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
    )


def path_sort_key(path: str | os.PathLike[str]) -> tuple[tuple[int | str, ...], str]:
    """Return a natural-name sort key, with full path as a deterministic tiebreaker."""
    return natural_name_key(Path(path).name), os.path.normcase(os.path.abspath(path))


def unique_destination(parent: Path, name: str, reserved: set[str] | None = None) -> Path:
    reserved = reserved or set()
    candidate = parent / name
    index = 2
    while candidate.exists() or _path_key(candidate) in reserved:
        candidate = parent / f"{name} ({index})"
        index += 1
    return candidate


def build_sequence_targets(
    sources: Sequence[str | os.PathLike[str]], file_prefix: str, start_number: str
) -> tuple[Path, ...]:
    """Build deterministic targets while preserving the caller's list order."""
    if not start_number or not start_number.isascii() or not start_number.isdecimal():
        raise ValueError("起始编号必须是非负整数")
    start = int(start_number)
    padding = len(start_number)
    targets: list[Path] = []
    for index, source in enumerate(sources):
        name = f"{file_prefix}{str(start + index).zfill(padding)}"
        if sanitize_name(name) != name:
            raise ValueError("文件名前缀包含非法字符或生成的名称过长")
        targets.append(Path(source).absolute().parent / name)
    return tuple(targets)


def analyze_explicit_preprocess_batch(
    sources: Sequence[str | os.PathLike[str]],
    targets: Sequence[str | os.PathLike[str]],
) -> PreprocessBatch:
    absolute = tuple(Path(source).absolute() for source in sources)
    if not absolute:
        return PreprocessBatch((), "请先添加文件夹")
    explicit_targets = tuple(Path(target).absolute() for target in targets)
    if len(explicit_targets) != len(absolute):
        message = "源文件夹与目标路径数量不一致"
        return PreprocessBatch(
            tuple(PreprocessPreview(path, None, INVALID, message) for path in absolute),
            message,
        )

    source_keys = [_path_key(path) for path in absolute]
    if len(set(source_keys)) != len(source_keys):
        message = "列表中存在重复文件夹"
        return PreprocessBatch(
            tuple(PreprocessPreview(path, target, INVALID, message) for path, target in zip(absolute, explicit_targets)),
            message,
        )

    source_key_set = set(source_keys)
    target_keys = [_path_key(path) for path in explicit_targets]
    if len(set(target_keys)) != len(target_keys):
        message = "生成了重复的目标路径"
        return PreprocessBatch(
            tuple(PreprocessPreview(path, target, INVALID, message) for path, target in zip(absolute, explicit_targets)),
            message,
        )

    previews: list[PreprocessPreview] = []
    errors: list[str] = []
    for source, target in zip(absolute, explicit_targets):
        if target.parent != source.parent:
            message = "目标文件夹必须与原文件夹位于同一目录"
            status = INVALID
        elif sanitize_name(target.name) != target.name:
            message = f"目标名称无效：{target.name}"
            status = INVALID
        elif not source.exists():
            message = f"文件夹不存在：{source.name}"
            status = INVALID
        elif not source.is_dir():
            message = f"不是文件夹：{source.name}"
            status = INVALID
        elif _is_reparse_point(source):
            message = f"不能修改链接或重解析目录：{source}"
            status = INVALID
        elif target.exists() and _path_key(target) not in source_key_set:
            message = f"目标已存在：{target.name}"
            status = INVALID
        else:
            message = "名称已正确" if _path_key(source) == _path_key(target) else f"将改名为 {target.name}"
            status = READY
        if status == INVALID:
            errors.append(message)
        previews.append(PreprocessPreview(source, target, status, message))
    return PreprocessBatch(tuple(previews), errors[0] if errors else "")


def analyze_preprocess_batch(
    sources: Sequence[str | os.PathLike[str]], options: PreprocessOptions
) -> PreprocessBatch:
    absolute = tuple(Path(source).absolute() for source in sources)
    if not absolute:
        return PreprocessBatch((), "请先添加文件夹")
    try:
        targets = build_sequence_targets(absolute, options.file_prefix, options.start_number)
    except ValueError as error:
        return PreprocessBatch(
            tuple(PreprocessPreview(path, None, INVALID, str(error)) for path in absolute),
            str(error),
        )
    return analyze_explicit_preprocess_batch(absolute, targets)


def folder_size(root: str | os.PathLike[str], cancelled: Callable[[], bool] | None = None) -> int:
    """Return recursive logical bytes without following symlinks or reparse points."""
    total = 0
    stack = [Path(root)]
    while stack:
        if cancelled and cancelled():
            raise InterruptedError("大小计算已取消")
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if cancelled and cancelled():
                    raise InterruptedError("大小计算已取消")
                info = entry.stat(follow_symlinks=False)
                attributes = getattr(info, "st_file_attributes", 0)
                is_reparse = bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
                if entry.is_dir(follow_symlinks=False) and not is_reparse:
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += info.st_size
    return total


def format_size(size: int) -> str:
    value = float(max(0, size))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def unwrap_single_child_chain(root: str | os.PathLike[str], tag_prefix: str = "") -> int:
    """Lift a single-child directory chain into root, returning levels removed."""
    root = Path(root)
    if _is_reparse_point(root):
        raise OSError(f"不能修改链接或重解析目录：{root}")
    removed = 0
    while True:
        entries = list(root.iterdir())
        meaningful = [entry for entry in entries if entry.name not in IGNORED_WRAPPER_ENTRIES]
        if len(meaningful) != 1:
            return removed
        nested = meaningful[0]
        normalized_tag_prefix = _sanitize_marker_text(tag_prefix)
        if normalized_tag_prefix and nested.name.startswith(normalized_tag_prefix):
            return removed
        if not nested.is_dir() or _is_reparse_point(nested):
            return removed
        nested_entries = list(nested.iterdir())
        collisions = [entry.name for entry in nested_entries if (root / entry.name).exists()]
        if collisions:
            raise FileExistsError(f"嵌套整理存在同名项目：{collisions[0]}")
        moved: list[tuple[Path, Path]] = []
        try:
            for entry in nested_entries:
                destination = root / entry.name
                shutil.move(str(entry), str(destination))
                moved.append((destination, entry))
            nested.rmdir()
            removed += 1
        except OSError:
            for destination, original in reversed(moved):
                try:
                    shutil.move(str(destination), str(original))
                except OSError:
                    pass
            raise


def resolve_preprocess_targets(
    sources: Sequence[str | os.PathLike[str]],
    targets: Sequence[str | os.PathLike[str]],
    tags: Sequence[str],
) -> tuple[Path, ...]:
    """Return targets with trailing filename tags stripped when a tag is written.

    Preprocessing normally keeps the folder name. When a marker tag is being
    added, however, an existing filename tag must be removed so the folder does
    not end up with both a filename tag and a marker directory.
    """
    absolute_sources = [Path(source).absolute() for source in sources]
    absolute_targets = [Path(target).absolute() for target in targets]
    if len(absolute_sources) != len(absolute_targets):
        return tuple(absolute_targets)
    normalized_tags = tuple(tags) + ("",) * max(0, len(absolute_sources) - len(tags))
    resolved: list[Path] = []
    for source, target, tag in zip(absolute_sources, absolute_targets, normalized_tags):
        if tag.strip() and _path_key(source) == _path_key(target):
            base_name, _ = split_numbered_folder_tag(source.name)
            if base_name and base_name != source.name:
                target = source.parent / sanitize_name(base_name)
        resolved.append(target)
    return tuple(resolved)


def _execute_preprocess_plan(
    batch: PreprocessBatch,
    tags: Sequence[str],
    tag_prefix: str,
    unwrap_nested: bool,
    cancelled: Callable[[], bool] | None = None,
    remove_marker_tags: Sequence[str] = (),
) -> tuple[PreprocessResult, ...]:
    if not batch.valid:
        return tuple(
            PreprocessResult(
                item.source,
                item.target,
                INVALID if item.status == INVALID else CANCELLED,
                item.message if item.status == INVALID else "批次校验失败，未执行",
            )
            for item in batch.previews
        )
    if cancelled and cancelled():
        return tuple(
            PreprocessResult(item.source, item.target, CANCELLED, "已取消") for item in batch.previews
        )

    staged: list[tuple[PreprocessPreview, Path]] = []
    finalized: list[tuple[PreprocessPreview, Path]] = []
    try:
        for item in batch.previews:
            if item.target is None or _path_key(item.source) == _path_key(item.target):
                continue
            stage = item.source.parent / f".manyyasuo-{uuid.uuid4().hex}.tmp"
            os.rename(item.source, stage)
            staged.append((item, stage))
        for item, stage in staged:
            os.rename(stage, item.target)
            finalized.append((item, item.target))
    except OSError as error:
        stages = {id(item): stage for item, stage in staged}
        locations = {id(item): stage for item, stage in staged}
        locations.update({id(item): current for item, current in finalized})
        recovery_errors: list[str] = []
        for item, current in reversed(finalized):
            try:
                os.rename(current, stages[id(item)])
                locations[id(item)] = stages[id(item)]
            except OSError as recovery_error:
                recovery_errors.append(str(recovery_error))
        for item, stage in reversed(staged):
            if locations[id(item)] != stage:
                continue
            try:
                if os.path.lexists(item.source):
                    raise FileExistsError(f"恢复路径已占用：{item.source}")
                os.rename(stage, item.source)
                locations[id(item)] = item.source
            except OSError as recovery_error:
                recovery_errors.append(str(recovery_error))
        details = ""
        if recovery_errors:
            kept = [f"原路径：{item.source}；实际保留位置：{locations[id(item)]}"
                    for item, _ in staged if locations[id(item)] != item.source]
            details = "；回滚异常：" + "；".join(recovery_errors + kept)
        return tuple(
            PreprocessResult(item.source, locations.get(id(item), item.source), FAILED,
                             f"批量重命名失败：{error}{details}")
            for item in batch.previews
        )

    results: list[PreprocessResult] = []
    normalized_tags = tuple(tags) + ("",) * max(0, len(batch.previews) - len(tags))
    normalized_removals = tuple(remove_marker_tags) + ("",) * max(0, len(batch.previews) - len(remove_marker_tags))
    for item, tag, remove_tag in zip(batch.previews, normalized_tags, normalized_removals):
        target = item.target or item.source
        try:
            levels = unwrap_single_child_chain(target, tag_prefix) if unwrap_nested else 0
            final_tag = tag.strip()
            removal_tag = remove_tag.strip()
            if final_tag and removal_tag and removal_tag.casefold() != final_tag.casefold():
                remove_empty_tag_marker(target, tag_prefix, removal_tag)
            if final_tag:
                existing = find_tag_marker(target, tag_prefix)
                existing_tag = extract_marker_tag(existing, tag_prefix) if existing is not None else ""
                if existing_tag and existing_tag.casefold() != final_tag.casefold():
                    try:
                        existing.rmdir()
                    except OSError as error:
                        raise OSError(f"旧标签目录非空或无法删除：{existing.name}") from error
            marker = create_tag_marker(target, tag_prefix, final_tag) if final_tag else None
            details = []
            if levels:
                details.append(f"整理 {levels} 层")
            if marker is not None:
                details.append(f"标签 {marker.name}")
            suffix = f" · {' · '.join(details)}" if details else ""
            results.append(PreprocessResult(item.source, target, PREPROCESSED, f"已完成{suffix}"))
        except OSError as error:
            results.append(PreprocessResult(item.source, target, FAILED, f"处理失败：{error}"))
    return tuple(results)


def execute_explicit_preprocess_batch(
    sources: Sequence[str | os.PathLike[str]],
    targets: Sequence[str | os.PathLike[str]],
    tags: Sequence[str],
    tag_prefix: str,
    unwrap_nested: bool = False,
    cancelled: Callable[[], bool] | None = None,
    remove_marker_tags: Sequence[str] = (),
) -> tuple[PreprocessResult, ...]:
    """Transactionally prepare a batch with caller-supplied target paths."""
    resolved_targets = resolve_preprocess_targets(sources, targets, tags)
    batch = analyze_explicit_preprocess_batch(sources, resolved_targets)
    return _execute_preprocess_plan(
        batch,
        tags,
        tag_prefix,
        unwrap_nested,
        cancelled,
        remove_marker_tags,
    )


def execute_preprocess_batch(
    sources: Sequence[str | os.PathLike[str]],
    tags: Sequence[str],
    options: PreprocessOptions,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[PreprocessResult, ...]:
    """Validate, transactionally rename, then unwrap and tag a folder batch."""
    batch = analyze_preprocess_batch(sources, options)
    return _execute_preprocess_plan(
        batch,
        tags,
        options.tag_prefix,
        options.unwrap_nested,
        cancelled,
    )


def analyze_folder(
    source: str | os.PathLike[str],
    options: RenameOptions,
    reserved_targets: set[str] | None = None,
) -> RenamePreview:
    folder = Path(source).absolute()
    if not folder.exists():
        return RenamePreview(folder, INVALID, "文件夹不存在")
    if not folder.is_dir():
        return RenamePreview(folder, INVALID, "拖入的项目不是文件夹")

    try:
        if _is_reparse_point(folder):
            return RenamePreview(folder, INVALID, f"不能修改链接或重解析目录：{folder}")
        terms = parse_block_terms(options.block_terms)
        blocker = find_blocking_file(folder, terms) if terms else None
        if blocker is not None:
            return RenamePreview(
                folder,
                PROTECTED,
                f"检测到“{blocker.name}”，保留原名",
                blocker_relative=blocker.relative_to(folder),
            )

        marker = find_tag_marker(folder, options.tag_prefix)
        if marker is None:
            return RenamePreview(folder, NO_TAG, "未找到有效标签目录")
        tag = extract_marker_tag(marker, options.tag_prefix)
        if not tag:
            return RenamePreview(folder, NO_TAG, "标签目录没有可用名称")

        marker_relative = marker.relative_to(folder)
        if is_already_named(folder.name, tag):
            return RenamePreview(
                folder,
                ALREADY_NAMED,
                "名称已经正确，无需重复改名",
                target=folder,
                marker_relative=marker_relative,
                tag=tag,
                base_name=folder.name,
            )

        base_name, _ = split_numbered_folder_tag(folder.name)
        final_name = sanitize_name(f"{base_name} {tag}" if base_name else tag)
        if final_name.casefold() == folder.name.casefold():
            return RenamePreview(
                folder,
                ALREADY_NAMED,
                "名称已经正确，无需重复改名",
                target=folder,
                marker_relative=marker_relative,
                tag=tag,
                base_name=folder.name,
            )

        target = unique_destination(folder.parent, final_name, reserved_targets)
        return RenamePreview(
            folder,
            READY,
            f"将改名为 {target.name}",
            target=target,
            marker_relative=marker_relative,
            tag=tag,
            base_name=final_name,
        )
    except OSError as error:
        return RenamePreview(folder, INVALID, f"无法读取文件夹：{error}")


def analyze_folders(
    sources: Iterable[str | os.PathLike[str]], options: RenameOptions
) -> list[RenamePreview]:
    previews: list[RenamePreview] = []
    seen: set[str] = set()
    reserved: set[str] = set()
    for source in sources:
        folder = Path(source).absolute()
        source_key = _path_key(folder)
        if source_key in seen:
            continue
        seen.add(source_key)
        preview = analyze_folder(folder, options, reserved)
        previews.append(preview)
        if preview.status == READY and preview.target is not None:
            reserved.add(_path_key(preview.target))
    return previews


def execute_rename(source: str | os.PathLike[str], options: RenameOptions) -> RenameResult:
    original = Path(source).absolute()
    preview = analyze_folder(original, options)
    if preview.status != READY or preview.target is None or preview.marker_relative is None:
        return RenameResult(original, preview.status, preview.message, preview.target)

    target = unique_destination(original.parent, preview.base_name)
    try:
        os.rename(original, target)
    except OSError as error:
        return RenameResult(original, FAILED, f"重命名失败：{error}", target)

    marker = target / preview.marker_relative
    try:
        marker.rmdir()
    except FileNotFoundError:
        return RenameResult(original, RENAMED, f"已改名为 {target.name}", target)
    except OSError:
        return RenameResult(
            original,
            RENAMED_MARKER_KEPT,
            f"已改名为 {target.name} · 标签目录非空或无法删除，已保留",
            target,
        )
    return RenameResult(original, RENAMED, f"已改名为 {target.name}", target, marker_removed=True)


def preserve_partial(staging: Path, output_parent: Path, archive_stem: str) -> Path | None:
    if not staging.exists():
        return None
    try:
        if not any(staging.iterdir()):
            staging.rmdir()
            return None
        destination = unique_destination(output_parent, f"{sanitize_name(archive_stem)}_解压未完成")
        staging.rename(destination)
        return destination
    except OSError:
        return staging


def finalize_extraction(
    staging: Path,
    output_parent: Path,
    archive: Path,
    options: dict[str, str],
) -> tuple[Path, str]:
    entries = list(staging.iterdir())
    payload = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging
    original_name = payload.name if payload != staging else archive.stem
    rules = TagRules(options.get("tag_prefix", "AAA_"), options.get("block_terms", "路径, 中文"))
    blocker = find_blocking_file(payload, rules.parsed_block_terms) if rules.parsed_block_terms else None
    marker = find_tag_marker(payload, rules.tag_prefix)
    tag = extract_marker_tag(marker, rules.tag_prefix) if marker else ""

    if blocker:
        final_name = original_name
        message = f"已解压 · 检测到“{blocker.name}”，保留原名"
    elif tag:
        base_name, _ = split_numbered_folder_tag(original_name)
        final_name = sanitize_name(f"{base_name} {tag}" if base_name else tag)
        message = f"已按标签改名为 {final_name}"
        try:
            marker.rmdir()
        except OSError:
            pass
    else:
        final_name = original_name
        message = "已解压 · 未找到有效标签，保留原名"

    destination = unique_destination(output_parent, sanitize_name(final_name))
    if payload == staging:
        staging.rename(destination)
    else:
        shutil.move(str(payload), str(destination))
        try:
            staging.rmdir()
        except OSError:
            pass
    return destination, message
