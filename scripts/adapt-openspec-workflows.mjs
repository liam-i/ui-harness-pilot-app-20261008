#!/usr/bin/env node
/**
 * Engineering Harness 的项目级 OpenSpec 工作流适配器。
 * 接入时将本文件与 openspec.sh 一起复制到业务项目的 scripts/ 目录。
 *
 * 两组名称分别属于不同层次：
 * - CLI init / update：终端命令，初始化项目集成或刷新已配置宿主的工作流文件。
 * - Agent 工作流：Apply / Update 分别实施 Tasks、修订规划，Explore / Verify 提供显式方法。
 * 本脚本在 CLI 生成文件后适配这四项入口及受控元数据；不执行它们的业务步骤。
 *
 * 【会写入 Agent 指令】下面的 recovery、review 和 adaptBody() 中的范围与替换文本
 * 不是供维护者阅读的注释：它们会成为项目 SKILL.md / Claude 命令文件的正文。
 * 注入位置、目标文件与实际写入点分别在 adaptBody()、targets()、adaptProject()。
 * 这些规则由 Agent 读取后执行；本脚本不监控业务测试、不计恢复轮次、不代替宿主权限。
 *
 * 两个运行入口：
 * - --check [project]：只读核对目标 Profile、入口及受控正文／元数据，不运行 CLI。
 * - --run <selected-cli> <args...>：openspec.sh 内部调用；生成成功后接续适配。
 *   CLI 必须由包装器按既定 A/B 路线选定，不在这里查找另一份安装作为回退。
 *
 * 刷新前的项目外备份、刷新后的自定义合并由接入流程负责。上游 CLI 可能已经覆盖
 * 文件，本脚本不能恢复未备份的定制，也不自行选择额外 Skill、升级或修改上游安装包。
 */
import fs from 'node:fs';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { constants } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const VERSION = '1.12.0';
// 适配政策版本与固定来源提交用于标识受控正文；它们不是业务 Change 的版本号。
const REVISION = 'harness-workflows-v3';
const SOURCE = 'e062b9572be933564ba3899d059377dfa1393e32';
const hash = (text) => createHash('sha256').update(text).digest('hex');
// 原始基线：官方模板经过实际宿主调用形式转换后的完整指令正文的 SHA-256。
// 不含 YAML frontmatter 和正文外空白；同名文件或相同版本号本身不足以通过核对。
// Claude 命令、both 模式的 Skill、skills-only 模式的 Skill 可能有不同的调用引用。
const ORIGINAL = {
  'codex:explore': '23e40e30e078282f9369cf7bcf146128bad780887a64d349acea6041d00d7d52',
  'claude:explore': '1ea3dafe32b5f8e38150c3fb9afd07d819fce11ac78c6e7b44678509049c310a',
  'claude-skill:explore': '99fecccd608955106f491078ff4b4b682651bebc3f22fb1b130bd19d41aed9e4',
  'claude-skill-only:explore': 'e55c5437c11dc26bda8bbd398a542c051f8b0aa83b19646d9f764702ac058898',
  'codex:verify': '63fd90c39d36b104ba27f7365a3fa9c3e09c51c90e60c6fc477d7aceafbbe265',
  'claude:verify': '78c64dc093af61bc58c267132d411d8aad369e8bd581492f44fa707a5297d0ab',
  'claude-skill:verify': '112868b23d87bbd39b823af65e26eebea08ed12151eed13419cf9410bf52ae0b',
  'claude-skill-only:verify': '3ac1746428f9cce52116c48f92ce53b8b65af301dfde3ab7ab3c8e1d6a797f7c',
  'codex:apply': 'ff7d3e7eb82bfb823816e3ffea094c51adc12cb2a49685fc1b89516daf24ea24',
  'codex:update': '642789363b1b985d82dd5c10576cf023ba15f6de0185fad0ba66d90102e5f1c8',
  'claude:apply': '652ce30fbb583f6827aedd8a860556e7825679d352b14abeeecd3f9c77b97947',
  'claude:update': 'b7081175de9e90fe525324bf1090413bb6639b40b3ec23d5d6eae1e0e0b99c86',
  'claude-skill:apply': '652ce30fbb583f6827aedd8a860556e7825679d352b14abeeecd3f9c77b97947',
  'claude-skill:update': 'a0be966f0c54001d2eb3847a3b6a1f7442d9c6efeb4f2377c892ae48987df313',
  'claude-skill-only:apply': '5efaf640fcf0a6bfeb6bf7b11bc7c1b901f0ff64125380fc19d2b602166741bd',
  'claude-skill-only:update': '21de2db96e0e922bbf4414a610c15bdf75a6005cf1a4c94ed63b9d7877a1172f',
};
// 适配基线：加入 Harness 指令并替换冲突规则后的完整正文的 SHA-256。
// 修改注入文本会改变这些值，须先审阅政策与生成差异、验证后再更新；不能读取当前
// 项目文件后自动“学习”新哈希，否则未知定制或损坏内容也会被错误接受。
const ADAPTED = {
  'codex:explore': 'b77fa25e5f7d7691d908cb97b59e2c76bcd8999e44c3e60148e82f8b1dc5f908',
  'claude:explore': '4bb973492a46647d7cd3ac199ce1e938f8005151abb90d00952185b94cbb0502',
  'claude-skill:explore': '0b1128c1ca1729c9642e7568c4da76dcaa381f62afb8b8408dc586644883f419',
  'claude-skill-only:explore': 'c81c9fbe2446eac1c0079f06d45dc2f84b84cdc99cce3874c8bc42b713994cf6',
  'codex:verify': '640eb97d39aab02abcc98273c22aee13d3a9268cf2e00b95f283efe09c0a9569',
  'claude:verify': '6a1f523a79f18cc327539db21c703960603fc89b92c4680c8c1d71b6151274a2',
  'claude-skill:verify': '7d37d915179895b7faacf6d6478f8a75272dff94d2bb0e50add719e8b4cb5045',
  'claude-skill-only:verify': 'd4135f4d1c830e0ee8084484babb4cacd70de4ecf7f49dbcd4e23f450f6459bb',
  'codex:apply': '6f841030d3e5b35615d1e39e887d7a5dc927f460d15111ae86a18871eedccaef',
  'codex:update': '617f48f3cea9555e1f81b13dba9ffc038d2a6575bcd4243ec90b68683a384ddb',
  'claude:apply': '8dd24c89c95132a1a54304f4200da458c1f9c7c1a4ceb2d14abf2044fe4a94e5',
  'claude:update': '3392f2b56eed78e5c83cb0981ca3e749cc938b73c809256f99a9c4c14c0abffb',
  'claude-skill:apply': '8dd24c89c95132a1a54304f4200da458c1f9c7c1a4ceb2d14abf2044fe4a94e5',
  'claude-skill:update': 'feb5df849ebfd7e83feb9af9f1161e13d7fa4a4e993cc73513efd91218712259',
  'claude-skill-only:apply': '51adbdbd3c8f96f214c32c176a1e79d5cb1864f37aa213bda849632309798357',
  'claude-skill-only:update': '0f829664eb854d81d4463cdde795df081619a670b4fb07094ade24da47952ba1',
};

