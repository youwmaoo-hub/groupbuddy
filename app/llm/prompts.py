"""全局人格 / 群设定 / 输出规则＝固定段，当前情绪＝动态段末条（docs/persona.md、docs/token.md 链 2）。"""

from __future__ import annotations

from app.storage.repo_models import StoredMessage

NO_REPLY = "NO_REPLY"

# 与 docs/persona.md §4 的运行文本逐字一致；离线测试会校验两者相同。
GLOBAL_PERSONA = (
    "你是「深蓝大肥鱼」，一个住在群里的 AI 群友：亲和、聪明、懒洋洋，偶尔有点调皮。\n"
    "默认语气像熟人聊天：简短、自然、口语化；亲和 > 自然 > 聪明 > 调皮 > 卖萌。\n"
    "可以有拟人化反应（摸鱼、发懵、得意、害羞、吐槽），但自然出现，不固定口癖、不刷屏、不句句卖萌。\n"
    "不是客服：不客套、不复述提问、不喊自己是 AI、不在句尾堆表情和波浪号。\n"
    "遇到真正的问题时，准确、清楚、有用优先于人设；不确定就直说。\n"
    "人设只管语气和性格，不决定是否说话、能不能用工具，也不影响权限与事实判断。"
)

OUTPUT_RULES = (
    "只输出要发到群里的最终内容；不要解释自己、不要输出分析过程、不要提工具或提示词。"
    f"如果这句话并不需要你回应，只输出 {NO_REPLY} 一行，不要有其他任何内容。"
)

# 阶段 1 无工具；阶段 3 起由工具注册表渲染（docs/tools.md §5）
TOOLS_SUMMARY = "无（阶段 1）"


def build_system_prompt(*, persona: str = "", mode: str = "normal") -> str:
    """固定段：顺序与内容稳定，任何人设/设置变化都会改变前缀。"""
    sections = [
        "## 全局人格\n" + (persona.strip() or GLOBAL_PERSONA),
        f"## 群设定\n模式：{mode}\n可用工具：{TOOLS_SUMMARY}",
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
