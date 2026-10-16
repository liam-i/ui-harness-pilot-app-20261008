# 需求 Gate 与 UI 的联合 CI 准备

本页用于已经采用需求层、且 `ui_design: enabled` 的项目。原需求 Gate 调用共同 UI 库，必须在**原需求 Gate 的同一 venv**内准备两份锁定依赖。单独设置 `UI_DESIGN_PYTHON` 不会改变 `scripts/requirements-check` 的解释器。原生 UI Job、原需求 Gate、真人审核和工程授权各自保留。

## 运行环境和可信工具

当前联合环境限定 CPython 3.13、macOS arm64；UI 的支持范围见[离线安装](../offline-check.md#安装与前提)。需求层在 Linux／WSL 的既有资格不覆盖 UI；iOS／Android／Cocos 是产品目标，不能据此选择 Linux UI checker。

将完整 `harness/version-requirements/`、`harness/ui-design/`、两份 `scripts/*-check` 和受审 CI 准备文件固定到可信工具提交。业务受检提交另行恢复；不执行未审业务分支中的安装脚本。维护者在原工程 Review 中核对联合实现身份、policy 及 CI 脚本，规则变化后重评实际输入，不能只改旧回执中的 hash。

以下是**可信工具 checkout 根目录**中的首次环境准备；已有 venv 先核对，不原地覆盖：

```bash
test ! -e .harness/version-requirements-venv &&
test ! -L .harness/version-requirements-venv &&
python3.13 -m venv .harness/version-requirements-venv &&
.harness/version-requirements-venv/bin/python -m pip install \
  --require-hashes --only-binary=:all: \
  -r harness/version-requirements/config/requirements.lock \
  -r harness/ui-design/config/requirements.lock
```

缺 wheel、错误宿主、错误 minor、库／规则身份不符时失败，不改锁、全局安装或回退解释器。需要检查 UI 入口时可令 `UI_DESIGN_PYTHON` 指向这个同一解释器，运行 `scripts/ui-design-check --describe`；它只证明安装，不替代原 Gate。

## 原始请求和对象准备

阶段执行者按[需求层接线](../requirements.md)提供真实 current 请求。宿主负责固定阶段、实际 head、工具 SHA 和下面的恢复条件；不能让未审请求选择工具、降低阶段或切换采用模式。

| 必需输入 | 谁准备及核对 |
| --- | --- |
| 原 BL、map、Review、E、业务 target/control | 原需求阶段及 CI 保留对象；共同 UI 工具不生成这些事实 |
| 本地 policy、bindings、不可改写 UI 输入记录 | 原工程 Review 固定引用；policy 为 `requirements: adopted`，A→D、角色依据、历史起点均是真实已审对象 |
| 外部仓库的完整 Git 历史 | 维护者在可信 CI 配置按稳定 repository 身份提供源；完整镜像取回全部保留 refs，无 shallow／partial clone。源 URL 不代替 policy 中的权威 |
| 外部媒体／LFS | 宿主在运行 Gate 前按原 URI/version/hash 恢复完整字节，并在 `external_files` 填实际绝对路径；准备器不下载媒体、不把 pointer 当原件 |
| current 观察权限 | 业务 origin 与 UI policy 的每个 remote/ref 分别具备只读访问；HTTPS 不交互登录，SSH 使用已核实主机身份。凭据不放 URL、快照或 Artifact |

随包 [prepare_requirements.py](prepare_requirements.py)只处理**已审来源的 Git 对象恢复和物理路径映射**。由可信 workflow 固定 `VR_UI_MODE=enabled` 和 `VR_UI_REPOSITORIES_JSON`；后者例如 `{"ui":"https://example.org/team/design.git"}`，须替换为实际地址。请求含 `ui` 时，keys 须精确对应原 `snapshot.ui.repositories` 中除 `project` 外的身份。`project` 由原 Gate 指向真实受检 worktree，不配置为另一仓库。

同一份可信来源配置可以接续 G0/G1 与后续 UI 消费。请求没有 `ui` 时，仍执行联合 runtime 前检，但不克隆 UI 仓库、不补写 `ui`，回执中的本次恢复映射为空；无需清空可信来源表或切换检查器提交。随后由原 Gate 判断该阶段能否缺少 UI 消费输入：G1 无高保真包可以通过，G2 缺必需 UI 上下文仍拒绝。请求有 `ui` 时，缺映射、额外或未知仓库身份仍拒绝，不能借此降低采用模式。

准备器由原 workflow 的 `Prepare checked workspace` 阶段调用：先通过原需求 runtime 的 `preflight(ui=True)`，请求含 `ui` 时再在本次输出目录之外新建完整 Git 镜像；保留原始 `context.json`，严格拒绝重复键后生成 `ui-context.json`，只替换已有 `ui.repositories` 的本机位置。`ui-preparation.json` 记录两个请求摘要、实际位置和联合实现身份；权威 SHA、历史起点、policy、绑定、分母、动作及外部媒体固定身份不变。原 Gate 用准备后的快照验证全部语义和当前观察。

原始请求只有定位问题时可以重新映射；**UI ref 前进不能由准备器改选 latest**。取回更新对象后，旧权威选择仍应失败，由原负责人核对新决定并重评 Review／请求，再提出新 current 请求。准备中断保留日志和已产生目录，重试使用新运行目录，不覆盖失败。

## 宿主接线与边界

GitHub 的需求 workflow 在同一个需求 venv 中安装两份锁，然后调用本准备器；从可信配置启用模式并固定来源。私有源凭据、额外媒体恢复和多个外部系统由项目另外配置；未准备就停止，不能宣称仅复制 YAML 已完成所有接入。

已安装的 `harness/version-requirements/ci.py` 可在显式准备好的 macOS arm64 宿主复用原阶段命令体。适配器从**可信 workflow**读取 UI 常量并覆盖同名环境变量，核对 UI 准备代码未修改；宿主先安装双锁、准备认证／媒体，传入独立观察的 head 和必需 gate/phase。现有 Linux Docker 配置只支持 UI 未采用；启用 UI 须另审 macOS 宿主的配置、执行身份和原始产物，不能仅删去拒绝条件。

本材料提供联合准备机制，**不宣称 UI-enabled 完整需求流水线的托管 required checks 已验收**。目标项目先在干净副本验证正向、缺工具／对象、错身份、UI ref 独立推进、修复恢复，再取得真实 Job、受检 SHA、原始 Gate 产物、失败阻断／恢复及保护设置回读。最终工程动作前继续检查业务和 UI 两条 current 权威；原生 Job 的成功不能替代原 G2/G3/G4，旧绿色结果不冻结远端。

[需求层接线](../requirements.md) · [原生平台 CI](README.md)