// 【注入文本 1：Apply 失败恢复政策】以下英文模板字符串会写入 Apply 的指令正文，
// 保留英文是为了衔接上游正文；本段中文注释不会进入生成文件。
// 内容区分真实行为 RED、授权内普通执行错误、必须停止的缺口；两轮上限由执行
// Apply 的 Agent 按当前 Task 证据维护，不是本脚本内的自动重试循环。
// 此政策仅适用于实际获批的 Apply，不能把只读／规划阶段变成实施授权。
const recovery = `**Harness recovery policy**

Read the applicable project AGENTS.md. Within an actually authorized Apply, continue ordinary diagnosis, correction and targeted verification for the current task without asking again for the same authorization. This policy does not authorize planning-only, read-only, unrelated work, new tools/dependencies, global configuration changes, or another phase.

- Confirmed assertion failures caused by the approved missing behavior are valid RED: follow the project's TDD method, implement minimally and verify GREEN. If an implementation attempt still fails that valid behavior assertion, continue the same TDD cycle; an attempted GREEN is not a successful GREEN or an execution-recovery round. Compilation errors, zero selected tests, stale runners and faulty test interaction are not RED or passing evidence.
- For execution/test-method problems, first inspect the relevant facts. Correct only the current task's implementation, tests or approved local tooling, preserving behavior, design, dependencies, required checks and acceptance criteria. Explain test corrections and retain the original failure. Do not weaken assertions, skip checks or relax an approved response-time limit to get GREEN.
- Use only approved project commands and isolated environments. Do not repeat an identical failed action without new evidence or expand an unproductive investigation indefinitely. Ordinary diagnosis does not implicitly load systematic-debugging or another optional Skill.
- Stop after two unsuccessful correction-and-targeted-retest rounds for the same unresolved failure. Reads/polls are not rounds; a new error caused by the correction, renaming a task or starting another session does not reset the count. Record the unresolved cause, attempted fixes and count briefly under the current task. Resolving the original check and affected regressions ends recovery; an unrelated successful command does not. Genuine behavior RED/GREEN is not a recovery round; verify that classification rather than relabeling errors.
- Stop earlier for missing TDD, CLI blocked, conflicting requirements/design, an unusable required acceptance method, unprotected user work/resources, or a need for new scope/authority. Preserve incomplete tasks and do not start another implementation task. State the evidence, attempts and concrete missing decision; do not ask a content-free “continue?” or rerun a proven ineffective action after a generic “continue”.
- When the approved design or required acceptance method must change, prepare the complete affected-artifact diff for Update's coherent review before asking for approval. A method suggestion or approval of a direction alone is not review of unshown revisions. After approval, write and cross-check the planning set before editing dependent implementation or tests; then resume under existing implementation authorization without another per-file or “continue?” confirmation. Honor any explicit user pause or planning-only boundary.
- If an authorized operation needs host permission, use the host's approval mechanism directly; do not add duplicate chat approval and do not bypass denial. Honor an explicit user stop. Already authorized logging, stopping this task's processes and restoring its test state may continue as cleanup; report any cleanup failure or additional permission needed. Preserve the original operation's failure separately when cleanup also fails; an overall failure code alone does not describe both failures.

Project rules and explicit user constraints determine the authorized scope. This adaptation replaces the upstream blanket error-pause policy; it does not override CLI state, schema instructions, required verification or an explicit user decision.`;

// 【注入文本 2：Update 整组审阅政策】替换原 Update 第 5 步的逐 Artifact 审批。
// 要求先展示连贯的完整差异，获批后写入并交叉校验；包括部分批准、用户并发修改、
// 部分写入失败的保护。这里的 apply 指“写入已批准的规划修订”，不是业务 Apply。
// Update 不实施代码；本段也不把 Apply 的两轮工程恢复授权扩展到规划阶段。
const review = `5. **Review and apply one coherent revision set**
   - Read the applicable project AGENTS.md and obtain affected artifact instructions/rules before preparing substantial revisions. Use the actual schema ids and existingOutputPaths.
   - Prepare all interdependent revisions for this request together. Show the reasons and a complete reviewable diff, including reopened tasks, acceptance changes and still-valid evidence. A temporary preview is not a second authoritative plan.
   - Write the coherent set after user approval. Do not request per-file approval for the same already approved set. Honor an explicit request for artifact-by-artifact review.
   - For partial approval, preserve rejected content and do not write a knowingly inconsistent subset. Ask only for the unresolved substantive decision. If source files change before writing, preserve user changes and recheck the affected diff/approval; unchanged approved parts need no repeated review.
   - Preserve the before-state for your writes. On a partial write failure, report actual state and recover only your own approved changes; never overwrite concurrent user edits with a whole old file. Cross-check the full set and run applicable validation before reporting planning ready. Do not enter implementation from Update.
   - Mere task-status/evidence corrections for existing approved requirements do not require a new planning review; follow the project's existing task/phase authorization instead of manufacturing an Update.`;

// 精确且仅替换一次：片段缺失、重复或被改动时拒绝猜测，不进行模糊匹配。
function replaceOnce(text, before, after) {
  if (text.split(before).length !== 2) throw new Error('固定模板片段不唯一或已改变，拒绝猜测替换');
  return text.replace(before, after);
}

/**
 * 纯文本转换，不读写文件。仅处理四种已知工作流，不替代阶段授权。
 * 必须同时改掉与新政策冲突的原句；只追加说明会留下两套相反的指令。
 * 返回的字符串稍后由 adaptProject() 包装标识并写入相应项目入口。
 */
