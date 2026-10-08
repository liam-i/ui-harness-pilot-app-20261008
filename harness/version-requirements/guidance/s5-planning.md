# S5 实际规划关联与审阅

采用 UI 时，先按[需求层 UI 接线](../../ui-design/requirements.md)准备本阶段的固定输入和原 Review/E；本页的业务职责、控制和授权条件继续适用。

[共同约束](README.md) · [前置：候选释放](s5-dispatch.md)

当前提供 `G2/planning`，包括同一 Change 在实施前后的受审规划修订：在已经发布的同一预占上，核对真实 OpenSpec Artifact、逐贡献 Trace 和规划 Review；实施后修订还须绑定已有代码与 Tasks 的实际输入。未发布初始 dispatch 不能进入此阶段。候选提供者按 S5 固定当前目标集成证明；Change 自有派生物按下文在原 Trace 登记并检查；G3/pre-archive 按 [S6](s6-delivery.md#g3-归档前检查) 独立检查，本规划检查通过不表示已获实施许可。

## 接续实际 Propose

先完成 S5 的原事件发布确认，再由 Agent 执行既有 Propose。需求层不运行另一套生成器；Explore／Verify 沿原显式方法政策，普通规划及本页工具查询不自动调用它们。

1. 恢复实际分支、HEAD、原 BL、确切 event_ref 和最新控制观察，核对当前 Propose 请求。检查器读取固定提交；操作者须确保传入的 head 是当前工作区实际提交，未提交的相关差异先保留并处理，不能用旧快照掩盖。
2. 读取既有 CLI 的实际 Schema 和 locator，再生成已释放候选的工程方案。中断后先查实际 Change/Artifact 和 Git 历史，继续同一个 Change；没有 Trace 不是再次创建的依据。有多个可能对应的 Change 时，先明确关联，不猜测、不删目录重来。
3. 实际文件生成后，在当前 `delivery-map.yaml` 为该候选绑定全仓唯一逻辑 `change_name`；按真实变化更新工程审阅及其固定 map/验证计划。仅关联工程对象不重写 R/AC 或原 BL。
4. 如果原 dispatch 的工程输入已变，沿原 `dispatch/C-NNN.yaml` 追加 `execution-alignment`，引用最新 `previous_dispatch_ref` 和实际评估依据；沿用原名额。先保存固定事件，后续规划预检通过再串行发布。原事件及已发布控制历史保留。

本阶段不要求尚未发生的实现、测试通过、Archive 或 Merge。设计内容继续只在实际 Change，不能在 Requirement/Trace 中复制 Spec 或另列 Feature Tasks。

## 留存实际 CLI 观察

在业务项目根目录，通过既有安装路线查询。以下是 B 路线的终端命令；A 路线使用 `npm run --silent spec --` 将同一参数传给项目既有入口，抑制 npm 运行横幅，保持原始 stdout 为纯 JSON，不改变工具来源。A 路线在 S6 留存 CLI Archive 和最终 OpenSpec 校验的 JSON 时也使用这一调用形式，不手工裁剪或改写原输出。

```bash
bash scripts/openspec.sh schema which spec-driven --json
bash scripts/openspec.sh status --change <实际逻辑名> --json
bash scripts/openspec.sh instructions apply --change <实际逻辑名> --json
bash scripts/openspec.sh validate <实际逻辑名> --strict --json
```

每条查询保存原始 stdout、stderr、参数、退出码及执行位置。`instructions apply` 仅获取上下文和任务观察，不调用 Agent Apply/TDD，不勾 Tasks，也不等同 Verify。遇非零、缺输出或来源不符先保留失败，不能拼接旧绿色输出。

使用 `openspec_observation` 模型保存一份 JSON 原始观察引用，建议放在 `requirements/versions/<Version>/trace/evidence/<本次观察>/`。目录每次新建，旧观察按原提交保留，不把可丢弃的 views 当权威证据。

| 字段 | 取值来源与要求 |
| --- | --- |
| `change / project_root / captured_revision` | 实际逻辑名、捕获时项目绝对路径和已提交的受查输入 SHA；不能填后保存证据的提交 |
| `schema_ref` | `schema which` 所选官方包内真实 Schema 的留存副本，带完整提交/路径/摘要；不手造 Schema |
| `input_refs` | 同一 captured_revision 下完整 Change 文件集合，项目 OpenSpec config、包装器、适配器、Profile 与实际版本来源；A 包含 package.json/package-lock.json，B 包含 harness/openspec-version；存在项目 Schema 覆盖时一并记录 |
| `commands.schema/status/apply/validate` | 上述四条查询的下游 `args`、实际 `exit_code` 和 `stdout_ref`；不把 Bash/npm 前缀写入下游 args |
| `stdout_ref` | 原 JSON 输出的路径/摘要；省略 commit 时从 observation 所在提交读取，显式填写时须是实际已有提交 |

先固定规划输入，再捕获查询，最后保存原输出和 observation；不能让记录引用其自身尚未生成的提交。复查捕获期间相关字节未变；若变了，保留本次记录并对新输入重新捕获。留存按 S4/pins 机制执行，检查器自身不运行 CLI、fetch 或发布。

读取器将真实 `planningHome/changeRoot/artifactPaths` 与固定 Git 文件集合对照，而非按预期目录拼接。当前支持仓库内 planningHome 和已核对的内置 spec-driven；外部 store 明确退出 2，保留原 locator 等待支持，不改写成仓库内路径。CLI 原生 `.openspec.yaml` 的未加引号 created 日期由独立窄解析器读取，不修改原文件，也不放宽 Requirement YAML 的日期规则。

## 固定 Trace，再保存规划 Review

实际关联使用 `planning_trace` 模型，权威落点为 `requirements/versions/<Version>/trace/changes/C-NNN.yaml`。它固定候选、Version/line、逻辑 Change、原 `baseline_ref`、最新 `dispatch_ref`、`observation_ref` 和根据实际内容计算的 `planning_digest`，不另存 ready 或任务状态。

- `links` 逐行选择当前候选的实际 contribution、分配的 AC、Spec 文件固定引用及 Requirement/Scenario 标题、Tasks 的显示编号和验证义务 ID。业务 AC 必须有行为 Spec；无 Delta 可以指向正确主 Spec，同一 Change 中没有修改的约束也可继续关联正确主 Spec。不要为统一文件位置将未修改要求重复声明为 Delta；归档后的引用按 [S6](s6-delivery.md#同一-trace-的归档后交付引用)接续。不能以文件存在代替标题/Scenario 归属核对，也不能把 CLI 的任务列表序号当稳定显示编号。
- 技术贡献不伪造 R/AC。作为依赖提供者或已有验证计划明确要求的技术贡献，须关联真实验证义务；未使用的能力声明不自动扩展成一套新任务。
- `design` 保存 present/not-required、理由和固定证据。实际 Schema 与适用性共同决定是否需要 Design；不能只用 `isPlanningComplete`，也不使用不存在的 skip_design 标记。
- `asset_uses` 保存贡献、既有 AST/DAS 的固定 owner 引用、用途与实际使用 Artifact；Artifact 内链接须解析到同一文件字节。共享资源仍引用原所有者。实施接续时，Tasks 勾选、重开或按 [S6 追加固定证据引用](s6-delivery.md#追加与纠正-tasks-证据引用)不使原使用引用失效；原固定引用保留，任务正文/附件链接、其他 Artifact 和附件字节仍须一致。Change 自有素材不能用普通裸文件引用绕过登记，未登记文件、已登记修订的覆写或删除都会阻断。

内部只读 `check_planning_trace(..., require_review=False)` 可以列出本轮必需 reviewed_inputs/context_refs/required_checks，便于装配审阅输入；它不是独立 Gate 或批准。工程负责人在实际阅读后保存 `reviews/planning/C-NNN.yaml`，使用同一 Review 模型，phase 为 planning。初始规划的六项必需检查为 scope-coverage、artifact-consistency、design-applicability、verification-obligations、input-applicability、asset-uses，分别绑定完整输入摘要和实际证据。缺口不能机械写成 passed。

保存顺序为 Artifact → 原查询输出/observation → Trace → Review。Review 引用已有 Trace；Trace 不反向引用尚不存在的 Review 提交。原 BL、事件、当前工程 Review/映射/验证计划及相关 context_refs 进入同一审阅语境；机械绑定不能代替语义审阅。

## 规划预检与发布确认

沿用 S5 快照，将 phase 改为 planning，并增加完整 `trace_ref`。`metadata_revision` 是实际保存当前 Review/Trace 的提交，`head_revision` 是当前实际工程 head；`dispatch_ref` 仍引用事件原提交。原 BL 发布观察保留，target/control 使用实际当前值。

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G2 --phase planning --subject candidate:v1.0.0/C-001 \
  --context <snapshot.json> --format json
```

新对齐尚未发布时，只有原预占已经发布且对齐基于其最新事件才能预检；通过输出 `alignment_published: false`。整合者随后核对最新前驱并发布，独立取回新控制提交，更新快照，再运行同一检查确认 `alignment_published: true`；`reservation_ref` 始终指向原预占。发布结果不明先查确切事件，不另建 dispatch 或重复占额。

current/historical 的 planning 都不授予 Apply，输出 `apply_permission: false`。historical 只复算固定历史，不能作为当前动作许可。初次实施另按 [G2/apply](s6-delivery.md)核对实际请求和 execution 对齐；不得因为 CLI 显示 ready 或 planning 退出 0 就开始实施。

## Change 自有派生素材

先确认实际用途。直接阅读产品原图或已有需求派生物，继续引用原 AST/SRC/DAS；只有本轮确需保存裁剪、标注、转换或新增设计材料时，才写到实际 CLI `changeRoot/assets/DAS-NNN/r<revision>/`。不为每条 R 建目录，不把原 PRD 包整体复制到 Change。应用运行或测试所需资源使用项目既有资源目录，本节的设计素材登记不替代实施导入及构建输入的生命周期核验。

按真实保存顺序操作，避免引用尚不存在的自身提交：

1. 保存制作输入、实际输出和制作/核对依据。输出固定为 O 中的 `output_ref`，含完整 commit/path/sha256；随后捕获包含该文件的实际 OpenSpec 规划观察。不能先填未来输出 SHA 或用临时文件路径代替。
2. 在当前唯一 `trace/changes/C-NNN.yaml` 增加可选 `asset_derivations`。每项使用 `change_derivation`：沿需求派生物的 `id / revision / sha256 / media_type / inputs / purpose / transformation / review_ref`，输出以 `output_ref` 定位，不使用可随归档移动的相对 `path` 作为身份。自动变换保留固定脚本或工具/版本/参数；手工修改如实记录。外置内容沿原 received_sha256/external 合同，不能把指针当媒体。
3. 保存上述 Trace 后，再以 `{identity: "<实际 Change 名>/DAS-001@1", manifest_ref: <该 Trace 的固定引用>}` 建立 `asset_uses`。manifest_ref 在这里引用已有 Trace，不新增 manifest 文件。使用方保留实际 Artifact 固定引用与可解析阅读链接；登记、使用、最终规划 Review 可分提交，不能构造 Trace 对自身提交的引用循环。
4. 完成覆盖全部当前输入的规划 Review，再运行原 G2/planning。机器核对实际目录清单、确切输出、完整制作输入链、使用位置及不可变修订；review_ref 可读取不等于制作语义已获批准，仍由实际规划审阅判断忠实性和适用范围。

`assets/` 中持久文件须全部登记；制作草稿保存在本次明确的临时位置。登记后的同一 ID/修订保留原记录与输出，新版追加修订；共享消费者复用固定引用。纯字节复制若确为独立交付所需，也说明输入、用途和输出，不默认为产品变更。更新设计含义或使用关系时沿本页 Update/完整 Review；只发布新 revision 不自动让原消费者改用它。

Archive 按 [S6 的完整文件移动检查](s6-delivery.md#保存与核对实际归档观察)接续。读取器根据已经核对的移动派生新位置，原 output_ref、DAS 身份与制作依据不变；没有更新定位不能把旧活动路径当成仍可阅读。归档不得暗改派生输出字节，主 Spec 的长期引用也在 S6 审阅并保存到项目既有长期位置。这里检查的是固定制作输入、输出和引用接续，不证明资源已经正确导入应用、进入构建或通过运行验收。

需要转为运行资源时，在当前 Design/Tasks 中明确项目输出位置、必要转换和验收方法；真正的导入及打包沿 [S6 运行资源接续](s6-delivery.md#运行资源的导入与交付)在实施授权内完成。`asset_uses.used_in` 仍只关联规划 Artifact，代码/运行文件由同一 Trace 的 delivery 和真实 E 关联，不能把“素材可取回”当作“资源已交付”。

## 尚未实施时修订规划

已 Propose、尚未 Apply，且代码/Tasks 仍未进入实施时，规划调整复用同一候选、Change 和原名额。按既有 Update 整体呈现受影响方案，经真实审阅后写入；工具不会运行第二次 Propose 或自动批准新正文。实现机制仍是本页的观察、Trace、规划 Review 与 G2，不增加 Update 状态表。

1. 保留有效 Spec、已有规划及原批准/请求的历史引用。修改必要的 Design/Tasks 等 Artifact；若业务义务未变，不仅因技术方案调整重建 R 或 BL。
2. 对新的完整 Artifact 集合重新取得实际 CLI 观察，更新当前 Trace、Design 适用性及受影响关联。旧规划 Review 不能绑定新 Trace，需按同一完整审阅合同保存新的规划 Review；不能只重算旧批准的摘要。
3. 当前目标/map/验证计划和受审工程前提未变时，保留仍适用的 S3 工程 Review 与原对齐事件。它们发生变化时，沿[工程输入适用性](#工程输入变化后的批准适用性)更新工程 Review 和 execution-alignment，先预检、再发布确认；始终沿用原名额。
4. G2/planning 通过后核对真实实施请求。旧记录若只绑定原方案，不能用于新的规划摘要/Review；按 [S6](s6-delivery.md#保存真实实施请求)保留原请求，另记录适用于新方案的绑定。既有授权仍覆盖修订时不自动重复询问；缺授权或超出原范围才补必要决定。G2/apply 仍消费最新控制与实际工作区，planning 通过不授予实施许可。

该路径已用 synthetic 规划/决定及实际 CLI/G2 验证，未据此验收 Agent 的 Update 行为。已经存在实施代码或完成/重开的 Tasks 时，不能清空它们来走此路径：未改规划按 S6 原点恢复，实质规划变化按下一节接续。

## 实施开始后的规划复核与 Update

已经进入 Apply 时，保留最初的 `apply_origin_ref`、原名额、当前代码及 Tasks。原点仍指向首次 current 准入，不把恢复快照串成链；S3 工程 Review 继续描述目标交付线，不能把功能分支伪装成目标线来消除差异。

首次准入所审方案未变时，G2/planning 可以携带原 `apply_origin_ref` 复核已有批准和对齐条件；上游改变时继续采用完整 no-impact 判断。它不新增实施许可，current Apply 仍消费独立请求与最新控制。真正修改方案时，按以下顺序接续：

1. 依实际问题执行既有 Update，整体呈现受影响规划并保留正确内容、已完成任务和失败记录。R/AC 不变不自动新建 BL；目标/map/验证计划或原适用性记录改变时，先更新对应工程 Review；需要新的 execution-alignment 时仍沿原名额，在下述规划预检通过后发布确认。未知、产品变化、重拆等待决处置不能假装成无影响。
2. 保存已审阅修订的完整工程 Artifact，重新捕获实际 CLI 观察并更新 Trace。对已有代码/测试、Tasks 实际状态及必要输入使用 [S6 的工作区捕获](s6-delivery.md#保存未提交输入的运行证据)；允许代码仍未提交，元数据单独保存。捕获必须覆盖真实规划目录和实际需要的额外输入目录。
3. 当前 G2/planning 快照同时给出 `apply_origin_ref` 和 `planning_inputs_ref`（固定工作区捕获引用）。规划 Review 仍在同一原位置，绑定新完整规划、Trace、上述两个输入，以及 `update-impact`、`execution-state` 两项检查：说明前后方案影响、保留/重开/调整的任务、已有实现与剩余工作，不能以文件存在充当语义审阅。旧批准保留在原固定引用中，不能只刷新其摘要。
4. current G2/planning 核对实际 HEAD/工作区与受审捕获。单独保存 Version 元数据不要求提交 TDD 中间代码；代码/任务状态在审阅后又变化则不能继续把该捕获当新的当前规划准入。historical 只解析留存输入，不读取今天的工作区、不授权。若当前工程 Review 仍选择旧批准沿用或保留待决处置，应先按实际 Update 结果更新该 Review，不能同时宣称沿用旧批准和批准新方案。
5. 完成必要的对齐发布确认并重新通过 G2/planning 后，将此次原始输入快照固定保存到 `trace/evidence/`；未新增对齐时仍须核对原事件已发布。适用于新规划的 `apply_request` 另以 `planning_snapshot_ref` 引用它，同时绑定确切新 Review/规划摘要及授权 Task 范围。快照、请求分先后保存，不引用未来提交；原授权仍覆盖修订时沿用真实授权，不因此每次重新询问。
6. Apply 快照仍使用最初的 `apply_origin_ref`，引用当前适用请求，不携带 planning_inputs_ref。检查器先复算首次准入，再历史复算请求绑定的修订规划，最后核对当前 BL/Q/工程输入、批准适用性、请求、已发布 execution 和最新 hold。修订后的实现可以继续提交或保持未提交，读取当前 Tasks 接续，不重置已完成项、原名额或恢复计数。

`planning_snapshot_ref` 是请求所针对的实际规划语境，不是新的批准来源或持续执行锁。新版规划继续遇到上游变化时，仍按原适用性合同处理；下一次实质 Update 再保存一份对应新 Review 的规划快照，执行原点始终不变。任务状态或既定证据的纠正与实质规划调整分别处理；证据补充按 [S6 的固定引用格式](s6-delivery.md#追加与纠正-tasks-证据引用)保存。检查器不能自动识别任意自由文本究竟是补证还是改规划，不能因此把所有证据说明都要求重新取得业务批准。

## 工程输入变化后的批准适用性

原规划已审阅后，先比较当前实际工程输入。已实施或已完成 Update 时，保留最初的 Apply 原点；受评估的原规划快照应对应实际适用的规划 Review，修订后使用该次 Update 的固定规划快照，不能退回首次旧方案。无影响判断保存在同一份 `reviews/engineering.yaml` 的 `engineering.planning_applicability`，由当前完整工程 Review 绑定；不重签原规划 Review，也不另建批准库。

| 字段 | 必须来自的实际事实 |
| --- | --- |
| `candidate_id` | 当前 map 的唯一候选，不能为同一候选提供互相冲突的两项判断 |
| `origin_snapshot_ref / origin_review_ref` | 对应受评估方案的 G2/planning **发布确认后**快照和规划 Review 的完整固定引用；实施后的 Update 快照包含原 Apply 准入及受审执行输入。对齐预检草稿不能充当已发布原点 |
| `observation_ref / target_revision` | 当前实际 CLI 观察与目标提交，不能沿用旧目标值 |
| `target_changes` | 原目标到当前目标的全部工程文件变化，含增加/删除；每项保存 path 及 before_ref/after_ref，缺失端为 null。仅 requirements/ 由原 BL/当前 Q/map 的专门检查覆盖，代码、测试、配置、Schema、Spec 和工程说明不自行排除 |
| `conclusion / reason / evidence_ref` | 实际影响结论、理由和固定依据；no-impact、update-required、repartition、requirement-change、unknown 分别表达无影响、需 Update、重拆、产品变化及待查 |

只有 no-impact 且完整检查通过才能保留原批准：原快照的控制历史中已经发布对应事件，当前控制延续该历史；原批准和固定输入可复核；原规划及 AC/Task/验证义务关联、实际 Schema 字节未变；当前工程 Review 覆盖完整差异与当前问题/依赖。后保存但字节相同的定位引用可以变化，不能因此改写原决定。重复对齐仍引用最初适用批准的原快照，不将上次 no-impact 记录伪装成新的原批准。

需 Update 时按既有整组审阅处理实际工程方案，形成新的 Trace/规划 Review，并更新当前工程 Review，撤去不再适用的 no-impact 沿用项；原项留在 Git 历史。重拆返回受审 map；产品义务变化先沿 [RC 处置](requirement-change.md)停止受影响动作，完成新 BL、逐对象规划对齐及对应入口恢复，再按当前 G2 与真实实施请求接续。unknown 或其余结论不能先进入 Apply。初始范围内通过无影响重评可以保留仍适用的实施请求；实质改变规划后则重新核对真实请求范围，不能只刷新摘要。

## 异常接续

- 缺 Trace、缺必需 Review 检查、错误 AC/Scenario/Task、与观察不符的文件增删或正文变化：保留现场，修正实际关联或回到既有规划审阅/Update，再捕获受影响输入。禁止只重算摘要掩盖变化。
- 已有 Task 完成或代码已开始变更：当前初始规划路径停止；已提交或未提交代码/状态按 [Apply 原点恢复](s6-delivery.md#实际工作区的恢复检查)接续，实质规划变化仍回 Update；不能擦除勾选、代码或历史来冒充首次规划。
- 上游工程事实变化：按上述适用性合同区分原批准沿用、Update/整体审阅与产品义务变化。实施状态按 S6 复核原准入和实际输入，实质 Update 绑定实际执行输入后整体审阅；Agent 按 S6 任务边界显式调用检查，不把它当作后台自动调度，也不把局部变化改写为所有情况都应重审全版。
- hold、旧 control、输入不可取回：沿 S5 恢复最新事实，不能切换 historical 放行，暂停继续占额。
- 删除已有 Trace、迁移逻辑 Change 给另一个候选/Version：检查拒绝；恢复原关联和历史后在真实阶段接续。

本页提供隔离试用的规划与修订检查；规划通过后仍须依据具体实施请求接续 S6，不将单次规划 PASS 当作交付已完成。
