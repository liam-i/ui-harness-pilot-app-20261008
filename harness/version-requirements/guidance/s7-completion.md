# S7 整版验收与发布接续

采用 UI 时，先按[需求层 UI 接线](../../ui-design/requirements.md)准备本阶段的固定输入和原 Review/E；本页的业务职责、控制和授权条件继续适用。

[共同约束](README.md) · [前置：实际交付](s6-delivery.md) · [需求变化](requirement-change.md) · [下一版](version-iteration.md)

本入口核对有效 BL 中全部 Requirement 的全部 AC，包括继承、已有能力、外部交付及退役义务。单个 Change 的 Archive、G3 或 Verify 通过不能代替整版验收。当前入口已在合成小版本、零 Change、Tiny 和外部交付物场景完成声明范围内的隔离验收；实际命令与模拟角色决定分别记录，真实规模、独立 Agent、人工 UAT 和托管平台采用仍须另验。

检查器只读既有 Artifact，不执行测试、批准、发布或回滚。产品、工程、QA 和发布负责人按实际职责作出决定；Agent 可准备资料，不能填写虚构批准。测试 Fixture 的 synthetic 决定不适用于业务项目。

## 固定候选组合

在业务项目中，先完成本版各贡献的 S6 交付及必要 RC 处置。Standard 保留实际 current G3/integrated 原快照、完整输出及成功名额释放；Tiny 保留实际任务／PR 的集成回执；已有／外部路径保留实际 scope 交付回执。取消不计作成功交付，未完成移植不计作已有能力。

确认本线实际集成提交 C，再固定待验构建和环境。这里的 C 是本次受检代码提交；它不同于 S4 的需求内容提交。后保存的测试／Review／决定位于 D，不能把 D 填成已经测试过的代码 SHA。

在 `requirements/versions/<Version>/release/candidate-NNN.yaml` 保存 `release_candidate` 模型，完整定义见随安装分发的 [Schema](../schemas/vr.schema.json)：

| 字段 | 应填写的事实 |
| --- | --- |
| `id / version / delivery_line` | 例如 `v1.0.0/candidate-001`，以及本版和目标线；它不是 S5 的 `C-001`，也不是需求变更 `RC-001` |
| `baseline_ref / code_revision` | 当前有效 BL 的固定引用、本线实际 C |
| `input_refs` | C 上完整受检工程文件，包含代码、主 Spec、测试、配置、依赖与资源；不能只列最近一个 Change 的文件 |
| `dependencies_ref / configuration_ref` | 上述工程输入中的确切依赖和配置身份 |
| `build_ref` | 实际 `release_build` JSON 回执的固定引用 |
| `environments` | 各环境的 ID、适用时点 `completion/release`、固定环境／数据／外部服务／部署目标引用 |
| `delivery_receipts` | 原 G3 的 `context_ref / result_ref` 与本次接纳的贡献 ID；所有有效业务贡献必须覆盖且不重复选择 |

`input_refs` 至少覆盖 C 上全部已跟踪工程文件；`requirements/`、需求工具目录和入口的元数据由原 BL／工程上下文另行保护，实际进入构建的来源资源仍须显式列入输入。检查器不会猜测哪些图片、配置或关卡被打包。

`release_build` 回执保存 C、确切 `input_refs`、构建命令、工作目录、起止时间、真实退出码、原始日志和产物 `artifact_ref`。产物字节、构建输入和日志均须留存，不能拿任意“构建成功”文本充当产物。构建环境、命令含义和证据来源由工程审查核实；摘要比对不替代可信 CI 或真实执行。

候选清单一经保存不可改写。同一 C 的构建、依赖或环境组合发生变化时，也需新候选及重新 qualification；保留旧候选和旧通过结果。只追加对同一组合的真实 E／Review／决定，不必重测证据提交 D。

## 执行整版验证并作出 Completion 决定

