"""Published hold consumption; derived in memory, never an editable state file.

Publication is distinct from acknowledgement. Acknowledgements record actual
safe stopping points and never release a hold. Admission/capacity and Gate
authorization are separate checks; this module alone grants no action.
"""
from .control import publication_points, published_events
from .core import canonical_bytes
from .errors import CheckError, InputError
from .models import validate
from .reviews import evidence

KINDS = {'hold': 'hold_payload', 'unhold': 'unhold_payload',
         'stop-acknowledgement': 'stop_payload'}
ENTRIES = {'propose', 'apply', 'merge', 'release'}


def check_target(target, version, line):
    validate('control_target', target)
    kind, identity = target.split(':', 1)
    if kind == 'line' and identity != line:
        raise CheckError('control.target-line', 'hold target and event line disagree', refs=[target])
    if kind in ('candidate', 'requirement', 'scope', 'version'):
        if identity.split('/')[0] != version:
            raise CheckError('control.target-version', 'hold target and event Version disagree', refs=[target])


class HoldState:
    def __init__(self, revision, *, entry_guard=None):
        self.revision = revision
        self.holds = {}
        self.acknowledgements = []
        self.entry_guard = entry_guard

    def _hold(self, reference, event):
        row = self.holds.get(canonical_bytes(reference))
        if row is None:
            raise CheckError('control.hold-reference', 'exact previously published hold required', refs=[reference])
        if (row['event']['version'], row['event']['target_line']) != (event['version'], event['target_line']):
            raise CheckError('control.hold-scope', 'release/stop cannot change the hold owner or delivery line')
        return row

    def consume(self, store, row):
        event, reference = row['event'], row['event_ref']
        model = KINDS.get(event['kind'])
        if model is None:
            raise InputError('control.kind-unsupported', 'unimplemented control event cannot be treated as no hold', refs=[reference])
        payload = validate(model, event['payload'], location=reference['path'] + '#' + reference['event_id'])
        targets = payload.get('targets', [payload.get('target')])
        for target in targets:
            check_target(target, event['version'], event['target_line'])
        evidence(store, event['evidence_ref'])
        if event['kind'] == 'hold':
            self.holds[canonical_bytes(reference)] = {
                'event_ref': reference, 'event': event,
                'remaining': {(target, entry) for target in payload['targets'] for entry in payload['entries']}}
        elif event['kind'] == 'unhold':
            hold = self._hold(payload['hold_ref'], event)
            pairs = {(target, entry) for target in payload['targets'] for entry in payload['entries']}
            if not pairs <= hold['remaining']:
                raise CheckError('control.unhold-scope', 'release must select still-held object/entry pairs', refs=[reference])
            # Alignment and its authorization precede the action's full Gate;
            # no Gate PASS blocked by this very hold is required to lift it.
            for item in payload['alignment_refs']:
                evidence(store, item)
            evidence(store, payload['authorization_ref'])
            hold['remaining'] -= pairs
        else:
            store.commit(payload['actual_revision'])
            for item in payload['hold_refs']:
                hold = self._hold(item, event)
                original = hold['event']['payload']
                if payload['target'] not in original['targets'] or payload['entry'] not in original['entries']:
                    raise CheckError('control.stop-scope', 'actual stopping point must identify an affected object/entry')
            self.acknowledgements.append(row)

    def blockers(self, *, line, entry, subjects):
        """Callers supply all actual R/AC/candidate/Change aliases for the action.

        Archive consumes the Apply restriction. The phase router adds relevant
        version, requirement and AC identities, rather than inferring them from
        an arbitrary Change name. Missing context is never a clear result.
        """
        if entry not in ENTRIES or not subjects:
            raise InputError('control.query-scope', 'a supported entry and actual action subjects are required')
        for subject in subjects:
            validate('control_target', subject)
        queried = set(subjects) | {'line:' + line}
        blockers = []
        for row in self.holds.values():
            if row['event']['target_line'] != line:
                continue
            matches = sorted(target for target, held_entry in row['remaining'] if held_entry == entry and target in queried)
            if matches:
                blockers.append({'hold_ref': row['event_ref'], 'targets': matches, 'entry': entry,
                                 'reason': row['event']['payload']['reason'],
                                 'restore_conditions': row['event']['payload']['restore_conditions']})
        return blockers

    def require_clear(self, **query):
        blockers = self.blockers(**query)
        if blockers:
            raise CheckError('control.held', 'published restrictions still apply; stop confirmation is not release', refs=blockers)
        if self.entry_guard is not None:
            self.entry_guard(**query)


def read_holds(store, revision):
    state = HoldState(revision)
    for row in published_events(store, revision):
        state.consume(store, row)
    return state
