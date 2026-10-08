"""G3 pre-merge: revalidated origin, actual archived candidate, current controls.

The integrator still serializes the actual action. This reader never merges,
publishes, releases capacity, or invents a future integrated commit.
"""
from dataclasses import replace

from .archive import check_archived_delivery
from .availability import implementation_dependencies
from .context import resolve
from .control import event
from .control_delivery import KINDS, read_delivery_control
from .core import canonical_bytes, digest, parse_json, parse_yaml
from .delivery import DeliveryIndex
from .delivery_trace import current_ref
from .dispatch import baseline_context, current_engineering, preserved_inputs, retain_inputs
from .errors import CheckError
from .feasibility import check_feasibility
from .final_checks import read_final_checks, unchanged_since
from .models import validate
from .planning import check_unique_change
from .planning_applicability import assessment_scope, retain_approval
from .prearchive import check_pre_archive, delivery_review_inputs, due_integration
from .requirements import RequirementIndex
from .review_scope import References, ReviewScope
from .reviews import check_review, decision, evidence
from .worktree import capture
from .ui_receipts import historical

REVIEW_CHECKS = ('final-inputs', 'project-checks', 'archive-and-sync',
                 'verification-coverage', 'integration-conditions', 'merge-scope')


def merge_review_inputs(snapshot, trace, archived, final, payload, planning_review_ref, condition_refs, *, ui=None):
    refs, contextual = delivery_review_inputs(snapshot, trace, archived['observation'], payload,
                                              {'planning_review_ref': planning_review_ref, 'ui': ui})
    refs.extend([snapshot['pre_archive_context_ref'], archived['archive']['observation_ref'],
                 *final['evidence_refs'], *final['input_refs'], *archived['asset_refs']])
    for row in archived['archive']['file_moves']:
        refs.extend(row.values())
    # Saving Review/request metadata advances head without changing the tested
    # main Spec. Bind that content at the actual tested commit, not a future
    # evidence-save commit. check_review still resolves each exact hash there.
    for row in archived['archive']['main_spec_refs']:
        refs.extend([row['archived_ref'], {**row['current_ref'], 'commit': final['tested_revision']}])
    refs.extend(archived['archive']['operation_refs'] + archived['archive']['linked_refs'])
    refs.extend({**ref, 'commit': final['tested_revision']} for ref in archived['archive']['main_linked_refs'])
    contextual.extend(condition_refs)
    unique = lambda rows: list({canonical_bytes(ref): ref for ref in rows}.values())
    return unique(refs), unique(contextual)


