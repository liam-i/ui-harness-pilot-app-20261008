# 已采用需求层时如何消费 UI

[返回交付目录](README.md) · [数据合同](data-contract.md) · [需求层阶段指引](../version-requirements/guidance/README.md)

本文说明需求层的共同 UI 输入及原阶段接线。人工团队和 AI 制作的包使用同一合同；制作过程不进入工程 Tasks。当前仅有已声明范围的隔离验证，完整采用资格仍须满足需求层入口列出的验证边界。

## 安装与职责

在业务项目中同时安装 `harness/version-requirements/`、本目录全部文件及各自 `scripts/` 入口，按[离线安装](offline-check.md#安装与前提)核对 UI 依赖；需求检查使用项目的需求层 venv，也须能导入 UI 锁定依赖。项目配置明确 `ui_design: enabled`，固定 UI policy 的 `adoption.requirements` 为 `adopted`。完整实现身份包含实际调用脚本、库、Schema 和锁；缺件或未知能力停止，不能临时改成 `not-adopted` 放行。

职责沿原流程保留：Version PRD/R/AC/BL 定义业务承诺；delivery-map 分配真实贡献及 UI 适用性；设计包定义被确认的界面输入；工程 Review 选择本轮消费合同；OpenSpec 保留唯一 Feature Tasks；原任务／PR 保存 Tiny 工作；E 证明实际受检组合；原控制、请求和 Gate 决定相应工程动作。

UI 与业务承诺矛盾先回共同 Q/R。已基线化的业务变化沿原 RC；纯视觉修订只重评实际消费者及相关工程审阅。G1 不要求整版高保真齐备。

## 按依赖顺序保存输入

1. 在本 Version 的 `delivery-map.yaml` 增加 `ui` 数组，独立审阅全部实际 allocation/capability 的适用性。每行包含真实 `contribution` 及 `behaviors`；业务行为格式为 `R-001/r1/AC-01`，技术能力行为为完整贡献 ID。不涉及 UI 时明确空数组；不能漏掉某个贡献，不能从现有设计覆盖反推业务分母。
2. 按共同合同恢复真实已批准 A、内容 D 及依赖闭包，核对当前决定。准备本地 `harness/ui-design/config/project.yaml`；实际身份、权威和角色依据须可取回。包在独立仓库时保留原 repository 身份及固定引用。
3. 保存本 Version 的 `ui-bindings.yaml`。候选／端点绑定到已保存 map 的实际 allocation 或 capability，并使用准确的 `identity_pointer`；Tiny 绑定原任务和实际 `tiny_association`，不创建候选。覆盖、允许差异和不适用依据均受审，不能以 URL 或 mutable ref 替代固定 A。
4. 在原 `trace/evidence/` 保存一个不可改写的 `vr-ui-inputs/1` JSON，包含 `rules`、本地固定 `policy_ref`、`bindings_ref` 和完整 `authorities`。`rules` 取自已安装共用库的实际身份；`authorities` 固定已读到的 repository/ref/history_root/commit。以后输入变化使用新的记录路径，保留原件。
5. 在原 `reviews/engineering.yaml` 的 `engineering.ui_inputs_ref` 引用该记录，按原工程审阅程序计算完整输入摘要并保存实际结论。审阅输入可以先于 Review 保存，不能互相引用尚不存在的提交。
6. 本次原 Gate 快照增加 `ui`，仅提供 `repositories`、`authorities`、`external_files` 三类恢复/观察信息。填写实际本地 Git 路径和当前权威提交；外部对象以原 URI、version、sha256 对应已经恢复的本地 path。所选贡献、任务和 new/existing 资格由原工程入口推导，快照不能自行缩小分母或声称已有准入。

字段的严格结构见已安装的[需求 Schema](../version-requirements/schemas/vr.schema.json)和[共同 UI Schema](schemas/ui.schema.json)。固定引用使用真实 `commit/path/sha256`；UI 跨仓库引用另带 repository。本地输入记录中的 policy/binding 引用属于业务仓库，不把外国 Git 对象当成本地对象读取。

map 后续补 E 或 availability 不必重写未变的消费定位。检查器核对当前精确 map 与旧定位指向的整个 allocation/capability 身份一致；分配、R 修订或 AC 变化不能借此沿用旧合同。不以新摘要代替实际适用性审阅。

## 接续原入口

| 原入口 | UI 输入与通过后的含义 |
| --- | --- |
| G1 | 完整贡献的 UI 适用性进入工程审阅；不强制全部包已经制作 |
| G2/dispatch、planning | 固定所选候选合同及共享闭包；沿原 Review、Propose 请求及占额规则。planning 不授予 Apply |
| G2/apply 首次／恢复 | 重查当前 UI 和业务 target/control；同一已审合同按原适用性规则接续，实质变化回原 Update/整体审阅 |
| Standard G3 | 原 pre-archive、Archive、最终检查、pre-merge、实际 Merge、integrated、slot-release 继续各自负责；UI 不替代任一项 |
| scope G3/integrated | 从原所选 AC 推导完整端点贡献，固定 UI 输入、工程 Review 和实际 E；含未交付候选的 AC 不能走 scope 旁路 |
| Tiny | 开始／恢复使用下节任务边界；交付仍使用原 G3/pre-merge、integrated、原任务和真实合并观察 |
| G4 | 按下节当前组合另核完整交付分母、真实构建与最终 E；completion、release、操作观察和后验保持独立 |

原工程 Review 增加 `ui-applicability`；需要具体合同的原规划／交付 Review 同时包含 `ui-inputs / ui-coverage / ui-delivery`。它们使用原 `review_input_digest` 绑定原工程引用和本地 UI 固定输入，不产生第二份审阅状态。

实际 E 的 `input_refs` 必须包括本次接受的不可改写 UI 输入记录。它固定 policy、bindings 及完整规则身份；原 E 同时保留真实代码提交、五类运行身份、测试定义、报告、覆盖和视觉验收证据。后保存 Review 或 E 的提交不是受检代码提交。共用库验证固定包和决定，不从截图自动判断实现符合设计。

可选 `engineering.ui_metadata_refs` 只列出经共用闭包验证、工程审阅提名的精确被动设计文件。不能整目录豁免 `design/**`；脚本、drafts、外逃引用、源码及直接进入构建的文件仍为工程输入。原素材 owner 不变，不将 AST/DAS 复制成第二套 UI 资产账本。

## Tiny 开始与恢复

先保存原任务的范围、真实实施授权和固定关联。采用 UI 的 `tiny_association` 显式提供 `ui_behaviors`；关联业务 UI 时覆盖当前对应 R/AC，没有业务义务的工程 UI 任务使用自身明确行为，不伪造 R。

使用该任务准备中的原 `G3/pre-merge` 快照，其中包含有效 BL、实际 head/target/control、当前工程输入、`tiny_ref` 和 `ui`。不要求尚未发生的最终检查、Merge 请求或 E。以下是业务根目录中的只读调用示例；`context.json` 必须是本次真实快照，`resume` 可替换为首次 `start`：

```bash
.harness/version-requirements-venv/bin/python -I -B - \
  '/absolute/path/to/context.json' resume <<'PY'
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path('harness/version-requirements').resolve()))
from lib.gitstore import GitStore
from lib.tiny_delivery import check_boundary
from lib.errors import CheckError
try:
    result = check_boundary(GitStore(Path.cwd()), json.loads(Path(sys.argv[1]).read_text()), action=sys.argv[2])
    code = 0
except CheckError as error:
    result = error.diagnostic()
    code = 2 if error.unreadable else 1
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(code)
PY
```

保存精确命令、原始结果和退出码。必须为 current 且 `current_checked: true`；结果不授予工程权限，仍按原任务授权执行。接口推导全部关联控制对象，重查 Apply hold、实际未完成 Standard 历史和脏权威输入；允许保留任务中的实现修改，不删除工作来重新开始。

无 R/AC 的 UI 技术任务仍需要实际 E。E 的 `task_coverage` 固定原 `subject / tiny_ref / ui_behaviors / case_ids`；实际执行输入包括原任务、关联和 UI 记录。原 `coverage` 可以为空，但不能同时缺少真实任务覆盖。保存方式、最终检查与 Merge 仍沿[原 Tiny 指引](../version-requirements/guidance/s6-delivery.md#tiny-任务pr-的交付核对)。

## G4 当前组合与历史

在原 `release_candidate.delivery_receipts` 选择真实已经交付的回执，按原完整贡献分母分区。当前工程 Review 选择的 UI 输入记录另保留本轮相关任务绑定；过时任务在旧不可改写记录中保留，不把它混入当前组合。无 R 的真实任务允许空贡献选择，但仍需要实际 integrated 回执、当前任务绑定和任务运行覆盖。

构建的 `input_refs` 包含当前不可改写 UI 输入记录，最终 E 验证同一实际 target/build/environment。最终 E 除原验证计划到期义务外，可包含实际已选技术任务的 `task_coverage`；无关 E 不能塞入。三方原 G4 Review 追加 `ui-current-composition / ui-runtime-coverage`，绑定本次 UI 固定引用；三方真人职责要求仍按[原 S7](../version-requirements/guidance/s7-completion.md)。

候选曾用 U001、后续任务交付 U002 时，旧回执按当时语境复算，当前组合选实际替换回执与 U002。仅修改绑定不能成为已交付证明；遗漏贡献、任务回执、当前构建输入或运行覆盖均失败。旧 U001 只存于历史时不阻断当前产品；当前依赖闭包仍使用它时，按现有决定的禁止范围阻断。

发布成功而后验未齐时保留操作观察，只补实际后验并重查原 G4，不重复发布。历史结果无当前准入权限。

## 失败与恢复

在实际停点保留原任务、BL、合同、观察、Review、E、控制及原始失败。UI 权威独立前进时先查询真实差异；缺包或未知对象先显式恢复，禁止检查器自行 fetch 或切换最新包。撤回不自动取消工程、释放名额或重置恢复次数。

恢复到新目录时按原 repository 身份恢复完整 Git 对象，外部素材按确切 URI/version/sha256 恢复；当前快照只更新真实物理路径和重新观察的权威选择。原固定批准、业务回执、受检 SHA 和失败记录保持原字节。沿原 Update、RC、返修或任务授权接续，不能用 historical 的绿色绕过 current。
