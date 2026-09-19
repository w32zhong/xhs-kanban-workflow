# 小红书 Kanban 工作流

用 Hermes Kanban 自动完成：

```text
搜索与核验 → 两位委员并行审稿 → 委员长定稿 → 精确发布 → 独立复核/有界清理
```

发布和复核会操作真实的小红书账号。流程默认安全失败：目标、楼层、文本或登录态无法确认时不会强行发送或删除。

## 新沙箱快速配置

### 1. 检查环境

```bash
command -v hermes
command -v agent-browser
hermes doctor
hermes profile list
```

确保共享浏览器中已经登录小红书。

### 2. 准备专用 Hermes Profile

**不要使用 default profile。** 选择已有专用 profile，或先创建一个：

```bash
hermes profile create <profile-name> --clone-from default
```

> **`--profile` 接受 profile ID，不是显示名。** `hermes profile list` 的
> `显示名 (profile-id)` 一栏里，括号内的才是要传的值。沙箱自带的 profile 显示名
> 可能与 ID 不同（例如 `efficient-Gabie (agent-3922e063be8d5bf1)`），这时
> `hermes --profile efficient-Gabie ...` 会报 `does not exist`，必须传
> `agent-3922e063be8d5bf1`。`runner-config.json` 的 `profile` 字段同样填 profile ID。

在仓库根目录配置该 profile：

```bash
cd /path/to/xhs-kanban-workflow
python3 scripts/configure-worker-profile.py \
  --profile <profile-name> \
  --workspace "$(pwd)"
```

该脚本会：

- 启用 Kanban worker 工具；
- 禁用 Vision；
- 使用本地 terminal；
- 将 worker 工作目录固定为本仓库。

然后确认 profile 的模型和凭据可用：

```bash
hermes --profile <profile-name> config check
hermes --profile <profile-name> tools list
```

### 3. 配置运行参数

推荐直接编辑 `runner-config.json`：

```json
{
  "profile": "<profile-name>",
  "workspace": ".",
  "account_name": "<当前登录的小红书昵称>",
  "board_slug": "xhs-run",
  "poll_seconds": 3,
  "timeout_minutes": 30,
  "keep_board": true,
  "max_output_chars": 6000
}
```

也可以不改文件，运行时传入 `--profile` 和 `--account-name`。

## 运行

完整跑一轮：

```bash
cd /path/to/xhs-kanban-workflow
python3 run.py \
  --profile <profile-name> \
  --account-name '<当前登录的小红书昵称>'
```

只测试搜索阶段，不进入起草和发布：

```bash
python3 run.py --scout-only \
  --profile <profile-name> \
  --account-name '<当前登录的小红书昵称>'
```

同一时间只能运行一轮；`run.py` 会加进程锁。完整流程通常需要数分钟到半小时。

持续循环运行（无需任何环境变量，profile 与昵称直接读 `runner-config.json`）：

```bash
./run_loop.sh
```

`run_loop.sh` 会等待每轮结束后再启动下一轮；单轮失败也会记录并继续。可用 `XHS_LOOP_SLEEP_SECONDS` 调整轮次间隔，`XHS_AGENT_PROFILE` / `XHS_ACCOUNT_NAME` 可临时覆盖 `runner-config.json`。

## 查看状态

```bash
hermes kanban --board xhs-run list --json
hermes kanban --board xhs-run show <task-id> --json
hermes kanban --board xhs-run log <task-id>
```

## 磁盘与状态保留（每轮不累积）

保留策略完全由仓库代码控制，不依赖任何外部 supervisor / cron 清理脚本。每轮结束后 `run.py`
都会删除本轮产生的全部状态，长期循环不会让磁盘增长：

- 本轮的全部卡片：先 `archive` 再 `archive --rm`，并对看板库 `VACUUM` 回收空间
  （`archive` 只是把卡片标记为已归档，不删数据）；
- 早前轮次或崩溃轮次残留的归档卡片；
- 本轮 worker 产生的会话：`hermes -p <profile> sessions prune --source kanban --yes`
  （正在运行的会话会被自动跳过，因此随时执行都安全），随后 `sessions optimize` 回收空间；
- dispatcher 为每张卡写的 worker 日志文件（`hermes kanban gc --log-retention-days 0`，
  默认保留 30 天，这里改成整轮清除；在轮次结束时执行，因此不会删掉活动 worker 的日志）；
- `runtime/`、`runtime-params/`、`logs/`、`evidence/`、`roundtable/`、`current-run.json`
  等运行时文件；
- 本轮打开的浏览器 session 与多余标签页。

`run_loop.sh` 自己以 append 模式持有 `logs/loop.out.log` 并在每轮开始时截断，所以日志只保留
一轮的输出，也不依赖 supervisor 的日志轮转。worker profile 的 `logging`（级别、单文件上限、
不保留备份）与 `sessions`（自动清理）由 `scripts/configure-worker-profile.py` 一并写入。

所以一个全新环境只需要：克隆仓库 → 跑一次 `scripts/configure-worker-profile.py` → 填好
`runner-config.json` → `./run_loop.sh`。不需要额外的配置或清理步骤。

## 发布安全规则

- Publisher 只在委员长 `APPROVE` 后发送一次。
- 定稿必须是**单行文本**。发布前会把 `\n`/`\r` 归一化为空格（`run.py` 的 `normalize_approved_draft()` 兜底 + Publisher 步骤内归一化），因为小红书评论框按回车即提交，含换行的定稿只会发出前半句。
- 输入前后都必须逐字校验；不一致时只允许清空编辑器重输一次（累计最多 2 次），仍不一致记 `TEXT_MISMATCH` 且不发送；禁止补丁式硬凑。
- 开页后先关闭广告屏蔽/插件/引导类遮挡弹窗，再绑定回复框；只点关闭类按钮，不点弹窗内的下载、安装、去登录、领取、购买等动作。
- 目标楼层已经有当前账号回复或定稿重复时，不发送。
- 发布后由 fresh session 独立复核。
- 正确且唯一：`VERIFIED`。
- 本轮造成重复：只删除多余重复，保留一条，记 `DUPLICATES_DELETED`。
- 本轮发出的内容与定稿语义不符：只删除本轮错发回复，记 `MISMATCH_DELETED`。
- 无法确认回复属于本轮、线程未穷尽或页面结构不明确：不删除，返回安全失败状态。
- 禁止删除历史回复、其他账号回复或其他楼层内容。


权威运行规范在：

- `pipeline.json`：任务图；
- `prompts/`：worker 操作规则（现行五份：`scout-worker`、`review-worker`、`chair-worker`、`publish-send-worker`、`publish-verify-worker`）；
- `schemas/`：结果格式；
- `highclaws-features.md`：产品事实唯一来源，圆桌与委员长只能据此引用真实能力；
- `roundtable-angles.md`：圆桌评审角度库；
- `prompts/xhs-reply-话术-原典.md`：必须逐字保留的原始话术资产。

其它目录说明：

- `source-archive/`：早期资料留档，**仅作可疑参考，不作执行依据**；
- `SCOUT-REFINEMENT.md` + `scout-pipeline.json`：`--scout-only` 单阶段调试路径；
- 独立的 `search-worker`、独立 `verify-worker` 等早期阶段已废弃。
