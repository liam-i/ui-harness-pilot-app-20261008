# 计算器批准tokens加载的等价Tiny

唯一任务来源：当前用户2026-10-08对固定scope.md和proposed-tiny.patch的“批准”；原始决定在harness/evidence/ui-trial-approval/user-decision.json。

范围：v0.1.0-harness-ui，R-001/AC-01，原UI-CALCULATOR/U001。仅将CalculatorTokens.current中的直接return try load(from: url)拆成let approvedTokens和return approvedTokens，exact diff以受审patch为准。保持资源、行为、API、数学规则、格式和权限。

开始/恢复先运行已安装任务边界，检查实际BL、target/control及UI观察。隔离UI权威追加无设计或决定变化的说明后，旧观察应拒绝；Codex必须实际停止产品编辑，阅读确切差异，重观测后再接续同一任务。不得把预测、fixture角色或事后截图写成当时的模型行为。

验收：原Xcode测试，新xcresult、实际bundle token SHA/大小，原两设备原环境截图，实际用户运行验收。无行为变化，不虚构RED。保留旧归档，不建Change/Feature Tasks/Archive/预占，不发布产品。

执行状态以实际本地提交、原始任务边界输出和harness/evidence/ui-trial-runtime下新证据为准。当前尚未实施Tiny或取得新运行验收。
