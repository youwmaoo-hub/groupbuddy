"""冷备份与校验脚本（阶段 9，契约见 `docs/database.md` §5）。

只读源库、不读 `.env`、不需要凭据，因此**可以在 Bot 运行中执行**。

用法示例：
    python scripts/backup_db.py
    python scripts/backup_db.py --db /home/bot/app/storage/bot.db --dest /home/bot/app/storage/backups --keep 7

退出码：0 = 备份成功且完整性检查通过；1 = 备份或校验失败；2 = 参数/数据库缺失。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage.backup import DEFAULT_KEEP, SnapshotInfo, create_backup  # noqa: E402

DEFAULT_DB = "storage/bot.db"
DEFAULT_DEST = "storage/backups"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQLite 冷备份与校验（阶段 9）")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite 路径（默认 {DEFAULT_DB}）")
    parser.add_argument("--dest", default=DEFAULT_DEST, help=f"备份目录（默认 {DEFAULT_DEST}）")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"保留最近几份，0 = 不清理（默认 {DEFAULT_KEEP}）")
    return parser.parse_args(argv)


def render(info: SnapshotInfo) -> str:
    counts = " ".join(f"{table}={count}" for table, count in info.counts.items())
    return (
        f"备份完成 path={info.path} bytes={info.bytes} user_version={info.user_version} "
        f"integrity={info.integrity} {counts}"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        info = create_backup(Path(args.db), Path(args.dest), keep=args.keep)
    except FileNotFoundError:
        print(f"找不到数据库 {args.db}；请先启动一次 Bot 生成数据库", file=sys.stderr)
        return 2
    except Exception as error:  # 失败必须可见；错误文本只含路径与 SQLite 原因，不含任何凭据
        print(f"备份失败：{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(render(info))
    if info.removed:
        print(f"已清理旧快照 {len(info.removed)} 份")
    return 0 if info.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
