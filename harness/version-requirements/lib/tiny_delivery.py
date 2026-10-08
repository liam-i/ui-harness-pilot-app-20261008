"""Task/PR delivery through the existing BL, Review, E and integration readers.

The association stores references, not another task list or completion state.
Actual Tiny selection and semantic scope remain reviewed against project policy.
"""
from dataclasses import replace

from .availability import implementation_dependencies
from .context import resolve
from .control_delivery import read_delivery_control
from .core import canonical_bytes, digest, parse_json
from .delivery import DeliveryIndex
from .delivery_trace import coverage_identity, current_ref, tested_content, tiny_review_key
from .dispatch import baseline_context, current_engineering, preserved_inputs, retain_inputs
from .errors import CheckError
from .feasibility import check_feasibility
from .final_checks import read_final_checks
from .models import unique, validate
from .prearchive import due_integration
from .requirements import RequirementIndex
from .review_scope import References, ReviewScope
from .reviews import check_review, decision
from .verification import check_execution
from .worktree import capture
from .ui_integration import check as check_ui, execution_inputs, local_refs, CHECKS as UI_CHECKS

REVIEW_CHECKS = ('tiny-path', 'task-scope', 'diff-and-history', 'project-checks',
                 'verification-coverage', 'integration-conditions', 'merge-scope')


def current_inputs(store, snapshot, *, integrated=False):
    context = resolve(store, snapshot)
    missing = [key for key in ('tiny_ref', 'engineering_inputs') if key not in snapshot]
    if missing or not snapshot['control_revision']:
        raise CheckError('tiny.context', 'task/PR delivery needs its fixed association, current engineering inputs and control', refs=missing)
    head, target = snapshot['head_revision'], snapshot['target_revision']
    if not store.ancestor(target, head):
        raise CheckError('tiny.target-history', 'checked delivery must include the current target')
    baseline, checked = baseline_context(store, snapshot)
    inputs = snapshot['engineering_inputs']
    if inputs['engineering_review_ref']['path'] != context.vr + '/reviews/engineering.yaml':
        raise CheckError('tiny.engineering-review', 'reuse the existing Version engineering Review')
    current = current_engineering(baseline, snapshot, inputs, executing=not integrated)
    for revision in {head, target, snapshot['metadata_revision'], current.content_commit}:
        preserved_inputs(baseline, revision, checked)
    requirements = RequirementIndex(baseline)
    requirements.check_content()
    delivery = DeliveryIndex(requirements, engineering_context=current, map_ref=inputs['map_ref'],
                             verification_plan_ref=inputs['verification_plan_ref'])
    if delivery.map['baseline'] != baseline.baseline['id']:
        raise CheckError('tiny.baseline', 'current map must retain the selected effective baseline')
    delivery.check()
    check_feasibility(delivery)
    scope = ReviewScope(requirements, delivery)
    engineering = scope.check_engineering()
    scope.engineering_questions.check_baseline(requirements.records)
    control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
    ref = snapshot['tiny_ref']
    if not ref['path'].startswith(context.vr + '/trace/evidence/'):
        raise CheckError('tiny.association-path', 'save task/PR associations in the existing Version evidence namespace')
    association = validate('tiny_association', parse_json(current_ref(store, ref, head)))
    for key in ('subject', 'version', 'delivery_line', 'baseline_ref'):
        if association[key] != snapshot[key]:
            raise CheckError('tiny.identity', 'association differs from the actual task/PR, baseline or line', refs=[key])
    if not any(ref['path'] == 'AGENTS.md' for ref in association['policy_refs']):
        raise CheckError('tiny.policy', 'Tiny selection must bind the actual project AGENTS.md policy')
    for reference in [association['task_ref'], *association['policy_refs'], *association['spec_refs']]:
        current_ref(store, reference, head)
    if any(not ref['path'].startswith('openspec/specs/') for ref in association['spec_refs']):
        raise CheckError('tiny.spec', 'Tiny retains applicable current main Specs, not a new Delta or old task body')
    selected = set()
    for uid, row in unique(association['requirements'], 'requirement', location='Tiny associations').items():
        info = requirements.records.get(uid)
        if info is None or not set(row['acceptance']) <= info['acs'].keys():
            raise CheckError('tiny.scope', 'task/PR association selects absent scoped R/AC', refs=[uid])
        selected.update((uid, ac) for ac in row['acceptance'])
    if selected and not association['spec_refs']:
        raise CheckError('tiny.spec', 'business behavior repairs must retain their actual main Spec contract')
    contributions = {ref for pair in selected for ref in delivery.coverage[pair]}
    candidates = {delivery.allocations[ref]['node'] for ref in contributions
                  if delivery.allocations[ref]['node'] in delivery.candidates}
    for cid in candidates:
        key = (snapshot['delivery_line'], snapshot['version'], cid)
        if key not in control.completed:
            raise CheckError('tiny.unfinished-standard', 'an unfinished candidate obligation must use its actual Standard delivery', refs=[cid])
    subjects = {snapshot['subject'], 'version:' + snapshot['version']}
    for uid, ac in selected:
        subjects.update({'requirement:' + snapshot['version'] + '/' + uid,
                         'scope:' + snapshot['version'] + '/' + uid + '/' + ac})
    for cid in candidates:
        subjects.add('candidate:' + snapshot['version'] + '/' + cid)
        name = delivery.candidates[cid]['change_name']
        if name: subjects.add('change:' + name)
    return baseline, current, delivery, control, association, selected, contributions, subjects, engineering


