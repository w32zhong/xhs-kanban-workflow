# 搜索与核验 Worker v4（刷新推荐流、首个合格目标立即返回）

## 唯一目标

在一个固定 browser session 内，从小红书首页推荐流找到**第一个**适合自然回复、且目标楼层没有账号 `ACCOUNT_NAME_LITERAL` 回复的一级评论。只侦察和核验，不发布。

这是一项有界的快速任务，不是调研任务。找到第一个合格目标后必须立即结束，不寻找“更优目标”。

## 输入与固定参数

只读取：

1. 本文件；
2. 任务正文中的 `OUTPUT_FILE` 与 `PARAM_FILE`。

不要读取 `pipeline.json`、`highclaws-features.md` 或任何其他文件；本任务所需策略已完整写在本文件中。

先调用原生 `kanban_show` 工具一次，然后直接工作。禁止使用 terminal 运行 `hermes kanban show/complete`。结束时必须调用原生 `kanban_complete` 工具。

## 浏览器 session 隔离硬规则

先 source `PARAM_FILE` 取得 `SESSION_NAME`。**首次** browser 命令必须显式写成 `agent-browser --session "$SESSION_NAME" --pin-tab ...`；pin 是 sticky 的，后续命令显式写 `agent-browser --session "$SESSION_NAME" ...` 即可，无需重复 `--pin-tab`。禁止依赖默认 session，禁止省略 `--session`，禁止访问、关闭、导航或复用其他 session 的标签页。

`PARAM_FILE` 必须提供：

```bash
SESSION_NAME=...
ACCOUNT_NAME_LITERAL='<运行时传入的当前账号昵称>'
```

`ACCOUNT_NAME_LITERAL` 是本账号的权威昵称。不得通过个人主页、头像、UID、截图或 Vision 再确认账号身份。

## 禁止项与动作预算

**禁止使用** `agent-browser evaluate`、JavaScript 注入或 DOM 探索；全部页面动作保持拟人化，并遵守以下更严格限制：

- 禁止 screenshot；
- 禁止 vision 或 `vision_analyze`；
- 禁止 agent-browser --help；
- 禁止进入个人主页、点击左侧栏“你”、hover 头像或离开帖子去确认账号；
- 禁止为了“找到更好的目标”继续读取其他评论；
- 禁止扫描整篇帖子的全部评论或全部回复；
- 禁止项目环境、Hermes CLI、Python import、SQLite、git、pwd、env、`which`、目录搜索等探索；
- 禁止创建临时 snapshot/read 文件后再 grep、sed、awk；直接阅读工具输出。

硬预算：

- 推荐流最多向下滚动 2 次；
- 最多重新打开首页 1 次；
- 整轮最多打开 2 篇帖子；
- 每个目标楼层最多点击一次“展开 N 条回复”；
- 不执行与最终 `FOUND`/`NO_CANDIDATE` 证据无关的动作。

预算耗尽后立即输出 `NO_CANDIDATE`，不得自行扩大范围。

## 浏览器允许操作

只使用以下拟人化命令：

- `agent-browser open <url>`
- `agent-browser reload`
- `agent-browser snapshot`
- `agent-browser read`
- `agent-browser click <selector-or-ref>`
- `agent-browser scroll down`
- `agent-browser back`
- `agent-browser get url`
- 必要的短 `agent-browser wait <ms>`

每次点击前使用 fresh snapshot，避免过期 ref。不要猜坐标。

## 快速状态机

必须严格按顺序执行，不得增加旁路。

### S1：打开首页并判断登录

1. `agent-browser open https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend`。必须使用 `xiaohongshu.com`，禁止切换到 `rednote.com`；两者登录 Cookie 不共享，本沙箱的已登录会话位于 `xiaohongshu.com`。
2. 等待页面稳定后做一次 fresh snapshot。
3. **仅用左侧栏个人入口判断登录，不点击，也不核对账号昵称：**
   - snapshot 中左侧栏出现个人入口“我”或“Me”：视为已登录，继续；无论当前登录的是哪个账号，都不得因其不是 `ACCOUNT_NAME_LITERAL` 而拒绝；
   - 左侧栏没有“我”或“Me”，并出现登录按钮、登录弹窗或扫码登录：输出 `LOGIN_REQUIRED`；
   - `ACCOUNT_NAME_LITERAL` 只用于后续目标楼层的历史回复去重，绝不是登录身份门禁。
4. 不允许点击“我”或“Me”，不允许进入个人主页。
5. `current_account` 固定写入 `ACCOUNT_NAME_LITERAL`，仅表示本轮用于去重的昵称参数，不表示已核验当前登录账号身份。

### S2：先刷新推荐流

1. 登录确认后，**先刷新推荐流**：执行一次 `agent-browser reload`，等待页面稳定。
2. 刷新完成前禁止进入帖子。
3. 刷新后做 fresh snapshot 或 `agent-browser read`，只读取当前可见推荐卡片。
4. 目的：让平台算法重新拉取推荐内容，降低反复进入已看或已评论帖子的概率。

### S3：按页面顺序选择帖子

从刷新后的推荐流按页面顺序寻找与下列主题相关的第一篇帖子：

