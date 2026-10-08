"""Four derived panels from fixed source, allocation, execution and control facts.

No ratios are written back. All AC stages use the complete selected scope;
multiple contributions and multiple due verification obligations are conjunctive.
Final execution/acceptance counts require an explicit release candidate snapshot.
"""
from collections import defaultdict
import json

from .completion import candidate_execution, candidate_inputs, check_version, retained_record
from .core import canonical_bytes, digest, parse_yaml
from .delivery_trace import coverage_identity, current_ref
from .errors import CheckError, InputError
from .integrated_receipt import read_integrated_receipt
from .models import validate
from .observations import diagnostic_state, generated_from, load, observe
from .planning_trace import check_planning_trace
from .readiness import project as readiness
from .rendering import fence

NOTICE = ('固定事实的派生面板；不维护状态台账，不改 R/Tasks/批准，不授予任何动作。'
          'mapped / planned / implemented / executed / passed / accepted 分开计算；'
          '比例不能代替 Gate、语义审查或产品验收。未选定整版候选时，最终验证与验收为 unknown。')
STAGES = {
    'mapped': '当前 scope AC 有合法的完整交付分配；仅证明路径存在。',
    'planned': '全部贡献已有实际 Trace/Spec/Task 关联，或已有/外部路径的契约与验证责任；不等于准入。',
    'implemented': '全部贡献的实际实现/交付引用仍适用于所选工程输入；不等于测试通过。',
    'executed': '当前整版候选的全部到期 AC 验证责任均有实际执行；失败算执行，跳过或未找到不算。',
    'passed': '上述当前执行均通过且覆盖全部必需贡献；不等于具名验收。',
    'accepted': '当前整版候选的完整 G4 验收事实可复算；历史结果不冒充当前验收。',
}


def fraction(rows, state='satisfied'):
    denominator = sorted(row['id'] for row in rows)
    numerator = sorted(row['id'] for row in rows if row['state'] == state)
    return {'numerator': len(numerator), 'denominator': len(denominator), 'numerator_ids': numerator,
            'denominator_ids': denominator, 'remaining_ids': sorted(set(denominator) - set(numerator)),
            'ratio': len(numerator) / len(denominator) if denominator else None}


def source_panel(requirements, checks=()):
    # These failures concern the interpretation graph as a whole. Individual
    # reverse mappings cannot prove processing is complete while it is cyclic
    # or the source relationship is still undecided.
    unresolved_graph = [check for check in checks if check.get('diagnostic', {}).get('rule_id') in
                        ('source.duplicate-cycle', 'source.supersession-cycle', 'source.relation-unknown')]
    rows = []
    for uid, unit in sorted(requirements.sources.units.items()):
        row = {'id': uid, 'disposition': unit['disposition'], 'reading': unit['reading'],
               'units_ref': requirements.current_ref(requirements.context.vr + '/source/units.yaml'),
               'targets': requirements.source_targets(uid), 'state': 'pending'}
        try:
            disposition, targets = unit['disposition'], row['targets']
            if disposition != 'duplicate' and 'duplicate_of' in unit:
                raise CheckError('source.duplicate-state', 'duplicate_of belongs only to duplicate sources', refs=[uid])
            if disposition != 'context' and unit.get('context_requirements'):
                raise CheckError('source.context-role', 'context associations require contextual disposition', refs=[uid])
            if disposition != 'superseded' and any(key in unit for key in ('previous_ref', 'successors')):
                raise CheckError('source.supersession-state', 'replacement fields require superseded disposition', refs=[uid])
            if 'supersedes_unit' in unit:
                old = requirements.sources.units.get(unit['supersedes_unit'])
                if old is None or old['disposition'] != 'superseded' or uid not in old.get('successors', []):
                    raise CheckError('source.supersession-successor', 'replacement direction disagrees with historical unit', refs=[uid])
            if disposition in ('mapped', 'duplicate'):
                if not targets or sorted(unit['targets'], key=canonical_bytes) != targets:
                    raise CheckError('source.mapping', 'source targets differ from authoritative R origins/scope confirmations', refs=[uid])
                duplicate = unit.get('duplicate_of')
                if duplicate and (duplicate == uid or duplicate not in requirements.sources.units or
                        {r['requirement'] for r in requirements.source_targets(duplicate)} != {r['requirement'] for r in targets}):
                    raise CheckError('source.duplicate-target', 'duplicate does not select the same obligations', refs=[uid])
            elif disposition == 'context':
                if targets or unit['targets']:
                    raise CheckError('source.context-obligation', 'context cannot hide mapped obligations', refs=[uid])
                for reference in unit.get('context_requirements', []):
                    requirements.target(reference)
            elif disposition == 'excluded':
                excluded = [item for item in requirements.scope['excluded'] if item.get('source_unit') == uid]
                if len(excluded) != 1 or targets or unit['targets'] or not unit.get('scope_decision'):
                    raise CheckError('source.exclusion', 'excluded source needs its exact scope decision', refs=[uid])
                question = requirements.questions.require_resolved(excluded[0]['decision_ref'], scope_decision=True)
                if (requirements.questions.resolve(unit['scope_decision'])['id'] != question['id'] or
                        uid not in requirements.questions.impact(question['id'])['source_refs']):
                    raise CheckError('source.exclusion', 'scope decision does not cover this source', refs=[uid])
            elif disposition == 'superseded':
                requirements.check_supersession(unit)
            if disposition != 'pending':
                row['state'] = 'satisfied'
                if unresolved_graph:
                    row.update(state='unknown', graph_diagnostics=unresolved_graph)
        except CheckError as error:
            row.update(state=diagnostic_state(error), diagnostic=error.diagnostic())
        rows.append(row)
    return {'meaning': '全部所选 Version 来源单元的处置/反向映射；全量 S2/Review 诊断另外保留。',
            **fraction(rows), 'rows': rows}


