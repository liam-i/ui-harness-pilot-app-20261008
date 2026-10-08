"""Read actual same-line delivery after Merge, without publishing its completion.

Original dispatch and admission remain history. Current engineering inputs and
Review assess the actual target; they are not a new execution authorization.
"""
from dataclasses import replace

from .archive import archived_projection, markdown_identity
from .context import resolve
from .control import event as read_event
from .control_delivery import read_delivery_control
from .core import canonical_bytes, digest, parse_json, parse_yaml
from .delivery import DeliveryIndex
from .delivery_trace import check_delivery_trace, current_ref
from .dispatch import baseline_context, current_engineering, preserved_inputs, retain_inputs
from .errors import CheckError
from .feasibility import check_feasibility
from .final_checks import engineering_paths, read_final_checks, unchanged_since
from .integration import read_integration
from .models import validate
from .planning import check_unique_change
from .prearchive import due_integration
from .requirements import RequirementIndex
from .review_scope import References, ReviewScope
from .reviews import check_review
from .worktree import capture

REVIEW_CHECKS = ('actual-target', 'contribution-coverage', 'evidence-applicability',
                 'merge-impact', 'asset-lifecycle', 'integration-conditions')


def integration_review_inputs(snapshot, trace, original, projection, *, control=None, condition_refs=(), final=None, ui=None):
    """Bind actual target files and unchanged historical authorization separately."""
    # The caller supplies the same already resolved context through projection;
    # no new copy of the original engineering plan is created.
    context = projection['context']
    store, target = context.store, snapshot['target_revision']
    refs = [snapshot['trace_ref'], original['observation_ref'], *projection['observation']['input_refs'],
            *projection['asset_refs']]
    refs.extend(ref for row in trace['delivery']['implementations'] for ref in row['file_refs'])
    refs.extend(row['verification_ref'] for row in trace['delivery']['verification'])
    final = final or original['original_admission']['final_checks']
    refs.extend(final['evidence_refs'] + final['input_refs'])
    paths = engineering_paths(context, target, trace['candidate_id'], control)
    for path in sorted(paths):
        refs.append({'commit': target, 'path': path, 'sha256': digest(store.read(target, path))})
    # Main Specs can evolve on the target; Archive remains immutable. Inspect
    # links at the actual target rather than copying pre-merge locators.
    for item in original['original_admission']['archive']['main_spec_refs']:
        path = item['current_ref']['path']
        _, links = markdown_identity(store, target, path)
        refs.extend(links)
        refs.append(item['archived_ref'])
    contextual = [snapshot['baseline_ref'], original['pre_merge_context_ref'], original['pre_merge_result_ref'],
                  original['operation_ref'], original['confirmation']['evidence_ref'],
                  {k: snapshot['dispatch_ref'][k] for k in ('commit', 'path', 'sha256')},
                  *snapshot['engineering_inputs'].values(), *condition_refs]
    contextual.extend(ref for item in snapshot['verification_inputs'] for ref in item['identities'].values())
    from .ui_integration import local_refs
    contextual.extend(local_refs(ui))
    unique = lambda values: list({canonical_bytes(ref): ref for ref in values}.values())
    return unique(refs), unique(contextual)


