## Why

计算器已有界面和行为，但视觉常量散落在四个View，尚不能消费固定获批设计输入。本轮接入UI-CALCULATOR/U001的tokens，验证设计交付到原生构建的真实链路，保持当前呈现和计算规则。

## What Changes

- 从批准A `db1d8d36482883a46f6624c02cde4241547f3d18`恢复内容D `c6f6cda8b823fa5a5fb9c2ec0f89e876c305bd60`，固定包与本轮适用范围；完整引用在Design。
- 将获批tokens导入应用bundle并由ContentView/NumberView/ActionView/FunctionView使用，不从设计目录动态加载。
- 为真实tokens加载和现有15条行为补原生验证，两种尺寸核布局；现有行为不制造RED。
- 不新增计算功能、历史、错误提示或持久化；不改公式、不重画已确认设计。

## Capabilities

### New Capabilities

无。当前界面与计算行为不变，属于视觉常量/运行资源组织的技术重构。

### Modified Capabilities

无。当前无主Spec，不能为了检查通过补造行为变化；本Change明确`skip_specs: true`。Design保存适用原行为、固定expected和实现验证，仍有唯一Tasks及完整规划Review。

## Impact

仅计算器四个View、获批JSON资源及Xcode资源/测试配置，必要的原生测试与测试标识。新测试目标与共享scheme用于现有无测试工程的可重复验收；不新增外部依赖。原源码基线18358f45268a02f848c3a1e46ed4139913d5168d，原作者MIT许可保留。
