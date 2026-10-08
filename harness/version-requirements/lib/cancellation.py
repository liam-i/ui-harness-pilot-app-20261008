"""Reviewed withdrawal of unintegrated work, never a successful delivery.

The original dispatch owns its terminal slot-release event. This reader checks
fixed Git work and the approved successor scope; it neither deletes files nor
publishes control, and never makes a cancelled candidate a dependency provider.
"""
from .core import canonical_bytes, digest, parse_yaml
from .delivery import DeliveryIndex
from .errors import CheckError
from .models import unique, validate
from .requirement_changes import effective_baseline
from .requirements import RequirementIndex
from .reviews import decision, evidence


def check_cancellation(store, control, row, reservation):
    from .dispatch import retain_inputs
    from .planning_applicability import target_changes

    event, reference = row['event'], row['event_ref']
    payload, original = event['payload'], reservation['inputs']
    proof = payload['cancellation']
    line, version, cid = original['key']
    context, snapshot, _ = effective_baseline(store, proof['context_ref'], version=version, line=line)
    if snapshot['evaluation_mode'] != 'current' or snapshot['control_revision'] != event['based_on_control']:
        raise CheckError('cancellation.context', 'cancellation must bind current effective scope at the exact publication predecessor')
    states = [state for state in control.changes.records.values() if state['latest_ref'] == proof['rc_ref']]
    if (len(states) != 1 or states[0]['status'] not in ('approved', 'aligned') or
            states[0]['to_baseline'] != snapshot['baseline_ref'] or
            (states[0]['target_line'], states[0]['version']) != (line, version)):
        raise CheckError('cancellation.rc', 'cancellation needs the exact published RC and its effective successor baseline')
    state = states[0]
    control.changes.baseline_chain(original['payload']['baseline_ref'], snapshot['baseline_ref'], version=version, line=line)
    requirements = RequirementIndex(context)
    requirements.check_content()
    delivery = DeliveryIndex(requirements)
    delivery.check()
    candidate = delivery.candidates.get(cid)
    if candidate is None or candidate['disposition'] not in ('cancelled', 'superseded'):
        raise CheckError('cancellation.active', 'whole withdrawal cannot release a candidate that still owes active contributions')
    identity = 'candidate:' + version + '/' + cid
    actions = {item['object_id']: item['action'] for item in state['assessment']['payload']['dispositions']}
    if actions.get(identity) not in ('remove', 'replace'):
        raise CheckError('cancellation.disposition', 'reviewed RC impact must explicitly remove or replace this candidate')
    if event['actor'] != context.version['owners']['integrator']:
        raise CheckError('slot-release.actor', 'responsible integrator must confirm cancellation')
    decision(context, payload['confirmation'], roles={'integrator'})
    if event['evidence_ref'] != payload['confirmation']['evidence_ref']:
        raise CheckError('slot-release.confirmation', 'event evidence must bind actual integrator confirmation')
    reviewers = unique(proof['reviews'], 'role', location='cancellation disposition')
    if set(reviewers) != {'engineering-owner', 'qa-owner'}:
        raise CheckError('cancellation.review', 'engineering cleanup and QA residual Review are both required')
    binding = digest(canonical_bytes({k: v for k, v in proof.items() if k not in ('reviews', 'input_digest')}))
    if proof['input_digest'] != binding:
        raise CheckError('cancellation.review-binding', 'disposition Review must bind the complete retained/cleanup/target input')
    for reviewer in reviewers.values():
        decision(context, reviewer, roles={'engineering-owner', 'qa-owner'})
        if binding not in evidence(store, reviewer['evidence_ref']).decode('utf-8', errors='replace'):
            raise CheckError('cancellation.review-binding', 'named disposition evidence must identify this exact input digest')
    evidence(store, proof['delivery_stopped']['evidence_ref'])
    retained, cleaned, target = (proof['retained_revision'], proof['cleanup_revision'], snapshot['target_revision'])
    for revision in (retained, cleaned, target):
        store.commit(revision)
    if not store.ancestor(retained, cleaned) or not store.ancestor(cleaned, reference['commit']):
        raise CheckError('cancellation.history', 'retain work before cleanup and preserve both commits before publishing disposition')
    if not store.ancestor(original['payload']['target_revision'], retained):
        raise CheckError('cancellation.origin', 'retained work must descend from the admitted engineering target')
    subjects = set(original['subjects'])
    name = candidate['change_name']
    if name != original['candidate']['change_name']:
        raise CheckError('cancellation.change', 'withdrawal must preserve the reserved Change identity')
    trace_path = context.vr + '/trace/changes/' + cid + '.yaml'
    if name:
        trace = validate('planning_trace', parse_yaml(store.read(retained, trace_path)))
        if (trace['candidate_id'], trace['version'], trace['delivery_line'], trace['change'], trace['dispatch_ref']) != (
                cid, version, line, name, reservation['event_ref']):
            raise CheckError('cancellation.trace', 'retained Trace must locate the original reservation and Change')
        # Locator is the actual observed OpenSpec root, not a fixed default path.
        from .core import parse_json
        from .openspec_artifacts import read_observation
        captured = validate('openspec_observation', parse_json(evidence(store, trace['observation_ref'])))['captured_revision']
        observed = read_observation(store, trace['observation_ref'], change=name,
                                    actual_revision=captured, allow_task_progress=True)
        active = observed['change_root'].rstrip('/') + '/'
        old_files = {path for path in store.tree(retained) if path.startswith(active)}
        archived = {path for path in store.tree(retained) if '/archive/' in path and
                    path.split('/archive/', 1)[1].split('/', 1)[0].endswith('-' + name)}
        if not old_files and not archived:
            raise CheckError('cancellation.artifacts', 'retain the actual active or already archived planning before withdrawal')
        if any(path.startswith(active) for path in store.tree(cleaned)):
            raise CheckError('cancellation.cleanup', 'cancelled planning remains in the active collection')
        # Existing archive is retained history. Withdrawal may not fabricate a
        # new success archive or edit an already retained archived delivery.
        later = {path for path in store.tree(cleaned) if '/archive/' in path and
                 path.split('/archive/', 1)[1].split('/', 1)[0].endswith('-' + name)}
        if later != archived or any(store.tree(cleaned)[path] != store.tree(retained)[path] for path in archived):
            raise CheckError('cancellation.false-archive', 'cancellation must not create or rewrite a successful archive')
        subjects.add('change:' + name)
    acknowledgements = {canonical_bytes(value['event_ref']): value for value in control.holds.acknowledgements}
    for stop in proof['stop_refs']:
        acknowledged = acknowledgements.get(canonical_bytes(stop))
        if acknowledged is None:
            raise CheckError('cancellation.stop', 'actual stopping point must already be published')
        stopped = acknowledged['event']['payload']
        if (acknowledged['event']['target_line'] != line or stopped['actual_revision'] != retained or
                stopped['target'] not in subjects or stopped['entry'] not in ('propose', 'apply')):
            raise CheckError('cancellation.stop', 'stop confirmation must identify this exact retained work and candidate')
        if not any(held['path'] == state['proposal_ref']['path'] for held in stopped['hold_refs']):
            raise CheckError('cancellation.stop', 'stop must acknowledge the disposing RC restriction')
    if not control.holds.blockers(line=line, entry='merge', subjects=sorted(subjects)):
        raise CheckError('cancellation.merge-stop', 'keep delivery stopped while releasing cancelled capacity')
    before = original['payload']['target_revision']
    changes = target_changes(store, before, retained)
    old_tree, target_tree, clean_tree = store.tree(before), store.tree(target), store.tree(cleaned)
    engineering = [item['path'] for item in changes if not (name and (
        item['path'].startswith(active) or item['path'] in archived))]
    # An ancestry test misses squash/cherry-pick. Require exact target bytes on
    # every touched engineering path as well, and retain a named semantic Review
    # for renamed/copied behavior and external effects which Git cannot infer.
    if any(target_tree.get(path) != old_tree.get(path) for path in engineering):
        raise CheckError('cancellation.target-impact', 'target contains overlapping engineering changes; establish integrated retirement or re-evaluate the actual scope before cancellation')
    # Check the whole cleanup diff too: renaming/copying unfinished behavior
    # to a path introduced only during cleanup must not evade the old worklist.
    residual = [item['path'] for item in target_changes(store, before, cleaned)
                if not (name and item['path'] in archived)]
    if residual:
        raise CheckError('cancellation.residual', 'withdrawn engineering changes remain in the cleanup commit')
    if name and any(path.startswith(active) or path in archived for path in target_tree):
        raise CheckError('cancellation.target-impact', 'target already contains this delivery; use reviewed retirement')
    # Pin the work, including incomplete code/resources, before branch cleanup.
    retain_inputs(context, [retained, cleaned, target, reference['commit']])
    return {'outcome': 'cancelled', 'candidate_id': cid, 'rc_ref': proof['rc_ref'],
            'baseline_ref': snapshot['baseline_ref'], 'context_ref': proof['context_ref'],
            'retained_revision': retained, 'cleanup_revision': cleaned, 'engineering_paths': engineering,
            'subjects': sorted(subjects), 'input_digest': binding, 'delivered': False}
