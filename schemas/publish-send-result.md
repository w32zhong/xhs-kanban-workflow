# 发布结果固定格式

```text
PUBLISH_SEND_RESULT
status: SEND_SUCCESS | NEEDS_VERIFIER | TARGET_NOT_FOUND | TOKEN_URL_MISSING | COMMENT_TARGET_NOT_FOUND | COMMENT_CONTEXT_UNCONFIRMED | WRONG_ELEMENT_CLICKED | REPLY_CONTEXT_UNCONFIRMED | WRONG_REPLY_TARGET | EDITOR_REF_INVALID | TEXT_MISMATCH | SEND_FAILED | LOGIN_REQUIRED | BROWSER_ERROR | SETUP_ERROR
session_name: <session>
share_url: <点击产生且含 xsec_token；无则 NONE>
target_title: <指定标题>
target_comment_author: <指定作者>
target_comment_excerpt: <指定评论唯一前缀>
target_floor_match: AUTHOR_AND_EXCERPT | NO | UNKNOWN
reply_context_evidence_mode: A11Y | READ_TEXT | NONE
reply_entry_kind: TEXT_REPLY | NUMBERED_REPLY_BUBBLE | NONE
vision_calls: 0
vision_format_retries: 0
reply_target_after_type_check: A11Y | READ_PRECHECK_CARRIED_FORWARD | UNKNOWN
draft_input_method: PARAM_FILE_VARIABLE
newline_normalized: YES | NO
text_input_attempts: 1 | 2
popup_dismissed: YES | NO | NONE
text_typed_once: YES | NO
text_exact_match: YES | NO | UNKNOWN
send_enabled_after_type: YES | NO | UNKNOWN
send_clicked: YES | NO
send_success: YES | NO | UNKNOWN
editor_reset_after_send: YES | NO | UNKNOWN
page_url_after_send: <发送后页面 URL；无变化则 SAME>
evidence_files:
  - NONE
obstacles:
  - <无则 NONE>
```

规则：

- `SEND_SUCCESS` 只用于：目标楼层的作者和唯一评论前缀均匹配、回复对象已明确、定稿通过参数变量输入、文字与**归一化后的单行文本**逐字匹配、发送按钮已 enabled、已点击发送、发送后编辑器已重置且页面未异常。
- **发布前必须归一化**：`final_comment` 中的 `\r\n`、`\r`、`\n` 全部替换为空格，连续两个以上空格合并为一个。`newline_normalized=YES` 表示原定稿含换行并已被归一化；`NO` 表示原本就是单行。归一化后的文本才是比对与输入的基准。
- `text_input_attempts` 只允许 `1`（首输即一致）或 `2`（发生过一次有界重输：清空编辑器后重输一次）。禁止超过 2 次，禁止用补丁式字符插入硬凑一致；重输后仍不一致必须 `TEXT_MISMATCH` 且不得发送。
- `popup_dismissed` 记录开页后的遮挡弹窗处理结果；`NONE` 表示页面没有弹窗。只允许点击关闭类按钮，禁止点击弹窗内的下载、安装、去登录、领取、购买等动作，也不得向弹窗输入内容。
- `SEND_FAILED` 用于：发送按钮点击后无响应、编辑器未清空、页面报错、或发送按钮仍 enabled 但文字未消失。
- `READ_TEXT` 表示使用 `agent-browser read` 确认 snapshot 缺失的评论正文与点击后的 `回复 <作者>`。
- `vision_calls` 与 `vision_format_retries` 永远为 `0`；read 缺少关键字段时必须 `NEEDS_VERIFIER`，不得输入或发送。
- `NUMBERED_REPLY_BUBBLE` 只允许用于一级楼层 action row 中已确认的第二个数字动作。
- 多同作者楼层必须通过 `agent-browser read` 区分；无法区分时 fail-closed。
- `evidence_files` 固定为 `NONE`。
- `send_clicked: YES` 是本 schema 与输入演练 schema 的核心区别。
- 完成后调用注入的 `kanban_complete`。