export function adaptBody(body, workflow) {
  if (workflow === 'apply') {
    // CLI 的生成指引不是规划写入授权；在 blocked 分支本身消除跨阶段歧义。
    const blocked = body.split('\n').filter((line) => line.startsWith('   - If `state: "blocked"`'));
    if (blocked.length !== 1) throw new Error('固定 blocked 分支缺失或重复');
    body = replaceOnce(body, blocked[0], '   - If `state: "blocked"` (missing artifacts): stop dependent implementation and report the gap and proposed planning work. You may inspect `openspec status --change "<name>" --json` and `openspec instructions <artifact-id> --change "<name>" --json` for actual schema paths and requirements; these reads do not authorize creating or editing planning files. A general Apply request does not authorize filling the gap. With explicit planning authorization (including authorization already given), follow the actual schema instructions to complete the planning, have it reviewed, then resume authorized Apply. Do not install another workflow just to clear this state.');
    // 【注入位置】在原 Apply 的 Pause if 列表前插入 recovery，保持原列表缩进。
    // 空行保持为空，生成文件才能通过正常的 Git 行尾空白检查。
    const indentedRecovery = recovery.split('\n').map((line) => line ? `   ${line}` : '').join('\n');
    body = replaceOnce(body, '   **Pause if:**', `${indentedRecovery}\n\n   **Pause if:**`);
    // 【注入文本 3】下面三段替换字符串也会写入 SKILL.md / 命令正文：
    // 将无条件遇错等待收窄为恢复耗尽或需要新决定；真实设计／范围冲突仍须暂停。
    body = replaceOnce(body, '   - Error or blocker encountered → report and wait for guidance',
      '   - Recovery reaches its limit or needs a new decision/authority → report the specific gap and wait; ordinary in-scope execution errors follow the Harness recovery policy above');
    body = replaceOnce(body, '- If implementation reveals issues, pause and suggest artifact updates',
      '- If implementation reveals a conflict with the approved design or scope, pause and suggest artifact updates; ordinary implementation errors follow the Harness recovery policy');
    body = replaceOnce(body, "- Pause on errors, blockers, or unclear requirements - don't guess",
      '- Follow the Harness recovery policy for execution errors; pause for unresolved blockers or required decisions, and never guess or weaken acceptance');
  } else if (workflow === 'update') {
    // 【注入位置】以固定的第 5、6 步标题定位整段，用 review 替换旧的逐份确认。
    const start = body.indexOf('5. **Confirm and apply, one artifact at a time**');
    const end = body.indexOf('\n6. **Point to the next step', start);
    if (start < 0 || end < 0) throw new Error('Update 审阅段缺失');
    body = replaceOnce(body, body.slice(start, end), `${review}\n`);
    // 【注入文本 4】同步修改 guardrail，避免仍要求每个文件重复确认。
    body = replaceOnce(body, '- Confirm every edit with the user before writing.',
      '- Obtain approval for the coherent revision set before writing; respect existing approval and explicit per-artifact review. Partial approval or writing failure must not leave planning falsely marked ready.');
    // 【注入文本 5】第 4 步只准备修改，不能在第 5 步审阅前就写入正式 Artifact。
    body = replaceOnce(body, '   - Apply the requested edit. Then check every other existing artifact against it',
      '   - Prepare the requested edit for review. Then check every other existing artifact against it');
  } else if (workflow === 'explore') {
    body = `**Harness explicit method scope**

Use this method only after the user explicitly selects Explore and the host makes this entry available. An Agent suggestion, an ordinary clarification request or an Agent-written skill name is not that selection. Read the applicable project AGENTS.md; identify the question, known facts, uncertainty, desired output, exit condition and originating phase. Keep the record in conversation by default; do not create a parallel Feature plan. Once the bounded investigation reaches its exit condition, explicitly state that Explore has ended and return the findings and unresolved decisions to the originating phase. Do not say the completed investigation remains in Explore, or treat this method's presence in context as continuing authority over later work.

No code, including temporary experiments, or schema/template/configuration changes are allowed inside Explore. Exit this method before an authorized isolated experiment or implementation. New full planning goes through Propose; substantial existing planning revisions use Update and coherent review. Bounded artifact capture follows the explicit first-write confirmation below and grants no implementation authority. Existing authorized Apply can resume after leaving Explore without manufacturing another Change. A strict request to leave every original-project file unchanged also prohibits wrapper queries that refresh .harness; use existing facts or an explicitly authorized equivalent isolated copy and report checks not run. Do not implicitly invoke another optional method or reset a stopped Apply's recovery count.

${body}`;
    body = replaceOnce(body, 'remind them to exit explore mode first and create a change proposal.',
      'remind them to exit explore mode first and return to the appropriate authorized phase (Propose for new planning, or the existing reviewed Change for authorized Apply).');
  } else if (workflow === 'verify') {
    body = `**Harness explicit verification scope**

Use this method only after the user explicitly selects Verify and the host makes this entry available. A project-required method remains required, but user-only host invocation must be satisfied; never read a disabled entry to simulate invocation. Ordinary review does not replace an already selected Verify. Read the applicable project AGENTS.md and verify the specified active Change using its actual schema and paths. Do not create an empty Change for Tiny, restore an archive just to inspect it, or silently switch an unsupported target or required method.

The default output is a report, not edits to code, tests, artifacts, task checkboxes, main specs or archives. You may run existing necessary checks within authorized scope; state their environment and generated test/build output. Reading instructions apply obtains context only: it does not enter Apply, load TDD, execute Tasks or authorize planning writes. No automatic Debugging, Verification, fixes, Archive, Merge or publication follows from this method.

Report the scope, artifact/code versions or diff, environment and reviewer. Map each applicable Requirement and Scenario through implementation, test or demonstration step, actual evidence and its current validity, then gaps or justified non-applicability. Include main-spec plus delta semantics, applicable Design and Tasks. Existing test code is not an executed result; old evidence is not a fresh run. Reuse evidence only while the relevant spec, code, inputs, dependencies and environment remain valid; otherwise rerun affected checks or report uncertainty. Explicitly selected Superpowers Verification still requires its fresh complete required checks, including requirement coverage. One Agent using two methods is not an independent reviewer.

Partial in-progress audits are allowed when explicitly scoped; retain incomplete Tasks and report the overall Change as in progress. Do not create a self-blocking Task that must already be checked before this report. Required gaps return to existing Tasks and authorized Apply; substantial planning or required-method changes first need Update's complete preview, review and planning cross-check. Respect the existing recovery limit; switching methods does not reset it.

${body}`;
    body = replaceOnce(body, '     - Recommendation: "Complete task: <description>" or "Mark as done if already implemented"',
      '     - Report the incomplete task and evidence gap; do not mark it done in Verify. Return any justified status correction to the authorized task workflow.');
    body = replaceOnce(body, '   - For each requirement from delta specs:', '   - For each applicable requirement from main specs and delta semantics:');
    body = replaceOnce(body, '   - For each scenario in delta specs (marked with "#### Scenario:"):',
      '   - For each applicable scenario from main specs and delta semantics (marked with "#### Scenario:"):');
    body = replaceOnce(body, '   - If no design.md: Skip design adherence check, note "No design.md to verify against"',
      '   - If Design is absent, check actual schema and approved scope: report a required missing artifact as a gap, or explain legitimate non-applicability.');
    body = replaceOnce(body, '   - If CRITICAL issues: "X critical issue(s) found. Fix before archiving."\n   - If only warnings: "No critical issues. Y warning(s) to consider. Ready for archive (with noted improvements)."\n   - If all clear: "All checks passed. Ready for archive."',
      '   - Classify the required scope as satisfied, required gaps found, unable to judge, or partial audit. These are report conclusions, not new workflow state files.\n   - Severity alone never determines acceptance. A WARNING about a required Scenario, Design constraint or missing evidence prevents a satisfied conclusion; uncertainty remains explicit.\n   - State remaining task, independent review, final-candidate CI and phase/authorization conditions. A satisfied report does not authorize Archive or delivery.');
    body = replaceOnce(body, '- **Correctness**: Use keyword search, file path analysis, reasonable inference - don\'t require perfect certainty',
      '- **Correctness**: Search locates candidates; substantiate required behavior with implementation and actual valid evidence. Mark inference or uncertainty explicitly.');
    body = replaceOnce(body, '- **False Positives**: When uncertain, prefer SUGGESTION over WARNING, WARNING over CRITICAL',
      '- **Uncertainty**: Explain confidence and missing evidence; lowering issue severity does not discharge a required check.');
    body = replaceOnce(body, '- If only tasks.md exists: verify task completion only, skip spec/design checks\n- If tasks + specs exist: verify completeness and correctness, skip design\n- If full artifacts: verify all three dimensions\n- Always note which checks were skipped and why',
      '- Determine required artifacts from the actual schema and approved scope before skipping anything. Required missing specs, Design or evidence are gaps.\n- For a legitimate no-delta change, check applicable main specs and approved technical goals; do not fabricate a delta or infer no verification duty.\n- Verify all applicable dimensions and explain each legitimate non-applicability; absent files alone do not justify skipping.');
  } else throw new Error(`未知受控工作流：${workflow}`);
  return body;
}

