# 流程调试变更记录

> 本文件按时间顺序记录调试版本，**最新版本在文件末尾**。
> 当前生产流程为 `dynamic-e2e-quality-roundtable-v3`：`搜索与核验 → 双委员圆桌 → 委员长定稿 → 精确发布 → 独立发布复核`。
> 早期单阶段调试稿（独立 `search-worker`、独立 `verify-worker`、`e2e_loop.py`、`watch_run.py`）已废弃，见文末 v0.48。

## v0.1 — 搜索阶段最小闭环

- 从旧目录复制资料到 `source-archive/`，明确旧资料仅是可疑参考。
- 暂不直接构建整条发布流水线，先用两个不同模型调试搜索与评论定位。
- Worker 不加载额外官方 skills。
- 新增机械化搜索步骤、固定失败状态和固定输出 schema。
- 每轮新建 board、task 和浏览器 session，避免继承旧上下文。
- 搜索 worker 最多检查 3 篇、最多交付 1 个候选，防止小模型无限探索。
- 禁止 eval，禁止手拼裸详情 URL，页面变化后必须重新 snapshot。

### 待观察假设

1. 首页搜索框是否能被两个模型稳定识别。
2. Enter 与搜索按钮的触发路径是否稳定。
3. 搜索结果 ref 是否能稳定进入带 `xsec_token` 的详情页。
4. 小模型能否区分帖子正文、一级评论和子回复。
5. 小模型能否明确绑定“我方回复”到目标楼层，而非整页误判。

## v0.2 — 首轮启动即重跑

### 日志证据

- Luna worker 在执行业务步骤前读取 README、current-run、pipeline、runner、CHANGELOG、git 状态，并尝试 `hermes kanban show`；说明“不要探索环境”放得不够靠前、也不够具体。
- Luna worker 主动加载 `spa-browser-automation`，违反本调试包“不依赖官方 skills”的目标。
- 两个 worker 首次执行长 session 名的 `agent-browser` 命令都立即失败，但日志没有保留明确 stderr；Luna 擅自换成 `xhs-e24f8df9` 后成功，破坏了由任务指定 session 的可复现隔离。
- Gemini worker 在失败后用 `which/file/head/strings` 研究二进制，并发生多次上下文压缩；说明失败分支缺少严格停止条件。
- Gemini 增加 `AGENT_BROWSER_SOCKET_DIR=/tmp` 后浏览器成功启动，说明该环境变量应成为固定初始化步骤，而不是由小模型临场猜测。

### 修订

- 在 prompt 最前面列出唯一允许读取的三个文件，明确禁止 git、目录、README 和 Kanban 上下文探索。
- 明确禁止主动 `skill_view` 加载任何额外 Skill。
- 固定加入 `AGENT_BROWSER_SOCKET_DIR=/tmp`。
- 浏览器失败只允许按相同 session 重试一次，禁止改 session 名。
- 禁止 `which/file/strings/head` 等二进制侦察；失败时直接结构化上报。

### 重跑决定

首轮未等待搜索结果，立即 reclaim、硬删除整板，并以全新 board/task/session 从 v0.2 重跑。

## v0.3 — 搜索页状态与点击目标修正

### 日志与独立浏览器证据

- Luna 输入关键词并点击搜索按钮后，URL 仍为 `/explore`，因此误报 `SEARCH_TRIGGER_FAILED`；委员长独立进入其 session 后确认搜索框保留关键词，页面卡片已经切换为高度相关结果。这证明小红书存在“首页内联搜索结果”，不能只用 URL 判定搜索是否成功。
- Gemini 成功进入完整搜索页，但先后点击无文本图片 link、其他 ref 和筛选项；说明“点击搜索结果”仍过于抽象，需要明确卡片结构和只点标题 link。
- Gemini 打开详情后使用 `click --help`、`scroll --help`、临时 `/tmp` 截图和 vision，流程过度探索；应给出固定滚动次数和评论结构。
- 两个 worker 仍主动运行 `hermes kanban show`；Luna 更进一步直接读取 Kanban SQLite。说明必须明确禁止 CLI/DB，并要求只用 `kanban_complete` 工具完成。
- Luna 在被 reclaim 后又被 gateway dispatcher 自动重新认领，证明仅 reclaim 不足以终止当前错误轮；整轮废弃时必须尽快切换并删除 board。
- 长 session 名首次曾导致浏览器启动失败；短名成功稳定，因此 runner 改用 `xhs-HHMMSS-N`。

### 修订

- 把“URL 变为搜索页”和“仍在 explore 但结果卡已刷新”都定义为搜索成功。
- 明确搜索结果卡的结构，只允许点击中间的笔记标题 link。
- 明确详情浮层的识别、最多两次固定滚动以及评论常见结构。
- 禁止查看浏览器子命令 help 和无必要 vision 探索。
- 禁止 Hermes Kanban CLI 与 SQLite 读取，完成必须调用 `kanban_complete` 工具。
- session 名缩短，避免 daemon/socket 路径或启动异常。

### 重跑决定

v0.2 已立即删除，开始全新 v0.3 搜索阶段重跑。

## v0.4 — 抑制 worker 启动仪式与误点

### 日志证据

- v0.3 中 Luna 在 prompt 已明确禁止后，仍先执行 `git status`、`hermes kanban show`、搜索 `kanban_show` 实现、读取环境和 SQLite，随后才进入浏览器；说明禁止规则必须同时放到卡正文第一行和 prompt 文件最顶部，不能只藏在“浏览器硬规则”中。
- Gemini 的业务操作明显收敛，但在回到搜索页后点击了与目标无关的 `@e133`；说明 ref 在页面变化后虽然重新 snapshot，模型仍可能凭编号而不是文字选择。后续继续观察标题选择，必要时增加“动作前在日志中复述 ref 对应标题”的确认步骤。
- v0.3 的搜索和详情浏览已可正常启动，短 session 名和 `/tmp` socket 设置有效。

### 修订

- 卡正文首句直接禁止项目/Kanban 探索。
- prompt 顶部增加最高优先级跳过启动仪式的明确清单。
- prompt 版本提升到 v0.4。

### 重跑决定

v0.3 未等待结果，直接硬删除整板并以全新上下文启动 v0.4。

## v0.5 — 调试者/委员长分离与资源上限

### 用户纠正

- 当前聊天中的打钳是看板外的独立流程调试者，不是圆桌委员长。
- 完整看板中的委员长应作为独立 worker/session 运行，使用与打钳同款可靠模型。
- 调试阶段完整清理角色尚未运行，因此必须由调试者手动限制标签；完整流程跑通后才由板内清理角色正常收尾。

### 实际清理

- 检查到共享浏览器已有 17 个标签，超过资源上限。
- 按稳定 CDP `targetId` 手动关闭 15 个旧调试、重复和空白标签，仅保留 1 个小红书登录态标签与 1 个 Kanban UI 标签；清理后共 2 个。
- 硬删除 3 个残留空调试 board，只保留 `default`。

### 规则修订

- README 明确区分独立调试者与板内委员长。
- 后续每次重跑前后都检查标签数；达到 8 个即主动清理，硬上限始终小于 10 个。
- 调试轮废弃时，先删除 board 停止 worker，再按 targetId 清理其遗留标签和 session。

## v0.6 — 评论空状态与 refs-first 卡壳修正

### 本轮观察

- Luna 找到相关帖子后看到评论区空状态，却把它报告为 `THREAD_UNCONFIRMED` 并提前结束。独立截图分析确认页面已经明确显示“这是一片荒地”，说明不是评论加载失败，而是该帖确实无评论；它应该换下一篇，而不是终止整个搜索。
- Gemini 虽然检查了 3 篇，但过程中频繁执行 `get html/get box/get attr class`、查看 `click --help`、坐标鼠标点击、session_search 和证据目录探索。这是典型小模型卡壳：离开 snapshot/ref 范式，用低可靠手段试探页面，耗时超过 10 分钟。
- Gemini 最终能给出三篇无候选的结构化结论，说明搜索入口、近期帖子选择和基本详情访问已大体可用；当前高频瓶颈集中在评论空状态识别和无语义 ref 时的退出策略。
- 两个 worker 仍执行自动 `kanban-worker` 的 orient 步骤。该行为来自 dispatcher 强制加载的基础 Skill，而不是额外 `--skill`；当前本地 prompt 无法完全压过系统级指令，因此不再为此无限重跑。我们的任务卡本身仍保持 `skills: []`，未传官方业务 Skill。

