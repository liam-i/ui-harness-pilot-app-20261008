"""G3 pre-archive: actual delivery evidence, Review and current admission.

This check neither archives nor releases the reservation. Pre-merge/integrated
must subsequently prove their own actual inputs and actions.
"""
from dataclasses import replace

from .availability import assessment_scope, provider_contract, provider_evidence
from .context import resolve
from .control import event
from .control_delivery import read_delivery_control
from .core import canonical_bytes, digest, parse_yaml
from .delivery import DeliveryIndex
from .delivery_trace import check_delivery_trace, current_ref
from .dispatch import baseline_snapshot, current_engineering, retain_inputs
from .errors import CheckError
from .execution import check_apply
from .models import validate
from .openspec_artifacts import read_observation
from .requirements import RequirementIndex
from .review_scope import References
from .reviews import check_review
from .worktree import capture

REVIEW_CHECKS = ('implementation-scope', 'behavior-and-tests', 'verification-coverage',
                 'asset-lifecycle', 'integration-conditions', 'pre-archive')


def delivery_review_inputs(snapshot, trace, observation, payload, admission):
    """Compute required references only; never create a decision or Review."""
    refs = [snapshot['trace_ref'], *observation['input_refs'], trace['delivery']['task_ref']]
    for row in trace['delivery']['implementations']:
        refs.extend(row['file_refs'])
    refs.extend(row['verification_ref'] for row in trace['delivery']['verification'])
    contextual = [snapshot['baseline_ref'], snapshot['apply_origin_ref'], snapshot['apply_request_ref'],
                  admission['planning_review_ref'], {k: snapshot['dispatch_ref'][k] for k in ('commit', 'path', 'sha256')},
                  payload['map_ref'], payload['verification_plan_ref'], payload['engineering_review_ref'],
                  *payload['context_refs']]
    for item in snapshot['verification_inputs']:
        contextual.extend(item['identities'].values())
    from .ui_integration import local_refs
    contextual.extend(local_refs(admission.get('ui')))
    unique = lambda values: list({canonical_bytes(ref): ref for ref in values}.values())
    return unique(refs), unique(contextual)