def contribution_progress(context, delivery, control, checks, candidate):
    """Keep mechanical planning/implementation evidence distinct from E results."""
    store, snap = context.store, context.snapshot
    progress = {key: {'planned': set(), 'implemented': set(), 'refs': [], 'diagnostics': []}
                for key in delivery.allocations}
    for cid, node in delivery.active.items():
        path = context.vr + '/trace/changes/' + cid + '.yaml'
        if path not in store.tree(snap['metadata_revision']):
            continue
        reference = {'commit': snap['metadata_revision'], 'path': path,
                     'sha256': digest(store.read(snap['metadata_revision'], path))}
        keys = [key for key, allocation in delivery.allocations.items() if allocation['node'] == cid]
        try:
            trace = validate('planning_trace', parse_yaml(store.ref(reference)))
            from .control import event
            payload = event(store, trace['dispatch_ref'])['payload']
            selected = {**snap, 'dispatch_ref': trace['dispatch_ref']}
            planned = check_planning_trace(delivery, reference, selected, payload,
                                           require_review=False, allow_task_progress=True)
            content = trace.get('delivery')
            actual_tasks = planned['observation']['tasks']
            implementations = {row['task_id']: row for row in content['implementations']} if content else {}
            for link in planned['links']:
                key = link['contribution']
                if key not in progress:
                    continue
                row = progress[key]
                row['planned'].update(link['acceptance'])
                row['refs'].append(reference)
                if not link['tasks'] or not all(actual_tasks[tid]['done'] and tid in implementations for tid in link['tasks']):
                    continue
                planning_files = {path for paths in planned['observation']['artifacts'].values() for path in paths}
                for tid in link['tasks']:
                    for ref in implementations[tid]['file_refs']:
                        if ref['path'] in planning_files or ref['path'].startswith('requirements/'):
                            raise CheckError('report.implementation-role', 'planning/upstream/E references alone do not prove implemented product bytes', refs=[ref])
                        current_ref(store, ref, snap['head_revision'])
                row['implemented'].update(link['acceptance'])
        except CheckError as error:
            for key in keys:
                progress[key]['diagnostics'].append(error.diagnostic())
    for key, allocation in delivery.allocations.items():
        if allocation['node'] not in delivery.endpoints:
            continue
        endpoint = delivery.endpoints[allocation['node']]
        covered = {ac for row in delivery.plan['obligations'] if key in row.get('contributions', [])
                   for ac in row.get('acceptance', [])}
        # An external future contract can be planned without claiming it is
        # present or implemented on the current target.
        store.ref(endpoint['contract_ref'])
        progress[key]['planned'].update(covered & allocation['acceptance'])
        progress[key]['refs'].append(endpoint['contract_ref'])
    receipts = list(candidate.get('delivery_receipts', [])) if candidate else []
    if control:
        for key, completed in control.completed.items():
            if key[:2] != (snap['delivery_line'], snap['version']):
                continue
            receipt = completed['receipt']
            receipts.append({'context_ref': receipt['context_ref'], 'result_ref': receipt['result_ref'],
                             'contributions': list(receipt['evidence']['integrated_acceptance'])})
    seen = set()
    for selected in receipts:
        identity = canonical_bytes(selected)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            receipt = read_integrated_receipt(context, selected['context_ref'], selected['result_ref'], allow_alternatives=True)
            origin, proof = receipt['snapshot'], receipt['evidence']
            if (not store.ancestor(origin['target_revision'], snap['target_revision']) or
                    not store.ancestor(origin['control_revision'], snap['control_revision'])):
                raise CheckError('report.stale-delivery', 'delivery belongs to another target/control history')
            # A historical integration proves implementation only while its
            # actual tested engineering inputs remain on this target.
            for expected in origin['verification_inputs']:
                record = validate('verification_record', parse_yaml(store.ref(expected['verification_ref'])))
                for ref in record['input_refs']:
                    current_ref(store, ref, snap['target_revision'])
                for coverage in record['coverage']:
                    if coverage['contribution'] in selected['contributions']:
                        coverage_identity(delivery, coverage)
            accepted = proof.get('integrated_acceptance')
            if accepted is None:
                accepted = defaultdict(set)
                for row in proof['delivery']['acceptance']:
                    for key in row['contributions']:
                        accepted[key].add(row['acceptance'])
            for key in selected['contributions']:
                if key in progress:
                    progress[key]['planned'].update(accepted.get(key, []))
                    progress[key]['implemented'].update(accepted.get(key, []))
                    progress[key]['refs'].extend([selected['context_ref'], selected['result_ref']])
        except CheckError as error:
            state = 'stale' if error.rule in ('ref.digest', 'ref.missing', 'delivery-trace.file-mode') else diagnostic_state(error)
            checks.append({'check': 'delivery-receipt', 'state': state, 'diagnostic': error.diagnostic()})
    return progress


