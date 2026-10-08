"""Apply admission/resumption with current worktree checks; Agent/TDD executes."""
from types import SimpleNamespace

from .context import resolve
from .control import event
from .core import parse_json, parse_yaml
from .dispatch import retain_inputs
from .errors import CheckError, InputError
from .models import validate
from .openspec_artifacts import read_observation
from .planning import check_planning
from .reviews import decision, evidence
from .worktree import check_apply_worktree
from .ui_receipts import historical


def original_admission(store, snapshot):
    """Revalidate the fixed first Apply for either continuation or replanning."""
    origin = None
    origin_ref = snapshot.get('apply_origin_ref')
    if origin_ref is not None:
        original = validate('snapshot', parse_json(evidence(store, origin_ref)))
        if original.get('apply_origin_ref') is not None:
            raise InputError('apply.origin-chain', 'resume from the actual initial admission, not a recursive chain of resume snapshots')
        if (original['gate'], original['phase'], original['subject'], original['version'], original['delivery_line']) != (
                'G2', 'apply', snapshot['subject'], snapshot['version'], snapshot['delivery_line']):
            raise CheckError('apply.origin-scope', 'original admission belongs to a different phase, candidate, Version/line or baseline')
        if original['evaluation_mode'] != 'current':
            raise CheckError('apply.origin-historical', 'a historical query is not an original current admission')
        if original['control_revision'] is None or snapshot['control_revision'] is None or not store.ancestor(original['control_revision'], snapshot['control_revision']):
            raise CheckError('apply.origin-control', 'resume must continue the original published control history')
        if original['baseline_ref'] != snapshot['baseline_ref']:
            from .control_delivery import read_delivery_control
            control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
            control.changes.baseline_chain(original['baseline_ref'], snapshot['baseline_ref'],
                                           version=snapshot['version'], line=snapshot['delivery_line'])
        # Recompute the fixed initial inputs and authority, never trust a saved
        # PASS. Historical evaluation here deliberately grants no fresh action.
        with store.input_scope():
            previous = check_apply(store, historical(original, snapshot))
        origin = {'snapshot': original, 'evidence': previous['evidence']}
    return origin