/**
 * 从包装器选中的 CLI 实际安装目录加载模板，不从任意项目 Skill 反推官方内容。
 * bin/openspec.js 的真实路径向上两层为包根目录；ESM 用文件 URL 支持路径含空格。
 * 这里只调用模板生成与引用转换函数，不执行 init/update，不写项目文件。
 */
export async function sourceBodies(cli) {
  const root = path.dirname(path.dirname(fs.realpathSync(cli)));
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  if (pkg.name !== '@fission-ai/openspec' || pkg.version !== VERSION) throw new Error(`适配仅支持 OpenSpec ${VERSION}`);
  const module = (file) => import(pathToFileURL(path.join(root, 'dist', file)).href);
  const apply = await module('core/templates/workflows/apply-change.js');
  const update = await module('core/templates/workflows/update-change.js');
  const explore = await module('core/templates/workflows/explore.js');
  const verify = await module('core/templates/workflows/verify-change.js');
  const { transformToCodexCompatibleSkillReferences: render,
    transformToSkillReferences: renderSkillOnly } = await module('utils/command-references.js');
  const bodies = {
    'codex:apply': render(apply.getApplyChangeSkillTemplate().instructions).trim(),
    'codex:update': render(update.getUpdateChangeSkillTemplate().instructions).trim(),
    'claude:apply': apply.getOpsxApplyCommandTemplate().content.trim(),
    'claude:update': update.getOpsxUpdateCommandTemplate().content.trim(),
    'claude-skill:apply': apply.getApplyChangeSkillTemplate().instructions.trim(),
    'claude-skill:update': update.getUpdateChangeSkillTemplate().instructions.trim(),
    // Claude 仅投递 Skills 时引用 /openspec-*；同时投递命令时保留 /opsx:*。
    'claude-skill-only:apply': renderSkillOnly(apply.getApplyChangeSkillTemplate().instructions).trim(),
    'claude-skill-only:update': renderSkillOnly(update.getUpdateChangeSkillTemplate().instructions).trim(),
  };
  for (const [workflow, skill, command] of [
    ['explore', explore.getExploreSkillTemplate(), explore.getOpsxExploreCommandTemplate()],
    ['verify', verify.getVerifyChangeSkillTemplate(), verify.getOpsxVerifyCommandTemplate()],
  ]) {
    bodies[`codex:${workflow}`] = render(skill.instructions).trim();
    bodies[`claude:${workflow}`] = command.content.trim();
    bodies[`claude-skill:${workflow}`] = skill.instructions.trim();
    bodies[`claude-skill-only:${workflow}`] = renderSkillOnly(skill.instructions).trim();
  }
  for (const [key, body] of Object.entries(bodies)) {
    // 在 CLI 开始生成前同时核对来源正文和转换结果，避免生成后才发现版本漂移。
    if (hash(body) !== ORIGINAL[key]) throw new Error(`固定来源模板不匹配：${key}`);
    if (hash(adaptBody(body, key.split(':')[1])) !== ADAPTED[key]) throw new Error(`适配实现与受审基线不匹配：${key}`);
  }
  return bodies;
}

// 【写入文件的标识】HTML 注释包围完整受控正文，记录投递形式、版本和来源。
// 有标识并不等于内容正确；checkText() 还会核对完整正文哈希。
function marker(key) {
  return `<!-- ${REVISION} ${key} OpenSpec ${VERSION} ${SOURCE} -->`;
}
const END = `<!-- /${REVISION} -->`;

// 沿项目内路径逐层用 lstat 核对，拒绝符号链接、特殊文件和多硬链接目标。
// 即使叶文件不存在，也不能通过上级符号链接把写入引向项目外。
// 返回 false 表示某段不存在；已存在但不符合要求的路径直接报错。
function regularPath(project, target, directory = false) {
  const relative = path.relative(project, target);
  if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error(`目标在项目外：${target}`);
  let current = project;
  const parts = relative.split(path.sep);
  for (let i = 0; i < parts.length; i++) {
    current = path.join(current, parts[i]);
    const stat = fs.lstatSync(current, { throwIfNoEntry: false });
    if (!stat) return false;
    const isDir = i < parts.length - 1 || directory;
    if (stat.isSymbolicLink() || (isDir ? !stat.isDirectory() : !stat.isFile() || stat.nlink !== 1)) {
      throw new Error(`入口须为项目内普通${isDir ? '目录' : '单链接文件'}：${current}`);
    }
  }
  return true;
}

