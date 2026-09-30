## Context

动机见proposal.md。原工程四个View直接内联视觉常量，没有测试目标；原计算与状态逻辑可运行。内容D中的新包只是提取/固定现有设计，本轮不改变可观察产品行为，因此skip_specs已由实际CLI报告skipped；没有编造新的数学Spec。

## Goals / Non-Goals

**Goals:** 将获批tokens作为真实bundle输入，保持原View职责与数学状态；建立可重复的原生验收及独立设计消费证据。

**Non-Goals:** 不改计算规则、存储、平台范围、VoiceOver全覆盖或动态字号；不添加设计自动Gate、后台服务或其他业务界面。

## Decisions

### 资源、代码和测试边界

1. 在CalculatorSwiftUI下导入获批tokens.json，Xcode Copy Bundle Resources明确包含该文件；四个View读取同一小型Decodable值对象。仅增加本包需要的类型/语义色映射，集中在UI实现旁；不用通用设计系统框架，不从原型生成SwiftUI。
2. 数学动作与CalculationState保持原逻辑。JSON只驱动已声明的尺寸/间距/字体/颜色语义；缺资源/非法值由加载测试明确失败，发布前必须保证实际bundle正常，不用隐藏硬编码回退掩盖导入失败。
3. 新增最小XCTest和XCUITest目标（CalculatorTests、CalculatorUITests）及共享scheme，使用当前Xcode构建。测试目标纳入现有工程，不另建业务服务或平行执行框架。新增稳定accessibilityIdentifier供UI定位，不改变按钮动作/文案。
4. 原有15条行为在两尺寸实际执行；原UI长数字/inf/nan也应保留。布局核对键64pt、外边距32pt、行距20pt等tokens及系统safe area，以获批handoff允许的系统绘制差异为准，不批准新截图来掩盖偏差。对tokens本身使用预先固定字节摘要，验证拷入的JSON与运行bundle一致且View实际读取。

### 消费绑定

```json
{
  "consumer": {
    "kind": "change",
    "subject": "adopt-calculator-ui-tokens",
    "proposal_path": "proposal.md"
  },
  "applicability": "required",
  "approved_release_ref": {
    "repository": "/private/tmp/ui-workflow-p0-20260930-u8jw1kyx/work/ui-authority",
    "commit": "db1d8d36482883a46f6624c02cde4241547f3d18",
    "path": "design/units/UI-CALCULATOR/decisions/approve-U001.yaml",
    "sha256": "78d7f4acab4fbb74a2098bfe26560f67ddb3d6538017fff53e2011c740236682"
  },
  "package_ref": {
    "repository": "/private/tmp/ui-workflow-p0-20260930-u8jw1kyx/work/ui-authority",
    "commit": "c6f6cda8b823fa5a5fb9c2ec0f89e876c305bd60",
    "path": "design/units/UI-CALCULATOR/releases/U001/manifest.yaml",
    "sha256": "2f1ec315db7bf890fde151b6c8ad8ca6075759f6ab7daf6ee976d0a121306630"
  },
  "expected_ref": {
    "repository": "/private/tmp/ui-workflow-p0-20260930-u8jw1kyx/work/ui-authority",
    "commit": "99526d0a38689138bd81fcd8f09e9693502d7d41",
    "path": "inputs/app-expected.json",
    "sha256": "8d705bffa2f4684f3e42f55dfa47a25eeed88e43730d31a83a651eecb514e92c"
  }
}
```

覆盖为清单所列calc的9状态与输入app-expected.json的A01–A15；适用性required，理由是首次将现成UI整理并导入固定包。允许差异只使用包内OS-RENDERING。现有计算业务无变化；其他功能不因本次接入自动获得UI批准。

### 固定消费与阶段检查

无需求层Standard：当前Change的Proposal/Design就是消费者上下文，唯一Tasks记实施，不另建需求库或任务台账。本Design固定A及D，包清单固定全部文件、来源和独立expected；规划Review以当前文件摘要固定整体，避免文件引用自身未来提交。

取包使用独立恢复的Git对象；当前权威为`/private/tmp/ui-workflow-p0-20260930-u8jw1kyx/work/ui-authority`的`refs/heads/main`，历史起点`a6bc9fb40ff11bdfe7190273b97ebb6901f9ad52`。policy为该仓库输入提交99526d0a38689138bd81fcd8f09e9693502d7d41的inputs/authority.md，完整摘要见固定闭包报告。每次Propose/开始或恢复Apply/归档交付前重读实际ref和可达决定历史，将观察留在消费方；缺件/未知/撤回停止，不改用latest或历史PASS。原无效历史查询已在开发证据保留，今后使用确切decisions目录，零匹配不算通过。

来源获取失败演练在单独导出副本中移除必需文件，记录缺件并停止，再从同一D恢复；不修改已批准原包。资源文件身份只归UI清单，运行副本由本Change引用导入，不登记为DAS。

### 原生验证与证据

独立expected在输入提交99526d0a38689138bd81fcd8f09e9693502d7d41形成，必须逐ID记录actual，不据实现改答案。新增加载逻辑先读项目TDD，用实际可调用接口做有效失败后实现；为既有行为补测、添加测试标识和静态布局验证不伪造RED。

两台专用设备为SE3 `4F72CD21-F071-4835-87B2-1456D125374B` 和17Pro `D14EBF55-3D41-419E-8F85-306D5D812CFD`，iOS27.0、竖屏、浅色、默认字号。每次测试记录实际设备、代码HEAD+差异、命令/环境、退出码、用例数、原始日志/xcresult与截图；不把旧结果算到新代码。

原构建命令见AGENTS；实际构建和单元运行上限各300秒，UI suite每设备600秒、关闭并行克隆，用`-parallel-testing-enabled NO`。测试支持使用现有Xcode/XCTest，不安装xcodegen或第三方测试框架。测试完成或失败都关闭本试点设备；保留原操作及清理的独立结果，不删除用户设备。

### 本地交付与回退

取得本规划Review及明确Apply授权后才改业务实现。工作仅限当前隔离功能分支，可在用户授权下保存规划/实现/归档的本地提交；不会推送上游、合并正式主线或发布产品。测试、人工界面核对齐备后按原Archive/Sync收尾；只归档当前Change。设计批准不等于运行验收；最终产品画面与行为证据仍交当前用户确认。

未完成时保留原Tasks和失败，不新建Change。代码回退按当前分支实际差异选择并复验，不能只回退设计指针；已批准D/A继续保留。运行资源不再需要时由相应工程返修处理，不删除决定历史。

## Risks / Trade-offs

- 旧Xcode工程缺测试入口 → 增加最小原生目标和共享scheme，不以零用例或编译错误当RED。
- JSON值或资源关联遗漏 → 核tokens字节、bundle路径及View读取，新增加载测试；不通过硬编码绕过。
- 原Double边界不符合一般计算器产品直觉 → 按已批准范围保留inf/nan和清除恢复，不扩数学功能。
- 无完整宿主自动发现验证 → 本次显式读取项目Skill执行并保存真实命令，不把静态入口检查声称为全模型行为验收。
