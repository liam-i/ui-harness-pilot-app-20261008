# UI 设计交付与当前观察

本目录提供团队／AI共用的交付合同、严格Schema和只读检查器：固定包、批准、历史与消费绑定使用同一离线库；current另查独立UI权威，并提供无需求层的原Change／任务接线。需求层已有原G2/G3/G4的薄集成，完整采用资格仍在验证；人工语义审阅和原工程授权继续独立执行。

将本目录完整复制到业务项目 `harness/ui-design/`。实际包保存在选定 UI 权威仓库的 `design/units/<unit>/releases/<release>/`；决定保存在该单元的 `decisions/`。模板中的占位符必须替换，不能直接当作批准或固定引用使用。

| 材料 | 实际落点与用途 |
| --- | --- |
| [brief.md](brief.md) | 包内 `brief.md`；需求、范围、平台与审核责任 |
| [handoff.md](handoff.md) | 包内 `handoff.md`；状态、交互、组件和运行资源映射 |
| [manifest.yaml.example](manifest.yaml.example) | 包内 `manifest.yaml`；唯一文件清单、依赖与验收输入 |
| [approve.yaml.example](approve.yaml.example) | `decisions/approve-<release>.yaml`；真实人确认后绑定内容 D |
| [closure.yaml.example](closure.yaml.example) | D的完整闭包预检证据，后续由批准记录固定引用 |
| [bindings.yaml.example](bindings.yaml.example) | 已采用需求层时为本 Version 的 `ui-bindings.yaml`；否则把适用条目保存到当前 Design 或真实任务／PR |
| [authority.md](authority.md) | 人工权威约定；固定policy必须有真实审阅依据 |
| [manual-checklist.md](manual-checklist.md) | 制作、审定、取包、工程消费、验收与恢复操作 |
| [离线检查](offline-check.md) | 隔离安装、薄入口、固定快照、输出和失败恢复 |
| [当前观察](current-check.md)／[无需求层接线](no-requirements.md) | 独立权威查询、动作前复查、原Change／任务／PR与失败恢复 |
| [需求层接线](requirements.md) | 原贡献／任务、工程Review、实际E、G2/G3/G4当前组合及恢复；完整采用仍受验证边界限制 |
| [数据合同](data-contract.md) | Schema、policy、历史、绑定及证明边界 |
| [policy.yaml.example](policy.yaml.example)／[snapshot.yaml.example](snapshot.yaml.example) | 固定权威与当前／历史快照，填写实际身份后使用 |

最短路径：固定 Brief → A 接收成品或 B 制作并迭代 → 导出完整内容提交 D → 真人确认最终字节 → 另存批准提交 A → 消费方固定 A 并恢复 D → 沿原工程流程实现、验收。

UI 包只定义设计输入。业务义务仍在原需求／Spec，技术选择在当前 Change 的 Design，唯一实施任务在 Tasks；没有需求层时不补 R/AC、BL 或空候选。设计批准与工程实施授权分别保存。使用说明自包含，不依赖教程计划或测试答案。

新包与撤回采用追加记录；制作源变化不自动更新消费者。`required` 和 `reuse` 都需要获批固定包；`not-applicable` 需要无 UI 影响的受审依据，不能作为缺包时的替代。

首次采用只接受当前单一目标格式；不提供旧格式转换或跨规则版本路由。完整取回与固定输入检查可以离线进行；新的工程动作须按[当前观察](current-check.md)重读权威，并核对原工程Review／请求，不能用历史PASS代替。
