# ADR 0004：沙箱分 Tier A / Tier B 两档

状态：已接受
负责：为什么沙箱分两档，两档的边界差在哪里。
上游：`docs/security.md` §4、`docs/deployment.md` §12.6。
改动影响：推翻本决策时新增 ADR；同步 `docs/security.md` §4、`docs/tools.md` §`run_code`、`docs/deployment.md` §12。

## 背景

- 大多数 `run_code` 只需要「跑一段计算并打印结果」，不需要读写文件。
- 少数任务（处理本群工作区里的文件）需要读写权限，但只应看到本群目录。

## 决策

- **Tier A**：不挂载任何宿主目录、无网络、非 root、工作目录用镜像默认（根文件系统只读，只有 `/tmp` 是 `tmpfs` 可写）。
- **Tier B**：rootless Podman + `--userns=keep-id`，把**本群**工作区挂到 `/workspace:rw`，并 `--workdir /workspace`；要求该群 `allow_write=true` 且该群有 `run_code` 权限。
- 两档共用同一组安全限制（12 项）：`--network=none`、`--read-only`、`--tmpfs /tmp:rw,noexec,nosuid,size=16m`、`--cap-drop=ALL`、`--security-opt no-new-privileges`、内存/CPU/PID 上限、`--ulimit nofile`/`fsize` 等。
- 档位判定由程序完成（`allow_write` + 后端能力），模型不能选择档位。

## 备选与放弃原因

- **单一档位（一律挂载工作区）**：所有代码都能写宿主目录，攻击面变大，否决。
- **只给 tmpfs 不挂载**：写不回工作区，失去 Tier B 的用途。
- **Tier C（宿主直接执行命令）**：永不提供。

## 后果

- `--workdir /workspace` **只能**在有挂载时出现：无挂载时容器内没有该路径，Podman 会直接拒绝启动（exit 126）。阶段 7 首次真机验收就是因为无条件追加 `--workdir` 而全项失败，修复见 commit `434f2f8`。
- argv 组装必须保持单一入口（`app/sandbox/spec.py`），两档差异只在「挂载 + workdir + 档位判定」三处。

## 验证方式

- `tests/offline/test_sandbox.py`：Tier A 断言不含 `--workdir` 与 `/workspace`；Tier B 断言恰好一次且值为 `/workspace`。
- 真机：Tier A 7/7（含无网络、只读根、cgroup 限额、超时销毁）、Tier B 4/4（本群读写、宿主可见、其他群不可见、宿主目录不可见）。