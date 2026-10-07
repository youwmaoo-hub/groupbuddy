"""写入事务边界：把若干条写语句合成一个原子单元（`docs/database.md` §6）。

整个进程共享同一条 aiosqlite 连接，各 repo 原先自己 `await connection.commit()`：
主表 + FTS 的相邻两条写语句之间可能抛错，留下"半成品"事务，随后被任意一次别的
`commit()` 顺带提交（技术债 T9）。这里统一用 `SAVEPOINT` 包住一段写入。

为什么用 `SAVEPOINT` 而不是 `BEGIN IMMEDIATE`：连接是共享的，另一任务可能已经开着
事务，`BEGIN` 会直接报 "cannot start a transaction within a transaction"；savepoint
可以安全嵌套，只有最外层的 `RELEASE` 才真正提交（嵌套时由外层提交）。失败路径
`ROLLBACK TO` + `RELEASE` 只回滚本段，不会把责任推给调用方。
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiosqlite

#: savepoint 名字必须互不相同，嵌套时才能各自回滚。
_counter = itertools.count(1)


@asynccontextmanager
async def transaction(connection: aiosqlite.Connection) -> AsyncIterator[None]:
    """成功即提交（最外层 savepoint），异常则整体回滚后原样抛出。"""
    name = f"tx{next(_counter)}"
    await connection.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        await connection.execute(f"ROLLBACK TO {name}")
        await connection.execute(f"RELEASE {name}")
        raise
    await connection.execute(f"RELEASE {name}")
