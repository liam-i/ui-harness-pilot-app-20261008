# 固定 UI 数据合同

唯一目标 Schema 为[ui.schema.json](schemas/ui.schema.json)，入口按对象类型验证相应 `$defs`。所有结构对象拒绝未知字段；固定引用必须包含 `repository / commit / path / sha256`，commit 为完整 Git 提交，path 为无外逃的仓库相对路径。JSON 和 JSON 类型的 YAML 均可使用；重复键、alias、anchor、merge key、显式 tag、多文档和非有限数值拒绝。没有旧格式转换。

## 文件与职责

| 对象 | 目标类型 | 核对内容 |
| --- | --- | --- |
| 内容 D 的 manifest | `ui-design/1`，`package` | 平台、画面／状态／流程、固定需求、完整文件、来源、依赖、验收范围 |
| A 及后续决定 | `ui-decision/1`，`decision` | approve／withdraw／supersede；确切包、角色、具名证据及禁止范围 |
| 消费 sidecar | `ui-bindings/1`，`bindings` | 原贡献、端点、任务或 Change 的固定关联与适用性；无任务状态 |
| 固定权威声明 | `ui-policy/1`，`policy` | 采用模式、能力要求、已审remote/ref／起点、角色、身份依据和留存方式 |
| 固定时点输入 | `ui-snapshot/1`，`snapshot` | 本轮实际 head／可选 target、subject、消费者、规则、权威时点；current须有动作名 |
| 闭包审阅证据 | `closure-report` | 受审 D、各包固定文件／外部输入／依赖及 policy 引用；其结论文字不代替批准 |

人工模板展示常用字段；字段穷举和必填项以 Schema 为准。无 R/AC 的真实工程任务使用固定需求材料及 `behavior_ref`，不伪造 R。原需求文件可以直接用固定引用，也可用 `requirement_ref + revision + acceptance` 表达确切 R 修订和 AC；这是不同输入对象，不是格式版本兼容。

## 包闭包与媒体

manifest 不把自己列入 `files`。同 D 的包目录必须恰好等于 `files`、声明的 LFS pointer 路径和 manifest；额外文件、缺件、symlink、submodule、自引用和重复路径均拒绝。每个参考／handoff／制作源说明必须属于已登记文件；screen/state/flow 引用、所需状态和 coverage 必须闭合。

依赖通过 `approved_release_ref` 递归读取，检查它的包、批准和当时限制。同一 `unit/release` 不能指向不同固定内容；实现有递归环保护。完整固定 Git 引用不能通过活动分支形成合法循环，缺件／错摘要的伪循环同样会被拒绝。

每个文件核对实际 SHA-256 和字节数。PNG、JPEG、GIF、WebP 进行真实解码及尺寸核对；SVG 做 XML 完整性和嵌入引用检查，不执行脚本或声称完成视觉验收。文本验证 UTF-8，JSON／YAML 验证可解析，ZIP 验证 CRC。其他二进制只证明固定字节完整，不证明视频可播放、字体可用或引擎可导入。

外部媒体以 `external_objects` 声明固定 `uri / version / sha256 / bytes / media_type / recovery`；实际文件由快照 `external_files` 提供本地路径。检查器不连接 URI。Git LFS 条目另填 `pointer_path`，由 `external_objects` 唯一登记，不再列入 `files`；同时核对 Git pointer 的 oid／size 和恢复后媒体实际字节。仅有 pointer 不会通过。所有已声明交付对象都必须完整，包括非运行必需的参考文件。

结构化文档上限 8 MiB；单个 Git／外部对象以及 ZIP 展开总量上限 128 MiB。图片采用锁定解码器的解压规模保护。超过能力边界明确拒绝，不截断后继续；需要更大范围时应先单独验证工具能力。

## 原素材 owner

UI 新输出由 UI 清单拥有。已有 AST／DAS 使用 `asset_inputs.owner` 固定原 `kind / id / manifest_ref / record_pointer`，JSON Pointer 指向原 manifest 中含 `id / sha256` 的记录；校验身份及内容摘要与 `source_ref` 相同。引用原素材时 `outputs: []`；真正的 UI 派生输出声明变换和文件，原文件同字节不能改名重登记为 UI 输出。

这只核对原记录身份、固定字节和本包输出归属，原 AST／DAS 的接收、审阅、派生历史仍由原素材合同验证；独立工具不重新实现整个需求层。运行资源导入和 Change DAS 继续沿工程 Design／Tasks／E，UI 检查器不建 runtime registry。