### 修订

- Prompt 提升到 v0.6。
- 明确“这是一片荒地/暂无评论”表示已定位评论区但该帖无评论，必须换下一篇；“点击评论”是发布入口，禁止点击。
- `THREAD_UNCONFIRMED` 仅用于已经找到真实目标评论、但无法确认该楼层回复状态的情况。
- 禁止 `get box/get html/get attr class`、坐标鼠标、命令 help、session_search 和证据目录探索。
- 最新 snapshot 无明确语义 ref 时，只允许有限滚动或返回搜索页换下一篇。
- 撤销人为 stagger；两个独立搜索卡恢复一次 dispatch 并行启动。此前 CDP 短暂失败已有 prompt 内 10 秒重试，不应为单次故障长期牺牲吞吐。

### 重跑决定

本轮搜索阶段暴露明确高频问题，已删除旧板并清理标签，使用全新 task/session 重跑 v0.6。

## v0.7 — 强制展开目标线程与限制视觉兜底

### v0.6 观察

- Luna 找到了一个完整候选，但目标评论旁明确存在“展开 2 条回复”，它未点击就结束，并错误使用 `FOUND`。调试者接管同一 session 后，仅用一次最新 snapshot 就清晰看到目标作者“溪溪”及对应 `展开 2 条回复` ref；点击后 800ms 即成功展开。说明这不是网站阻碍，而是 prompt 没把展开设成强制验收门槛。
- Luna 还主动加载额外浏览器 Skill、读取 README/CHANGELOG/watch log，并用 vision 和 `get text body`；这与精简目标不符。
- Gemini 仍用多张 `/tmp` 截图、多次 vision、hover 和截图复制处理评论。最终判断基本合理，但耗时接近任务上限。独立分析确认其最终截图中的评论数、评论文字和 THE END 可在单一画面中完成验证，不需要多轮视觉探测。

### 修订

- Prompt 提升到 v0.7。
- 任何目标评论旁存在 `展开 N 条回复` 时，展开成为候选交付前的强制门槛；未展开只能 `THREAD_UNCONFIRMED`。
- 点击前要求复述目标作者与展开文字，减少点到相邻楼层。
- 展开后以 `收起回复` 或子回复作者出现作为成功证据。
- 禁止 `get text body`、hover、`/tmp` 截图与复制；每任务 vision 最多一次，snapshot 已含文本时不得调用。
- Schema 同步要求 `FOUND` 必须记录 `EXPANDED N`；账号未知时不能宣称确定无我方回复。

### 下一步

再次从空板重跑搜索 v0.7。若两种模型都能在时限内按 refs-first 完成三帖检查或交付已展开候选，则搜索阶段视为基本稳定，开始加入独立验证卡。

## v0.8 — Gemini 搜索触发卡壳修正

### Loop 观察

- 调试者连续进行了多轮 15 秒 wait/list/log 检查，而不是等待后台通知。
- Luna 在约 5 分钟内完成 3 篇检查，能识别当前账号“点点”、展开目标线程并因发现我方回复淘汰候选；搜索与线程检查路径已基本稳定。
- Gemini 第一 run 崩溃后自动重试。重试中在搜索框反复执行点击、Enter、`type`、`keyboard inserttext "测试"`、错误的 `keyboard press Enter` 与 `press @ref Enter`，明显卡在搜索触发阶段。它没有遵守“只输入一次”的抽象要求，说明需要唯一、不可分叉的命令序列。

### 修订

- Prompt 提升到 v0.8。
- 搜索输入改为唯一固定路径：点击 textbox → Control+A → keyboard type 关键词 → press Enter → wait → URL + snapshot。
- 明确禁止点击无文字搜索按钮、重复输入、`agent-browser type`、`keyboard inserttext`、测试文字和自创 press 语法。
- 第一次后 textbox 保留完整关键词且结果相关即视为成功，不得继续触发。

### 重跑决定

Gemini 出现明确高频卡壳，未等待其超时；已删除 v0.7 板并清理标签，以全新上下文重跑 v0.8。

## v0.9 — 绕过不稳定的首页搜索框

### Loop 观察

- v0.8 中 Luna 按唯一固定路径成功触发搜索并正常检查帖子，说明该模型可用。
- Gemini 的同一固定路径仍不稳定：首个 run 崩溃；第二 run 执行完并输出 `SEARCH_TRIGGER_FAILED`，却未调用完成工具，触发 protocol violation；第三 run 再次从头启动。
- 第二 run 的证据表明首页搜索框会吞掉输入或失焦。这不是需要继续用 prompt 微调点击顺序解决的问题。
- 调试者用独立 session 实测直接打开官方搜索 URL：`/search_result?keyword=<URL编码>&type=51`，3 秒内稳定得到完整搜索页、正确 textbox 值和结果卡片。

### 修订

- Prompt 提升到 v0.9。
- 保留首页短暂打开仅用于确认登录状态；随后使用 Python 标准库 URL 编码关键词，直接打开官方搜索结果页。
- 明确搜索页 URL 可以构造；帖子详情 URL 仍禁止拼接，必须点击标题 ref 获取 `xsec_token`。
- 首页等待由 3 秒缩短为 1.5 秒，减少固定开销。

### 重跑决定

v0.8 因 Gemini 重复崩溃和搜索框失焦废弃。已删除整板、清理标签，并以 v0.9 重跑搜索阶段。

## v0.10 — 恢复真实用户式首页搜索

### 用户纠正

- 不使用构造的 `/search_result` URL，也不使用 curl/API；小红书反检测场景优先模仿真实用户行为。
- 即使小模型能力有限，也应通过足够细的 `agent-browser` 状态机提升稳定性，而不是绕开网页交互。

### 日志复盘

- v0.9 的 URL 直达虽能进入结果页，但不符合真实用户式访问约束，因此该轮无论结果如何均废弃。
- Gemini 日志还显示完成摘要后未及时调用完成工具而被重复执行；继续等待该轮不具调试价值。

### 修订

- Prompt 提升到 v0.10，删除搜索 URL 编码与直达路径。
- 固定为 `snapshot → click textbox → Control+A → Backspace → snapshot 验空 → click 最新 ref → keyboard type → snapshot 验证完整 value → Enter 一次 → URL + snapshot 验证结果`。
- 输入不完整时只允许一次“全部清空后完整重输”，禁止补字、测试文字、重复 Enter、无文字按钮和 URL 兜底。
- 同时接受 `/search_result` 与 `/explore` 内联相关结果，避免把真实成功误判为失败。

### 重跑决定

立即停止 v0.9 watcher，硬删除旧板，清理遗留标签，并使用全新 task/session 从 v0.10 重跑。

## v0.11 — 重新发现助手并切换为单 Gemini 调试

### 助手清单复核

- 通过实时 `hermes profile list` 与 `hermes kanban assignees --json` 重新发现助手，不沿用旧 ID 假设。
- `agent-26c319b9362c7cec` 当前模型为 `gemini-3.8-flash-high`，profile 在磁盘且可用。
- `agent-afab924c0d9aa0e7` 已不在磁盘、没有有效模型配置，只因旧任务仍 running 才残留在 assignee 输出中；不得再创建新任务给它。
- Luna 已 out of quota，本轮不再使用；之前把 `agent-26c319b9362c7cec` 标记为 Luna 的映射已经过期。

### 修订与重跑

- `pipeline.json` 改为单任务、`max_parallel: 1`，唯一 assignee 为 Gemini：`agent-26c319b9362c7cec`。
- 硬删除包含旧助手及 crash loop 的 v0.10 看板，清理浏览器标签后用全新 board/task/session 重跑。

## v0.12 — 修复 Gemini 无法完成 Kanban 协议

