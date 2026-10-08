# Version Requirement 可复制实现

[返回模板](../README.md) · [阶段指引](guidance/README.md)

本目录是可复制的 Version Requirement 工具、配置和阶段指引。先按下表确认采用范围，再使用本文安装步骤；工具结果不替代产品决定或实际工程审阅。

| 能力 | 入口 | 当前支持与验证边界 |
| --- | --- | --- |
| PRD 包与需求建模 | [S0 接收](guidance/s0-intake.md)、[S1 Challenge](guidance/s1-challenge.md)、[S2 R/AC](guidance/s2-requirements.md) | 多文档/共享附件、来源与派生引用、Q、独立阅读报告；已完成隔离工具及实际 Agent 验证 |
| 工程粗分配与基线 | [S3](guidance/s3-engineering.md)、[S4](guidance/s4-baseline.md) | 全量贡献/验证责任、完整 Review、G1 content/record/effective、固定历史与新克隆恢复；已完成声明范围内的上游验收 |
| 候选释放与规划 | [S5 释放](guidance/s5-dispatch.md)、[S5 规划](guidance/s5-planning.md) | G2 dispatch/planning、当前依赖、占额、发布确认、引用交接、实际 OpenSpec locator/Trace 及受审 Update；已有本地 CLI/Git 证据，限隔离试用 |
| 实施与交付检查 | [S6](guidance/s6-delivery.md) | G2/apply 首次/恢复、Standard G3 pre-archive/pre-merge/integrated、同一 Trace、名额释放及后继依赖证明；已有工具组合及两轮隔离 Agent 交付证据，包含实际任务边界停止/恢复 |
| 需求变更与版本迭代 | [RC 处置](guidance/requirement-change.md)、[新版本与维护线](guidance/version-iteration.md) | 新 BL 对齐、实际整改/取消/退役及局部恢复；新版独立基线与本线验证，按具体验证范围隔离试用 |

