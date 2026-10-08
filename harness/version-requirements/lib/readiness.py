"""Whole-Version observation of candidate readiness, never dispatch permission."""
from itertools import combinations
from copy import copy
import json

from .availability import assessment_scope, implementation_state
from .engineering_view import applicability, selected_filters
from .core import canonical_bytes
from .errors import CheckError, InputError
from .observations import diagnostic_state, generated_from, load, observe
from .rendering import fence

NOTICE = ('固定输入的就绪观察；ready 只是本次检查内的待选集合。仍须逐候选通过当前 G2、'
          '明确选择并发布 dispatch；不预占、不 Propose、不授权 Apply。并行组按 ID 稳定分组，'
          '不是优先级、工期或自动排程；跨组不保证无冲突。')


def subjects(delivery, cid):
    version, node = delivery.context.version['version'], delivery.candidates[cid]
    result = {'version:' + version, 'candidate:' + version + '/' + cid}
    for allocation in node['allocation']:
        result.add('requirement:' + version + '/' + allocation['requirement'])
        result.update('scope:' + version + '/' + allocation['requirement'] + '/' + ac for ac in allocation['acceptance'])
    if node['change_name']:
        result.add('change:' + node['change_name'])
    return sorted(result)


def pair_conflicts(delivery, left, right):
    """Reviewed exclusive resources plus unresolved semantic/order coupling.

    Do not assume a shared requirement or unresolved ordering can be parallel
    merely because no common resource label was entered.
    """
    a, b = delivery.candidates[left], delivery.candidates[right]
    reasons = []
    resources = sorted(set(a['shared_resources']) & set(b['shared_resources']))
    if resources:
        reasons.append({'state': 'unsatisfied', 'kind': 'shared-resource', 'resources': resources})
    ra = {row['requirement'] for row in a['allocation']}
    rb = {row['requirement'] for row in b['allocation']}
    if ra & rb:
        reasons.append({'state': 'unknown', 'kind': 'shared-requirement', 'requirements': sorted(ra & rb)})
    for eid, edge in delivery.edges.items():
        if edge['active'] and edge['entry']['strength'] == 'hard' and {edge['provider'], edge['consumer']} == {left, right}:
            reasons.append({'state': 'unknown', 'kind': 'integration-order', 'edge': eid,
                            'checkpoint': edge['entry']['checkpoint']})
    for uid in sorted(ra | rb):
        if uid not in delivery.requirements.records:
            continue
        info = delivery.requirements.records[uid]
        for relation in info['value']['relationships'] + info['value']['constraints']:
            target = relation.get('target', relation.get('requirement'))
            target_uid = target if isinstance(target, str) else target.get('requirement') if isinstance(target, dict) else None
            if target_uid in (rb if uid in ra else ra) and relation.get('type') != 'related-to':
                reasons.append({'state': 'unknown', 'kind': 'semantic-coupling', 'origin_ref': info['record_ref'],
                                'relation': relation['id']})
    return reasons


def later_due(snapshot, entry):
    if snapshot.get('gate') == 'G4':
        return entry['checkpoint'] != 'release' or snapshot['phase'] == 'release'
    checkpoints = ('integration',) if snapshot.get('phase') == 'pre-archive' else ('integration', 'merge')
    return snapshot.get('gate') == 'G3' and entry['kind'] == 'integration' and entry['checkpoint'] in checkpoints


def condition_executions(context, delivery, checks):
    """Read explicit E identities once; never run tests or infer another head."""
    from .completion import candidate_execution, candidate_inputs, retained_record
    from .delivery_trace import coverage_identity, current_ref
    from .verification import check_execution

    snapshot, candidate = context.snapshot, None
    if snapshot['gate'] == 'G4':
        def select():
            if not snapshot.get('release_candidate_ref'):
                raise InputError('report.execution-context', 'due Version conditions require the fixed release candidate')
            value = retained_record(context, snapshot['release_candidate_ref'], 'release_candidate', 'candidate')
            if snapshot['subject'] != 'release-candidate:' + value['id']:
                raise InputError('report.candidate-subject', 'snapshot must select this exact release candidate')
            candidate_inputs(context, value)
            return value
        candidate = observe(checks, 'dependency-candidate', select)
        if candidate is None:
            return None, {}
    executions, errors = {}, {}
    seen = set()
    for expected in snapshot.get('verification_inputs', []):
        key = canonical_bytes(expected['verification_ref'])
        try:
            if key in seen:
                raise InputError('report.duplicate-execution', 'one E must have exactly one selected expectation')
            seen.add(key)
            if candidate is not None:
                checked = candidate_execution(delivery.context, candidate, expected)
            else:
                if not context.store.ancestor(expected['tested_revision'], snapshot['head_revision']):
                    raise CheckError('report.stale-execution', 'combination evidence belongs to another engineering history')
                checked = check_execution(delivery.context, expected['verification_ref'],
                    tested_revision=expected['tested_revision'], identities=expected['identities'], engineering_review=delivery.review)
                for reference in checked['record']['input_refs']:
                    current_ref(context.store, reference, snapshot['head_revision'])
            for coverage in checked['record']['coverage']:
                coverage_identity(delivery, coverage)
            executions[key] = checked
        except CheckError as error:
            executions.pop(key, None)
            errors[key] = error
            checks.append({'check': 'dependency-execution', 'state': diagnostic_state(error),
                           'verification_ref': expected['verification_ref'], 'diagnostic': error.diagnostic()})
    return executions, errors


