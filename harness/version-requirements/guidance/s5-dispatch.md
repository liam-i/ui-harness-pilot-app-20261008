# S5 初始候选释放与确认

采用 UI 时，先按[需求层 UI 接线](../../ui-design/requirements.md)准备本阶段的固定输入和原 Review/E；本页的业务职责、控制和授权条件继续适用。

[共同约束](README.md) · [前置：S4](s4-baseline.md) · [后续：实际规划](s5-planning.md)

本页用于**尚未 Propose**的候选：根据有效 BL 和当前工程事实选择依赖就绪的候选，预检释放草稿，再由整合者发布并独立确认，得到交给原 Propose 的引用包。检查同时核对本线容量和暂停限制。Propose 后进入 [G2/planning](s5-planning.md)，实施前另按 [G2/apply](s6-delivery.md)核对请求及 execution 对齐；不会一次性生成全版本的详细 Change。已有两轮顺序交付的实际 Agent 隔离证据，使用范围仍沿[共同约束](README.md)，不据此推断真实规模或任意宿主已通过验收。

## 固定输入与责任

选择候选前，可先生成[全版本就绪与阻断观察](s3-engineering.md#查看当前候选的就绪与阻断)。其中的小批建议不占额，也不代替下列逐候选的当前检查和明确决定。

在业务仓库读取当前已发布 BL、最新目标线和控制分支。先按 S4 取回原 B/C、批准、原发布观察及 pins；不得把本轮工程元数据 D 填成原 G1 的资料提交。current 模式核对真实远端，historical 只重算固定时点。

1. 工程负责人阅读当前代码、主 Spec、契约和资产，重新判断候选边界、全量分配、依赖与验证安排。保留原 BL 的 R/AC、scope、来源与批次审阅；单纯更新工程安排不重签原 BL。
2. 核对当前 Q 与原 BL：未变的 Q 保留原落实提交，新增或修改 Q 的 `applied_to` 使用完整固定引用；保留原 Q 身份，当前主项及重复项影响进入具名 question-applicability 检查。开放但只阻塞未来候选的问题不成为本轮隐藏门槛，当前 baseline/candidate 阻塞仍须解决。保存受审 `delivery-map.yaml` 和 `verification-plan.yaml`，再保存 `reviews/engineering.yaml`。Review 绑定原需求闭包及当前工程/规则输入；map/计划先于 Review 提交时保留确切 commit/path/sha256，不把旧哈希重新贴到新提交上。使用同一 ReviewScope 计算必需引用，实际结论和具名检查仍由负责人作出。
3. 逐边复核到期实施条件，并在当前工程 Review 记录[可用性依据](#当前依赖可用性)。已有/外部能力必须在目标 T 存在，原始执行与 E 的受检 T、身份、贡献一致；候选提供者按下节引用实际集成检查。未知不能作为已满足，已知未满足只可按确切边集合进入批准的 planning-only 例外。
4. 获得本候选的释放决定和 Propose 请求，将拟发布事件追加到 `requirements/versions/<Version>/dispatch/C-NNN.yaml`。当前合同要求 `release_decision` 和 `propose_request` 均由 `version.yaml` 中的 `engineering-owner` 作出：`role` 填 `engineering-owner`，`actor` 必须匹配该负责人。产品可以提出需求，整合者负责发布控制事件；这两种身份不能直接替代此处的工程决定。人员兼任时仍记录本次实际履行的职责，不只为通过检查改写角色。使用 `dispatch_payload` 的固定 BL、map/计划/Review、目标 T、上下文引用和两项决定；`based_on_control` 为本次实际读取的 P。保存 D 并按既有留存协议取回核对。D 尚未发布，不占额。
5. 准备下表快照，用唯一入口检查。检查器不写入事件、Review 或共享发布索引。

| 快照字段 | 本阶段含义 |
| --- | --- |
| `gate / phase / subject` | `G2 / dispatch / candidate:<Version>/C-NNN` |
| `baseline_ref` | 原有效 BL 的确切 B/path/sha256，必须是该 Version 当前已发布链头 |
| `publication_revision / publication_evidence_ref` | 成对引用原 BL 的真实首次观察，沿 S4；不是 dispatch 的发布证明 |
| `metadata_revision` | 原初始事件所在 D，与 `dispatch_ref.commit` 相同；确认已发布事件时保留原 D |
| `head_revision` | 本轮实际工程 head；规划前无提前实施，原产品/派生字节、当前 Q、map/Review 和实际安装规则不能藏在旧 D 后面 |
| `target_revision / control_revision` | 当前目标 T 与控制 P；发布前 P 是事件前驱，发布后用实际最新控制提交 P1；不能将旧观察视为持续锁定 |
| `dispatch_ref` | D/path/完整文件摘要及确切 event_id，不能只填文件路径 |
| 其余公共字段 | 沿既有 snapshot 模型填写 Version、交付线、checker/rule 版本、current/historical；有历史 BL 时保留各自 baseline_contexts |

终端：业务仓库根目录。`<snapshot.json>` 使用项目外本次专用目录中的实际快照路径。

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G2 --phase dispatch --subject candidate:v1.0.0/C-001 \
  --context '<snapshot.json>' --format json
```

尚未发布时，退出 0 只说明固定草稿可进入整合者的发布前核对，输出 `published: false`、`propose_permission: false`、`handoff: null`。重复预检不占额、不创建 Change。

## 当前依赖可用性

在同一 `reviews/engineering.yaml` 的 `engineering.availability` 中，按当前 map 的 `edge_id` 保存 `target_revision / conclusion / reason / assessment_ref / observed_refs / executions`。`conclusion` 为 available、unavailable 或 unknown；每项 execution 引用固定的运行证据 E 和本次所需运行身份。它是工程 Review 的依据，不是可手改的 ready 状态表。S3 只检查其结构与目标归属；本页释放时才核对到期条件的当前事实。

G2/dispatch 对到期 implementation hard 边核对目标线契约字节、map 选定的提供者证据、实际执行及确切 R 修订/AC 或技术贡献。写成 available 本身不能放行；缺判断或 unknown 返回条件未满足。明确 unavailable 只可在实际批准的 planning-only 例外中逐边列出，例外集合必须恰好覆盖本次未满足条件，仍不授予 Apply。软条件沿受审处置，尚未到期的 integration/release 不提前要求交付完成。候选提供者另按[后继候选的集成证明](#把实际集成事实用于后继候选)检查，不能只用 Archive 或局部测试替代。

## 串行发布控制事件

使用项目 `config/project.yaml` 中声明的单一控制分支和整合责任人。该分支的 `requirements/control/published.yaml` 只追加 `events[].event_ref`；事件正文仍在原 dispatch 或相应业务记录中，不复制 R、Spec、Tasks 或可编辑的容量计数。首次控制起点与固定对象留存沿 [S4](s4-baseline.md)。

1. 读取权威远端的当前控制 P 和目标 T，审阅本次真实决定、对象范围、输入与已有占额。将事件及其依据先保存为 D，并留存必要固定对象；`event_ref` 含 `event_id / commit / path / sha256`，摘要绑定整份事件文件，ID 选择其中确切事件。信封和 payload 使用已安装 Schema，不能引用尚不存在的提交。
2. 对原 P/T 和 D 执行本阶段检查。通过后，由同一整合者基于 P 只追加该固定 event_ref，显式暂存控制索引文件并提交 P1；不要把切换分支后出现的 `.harness/` 缓存或业务文件全量暂存进控制分支。
3. 再确认远端仍为 P，按快进方式发布 P1；不 force 覆盖，也不在另一个发布者已经前进后仅解决 YAML 冲突就重推。前驱或目标改变须重读事实、重算容量及适用决定，再准备基于新前驱的事件。`based_on_control` 必须对应该事件首次发布提交的直接前驱。
4. 独立读取远端结果，确认确切 event_ref 已发布；发布失败或结果不明时先查询，未确认前不开始依赖动作。同一固定引用重查/重复投递不重复生效，已发布 ID 不能改指其他字节，历史索引不能删除；更正使用新事件关联原记录。
5. 发布确认才形成共享预占，Propose 前也占额。容量按整条交付线汇总所有 Version；暂停、等待、超时或归档未合并不自动释放。planning-only 提升通过同一候选的 execution-alignment 沿用原名额，另核对实施请求；成功集成后的释放按 [S6](s6-delivery.md#名额释放预检与发布确认)单独发布和确认。取消决定或关闭 PR 本身不释放名额；整项未集成工作按[取消处置](requirement-change.md#独占未集成工作的取消)完成停止、留存、清理及审阅后，在原 `slot-release` 中使用 `outcome: cancelled`，经预检、发布和确认退出。共享候选仍欠其他贡献时保留原名额；取消退出不计成功交付，也不满足后继依赖。

控制发布与最终 Merge 由同一整合角色串行协调；普通 required check 不会因另一个分支改变而自动失效，动作前仍须读取最新控制并复核。检查器只读并拒绝不支持的事件，不是发布器或持续执行锁。hold/unhold/停止确认的字段和执行停点见 [S6](s6-delivery.md#任务边界暂停与恢复)。

## 发布后独立确认与引用交接

1. 整合者沿[串行发布协议](#串行发布控制事件)发布固定 event_ref，检查最新前驱；检查器不发布。结果不明先查确切事件，不另发新的初始 dispatch。
2. 独立取回最新实际控制提交 P1，保留原 D/event_ref，按本轮实际 head 重新准备 current 快照并执行同一 G2/dispatch。检查器从真实控制历史识别已占额的同一事件，重验 BL、当前工程/问题、留存与最新 hold。旧 P 的绿色结果不能代替此步；对齐事件已成为最新记录时，旧 dispatch 不再可用。
3. 确认通过后，输出 `published: true`；仅 current 且具备当前有效 Propose 请求时，`propose_permission: true`。这不是新的批准来源，实际请求仍在固定事件中；historical 只确认历史发布，始终不给当前许可。暂停期间仍占额，适用于当前对象和入口的所有 hold 都须分别核对；解除其中一个不清除其他限制。
4. `handoff` 是可重建的 JSON 引用包：`generated_from`、输入摘要、选定 R/AC/贡献、来源单元及文件/区间、所需资产/派生链、当前工程依据。引用保留实际 owner/提交/摘要，不复制产品正文或另写 Tasks。可将本次输出保存在项目外临时目录交给 Agent；不能编辑派生包来改变范围。
5. Agent 沿既有 Propose 入口核对实际工作区、Schema 和已有 Artifact，再执行已获请求的 Propose。生成/中断后的实际 Change 定位和 Trace 关联必须按后续规划流程接续，不能把无 Trace 当成可反复创建 Change 的依据。已存在或曾删除的 Trace 会被本初始阶段拒绝；随后按 [G2/planning](s5-planning.md)核对初始实际关联；初次实施按 [G2/apply](s6-delivery.md)继续，已提交及未提交代码/状态的恢复及任务边界检查见同页。

每次查询只提供当次观察，不占有后续执行锁；开始动作前仍须消费最新控制。项目 AGENTS 负责把这些检查接入已有入口，完整 Agent 执行过程仍须在目标环境验收。

## 把实际集成事实用于后继候选

前序候选实际 Merge 后，先完成 [G3/integrated 与名额释放确认](s6-delivery.md#名额释放预检与发布确认)。工程负责人再据实际目标代码、主 Spec、契约和测试修订现有 map、验证责任和工程 Review；纯工程反馈保留原 R/AC 与 BL，第二个候选尚未 Propose 时不提前生成其详细 Design/Tasks。

`engineering.availability` 沿原 edge_id 记录当前结论。提供者为候选时，available 记录增加 `provider_integration`，只保存三项固定引用：

| 字段 | 来源与核对 |
| --- | --- |
| `context_ref` | 提供者原始 current G3/integrated 快照，不带 slot_release_ref；必须对应本 Version、BL、候选和当前目标 T |
| `result_ref` | 该次完整实际 JSON 结果；检查器历史复算原 Gate，不从 PASS 文本推断完成 |
| `contract_ref` | 消费者使用的当前目标契约，例如主 Spec 或接口文件；明确列在 observed_refs，并确实属于提供者运行的输入 |

`executions` 选择前序同一 Trace 已验收的 E 和运行身份；所需 AC/能力必须属于该提供者的实际集成贡献，当前 R 修订、配置和 AC 分配仍逐项核对。`observed_refs` 固定目标 T 上的原执行输入。squash 后原 E 的受检提交仍是原提交，不改写为 T；集成检查已证明其适用性，再按目标字节与模式核对。仅 Archive、只有另一条线的完成记录、未关联的 E、未知或缺失判断均不能放行。

当前检查要求提供者集成证明对应**同一实际目标 T**。目标再次前进时，保留旧证明，在同一 Trace 上按 S6 重评当前适用性；涉及工程内容变化时补当前 E/最终检查，不将旧证明的 target 修改为新 SHA。该检查不创建新的实现请求或重复名额。此候选集成证明尚不支持跨 Version/交付线的继承与迁移，不用另一条线的 PASS 充当本线可用。

名额与依赖分别判断：提供者贡献有证据但尚未发布释放时仍占容量；释放已确认但当前依赖证据不足时，后继仍阻塞。工程反馈、受审当前 map 与验证责任进入后继 dispatch 固定输入；到期 integration/merge 条件还需要消费方实际组合验证，不能只用提供者局部测试替代。

## 失败与恢复

- 目标/控制已变：先取回最新事实，重新评估受影响输入；不改成 historical 取得当前许可。结果不明先查权威发布索引，不能重复预占。
- 工程 Review 与 map/规则不一致：重新审阅真实差异，保留有效内容；不能机械刷新摘要代替判断。D/head 中已有未受审代码则返回正确工程阶段。
- hold 或本线容量不足：保留已占额状态，等待明确解除/合法释放；暂停、归档或等待不能自动腾出名额。
- 原产品字节变化：不得沿用原 BL 掩盖差异。已有/外部到期 implementation 证据不适用时重新评估或实际重验；候选提供者缺少有效本线集成证明时同样阻断，不删边或改成 soft 获取通过。当前 Q 必须进入本轮工程 Review；D 的问题集合与 Review 不同则重新审阅，baseline/所选候选仍有阻塞则先落实决定。Q 答复实际改变已批准产品义务时，沿 [RC 处置](requirement-change.md)记录影响、限制相关动作并完成新 BL 与逐对象对齐；在适用解除和当前 G2 成立后接续，不能仅刷新 BL 引用继续。
- 历史 Trace 存在但当前已删除：不能退回首次 dispatch；恢复实际关联后走规划/返修入口。
- pin 缺失、错误、对象取不回：恢复确切已记录对象和引用，再重查；本地缓存存在不代替权威留存。

本阶段结束时交接原 BL、当前受审工程输入、确切发布事件和引用包。后续按 [S5 规划及修订](s5-planning.md)和 [S6 实施与交付](s6-delivery.md)接续各自的检查与授权；释放确认不授权 Apply、Archive、Merge 或 Version Completion。需求变化沿 [RC 处置](requirement-change.md)，整版验收沿 [S7](s7-completion.md)。GitLab 私库已有固定阶段作业、引用保护及受信任串行整合模式的验收证据；目标项目仍须核对实际平台版本、配置、权限和 Runner，不能从平台聚合绿色推断所需作业已执行。最终动作前由整合者核对真实 Job、产物及最新目标和控制，不把既有验收外推到任意宿主或自动合并。
