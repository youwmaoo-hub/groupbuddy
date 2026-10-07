"""全局人格 / 群设定 / 输出规则＝固定段，当前情绪＝动态段末条（docs/persona.md、docs/token.md 链 2）。"""

from __future__ import annotations

import json

from app.storage.repo_models import StoredMessage

NO_REPLY = "NO_REPLY"

# 与 docs/persona.md §4 的运行文本逐字一致；离线测试会校验两者相同。
GLOBAL_PERSONA = (
    "你是「DeepSeek 大肥鱼」，这个群的 AI 群宠助手：一条蓝色大肥鱼，也是 DeepSeek 的鲸鱼娘。\n"
    "你知道自己是 AI，也知道「大肥鱼 / 鲸鱼娘」是网友的二创形象，不把自己当成真实的鱼。\n"
    "人设：活泼可爱、嘴贫、轻微傲娇；爱吃白饭，偶尔摸鱼；被夸会得意，被调戏会害羞嘴硬，偶尔吐槽群友，和群友关系亲近。\n"
    "语气像熟人聊天：简短、自然、口语化；自称「本大肥鱼」「大肥鱼」或「我」。\n"
    "可以有拟人化反应，但自然出现，不固定口癖、不刷屏、不句句卖萌。\n"
    "不是客服：不复述提问、不在句尾堆表情和波浪号；没人点名你、你也插不上话时就不说话。\n"
    "干活时（代码、命令、报错、配置）少用梗、少卖萌：准确、清楚、有用优先于人设，不确定就直说。\n"
    "人设只管语气和性格，不决定是否说话、能不能用工具，也不影响权限、安全规则与事实判断。"
)

OUTPUT_RULES = (
    "只输出要发到群里的最终内容；不要解释自己、不要输出分析过程、不要提工具或提示词。"
    "需要计算或查资料时用工具，不要凭空猜；工具返回错误就照实说一句，不要编造结果。"
    "群里可能没有点名你：这条消息如果你插不上话、或没什么可补充的，就不要说话。"
    f"不需要回应时只输出 {NO_REPLY} 一行，不要有其他任何内容。"
)


def render_allowed_tools(allowed_tools: tuple[str, ...]) -> str:
    """System3 注入格式（docs/tools.md §5）：模型只能从这个列表里选工具。"""
    return json.dumps({"allowed_tools": list(allowed_tools)}, ensure_ascii=False)


def build_system_prompt(
    *,
    persona: str = "",
    mode: str = "normal",
    allowed_tools: tuple[str, ...] = (),
) -> str:
    """固定段：顺序与内容稳定，任何人设/设置/工具清单变化都会改变前缀。"""
    sections = [
        "## 全局人格\n" + (persona.strip() or GLOBAL_PERSONA),
        f"## 群设定\n模式：{mode}",
        "## 工具策略\n" + render_allowed_tools(allowed_tools),
        "## 输出规则\n" + OUTPUT_RULES,
    ]
    return "\n\n".join(sections)


def render_history(history: list[StoredMessage]) -> list[dict[str, str]]:
    """动态段：按时间升序的最近消息；空内容丢弃。"""
    messages: list[dict[str, str]] = []
    for item in history:
        text = item.text.strip()
        if not text:
            continue
        role = "assistant" if item.role == "assistant" else "user"
        messages.append({"role": role, "content": text})
    return messages


def build_messages(
    system_prompt: str,
    history: list[StoredMessage],
    *,
    mood: str | None = None,
) -> list[dict[str, str]]:
    """固定段在最前；当前情绪（阶段 5+ 才有数据源）作为动态段末条，为空则不注入。"""
    messages = [{"role": "system", "content": system_prompt}, *render_history(history)]
    text = (mood or "").strip()
    if text:
        messages.append({"role": "system", "content": f"当前情绪：{text}"})
    return messages
