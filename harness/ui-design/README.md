# UI 设计人工交付包

本目录提供可复制的人工合同，用于接收团队设计或 AI 制作结果。尚未提供 Schema、自动检查器或自动 UI Gate；已有工程检查通过不能替代这里的人工核对。

将本目录作为说明材料复制到业务项目 `harness/ui-design/`。实际包保存在选定 UI 权威仓库的 `design/units/<unit>/releases/<release>/`；决定保存在该单元的 `decisions/`。模板中的占位符必须替换，不能直接当作批准或固定引用使用。

| 材料 | 实际落点与用途 |
| --- | --- |
| [brief.md](brief.md) | 包内 `brief.md`；需求、范围、平台与审核责任 |
| [handoff.md](handoff.md) | 包内 `handoff.md`；状态、交互、组件和运行资源映射 |
| [manifest.yaml.example](manifest.yaml.example) | 包内 `manifest.yaml`；唯一文件清单、依赖与验收输入 |
| [approve.yaml.example](approve.yaml.example) | `decisions/approve-<release>.yaml`；真实人确认后绑定内容 D |
| [bindings.yaml.example](bindings.yaml.example) | 已采用需求层时为本 Version 的 `ui-bindings.yaml`；否则把适用条目保存到当前 Design 或真实任务／PR |
| [authority.md](authority.md) | 项目固定的人工权威约定；不能代替尚未提供的自动配置 |
| [manual-checklist.md](manual-checklist.md) | 制作、审定、取包、工程消费、验收与恢复操作 |

最短路径：固定 Brief → A 接收成品或 B 制作并迭代 → 导出完整内容提交 D → 真人确认最终字节 → 另存批准提交 A → 消费方固定 A 并恢复 D → 沿原工程流程实现、验收。

UI 包只定义设计输入。业务义务仍在原需求／Spec，技术选择在当前 Change 的 Design，唯一实施任务在 Tasks；没有需求层时不补 R/AC、BL 或空候选。设计批准与工程实施授权分别保存。使用说明自包含，不依赖教程计划或测试答案。

新包与撤回采用追加记录；制作源变化不自动更新消费者。`required` 和 `reuse` 都需要获批固定包；`not-applicable` 需要无 UI 影响的受审依据，不能作为缺包时的替代。
