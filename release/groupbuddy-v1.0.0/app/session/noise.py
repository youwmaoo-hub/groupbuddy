"""噪声判定：决定消息是否进入触发与模型上下文（docs/memory.md §3）。

入库时打标，不影响存储：noise=1 的消息仍然入库、可回溯。
"""

from __future__ import annotations

import re

MIN_INFORMATIVE_CHARS = 4
NON_WORD_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)
LINK = re.compile(r"https?://|www\.", re.IGNORECASE)
FENCE = re.compile(r"[\x60]{3}")
QUESTION_MARKS = ("?", "？")
QUESTION_WORDS = ("吗", "呢", "怎么", "为什么", "什么", "哪", "几", "多少", "谁")
ERROR_WORDS = ("报错", "错误", "异常", "失败", "崩溃", "跑不起来", "error", "exception", "traceback", "failed")

# 常见无信息量短句（不含疑问词；含疑问词的一律不算噪声）
NOISE_PHRASES = frozenset(
    {
        "哈哈", "哈哈哈", "哈哈哈哈", "草", "笑死", "确实", "晚安", "早", "早安",
        "嗯", "嗯嗯", "哦", "哦哦", "好的", "好", "收到", "6", "666", "绝了", "xswl", "awsl",
    }
)


def is_noise(text: str, *, mentions_bot: bool = False, reply_to_bot: bool = False) -> bool:
    """True = 噪声：不参与触发、不进短期上下文、不进摘要输入。"""
    raw = (text or "").strip()
    if not raw:
        return True
    if mentions_bot or reply_to_bot:
        return False

    lowered = raw.casefold()
    if "@" in raw or any(mark in raw for mark in QUESTION_MARKS):
        return False
    if LINK.search(raw) or FENCE.search(raw):
        return False
    if any(word in lowered for word in ERROR_WORDS):
        return False

    if lowered in NOISE_PHRASES:
        return True
    if NON_WORD_ONLY.match(raw):
        return True
    if len(raw) < MIN_INFORMATIVE_CHARS and not any(word in lowered for word in QUESTION_WORDS):
        return True
    return False