def later_condition(delivery, snapshot, eid, assessments, executions, errors):
    """Reuse the complete provider/consumer condition reader for a due edge.

    For G3 only the explicit integration/merge checkpoints are selected by the
    caller. G3 observations establish current combination facts, not accepted
    Trace coverage, final Review, merge or any other Gate permission.
    """
    from .completion import version_conditions
    edge = delivery.edges[eid]
    assessment = assessments.get(eid)
    if assessment is None or assessment['conclusion'] == 'unknown':
        return {'state': 'unknown', 'reason': 'due condition has no known provider assessment'}
    if assessment['target_revision'] != snapshot['target_revision']:
        raise CheckError('availability.stale-target', 'due condition assessment belongs to an old target', refs=[eid])
    if assessment['conclusion'] == 'unavailable':
        return {'state': 'unsatisfied', 'assessment_ref': assessment['assessment_ref']}
    if executions is None:
        return {'state': 'unknown', 'reason': 'fixed candidate identity could not be established'}
    refs = [ref for row in delivery.plan['obligations'] if eid in row.get('edge_refs', []) for ref in row['evidence_refs']]
    for reference in refs:
        key = canonical_bytes(reference)
        if key in errors:
            raise errors[key]
        if key not in executions:
            raise InputError('report.missing-execution', 'due condition needs its explicitly selected current combination E', refs=[eid, reference])
    selected = copy(delivery)
    selected.edges = {eid: edge}
    phase = snapshot['phase'] if snapshot['gate'] == 'G4' else 'completion'
    state = version_conditions(selected, {**snapshot, 'phase': phase}, {}, executions)[0]
    return {**state, 'assessment_ref': assessment['assessment_ref'], 'verification_refs': refs}