def due_integration(delivery, snapshot, trace, verified, *, checkpoints=('integration',), consumer_contributions=None):
    """Discharge only explicit hard integration edges due before Archive.

    Untagged Version/final obligations do not create implicit execution waits.
    Candidate milestones require the actual integration checker; never
    infer them from a provider's E or an archive directory.
    """
    assessments = assessment_scope(delivery)
    obligations = {row['id']: row for row in delivery.plan['obligations']}
    states, required = [], []
    for eid, edge in delivery.edges.items():
        if edge['consumer'] != trace['candidate_id']:
            continue
        if consumer_contributions is not None and not edge['consumers'] & set(consumer_contributions):
            continue
        entry = edge['entry']
        state = {'edge': eid, 'state': 'not-due'}
        if not edge['active']:
            state['state'] = 'not-applicable'
        elif entry['strength'] == 'soft':
            state['state'] = 'reviewed-soft'
        elif entry['kind'] == 'integration' and entry['checkpoint'] in checkpoints:
            assessment = assessments.get(eid)
            if assessment is None or assessment['conclusion'] != 'available':
                raise CheckError('G3.integration-availability', 'due provider availability is unknown or unsatisfied', refs=[eid])
            if assessment['target_revision'] != snapshot['target_revision']:
                raise CheckError('G3.integration-target', 'due integration assessment does not select the actual target', refs=[eid])
            provider = provider_evidence(delivery, edge, assessment, snapshot['target_revision'])
            contract = provider_contract(delivery, edge, assessment)
            current_ref(delivery.store, contract, snapshot['head_revision'])
            required.extend([assessment['assessment_ref'], contract])
            if 'provider_integration' in assessment:
                required.extend(assessment['provider_integration'].values())
            tagged = {oid: row for oid, row in obligations.items() if eid in row.get('edge_refs', [])}
            if not tagged:
                raise CheckError('G3.integration-plan', 'due condition lacks a declared verification responsibility', refs=[eid])
            executions = {}
            for oid, obligation in tagged.items():
                links = [row for row in verified['verification_links'] if row['obligation_id'] == oid]
                covered, capabilities = {}, set()
                for link in links:
                    ref = link['verification_ref']
                    # check_delivery_trace has already checked these exact E
                    # records, selected cases, current bytes and identities.
                    record = validate('verification_record', parse_yaml(delivery.store.ref(ref)))
                    inputs = {row['path']: row for row in record['input_refs']}
                    if contract['path'] not in inputs or inputs[contract['path']]['sha256'] != contract['sha256']:
                        raise CheckError('G3.integration-input', 'consumer execution omits the fixed provider contract from its actual inputs', refs=[eid, ref])
                    for row in record['coverage']:
                        if not set(row['case_ids']) <= set(link['case_ids']):
                            continue
                        if 'requirement' in row:
                            covered.setdefault(row['contribution'], set()).update(row['acceptance'])
                        else:
                            capabilities.add(row['contribution'])
                    executions[canonical_bytes(ref)] = ref
                needed = ({obligation['capability_ref']: set()} if 'capability_ref' in obligation else
                          {ref: set(obligation['acceptance']) & delivery.allocations[ref]['acceptance']
                           for ref in obligation['contributions']})
                needed.setdefault(edge['provider_ref'], set()).update(edge['provider_acceptance'])
                if any((acs and not acs <= covered.get(ref, set())) or
                       (ref in delivery.capabilities and ref not in capabilities) for ref, acs in needed.items()):
                    raise CheckError('G3.integration-coverage', 'due integration needs actual consumer/provider combination evidence, not provider-only or local partial coverage', refs=[eid, oid])
            state.update(state='satisfied', provider_executions=provider, verification_refs=list(executions.values()))
        states.append(state)
    return states, required


