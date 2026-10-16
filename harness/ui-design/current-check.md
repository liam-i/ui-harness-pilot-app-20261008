# UI 当前观察与动作前复查

先按[离线检查的安装步骤](offline-check.md#安装与前提)安装同一工具。`mode: current` 会查询固定 policy 的实际 UI remote/ref，再将所选内容与当前观察一起核对；不 fetch、下载媒体、push、写 Tasks 或生成批准。需求层的业务 target/control 仍是独立检查；已采用需求层时按[原 Gate 接线](requirements.md)复用本库及 observer。

## 准备一次动作的输入

1. 在原工程 Review 中固定[policy](policy.yaml.example)的 commit/path/sha256：采用模式、能力要求、真实角色依据、明确 remote/ref、历史起点和留存责任。远端使用绝对本地路径、`file:///`、`https://` 或 `ssh://` 地址，不用 `origin` 等可重定向别名，不把凭据写入地址。HTTPS／SSH 需要运行环境已有只读访问能力；工具不登录或安装凭据，SSH 不接受未知主机。
2. 通过**单独且明确授权的准备操作**恢复原固定 Git 历史和媒体。`repositories` 只映射稳定身份到本地完整副本；远端在 policy 中，二者不必相同。原 D/A 字节不改，批准仍来自真实人审。
3. 按当前 Change／任务的工程审阅填写[snapshot](snapshot.yaml.example)：`mode: current`、本次 `action`、已审规则锁身份、实际 subject/head、固定 policy／bindings、独立行为分母和选择的 UI 权威 SHA。查询得到新 SHA 时先核对变化及原 Review／请求的适用性，再明确更新快照；检查器不自动改选。
4. 核对实际工作区、HEAD、相关差异与本轮 Review／请求。工具读取固定 Git 对象，不会把未提交文件自动纳入受检实现；未提交差异需沿原工程证据留存并审阅。快照只是受检输入，不是独立批准。

## 调用与留证

无需求层沿[原入口接线](no-requirements.md)；以开始实施为例，在业务副本执行：

```bash
# UI_DESIGN_PYTHON 已按安装说明指向锁定venv；快照中的action也必须为start。
bash scripts/ui-design-check --root "$PWD" \
  --context /absolute/path/to/ui-snapshot.json --action start --format json
```

`--action` 校验 `current`、动作名和原 `change/task` 身份；不会执行相应业务动作。没有该参数时仍按快照 mode 检查，适合共享库或固定历史复算，不能作为动作入口的替代。`--describe` 校验安装并返回完整能力／文件／依赖身份；不是内容或动作通过。

在原阶段证据目录保存输入快照、原始 JSON、命令、退出码、受审输入和工作区身份。可由调用方重定向 stdout 到独立文件；保留非零退出码，禁止用 `|| true` 掩盖失败。不要为保存观察向被观察的 UI ref 提交或推送。

| 输出 | 含义与接续 |
| --- | --- |
| `PASS`、退出0、`current_checked: true` | 本次查询的 remote/ref/SHA 与选择相同，完整固定输入和历史通过；还需原工程授权及适用验证 |
| `FAIL`、非零 | 已观察时点存在明确禁止采用或历史篡改；停止相关动作，交原负责人处理 |
| `UNKNOWN`、非零 | 查询失败、选择过时、对象不齐、能力／规则／格式无法验证等；停止依赖动作，保留具体诊断 |
| `PASS`、`ui_applicability: not-applicable` | 固定工程输入已证明所选消费者无UI义务，未查询UI权威；不代表 UI 包检查通过 |

`observations` 保存实际命令、开始／结束 UTC 时间、stdout/stderr、退出码、实际 SHA 和对应选择；`policy_ref`、`implementation`、`inputs` 与 `authorities` 保存确切依据和可达历史。失败时 `fixed_result` 保留所选时点的检查结果；它的 PASS 不能覆盖顶层 UNKNOWN。`engineering_authorized` 和 `current_permission` 始终为 false。

每次调用重新查询，不接受快照中注入旧观察。单次调用内同一明确 remote/ref 可以复用查询，但仍分别核验所需历史；只有相同 remote/ref、起点、SHA、路径与字节的权威别名才允许同一决定重复读取，不能借别名隐藏重用ID。原业务观察的复用须由共用调用方证明同一权威和 SHA，本入口不实现业务控制观察器。

## 失败与恢复

查询失败先恢复原权限或端点；缺对象由独立取回操作恢复原对象。快照过时先查看新增决定及其禁止范围，核对仍消费的共享依赖、绑定、工程审阅与请求。不要自动切换到 latest、更换历史根、删 required 或把模式改成 historical 取得放行。

恢复后按当前动作重新调用，保留上次失败。Propose、开始／恢复实施、Merge、集成及发布前均要重读；一次 PASS 不覆盖下一动作，也不是持续锁。原 Tiny/Standard、WIP、hold、控制与授权规则继续适用。

历史复算显式使用 `mode: historical`，不传 `--action`，不会连接远端。复算保留所用完整规则身份；旧受检结果保留当时字节，不由新版结果覆盖。不支持的目标格式明确拒绝，无旧格式转换或多规则路由。

[交付入口](README.md) · [无需求层接线](no-requirements.md) · [数据合同](data-contract.md)