def actual_path(store, snapshot):
    # Looking at history catches a Change created and then deleted in the same
    # branch, even when the final tree alone appears to be a small code patch.
    paths = store.git('log', '--format=', '--name-only', snapshot['target_revision'] + '..' + snapshot['head_revision'],
                      '--', 'openspec/changes').decode().splitlines()
    if any(path for path in paths):
        raise CheckError('tiny.standard-history', 'this unmerged history changes OpenSpec Change artifacts; continue its actual Standard path', refs=sorted(set(paths) - {''}))


def executions(delivery, snapshot, association, selected, *, control, integration=None):
    expectations = snapshot.get('verification_inputs', [])
    if selected and not expectations:
        raise CheckError('tiny.executions', 'associated business ACs need actual execution evidence')
    checked, refs, task_behaviors = [], [], set()
    for row in expectations:
        if row['verification_ref'] in refs:
            raise CheckError('tiny.executions', 'duplicate execution reference')
        refs.append(row['verification_ref'])
        result = check_execution(delivery.context, row['verification_ref'], tested_revision=row['tested_revision'], identities=row['identities'], engineering_review=delivery.review)
        for coverage in result['record']['coverage']:
            coverage_identity(delivery, coverage)
        for coverage in result['record'].get('task_coverage', []):
            if coverage['subject'] != snapshot['subject'] or coverage['tiny_ref'] != snapshot['tiny_ref']:
                raise CheckError('tiny.execution-task', 'E task coverage belongs to another task/association')
            task_behaviors.update(coverage['ui_behaviors'])
        for contract in association['spec_refs']:
            if not any(ref['path'] == contract['path'] and ref['sha256'] == contract['sha256'] for ref in result['record']['input_refs']):
                raise CheckError('tiny.execution-contract', 'actual regression inputs must include the applicable main Spec')
        checked.append(result)
    tested_content(delivery.context, checked, snapshot['head_revision'], None, candidate_id=None, control=control,
                   integration=integration, delivery_subject=snapshot['subject'])
    covered, links = {}, {}
    for execution in checked:
        for row in execution['record']['coverage']:
            if 'requirement' in row:
                for ac in row['acceptance']:
                    covered.setdefault((row['requirement'], ac), set()).add(row['contribution'])
            for obligation in delivery.plan['obligations']:
                same = (row['contribution'] == obligation.get('capability_ref') or
                        row.get('requirement') == obligation.get('requirement') and
                        row['contribution'] in obligation.get('contributions', []) and
                        bool(set(row.get('acceptance', [])) & set(obligation.get('acceptance', []))))
                if same:
                    # A combination obligation can span several coverage rows
                    # in one E. Keep other obligations and executions separate.
                    key = (obligation['id'], canonical_bytes(execution['reference']))
                    link = links.setdefault(key, {'obligation_id': obligation['id'],
                        'verification_ref': execution['reference'], 'case_ids': []})
                    link['case_ids'] = sorted(set(link['case_ids']) | set(row['case_ids']))
    for pair in selected:
        if not delivery.coverage[pair] <= covered.get(pair, set()):
            raise CheckError('tiny.coverage', 'actual regression evidence omits part of the selected AC contribution set', refs=list(pair))
    # Business behaviors are covered by the original R/AC/case association;
    # UI-only engineering behaviors use the real task, never a fabricated R/C.
    needed = set(association.get('ui_behaviors', []))
    if needed:
        business_ui = {f"{uid}/r{delivery.requirements.records[uid]['value']['revision']}/{ac}" for uid, ac in selected}
        needed -= business_ui
    if not needed <= task_behaviors:
        raise CheckError('tiny.ui-execution-coverage', 'actual task E omits selected UI engineering behaviors', refs=sorted(needed - task_behaviors))
    return {'acceptance': [{'requirement': uid, 'acceptance': ac, 'contributions': sorted(delivery.coverage[(uid, ac)])}
                          for uid, ac in sorted(selected)], 'verification_links': list(links.values()),
            'verification_refs': refs,
            'task_ui_behaviors': sorted(task_behaviors),
            'deferred_obligations': [row['id'] for row in delivery.plan['obligations']
                                    if row['checkpoint'] in ('completion', 'release') and
                                    any((row.get('requirement'), ac) in selected for ac in row.get('acceptance', []))]}


