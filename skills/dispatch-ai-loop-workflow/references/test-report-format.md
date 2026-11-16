# 测试 HTML 报告规范

仅在交付链确认需要 HTML 时读取。用例事实和授权要求见 [测试执行链](delivery-chains.md#测试执行链)。报告校验不证明测试事实真实，PASS/FAIL 仍需实际执行证据。

## 生成与恢复

- 报告为 UTF-8、自包含且可直接打开的 HTML，无本地服务依赖、自动加载外部资源、表单提交或网络请求入口。
- 有 planning 时，为每轮选择未使用的稳定路径，如 `reports/round-2/test-execution-report.html`，在 progress 记录路径、统计和执行结果；下一步只写入 task_plan。中断恢复时核对报告与执行证据，不重复已完成用例。
- 无 planning 的小报告保存到用户指定或任务专用位置，直接用 `--report` 校验，不额外建立空计划。新轮次不覆盖历史报告，同轮修正继续使用原路径。
- 逐例事实可由 HTML 作为唯一来源，findings 只保留报告路径和主要发现，progress 只保存执行记录和统计。

## 内容契约

- 使用真实 HTML 节点写入 `ai-loop-test-report=v1` 格式标记。
- 以 `data-report-section` 唯一标记六个非空章节：`scope`、`environment`、`cases`、`findings`、`data-state`、`authorization`。
- 每条结果行使用唯一 `data-case-id` 和 `data-status=PASS|FAIL|BLOCKED|NOT_RUN`；用非空 `data-fields` 标记 `expected`、`actual`、`evidence`、`state`、`cleanup`。
- 可见统计使用 `strong` 节点，用唯一且未隐藏的 `data-result-count` 标记 `PLANNED` 与四类结果；逐例数、分类数和可见统计一致，有plan时也须与progress统计一致。

## 校验与交付

有计划时保留计划内路径约束和旧命令兼容：

```bash
python3 skills/dispatch-ai-loop-workflow/scripts/validate-test-report.py --plan-dir <绝对计划目录> --report <本轮报告路径> --planned-cases <总数> --pass-count <数量> --fail-count <数量> --blocked-count <数量> --not-run-count <数量>
```

无计划时显式指定报告，保持同样的章节、证据字段、自包含性和计数校验：

```bash
python3 skills/dispatch-ai-loop-workflow/scripts/validate-test-report.py --report <报告路径> --planned-cases <总数> --pass-count <数量> --fail-count <数量> --blocked-count <数量> --not-run-count <数量>
```

任一校验失败先修正报告。校验只针对本轮文件，不要求整个功能计划完成或关闭；有plan时通过后记录绝对路径和本轮完成状态。

可见性校验基于静态 HTML 解析，不等同于浏览器 computed style。隐藏子元素中的文本不计入可见内容；必要节点及祖先支持标签、类、ID和后代选择器的常见层叠规则。含隐藏声明的条件样式或复杂选择器，需改用静态样式并人工核对。

最终回复同时给本轮报告的可点击本地链接与完整绝对路径，不能只说已生成或只给目录。旧轮次报告与交付链接保持可读。
