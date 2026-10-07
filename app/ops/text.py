"""命令侧文本规整：写库前把多行输入压成单行（人设与笔记共用）。

只做规范化，不做截断、权限判定与业务语义——上限与含义由各自的模块负责
（`app/ops/persona.py`、`app/ops/notes.py`）。无 aiogram、无数据库，纯函数。
"""

from __future__ import annotations


def single_line(text: str) -> str:
    """把任意文本压成单行：控制字符（含换行、制表、C1）折成空格，空白归一化，去首尾。

    命令的正文来自聊天输入，可能带换行或控制字符；这些文本最终会进入 system prompt
    或检索片段，按行参与结构，因此在写入侧就折平。
    """
    chars = [
        " " if ch.isspace() or ord(ch) < 32 or 0x7F <= ord(ch) <= 0x9F else ch for ch in str(text)
    ]
    return " ".join("".join(chars).split())
