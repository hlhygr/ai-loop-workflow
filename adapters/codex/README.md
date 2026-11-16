# Codex 接入

这里包含宿主参数和事件映射；核心规则位于仓库 skills。工作流使用宿主当前配置，不硬编码模型。

## 技能与发现

将仓库 `skills/` 中三个技能目录接入当前宿主的技能发现位置；本地使用可通过目录链接指向同一来源。无需安装或移动用户领域技能。更新/替换已有安装前核对其内容并备份，不覆盖未确认的本地改动。

在项目或会话指令中引用 `skills/dispatch-ai-loop-workflow/SKILL.md` 作为统一入口。已加载的入口不每轮重复读取；简单任务由入口直接处理，其他模块按需加载。具体发现机制需在当前宿主验证。

## Reviewer

创建独立 Reviewer 时使用 `fork_turns="none"`，省略 `model` 和 `reasoning_effort` 以采用当前宿主配置；用户明确指定时仅按其要求设置对应字段。提供原始目标、对象、基线、约束和验证证据，并加 `[EVIDENCE_REVIEW_SUBAGENT=1]`。接到标记的 Reviewer 直接执行审查，不继续派生。

定向复核使用宿主 follow-up 能力，加 `[EVIDENCE_RECHECK=1]` 并提供原 findings 与修复范围；主 Agent 核实后继续已授权任务。超时、替换和容量遵循核心 Loop 策略及实际宿主能力。

## 可选 hook

现有事件 `SessionStart`、`UserPromptSubmit`、`PreCompact`、`Stop` 分别映射为 `start`、`prompt`、`compact`、`stop`。示例命令（替换为实际安装与工作区路径）：

```bash
python3 /path/to/AI-Loop-Workflow/adapters/codex/adapter.py --workspace /path/to/workspace
```

通过 stdin 接收原事件 JSON。适配器只处理所选工作区及子目录；会话绑定优先 `AI_LOOP_SESSION_ID`，其次 `CODEX_THREAD_ID`，最后 payload 的 `session_id`。输出保留已有 `hookSpecificOutput`/`systemMessage` 格式。信任、事件注册和重新加载由宿主控制；脚本测试不代表真实事件已触发。

## 旧安装兼容

旧 `scripts/planning.py` 入口委托给同仓库核心及本适配器，默认以工作流目录的父目录作为工作区，并映射宿主会话标识；适用于工作流直接放在工作区下的既有布局。旧 `hook` 命令继续支持。新绑定使用完整 ID 哈希；适配器只为原样符合 `[A-Za-z0-9._-]{1,120}` 的旧会话 ID 读取 `.active/thread-*`，不为需要替换或截断的标识猜测旧键。已有安全绑定无需批量迁移；不能无损匹配的旧标识需显式选计划，既有 hook 注册不变。其他布局的普通命令使用显式 `--workspace`；hook 使用上文的 adapter.py 命令，不使用旧 wrapper 的裸 hook 默认。

这是本地兼容入口，不是第二套实现。通用接入直接使用 `skills/planning/scripts/planning.py`；自定义计划根继续使用 `PLANNING_ROOT` 或 `--planning-root`。

经验候选脚本现在要求显式 `--plan-dir`；旧的仅 `--name` 调用会提示缺少参数，不再根据宿主或当前目录推断计划。