1. 沿本版唯一 `verification-plan.yaml` 执行实际用户旅程、适用 NFR、权限／异常和人工验收；在原 `trace/verification/` 保存新 E，并把引用追加到相应义务。E 必须记录实际 C、候选构建／配置／依赖、环境／数据、测试定义与真实原始结果。未执行、跳过、零匹配及失败均保留原结果。
2. 更新既有 `delivery-map.yaml` 和 `reviews/engineering.yaml`，对本线当前契约、依赖和验证责任重新审阅。保留原交付回执；不把历史 G3 重新标成测试过最终组合。检查器复算历史交付，并另外要求当前 C 的整版 E。
3. 产品、工程和 QA 在现有 `reviews/delivery/` 分别保存具名 `delivery` Review，三方不得由同一个身份冒充。审阅须绑定候选、BL、当前 map／plan／工程 Review、完整工程输入、构建、原 G3 回执和全部到期 E。沿用 `review_input_digest(...)`，检查项为 `version-scope / combination-acceptance / traceability / build-provenance / evidence-applicability / issues-and-changes`；实际通过后才写 passed。
4. 在 `release/decision-NNN.yaml` 保存 `release_decision`：本版身份、候选引用、`phase: completion`、三份 Review 的固定引用及 `authorization: null`。决定不能早于它所依据的运行；Review 中的未读项必须处理，问题必须对应本版共享 Q。
5. 取回当前目标／控制及全部固定对象，准备 current G4 快照。保留原有效 BL／发布观察，固定真实 metadata/head/target/control；增加 `release_candidate_ref / release_decision_ref`、当前 `engineering_inputs` 和实际 `verification_inputs`。后者覆盖本阶段验证计划选择的全部 E；采用UI且包含无R技术任务时，另包含该实际已选任务的最终运行E，按共同任务覆盖合同核对，不能塞入无关记录。

```bash
# 在业务项目根目录；快照及本次命令输出保存在项目外的检查目录。
bash scripts/requirements-check --root "$PWD" \
  --gate G4 --phase completion --subject 'release-candidate:v1.0.0/candidate-001' \
  --context '<本次 current 快照的绝对路径>' --format json
```

退出 0 后核对 `G4.completion`、确切候选／决定／C，以及 `qualification: complete`。逐 AC 结果来自整个有效 scope，不来自已经生成的 Change 集合。零 Change 版本同样进入 S6→S7，不建空 Change 或伪造 Archive。

所有最终业务 AC 都是 Completion 的分母。把最终业务验收写到 `checkpoint: release` 不会使其自动从分母消失；若尚未执行，Completion 仍不能通过。纯发布准入使用非 final 或技术验证义务、明确的 release 时点与具名适用性依据，不能用它隐藏未完成的业务功能。

共享 Q 可用 `completion` 或 `release` 标明阻断时点；已有 baseline／候选阻断继续保留。纯 release 问题和未到期 release 条件不会阻断 Completion；非阻断事项也须有具名负责人及已接受的处置。必要 RC 必须完成实际处置，不能仅批准或 aligned。现有 Apply／Merge 限制仍须处理，Completion 不自动解除任何 hold。

## 持续查看来源、分配、验证与阻断

需要跟踪进展时，复用已有阶段快照生成四组只读面板，不新增状态表。在业务仓库终端执行，先准备本版本的 `views/` 父目录，并选择新的输出目录：

```bash
.harness/version-requirements-venv/bin/python -I -B \
  harness/version-requirements/lib/report.py --root "$PWD" \
  --context '/absolute/path/to/current-stage-context.json' \
  --view metrics --output requirements/versions/v1.0.0/views/metrics-001
```

输出 `metrics.md` 和 `metrics.json`：来源面板保留全部来源单元和未处理 ID；分配面板以 scope 的全部 R/AC 为分母；验证面板核对明确选定的整版候选及全部到期验证责任；阻断面板列出 Q、hold、未关闭 RC、当前候选阻断和过时证据。每个比例都有分子、分母和剩余 ID，零分母显示空值，不显示 100%。分母不接受 AC 筛选。来源解释存在循环或关系尚未裁决时，单条反向映射不能证明处理闭合，面板保留 unknown 和全图诊断。

| 状态 | 所需事实 |
| --- | --- |
| mapped | 当前 AC 已分配到合法交付贡献；只有边存在 |
| planned | 贡献有实际 Trace/Spec/Task 关联，或已有/外部路径的契约及验证责任；尚不表示规划批准或准入 |
| implemented | 实际 Task/实现或交付引用在当前工程输入上仍成立；不由勾选或测试链接单独推断 |
| executed | 当前整版候选的到期验证责任实际执行；失败算执行，skipped/未找到不算 |
| passed | 当前执行通过并覆盖全部必需贡献；同一 AC 的多份贡献不能只完成其一 |
| accepted | 完整候选、交付、当前执行、三方决定及控制事实可按 G4 复算；历史验收不计为当前验收 |

S3～S6 可以查看来源、分配和已保存的工程关联；尚未选定 `release_candidate_ref` 时，最终验证和验收明确为 unknown，不将局部 Feature 的绿色当作整版通过。S7 使用真实 G4 快照中的候选、工程和 E 身份；缺决定、失败、跳过或旧构建/环境分别留下诊断。历史模式显示所选时点的证据并标记 `current: false`，accepted 不升级为当前验收。

