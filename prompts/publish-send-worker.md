# 精确发布 Worker v1（复用 share URL、目标楼层门禁）

目标：只在本轮定稿已批准时，打开 scout 保存的真实 share URL，精确绑定目标评论并发送一次。

只读取：

1. `./runtime/scout-result.json`；
2. `./runtime/chair-decision.json`；
3. `./prompts/xhs-reply-style.md`；
4. 本文件；
5. 任务正文中的 `OUTPUT_FILE` 与 `PARAM_FILE`。

`runtime/chair-decision.json` 的 `decision` 不是 `APPROVE`，或 `final_comment` 为空/NONE 时，立即写 `SKIPPED_NOT_APPROVED`，不得打开浏览器。

## 浏览器 session 隔离硬规则

先 source `PARAM_FILE` 取得 `SESSION_NAME`。**首次** browser 命令必须显式写成 `agent-browser --session "$SESSION_NAME" --pin-tab ...`；pin 是 sticky 的，后续命令显式写 `agent-browser --session "$SESSION_NAME" ...` 即可，无需重复 `--pin-tab`。禁止依赖默认 session，禁止省略 `--session`，禁止访问、关闭、导航或复用其他 session 的标签页。

## 快速且安全的门禁

**严格走短路径：**禁止 `agent-browser --help`、`session_search`、技能/源码/HTML/DOM 探索、无关点击实验和从首页重新搜索。直接使用 scout 的 share URL。最多重新加载页面 1 次，目标回复入口最多尝试 2 次，文字输入最多尝试 2 次（1 次首输 + 1 次有界重输，规则见第 12 步）；仍无法绑定或校验不一致就立即写 `NEEDS_VERIFIER` / `TEXT_MISMATCH` 并完成，不得继续探索。

1. 从 scout 读取 `post_url`、`target_comment_author`、`target_comment_text`、`target_comment_excerpt`；从 chair 读取 `final_comment`。禁止使用 publish-target-pool 或 PARAM_FILE 中的旧目标/旧草案覆盖它们。
2. 打开浏览器前先执行回复门禁：长度应由目标评论的 wish 和复杂度决定。通常 1–3 句话；超过 5 句话、超过 8 行、明显机械分点或属于完整教程式展开时，写 `TEXT_TOO_LONG` 并结束，不得发布。不要替委员长现场改稿。
3. **归一化待发送文本（强制，先于任何浏览器动作）**：把 `final_comment` 处理成单行文本后再输入——`\r\n`、`\r`、`\n` 全部替换为一个空格，连续两个以上空格合并为一个空格，去掉首尾空白。归一化结果记为 `SEND_TEXT`，之后所有比对与输入一律以 `SEND_TEXT` 为准。原因：小红书评论框按回车即提交，任何换行都会导致只发出前半句。若 `SEND_TEXT` 与 `final_comment` 不同（说明定稿含换行），在结果里记 `newline_normalized: YES`；相同则记 `NO`。
4. 用新的 pinned browser session 直接 `agent-browser open "$POST_URL"`。这是本轮 scout 点击产生的 share URL；无需重新从首页搜索。
5. **先清掉遮挡弹窗**：页面刚打开时若出现广告屏蔽提示、插件提示、登录引导、新手引导、活动浮层或全屏遮罩（“我知道了”“关闭”“×”“继续浏览”类按钮），用 fresh snapshot 找到关闭按钮并点击关闭，确认遮罩消失后再继续。遮挡物最多尝试关闭 2 次；关不掉但目标楼层仍能正常读取时继续，关不掉且完全无法读取时才写 `BROWSER_ERROR` 并完成。禁止点击弹窗内的下载、安装、去登录、领取、购买等动作，也不得向任何弹窗输入内容。
6. snapshot + read 锁定作者和逐字评论。作者 + 唯一前缀必须匹配。
7. 只检查目标楼层当前可见回复；若有明确“展开 N 条回复”，最多展开一次再 read。
8. **先做幂等检查：**如果目标楼层已经出现当前账号发布的 `SEND_TEXT`（按归一化文本比对），视为本轮或前次尝试已经发送成功；不得再次输入或点击发送。立即写 `SEND_SUCCESS`，`send_clicked` 填 `YES`（表示本轮发送动作已发生，不表示本次重跑再次点击），reason 明确写“existing exact reply reconciled”，然后 `kanban_complete`，让最后的发布复核 task 独立确认。
9. 当前账号 UNKNOWN 不阻止首次发布。仅当目标楼层明确已有当前账号的其他回复，或存在无法判断归属的逐字重复时，写 `NEEDS_VERIFIER`，不得继续发送。
10. 点击目标一级评论自己的回复入口。优先使用明确“回复”文字；若 action row 明确按页面顺序显示两个连续动作数字，解释为“点赞数 → 回复气泡数”，可以点击第二个纯数字作为该楼层的回复入口。前提是作者 + 评论前缀已唯一锁定、该数字确属同一一级楼层，且不是子回复或帖子总评论数。每次点击后必须用 fresh read 确认出现 `回复 <目标作者>`；累计最多尝试 2 次。对象不对或仍未绑定时立即写 `NEEDS_VERIFIER` 并完成，不输入。
11. fresh read 必须出现 `回复 <目标作者>`。输入 `SEND_TEXT` 前先确认编辑器为空；若编辑器里已有残留文本，先清空（全选删除或点击清除入口）再输入。
12. 输入后立刻逐字校验：fresh snapshot 确认发送按钮 enabled，且 fresh editable ref 的 `get text` 与 `SEND_TEXT` 完全一致。
    - 一致 → 进入第 13 步。
    - 不一致（重复前缀、缺字、多字、混入其它字符）→ **允许一次有界重输**：先清空编辑器，再完整重输一次 `SEND_TEXT`，然后再校验一次。输入动作累计最多 2 次（1 次首输 + 1 次重输）。
    - 重输后仍不一致 → 写 `TEXT_MISMATCH` 并完成，**不得点击发送**，也不得再无界重试。禁止用“连续单字补齐”或“插入补丁字符”的方式硬凑一致。