def check_pre_merge(store, snapshot, *, alignment_only=False):
    context = resolve(store, snapshot)
    required = ('dispatch_ref', 'trace_ref', 'apply_origin_ref', 'apply_request_ref', 'verification_inputs',
                'pre_archive_context_ref', 'final_checks_ref', 'merge_request_ref')
    missing = [key for key in required if key not in snapshot]
    if missing:
        raise CheckError('premerge.context-required', 'pre-merge needs its actual origin, archived Trace, final checks and bound merge request', refs=missing)
    origin = validate('snapshot', parse_json(evidence(store, snapshot['pre_archive_context_ref'])))
    same = ('subject', 'version', 'delivery_line', 'baseline_ref', 'apply_origin_ref', 'apply_request_ref')
    if ((origin['gate'], origin['phase'], origin['evaluation_mode']) != ('G3', 'pre-archive', 'current') or
            any(origin.get(key) != snapshot[key] for key in same)):
        raise CheckError('premerge.origin', 'pre-merge must continue this actual current pre-archive admission and implementation authority')
    if not origin['control_revision'] or not snapshot['control_revision'] or not store.ancestor(origin['control_revision'], snapshot['control_revision']):
        raise CheckError('premerge.control-history', 'current control must continue the original published history')
    with store.input_scope():
        admitted = check_pre_archive(store, historical(origin, snapshot))['evidence']
    trace = validate('planning_trace', parse_yaml(current_ref(store, snapshot['trace_ref'], snapshot['head_revision'])))
    if snapshot['subject'] != 'change:' + trace['change']:
        raise CheckError('premerge.change', 'current subject differs from the archived Trace Change')
    check_unique_change(store, snapshot['trace_ref'], trace, snapshot['metadata_revision'])
    row = event(store, snapshot['dispatch_ref'])
    if row['kind'] not in KINDS:
        raise CheckError('premerge.dispatch', 'continue the original reservation or its real alignment')
    payload = validate(KINDS[row['kind']], row['payload'])
    if ((row['version'], row['target_line'], payload['baseline_ref'], payload['target_revision'], payload['candidate_id']) !=
            (snapshot['version'], snapshot['delivery_line'], snapshot['baseline_ref'], snapshot['target_revision'], trace['candidate_id']) or
            trace['dispatch_ref'] != snapshot['dispatch_ref']):
        raise CheckError('premerge.dispatch', 'current published inputs, Trace and actual target disagree')
    control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
    key = (snapshot['delivery_line'], snapshot['version'], trace['candidate_id'])
    reservation = control.reservations.get(key)
    if reservation is None or reservation['reservation_ref'] != admitted['reservation_ref']:
        raise CheckError('premerge.reservation', 'archived delivery still occupies its original reservation')
    published = control.event_refs.get(snapshot['dispatch_ref']['event_id']) == snapshot['dispatch_ref']
    if published:
        if reservation['event_ref'] != snapshot['dispatch_ref']:
            raise CheckError('premerge.alignment', 'use the latest confirmed reservation alignment')
    elif row['kind'] == 'execution-alignment':
        control.preview(store, snapshot['dispatch_ref'])
    else:
        raise CheckError('premerge.alignment', 'an initial unpublished release cannot enter final delivery')
    if payload['mode'] != 'execution':
        raise CheckError('premerge.mode', 'planning-only is not delivery authority')
    prefix = 'task:' + trace['change'] + '/'
    subjects = reservation['inputs']['subjects'] + ['change:' + trace['change']]
    subjects.extend(target for held in control.holds.holds.values()
                    for target, _ in held['remaining'] if target.startswith(prefix))
    for entry in ('apply', 'merge'):
        if alignment_only and entry == 'merge':
            # RC restoration needs the actual completed delivery facts while
            # Merge is held. Only the private local proof skips this entry;
            # Apply restrictions and all delivery/Review checks still apply.
            # The public Gate never exposes this switch or grants permission.
            continue
        control.holds.require_clear(line=key[0], entry=entry, subjects=subjects)
    baseline, checked = baseline_context(store, snapshot)
    current = current_engineering(baseline, snapshot, payload, executing=True)
    for revision in {snapshot['metadata_revision'], snapshot['head_revision'], current.content_commit}:
        preserved_inputs(baseline, revision, checked)
    requirements = RequirementIndex(baseline)
    requirements.check_content()
    delivery = DeliveryIndex(requirements, engineering_context=current, map_ref=payload['map_ref'],
                             verification_plan_ref=payload['verification_plan_ref'])
    delivery.check()
    check_feasibility(delivery)
    scope = ReviewScope(requirements, delivery)
    engineering = scope.check_engineering()
    questions = scope.engineering_questions
    questions.check_endpoints(requirements.sources.units, requirements.question_requirement_ids(), candidates=delivery.candidates)
    questions.check_baseline(requirements.records)
    for qid, group in questions.impacts.items():
        if trace['candidate_id'] in group['blocking_for']:
            questions.require_resolved(qid)
    dependencies = implementation_dependencies(delivery, trace['candidate_id'], payload, snapshot['target_revision'])
    archived = check_archived_delivery(delivery, snapshot['trace_ref'], head_revision=snapshot['head_revision'],
                                       verification_inputs=snapshot['verification_inputs'], control=control)
    from .ui_integration import CHECKS, candidate as check_ui, execution_inputs
    ui = check_ui(delivery, snapshot, trace['candidate_id'], action='pre-merge', previous=admitted.get('ui'))
    ui = execution_inputs(delivery, ui, snapshot['verification_inputs'], previous=admitted.get('ui'))
    before, archive_commit = archived['archive']['before_revision'], archived['archive']['archive_revision']
    if not store.ancestor(origin['head_revision'], before):
        raise CheckError('premerge.archive-origin', 'actual Archive does not descend from its claimed pre-archive admission')
    store.read(before, origin['trace_ref']['path'], origin['trace_ref']['sha256'])
    unchanged_since(current, origin['head_revision'], before, trace['candidate_id'], control=control)
    # Behavior repairs require restoring the Change. Newly incorporated target
    # files may be kept when exact, but their current applicability is reviewed.
    if not store.ancestor(snapshot['target_revision'], snapshot['head_revision']):
        raise CheckError('premerge.target-not-included', 'test a real final candidate that includes the current target before merging')
    old_payload = event(store, origin['dispatch_ref'])['payload']
    applicability = None
    if trace['candidate_id'] in assessment_scope(delivery):
        candidate = {**snapshot, 'subject': 'candidate:' + snapshot['version'] + '/' + trace['candidate_id']}
        applicability = retain_approval(delivery, candidate, {'trace': trace}, control)
        planning_ref = applicability['review_ref']
        if store.ref(planning_ref) != store.ref(admitted['planning_review_ref']):
            raise CheckError('premerge.planning-review', 'no-impact assessment does not retain the actual archived planning approval')
    else:
        if (origin['target_revision'] != snapshot['target_revision'] or
                any(store.ref(old_payload[key]) != store.ref(payload[key]) for key in ('map_ref', 'verification_plan_ref', 'engineering_review_ref'))):
            raise CheckError('premerge.reassessment-required', 'target or engineering inputs changed; retain approval only with actual current impact Review')
        planning_ref = admitted['planning_review_ref']
    # A real no-impact alignment updates reviewed map/plan/engineering metadata
    # after Archive. Validate that conclusion first; do not classify arbitrary
    # Requirement files or caller-selected paths as harmless evidence. The final
    # command observation below still binds every one of these tested files.
    from .ui_integration import local_refs
    reviewed_metadata = ([payload[key] for key in ('map_ref', 'verification_plan_ref', 'engineering_review_ref')] + local_refs(ui)) if applicability else []
    unchanged_since(current, archive_commit, snapshot['head_revision'], trace['candidate_id'], control=control,
                    target=snapshot['target_revision'], reviewed_metadata=reviewed_metadata)
    for ref in (planning_ref, snapshot['apply_request_ref']):
        current_ref(store, ref, snapshot['head_revision'])
    final = read_final_checks(current, snapshot['final_checks_ref'], change=trace['change'], candidate_id=trace['candidate_id'],
                             head_revision=snapshot['head_revision'], target_revision=snapshot['target_revision'],
                             archive_revision=archive_commit, control=control)
    # Archive and final CI may run in different clones. Their project identity
    # is the fixed Git/Version/control context above; absolute source_root is
    # only required to agree within each original run and its own CLI outputs.
    conditions, condition_refs = due_integration(delivery, snapshot, trace, archived['delivery'], checkpoints=('integration', 'merge'))
    refs, contextual = merge_review_inputs(snapshot, trace, archived, final, payload, planning_ref, condition_refs, ui=ui)
    review_context = replace(current, content_commit=snapshot['metadata_revision'])
    relative = 'reviews/merge/' + trace['candidate_id'] + '.yaml'
    review = check_review(review_context, relative, 'delivery', (), roles={'engineering-owner'},
                          required_refs=refs, required_context_refs=contextual, required_checks=(*REVIEW_CHECKS, *(CHECKS if ui else ())))
    review_ref = {'commit': snapshot['metadata_revision'], 'path': context.vr + '/' + relative,
                  'sha256': digest(store.read(snapshot['metadata_revision'], context.vr + '/' + relative))}
    current_ref(store, review_ref, snapshot['head_revision'])
    request_ref = snapshot['merge_request_ref']
    if not request_ref['path'].startswith(context.vr + '/trace/evidence/'):
        raise CheckError('premerge.request-path', 'retain merge authority in the existing Version evidence namespace')
    request = validate('merge_request', parse_json(current_ref(store, request_ref, snapshot['head_revision'])))
    expected = {'change': trace['change'], 'version': snapshot['version'], 'delivery_line': snapshot['delivery_line'],
                'baseline_ref': snapshot['baseline_ref'], 'reservation_ref': reservation['reservation_ref'],
                'dispatch_ref': snapshot['dispatch_ref'], 'final_checks_ref': snapshot['final_checks_ref'],
                'candidate_revision': final['tested_revision'], 'target_revision': snapshot['target_revision']}
    if any(request[key] != value for key, value in expected.items()):
        raise CheckError('premerge.request-scope', 'merge request belongs to another candidate, target, reservation or final check')
    selected = request['review_ref']
    if selected['path'] != review_ref['path'] or store.ref(selected) != store.ref(review_ref):
        raise CheckError('premerge.request-review', 'merge request does not bind the actual final Review')
    decision(current, request['decision'], roles={'integrator'})
    references = References(current)
    for value in (snapshot, trace, engineering, review, request):
        references.fixed(value)
    pins = retain_inputs(baseline, [snapshot[k] for k in ('metadata_revision', 'head_revision', 'target_revision')])
    if snapshot['evaluation_mode'] == 'current':
        live = capture(store, extra_roots=['openspec'])
        if live.record['base_revision'] != snapshot['head_revision'] or live.record['changes']:
            raise CheckError('premerge.uncommitted-inputs', 'current final delivery requires the actual clean checked head')
        live.assert_current(store)
    resolve(store, snapshot)
    return {'rule_id': 'G3.pre-merge', 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {'change': trace['change'], 'trace_ref': snapshot['trace_ref'], 'baseline_ref': snapshot['baseline_ref'],
                'reservation_ref': reservation['reservation_ref'], 'alignment_published': published,
                'pre_archive_context_ref': snapshot['pre_archive_context_ref'], 'archive': archived['archive'],
                'delivery': archived['delivery'], 'final_checks': final, 'final_review_ref': review_ref, 'ui': ui,
                'merge_request_ref': request_ref, 'planning_applicability': applicability,
                'dependencies': dependencies, 'integration_conditions': conditions, 'retained_pins': pins,
                'merge_ready': not alignment_only and snapshot['evaluation_mode'] == 'current' and published,
                **({'local_alignment_only': True} if alignment_only else {}),
                'scope': 'current pre-merge conditions only; integrator still serializes final action, rechecks actual refs and records real integration; no merge, slot release or Version Completion'},
            'next_owner': 'integrator'}
