# S6 实施与交付接续

[共同约束](README.md) · [前置：实际规划](s5-planning.md)

当前开放实际工作区的**初次 G2/apply 及基于原准入的恢复检查**，包括批准在明确无影响变化下的沿用，以及实施后的受审规划修订；行为实施仍由既有 Apply/TDD 执行。另提供下文的 **G3/pre-archive 归档前检查及 Standard 的 G3/pre-merge、G3/integrated 检查**。已有能力／外部交付直接进入[无 Change 的交付核对](#无-change-的交付核对)。项目规则通过下文任务边界接入这些检查，当前限声明范围内的隔离试用；Tiny 按下文任务／PR 路径接续；全部义务交付后进入 [S7 整版验收](s7-completion.md)，单项交付不代表 Version Completion。

## 无 Change 的交付核对

适用于有效 BL 中所选 AC 的全部贡献都由当前 delivery-map 的已有／外部端点承担。R 整体标为 `already-satisfied` 或 `external-deliverable` 时，仍须逐项核对实际贡献和证据；R 标为 `change` 时，也允许只核对其中完全由端点承担的 AC，其余候选义务继续等待实际交付。所选 AC 只要仍含候选贡献，就不能使用此路径，也不能因尚未创建 Change 而绕过它。一个版本包含多种交付路径时，选择本次已交付的 R／AC；`scope:<Version>` 要求其中所有纳入义务均符合此路径。

在业务项目中按以下顺序操作：

1. 取回当前目标线和控制引用，沿用 S4 的有效 BL、原发布观察及固定 R/AC。已有能力引用当前 `openspec/specs/` 主 Spec 和实现；外部交付保留责任人、固定契约和当前线的交付依据，`port-planned` 不代表已交付。
2. 对实际目标提交运行适用测试／验收，把原始结果保存为不可改写的 E；失败、零匹配、跳过、错误目标或环境不得标成通过。代码、测试定义、契约和配置作为实际运行输入固定。外部服务应固定本次目标线采用的契约／环境，不能只提供预计交付日期。
3. 在现有 delivery-map 端点的 `availability_refs` 和 verification-plan 对应义务的 `evidence_refs` 引用这些 E。贡献与 R/configuration/AC 的对应关系仍由 map 与 E 保存，不另建 C Trace 或验收状态文件。保存 map/plan 后，在同一 `reviews/engineering.yaml` 审阅当前上下文，并增加 `scope-delivery` 检查：核对每个所选 AC、提供方契约、实际实现和测试／验收的含义、层级、方法及环境。该检查与其他工程检查绑定同一完整输入摘要。
4. 编写 current `G3/integrated` 快照，填真实 `head_revision / metadata_revision / target_revision / control_revision`、原 `baseline_ref` 和发布观察；`engineering_inputs` 选择已保存的 map、plan、工程 Review，`verification_inputs` 明确每个 E 的受检提交和五类执行身份。引用集合必须与所选义务实际使用的 E 一致。新元数据保存后重新固定引用并留存，不把元数据提交冒称受检目标。

```bash
# 在业务项目根目录执行；快照和输出保存在项目外的本次检查目录。
bash scripts/requirements-check --root "$PWD" \
  --gate G3 --phase integrated --subject 'scope:v1.0.0/R-001/AC-01' \
  --context '<本次 current 快照的绝对路径>' --format json
```

`subject` 也可选 `scope:v1.0.0/R-001` 或 `scope:v1.0.0`。该路径不填 `dispatch_ref / trace_ref / apply_origin_ref / apply_request_ref`、Archive、合并或名额释放输入，也不先运行空的 pre-archive/pre-merge。

通过标志是退出 0，`delivery.acceptance` 列出所选 AC 的实际贡献和验证关联；它是本次查询结果，不回写 Requirement 状态。`deferred_obligations` 明确保留 completion/release 时才到期的义务，即使已有局部证据也不宣布整版验收完成。`current_holds` 原样保留所选 Version/R/AC/线上的限制；交付事实成立不解除 hold、不授予后续 Apply/Merge/Release。

缺契约／实现引用、覆盖不全或检查失败时，补真实证据并重新审阅；工程目标改变后重新判断并提供适用的当前测试。只更新 E 标签或 subject 不能恢复通过。旧 E、BL 和原失败保留。需要修改需求时回既有问题／变更出口；需要实际工程修改时先按 Tiny/Standard 分流，不能在这个只读核对中顺带实施。Tiny 的具体输入和失败出口见下节。

## Tiny 任务／PR 的交付核对

本路径适用于已经按项目 Tiny/Standard 规则选定的独立任务。显式 Tiny 仍须满足业务契约、公共接口、数据格式、权限和部署等通用边界；自动 Tiny 还须命中项目白名单。路径依据保存在原任务／PR 中，由工程审阅核对实际 diff、历史和检查。工具不能从文件扩展名、修改行数或 `task:` 字符串推断这些语义条件。

尚未合并的 Standard Change 继续原返修流程。Tiny 检查会拒绝本次未合并历史中对 `openspec/changes/` 的改动，包括创建后又删除的 Artifact；已经交付的旧归档保留不动。关联 AC 若仍有未完成的候选贡献，不能借 Tiny 绕过候选交付。

### 实施和关联

1. 沿既有任务／PR 保存目标、实际路径选择、实施授权和验收方法。开始／恢复实施及收到控制变化通知时，读取最新共享控制，按当前线、Version、任务／PR、关联 R/AC 及其候选／Change 核对 Apply 限制；使用下述安装库的只读接口。遇 hold 沿本页的停止确认与解除协议接续。Tiny 不使用虚构的 G2/Apply 准入或 Feature Tasks。
2. 在现有 `trace/evidence/` 保存 `tiny_association` JSON。它仅关联已经存在的原任务、项目规则、主 Spec 和 R/AC，不复制任务正文、勾选状态，也不成为另一份任务清单。固定引用前先提交并留存实际文件。任务来自外部平台时，保留可核对的原始记录及平台身份。
3. 按原任务和方法政策实施，执行适用检查。涉及既定业务行为的修复，使用不变的当前主 Spec，保存实际回归 E 及完整输入、用例和 AC 贡献映射。纯技术／文字任务可以不关联 R/AC，但仍须有真实任务、检查和最终审阅，不凭空新增业务需求。补证保留原始运行的受检提交，不把证据保存提交重新标成已测试提交。

开始／恢复时使用安装库的 [`check_boundary(store, snapshot, action=...)`](../lib/tiny_delivery.py)，完整调用与 UI 输入见[任务边界](../../ui-design/requirements.md#tiny-开始与恢复)。它从当前 map 和原任务关联推导控制对象，核对真实 target/control、工程 Review、当前 UI 及未完成 Standard 历史。保存精确命令和完整结果，current 查询通过仍不代替原实施授权。底层 [`read_delivery_control`](../lib/control_delivery.py) 可用于独立查询 hold；仅查询任务名不能替代完整边界核查。

关联记录使用以下字段；所有引用均为已保存文件的完整 `commit / path / sha256`：

| 字段 | 内容 |
| --- | --- |
| `schema_version / subject / version / delivery_line / baseline_ref` | `vr/1`、真实 `task:<ID>` 或 `pr:<ID>`、所在 Version/目标线及有效 BL |
| `task_ref` | 原任务／PR 的固定记录，含路径依据和实际授权来源 |
| `selection / policy_refs` | `user-explicit` 或 `project-policy`；必须包含实际项目 `AGENTS.md`，按需包含其他适用规则 |
| `spec_refs` | 适用的 `openspec/specs/` 主 Spec；关联业务 AC 的修复不得为空 |
| `requirements` | 本任务影响的 `requirement` 与 `acceptance` 数组；纯技术任务允许空数组 |
| `ui_behaviors` | 采用UI时显式填写所选行为；含关联业务UI的准确R/revision/AC，纯技术UI使用原任务行为；不适用时明确空数组 |

### 合并前

保留工程 Review 对**实际目标线**的绑定；分支修复及其测试由最终交付 Review 审阅，不把尚未合并的修复提交冒充当前目标。准备 current `G3/pre-merge` 快照，复用原有效 BL/发布观察，填写真实 head、metadata、target、control，并增加：

- `tiny_ref`：上述关联记录的固定引用。
- `engineering_inputs`：当前受审 map、验证计划和工程 Review。
- `verification_inputs`：实际业务回归 E 的受检提交及执行身份；不关联业务 AC 时按真实检查情况提供。
- `final_checks_ref`：复用下文最终命令观察；以 `subject` 标识任务／PR，省略 `change`。保留项目检查、入口 `--check` 和两项 OpenSpec 校验，完整绑定受检工程文件。
- `merge_request_ref`：复用下文合并请求，使用 `subject / tiny_ref`，省略 `change / reservation_ref / dispatch_ref`；仍固定真实最终 Review、检查、候选提交、目标及整合者授权。

最终 Review 保存在现有 `reviews/merge/`，以 `tiny_review_key(subject)` 生成文件名，例如 `task:duration-fraction` 对应 `task-duration-fraction.yaml`。复用 `delivery` Review，检查项为 `tiny-path / task-scope / diff-and-history / project-checks / verification-coverage / integration-conditions / merge-scope`，绑定关联记录、BL、规则／主 Spec、当前工程输入、E 和实际最终命令输入／结果；到期依赖评估放入 contextual 引用。可用已安装 `tiny_delivery.review_inputs(...)` 组装确切引用，并沿原 `review_input_digest(...)` 计算绑定；这些函数不生成审阅决定。它不代替原任务或产品批准。

```bash
# 在业务项目根目录执行；使用本次确切 current 快照。
bash scripts/requirements-check --root "$PWD" \
  --gate G3 --phase pre-merge --subject 'task:duration-fraction' \
  --context '<本次合并前快照的绝对路径>' --format json
```

只有退出 0 且 `merge_ready: true` 才表示本次合并前条件成立。保存原快照和完整输出后，由整合者依现有协议执行实际 Merge。没有 Archive、预占或名额释放；不得填入空 Change/Trace、Apply 原点或归档记录。历史查询的 `merge_ready` 为 false。

### 合并后

保存同一种 `integration_observation`：原合并前快照和完整结果、真实源提交／合并提交／合并方式、原操作证据及整合确认。新 current `G3/integrated` 快照沿用 `tiny_ref`，以 `integration_observation_ref` 直接选择实际观察；移除合并前的 `final_checks_ref / merge_request_ref`，将工程 Review、map/plan 和实际 E 更新到当前线。复用 `reviews/integration/<tiny_review_key>.yaml`，在同类检查上绑定实际合并和原准入依据。

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G3 --phase integrated --subject 'task:duration-fraction' \
  --context '<本次合并后快照的绝对路径>' --format json
```

检查器复算原合并前准入并核对实际 Git 历史。工程内容变化时，补当前适用的回归 E 和 `integration_checks_ref`，不能沿用错误目标上的绿色结果。通过后 `current_integration: true` 仅表示本任务实际交付事实；关联 AC 仍保留整版 completion/release 义务，当前 hold 继续列出，不自动解除或授予下一步行动。

缺原任务、原准入、有效 Review 或实际合并证据时，停止在具体缺件处，从 Git/留存恢复对应对象。重复只读检查不创建新任务、Change 或发布事件；也不能把结果不明当作已经合并。语义边界失效时，保留已有工作，按原路径裁决和必要的 Standard 规划接续，不通过更换 subject 消除冲突。

## 保存真实实施请求

规划 Review 确认实际工程方案后，取得针对该规划的实施请求。原 BL 批准、释放决定、Propose 请求或 planning PASS 均不能代替它。兼任角色仍记录真实职责；使用 synthetic 决定时明确标注，不当成产品或用户签名。

既有明确授权在仍覆盖当前方案和任务时持续有效；保存或更新绑定记录不意味着每次检查都要重新询问用户。记录实际授权来源及适用范围，缺少授权或超出原范围才停下取得决定，不能补造一次同意。

在 `requirements/versions/<Version>/trace/evidence/<本次请求>.json` 保存 `apply_request` 模型，固定保存后再引用；不能为每次查询覆盖旧请求或改写其原证据。

| 字段 | 绑定范围 |
| --- | --- |
| `candidate_id / version / delivery_line / baseline_ref` | 当前候选和原有效 BL，不以同名 Change 猜版本 |
| `reservation_ref` | 最初已发布的预占引用；对齐沿用它，不新领名额 |
| `planning_review_ref / planning_digest` | 实际适用的规划 Review 及受审内容摘要；引用请求所针对的已存在 Review |
| `planning_snapshot_ref` | 实施后修订时，固定引用该次 Update 通过 G2/planning 的原始输入快照；与同一最初 Apply 原点绑定。初次或未修订的原方案不必提供 |
| `task_ids` | 本请求覆盖的实际显示 Task 编号；允许明确子集，不复制任务正文或勾选状态 |
| `decision` | 工程负责人职责下的真实请求、时间、原始依据；不能把原释放/Propose 的同一固定证据重新标成后续实施请求 |

请求引用的 Review 必须与当前适用 Review 为同一份内容，并能取回其确切原引用。请求元数据允许在独立留存分支保存或经过 squash；不要求两个元数据提交具有 Git 祖先关系，也不把 Git 拓扑当作决定的时间或授权依据。不能把后保存证据的提交写成原批准时间或受检代码提交。原请求在当前 metadata/head 必须仍为相同字节；新请求保留原记录与历史。

## 初次 Apply 前检查

沿 S5 取回原 BL、实际 Trace/Review、最新工程目标和控制历史。若工程输入改变，先按[规划适用性](s5-planning.md#工程输入变化后的批准适用性)处理。准备当前快照：沿用 candidate/BL/event/trace 身份，将 phase 改为 apply，增加完整 `apply_request_ref`；metadata/head 必须反映本轮实际已保存输入，不能传旧 head 隐藏本地改动。

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G2 --phase apply --subject candidate:v1.0.0/C-001 \
  --context '<snapshot.json>' --format json
```

current 通过时返回 `apply_permission: true` 和 `authorized_task_ids`，供已获授权的既有 Agent Apply 接续；检查器不写代码、启动 TDD、勾 Tasks 或发布。还必须满足：最新事件已经确认发布、mode 为 execution、到期实施硬前置满足、当前规划及原请求适用、所有对象的 Apply hold 已解除。新的 Propose 专属 hold 不等同于 Apply hold；归档前仍须消费 Apply 限制，不能借换入口绕过。

historical 只复算固定时点，始终返回 `apply_permission: false`。planning-only、未发布的对齐草稿、缺请求或请求范围/任务/批准不匹配均不能进入实施。预检无副作用；重复查询不再次占额，也不扩大任务授权。

## 实际工作区的恢复检查

首次 G2/apply 在实际 current 输入下通过后，将其原始输入快照固定留存到 `trace/evidence/`，后续快照增加完整 `apply_origin_ref`。它保存检查语境的引用，不记录第二份任务状态、恢复次数或授权决定；保留原快照，不能用一份 historical 结果或任意 PASS 字符串代替。始终引用最初的有效 Apply 快照，不递归串接恢复快照。

原准入按单一目标合同及原完整规则身份复核，不存在跨版本兼容路由。输入漂移时按S5重评工程Review、规划适用性及原预占上的对齐；只有实际无影响才沿用原规划批准和请求。不支持的身份停止接续，不能改写原准入、重建初始dispatch或切换historical取得实施许可。

当已有代码提交、未提交的实现变化或 Tasks 完成状态变化时，仍使用 G2/apply，并提供实际当前 metadata/head/target/control、请求与 Trace。检查器重新核对原首次准入的固定 BL、发布、规划及请求，然后消费当前预占和 Apply hold、当前 BL/Q/受审工程输入及实施前置。原名额、候选/Version/交付线不变；尚未完成的原始首次准入不能由恢复参数补成有效。

current 核对实际 HEAD 等于 `head_revision`，并读取工作区实际 Tasks；historical 只读取固定提交、不读取当前工作区，也不授予许可。勾选或重开不改变规划摘要，也不单独要求重新审阅规划。输出 `tasks_input`（基准提交及工作区输入摘要）；Tasks 含未提交状态变化时 `tasks_revision` 为 null，不能伪称该内容已在 head。`remaining_authorized_task_ids` 只是当前 Tasks 与实际请求的派生交集，不是新任务表。允许授权范围内的代码/测试继续演进，但不能借恢复当前 Change 新建或修改同一实际规划根下的其他 Change/归档目录；已在当前目标集成的其他 Change 保持完整。语义范围和真实行为结果仍需既有 TDD、实现审查与后续 G3 验证，不能把恢复 Gate 通过称为实现正确。

原目标、map、验证计划和工程 Review 未变，且规划内容/关联、Schema、原规划 Review 均未变时，保留原批准。上游或受审工程输入变化须提供当前完整的规划适用性判断；真正的规划调整按 [S5 实施后 Update](s5-planning.md#实施开始后的规划复核与-update)绑定实际代码/任务输入并整体审阅，适用请求再引用该次规划快照。Apply 的 `apply_origin_ref` 始终不变，当前 Apply 快照不携带仅供修订审阅使用的 `planning_inputs_ref`。Tasks 完成状态和下节规定的固定证据引用可以接续；其余正文仍受原规划绑定保护，不能把任意自由文本变化自动当作补证，也不能把补证本身解释为需要产品重新批准。

A 路线的实际 CLI 观察绑定完整 `package.json` 和 `package-lock.json`，它们同时参与规划摘要。因此，即使只按已批准 Tasks 新增 `npm test`，也会使旧观察失效并报告 `openspec.stale-observation`。先核对实际差异及授权范围，再沿上述实施后规划复核入口重新捕获 CLI 和当前执行输入、审阅完整方案、更新 Trace/规划 Review 及适用请求；原方案正文、R/AC、BL、已实现代码、原名额和首次 Apply 原点保留。不能只刷新旧批准摘要，也不因这类工程配置变化重新询问已经覆盖它的授权。未改变的目标/map/验证计划及工程 Review 沿用，不为刷新观察另造一次释放或对齐事件。

代码/测试的未提交变化可沿原有效准入接续，不要求每个 TDD 中间步骤提交。未提交的需求权威、规划正文/Schema、项目规则或需求工具改动会阻断；先保留并按其实际归属审阅/保存，再刷新快照，不能用忽略规则或旧 head 隐藏它们。冲突索引、submodule 或变化的执行符号链接尚不在支持范围。保留失败日志、已用恢复次数和真实停点；本检查不重置、代管或增加恢复次数。任务全部完成也不自动 Archive 或释放名额。

## 任务边界、暂停与恢复

采用需求层的项目将本检查点合入根 `AGENTS.md`；Claude 沿既有 `CLAUDE.md` 导入同一规则。原 v3 Apply/Update 已要求读取项目规则，本接续不增加另一份 Skill、任务循环或工作流适配器，也不改变 Explore／Verify 的显式调用政策。此处是 Agent 必须执行的操作；只读检查器核对实际输入，不是常驻进程，不能声称瞬间中断正在运行的命令。

首次或恢复 Apply、完成一个 Task 后准备开始下一个，以及失败修正后继续实施之前，按以下顺序执行：

新增固定引用后，先按项目的 `authority_remote / pin_namespace` 留存并回读核对所引用的每个确切提交。例如测试使用代码提交 C，后来在证据提交 D 的 Tasks 尾块引用 C，则 C 和 D 都须有对应的固定留存引用；只有 D 的引用、C 是 D 的祖先或本地能读到 C，均不满足 C 的留存检查。按实际新增引用补齐，不给所有历史提交机械建 pin；检查器报 `dispatch.retention` 时核对诊断列出的完整提交，保留原引用和失败，补齐留存后再运行 current 检查。

1. 从本次实际 Change/Trace 恢复候选、Version、交付线、原预占、首次 Apply 快照、当前请求和 Tasks；缺其中必需对象则报告具体缺口，不从聊天猜值或重新 Propose。有限恢复计数仍归当前 Task 的原记录，换会话或查询 Gate 不重置。
2. 由操作者按项目 `authority_remote / integration_ref / control_ref` 取回当前目标与控制对象，并确认必要固定对象/留存。不要把 fetch 写进只读检查器；取回失败停止。准备新的临时 current 快照，metadata/head 使用实际已保存输入，head 必须等于工作区 HEAD，target/control 使用当次远端观察。保留确切原点和请求；目标变化时先做 S5 的适用性评估，不能仅替换 SHA。
3. 执行上文 G2/apply 命令，保留本次原始 JSON 和退出码。退出 0 后逐项确认 gate/phase/subject、`evaluation_mode: current`、输入身份与本次请求一致；在 `G2.apply` 诊断的 evidence 中确认 `apply_permission: true`，且下一 Task 属于 `remaining_authorized_task_ids`。没有剩余 Task 时转交付核验，不另造任务。
4. 只有当前检查通过，才沿原 Apply 执行该 Task 和 TDD。无需每个读文件操作或 RED/GREEN 工具调用都重跑全 Gate；出现新控制通知、目标/规划变化、明确停止或恢复入口时立即处理，不等整轮 Apply 结束。Gate 在读入和返回前复核当前远端，但结果不占有后续锁；Archive/Merge 仍需其各自最后检查。
5. 退出 1 表示实际条件未满足，退出 2 表示输入/能力不可评估；两者均停止依赖实施。保留已有改动、未完成任务、原失败与已用恢复次数。`control.held` 按下文记录停点；stale-target/control 取回确切新事实后按影响接续；产品义务变化沿 [RC 处置](requirement-change.md)完成影响、新 BL 和逐对象对齐。对应入口已恢复且当前 G2/请求成立后才继续，不能改成 historical、删除边或放松 required 检查。

发现 hold 后，先停止新的受限写入；已获授权的日志保存及本任务进程安全收尾可继续。不能为了凑一次 GREEN 继续受限实施。将实际 head、未提交差异/工作区捕获、当前 Task、所见 hold 引用、失败/恢复次数和停止位置保存在本次 `trace/evidence/` 的固定证据中。整合者核对后沿原控制协议发布 `stop-acknowledgement`：`hold_refs` 是确切原事件，`target / entry` 是受影响对象/入口，`actual_revision` 是实际提交，`task_ref` 是当前 `<Change>/<Task>`（没有 Task 时为 null），事件 `evidence_ref` 指向上述停点证据。未提交状态由证据表达，不能把 head 冒称为完整工作区。

发布结果不明先按原 event_ref 查询，不重复造停点事件。ack 只记录实际停止，不腾出名额或解除限制。明确 unhold 发布后重新执行上述完整 current 检查；同对象存在其他 hold、原条件仍不满足或恢复次数已耗尽时继续停止。解除 hold 不能替代新的业务决定，也不能授权先前已失败的无限重试。实际停点和接续过程须由场景证据验证，不能只凭本段文字或控制解析单测声明通过。

暂停类事件复用同一 `event` 信封及[串行发布协议](s5-dispatch.md#串行发布控制事件)，不建立另一份暂停状态文件。payload 以已安装 `schemas/vr.schema.json` 为准：

| kind / payload | 必需内容与边界 |
| --- | --- |
| hold / hold_payload | targets、entries、reason、restore_conditions；多个 hold 独立叠加 |
| unhold / unhold_payload | hold_ref、targets、entries、alignment_refs、authorization_ref；只解除该 hold 中仍有效的指定对象/入口，先有适用对齐与授权，再重跑 Gate，不把被 hold 阻断的 PASS 当解除前提 |
| stop-acknowledgement / stop_payload | hold_refs、target、entry、actual_revision、task_ref；配合信封 evidence_ref 表达真实停点，不解除限制 |

入口为 propose/apply/merge/release；Archive 消费 Apply 限制。对象使用带类型身份，Version/候选/R/AC 的归属和交付线必须与事件一致；不能把 Version 级 hold 猜成某个 Task 的局部限制来解除。普通文档、Task 改名或某次绿色 CI 均不能解除 hold。

## 追加与纠正 Tasks 证据引用

完成状态与既定要求的实施／验证证据可以按原授权纠正；改变行为、范围、设计或验收要求时，沿原 Update 做整组修订和审阅。为使检查器确定地区分证据引用与规划正文，采用本需求层的项目约定：保留原 Tasks 正文字节，追加一个换行，再写唯一的文末 `harness-task-evidence` 代码块。再次补证修改这个尾块，Git 保留前次引用；不另建任务表，也不修改官方 Schema 或 CLI。

以下是 Markdown 示意，完整提交、路径和 SHA-256 必须替换为已经保存的真实文件引用；不要照抄占位值：

````markdown
```harness-task-evidence
{
  "schema_version": "vr/1",
  "entries": [
    {
      "task_id": "1.1",
      "refs": [
        {
          "commit": "<已存在的完整提交 SHA>",
          "path": "requirements/versions/v1.0.0/trace/verification/E-001.yaml",
          "sha256": "<该文件的完整 SHA-256>"
        }
      ]
    }
  ]
}
```
````

每个显示 Task ID 只出现一次、必须实际存在；refs 非空且引用字节可读取、摘要一致。引用可以指向既有 E、实际代码／测试定义或原始执行说明；详细解释写在其所属证据中，不在尾块添加描述、完成状态、通过结论或授权字段。失败／未完成记录也可作为过程引用，读取成功不改变原结果。保留正文原有换行；不完整、重复、非文末的尾块及任意附加字段都会被拒绝。

G2 返回的 `task_evidence` 仅为当前 Tasks 的引用导航，不证明业务已实现或测试通过，也不代替 Trace/E 的交付核验。未提交尾块按真实工作区读取；historical 只看固定提交。保存引用不会扩大实施请求、绕过 hold 或清除恢复次数；新增固定引用仍受同一留存检查约束。

既定要求的新增证据使用这个格式即可，无需仅因补证重签规划。修改受审任务正文、范围、方案、依赖或必要验收仍走 Update；没有采用本需求层的项目继续使用既有 Tasks 规则，不被此格式要求影响。原有自由文本不能仅凭“这是证据”的声明从规划摘要中排除。

## 保存未提交输入的运行证据

current Apply 返回的 `worktree` 是当次 `worktree-observation`：包含基准提交、路径/摘要和变化清单，`retained: false`。它没有保存差异文件，不是可供 E 引用的留存包。需要记录一次 dirty 测试时，用同一库的捕获工具保存真实输入；普通已提交测试沿用现有固定引用。

终端：已安装本模板及精确 venv 的业务仓库根目录。先在仓库外选一个父目录已存在、尚未创建的独立输出目录；`--include-root` 使用实际 locator 中的规划目录，以下路径仅为示例：

```bash
.harness/version-requirements-venv/bin/python -I -B \
  harness/version-requirements/lib/worktree.py --root "$PWD" \
  --output /private/tmp/vr-run-001-input \
  --include-root openspec
```

工具读取 Git 已跟踪及未忽略的未跟踪文件，并强制清点 `requirements/`；额外目录可重复指定，捕获其中被忽略的输入。需求的派生 views 不作为额外权威目录扫描。它不自动枚举被忽略的构建/依赖缓存，不代表已证明所有执行依赖完整；实际命令的构建、依赖、配置、环境和数据身份仍由 E 的 `identities` 及受审验证计划说明。只存链接文本、不跟随符号链接，不能把链接文本充当实际源码/测试定义。

按以下顺序保存一轮运行：

1. 捕获实际 HEAD、完整文件清单/摘要、相对基准的增删/模式变化及独立暂存状态。输出含 `worktree.json` 与内容寻址的 `blobs/`；暂存和工作区不同则分别留存。工具不写源文件、不更改索引或提交。
2. 运行已获授权的实际测试，原样保留命令、起止时间、报告和退出码；核对完成前将日志/报告保存在仓库外，避免新增输出改变受检输入。集成调用使用 `Worktree.assert_current(store)`，CLI 调用可在另一新目录再次捕获并比较 `worktree.json`。执行期间输入变化时保留失败证据，不能把该报告绑定为一次稳定输入的 PASS。
3. 测试结束后才把捕获包和原始报告/过程记录保存到本 Version 的 `trace/evidence/<run>/`。原过程的差异/捕获字节/报告引用可先记录路径和摘要，在它们实际保存的元数据提交中解析；随后 E 使用完整 commit/path/sha256。不把后续保存日志的提交当受检源码提交。
4. 保存元数据时仅提交明确证据路径。已有其他暂存内容时使用 `git commit --only ... -- <本次证据路径>` 并核对前后索引与源码，避免普通 commit 顺带提交 TDD 中间代码。E 再独立留存；新执行用新 E ID，原失败不覆盖。元数据提交改变实际 HEAD，后续 current Apply 须刷新实际快照及留存引用。

捕获输出目录已存在、位于源仓库内或路径经过符号链接时拒绝。写入中断留下登记文件和已完成字节；没有完整 `worktree.json` 不能消费，核对残件后另选新目录重试，不自动覆盖。捕获包是执行证据副本，其原始素材、派生素材、工程代码仍沿既有所有权管理；不新增 Requirement Asset 或当前任务状态来源。

读取 dirty E 时必须显式传入相同的 `worktree_diff_ref`；默认只查询提交证据的调用会拒绝它。实际输入的 `{path, content_ref}` 必须命中捕获的普通文件字节；基准 ref 不能隐藏已修改/删除文件，也不能重新标记原过程记录来冒用另一份工作区差异。G3 仍需核对最终实际提交与集成证据，此处不授予归档或合并许可。

## 在同一 Trace 中补齐交付引用

实际实现与核验发生后，在原 `trace/changes/C-NNN.yaml` 增加可选 `delivery`，使用 `delivery_trace` 模型。初始规划不要求它；不能在实施前填未来文件、测试结果或完成状态。内部只读关联检查由下节 G3/pre-archive 组合消费；归档、合并及名额释放仍是后续独立动作，不能凭关联检查自行执行。

| 字段 | 来源与保存规则 |
| --- | --- |
| `task_ref` | 实际 CLI locator 对应的 Tasks 固定引用；交付检查要求其任务正文、编号、完成状态与实际 head 相符，受限证据尾块可继续补充 |
| `implementations[].task_id / file_refs` | 每个实际 Task 对应的代码、测试或其他实施结果文件固定引用；纯验证 Task 可引用同一 Trace 选中的真实 E，不强造代码修改。需求记录与规划元数据不能代替结果，实际相关性由交付 Review 核对 |
| `verification[].obligation_id / verification_ref / case_ids` | 原 Trace 已关联的验证义务、真实 E 固定引用及其中的稳定用例 ID；同一义务/E 的用例合并为一行，多个义务可以引用同一次执行 |

先保存实际实现与已完成任务的状态，再运行适用检查、保存原过程/报告和不可变 E。纯验证 Task 在检查及必要审阅完成后才勾选，可引用这次 E；随后保存完成后的 Tasks，并补齐这份 Trace。代码提交 C 与后来保存证据或任务状态的 D 分别记录，不把 D 改写成已测试的 C，也不为提前勾选验证任务而重复执行同一检查。E 的输入清单按真实执行依赖填写，不把只用于交付导航的 Tasks 当作测试读取的文件；若实际命令确实读取了 Tasks，则其变动仍须按执行输入变化处理。

保存引用本身不触发规划重新批准；修改 `links` 中的 AC/Spec/Tasks/验证责任仍按原规划适用性与 Update 规则处理。交付引用不因此自动获得实现审查或业务验收。

内部 `check_delivery_trace` 复用已解析的当前 map、实际 CLI 观察和 `check_execution`。调用方另外提供 `delivery_verification_inputs`：每份被选 E 的固定引用、所需 `tested_revision` 与五项 `identities`，与 Trace 的 E 集合精确一致。这些期望必须来自当前受审工程语境；函数不能替调用方决定环境，也不将 E 的自报值自动当成当前值。

检查要求每个实际 Task 已完成且有当前实施文件引用；E 的 R 修订、原配置、贡献及 AC 与当前分配一致；被选用例真实通过并覆盖该候选的局部贡献。当前只接受已提交执行，dirty E 继续作为过程证据，不能冒充归档前提交证据。候选的一项局部贡献可能关联 completion/integration 验证责任，但局部通过不表示该义务已整体完成；其他候选的贡献、到期 hard 集成条件及最终组合验收分别由完整 Gate 核对，不能提前阻塞或伪报完成。

证据适用性比较真实测试提交到当前 head 的文件字节与模式。允许当前 C 的 Trace/交付 Review、本 Version 的 `trace/evidence/` 与 `trace/verification/` 元数据保存，以及不改变规划的 Tasks 状态/受限尾块变化。G3 另外从实际已发布控制历史识别同 Version/线的事件文件；保存或解除暂停本身不要求重跑未变的代码。仅将文件放进 `change-requests/` 不构成豁免，也不使草稿获得控制效力。被 E 明确列为执行输入或身份的文件仍逐个比较，即使它位于元数据目录；被选报告/过程/E 自身也须保持原引用字节。源包、需求派生资产、代码、测试、配置、规则及其他未分类变化均不在豁免内；新工程内容需要重新执行适用检查，不能仅凭祖先关系沿用旧 PASS。未引用的原始日志可以留存，但不会因此成为通过证据。

重复读取没有写入或新状态；保留过期 E 作为历史，另存新执行结果并更新引用。此内部检查返回局部关联，不返回 G3、Dependency Ready、完整义务完成或归档许可；G3/pre-archive 再组合准入、交付 Review 和到期条件。Agent 仍须执行项目规则规定的阶段与任务边界检查，不能从一次关联检查通过推断整个执行过程已遵守这些规则。

## 运行资源的导入与交付

适用于本轮实现确实需要加载 PRD 配置、设计素材或其转换结果的情况。只用于阅读的原型继续固定引用；无需给每条 Requirement 建立资源副本。应用资源进入项目既有资源目录，测试专用数据进入项目测试目录，构建缓存按项目规则再生成。

以配置文件为例，下面是职责和路径示意，不是 Harness 自动生成的一套目录：

| 对象 | 本例落点与关联 |
| --- | --- |
| 收到的原始配置 | `requirements/versions/v1.0.0/source/intake-001/config.json`，沿原 AST 身份保留 |
| 需要持久保存的设计转换结果 | 实际 Change 的 `assets/DAS-001/r1/duration.json`，登记制作输入及输出；直接采用原件时可省略 |
| 应用加载的资源 | `resources/duration.json`，由实现、打包和测试管理 |
| 导入过程 | 项目实际脚本及既有 `trace/evidence/` 中的执行记录，固定来源、脚本和输出引用 |

按以下顺序接续已有流程：

1. 在实际 Design/Tasks 中说明采用的固定素材、用途、必要转换、输出位置和验收方法。`asset_uses.used_in` 只关联规划 Artifact，不能拿它登记任意运行文件；修改已审方案时沿 Update 和规划 Review 接续。
2. 通过当前 G2/apply、持有覆盖本次操作的实施请求后，执行项目实际导入或构建步骤。保留原件及已登记 DAS；记录真实命令/脚本、工具版本、参数、退出码、日志、固定输入身份和输出摘要。手工制作如实保存作者、操作说明及核对依据。
3. 在同一 Trace 的 `delivery.implementations[].file_refs` 中，把对应 Task 关联到实际资源及相关脚本/代码。需要导入记录时放在既有 `trace/evidence/`，不再建立资源 registry；该记录不是代码实现的替代品。
4. 执行项目的实际构建和行为测试，把真正读取的资源、脚本、配置及必要来源核对材料纳入 E 的输入。测试若读取导入记录，也固定该记录。不要把未读取的全部 PRD 媒体列为运行输入；构建产物应能脱离活动 Change 和原始 PRD 包运行。交付 Review 的 `asset-lifecycle` 核对语义是否忠实、运行归属和来源关系，不能只比较摘要。
5. 缺失或错误资源导致运行失败时保留失败结果，修正实际资源及受影响方案后重新测试。资源在 PASS 后变化也须重新判断并执行适用检查；改写引用或摘要不能让旧 PASS 继续适用。
6. Archive/Sync 前核对主 Spec 的长期链接，指向稳定项目资源/文档位置或可恢复的固定对象。归档分别核对主 Spec 与归档目录的链接深度，保留原 DAS 身份及导入历史；按后文完成归档后实际检查、G3/pre-merge 和合并后核对。只读 Gate 不负责搬运、转码或打包资源。

可发给 Agent 的提示词；使用本轮实际文件和已有授权：

```text
按当前已审 Design 和 Tasks 处理本轮需要的资源。先核对 G2/apply 和固定素材来源，再执行项目实际导入/构建步骤；保留原始素材和制作记录。应用只能加载项目自己的运行资源。将 Task 关联到实际资源/脚本，运行适用测试并保存真实输入与结果；归档时核对主 Spec 的长期引用。若转换改变了获批规则或当前授权不足，停止依赖实施并报告具体问题。
```

## G3 归档前检查

当前开放 `G3 / pre-archive / change:<实际逻辑名>` 的只读检查。它复用同一 BL、预占、Trace 和 G2/apply 准入，要求实际 Tasks 完成、实现及 E 适用、交付 Review 通过，并核对本阶段到期条件。活动 Change 必须仍能由原 CLI locator 解析；不填尚不存在的归档提交、最终 CI 或 merged_commit。候选提供者的实际集成证明、已登记 Change 派生物和下文的归档观察已有对应工具检查，必需引用仍须完整提供；运行资源按上节实际导入和验证，素材引用通过不能代替实际构建。

按顺序准备：

1. 完成实际实现与适用测试，按上节顺序保存 Tasks、原始过程/报告、E 和同一 C Trace。保留失败记录；在功能分支提交已经授权的工作，不能把 dirty E 当最终提交证据。
2. 从当前 G2/apply 快照接续，保留原有效 `apply_origin_ref`、当前适用 `apply_request_ref`、原 BL 发布语境、已发布 `dispatch_ref` 和实际 `trace_ref`。将 gate/phase/subject 改为 G3/pre-archive/实际 Change 名；更新 metadata/head/target/control 及留存对象，不携带仅用于实施后规划审阅的 `planning_inputs_ref`。
3. 在快照增加 `verification_inputs`，结构沿 `delivery_verification_inputs`：每份选中 E 的完整固定引用、原真实 `tested_revision` 与 build/dependencies/configuration/environment/data 五项身份。E 集合与 Trace 精确一致；身份和所需受检提交来自本轮受审验证语境，不能直接照抄旧 E 声称适用。后保存证据或 Review 的提交不替换原测试提交。
4. 工程负责人结合实际代码、原始结果及验证责任组织交付审阅，保存 `reviews/delivery/C-NNN.yaml`，`phase: delivery`；沿同一 Review 模型和 `review_input_digest` 绑定输入。保存后再刷新 metadata/head 与留存；Review 不引用自身未来摘要。

交付 Review 的 `reviewed_inputs` 必须包括当前 Trace、原 CLI 观察的全部输入、实际 Tasks、每个 Task 的实施文件及选中 E。`context_refs` 绑定 BL、首次准入、当前请求、适用规划 Review、发布事件文件、当前 map/验证计划/工程 Review、事件原有上下文及五项执行身份；到期集成边另加入其 assessment 和提供方 contract。内部 `delivery_review_inputs(...)` 只计算这些已有引用，`due_integration(...)` 返回到期条件的补充引用；两者不生成审阅决定。完整集成条件的所有 E 仍从同一 Trace 选取。

Review 必需六项检查：

| check_id | 实际审查内容 |
| --- | --- |
| `implementation-scope` | 当前实现对应批准范围和 Tasks，保留无关工作 |
| `behavior-and-tests` | 行为及异常路径的实现、测试和原始运行结果成立 |
| `verification-coverage` | 用例与 R/AC/技术能力、验证环境和本轮义务的语义关联成立 |
| `asset-lifecycle` | 来源/派生/运行资源的使用和固定引用符合当前支持范围 |
| `integration-conditions` | 本阶段到期的提供方与消费方组合条件已满足；未到期项有明确归属 |
| `pre-archive` | 核对实际活动 Change、完整文件/任务及已知遗留项，具备接续既有归档前检查的条件 |

当前到期判断只消费受审 map 中 active、hard、`kind: integration` 且 `checkpoint: integration` 的边。implementation 前置由复用的 Apply 准入核对；merge/completion/release 检查点继续留到其实际阶段。到期已有/外部提供者须在真实 target 可用，当前 head 保留契约字节/模式；以 `edge_refs` 明确关联的每项验证义务都要有当前消费方实际执行、契约输入和所需组合覆盖。提供方单独通过、消费方局部通过或单一 available 结论均不足。未关联到期边的整版/最终验证责任不自动成为本 Change 的提前等待条件。

终端：已安装该版本工具、快照和留存均已准备的业务仓库根目录。替换实际 Change 名和快照路径：

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G3 --phase pre-archive \
  --subject change:v1-0-0-c001-configure-duration \
  --context /private/tmp/vr-prearchive-context.json --format json
```

退出 0 且诊断为 `G3.pre-archive` 表示当次检查通过；只有 current 的 `archive_ready` 为 true，historical 始终为 false。current 要求实际 HEAD 与快照一致、工作区没有待提交输入，检查结束前再次核对输入及最新远端。它继续消费 Apply 的暂停限制，包括该 Change 的 Task 限制；Task 改名或从当前列表消失也不会清除原已发布 hold。解除须走原控制协议，不能编辑 Task 或复用旧绿色结果绕过。

缺 Review/绑定/用例、未提交输入、代码或环境过期、到期前置不足时，保留具体诊断并修复其所属输入；需要重测则另存新 E，需修订规划则返回既有 Update。仅控制元数据变化仍要刷新快照并重新检查当前限制，不必重做未变代码的运行。通过不执行 Archive、不同步主 Spec、不合并或释放名额；实际 Archive 请求、完整文件/任务预检以及功能分支内独立归档提交按[下节的实际顺序](#保存与核对实际归档观察)执行。本阶段也不隐式调用 Explore／Verify。

## 保存与核对实际归档观察

内部只读 `archive.read_archive(store, reference, change=..., actual_revision=...)` 核对已经执行的 Archive 和完整文件移动，由下节 G3/pre-merge 组合消费。单独读取不替代最终 CI、Review、当前控制或合并授权，也不把“文件保留”当成 Change 自有派生资产的正式采用验收。

沿既有功能分支归档流程，保留以下实际顺序：

1. 保存当前完整实现、Tasks、适用核验与交付 Review，记录归档前真实提交；保留原 `planning_observation_ref`。原 CLI 观察仍指向当时活动 Change，不能在归档后伪造 `status` 或 `instructions apply` 输出。
2. 在本轮确有 Archive 请求且前置条件通过后，调用原 Archive 入口。现有 Skill 由 Agent 同步主 Spec 并执行目录移动；保留原 Skill、Sync 结论、实际 `mv` 输入/输出及退出码，不能补造 CLI Archive 输出。若选择既有终端路线，则使用包装器的 `archive <实际名> --yes --json`，保留原始 stdout/stderr/退出码，以输出中的 `archive.path / archivedAs` 定位。已同步且确认一致时可显式增加 `--skip-specs`，不得使用 `--no-validate` 绕过失败。两条路线共用后续提交/文件核对，不为接入检查器替换现有 Skill。
3. 检查活动目录已消失、全部文件/附件/Tasks 已保留，并分别检查归档 Markdown 与主 Spec 的相对链接。Archive 加深 Change 目录，Sync 则把 Delta 内容放到较浅的主 Spec；同一原链接可能需要两个不同的新相对路径。只修正指向同一资源的链接，保留正文、Task ID/完成状态及原固定证据；需要实质规划或行为返修时按既有恢复入口处理。
4. 将规格同步、归档移动及上述机械链接修正放在同一个独立归档提交 A，其唯一父提交是归档前提交。原始查询日志、观察记录、代码或无关文件不混入 A；在随后证据提交 D 保存实际观察，不能把 D 称为归档提交。

`trace/evidence/<归档运行>/observation.json` 使用 `openspec_archive_observation` 模型：

| 字段 | 实际来源 |
| --- | --- |
| `schema_version / change / project_root` | `vr/1`、同一逻辑 Change 名、执行时真实项目绝对路径 |
| `before_revision / archive_revision` | 归档前提交及独立归档提交 A；完整 SHA，不能填未来提交 |
| `planning_observation_ref` | 已留存的原真实 CLI 规划观察完整引用 |
| `command`（CLI 路线） | 原包装器的 `args / exit_code / stdout_ref`；stdout 与观察分提交保存时显式带其 commit |
| `workflow`（既有 Skill 路线） | `workflow_ref` 固定实际使用的 Archive 入口字节；`execution_ref` 指向原移动过程；`sync_evidence_ref` 固定实际同步结论，`sync` 记录 synced/already-synced/no-delta/without-sync 的本次选择 |

`command` 和 `workflow` 恰选其一。移动过程采用 `archive_move_receipt`：保存 `kind: archive-move`、同一逻辑 Change、project_root、before_revision、source/destination 的执行时绝对路径、真实 `mv` 参数、退出码、起止时间、执行者及 stdout/stderr 固定引用。输出先保存，再保存引用它们的过程记录，最后保存归档观察；归档提交 A 中不混入这些元数据。原工具调用或进程记录是依据，不能从“目录已经存在”倒填一次成功执行；库只能核对记录与实际 Git 内容，真实 Agent 是否遵从完整 Skill 仍须另验。

运行位置和源目录只作为观察身份，读取器不会访问旧机器路径或重新执行 CLI。它从确切 Git 对象重算单父提交关系、活动/归档定位、完整文件集合与模式、Task 状态及原观察适用性；二进制和非 Markdown 文件必须原样保留。Markdown 复用已有解析器，将每个位置的链接解析为目标路径/锚点，再比较文本、代码、结构和引用定义；位置、排版源码与相对 URL 的机械差异不等于规划修改。原始前后字节仍逐一固定，不改变规划摘要算法。重复引用定义、未支持的 HTML/wiki 等内容明确报告不可判断，不能静默认为链接已保留。

主 Spec 的相关链接另在归档提交和当前输入中核对，不允许依赖仍活动的 Change 路径。需长期保留的设计附件先明确所有者，使用项目既有文档/能力资源目录或可恢复固定引用，审阅迁移、来源关系和当前阅读链接；Sync 不自动迁移任意附件。共享源/派生物继续引用原固定身份，不随某条 R 或 Change 退出而删除；正式清理前核对保留 BL、归档、证据和受支持版本的全部反向引用，符合项目保留政策后再处理。当前设计素材检查不替代完整实施资源导入与长期迁移验收。

无 Delta/显式不再 Sync 的归档不得同时改变主 Spec；正常 Sync 只允许触及本 Change 的实际 Delta 对应路径，合并内容是否完整正确仍需后续 Review 和验证。输出的文件移动、链接和主 Spec 引用是派生观察，没有第二份 Task、Trace 状态或合并许可。

错误的目录/提交、丢失文件、未完成 Tasks、归档中夹带代码、超出链接迁移的正文修改和失效资源引用都会拒绝。旧归档已恢复成活动 Change 时，旧观察不再代表当前归档完成；保留历史并沿实际恢复/返修/再次归档接续。重复查询没有副作用；结果不明先检查原命令、提交与实际目录，不再次盲目归档。原失败、旧记录和旧 Git 对象继续留存；后续合并与名额释放按本页对应阶段分别检查。

归档正文及其资产引用保持固定；指向交付元数据的导航链接不冻结后续业务记录。完整交付检查中，当前 map、验证计划和工程 Review 必须与本次受审输入一致；已发布控制记录只能追加，须同时保留归档时和最新已发布记录的原事件。链接和锚点仍须可解析。这不会授权发布新事件，也不放宽来源／派生资产、任意附件或测试明确读取的输入；独立归档读取未取得上述当前语境时仍按固定内容检查。

## 同一 Trace 的归档后交付引用

保存实际归档观察后，在原 C Trace 的 `delivery` 增加完整 `archive_observation_ref`。原 `links`、来源资产使用、规划观察和 `delivery.task_ref` 保留归档前的固定身份；实际文件位置由已核对的移动关系推导，不能手写新位置来掩盖丢失文件或改变 AC/Task 关联。Trace 的归档前版本仍在归档提交的父提交中，不新增一份可编辑的归档 Trace。

若 Trace 关联的是主 Spec 中未修改的 Requirement，而同文件其他 Requirement 被本次 Sync 更新，仍保留原固定引用。检查器仅对实际归档已确认的 Sync 文件推导当前定位，核对原引用在归档前成立，并比较完整被引用 Requirement 在归档前、归档提交及当前输入中的内容、Scenario、链接和引用定义；文件模式与关联标题也须保持。位于段落外的引用定义仍参与比较，共享附件继续核对原字节。同文档内部导航不冻结整份旧主 Spec，当前完整主 Spec 仍由最终检查和审阅绑定。该投影不保存新 Trace、不替代 Sync 语义审阅；被引用内容改变、标题缺失/重复或外部素材变化时停止，不能刷新旧摘要或复制未修改的要求为 Delta 来放行。

内部 `archive.check_archived_delivery(delivery, trace_ref, head_revision=..., verification_inputs=..., control=...)` 读取同一当前 Trace，重新核对归档观察与原关联，再通过已验证的文件映射读取归档 Spec/Task 和来源资产使用。它在内存中产生当前定位视图，明确标为派生结果；不会伪造归档后的 `status`、Apply 指令输出或第二份 Tasks。Tasks 后补的受限证据导航仍可保留，原交付 Task 的正文、编号和完成状态必须与归档前实际状态相符。

按归档后的实际输入执行适用测试，原样保存新的过程/报告和不可变 E；更新原 Trace 的 `delivery.verification`，必要时更新纯验证 Task 对所选 E 的实施引用。每份调用期望继续由受审验证语境提供，不能直接改旧 E 的测试提交。所选执行必须发生在实际归档提交或其后继提交；较早 E 保留为历史，不充当最终检查。新报告仍须通过既有用例、贡献、身份、实际执行和测试后内容变化检查。

旧测试、重新标记的执行、归档时改变规划关联、错置原 Task 引用及测试后工程内容变化均不能通过。需要行为返修仍恢复同一活动 Change，沿既有 Update/Apply/TDD 接续；新轮归档前的当前 `delivery` 不再携带旧归档观察，原观察及旧 Trace 保留在历史中。这里提供归档后关联读取；原准入、当前 BL/目标线/控制、最终检查、Review 和合并授权由下节组合核对。文件/来源使用检查不等于 Change 自有派生资产已完成正式采用。

## G3 合并前检查

`G3 / pre-merge / change:<实际逻辑名>` 接续同一 Standard 交付，重新核对原归档前准入、实际归档、当前 BL/目标线/控制、归档后运行、最终审阅与合并请求。它只读取真实记录，不执行 CI、调用 Explore／Verify、合并或发布事件。候选提供者的实际集成证明和已登记 Change 派生物的归档定位已接入工具检查；Tiny 的 task/pr subject 使用上文独立任务关联，不能用伪造 Change 绕过。素材引用通过仍不能替代实际资源导入、构建和长期引用验收。

先保留前一节实际通过的 **current pre-archive 快照原件**，随后执行既有归档并保存独立提交 A。归档后按项目既有检查政策运行适用检查，形成真实受检提交 C；C 必须包含 A 及当前目标提交。原始结果、E、审阅和请求在之后的证据提交 D 保存，D 继续指向 C，不把 D 改称已经测试的提交。只有实际输入未变时才可复用这些运行；证据保存本身不要求重跑代码。

### 最终检查的原始记录

在现有 `trace/evidence/<运行>/` 保存 `final_checks_observation` JSON，不建立另一份 CI 配置或 Feature Tasks：

| 字段 | 内容及边界 |
| --- | --- |
| `schema_version / change / project_root` | `vr/1`、Standard 实际逻辑名、本轮命令实际运行的绝对目录；Tiny 用 `subject` 替代 `change`，两者不得混填 |
| `tested_revision / target_revision` | 实际受检提交 C、已纳入 C 的当前目标提交；不填未来 merged_commit |
| `input_refs` | C 的完整受检工程文件集合；仅排除已识别的交付元数据。原过程明确声明的数据文件即使位于证据目录也必须纳入 |
| `policy_refs` | C 中既有项目检查政策/配置的固定引用，供最终 Review 判断实际检查是否充分 |
| `entry_policy_run_ref` | 实际 `node scripts/adapt-openspec-workflows.mjs --check` 的独立原过程；它不代替业务测试 |
| `project_run_refs` | 实际项目检查过程；可直接引用同一 E 的 `execution_receipt`，避免为同一运行再造记录 |
| `openspec.all / openspec.archived` | 原包装器的 `args / exit_code / stdout_ref`，保存实际 JSON 输出；输出与观察分提交保存时带原 commit |

普通命令过程采用 `command_run`：记录 `schema_version: vr/1`、`kind: command-run`、真实 argv、`cwd: .`、source_root、tested_revision、起止时间、actor、exit_code、五项 identities、input_refs 及 stdout_ref/stderr_ref。输出引用可省 commit，此时从该过程记录的原保存提交解析；其他固定引用沿已有模型。自动测试优先使用原 `execution_receipt`，最终检查只接受已提交执行。所有过程都绑定同一 C，各自保留原失败、日志和身份；检查器不从文件存在或任意命令退出 0 推断业务验收。

使用业务项目 AGENTS 和 CI 已规定的构建、测试与静态检查命令，检查原过程是否覆盖当前改动；需求 Gate 不替代这些工程检查。捕获 OpenSpec 结果时，为既有调用追加 `--json`：all 要求 `validate --all --strict --json`，archived 要求 `validate --archived --no-interactive --json`；可保留 `--no-interactive` 及 `--report full|findings`。`findings` 返回的是问题条目，检查器还核对完整总数、按类型计数及实际 Git 对象集合，不能用空 itemFindings 当零项成功。归档目录仍逐份要求可识别且全部完成的 Tasks，不能只依赖 CLI 返回码。

检查器只核对固定 Git 对象和原结果，不访问原机器目录。Archive 与最终检查可以位于不同克隆；每一次运行内部的 project_root/source_root/CLI root 必须一致，跨运行则由 Git、Version、目标线及控制身份关联。真实托管 CI 来源和 required checks 的生效仍需平台验收，本地记录不提供这种保证。

### 审阅、请求与快照

1. 保存最终原过程和结果，再保存观察及同一 Trace 的最终 E 引用。保留原 BL、reservation、Apply 原点/请求及 pre-archive 快照；不得通过重建原准入消除失败历史。
2. 在 `reviews/merge/C-NNN.yaml` 用现有 `phase: delivery` Review 模型记录工程负责人的最终审阅。`merge_review_inputs(...)` 组合原交付上下文、原 pre-archive 快照、真实归档/移动/附件引用、最终受检输入/过程及到期条件；它只计算绑定，不生成决定。主 Spec 的当前内容绑定真实受检 C，随后保存 Review 的 D 不改变审阅对象。
3. Review 必须明确检查 `final-inputs`、`project-checks`、`archive-and-sync`、`verification-coverage`、`integration-conditions`、`merge-scope`。结合项目政策判断检查是否充分、Sync 语义是否正确、遗留项是否允许合并；不能以机器读取成功代替这些判断。
4. 在现有证据目录保存 `merge_request` JSON，绑定 schema_version、change、version、delivery_line、baseline_ref、原 reservation_ref、当前 dispatch_ref、final_checks_ref、candidate_revision=C、target_revision、review_ref 和具有原始来源的 integrator decision。请求最后绑定已经存在的 Review，避免双方填写未来摘要。此记录保存实际授权，不自动请求新的批准或执行合并。
5. 更新临时阶段快照的 metadata/head/target/control、留存及 `verification_inputs`，设置 G3/pre-merge/实际 Change；增加 `pre_archive_context_ref / final_checks_ref / merge_request_ref`。这三个字段只适用于本阶段。原 pre-archive 快照以 historical 重新执行完整规则，不直接信任保存的 PASS。

构造 `merge_review_inputs(...)` 时，`planning_review_ref` 必须与当前适用的批准引用一致。有当前 `planning_applicability / no-impact` 时，采用该审阅选定并经 `retain_approval` 核对的 `origin_review_ref`（返回值为 `review_ref`）；没有这项适用性接续时，沿用实际归档前准入的 `planning_review_ref`。同一文件在两个提交中的字节相同，不代表完整固定引用相同；不能直接用旧阶段返回的另一提交位置替代当前选定的引用。错绑时修正本轮合并 Review、摘要、请求与快照，保留原规划 Review、Apply 和归档历史。

终端：已安装本版本工具并准备好上述输入的业务仓库根目录，替换实际名称及快照路径：

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G3 --phase pre-merge \
  --subject change:v1-0-0-c001-configure-duration \
  --context /private/tmp/vr-premerge-context.json --format json
```

退出 0、诊断 `G3.pre-merge` 只表示本次条件通过；仅 current 且 execution 对齐已确认发布时 `merge_ready: true`。未发布的 execution-alignment 可在原预占上预检，不能据此合并；historical 始终不授予当前许可。current 要求真实干净 HEAD，结束前重新核对输入与远端，整合者仍须在最终动作前串行复核。

本阶段消费 Apply 和 Merge 两类限制，包括已发布的 Task hold；旧 CI、Task 改名或删除不清除暂停。解除后刷新当前控制/快照并复核，不因纯控制元数据变化重跑未变代码。到期 integration 边包含 integration 与 merge 两个检查点；已有/外部提供者仍须有当前目标契约和实际组合覆盖，completion/release 按其实际阶段处理。

原目标、map、验证计划或工程 Review 改变时，须有当前完整 Impact Review 才能沿用原规划批准。通过该判断后，归档提交到当前 head 的比较才允许本次已核对的 map、验证计划及工程 Review 引用发生变化；不对整个 requirements 目录豁免。最终命令仍将这三份文件纳入实际受检 C 的输入，之后再改字节会使该次结果过期。新目标须实际纳入分支并保留其原字节；归档后不能重新伪造活动 Change 的 CLI 观察。当前 Trace 保留原规划观察、原批准和实施请求，以新 execution-alignment 更新受审工程输入。

行为/规格需要返修则恢复同一活动 Change，走既有 Update/Apply/TDD。缺原准入、检查失败、输入变化、Review/请求错绑、stale 控制或未提交工程文件均停止本次接续，保存诊断和原记录；修正后从实际状态复核，不伪造过去命令或未来集成。

## 原准入与实际集成事实的内部读取

`lib/integration.py` 读取实际集成事实，由下节 G3/integrated 组合消费。以下说明原始观察的保存合同；单独的函数返回值不代表 Gate PASS，也不发布名额释放或判定后继候选就绪。

沿现有流程，在获授权且当前 pre-merge 通过后，固定保存该次原始输入快照和完整 JSON 输出；它们须存在于实际待合并的源提交 S 中，不能合并后重跑 historical 再冒充原准入。保存这些证据不能改变受检工程内容。整合者按既有串行协议，在实际动作前核对目标和控制仍适用；目标变化或新增限制时回到合并前接续。Merge 完成后保存原操作/平台证据、实际结果 M 和整合者确认；响应不明先查实际远端，不再次执行 Merge。

在既有 `trace/evidence/<本次集成>/` 保存 `integration_observation` JSON：

| 字段 | 原始事实 |
| --- | --- |
| `pre_merge_context_ref / pre_merge_result_ref` | 原 current/pre-merge 的固定输入和完整原始输出；必须确认发布对齐且当次允许合并 |
| `source_revision` | 实际被合并的源提交 S，包括已留存的原准入证据；不改写最终命令的受检 C |
| `merged_revision` | 真实目标集成提交 M；不能预填未来 SHA |
| `method` | 实际 `fast-forward / merge / squash / rebase`，结合原操作和 Git 父提交关系核对 |
| `operation_ref` | 原 Git 操作记录或平台记录的固定引用，保留实际目标更新和失败/恢复范围 |
| `confirmation` | 原模型 `decision` 下的 integrator 确认，引用真实依据；兼任角色仍保留职责，synthetic 输入明确标注 |

读取器复算原 pre-merge 的历史输入，并与原输出中的归档、测试、Review、请求和原预占对账；未发布预检不成立。随后核对原目标、S、M 与所选目标历史，逐项比较受检输入的实际字节和文件模式，包括新增、删除、二进制资产及显式声明为测试输入的证据目录文件。普通 merge 当前核对单个源提交的双亲关系；多源 octopus 合并不属于已支持形态。

squash/rebase 后，原 Archive A 或受检 C 可以不再是 M 的祖先；原固定引用继续保留，不能将 E 的 `tested_revision` 改成 M。Git 内容未变可作为后续适用性判断的依据，但不替代贡献覆盖、当前 BL/控制和工程审阅。M 或后续目标的工程内容变化会作为完整差异返回；这不自动表示业务失败，也不允许沿用原 PASS，后续 Gate 须结合当前贡献及实际输入重新审阅证据是否适用，必要时执行相关检查。

该读取器不认证平台身份或远端保护，不运行 Git 写入/测试，不自行接受冲突解决结果。同一 Trace 的集成节点与当前控制由下节组合核对；后继证据消费和名额释放按下文及 S5 接续。已有两轮有前后依赖的隔离 Agent 交付证据，覆盖实际合并、集成确认、名额释放和后继反馈；它不证明任意目标环境、远端自动合并或真实产品整版交付均已验收。

## G3 合并后检查

`G3 / integrated / change:<实际逻辑名>` 处理已经发生的 Standard 交付。它复算上节保存的原合并前准入，核对实际目标线、原预占、归档定位、当前工程审阅与贡献证据。原始 Archive 和测试提交即使不再是 squash/rebase 结果的祖先，也保留原引用；实际 M 必须属于当前目标历史。

按以下顺序保存，避免引用尚未存在的自身提交：

1. 保留原 pre-merge 快照/完整结果、实际操作及确认，形成上节的 `integration_observation`。缺少合并前保存的原准入时不能补写历史 PASS。
2. 在实际目标历史的元数据工作区，读取当前代码/主 Spec，复核现有 `delivery-map.yaml`、`verification-plan.yaml` 和 `reviews/engineering.yaml`。工程 Review 的 code_ref/spec_refs 指向实际 target。纯工程反馈沿用原 BL；产品承诺或硬约束变化先沿 [RC 处置](requirement-change.md)记录影响、限制相关动作并完成新 BL 与逐对象对齐，再返回本阶段，不能在工程反馈中暗改 R/AC。
3. 在原 `trace/changes/C-NNN.yaml` 的 delivery 节点增加 `integration_observation_ref`，保留原 `archive_observation_ref`、规划关联和原 Task 引用。实现/E 引用按当前实际内容更新。Archive 内完整文件和长期链接仍须可核对，不能另建一份集成 Trace。
4. 准备 integrated 快照：保留原 `dispatch_ref`，选择同一 `trace_ref`，提供当前 `verification_inputs` 和 `engineering_inputs`。后者仅包含固定 `map_ref / verification_plan_ref / engineering_review_ref`，指向上述既有文件；不是新 dispatch 或新的执行名额。metadata/head 是实际保存这些元数据的提交，target 是权威远端上的当前集成提交，control 是当前发布索引。移除仅适用于 pre-merge 的三个最终动作字段；可省略 Apply 原点/请求，若保留则必须与原准入一致。
5. 工程负责人在 `reviews/integration/C-NNN.yaml` 保存 phase delivery 的当前审阅。必需检查为 `actual-target / contribution-coverage / evidence-applicability / merge-impact / asset-lifecycle / integration-conditions`，绑定实际 target 文件、当前 Trace/E、适用最终检查、原准入和当前工程输入。按 Review 的实际输入计算摘要，不从最终 outcome 反推审阅已经发生。
6. 留存全部固定对象，在该工作区保持干净 HEAD，使用同一项目检查入口：

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G3 --phase integrated \
  --subject 'change:<实际逻辑名>' \
  --context /private/tmp/<本轮>/integrated-context.json --format json
```

原 E 可以继续使用的条件是：其测试提交属于实际源历史，且与当前 target 的工程内容仍一致；E 声明的输入及 build/config/data/environment 等身份逐项核对字节和文件模式。保存证据和已完整审阅的三个工程元数据文件不会单独触发重新测试，但显式声明为执行输入的文件仍受约束。代码、资产、配置、测试或所依赖内容变化时，保留原 E，针对实际合入结果执行适用检查并保存新 E；新测试提交必须属于实际 M 之后的受检历史。归档、链接检查及具名 Review 不能由一份新报告替代。实际工程内容相对源提交 S 改变时，还必须执行适用的最终项目检查、v3 入口政策检查及 OpenSpec 完整校验；用现有 `final_checks_observation` 保存真实结果，并在 integrated 快照提供 `integration_checks_ref`。它复用原检查器，受检提交属于 M 之后的实际历史，target 仍是当前目标；不新建 CI 配置。只有已完整审阅的三项工程元数据变化时，可保留原最终检查，其显式 E 输入约束仍然有效。

退出 0、`G3.integrated` 表示该候选在所选目标上的贡献与适用证据通过检查；`integrated_acceptance / integrated_capabilities` 是本候选的覆盖结果，不等于 Requirement 的全版 verified/accepted。current 返回 `current_integration: true`，historical 仅解释旧时点。`final_checks_basis` 区分原源内容保留和实际目标重新检查，不改写原测试身份；结束前仍复查真实工作区及远端身份。

当前 hold 会在 `current_holds` 中保留并返回：已经发生的 Merge 事实不会因后来暂停而消失，记录事实也不会解除暂停或授权下一次实施。名额仍由原控制事件占用，按下节单独确认释放；检查器不发布控制事件。候选提供者的消费见 [S5 工程反馈](s5-dispatch.md#把实际集成事实用于后继候选)。实际 Agent 过程、CI 运行与托管 required checks 的生效分别验收，不能由本地读取结果推断。

### 检查器升级后的接续

候选已合并后升级检查器，仍接续本节的 integrated，不重新创建 Change、Apply 请求或预占。先按既有安装保护步骤冻结来源、备份并逐文件比较，完成项目要求的升级验证和获准发布，再固定实际目标 T。`lib/`、Schema、锁及guidance也是工程输入；仅在外部运行新检查器，不能替代目标工程安装和审阅。current 的 metadata/head 与工程审查提交须包含所运行检查器的完整规则身份，historical不放宽这一要求；不支持的固定实现保持拒绝。

在 T 上先审阅当前 map/plan 和 `reviews/engineering.yaml`，code/spec 引用绑定 T；无分配变化时不改 map/plan。保存工程 Review 后再固定测试提交 C，执行适用验证，随后保存新 E 和 `final_checks_observation` 到证据提交 D，并提供 `integration_checks_ref`。工具变化使旧 E 的整树工程身份不再相同，应保留旧记录并实际验证新内容；构建输入未变时可复用原构建，但注明原受检身份，不声称重建。

尤其不要在 final checks 执行后才更新工程 Review：该检查要求 C 到当前 head 的工程内容不变，否则刚保存的结果会失效。测试后按本节限定的证据元数据路径保存 Trace、E、最终检查及具名 integration Review；显式执行输入即使位于这些目录仍须保持原字节。原 BL、Apply 原点、Archive、dispatch 和原合并 S/T0/M 均保留，工具升级作为当前目标的后续变化核对。留存新 C/D 引用、保持工作区干净，再运行上述 current integrated；通过后才进入名额释放。

## 名额释放预检与发布确认

适用前提是 Standard Change 已实际集成本线，且上述 current G3/integrated 通过。独占未集成工作的退出使用[取消处置](requirement-change.md#独占未集成工作的取消)中的同一 `slot-release` 取消形式，通过 RC 阅读入口预检和确认；不能把取消事件或结果送入本节的成功集成路径。既有派生占额从同一控制历史读取，释放后仍保留原 reservation、最新 execution 对齐及完成引用；不新增可编辑的 completed 清单。

1. 在当前目标 T、控制 P 上完成不带 `slot_release_ref` 的 G3/integrated。将原始快照和完整 JSON 输出保存到现有 `trace/evidence/<本轮>/` 并提交、留存。快照中的受检 head 不改成随后保存证据的提交，历史输出不能改成 current；只写一个 PASS 标记不能替代完整原结果。
2. 整合者核对实际合并结果和集成检查，留下有来源的确认。在原 `dispatch/C-NNN.yaml` 追加 `kind: slot-release`，使用 `slot_release_payload`：`candidate_id / baseline_ref / reservation_ref / dispatch_ref / integrated_context_ref / integrated_result_ref / confirmation`。`reservation_ref / dispatch_ref` 分别选择最初预占和最新已发布对齐；BL、Version 和交付线必须保持一致。`confirmation` 使用现有 decision 模型，角色为 integrator；事件 `evidence_ref` 与确认依据相同，`based_on_control` 为原集成检查使用的 P。
3. 保存事件 D，保留完整文件摘要和 event_id。在同一 G3/integrated 快照增加 `slot_release_ref`，head/metadata 使用实际已保存 D 的干净工作区，继续提供当前 Trace、工程 Review 和原准入。沿用上一节命令预检。退出 0 且 `slot_release.publication_ready: true` 仅表示 current 预检通过；此时 `published: false`、`reservation_occupied: true`，原名额仍占用。
4. 整合者依[串行发布协议](s5-dispatch.md#串行发布控制事件)，在 P 追加确切 event_ref 并快进发布 P1。检查器不执行写入。发布前目标或控制前进时，重新取得工程/控制事实并检查；原证明不能只更换 SHA 冒用到新前驱。
5. 取回实际 P1，用原 `slot_release_ref` 和当前目标重新运行同一 G3/integrated。确认输出 `published: true / reservation_occupied: false / publication_ready: false`。控制读取会复算原集成快照中的 Gate、实际贡献和证据，完成后回到当前目标复查；不会信任保存的绿色标签，也不会删除原预占或清除 hold。

结果不明时先查询同一事件是否已经发布：未发布继续占额，已发布则确认原事件。完全相同的引用重复投递只生效一次；不能另建初始 dispatch 给已完成候选再次占额，也不能用第二个完成事件重复释放。historical 只复查旧时点，`publication_ready` 始终为 false。已发布完成记录可供后续当前集成复核使用，原历史保留；新检查不是再次释放。

后继候选仍要分别通过当前依赖证据、工程 Review、容量、hold 和本候选真实释放/Propose 请求检查。名额空闲不等于依赖就绪，集成贡献也不等于整版验收。中断后从原快照、原结果和控制发布引用恢复，不重新实施已合并 Change 或复制一份 Trace。

## 检查之后

通过只对当次真实输入成立，不提供持续执行锁。完整集成仍须在实际首次/恢复/任务边界读取最新控制，保留既有有限恢复计数及实际停点；原 TDD/Update 和显式 Explore／Verify 政策继续有效，不增加第二套任务循环。

没有原准入引用时，初次检查会拒绝已经开始实施的输入；对已提交或未提交代码/Tasks 状态按上述恢复路径接续。遇到不支持的输入时保留现场与确切请求，补齐相应支持和验证后再接续；不能清空代码、Tasks 或历史伪装为首次规划，也不能由局部通过推断其他交付条件已经满足。相关规划发生实质变化时走既有 Update/整体审阅，并重新核对实施请求；改变 R/AC/BL 时先按 [RC 处置](requirement-change.md)完成新基线、逐对象对齐和适用入口恢复，保留原准入/名额，再重新检查当前 G2/G3。

G3/pre-archive 通过后仍需分支内独立 Archive 提交、最终检查/Review、G3/pre-merge 与实际 Merge，再确认本线集成及控制回写。名额释放确认按上节接续；若由 CI 调用，仍须提供相同的真实阶段快照与固定对象，并核对返回的对象身份、具名诊断和权限字段。仅创建 Artifact 或通过合并前检查不算交付，暂停/归档/等待期间名额均不自动释放。
