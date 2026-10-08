"""运维与权限面（阶段 8）：管理员判定与群主命令通道。

放在 `app/ops/` 而不是 `app/services/`：`app/services/` 是阶段 10 才建的服务层
（业务唯一入口），这里只解决"谁能用命令"这一件事（docs/architecture.md §3）。
"""