// 与固定 profiles.js / skill-generation.js 的名称和依赖一致；不从目录名猜 workflow。
const SKILLS = {
  propose: 'openspec-propose', explore: 'openspec-explore', new: 'openspec-new-change',
  continue: 'openspec-continue-change', apply: 'openspec-apply-change', update: 'openspec-update-change',
  ff: 'openspec-ff-change', sync: 'openspec-sync-specs', archive: 'openspec-archive-change',
  'bulk-archive': 'openspec-bulk-archive-change', verify: 'openspec-verify-change', onboard: 'openspec-onboard',
};
const CONTROLLED = ['apply', 'update', 'explore', 'verify'];
const DESCRIPTIONS = {
  explore: 'Use only when the user explicitly selects Explore for bounded investigation and options discussion. Do not load for ordinary clarification or implement code.',
  verify: 'Use only when the user explicitly selects Verify to check a specified Change against applicable artifacts, implementation and evidence. Ordinary tests or review do not invoke it; it grants no archive authority.',
};

function selection(config) {
  if (!config || Array.isArray(config) || typeof config !== 'object' ||
      Object.keys(config).some((key) => !['profile', 'delivery', 'workflows'].includes(key)) ||
      !['core', 'custom'].includes(config.profile) || !['commands', 'skills', 'both'].includes(config.delivery)) {
    throw new Error('Profile 必须只使用受支持的 profile、delivery、workflows 字段');
  }
  const names = config.workflows;
  if (names !== undefined && (!Array.isArray(names) || names.some((name) => !Object.hasOwn(SKILLS, name)) ||
      new Set(names).size !== names.length)) throw new Error('workflows 必须是无重复的已知名称数组');
  if (config.profile === 'custom' && !names?.length) throw new Error('custom 必须提供非空 workflows');
  if (config.profile === 'core' && names?.length) throw new Error('core 不接受会被忽略的 workflows');
  const workflows = config.profile === 'core' ? ['propose', 'explore', 'apply', 'update', 'sync', 'archive'] : [...names];
  if (workflows.some((name) => ['archive', 'bulk-archive'].includes(name)) && !workflows.includes('sync')) workflows.push('sync');
  return { workflows: workflows.sort(), delivery: config.delivery };
}

function projectSelection(project, required) {
  const file = path.join(project, 'harness/openspec-profile.json');
  if (!regularPath(project, file)) {
    if (required) throw new Error(`尚未完成项目配置接入，缺少 Profile：${file}`);
    return null;
  }
  return selection(JSON.parse(fs.readFileSync(file, 'utf8')));
}

// 保守的逐行 YAML 编辑器：顶层普通映射，受控标量为单行，policy 为两空格映射。
// 不重排或序列化其他字段；复杂受控 YAML、重复键、merge/alias 等交给人工合并。
// 未受控 UI / dependencies 的缩进块保持原字节，不作为本工具的通用 YAML 验证范围。
function mapping(text, indent = 0) {
  if (text.includes('\r') || text.includes('\t')) throw new Error('受控 YAML 仅支持 LF 与空格缩进');
  const lines = text.split('\n');
  const entries = new Map();
  let previous;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim() || line.trimStart().startsWith('#')) continue;
    const spaces = line.length - line.trimStart().length;
    if (spaces > indent) {
      if (!previous) throw new Error('YAML 缩进没有所属映射键');
      continue;
    }
    const match = line.slice(indent).match(/^([A-Za-z_][A-Za-z0-9_-]*):(?:[ ]+(.*)|[ ]*)$/);
    if (spaces !== indent || !match) throw new Error(`无法安全解析 YAML 映射：${line}`);
    if (entries.has(match[1])) throw new Error(`YAML 重复键：${match[1]}`);
    if (previous) previous.end = i;
    previous = { start: i, end: lines.length, raw: match[2] || '' };
    entries.set(match[1], previous);
  }
  return { lines, entries };
}