### 原始日志结论

- Gemini 的真实用户式浏览器路径已经稳定：搜索框清空、逐字输入、一次 Enter、依次检查三篇帖子均能完成，单段浏览器流程约一分钟，没有 URL/curl 绕行。
- 不顺滑主要发生在业务操作前后：每个 run 开始时花大量命令查找 Hermes/PYTHONPATH；输出结果后又搜索 `kanban_complete` 实现，最终没有调用完成工具，触发 protocol violation 并整项重跑。
- 根因不是搜索 prompt，而是 Gemini profile 的 `agent.disabled_toolsets` 明确禁用了 `kanban`。Dispatcher 虽能创建 worker，但完成工具未注入，导致它只能错误探索 CLI 和源码。

### 修订与重跑

- 从 `/home/agent/.hermes/profiles/agent-26c319b9362c7cec/config.yaml` 的 `agent.disabled_toolsets` 移除 `kanban`，保留浏览器操作仍由本地 `agent-browser` 文档驱动。
- 废弃当前已进入协议 crash-loop 的 board，以全新 task/session 验证：业务路径完成后应直接调用注入的 `kanban_complete`，不再探索 Hermes CLI、PYTHONPATH 或插件源码。

## v0.13 — 小虾换模与快速调试循环

### 运行结果及模型变化

- `agent-26c319b9362c7cec` 已由 Gemini 更换为 `Qwen/Qwen3.8-27B-FP8`，继续作为小虾执行 worker。
- 上一轮最终 run 已成功调用 `kanban_complete`，证明 Kanban toolset 修复有效；真实用户式搜索、标题点击、xsec_token 获取和三帖检查均完成。
- 上一轮耗时偏长，主要浪费在三帖重复浏览、snapshot 无评论正文后调用 vision，以及旧 Gemini quota 的多次自动失败重试；这些不应进入新模型调试基线。

### 加速修订

- 搜索调试上限从 3 帖降到 2 帖；当前目标是验证操作稳定性，不追求候选结果。
- 搜索阶段完全禁用 vision；snapshot 读不到评论正文或日期时记录 `COMMENT_TEXT_UNREADABLE` 并立即换帖。
- task max runtime 从 12 分钟降到 7 分钟。
- 每轮完成或发现通用问题后立即清理旧板并全新重跑，减少等待无价值结果。

## v0.14 — 锁定搜索关键词字面值

### 主动 loop 发现

- 新 Qwen 小虾启动顺滑，但将任务中的 `AI长任务总是中断` 擅自改写为 `AI赋能任务总是中断`，随后还错误声称输入成功。
- 这是小模型把关键词当作语义提示而非不可变参数；继续跑出的搜索结果无调试价值，因此不等待完成。

### 修订与重跑

- 参数改名为 `KEYWORD_LITERAL`，卡正文与 prompt 同时声明禁止翻译、润色、同义替换、增删字。
- 浏览器前要求单独抄写 `KEYWORD_LITERAL=...`；`keyboard type` 只能复制该字面值。
- snapshot 验收改为逐字符相等，并明确警示不得把“长”改成“赋能”。
- 立即废弃当前板并用全新 task/session 重跑。

## v0.15 — 参数文件变量直传

### 主动 loop 发现

- v0.14 已要求逐字抄写，但 Qwen 仍在推理中把中文 `AI长任务总是中断` 翻译成英文含义，再把错误翻译结果当作 `KEYWORD_LITERAL`。
- 说明仅靠自然语言强调“逐字”仍会经过小模型重生成，无法保证字符串保真。

### 修订与重跑

- Runner 为每个新 session 生成独立 `runtime-params/<session>.sh`，其中以 shell-safe 格式保存关键词和 session。
- 卡正文不再展示关键词，只提供 `PARAM_FILE`；worker 禁止复述关键词。
- 所有浏览器命令先 `source PARAM_FILE`，搜索输入固定为 `agent-browser keyboard type "$KEYWORD_LITERAL"`，避免模型重写字符串。
- 立即废弃 v0.14 并全新重跑。

## v0.16 — 单帖快速稳定性测试

### Timer loop 结论

- v0.15 的参数文件变量直传成功，最终 run 搜索关键词未再失真，并正确调用 `kanban_complete`。
- 但该任务前三次均达到 420 秒超时，第四次才在 356 秒完成；流程仍不满足“快速、大概率完成”。
- 日志显示小虾反复落盘 `/tmp/xhs-snap*.txt`、用 awk/grep 修理自创校验、读取临时快照，并检查两篇帖子。参数保真问题已解决，不应继续为其付出复杂 shell 校验和多帖耗时。

### 加速修订

- 将搜索 prompt 重写为单帖稳定性测试：最多检查 1 篇、详情最多滚动 1 次。
- 删除临时 snapshot 文件、awk/grep 自创校验、vision 和第二篇帖子路径。
- 最大运行时间由 7 分钟降为 4 分钟；当前验收目标是一次完成并正常 `kanban_complete`。
- 清理 v0.15 和两个意外残留空板后，以全新 task/session 重跑。

## v0.17 — 纠正目标：防上下文爆炸，并推进独立验证

### 用户纠正与实跑结论

- 不再拍脑袋设置“4 分钟完成”作为优化目标。允许模型较慢；真正不可接受的是重复试探、无限分支、上下文膨胀和整项反复重跑。
- v0.16 实跑只用 152 秒一次完成：18 次工具调用内完成真实搜索、标题点击、xsec_token、一次评论滚动、截图和 `kanban_complete`；没有 `/tmp` 快照、vision、DOM、环境探索或重试。说明搜索阶段现已具备有限动作边界，未观察到上下文爆炸。
- 因搜索阶段已无明确高频 prompt 问题，不继续为了速度缩短业务范围；最大 runtime 恢复为 12 分钟，仅作为故障保险，而不是性能目标。

### Move on

- 按 bottom-up 计划推进独立验证阶段，不再反复微调已稳定的搜索卡。
- 新增 `prompts/verify-worker.md` 与 `schemas/verify-result.md`：从首页重新搜索指定标题，独立核验 context、分享 URL、评论状态、折叠回复和我方历史；动作次数有硬上限，禁止 vision/DOM/临时快照。
- 验证任务仍使用全新 board/task/browser session 和参数文件变量直传；不依赖搜索 task ID、旧评论或 kanban.db。

## v0.18 — 验证阶段补充受限视觉兜底

### 实跑与独立复现

- 独立验证 v0.1 一次完成，244 秒、无重试、无环境探索和无界分支；能重新搜索指定标题、点击获得 xsec_token、两次滚动、截图并 `kanban_complete`，上下文未爆炸。
- Worker 报告评论正文和日期不在 accessibility snapshot。板外调试者对同一证据截图独立视觉检查确认：评论正文、`4天前` 和地区其实已经渲染在像素中，只是正文缺少 a11y 节点；继续单靠 snapshot 会稳定漏掉可见证据。
- 这不是增加无界 vision 的理由，而是验证阶段一个明确、可复现的 a11y 缺口。

### 修订与重跑

- 验证 prompt v0.2 仅在“评论楼层存在但正文或日期缺失于 snapshot”时允许 1 次 vision，并复用同一张最终证据截图。
- Vision 只读取该楼层正文、日期、地区；禁止重试、第二张截图或业务推断。失败即 `VISION_UNAVAILABLE`/`COMMENT_TEXT_UNREADABLE`。
- Schema 新增 `evidence_mode`，明确区分 A11Y 与 VISUAL_EVIDENCE。
- 立即用全新 board/task/session 重跑验证阶段，观察小虾是否严格保持单次受限视觉分支。

## v0.19 — 圆桌阶段实跑与委员长启动修正

### 圆桌实跑

- 两名小虾委员均一次完成，分别约 144 秒与 109 秒；都在同一轮综合评估价值、风险、自然表达、合规和可信度，未创建第二轮或额外卡。
- 两份结果按固定文件写入并调用 `kanban_complete`。委员长在父任务都完成后自动 promoted/spawned，并在约 61 秒完成 APPROVE 定稿。
- 整条圆桌链没有重试、上下文爆炸或浏览器资源消耗，可以继续向发布阶段推进。

