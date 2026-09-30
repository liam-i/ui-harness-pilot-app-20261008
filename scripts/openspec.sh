#!/usr/bin/env bash
# OpenSpec 命令速查 · 1.12.0
# 校验来源与版本 → 加载项目 Profile → 执行 CLI；生成后适配 Apply/Update 与显式 Explore/Verify。

# ── 1. 直接调用 ────────────────────────────────────────────────
#
# 将脚本放在业务项目 scripts/openspec.sh；需要 Bash、Node.js >=20.19.0。
#
#   bash scripts/openspec.sh <命令> [参数]
#
# 示例：
#   bash scripts/openspec.sh --version
#   bash scripts/openspec.sh init --tools codex
#   bash scripts/openspec.sh status --change custom-focus-duration
#
# 安装来源由环境变量 HARNESS_OPENSPEC_SOURCE 选择：
#   global（默认）  使用全局 CLI，版本须匹配 harness/openspec-version。
#   local          使用项目 CLI，版本须匹配 package.json 的 devDependencies。
#
# 使用项目 CLI：
#   HARNESS_OPENSPEC_SOURCE=local bash scripts/openspec.sh --version
#
# 无论选择哪种来源，都须先安装对应的 OpenSpec，并提供 harness/openspec-profile.json。
# 缺包或版本不符时停止；脚本不自动安装或切换来源。

# ── 2. 常用命令 ────────────────────────────────────────────────
#
# 以下命令接在 bash scripts/openspec.sh 后。
# <change> 换为 Change 名；<capability> 换为 list --specs 列出的能力名。
#
# 帮助与集成
#   --version                          查看版本（简写 -V）
#   --help                             查看命令（简写 -h）
#   init --tools codex                 初始化 Codex；多宿主用 codex,claude
#   update                             刷新已配置的 Skill／指令文件
#   config path                        查看运行配置路径
#   schema which spec-driven --json    查看 Schema 来源，教程预期为 package
#
# 规划与查询
#   new change <change>                  创建目录，规划内容仍需后续编写
#   list                                 列出活动 Change
#   list --specs                         列出主 Spec
#   show <capability> --type spec        查看主 Spec 正文
#   status --change <change>             查看 Artifact 完成情况
#   instructions apply --change <change> --json    读取执行指引与任务状态，不实施代码
#
# 校验与归档
#   validate <change> --strict --no-interactive                   校验指定 Change
#   validate --all --strict --report findings --no-interactive    校验活动 Change 和主 Spec
#   validate --archived --no-interactive                          单独检查归档 Tasks 的未完成项
#   archive <change> --yes                                        同步主 Spec 并归档，须先完成验收

# ── 3. 常用参数 ────────────────────────────────────────────────
#
# 参数只用于支持它的命令；完整列表用“命令 --help”查询。
#
# 选择目标
#   --change <id>          status / instructions：指定 Change
#   --type change|spec     show / validate：消除同名歧义
#   --schema <name>        new change / status / instructions：指定 Schema
#
# 输出与交互
#   --json                 输出 JSON，便于程序读取
#   --no-interactive       show / validate：禁用交互，须明确目标或范围
#   --report full|findings validate：批量报告显示全部结果／仅发现项
#
# 校验与归档
#   --all                  validate：活动 Change + 主 Spec，不含归档历史
#   --archived             validate：仅查可识别任务的未完成项；与 --all 分开运行
#   --strict               validate：WARNING 也算不通过
#   --yes / -y             archive：跳过确认，包括未完成 Tasks 的确认
#   --skip-specs           archive：跳过主 Spec 同步，不用于绕过真实 Delta
#   --no-validate          archive：跳过校验，不建议使用
#
# 注意：--archived 不检查 tasks.md 是否存在／非空，也不校验全部历史 Delta。
# 静态校验不能代替业务测试和审查；--yes 也不代表验收通过。

# ── 4. 配置与易混淆点 ──────────────────────────────────────────
#
# • Profile 只接受 profile、delivery、workflows；字段详解见 templates/README.md。
#   修改 harness/openspec-profile.json 后运行 update，刷新集成。
# • 每次调用（包括帮助）都先预检，再重写 .harness/xdg-config/openspec/config.json。
#   config set 只改此运行副本，下次会被覆盖；请维护上面的项目配置源。
# • 以脚本所在目录的父目录作为项目根目录执行 CLI；仅隔离 Profile，不隔离 Schema 或宿主权限。
# • update 刷新集成；$openspec-update-change 修订规划，后者发给 Agent。
#   $openspec-*、/opsx:* 都是对话入口，不是本脚本的终端参数。
# • scripts/adapt-openspec-workflows.mjs 与本文件一起复制；只适配固定版本生成正文。
#   刷新前须在项目外备份全部受影响入口，刷新后合并自定义；CLI 不自动合并。
#   node scripts/adapt-openspec-workflows.mjs --check 只读检查实际适配，不运行 CLI。
#
# 更多示例：engineering-harness/tutorials/reference/commands.md