def conditions(delivery, snapshot, contributions, verified):
    states, refs = [], []
    for cid in sorted({delivery.allocations[ref]['node'] for ref in contributions} & delivery.candidates.keys()):
        readiness = implementation_dependencies(delivery, cid, {'mode': 'execution'}, snapshot['target_revision'],
                                                consumer_contributions=contributions)
        refs.extend(row['assessment_ref'] for row in readiness if 'assessment_ref' in row)
        rows, required = due_integration(delivery, snapshot, {'candidate_id': cid}, verified,
                                         checkpoints=('integration', 'merge'), consumer_contributions=contributions)
        states.extend(rows)
        refs.extend(required)
    return states, refs


def review_inputs(snapshot, association, final, verified, condition_refs, original=None, ui=None):
    refs = [snapshot['tiny_ref'], snapshot['baseline_ref'], association['task_ref'],
            *association['policy_refs'], *association['spec_refs'],
            *snapshot['engineering_inputs'].values(), *verified['verification_refs'],
            *final['input_refs'], *final['evidence_refs'], *local_refs(ui)]
    if original:
        refs.extend([original['observation_ref'], original['pre_merge_context_ref'], original['pre_merge_result_ref'],
                     original['operation_ref'], original['confirmation']['evidence_ref']])
    unique_refs = lambda rows: list({canonical_bytes(ref): ref for ref in rows}.values())
    return unique_refs(refs), unique_refs(condition_refs)


def reviewed(current, snapshot, association, final, verified, condition_refs, original=None, ui=None):
    refs, contextual = review_inputs(snapshot, association, final, verified, condition_refs, original, ui)
    phase = 'integration' if original else 'merge'
    path = 'reviews/' + phase + '/' + tiny_review_key(snapshot['subject']) + '.yaml'
    check_review(replace(current, content_commit=snapshot['metadata_revision']), path, 'delivery', (),
                 roles={'engineering-owner'}, required_refs=refs, required_context_refs=contextual,
                 required_checks=REVIEW_CHECKS + (UI_CHECKS if ui else ()))
    ref = {'commit': snapshot['metadata_revision'], 'path': current.vr + '/' + path,
           'sha256': digest(current.store.read(snapshot['metadata_revision'], current.vr + '/' + path))}
    current_ref(current.store, ref, snapshot['head_revision'])
    return ref


def finish(baseline, snapshot, *values):
    references = References(baseline)
    for value in (snapshot, *values): references.fixed(value)
    pins = retain_inputs(baseline, [snapshot[key] for key in ('metadata_revision', 'head_revision', 'target_revision')])
    if snapshot['evaluation_mode'] == 'current':
        live = capture(baseline.store, extra_roots=['openspec'])
        if live.record['base_revision'] != snapshot['head_revision'] or live.record['changes']:
            raise CheckError('tiny.uncommitted-inputs', 'final delivery needs the actual clean metadata head')
        live.assert_current(baseline.store)
    resolve(baseline.store, snapshot)
    return pins


