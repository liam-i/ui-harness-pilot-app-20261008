"""Published reservations and holds, derived from the one control log.

This consumer checks fixed admission inputs and line-wide capacity. It is not
G2: baseline effectiveness, current dependency evidence, retained publication
and engineering authorization applicability remain phase checks. Slot release
replays the original integrated Gate; only published releases remove capacity.
"""
from copy import deepcopy
from types import SimpleNamespace

from .control import check_source_append, event as read_event, published_events
from .control_holds import HoldState, KINDS as HOLD_KINDS
from .core import parse_yaml
from .errors import CheckError, InputError
from .models import unique, validate
from .reviews import decision, evidence
from .requirement_changes import ChangeRequests, KINDS as RC_KINDS

KINDS = {'dispatch': 'dispatch_payload', 'execution-alignment': 'alignment_payload'}


def admission_inputs(store, row):
    """Resolve the fixed map/review and original BL owner, without granting G2."""
    event, reference = row['event'], row['event_ref']
    kind = event['kind']
    if kind not in KINDS:
        raise InputError('control.kind-unsupported', 'unsupported admission event', refs=[reference])
    payload = validate(KINDS[kind], event['payload'], location=reference['path'])
    version, line = event['version'], event['target_line']
    prefix = 'requirements/versions/' + version + '/'
    cid = payload['candidate_id']
    if reference['path'] != prefix + 'dispatch/' + cid + '.yaml':
        raise CheckError('dispatch.path', 'candidate event must remain in its original dispatch record', refs=[reference])
    baseline = validate('baseline', parse_yaml(store.ref(payload['baseline_ref'])))
    if baseline['version'] != version or payload['baseline_ref']['path'] != prefix + 'baselines/' + baseline['id'] + '.yaml':
        raise CheckError('dispatch.baseline', 'dispatch requires the exact Version baseline identity')
    owner = validate('version', store.yaml(baseline['content_commit'], prefix + 'version.yaml'))
    if (owner['version'], owner['delivery_line']) != (version, line):
        raise CheckError('dispatch.line', 'dispatch cannot move the baseline to another delivery line')
    if event['actor'] != owner['owners']['integrator']:
        raise CheckError('dispatch.actor', 'control admission must identify the responsible integrator')
    store.commit(payload['target_revision'])
    if not store.ancestor(owner['starting_commit'], payload['target_revision']):
        raise CheckError('dispatch.target', 'engineering target does not descend from the declared line start')
    context = SimpleNamespace(store=store, version=owner)
    for key in ('release_decision', 'propose_request'):
        decision(context, payload[key], roles={'engineering-owner'})
    if event['evidence_ref'] != payload['release_decision']['evidence_ref']:
        raise CheckError('dispatch.decision', 'event evidence must bind the actual release decision')
    for ref in payload['context_refs']:
        evidence(store, ref)
    values = {}
    for key, path, model in (('map_ref', 'delivery-map.yaml', 'delivery_map'),
                             ('verification_plan_ref', 'verification-plan.yaml', 'verification_plan'),
                             ('engineering_review_ref', 'reviews/engineering.yaml', 'review')):
        ref = payload[key]
        if ref['path'] != prefix + path:
            raise CheckError('dispatch.input-path', 'dispatch input belongs to another Version/role', refs=[ref])
        values[key] = validate(model, parse_yaml(store.ref(ref)), location=ref['path'])
    mapping, plan, review = (values[k] for k in ('map_ref', 'verification_plan_ref', 'engineering_review_ref'))
    if mapping['version'] != version or plan['version'] != version or mapping['baseline'] != baseline['id']:
        raise CheckError('dispatch.input-owner', 'map/plan must select the original approved baseline scope')
    if review['phase'] != 'engineering' or review['outcome'] != 'passed' or 'engineering' not in review:
        raise CheckError('dispatch.review', 'a passed engineering Review with explicit capacity is required')
    if review['role'] != 'engineering-owner' or review['actor'] != owner['owners']['engineering-owner']:
        raise CheckError('dispatch.review-owner', 'engineering Review has the wrong responsible actor')
    evidence(store, review['evidence_ref'])
    bound = {(item.get('commit', payload['engineering_review_ref']['commit']), item['path']): item['sha256']
             for item in review['reviewed_inputs']}
    for key in ('map_ref', 'verification_plan_ref'):
        ref = payload[key]
        if bound.get((ref['commit'], ref['path'])) != ref['sha256']:
            raise CheckError('dispatch.review-binding', 'capacity Review must bind the selected map and verification plan', refs=[ref])
    candidates = unique(mapping['candidates'], 'candidate_id', location=payload['map_ref']['path'])
    candidate = candidates.get(cid)
    if candidate is None or candidate['disposition'] != 'planned':
        raise CheckError('dispatch.candidate', 'admission must select a present active candidate', refs=[cid])
    engineering = review['engineering']
    limits = (engineering['wip_limit'], engineering['planning_limit'])
    if limits[1] > 1:
        raise CheckError('dispatch.planning-limit', 'at most one additional planning-only reservation is supported')
    if limits[0] > 1 or limits[1] > 0:
        if not engineering['parallel_approval_ref']:
            raise CheckError('dispatch.capacity-approval', 'non-default line capacity requires actual approval')
        evidence(store, engineering['parallel_approval_ref'])
    exception = payload['planning_exception']
    if payload['mode'] == 'planning-only':
        if exception is None:
            raise CheckError('dispatch.planning-exception', 'early planning requires a bounded explicit exception')
        decision(context, exception['approval'], roles={'engineering-owner'})
        for ref in exception['stable_contract_refs']:
            evidence(store, ref)
        edges = {item['id'] for item in candidate['predecessor_edges']
                 if item['kind'] == 'implementation' and item['strength'] == 'hard'}
        if not set(exception['unmet_implementation_edges']) <= edges:
            raise CheckError('dispatch.planning-edge', 'planning exception names absent or non-hard implementation edges')
    elif exception is not None:
        raise CheckError('dispatch.planning-exception', 'execution cannot carry unresolved planning-only conditions')
    subjects = {'candidate:' + version + '/' + cid, 'version:' + version}
    for allocation in candidate['allocation']:
        subjects.add('requirement:' + version + '/' + allocation['requirement'])
        for ac in allocation['acceptance']:
            subjects.add('scope:' + version + '/' + allocation['requirement'] + '/' + ac)
    if candidate['change_name']:
        subjects.add('change:' + candidate['change_name'])
    return {'payload': payload, 'candidate': candidate, 'limits': limits,
            'subjects': sorted(subjects), 'key': (line, version, cid)}