def check_pre_archive(store, snapshot):
    context = resolve(store, snapshot)
    required = ('dispatch_ref', 'trace_ref', 'apply_origin_ref', 'apply_request_ref', 'verification_inputs')
    missing = [key for key in required if key not in snapshot]
    if missing:
        raise CheckError('G3.context-required', 'pre-archive requires the actual execution origin, applicable request, Trace and execution expectations', refs=missing)
    trace = validate('planning_trace', parse_yaml(store.ref(snapshot['trace_ref'])))
    if snapshot['subject'] != 'change:' + trace['change']:
        raise CheckError('G3.change-subject', 'pre-archive subject differs from the actual Trace Change')
    candidate_snapshot = {**snapshot, 'gate': 'G2', 'phase': 'apply',
                          'subject': 'candidate:' + snapshot['version'] + '/' + trace['candidate_id']}
    candidate_snapshot.pop('verification_inputs')
    admitted = check_apply(store, candidate_snapshot)['evidence']
    if admitted['worktree'] is not None and admitted['worktree']['changed_paths']:
        raise CheckError('G3.uncommitted-inputs', 'pre-archive checks committed delivery inputs; preserve and commit authorized work before checking', refs=admitted['worktree']['changed_paths'])
    payload = event(store, snapshot['dispatch_ref'])['payload']
    # Admission above already proves BL/current engineering applicability. Reuse
    # that fixed owner to build the same indexes; do not run a second BL engine.
    baseline_context = replace(resolve(store, baseline_snapshot(store, snapshot)))
    requirements = RequirementIndex(baseline_context)
    requirements.check_content()
    current = current_engineering(baseline_context, candidate_snapshot, payload, executing=True)
    delivery = DeliveryIndex(requirements, engineering_context=current,
        map_ref=payload['map_ref'], verification_plan_ref=payload['verification_plan_ref'])
    delivery.check()
    observed = read_observation(store, trace['observation_ref'], change=trace['change'],
                                actual_revision=snapshot['head_revision'], allow_task_progress=True)
    control = read_delivery_control(store, snapshot['control_revision'], ui_context=snapshot)
    task_prefix = 'task:' + trace['change'] + '/'
    key = (snapshot['delivery_line'], snapshot['version'], trace['candidate_id'])
    reservation = control.reservations.get(key)
    if reservation is None or reservation['reservation_ref'] != admitted['reservation_ref']:
        raise CheckError('G3.reservation', 'Archive must retain the actual original candidate reservation')
    # G2 checked this candidate and its R/AC aliases. Keep that same identity
    # when adding Change/Task restrictions; a valid candidate alignment must
    # not become invisible merely because Archive adds a narrower task query.
    subjects = reservation['inputs']['subjects'] + ['change:' + trace['change']]
    subjects.extend(task_prefix + tid for tid in observed['tasks'])
    # Archive covers the whole Change. A hold on a renamed/deleted old Task
    # remains relevant; removing its display ID cannot clear the restriction.
    subjects.extend(target for row in control.holds.holds.values()
                    for target, entry in row['remaining'] if entry == 'apply' and target.startswith(task_prefix))
    control.holds.require_clear(line=snapshot['delivery_line'], entry='apply', subjects=subjects)
    verified = check_delivery_trace(delivery, trace, observed, head_revision=snapshot['head_revision'],
                                    verification_inputs=snapshot['verification_inputs'], control=control)
    from .ui_integration import CHECKS, execution_inputs
    ui = execution_inputs(delivery, admitted.get('ui'), snapshot['verification_inputs'])
    conditions, condition_refs = due_integration(delivery, snapshot, trace, verified)
    refs, contextual = delivery_review_inputs(snapshot, trace, observed, payload, admitted)
    contextual = list({canonical_bytes(ref): ref for ref in [*contextual, *condition_refs]}.values())
    review_context = replace(current, content_commit=snapshot['metadata_revision'])
    relative = 'reviews/delivery/' + trace['candidate_id'] + '.yaml'
    review = check_review(review_context, relative, 'delivery', (), roles={'engineering-owner'},
        required_refs=refs, required_context_refs=contextual, required_checks=(*REVIEW_CHECKS, *(CHECKS if ui else ())))
    review_path = context.vr + '/' + relative
    review_ref = {'commit': snapshot['metadata_revision'], 'path': review_path,
                  'sha256': digest(store.read(snapshot['metadata_revision'], review_path))}
    current_ref(store, review_ref, snapshot['head_revision'])
    references = References(current)
    for value in (snapshot, trace, review):
        references.fixed(value)
    pins = retain_inputs(baseline_context, [snapshot[key] for key in ('metadata_revision', 'head_revision', 'target_revision')])
    if snapshot['evaluation_mode'] == 'current':
        actual = capture(store, extra_roots=admitted['worktree']['extra_roots'])
        if actual.record['base_revision'] != snapshot['head_revision'] or actual.record['changes']:
            raise CheckError('G3.inputs-changed', 'actual working inputs changed during the pre-archive check')
        actual.assert_current(store)
    resolve(store, snapshot)
    return {'rule_id': 'G3.pre-archive', 'result': 'passed', 'object_refs': [snapshot['subject']],
            'evidence': {'change': trace['change'], 'trace_ref': snapshot['trace_ref'],
                'baseline_ref': snapshot['baseline_ref'], 'reservation_ref': admitted['reservation_ref'],
                'apply_origin_ref': snapshot['apply_origin_ref'], 'apply_request_ref': snapshot['apply_request_ref'],
                'planning_review_ref': admitted['planning_review_ref'], 'delivery_review_ref': review_ref,
                'delivery': verified, 'dependencies': admitted['dependencies'], 'integration_conditions': conditions, 'ui': ui,
                'retained_pins': pins, 'archive_ready': snapshot['evaluation_mode'] == 'current',
                'scope': 'pre-archive conditions only; existing explicit Archive request/entry still required; no archive, merge, slot release or Version Completion'},
            'next_owner': 'engineering-owner'}