### 可改进点

- 委员长先猜测读取不存在的 `value-review.md`、`risk-review.md`，又用 Python 计数字符；虽未形成高频卡壳，但属于可消除的无效探索。
- 委员长使用 shell `hermes kanban complete` 而不是注入工具。根因是 default profile 的 `kanban` toolset 被禁用，与此前小虾配置问题相同。

### 修订

- 委员长 prompt 明确只读精确路径，禁止猜测别名和运行脚本计数字符；完成必须使用注入的 `kanban_complete`。
- 已从 default profile 的 `agent.disabled_toolsets` 移除 `kanban`，确保后续板内委员长获得原生 Kanban 工具。

## v0.20 — 恢复并扩充初始要求中的圆桌角度

### 原始要求回溯

通过历史会话复核，用户最初明确要求的角度包括：事实核查、回复是否冗长、是否暴露产品 URL/名称、是否像钓鱼回复、痛点是否真实且产品可解决、用户是否有付费意愿、表达是否拟人并具社交话术、是否切中用户潜在渴望。后续又明确禁止公开产品名、价格、URL、明显营销倾向，策略是先提供价值并引起自然兴趣。

### 文档扩充

- 新增 `roundtable-angles.md`，把原始角度扩展为 46 项，分为：候选与上下文、帮助价值、社交表达、零营销/反钓鱼、商业价值、最终发布可执行性。
- 补充自动 REJECT 门槛：产品名/URL/价格/主动私信引流、目标或上下文不可验证、整帖已有我方回复、钓鱼/虚假承诺/伪造经历、产品无真实适配。
- 委员 schema 新增八组 `angle_findings`，强制覆盖完整角度库；委员侧重点分别调整为“用户心理与社交表达”和“事实、风险与商业适配”。
- 委员长必须使用同一角度库区分候选 REJECT 与草案 REVISE；所有角度仍在一轮圆桌内完成，不拆专项 R2。

### 重跑决定

当前旧 schema 圆桌虽完成，但未显式覆盖全部初始角度，因此废弃并以新文档、全新 task/session 重跑整个圆桌板。

## v0.21 — 全角度圆桌通过，推进发布机械路径演练

### 全角度圆桌实跑

- 两名委员均一次完成并显式填写八组 `angle_findings`，覆盖 46 项角度；委员 A 约 140 秒、委员 B 约 161 秒，无重试和上下文膨胀。
- 委员长在依赖完成后自动启动，约 48 秒完成；只读精确路径、不再猜测文件、不运行字符统计脚本，并使用注入的 `kanban_complete`。
- 委员长对事实、目标、痛点、产品适配、社交自然度、零营销、反钓鱼、安全、商业信号与发布可执行性给出明确 `angle_gate`。圆桌阶段已无明显高频阻碍。

### Move on：发布阶段安全演练

- 当前只调试“找到指定帖子和指定评论楼层 → 点击该楼层回复 → 验证编辑器绑定目标”的机械路径。
- 为避免调试过程中产生真实副作用，演练卡严禁输入文字和点击发送；`text_typed`、`send_clicked` 必须均为 NO。
- 新增 `prompts/publish-rehearsal-worker.md` 与 `schemas/publish-rehearsal-result.md`；目标标题、关键词、目标评论作者通过参数文件变量直传。
- 只有目标楼层和回复编辑器绑定证据明确、编辑器为空时才返回 `READY_TO_PUBLISH`。

## v0.22 — 发布回复绑定的 a11y 缺口与视觉兜底

### 首轮发布演练证据

- 小虾一次完成真实搜索、标题精确点击、带 `xsec_token` 详情访问、目标作者楼层与相邻“回复”按钮定位，并正确保持 `text_typed: NO`、`send_clicked: NO`。
- 点击目标楼层“回复”后，a11y snapshot 只显示底部持续存在的 editable、disabled 发送与取消，没有暴露回复对象。小虾因此重复点击一次，并以“editable 早已存在、位置未移动”为由报告 `REPLY_CONTEXT_UNCONFIRMED`。
- 板外调试者复用该轮唯一证据截图做视觉核验，清楚看到底部编辑器原生文字“回复 明天就发大财”和“取消”；说明实际绑定已经成功，失败来自发布界面的可复现 a11y 缺口，而非点击无效。
- 旧 `source-archive/xhs-publisher-flow.md` 第 37 行已经要求看到“回复 <目标作者>”，但没有规定 snapshot 看不到时如何安全取证；旧经验也明确要求点击目标楼层回复、1920×1080、输入后禁 Escape、一次发送与独立复核，均继续保留。

### 修订与重跑

- 发布演练 prompt 提升到 v0.2：底部编辑器预先存在或位置不动不再视为失败；snapshot 不显示回复对象时，不重复点击，保存唯一一张截图并只做一次受限 vision。
- Vision 只读取“回复对象、编辑器是否为空、发送是否 disabled、是否有取消”，禁止第二张截图、重试和业务推断。
- 新增 `reply_context_evidence_mode` 与 `WRONG_REPLY_TARGET`，让错误对象和无法读取不再混为一谈。
- 立即硬删除旧发布演练板，以新 task/session/context 重跑，不等待旧结果。

## v0.23 — 回复绑定复跑通过，进入输入/清空安全演练

### v0.2 实跑

- 全新 task/session 从空上下文一次完成，约 160 秒，无 retry、无环境探索、无重复点击回复。
- 小虾在 a11y 缺失时严格只保存一张截图并调用一次受限 vision；视觉确认“回复 明天就发大财”、编辑器为空、发送 disabled、存在取消。
- 结果为 `READY_TO_PUBLISH`，证据模式 `VISUAL_EVIDENCE`，并保持未输入、未发送。说明目标楼层绑定路径已修正并可线性复现。

### 继续拆解发布难点

- 参考旧 `xhs-publisher-flow.md` 的逐字定稿、发送前双重核对、输入后禁 Escape、一次发送、发布员不自证成功与独立复核规则，新增“输入但绝不发送”演练。
- 定稿写入参数文件 `APPROVED_DRAFT_LITERAL`，worker 只能使用一次 `keyboard type "$APPROVED_DRAFT_LITERAL"`，避免小模型重写或重复输入。
- 演练验证：回复对象保持正确、输入逐字一致、发送由 disabled 变 enabled；随后强制 Control+A + Backspace 清空，并确认发送重新 disabled。
- 禁止点击发送、输入后 Escape、第二次输入、点击取消清空或刷新重做。下一轮仍使用新 board/task/session/context。

## v0.24 — 输入/清空演练首跑通过，但清除命令猜测与证据散落

### 原始日志结论

- 全新输入演练一次完成，约 251 秒，无 retry、无发送、无 Escape、无第二次定稿输入；定稿通过参数变量输入，`get text` 与变量逐字比较为 YES，发送由 disabled 变 enabled，随后 Control+A + Backspace 清空并恢复 disabled。
- 回复对象在输入前后各用一次受限 vision 确认，动作有界；未出现上下文膨胀。
- 但 I0 只写了高层“1920×1080”，小虾先发明不存在的 `resize`，再尝试不存在的 `viewport` 和 `set-viewport`，最后错误声称本环境不支持 viewport。此前发布绑定轮已实证正确命令是 `agent-browser set viewport 1920 1080`，因此这是 prompt 未给唯一命令造成的可消除探索。
- 搜索阶段未先 Control+A + Backspace 验空，恰好因新首页输入框为空而成功；这对复现不够稳。
- 两张截图散落在 workspace 根目录而不是 `evidence/`。第二次 vision 又逐字读取整篇定稿，和程序化变量比对重复。

### 修订与重跑

