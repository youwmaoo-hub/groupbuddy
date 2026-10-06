"""一次性本地运维脚本：把一张 Telegram 贴纸登记进 stickers 表（阶段 5）。

只做登记：不做群主命令、不做批量抓取、不读 .env、不需要任何凭据。
用法示例：
    python scripts/register_sticker.py --chat-id -1001234567890 \
        --file-id CAACAgIAAxkBAAE... --file-unique-id AQAD... \
        --valence 0.6 --arousal 0.4 --tags 开心,摸鱼
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage.repo.stickers import UPSERT_SQL, encode_tags  # noqa: E402

REQUIRED_VERSION = 2
DEFAULT_DB = "storage/bot.db"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="登记一张贴纸到 stickers 表（阶段 5）")
    parser.add_argument("--chat-id", type=int, required=True, help="群 chat_id")
    parser.add_argument("--file-id", required=True, help="Telegram file_id（不会回显）")
    parser.add_argument("--file-unique-id", required=True, help="Telegram file_unique_id")
    parser.add_argument("--valence", type=float, required=True, help="情绪效价 -1..1")
    parser.add_argument("--arousal", type=float, required=True, help="情绪唤醒度 -1..1")
    parser.add_argument("--tags", default="", help="逗号分隔标签，可为空")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 路径（默认 storage/bot.db）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not -1.0 <= args.valence <= 1.0 or not -1.0 <= args.arousal <= 1.0:
        print("valence/arousal 必须在 -1..1 之间", file=sys.stderr)
        return 2

    path = Path(args.db)
    if not path.is_file():
        print(f"找不到数据库 {path}；请先启动一次 Bot 生成数据库", file=sys.stderr)
        return 2

    tags = [item.strip() for item in args.tags.replace("，", ",").split(",") if item.strip()]
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version < REQUIRED_VERSION:
            print("数据库 schema 版本过低：请先启动一次 Bot 以应用迁移（migration 2 建 stickers 表）", file=sys.stderr)
            return 2
        connection.execute(
            UPSERT_SQL,
            (
                args.chat_id,
                args.file_id,
                args.file_unique_id,
                args.valence,
                args.arousal,
                encode_tags(tags),
                int(time.time()),
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id FROM stickers WHERE chat_id = ? AND file_unique_id = ?",
            (args.chat_id, args.file_unique_id),
        ).fetchone()
    finally:
        connection.close()

    sticker_id = int(row[0]) if row else 0
    # 只打印内部 id 与情绪参数：file_id 不回显、不写日志
    print(
        f"已登记 chat_id={args.chat_id} sticker_id={sticker_id} "
        f"valence={args.valence} arousal={args.arousal} tags={tags}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