# ── 以下为脚本实现 ────────────────────────────────────────────
# 命令失败、变量未定义或管道失败时立即退出。
set -euo pipefail

# 根据脚本位置定位项目，不依赖调用者的当前目录；-P 使用实际物理路径。
harness_project_root="$(CDPATH='' cd -P -- "$(dirname -- "$0")/.." && pwd -P)"
harness_config_root="$harness_project_root/.harness/xdg-config"
harness_source="${HARNESS_OPENSPEC_SOURCE-global}"
case "$harness_source" in
  local|global) ;;
  *) printf 'HARNESS_OPENSPEC_SOURCE 必须为 local 或 global\n' >&2; exit 1 ;;
esac
command -v node >/dev/null || { printf '请先安装 Node.js（OpenSpec 的运行环境）\n' >&2; exit 1; }
# 固定本次使用的 Node，避免切换目录后相对 PATH 指向另一份运行环境。
harness_node="$(node --input-type=commonjs -p 'process.execPath')"

# global 支持 npm 全局安装布局，并核对 PATH 找到的入口确实来自当前 npm 前缀。
# 不跳过 PATH 中错误的第一项去寻找另一份，以免隐藏环境配置问题。
harness_global_root=""
harness_found_cli=""
if [[ "$harness_source" == global ]]; then
  command -v npm >/dev/null || { printf '全局方案需要 npm；请检查 Node.js/npm 安装\n' >&2; exit 1; }
  harness_found_cli="$(type -P openspec)" || { printf '找不到全局 openspec；请按项目约定安装并检查 PATH\n' >&2; exit 1; }
  harness_global_root="$(npm root --global)"
fi

# local 从项目清单读取精确版本；global 从文本版本文件读取。先验证来源和版本，
# 再写运行配置，避免失败时留下新副本。两种来源的 OpenSpec CLI 均由 Node 运行。
harness_selection="$("$harness_node" --input-type=commonjs - "$harness_project_root" "$harness_source" \
  "$harness_global_root" "$harness_found_cli" <<'NODE'
const fs = require('node:fs');
const path = require('node:path');
try {
  const [project, source, globalRoot, found] = process.argv.slice(2);
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < 20 || (major === 20 && minor < 19)) throw new Error('需要 Node.js >=20.19.0');
  const manifest = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
  const expected = source === 'local'
    ? manifest(path.join(project, 'package.json')).devDependencies?.['@fission-ai/openspec']
    : fs.readFileSync(path.join(project, 'harness/openspec-version'), 'utf8').trim();
  if (typeof expected !== 'string' || !/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.test(expected)) {
    throw new Error('请在所选路线的版本来源中填写精确版本，如 1.12.0');
  }
  const packageRoot = path.join(source === 'local' ? path.join(project, 'node_modules') : globalRoot,
    '@fission-ai/openspec');
  const entry = fs.realpathSync(path.join(packageRoot, 'bin/openspec.js'));
  if (source === 'global' && fs.realpathSync(found) !== entry) {
    throw new Error(`PATH 中的 openspec 不属于当前 npm 全局安装：${found}；请检查 PATH/npm 前缀`);
  }
  const installed = manifest(path.join(packageRoot, 'package.json'));
  if (installed.name !== '@fission-ai/openspec' || installed.version !== expected) {
    throw new Error(`期望 OpenSpec ${expected}，实际 ${installed.version}：${entry}`);
  }
  // 在 CLI 读取配置前拒绝特殊文件与多硬链接文件，避免阻塞或改写共享内容。
  const target = path.join(project, '.harness/xdg-config/openspec/config.json');
  const current = fs.lstatSync(target, { throwIfNoEntry: false });
  if (current && (!current.isFile() || current.nlink !== 1)) {
    throw new Error(`运行配置必须是普通文件，且不能有多个硬链接：${target}`);
  }
  process.stdout.write(`${expected}\n${entry}`);
} catch (error) {
  console.error(`OpenSpec 预检失败：${error.message}`);
  process.exit(1);
}
NODE
)"
harness_expected_version="${harness_selection%%$'\n'*}"
harness_cli="${harness_selection#*$'\n'}"

# 写入前拒绝配置路径上的符号链接，包括目标不存在的悬空链接，避免沿链接覆盖文件。
for harness_config_path in \
  "$harness_project_root/.harness" \
  "$harness_config_root" \
  "$harness_config_root/openspec" \
  "$harness_config_root/openspec/config.json"
do
  if [[ -L "$harness_config_path" ]]; then
    printf 'Refusing symlink in OpenSpec config path: %s\n' "$harness_config_path" >&2
    exit 1
  fi
done
# 版本查询与最终执行使用同一入口及环境，不修改用户全局配置。
harness_actual_version="$(env XDG_CONFIG_HOME="$harness_config_root" \
  OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1 OPENSPEC_NO_COMPLETIONS=1 OPENSPEC_NO_ANIMATION=1 \
  "$harness_node" "$harness_cli" --version)"
if [[ "$harness_actual_version" != "$harness_expected_version" ]]; then
  printf 'OpenSpec 版本输出不符：期望 %s，实际 %s（%s）\n' \
    "$harness_expected_version" "$harness_actual_version" "$harness_cli" >&2
  exit 1
