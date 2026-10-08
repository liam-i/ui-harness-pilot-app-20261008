"""RC history in its original append-only record, replayed without side effects.

The shared control branch publishes references only. A generated impact report
is checked against both actual graphs; it is not an approval or a second source
of product state. Approved C and effective BL are deliberately separate steps.
Local alignment is distinct from lifting a hold or passing an execution Gate.
"""
from dataclasses import replace
from types import SimpleNamespace

from .baselines import check_baseline, published_chain
from .context import resolve
from .control_holds import check_target
from .core import canonical_bytes, digest, parse_json, parse_yaml
from .errors import CheckError, InputError
from .impact import analyze
from .models import unique, validate
from .reviews import decision, evidence

KINDS = {'rc-proposed': 'rc_proposal_payload', 'rc-impact-assessed': 'rc_impact_payload',
         'rc-decided': 'rc_decision_payload', 'rc-baselined': 'rc_baseline_payload',
         'rc-aligned': 'rc_alignment_payload', 'rc-restored': 'rc_alignment_payload',
         'rc-verified': 'rc_verification_payload'}
ROLES = {'product-owner', 'engineering-owner', 'qa-owner'}


def withdrawn_subjects(history, current, records, dispositions, version):
    """Old aliases are disposition duties, never current delivery coverage.

    Moving an obligation to another candidate is not a product withdrawal.
    Only explicitly removed/replaced R/AC absent from the effective scope may
    remain accountable to their original shared Change.
    """
    allowed = set(current)
    for subject in set(history) - allowed:
        if dispositions.get(subject) not in ('remove', 'replace'):
            continue
        kind, _, identity = subject.partition(':')
        parts = identity.split('/')
        if not parts or parts[0] != version:
            continue
        if kind == 'requirement' and len(parts) == 2 and parts[1] not in records:
            allowed.add(subject)
        if kind == 'scope' and len(parts) == 3:
            info = records.get(parts[1])
            if info is None or parts[2] not in info['acs']:
                allowed.add(subject)
    return sorted(allowed)


def retired_subjects(current, requirements, mapping, acceptance, dispositions, *, baseline, version, line):
    """A fully delivered retirement can settle its exact excluded predecessor.

    Called only after current integrated evidence and capacity release have
    been rechecked. These aliases settle old duties; they never enlarge
    planning/Apply permission or count removed AC as successful delivery.
    """
    delivered = {}
    for candidate in mapping['candidates']:
        for allocation in candidate['allocation']:
            actual = set(acceptance.get(candidate['candidate_id'] + '/' + allocation['id'], []))
            delivered.setdefault(allocation['requirement'], set()).update(actual & set(allocation['acceptance']))
    fixed_keys = ('version', 'requirement', 'baseline_ref', 'record_ref', 'configuration_ref')
    history = set()
    for uid, info in requirements.records.items():
        if not set(info['acs']) <= delivered.get(uid, set()):
            continue
        for reference in info['value'].get('retires', []):
            if reference['version'] != version or reference['baseline_ref'] != baseline:
                continue
            # An arbitrary historical link is insufficient: the same original
            # record/configuration must be explicitly removed from this scope.
            if not any(row.get('disposition') == 'removed' and
                       all(row.get('predecessor', {}).get(k) == reference[k] for k in fixed_keys)
                       for row in requirements.scope['excluded']):
                continue
            original = requirements.historical(reference)
            if original['owner'].version['delivery_line'] != line:
                continue
            old = original['uid']
            history.add('requirement:' + version + '/' + old)
            history.update('scope:' + version + '/' + old + '/' + ac for ac in original['acs'])
    return withdrawn_subjects(history, current, requirements.records, dispositions, version)


def fixed_context(store, reference, *, version, line, ui_context=None):
    value = validate('snapshot', parse_json(evidence(store, reference)))
    if (value['version'], value['delivery_line']) != (version, line):
        raise CheckError('rc.context-owner', 'RC inputs must retain their exact Version and delivery line', refs=[reference])
    # Publication/decision is historical here. Current callers still query the
    # actual authority through their ordinary Gate/report snapshot.
    from .ui_receipts import historical, relocate
    value = relocate(value, ui_context or {})
    context = resolve(store, historical(value, ui_context or {}))
    return replace(context), value


def effective_baseline(store, reference, *, version, line):
    context, value = fixed_context(store, reference, version=version, line=line)
    if (value['gate'], value['phase']) != ('G1', 'effective'):
        raise CheckError('rc.baseline-context', 'RC baseline needs the original effective G1 context')
    checked = check_baseline(context)
    _, head = published_chain(context, value['target_revision'])
    if head != value['baseline_ref']['path']:
        raise CheckError('rc.stale-baseline', 'RC must select the effective head at its declared target observation')
    return context, value, checked


def refs(store, values):
    for value in values:
        evidence(store, value)


def baseline_approval(context, *, control_revision):
    """Bind B to a previously published approval without replaying its future.

    The RC approved C before B existed. Replaying rc-baselined here would make
    G1 depend on its own future confirmation, so replay this RC only through
    the selected decision. G1's ordinary history/retention checks still apply.
    """
    baseline, store = context.baseline, context.store
    reference = baseline.get('requirement_change_ref')
    if baseline['supersedes'] is None:
        if reference is not None:
            raise CheckError('baseline.rc-first', 'first Version baseline has no same-Version change predecessor')
        return None
    if reference is None:
        schema = parse_json(store.read(context.content_commit, 'harness/version-requirements/schemas/vr.schema.json'))
        # Only an actual original publication may retain the old contract.
        # Copying old tooling into a new unpublished draft is no exemption.
        if ('requirement_change_ref' not in schema['$defs']['baseline']['properties'] and
                context.snapshot.get('publication_evidence_ref') is not None):
            return None
        raise CheckError('baseline.rc-required', 'new same-Version baseline must name its exact published RC approval')
    from .control import published_events
    selected, history = None, ChangeRequests()
    for row in published_events(store, control_revision):
        if row['event_ref']['path'] == reference['path'] and row['event']['kind'] in KINDS:
            history.consume(store, row)
        if row['event_ref'] == reference:
            selected = row
            break
    if selected is None:
        raise CheckError('baseline.rc-unpublished', 'baseline RC decision was not published in its applicable control observation')
    event = selected['event']
    if event['kind'] != 'rc-decided' or event['payload']['outcome'] != 'approved':
        raise CheckError('baseline.rc-decision', 'baseline must reference the approved decision, not another lifecycle event')
    state = history.records.get((context.version['delivery_line'], context.version['version'], event['payload']['rc_id']))
    if (state is None or state['status'] != 'approved' or state['from_baseline'] != baseline['supersedes'] or
            state['approved_content'] != context.content_commit):
        raise CheckError('baseline.rc-binding', 'published RC approval must bind this same Version/line, C and predecessor BL')
    approved = {value['role']: value for value in state['decision']['decisions']}
    for value in baseline['approvals']:
        if any(value[key] != approved[value['role']][key] for key in ('actor', 'evidence_ref')):
            raise CheckError('baseline.rc-approvals', 'B must retain the exact role decision evidence already approved in the RC')
    return state