报告会读取和复算已有证据，不执行测试或发布。`generated_from` 保存完整固定快照、输入摘要和生成器指纹；`gate_evaluated: false` 表示报告不是一次可消费的 Gate 结果。它不改 R、Tasks、批准或控制事件；任何比例都不代替语义审查、实际验收及上节的当前 G4 命令。已有输出拒绝覆盖，后续输入变化生成新的报告。当前候选的释放建议另见[就绪观察](s3-engineering.md#查看当前候选的就绪与阻断)。

## 发布前检查

发布决定使用本版已声明的 `owners.integrator`，或专职的可选 `owners.release-owner`。整合者承担发布职责时，仍须有针对本次候选的真实发布授权，原 Merge 请求不能代替它；三方发布审阅同时核对授权来源。使用已有整合身份不要求为了 S7 修改产品 BL。若实际责任人发生变化，先按受控身份变更审阅其适用范围，不能悄悄改写冻结内容。

按项目实际情况核对安装、升级、迁移、回退、外部环境、交付资料等发布条件。不适用有实际依据，不一律新增迁移或培训工作。到期义务沿同一验证计划记录 E，重新审阅当前工程输入；候选组合未变时沿用原 candidate 文件。

保存新的 `release/decision-NNN.yaml`，`phase: release`。三方 Review 除上述检查外增加 `release-conditions / deployment-target / release-authorization`，绑定本次全部到期证据；`authorization` 使用已声明发布负责人的真实决定，不能由 Completion 或工程自检代替。

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G4 --phase release --subject 'release-candidate:v1.0.0/candidate-001' \
  --context '<发布前 current 快照的绝对路径>' --format json
```

仅退出 0、`current_qualification: true` 且 `release_ready: true` 表示本次组合已满足发布前条件；此时 `qualification: ready-to-release`，尚未发布。historical 不授予当前许可。CI 使用同一入口、快照与结果绑定，不另维护一份 Version 状态。

整合者在实际发布前按既有串行消费协议重新核对目标、候选和控制，发布由团队工具执行。Gate 不是未来状态的租约，不自动调用发布平台，也不以一次旧查询覆盖新 hold。

## 实际发布与发布后确认

保存真实 `release_operation` JSON：候选／决定／构建／产物／部署目标引用、执行者、命令、工作目录、起止时间、退出码及原始日志。操作必须在本次明确授权之后开始，事后新增的决定不能追认先前操作。失败先保留现场，按团队发布恢复流程处理；重试前检查实际平台状态和已有操作记录，不因上次返回不明就重复发布。

在 `release/observation-NNN.yaml` 保存 `release_observation`，引用该操作、相同组合、真实结果与具名整合者／发布负责人确认。成功操作之后才运行必须的 smoke／人工检查，并通过 `post_verification_inputs` 引用其实际 E；发布前的绿色结果不能充当发布后确认。

将新 `release_observation_ref` 加入 release 快照，再运行相同 G4/release 命令。操作与后验都成立才返回 `qualification: released`；此时 `release_ready` 为 false，不表示授权再次发布。结论确认所选 observation 对应的实际操作，不代替发布平台的最新部署状态；有后续尝试时保留其记录，并核对实际平台状态后接续。失败返回非零，保留早先 Completion、失败观察及发布恢复记录；不能修改旧 E、候选或决定来消除失败。

## 失败与上下文恢复

- C、BL、构建、环境或当前控制不匹配：保留旧结果，定位实际变化；新组合重新 qualification，不能只更新 PASS 标签。
- 返回`rules.snapshot-mismatch`：按[S4的固定规则边界](s4-baseline.md#历史-bl继承和同版本前驱)核对完整安装及所选输入。只支持当前目标合同；保留原记录并停止依赖动作，不登记旧profile、改写原证据或切换historical取得发布权限。
- 缺原 G3、未确认成功交付、scope 分母缺项或 RC 未处置：回对应 S6／RC 入口，不能通过删贡献、复制另一线证据或伪造 Archive 补齐。
- 测试／Review 未通过：保留原失败，只重跑修复或变化实际影响的检查。代码缺陷沿原返修路径，业务变化走 RC；Explore／Verify 继续保持显式选择。
- 中断、对象缺失或配置回滚：恢复确切 candidate／decision／BL／G3／E 和受验规则，核对真实远端后重新只读检查。未知模型明确拒绝，不覆盖历史以迁就当前 Schema。

离开本阶段时，交接确切候选、最后真实结果、未决问题／失败操作、证据位置和下一入口；下一版本从独立 Intake 开始，不能把旧版本的 released 当作新线所有义务已经满足。
