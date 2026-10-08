"""Current UI composition from the original G4 receipt partition and real E.

No release index, package resolver or observer lives here. Original delivery
readers replay historical facts; the shared UI API checks selected current
consumers. An old package is not current merely because it appears in history.
"""
from copy import deepcopy

from .core import canonical_bytes, parse_json
from .delivery_trace import current_ref
from .errors import CheckError
from .integrated_receipt import read_integrated_receipt
from .models import validate
from .ui_integration import binding_rows, check, execution_inputs, load_inputs, local_refs

CHECKS = ('ui-current-composition', 'ui-runtime-coverage')


def _selected_prior(previous, contributions):
    """Project already replayed contribution facts; never invent an admission."""
    value = deepcopy(previous)
    contract = value['contract']
    if (len(contract['contributions']) != len(contract['bindings']) or
            not set(contributions) <= set(contract['contributions'])):
        raise CheckError('ui.composition-lineage', 'selected contributions lack their original delivered UI contract')
    rows = dict(zip(contract['contributions'], contract['bindings']))
    contract['contributions'] = sorted(contributions)
    contract['bindings'] = [rows[key] for key in sorted(contributions)]
    return value


def current_tasks(delivery, data, target):
    """The current reviewed sidecar selects task associations, not a task list.

    Obsolete task bindings stay in their old immutable input record. Keeping a
    task binding in the current selection declares a current consumer that G4
    must account for, including technical work without a product R/AC.
    """
    tasks = {}
    for row in binding_rows(delivery, data):
        consumer = row['consumer']
        if consumer['kind'] in ('contribution', 'endpoint'):
            continue
        if consumer['kind'] != 'task' or 'association_ref' not in consumer:
            raise CheckError('ui.composition-owner', 'requirements-layer UI must bind original contributions or actual task associations')
        reference = consumer['association_ref']
        if reference['repository'] != 'project' or not reference['path'].startswith(delivery.context.vr + '/trace/evidence/'):
            raise CheckError('ui.composition-task', 'task binding must retain this Version original local association')
        ref = {key: value for key, value in reference.items() if key != 'repository'}
        association = validate('tiny_association', parse_json(current_ref(delivery.store, ref, target)))
        if (association['subject'] != consumer['subject'] or
                {'repository': 'project', **association['task_ref']} != consumer['record_ref'] or
                association['version'] != delivery.context.version['version'] or
                association['delivery_line'] != delivery.context.version['delivery_line'] or
                consumer['subject'] in tasks):
            raise CheckError('ui.composition-task', 'current task binding and its original association disagree or repeat')
        current_ref(delivery.store, association['task_ref'], target)
        tasks[consumer['subject']] = {'reference': ref, 'association': association}
    return tasks


def prepare(delivery, snapshot, candidate, receipts):
    data = load_inputs(delivery)
    if data is None:
        return None
    tasks = current_tasks(delivery, data, candidate['code_revision'])
    selected_tasks, entries = set(), []
    action = 'release' if snapshot['phase'] == 'release' else 'version-admit'
    for row in receipts:
        receipt = read_integrated_receipt(delivery.context, row['context_ref'], row['result_ref'], allow_alternatives=True)
        origin, proof = receipt['snapshot'], receipt['evidence']
        previous = proof.get('ui')
        if previous is None:
            raise CheckError('ui.composition-lineage', 'adopted UI needs the actual delivered receipt UI facts')
        selected = sorted(row['contributions'])
        subject = previous['contract']['subject']
        task = None
        if subject['kind'] == 'task':
            entry = tasks.get(origin['subject'])
            if entry is None or entry['reference'] != origin['tiny_ref'] or origin['subject'] in selected_tasks:
                raise CheckError('ui.composition-task', 'select each current task once using its actually integrated association')
            association = entry['association']
            pairs = {(item['requirement'], ac) for item in association['requirements'] for ac in item['acceptance']}
            if not pairs <= delivery.coverage.keys():
                raise CheckError('ui.composition-task', 'task no longer selects the current scoped obligations')
            contributions = sorted({ref for pair in pairs for ref in delivery.coverage[pair]})
            if not set(selected) <= set(contributions):
                raise CheckError('ui.composition-task', 'receipt selects contributions outside its real task')
            task = association, entry['reference']
            selected_tasks.add(origin['subject'])
        else:
            if not selected:
                raise CheckError('ui.composition-empty', 'only a real task may have no product contribution')
            contributions = selected
            previous = _selected_prior(previous, contributions)
        ui = check(delivery, snapshot, kind=subject['kind'], subject=subject['id'],
                   contributions=contributions, action=action, previous=previous, task=task)
        if ui['contract'] != previous['contract']:
            raise CheckError('ui.composition-not-delivered', 'current design contract differs from the actually delivered selection; new binding alone is not delivery')
        # The candidate/build must retain this current immutable input record.
        # Explicit runtime files remain protected by the original build reader.
        reference = ui['inputs_ref']
        if not any((ref['path'], ref['sha256']) == (reference['path'], reference['sha256']) for ref in candidate['input_refs']):
            raise CheckError('ui.composition-build', 'actual candidate/build omits the selected fixed UI contract')
        entries.append({'subject': origin['subject'], 'contributions': selected,
                        'context_ref': row['context_ref'], 'result_ref': row['result_ref'], 'ui': ui})
    if selected_tasks != tasks.keys():
        raise CheckError('ui.composition-task-missing', 'current task consumers need their actual integrated receipts', refs=sorted(tasks.keys() - selected_tasks))
    return {'entries': entries, 'tasks': tasks,
            'scope': 'current UI consumers selected by actual G4 delivery/build; original package history is replayed separately'}


def execution_coverage(delivery, composition, expectations, executions):
    if composition is None:
        return None
    for entry in composition['entries']:
        relevant = []
        covered_behaviors = set()
        for expected in expectations:
            record = executions[canonical_bytes(expected['verification_ref'])]['record']
            business = any(row['contribution'] in entry['contributions'] for row in record['coverage'])
            tasks = [row for row in record.get('task_coverage', []) if row['subject'] == entry['subject']]
            if business or tasks:
                relevant.append(expected)
            for row in tasks:
                if row['tiny_ref'] != composition['tasks'][entry['subject']]['reference']:
                    raise CheckError('ui.composition-execution', 'current task execution selects a different fixed association')
                covered_behaviors.update(row['ui_behaviors'])
        if entry['subject'] in composition['tasks']:
            association = composition['tasks'][entry['subject']]['association']
            business = {f"{item['requirement']}/r{delivery.requirements.records[item['requirement']]['value']['revision']}/{ac}"
                        for item in association['requirements'] for ac in item['acceptance']}
            needed = set(association.get('ui_behaviors', [])) - business
            if not needed <= covered_behaviors:
                raise CheckError('ui.composition-execution', 'current Version E omits a task UI behavior', refs=sorted(needed - covered_behaviors))
        entry['ui'] = execution_inputs(delivery, entry['ui'], relevant)
    return composition


def review_refs(composition):
    return list({canonical_bytes(ref): ref for entry in (composition or {}).get('entries', [])
                 for ref in local_refs(entry['ui'])}.values())