13. 点击发送一次。**调用返回后立即**写 `runtime/publish-result.json` 并执行 `kanban_complete`：编辑器清空/重置且 URL 未异常变化时记 `SEND_SUCCESS`；点击结果不确定时记 `NEEDS_VERIFIER` 且 `send_clicked=YES`。不要继续做深度页面验证，目标楼层渲染、重复和内容一致性由最后的 `发布复核` task 负责。

不要因帖子超过 7 天、账号未知、其他楼层存在相同文本而阻止。不得 URL 构造、DOM/eval、坐标点击、Vision；**禁止重复发送**，输入动作只允许第 12 步规定的那一次有界重输。

将 JSON 写入 `runtime/publish-result.json`：

```json
{
  "status": "SEND_SUCCESS | SKIPPED_NOT_APPROVED | TEXT_TOO_LONG | TARGET_FLOOR_NOT_FOUND | DUPLICATE_IN_TARGET_THREAD | NEEDS_VERIFIER | TEXT_MISMATCH | SEND_FAILED | BROWSER_ERROR",
  "send_clicked": "YES | NO",
  "editor_reset_after_send": "YES | NO | UNKNOWN",
  "post_url": "本轮 share URL",
  "target_comment_author": "目标作者",
  "final_comment": "本轮定稿（chair 原值）",
  "send_text": "归一化后的单行实际发送文本",
  "newline_normalized": "YES | NO",
  "text_input_attempts": 1,
  "popup_dismissed": "YES | NO | NONE",
  "reason": "一句话"
}
```

`text_input_attempts` 只能是 `1`（首输即一致）或 `2`（发生过一次有界重输）；不得大于 2。`newline_normalized=YES` 表示定稿含换行、已在输入前归一化为空格。`popup_dismissed` 记录是否处理过遮挡弹窗（`NONE` 表示页面没有弹窗）。

完成后立即 `kanban_complete`，metadata 至少包含 `status`、`send_clicked`、`output_file`。
