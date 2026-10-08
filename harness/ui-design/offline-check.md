# 离线 UI 检查

本入口只回答：**指定时点的包、批准声明、决定历史和所选消费绑定是否完整且一致。** 输出不会授权 Propose、Apply、Merge 或发布。当前权威查询见[当前观察](current-check.md)；工程Gate和平台运行验收仍由原流程负责。

## 安装与前提

当前锁定环境为 **CPython 3.13、macOS arm64**。依赖的确切版本和 wheel 摘要见[requirements.lock](config/requirements.lock)；代码、Schema、入口及锁文件身份见[rules.lock.json](config/rules.lock.json)。其他平台尚未验收，工具会明确拒绝；不以换 Python 或忽略依赖错误作为回退。

在项目原接入操作中，把本目录完整复制为 `harness/ui-design/`，并把其中 `ui-design-check` 复制为 `scripts/ui-design-check`。不要在教程仓库初始化业务目录。未采用需求层的项目不需要安装 Doorstop 或创建需求数据库。

以下在**隔离业务副本**执行；`ui_venv` 是本次明确选择的临时环境路径：

```bash
ui_venv="$(mktemp -d "${TMPDIR:-/tmp}/ui-design-venv.XXXXXX")"
python3.13 -m venv "$ui_venv"
"$ui_venv/bin/python" -m pip install --require-hashes \
  -r harness/ui-design/config/requirements.lock
export UI_DESIGN_PYTHON="$ui_venv/bin/python"
bash scripts/ui-design-check --describe
```

安装是显式准备操作，检查命令不安装依赖。已有对应 wheel 目录时，用 `--no-index --find-links '<wheel目录>'` 安装，可完全离线恢复环境。不要在检查器内加入下载或自动安装回退。

## 准备固定快照

1. 按[人工检查单](manual-checklist.md)完成 D、真实审阅、A 和独立取回。Git 仓库必须有完整历史；显式取回所需媒体和对象，不将分支名、网页链接或 LFS pointer 当作内容。
2. 固定[policy](policy.yaml.example)及它的真实审阅依据。审核者核对 actor／角色、权威、历史起点、留存责任；历史根只能来自该 policy，不能为跳过撤回而另选。制作源／审批的真实性由人核验，脚本不会把 YAML 名字变成真实身份。
3. 按[绑定模板](bindings.yaml.example)选择真实消费者，并固定当前 Review／任务中的 UI 适用性、覆盖和允许差异。候选和 scope 用原记录的 JSON Pointer 定位实际贡献身份；Change／任务固定原 Proposal／任务材料，不另存任务状态。
4. 填写[snapshot](snapshot.yaml.example)，historical复算时明确改为`mode: historical`，从 `--describe` 记录本次已审安装的规则身份。`repositories` 只映射仓库身份到本地完整副本；改变副本位置无需改写已批准引用。`selections.behaviors` 来自受审工程输入，不能从检查输出生成，也不能为 PASS 删减。

快照及 policy 是需要工程审阅的输入，不是审批工具。离线库不能判断用户是否隐瞒了应选的业务义务，也不能识别伪造的一整套人审叙述；它会验证所声明的角色／证据引用及完整字节。自动接入应由原阶段 Review 和消费者选择器固定这些输入。

本消费检查入口需要已经存在的A。D阶段继续按人工清单预检；不能为运行检查器先填虚假批准。

## 执行与结果

```bash
bash scripts/ui-design-check --root "$PWD" \
  --context ui-snapshot.json --format json
```

选择historical时，退出 `0` 表示所选固定输入通过；退出非零表示拒绝或未能完整验证。JSON 包含 `rules`、实际固定 `inputs`、获批 `packages` 与 `diagnostics`；通过时另有历史 `authorities`、所选 `consumers`、`external_objects`。启动尚未核实规则时`rules: null`，不是默认通过。每次保存命令、退出码、原始JSON、输入快照及规则身份，放在项目原阶段证据位置。

`engineering_authorized` 和 `current_permission` 始终为 `false`。`mode: current` 另调用独立观察器；查询或固定输入无法验证返回UNKNOWN／非零，不改成historical放行。`--describe` 只核对安装并报告能力，不能当作包检查通过。

Python 调用方使用 `lib/` 下的 `ui_design.api.check(snapshot, root)`，返回同一结果对象；不另写一套包／历史规则。库不创建目录、生成批准、修改输入或 Git 索引。输入前后快照验证只证明该次前后文件内容／元数据不变，不是连续写入监控。

## 失败与恢复

| 诊断类别 | 下一步 |
| --- | --- |
| `schema.*`／`parse.*` | 修正未获批输入的目标格式。已获批包字节要改变时生成新 D/A；不放宽模型或忽略字段 |
| `object.*`／`media.*` | 显式恢复原固定对象／媒体，核对摘要和完整性；不换 latest。图片损坏需要原 owner 处理 |
| `package.*`／`asset.*`／`binding.*` | 核对原清单、owner、实际消费者和工程分母；保留失败，不删 required 或减少覆盖 |
| `approval.*` | 核对确切 D/A、角色、原审批证据和所选时点禁止范围；需要新设计决定时交真人 |
| `history.*` | 恢复完整原历史；保留删除／覆写现场并交权威负责人。不能换历史根消除失败 |
| `rules.*`／`runtime.*` | 恢复本轮已审的完整工具和锁定环境；规则升级须重新审阅，不能只把快照摘要改成当前值 |
| `observation.*` | 按[当前观察](current-check.md)恢复实际权威或重新审阅过时输入；历史结果不放行当前动作 |

包能恢复不代表工程代码已回退。按原 Change／任务和 CI 处理实现修复，不重建候选、批准或平行 Tasks。

[交付入口](README.md) · [数据合同](data-contract.md)