已有能力／外部交付可按 [S6](guidance/s6-delivery.md#无-change-的交付核对)直接核对 `scope:`；Tiny 的 [任务／PR 接续](guidance/s6-delivery.md#tiny-任务pr-的交付核对)使用 G3/pre-merge 与 integrated。[运行资源接续](guidance/s6-delivery.md#运行资源的导入与交付)已有配置文件导入、打包和归档后交付的隔离样本；实际整组 Update、无 Delta、显式 Verify 与归档未合并返修也有隔离接续证据。真实多文档包的受控上游、一个本地候选和教程小版本已有证据；原包允许格式、固定版本成本、Codex CLI/App接续及GitLab串行整合模式已有实际验收；未声明媒体格式、自动合并及其他宿主不能据此采用。需求变更按声明的本地处置范围接续，G4/completion、release 已接入，并有小版本完整链、组合失败、替代交付及发布确认的隔离证据，操作与限制见 [S7](guidance/s7-completion.md)。不支持的 phase/subject 返回明确非零结果；未验收的能力不能视为已经完成正式采用。合成测试决定不能当作真实产品批准。详细验证边界见[版本说明](../../tutorials/version-and-sources.md#验证边界)，CI 的本地检查与远程限制见[流水线示例](../../examples/version-requirements/README.md)。

## 文件与业务落点

| 本目录文件 | 业务项目位置 | 职责 |
| --- | --- | --- |
| `requirements-check` | `harness/version-requirements/requirements-check`及`scripts/requirements-check` | 前者保存受审入口原件，后者是实际调用副本；两者完整身份一致，只用项目指定venv |
| `review.py` | `harness/version-requirements/review.py` | 已审单项的显式写入入口；调用官方 review/strict，只接收原生标记并保留原字段值 |
| `ci.py`（可选） | `harness/version-requirements/ci.py` | 在宿主已准备的可信checkout中执行唯一阶段 CI 命令；不安装依赖，不新增Gate规则或发布能力 |
| `lib/` | `harness/version-requirements/lib/` | 安全读取、固定对象、模型、投影和阶段判断；不发布或写权威数据 |
| `schemas/` | `harness/version-requirements/schemas/` | `vr/1` 机器合同，领域/跨文件义务仍由各阶段检查 |
| `config/` | `harness/version-requirements/config/` | 唯一依赖锁、官方源码校验和 Doorstop 初始配置；`project.yaml` 由接入者按真实身份补齐 |
| `guidance/` | `harness/version-requirements/guidance/` | 获授权的 Agent/人员执行阶段；不是额外安装的 Skill |

R/AC 仍在 `requirements/items/`；来源、scope、Q、Review、BL 等仍在 `requirements/versions/<Version>/`。本库、测试夹具和教程不保存业务状态。OpenSpec A/B 与 Superpowers 的现有安装和唯一来源保留；选用此层后，两条路线都另用同一 Python venv，不切换 OpenSpec 来源。

项目配置须明确`ui_design: not-adopted`或`enabled`。UI需求层仍在集成验证：G0/G1保留原业务职责；G2、Standard G3、scope/Tiny已有共同UI检查及隔离链路证据；G4已接入当前组合，恢复、整链及实际采用资格尚未全部验收，不能据此作完整业务采用。采用时按[需求层UI接线](../ui-design/requirements.md)同时准备共同工具、严格policy、固定绑定及原Review/E，缺件不得降级为不采用。

`ci.py` 不属于首次S0～S4试用的必需入口。选择其他CI宿主时，按[平台适配说明](../../examples/version-requirements/README.md#已准备运行时中的平台适配)复制并审阅该文件及阶段 YAML，提供宿主独立观察的HEAD和受保护配置要求的阶段；当前适配边界测试不替代托管保护验收。 GitLab 的宿主配置、Runner、快照输入和 MR 验收步骤见[GitLab 接线](../../examples/version-requirements/README.md#gitlab-接线步骤)。

## 安装、重试与保护已有文件

在明确的业务仓库根目录操作。首次接入先查看 Git 差异，再清点上表本次采用范围内的目标及 `.harness/version-requirements-venv/`。原稿目录另按 S0 保护，不属于安装器的覆盖范围。

1. 在项目外登记本次准备目录和备份位置，逐文件保存已有同名目标及摘要；备份核对完成后才有恢复依据。没有同名目标时，将上述副本先放入临时 staging 目录，检查文件集合、语法和依赖。
2. 对照 staging 与业务目标：相同字节保持不动，缺文件可补；已有不同字节先确认是否用户定制，不能整目录强制覆盖。按文件完成复制并记录已安装/未安装集合。模板版本采用来源提交和逐文件 SHA-256，安装清单保存在项目 `.harness/` 的安装记录中，不代表产品批准。
3. 中断后读取实际目标、清单和原始备份，核对已完成部分再补缺，不重写成功文件。发现未知改动保留并报告差异；复制不是多文件事务。不要删除整个 `harness/` 或 `scripts/` 来重试。
4. 将 `.harness/` 加入项目忽略规则。安装 Python 3.13 的项目隔离 venv，固定依赖见下方；不全局安装 Doorstop、BMad、Spec Kit 或另一组 Skills。
5. 首次运行先确认入口能显示帮助、公共预检与准确的非零诊断。缺少该阶段必需的业务输入不等于安装失败；未知 phase/subject 必须明确拒绝，不能改为绿色占位实现。各阶段的前提与验收按 guidance 执行。

终端：业务仓库根目录。先确认此位置没有既有 venv；有则查询/核对，不能用创建命令覆盖未知环境。

```bash
python3.13 -m venv .harness/version-requirements-venv
.harness/version-requirements-venv/bin/python -m pip install \
  --require-hashes -r harness/version-requirements/config/requirements.lock
bash scripts/requirements-check --help
```

每步确认退出 0 再继续。当前同一锁文件已实测 macOS arm64 和 Ubuntu 24.04 x86_64（含 Windows 托管环境中的实际 WSL2）的 CPython 3.13 wheel 安装、运行时预检及入口帮助；这不等于各平台的完整工程流程都已验收。其他平台应先资格验证并扩充同一锁文件的允许 wheel，不能删除哈希限制或隐式升级。离线安装先取回与当前平台及锁文件一致、已经核对摘要的 wheel，再加 `--no-index --find-links <已核对目录>`；macOS 缓存不能代替 Linux 专用 wheel。网络/包缺失保留原始日志并停在准备阶段；使用精确路径，不用 PATH 的 `doorstop` 顶替。

`config/doorstop.yml` 是创建需求文档后的初始配置材料。逐项审阅后按 [S4](guidance/s4-baseline.md#显式保存原生审阅标记)调用 `review.py`：官方 review 在临时副本生成标记，封装保留全部原字段值并经官方 strict 复核后才写回。直接运行原生 review 可能把较长的嵌套路径添加换行，不能用于这些正式记录。正式检查永不调用 review/clear/edit，只对按固定内容和历史配置分组的临时投影执行 strict。原生字段并非三方批准，报告也不是批准凭证。

采用 `supersedes` 或 `retires` 的当前条目前，核对业务 `.doorstop.yml` 已将相应字段列入 `attributes.reviewed`；默认模板现包含两者。配置变化须复核当前内容及 Review，再建立新的内容提交；历史 BL 继续使用当时固定配置，不回写旧配置或旧 R。

升级同样先备份、比较和按文件合并；未知 Schema/规则停止读取，不让旧工具降级理解新数据。移除工具时只移除已确认由安装产生且未被定制的工具副本/venv；保留 PRD、R、BL、控制/编号、标签和历史证据。工具回退不能撤销已经发布的业务决定。

已有候选合并后升级工具，继续按 [S6 检查器升级后的接续](guidance/s6-delivery.md#检查器升级后的接续)固定当前目标、工程审阅和实际验证。安装完成或历史查询通过都不替代 current 整合准入；先保存工程 Review，再固定测试提交，避免测试后更新 Review 使最终检查失效。

## 安装后怎样使用

在业务根目录按[规则合入与试用步骤](../../tutorials/project-integration.md#7-隔离试用-version-requirement-layer)，将需求层路由合入项目 AGENTS，再从已复制的 `harness/version-requirements/guidance/README.md` 选择真实阶段。每份指引说明应准备的输入、实际责任、保存顺序、检查命令和失败出口，日常操作从这些项目内指引接续。

`requirements-check` 与报告入口保持只读；`review.py` 是单独显式调用的机械写入封装。原稿接收、需求提取、审阅记录、固定引用及 Git 发布由获授权的人员/Agent 按指引显式完成，不存在一条自动把 PRD 转成已批准 Change 的命令。先完成上游隔离试用；只有明确选择工程接续试用时，才按 S5/S6 使用已经提供的检查与项目规则，并保留尚未验收的边界。

下面的数据模型和库接口供编写记录、排错或工具集成时按需查阅，不是逐项调用全部模块的业务流程。可复制指引只依赖安装清单中的材料；本页与后面的维护测试入口保留在教程仓库。

<details>
<summary>数据模型与 API 参考</summary>

## 数据与公共接口

`schemas/vr.schema.json` 管单一首次发布合同，当前检查／规则身份为 `vr-check/2`、`vr-rules/2`。领域记录继续使用 `vr/1`，UI输入信封使用 `vr-ui-inputs/1`；每种具名模型只接受其确切格式和完整实现身份。不存在旧profile或跨版本规则路由，historical只复算本合同运行后形成的固定业务时点，不执行历史仓库源码。

Schema 的具名模型见 [vr.schema.json](schemas/vr.schema.json)。所有顶层业务记录显式带 `schema_version: vr/1`，R 同样包含此字段，并列入 Doorstop reviewed 属性。除明确作为机械信封的 `event.payload` 外，未知字段拒绝；不允许 `tasks`、`ready`、CI 或批准布尔值混进 R。未来事件正文只是可读取数据，不获得业务执行权限。

R ID 保留原拼写，数字相同的不同拼写（如 R-001/R-0001）不能作为两个身份。检查当前内容提交的正式 R 文件名、scope 和固定历史闭包，并在原配置分组之前拒绝别名冲突；不自动重编号，不把无关草稿正文纳入验收。相同确切 ID 的不同固定修订仍可分别读取。scope 中仅排除来源片段不需要 R ID；同时声明被排除 R 与固定 predecessor 时，必须是同一稳定身份。

明确排除的 R 必须能解析到实际文件/配置或固定 BL 选择，取消 Q 须覆盖该对象。取消语境进入批次/工程 Review 与 BL 清单，不扩充交付分母；仅被取消的未批准本地草稿不要求原生 review，不展开其遗留规划关系。纳入、背景或历史 BL 角色的原检查仍有效，缓存读取不能取消原生检查义务。具体操作见 [S2 范围处理](guidance/s2-requirements.md)。

YAML 使用 PyYAML SafeLoader，支持 JSON 可表达的对象与无环别名；重复键、非字符串键、对象标签、递归/过量展开、非有限数均拒绝。日期/时间加引号，原件字节不重写。单个结构化文档上限 16 MiB、嵌套 64 层、展开一百万节点；这些限制不约束原始媒体文件体积。文件身份对原始字节计算 SHA-256，派生结果的 `input_digest` 才对确定顺序的 JSON 表示计算摘要。

`when` 缺省表示 always，显式 null 保留 unknown；Schema 可接受该未知形状，业务 Gate 必须按当前阶段阻断适用未知条件。Schema 自检通过不是依赖可行性或需求批准。

| 公共模块 | 输入与结果 | 边界 |
| --- | --- | --- |
| `core` | YAML/JSON、路径、原始字节摘要、只读快照 | 不修复、写回或分配身份 |
| `models` | 具名 Schema 与 JSON/YAML 对象；带字段位置的错误 | 不获取远端 Schema；未知版本拒绝 |
| `gitstore` | 完整 commit/path/sha256；读取实际 blob 和输入清单 | 不使用浮动分支替代固定输入，不跟随链接/子模块，不 fetch 或改索引 |
| `context` | typed subject、阶段快照、version 与受控远端身份 | current 核对最新远端；historical 固定历史且不放行当前动作；不自动切换模式 |
| `report / metrics / readiness` | 固定 scope/来源/map/Trace/E/control 的四组指标、当前候选就绪及冲突明细 | [指标](guidance/s7-completion.md#持续查看来源分配验证与阻断)保留全部 AC 分母与六种状态；[就绪观察](guidance/s3-engineering.md#查看当前候选的就绪与阻断)保留全线容量和逐候选阻断。只写新派生目录，不发布状态、预占、批准或动作 |
| `backend` | 确切 R 字节及各自原配置 | 前检原生 stamp/重复 UID，分组投影，后检字节/mtime；错误不转为批准 |
| `control` | 固定发布索引、event_ref 与编号预留 | 只读机械信封，区分重复投递/重写；不消费 hold、计算占额或批准 Apply |
| `control_holds` | 已发布 hold/unhold/停止确认及其首次控制前驱，派生逐对象/入口限制 | 独立入口只消费暂停类事件，和容量组合的读取由 `control_delivery` 负责；改写/越界解除拒绝，停止确认不解除 hold。G2/dispatch/planning/apply 组合消费，不单独授权执行；G3/pre-archive 消费 Change/Task 的 Apply 限制，pre-merge 另核对 Merge 限制。Agent 按 [S6 任务边界](guidance/s6-delivery.md#任务边界暂停与恢复)显式检查，实际停止/恢复范围见验证说明 |
| `control_delivery` | 复用发布历史和暂停消费者，读取 dispatch/对齐的固定输入，派生本线跨 Version 预占和容量 | 预检不占额，发布后才纳入。提升保留原名额，不清 hold；G2/dispatch/planning/apply 与 G3/pre-archive/pre-merge/integrated 使用该消费者；名额释放按原集成结果复算，发布后派生完成历史，未知事件拒绝；发布与占额见 [S5](guidance/s5-dispatch.md#串行发布控制事件) |
| `dispatch / handoff` | 原有效 BL、当前受审 map/计划、原事件、目标/控制、留存和派生引用包 | 未 Propose；到期实施前置按当前目标证据核对，候选提供者须另复算本线实际集成 Trace。草稿不授予许可，当前发布确认后才可接续原 Propose 请求；同一事件可重查，不重复占额。历史 Trace 不能退回初始阶段；不发布、不生成 Feature Tasks、不批准 Apply |
| `openspec_artifacts` | 原 CLI 观察、实际 Schema/locator 和固定 Git Artifact | 只读核对，不运行 CLI/模型；支持内置 spec-driven 与仓库内路径，外部 store 明确拒绝；Tasks 可附加[固定证据引用](guidance/s6-delivery.md#追加与纠正-tasks-证据引用)，不把正文变化或引用存在当作完成证明 |
| `change_assets` | 复用原资产解析器，在同一 Trace 读取 Change 派生物的固定制作输入/输出 | 注册修订不可覆写；规划清单与归档定位分开核对，不转换文件或代替实施资产/构建审阅；见 [S5](guidance/s5-planning.md#change-自有派生素材) |
| `planning_trace / planning` | 原 BL/预占、当前受审工程输入、实际 AC/Spec/Scenario/Tasks/验证义务及规划 Review | G2/planning 及实施前后受审修订；对齐预检/发布确认保留同一名额，不授予 Apply；实施后修订绑定已有执行输入，Apply 由 execution 复用检查；Change 派生物在原 Trace 登记并核对当前使用/归档定位；交付由独立 G3 检查 |
| `planning_applicability` | 当前工程 Review 中的原批准、完整目标差异和实际影响结论 | 仅在原发布/批准及已有 Apply/修订语境可复核，规划/Schema/关联未变时允许 no-impact 沿用；不替代 Update 或自动判断语义 |
| `worktree` | 实际 HEAD、工作区文件和独立暂存状态；可选输出固定差异字节 | current Apply 与实施后规划 Review 的实际输入检查；捕获工具只写新的仓库外证据目录，不提交/执行/授权。符号链接只保存链接文本；执行输入不据此推断目标内容，见 [S6](guidance/s6-delivery.md#保存未提交输入的运行证据) |
| `execution` | 原预占、当前有效规划与独立实施请求 | 实际工作区的首次/恢复 G2/apply；恢复复核原准入且读取当前 Tasks，仅 current 且 execution 已发布、Apply 限制解除时输出当次许可和授权 Task 范围。由 Agent 在任务边界显式调用，不运行 Agent/TDD；G3/pre-archive 复用本准入 |
| `verification` | 固定 E、受检提交、调用方提供的构建/环境等身份、实际报告与测试定义 | 校验零匹配/跳过/失败、定义文件和不可变历史；内部接口不单独证明依赖就绪、集成或 G3 通过，详见[工程运行证据 E](#工程运行证据-e) |
| `delivery_trace` | 同一 Trace 中的实际 Task/实现/E 引用，当前 map/CLI 观察和调用方独立提供的执行期望 | 复用固定 E，检查已提交输入适用性及局部贡献关联；不授予 G3、到期集成条件满足或归档许可，字段和保存顺序见 [S6](guidance/s6-delivery.md#在同一-trace-中补齐交付引用) |
| `prearchive` | 实际 G3 阶段快照、原 Apply 准入、交付 Trace/E/Review 和当前控制 | G3/pre-archive 只读核对实际归档前条件；已有/外部到期集成条件另需组合覆盖，不授予归档动作或释放名额，详见 [S6](guidance/s6-delivery.md#g3-归档前检查) |
| `archive` | 原 CLI Archive 输出或既有 Skill 的真实移动过程、归档前/独立归档提交、原规划观察及同一交付 Trace | 核对完整移动、Task/链接与主 Spec 引用；派生当前定位并关联归档后实际 E。内部读取不替代 Sync 语义审阅或 G3/pre-merge，见 [S6](guidance/s6-delivery.md#同一-trace-的归档后交付引用) |
| `final_checks / premerge` | 原最终命令/输入、实际归档、原 pre-archive 准入、当前控制及最终 Review/请求 | G3/pre-merge 的 Standard Change 组合；保留真实受检 C 与证据 D 区别，消费 Apply/Merge hold，不合并、释放名额或证明托管 CI；操作及支持范围见 [S6](guidance/s6-delivery.md#g3-合并前检查) |
| `tiny_delivery` | 有效 BL、原任务／PR 关联、当前工程 Review、主 Spec、实际 E、最终命令及实际 Merge | G3/pre-merge/integrated 复用最终检查、Review 和 Git 集成读取；消费 hold，不造 Change/Tasks/Archive，不预占或释放候选名额；[Tiny 操作](guidance/s6-delivery.md#tiny-任务pr-的交付核对) |
| `integration` | 原 pre-merge 快照/完整结果、真实源提交与合并结果、操作证据及责任确认 | 内部复算原准入并比较本线实际工程内容，保留 squash/rebase 前的原受检/归档身份；变化完整返回，不等同于 G3/integrated、贡献满足或名额释放，见 [S6](guidance/s6-delivery.md#原准入与实际集成事实的内部读取) |
| `integrated` | 同一 Trace 的实际集成观察、原准入、当前工程输入/Review、本线实际内容和 E | G3/integrated 核对该候选的 AC/能力贡献；squash 不改写原受检提交，实际差异须有适用证据，当前 hold 保留；不发布名额释放或宣称 Version 完成，见 [S6](guidance/s6-delivery.md#g3-合并后检查) |
| `scope_delivery` | 有效 BL、现有 scope/map/plan、当前工程 Review 与真实 E | 直接核对已有／外部交付的 Version/R/AC；保留 hold 与未来整版义务，不创建 Change 或释放名额，见 [S6](guidance/s6-delivery.md#无-change-的交付核对) |
| `integrated_receipt` | 现有 evidence 目录中保留的原始 current integrated 快照与完整输出 | 复算原 Gate；供名额释放和当前候选依赖共同消费，不建立完成数据库。单次只读查询内复用相同固定证明时仍保留完整输入审计；保存的 PASS 不成为权威状态 |
| `runtime` | 唯一锁文件、固定官方关键源码和完整安装身份 | 缺包、版本/源码或受审安装身份不符退出 2；不联网修复，不执行旧仓库源码 |
| `markdown_source / sources` | 固定原稿、全包 DOC/AST/SRC、链接和接收历史 | 全量枚举，保存原文/规范化目标，外置内容只取已明确留存的固定字节；不写 manifest |
| `assets` | 固定文件/所有者 manifest、派生输入/输出、使用边及完整 Git 修订历史 | G1 的 Requirement 与 Review 检查复用 `AssetIndex.check_manifest / resolve_use`；保留确切制作输入，不复制、转换、执行脚本或批准含义 |
| `reviews` | 实际职责、固定证据、完整输入与具名检查绑定 | 不创造业务判断；工具规则或来源变化不能静默沿用旧 Review |
| `review_scope` | 从 source/scope/R/原配置、关系/派生/Q 及 map/验证计划计算实际绑定范围 | 检查 S1～S3 具名检查、明确批次 R 覆盖和当前 Q 适用性声明；业务/工程真假仍需人工判断，历史 BL 生效不由本库证明 |
| `requirements / questions / relations` | scope 下确切 R/配置、来源反向映射、Q 落实与阻塞、层级/历史闭包和业务关系 | 供 S2 和 G1 复用；候选阶段死锁归 feasibility，历史 BL 的批准/生效归 baselines，单独读取记录不证明基线有效 |
| `delivery / feasibility` | 固定 map/验证计划/工程 Review、确切贡献与阶段条件 | 供 S3 和 G1 复用；检查全量分配、关系处置、验证责任与有限容量顺序，不代替完整 Review 或当前释放判断；语义和工程证据真实性仍需实际审阅 |
| `baselines` | 组合 G0、S2/S3、Review、原生检查、内容清单、批准/控制/留存与实际发布 | content/record/effective 及显式历史 BL/前驱链；逐份核对原批准/配置、发布、编号与留存，缺历史语境拒绝。不创建批准、发布引用或消费执行权限 |
| `report / rendering / engineering_view` | 同一固定输入的 Catalog、逐 AC 阅读、资产定位及 S3 分层图/诊断 | 只写显式新建派生输出；允许呈现开放 Q，不批准、不回写；[S2 报告](guidance/s2-requirements.md#生成-catalog-与阅读报告)与 [S3 视图/筛选](guidance/s3-engineering.md#生成分层依赖与待处理事项视图)；不计算当前 ready |
| `impact` | 固定新旧来源/scope/R/map/验证计划、实际 Git 差异与 Trace | 同一报告入口的 `--view impact` 生成保守审查集合，保留已删除关系、共享消费者和未映射差异；[操作说明](guidance/requirement-change.md)。不推断执行顺序、不批准 RC 或恢复执行 |
| `requirement_changes` | 原 RC 的提出/影响/决定/新 BL、逐对象对齐/验证及终态入口恢复事件，沿同一已发布控制引用读取 | 复算旧新影响、核对三方决定与获批 C/新 BL；`--view changes --event-ref` 提供只读预检或确切发布确认。跨 BL G2 恢复保留首次 Apply/名额；Standard 整改经独立 Merge 恢复、完整 G3 和名额释放后逐对象验证 RC，其他 hold 保留。有限隔离范围见[操作指引](guidance/requirement-change.md)；独占未集成工作可经 `cancellation` 核对停止/留存/清理，取消释放不进入成功交付集合；未 Propose 的取消和纯上游处置保留后续交付义务，关闭后仍按实际阶段逐项恢复 hold；共享 Change 部分取消保持原名额并沿剩余贡献的实际 G3 完成交付与 RC 处置；已归档未合并的返修/整项取消分别保留旧归档和正确交付路径。集成后退役与广域恢复已有隔离证据；G4 另按 [S7](guidance/s7-completion.md)核对完整版本 |

统一入口使用 `--root / --gate / --phase / --subject / --context / --format`。退出 0 仅用于全部适用规则执行通过，1 为已能判断的条件不满足，2 为输入/工具不可读或不支持。支持的阶段见上方能力表；历史 BL 采用固定 baseline_contexts 逐份复核，操作和固定规则边界见 S4。后续复核旧发布点时，快照成对提供 publication_revision/publication_evidence_ref；不凭 Git 祖先自动猜测发布。解析输出保留 current/historical、Version、line、metadata/head/target/control、实际读取摘要与执行规则文件摘要，错误不可静默吞掉。

工程接续接口允许 `DeliveryIndex(requirements, engineering_context=..., map_ref=..., verification_plan_ref=...)` 分开读取固定需求与当前工程输入。两者必须属于同一 Version、交付线和权威配置；原 R/来源/scope/批次审阅不随工程提交移动。map/计划可以先于工程 Review 保存，显式引用须保留原提交，并在 Review 所在提交核对相同字节。`ReviewScope.check_engineering()` 只核对本轮完整工程审阅；调用方仍须先核对原 BL 生效、当前控制和依赖证据，内部接口通过本身不是 G2；初始预检由 dispatch 组合这些检查。S3/G1 不传这些参数，沿用原内容绑定。当前工程 Review 额外绑定当前 Q；未变 Q 的落实提交来自原批准语境，新增/修改 Q 须明确固定落实引用。审阅过开放 Q 不表示它已经解决，候选 Gate 另核对当前阻塞。

来源解析固定采用 markdown-it-py 与 mdurl；它们与原有 Doorstop 报告依赖承担不同职责，全部版本仍只由 `config/requirements.lock` 维护。S0 的 Markdown 方言、原始/解析字符串、非文本片段摘要与外置资产取回边界集中在 S0 指引，不把解析结果等同真实产品理解。

## 当前依赖可用性

可用性依据保存在同一工程 Review，字段、到期条件和 planning-only 边界集中在 [S5 当前依赖可用性](guidance/s5-dispatch.md#当前依赖可用性)。候选提供者通过 `provider_integration` 关联当前目标上的原集成证明，见 [S5 工程反馈](guidance/s5-dispatch.md#把实际集成事实用于后继候选)。库不创建另一份 ready 状态表，记录引用也不自动释放容量。

## 实际规划观察与 Trace

`openspec_observation` 绑定真实 CLI 的 Schema/status/Apply 上下文/strict 输出和捕获时的完整工程输入；它保存观察引用，不复制工程方案。实际 locator、适用 Artifact 和固定文件必须一致；缺可选 Design 不仅由 isPlanningComplete 判断，合法无 Delta 可引用正确主 Spec。原生 Change 元数据的日期采用窄解析适配，Requirement YAML 规则不变。

`planning_trace` 将当前候选的逐贡献 AC 关联到实际 Spec/Scenario、显示 Task 编号和受审验证义务，保留原 BL、最新对齐、观察及资产使用引用。先保存 Trace，再由同一 Review 模型保存 `reviews/planning/C-NNN.yaml`，避免互指未来提交。初始规划与实施后修订详见 [S5 保存顺序、字段及复查](guidance/s5-planning.md)。实际实施/运行引用追加到同一文件的可选 `delivery`，字段及内部检查边界见 [S6](guidance/s6-delivery.md#在同一-trace-中补齐交付引用)；不提前填写未来完成状态。新对齐的预检不发布，发布后的确认不新建名额，planning 通过不授予 Apply。

原批准的当前适用性放在同一工程 Review 的 `engineering.planning_applicability`，字段与沿用/失效条件见 [S5](guidance/s5-planning.md#工程输入变化后的批准适用性)。实际实施请求采用 `apply_request`，固定原预占、适用规划 Review/摘要及 Task 授权范围，快照用 `apply_request_ref` 引用；保存位置和初次检查见 [S6](guidance/s6-delivery.md)。既有授权在范围仍适用时持续有效，记录绑定不增加每次重批的要求。实施状态恢复由快照的 `apply_origin_ref` 固定最初 current 准入；复核实际原输入后再查当前控制/规划，current 的 Tasks 状态从实际工作区派生，historical 从固定 head 派生，不信任旧 PASS 或另建完成状态。 嵌套历史复核只按其自身读取核对留存，返回后保留完整外层审计；不把调用方新控制提交错误算入旧准入的 pin 义务。实施后 Update 在 G2/planning 快照增加 `planning_inputs_ref`，同一规划 Review 再绑定实际执行输入与 update-impact/execution-state 检查；新请求通过 `planning_snapshot_ref` 指向该次固定规划语境，当前 Apply 先历史复算它再检查当下输入。步骤集中在 [S5](guidance/s5-planning.md#实施开始后的规划复核与-update)，两项引用不成为批准或 Tasks 的新来源。

## 工程运行证据 E

业务落点为 `requirements/versions/<Version>/trace/verification/E-NNN.yaml`，使用 `verification_record` Schema。一次真实执行一个 E，保存后不改写；重跑另建 ID，失败记录和原日志保留。记录是运行观察，不能保存可手改的当前 ready、Tasks 或 CI 状态。它是交付检查复用的内部读取能力，不单独授予阶段权限。

记录绑定以下输入：

- `tested_revision` 与 `input_refs`：实际受检提交及其中的代码、测试定义、配置/资源；日志和 E 可以在后续元数据提交保存。已提交输入使用固定 ref；未提交输入另绑定 `worktree_diff_ref`，实际路径用 `{path, content_ref}` 引用捕获的普通文件字节，不伪造提交。完整捕获/留存操作见 [S6](guidance/s6-delivery.md#保存未提交输入的运行证据)。
- `identities`：`build_ref / dependencies_ref / configuration_ref / environment_ref / data_ref`，均为带完整提交/路径/摘要的事实引用；无额外构建、外部依赖或数据时引用实际说明，不能省略成未知。不同角色可指向同一份完整运行清单。执行人/CI 身份、起止时间和 `execution_ref` 保留本次原始过程。
- `cases`：稳定 ID 与 `definition_ref`；自动测试另有报告的 classname/name。`coverage` 只记录这些实际 case 对确切 R 修订/AC 或技术贡献的观察关联；Requirement 的记录及配置引用保留历史身份，不在 E 重写行为要求。覆盖含义仍须 Review 核对。
- `automatic`：真实命令参数、执行目录、`source_root`、退出码、原报告固定引用和用例计数。当前解析器接入 UTF-8 JUnit，已实测 Node 的原生报告；按报告中的定义文件及 classname/name 精确选择目标，重算发现/执行/通过/失败/跳过数。只有退出 0、目标全部实际通过且没有报告失败才可记录 passed；未选且确实无关的跳过不充当覆盖。无文件定位、其他报告格式或未知结构不能静默推为通过。
- `manual`：实际步骤、逐个稳定 step ID 的观察/证据和具名验收决定，不能只填一句已验收；人工演练用的 synthetic 决定须明确标注，不当真人签名。

自动执行的 `execution_ref` 指向实际运行时保存的 JSON 过程记录，使用 `execution_receipt` Schema：受检提交/差异、输入与五项身份、执行人/起止时间、命令/目录/报告格式/退出码及 `report_ref`。读取器逐项与 E 核对；过程记录中的报告、工作区差异及捕获字节引用可省 commit，此时仅从该过程记录所在提交解析，避免自引用提交哈希循环；保存 E 时填写完整引用。修改 E 的 SHA 不能把旧过程和报告重新标成新测试。它校验已有过程记录的一致性，不认证可同时伪造全部输入的执行者；受控 CI/宿主来源仍须单独验收。

内部 `check_execution(context, reference, tested_revision=..., identities=..., worktree_diff_ref=None)` 只读固定 Git 对象，不执行命令、不访问报告中的源目录、不发布或授权。调用方必须从当前受审工程语境取得所需提交和身份；不得把 E 自报的旧值原样传回，就声称适用于新的目标。默认 `worktree_diff_ref=None` 只接受已提交执行；读取 dirty E 时，调用方须明确给出期望的同一固定差异引用。dirty PASS 不自动提升为基准提交 PASS，已有/外部提供者的当前可用性仍只接受相应已提交证据。历史失败可用 `require_pass=False` 读取，但不会获得交付许可。代码演进后的适用性、完整输入范围、合并事实和逐贡献满足由后续 G2/G3 与工程 Review 组合判断；不能靠提交祖先关系提升旧 PASS。

</details>

## 维护测试与证据

维护者在教程仓库使用独立临时环境执行 [公共回归](../../tests/version-requirements/runners/intake/test_public.py)与[来源/G0 场景](../../tests/version-requirements/scenarios/intake-package/scenario.yaml)。测试工厂提供标明 synthetic 的读取/决定输入，不能安装进业务项目，也不证明真实 Agent 语义或三方批准。上游历史结论见 [上游基线验证摘要](../../tests/version-requirements/README.md#goal-02)，后续工程能力逐项记录在 [滚动交付工具验证摘要](../../tests/version-requirements/README.md#goal-03)。