- Prompt v0.4 把 I0-I3 展开成完整状态机，唯一允许 `agent-browser set viewport 1920 1080`；明确禁止 `resize`、`viewport`、`set-viewport`、fallback 链和 help。原样重试一次仍失败即退出，不能带未知 viewport 继续。
- 搜索恢复“点击 → Control+A → Backspace → snapshot 验空 → 最新 ref → 变量输入 → snapshot 验值 → Enter 一次”。
- 截图统一写入 `evidence/`；输入后 vision 只核验回复对象和发送 enabled，文本正确性只由 `get text` 与参数变量比较，避免重复视觉抄写。
- 当前轮虽业务门槛通过，但存在明确可泛化 prompt 缺口，故删除整板并从全新 task/session/context 重跑同一输入演练。

## v0.25 — v0.4 首次干净通过，采用三连跑稳定性门槛

### v0.4 实跑结果

- 全新 task/session/context 一次完成，约 254 秒，无 retry、无障碍、无环境探索。
- 正确执行唯一 viewport 命令；搜索前清空并验空；关键词只输入一次且 Enter 一次。
- 标题精确命中，点击获得含 `xsec_token` 的详情 URL；目标楼层“回复”只点击一次。
- 两次受限 vision 分别只检查输入前绑定状态和输入后回复对象/发送状态；未复述定稿。
- 定稿仅通过参数变量输入一次，程序化逐字比对为 YES；发送 disabled→enabled；清空后恢复 disabled。
- 所有截图都进入 `evidence/`；未点击发送、取消或 Escape。

### 稳定性决定

- 发布属于高风险动作，单次干净通过不足以宣布收敛。
- 采用 **v0.4 连续三次全新上下文干净通过** 的门槛；当前计数 1/3。
- 再运行两次相同生产型输入/清空演练。任一轮出现可泛化问题就清零计数、修文档并重新开始；若连续达到 3/3，则不再重复这一层，推进“一次发送 + 独立复核/错发协调”阶段的安全设计。

## v0.26 — 默认视口可用；真正高频障碍是误点评论图片

### 卡死判断与原始日志

- 第二次稳定性测试不是 API 卡死，而是在目标评论楼层误点 `image` ref，打开图片 lightbox；随后虽然 Escape 恢复，但又离开业务流程去手写 PIL/ImageMagick 标注、安装 Pillow，并连续探索系统工具。该轮已失去调试价值，立即停止 watcher 并废弃。
- 误点根因是小模型把“目标作者附近”误当成“回复按钮”，只凭 ref 位置猜测，没有核对元素角色与可见文字。日志明确显示第一次点击的是 image，真正的 `generic "回复"` 在新 snapshot 中是另一个 ref。

### 板外独立复现

- 使用独立 session `daqian-input-debug`，**完全不调用 viewport 设置**，浏览器截图实测为默认 1280×720。
- 真实首页搜索 → 标题点击 → 带 `xsec_token` 详情 → `generic "回复"` 点击均成功。
- 视觉明确看到“回复 明天就发大财”；编辑器为空、发送 disabled、取消存在。
- 在默认 1280×720 下输入“安全测试”成功，`get text` 读回一致，发送变 enabled；Control+A + Backspace 后编辑器为空且发送恢复 disabled。未点击发送。
- 结论：当前网页版本不需要强制 1920×1080。Viewport 不是本次卡点；真正诀窍是使用语义结构锁定 `generic "回复"`，然后点击持续存在的底部 contenteditable。

### Prompt 修订

- 移除 viewport 调整，禁止 worker 在该步骤花费命令和恢复分支。
- 评论楼层必须识别结构：目标作者 link → 可选 image → 赞 → **明确文字为“回复”的 generic**；禁止点作者、头像/image、赞、三点菜单或通用输入框。
- 点击前强制记录作者 ref、回复 ref、role=generic、text=回复；四项不全则结构化退出，不猜。
- 一旦误开 lightbox/头像/导航，直接 `WRONG_ELEMENT_CLICKED` 结束，不在卡内 Escape 恢复、安装包或研究截图工具；由板外调试者改文档并整板重跑。
- 稳定性计数清零，按 v0.5 从全新上下文重新开始。

## v0.27 — v0.5 默认视口语义定位实跑评估

### 结果

- 新 task/session/context 一次完成，约 291 秒，最终 `INPUT_PATH_READY`；两张证据截图均确认是默认 1280×720。
- 不再修改 viewport；搜索前清空、关键词一次、Enter 一次、标题精确点击、`xsec_token` 验证均通过。
- 本轮正确识别目标评论结构并只点击明确文字为 `generic "回复"` 的 ref，没有再误点 image、打开 lightbox 或使用 Escape。
- 定稿通过参数变量只输入一次，`TEXT_EXACT=YES`；发送由 disabled 变 enabled；清空后恢复 disabled。未点击发送、取消，未刷新重做。
- 两次 vision 均限定在回复对象/按钮状态，证据写入 `evidence/`；生命周期以原生 `kanban_complete` 正常结束。

### 仍可精简但不阻塞

- 小虾在两次截图后各调用了 `execute_code` 制作红框标注。动作有界、未安装包、未失败重试，也没有影响业务路径；但视觉模型直接读取原始截图已足够，后续可明确禁止二次加工截图，减少约两次工具调用。
- 本轮证明 viewport 并非输入框难点；主要可靠性来自“语义文字 `generic 回复` → 点击一次 → 底部 persistent contenteditable → vision 核对绑定”的机械路径。

### 判断

- 表现评为 **合格且显著改善**。核心高风险路径已正确执行，无副作用。
- 尚不能称完全收敛：这是 v0.5 修订后的首个干净样本，稳定性计数为 1/3；若继续调试，应再用全新上下文做两次相同验证，且禁止截图二次加工。

## v0.28 — 决定继续两次严格稳定性测试

- 发布输入属于高风险路径；一次 v0.5 干净通过不足以判断小模型是否已稳定掌握语义 ref，尤其上一轮刚出现过误点 image。
- 因此继续测试两次，目标仍为连续 3 个全新 task/session/context 干净通过；当前为 1/3。
- Prompt 提升到 v0.6，禁止截图后二次加工：保存原始截图后必须直接 vision，禁止 execute_code、Python、PIL、ImageMagick、ffmpeg、安装包、裁切、画框和加横幅。
- 若后续两轮都无误点、无截图加工、无探索、一次输入并安全清空，则该层收敛；任一轮出现可泛化缺陷则修订并清零。

## v0.29 — 用户提高收敛门槛为连续五轮

- 鉴于评论回复路径在历史上让多个小模型频繁卡壳，用户要求只有 **连续 5 轮** 全部通过才可 PASS。
- 从 v0.6 开始重新计连续成功：每轮必须是全新 board/task/session/context，且无误点、无截图加工、无环境探索、无 retry；定稿一次输入、逐字匹配、安全清空，绝不发送。
- 当前运行 `xhs-013017-1` 是 v0.6 的第 1 轮候选；完成并审查原始日志后才计数。任一轮出现可泛化缺陷，立即修文档并将连续成功计数清零。

## v0.30 — 五连跑改为多目标泛化测试

- 用户要求五轮尽量使用不同评论 targets，避免流程只对同一帖子、作者和楼层结构过拟合。
- 新增 `publish-target-pool.json`，记录测试目标与布局覆盖；首个目标是含 image ref 的单评论楼层，第二个历史候选是“Codex连续长时间任务诀窍”下的长文本问题评论。
- Runner 新增 `TARGET_COMMENT_EXCERPT_LITERAL`；pipeline/schema/prompt 同步要求目标楼层必须同时匹配作者和唯一评论前缀。只匹配作者不再允许进入输入，因为同一作者可能有多个楼层。
- 五轮尽量覆盖不同布局：含图片楼层、长文本评论、多评论列表、需要滚动的楼层，以及可得时靠近折叠子回复的楼层。
- 当前 v0.6 第 1 轮仍可计入，因其目标结构包含 image，正好验证了修复后的语义点击。后续四轮将更换目标；每个新目标在启动前重新验证存在性，所有演练仍只输入后清空，绝不发送。

## v0.31 — Vision 改为按需兜底，独立 verifier 承担不确定性

