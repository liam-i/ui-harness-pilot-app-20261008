# 需求变化的影响分析与决定记录

[阶段约束](README.md) · [原始包接收](s0-intake.md) · [基线保存与恢复](s4-baseline.md)

位置：已安装需求层的业务仓库根目录。收到 PRD 换稿、附件更新或具名产品答复后，先保留旧输入与真实工程状态，再分析哪些承诺和交付对象需要重新决定。本指引覆盖影响分析、新 BL、逐对象对齐、指定入口恢复，以及按实际状态整改、取消、退役和确认 RC 处置。业务承诺改变时重审整组规划；承诺未变时可经适用性审查沿用原 Review，两者均需与当前 BL 相符的新实施请求。

上述路径已有声明范围内的隔离验证，包含共享取消、归档未合并返修、已集成功能退役和两个候选的广域恢复。退役样本检查本地入口、专用模块和配置资源，不能替代项目实际适用的数据、权限或外部系统检查。RC verified 只表示本次处置完成；版本迭代、整版验收和生产采用仍需各自证据。

旧候选已由需求层完成集成并释放名额、同版本再以新候选修改承诺时，按下文[保留已完成交付](#保留已完成交付)处理旧身份。旧候选不能重新占额，新候选也不能冒领旧候选的交付责任。该路径已有局部规则与原交付重放验证，完整 RC 接续验收仍在进行；不得据此宣称整条变更流程或生产采用已通过。

## 准备固定输入

1. 保留原 intake、旧 BL、原 Review、Trace 与运行证据。新包进入新的 intake，full/delta、前置和替换关系沿 S0；删段或换图只说明输入变化，不自动取消原承诺。简短答复引用具名 Q 的原证据，不要求重新复制整个 PRD 包。
2. 保存旧状态的阶段快照 `before.json`：明确版本、交付线、原 BL 与内容、当时目标提交及工程 Trace 所在的元数据提交。复查历史使用 `evaluation_mode: historical`，不将过时的远端观察冒称 current。
3. 在隔离分支保存拟修订的来源、scope/R、map/验证计划及当前工程事实。使用 G1/content 快照 `after.json` 指向该固定内容提交；旧 BL 仍是当前承诺，草稿没有获得批准。`metadata_revision` 用实际 Trace 所在提交；代码和目标线输入分别由 `head_revision`、`target_revision` 固定。
4. 两份快照须属于同一 Version、delivery line 和仓库。跨线影响分别准备各线确切输入；相同 R ID 或 revision 序号不允许合并成一份无上下文的比较。缺固定文件、非法 Schema 或无法恢复历史时先停止分析并恢复证据。

本报告不要求新稿已经通过 G1。它允许呈现尚待处理的依赖、删除后残留分配和未知影响；来源身份及文件摘要仍必须能解析，不能靠忽略坏输入得到空清单。已知影响按 [S6 暂停与恢复](s6-delivery.md)的共享 hold 协议处理，报告本身不发布控制事件。

## 生成和审查

用项目已安装的精确 venv，输出到明确的新目录。以下占位路径替换为本轮实际快照；输出父目录须已经存在。

```bash
.harness/version-requirements-venv/bin/python -I -B \
  harness/version-requirements/lib/report.py --root "$PWD" \
  --view impact \
  --previous-context /absolute/review/before.json \
  --context /absolute/review/after.json \
  --output /absolute/review/impact-001
```

`impact.json` 保存实际差异、受影响对象、旧/新引用、传播理由及 `generated_from`；`impact.md` 提供阅读清单。退出 0 仅表示报告已生成，结果的 `gate_evaluated` 始终为 false。相同固定输入可在另一个新目录复跑；已有输出不覆盖。不得编辑报告来修改 scope、批准或当前状态。

没有文件差异但存在明确的外部工程事实时，可以用 `--impact-seed requirement:v1.0.0/R-001` 等已有图对象作为审查起点。未知 ID 拒绝；它只扩大待分析集合，不表示工程事实已经证实。影响视图不接受 S3 的筛选参数，避免过滤掉应处理的旧消费者。

审阅时依次核对：

- **旧新关系并集：** 删除或替换的边仍带回原提供者、原消费者和后继；层级只触发相关系统义务的影响审查，不变成执行前置。普通 informational 关系保留说明，不自动沿整张图扩散。
- **来源与附件：** 比较实际生效包的目录、显式替换、源单元和当前链接语境。只替换附件也能命中未改字节的主文档及原消费者。派生物沿原所有者的固定输入追溯；新增但尚未采用的附件不自动使全部 R 失效。
- **实际工程对象：** 从 Trace 关联 AC、候选、Spec、Task、实现文件、测试定义和 E；共享代码或契约需同时审查其他消费者。图里的 E 是待重新判断的历史证据，报告不复算其运行结果，也不改写原 PASS。
- **未知与范围：** `unmapped_diff` 保留尚无关联的真实文件变化；`diagnostics` 保留缺端点、未知条件等问题。逐项给出受审的保留、修订、取消、替代或重验依据，不能把未映射解释为无影响。保守传播可能包括最后经审查确认不受影响的对象，不能据连通性自动要求全版本重批。

源码、部署、数据或外部服务中未进入 Trace 的真实影响仍需工程/QA 补查。报告发现未知，或已知控制尚未解除时，保持相应行动阻塞；成功生成报告不能替代产品决定、实际停止确认、G1/G2/G3 或版本验收。

## 记录并预检 RC

RC 是需求变更记录，保存于 `requirements/versions/<version>/change-requests/RC-NNN.yaml`，使用既有 `schema_version: vr/1` 和 `events` 信封。事件及其证据先提交并持久留存；控制分支只追加确切 `event_ref`。整合者沿 [S5 串行发布协议](s5-dispatch.md#串行发布控制事件)操作，不能把原 RC 正文复制成另一份控制状态。

每条事件保留 `event_id / kind / version / target_line / actor / evidence_ref / based_on_control / payload`。`actor` 为该版本整合者，责任人的决定另含真实 `actor / role / at / statement / evidence_ref`。事件 ID 不复用，同一 RC 文件只追加；以下引用均包含实际 `commit / path / sha256`，事件引用再带 `event_id`。

| 事件 | payload 的内容 | 退出条件 |
| --- | --- | --- |
| `rc-proposed` | `rc_id / from_context_ref / source_refs / reason / known_targets / request`；原快照选已生效 G1，已知对象使用 S5/S6 的 typed target | 具名提出、原 BL 可复核；不会占用新名额或批准修改 |
| `rc-impact-assessed` | `rc_id / previous_ref / before_context_ref / after_context_ref / report_ref / dispositions / unmapped_dispositions / review`；可选 `historical_deliveries` 见下文 | 复算原报告；每个受影响对象和未映射差异有审阅依据，不能删掉清单中的旧消费者 |
| `rc-decided` | `rc_id / previous_ref / outcome / content_context_ref / decisions` | approved 绑定确切受审 C 及产品/工程/QA 三方决定；存在 investigate 时拒绝批准。rejected 由产品决定，withdrawn 由原提出人角色决定；两者不携带新内容批准 |
| `rc-baselined` | `rc_id / previous_ref / effective_context_ref / confirmation` | 复核实际 G1/effective、新 BL 的原前驱与获批 C，以及同一组三方批准证据；仍为 approved，不代表工程已 aligned |
| `rc-aligned` | `rc_id / previous_ref / context_ref / object_ids / review` | 固定当前分配、整组规划或已完成整改的合并前事实，按已审影响清单逐对象记录局部对齐；检查不产生执行许可 |
| `rc-restored` | 与 `rc-aligned` 相同 | rejected/withdrawn 使用原有效承诺，verified 使用已批准后继；分别核对实际入口，保持终态决定，不批准新 BL 或自动解除 hold |
| `rc-verified` | Standard 使用 `rc_id / previous_ref / context_ref / object_ids / result_ref / reviews`；取消以 `outcome: cancelled / slot_release_ref` 代替 `result_ref`；纯上游以 `outcome: upstream / input_digest` 代替 `result_ref` | 分别复算 current G3/integrated、实际取消退出或当前 G1/上游处置；均需工程/QA 审查，全部必要对象验证后才关闭 RC。取消和纯上游不代表成功交付 |

`previous_ref` 指向本 RC 最新已发布的生命周期事件；hold 等控制事件另按原规则追加。`from_context_ref` 是固定 G1/effective 快照文件的引用，不是只有一个 BL 文件路径。`before_context_ref` 可固定同一原 BL 的实际工程/Trace 语境；`after_context_ref` 选择尚未获批的 G1/content 草稿。未回答的问题可先出影响报告，批准前必须满足全版本 G1/content 的结构及 Review 条件。

`dispositions` 每项写 `object_id / action / owner / reason / review_refs / revalidation`，action 为 `retain / revise / remove / replace / retest / investigate`；它是处置决定和验收条件，不复制 Feature Tasks。`unmapped_dispositions` 按报告中的 `group / path` 逐项写 `action / reason / review_refs`，action 为 `accounted-for` 或 `investigate`。后者保留待查问题，不能凭“报告可读”批准。

将拟发布事件的确切引用保存为本地 `rc-event-ref.json`，准备含最新控制提交的同版本/交付线快照。使用项目已有精确环境执行：

```bash
.harness/version-requirements-venv/bin/python -I -B \
  harness/version-requirements/lib/report.py --root "$PWD" \
  --view changes --context /absolute/review/current-context.json \
  --event-ref /absolute/review/rc-event-ref.json \
  --output /absolute/review/rc-preview-001
```

检查 `changes.json` 的 `event_check`：草稿校验通过时 `published: false`。随后按串行协议发布同一引用，独立读取当前控制，更新快照，并用另一个新输出目录重跑；只有确切引用已在所选控制历史中，才显示 `published: true`。结果不明时重复读取同一事件，不重新编号。省略 `--event-ref` 只列出已发布 RC。报告始终 `gate_evaluated: false`，不写业务文件或控制，也不代替 G1/G2。

## 保留已完成交付

适用于旧候选在本 RC 提出之前已实际集成并发布成功 `slot-release` 的同版本、同交付线场景。已取消、尚未集成、未释放、跨线或后来才完成的候选不适用。原释放引用的可读性不足以证明完成，检查器从 `rc-proposed.based_on_control` 重放原完成预占及 G3 回执。

1. 旧候选在拟议 map 中保留原 ID 和 Change 名称，标为 `superseded`；修改后的 R/AC、代码和测试责任明确分配给当前候选。旧 Trace 和 Archive 保留，不重新 Apply、占额或取消历史成功。完整 Impact 清单仍逐项审查，旧候选/Change 的处置为 `retain`。
2. 在 `rc-impact-assessed.payload.historical_deliveries` 中，每项填写 `slot_release_ref / object_ids / input_digest / reviews`。`slot_release_ref` 是原确切发布事件引用；`object_ids` 只能包含原候选及原 Change 在本报告中实际出现的全部身份，例如 `candidate:v1.0.0/C-001` 和 `change:original-change`。不能夹带 R/AC、Task、代码、测试或整版验收。
3. 计算该项摘要：组成一个 JSON 对象，字段为 assessment 的 `rc_id / previous_ref / before_context_ref / after_context_ref / report_ref`，加该项的 `slot_release_ref / object_ids`；以 UTF-8、键排序、无多余空格、不转义非 ASCII 的规范 JSON 计算 SHA-256。数组保持填写顺序。工程和 QA 负责人实际核对上述输入与历史保留责任后，在各自审阅证据中写明该摘要，分别填写具名 `decision` 到 `reviews`；不能只复制旧成功的批准。
4. 依照原协议预检并发布 assessment。历史证明只结清两个旧身份的保留责任，不产生可执行入口，也不减少影响清单。当前候选继续新 BL、分配/规划审阅、对应 G2、授权、Apply、G3、Archive 和名额释放；当前 R/AC、代码/测试与其他影响仍需实际处置。
5. 如需解除本 RC 对旧候选、旧 Change 或其确切旧 Task 的 Propose/Apply/Merge hold，另发具名 `unhold`，其 `alignment_refs` 显式引用本次已发布 assessment 的文件引用。Version/line 的广域解除必须同时引用适用于该入口的当前候选局部证明；历史保留加这些局部证明须覆盖完整影响清单。只证明 Propose 不能解除 Apply/Merge，历史保留不支持 Release，也不解除其他 hold。
6. 新候选的 `rc-aligned / rc-verified.object_ids` 仍只写它实际承担的处置；检查器合并已证明的历史对象判断 RC 是否收齐，不把旧身份塞入新候选证明。最终关闭还核对当前目标/元数据中的原归档完整文件集、字节和模式，以及原 Trace 和本 RC 残余执行 hold。原 G3 允许整合证据晚于 Merge 保存，因此目标线可保留原合并时的 Trace，或接纳确切的最终集成 Trace；当前元数据必须保留后者，不能任意重写。

assessment 或局部检查通过都不等于 RC verified。后续若改写旧归档/Trace、重开旧 Change，或留有本 RC 对旧对象的执行限制，关闭会拒绝。整版验收仍使用新组合的当前证据，旧历史证明不进入成功交付/AC 覆盖集合。

## 批准、新基线与停止边界

提出后，先按已知影响发布 hold，通知执行者并保存真实停止确认；分析扩展时追加作用域。已识别的受影响 RC 本身也会阻止新的相关执行准入，避免 hold 尚未发布的间隙放行；它不自动生成 hold，不影响已确认无关的对象。拒绝或撤回不会删除既有 hold，也不会释放名额。

阈值等业务语义变化应推进 R 修订，保留原 R/AC 身份和旧原稿。以具名 Q 作为新来源时，必须同时核对来源替代关系、Q 的落实与当前适用性、受影响全局/批次/工程 Review、map 和验证义务，再保存最终 C；仅重新计算 Review 摘要不能补上缺失的语义审查。

三方决定引用确切 C；批准事件发布后，沿 [S4](s4-baseline.md)保存 B，以 `requirement_change_ref` 指向该确切批准事件。再检查 record、实际发布并确认 effective，最后追加 `rc-baselined`。新 BL 必须指向本版本原生效前驱，批准证据与 RC 三方决定相同；G1 和 RC 确认分别核对这两个方向。尚未发布、指向另一 C/前驱/版本或批准证据不同，均不能作为新 BL 的有效决定。检查不会递归要求后来才存在的 `rc-baselined`。

首 BL 不需要 RC；已发布的旧格式 BL 按已受验的原规则和确切原发布观察复核，不补写新字段。尚未发布的旧格式后继草稿仍须补齐当前合同。C 的获批内容清单保持原字节；独立的 RC/控制记录按原追加和固定引用协议延续，不能因提出记录早于 C 就禁止后来追加决定。即使 Review 明确引用早期 RC，获批原件仍保存在固定 C，当前原 RC 只可追加后续事件，不可改写被引用的历史前缀；原 PRD/附件、R 和代码不适用这项追加规则。

## 在隔离项目对齐当前对象

1. 从新有效 BL 读取 R/scope，复核当前 map、验证计划及工程 Review。已存在的预占追加 `execution-alignment`，保留原名额；已关联 Change 的候选必须保持该真实名称。多次 BL 变化可一次对齐最新 BL，但中间各 RC 批准和 BL 生效证据都必须可恢复。此时 hold 仍有效。
2. 未 Propose 的候选准备 G2/dispatch 快照；已有 Change 准备 G2/planning 快照及实际 Trace/整组 Review。业务承诺改变时按既有 Update 审阅，不把旧 Review 改标签。Apply 已开始则保留 `apply_origin_ref`，新规划 Review 还须绑定实际部分代码和 Tasks 状态。新 BL 的发布不得夹带尚未获准集成的 Feature 代码。
3. 在原 RC 追加 `rc-aligned`。`context_ref` 指向上述固定快照，快照选 current，且 `control_revision` 等于本次事件的 `based_on_control`；`object_ids` 只列已审影响清单中实际对齐的对象，`review` 为工程负责人的具名决定。一个候选的证明不能替另一个候选消除影响。完整清单尚未由当前局部证明及确切历史保留证明覆盖时，RC 总体仍为 approved。
4. 沿前述 `--view changes --event-ref` 预检、发布及独立确认。局部检查会重新检查 BL、来源保护、工程输入与适用规划；为避免等待环，它不要求先解除 hold 或已满足实施依赖。输出始终不授权执行。
5. 在原记录追加独立 `unhold`，`alignment_refs` 精确引用已发布 `rc-aligned` 所在文件的提交、路径和摘要，只选择原 hold 中对应的对象/入口。未 Propose 的分配对齐仅支持恢复 Propose；已审完整规划才可能支持恢复 Apply。不能仅列少数受影响对象就解除整个候选；解除 Version/line 范围时，所引用的同入口局部证明，加显式引用的历史保留证明（若适用），必须合计覆盖完整影响清单；当前入口的局部证明不能缺席。候选带有 Version 别名不代表已核对其他对象，另一个 RC 的 hold 也不会一起消失。
6. 发布解除后重新获取最新控制快照，再运行完整 G2 和既有工程入口。Apply 仍需与新 BL/规划相符的独立实施请求；恢复原 Apply 时保留首次准入和实际进度。依赖未就绪、另有 hold、请求过期或输入变化仍须停止。上述分配/规划证明不能解除 Merge/Release，也不表示代码整改已经 verified。

无影响沿用旧规划需要当前工程适用性审阅：在原 BL 中重读旧 map/Trace，再比较当前候选的 R/AC、相关层级/约束及实际工程差异。无关需求变化不自动推翻旧规划，候选义务或相关约束改变则回整组 Update/Review；不得全局忽略 Trace 的 BL 字段。整项取消按下文处理，不能为退出而重新释放已取消候选；纯上游关闭按下文核对实际工程边界和保留义务。两个实际候选的整版/整线 Propose 恢复已有隔离验证；恢复其他入口仍分别需要相应阶段证据。

## 整改后的合并恢复与处置确认

本节适用于已有 Standard Change 的隔离试用；角色审阅、实际命令执行及发布操作仍由既有阶段承担。

1. 按新批准的整组规划和当前请求完成 Apply、真实测试及 Review。继续沿 [S6](s6-delivery.md) 执行 G3/pre-archive、分支内 Archive、最终检查和合并审阅，保留原 Apply 与预占。Merge hold 不等于禁止在已恢复的 Apply 范围内整改。
2. 准备当前 `G3/pre-merge/change:<实际名称>` 快照，固定新 BL、原准入、实际归档、最终运行、Review 和具体合并请求。将该快照作为 `rc-aligned.context_ref`，指定本 Change 实际承担的影响对象，由工程负责人审查局部合并条件。
3. 预检内部复用合并前检查，仅为验证这份局部证明暂不要求 Merge 已解除；Apply 限制、真实工程证据和其他合并条件仍须成立。结果明确不授权合并，没有可由调用者开启的公共 Gate 绕过开关。发布证明后，再引用它解除本 RC 对这些对象的 Merge hold。
4. 重新观察目标线和 control，更新当前快照及其中各历史 BL 的当前观察。固定批准、原发布观察和历史运行引用不改。完整 G3/pre-merge 必须通过后才执行已授权合并；旧快照、另一 RC 的 hold 或工程变化仍阻断。
5. 实际合并后沿 S6 保存集成观察，运行 current G3/integrated，再预检并发布原名额的 `slot-release`。只有发布确认后名额才释放；集成记录和历史归档保留。
6. 在最新控制观察下保存实际 current G3/integrated 的原始输入与完整输出，作为 `context_ref / result_ref`；该快照不包含 `slot_release_ref`，其 `control_revision` 须等于本次 `rc-verified` 的 `based_on_control`。名额发布改变了控制提交，因此需要在发布后的控制上取得这份独立整合证明；带释放确认的结果不能直接复用，删除已保存快照的字段也不能代替实际查询。使用既有 `trace/evidence/`，保留原始结果并区分被测提交与后来保存证据的提交，不重复发布名额。追加 `rc-verified`，`reviews` 分别由工程和 QA 负责人绑定处置与复验依据。先预检，再发布并独立确认。

检查器重放完整集成事实，不信任手填 PASS；原名额仍占用、本 RC 对该对象的 Propose/Apply/Merge 限制未解除、证明属于另一候选或影响对象缺失，都不能关闭相应处置。另一个 RC 的 hold 原样保留，Release 限制也不由本步骤解除。多个对象逐次验证，已登记的局部证明不等于 RC 总体 verified；失败时从真实未完成步骤接续，不重开旧 Change 或重复合并。

## 已集成行为的退役

这条路径用于实际进入目标线的行为。已发布的产品历史保持不变，后续变更进入新的维护/产品版本；当前未发布版本内的退役仍先完成 RC 和新 BL。

1. 保留原 BL、实际集成提交、旧 Change 归档和测试。产品明确撤下行为后，新建可验收的退役 R；其 `retires` 固定旧 Version、BL、R 文件和原配置，写明原因与具名决定。当前 scope 排除旧义务并固定同一 predecessor，纳入新的退役义务；不能只改 scope。
2. 用实际运行入口和打包方式明确残留检查：入口、权限、专用代码/资源、持久数据与下游消费者中哪些适用。保留数据、迁移或删除需要真实产品决定；不适用项说明依据，不把样本中的“无数据”当成项目默认值。完成 S2/S3 Review 和新 G1。
3. 释放承担退役的候选，建立新 Standard Change，引用旧归档。按新义务写 Spec/Tasks 和 Trace，分阶段保存局部对齐证明、解除对应 hold，再执行完整 G2；旧已集成 Change 不重新打开，原记录不改写。
4. 经过当前请求执行实际清理、残留测试、Review、Archive、最终检查与合并。新 E 证明目标线已不再提供被撤下行为；旧正向测试只能证明过去的功能，不能替代退役验证。清理前失败和清理后通过分别留存。
5. 按上一节确认当前 G3 和原名额释放，再提交具名工程/QA 的 `rc-verified`。检查器只将完整交付的退役 R 与明确移出的同线原义务关联：确切 BL/记录/配置必须一致，退役 R 的全部 AC 须有实际集成覆盖。部分覆盖、另一候选的证据、任意历史链接或未明确移出均不足以确认旧义务已处置。

这里的旧 R/AC 是退役责任的追踪对象，不会重新加入当前交付分母，不授予旧义务的 Apply 权限，也不把原功能记为新版本成功交付。版本仍须经过最终组合验收；多个候选分担的退役不能凭其中一份局部 PASS 确认整体撤除。

## 已归档未合并时收到需求变更

先核对实际目标线：若行为已经通过普通合并、squash 或移植进入目标线，按已集成行为处置；仅分支内 Archive 的交付才使用本节。保存原归档提交/观察、主 Spec、Trace、E 与真实交付状态，新产品口径仍先走 RC、三方决定和新有效 BL。

**继续交付或只缩减部分贡献：**

1. 在原交付分支恢复同一活动 Change，保留旧归档的固定提交和原名额。先恢复再执行行为修改，不能直接在 archive 中改 Tasks 或编码，也不能为同轮小修绕过到 Tiny。
2. 核对上次 Sync 后的实际主 Spec，再 Update 整组规划和受影响 Tasks。原 Delta 未必仍适用于当前主 Spec，不能机械重复首次新增操作。保留正确内容，重开确需返修的任务；局部取消另按下一节撤出贡献。
3. 当前 Trace 对齐新 BL、原 dispatch 的最新对齐和真实活动规划观察；旧 Trace/归档观察保留为历史。当前这轮不能继续携带旧 `delivery.archive_observation_ref` 冒充已归档。审阅后发布局部对齐、指定入口解除，并用当前请求通过完整 G2 才开始 Apply。
4. 完成实际修正和测试，保存新的不可变 E；旧 E 的 ID、字节和受检提交不改写。沿 [S6](s6-delivery.md#同一-trace-的归档后交付引用)再次执行 G3/pre-archive、独立 Archive、最终检查和本节前文的 Merge 恢复/完整 G3。归档落点可能相同，原归档仍由确切历史提交定位。
5. 实际集成、原名额释放和 RC 处置逐项确认；旧归档或旧测试通过不能替代这次交付。

**整项取消且目标线尚未接受行为：** 沿后文独占取消协议停止原交付、清理未集成代码/配置/资源并保留可恢复提交。已存在的归档是历史，cleanup 中保留其原文件集合与字节，不删除重建、不改写 Tasks，也不为取消再次运行 Archive。名额通过取消形式退出，旧 Archive 不会使该候选进入成功集成集合。处置其他保留需求后才能关闭整个 RC；共享 Change 仍有贡献时使用上一种继续交付路径。

## 共享 Change 只取消部分贡献

起点：同一活动 Change 承担多项 R/AC，其中部分贡献经 RC 决定退出当前版本，剩余贡献仍需交付。保留原候选、Change、首次 Apply 与名额；不把整个候选标为 cancelled，也不提前发布取消形式的 `slot-release`。

1. 保留实际停点的规划、代码和资源。在新有效 BL 中明确退出的 R/AC，更新同一候选的分配和验证计划，检查剩余义务完整。原输入、旧 BL、旧分配和实际进度保留在固定 Git 引用中。
2. 在同一 Change 执行 Update，撤出被取消贡献的当前 Spec/Tasks/Trace 关联，保留正确工程内容。取消的 Task 从当前必做清单撤出，不能勾成完成；用旧提交及 RC 说明它原先的内容和真实进度。对剩余完整规划进行 Review。
3. 按前文发布新 BL 的 `execution-alignment` 和实际规划的 `rc-aligned`。影响清单中的已撤销 R/AC 仍须处置，不能因它们已退出新 map 而漏记。检查器只允许本预占已发布历史中、当前有效 scope 已不再要求、且本 RC 明确 `remove / replace` 的旧 R/AC 加入该证明；仍在 scope 中而只是转给另一候选的义务不能借此关闭。旧对象仅作为处置责任，不回到交付覆盖或依赖满足集合。
4. 指定入口解除、当前实施请求及完整 G2 成立后，继续 Apply，清理取消贡献的代码、配置和资源。共享文件只改受影响部分；用真实测试检查剩余行为及适用残留。保留功能的旧测试继续有效，被取消功能的测试则随受审契约调整，不能只删测试而留下旧行为。
5. 沿上一节完成同一 Change 的 G3、归档、合并和成功交付名额释放，再用 Standard 形式的 `rc-verified` 核对本候选承担的处置。剩余贡献计入真实交付，被取消贡献只记录撤除；只有全影响清单都已有适用证据时 RC 才关闭。部分失败仍保留原名额和未解除的 hold，从实际停点恢复。

## 独占未集成工作的取消

本节用于一项预占对应的交付整体退出，且实际目标线上尚未接受其行为。共享 Change 仍欠其他贡献时，须保留名额并走 Update/Apply；已经进入目标线的行为须经过新的退役交付。仅关闭 PR、改候选 disposition 或移出 scope 都不够。

1. 按前文完成 RC 影响审查、三方决定、新 BL 和 G1/effective。当前 map 将该候选明确记为 `cancelled`，重拆时为 `superseded` 并完整安排替代贡献。保留原 ID、分配和已关联 Change 名称；剩余需求仍有完整验证责任。RC 对该候选的 action 明确为 `remove` 或 `replace`。
2. 发布 hold 并让执行者在真实安全点停止，将所有未提交规划、代码、测试及资产先保存在可恢复提交中。`stop-acknowledgement.actual_revision` 指向该提交，确认对应候选/Change 的 Propose 或 Apply 停点；保留 Merge 限制和原名额。提交必须持久 pin 并可从权威仓库取回，不能只有临时工作区。
3. 记录实际 PR/交付状态为 `not-opened / closed / withdrawn` 及具名证据。审阅后撤出该 Change 的活动规划，清理独占的未集成工程变化，形成后续 cleanup 提交；保留原工作和 cleanup 的 Git 祖先关系。不得把未完成 Tasks 勾成完成，或调用 Archive 制造成功交付。检查器不执行删除、重置、关闭 PR 或发布。
4. 准备 `cancellation` 正文：`context_ref` 为当前新 BL 的 G1/effective 快照；`rc_ref` 为该 RC 最新已发布生命周期事件；另含 `retained_revision / cleanup_revision / stop_refs / delivery_stopped`。`delivery_stopped` 包含上述 `state / evidence_ref`，停止引用必须已发布。快照中的控制提交与拟发布事件的 `based_on_control` 相同。
5. 工程和 QA 审阅目标线、原工作、清理结果、剩余义务及适用残留。用公共库的 `digest(canonical_bytes(body))` 计算正文摘要，body 排除 `reviews / input_digest`；将摘要放入 `input_digest`，两份具名审阅的实际证据正文都明确包含该摘要，再填 `reviews`。这样改停点、提交或处置输入会使原审阅失效。路径字节检查不能识别所有改名复制、外部数据或已部署行为，责任人仍须检查真实影响；有疑问先停止取消。
6. 在原 `dispatch/C-NNN.yaml` 追加 `slot-release`：保留原 `candidate_id / baseline_ref / reservation_ref / dispatch_ref / confirmation`，使用 `outcome: cancelled / cancellation`，不填集成结果。`baseline_ref` 保留原预占的基线，新的批准基线由 cancellation 快照固定；不能伪造一次针对已取消候选的新准入。
7. 沿前述 `--view changes --event-ref` 先预检再串行发布并独立确认。预检通过仍占额，发布后才移出在制集合；生成视图中的 `cancelled_reservations` 列出确切退出证明。它是原控制历史的只读投影，不是第二份可编辑状态，也不会进入成功交付集合或满足依赖。
8. 发布确认后，在原 RC 追加取消形式的 `rc-verified`，固定最新控制下的 G1/effective、确切 `slot_release_ref`、本候选承担的 `object_ids` 和工程/QA 审阅。原 hold 保留。还有其他对象、来源解释或保留需求待处置时，RC 总体继续未完成；取消一项不能关闭整张影响清单。

缺实际停止、留存 pin、清理、审阅绑定或新有效基线时，名额仍占用。若目标线在本交付触及的工程路径上已有变化，检查器保守拒绝：先辨明已集成行为与无关重叠，不能自动断言必须删掉别人工作，也不能跳过检查。已有归档属于历史，取消不得新增或重写；已归档未合并的整项取消另有独立场景，保留原归档字节；共享取消按前文单独处理，不能从本节的独占取消场景推断。

## 尚未进入工程的上游处置

适用情形：需求的来源、范围、验收条件或粗分配已完成本次变更审查，但相关候选尚未 Propose；已经存在的工程对象则须先用前文的实际整改或取消证明完成处置。RC 关闭只表示这次变化已经处理，保留候选的功能、测试和版本验收义务仍须继续交付。

1. 完成原 RC 的全影响审查、三方决定及新 G1/effective。核对剩余 R/AC、贡献和验证责任完整；保留原输入与历史，不为上游审阅生成空 Change、Tasks 或运行 PASS。
2. 从已发布控制和旧新影响清单核对真实工程状态。未释放候选保持未释放；已预占但尚未 Propose 的保留候选先追加针对新 BL 的 `execution-alignment`，继续占原名额；关闭检查还会复用局部 G2 核对该预占的实际分配和工程 Review，只有 BL 引用相同并不够。整项取消且已有预占的候选先完成实际停止、取消释放及取消形式的 `rc-verified`。已有 Change/Trace/Task/实现或外部能力不能直接用上游证明关闭。
3. 准备当前新 BL 的固定 G1/effective 快照。G1 快照保留批准内容和有效发布语境；另存的 G2 工程 Review/快照不能冒充 G1 元数据。未验证的目标代码变化或夹带的部分工程代码会阻断本路径，应回实际工程处置。
4. 追加 `rc-verified`，正文为 `rc_id / previous_ref / context_ref / object_ids / outcome: upstream / input_digest / reviews`。`object_ids` 来自原影响清单；按前述摘要方法排除 `reviews / input_digest` 后计算完整正文摘要，工程和 QA 两份审阅证据都明确绑定该摘要，说明实际处置与未来保留义务。事件的 `evidence_ref` 引用 QA 审阅。不填写假的 G3 `result_ref`。
5. 经报告入口预检、发布并独立确认。所有必要对象都有证明后，RC 总体才为 `verified`；返回的 `delivered: false`、`engineering_permission: false` 表示没有交付或执行许可。原名额和 hold 不自动改变，后续仍走实际 G2/G3 和版本验收。

已关闭 RC 仍可能保留 Apply/Merge 等尚未具备恢复依据的 hold。以后在实际阶段具备条件时，可按下节追加局部恢复证明；不能因 RC 已关闭而放行所有入口，也不需要伪造一份新需求变更来解除原限制。

## 终态决定后的入口恢复

先发布具名 rejected/withdrawn 决定，保留 hold 和原名额。按真实停点准备原有效 BL 下的 G2/dispatch、G2/planning 或 G3/pre-merge 快照，在原 RC 追加 `rc-restored` 并完成工程审查。该事件仍保留 rejected/withdrawn 状态，不建立新的产品批准。确切恢复证明发布后，才按上文解除其支持的指定入口，再运行完整 Gate 和原工程授权检查。

不能用拒绝决定本身、任意附件或另一个对象的证明清空 hold。未 Propose 的局部证明只支持恢复 Propose；恢复 Apply 或 Merge 仍分别需要实际规划或完成的工程处置。多个候选/广域恢复及取消路径须以对应完整验收范围为准。

对已经 `verified` 的 RC，同样可追加 `rc-restored`，但恢复依据使用该 RC 的已批准后继 BL（或经过完整有效前驱链的当前 BL），不得退回被替代的原 BL。引用当前实际 G2/dispatch、G2/planning 或 G3/pre-merge，仍按对应阶段限制可恢复的入口；发布后 RC 保持 `verified`，原验证、剩余名额和未选择的 hold 保留。新的产品变化另建 RC，不通过恢复事件改写终态决定。

## 中断与交接

保存两份快照、RC 原记录和已发布引用、输出摘要、未映射差异、尚待回答的 Q、实际停点和新旧 BL。重启后先比对确切提交及远端当前状态；输出可从原输入重建，不重新编号或覆盖原稿。批准、新 BL 确认、对象对齐、入口解除及实际验证分别接续，不能把未确认的发布写成生效，也不能用局部对齐替代完整 RC 处置。遇到未支持的阶段或缺少证据时保留原名额和停止状态。
