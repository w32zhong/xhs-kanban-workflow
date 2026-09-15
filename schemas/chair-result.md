# 委员长裁定格式

```text
CHAIR_RESULT
decision: APPROVE | REVISE | REJECT
consensus: <2-4句，综合两名委员全部维度>
angle_gate: <说明事实/目标/痛点/社交/零营销/安全/商业适配/发布可执行性是否通过>
final_comment: <APPROVE时为自然简洁的逐字定稿；否则NONE。必须是单行，禁止任何换行符>
reasons:
  - <最多3项>
publish_constraints:
  - 必须逐字发送 final_comment
  - 不得追加产品名、URL、价格或引流语
  - final_comment 必须是单行文本：禁止 \n、\r、空行、缩进或按行排版的列表
```

`final_comment` 的单行约束是发布安全硬规则：小红书网页评论框按回车即提交，含换行的定稿会被提前截断发送，只发出前半句。需要多个信息点时用句号、逗号或空格在同一行内连接。

委员长必须独立读取固定样例和两份委员输出；不能把当前聊天中的调试者当作板内节点。完成后写入指定 `OUTPUT_FILE` 并调用 `kanban_complete`。