fi

# 用固定的 Node 预检团队配置；通过后才创建目录并原子替换运行配置。
# 这是教程的三字段配置约定，枚举对应 OpenSpec 1.12.0；升级时一并复核。
"$harness_node" --input-type=commonjs - "$harness_project_root/harness/openspec-profile.json" \
  "$harness_config_root/openspec/config.json" <<'NODE'
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
let temporary;
try {
  const raw = fs.readFileSync(process.argv[2], 'utf8');
  const config = JSON.parse(raw);
  const fail = (message) => { throw new Error(message); };
  if (!config || typeof config !== 'object' || Array.isArray(config)) {
    fail('配置必须是 JSON 对象');
  }
  if (Object.keys(config).some((key) => !['profile', 'delivery', 'workflows'].includes(key))) {
    fail('团队配置仅支持 profile、delivery、workflows，请检查字段名');
  }
  if (!['core', 'custom'].includes(config.profile)) fail('profile 必须是 core 或 custom');
  if (!['both', 'skills', 'commands'].includes(config.delivery)) {
    fail('delivery 必须是 both、skills 或 commands');
  }
  const known = ['propose', 'explore', 'new', 'continue', 'apply', 'update',
    'ff', 'sync', 'archive', 'bulk-archive', 'verify', 'onboard'];
  if (config.workflows !== undefined && (!Array.isArray(config.workflows) ||
      config.workflows.some((name) => !known.includes(name)) ||
      new Set(config.workflows).size !== config.workflows.length)) {
    fail('workflows 必须是无重复的已知工作流名称数组');
  }
  if (config.profile === 'custom' && !config.workflows?.length) {
    fail('custom 必须明确提供非空 workflows');
  }
  if (config.profile === 'core' && config.workflows?.length) {
    fail('core 使用官方固定集合，请移除会被忽略的 workflows 或改用 custom');
  }
  const target = process.argv[3];
  const directory = path.dirname(target);
  fs.mkdirSync(directory, { recursive: true });
  const candidate = path.join(directory, `.config-${randomUUID()}.tmp`);
  const fd = fs.openSync(candidate, 'wx', 0o600);
  temporary = candidate; // 仅清理本进程成功创建的文件。
  try {
    fs.writeFileSync(fd, raw);
  } finally {
    fs.closeSync(fd);
  }
  // 替换前再次核对目标；同目录 rename 让读取者只看到完整的旧版或新版。
  const current = fs.lstatSync(target, { throwIfNoEntry: false });
  if (current && (!current.isFile() || current.nlink !== 1)) {
    fail(`运行配置必须是普通文件，且不能有多个硬链接：${target}`);
  }
  fs.renameSync(temporary, target);
  temporary = undefined;
} catch (error) {
  console.error(`OpenSpec 团队配置未应用：${error.message}`);
  process.exitCode = 1;
} finally {
  if (temporary) {
    try {
      fs.unlinkSync(temporary);
    } catch (error) {
      if (error.code !== 'ENOENT') {
        console.error(`OpenSpec 临时配置清理失败：${error.message}`);
        process.exitCode = 1;
      }
    }
  }
}
NODE
# 每次调用都会刷新运行时副本；编辑 harness/openspec-profile.json 调整选择集。
# .harness/ 应加入 .gitignore；配置失败时不会执行请求的操作或刷新已有集成。
cd "$harness_project_root"
# XDG_CONFIG_HOME 仅对本次子进程生效；不会隔离用户 Schema、宿主 Skills 或权限。
# 普通命令仍直接 exec CLI；只拦截真正的 init/update，不匹配参数或 Change 名。
# 根级 --no-color 和 -- 不改变子命令位置；帮助/版本由适配器按固定 CLI 语法识别。
harness_generation=false
for harness_argument in "$@"; do
  case "$harness_argument" in
    --no-color|--) continue ;;
    init|update) harness_generation=true ;;
  esac
  break
done
if [[ "$harness_generation" == true ]]; then
  # Node 监督生成进程并转发信号；CLI 失败保留原退出码，不执行后置适配。
  # 适配失败单独报告，并以非零退出，保留真实部分结果供恢复。
  exec env XDG_CONFIG_HOME="$harness_config_root" \
    HARNESS_OPENSPEC_CONFIG="$harness_config_root/openspec/config.json" \
    OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1 \
    OPENSPEC_NO_COMPLETIONS=1 OPENSPEC_NO_ANIMATION=1 \
    "$harness_node" "$harness_project_root/scripts/adapt-openspec-workflows.mjs" \
    --run "$harness_cli" "$@"
fi
# 关闭遥测、更新检查、补全和动画；"$@" 原样转交参数，exec 保留 CLI 的退出状态。
exec env XDG_CONFIG_HOME="$harness_config_root" \
  OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1 \
  OPENSPEC_NO_COMPLETIONS=1 OPENSPEC_NO_ANIMATION=1 \
  "$harness_node" "$harness_cli" "$@"