def verification_panel(context, delivery, candidate, checks):
    expectations = {canonical_bytes(row['verification_ref']): row for row in context.snapshot.get('verification_inputs', [])}
    if len(expectations) != len(context.snapshot.get('verification_inputs', [])):
        raise InputError('report.duplicate-execution', 'one E must have exactly one selected expectation')
    records, rows = {}, []
    due = [row for row in delivery.plan['obligations'] if row['checkpoint'] != 'release' or
           context.snapshot['phase'] == 'release' or row.get('final')]
    selection_matches = {canonical_bytes(ref) for row in due for ref in row['evidence_refs']} == expectations.keys()
    if candidate is not None and not selection_matches:
        checks.append({'check': 'execution-selection', 'state': 'unknown',
                       'reason': 'selected E expectations must exactly match all due plan evidence'})
    for obligation in due:
        for ref in obligation['evidence_refs']:
            key = canonical_bytes(ref)
            if key in records:
                continue
            row = {'id': ref['path'], 'verification_ref': ref, 'state': 'unknown'}
            try:
                if candidate is None or key not in expectations:
                    raise InputError('report.execution-context', 'select the fixed release candidate and independent E expectation')
                checked = candidate_execution(delivery.context, candidate, expectations[key], require_pass=False)
                for coverage in checked['record']['coverage']:
                    coverage_identity(delivery, coverage)
                row.update(state='satisfied' if checked['record']['result'] == 'passed' else 'unsatisfied',
                           result=checked['record']['result'], cases=checked['cases'], counts=checked['counts'])
                records[key] = checked
            except CheckError as error:
                row.update(state=diagnostic_state(error), diagnostic=error.diagnostic())
                records[key] = None
            rows.append(row)
    outcomes = {}
    for pair, contributions in delivery.coverage.items():
        uid, ac = pair
        needed = [row for row in due if row.get('requirement') == uid and ac in row.get('acceptance', [])]
        stage_sets = {stage: defaultdict(set) for stage in ('executed', 'passed')}
        obligations = []
        for obligation in needed:
            local = {stage: set() for stage in stage_sets}
            observed = {stage: defaultdict(list) for stage in stage_sets}
            required = contributions & set(obligation['contributions'])
            for ref in obligation['evidence_refs']:
                checked = records.get(canonical_bytes(ref))
                if checked is None:
                    continue
                for coverage in checked['record']['coverage']:
                    key = coverage['contribution']
                    if key not in required or coverage.get('requirement') != uid or ac not in coverage.get('acceptance', []):
                        continue
                    results = [checked['cases'][case] for case in coverage['case_ids']]
                    observed['executed'][key].append(bool(results) and all(value in ('passed', 'failed') for value in results))
                    observed['passed'][key].append(bool(results) and all(value == 'passed' for value in results)
                                                   and checked['record']['result'] == 'passed')
            for stage in stage_sets:
                local[stage] = {key for key, values in observed[stage].items() if values and all(values)}
            obligations.append({'id': obligation['id'], 'required_contributions': sorted(required),
                                **{stage: sorted(local[stage]) for stage in stage_sets}})
            for stage in stage_sets:
                selected = [records.get(canonical_bytes(ref)) for ref in obligation['evidence_refs']]
                if (selected and all(item is not None for item in selected) and
                        (stage == 'executed' or all(item['record']['result'] == 'passed' for item in selected))):
                    stage_sets[stage][obligation['id']].update(local[stage])
        complete_final = set().union(*(set(row['contributions']) for row in needed if row.get('final'))) if needed else set()
        outcomes[pair] = {stage: selection_matches and bool(contributions) and complete_final >= contributions and bool(needed) and all(
            (contributions & set(row['contributions'])) <= stage_sets[stage][row['id']] for row in needed) for stage in stage_sets}
        outcomes[pair]['obligations'] = obligations
    return outcomes, rows


