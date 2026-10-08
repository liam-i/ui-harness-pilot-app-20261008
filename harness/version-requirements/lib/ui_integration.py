"""Thin UI input adapter; business allocation and the shared UI core keep ownership.

The map declares independently reviewed UI applicability for its real
contributions. The original engineering Review selects a fixed input record
after that map and its bindings exist, avoiding a map/binding reference cycle.
No package parsing, approval-history algorithm or remote observer is duplicated.
"""
from copy import deepcopy
from pathlib import Path
import re

from .core import canonical_bytes, digest, parse_json, parse_yaml
from .errors import CheckError, InputError
from .models import unique, validate
from .runtime import ui_runtime

POLICY = 'harness/ui-design/config/project.yaml'
CHECKS = ('ui-inputs', 'ui-coverage', 'ui-delivery')


def require_entry(configuration, snapshot):
    # Until an original entry has its complete UI contract, it cannot issue a
    # current permission by ignoring this adopted layer. This list expands only
    # with the corresponding implementation and entry-level verification.
    if configuration['ui_design'] == 'not-adopted' and 'ui' in snapshot:
        raise InputError('ui.adoption', 'not-adopted cannot accept ignored UI context')
    if configuration['ui_design'] == 'enabled' and snapshot['gate'] not in ('G0', 'G1', 'G2', 'G3', 'G4'):
        raise InputError('ui.entry-unavailable', 'this original entry has not completed its required UI integration')


def enabled(context):
    mode = context.configuration['ui_design']
    if mode not in ('enabled', 'not-adopted'):
        raise InputError('ui.adoption', 'explicit supported UI adoption is required')
    return mode == 'enabled'


def claims(delivery):
    """UI applicability never changes the original contribution denominator."""
    rows = delivery.map.get('ui')
    if not enabled(delivery.context):
        if rows or delivery.review['engineering'].get('ui_inputs_ref') is not None:
            raise CheckError('ui.adoption', 'UI inputs cannot be hidden behind not-adopted')
        return {}
    if rows is None:
        raise CheckError('ui.applicability-required', 'engineering map needs reviewed UI applicability for every actual contribution')
    for row in rows:
        validate('ui_claim', row)
    declared = unique(rows, 'contribution', location='delivery-map UI applicability')
    required = delivery.allocations.keys() | delivery.capabilities.keys()
    if declared.keys() != required:
        raise CheckError('ui.contribution-coverage', 'UI applicability must cover the exact original allocation/capability set',
                         refs=sorted(declared.keys() ^ required))
    for contribution, row in declared.items():
        if contribution in delivery.allocations:
            allocation = delivery.allocations[contribution]
            info = allocation['info']
            allowed = {f"{info['uid']}/r{info['value']['revision']}/{ac}" for ac in allocation['acceptance']}
        else:
            allowed = {contribution}
        if not set(row['behaviors']) <= allowed:
            raise CheckError('ui.behavior-scope', 'UI applicability names a different R revision/AC or technical contribution', refs=[contribution])
    return {key: value['behaviors'] for key, value in declared.items()}


def selections(delivery, contributions, *, consumption='new'):
    expected = claims(delivery)
    if not enabled(delivery.context):
        return []
    if len(contributions) != len(set(contributions)) or not set(contributions) <= expected.keys():
        raise CheckError('ui.contribution-selection', 'select actual unique contributions from the original delivery path')
    selected = []
    for contribution in sorted(contributions):
        item = delivery.allocations.get(contribution) or delivery.capabilities[contribution]
        node = item['node']
        group = 'candidates' if node in delivery.candidates else 'endpoints'
        field = 'candidate_id' if group == 'candidates' else 'id'
        positions = [i for i, row in enumerate(delivery.map[group]) if row[field] == node]
        if len(positions) != 1:
            raise CheckError('ui.consumer', 'original map node is absent or ambiguous', refs=[node])
        index = positions[0]
        original = delivery.map[group][index]
        if contribution in delivery.allocations:
            matches = [(i, row) for i, row in enumerate(original['allocation']) if node + '/' + row['id'] == contribution]
            if len(matches) != 1:
                raise CheckError('ui.consumer', 'original allocation is absent or ambiguous', refs=[contribution])
            position, row = matches[0]
            subject, pointer = row['id'], f'/{group}/{index}/allocation/{position}/id'
        else:
            subject = item['capability']
            position = original['expected_capabilities'].index(subject)
            pointer = f'/{group}/{index}/expected_capabilities/{position}'
        selected.append({'consumer': {'kind': 'contribution' if group == 'candidates' else 'endpoint',
                         'subject': subject, 'record_ref': {'repository': 'project', **delivery.map_ref},
                         'identity_pointer': pointer}, 'behaviors': expected[contribution], 'consumption': consumption})
    return selected


