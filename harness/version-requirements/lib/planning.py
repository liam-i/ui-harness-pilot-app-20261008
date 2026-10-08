"""G2 planning: one published reservation, actual artifacts and bound Review."""
from .availability import implementation_dependencies
from .context import resolve
from .control import event
from .control_delivery import KINDS, read_delivery_control
from .core import parse_json, parse_yaml
from .delivery import DeliveryIndex
from .dispatch import baseline_context, current_engineering, preserved_inputs, retain_inputs
from .errors import CheckError, InputError
from .feasibility import check_feasibility
from .models import validate
from .openspec_artifacts import read_observation
from .planning_applicability import assessment_scope, retain_approval, stable_trace
from .planning_trace import check_planning_trace
from .requirements import RequirementIndex
from .review_scope import References, ReviewScope


def check_change_scope(store, target, head, change_root):
    """Implementation permission covers this Change, not other planning work.

    Other Changes already integrated on the selected target remain intact.
    Derive the namespace from the actual locator rather than inventing a root.
    """
    namespace = change_root.rsplit('/', 1)[0] + '/'
    selected = change_root + '/'
    before, after = store.tree(target), store.tree(head)
    changed = sorted(path for path in before.keys() | after.keys()
                     if path.startswith(namespace) and not path.startswith(selected) and before.get(path) != after.get(path))
    if changed:
        raise CheckError('apply.other-change', 'resuming this Change cannot create or alter another Change planning/archived directory', refs=changed)


def check_unique_change(store, trace_ref, trace, revision):
    """One logical Change cannot be owned by another candidate or Version."""
    for path in store.tree(revision):
        if path.startswith('requirements/versions/') and '/trace/changes/' in path and path.endswith('.yaml') and path != trace_ref['path']:
            other = parse_yaml(store.read(revision, path))
            if not isinstance(other, dict) or 'change' not in other:
                raise InputError('trace.identity-unreadable', 'cannot establish uniqueness against an unreadable Trace', refs=[path])
            if other['change'] == trace['change']:
                raise CheckError('trace.duplicate-change', 'another candidate/Version already owns this logical Change', refs=[path])


