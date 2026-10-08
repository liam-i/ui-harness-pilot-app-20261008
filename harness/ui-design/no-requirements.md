# 无需求层的 Change／任务接入

这份指引接入项目已有的 Standard Change 或独立 Tiny/task/PR，不创建需求数据库、候选、第二份 Tasks 或新的 OpenSpec workflow。先完成[安装](offline-check.md#安装与前提)、[固定权威](authority.md)和[当前观察输入](current-check.md#准备一次动作的输入)。项目负责人在原工程审阅中确认适用性、policy 与完整工具身份。

## 一次接线

将下面的规则合并到业务项目原 `AGENTS.md` 的阶段规则；按项目替换固定输入位置，不另建业务状态台账。完整指引随 `harness/ui-design/` 一起安装。

```markdown
### UI 工程输入

涉及 UI 的原 Change／任务先读取 harness/ui-design/no-requirements.md。
按原 Tiny/Standard 分流及阶段授权执行；消费固定 ui-bindings 与已审包，不读取 latest 自动替换。
每次 Propose、开始/恢复实施、合并、集成、发布前，先核对当前工作区与原 Review／请求，
准备本次动作的固定快照，调用 scripts/ui-design-check --context <实际快照> --action <本次动作>。
UI工具使用已审版本及锁定venv；快照mode必须current，action必须相同，固定policy不能删。
非零或UNKNOWN停止依赖动作，记录失败与下一允许操作，不改成historical、不自动fetch或批准。
PASS只是一项证据；原授权、行为测试、UI验收及CI仍须满足。
Standard仅在当前Change的唯一tasks.md记录实施；Tiny只记原任务/PR，不制造C、Change或R/AC。
恢复从原Artifact、Tasks/任务、固定输入和上次失败重建；重新观察后接续，不重签包或重复动作。
```

`--root` 默认当前工作目录；仓库映射使用相对路径时须明确指定正确根。项目与 CI 的已有命令链应要求此命令退出0，并核对 JSON 顶层 `result` 和受检身份；不能只看 `fixed_result` 或 `--describe`。接线只插入前置检查，不自动调用 Propose、Apply、Archive、Merge 或发布。

## 原阶段中放什么

| 原入口 | 保存位置与固定内容 | 动作前调用 |
| --- | --- | --- |
| Standard Propose | 原请求/任务已有的需求与范围、预选UI包和适用性；Change尚未创建时用真实task身份，创建后在Proposal关联原任务与包，不伪造未来Change提交 | `--action propose`；快照 `action: propose` |
| Standard 规划审阅 | Proposal引用范围；Spec描述可观察行为/状态；需要技术Design时保存组件/资源/适配/验证；`tasks.md`唯一。绑定引用已存在的Proposal和真实工程审阅 | 规划确认后才允许开始；设计包存在不强制新增技术Design |
| Standard 开始／恢复 | 原规划审阅、实施请求和当前工作区；包、行为覆盖、允许差异和固定绑定与受审输入一致 | `--action start`／`--action resume`；不得让旧PASS替代重读 |
| 独立 Tiny／无 R 技术任务 | 原任务或PR的实际需求、边界、授权、验收、固定绑定及不适用依据；`consumer.kind: task`。不制造R或空候选 | 开始／恢复用相同动作入口；Tiny不得接管未交付Standard工作 |
| 合并／集成／发布 | 原PR、运行及交付证据，实际待交付组合；仍沿原归档、CI、审阅和授权 | `--action pre-merge`／`integrated`／`release`；各次动作单独重读 |

UI-only元数据的工具准备、只读调查本身不是业务Propose；不得机械创建Change。反过来，正式业务开始实施需要确切已审输入，缺设计包的 required 消费者必须停下。

## 最小填写示例

以下是**字段示意**，占位值不可运行。原[bindings模板](bindings.yaml.example)和[snapshot模板](snapshot.yaml.example)给出完整结构，不另复制全部模型。

```yaml
# Standard：引用已经存在的Proposal；唯一Tasks仍是该Change的tasks.md。
consumer:
  kind: change
  subject: adjust-menu
  record_ref:
    repository: project
    commit: <已有Proposal提交>
    path: openspec/changes/adjust-menu/proposal.md
    sha256: <原Proposal摘要>
# 独立Tiny、无R技术任务或Propose前的真实请求：
# kind: task；subject: <原任务ID>；record_ref固定原任务/已归档PR导出材料。
```

没有技术Design时，把 binding sidecar 放在原 Change 下并由 Proposal／规划审阅引用；有Design可由它索引。Tiny放原任务/PR证据目录。sidecar只有固定消费关联，无任务状态。PR网页须先按原证据方式固定为可恢复文件；不能把动态URL当Git引用。

每条 `required/reuse` 绑定固定 A，完整递归 D/资源/允许差异由同一库核对；原实际工程行为构成独立 `selections.behaviors`。无UI影响用有依据的 `not-applicable` 并且行为分母为空；不能靠清空分母消除真实义务。机器无法判断整体伪造的审阅输入，原工程Review负责核对分母和语义。

## 失效后的停点

缺包、撤回或UNKNOWN时，保留当前代码和唯一任务事实，记录失败、确切policy/UI SHA、受检HEAD与差异、最后有效Review／请求、未解决问题和下一允许动作。对象缺失先沿获授权的准备操作恢复；实质设计或范围变化沿原Update及整组审阅；仅补对象且原请求仍有效时重新检查后接续，已有授权不重复索取。

检查器本身不改变任务状态、不暂停原生Goal、不授予工程动作。安装规则漂移先恢复已审安装或明确审阅新实现，不能仅刷新快照中的摘要。下次会话从上述原记录恢复，禁止复用过时PASS。

需求层的联合实现身份、ReviewScope、控制及G2/G3/G4尚未接入。已有需求层关联不能用本无需求层示例解除；此时仅作为独立UI检查证据，仍执行原需求层规则，待相应正式接线验收。

[交付入口](README.md) · [当前观察](current-check.md)