def load_inputs(delivery, *, required=True):
    claims(delivery)
    reference = delivery.review['engineering'].get('ui_inputs_ref')
    if not enabled(delivery.context):
        return None
    if reference is None:
        if required:
            raise CheckError('ui.inputs-required', 'this delivery entry needs fixed UI inputs selected by the original engineering Review')
        return None
    return load_record(delivery.context, reference)


def load_record(context, reference):
    """The local fixed record; callers still derive their own business scope."""
    validate('ref', reference)
    store = context.store
    if not reference['path'].startswith(context.vr + '/trace/evidence/'):
        raise CheckError('ui.inputs-owner', 'UI input selection belongs in the existing Version evidence namespace')
    value = validate('ui_inputs', parse_json(store.ref(reference)), location=reference['path'])
    if value['policy_ref']['path'] != POLICY or value['bindings_ref']['path'] != context.vr + '/ui-bindings.yaml':
        raise CheckError('ui.inputs-owner', 'use the actual project policy and this Version binding file')
    # Fixed data may predate its Review. It must still be the exact policy at
    # the reviewed engineering point; the BL's earlier policy remains retained.
    store.read(context.content_commit, POLICY, value['policy_ref']['sha256'])
    store.ref(value['bindings_ref'])
    runtime = ui_runtime()
    if value['rules'] != runtime.identity():
        raise InputError('ui.rules', 'UI inputs require a different shared implementation')
    from ui_design.models import parse, validate as ui_validate
    from ui_design.errors import CheckError as UIError
    try:
        policy = ui_validate('policy', parse(store.ref(value['policy_ref']), POLICY), POLICY)
        runtime.policy_capabilities(policy)
    except UIError as error:
        raise InputError('ui.policy', str(error), refs=[error.diagnostic]) from error
    if policy['adoption'] != {'ui': 'enabled', 'requirements': 'adopted'}:
        raise CheckError('ui.policy-adoption', 'fixed UI policy must agree with requirements-layer adoption')
    return {'reference': reference, 'document': value, 'policy': policy}


def review_refs(delivery, *, required=True):
    """Local fixed contracts expand in the original Review, not foreign stores."""
    data = load_inputs(delivery, required=required)
    return [data['reference'], data['document']['policy_ref'], data['document']['bindings_ref']] if data else []


def candidate(delivery, snapshot, cid, *, action, previous=None):
    contributions = [ref for ref, row in (delivery.allocations | delivery.capabilities).items() if row['node'] == cid]
    if cid not in delivery.active:
        raise CheckError('ui.candidate', 'UI selection must belong to the actual active candidate')
    return check(delivery, snapshot, kind='candidate', subject='candidate:' + snapshot['version'] + '/' + cid,
                 contributions=contributions, action=action, previous=previous)


def binding_rows(delivery, data):
    from ui_design.models import parse, validate as ui_validate
    from ui_design.errors import CheckError as UIError
    try:
        reference = data['document']['bindings_ref']
        return ui_validate('bindings', parse(delivery.store.ref(reference), 'UI bindings'), 'UI bindings')['bindings']
    except UIError as error:
        raise InputError('ui.binding-inputs', str(error)) from error


def bound_consumers(delivery, data, chosen):
    """Keep a fixed locator only while its original allocation is still exact.

    The current checked map owns the denominator and behaviors. A later map
    may add E/availability references without changing an allocation. Requiring
    its new Git locator in E would otherwise create a map/binding/E cycle.
    This reads only original business identities; shared UI validation still
    owns bindings, coverage, approvals and the complete design closure.
    """
    if (delivery.map_ref['path'] != delivery.context.vr + '/delivery-map.yaml' or
            parse_yaml(delivery.store.ref(delivery.map_ref)) != delivery.map):
        raise CheckError('ui.consumer-map', 'use the exact current reviewed delivery map')
    bindings = binding_rows(delivery, data)
    def identity(consumer):
        ref = consumer['record_ref']
        pointer = re.fullmatch(r'/(candidates|endpoints)/([0-9]+)/(allocation/([0-9]+)/id|expected_capabilities/([0-9]+))',
                               consumer.get('identity_pointer', ''))
        if ref['repository'] != 'project' or ref['path'] != delivery.map_ref['path'] or pointer is None:
            return None
        original = parse_yaml(delivery.store.read(ref['commit'], ref['path'], ref['sha256']))
        if any(original.get(key) != delivery.map.get(key) for key in ('schema_version', 'version', 'baseline')):
            return None
        group, index, _, allocation, capability = pointer.groups()
        if consumer['kind'] != ('contribution' if group == 'candidates' else 'endpoint'):
            return None
        try:
            node = original[group][int(index)]
            name = node['candidate_id' if group == 'candidates' else 'id']
            value = node['allocation'][int(allocation)] if allocation is not None else node['expected_capabilities'][int(capability)]
            if (value['id'] if allocation is not None else value) != consumer['subject']:
                return None
            return group, name, value
        except (KeyError, IndexError, TypeError):
            return None
    result = []
    for selected in chosen:
        expected = identity(selected['consumer'])
        matches = [row['consumer'] for row in bindings
                   if row['consumer']['kind'] == selected['consumer']['kind'] and
                   row['consumer']['subject'] == selected['consumer']['subject'] and
                   identity(row['consumer']) == expected] if expected is not None else []
        if len(matches) != 1:
            raise CheckError('ui.binding-selection', 'current contribution needs one fixed binding for its unchanged original allocation')
        result.append({**selected, 'consumer': matches[0]})
    return result