def check_integrated(store, snapshot):
    context = resolve(store, snapshot)
    required = ('dispatch_ref', 'trace_ref', 'verification_inputs', 'engineering_inputs')
    missing = [key for key in required if key not in snapshot]
    if missing or not snapshot['control_revision']:
        raise CheckError('integrated.context-required', 'integrated needs original dispatch, current Trace, engineering Review and actual execution expectations', refs=missing)
    head, target = snapshot['head_revision'], snapshot['target_revision']
    trace = validate('planning_trace', parse_yaml(current_ref(store, snapshot['trace_ref'], head)))
    cid = trace['candidate_id']
    if (snapshot['trace_ref']['path'] != context.vr + '/trace/changes/' + cid + '.yaml' or
            snapshot['subject'] != 'change:' + trace['change']):
        raise CheckError('integrated.trace', 'continue this logical Change and its single candidate Trace')
    check_unique_change(store, snapshot['trace_ref'], trace, snapshot['metadata_revision'])
    reference = trace.get('delivery', {}).get('integration_observation_ref')
    if reference is None:
        raise CheckError('integrated.observation-required', 'actual integration observation is required; Archive is not Merge')
    current_ref(store, reference, head)
    original = read_integration(context, reference, target_revision=target)
    if ((original['candidate_id'], original['change'], original['baseline_ref'], original['dispatch_ref']) !=
            (cid, trace['change'], snapshot['baseline_ref'], snapshot['dispatch_ref']) or
            trace['baseline_ref'] != snapshot['baseline_ref'] or trace['dispatch_ref'] != snapshot['dispatch_ref']):
        raise CheckError('integrated.origin', 'integration must continue the same baseline, candidate and actual source dispatch')
    source_snapshot = parse_json(store.ref(original['pre_merge_context_ref']))
    for key in ('apply_origin_ref', 'apply_request_ref'):
        if key in snapshot and snapshot[key] != source_snapshot[key]:
            raise CheckError('integrated.authority', 'optional implementation authority must remain the original admitted authority')
    if not store.ancestor(original['control_revision'], snapshot['control_revision']):
        raise CheckError('integrated.control-history', 'current control must retain the original admission history')
    if not store.ancestor(target, head):
        raise CheckError('integrated.target-history', 'save current integration metadata on the actual target history')
    control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
    key = (snapshot['delivery_line'], snapshot['version'], cid)
    reservation = control.reservations.get(key) or control.completed.get(key)
    if (reservation is None or reservation['reservation_ref'] != original['reservation_ref'] or
            reservation['event_ref'] != snapshot['dispatch_ref'] or
            control.event_refs.get(snapshot['dispatch_ref']['event_id']) != snapshot['dispatch_ref']):
        raise CheckError('integrated.reservation', 'actual integrated delivery must retain its original confirmed reservation or published completion history')
    baseline, checked = baseline_context(store, snapshot)
    inputs = snapshot['engineering_inputs']
    if inputs['engineering_review_ref']['path'] != context.vr + '/reviews/engineering.yaml':
        raise CheckError('integrated.engineering-owner', 'reuse the existing Version engineering Review owner')
    current = current_engineering(baseline, snapshot, inputs, executing=True)
    for revision in {snapshot['metadata_revision'], head, target, current.content_commit}:
        preserved_inputs(baseline, revision, checked)
    requirements = RequirementIndex(baseline)
    requirements.check_content()
    delivery = DeliveryIndex(requirements, engineering_context=current, map_ref=inputs['map_ref'],
                             verification_plan_ref=inputs['verification_plan_ref'])
    if delivery.map['baseline'] != baseline.baseline['id']:
        raise CheckError('integrated.baseline', 'current engineering map must retain the effective baseline scope')
    delivery.check()
    check_feasibility(delivery)
    scope = ReviewScope(requirements, delivery)
    engineering = scope.check_engineering()
    questions = scope.engineering_questions
    questions.check_endpoints(requirements.sources.units, requirements.question_requirement_ids(), candidates=delivery.candidates)
    questions.check_baseline(requirements.records)
    for qid, group in questions.impacts.items():
        if cid in group['blocking_for']:
            questions.require_resolved(qid)
    archived = original['original_admission']['archive']
    if trace['delivery'].get('archive_observation_ref') != archived['observation_ref']:
        raise CheckError('integrated.archive-origin', 'retain the actual source Archive observation')
    projection = archived_projection(delivery, trace, archived, head_revision=head,
                                     trace_ref=snapshot['trace_ref'], control=control)
    projection['context'] = current
    from .ui_integration import CHECKS, candidate as check_ui, execution_inputs, local_refs
    previous_ui = original['original_admission'].get('ui')
    ui = check_ui(delivery, snapshot, cid, action='integrated', previous=previous_ui)
    ui = execution_inputs(delivery, ui, snapshot['verification_inputs'], previous=previous_ui)
    reviewed_inputs = {**inputs, **{'ui_' + str(i): ref for i, ref in enumerate(local_refs(ui))}}
    # Qualified fixed UI records join the original reviewed metadata set.
    # Original E readers still protect every explicitly executed file; a UI
    # record can never exempt source or relabel an earlier tested revision.
    unchanged_since(current, target, head, cid, control=control, reviewed_metadata=reviewed_inputs.values())
    verified = check_delivery_trace(delivery, projection['trace'], projection['observation'], head_revision=head,
        verification_inputs=snapshot['verification_inputs'], control=control,
        integration={**original, 'engineering_inputs': reviewed_inputs})
    source = original['facts']['source_revision']
    left, right = store.tree(source), store.tree(target)
    reviewed_paths = {ref['path'] for ref in inputs.values()}
    changed = [path for path in sorted(engineering_paths(current, source, cid, control) |
                                       engineering_paths(current, target, cid, control))
               if path not in reviewed_paths and left.get(path) != right.get(path)]
    final_ref = snapshot.get('integration_checks_ref')
    if changed and final_ref is None:
        raise CheckError('integrated.final-checks-required', 'actual engineering changes require applicable final project, entry-policy and OpenSpec checks; a new E alone is insufficient', refs=changed)
    final = original['original_admission']['final_checks']
    basis = 'original-source-content-preserved'
    if final_ref is not None:
        final = read_final_checks(current, final_ref, change=trace['change'], candidate_id=cid, head_revision=head,
            target_revision=target, archive_revision=original['facts']['merged_revision'], control=control)
        basis = 'actual-target-execution'
    conditions, condition_refs = due_integration(delivery, snapshot, trace, verified, checkpoints=('integration', 'merge'))
    refs, contextual = integration_review_inputs(snapshot, trace, original, projection, control=control, condition_refs=condition_refs, final=final, ui=ui)
    relative = 'reviews/integration/' + cid + '.yaml'
    review = check_review(replace(current, content_commit=snapshot['metadata_revision']), relative, 'delivery', (),
        roles={'engineering-owner'}, required_refs=refs, required_context_refs=contextual, required_checks=(*REVIEW_CHECKS, *(CHECKS if ui else ())))
    review_ref = {'commit': snapshot['metadata_revision'], 'path': context.vr + '/' + relative,
                  'sha256': digest(store.read(snapshot['metadata_revision'], context.vr + '/' + relative))}
    current_ref(store, review_ref, head)
    # A hold raised after Merge remains published. Reporting completed facts
    # neither cancels it nor authorizes further Apply/Merge work.
    prefix = 'task:' + trace['change'] + '/'
    subjects = reservation['inputs']['subjects'] + ['change:' + trace['change']]
    subjects.extend(subject for held in control.holds.holds.values() for subject, _ in held['remaining'] if subject.startswith(prefix))
    holds = [row for entry in ('propose', 'apply', 'merge')
             for row in control.holds.blockers(line=key[0], entry=entry, subjects=subjects)]
    references = References(current)
    for value in (snapshot, trace, engineering, review):
        references.fixed(value)
    release = None
    release_ref = snapshot.get('slot_release_ref')
    if release_ref is not None:
        row = {'event_ref': release_ref, 'event': read_event(store, release_ref)}
        if row['event']['kind'] != 'slot-release':
            raise CheckError('slot-release.kind', 'integration confirmation must select a slot-release event')
        if (row['event']['version'], row['event']['target_line'], row['event']['payload'].get('candidate_id')) != (key[1], key[0], key[2]):
            raise CheckError('slot-release.subject', 'release confirmation must select this integrated candidate')
        published = control.event_refs.get(release_ref['event_id']) == release_ref
        if published:
            completed = control.completed.get(key)
            if completed is None or completed['release_ref'] != release_ref:
                raise CheckError('slot-release.stale-event', 'confirm this exact published completion')
        else:
            control.preview(store, release_ref)
            completed = control.release(store, row)
            if completed['receipt']['snapshot']['target_revision'] != target:
                raise CheckError('slot-release.stale-target', 'unpublished release must use the actual current target integration proof')
        if not store.ancestor(release_ref['commit'], head):
            raise CheckError('slot-release.metadata', 'current metadata head must retain the saved release event')
        current_ref(store, {k: release_ref[k] for k in ('commit', 'path', 'sha256')}, head)
        references.fixed(row['event'])
        release = {'event_ref': release_ref, 'published': published,
            'reservation_occupied': key in control.reservations,
            'publication_ready': not published and snapshot['evaluation_mode'] == 'current',
            'scope': 'capacity confirmation only; no hold clearance, dependency readiness, publication or next action authority'}
    pins = retain_inputs(baseline, [snapshot[k] for k in ('metadata_revision', 'head_revision', 'target_revision')])
    if snapshot['evaluation_mode'] == 'current':
        live = capture(store, extra_roots=['openspec'])
        if live.record['base_revision'] != head or live.record['changes']:
            raise CheckError('integrated.uncommitted-inputs', 'current integration check needs its actual clean metadata head')
        live.assert_current(store)
    resolve(store, snapshot)
    result = {'rule_id': 'G3.integrated', 'result': 'passed', 'object_refs': [snapshot['subject']],
        'evidence': {'change': trace['change'], 'trace_ref': snapshot['trace_ref'], 'baseline_ref': snapshot['baseline_ref'],
            'reservation_ref': original['reservation_ref'], 'integration_observation_ref': reference,
            'facts': original['facts'], 'engineering_inputs': inputs, 'integration_review_ref': review_ref,
            'delivery': verified, 'final_checks': final, 'final_checks_basis': basis, 'ui': ui,
            'integration_conditions': conditions, 'current_holds': holds,
            'integrated_acceptance': verified['local_acceptance'], 'integrated_capabilities': verified['local_capabilities'],
            'retained_pins': pins, 'current_integration': snapshot['evaluation_mode'] == 'current',
            'scope': 'actual same-line candidate contributions and reviewed evidence; no publication, slot release, further action authority or Version Completion'},
        'next_owner': 'integrator'}
    if release is not None:
        result['evidence']['slot_release'] = release
    return result