class ChangeRequests:
    def __init__(self, *, ui_context=None):
        from .ui_receipts import locations
        self.ui_context = locations(ui_context)
        self.records = {}

    def evaluate(self, store, row):
        """Return a new projection; preview must not change the published state."""
        event, reference = row['event'], row['event_ref']
        kind = event['kind']
        if kind not in KINDS:
            raise InputError('rc.kind-unsupported', 'unsupported RC lifecycle event')
        payload = validate(KINDS[kind], event['payload'], location=reference['path'])
        version, line, identity = event['version'], event['target_line'], payload['rc_id']
        path = 'requirements/versions/' + version + '/change-requests/' + identity + '.yaml'
        if reference['path'] != path:
            raise CheckError('rc.path', 'RC events must stay in their original Version record', refs=[reference])
        key = (line, version, identity)
        previous = self.records.get(key)
        if kind == 'rc-proposed':
            if previous is not None:
                raise CheckError('rc.duplicate', 'published RC identity cannot be proposed again')
            if any(key[:2] == other[:2] and int(identity[3:]) == int(other[2][3:]) for other in self.records):
                raise CheckError('rc.identity-alias', 'another spelling already owns this RC number in the Version and line')
            context, original, _ = effective_baseline(store, payload['from_context_ref'], version=version, line=line)
            state = {'id': identity, 'version': version, 'target_line': line, 'status': 'proposed',
                     'proposal_ref': reference, 'proposal': payload, 'from_baseline': original['baseline_ref'],
                     'owner': context.version, 'assessment': None, 'decision': None, 'to_baseline': None,
                     'alignments': [], 'verifications': []}
        else:
            if previous is None or payload['previous_ref'] != previous['latest_ref']:
                raise CheckError('rc.previous', 'RC transition must extend its exact latest published lifecycle event')
            restoring = kind == 'rc-restored' and previous['status'] in ('rejected', 'withdrawn', 'verified')
            if previous['status'] in ('rejected', 'withdrawn', 'verified') and not restoring:
                raise CheckError('rc.terminal', 'a terminal RC is retained; a new decision needs a new RC identity')
            state = dict(previous)
        owner = SimpleNamespace(store=store, version=state['owner'])
        if event['actor'] != state['owner']['owners']['integrator']:
            raise CheckError('rc.actor', 'responsible integrator must publish the actual RC decision references')
        evidence(store, event['evidence_ref'])
        if kind == 'rc-proposed':
            decision(owner, payload['request'], roles=set(state['owner']['owners']))
            if event['evidence_ref'] != payload['request']['evidence_ref']:
                raise CheckError('rc.evidence', 'proposal event must bind the actual named request')
            refs(store, payload['source_refs'])
            for target in payload['known_targets']:
                check_target(target, version, line)
        elif kind == 'rc-impact-assessed':
            if state['status'] not in ('proposed', 'impact-assessed'):
                raise CheckError('rc.assessment-stage', 'new impact cannot silently replace an approved decision')
            state['assessment'] = self.assess(store, owner, state, payload)
            state['status'] = 'impact-assessed'
            state['assessment_ref'] = reference
            if event['evidence_ref'] != payload['review']['evidence_ref']:
                raise CheckError('rc.evidence', 'assessment event must bind its engineering review')
        elif kind == 'rc-decided':
            self.decide(store, owner, state, payload, event)
            state.update(status=payload['outcome'], decision=payload, decision_ref=reference)
        elif kind == 'rc-baselined':
            if state['status'] != 'approved' or state['to_baseline'] is not None:
                raise CheckError('rc.baseline-stage', 'new BL follows one approved C, before engineering alignment')
            context, snapshot, _ = effective_baseline(store, payload['effective_context_ref'], version=version, line=line)
            if (context.baseline['supersedes'] != state['from_baseline'] or
                    context.content_commit != state['approved_content'] or
                    context.baseline.get('requirement_change_ref', payload['previous_ref']) != payload['previous_ref'] or
                    snapshot['control_revision'] != event['based_on_control']):
                raise CheckError('rc.baseline-binding', 'new effective BL must preserve the approved C, exact predecessor and publication control')
            approved = {value['role']: value for value in state['decision']['decisions']}
            if any(value['evidence_ref'] != approved[value['role']]['evidence_ref']
                   for value in context.baseline['approvals']):
                raise CheckError('rc.baseline-approval', 'baseline approvals must retain the same exact three-role RC decisions on C')
            decision(owner, payload['confirmation'], roles={'integrator'})
            if event['evidence_ref'] != payload['confirmation']['evidence_ref']:
                raise CheckError('rc.evidence', 'baseline confirmation must retain the actual integrator evidence')
            state.update(to_baseline=snapshot['baseline_ref'], baseline_event_ref=reference,
                         effective_context_ref=payload['effective_context_ref'])
        elif kind in ('rc-aligned', 'rc-restored'):
            proof = self.align(store, owner, state, payload, event, restoring=kind == 'rc-restored')
            state['alignments'] = [*state['alignments'], {**proof, 'event_ref': reference}]
            covered = {identity for item in state['alignments'] for identity in item['object_ids']}
            covered.update(self.historical_objects(state))
            if kind == 'rc-aligned':
                state['status'] = 'aligned' if self.required_objects(state) <= covered else 'approved'
        elif kind == 'rc-verified':
            proof = self.verify(store, owner, state, payload, event)
            state['verifications'] = [*state['verifications'], {**proof, 'event_ref': reference}]
            covered = {identity for item in state['verifications'] for identity in item['object_ids']}
            covered.update(self.historical_objects(state))
            if self.required_objects(state) <= covered:
                self.check_historical_closure(store, state, payload, event)
                state['status'] = 'verified'
        state['latest_ref'] = reference
        return key, state

    def assess(self, store, owner, state, payload):
        version, line = state['version'], state['target_line']
        before, raw_before = fixed_context(store, payload['before_context_ref'], version=version, line=line, ui_context=self.ui_context)
        after, raw_after = fixed_context(store, payload['after_context_ref'], version=version, line=line, ui_context=self.ui_context)
        if before.snapshot['baseline_ref'] != state['from_baseline']:
            raise CheckError('rc.impact-origin', 'impact must keep the original baseline and its engineering metadata')
        if (raw_after['gate'], raw_after['phase'], raw_after['baseline_ref']) != ('G1', 'content', None):
            raise CheckError('rc.impact-draft', 'proposed requirements use a fixed G1 content draft, not a pretend new BL')
        if before.version != state['owner'] or after.version != state['owner']:
            raise CheckError('rc.owner-change', 'RC cannot silently replace Version responsibilities or line identity')
        report = parse_json(evidence(store, payload['report_ref']))
        if not isinstance(report, dict) or not isinstance(report.get('generated_from'), dict):
            raise InputError('rc.impact-binding', 'expected a complete generated impact report')
        generated = report['generated_from']
        declared = {key: value for key, value in generated.items() if key != 'sha256'}
        if (report.get('kind') != 'generated-requirement-impact' or
                generated.get('before') != raw_before or generated.get('after') != raw_after or
                generated.get('sha256') != digest(canonical_bytes(declared))):
            raise CheckError('rc.impact-binding', 'report must bind both exact saved snapshots and its complete generation inputs')
        actual = analyze(before, after, seeds=generated.get('explicit_seeds', []))
        # Runtime packaging can evolve while these qualified input semantics
        # stay identical. Compare actual graph/diff content, not a stale PASS
        # or a current generator hash relabelled as the original generator.
        fields = ('affected', 'affected_requirements', 'diff', 'unmapped_diff', 'diagnostics', 'edges')
        if any(report.get(field) != actual[field] for field in fields):
            raise CheckError('rc.impact-content', 'saved analysis omits or changes actual old/new graph or diff content')
        dispositions = unique(payload['dispositions'], 'object_id', location='RC impact')
        if set(dispositions) != {value['id'] for value in actual['affected']}:
            raise CheckError('rc.impact-coverage', 'every affected object needs an explicit reviewed disposition')
        unknown = {(value['group'], value['path']): value for value in payload['unmapped_dispositions']}
        if (len(unknown) != len(payload['unmapped_dispositions']) or
                set(unknown) != {(value['group'], value['path']) for value in actual['unmapped_diff']}):
            raise CheckError('rc.unknown-coverage', 'unmapped differences require exact individual accounting')
        for value in list(dispositions.values()) + list(unknown.values()):
            refs(store, value['review_refs'])
        decision(owner, payload['review'], roles={'engineering-owner'})
        history = self.historical_deliveries(store, owner, state, payload, report, raw_after)
        return {'payload': payload, 'report': report, 'after': raw_after, 'historical_deliveries': history,
                'pending': sorted(value['object_id'] for value in dispositions.values() if value['action'] == 'investigate') +
                           sorted(group + ':' + path for (group, path), value in unknown.items() if value['action'] == 'investigate')}

    def historical_deliveries(self, store, owner, state, payload, report, after):
        """Retain completed identities, without inventing current delivery credit.

        The proposal's predecessor excludes this RC and its future assessment.
        Replaying that control proves release and its original integrated G3;
        an event file, retained disposition or later completion is insufficient.
        """
        from .archive import read_archive
        from .control import event as read_event
        from .control_delivery import read_delivery_control
        from .openspec_artifacts import read_observation

        declarations = payload.get('historical_deliveries', [])
        if not declarations:
            return []
        proposal = read_event(store, state['proposal_ref'])
        control = read_delivery_control(store, proposal['based_on_control'], ui_context=self.ui_context)
        version, line = state['version'], state['target_line']
        mapping = validate('delivery_map', store.yaml(after['metadata_revision'],
            'requirements/versions/' + version + '/delivery-map.yaml'))
        candidates = unique(mapping['candidates'], 'candidate_id', location='historical RC disposition')
        affected = {row['id'] for row in report['affected']}
        dispositions = {row['object_id']: row['action'] for row in payload['dispositions']}
        history, accounted = [], set()
        for declaration in declarations:
            selected = [row for key, row in control.completed.items()
                        if key[:2] == (line, version) and row['release_ref'] == declaration['slot_release_ref']]
            if len(selected) != 1:
                raise CheckError('rc.history-release', 'historical disposition needs the exact same-line completed release published before this RC')
            completed = selected[0]
            cid = completed['inputs']['key'][2]
            receipt = completed['receipt']
            change = receipt['evidence']['change']
            subjects = {'candidate:' + version + '/' + cid, 'change:' + change}
            objects = set(declaration['object_ids'])
            if not objects or objects != subjects & affected or objects & accounted:
                raise CheckError('rc.history-objects', 'historical proof covers only its exact affected candidate and Change, once; never R/AC, code or tests')
            candidate = candidates.get(cid)
            if (candidate is None or candidate['disposition'] != 'superseded' or
                    candidate['change_name'] != change or any(dispositions.get(obj) != 'retain' for obj in objects)):
                raise CheckError('rc.history-disposition', 'retain the completed Change under its superseded candidate; current obligations need their own disposition')
            binding = digest(canonical_bytes({
                **{key: payload[key] for key in ('rc_id', 'previous_ref', 'before_context_ref', 'after_context_ref', 'report_ref')},
                'slot_release_ref': declaration['slot_release_ref'], 'object_ids': declaration['object_ids']}))
            reviewers = unique(declaration['reviews'], 'role', location='historical delivery Review')
            if declaration['input_digest'] != binding or set(reviewers) != {'engineering-owner', 'qa-owner'}:
                raise CheckError('rc.history-review', 'engineering and QA must bind the exact impact, draft and original release')
            for review in reviewers.values():
                decision(owner, review, roles={'engineering-owner', 'qa-owner'})
                if binding not in evidence(store, review['evidence_ref']).decode('utf-8', errors='replace'):
                    raise CheckError('rc.history-review', 'each named historical Review must identify this exact input digest')
            trace_ref = receipt['snapshot']['trace_ref']
            trace = validate('planning_trace', parse_yaml(store.ref(trace_ref)))
            archive_ref = trace['delivery']['archive_observation_ref']
            original_archive = parse_json(evidence(store, archive_ref))
            archive = read_archive(store, archive_ref, change=change,
                                   actual_revision=original_archive['archive_revision'])
            planning = read_observation(store, archive['planning_observation_ref'], change=change,
                                        actual_revision=archive['before_revision'], allow_task_progress=True)
            subjects.update('task:' + change + '/' + tid for tid in planning['tasks'])
            proof = {'object_ids': declaration['object_ids'], 'subjects': sorted(subjects),
                     'trace_ref': trace_ref, 'archive': archive, 'active_path': planning['change_root'],
                     'original_target': receipt['snapshot']['target_revision'],
                     'slot_release_ref': declaration['slot_release_ref'], 'input_digest': binding}
            self.preserve_historical_delivery(store, proof, after)
            history.append(proof)
            accounted.update(objects)
        return history

    @staticmethod
    def historical_objects(state):
        return {obj for proof in (state.get('assessment') or {}).get('historical_deliveries', [])
                for obj in proof['object_ids']}

    @staticmethod
    def preserve_historical_delivery(store, proof, snapshot):
        """Preserve complete old Trace/Archive bytes; current code may evolve."""
        archive, trace = proof['archive'], proof['trace_ref']
        if not store.ancestor(proof['original_target'], snapshot['target_revision']):
            raise CheckError('rc.history-target', 'current target must retain the original completed delivery history')
        originals = [trace, *[row['archived_ref'] for row in archive['file_moves']]]
        expected = {row['archived_ref']['path'] for row in archive['file_moves']}
        for side in ('target_revision', 'metadata_revision'):
            revision = snapshot[side]
            tree = store.tree(revision)
            if ({path for path in tree if path.startswith(archive['archived_path'] + '/')} != expected or
                    any(path.startswith(proof['active_path'] + '/') for path in tree)):
                raise CheckError('rc.history-preservation', 'completed Archive must retain its full file set without reopening the old Change')
            for reference in originals:
                store.ref(reference)
                allowed = {store.tree(reference['commit'])[reference['path']]}
                if reference == trace and side == 'target_revision':
                    # Integrated evidence is saved after the actual merge. The
                    # target may retain its original merged Trace or later
                    # incorporate the exact final Trace; neither is a rewrite.
                    prior = store.tree(proof['original_target']).get(trace['path'])
                    allowed.add(prior)
                    if prior is not None:
                        store.read(proof['original_target'], trace['path'])
                if tree.get(reference['path']) not in allowed:
                    raise CheckError('rc.history-preservation', 'retain the exact original Trace and all Archive bytes/modes', refs=[reference])
                if reference['path'] in tree:
                    store.read(revision, reference['path'])

    def check_historical_closure(self, store, state, payload, event):
        history = (state.get('assessment') or {}).get('historical_deliveries', [])
        if not history:
            return
        from .control_delivery import read_delivery_control

        _, snapshot = fixed_context(store, payload['context_ref'], version=state['version'], line=state['target_line'], ui_context=self.ui_context)
        subjects = {'version:' + state['version'], 'line:' + state['target_line']}
        for proof in history:
            self.preserve_historical_delivery(store, proof, snapshot)
            subjects.update(proof['subjects'])
        task_prefixes = tuple('task:' + subject.split(':', 1)[1] + '/'
                              for subject in subjects if subject.startswith('change:'))
        control = read_delivery_control(store, event['based_on_control'], ui_context=self.ui_context)
        pending = [(target, entry) for held in control.holds.holds.values()
                   if held['event_ref']['path'] == state['proposal_ref']['path']
                   for target, entry in held['remaining']
                   if (target in subjects or target.startswith(task_prefixes)) and entry in ('propose', 'apply', 'merge')]
        if pending:
            raise CheckError('rc.verification-held', 'explicitly resolve this RC historical execution holds before closure', refs=pending)

    def decide(self, store, owner, state, payload, event):
        if state['status'] not in ('proposed', 'impact-assessed'):
            raise CheckError('rc.decision-stage', 'approved scope cannot be overwritten by a later decision in the same RC')
        decisions = unique(payload['decisions'], 'role', location='RC decision')
        deciding_role = state['proposal']['request']['role'] if payload['outcome'] == 'withdrawn' else 'product-owner'
        required = ROLES if payload['outcome'] == 'approved' else {deciding_role}
        if set(decisions) != required:
            raise CheckError('rc.decision-roles', 'decision must identify the required product/engineering/QA responsibility')
        for value in decisions.values():
            decision(owner, value, roles=required)
        if event['evidence_ref'] != decisions[deciding_role]['evidence_ref']:
            raise CheckError('rc.evidence', 'scope decision/withdrawal event must bind the actual responsible decision')
        if payload['outcome'] != 'approved':
            if payload['content_context_ref'] is not None:
                raise CheckError('rc.rejected-content', 'rejection/withdrawal grants no approved content')
            return
        assessment = state['assessment']
        if assessment is None or assessment['pending']:
            raise CheckError('rc.impact-pending', 'approve only after the actual impact and unmapped worklist have been reviewed')
        context, snapshot = fixed_context(store, payload['content_context_ref'], version=state['version'], line=state['target_line'], ui_context=self.ui_context)
        # Publishing the assessed event advances control without changing C.
        # G1 rechecks the new control observation and inherited contexts below;
        # content, target and owner cannot change under that bookkeeping update.
        fixed = ('head_revision', 'metadata_revision', 'target_revision', 'gate', 'phase',
                 'subject', 'version', 'delivery_line', 'baseline_ref')
        if (any(snapshot[key] != assessment['after'][key] for key in fixed) or
                snapshot['control_revision'] != event['based_on_control'] or snapshot['evaluation_mode'] != 'current'):
            raise CheckError('rc.approval-content', 'approval must bind the exact assessed C and current publication predecessor')
        # Existing G1 owns whole-version content/semantic Review. No future code
        # or BL descriptor is required to approve these product obligations.
        check_baseline(context)
        state['approved_content'] = snapshot['head_revision']

    def consume(self, store, row):
        key, state = self.evaluate(store, row)
        self.records[key] = state

    def baseline_chain(self, before, after, *, version, line):
        """Require every actual published RC/BL step, never infer from ordinals.

        A reservation may jump to the current BL after several approved changes;
        it need not obtain execution permission at obsolete intermediate BLs.
        """
        selected, seen, chain = after, set(), []
        while selected != before:
            key = canonical_bytes(selected)
            if key in seen:
                raise CheckError('rc.baseline-cycle', 'RC baseline transitions cannot cycle')
            seen.add(key)
            candidates = [state for identity, state in self.records.items()
                          if identity[:2] == (line, version) and state['to_baseline'] == selected]
            if len(candidates) != 1:
                raise CheckError('rc.baseline-chain', 'baseline realignment requires every exact approved and effective RC transition',
                                 refs=[{'from': before, 'to': after, 'unresolved': selected}])
            state = candidates[0]
            if state['status'] not in ('approved', 'aligned', 'verified'):
                raise CheckError('rc.baseline-chain', 'unapproved or rejected RC cannot restore a baseline transition')
            chain.append(state['baseline_event_ref'])
            selected = state['from_baseline']
        return list(reversed(chain))

    @staticmethod
    def required_objects(state):
        objects = {row['id'] for row in state['assessment']['report']['affected']} if state['assessment'] else set()
        return objects | {value for value in state['proposal']['known_targets']
                          if not value.startswith(('version:', 'line:'))}

    def disposition_subjects(self, store, state, snapshot, control, record):
        """Reuse only this published reservation's original/aligned inputs."""
        from .control import event as read_event
        from .control_delivery import admission_inputs
        from .requirements import RequirementIndex

        history, seen = set(), set()
        reference = record['event_ref']
        while True:
            identity = reference['event_id']
            if identity in seen or control.event_refs.get(identity) != reference:
                raise CheckError('rc.disposition-origin', 'withdrawn duties require the exact published reservation history')
            seen.add(identity)
            row = {'event_ref':reference, 'event':read_event(store, reference)}
            inputs = admission_inputs(store, row)
            if inputs['key'] != record['inputs']['key']:
                raise CheckError('rc.disposition-origin', 'withdrawn duties cannot move to another reservation or line')
            history.update(inputs['subjects'])
            if reference == record['reservation_ref']:
                break
            if row['event']['kind'] != 'execution-alignment':
                raise CheckError('rc.disposition-origin', 'alignment history must reach the original reservation')
            reference = inputs['payload']['previous_dispatch_ref']
        context = replace(resolve(store, {**snapshot, 'evaluation_mode':'historical'}))
        requirements = RequirementIndex(context)
        dispositions = {row['object_id']:row['action'] for row in
                        state['assessment']['payload']['dispositions']} if state['assessment'] else {}
        return withdrawn_subjects(history, record['inputs']['subjects'], requirements.records,
                                  dispositions, state['version'])

    def align(self, store, owner, state, payload, event, *, restoring=False):
        """Recheck local planning facts while held, without a new public Gate."""
        from .control import event as read_event
        from .control_delivery import admission_inputs
        from .dispatch import check_dispatch
        from .planning import check_planning
        from .premerge import check_pre_merge

        if restoring:
            if state['status'] == 'verified' and state['to_baseline'] is not None:
                # Closing a product disposition does not erase its holds. Later
                # engineering readiness may restore an entry on the approved
                # successor without reopening the RC or inventing an approval.
                origin_baseline = state['to_baseline']
            elif state['status'] in ('rejected', 'withdrawn') and state['to_baseline'] is None:
                origin_baseline = state['from_baseline']
            else:
                raise CheckError('rc.restoration-stage', 'terminal restoration retains the actual decision and its applicable baseline')
        elif state['to_baseline'] is None or state['status'] not in ('approved', 'aligned'):
            raise CheckError('rc.alignment-stage', 'object alignment needs the approved effective successor BL')
        else:
            origin_baseline = state['to_baseline']
        _, snapshot = fixed_context(store, payload['context_ref'], version=state['version'], line=state['target_line'], ui_context=self.ui_context)
        phase = (snapshot['gate'], snapshot['phase'])
        checks = {('G2', 'dispatch'): check_dispatch, ('G2', 'planning'): check_planning,
                  ('G3', 'pre-merge'): check_pre_merge}
        if (phase not in checks or
                snapshot['evaluation_mode'] != 'current' or snapshot['control_revision'] != event['based_on_control']):
            raise CheckError('rc.alignment-context', 'local alignment must bind current candidate inputs at this exact control predecessor')
        self.baseline_chain(origin_baseline, snapshot['baseline_ref'], version=state['version'], line=state['target_line'])
        decision(owner, payload['review'], roles={'engineering-owner'})
        if event['evidence_ref'] != payload['review']['evidence_ref']:
            raise CheckError('rc.evidence', 'object alignment must bind its actual responsible Review')
        reference = snapshot.get('dispatch_ref')
        if reference is None:
            raise CheckError('rc.alignment-context', 'candidate alignment needs exact dispatch/allocation inputs')
        row = {'event_ref': reference, 'event': read_event(store, reference)}
        inputs = admission_inputs(store, row)
        expected = ('change:' + inputs['candidate']['change_name'] if phase == ('G3', 'pre-merge')
                    and inputs['candidate']['change_name'] else
                    'candidate:' + state['version'] + '/' + inputs['payload']['candidate_id'])
        if snapshot['subject'] != expected:
            raise CheckError('rc.alignment-subject', 'local proof must identify the actual candidate or its existing Change')
        objects = set(payload['object_ids'])
        if not objects <= self.required_objects(state):
            raise CheckError('rc.alignment-objects', 'alignment cannot invent objects outside the reviewed impact worklist')
        actionable = {value for value in objects if value.startswith(('candidate:', 'change:', 'scope:', 'requirement:'))}
        subjects = inputs['subjects']
        if not actionable <= set(subjects):
            from .control_delivery import read_delivery_control
            control = read_delivery_control(store, snapshot['control_revision'], ui_context=self.ui_context)
            record = control.reservations.get(inputs['key'])
            if record is not None and record['event_ref'] == reference:
                subjects = self.disposition_subjects(store, state, snapshot, control, record)
        if not actionable <= set(subjects):
            raise CheckError('rc.alignment-scope', 'one candidate proof cannot align another candidate or its unrelated obligations')
        check = checks[phase]
        # Replaying the prior control point excludes this new alignment event.
        # The private local check deliberately skips holds and execution-ready
        # dependencies; public G2 still consumes both after explicit unhold.
        with store.input_scope():
            checked = check(store, {**snapshot, 'evaluation_mode': 'historical'}, alignment_only=True)
        entries = ['merge'] if phase == ('G3', 'pre-merge') else ['propose']
        if snapshot['phase'] == 'planning' and inputs['payload']['mode'] == 'execution':
            entries.append('apply')
        return {'subject': snapshot['subject'], 'subjects': subjects, 'entries': entries,
                'object_ids': payload['object_ids'], 'context_ref': payload['context_ref'],
                'baseline_ref': snapshot['baseline_ref'], 'review': payload['review'],
                'local_rule': checked['rule_id'], 'engineering_permission': False}

    def projections(self, *, version, line):
        return [{key: value for key, value in state.items() if key not in ('owner', 'assessment', 'proposal', 'decision')}
                for identity, state in sorted(self.records.items()) if identity[:2] == (line, version)]

    def verify(self, store, owner, state, payload, event):
        """Bind actual integrated facts and disposition Review, never grant work.

        The saved public result is fully replayed by the existing G3 receipt
        reader. Replaying its predecessor excludes this new verification event.
        Remaining reservations and this RC's execution holds must already be
        resolved; unrelated holds are kept, not silently cleared on closure.
        """
        from .control_delivery import read_delivery_control
        from .integrated_receipt import read_integrated_receipt

        if state['to_baseline'] is None or state['status'] not in ('approved', 'aligned'):
            raise CheckError('rc.verification-stage', 'actual disposition verification follows the approved effective baseline')
        if payload.get('outcome') == 'cancelled':
            return self.verify_cancelled(store, owner, state, payload, event)
        if payload.get('outcome') == 'upstream':
            return self.verify_upstream(store, owner, state, payload, event)
        context, snapshot = fixed_context(store, payload['context_ref'], version=state['version'], line=state['target_line'], ui_context=self.ui_context)
        if ((snapshot['gate'], snapshot['phase'], snapshot['evaluation_mode']) != ('G3', 'integrated', 'current') or
                snapshot['control_revision'] != event['based_on_control'] or not snapshot['subject'].startswith('change:')):
            raise CheckError('rc.verification-context', 'Standard RC disposition needs actual current integrated input at its publication predecessor')
        self.baseline_chain(state['to_baseline'], snapshot['baseline_ref'], version=state['version'], line=state['target_line'])
        reviewers = unique(payload['reviews'], 'role', location='RC verification')
        if set(reviewers) != {'engineering-owner', 'qa-owner'}:
            raise CheckError('rc.verification-review', 'actual engineering disposition and QA revalidation both need named Review')
        for value in reviewers.values():
            decision(owner, value, roles={'engineering-owner', 'qa-owner'})
        if event['evidence_ref'] != reviewers['qa-owner']['evidence_ref']:
            raise CheckError('rc.evidence', 'verification event must bind the actual QA disposition evidence')
        receipt = read_integrated_receipt(context, payload['context_ref'], payload['result_ref'])
        control = read_delivery_control(store, snapshot['control_revision'], ui_context=self.ui_context)
        completed = [row for key, row in control.completed.items()
                     if key[:2] == (state['target_line'], state['version']) and
                     row['reservation_ref'] == receipt['evidence']['reservation_ref']]
        if len(completed) != 1:
            raise CheckError('rc.verification-reservation', 'confirm the original delivered reservation release before closing its disposition')
        subjects = completed[0]['inputs']['subjects']
        objects = set(payload['object_ids'])
        if not objects <= self.required_objects(state):
            raise CheckError('rc.verification-objects', 'verification cannot invent objects outside the reviewed impact worklist')
        actionable = {value for value in objects if value.startswith(('candidate:', 'change:', 'scope:', 'requirement:'))}
        if not actionable <= set(subjects):
            subjects = self.disposition_subjects(store, state, snapshot, control, completed[0])
        if not actionable <= set(subjects):
            from .requirements import RequirementIndex
            requirements = RequirementIndex(context)
            mapping = validate('delivery_map', parse_yaml(store.ref(receipt['evidence']['engineering_inputs']['map_ref'])))
            dispositions = {row['object_id']:row['action'] for row in state['assessment']['payload']['dispositions']}
            subjects = retired_subjects(subjects, requirements, mapping,
                receipt['evidence']['integrated_acceptance'], dispositions,
                baseline=state['from_baseline'], version=state['version'], line=state['target_line'])
        if not actionable <= set(subjects):
            raise CheckError('rc.verification-scope', 'one delivered candidate cannot close another affected candidate')
        for held in control.holds.holds.values():
            if held['event_ref']['path'] == state['proposal_ref']['path']:
                pending = [(target, entry) for target, entry in held['remaining']
                           if entry in ('propose', 'apply', 'merge') and
                           (target in subjects or target == 'line:' + state['target_line'] or
                            target.startswith('task:' + snapshot['subject'].split(':', 1)[1] + '/'))]
                if pending:
                    raise CheckError('rc.verification-held', 'explicitly restore this RC execution holds before closing its delivered objects', refs=pending)
        return {'subject': snapshot['subject'], 'subjects': subjects, 'object_ids': payload['object_ids'],
                'context_ref': payload['context_ref'], 'result_ref': payload['result_ref'],
                'baseline_ref': snapshot['baseline_ref'], 'slot_release_ref': completed[0]['release_ref'],
                'reviews': payload['reviews'], 'engineering_permission': False}

    def verify_cancelled(self, store, owner, state, payload, event):
        """Close withdrawn objects after their actual capacity release, not G3."""
        from .control_delivery import read_delivery_control

        _, snapshot, _ = effective_baseline(store, payload['context_ref'], version=state['version'], line=state['target_line'])
        if snapshot['evaluation_mode'] != 'current' or snapshot['control_revision'] != event['based_on_control']:
            raise CheckError('rc.verification-context', 'cancelled disposition needs current effective scope at the exact control predecessor')
        self.baseline_chain(state['to_baseline'], snapshot['baseline_ref'], version=state['version'], line=state['target_line'])
        control = read_delivery_control(store, snapshot['control_revision'], ui_context=self.ui_context)
        selected = [row for key, row in control.cancelled.items()
                    if key[:2] == (state['target_line'], state['version']) and row['release_ref'] == payload['slot_release_ref']]
        if len(selected) != 1 or selected[0]['receipt']['rc_ref']['path'] != state['proposal_ref']['path']:
            raise CheckError('rc.verification-cancellation', 'confirm this RC original cancelled reservation before closing its objects')
        disposed = selected[0]
        subjects = disposed['receipt']['subjects']
        objects = set(payload['object_ids'])
        if not objects <= self.required_objects(state):
            raise CheckError('rc.verification-objects', 'verification cannot invent objects outside the reviewed impact worklist')
        actionable = {value for value in objects if value.startswith(('candidate:', 'change:', 'scope:', 'requirement:'))}
        if not actionable <= set(subjects):
            raise CheckError('rc.verification-scope', 'cancelled reservation cannot close another affected candidate or retained obligation')
        before = store.tree(disposed['inputs']['payload']['target_revision'])
        target = store.tree(snapshot['target_revision'])
        if any(before.get(path) != target.get(path) for path in disposed['receipt']['engineering_paths']):
            raise CheckError('rc.verification-residual', 'target changed after cancellation; re-evaluate actual residual/integrated obligations')
        reviewers = unique(payload['reviews'], 'role', location='RC cancellation verification')
        if set(reviewers) != {'engineering-owner', 'qa-owner'}:
            raise CheckError('rc.verification-review', 'engineering disposition and QA residual verification both need named Review')
        for value in reviewers.values():
            decision(owner, value, roles={'engineering-owner', 'qa-owner'})
        if event['evidence_ref'] != reviewers['qa-owner']['evidence_ref']:
            raise CheckError('rc.evidence', 'verification event must bind actual QA disposition evidence')
        return {'subject': 'candidate:' + state['version'] + '/' + disposed['inputs']['key'][2],
                'subjects': subjects, 'object_ids': payload['object_ids'], 'context_ref': payload['context_ref'],
                'baseline_ref': snapshot['baseline_ref'], 'slot_release_ref': payload['slot_release_ref'],
                'reviews': payload['reviews'], 'outcome': 'cancelled', 'delivered': False, 'engineering_permission': False}

    def verify_upstream(self, store, owner, state, payload, event):
        """Resolve upstream changes while retaining every future delivery duty.

        G1 can prove the revised scope and maps, not implemented behavior. Any
        affected existing engineering work must first have its own published
        disposition; an unstarted allocation remains a future G2/G3 obligation.
        """
        from .control_delivery import read_delivery_control
        from .delivery import DeliveryIndex
        from .dispatch import check_dispatch
        from .planning_applicability import target_changes
        from .requirements import RequirementIndex

        context, snapshot, _ = effective_baseline(store, payload['context_ref'],
            version=state['version'], line=state['target_line'])
        if snapshot['evaluation_mode'] != 'current' or snapshot['control_revision'] != event['based_on_control']:
            raise CheckError('rc.verification-context', 'upstream disposition needs current effective scope at its exact publication predecessor')
        self.baseline_chain(state['to_baseline'], snapshot['baseline_ref'],
                            version=state['version'], line=state['target_line'])
        objects = set(payload['object_ids'])
        required = self.required_objects(state)
        if not objects <= required:
            raise CheckError('rc.verification-objects', 'verification cannot invent objects outside the reviewed impact worklist')
        binding = digest(canonical_bytes({k: v for k, v in payload.items() if k not in ('reviews', 'input_digest')}))
        if payload['input_digest'] != binding:
            raise CheckError('rc.verification-review-binding', 'upstream Review must bind the exact context, RC predecessor and objects')
        reviewers = unique(payload['reviews'], 'role', location='upstream disposition')
        if set(reviewers) != {'engineering-owner', 'qa-owner'}:
            raise CheckError('rc.verification-review', 'engineering and QA must review the retained future delivery obligations')
        for value in reviewers.values():
            decision(owner, value, roles={'engineering-owner', 'qa-owner'})
            if binding not in evidence(store, value['evidence_ref']).decode('utf-8', errors='replace'):
                raise CheckError('rc.verification-review-binding', 'named upstream evidence must identify this exact input digest')
        if event['evidence_ref'] != reviewers['qa-owner']['evidence_ref']:
            raise CheckError('rc.evidence', 'verification event must bind the actual QA disposition evidence')
        requirements = RequirementIndex(context)
        requirements.check_content()
        delivery = DeliveryIndex(requirements, engineering_context=context.at(snapshot['metadata_revision'], state['version']))
        delivery.check()
        control = read_delivery_control(store, snapshot['control_revision'], ui_context=self.ui_context)
        # An earlier upstream review did not dispose of engineering work. If
        # that candidate has since entered Propose, re-evaluate its real state.
        settled = {identity for proof in state['verifications'] if proof.get('outcome') != 'upstream'
                   for identity in proof['object_ids']}
        settled.update(self.historical_objects(state))
        # Existing planning/code/test/endpoint work cannot disappear merely
        # because the new map omits it. Inspect the reviewed old/new worklist.
        engineering = {identity for identity in required if identity.startswith(('change:', 'trace:', 'task:', 'provider:')) or
                       (identity.startswith('file:') and not identity.startswith('file:requirements/'))}
        if engineering - settled:
            raise CheckError('rc.upstream-engineering', 'existing affected engineering work needs actual disposition before upstream closure',
                             refs=sorted(engineering - settled))
        unresolved = []
        for identity in sorted(required - settled):
            if not identity.startswith('candidate:' + state['version'] + '/'):
                continue
            cid = identity.rsplit('/', 1)[1]
            key = (state['target_line'], state['version'], cid)
            candidate = delivery.candidates.get(cid)
            old_names = [node['change_name'] for item in state['assessment']['report']['affected'] if item['id'] == identity
                         for side in ('before', 'after') for node in (item[side] or {}).get('values', []) if node.get('change_name')]
            trace = context.vr + '/trace/changes/' + cid + '.yaml'
            if (candidate is None or candidate['change_name'] or old_names or
                    trace in store.tree(snapshot['metadata_revision']) or key in control.completed or key in control.cancelled):
                unresolved.append(identity)
                continue
            reserved = control.reservations.get(key)
            if reserved and (candidate['disposition'] != 'planned' or reserved['inputs']['candidate']['change_name'] or
                             reserved['inputs']['payload']['baseline_ref'] != snapshot['baseline_ref']):
                unresolved.append(identity)
            elif reserved:
                # The baseline ID alone cannot prove the reservation's current
                # allocation/Review. Reuse the same local G2 contract as RC
                # alignment, without lifting holds or authorizing Propose.
                admitted = reserved['inputs']['payload']
                local = {**snapshot, 'evaluation_mode': 'historical', 'gate': 'G2', 'phase': 'dispatch',
                         'subject': identity, 'head_revision': admitted['engineering_review_ref']['commit'],
                         'metadata_revision': reserved['event_ref']['commit'], 'dispatch_ref': reserved['event_ref']}
                with store.input_scope():
                    check_dispatch(store, local, alignment_only=True)
        if unresolved:
            raise CheckError('rc.upstream-engineering', 'unstarted scope must retain an aligned reservation or finish actual cancellation first', refs=unresolved)
        before = state['assessment']['report']['generated_from']['before']['target_revision']
        changed_target = target_changes(store, before, snapshot['target_revision'])
        integrated_here = any(proof.get('result_ref') and
            parse_json(evidence(store, proof['context_ref']))['target_revision'] == snapshot['target_revision']
            for proof in state['verifications'])
        if (changed_target and not integrated_here) or target_changes(store, snapshot['target_revision'], snapshot['metadata_revision']):
            raise CheckError('rc.upstream-engineering', 'upstream scope cannot certify unverified target changes or unfinished engineering in metadata')
        return {'subject': snapshot['subject'], 'subjects': sorted(objects), 'object_ids': payload['object_ids'],
                'context_ref': payload['context_ref'], 'baseline_ref': snapshot['baseline_ref'],
                'reviews': payload['reviews'], 'input_digest': binding, 'outcome': 'upstream',
                'delivered': False, 'engineering_permission': False}

    @staticmethod
    def affected_targets(state):
        affected = set(state['proposal']['known_targets'])
        if state['assessment']:
            affected.update(row['id'] for row in state['assessment']['report']['affected']
                            if row['id'].startswith(('requirement:', 'scope:', 'candidate:', 'change:')))
        return affected

    def restoration_covers(self, state, proof, entry, subjects):
        matches = self.affected_targets(state) & set(proof['subjects'])
        local = {value for value in matches if not value.startswith(('version:', 'line:'))}
        return (proof['subject'] in subjects and entry in proof['entries'] and
                local <= set(proof['object_ids']))

    def require_entry_ready(self, *, line, entry, subjects):
        """A readable unresolved RC must not turn an old unsupported stop green.

        This checks an entry prerequisite from the published RC, not a second
        hold collection. Explicit holds, acknowledgements and restoration still
        follow their original records and remain independently mandatory.
        """
        queried = set(subjects) | {'line:' + line}
        for state in self.records.values():
            if state['target_line'] != line or state['status'] in ('rejected', 'withdrawn', 'verified'):
                continue
            affected = self.affected_targets(state)
            matches = sorted(queried & affected)
            aligned = any(self.restoration_covers(state, item, entry, queried) and
                          set(matches) - {value for value in matches if value.startswith(('version:', 'line:'))} <= set(item['object_ids'])
                          for item in state['alignments'])
            if matches and not aligned:
                raise CheckError('rc.alignment-required', 'affected entry needs published object alignment and applicable hold restoration before continuing',
                                 refs=[{'rc_ref': state['latest_ref'], 'entry': entry, 'targets': matches}])

    def guard_hold(self, row):
        """A published local proof may lift only its selected object/entry pairs.

        Existing standalone holds retain their already-qualified semantics.
        Rejection alone never silently removes a published restriction.
        """
        if row['event']['kind'] != 'unhold':
            return
        payload = validate('unhold_payload', row['event']['payload'])
        source = payload['hold_ref']['path']
        for state in self.records.values():
            if state['proposal_ref']['path'] != source:
                continue
            if row['event']['actor'] != state['owner']['owners']['integrator']:
                raise CheckError('rc.actor', 'responsible integrator must publish RC restoration')
            proofs = [item for item in state['alignments']
                      if {k: item['event_ref'][k] for k in ('commit', 'path', 'sha256')} in payload['alignment_refs']]
            assessment = state.get('assessment_ref')
            history = ((state.get('assessment') or {}).get('historical_deliveries', [])
                       if assessment and {k: assessment[k] for k in ('commit', 'path', 'sha256')} in payload['alignment_refs'] else [])
            for target in payload['targets']:
                for entry in payload['entries']:
                    applicable = [proof for proof in proofs
                                  if self.restoration_covers(state, proof, entry, proof['subjects'])]
                    if target.startswith(('version:', 'line:')):
                        # A candidate's Version alias is not a proof for every
                        # other affected object. Broad restoration aggregates
                        # exact published local proofs for this entry only.
                        covered = {identity for proof in applicable for identity in proof['object_ids']}
                        if entry in ('propose', 'apply', 'merge'):
                            covered.update(obj for proof in history for obj in proof['object_ids'])
                        complete = bool(applicable) and self.required_objects(state) <= covered
                    else:
                        complete = (any(target in proof['subjects'] for proof in applicable) or
                                    (entry in ('propose', 'apply', 'merge') and any(target in proof['subjects'] for proof in history)))
                    if not complete:
                        raise CheckError('rc.alignment-required', 'unhold needs exact published alignment for every selected object and entry',
                                         refs=[{'target': target, 'entry': entry}])
