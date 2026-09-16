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

持续循环运行：

```bash
XHS_AGENT_PROFILE=<profile-name> \
XHS_ACCOUNT_NAME='<当前登录的小红书昵称>' \
./run_loop.sh
```

`run_loop.sh` 会等待每轮结束后再启动下一轮；单轮失败也会记录并继续。可用 `XHS_LOOP_SLEEP_SECONDS` 调整轮次间隔。

## 查看状态

```bash
hermes kanban --board xhs-run list --json
hermes kanban --board xhs-run show <task-id> --json
hermes kanban --board xhs-run log <task-id>
```

`run.py` 会保留当前 `xhs-run` 看板，清理本轮临时文件和多余浏览器标签页。

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
