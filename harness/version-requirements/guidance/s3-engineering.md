# S3：工程上下文、全量粗分配与验证责任

采用 UI 时，先按[需求层 UI 接线](../../ui-design/requirements.md)准备本阶段的固定输入和原 Review/E；本页的业务职责、控制和授权条件继续适用。

[阶段约束与支持范围](README.md) · [前一步：S2](s2-requirements.md)

操作位置是已采用此层的业务仓库。输入为 S2 的固定 source/scope/R/AC/Q 与实际代码、主 Spec、资源和构建条件。输出仍在当前 Version 的 `delivery-map.yaml`、`verification-plan.yaml` 和 `reviews/engineering.yaml`；不创建业务 Change、Proposal、Design 或 Feature Tasks。

本阶段形成的贡献分配、阶段可行性和工程 Review 交给 [S4 的 G1/content](s4-baseline.md)检查。库通过只说明所检查结构成立，实际工程判断由负责人作出，BL 还须经过批准和发布。具名检查与最终装配沿[共同合同](README.md#审阅范围与最终封装)，历史 BL/前驱链按 S4 的确切原批准、发布语境与受支持规则核对，缺件不放行。

## 先固定工程起点

1. 读取实际目标线、工程提交和相关主 Spec；核对本次 source/scope/R/AC/Q 是否仍是准备基线的内容。继承项读取确切旧记录和原配置，不从其他工作区同名文件取“最新值”。
2. 在隔离副本按该项目实际安装和构建/测试入口运行，保存命令、运行时、受测文件/提交、退出结果及日志。不能用一份只有“已构建”的文字文件替代结果；没有条件时保留缺口。
3. 工程 Review 的 `engineering` 记录 `code_ref / spec_refs / build_evidence_ref / shared_contract_refs`、资源、估算依据、验证环境和重要假设。引用使用完整 commit/path/sha256。文件可读取只是机器检查，工程负责人仍须核对依据确实支持结论。
4. 会影响可行性的未知假设使用 `blocking: true`，未有实际 `resolution_ref` 时不能通过。S3 的完整 Review 必须绑定实际 R、scope、map、验证计划、Q 和相关来源/资产及工程上下文；引用旧答复不证明它已经应用到当前内容。

发给已获本阶段授权的 Agent：

```text
执行当前 Version 的 S3。先按 guidance/README.md 恢复实际固定输入与剩余 Q，
读取现有架构、主 Spec、源码、测试和真实构建记录，再分析全部纳入的 R/AC。
为所有 AC 分配候选贡献、已有能力或具名外部交付；明确集成和最终验收责任。
业务关系逐条记录处置，按真实需要映射到实施、集成或发布条件。
只保存粗候选与依据，不生成 OpenSpec Artifact 或详细 Tasks。
缺工程事实、产品决定或验证条件时保留具体缺口及影响范围，继续独立部分。
结束时保存实际修改、检查结果、未决项和恢复入口；不得代签批准。
```

## 分配到可定位的贡献

候选 ID 在 Version 内稳定；`allocation.id` 在其候选/端点内稳定。引用为 `<节点 ID>/<allocation.id>`，例如 `C-002/settings-input`。人类可读的 `contribution` 描述其行为与边界，不充当身份。修改描述不换身份；真正拆分/替代时保留旧候选记录，完整重分剩余 AC。

一个分配条目具有 `id / requirement / revision / acceptance / contribution`。默认从当前 scope 取确切 R/配置；一条 R 可分多候选，一个候选可承接多 R。同一 AC 的多个贡献分别保留，不能靠都填写“实现 AC-01”掩盖责任边界。

| 交付路径 | 数据与限制 |
| --- | --- |
| 本版候选 | `change_name: null`、`disposition: planned`；完整 AC 分配、预计能力、理由、真实拆分审阅引用和 `shared_resources`。不填 ready、进度或完成状态 |
| 已有能力 | `endpoints[].kind: existing`，固定契约、责任、Version/line、目标线/服务路径与实际可用证据；`port-planned` 不是已可用 |
| 未来外部交付 | `kind: external`，固定契约、提供者责任、明确条件与可行依据；尚未交付时 `availability_refs: []`，不伪造完成 |
| 历史提供方 | 端点 allocation 另有 `requirement_ref`，固定旧 Version/BL/R/原配置。相同 UID 或 revision 不代表当前义务；仅确切等于 scope 选择的记录/配置时计入当前 AC 覆盖 |
| 纯技术提供方 | 可无业务 allocation，声明具名 `expected_capabilities`；必须经真实边连到当前义务，有工程依据和专门验证责任，不能由脱离业务的技术环自证必要 |

`scope.delivery` 与实际路径一致：`change` 至少有一项候选贡献；`already-satisfied` 的全部 AC 由实际已有端点覆盖；`external-deliverable` 使用具名外部路径。取消/替代候选不计当前覆盖，活动边不指向它们。技术能力引用为 `<节点 ID>/capability:<能力名>`；能力名只声明预计契约，不证明代码已经存在。

## 业务关系、执行边与审阅处置

R 的父子/历史关系不加入执行图。业务关系从 `R-NNN/REL-NNN` 或 `R-NNN/CON-NNN` 解析到确切提供 R 与目标 AC，再检查实际受影响贡献。当前纳入的继承 R 仍按当前 scope 解析字符串父项/关系；显式历史引用及背景项按各自固定 scope/Version 展开。父项或关系目标修订后，复核引用它的批次及工程结论，不能只重审目标本身；原 R/BL 与附件来源身份保持。

先复核业务关系本身的范围，再映射执行边。例如消费者只需要共享服务的读写能力，不能仅因同属一个提供方 R 就推断它也需要内容管理能力。若 S2 的目标 AC 或 applies_to 过宽，回到 [S2](s2-requirements.md#q-落实与关系检查)修正权威关系并重审受影响对象，再更新本阶段的分配和处置；已基线化的语义变化沿需求变更流程。不能保留错误硬依赖、再用 no-wait 或遗漏目标 AC 掩盖它。确实适用的全局约束仍保留，并在真实需要的实施、集成或发布检查点承接；仅凭 R 图上的一条广泛关系，不能直接宣称 S5 已死锁。

- `required_contribution` 引用业务提供方时填写 `requirement / acceptance / allocation_ref / contribution`；技术提供方填写 `capability / contribution`。不能仅凭描述文字匹配一个前置候选。
- `consumer_contribution` 是本候选的贡献引用子集；省略时作用于其全部业务 allocation，纯技术候选则作用于其全部具名能力。不能指向其他节点的贡献。
- `origin_refs` 使用真实业务关系/约束，或 `engineering:<check_id>` 指向本次工程 Review 的实际通过检查。完整 Review 还须把检查绑定到当前输入摘要；“存在这个 check_id”不等于完成语义审查。
- `when` 省略为 always，显式 null/unknown 阻断。soft 需要实际替代与审阅；active hard 业务依赖不能映射到失效/soft 执行边以规避义务。
- `dependency_dispositions` 按 origin 对受影响消费贡献分组处置。`internal` 在同候选内部兑现；`execution-edge` 引用真实边；`existing-provider` 使用可用端点；`no-wait` 保存无需等待的真实理由/证据。消费贡献不得漏处置或重复分配，目标 AC 责任不得漏掉。

`no-wait` 的合理性必须由工程/QA 审查，不能成为删除硬前提的快捷方式。具名条件明确不成立时用 no-wait，可没有提供贡献和 edge_refs；原业务关系及判定依据仍保留。同一 AC 由多个提供方共同兑现时，在处置中明确本消费者实际需要哪些贡献，不等待无关 AC 的最终验收。

## 验证计划与有限可行性

`verification-plan.obligations` 为每个 R 修订/AC 指定贡献、方法、环境、责任人和检查点。至少一个 `final: true` 义务覆盖该 AC 的全部当前贡献，层级不低于 R 中约定；多贡献 AC 不能在单项 contribution 检查点宣称最终通过。quality/constraint 的最终责任在 completion/release，采用 system/acceptance 层级。

技术提供方使用 `capability_ref` 的验证条目，仍有方法、环境、责任人和检查点，但 `final: false`，不扩大产品 R 分母。硬 integration/release 边必须由验证条目的 `edge_refs` 明确承接到期检查，不能只在最终 AC 写“QA 验证”而漏掉合并前集成。`merge` 边对应验证计划的 integration 检查点；未来运行证据可空，责任安排不可空。

阶段模型仅用于 S3 检查等待是否可行：

```text
每个候选：start → contract → apply-start → implemented → integrated → merged
本版：全部候选 merged → completion → release
```

这里 start 表示 execution 释放起点，contract 表示规划得到的契约；它们不新增 Harness 阶段，也不替代 Apply、Review、CI、Archive 或 Merge。真实执行仍沿既有链路；本模型只抽取等待条件所需的里程碑。未来外部条件有其受审交付路径，模型不把它当作目前已满足。

| 执行边 | 允许的里程碑组合 |
| --- | --- |
| implementation | checkpoint 为 apply-start，但条件同时约束 execution 的 start；本版候选提供方须 merged 且为 merged-and-verified-on-integration-base。外部端点按 provider-available 或明确 merged 的本线证据判断 |
| integration | checkpoint 为 integration/merge/completion；按 provider-available 或 integration-verified 判断。后者提供阶段至少 integrated。不能把计划日期充当可用证据 |
| release | checkpoint 为 completion/release；provider-available 或 release-combination。共同发布组合内的本版候选先到 merged，不互设“对方必须先发布” |

先用图算法检查跨阶段循环，再按批准的 `wip_limit` 和 `shared_resources` 检查有限顺序。`shared_resources` 在此列表中表示从 start 到 merged 的独占资源；仅共享主 Spec 名不自动成为全程独占，工程审阅仍须识别真实写入/契约冲突，同 capability 的 Sync/Merge 沿现有串行规则。

默认 WIP 为 1、提前规划为 0；超出默认需要实际授权引用，提前规划最多 1。planning-only 不解除实施前提，也不用于掩盖不可行切分。互等合并前集成可能需要重拆边界、独立验证路径或有界并行；拓扑无环不能证明 WIP 1 足够。

机械搜索最多探索 20,000 个容量状态；耗尽返回 unreadable/unknown，不能认定不可行或放行。可在工程 Review 的可选 `stage_order` 保存一条具体的抽象里程碑顺序，检查器核对全部节点、依赖、容量和独占资源；它只是本次可行性证明，不是详细 Tasks、实时排程或另一份状态表。输入/边/资源变化后重新检查，不能靠沿用旧顺序固定后续工程方案。

## 生成分层依赖与待处理事项视图

完成本阶段的文件草稿并保存内容提交后，沿 S4 的 G1/content 快照固定 Version、line、head/metadata/target。视图使用同一报告入口；它只读固定 Git 输入，在明确的新目录输出派生物。在业务仓库终端执行，先替换快照路径和版本：

```bash
mkdir -p requirements/versions/v1.0.0/views
.harness/version-requirements-venv/bin/python -I -B \
  harness/version-requirements/lib/report.py --root "$PWD" \
  --context '/absolute/path/to/g1-content-context.json' \
  --view engineering --output requirements/versions/v1.0.0/views/s3-001
```

输出 `engineering.json`、`engineering.md` 和 `engineering-basic.md`；后两份分别为同一图的样式版/基础版。JSON 保存固定来源、条件、诊断与 `generated_from` 摘要，Markdown 解释图的方向和证据边界。R 节点保留所选记录的 Version 和内容语境；`scope_commit / scope_version / scope_delivery_line` 说明本次关系在哪个固定范围内解释。两者不同时图中追加 scope 标签，完整记录/原配置仍用 commit/path/sha256 区分。这样可同时呈现继承的旧记录和当前父项，不把旧 BL 关系改写为新版本关系。

| 分层内容 | 阅读方式 |
| --- | --- |
| 需求层级 | 父 → 子，沿确切 scope 读取必要背景祖先，不据此排执行顺序 |
| 业务关系 | 提供方 → 消费方；related-to/conflicts-with 为无向关联，语义环不等于死锁 |
| 交付条件 | 提供方 → 消费候选；保留 implementation/integration/release、hard/soft、适用条件、贡献/AC 和检查点 |
| 全版本阶段图 | 复用可行性检查的里程碑图，存在阶段环时仍显示图和实际诊断；结构/阶段合同不成立时明确说明未生成 |
| 待处理事项和瓶颈 | 共享 Q、工程假设、独占资源竞争、S2/S3 检查诊断及无权深度/扇入/扇出；不推算工期或许可并行 |

可以在上述命令追加筛选，输出改用另一新目录：`--ac R-001/AC-01 --edge-kind implementation --strength hard --checkpoint apply-start`。每个参数可重复，多值取并集，不同参数取交集。AC 必须存在于当前 scope；涉及历史提供方时只将与当前选定记录/配置一致的贡献算作当前 AC。版本/交付线由完整快照选择，跨线提供者仍显示原身份与路径，不能用显示筛选排除必需前置。

AC/strength 筛选业务关系，AC 筛选相关层级；全部筛选作用于交付边。Q、检查、资源竞争和阶段图始终保留全版本范围，不能过滤掉失败再宣称结构通过。无关的提供方 AC 不因同属一条 R 就匹配所选边。结构化视图保留筛选参数和实际读取摘要，内容或筛选变化会生成不同摘要。

命令退出 0 只表示派生文件成功生成；JSON 的 `gate_evaluated: false` 不会变成 G1/G2 通过。已知 S2/S3 问题会显示 failed/unreadable/not-run；非法 Schema、固定输入不可读取等使生成非零退出并不产生报告。S3 结构图只显示条件 applies/not-applicable/unknown/unreadable，运行时可用性标为 not-evaluated-at-S3；当前事实另用下节观察，不能由结构图或 endpoint 声明推断。

不要手改图、JSON 或检查摘要来消除失败。依据诊断回 Q/S2/S3 修改权威文件及受影响审阅，再保存新内容提交和新报告。已有输出拒绝覆盖；多文件写入失败仅清理本次生成物并保留原错误。Markdown 宿主需支持 Mermaid；图源可使用团队已有渲染工具导出，运行时不新增 Mermaid/npm 依赖。

## 查看当前候选的就绪与阻断

取得当前 BL、目标和控制修订，以及受审 map／验证计划／工程 Review 后，可用已有 S5/S6/S7 快照生成全版本候选观察。快照中的 `dispatch_ref` 或 `engineering_inputs` 明确选择工程输入；不会从工作区猜测最新文件。G1/content 草稿也能查看，但未有有效 BL 和当前控制时不产生 ready 建议。

```bash
.harness/version-requirements-venv/bin/python -I -B \
  harness/version-requirements/lib/report.py --root "$PWD" \
  --context '/absolute/path/to/current-stage-context.json' \
  --view readiness --output requirements/versions/v1.0.0/views/readiness-001
```

`readiness.json` 保存全部候选、依赖边、固定引用和计算摘要；`readiness.md` 展示候选阻断与小批建议。单条条件区分 satisfied、unsatisfied、unknown、stale；仅尚未到期的 integration/release 条件保留 not-due。G3 按当前 integration/merge 检查点核对实际组合 E；G4 按 completion/release 核对固定候选、提供方和消费方组合，缺独立执行身份时显示 unknown。G3 的组合观察不等于已接受的 Trace 覆盖、最终 Review 或合并准入。缺当前提供方执行、契约变更、旧目标上的证据都不能当作已满足。已预占、已有 Change、已集成或取消的历史对象分别显示，不重新加入初始释放集合。

`ready` 在依赖之外还核对 Q、当前 propose/apply 限制、同线所有 Version 的占额和独占资源。`parallel_candidates` 与 `small_batches` 从 ready 集合扣除共享资源、未解决的共同需求/语义耦合和集成顺序冲突，按候选 ID 生成稳定的小批建议；未知冲突留待工程审阅，不自动提高 WIP。不同建议组之间不保证可并行；它们不是优先级或工期计划。历史模式只保留 `observed_ready`，当前 ready 和批量建议为空。

筛选参数与上节相同，但只控制呈现；全量候选、阻断和同线容量检查不会缩小。生成报告不选择候选、不发布预占、不 Propose 或开工。实际选择后仍逐候选走 [S5 的当前 G2/dispatch 与确认](s5-dispatch.md)；报告不能替代该次输入和决定。

## 失败、恢复与下一步

分配/关系/验证文件按实际差异分别保存。中断后读取 Git 中已保存的集合，补齐遗漏；不要删除旧候选、换编号、手改报告或扩大 source/scope 分母让检查通过。相同固定输入重复检查应产生相同结果且不改原稿、R、索引或证据。

缺可用事实、未知条件、阶段环、容量死锁分别回实际问题负责方；不自动降 soft、加 WIP 或代答 Q。语义问题改 R/范围时返回 S2/Q，纯工程重拆回本阶段并完整重分配。历史提供方的 BL 生效、完整 Review 摘要/适用性与发布恢复仍须通过 S4/G1，当前库不代行这些判断。只有 S3 的真实审阅与 G1 内容条件齐备，才准备基线批准；此处不继续 Propose。