function scalar(raw) {
  // 分离引号外的行尾注释；只接受明确的单行字符串/布尔值。
  let value, end;
  if (raw.startsWith('"')) {
    const match = raw.match(/^"(?:[^"\\]|\\.)*"/);
    if (!match) throw new Error('无法解析 YAML 双引号标量');
    try { value = JSON.parse(match[0]); } catch { throw new Error('不支持此 YAML 转义'); }
    end = match[0].length;
  } else if (raw.startsWith("'")) {
    const match = raw.match(/^'(?:[^']|'')*'/);
    if (!match) throw new Error('无法解析 YAML 单引号标量');
    value = match[0].slice(1, -1).replaceAll("''", "'");
    end = match[0].length;
  } else {
    const match = raw.match(/^(.*?)(\s+#.*)?$/);
    const token = match[1].trimEnd();
    if (!token || /^[!&*|>{}\[\],?%@`]/.test(token) || /:\s/.test(token)) throw new Error('不支持复杂受控 YAML 标量');
    value = token === 'true' ? true : token === 'false' ? false : token;
    end = token.length;
  }
  const suffix = raw.slice(end);
  if (suffix.trim() && !/^\s+#/.test(suffix)) throw new Error('YAML 标量后有不明内容');
  return { value, suffix };
}

function editScalar(text, key, desired, indent = 0) {
  const { lines, entries } = mapping(text, indent);
  const entry = entries.get(key);
  if (!entry) return `${text}${text && !text.endsWith('\n') ? '\n' : ''}${' '.repeat(indent)}${key}: ${JSON.stringify(desired)}\n`;
  if (lines.slice(entry.start + 1, entry.end).some((line) => line.trim() && !line.trimStart().startsWith('#'))) {
    throw new Error(`受控字段须为单行标量：${key}`);
  }
  const { value, suffix } = scalar(entry.raw);
  if (typeof value !== typeof desired) throw new Error(`受控字段类型不匹配：${key}`);
  if (value === desired) return text;
  lines[entry.start] = `${' '.repeat(indent)}${key}: ${JSON.stringify(desired)}${suffix}`;
  return lines.join('\n');
}

export function codexPolicy(text) {
  const { lines, entries } = mapping(text);
  const policy = entries.get('policy');
  if (!policy) return `${text}${text && !text.endsWith('\n') ? '\n' : ''}policy:\n  allow_implicit_invocation: false\n`;
  if (policy.raw.trim() && !policy.raw.trimStart().startsWith('#')) throw new Error('policy 须为普通缩进映射，不支持别名或内联对象');
  const block = lines.slice(policy.start + 1, policy.end).join('\n');
  const parsed = mapping(block, 2);
  for (const [key, entry] of parsed.entries) {
    if (/^[!&*]/.test(entry.raw)) throw new Error(`policy 不支持别名或标签：${key}`);
  }
  const after = editScalar(block, 'allow_implicit_invocation', false, 2);
  // slice 边界本身携带换行；仅在两段之间补一个换行，保留块外文本。
  return lines.slice(0, policy.start + 1).join('\n') + '\n' + after +
    (policy.end < lines.length ? (after.endsWith('\n') ? '' : '\n') + lines.slice(policy.end).join('\n') : '');
}

function header(text) {
  const match = text.match(/^---\n([\s\S]*?)\n---\n/);
  if (!match) throw new Error('入口须有 LF 格式的 YAML frontmatter');
  return match;
}

function entryMetadata(text, key) {
  const workflow = key.split(':')[1];
  if (!DESCRIPTIONS[workflow]) return text;
  const h = header(text);
  const expected = key.startsWith('claude:') ? `OPSX: ${workflow === 'explore' ? 'Explore' : 'Verify'}` : SKILLS[workflow];
  // 比较编辑结果仅作校验，同时拒绝标量后的非法缩进；不只核对首行值。
  if (editScalar(h[1], 'name', expected) !== h[1]) throw new Error(`入口 name 与投递不匹配：${key}`);
  let yaml = editScalar(h[1], 'description', DESCRIPTIONS[workflow]);
  if (key.startsWith('claude')) {
    const entry = mapping(yaml).entries.get('user-invocable');
    if (entry && scalar(entry.raw).value !== true) throw new Error('user-invocable 已限制用户入口，须先审阅项目停用决定');
    yaml = editScalar(yaml, 'disable-model-invocation', true);
  }
  return `---\n${yaml.replace(/\n$/, '')}\n---\n${text.slice(h[0].length)}`;
}

// 固定版本已知的非受控宿主目录。这里只报告实际 OpenSpec 痕迹，普通 .github 等不算安装。
// .agents 是共享投递位置；文件检查不能判定读取它的所有宿主，输出始终限定支持范围。
const OTHER_ROOTS = ['.amazonq', '.agent', '.augment', '.bob', '.cline', '.commandcode', '.codeartsdoer',
  '.codex', '.devin', '.windsurf', '.forge', '.codebuddy', '.continue', '.cospec', '.crush', '.cursor',
  '.factory', '.gemini', '.github', '.hermes', '.iflow', '.junie', '.kilocode', '.kimi-code', '.kimi',
  '.kiro', '.lingma', '.minimax', '.vibe', '.omp', '.opencode', '.pi', '.codeassistant', '.qoder',
  '.qwen', '.rovodev', '.roo', '.trae', '.zed', '.zcode', '.agents/workflows'];
function unsupportedSurfaces(project) {
  const found = [];
  const ownerFile = path.join(project, '.agents/skills/.openspec-target');
  if (regularPath(project, ownerFile)) {
    const owner = fs.readFileSync(ownerFile, 'utf8').trim();
    if (owner !== 'codex') found.push(`.agents/skills/.openspec-target=${JSON.stringify(owner)}`);
  }
  function scan(directory, depth) {
    if (!regularPath(project, directory, true)) return;
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (/^(openspec[-.]|opsx(?:[-.:]|$))/.test(entry.name)) { found.push(path.relative(project, path.join(directory, entry.name))); continue; }
      if (entry.isDirectory() && depth > 0) scan(path.join(directory, entry.name), depth - 1);
    }
  }
  for (const directory of OTHER_ROOTS) scan(path.join(project, directory), 2);
  return found;
}

// 枚举实际表面，每种已安装表面均须匹配目标 Profile，包括未改正文的入口。
// Codex 固定投递 Skills；Claude 按 commands / skills / both 生成，残留镜像也须检查。
function targets(project, selected, requestedTools) {
  const result = [], surfaces = [];
  for (const [surface, directory, kind] of [
    ['codex', '.agents/skills', 'skill'], ['claude', '.claude/commands/opsx', 'command'],
    ['claude-skill', '.claude/skills', 'skill'],
  ]) {
    const root = path.join(project, directory);
    const entries = regularPath(project, root, true) ? fs.readdirSync(root) : [];
    const installed = entries.some((name) => kind === 'skill' ? name.startsWith('openspec-') : name.endsWith('.md'));
    if (installed) surfaces.push(surface);
    if (!installed) continue;
    const expected = selected.workflows.map((workflow) => kind === 'skill' ? SKILLS[workflow] : `${workflow}.md`);
    const actual = entries.filter((name) => kind === 'skill' ? name.startsWith('openspec-') : name.endsWith('.md'));
    const extra = actual.filter((name) => !expected.includes(name));
    if (extra.length) throw new Error(`未选残留入口：${directory}/${extra.join(', ')}`);
    for (const workflow of selected.workflows) {
      const file = path.join(root, kind === 'skill' ? `${SKILLS[workflow]}/SKILL.md` : `${workflow}.md`);
      if (!regularPath(project, file)) throw new Error(`已配置投递缺少入口：${file}`);
      if (!CONTROLLED.includes(workflow)) continue;
      const keys = [`${surface}:${workflow}`];
      if (surface === 'claude-skill') keys.push(`claude-skill-only:${workflow}`);
      result.push({ file, keys, workflow, sidecar: surface === 'codex' && DESCRIPTIONS[workflow] ? path.join(path.dirname(file), 'agents/openai.yaml') : null });
    }
  }
  const wanted = new Set(surfaces);
  if (requestedTools?.includes('codex')) wanted.add('codex');
  if (surfaces.some((name) => name.startsWith('claude')) || requestedTools?.includes('claude')) {
    if (selected.delivery !== 'skills') wanted.add('claude');
    if (selected.delivery !== 'commands') wanted.add('claude-skill');
  }
  for (const surface of wanted) if (!surfaces.includes(surface)) throw new Error(`所选投递缺少全部入口：${surface}`);
  if ((selected.delivery === 'commands' && surfaces.includes('claude-skill')) ||
      (selected.delivery === 'skills' && surfaces.includes('claude'))) throw new Error('Claude 实际投递与 Profile delivery 不一致，保留残留入口供审阅');
  return { files: result, surfaces };
}

// 只核对受控正文、描述和 Claude 调用字段；Codex sidecar 在项目预检中单独检查。
export function checkText(text, key) {
  const h = header(text);
  if (!key.startsWith('claude:')) {
    const parsed = mapping(h[1]);
    const metadata = parsed.entries.get('metadata');
    if (!metadata || (metadata.raw.trim() && !metadata.raw.trimStart().startsWith('#'))) throw new Error(`入口生成 metadata 结构不匹配：${key}`);
    const fields = parsed.lines.slice(metadata.start + 1, metadata.end).join('\n');
    if (editScalar(fields, 'generatedBy', VERSION, 2) !== fields) throw new Error(`入口版本不匹配：${key}`);
  }
  const start = marker(key);
  if (text.split(start).length !== 2 || text.split(END).length !== 2 ||
      (text.match(/<!-- \/?harness-workflows-/g) || []).length !== 2) throw new Error(`适配标识缺失或重复：${key}`);
  const body = text.split(start)[1].split(END)[0];
  if (body !== `\n${body.trim()}\n` || hash(body.trim()) !== ADAPTED[key]) throw new Error(`受控正文已改变：${key}`);
  if (entryMetadata(text, key) !== text) throw new Error(`受控 description / disable-model-invocation 不匹配：${key}`);
}

function samePreimage(project, file, before) {
  const exists = regularPath(project, file);
  if ((before === null ? exists : !exists || fs.readFileSync(file, 'utf8') !== before)) throw new Error(`入口在预检后改变：${file}`);
}

// 多文件不构成事务。先写完整的同目录独占临时文件；已有目标 rename 替换。
// 新目标用 link 独占发布，EEXIST 时保留并发用户文件，再删除本次临时链接。
// 所有预检通过后才创建 sidecar 父目录，逐层重新检查；只清理本次创建的空目录。
function atomicWrite(file, text, before, project) {
  samePreimage(project, file, before);
  const created = [];
  let temporary;
  try {
    const parents = path.relative(project, path.dirname(file)).split(path.sep);
    let current = project;
    for (const part of parents) {
      current = path.join(current, part);
      if (!regularPath(project, current, true)) { fs.mkdirSync(current); created.push(current); }
    }
    samePreimage(project, file, before);
    const candidate = path.join(path.dirname(file), `.harness-${randomUUID()}.tmp`);
    const mode = before === null ? 0o644 : fs.statSync(file).mode & 0o777;
    const fd = fs.openSync(candidate, 'wx', mode);
    temporary = candidate; // 只清理本进程成功独占创建的文件。
    try {
      fs.writeFileSync(fd, text);
      // 新文件遵从 umask；替换已有文件则恢复原权限，不能被当前 umask 意外收窄。
      if (before !== null) fs.fchmodSync(fd, mode);
    } finally { fs.closeSync(fd); }
    samePreimage(project, file, before);
    if (before === null) {
      fs.linkSync(temporary, file);
      fs.unlinkSync(temporary);
    } else fs.renameSync(temporary, file);
    temporary = null;
  } finally {
    if (temporary && fs.existsSync(temporary)) fs.unlinkSync(temporary);
    for (const dir of created.reverse()) {
      try { fs.rmdirSync(dir); } catch (error) { if (!['ENOTEMPTY', 'ENOENT'].includes(error.code)) throw error; }
    }
  }
}

/** 全部正文、元数据、目标集合先预检。--check 不启动 CLI，不创建目录或配置。 */
export function adaptProject(directory, bodies, { check = false, write = atomicWrite, context } = {}) {
  const project = fs.realpathSync(directory);
  const own = projectSelection(project, check || !context);
  const selected = context?.selection || own;
  if (own && JSON.stringify(own) !== JSON.stringify(selected)) throw new Error('目标 Profile 与本次生成集合 / delivery 不一致；未修改目标配置');
  const unsupported = unsupportedSurfaces(project);
  const requested = context?.tools?.filter((tool) => !['codex', 'claude', 'none'].includes(tool)) || [];
  if (unsupported.length || requested.length) throw new Error(`存在未纳入政策验收的宿主：${[...requested, ...unsupported].join(', ')}`);
  const { files, surfaces } = targets(project, selected, context?.tools);
  if (check && surfaces.length === 0) throw new Error('未发现已适配的 Codex/Claude OpenSpec 入口');
  const changes = [], differences = [];
  for (const { file, keys, workflow, sidecar } of files) {
    const before = fs.readFileSync(file, 'utf8');
    try {
      let after, key;
      if (before.includes('harness-workflows-') || check) {
        const matches = keys.filter((candidate) => before.includes(marker(candidate)));
        if (matches.length !== 1) throw new Error('适配标识缺失或版本 / 投递冲突；旧政策需保护后 update --force');
        key = matches[0];
        checkText(before, key);
        after = before;
      } else {
        const matches = keys.filter((candidate) => before.includes(bodies[candidate]));
        if (matches.length !== 1) throw new Error('固定模板正文缺失或投递形式不唯一');
        key = matches[0];
        after = replaceOnce(before, bodies[key], `${marker(key)}\n${adaptBody(bodies[key], workflow)}\n${END}`);
        const controlled = entryMetadata(after, key);
        if (controlled !== after) {
          const old = mapping(header(after)[1]).entries;
          const description = old.get('description');
          const invocation = old.get('disable-model-invocation');
          differences.push(`${path.relative(project, file)}: description ${description ? JSON.stringify(scalar(description.raw).value) : '缺失'} → ${JSON.stringify(DESCRIPTIONS[workflow])}${key.startsWith('claude') ? `, disable-model-invocation=true（此前 ${invocation ? JSON.stringify(scalar(invocation.raw).value) : '缺失'}）` : ''}`);
        }
        after = controlled;
        checkText(after, key);
      }
      changes.push({ file, before, after });
      if (sidecar) {
        const exists = regularPath(project, sidecar);
        const raw = exists ? fs.readFileSync(sidecar, 'utf8') : null;
        const controlled = codexPolicy(raw || '');
        if (check && raw !== controlled) throw new Error(`policy.allow_implicit_invocation 须为 false：${sidecar}`);
        if (raw !== controlled) differences.push(`${path.relative(project, sidecar)}: policy.allow_implicit_invocation=false（此前 ${raw?.match(/^  allow_implicit_invocation: *(.*)$/m)?.[1] || '缺失'}${raw === null ? '，新建文件' : ''}）`);
        changes.push({ file: sidecar, before: raw, after: controlled });
      }
    } catch (error) { throw new Error(`${file}: ${error.message}`); }
  }
  const written = [];
  let attempted;
  try {
    for (const { file, before, after } of changes) {
      if (before === after) continue;
      attempted = path.relative(project, file);
      samePreimage(project, file, before);
      write(file, after, before, project);
      written.push(path.relative(project, file));
    }
  } catch (error) {
    throw new Error(`${error.message}；失败目标：${attempted}；已适配：${written.join(', ') || '无'}。保留实际结果和刷新前原始备份，核对失败目标是否已发布后再接续。`);
  }
  return { checked: files.length, surfaces, workflows: selected.workflows, written, differences, configured: Boolean(own) };
}

// 使用同一安装包的 Commander 复现固定版本 init/update 参数语法，仅确定目标目录。
// 解析 action 只记录路径，不生成文件。参数值或 Change 名中的 update 不是生成命令。
// 帮助／版本仍交给真实 CLI 输出；解析没有得到目标时不做来源转换和后置适配。
// 上游升级时必须同时复核此语法和 openspec.sh 的子命令识别，不能只改 VERSION。
function generationTarget(cli, args) {
  const require = createRequire(pathToFileURL(cli));
  const { Command } = require('commander');
  let target;
  const parser = new Command().exitOverride().configureOutput({ writeOut() {}, writeErr() {} });
  parser.option('--no-color').version(VERSION);
  parser.command('init [path]').option('--tools <tools>').option('--language <language>')
    .option('--force').option('--profile <profile>').option('--no-animation')
    .option('--copilot-cloud').option('--no-copilot-cloud')
    .action((directory = '.', options) => { target = { directory: path.resolve(directory), profile: options.profile, tools: options.tools?.split(',') }; });
  parser.command('update [path]').option('--force')
    .action((directory = '.') => { target = { directory: path.resolve(directory) }; });
  try { parser.parse(args, { from: 'user' }); }
  catch (error) {
    if (!['commander.helpDisplayed', 'commander.version'].includes(error.code)) throw new Error(`生成参数预检失败：${error.message}`);
  }
  return target;
}

// 读取包装器已校验并写入的运行快照，不再次执行 CLI，不猜调用方就是生成目标。
function generationContext(target) {
  const snapshot = process.env.HARNESS_OPENSPEC_CONFIG;
  if (!snapshot) throw new Error('缺少包装器生成配置快照上下文');
  const stat = fs.lstatSync(snapshot);
  if (!stat.isFile() || stat.nlink !== 1) throw new Error('生成配置快照须为普通单链接文件');
  const config = JSON.parse(fs.readFileSync(snapshot, 'utf8'));
  selection(config);
  if (target.profile !== undefined) {
    if (!['custom', 'core'].includes(target.profile)) throw new Error(`不支持 Profile：${target.profile}`);
    config.profile = target.profile;
    if (target.profile === 'core') delete config.workflows;
  }
  return { selection: selection(config), tools: target.tools };
}

// 用当前 Node 启动已选 CLI，继承终端输入输出，保留交互及原始诊断。
// 包装器因后置适配不能直接 exec CLI，所以这里转发终止信号并回收监听器。
export async function runChild(cli, args) {
  const child = spawn(process.execPath, [cli, ...args], { stdio: 'inherit' });
  let interrupted;
  const handlers = new Map(['SIGINT', 'SIGTERM', 'SIGHUP'].map((signal) => [signal, () => {
    interrupted = signal;
    child.kill(signal);
  }]));
  for (const [signal, handler] of handlers) process.on(signal, handler);
  try {
    const result = await new Promise((resolve, reject) => {
      child.once('error', reject);
      child.once('exit', (code, signal) => resolve({ code, signal }));
    });
    return { ...result, signal: interrupted || result.signal };
  } finally {
    for (const [signal, handler] of handlers) process.off(signal, handler);
  }
}

// 主链路：只读检查，或 参数预检 → 固定来源预检 → CLI 生成 → 项目正文适配。
async function main() {
  const [mode, cli, ...args] = process.argv.slice(2);
  if (mode === '--check' && args.length === 0) {
    // 此模式的第二个参数实际为项目目录；省略时取 scripts/ 的父目录，而非当前 cwd。
    const result = adaptProject(cli || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'), null, { check: true });
    console.log(`Harness 文件合同检查通过：${result.workflows.join(', ')}；表面 ${result.surfaces.join(', ')}；${result.checked} 个受控正文。未执行 CLI 或写入配置；不证明宿主发现或模型遵从，仅覆盖 Codex / Claude 政策。`);
    return;
  }
  if (mode !== '--run' || !cli) throw new Error('用法：node adapt-openspec-workflows.mjs --check [project]；生成由 openspec.sh 接续');
  const target = generationTarget(cli, args);
  const context = target ? generationContext(target) : null;
  const bodies = target ? await sourceBodies(cli) : null;
  const result = await runChild(cli, args);
  if (result.signal) {
    // 先转发给子进程，再以同一信号结束监督进程；退出码写法仅作必要的后备。
    process.kill(process.pid, result.signal);
    process.exit(128 + constants.signals[result.signal]);
  }
  if (result.code !== 0) {
    // CLI 可能只生成了一部分文件；保留原退出码，不在失败状态下继续适配。
    process.exitCode = result.code;
    return;
  }
  if (!target) return;
  try {
    const adapted = adaptProject(target.directory, bodies, { context });
    console.log(`Harness ${REVISION} 适配完成：${adapted.workflows.join(', ')}；表面 ${adapted.surfaces.join(', ') || '无'}；检查 ${adapted.checked} 个受控正文，写入 ${adapted.written.length} 个文件。`);
    for (const difference of adapted.differences) console.log(`受控字段采用差异：${difference}`);
    if (!adapted.configured) console.log('目标尚未完成项目配置接入：缺少自身 Profile，独立 --check 将失败；未自动复制配置。');
    // 例如 init --tools none：CLI 本身可成功，但零入口不代表 Harness 接入成功。
    if (!adapted.checked) console.log('未发现支持的投递入口；尚不能据此判定 Harness 接入通过。');
  } catch (error) {
    throw new Error(`CLI 生成成功，Harness 适配失败：${error.message}`);
  }
}

// 直接运行才调用 main；测试导入本模块时不会误启动 CLI 或修改项目。
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(`Harness：${error.message}`); process.exitCode = 1; });
}
