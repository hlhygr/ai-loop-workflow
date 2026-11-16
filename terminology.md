# AI Loop 术语

本页只解释名词，不规定流程、权限、触发条件或报告格式。执行规则入口见 [README](README.md)。

| 术语 | 含义 |
|---|---|
| AI Loop / Delivery Loop | 围绕当前目标组织实施、验证、必要审查和交付的工作方式 |
| Review–Fix Loop | 审查发现问题后，核实、修复、验证与复核的过程 |
| Reviewer | 提供独立证据审查的临时 Agent |
| Full Review | 对明确范围及直接影响的完整审查 |
| Recheck | 对原 finding 修复与直接副作用的定向复核 |
| Final Review | 因具体证据缺口、重要变化或用户要求追加的独立审查 |
| Finding | 有证据支持、违反当前目标或约束的问题 |
| Scope / Baseline | 审查覆盖范围 / 判断变化所依据的对照对象 |
| P0～P3 | 问题影响严重度；定义见审查 skill，阻塞性见 Loop 策略 |
| clean | 当前审查范围未发现确定问题 |
| accepted_non_blocking | 仍有经证据判断可接受且公开风险的非阻塞遗留 |
| open / fixed_pending_recheck / closed | 问题未关闭 / 修复待复核 / 已复核关闭 |
| 已复现 / 静态确定 | 可重复观察到结果 / 调用链与条件足以证明 |
| 历史交叉验证 | 历史事实提供支持，仍须核对当前适用性 |
| 合理推断 / 待验证 | 有证据支持但缺验证 / 缺必要条件或证据 |
| Planning | 跨阶段或跨会话保留任务状态、证据和执行结果 |
| task_plan.md | 当前目标、阶段、当前状态及唯一下一步 |
| findings.md / progress.md | 证据与决策 / 执行、验证和重要外部状态记录 |
| pending / in_progress / complete | 阶段尚未开始 / 进行中 / 成功标准已满足 |
| delivery.md / 交付游标 | 旧版历史交付材料 / 旧版固定动作标记 |
| 测试执行报告 | 用例预期、实测、证据、结果与数据状态的交付记录 |
| PASS / FAIL / BLOCKED / NOT_RUN | 实测通过 / 实测失败 / 条件阻塞 / 未执行 |
| Learning Candidate | 按需整理的经验变更候选，不等于获准实施 |
| Agent / Skill | 执行任务的实例 / 按需加载的专项能力说明 |
| Worktree | Git 工作目录及其当前改动状态 |
