"""run_code：在一次性沙箱容器里执行 Python（F4.6、docs/tools.md §run_code）。"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.tools.registry import ToolContext, ToolError, ToolSpec

# 输入/输出上限固定（docs/tools.md §run_code）；stdout/stderr 各 8KB 由沙箱层截断
MAX_CODE_CHARS = 20000
DEFAULT_TIMEOUT_S = 15
MAX_TIMEOUT_S = 30
SANDBOX_TOOL_TIMEOUT_S = 35.0
MAX_PAYLOAD_BYTES = 20480


class RunCodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS, description="要执行的 Python 代码")
    timeout_s: int = Field(default=DEFAULT_TIMEOUT_S, ge=1, le=MAX_TIMEOUT_S)
    workspace: bool = Field(
        default=False,
        description="true 时把本群工作区挂载到容器 /workspace；需要本群同时开启文件写入",
    )


class SandboxRunnerLike(Protocol):
    def describe(self) -> dict[str, object]: ...

    async def run(
        self,
        *,
        chat_id: int,
        code: str,
        timeout_s: int | None = None,
        workspace: bool = False,
    ) -> dict[str, object]: ...


class SandboxErrorLike(RuntimeError):
    code: str
    message: str


class RunCodeTool:
    """模型不能选择镜像、挂载、runtime 参数；权限由 Tool Policy 与本群开关决定。"""

    spec = ToolSpec(
        name="run_code",
        level="L3",
        description="在一次性容器里运行一段 Python 代码（无网络、只读根、非 root、超时即销毁）。",
        args_model=RunCodeArgs,
        timeout_seconds=SANDBOX_TOOL_TIMEOUT_S,
        max_payload_bytes=MAX_PAYLOAD_BYTES,
    )

    def __init__(self, runner: SandboxRunnerLike) -> None:
        self._runner = runner

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        workspace = bool(args.workspace)  # type: ignore[attr-defined]
        if workspace and not bool(int(context.group.get("allow_write", 0) or 0)):
            raise ToolError("permission_denied", "本群未开启文件写入，不能挂载工作区")
        try:
            return await self._runner.run(  # type: ignore[attr-defined]
                chat_id=context.chat_id,
                code=args.code,  # type: ignore[attr-defined]
                timeout_s=args.timeout_s,  # type: ignore[attr-defined]
                workspace=workspace,
            )
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - 沙箱错误码与工具错误码一致
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None)
            if isinstance(code, str) and isinstance(message, str):
                raise ToolError(code, message) from exc
            raise