def input_contract(delivery, data, chosen, *, kind, subject, contributions):
    """Compare reviewed UI meaning, not the relocation of the enclosing map.

    The shared checker still validates every selected binding and approval.
    Only its original business owner may supply an already replayed admission
    as `previous`; there is no external existing/new switch in the VR context.
    """
    document = data['document']
    bindings = binding_rows(delivery, data)
    rows = []
    for selected in chosen:
        matches = [row for row in bindings if row['consumer'] == selected['consumer']]
        if len(matches) != 1:
            raise CheckError('ui.binding-selection', 'every independently selected consumer needs one exact fixed binding')
        # A fresh reviewed rationale may substantiate the same applicability;
        # it remains fully bound by the current engineering Review but does
        # not by itself change the approved UI implementation contract.
        rows.append({'consumer': {key: selected['consumer'][key] for key in ('kind', 'subject')},
                     'behaviors': sorted(selected['behaviors']),
                     'binding': {key: value for key, value in matches[0].items() if key not in ('consumer', 'rationale_ref')}})
    return {'subject': {'kind': kind, 'id': subject}, 'contributions': sorted(contributions),
            'policy': {key: document['policy_ref'][key] for key in ('path', 'sha256')},
            'rules': document['rules'], 'bindings': rows}


def candidate_contract(delivery, snapshot, cid):
    data = load_inputs(delivery)
    if data is None:
        return None
    contributions = [ref for ref, row in (delivery.allocations | delivery.capabilities).items() if row['node'] == cid]
    chosen = bound_consumers(delivery, data, selections(delivery, contributions))
    return input_contract(delivery, data, chosen, kind='candidate',
                          subject='candidate:' + snapshot['version'] + '/' + cid, contributions=contributions)


def local_refs(ui):
    return [ui[key] for key in ('inputs_ref', 'policy_ref', 'bindings_ref')] if ui else []


def execution_inputs(delivery, ui, expectations, *, previous=None):
    """Bind UI to the original actual E without relabeling its tested revision.

    Original E readers still own report/identity/content/coverage validation.
    A replayed prior acceptance may retain the same UI contract across a map
    relocation. Changed design meaning requires newly run evidence.
    """
    if ui is None:
        return None
    if ui['result']['ui_required'] and not expectations:
        raise CheckError('ui.execution-inputs', 'required UI delivery needs actual runtime evidence')
    choices = [local_refs(ui)]
    prior_executions = []
    if previous is not None and previous['contract'] == ui['contract']:
        choices.append(local_refs(previous))
        prior_executions = previous.get('executions', [])
    checked = []
    from .core import parse_yaml
    for expected in expectations:
        ref = expected['verification_ref']
        record = validate('verification_record', parse_yaml(delivery.store.ref(ref)))
        inputs = {row['path']: row for row in record['input_refs'] if 'sha256' in row}
        retained = [row['bindings'] for row in prior_executions if row['verification_ref'] == ref]
        # The immutable local selection record contains the exact policy and
        # binding refs. E consumes that fixed record, not a mutable sidecar's
        # later map locator. Any additional explicitly executed sidecar remains
        # byte-protected by the original E/content reader.
        matched = next((refs for refs in [*choices, *retained]
                        if inputs.get(refs[0]['path'], {}).get('sha256') == refs[0]['sha256']), None)
        if matched is None:
            raise CheckError('ui.execution-inputs', 'actual E does not include the fixed UI contract accepted for this delivery', refs=[ref])
        checked.append({'verification_ref': ref, 'bindings': matched})
    return {**ui, 'executions': checked}