def check_planning(store, snapshot, *, control_entry='propose', execution_origin=None, alignment_only=False):
    continuing = snapshot['phase'] == 'planning' and snapshot.get('apply_origin_ref') is not None
    replanning = continuing and snapshot.get('planning_inputs_ref') is not None
    if continuing and execution_origin is None:
        from .execution import original_admission
        execution_origin = original_admission(store, snapshot)
    reference, trace_ref = snapshot.get('dispatch_ref'), snapshot.get('trace_ref')
    if reference is None or trace_ref is None or snapshot['control_revision'] is None:
        raise CheckError('planning.context-required', 'planning needs exact published event, current Trace and control references')
    row = event(store, reference)
    if row['kind'] not in KINDS:
        raise InputError('planning.event', 'planning requires a dispatch or execution-alignment event')
    payload = validate(KINDS[row['kind']], row['payload'])
    if (row['version'] != snapshot['version'] or row['target_line'] != snapshot['delivery_line'] or
            snapshot['subject'] != 'candidate:' + snapshot['version'] + '/' + payload['candidate_id'] or
            payload['baseline_ref'] != snapshot['baseline_ref'] or payload['target_revision'] != snapshot['target_revision']):
        raise CheckError('planning.snapshot-binding', 'published inputs do not bind the requested candidate, baseline and current target')
    context, baseline = baseline_context(store, snapshot)
    control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
    key = (snapshot['delivery_line'], snapshot['version'], payload['candidate_id'])
    reservation = control.reservations.get(key)
    if execution_origin is not None and (reservation is None or reservation['reservation_ref'] != execution_origin['evidence']['reservation_ref']):
        raise CheckError('apply.origin-reservation', 'planning/execution must preserve the original reservation')
    published = control.event_refs.get(reference['event_id']) == reference
    if published:
        if reservation is None or reservation['event_ref'] != reference:
            raise CheckError('planning.unpublished-or-stale', 'planning must resume the latest confirmed event of the original reservation')
    else:
        if row['kind'] != 'execution-alignment' or reservation is None:
            raise CheckError('planning.unpublished-or-stale', 'initial dispatch must be published before any planning; only alignment of its existing reservation may be previewed')
        control.preview(store, reference)
    trace = validate('planning_trace', parse_yaml(store.ref(trace_ref)))
    if not alignment_only:
        control.holds.require_clear(line=key[0], entry=control_entry, subjects=reservation['inputs']['subjects'] + ['change:' + trace['change']])
    observation = read_observation(store, trace['observation_ref'], change=trace['change'],
                                   actual_revision=snapshot['head_revision'], allow_task_progress=execution_origin is not None)
    allowed = {p for paths in observation['artifacts'].values() for p in paths} | {observation['change_root'] + '/.openspec.yaml'}
    allowed.update(ref['path'] for ref in observation['input_refs']
                   if ref['path'].startswith(observation['change_root'] + '/assets/'))
    if execution_origin is None and any(t['done'] for t in observation['tasks'].values()):
        raise InputError('planning.resume-unsupported', 'implementation has started; use the pending Apply/Update applicability path, not initial planning admission')
    current = current_engineering(context, snapshot, payload, planning_files=allowed, executing=execution_origin is not None)
    if execution_origin is not None:
        check_change_scope(store, snapshot['target_revision'], snapshot['head_revision'], observation['change_root'])
    for revision in {snapshot['metadata_revision'], snapshot['head_revision'], current.content_commit}:
        preserved_inputs(context, revision, baseline)
    requirements = RequirementIndex(context)
    requirements.check_content()
    delivery = DeliveryIndex(requirements, engineering_context=current, map_ref=payload['map_ref'], verification_plan_ref=payload['verification_plan_ref'])
    structure, feasibility = delivery.check(), check_feasibility(delivery)
    scope = ReviewScope(requirements, delivery)
    engineering = scope.check_engineering()
    scope.engineering_questions.check_endpoints(requirements.sources.units, requirements.question_requirement_ids(), candidates=delivery.candidates)
    scope.engineering_questions.check_baseline(requirements.records)
    for qid, group in scope.engineering_questions.impacts.items():
        if payload['candidate_id'] in group['blocking_for']:
            scope.engineering_questions.require_resolved(qid)
    states = [] if alignment_only else implementation_dependencies(delivery, payload['candidate_id'], payload, snapshot['target_revision'])
    retaining = payload['candidate_id'] in assessment_scope(delivery)
    if replanning and retaining:
        raise CheckError('planning.update-assessment', 'a new whole-plan Review needs the current engineering assessment resolved; do not retain an old planning approval or pending disposition')
    checked = check_planning_trace(delivery, trace_ref, snapshot, payload,
        require_review=not retaining and (execution_origin is None or replanning), allow_task_progress=execution_origin is not None)
    from .ui_integration import candidate
    action = ('resume' if execution_origin is not None else 'start') if snapshot['phase'] == 'apply' else 'propose'
    ui = candidate(delivery, snapshot, payload['candidate_id'], action=action,
                   previous=execution_origin['evidence'].get('ui') if execution_origin is not None else None)
    applicability = None
    if retaining:
        applicability = retain_approval(delivery, snapshot, checked, control)
        checked.update(review=applicability['review'], review_ref=applicability['review_ref'],
                       execution_inputs=applicability['execution_inputs'])
    elif execution_origin is not None and not replanning:
        origin, admitted = execution_origin['snapshot'], execution_origin['evidence']
        original_payload = event(store, origin['dispatch_ref'])['payload']
        if (origin['target_revision'] != snapshot['target_revision'] or
                any(store.ref(original_payload[k]) != store.ref(payload[k]) for k in
                    ('map_ref', 'verification_plan_ref', 'engineering_review_ref'))):
            raise CheckError('apply.reassessment-required', 'upstream or reviewed engineering inputs changed; provide current planning applicability or Update')
        original_trace = validate('planning_trace', parse_yaml(store.ref(origin['trace_ref'])))
        if stable_trace(original_trace) != stable_trace(checked['trace']):
            raise CheckError('planning.approval-stale', 'planning associations changed after initial admission; use the actual Update/review path')
        original_observation = parse_json(store.ref(original_trace['observation_ref']))
        current_observation = parse_json(store.ref(checked['trace']['observation_ref']))
        if store.ref(original_observation['schema_ref']) != store.ref(current_observation['schema_ref']):
            raise CheckError('planning.approval-stale', 'Schema content changed after initial admission')
        approved = admitted['planning_review_ref']
        for revision in {snapshot['metadata_revision'], snapshot['head_revision']}:
            store.read(revision, approved['path'], approved['sha256'])
        checked.update(review=parse_yaml(store.ref(approved)), review_ref=approved)
    # The original published event is not a capability to create another Change.
    # Bind its one actual name in the shared current map and retained Trace.
    check_unique_change(store, trace_ref, trace, snapshot['metadata_revision'])
    refs = References(current)
    for value in (row, payload, engineering, checked['trace'], checked['review'], parse_json(store.ref(trace['observation_ref']))):
        refs.fixed(value)
    pins = retain_inputs(context, [snapshot[k] for k in ('metadata_revision', 'head_revision', 'target_revision')])
    resolve(store, snapshot)
    return {'rule_id': 'rc.planning-alignment' if alignment_only else 'G2.planning', 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {'trace_ref': trace_ref, 'change': trace['change'], 'dispatch_ref': reference,
                'reservation_ref': reservation['reservation_ref'], 'baseline_ref': snapshot['baseline_ref'],
                'alignment_published': published,
                'planning_digest': checked['observation']['planning_digest'], 'locator': checked['observation']['change_root'],
                'review': checked['review']['id'], 'planning_review_ref': checked['review_ref'],
                'applicability': applicability, 'dependencies': states, 'links': checked['links'],
                'execution_inputs': checked['execution_inputs'],
                'tasks': (checked['execution_inputs'] if replanning else observation)['tasks'],
                'tasks_revision': (checked['execution_inputs'] if replanning else observation)['tasks_revision'],
                'assets': checked['assets'], 'structure': structure, 'feasibility': feasibility, 'ui': ui,
                'retained_pins': pins, 'apply_permission': False,
                'scope': ('local RC whole-plan alignment only; control and dependency readiness still require G2' if alignment_only else
                          'actual planning and whole-plan revisions with bound Review; no implementation or delivery permission')},
            'next_owner': 'engineering-owner'}
