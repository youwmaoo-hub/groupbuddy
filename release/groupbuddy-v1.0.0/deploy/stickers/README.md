# 贴纸 catalog 与素材导入（一次性运维）

目的：让 `send_sticker` 能在真实群里按情绪取到贴纸。运行期只读 SQLite 的 `stickers` 表
（`app/storage/repo/stickers.py`），按 valence/arousal/tags 打分选图（`app/tools/builtin/send_sticker.py`）。

**Telegram 自己的贴纸包和本项目是两回事**：Telegram 贴纸包只是素材来源；只有登记进本项目的
`stickers` 表（每个群一份），`send_sticker` 才能按情绪选到。贴纸库为空时运行期不下发该工具。

## 1. 目录约定

| 路径 | 是否入库 | 说明 |
|---|---|---|
| `deploy/stickers/catalog.json` | 是 | 情绪槽位定义（key/emotion/emoji/tags/valence/arousal/asset/source/license） |
| `deploy/stickers/assets/` | **否**（`.gitignore`） | 素材本体，部署方自行准备；体积与版权都不适合进 Git |

`catalog.json` 只定义槽位，**不含素材本体**。当前 catalog 有 **104 个槽位**，逐张对齐公开贴纸包
`deepseek_whale_girl`（title `@dejavuBlog 的大肥鱼`，104 张全为 video/WebM；素材同源仓库
`DejavuMoe/deepseek_wale_girl` 的 `telegram_webm/`，**MIT License © 2026 Dejavu Moe**）：

- 条目顺序 = 贴纸包顺序，`emoji` 取自该贴纸包自身（含重复 emoji，如 👍🍚🐟🚀🪙 各 3 张），
  `key` 用对齐后的仓库文件名（stem）。因此流程 A 按 emoji 配对时是恒等映射，重复 emoji 也不会错位。
- 注意：`getStickerSet` 的返回顺序**不等于**仓库编号顺序，而是仓库顺序整体前移一位
  （包内第 1 张 = 仓库 `002_haha`，包内第 104 张 = 仓库 `001_hehe`，已用逐张 `file_size` 相等证明）。
  重新生成 catalog 时务必沿用这个对齐关系，否则重复 emoji 的槽位会串位。
- `asset` 是可选字段，只在流程 B（自备素材 + `--asset-dir` 校验）里用到；流程 A 不需要本地素材，
  `deploy/stickers/assets/` 保持为空即可。
- 情绪覆盖：开心、笑、害羞、哭、生气、无语、震惊、惊恐、困、得意、卖萌、喜欢、点赞、拒绝、答应、
  拜拜、认输、抱抱、吃饭、加油、谢谢、对不起、晚安、早安、加班、摸鱼、失败、摆烂、卷、躺平、感动、
  破防、疑惑、疑惑/敷衍、等待、思考、上线、回滚、背锅、打钱、转发、在看、磕 CP、鲸落……

`source` / `license` 未填写的条目，导入脚本会逐条警告（政策见 §3）。当前 catalog 的每一条都写了
`source`（`telegram:deepseek_whale_girl/<stem>.webm`）与 `license`（MIT，Dejavu Moe）。

## 2. 素材规格

- 优先 Telegram 已适配格式：静态 `.webp`（512×512、≤64 KB）、视频 `.webm`（VP9、≤256 KB）、
  动图 `.tgs`（≤64 KB）。**推荐 webp / webm**：静态图最稳，视频贴纸体积上限更大。
- 文件名必须与 `catalog.json` 的 `asset` 一致，且必须是**裸文件名**（不接受任何路径分隔符，
  导入脚本会拒绝 `../`、盘符等，见 `app/ops/sticker_catalog.py` 的 `validate_asset_name`）。
- 一个槽位一张；同一情绪想放多张时，在 catalog 里新增 `key`（tags 更具体即可）。

## 3. 来源与许可政策

- **只导入来源与许可清楚的素材**；来源不明、作者未授权、平台条款禁止再分发的素材一律不入库。
- 本项目不内置任何素材本体，也不把 `.env` 或 `file_id` 写进文档（`file_id` 与 Bot 身份绑定，
  换 Token 后要重新导入）。
- **已采用来源（2026-10-08）**：`DejavuMoe/deepseek_wale_girl`（GitHub）的 104 张
  `telegram_webm/`，**MIT License © 2026 Dejavu Moe**，官方 Telegram 包
  `https://t.me/addstickers/deepseek_whale_girl`；`catalog.json` 的每条 `source` / `license` 已写明。
  导入走流程 A（贴纸包按 emoji 匹配），不需要下载素材本体。
- 其它社区「DeepSeek 大肥鱼 / 鲸鱼娘」二创素材（**许可状态均未核实**，仅作检索起点，使用前请自行确认
  授权）：`the-beating-light-of-the-nail/deepseek-chan-meme-pack`、`EDMOK/blue-fish-archive`、
  B 站与 tg.okhk.net 的合集帖。未核实许可的素材一律**不导入**。
- 部署方自制的素材（自己截图 / 自己画 / 已获授权）最安全：在 `catalog.json` 的 `source`
  与 `license` 里写清来源与许可，再走下面的导入流程。

## 4. 导入流程

前提：先让 Bot 启动一次完成迁移（`stickers` 表需要 schema `user_version ≥ 2`）。

**A. 已有 Telegram 贴纸包（推荐）**：按 emoji 把贴纸包配到 catalog 槽位，一条命令批量导入。

```bash
BOT_TOKEN=... python scripts/import_sticker_set.py --set-name <贴纸包短名> --chat-id <群 ID> --db storage/bot.db --dry-run
# 确认报告无误后去掉 --dry-run
```

**B. 手工/自备 manifest**：把 `file_id` / `file_unique_id` 填进 catalog 条目（或另存一份
manifest JSON），指定素材目录做名称与可选 sha256 校验：

```bash
python scripts/register_sticker.py --manifest deploy/stickers/catalog.json --chat-id <群 ID> \
    --asset-dir deploy/stickers/assets --dry-run
python scripts/register_sticker.py --manifest deploy/stickers/catalog.json --chat-id <群 ID>
```

**C. 单张补登记 / 替换**（原有的单张模式，参数不变）：

```bash
python scripts/register_sticker.py --chat-id <群 ID> --file-id <file_id> \
    --file-unique-id <file_unique_id> --valence 0.8 --arousal 0.6 --tags 开心,好耶
```

三个流程都是**幂等**的：唯一键是 `(chat_id, file_unique_id)`，重复执行只更新字段，不会产生重复行。
导入完成后核对：`sqlite3 storage/bot.db "SELECT COUNT(*) FROM stickers WHERE chat_id = <群 ID>"`。