def check_apply(store, snapshot):
    reference = snapshot.get('apply_request_ref')
    if reference is None:
        raise CheckError('apply.request-required', 'planning approval and release are not an implementation request')
    request = validate('apply_request', parse_json(evidence(store, reference)))
    context = resolve(store, snapshot)
    path = context.vr + '/trace/evidence/'
    if not reference['path'].startswith(path):
        raise CheckError('apply.request-path', 'retain the actual implementation request in this Version evidence namespace')
    for revision in {snapshot['metadata_revision'], snapshot['head_revision']}:
        store.read(revision, reference['path'], reference['sha256'])
    origin_ref = snapshot.get('apply_origin_ref')
    origin = original_admission(store, snapshot)
    planning_origin = origin
    updated_ref = request.get('planning_snapshot_ref')
    if updated_ref is not None:
        updated = validate('snapshot', parse_json(evidence(store, updated_ref)))
        if (origin is None or updated.get('apply_origin_ref') != origin_ref or
                (updated['gate'], updated['phase'], updated['evaluation_mode'], updated['subject'], updated['version'], updated['delivery_line'], updated['baseline_ref']) !=
                ('G2', 'planning', 'current', snapshot['subject'], snapshot['version'], snapshot['delivery_line'], snapshot['baseline_ref'])):
            raise CheckError('apply.updated-planning-scope', 'updated planning must continue this exact original execution, candidate, line and baseline')
        if updated['control_revision'] is None or snapshot['control_revision'] is None or not store.ancestor(updated['control_revision'], snapshot['control_revision']):
            raise CheckError('apply.updated-planning-control', 'current control does not extend the reviewed planning context')
        with store.input_scope():
            replay = check_planning(store, historical(updated, snapshot), execution_origin=origin)
        planning_origin = {'snapshot': updated, 'evidence': replay['evidence']}
    # Apply consumes the Apply restriction, not a later Propose-only hold.
    checked = check_planning(store, snapshot, control_entry='apply', execution_origin=planning_origin)
    result = checked['evidence']
    payload = event(store, snapshot['dispatch_ref'])['payload']
    if not result['alignment_published'] or payload['mode'] != 'execution':
        raise CheckError('apply.execution-required', 'only the confirmed execution reservation can enter Apply; planning-only/draft cannot')
    if origin is not None and origin['evidence']['reservation_ref'] != result['reservation_ref']:
        raise CheckError('apply.origin-reservation', 'resumption cannot transfer work to another reservation')
    if ((request['candidate_id'], request['version'], request['delivery_line'], request['baseline_ref']) !=
            (payload['candidate_id'], snapshot['version'], snapshot['delivery_line'], snapshot['baseline_ref']) or
            request['reservation_ref'] != result['reservation_ref'] or
            request['planning_digest'] != result['planning_digest']):
        raise CheckError('apply.request-scope', 'implementation request belongs to another reservation, baseline or plan')
    approved = result['planning_review_ref']
    selected = request['planning_review_ref']
    # Metadata may be saved after the approval; compare the actual same Review,
    # while preserving the request's original fixed commit identity.
    if (selected['path'] != approved['path'] or selected['sha256'] != approved['sha256'] or
            store.ref(selected) != store.ref(approved)):
        raise CheckError('apply.request-review', 'request does not bind the applicable actual planning Review')
    # A retained metadata commit can be squashed or stored on a separate branch.
    # Its exact reference binds an already existing approval; ancestry is not
    # the request's authority or the clock of its actual decision.
    decision(SimpleNamespace(store=store, version=context.version), request['decision'], roles={'engineering-owner'})
    if request['decision']['evidence_ref'] in [payload[k]['evidence_ref'] for k in ('release_decision', 'propose_request')]:
        raise CheckError('apply.request-evidence', 'cannot relabel the original release/Propose request as a later implementation request')
    trace = validate('planning_trace', parse_yaml(store.ref(snapshot['trace_ref'])))
    observation = read_observation(store, trace['observation_ref'], change=trace['change'],
        actual_revision=snapshot['head_revision'], allow_task_progress=origin is not None)
    if not set(request['task_ids']) <= observation['tasks'].keys():
        raise CheckError('apply.request-task', 'implementation request selects missing or changed Task identities')
    extra_roots = (planning_origin['evidence'].get('execution_inputs') or {}).get('extra_roots', []) if planning_origin else []
    live = check_apply_worktree(store, snapshot, observation, resuming=origin is not None,
                               extra_roots=extra_roots) if snapshot['evaluation_mode'] == 'current' else None
    retain_inputs(context, [snapshot[k] for k in ('metadata_revision', 'head_revision', 'target_revision')])
    resolve(store, snapshot)
    current_tasks = live['tasks'] if live else observation['tasks']
    worktree = None
    tasks_revision = snapshot['head_revision']
    if live:
        worktree = {'kind': 'worktree-observation', 'base_revision': live['input']['base_revision'],
                    'input_digest': live['input']['input_digest'], 'extra_roots': live['input']['extra_roots'],
                    'files': live['input']['files'], 'retained': False,
                    'changed_paths': [row['path'] for row in live['input']['changes']]}
        if observation['artifacts']['tasks'][0] in worktree['changed_paths']:
            tasks_revision = None
    return {'rule_id': 'G2.apply', 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {**result, 'apply_request_ref': reference, 'apply_origin_ref': origin_ref,
                         'planning_snapshot_ref': updated_ref,
                         'worktree': worktree, 'tasks': current_tasks, 'tasks_revision': tasks_revision,
                         'task_evidence': (live if live else observation)['task_evidence'],
                         'tasks_input': {'base_revision': snapshot['head_revision'],
                                         'worktree_input_digest': worktree['input_digest'] if worktree else None},
                         'authorized_task_ids': request['task_ids'],
                         'remaining_authorized_task_ids': [tid for tid in request['task_ids'] if not current_tasks[tid]['done']],
                         'apply_permission': snapshot['evaluation_mode'] == 'current',
                         'scope': 'actual-worktree Apply admission/resumption with reviewed planning revisions; no delivery permission; controlled entry/task-boundary integration remains pending'},
            'next_owner': 'coding-agent'}
