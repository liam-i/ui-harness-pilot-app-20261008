# S2：R/AC、来源投影与阅读报告

[共同约束](README.md) · [前一步 S1](s1-challenge.md)

位置：业务仓库根目录。输入是完整来源、S1 审阅与已知 Q、当前 scope/批次记录和本轮授权。逐批形成 R/AC、来源映射、关系和局部审阅，并可生成阅读报告；结果交 S3。库负责结构、引用与输入绑定，实际语义仍需审阅。本页操作不产生有效 BL 或 OpenSpec Change。

## 分批建立承诺

按完整业务用例、边界与异常路径分批；先核对已有 R 和编号预留，复用已有身份。授权阶段使用官方 Doorstop create/add 管理根 R 文档及编号，按初始 `config/doorstop.yml` 配置语义审阅属性；编辑器直接修改逐项 YAML。检查器不调用 Doorstop edit/review/clear，原生 edit 的隐含 Git 行为不作为本流程编辑入口。

R 正文保存业务承诺，acceptance 每项有稳定 AC ID、条件、可观察结果、验证层级与方法。性能等量化义务还要有 metric、threshold、unit、load、environment、observation_window；缺项不能用“快速”或“可靠”补齐。记录全部真实来源和 Q 依据，不加入代码进度、CI 状态或 Feature Tasks。

修改已有 R 的业务语义、AC、来源解释或自身适用关系时，递增所在线的 `revision`，保留 R ID 和未删除的 AC ID；尚未形成 BL 不自动豁免该规则。一次逻辑修订与其机械封装使用同一序号，不按每次文件写入递增。仅改变版本纳入/排除关系时只改 scope；纯排版或 Doorstop 原生 stamp/末尾换行不另增语义序号，但仍记录实际摘要。同步 scope 和确切引用，复核 Q 的实际落实及受影响批次/工程 Review，再绑定最终内容。检查器可核对所选记录与 scope 的修订一致性；是否发生语义变化仍须实际差异审阅，不能由单次 Schema 或原生严格检查代判。

