"""一次性本地运维脚本：把 Telegram 贴纸包批量导入本项目的 stickers 表（阶段 8）。

按 emoji 把贴纸包里的贴纸配到 `deploy/stickers/catalog.json` 的情绪槽位，再走与
`scripts/register_sticker.py` 相同的幂等 UPSERT（唯一键 `(chat_id, file_unique_id)`）。

    BOT_TOKEN=... python scripts/import_sticker_set.py --set-name <短名> --chat-id <群 ID> --dry-run

只读 `BOT_TOKEN` 环境变量（不读 `.env`、不回显 Token）；Telegram 贴纸包只是素材来源，
登记进本项目 `stickers` 表之后 `send_sticker` 才能按情绪取到。素材来源与许可政策见
`deploy/stickers/README.md` §3。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ops.sticker_catalog import (  # noqa: E402
    CatalogError,
    load_manifest,
    match_sticker_set,
    register_entries,
)

REQUIRED_VERSION = 2
DEFAULT_DB = "storage/bot.db"
DEFAULT_CATALOG = "deploy/stickers/catalog.json"
API_BASE = "https://api.telegram.org"


class StickerSetError(RuntimeError):
    """取贴纸包失败（错误信息里绝不出现 Token）。"""


def fetch_sticker_set(set_name: str, *, token: str, timeout: float = 10.0) -> list[dict[str, object]]:
    """调用 Bot API getStickerSet；失败只报类型或 Telegram 的 description，不回显 URL。"""
    url = f"{API_BASE}/bot{token}/getStickerSet?name={urllib.parse.quote(set_name)}"
    request = urllib.request.Request(url, headers={"User-Agent": "deepseek-fish-bot/sticker-import"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise StickerSetError(f"请求 Telegram 失败：{type(error).__name__}") from error
    if not isinstance(payload, dict) or not payload.get("ok"):
        description = payload.get("description") if isinstance(payload, dict) else None
        raise StickerSetError(f"Telegram 返回失败：{description or 'unknown'}")
    result = payload.get("result")
    stickers = result.get("stickers") if isinstance(result, dict) else None
    if not isinstance(stickers, list) or not stickers:
        raise StickerSetError("贴纸包为空或结构不符")
    return [dict(item) for item in stickers if isinstance(item, dict)]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 Telegram 贴纸包导入 stickers 表（阶段 8）")
    parser.add_argument("--set-name", required=True, help="贴纸包短名（t.me/addstickers/<短名>）")
    parser.add_argument("--chat-id", type=int, required=True, help="群 chat_id")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help=f"catalog 路径（默认 {DEFAULT_CATALOG}）")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 路径（默认 storage/bot.db）")
    parser.add_argument("--token-env", default="BOT_TOKEN", help="读取 Token 的环境变量名（默认 BOT_TOKEN）")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP 超时秒数")
    parser.add_argument("--dry-run", action="store_true", help="只做匹配与统计，不连数据库")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get(args.token_env, "").strip()
    if not token:
        print(f"缺少环境变量 {args.token_env}（本脚本不读 .env）", file=sys.stderr)
        return 2

    try:
        catalog = load_manifest(args.catalog)
        stickers = fetch_sticker_set(args.set_name, token=token, timeout=args.timeout)
        result = match_sticker_set(stickers, catalog)
    except (CatalogError, StickerSetError) as error:
        print(f"导入失败：{error}", file=sys.stderr)
        return 2

    print(
        f"贴纸包 {args.set_name}：共 {len(stickers)} 张，匹配 {len(result.matched)} 个槽位，"
        f"包内未使用 {len(result.unused_in_set)} 张"
    )
    if result.missing_in_set:
        missing = "、".join(entry.emotion for entry in result.missing_in_set)
        print(f"未匹配到的槽位（贴纸包里没有同 emoji）：{missing}", file=sys.stderr)
    for entry, _ in result.matched:
        if not entry.source or not entry.license:
            print(
                f"警告：槽位 {entry.key} 未填写 source/license，请确认来源与许可"
                "（deploy/stickers/README.md §3）",
                file=sys.stderr,
            )
    if not result.matched:
        print("没有任何槽位匹配成功，未写库", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"[dry-run] 未写库；确认无误后去掉 --dry-run 重新执行")
        return 0

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
            report = register_entries(
                connection,
                chat_id=args.chat_id,
                entries=[entry for entry, _ in result.matched],
            )
        except CatalogError as error:
            print(f"登记失败：{error}", file=sys.stderr)
            return 2
    finally:
        connection.close()

    print(f"已登记 chat_id={args.chat_id} 条目={report.total} 新增={report.inserted} 更新={report.updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