- 用户指出常规每轮两次 vision 过重；正式 Kanban 本就有独立 verifier，可用于处理发布员无法确认的状态。
- 判断正确：vision 不应成为 happy path。Publisher 默认只用 snapshot/ref、`get text` 和发送按钮 a11y 状态；只有滚动与额外 wait+snapshot 后仍缺少关键字段时，才允许最多一次 vision。
- 输入后不再做第二次 vision：定稿用变量只读比对，发送 enabled 用 a11y，回复对象因中间无楼层切换而沿用输入前证据。
- 若一次 vision 仍不能确认，publisher 返回 `NEEDS_VERIFIER` 且不输入；独立 verifier 用新 session 重查。真实发布后 verifier 仍必须独立确认结果，publisher 不自证成功。
- 当前多目标第 2 轮在评论未滚入截图时已过早消耗 vision，暴露旧 prompt 的问题；该轮废弃，不计五连跑。更新文档后从多目标测试重新开始。

## v0.32 — 明确禁止 hover，并区分回复文字按钮与线程计数

- 新一轮日志出现“Hovering over the author link didn't reveal a reply button”。这是 Prompt 不完整造成的误解：此前只描述 `generic "回复"` 的单评论形态，没有明确说回复控件不靠 hover 出现，也没有定义已有子回复时的纯数字计数形态。
- 小虾把两个 `generic "7"` 误解为 like/reply counts，又猜测回复按钮需要 hover 作者或 action row。这不是网站要求，而是弱模型面对未定义状态自行发明恢复策略。
- Prompt v0.7 明确禁止所有 hover。回复控件分为：明确 `generic "回复"` 可直接点击；纯数字 `generic "N"` 只作为折叠线程展开入口，点击后必须验证 `收起回复` 或子回复出现，再重新寻找一级评论的明确回复按钮。
- 展开后仍无 `generic "回复"` 就结构化退出，禁止 hover、猜 ref 或把数字直接当回复按钮。
- 当前轮已经违反新状态机，立即停止并废弃；不计五连跑，连续成功仍为 1/5。下一轮从全新上下文重跑同一复杂目标。

## v0.33 — 复杂详情浮层必须 scrollintoview 后再考虑 vision

- v0.7 轮安全完成为 `NEEDS_VERIFIER`，未输入、未发送，但不能计入 PASS。它在评论仍不在视觉 viewport 时就消耗唯一 vision；随后两次窗口级 scroll 没有移动右侧详情浮层。
- 板外读取最终截图确认：右侧仍停在帖子正文，底部只有固定互动栏；评论列表属于浮层内部 overflow，普通 window scroll 可能只作用于背景页面。
- `agent-browser` 原生提供 `scrollintoview <ref>`。Prompt v0.8 改为：a11y 已找到目标作者但视觉不可见时，先 `scrollintoview @作者ref`，再 wait + fresh snapshot；失败时只允许用新 ref 原样重试一次。
- 只有作者已进入视觉 viewport 后，才允许一次按需 vision。纯数字 `generic "N"` 也不能再凭数字猜成线程入口，必须由 full snapshot 或这一次 vision 明确绑定到“展开 N 条回复”。
- 本轮暴露新通用缺口，因此不计五连跑；连续成功仍为 1/5，更新后以同一复杂目标全新重跑。

## v0.34 — 气泡数字不是“展开 N 条回复”入口

- v0.8 轮使用 `scrollintoview` 成功把复杂评论楼层带入截图，按需 vision 正确识别评论正文和控件；这是进步。但它随后把一级评论气泡数字 `7` 当成线程展开入口，点击后无变化，最终安全退出 `COMMENT_CONTEXT_UNCONFIRMED`，未输入、未发送。
- 板外复核同一截图确认结构：一级评论 action row 是点赞 7 + 回复气泡总数 7；已露出一条作者子回复；真正展开控件是子回复下方独立文字 **“展开 6 条回复”**。应点击文字入口，而不是气泡数字。
- Prompt v0.9 规定纯数字永远不能单独作为展开入口或回复按钮。只允许点击有明确 ref 的 `展开 N 条回复` 文字；若视觉看得到文字但 a11y 无 ref，则 `NEEDS_VERIFIER`，不得坐标或数字替代点击。
- 展开线程和回复一级评论是两个不同动作：展开不会保证一级楼层出现新按钮。一级楼层没有明确 `generic "回复"` 时，publisher 必须交 verifier，不猜。
- 本轮安全但未完成，不能计 PASS；连续成功仍为 1/5。

## v0.35 — 纠正：一级评论的回复气泡数字本身可绑定回复

- v0.9 轮按文档安全返回 `NEEDS_VERIFIER`，但板外调试者复用其遗留 session 做了最小独立复现，发现此前规则仍混淆了“直接回复”和“展开线程”。
- 当前 snapshot 中，目标一级楼层结构为作者 `煎饼果子松鼠` → 两个数字动作 `7 / 7`；第二个数字是评论气泡。点击该第二个数字一次后，页面未导航、未打开图片，底部视觉明确显示 `回复 煎饼果子松鼠`，编辑器为空且发送 disabled。
- 同一页面另有独立 `展开 6 条回复`；它只负责展开已有子回复，和直接回复气泡是两个不同控件。因此“纯数字永远不能点击”过度保守，会让含已有回复数的一级评论永久无法发布。
- 此轮 vision 首次只描述笔记头部并非目标评论不在截图；板外再次分析同一原图可逐字读到目标评论。根因是提示使用了含糊的 `first top-level comment`，而整页同时包含搜索背景、AI 面板和大图，注意范围不稳定。
- Prompt 升至 v1.0：允许在严格锁定目标一级楼层 action row 后，把第二个数字动作当 `NUMBERED_REPLY_BUBBLE`；点击后必须用全任务唯一一次 vision 同时核验评论前缀和底部 `回复 <目标作者>`。`展开 N 条回复` 仍只能用明确文字 ref，不得与气泡混用。
- Vision 提示改为按目标作者和评论前缀定向，只看右侧评论栏与底部编辑器，禁止再用相对位置描述。
- 本轮发现通用错误规则，连续成功计数清零为 **0/5**；删除旧板并以全新 board/task/session/context 重跑复杂目标。

## v0.36 — 目标轮换 runner 与 target-a 通过

- 复核发现多轮测试此前静默复用 `pipeline.json` 中的 target-b，不满足多目标泛化要求；同一目标重复 PASS 不能当作五个不同目标。
- Runner 已接入 `publish-target-pool.json` 与 `target-rotation-state.json`，每轮记录 `target_id`、标题和布局目标；新增 `--target-id` 显式覆盖，避免操作员误跑目标。
- target-a 首轮因目标正文实际以 `^_^` 开头、旧参数误写为 `302`，安全返回 `NEEDS_VERIFIER`；将经过像素证据确认的逐字前缀修正为 `^_^` 后，以全新 board/task/session 重跑。
- target-a 重跑结果 `INPUT_PATH_READY`：文字 `回复` 入口、含 image ref 的楼层、作者+前缀双匹配、一次 vision、一次变量输入、逐字匹配、清空恢复 disabled，且未发送。
- 用户确认 target-b（run 2）PASS；当前可计的不同目标为 target-a 与 target-b。下一步运行 target-c、target-d、target-e，并根据实跑证据修正尚未验证的目标参数。

## v0.37 — 未验证目标的搜索词必须可复现

- target-c 首跑安全结束为 `TARGET_NOT_FOUND`：worker 真实输入宽泛关键词“美食”，进入 AI 搜索页后按上限滚动一次，未发现指定标题；无误点、无输入、无发送。
- 这不是发布状态机缺陷，而是测试夹具不可复现。c/d/e 原先分别使用“美食/穿搭/旅行”等宽泛词，却要求命中固定帖子，容易受搜索排序变化影响。
- 将 c/d/e 的 `keyword` 改为各自目标帖完整标题。仍通过首页真实键盘搜索，不拼 URL；只消除测试参数的随机性。
- target-c 不计 PASS，target-a 与用户确认的 target-b 保持两个不同目标通过。修正后以全新 board/task/session 重跑 target-c。

## v0.38 — 同作者多楼层需要两阶段视觉闭环