class UIFailure(CheckError):
    """Keep the common checker output, including its failed current observation."""
    def __init__(self, result):
        diagnostics = result.get('diagnostics', [])
        code = diagnostics[0]['code'] if diagnostics else 'check'
        super().__init__('ui.' + code, 'shared UI check did not pass', unreadable=result['result'] == 'UNKNOWN')
        self.result = result

    def diagnostic(self):
        return {**super().diagnostic(), 'evidence': self.result}


def check(delivery, snapshot, *, kind, subject, contributions=(), action, previous=None, task=None):
    """Check only selections derived by the calling original business entry.

    The caller must retain its own BL/control/Review/request/E checks. Returning
    UI PASS never grants Propose, Apply, Merge, acceptance or release permission.
    """
    data = load_inputs(delivery)
    if data is None:
        if 'ui' in snapshot or task is not None and task[0].get('ui_behaviors'):
            raise CheckError('ui.adoption', 'not-adopted cannot accept an ignored UI context')
        return None
    runtime = snapshot.get('ui')
    if runtime is None:
        raise InputError('ui.context-required', 'select explicit local UI objects and authority revisions; no implicit fetch')
    validate('ui_runtime_context', runtime)
    repositories = dict(runtime['repositories'])
    root = delivery.store.root
    if 'project' in repositories:
        supplied = Path(repositories['project'])
        supplied = supplied if supplied.is_absolute() else root / supplied
        if supplied.resolve() != root.resolve():
            raise InputError('ui.repository', 'project alias must name the actual business repository')
    repositories['project'] = str(root)
    document = data['document']
    for revision in {snapshot['head_revision'], snapshot['metadata_revision']}:
        delivery.store.read(revision, POLICY, document['policy_ref']['sha256'])
    chosen = selections(delivery, list(contributions))
    if task is not None:
        association, reference = task
        if kind != 'task' or subject != association['subject']:
            raise CheckError('ui.task', 'UI task input must be the original task/PR subject')
        behaviors = association.get('ui_behaviors')
        if behaviors is None:
            raise CheckError('ui.task-applicability', 'original task association needs reviewed UI applicability')
        selected_business = {f"{row['requirement']}/r{delivery.requirements.records[row['requirement']]['value']['revision']}/{ac}"
                             for row in association['requirements'] for ac in row['acceptance']}
        allowed = {behavior for contribution in contributions for behavior in claims(delivery)[contribution]} & selected_business
        if not allowed <= set(behaviors):
            raise CheckError('ui.task-coverage', 'task UI selection must retain every associated contribution UI obligation')
        chosen = [{'consumer': {'kind': 'task', 'subject': subject,
                   'record_ref': {'repository': 'project', **association['task_ref']},
                   'association_ref': {'repository': 'project', **reference}},
                   'behaviors': behaviors, 'consumption': 'new'}]
    else:
        chosen = bound_consumers(delivery, data, chosen)
    if not chosen:
        raise CheckError('ui.empty-selection', 'an actual UI consumption entry cannot have an empty denominator')
    contract = input_contract(delivery, data, chosen, kind=kind, subject=subject, contributions=contributions)
    if previous is not None and previous['contract'] == contract:
        for selected in chosen:
            selected['consumption'] = 'existing'
    selected = {
        'schema_version': 'ui-snapshot/1', 'mode': snapshot['evaluation_mode'], 'action': action,
        'rules': document['rules'], 'repositories': repositories,
        'policy_ref': {'repository': 'project', **document['policy_ref']},
        'bindings_ref': {'repository': 'project', **document['bindings_ref']},
        'authorities': deepcopy(runtime['authorities']), 'external_files': runtime['external_files'],
        'subject': {'kind': kind, 'id': subject,
                    'head': {'repository': 'project', 'commit': snapshot['head_revision']},
                    'target': {'repository': 'project', 'commit': snapshot['target_revision']}},
        'selections': chosen,
    }
    from ui_design.api import check as check_ui
    result = check_ui(selected, root)
    if result['result'] != 'PASS':
        raise UIFailure(result)
    # Keep the foreign closure inside the common result. The original Review
    # binds its local fixed input record; foreign Git refs must never be fed to
    # the requirements store as though they belonged to the business repository.
    return {'contract': contract, 'inputs_ref': data['reference'], 'policy_ref': document['policy_ref'],
            'bindings_ref': document['bindings_ref'], 'snapshot': selected, 'result': result,
            'input_digest': digest(canonical_bytes({'inputs_ref': data['reference'],
                'selections': chosen, 'policy_ref': document['policy_ref'], 'rules': document['rules']}))}