def prepare(context, *, filters=None):
    if filters:
        raise InputError('report.filter', 'metrics always retain the entire scope denominator')
    r, delivery, questions, control, checks = load(context)
    # A prior per-unit error must not hide another graph-wide source failure.
    observe(checks, 'source-relationships', r.check_source_relations)
    observe(checks, 'source-interpretation-graph', r.check_source_cycles)
    sources = source_panel(r, checks)
    # Rebuild all typed allocations even if the complete map has missing ACs.
    # Partial coverage is observable; a node/identity error invalidates mapping.
    delivery.allocations.clear(); delivery.capabilities.clear(); delivery.coverage.clear()
    allocation_checks = []
    observe(allocation_checks, 'allocation-identities', delivery._nodes)
    checks.extend(allocation_checks)
    mapping_valid = all(row['state'] == 'satisfied' for row in allocation_checks)
    candidate = None
    if context.snapshot.get('release_candidate_ref'):
        candidate = observe(checks, 'candidate-record', lambda: retained_record(
            context, context.snapshot['release_candidate_ref'], 'release_candidate', 'candidate'))
        if candidate:
            if context.snapshot['subject'] != 'release-candidate:' + candidate['id']:
                raise InputError('report.candidate-subject', 'snapshot must select this exact release candidate')
            before = len(checks)
            observe(checks, 'candidate-inputs', lambda: candidate_inputs(context, candidate))
            if checks[before]['state'] != 'satisfied':
                candidate = None
    progress = contribution_progress(context, delivery, control, checks, candidate) if mapping_valid else {}
    verification, executions = verification_panel(context, delivery, candidate, checks) if mapping_valid else ({}, [])
    qualification = None
    if candidate is not None:
        qualification = observe(checks, 'candidate-acceptance', lambda: check_version(context.store, context.snapshot))
    accepted = qualification is not None and context.snapshot['evaluation_mode'] == 'current'
    ac_rows = []
    for uid, info in sorted(r.records.items()):
        for ac in sorted(info['acs']):
            contributions = delivery.coverage[(uid, ac)] if mapping_valid else set()
            states = {stage: 'pending' for stage in STAGES}
            states['mapped'] = 'satisfied' if contributions else 'pending' if mapping_valid else 'unknown'
            for stage in ('planned', 'implemented'):
                states[stage] = 'satisfied' if contributions and all(ac in progress[key][stage] for key in contributions) else 'pending'
            for stage in ('executed', 'passed'):
                states[stage] = ('unknown' if candidate is None else 'satisfied' if verification.get((uid, ac), {}).get(stage) else 'pending')
            states['accepted'] = 'satisfied' if accepted else 'unknown' if candidate is None or context.snapshot['evaluation_mode'] == 'historical' else 'pending'
            ac_rows.append({'id': uid + '/' + ac, 'record_ref': info['record_ref'], 'configuration_ref': info['configuration_ref'],
                            'contributions': sorted(contributions), 'stages': states,
                            'verification_obligations': verification.get((uid, ac), {}).get('obligations', [])})
    stage_counts = {stage: fraction([{'id': row['id'], 'state': row['stages'][stage]} for row in ac_rows]) for stage in STAGES}
    current = readiness(context, r, delivery, questions, control, checks, {})
    blockers = []
    for row in current['candidates']:
        for index, blocker in enumerate(row['blockers']):
            blockers.append({'id': row['id'] + '/blocker-' + str(index + 1), 'candidate': row['id'], **blocker})
    for qid, impact in sorted(questions.impacts.items()):
        value = questions.resolve(qid)
        if impact['blocking_for'] and value['status'] != 'resolved':
            blockers.append({'id': qid, 'state': 'unsatisfied', 'kind': 'question', 'status': value['status'],
                             'blocking_for': sorted(impact['blocking_for']), 'path': questions.paths[qid]})
    if control:
        for value in control.holds.holds.values():
            if value['event']['target_line'] == context.snapshot['delivery_line'] and value['remaining']:
                blockers.append({'id': value['event_ref']['event_id'], 'state': 'unsatisfied', 'kind': 'hold',
                                 'hold_ref': value['event_ref'], 'remaining': sorted(value['remaining'])})
        for row in control.changes.projections(version=context.snapshot['version'], line=context.snapshot['delivery_line']):
            if row['status'] not in ('rejected', 'withdrawn', 'verified'):
                blockers.append({'id': row['id'], 'state': 'unsatisfied', 'kind': 'requirement-change', 'projection': row})
    issues = [*checks, *executions]
    issues += [{'id': key, 'state': 'stale' if any('stale' in item['rule_id'] for item in value['diagnostics']) else 'unknown',
                'diagnostics': value['diagnostics']} for key, value in progress.items() if value['diagnostics']]
    stale = [row for row in issues if row['state'] == 'stale']
    model = {'kind': 'version-metrics-observation', 'notice': NOTICE, 'gate_evaluated': False,
             'current': context.snapshot['evaluation_mode'] == 'current', 'stage_meanings': STAGES,
             'sources': sources, 'allocation': stage_counts['mapped'], 'lifecycle': stage_counts, 'acceptance': ac_rows,
             'verification': {'candidate_ref': context.snapshot.get('release_candidate_ref'),
                              'executed': stage_counts['executed'], 'passed': stage_counts['passed'],
                              'accepted': stage_counts['accepted'], 'evidence': executions},
             'open_items': {'blocker_count': len(blockers), 'blockers': blockers, 'stale_count': len(stale),
                            'stale_evidence': stale, 'checks': checks,
                            'evidence_issues': [row for row in issues if row['state'] != 'satisfied']},
             'contribution_progress': {key: {**value, 'planned': sorted(value['planned']), 'implemented': sorted(value['implemented'])}
                                       for key, value in progress.items()}}
    model['generated_from'] = generated_from(context)
    lines = ['# 版本持续指标', '', NOTICE, '', '输入摘要：`' + model['generated_from']['sha256'] + '`。', '',
             '## 来源处理', '', fence(json.dumps(model['sources'], ensure_ascii=False, indent=2), 'json'), '',
             '## AC 交付分配', '', fence(json.dumps(model['allocation'], ensure_ascii=False, indent=2), 'json'), '',
             '## 当前候选的有效验证', '']
    for stage, meaning in STAGES.items():
        value = stage_counts[stage]
        lines += ['- `' + stage + '`：' + str(value['numerator']) + '/' + str(value['denominator']) + '。' + meaning]
    lines += ['', '逐 AC / 全贡献 / 全部到期验证责任及固定 E 见 `metrics.json`，unknown 不计入分子。', '',
              '## 开放阻断与过时证据', '', fence(json.dumps(model['open_items'], ensure_ascii=False, indent=2), 'json'), '']
    return model, {'metrics.json': json.dumps(model, ensure_ascii=False, indent=2) + '\n', 'metrics.md': '\n'.join(lines)}