- target-c 修正搜索词后能稳定进入目标帖，但作者“酸奶”有两个一级楼层；a11y 仅暴露作者与 action row，不暴露正文。
- Worker 的唯一 Vision 在评论未进入其视觉判断时耗尽，最终安全返回 `NEEDS_VERIFIER`。板外使用独立 session 对两个作者 ref 分别 `scrollintoview` 后截图，均可完整看到评论区；目标前缀属于第一条“酸奶”楼层，其入口是 `点赞 13 + 回复气泡 2`，第二条为另一正文并使用文字“回复”。
- 根本矛盾是：多同名楼层必须先用视觉选中正确楼层，点击后又必须视觉确认回复绑定；单次 Vision 无法同时安全完成两个先后状态。
- Prompt 对该明确场景开放严格上限 2 次 Vision：第一次只做点击前楼层/动作行选择，第二次只核验点击后的 `回复 <作者>` 和空编辑器；禁止第三次。普通或唯一作者仍维持最多一次。
- target-c 本轮不计 PASS；更新后全新重跑。

## v0.39 — target-c 同作者双楼层通过

- v1.1 全新重跑返回 `INPUT_PATH_READY`。点击前 Vision 正确识别第一条“酸奶”为目标楼层及 `点赞13 + 回复气泡2`；点击后第二次 Vision 确认 `回复 酸奶`。
- post-click Vision 对编辑器空状态略有歧义，但 worker 用只读 `get text` 得到长度 0，并结合发送 disabled 做确定性确认，没有增加第三次 Vision。
- 定稿变量只输入一次，逐字比对 YES；发送 disabled→enabled；清空后恢复 disabled；未发送、未 Escape、未误点。
- 当前已有三个不同目标通过：target-a、target-b、target-c。继续 target-d。

## v0.40 — Vision 格式失败允许同图同问原样重试

- target-d 已正确搜索、进入目标帖、锁定唯一作者楼层并点击数字回复气泡，但唯一 Vision 返回与问题无关的截断全页描述，安全结束 `NEEDS_VERIFIER`。
- 板外对同一原图使用同一目标字段重新分析，能够明确确认评论前缀、`回复 L......` 和空编辑器，证明截图与浏览器路径均正确，失败来自 Vision 偶发未遵循输出范围。
- 新规则区分“业务不确定”与“格式失败”：前者禁止重试；后者仅允许对同一截图、同一问题逐字不变重试一次，记录 `vision_format_retries`。仍失败则交 verifier。
- target-d 不计 PASS，更新后全新重跑。

## v0.41 — target-d 通过

- 全新重跑返回 `INPUT_PATH_READY`：唯一作者楼层、数字回复气泡、作者+正文前缀双匹配、一次 Vision、变量定稿输入一次、逐字比对与清空状态全部通过。
- 本轮 Vision 正常遵循问题，无格式重试；`vision_format_retries: 0`。
- 搜索 Enter 将结果打开到新标签，worker 检查 tab 后在 active 结果页继续，没有重输或拼 URL。该分支有界且成功，不构成阻碍。
- 已有四个不同目标通过：target-a、target-b、target-c、target-d。继续 target-e。

## v0.42 — 视频布局 Vision 提示强化

- target-e 已正确搜索、进入含 xsec_token 的目标视频帖、锁定唯一作者楼层并点击文字“回复”；URL 未变且编辑器保持空、发送 disabled。
- 唯一 Vision 与同图同问格式重试均被视频/全页内容抢占注意力，未回答指定字段，worker 按规则安全返回 `NEEDS_VERIFIER`，未输入、未发送。
- 板外对同一原图改用“忽略左侧视频，只检查右侧下半部，四项编号，NOT_IN_VIEW”提示后，作者、正文前缀、回复对象和空编辑器四项均为 YES，证明目标与浏览器路径正确。
- 普通 Vision 固定提示更新为该四项区域约束格式；target-e 不计 PASS，立即全新重跑。

## v0.43 — Qwen 五个不同目标通过，开始 Mimo 跨模型复跑

- target-e 使用强化后的固定视觉提示全新重跑，返回 `INPUT_PATH_READY`；一次 Vision 即按四项格式确认作者、正文前缀、`回复 一时` 和空编辑器。
- 定稿仍只通过参数变量输入一次，逐字比对为 YES；发送 disabled→enabled；随后清空并恢复 disabled；未发送、未 Escape、未误点、无格式重试。
- 至此 Qwen worker 已在 target-a、b、c、d、e 五个不同帖子/作者/布局上全部通过输入与清空演练，说明该层对 Qwen 已达到多目标门槛。
- 单一模型通过仍不足以证明流程可由不同较小模型复现。实时助手清单确认 `agent-36c92559bdf96bcf` 使用 `mimo-v2.5` 且可分配；下一轮把相同本地文档、空 skills、全新 board/task/session 交给 Mimo，从 target-a 开始跨模型复跑。
- 仍维持无副作用门槛：只输入后清空，绝不点击发送。跨模型日志若出现通用问题，立即改落盘文档并重跑；若只是模型特有但有界的首次 orient，不为此无限重跑。

## v0.44 — 用户暂停 Mimo，仅保留 Qwen

- Mimo 首轮尚未执行任何网页动作即因 provider 缺少 `x-opencode-session` 请求头失败；该问题属于模型接入环境，不是小红书流程缺陷，因此不修改浏览器 prompt。
- 用户明确要求 Mimo 暂时不要使用，只用 Qwen。立即废弃 Mimo board/task/session，不再修理或重试其 provider。
- `pipeline.json` 恢复唯一 assignee `agent-26c319b9362c7cec`（Qwen）；后续所有调试轮继续保持空 skills、全新上下文和本地文档驱动。

## v0.45–v0.46 — 未单独落盘

- 这两个版本的调试细节没有单独记录，其成果已并入 v0.47 的真实发送与独立复核收敛。

## v0.47 — 真实发送、独立复核与失败协调收敛

- 真实发送在 target-c、target-d、target-e 三个不同目标上连续通过：`SEND_SUCCESS`、`READ_TEXT`、`vision_calls=0`，发送后编辑器重置。
- 新增 `publish-verify-worker.md` 与结果 schema；修复单评论楼层的可见线程识别、状态机从头重跑、未穷尽线程误报不存在等问题。
- 最终独立复核在 target-c、target-d、target-a 三个不同目标上连续通过：目标线程已穷尽、定稿逐字恰好一次、其他楼层无重复、零 Vision、零页面修改。
- 新增纯结构化失败协调：错发与重复只标记人工处理并禁止重试；明确未发送且复核确认不存在时仅允许全新 session 重试一次；发送结果不明确或线程未穷尽时禁止自动重试并转人工复核。
- 扩展 runner 的 `param_vars`，使非浏览器阶段可从参数文件读取不可变状态；非发布阶段不再强制轮换目标池。
- 每轮均实际使用 `process wait` 观察 watcher，并在完成后删除临时看板、停止 watcher、关闭任务标签。

## v0.48 — 文档与计划清理

- 删除过时的精简计划稿 `.hermes/plans/2026-09-09_*.md`。该稿的三条主张与既定原则冲突，全部不予采纳：把 6 个 Agent 节点精简为 3 个（本流程必须保留多阶段审核冗余）、引入 unittest（本项目不留测试文件）、用 subagent 驱动实施（本项目由主代理直接完成）。
- 删除已被取代的单阶段调试件：`prompts/search-worker.md` 与 `schemas/search-result.md`（已被 scout 阶段取代）、`prompts/verify-worker.md` 与 `schemas/verify-result.md`（已被 `publish-verify` 阶段取代）。
- 删除无任何引用的历史脚本 `e2e_loop.py`、`watch_run.py`，以及孤立的九行样例 `review-case.md`。
- 清理已删除测试遗留的字节码 `__pycache__/test_*.pyc`。
- 经全仓引用核查后保留：`highclaws-features.md` 仍是 chair/review prompt 与角度库共同依赖的产品事实唯一来源；`SCOUT-REFINEMENT.md` 与 `scout-pipeline.json` 仍是 `run.py --scout-only` 的现行调试路径；`source-archive/` 维持“可疑参考、不作执行依据”的口径。
- 修正本文件版本顺序：v0.47 此前被插在 v0.1 之前，现统一为时间正序、最新在末尾，并在文件头注明。