class DeliveryControl:
    def __init__(self, revision, *, ui_context=None):
        from .ui_receipts import locations
        self.ui_context = locations(ui_context)
        self.revision = revision
        self.changes = ChangeRequests(ui_context=self.ui_context)
        self.holds = HoldState(revision, entry_guard=self.changes.require_entry_ready)
        self.reservations = {}
        self.completed = {}
        self.cancelled = {}
        self.event_refs, self.record_refs = {}, {}

    def capacity(self, key, candidate, limits, mode='execution'):
        """Check the same line-wide capacity for admission or an observation.

        This neither reserves a slot nor resolves semantic conflicts not named
        by the reviewed shared_resources inventory.
        """
        others = {identity: value for identity, value in self.reservations.items()
                  if identity[0] == key[0] and identity != key}
        counts = {name: sum(row['inputs']['payload']['mode'] == name for row in others.values())
                  for name in ('execution', 'planning-only')}
        counts[mode] += 1
        if counts['execution'] > limits[0] or counts['planning-only'] > limits[1]:
            raise CheckError('dispatch.capacity', 'published line-wide reservations exceed the reviewed allowance', refs=[counts])
        resources = set(candidate['shared_resources'])
        for value in others.values():
            overlap = resources & set(value['inputs']['candidate']['shared_resources'])
            if overlap:
                raise CheckError('dispatch.shared-resource', 'independent readiness does not allow conflicting shared writes/contracts', refs=sorted(overlap))
        return {'counts_including_candidate': counts, 'limits': dict(zip(('execution', 'planning-only'), limits))}

    def admission(self, store, row, *, alignment_only=False):
        """Pure preview. No mutation, publication or Propose permission."""
        event = row['event']
        inputs = admission_inputs(store, row)
        payload, key = inputs['payload'], inputs['key']
        if key in self.completed or key in self.cancelled:
            raise CheckError('dispatch.completed-reservation', 'completed candidate retains its original reservation history and cannot acquire another slot')
        previous = self.reservations.get(key)
        if event['kind'] == 'dispatch':
            if previous is not None:
                raise CheckError('dispatch.duplicate-reservation', 'candidate already has a reservation; resume its exact published event')
        else:
            if previous is None or payload['previous_dispatch_ref'] != previous['event_ref']:
                raise CheckError('dispatch.alignment-reference', 'alignment must select the exact latest event of this reservation')
            if previous['inputs']['payload']['mode'] == 'execution' and payload['mode'] != 'execution':
                raise CheckError('dispatch.mode-reversal', 'execution cannot be demoted to evade line capacity')
            if previous['inputs']['payload']['baseline_ref'] != payload['baseline_ref']:
                self.changes.baseline_chain(previous['inputs']['payload']['baseline_ref'], payload['baseline_ref'],
                                            version=key[1], line=key[0])
            original_name = previous['inputs']['candidate']['change_name']
            if original_name is not None and original_name != inputs['candidate']['change_name']:
                raise CheckError('dispatch.change-identity', 'alignment must retain the actual Change of the original reservation')
            evidence(store, payload['assessment_ref'])
        if event['kind'] == 'dispatch' and not alignment_only:
            self.holds.require_clear(line=key[0], entry='propose', subjects=inputs['subjects'])
        # Alignment may record corrective facts while held. Its publication
        # never releases a restriction or authorizes the blocked action.
        self.capacity(key, inputs['candidate'], inputs['limits'], payload['mode'])
        return {'inputs': inputs, 'event_ref': row['event_ref'],
                'reservation_ref': previous['reservation_ref'] if previous else row['event_ref']}

    def release(self, store, row):
        """Validate completed or cancelled disposition before releasing capacity."""
        from .context import resolve
        from .integrated_receipt import read_integrated_receipt
        from .core import parse_json

        event, reference = row['event'], row['event_ref']
        payload = validate('slot_release_payload', event['payload'], location=reference['path'])
        key = (event['target_line'], event['version'], payload['candidate_id'])
        previous = self.reservations.get(key)
        if previous is None:
            raise CheckError('slot-release.reservation', 'slot release requires the still active original reservation; resume an already published event by its exact reference')
        if (reference['path'] != previous['event_ref']['path'] or
                payload['reservation_ref'] != previous['reservation_ref'] or
                payload['dispatch_ref'] != previous['event_ref'] or
                payload['baseline_ref'] != previous['inputs']['payload']['baseline_ref']):
            raise CheckError('slot-release.origin', 'release must append to the exact original reservation, latest alignment and baseline')
        if payload.get('outcome') == 'cancelled':
            from .cancellation import check_cancellation
            # Historical disposition must not require a pin for its caller's
            # later control reads. Keep this proof's complete closure separate,
            # then merge it back into the enclosing audit like integrated G3.
            with store.input_scope():
                receipt = check_cancellation(store, self, row, previous)
            return {**previous, 'release_ref': reference, 'receipt': receipt, 'outcome': 'cancelled'}
        origin = validate('snapshot', parse_json(evidence(store, payload['integrated_context_ref'])))
        if origin['control_revision'] != event['based_on_control']:
            raise CheckError('slot-release.stale-control', 'release confirmation must bind an integrated check on its exact publication predecessor')
        from .ui_receipts import historical
        context = resolve(store, historical(origin, self.ui_context))
        if (context.version['version'], context.version['delivery_line']) != (key[1], key[0]):
            raise CheckError('slot-release.line', 'release cannot consume another Version or delivery line')
        if event['actor'] != context.version['owners']['integrator']:
            raise CheckError('slot-release.actor', 'responsible integrator must confirm the actual completed integration')
        decision(context, payload['confirmation'], roles={'integrator'})
        if event['evidence_ref'] != payload['confirmation']['evidence_ref']:
            raise CheckError('slot-release.confirmation', 'event evidence must identify the actual integrator confirmation')
        for name in ('integrated_context_ref', 'integrated_result_ref'):
            ref = payload[name]
            if not store.ancestor(ref['commit'], reference['commit']):
                raise CheckError('slot-release.late-proof', 'retain integrated input and result before appending release')
            store.read(reference['commit'], ref['path'], ref['sha256'])
        receipt = read_integrated_receipt(context, payload['integrated_context_ref'], payload['integrated_result_ref'])
        proof = receipt['evidence']
        if (proof['reservation_ref'] != payload['reservation_ref'] or
                origin.get('dispatch_ref') != payload['dispatch_ref'] or
                origin['baseline_ref'] != payload['baseline_ref'] or
                origin['trace_ref']['path'] != context.vr + '/trace/changes/' + key[2] + '.yaml'):
            raise CheckError('slot-release.proof', 'integrated proof must select this same baseline, candidate and latest original reservation')
        return {**previous, 'release_ref': reference, 'receipt': receipt}

    def preview(self, store, reference, *, alignment_only=False):
        row = {'event_ref': reference, 'event': read_event(store, reference)}
        previous = self.event_refs.get(reference['event_id'])
        if previous is not None and previous != reference:
            raise CheckError('control.duplicate-id', 'event identity already selects different published bytes', refs=[reference])
        check_source_append(store, self.record_refs.get(reference['path']), reference)
        if row['event'].get('based_on_control') != self.revision:
            raise CheckError('control.stale-decision', 'admission preview must use this exact control predecessor')
        if row['event']['kind'] in RC_KINDS:
            _, state = self.changes.evaluate(store, row)
            return {'scope': 'RC transition preview only; no publication or engineering permission',
                    'control_revision': self.revision, 'event_ref': reference, 'published': False,
                    'rc_status': state['status'], 'to_baseline': state['to_baseline']}
        if row['event']['kind'] == 'slot-release':
            self.release(store, row)
            return {'scope': 'verified slot-release preview; reservation remains occupied until publication',
                    'control_revision': self.revision, 'event_ref': reference, 'published': False}
        result = self.admission(store, row, alignment_only=alignment_only)
        return {'scope': 'admission structure/capacity only; not G2 or publication',
                'control_revision': self.revision, 'candidate': result['inputs']['key'][1:],
                'mode': result['inputs']['payload']['mode'], 'event_ref': reference}

    def consume(self, store, row):
        kind = row['event']['kind']
        if kind in HOLD_KINDS:
            self.changes.guard_hold(row)
            self.holds.consume(store, row)
        elif kind in RC_KINDS:
            self.changes.consume(store, row)
        elif kind in KINDS:
            admission = self.admission(store, row)
            self.reservations[admission['inputs']['key']] = admission
        elif kind == 'slot-release':
            completed = self.release(store, row)
            key = completed['inputs']['key']
            target = self.cancelled if completed.get('outcome') == 'cancelled' else self.completed
            target[key] = completed
            del self.reservations[key]
        else:
            raise InputError('control.kind-unsupported', 'unimplemented control event cannot be treated as an empty restriction/reservation', refs=[row['event_ref']])
        reference = row['event_ref']
        self.event_refs[reference['event_id']] = reference
        self.record_refs[reference['path']] = reference


def read_delivery_control(store, revision, *, ui_context=None):
    """Replay each exact historical control commit once per reader invocation.

    RC alignment recursively checks earlier admissions on the same history.
    Reuse only fully checked fixed inputs, with independent projections and
    their complete read closure. Current Gates still observe the live remote
    before/after the check; no result or permission is persisted here.
    """
    from .core import canonical_bytes
    from .ui_receipts import locations
    key = canonical_bytes([revision, locations(ui_context)])
    if key in store._delivery_controls:
        result, inputs = store._delivery_controls[key]
        store.inputs.update(inputs)
        return deepcopy(result)
    with store.input_scope():
        result = DeliveryControl(revision, ui_context=ui_context)
        for row in published_events(store, revision):
            result.consume(store, row)
        inputs = dict(store.inputs)
    store._delivery_controls[key] = (deepcopy(result), inputs)
    return result