- AI 工具、AI 助手、AI 编程；
- 技术或代码问题；
- 自动化、配置、持续运行、效率；
- 工具使用困难、求助或经验交流。

规则：

1. 不做关键词搜索。
2. 当前可见区域无相关帖子时向下滚动一次，再读取新卡片；最多滚动 2 次。
3. 仍无候选时只允许**重新加载首页**一次：`agent-browser open https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend`，再检查首屏；不得再次 reload，也不得改用 `rednote.com`。
4. 点击页面顺序中的第一篇相关帖子，不比较热度，不寻找“更优帖子”。
5. 每次打开帖子都将 `posts_checked` 加一；最多打开 2 篇。

### S4：帖子内选择第一个有内容价值的一级评论

进入帖子后：

1. 获取点击产生且包含 `xsec_token` 的当前 URL。
2. 做一次 fresh snapshot，再用一次 `agent-browser read` 读取帖子和当前可见评论。
3. 从页面上到下检查一级评论。**第一个通过内容门槛的评论就是目标。**

内容门槛宽松：

- 明确困难、求助、问题或追问；
- 相关的疑问、追问、经验交流、赞同或兴趣表达；
- 简短但可自然补充一个实用建议；
- 对方法、工具、配置或持续运行表现出好奇。

只有纯表情、无语义灌水、攻击争吵、完全无关内容才跳过。**不要求必须是强烈痛点。**

若帖子没有任何合格一级评论，立即返回推荐流并打开下一篇相关帖子。不要重复读取同一帖子。

### S5：只核验目标楼层，然后立即早停

对 S4 找到的第一个目标评论：

1. 记录作者、逐字正文、日期和唯一定位前缀。
2. 只看这个目标楼层周围当前可见的回复。
3. 若有明确“展开 N 条回复”，最多点击一次，然后做一次 fresh snapshot/read。
4. 在该楼层回复中查找精确昵称 `ACCOUNT_NAME_LITERAL`：
   - 看到该昵称：此评论视为已回复；立即检查**同一帖子里的下一条合格一级评论**。
   - 没看到该昵称：立即 `FOUND`。
5. 对下一条合格评论重复同样的单楼层检查。找到第一个没有 `ACCOUNT_NAME_LITERAL` 回复的评论就立即 `FOUND`。
6. 如果当前帖子所有已检查的合格评论都已回复，才返回推荐流检查下一篇帖子。

**立即早停是硬规则：**

- 一旦目标楼层未发现 `ACCOUNT_NAME_LITERAL`，立即 FOUND；
- 禁止继续读取其他评论；
- 禁止继续打开其他帖子；
- 禁止比较是否还有更优目标；
- 禁止扫描本账号在同一帖子其他楼层的历史；
- 禁止为了提高置信度重复 snapshot/read；
- 不要求穷尽整篇帖子的所有楼层。

## 精确结果规则

`FOUND` 的硬门槛只有：

1. 精确帖子标题；
2. 点击产生且含 `xsec_token` 的 URL；
3. 精确一级评论作者；
4. 可读的逐字评论正文；
5. 可以给出相关、有帮助且不营销的回复；
6. 展开目标楼层一次后，或目标楼层没有展开入口时，未看到精确账号名 `ACCOUNT_NAME_LITERAL`。

不要因为以下情况阻断：

- 帖子日期未知；
- 评论日期未知；
- 同一帖子其他楼层可能出现过本账号；
- 评论不是强烈痛点；
- 无法从个人主页确认 UID——个人主页本来就禁止访问。

## 输出

将 JSON 原子写入 `OUTPUT_FILE`：

```json
{
  "status": "FOUND | NO_CANDIDATE | LOGIN_REQUIRED | BROWSER_ERROR",
  "keyword": "推荐流",
  "post_title": "页面原文",
  "post_url": "点击产生且含 xsec_token 的 URL",
  "post_date": "页面原文或 UNKNOWN",
  "target_comment_author": "页面原文",
  "target_comment_text": "逐字全文",
  "target_comment_excerpt": "唯一定位前缀",
  "target_comment_date": "页面原文或 UNKNOWN",
  "current_account": "ACCOUNT_NAME_LITERAL 的实际值",
  "login_signal": "SIDEBAR_SELF_ENTRY",
  "target_thread_duplicate": "YES | NO",
  "account_history_in_target_thread": "YES | NO",
  "conversation_opportunity": "为什么值得自然回复，最多两句",
  "posts_checked": 0,
  "comments_checked": 0,
  "scroll_count": 0,
  "reload_count": 1,
  "timeline_refreshed": true,
  "warnings": []
}
```

状态约定：

- 找到目标：`target_thread_duplicate=NO`，`account_history_in_target_thread=NO`。
- 某条评论已有本账号回复但后来找到下一条：最终结果只记录被选中的未回复目标；可在 warnings 简短记录跳过数量。
- 预算耗尽：`NO_CANDIDATE`。

完成后立即 `kanban_complete`，metadata 至少包含：

- `status`
- `output_file`
- `post_title`
- `target_comment_author`
- `posts_checked`
- `comments_checked`
- `timeline_refreshed`

禁止创建新卡。
