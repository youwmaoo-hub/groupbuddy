"""一次性本地运维脚本：写入/更新一条群记忆笔记（阶段 6）。

只做登记：不做群主命令、不做面板、不读 .env、不需要凭据。
用法示例：
    python scripts/register_note.py --chat-id -1001234567890 --name 部署 --text "生产用 systemd 托管"
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

from app.session.retrieval import term_tokens  # noqa: E402
from app.storage.repo.notes import (  # noqa: E402
    FTS_DELETE_SQL,
    FTS_INSERT_SQL,
    SELECT_ONE_SQL,
    UPSERT_SQL,
)

REQUIRED_VERSION = 3
DEFAULT_DB = "storage/bot.db"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="写入/更新一条群记忆笔记（阶段 6）")
    parser.add_argument("--chat-id", type=int, required=True, help="群 chat_id")
    parser.add_argument("--name", required=True, help="笔记名（同名覆盖，version 递增）")
    parser.add_argument("--text", required=True, help="笔记内容（≤500 字）")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 路径（默认 storage/bot.db）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    text = args.text.strip()
    if not text or len(text) > 500:
        print("笔记内容需为 1–500 字", file=sys.stderr)
        return 2

    path = Path(args.db)
    if not path.is_file():
        print(f"找不到数据库 {path}；请先启动一次 Bot 生成数据库", file=sys.stderr)
        return 2

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version < REQUIRED_VERSION:
            print("数据库 schema 版本过低：请先启动一次 Bot 以应用迁移（migration 3 建 notes/summaries）", file=sys.stderr)
            return 2
        previous = connection.execute(SELECT_ONE_SQL, (args.chat_id, args.name)).fetchone()
        tokens = term_tokens(text)
        now = int(time.time())
        connection.execute(UPSERT_SQL, (args.chat_id, args.name, text, tokens, now, now))
        row = connection.execute(SELECT_ONE_SQL, (args.chat_id, args.name)).fetchone()
        if row is None:
            print("写入失败", file=sys.stderr)
            return 1
        if previous is not None:  # external content FTS：先删旧 tokens 再插新
            connection.execute(FTS_DELETE_SQL, (previous[0], previous[4]))
        connection.execute(FTS_INSERT_SQL, (row[0], tokens))
        connection.commit()
        version_number = int(row[5])
    finally:
        connection.close()

    print(f"已写入笔记 chat_id={args.chat_id} name={args.name} version={version_number} chars={len(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
