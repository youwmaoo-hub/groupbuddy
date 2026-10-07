"""一次性本地运维脚本：登记贴纸到 stickers 表（阶段 5；阶段 8 增加 manifest 批量导入）。

两种用法：
    单张：python scripts/register_sticker.py --chat-id -1001234567890 \\
        --file-id CAACAgIAAxkBAAE... --file-unique-id AQAD... \\
        --valence 0.6 --arousal 0.4 --tags 开心,摸鱼
    批量：python scripts/register_sticker.py --chat-id -1001234567890 \\
        --manifest deploy/stickers/catalog.json [--asset-dir deploy/stickers/assets] [--dry-run]

只做登记：不做群主命令、不自动抓取贴纸包、不读 .env、不需要任何凭据。
素材规格、来源与许可政策见 `deploy/stickers/README.md`。
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ops.sticker_catalog import (  # noqa: E402
    CatalogEntry,
    CatalogError,
    load_manifest,
    register_entries,
    resolve_asset,
)

REQUIRED_VERSION = 2
DEFAULT_DB = "storage/bot.db"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="登记贴纸到 stickers 表（阶段 5 / 阶段 8）")
    parser.add_argument("--chat-id", type=int, required=True, help="群 chat_id")
    parser.add_argument("--manifest", default="", help="catalog/manifest 文件或目录（批量模式）")
    parser.add_argument("--asset-dir", default="", help="素材目录：校验 asset 裸文件名与可选 sha256")
    parser.add_argument("--dry-run", action="store_true", help="只校验与统计，不写库")
    parser.add_argument("--file-id", default="", help="Telegram file_id（单张模式；不会回显）")
    parser.add_argument("--file-unique-id", default="", help="Telegram file_unique_id（单张模式）")
    parser.add_argument("--valence", type=float, default=None, help="情绪效价 -1..1（单张模式）")
    parser.add_argument("--arousal", type=float, default=None, help="情绪唤醒度 -1..1（单张模式）")
    parser.add_argument("--tags", default="", help="逗号分隔标签，可为空（单张模式）")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 路径（默认 storage/bot.db）")
    return parser.parse_args(argv)


def _split_tags(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]


def _single_entry(args: argparse.Namespace) -> CatalogEntry:
    if not (args.file_id and args.file_unique_id):
        raise CatalogError("单张模式需要 --file-id 与 --file-unique-id（或用 --manifest 批量）")
    if args.valence is None or args.arousal is None:
        raise CatalogError("单张模式需要 --valence 与 --arousal")
    for label, value in (("valence", args.valence), ("arousal", args.arousal)):
        if not -1.0 <= value <= 1.0:
            raise CatalogError(f"{label} 必须在 -1..1 之间")
    return CatalogEntry(
        key="single",
        emotion="",
        emoji="",
        tags=tuple(_split_tags(args.tags)),
        valence=args.valence,
        arousal=args.arousal,
        file_id=args.file_id,
        file_unique_id=args.file_unique_id,
    )


def _verify_assets(entries: list[CatalogEntry], asset_dir: Path) -> None:
    """素材目录校验：裸文件名（resolve_asset 拒绝穿越）+ 存在性 + 可选 sha256。"""
    for entry in entries:
        if not entry.asset:
            continue
        path = resolve_asset(asset_dir, entry.asset)
        if not path.is_file():
            raise CatalogError(f"素材缺失：{path}")
        if entry.sha256:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != entry.sha256:
                raise CatalogError(f"素材 sha256 不匹配：{entry.asset}")


def _warn_unlicensed(entries: list[CatalogEntry]) -> None:
    for entry in entries:
        if not entry.source or not entry.license:
            print(
                f"警告：槽位 {entry.key} 未填写 source/license，"
                "请确认素材来源与许可后再用于生产（deploy/stickers/README.md §3）",
                file=sys.stderr,
            )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = Path(args.db)
    if not path.is_file():
        print(f"找不到数据库 {path}；请先启动一次 Bot 生成数据库", file=sys.stderr)
        return 2

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version < REQUIRED_VERSION:
            print("数据库 schema 版本过低：请先启动一次 Bot 以应用迁移（migration 2 建 stickers 表）", file=sys.stderr)
            return 2
        try:
            if args.manifest:
                entries = load_manifest(args.manifest)
                if args.asset_dir:
                    _verify_assets(entries, Path(args.asset_dir))
                _warn_unlicensed(entries)
            else:
                entries = [_single_entry(args)]
            report = register_entries(
                connection, chat_id=args.chat_id, entries=entries, dry_run=args.dry_run
            )
        except CatalogError as error:
            print(f"登记失败：{error}", file=sys.stderr)
            return 2
    finally:
        connection.close()

    if args.manifest:
        prefix = "[dry-run] " if report.dry_run else ""
        print(
            f"{prefix}已处理 chat_id={args.chat_id} 条目={report.total} "
            f"新增={report.inserted} 更新={report.updated}"
        )
    else:
        # 只打印内部 id 与情绪参数：file_id 不回显、不写日志
        sticker_id = report.ids[0] if report.ids else 0
        print(
            f"已登记 chat_id={args.chat_id} sticker_id={sticker_id} "
            f"valence={args.valence} arousal={args.arousal} tags={list(entries[0].tags)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
