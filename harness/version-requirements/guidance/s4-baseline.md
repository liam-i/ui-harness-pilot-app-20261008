# S4：内容检查与基线建立

[阶段约束与支持范围](README.md) · [前一步：S3](s3-engineering.md)

操作位置为已安装扩展的业务仓库。输入是 S0～S3 的实际来源、R/AC、scope、Q、工程分配、验证计划和审阅记录。S4 的完整目标是先检查内容 C，再批准并保存 BL 记录 B，最后确认目标线生效。

当前支持 **G1/content、record、effective**，并逐份核对明确引用的历史 BL、原批准/配置、留存和实际发布。历史引用需要下文的固定发布语境；缺件、未知原规则或非法前驱返回非零。不要删掉真实继承关系来取得通过。三阶段必须分别满足各自条件；内容通过、标签存在或 BL 文件存在都不能单独证明生效。

## 保存待批准的内容 C

1. 从真实 source/scope/R/Q/Review 恢复本版，不从 Catalog 或测试夹具生成批准。所有纳入 AC 已分配，来源的 pending 和阻断 Q 已按真实决定处理；S3 有实际工程起点、构建条件和负责人判断。
2. 按[审阅范围与最终封装](README.md#审阅范围与最终封装)核对 S0 接收、global、各批 batch 和 engineering 记录。来源/共同 Q 后续改变时比较实际差异并确认适用性，不盲目刷新摘要。
3. 对实际已审的 R 按下文显式调用 `review.py` 保存官方 Doorstop 标记，核对机械差异，然后绑定最终 R/原配置及上下文。检查器不会代为 review 或 clear；缺原生标记会被拒绝。
4. 审阅 diff，保存本次已确认的需求材料和所用工具/配置为 C。C 的工程字节须与已审 E 一致；从旧固定内容恢复时按下文对齐真实 E，不借资料提交引入未审业务代码。保留原始 intake 字节；无关草稿不加入 scope，也不因本次提交而获得批准。C 不依赖尚不存在的 BL 自身提交。

S2 对 `source/manifest.yaml` 的角色解释或 `source/units.yaml` 的来源处置/映射更新，也会改变原接收 Review 绑定的索引字节。最终封装时须核对每份 intake Review：比较它曾审阅的原件集合、字节、身份/定位与当前索引，复核本轮变化及原阅读证据是否仍适用，保存真实复核依据后再绑定最终索引。原件未变可沿用确切的既有阅读证据，不重新接收或伪称重新阅读；若原件、定位或含义发生实质变化，回到相应 S0/S1/Q 处理。不能只补 global/batch/engineering 而遗漏 intake，也不能只更新 intake 摘要来掩盖未审差异。

发给已获 S4 内容准备授权的 Agent：

```text
从现有 S0～S3 产物准备本版 G1/content。
核对原件、全量义务、共享 Q、实际工程依据和审阅差异，列出尚未满足的条件。
仅为实际已审 R 执行明确的机械封装，保存最终摘要和内容提交 C。
使用当前受控目标准备快照，执行唯一 requirements-check 入口并保存原始结果。
不得创建三方批准、将历史 BL 引用删除以绕过缺口，或开始 OpenSpec/Apply。
```

## 显式保存原生审阅标记

终端：业务仓库根目录。仅把下例 ID 换成已实际审阅的条目，不批量确认未审需求。

```bash
.harness/version-requirements-venv/bin/python -I -B \
  harness/version-requirements/review.py --root "$PWD" --requirement R-001
git diff -- requirements/items/R-001.yml
```

封装按当前单 R 文档策略，在独立临时 Git 投影中调用官方 Doorstop review，取回其 `reviewed` 标记，保留原记录的其他全部字段值，再执行官方严格检查。原因是原生 review 的 YAML 重排可能把较长嵌套路径添加换行；封装不重写官方指纹算法。成功时仅此条目的标记值改变，YAML 排版可能重排；核对 diff 后再固定完整摘要。输出 `changed: false` 表示标记相同，没有重写文件。它不提交、不暂存业务文件，也不批准 R 或 BL。

`supersedes`、`retires` 若被使用，必须进入当前 `.doorstop.yml` 的 `attributes.reviewed`；缺少时先审配置差异，不能从记录删除字段绕过。原历史 BL 仍引用当时配置。超时、原生失败或严格检查失败时原记录不写回；并发编辑被检测到时保留实际编辑并返回失败，重新阅读差异后再重试。调用期间对所选条目和配置保持单写者；最终检查与替换之间不是跨进程事务。缺失文件、符号链接和非法 ID 明确拒绝，不隐式改用全局 CLI。

## 执行 G1/content

先记录 C 与本次实际工程目标 E。工程 Review 的 code_ref、当前主 Spec 必须对应 E；current 模式还核对 E 是否确为权威远端的当前目标。不要用本地未发布分支的 SHA 冒充目标线。

在本次已登记的仓库外检查目录准备 `context.json`。下列是需要填写真实完整 SHA 的 JSON 形状，不能原样运行占位符：

```json
{
  "schema_version": "vr/1",
  "evaluation_mode": "current",
  "gate": "G1",
  "phase": "content",
  "subject": "version:v1.0.0",
  "version": "v1.0.0",
  "delivery_line": "main",
  "checker_version": "vr-check/2",
  "rule_version": "vr-rules/2",
  "metadata_revision": "<完整 C SHA>",
  "head_revision": "<完整 C SHA>",
  "target_revision": "<实际工程目标 E SHA>",
  "control_revision": null,
  "baseline_ref": null
}
```

Version/line/目标 ref 以实际 version.yaml 为准，示例不要求所有项目使用 main。content 允许尚无控制起点或 BL；首次 record 前仍须完成控制/留存接入。若已有控制快照，使用确切提交并核对其远端状态。

终端中令 `vr_check_dir` 指向上述已登记目录，确认输出文件尚不存在，每次运行保留独立结果：

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G1 --phase content --subject version:v1.0.0 \
  --context "$vr_check_dir/context.json" --format json \
  > "$vr_check_dir/content-result.json"
vr_exit=$?
printf '%s\n' "$vr_exit"
```

退出 0 且结果为 `G1.content / passed`，表示这份固定内容满足已实现的全部内容条件，可以提交三方批准。实际检查包括每个已声明 intake 的 G0、全量来源/R/AC/Q、贡献/依赖/验证责任、阶段可行性、完整 Review 绑定及官方只读 strict；不是只检查 YAML 形状。

`diagnostics[0].evidence.content_manifest` 给出由实际权威对象与审阅上下文计算的固定文件集合，供后续 BL 使用。它包括所有相应 Review、规则、原配置、源/派生闭包和明确使用的额外上下文；不把检查历史时偶然读到的每个 Git 文件都当成本次承诺。无关 R 草稿不增加本版分母。同样的 R/原配置在不同内容上下文中被选择时，各自的 scope/version 引用仍需保留。

例如 BL-001 与 BL-002 选择完全相同的 R/配置，后续内容同时引用两者：文件字节可以按确切引用去重，但两份 BL、各自 C 的 scope/version 和各自发布观察不能合并。实际历史上下文须逐份提供；不能用第一份 BL 的 effective 观察替代第二份，即使 R revision 和摘要相同。原稿/派生误改的未发布恢复见 [S0](s0-intake.md#原稿或派生物误改后的恢复)，不以重置原编号解决历史问题。

## 失败与接续

| 结果 | 接续动作 |
| --- | --- |
| 退出 1，来源/义务/分配不完整 | 回到对应 S0/S2/S3 或 Q，修正实际权威对象，重审受影响部分后保存新 C |
| Review 引用或原生标记失效 | 对照旧新内容和上下文定位变化；按实际差异复核与封装，不能自动 review all 或只改 hash |
| current 目标过时/远端不可读 | 先确认实际目标和工程影响，再准备新快照；不自动切换 historical |
| 退出 2，历史发布语境缺失或原规则未被支持 | 取回确切旧快照/发布观察，核对受支持规则；缺证据则停止，不用当前同名文件或伪造结果替代 |
| 内容已保存，批准/BL 尚未完成 | 从 C 和实际审阅继续，不重分 R/Q/批次编号、不重写原件；内容检查通过不是最终三方批准 |

historical 只用于明确指定的历史复算，结果保留该模式，不能作为当前发布或实施许可。读取失败保留原始诊断和输出文件，新目录重试，不覆盖失败证据。

## 历史 BL、继承和同版本前驱

每个历史 BL 保留自己的 C、B、version.yaml、原配置和三方批准。原始 R/配置在旧提交按固定引用读取；新 Version 的 source_confirmations 表达本版对它的采用，不复制 R 产生第二份权威记录。G1 验证继承身份和内容依据，不证明旧代码已经存在于新交付线，也不替代后续释放条件。

新版本首 BL 对账 `version.predecessor_baseline` 的全部纳入义务；未再提及的旧承诺必须明确纳入或以具名决定排除，排除须固定实际前驱 R/原配置。该版本已有有效 BL 后，后续内容以本版当前前驱为对账分母，不能让更早旧版中已获准退出的义务重新出现。新版本首 BL 不 supersede 旧版；后续本版 BL 沿本版合法链头及 RC 批准更新。完整操作见[版本迭代](version-iteration.md)。

传递继承时，附件简写沿固定 predecessor 找到原记录所属的来源语境；不能把 v2 BL 的 Version 与原 v1 R 的提交直接组合。保留每一跳的 BL/原配置及来源，查询时提供它们各自的发布语境。检查、审阅和报告共用此解析；这不改变当前 Version 的关系评估、采用决定或交付分母。缺件或继承内容不一致应先修复引用/留存，不能重写旧 R/BL 来取得通过。

在查询快照的 `baseline_contexts` 数组中，为每个被实际引用的历史 BL 提供以下字段。下列 JSON 只展示数组中一个对象的形状，完整 SHA 和摘要必须来自实际对象：

```json
{
  "baseline_ref": {"commit": "<原 B>", "path": "requirements/versions/v1.0.0/baselines/BL-v1.0.0-001.yaml", "sha256": "<原 BL 字节摘要>"},
  "target_revision": "<原 Version 所在线本次实际目标>",
  "control_revision": "<本次选定控制提交>",
  "publication_revision": "<原首次 effective 实际发布提交>",
  "publication_evidence_ref": {"commit": "<保存原检查结果的提交>", "path": "<原始结果路径>", "sha256": "<结果字节摘要>"}
}
```

操作步骤：

1. 从原 BL、留存标签和已保存的原始 current/effective 结果取回 C/B、发布与证据；包括它自身依赖的更早 BL。每个确切 BL 只有一个语境条目，不能给同一对象并列不同目标。当前实现限制最多 128 个历史条目、递归深度 64；超界明确停止，不能截断后宣称通过。
2. current 查询分别对照每个原 version.yaml 的 integration_ref 和原配置的控制 ref。v1.x 与 v2 可选不同集成线；更新其中一条线后，旧快照必须重新核对。historical 使用明确固定目标，不自动切换分支或获得当前动作许可。
3. 检查器重算原 C 的来源/审阅/配置/完整清单，核对三方批准、实际原发布字节、后续不可改写与权威 pin；原观察只证明观察语境，不能代替批准。控制历史必须包含原观察时的控制点，不能换一条新控制根假装延续。
4. transition 描述相对前一个 Version 的业务关系，同版本新 BL 中未变的 added/modified 项可以保留原分类与编号依据，编号模式变化不要求重新分配已有 ID。新 Version 使用旧 ID 时则须声明实际 modified/inherited 前驱，不能伪装为新身份。
5. 同版本 supersedes 前驱须先实际发布，新记录必须接续目标线当前链头；目标目录缺前驱、分叉、断链或改写不能通过。已被合法新 BL 接续的旧 BL 仍能做历史复核，不强求旧 BL 继续是链头。
6. 内容清单包含确切历史 BL、其受审内容与批准闭包；本次可能变化的目标/控制及发布观察属于查询语境，不塞入旧 BL 或改写旧清单。保留本次完整快照与原始输出，便于新克隆重复检查。

固定BL按当时的业务输入、policy、批准和发布语境复算，所用工具必须匹配当前单一目标合同的完整实现身份。不读取历史兼容表，不导入旧仓库代码，也不以相同`vr/1`字符串认定不同Schema／工具兼容。不支持的模型或规则身份返回具名拒绝，原记录保持不变。

历史通过不授予当前工程权限。G2～G4的current仍要读取当前工程输入和实际业务／UI权威；只有输入、Review、请求和限制均适用时才能沿原阶段接续。规则回退同样核对完整身份及必需能力，不把historical作为当前动作的降级通道。

## 批准 C 并保存记录 B

身份清点失败时先核对实际 R 文件名、scope 与历史引用。`identity.uid-alias` 表示相同数字被不同拼写重复使用；不能通过换配置投影或移出 included 来规避。保留已登记原身份，按原记录和批准范围纠正候选草稿/错误引用，重新检查受影响的来源、分配和 Review；检查器不自动改名。来源片段排除与 Requirement 取消分别记录，固定前驱必须对应被取消的同一 R；排除不会产生新的 AC 交付义务。

1. 将 C、完整内容清单和实际审阅差异交给 version.yaml 声明的产品、工程、QA 负责人。每个角色各有一项实际批准，兼任时仍分开记录职责；批准内容未变不逐条重审相同要求。没有实际批准则停在这里，不能用测试输入或 Agent 编写的角色名称替代。
2. 保存批准的原始证据，再取得其完整 `commit / path / sha256`。批准条目使用 `actor / role / at / content_commit / evidence_ref`；at 为带时区的真实时间字符串，三项均绑定 C。机器核对身份、引用和内容一致性，不认证文件背后的真实签署行为；本地受控试用仍由责任人核对证据来源。
3. 创建 `requirements/versions/<Version>/baselines/<BL ID>.yaml`。使用已检查的 prospective_baseline ID、C 和完整 content_manifest，记录上述 approvals。首份 BL 的 supersedes 为 null；同版本后续 BL 必须指向当前合法前驱，并以 `requirement_change_ref` 固定已发布 `rc-decided/approved` 事件的 event_id、commit、path、sha256，流程见[需求变更决定](requirement-change.md#批准新基线与停止边界)。B 的三方批准沿用该 RC 对同一 C 的确切决定证据。跨版本继承由 version/scope 记录，不能用 supersedes 跨版本连链。清单与内容检查计算的闭包一致；不能删除源/配置/审阅项，也不把报告输出塞进权威输入凑数。
4. 审阅 diff，保存 B。B 不含自身 SHA；固定 BL 引用从已保存 B 的文件取得。BL 的记录、批准和运行观察可以分属不同提交，无须将它们改写成同一个 SHA。目录外的代码、主 Spec、构建配置和 CI 变更须先在 S3 核对，不能混入本次纯需求资料发布。

发给已获 S4 记录准备授权的 Agent：

```text
从已通过 G1/content 的 C 和实际收到的三方批准准备 BL。
核对角色、批准人、带时区时间、C 与各自证据的固定引用。
逐项保存完整清单；尚未收到的批准保持缺口，不自动补签。
对照差异保存 B，报告 C/B/批准的确切引用及下一步所需留存提交。
不要发布远端或进入 OpenSpec；这些动作需要其实际阶段授权。
```

## 完成控制与留存接入

操作位置仍是业务项目及登记的隔离准备目录。`config/project.yaml` 指定实际 authority_remote、control_ref、pin_namespace、control_owner、retention_policy 和 protection_evidence_ref。当前支持范围是 local-controlled-trial；文字声明不能代替托管平台保护验收。

首次 record 前先检查权威远端是否已有控制分支。已有则显式取回并核对完整历史，不能重新初始化或清空事件；确实没有时，整合者在专用副本建立独立根控制分支，仅包含 `requirements/control/published.yaml` 和 `requirements/id-allocations.yaml`。没有任何需登记事件/预留时，才分别使用 `schema_version: vr/1` 加 `events: []` / `allocations: []`。控制分支不合并业务历史，也不保存另一套 R/Spec。发布后独立查询实际控制 SHA，作为 P。

编号模式由 project.yaml 的 `id_allocation_mode` 声明，省略时为 serial，沿单整合者协调。reserved 模式要求已发布、已消费、属于本线的编号段；reserved 和 serial 都不得复用已预留或废弃编号。R.owner 表达业务职责，不拿它代替编号分配责任人。modified/inherited 身份沿其已验证前驱 BL 的原编号依据，不在新线重新分配同一 R。新增身份仍按本线当前模式检查；serial 的单整合者协调不能说成机器并发仲裁。

整合者需要留存 C、B、全部 content_manifest 与批准证据引用的提交，以及工程起点、保护依据和实际控制条目引用的证据提交。每个留存引用是**直接指向对应提交的轻量标签**，命名为 `refs/tags/vr-pin/<完整 SHA>`；不使用同名但指向不同对象的标签。控制历史通过受保护的追加分支保留，P 不要求另建逐提交标签。

终端示例中的变量须先从真实对象取得；一次只操作已核对的提交，不把占位符当值：

```bash
git push "$vr_authority" "$vr_fixed_sha:refs/tags/vr-pin/$vr_fixed_sha"
git ls-remote --refs "$vr_authority" "refs/tags/vr-pin/$vr_fixed_sha"
```

发布返回不明时先查询远端。相同目标已存在就保持；缺失才重试，错误目标停止调查，不用 force 覆盖。标签不代表批准，也不自动让 BL 进入目标线。检查器只查询确切标签、读取已取回的对象；它不 fetch、打标签、推送或替整合者确认保护设置。

在新的独立完整克隆中，显式获取控制 ref 和所需 vr-pin 引用；不依赖源工作区缓存、默认 tag 跟随或仅设置 fetch-depth。然后按安装说明准备独立 venv 和薄入口。这个克隆是运行 record 的验证位置：对每个固定文件实际读取并核对摘要，确认附件真实字节可恢复。新克隆不能读取旧源分支未留存的缓存来取得通过。

## 检查 record，再发布并检查 effective

在独立验证克隆外准备 record 快照：沿 content 的 schema/checker/rule/Version/line 字段，修改为 `phase: record`、`subject: baseline:<BL ID>`、metadata_revision 为 B 或包含同一 BL 字节的后续元数据提交、head_revision 为 C、target_revision 为实际权威目标、control_revision 为 P、baseline_ref 为 B 中 BL 的完整引用。current 模式核对目标与控制是否仍是远端实际值。

终端：检查目录中的输出文件必须尚不存在，每次保留独立结果。

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G1 --phase record --subject "baseline:$vr_baseline_id" \
  --context "$vr_check_dir/record-context.json" --format json \
  > "$vr_check_dir/record-result.json"
vr_exit=$?
printf '%s\n' "$vr_exit"
```

退出 0 表示该记录满足已实现的可发布性条件；尚未进入目标线是此阶段的合法状态。缺控制/批准/完整清单、编号冲突、缺失/错误 pin、不可取回对象或工程变化都会返回非零。逐项修正实际缺口，保留失败证据；不能手改检查结果或自动刷新 Review 取得绿色输出。

随后沿团队需求资料 PR 完成实际审查和发布授权，将获审内容与 BL 发布到 version.yaml 声明的集成线。允许团队原有合并方式；squash/rebase 后仍保留原 C/B 标签，不能回写 BL.content_commit。查询实际目标 T，建立 T 的留存标签，重新取得目标/控制对象。首次 effective 快照沿用 C/B，phase 改为 effective，target_revision 使用实际 T；不引用尚不存在的本次检查结果。

```bash
bash scripts/requirements-check --root "$PWD" \
  --gate G1 --phase effective --subject "baseline:$vr_baseline_id" \
  --context "$vr_check_dir/effective-context.json" --format json \
  > "$vr_check_dir/effective-result.json"
vr_exit=$?
printf '%s\n' "$vr_exit"
```

首次 effective 检查实际 T 的 BL、权威材料和工程内容，不能用提交历史中较早出现同名文件的 B 冒充发布结果。内容已保存但目标尚未发布时返回 baseline.not-published；发布改变了 Requirement 或原稿字节则拒绝。需求元数据和已绑定工具单独核对；src、tests、主 Spec、构建/依赖配置、CI 等不因“资料发布”而跳过工程差异检查。

## 保存发布观察，恢复后再核对

effective 通过后保存原始 JSON、实际快照及来源说明，再取得结果文件的固定引用并留存其提交。它记录实际 current/effective 观察，不能代替 BL 或三方批准。首次结果不依赖自身提交；后续查询才可引用它。

后续目标因正常开发演进时，若要复核同一 BL 的原发布点，在快照中成对给出 `publication_revision` 与 `publication_evidence_ref`。前者取原结果实际 target_revision，后者固定原 current/effective JSON。检查器核对版本/线、C/B、目标与结果身份，并重新检查原发布点的内容、批准、留存及其在当前目标中的实际集成关系；不是只读取 passed 字符串。缺原始观察则保留缺口，不从 Git 最早出现同名文件的提交猜测，也不重写 S3 的原工程起点。

原观察中的 control_revision 同时固定该 BL 当时的编号语境。复核时重新读取这个控制提交计算新增身份的依据，继承身份继续核对其原 BL；当前控制另验延续与冲突。结果中的 control.revision 是本次所选 P，control.allocation_revision 是该 BL 所用的原观察控制（首次检查则为 P），不是所有继承 R 的共同创建点。二者都是派生诊断，不新增编号台账。

后加预留段覆盖原 serial 编号时返回 `ids.origin-conflict`；原观察声称的控制点尚无必需的已消费预留时返回 `ids.not-reserved`。保留失败与原观察，由整合者检查预留范围、发布事实及是否选错语境。未发布的错误草稿按真实差异修正；已发布冲突不能通过删除控制历史、重分旧 ID 或换写观察取得通过。历史查询可固定合法旧语境查证，但不授权继续当前交付。

历史复算使用显式 historical，保留当时目标/控制及证据；它仍需实际可读的固定对象和持久 pin，不能作为当前发布许可。当前查询发现目标过时，先重新读取实际远端并评估受影响输入，不静默降成 historical。已观察 BL 被后续集成历史删除/改写时停止，保留证据并按历史纠正合同处理，不清理留存引用。

## 已集成原稿或派生物误改的恢复

本节处理原稿/已登记 DAS 输出被意外覆盖，但原字节、原 C/B、BL、批准及控制历史仍完整可取回的情况。若 BL 或控制历史本身已被删改，或原件已不可取回，保持阻断并交回整合者处理；本流程不能消除那些缺口。实际业务解释改变时按相应变更流程裁决，不能用“恢复”绕过范围批准。

1. 保存错误提交、受影响路径、错误字节、实际目标和 Gate 原始输出，取回并核对原固定内容。旧 BL 的原发布复核可能仍通过，因为它检查的是原 C/发布点；这不批准当前误改内容，也不能替代新内容的 G0/G1。
2. 在集成线上通过正常追加提交恢复明确路径的原字节，保留同时进入目标线的合法工程变化；不 force/reset 目标或覆盖旧 pin。先核对实际远端已接收修复。历史覆盖仍存在，直接把修复后的目标作为新 C，仍可能触发 source.intake-overwrite 或 ref.digest；不能更新旧摘要来消除这个结果。
3. 需要继续形成新内容/基线时，在隔离恢复工作区从无误改历史、可取回的固定 C/B 接续需求材料。原 intake、R 和 DAS 身份保持，错误提交留在集成历史与证据中。恢复工作区只用于准备受审内容，不建立新的权威分支或恢复状态库。
4. 重新核对实际目标 E 的工程事实。恢复工作区的 src、tests、主 Spec、构建/依赖配置、CI 等工程字节须与已审 E 一致；逐项取回确切 E 中的合法新增/修改/删除，不把旧代码随需求材料一起恢复。S3 的 code_ref/spec_refs 绑定真实 E；未审工程差异由 S3 处理，不能借资料发布夹带。检查器仍执行完整工程树比较。
5. 比较 source/scope/R/AC、Q、分配和审阅的实际输入，重评受影响部分，再保存新 C 并运行 G1/content。若形成同版本新 BL，按上文取得对该 C 的真实批准并发布相应 RC 决定，保存带该引用的新 B；supersedes 指向实际目标线当前 BL。原 BL、原发布观察和历史 Requirement 记录不修改，也不因同一文件恢复而重分身份。
6. 发布并独立取回 C/B、引用闭包和所需 pin，运行 record。通过后，将受审资料差异按团队允许的方式整合到修复后的目标；本地试验使用 squash，C/B 仍独立保留。相对实际 E 不得产生未审工程变化。随后对实际 T 运行 effective、保留原始观察，并从新的完整克隆重复验证；记录未发布时 effective 应拒绝。
7. 后续新内容继续从受验且无误改祖先的固定 C/B 准备，工程起点始终更新到真实目标。不能因上次 effective 通过，就把含误改历史的目标快照当成干净来源内容。新内容照常经过 S0～S4 的适用检查与审阅；固定内容与当前工程事实分别核对，不抹掉错误历史，也不绕过批准。

本地 synthetic 回归覆盖原稿与 DAS 输出两条恢复路径、合法工程文件保留、原身份保留，以及恢复后的下一份 G1/content；三方决定为显式测试输入。它不证明任意损坏均可自动修复，也不代替实际 Agent、真实工程判断或托管平台接入验收。

本阶段结束时交接 C、B、批准引用、完整清单、控制 P、留存和原始 effective 观察，以及所有未解决项。历史/误改恢复仅覆盖上述声明范围；每个实际项目仍须验证自身工程前提、人员决定和接入条件。BL 三阶段通过不授予业务 Propose/Apply 权限。
