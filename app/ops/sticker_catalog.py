"""贴纸 catalog / manifest：情绪槽位校验与一次性批量导入（见 `deploy/stickers/README.md`）。

职责分离：运行期只读 `stickers` 表（`app/storage/repo/stickers.py`），按情绪选贴纸的逻辑
属于 `app/tools/builtin/send_sticker.py`；本模块只服务于**运维侧导入**，不参与任何 LLM 调用，
也不被运行期 import。

调用方：`scripts/register_sticker.py`（单张 / manifest 批量）、
`scripts/import_sticker_set.py`（从 Telegram 贴纸包按 emoji 匹配后导入）。
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.storage.repo.stickers import UPSERT_SQL, encode_tags

MANIFEST_KEYS = frozenset({
    "key", "emotion", "emoji", "tags", "valence", "arousal",
    "asset", "source", "license", "sha256", "file_id", "file_unique_id",
})
REQUIRED_KEYS = ("key", "emotion", "emoji", "tags", "valence", "arousal")
# 素材名必须是裸文件名：这些字符一律拒绝，避免路径穿越或写到他处
FORBIDDEN_NAME_CHARS = ("/", "\\", ":", "\x00")


class CatalogError(ValueError):
    """manifest / catalog 内容不合法（fail-closed：宁可拒绝也不猜）。"""


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """一个情绪槽位。`file_id`/`file_unique_id` 由导入流程回填后才可写库。"""

    key: str
    emotion: str
    emoji: str
    tags: tuple[str, ...]
    valence: float
    arousal: float
    asset: str = ""
    source: str = ""
    license: str = ""
    sha256: str = ""
    file_id: str = ""
    file_unique_id: str = ""

    @property
    def bound(self) -> bool:
        """是否已经带上 Telegram file_id（只有绑定后才能登记进库）。"""
        return bool(self.file_id.strip() and self.file_unique_id.strip())


@dataclass(frozen=True, slots=True)
class ImportReport:
    inserted: int
    updated: int
    ids: tuple[int, ...]
    dry_run: bool = False

    @property
    def total(self) -> int:
        return self.inserted + self.updated


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched: tuple[tuple[CatalogEntry, Mapping[str, object]], ...]
    missing_in_set: tuple[CatalogEntry, ...]
    unused_in_set: tuple[Mapping[str, object], ...]


def validate_asset_name(name: str) -> str:
    """素材名必须是裸文件名（拒绝路径分隔符、盘符、`..`、空名）。"""
    clean = name.strip()
    if not clean:
        raise CatalogError("asset 不能为空")
    if clean in {".", ".."}:
        raise CatalogError(f"asset 不能是 {clean!r}")
    if any(char in clean for char in FORBIDDEN_NAME_CHARS) or clean.startswith(".."):
        raise CatalogError(f"asset 只能是裸文件名，不接受路径：{name!r}")
    return clean


def resolve_asset(asset_dir: Path | str, name: str) -> Path:
    """把（已校验的）素材名解析到素材目录内；越界即拒绝（纵深防御）。"""
    directory = Path(asset_dir).resolve()
    path = (directory / validate_asset_name(name)).resolve()
    if path.parent != directory:
        raise CatalogError(f"asset 越出素材目录：{name!r}")
    return path


def _entry_from_mapping(raw: object, *, where: str) -> CatalogEntry:
    if not isinstance(raw, Mapping):
        raise CatalogError(f"{where}: 条目必须是对象")
    unknown = set(raw) - MANIFEST_KEYS
    if unknown:
        raise CatalogError(f"{where}: 未知字段 {sorted(unknown)}（拼错会被拒绝，不静默忽略）")
    missing = [key for key in REQUIRED_KEYS if not str(raw.get(key, "")).strip()]
    if missing:
        raise CatalogError(f"{where}: 缺少字段 {missing}")

    tags = raw["tags"]
    if not isinstance(tags, list) or not tags or not all(str(tag).strip() for tag in tags):
        raise CatalogError(f"{where}: tags 必须是非空字符串数组")
    try:
        valence = float(raw["valence"])
        arousal = float(raw["arousal"])
    except (TypeError, ValueError) as error:
        raise CatalogError(f"{where}: valence/arousal 必须是数字") from error
    for label, value in (("valence", valence), ("arousal", arousal)):
        if not -1.0 <= value <= 1.0:
            raise CatalogError(f"{where}: {label} 必须在 -1..1 之间")
    sha256 = str(raw.get("sha256", "")).strip()
    if sha256 and (len(sha256) != 64 or any(char not in "0123456789abcdefABCDEF" for char in sha256)):
        raise CatalogError(f"{where}: sha256 必须是 64 位十六进制")
    asset = str(raw.get("asset", "")).strip()

    return CatalogEntry(
        key=str(raw["key"]).strip(),
        emotion=str(raw["emotion"]).strip(),
        emoji=str(raw["emoji"]).strip(),
        tags=tuple(str(tag).strip() for tag in tags),
        valence=valence,
        arousal=arousal,
        asset=validate_asset_name(asset) if asset else "",
        source=str(raw.get("source", "")).strip(),
        license=str(raw.get("license", "")).strip(),
        sha256=sha256.lower(),
        file_id=str(raw.get("file_id", "")).strip(),
        file_unique_id=str(raw.get("file_unique_id", "")).strip(),
    )


def load_manifest(path: Path | str) -> list[CatalogEntry]:
    """读入 manifest：单个 JSON 文件，或目录（目录下 `*.json` 按文件名排序合并）。

    文件可以是数组，或 `{"stickers": [...]}`；条目按 `key` 去重（重复即报错）。
    """
    target = Path(path)
    files = sorted(target.glob("*.json")) if target.is_dir() else [target]
    if not files:
        raise CatalogError(f"manifest 目录里没有 JSON：{target}")
    entries: list[CatalogEntry] = []
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise CatalogError(f"manifest 不存在：{file}") from error
        except ValueError as error:
            raise CatalogError(f"{file.name}: 不是合法 JSON（{error}）") from error
        raw_list = data.get("stickers") if isinstance(data, Mapping) else data
        if not isinstance(raw_list, list):
            raise CatalogError(f"{file.name}: 顶层必须是数组，或 {{\"stickers\": [...]}}")
        entries.extend(_entry_from_mapping(item, where=file.name) for item in raw_list)

    seen: dict[str, str] = {}
    for entry in entries:
        if entry.key in seen:
            raise CatalogError(f"key 重复：{entry.key}")
        seen[entry.key] = entry.emotion
    return entries


def match_sticker_set(
    stickers: Sequence[Mapping[str, object]],
    catalog: Sequence[CatalogEntry],
) -> MatchResult:
    """按 emoji 把贴纸包里的贴纸配到 catalog 槽位：每个槽位取第一张未被占用的同 emoji 贴纸。"""
    used: set[int] = set()
    matched: list[tuple[CatalogEntry, Mapping[str, object]]] = []
    missing: list[CatalogEntry] = []
    for entry in catalog:
        chosen: int | None = None
        for index, sticker in enumerate(stickers):
            if index in used or str(sticker.get("emoji", "")).strip() != entry.emoji:
                continue
            chosen = index
            break
        if chosen is None:
            missing.append(entry)
            continue
        used.add(chosen)
        bound = CatalogEntry(
            key=entry.key,
            emotion=entry.emotion,
            emoji=entry.emoji,
            tags=entry.tags,
            valence=entry.valence,
            arousal=entry.arousal,
            asset=entry.asset,
            source=entry.source,
            license=entry.license,
            sha256=entry.sha256,
            file_id=str(stickers[chosen].get("file_id", "")).strip(),
            file_unique_id=str(stickers[chosen].get("file_unique_id", "")).strip(),
        )
        matched.append((bound, stickers[chosen]))
    unused = tuple(sticker for index, sticker in enumerate(stickers) if index not in used)
    return MatchResult(matched=tuple(matched), missing_in_set=tuple(missing), unused_in_set=unused)


def register_entries(
    connection: sqlite3.Connection,
    *,
    chat_id: int,
    entries: Sequence[CatalogEntry],
    dry_run: bool = False,
    now: int | None = None,
) -> ImportReport:
    """把（已绑定 file_id 的）条目幂等写进 `stickers`：同 chat_id + file_unique_id 冲突即更新。

    `dry_run=True` 只做校验与统计，不写库。未绑定的条目一律拒绝（列出 key），不静默跳过。
    """
    if not isinstance(chat_id, int) or chat_id == 0:
        raise CatalogError("chat_id 必须是非 0 整数")
    unbound = [entry.key for entry in entries if not entry.bound]
    if unbound:
        raise CatalogError("manifest 缺少 file_id/file_unique_id 的条目：" + ", ".join(unbound))

    stamp = int(time.time()) if now is None else int(now)
    inserted = 0
    updated = 0
    ids: list[int] = []
    with connection:  # 事务：全部成功或全部回滚
        for entry in entries:
            cursor = connection.execute(
                "SELECT id FROM stickers WHERE chat_id = ? AND file_unique_id = ?",
                (chat_id, entry.file_unique_id),
            )
            row = cursor.fetchone()
            cursor.close()
            if row is None:
                inserted += 1
            else:
                updated += 1
                ids.append(int(row[0]))
            if dry_run:
                continue
            connection.execute(
                UPSERT_SQL,
                (
                    chat_id,
                    entry.file_id,
                    entry.file_unique_id,
                    entry.valence,
                    entry.arousal,
                    encode_tags(entry.tags),
                    stamp,
                ),
            )
            cursor = connection.execute(
                "SELECT id FROM stickers WHERE chat_id = ? AND file_unique_id = ?",
                (chat_id, entry.file_unique_id),
            )
            written = cursor.fetchone()
            cursor.close()
            if row is None and written is not None:
                ids.append(int(written[0]))
    return ImportReport(inserted=inserted, updated=updated, ids=tuple(ids), dry_run=dry_run)
