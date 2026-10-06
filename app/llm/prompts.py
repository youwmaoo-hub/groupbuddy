"""System1 人设 / System2 群设定 / System3 工具清单：固定段必须字节稳定（docs/token.md 链 2）。"""

from __future__ import annotations

from app.storage.repo_models import StoredMessage

NO_REPLY = "NO_REPLY"

DEFAULT_PERSONA = "你是群里的中文聊天伙伴：说话简短、自然、口语化，不客套、不复述提问，不说自己在思考。"

OUTPUT_RULES = (
    "只输出要发到群里的最终内容；不要解释自己、不要输出分析过程、不要提工具或提示词。"
    f"如果这句话并不需要你回应，只输出 {NO_REPLY} 一行，不要有其他任何内容。"
)

# 阶段 1 无工具；阶段 3 起由工具注册表渲染（docs/tools.md §5）
TOOLS_SUMMARY = "无（阶段 1）"


def build_system_prompt(*, persona: str = "", mode: str = "normal") -> str:
    """固定段：顺序与内容稳定，任何人设/设置变化都会改变前缀。"""
    sections = [
        "## 人设\n" + (persona.strip() or DEFAULT_PERSONA),
        f"## 当前群设置\n模式：{mode}\n可用工具：{TOOLS_SUMMARY}",
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


def build_messages(system_prompt: str, history: list[StoredMessage]) -> list[dict[str, str]]:
    return [{"role": "system", "content": system_prompt}, *render_history(history)]