## v0.49 — 登录态失效时阻塞看板并长时间休眠等待

- scout 返回 `LOGIN_REQUIRED` 后，不再让整轮草草结束、下一轮立刻重来：runner 先把本轮剩余卡片（review-a、review-b、chair、publish-send、publish-verify）置为 blocked，并把原因写在卡上（先 `promote` 再 `block`，因为 `hermes kanban block` 只接受 running/ready 的卡），然后长时间休眠等待人工扫码登录。
- blocked 是 sticky 状态：派发器不会重新拉起这些卡，看板上直接可见「等待人工登录」，不会再有 5 秒一轮的空转。
- 休眠期间每 60 秒检查一次，任一卡片被人工 unblock 就立即提前唤醒；随后本轮按既有语义门以 SKIPPED 收尾，下一轮自动重新侦察并继续正常流程。默认最长休眠 6 小时，可用 `XHS_LOGIN_PARK_SECONDS`、`XHS_LOGIN_PARK_POLL_SECONDS` 调整。
- 休眠时长可能超过每轮 45 分钟上限，故 `wait_for_board` 在 park 返回后重置本轮超时预算，避免把「等待人工登录」误报成 TimeoutError。
- 只改 `run.py` 一处：不动判断节点、审核冗余、prompt、schema 与发布路径，不新增测试文件。
- 实测（临时看板，验后已删除）：5 张下游卡 8 秒内全部 blocked 并带原因注释；park 严格按预算休眠（20 秒、90 秒两次实测）；人工 unblock 后提前唤醒（120 秒预算下 10.6 秒返回）；park 超过本轮超时后 `wait_for_board` 仍正常返回 terminal。

## v0.50 — 登录态失效时阻塞看板后直接停止循环

- 用户要求取消 v0.49 的「休眠 + 每 60 秒偷看」机制：登录恢复必须由本人扫码，轮询没有任何收益，只会白占资源。因此把 park 改为**阻塞后直接退出**。
- scout 返回 `LOGIN_REQUIRED` 时，本轮剩余 5 张卡（review-a、review-b、chair、publish-send、publish-verify）仍按 v0.49 的方式 `promote` 后 `block`，原因写在卡上；随后抛 `LoginRequired` 中止本轮，不再调用 `skip()`。**卡片保持 blocked 状态不动，不完成、不归档、不删除**，看板上一直显示「等待人工登录」。
- `run.py` 以退出码 3 表示「等待人工登录」；`run_loop.sh` 收到 3 就打印提示并退出整个循环，等待人工重启服务（Supervisor 为 `autorestart=false`，服务停在 EXITED，不会自我复活）。退出码 0/1 的语义不变，普通失败仍按原有间隔继续下一轮。
- 删除 `park_while_login_missing()` 与 `XHS_LOGIN_PARK_SECONDS`、`XHS_LOGIN_PARK_POLL_SECONDS` 及其超时预算重置分支；`apply_semantic_gates()` 不再返回 `"parked"`，改为抛 `LoginRequired`。判断节点、审核冗余、prompt、schema、发布路径与发布门槛一律未动。
- 本次改动为两处文件：`run.py`（阻塞后中止）与 `run_loop.sh`（识别退出码 3 后停止循环）——两者缺一不可，单独改 `run.py` 会让外层 `while true` 在 5 秒后重开一轮并重新派活。未新增任何测试文件。
- 零成本实测（`/tmp` 桩程序替换 `run.py`，不派 worker、不花钱）：退出码 3 时打印提示并以 0 退出；退出码 1 时按 `XHS_LOOP_SLEEP_SECONDS` 继续循环。
- 真实链路的「scout 判定 LOGIN_REQUIRED → 卡片 blocked → 循环退出」待下次真实运行确认；当前运行中的进程仍是 v0.49 的休眠版本，可继续停留在休眠状态。

## v0.51 — scout 固定使用 xiaohongshu.com 域名

- 现象：共享浏览器里小红书明明已登录，scout 仍稳定返回 `LOGIN_REQUIRED`，连续三轮被登录门禁拦下。
- 根因：scout prompt 的 S1/S3 让 worker 打开 `https://www.rednote.com/`，而登录 Cookie 属于 `https://www.xiaohongshu.com/`。同一浏览器下两个域名登录态不共享，`rednote.com` 真实显示未登录，左侧栏没有“我”，于是状态机按规则判定 `LOGIN_REQUIRED`——判断本身没错，错的是 prompt 给的域名。
- 修订：S1 改为 `https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend`，S3 的重新打开首页同样改用该域名，并明确禁止切回 `rednote.com`。
- 验证：改用新地址后 S1 直接通过（左侧栏识别到“我”），随后 S2 刷新推荐流、S3 读卡正常推进。

## v0.52 — 定稿单行硬规则、有界重输与遮挡弹窗处理

- 现象一（真实副作用）：两轮把定稿只发出了前半句。委员长定稿含 `\n`，`agent-browser type` 把换行当回车，而小红书网页评论框**按回车即提交**，第二句根本没进编辑器；这类失败被记为 `NEEDS_VERIFIER`，导致发布复核被跳过，残缺回复留在线上。
- 现象二：一轮输入后编辑器出现重复前缀（64 字 vs 定稿 60 字），发布 worker 遵守“禁止重复输入”直接放弃整轮，什么都没发，白跑一轮。
- 现象三：一轮因页面弹出广告屏蔽插件提示，回复框绑定失败，尝试 2 次后未发送。
- 修订（prompt 层）：
  - `chair-worker.md` 增加“单行硬规则（发布安全，最高优先级）”：`final_comment` 禁止任何换行符、空行、缩进与按行排版，`line_count` 必须为 1，并解释回车即提交的原因；批准前自检项同步加入单行校验。
  - `review-worker.md` 的 `draft` 同样要求单行，避免委员稿的换行污染下游定稿。
  - `xhs-reply-style.md` 增加执行层单行约束，并把“是否为无换行单行文本”加入发布前自检清单。
  - `publish-send-worker.md`：新增强制归一化步骤（输入前把 `\r\n`、`\r`、`\n` 替换为空格并合并连续空格，得到 `SEND_TEXT` 作为唯一比对基准）；新增“开页先清遮挡弹窗”步骤（广告屏蔽/插件/引导/浮层，最多尝试关闭 2 次，只点关闭类按钮）；第 12 步改为**有界重输**：输入后逐字校验，不一致时清空编辑器重输一次，累计最多 2 次，仍不一致写 `TEXT_MISMATCH` 且不得发送；明确禁止用补丁式字符插入硬凑一致。输入前还要求先确认编辑器为空。
  - `schemas/chair-result.md`、`schemas/publish-send-result.md` 同步单行约束，并新增 `newline_normalized`、`text_input_attempts`（只允许 1 或 2）、`popup_dismissed` 三个字段与规则说明。
- 修订（确定性兜底）：`run.py` 新增 `normalize_approved_draft()`，在委员长 APPROVE 之后、激活发布卡之前，直接读取并改写 `runtime/chair-decision.json`：把 `final_comment` 中的换行折叠为空格、合并连续空格、把 `line_count` 置 1、写入 `newline_normalized: true`，命中时向 stderr 打印 `[draft-guard]` 行。该守卫幂等，重复调用返回 `UNCHANGED`；文件缺失或不可解析时安全跳过，不阻断流程。这样即使模型无视 prompt 输出了换行定稿，也不会有换行进入发布路径。
- 落地验证：以临时目录构造含换行定稿实测——首次调用返回 `NORMALIZED`（折叠 1 个换行、`line_count` 变 1、`newline_normalized=true`），再次调用返回 `UNCHANGED`，单行定稿返回 `UNCHANGED`，文件缺失返回 `SKIPPED_UNREADABLE`。
- 未改动：判断节点结构、审核冗余、轮次编排、发布与复核的语义门、其他 prompt 的既有约束。未新增测试文件。