每批完成局部语义审阅，核对原文与 R 的双向差异，包括同义合并、冲突、遗漏、错误提升和验收可观察性。先由来源逐项检查义务是否落入 R/AC，再由每条 AC 回读其实际依据；来源有目标、AC 有来源以及两向投影一致，都不能证明语义正确。表格要核对实际数据行、续表和末行，不能用预估条数或临时脚本中写死的行区间代替完整阅读。记录在 `reviews/batches/B-NNN.yaml`，显式声明 reviewed_requirements，保留完整 reviewed_inputs 和 context_refs；具名检查与装配顺序沿[共同合同](README.md#审阅范围与最终封装)。实际审阅后按 [S4 的显式封装](s4-baseline.md#显式保存原生审阅标记)保存官方标记，核对字段值和最终字节；它不替代产品/工程/QA 的真实结论。使用 `supersedes`、`retires` 时，同步核对当前原生审阅配置包含这些字段，保留历史配置引用。

scope 是版本成员唯一来源。added/modified/inherited 与 delivery 分开；modified/inherited 引用真实前序 BL/记录/原配置，modified 推进修订，inherited 使用前序确切字节与原配置。同 revision 不证明跨线内容相同。父项若仅作背景，在 scope.context_requirements 中固定记录/配置及必要的原 Version，不把父/兄弟的全部 AC 自动加入本版分母。

取消已形成正式文件的草稿时，scope.excluded 保留 R 身份及实际产品 Q；有固定 predecessor 就选择原承诺，没有时读取当前规范 R/配置（已声明固定背景记录则沿该引用）。没有正式 R 的来源可以直接排除。Q 的合并影响集合须覆盖被排除 R/来源，不能复用一个不涉及该对象的答复。批次和工程 Review 绑定取消记录及来源/资产语境，BL 沿用同一清单；取消草稿不计交付分母，不展开其遗留规划依赖，也不为取消而补原生 review。它若另被选择为背景/有效依赖，仍须满足该角色的检查。

## 来源关系的唯一位置

R.source_refs 保存 origin 与 clarification。origin 的 acceptance 可省略，表示本 R 全部 AC；若只支持部分 AC，明确列出子集。clarification 指向共享 Q，不复制答复。当前版本对原承诺的再次确认保存在 scope.included[].source_confirmations，包含 unit、AC 子集和固定决定依据，不倒改原 R 的来源。

建立 origin 时，逐条核对该 SRC 支持哪些 AC 的条件、结果或约束。只有它确实适用于本 R 的全部 AC，才省略 acceptance；同属一个模块、章节或 R 不是全量关联的依据。临时提取脚本也必须保留实际子集，不能把 R 的来源集合批量套到每条 AC。一个 AC 可以由多个来源和答复共同支持，不要求每个来源单独重复整个 AC；附件的辅助用途沿 asset_refs 表达。

移除某个 R 的错误 origin 后，从当前完整 scope 重新核对该 SRC 的全部目标。其他 R/AC 仍有效使用它时，保留 mapped/duplicate 及有效映射；不能因为它对本 R 只是背景，就把共享单元整体改成 context。仅在整个来源单元不产生独立义务、没有有效目标且背景处置已经审阅时，按下表保存 context；targets 为空本身不是无义务的证明。

`units.targets` 中 mapped/duplicate 行从这两处生成，区分 origin/confirmation；不能单独编辑目标以补覆盖率。`RequirementIndex.source_targets(unit_id)` 提供同一固定 scope 下的机械投影，更新索引仍是授权编辑动作，查询本身不写文件。

| 来源处置 | 保存规则 |
| --- | --- |
| mapped / duplicate | 完整反向目标；duplicate 可指同义单元，端点必须映射相同义务，不能形成重复环 |
| context | 不产生独立义务，targets 为空；可用 context_requirements 列出解释关联的 R，仍需 scope 中的固定端点 |
| excluded | targets 为空，scope 排除记录与 scope_decision 指向同一已落实产品决定 |
| superseded | 保留原 targets；previous_ref 固定替代前 units.yaml，successors 指新 SRC 或决定 Q，scope_decision/decision_ref 固定实际产品答复。新 SRC 的 supersedes_unit 与旧单元方向一致 |
| pending | 保留负责人/阻塞原因，不能通过最终来源解释检查 |

superseded 的 previous_ref 使用已存在的前序提交，不能指自身或改写历史映射。原映射非空时，从旧快照的 scope/R/确认关系核对；尚未建 R 的历史来源可以保留空映射。旧稿仍在接收索引中；替代图无环，当前承诺仍需来源与全量 AC 对账。已基线化承诺的变化与取消沿 [RC 处置](requirement-change.md)建立影响、决定、新 BL 和工程对齐；新版继承及双线变更沿[版本迭代](version-iteration.md)接续。修改来源关系本身不解除 hold 或证明代码已经处置。

## Q 落实与关系检查

Q 收到答复后先 answered。将决定落实到实际 R/scope/关系等对象，applied_to 记录完整文件摘要和必要的固定提交，verified_by 保存真实复核者与证据，再 resolved。不能把 Q 自身当作落实对象。若实际改动对象是 Review，先保存该对象的固定提交再登记 Q；后续完整 Review 复核最终 Q 与当前上下文的适用性，避免互填自身摘要或尚不存在的 SHA。

落实时核对答复的适用条件及全部受影响 R，不只检查引用 Q 的那一段。例如“前台动画不暂停计时”和“切到后台暂停计时”具有不同条件，不能合并成“动画或后台都不暂停”。先保留原文与答复的确切范围；草稿误用明确答复时修正草稿，答复本身仍冲突或含糊时回到共享 Q。未消除的矛盾保留在未完成审阅中，不以字段已填写或 Q 已 answered 宣告语义通过。

R 层级使用 hierarchy.parent；业务依赖使用 requires-capability/constraints。关系 ID 在 R 内稳定且唯一，目标 AC 与本 R 的 applies_to 分开。when 省略为 always；显式 null/unknown 阻断适用判断，条件 false 必须有具名决定。soft 必须有可接受替代和真实审阅依据，不能把 hard 改名放行。related-to/conflicts-with 同 scope 按 R ID 字典序较小一端保存，冲突归共享 Q。

建关系时分别说明消费者哪些 AC 需要提供方哪些 AC，以及依赖成立的条件。不能因为提供方是“公共服务”或“平台能力”，就将其全部 AC 自动设为消费者的硬前置；确实约束全部相关行为的全局义务仍须完整保留。执行等待发生在哪个阶段由 S3 基于这些业务关系和当前工程事实决定。

本地业务前置必须在当前 scope 中，版本外端点使用固定 Version/line/BL/记录/配置与可用性依据。仅作上下文的父项不自动成为交付提供者。层级和历史推导检查完整固定关系闭包及环；单个闭包最多 10000 节点，超限明确拒绝，不能截断后通过。业务依赖环需要 S3 映射到候选与阶段图判断，不直接等同实施死锁。

## 生成 Catalog 与阅读报告

先保存当前内容提交，用 G1/content 的 snapshot 模型明确 Version、line、metadata/head/target 与 current/historical 模式；这份快照不需要 BL。报告允许呈现未解决 Q，生成不执行 G1。使用项目精确 venv，不依赖测试目录或原生 publish：

```bash
.harness/version-requirements-venv/bin/python -I -B \
  harness/version-requirements/lib/report.py --root "$PWD" \
  --context '<固定内容快照 JSON>' \
  --output '<事先准备的父目录下尚不存在的报告目录>'
```

项目内输出只能在 `requirements/versions/<Version>/views/` 下；也可用项目外专用目录。先建立父目录并登记本轮输出，不写原稿、R 或工具目录。成功生成 catalog.yaml 与 report.md，输出明确 `gate_evaluated: false`。报告在每条 AC 下列出其声明适用的 origin 和当前 scope 的 confirmation，后者保留决定引用、不倒改原 R；共享 Q 单列为 R 级澄清，不自动投影成每条 AC 的支持依据。来源为空或全量关联均如实显示，实际支持仍需回读原文和答复判断。

Catalog 只含 ID、标题、类型、修订、固定文件/配置与来源关系，不保存第二份 AC 正文或手工状态。generated_from 绑定固定快照、实际读取清单和生成器摘要。阅读报告逐 AC 按字面显示条件/结果，并附完整字段；原生导出的竖线/换行问题不进入此路径。

资产继续引用，不复制到报告目录。当前工作区文件与固定内容摘要相同时给出可点击相对链接；缺件、同名不同字节或符号链接不生成误导链接，仍提供 `git show <完整SHA>:<路径>` 的固定取回命令及片段身份。移动报告后相对链接可能失效，应从固定输入重新生成，不能据另一个同名文件判定成功。

相同输入可生成新的相同视图；已有输出目录拒绝覆盖。输入错误先拒绝再写文件；两份文件不是事务，写失败只清理本次已创建文件，清理失败保留原错误、残件和目录。先保留失败证据，再由执行者处理其登记残件或选新目录重试，不删除版本目录。

## 批次交接

保存输入提交、实际 R/AC 与 scope、已处理/未处理 SRC、Q 状态、局部审阅和报告位置。重启先核对这些权威记录与差异，不从报告反写状态或重新编号。下一步按 [S3](s3-engineering.md)基于固定代码/主 Spec、资源和验证条件分配全部 AC；随后仍须完成 S4 三阶段，不能以本页处理结束宣称 Baseline 已有效。