## D/A、角色与决定历史

先产生 D，再审阅固定闭包，最后保存 A。approve 绑定 D、闭包证据、平台／状态范围、工程可行性与真实人审证据；证据路径在 A 的决定目录下解析。闭包证据的 `packages` 可包含本次一起审核的多个包；每项文件、外部输入和依赖必须与相应清单一致。`policy_ref` 必须是当前固定 policy 或其明确列出的受审依据之一。

policy 的 actor／角色由真人核对；机器核所声明身份、所需角色、固定审批证据和原字节，不能认证真人、判断审美或代签。AI 可以整理工程可行性证据，这不替代 product／ui 的实际批准。

历史从 policy 起点到所选 SHA 遍历全部可达提交及每条父边，包括合并侧支；包所引用批准必须在该时点可达。决定目录中批准和证据只追加，删除、移动、覆写、同 ID 重用、先删后恢复均拒绝。浅克隆、partial/promisor、Git replace/graft、缺历史对象或绕过起点的合并均拒绝。起点本身是受审信任边界，库不会搜索另一个“更方便”的起点；更换 policy 仍需原工程审阅，不能从一次内容 PASS 推断它已获真实批准。

withdraw 和 supersede 均明确写 `prohibit_new_consumers`、`prohibit_existing_consumers`；消费者在快照声明本次属于 new 或 existing，该声明需工程审阅。supersede 还必须固定不同的 `replacement_ref`。新版本或无禁止范围的替代不会自动撤回旧版本，也不会替换绑定。未来决定不改变旧时点结论；正在消费的共享依赖同样受禁止范围约束。

## 消费与证明边界

快照的 `selections` 是原工程输入给出的分母。每个选择必须精确匹配一项 binding；candidate 选 contribution，scope 选 endpoint，task／change 选对应身份。contribution／endpoint 的 `identity_pointer` 从原 delivery-map 等固定记录中读出身份；task／change 固定原任务／Proposal，适用时加 `association_ref`。不存在的分配、漏绑定、重复消费者、缺状态及未获批差异拒绝。

`required / reuse` 都需有效批准和完整行为覆盖。`not-applicable` 必须有固定受审依据，而且不得携带包、画面覆盖或剩余 UI 义务。行为名来自本轮工程上下文，可以把新版本的 R/AC 映射到原包已批准的状态；语义适用性由 `rationale_ref` 的工程审阅负责。多包状态重名时 coverage 用 `unit / release` 消除歧义。

离线库不调度候选、不判断业务 WIP，也不替代 scope 对未交付 Standard 贡献的原约束。实际贡献选择、授权及 Review／E 的适用性由 Harness 原阶段负责接入。固定快照是审阅输入；恶意伪造整套 policy 和证据、或刻意隐藏业务分母，不可能仅靠内部自洽证明真实批准。

historical通过只覆盖所选固定时点，current另绑定本次实际查询，见[当前观察](current-check.md)。规则锁变化、对象缺失或当前查询失败不能静默忽略或转用旧结果。回退工具若不支持该目标合同应拒绝，已形成的 D/A、历史、失败和原工程记录继续保留。

## 采用模式与完整身份

policy的`adoption.ui`为`enabled / not-adopted`，`adoption.requirements`为`adopted / not-adopted`。两层采用分别声明；后者不代表自动需求Gate已接线。未采用UI时authorities必须为空，且实际所选binding全部具有有依据的not-applicable、空UI行为分母；仍读固定policy及工程输入，不能删除policy绕过required。

`required_capabilities`至少含fixed-objects、strict-models、historical-decisions；启用UI还必须要求current-observation。未知能力或主动删必需检查均拒绝。UI已启用但本次所选功能确无UI义务时，严格核对原受审适用性后可不查询UI权威，不让无关UI远端故障阻断该任务。

规则只支持`ui-check/1`。完整身份绑定代码、Schema、依赖锁、声明能力和薄入口；规则锁自身由SHA-256固定，实际调用的scripts入口也核对。库不验证整个宿主平台或恶意替换后的任意程序，自我报告不能充当可信签名；原工程审阅和调用方应固定完整已审安装，不允许随失败刷新摘要。

[交付入口](README.md) · [使用与恢复](offline-check.md)