def project(context, requirements, delivery, questions, control, checks, filters):
    snapshot, target = context.snapshot, context.snapshot['target_revision']
    structure_ok = any(row['check'] == 'delivery-structure' and row['state'] == 'satisfied' for row in checks)
    assessments = observe(checks, 'availability-assessments', lambda: assessment_scope(delivery)) if structure_ok else None
    executions, execution_errors = {}, {}
    if structure_ok and assessments is not None and any(
            edge['active'] and edge['entry']['strength'] != 'soft' and later_due(snapshot, edge['entry'])
            for edge in delivery.edges.values()):
        executions, execution_errors = condition_executions(context, delivery, checks)
    edges = []
    for cid, node in sorted(delivery.active.items()):
        for entry in node['predecessor_edges']:
            eid = entry['id']
            row = {'id': eid, 'consumer': cid, 'provider': entry.get('candidate', entry.get('endpoint')),
                   'source': entry, 'map_ref': delivery.map_ref, 'kind': entry['kind'],
                   'strength': entry['strength'], 'checkpoint': entry['checkpoint'],
                   'applicability': applicability(delivery.store, entry, eid)}
            row['state'] = 'unknown'
            if structure_ok and assessments is not None:
                try:
                    edge = delivery.edges[eid]
                    state = (later_condition(delivery, snapshot, eid, assessments, executions, execution_errors)
                             if edge['active'] and entry['strength'] != 'soft' and later_due(snapshot, entry)
                             else implementation_state(delivery, eid, assessments, target))
                    row.update({key: value for key, value in state.items() if key != 'provider'})
                    row['provider_contribution'] = edge['provider_ref']
                except CheckError as error:
                    row.update(state=diagnostic_state(error), diagnostic=error.diagnostic())
            edges.append(row)
    global_blockers = [row for row in checks if row['state'] != 'satisfied']
    if context.baseline is None:
        global_blockers.append({'state': 'unknown', 'check': 'effective-baseline', 'reason': 'draft has no effective BL'})
    if not any(row['check'] == 'current-engineering' and row['state'] == 'satisfied' for row in checks):
        global_blockers.append({'state': 'unknown', 'check': 'current-engineering-selection',
                                'reason': 'select explicit downstream map/plan/Review inputs before current readiness'})
    if control is None:
        global_blockers.append({'state': 'unknown', 'check': 'current-control', 'reason': 'no qualified fixed control'})
    engineering = delivery.review['engineering']
    limits = (engineering['wip_limit'], engineering['planning_limit'])
    candidates = []
    for cid, node in sorted(delivery.candidates.items()):
        blockers = list(global_blockers)
        state = node['disposition']
        key = (snapshot['delivery_line'], snapshot['version'], cid)
        own_edges = [row for row in edges if row['consumer'] == cid]
        dependency_blockers = [row for row in own_edges if row['state'] in ('unknown', 'unsatisfied', 'stale')]
        blockers += [{'state': row['state'], 'check': 'dependency', 'edge': row['id'],
                      'diagnostic': row.get('diagnostic'), 'assessment_ref': row.get('assessment_ref')} for row in dependency_blockers]
        for qid, impact in sorted(questions.impacts.items()):
            if cid in impact['blocking_for'] or 'baseline' in impact['blocking_for']:
                observe(blockers, 'question:' + qid, lambda qid=qid: questions.require_resolved(qid))
        capacity = None
        if node['disposition'] == 'planned' and control is not None:
            for entry in ('propose', 'apply'):
                observe(blockers, 'control:' + entry, lambda entry=entry: control.holds.require_clear(
                    line=key[0], entry=entry, subjects=subjects(delivery, cid)))
            capacity = observe(blockers, 'capacity', lambda: control.capacity(key, node, limits))
            if key in control.completed:
                state = 'integrated-history'
            elif key in control.cancelled:
                state = 'cancelled-history'
            elif key in control.reservations:
                state = 'reserved'
            elif node['change_name'] is not None or context.store.git('log', '-1', '--format=%H',
                    snapshot['metadata_revision'], '--', delivery.context.vr + '/trace/changes/' + cid + '.yaml').strip():
                state = 'existing-change'
            else:
                state = 'ready' if not any(row['state'] != 'satisfied' for row in blockers) else 'blocked'
        elif state == 'planned':
            state = 'blocked'
        blockers = [row for row in blockers if row['state'] != 'satisfied']
        candidates.append({'id': cid, 'state': state, 'dependency_ready': structure_ok and not dependency_blockers,
                           'blockers': blockers, 'capacity': capacity, 'source': node, 'map_ref': delivery.map_ref,
                           'subjects': subjects(delivery, cid), 'gate_required': 'G2'})
    observed_ready = [row['id'] for row in candidates if row['state'] == 'ready']
    historical = snapshot['evaluation_mode'] == 'historical'
    ready = [] if historical else observed_ready
    conflicts = [{'candidates': [a, b], 'reasons': reasons} for a, b in combinations(observed_ready, 2)
                 if (reasons := pair_conflicts(delivery, a, b))]
    incompatible = {frozenset(row['candidates']) for row in conflicts}
    occupied = sum(row['inputs']['payload']['mode'] == 'execution' for key, row in control.reservations.items()
                   if key[0] == snapshot['delivery_line']) if control is not None else 0
    free = max(0, limits[0] - occupied)
    groups = []
    for cid in ready:
        for group in groups:
            if len(group) < free and all(frozenset((cid, other)) not in incompatible for other in group):
                group.append(cid)
                break
        else:
            if free:
                groups.append([cid])
    # Filtering affects presentation only. Ready/group/capacity results always
    # derive from all candidates, including other Versions on this line.
    acs = set(filters.get('acceptance', []))
    visible = {cid for cid, node in delivery.candidates.items() if not acs or any(
        row['requirement'] + '/' + ac in acs for row in node['allocation'] for ac in row['acceptance'])}
    shown_edges = [row for row in edges if (row['consumer'] in visible or row['provider'] in visible)
                   and all(not filters.get(key) or row[key] in filters[key] for key in ('kind', 'strength', 'checkpoint'))]
    return {'kind': 'candidate-readiness-observation', 'notice': NOTICE, 'gate_evaluated': False,
            'current': not historical, 'version': snapshot['version'], 'delivery_line': snapshot['delivery_line'],
            'checks': checks, 'candidates': candidates, 'visible_candidates': sorted(visible), 'edges': edges,
            'visible_edges': [row['id'] for row in shown_edges], 'ready': ready, 'observed_ready': observed_ready,
            'parallel_candidates': [group for group in groups if len(group) > 1], 'small_batches': groups,
            'pair_conflicts': conflicts, 'line_capacity': {'execution_limit': limits[0], 'occupied': occupied, 'free': free},
            'permissions': {'dispatch': False, 'propose': False, 'apply': False}}


def prepare(context, *, filters=None):
    requirements, delivery, questions, control, checks = load(context)
    filters = selected_filters(requirements, filters)
    model = project(context, requirements, delivery, questions, control, checks, filters)
    model['generated_from'] = generated_from(context, filters=filters)
    lines = ['# 当前候选就绪观察', '', NOTICE, '', '输入摘要：`' + model['generated_from']['sha256'] + '`。', '',
             '历史模式不提供当前待选或批量释放建议。' if not model['current'] else '当前待选：' + ', '.join(model['ready']), '',
             '## 候选与阻断', '']
    for row in model['candidates']:
        if row['id'] in model['visible_candidates']:
            lines += ['### ' + row['id'], '', fence(json.dumps(row, ensure_ascii=False, indent=2), 'json'), '']
    lines += ['## 并行与小批建议', '', fence(json.dumps({key: model[key] for key in
              ('parallel_candidates', 'small_batches', 'pair_conflicts', 'line_capacity')}, ensure_ascii=False, indent=2), 'json'), '',
              '全量边、检查结果和原始引用见 `readiness.json`；筛选不缩小检查范围。', '']
    return model, {'readiness.json': json.dumps(model, ensure_ascii=False, indent=2) + '\n',
                   'readiness.md': '\n'.join(lines)}