def check_tiny_pre_merge(store, snapshot):
    if any(key not in snapshot for key in ('final_checks_ref', 'merge_request_ref')):
        raise CheckError('tiny.premerge-context', 'Tiny merge requires actual final checks and a bound merge request')
    baseline, current, delivery, control, association, selected, contributions, subjects, engineering = current_inputs(store, snapshot)
    actual_path(store, snapshot)
    for entry in ('apply', 'merge'):
        control.holds.require_clear(line=snapshot['delivery_line'], entry=entry, subjects=subjects)
    final = read_final_checks(current, snapshot['final_checks_ref'], change=None, candidate_id=None,
        head_revision=snapshot['head_revision'], target_revision=snapshot['target_revision'], archive_revision=None,
        control=control, delivery_subject=snapshot['subject'])
    verified = executions(delivery, snapshot, association, selected, control=control)
    ui = check_task_ui(delivery, snapshot, association, contributions, action='pre-merge')
    ui = execution_inputs(delivery, ui, snapshot.get('verification_inputs', []))
    states, condition_refs = conditions(delivery, snapshot, contributions, verified)
    review_ref = reviewed(current, snapshot, association, final, verified, condition_refs, ui=ui)
    reference = snapshot['merge_request_ref']
    if not reference['path'].startswith(current.vr + '/trace/evidence/'):
        raise CheckError('tiny.request-path', 'retain merge authority in the existing evidence namespace')
    request = validate('merge_request', parse_json(current_ref(store, reference, snapshot['head_revision'])))
    expected = {key: snapshot[key] for key in ('subject', 'version', 'delivery_line', 'baseline_ref', 'tiny_ref', 'final_checks_ref', 'target_revision')}
    expected['candidate_revision'] = final['tested_revision']
    if any(request.get(key) != value for key, value in expected.items()):
        raise CheckError('tiny.request-scope', 'merge request does not select these actual task/PR checks and target')
    if request['review_ref']['path'] != review_ref['path'] or store.ref(request['review_ref']) != store.ref(review_ref):
        raise CheckError('tiny.request-review', 'merge request must bind the actual final Review')
    decision(current, request['decision'], roles={'integrator'})
    pins = finish(baseline, snapshot, association, engineering, verified, request)
    return {'rule_id': 'G3.pre-merge', 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {'subject': snapshot['subject'], 'tiny_ref': snapshot['tiny_ref'], 'baseline_ref': snapshot['baseline_ref'],
                'delivery': verified, 'final_checks': final, 'final_review_ref': review_ref, 'merge_request_ref': reference,
                'ui': ui,
                'integration_conditions': states, 'retained_pins': pins, 'merge_ready': snapshot['evaluation_mode'] == 'current',
                'scope': 'actual Tiny pre-merge conditions only; no merge, Change, reservation or Version Completion'},
            'next_owner': 'integrator'}


def check_tiny_integrated(store, snapshot):
    from .integration import read_integration
    if 'integration_observation_ref' not in snapshot:
        raise CheckError('tiny.integration-context', 'Tiny integration needs the real merge observation and original admission')
    baseline, current, delivery, control, association, selected, contributions, subjects, engineering = current_inputs(store, snapshot, integrated=True)
    reference = snapshot['integration_observation_ref']
    current_ref(store, reference, snapshot['head_revision'])
    original = read_integration(current, reference, target_revision=snapshot['target_revision'])
    if any(original.get(key) != snapshot[key] for key in ('subject', 'tiny_ref', 'baseline_ref')):
        raise CheckError('tiny.integration-origin', 'integration must continue the same actual task/PR association and baseline')
    if not store.ancestor(original['control_revision'], snapshot['control_revision']):
        raise CheckError('tiny.control-history', 'retain the original admission control history')
    projection = {**original, 'engineering_inputs': snapshot['engineering_inputs']}
    previous_ui = original['original_admission'].get('ui')
    ui = check_task_ui(delivery, snapshot, association, contributions, action='integrated', previous=previous_ui)
    if ui:
        projection['engineering_inputs'] = {**projection['engineering_inputs'],
            **{f'ui_{i}': ref for i, ref in enumerate(local_refs(ui))}}
    verified = executions(delivery, snapshot, association, selected, control=control, integration=projection)
    ui = execution_inputs(delivery, ui, snapshot.get('verification_inputs', []), previous=previous_ui)
    final = original['original_admission']['final_checks']
    fresh = snapshot.get('integration_checks_ref')
    if not original['facts']['branch_inputs_preserved'] and fresh is None:
        raise CheckError('tiny.changed-integration', 'changed actual integration inputs need applicable current final checks')
    if fresh is not None:
        final = read_final_checks(current, fresh, change=None, candidate_id=None,
            head_revision=snapshot['head_revision'], target_revision=snapshot['target_revision'], archive_revision=None,
            control=control, delivery_subject=snapshot['subject'])
    states, condition_refs = conditions(delivery, snapshot, contributions, verified)
    review_ref = reviewed(current, snapshot, association, final, verified, condition_refs, original, ui)
    holds = [row for entry in ('propose', 'apply', 'merge', 'release')
             for row in control.holds.blockers(line=snapshot['delivery_line'], entry=entry, subjects=subjects)]
    pins = finish(baseline, snapshot, association, engineering, verified)
    return {'rule_id': 'G3.integrated', 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {'subject': snapshot['subject'], 'tiny_ref': snapshot['tiny_ref'], 'baseline_ref': snapshot['baseline_ref'],
                'current_integration': snapshot['evaluation_mode'] == 'current', 'integration': original['facts'], 'delivery': verified,
                'ui': ui,
                'final_checks': final, 'final_review_ref': review_ref, 'integration_conditions': states,
                'current_holds': holds, 'retained_pins': pins,
                'scope': 'actual integrated task/PR facts only; no reservation, new action authority or Version Completion'},
            'next_owner': 'engineering-owner'}


