# AI Loop Workflow

AI Loop 根据用户目标自动分诊、发现当前环境的能力并按需加载，组织执行、验证、必要审查与交付。使用者直接描述目标，无需选择任务类型或执行链。工作流不绑定具体模型，不管理用户的领域技能。

## 开始使用

从 [GitHub 仓库](https://github.com/hlhygr/ai-loop-workflow) 下载源码，或克隆到本地：

```bash
git clone https://github.com/hlhygr/ai-loop-workflow.git
cd ai-loop-workflow
```

把 [统一入口](skills/dispatch-ai-loop-workflow/SKILL.md) 提供给 Agent，或让宿主将它作为项目/会话指令。之后直接描述目标，例如“分析这个报错”“完成这个需求”“审查这些改动”或“继续这个计划”。入口自行选择必要能力，随着证据变化调整流程。

支持技能发现的宿主可接入本仓库的三个技能目录；已有的用户领域技能继续由宿主管理。核心只根据实际目录和能力选择调用，不要求固定技能名称或个人目录。纯对话环境需由用户提供入口及按需引用的内容；无法读取、执行或持久化的部分会明确报告。

## 结构与规范

| 位置 | 职责 |
|---|---|
| [dispatch-ai-loop-workflow](skills/dispatch-ai-loop-workflow/SKILL.md) | 核心入口：自动分诊、按需加载、权限与证据边界 |
| [evidence-based-review](skills/evidence-based-review/SKILL.md) | 独立证据审查和定向复核 |
| [planning](skills/planning/SKILL.md) | 任务状态、证据、显式选择和恢复 |
| [Loop 策略](skills/dispatch-ai-loop-workflow/references/loop-strategy.md) | 审查与修复的通过条件和收敛 |
| [adapters](adapters/README.md) | 连接宿主工具、独立上下文与生命周期事件 |
| [术语](terminology.md) | 概念解释，不复制执行规范 |

三个核心技能随同一份源码维护。用户的页面开发、文档、服务集成等技能由当前环境发现和调用，不复制进工作流，不作为工作流扩展注册。

## 工具与兼容性

核心规则以文本提供；文件和命令能力不是使用分诊原则的前提。可选 planning 工具仅依赖 Python 3.10+ 标准库，支持任意显式工作区和计划根目录，不依赖其他安装的技能。能力不足时保留验证缺口，不把自查称为独立审查或把对话摘要称为持久化。

```bash
python3 skills/planning/scripts/planning.py --workspace /path/to/project init task-name
python3 skills/planning/scripts/planning.py --workspace /path/to/project --plan-id <id> brief
python3 -m unittest discover -s tests -v
```

Codex 有 [参考适配](adapters/codex/README.md)；其他宿主按同一接入契约实现，不修改分诊规则。文件、脚本和隔离测试通过不等于所有宿主已实测。当前验证边界见 [进度](progress.md)。

## 许可证与维护来源

采用 [MIT License](LICENSE)，允许自由使用、修改和集成，分发时保留版权及许可声明。本地使用与 GitHub 分发共用这一份源码；不附带个人计划、业务历史或用户领域技能。
