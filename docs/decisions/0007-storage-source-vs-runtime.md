# ADR 0007：只忽略仓库根 `/storage/`；`app/storage/` 是源码必须入库

状态：已接受
负责：忽略规则为什么必须带前导斜杠（app/storage 假绿事故）。
上游：`docs/architecture.md` §2/§3、`docs/database.md`。
改动影响：推翻本决策时新增 ADR；同步 `docs/architecture.md` §3 与 `.gitignore` 注释。

## 背景

- 历史 `.gitignore` 写的是 `storage/`（无前导斜杠），Git 会匹配**任意层级**的同名目录，于是 `app/storage/**` 的 12 个源文件从未入库。
- 后果：真机 clone 后缺少整个存储包，16 个测试报 `ModuleNotFoundError: No module named app.storage`（本机因文件仍在磁盘上而全绿，属于典型的假绿）。

## 决策

- 只忽略仓库根的运行时目录：`/storage/`（前导斜杠）。
- `app/storage/` 是源码包，必须入库；运行时产物（`storage/bot.db`、`storage/logs/`、`storage/sandbox/`、`storage/workspaces/`、`.venv/`、`__pycache__/`）保持忽略。
- 新增顶层运行时目录时，`.gitignore` 规则必须带前导斜杠。

## 备选与放弃原因

- **把包改名**（例如 `app/persistence/`）：改动面大、无必要，且不能防止同类规则再次误伤。
- **用 `!app/storage/` 反向否定**：可读性差，容易被后续规则覆盖，否决。

## 后果

- 判断「某个目录是否被跟踪」不能靠眼睛看 ✅，必须用 `git check-ignore -v <path>` 与 `git ls-files | wc -l` 复核；提交前要检查 `git status --short` 的条目数与预期一致。
- 同类风险清单：任何带「裸目录名」的忽略规则（例如 `logs`、`build`）都可能误伤源码目录。

## 验证方式

- 修复提交 `d27e1e07d2266056add802f3907b0b78d244ca7b`（`.gitignore` 第 7 行 `/storage/`）。
- `git check-ignore -v app/storage/db.py` 无匹配；跟踪文件数 92 → 104；真机重跑 283 个测试 OK（见 `docs/status.md`）。