def check_task_ui(delivery, snapshot, association, contributions, *, action, previous=None):
    return check_ui(delivery, snapshot, kind='task', subject=snapshot['subject'],
                    contributions=sorted(contributions), action=action, previous=previous,
                    task=(association, snapshot['tiny_ref']))


def check_boundary(store, snapshot, *, action):
    """Original task boundary: actual BL/target/control + the shared observer.

    Reuse the task's prospective pre-merge context without requiring future E,
    final checks or a merge request. This is not G2/apply or a G3 admission.
    The original task remains the authority for explicit scope/authorization.
    """
    if (action not in ('start', 'resume') or snapshot['gate'] != 'G3' or
            snapshot['phase'] != 'pre-merge' or not snapshot['subject'].startswith(('task:', 'pr:'))):
        raise CheckError('tiny.boundary-context', 'use the actual Tiny task context and start/resume action')
    baseline, current, delivery, control, association, selected, contributions, subjects, engineering = current_inputs(store, snapshot)
    actual_path(store, snapshot)
    control.holds.require_clear(line=snapshot['delivery_line'], entry='apply', subjects=subjects)
    ui = check_task_ui(delivery, snapshot, association, contributions, action=action)
    # A dirty implementation is expected on resume; authority/planning bytes
    # cannot drift silently. Capture the original inventory without discarding
    # edits or turning that inventory into implementation permission.
    live = capture(store, extra_roots=['openspec']) if snapshot['evaluation_mode'] == 'current' else None
    if live:
        if live.record['base_revision'] != snapshot['head_revision']:
            raise CheckError('tiny.boundary-head', 'task boundary must inspect the actual worktree HEAD')
        protected = {ref['path'] for ref in [snapshot['tiny_ref'], association['task_ref'],
                     *association['policy_refs'], *association['spec_refs'],
                     *snapshot['engineering_inputs'].values(), *local_refs(ui)]}
        for row in live.record['changes']:
            path = row['path']
            if (path in protected or path in ('scripts/requirements-check', 'scripts/ui-design-check') or
                    path.startswith(('requirements/', 'harness/', 'openspec/changes/'))):
                raise CheckError('tiny.boundary-inputs', 'review changed task/authority inputs before resuming', refs=[path])
        live.assert_current(store)
    references = References(current)
    for value in (snapshot, association, engineering): references.fixed(value)
    resolve(store, snapshot)
    return {'rule_id': 'tiny.boundary', 'result': 'passed', 'subject': snapshot['subject'],
            'action': action, 'current_checked': snapshot['evaluation_mode'] == 'current',
            'engineering_authorized': False, 'merge_ready': False, 'ui': ui,
            'control_revision': snapshot['control_revision'], 'subjects': sorted(subjects),
            'task_ref': association['task_ref'], 'tiny_ref': snapshot['tiny_ref'],
            'worktree': live.record if live else None,
            'scope': 'task boundary inputs and restrictions only; retain the original task scope, authorization and recovery limits'}
