"""Read original final command runs; the existing project CI executes them.

The final Review judges whether project checks cover its real policy. This
reader checks input/run identities, mandatory Harness/OpenSpec results and
complete archived Task files, not semantic acceptance or hosted protection.
"""
from pathlib import PurePosixPath
import re

from .core import parse_json
from .delivery_trace import current_ref, metadata_scope
from .errors import CheckError, InputError
from .models import unique, validate
from .openspec_artifacts import _object, _rows, absolute
from .reviews import evidence
from .verification import _time


def engineering_paths(context, revision, candidate_id, control=None, *, delivery_subject=None):
    metadata, roots = metadata_scope(context, candidate_id, control, delivery_subject=delivery_subject)
    return {p for p in context.store.tree(revision) if p not in metadata and not p.startswith(roots)}


def unchanged_since(context, before, after, candidate_id, *, control=None, target=None, reviewed_metadata=(), delivery_subject=None):
    """Allow known evidence saves, checked engineering metadata or target bytes.

    Only the enclosing Gate can supply metadata already checked by its current
    engineering/impact Review. Final command inputs still bind these files.
    """
    store = context.store
    left, right = store.tree(before), store.tree(after)
    upstream = store.tree(target) if target else {}
    reviewed = set()
    for reference in reviewed_metadata:
        current_ref(store, reference, after)
        reviewed.add(reference['path'])
    changed = [p for p in sorted(engineering_paths(context, before, candidate_id, control, delivery_subject=delivery_subject) |
                                  engineering_paths(context, after, candidate_id, control, delivery_subject=delivery_subject))
               if p not in reviewed and left.get(p) != right.get(p) and
               (target is None or right.get(p) != upstream.get(p))]
    if changed:
        raise CheckError('final.engineering-changed', 'engineering content changed after the checked input; preserve it and use the applicable review/repair path', refs=changed)


def read_final_checks(context, reference, *, change, candidate_id, head_revision, target_revision, archive_revision,
                      control=None, delivery_subject=None):
    store = context.store
    observed = validate('final_checks_observation', parse_json(current_ref(store, reference, head_revision)))
    owner_matches = (observed.get('change') == change and 'subject' not in observed if delivery_subject is None else
                     change is None and candidate_id is None and observed.get('subject') == delivery_subject and 'change' not in observed)
    if not owner_matches or observed['target_revision'] != target_revision:
        raise CheckError('final.scope', 'final checks belong to another delivery subject or target')
    tested = observed['tested_revision']
    start = target_revision if delivery_subject is not None else archive_revision
    if not store.ancestor(start, tested) or not store.ancestor(tested, head_revision):
        raise CheckError('final.history', 'final checks must test the actual delivery history')
    root = str(absolute(observed['project_root']))
    if observed['entry_policy_run_ref'] in observed['project_run_refs']:
        raise CheckError('final.project-checks', 'the entry-policy process cannot also stand in for project engineering checks')
    original_processes = {}
    receipts = unique([observed['entry_policy_run_ref'], *observed['project_run_refs']], 'path', location='final command receipts')
    for ref in receipts.values():
        value = parse_json(current_ref(store, ref, head_revision))
        automatic = isinstance(value, dict) and value.get('kind') == 'automatic-execution'
        value = validate('execution_receipt' if automatic else 'command_run', value)
        if automatic and value['worktree_diff_ref'] is not None:
            raise CheckError('final.process-input', 'final project execution requires committed inputs')
        original_processes[ref['path']] = value
    inputs = unique(observed['input_refs'], 'path', location='final checked inputs')
    required = engineering_paths(context, tested, candidate_id, control, delivery_subject=delivery_subject)
    # A declared execution input is engineering data even in an evidence
    # namespace. Derive this from original receipts, not a caller's exemption.
    required.update(ref['path'] for value in original_processes.values() for ref in value['input_refs'])
    if set(inputs) != required:
        raise CheckError('final.input-set', 'final observation must bind all tracked engineering inputs, excluding only known delivery evidence', refs=sorted(set(inputs) ^ required))
    for ref in inputs.values():
        if ref['commit'] != tested:
            raise CheckError('final.input-revision', 'final inputs must select their actual tested revision')
        current_ref(store, ref, head_revision)
    unchanged_since(context, tested, head_revision, candidate_id, control=control, delivery_subject=delivery_subject)
    if not observed['policy_refs']:
        raise CheckError('final.policy', 'final Review needs the actual existing project check policy')
    for ref in observed['policy_refs']:
        if inputs.get(ref['path']) != ref:
            raise CheckError('final.policy', 'project check policy must be part of the tested engineering input set')
    refs = [reference, *observed['policy_refs']]

    def process(ref, *, entry=False):
        data = original_processes[ref['path']]
        automatic = data['kind'] == 'automatic-execution'
        if automatic and (entry or data['worktree_diff_ref'] is not None):
            raise CheckError('final.process-input', 'entry-policy needs its own real command; final execution must use committed inputs')
        if data['tested_revision'] != tested or data['source_root'] != root or data['cwd'] != '.':
            raise CheckError('final.process-input', 'original process does not belong to the selected project and tested input')
        if data['exit_code'] != 0 or _time(data['finished_at']) < _time(data['started_at']):
            raise CheckError('final.process-failed', 'final check failed or has invalid execution times')
        if entry and (PurePosixPath(data['command'][0]).name != 'node' or
                      data['command'][1:] != ['scripts/adapt-openspec-workflows.mjs', '--check']):
            raise CheckError('final.entry-policy', 'mandatory existing Harness entry check was not executed')
        for item in [*data['input_refs'], *data['identities'].values()]:
            current_ref(store, item, head_revision)
        for item in data['input_refs']:
            if item['commit'] != tested or inputs.get(item['path']) != item:
                raise CheckError('final.process-input', 'original process input does not match final tested project files')
        for key in (('report_ref',) if automatic else ('stdout_ref', 'stderr_ref')):
            item = {**data[key], 'commit': data[key].get('commit', ref['commit'])}
            current_ref(store, item, head_revision)
            refs.append(item)
        refs.extend([ref, *data['identities'].values()])
        return data

    policy = process(observed['entry_policy_run_ref'], entry=True)
    project_runs = [process(ref) for ref in observed['project_run_refs']]
    tree = store.tree(tested)
    archive_root = 'openspec/changes/archive/'
    archive_names = {p[len(archive_root):].split('/')[0] for p in tree if p.startswith(archive_root) and '/' in p[len(archive_root):]}
    if any(p.startswith(archive_root) and '/' not in p[len(archive_root):] and tree[p][0] == '120000' for p in tree):
        raise CheckError('final.archive-tasks', 'archive entries cannot be symbolic links')
    for name in archive_names:
        path = archive_root + name + '/tasks.md'
        if name.startswith('.') or path not in tree or tree[path][0] not in ('100644', '100755'):
            raise CheckError('final.archive-tasks', 'supported Feature archives require visible directories and regular Tasks files', refs=[path])
        # Match the fixed CLI/CI checkbox contract, not this Change's ID schema.
        rows = re.findall(r'^\s*[-*]\s*\[([\sxX])\]\s*(.*)', store.read(tested, path).decode('utf-8-sig'), re.M)
        if not rows or any(state.lower() != 'x' for state, _ in rows):
            raise CheckError('final.archive-tasks', 'an archived Feature has no identifiable Tasks or incomplete Tasks', refs=[path])
    expected_all = {('spec', p.split('/')[2]) for p in tree if p.startswith('openspec/specs/') and
                    len(p.split('/')) > 3 and not p.split('/')[2].startswith('.')}
    expected_all |= {('change', p.split('/')[2]) for p in tree if p.startswith('openspec/changes/') and
                     len(p.split('/')) > 3 and p.split('/')[2] != 'archive' and not p.split('/')[2].startswith('.')}
    outcomes = {}
    for kind, expected, required_flags in (
            ('all', expected_all, {'--all', '--strict', '--json'}),
            ('archived', {('change', name) for name in archive_names}, {'--archived', '--no-interactive', '--json'})):
        command = observed['openspec'][kind]
        args, report = list(command['args']), 'full'
        if '--report' in args:
            at = args.index('--report')
            if at + 1 < len(args):
                report = args[at + 1]
                del args[at:at + 2]
        flags = args[1:]
        if (args[:1] != ['validate'] or command['exit_code'] != 0 or report not in ('full', 'findings') or
                len(flags) != len(set(flags)) or not required_flags <= set(flags) <= required_flags | {'--no-interactive'}):
            raise CheckError('final.openspec-command', 'mandatory OpenSpec final validation failed or used different arguments', refs=[kind])
        ref = {**command['stdout_ref'], 'commit': command['stdout_ref'].get('commit', reference['commit'])}
        result = _object(parse_json(current_ref(store, ref, head_revision)), ('root', 'summary'), kind)
        if not isinstance(result['root'], dict) or result['root'].get('path') != root:
            raise InputError('final.openspec-output', 'original final CLI output has no project/item identity')
        rows = _rows(result.get('itemFindings') if report == 'findings' else result.get('items'), kind)
        if any(row.get('type') not in ('spec', 'change') or not isinstance(row.get('id'), str) for row in rows):
            raise InputError('final.openspec-output', 'final validation item has no supported type/string identity')
        selected = {(row['type'], row['id']) for row in rows}
        summary = _object(result['summary'], ('totals', 'byType'), kind + ' summary')
        totals = {'items':len(expected), 'passed':len(expected), 'failed':0}
        by_type = {name:{'items':sum(typ == name for typ, _ in expected),
                        'passed':sum(typ == name for typ, _ in expected), 'failed':0}
                   for name in (('change','spec') if kind == 'all' else ('change',))}
        if summary['totals'] != totals or summary['byType'] != by_type:
            raise CheckError('final.openspec-coverage', 'final validation totals do not cover the actual Git item set', refs=[kind])
        if report == 'findings':
            expected_report = {'kind':'validation-findings','version':'1.0','scope':kind,
                               'returnedItems':len(rows),'totalItems':len(expected)}
            complete = result.get('report') == expected_report and len(selected) == len(rows) and selected <= expected
        else:
            complete = len(rows) == len(expected) and selected == expected
        if (not complete or any(row.get('valid') is not True or
                any(i.get('level') == 'ERROR' for i in _rows(row.get('issues', []), kind + ' issues')) for row in rows)):
            raise CheckError('final.openspec-coverage', 'final CLI report omits an actual Spec/Change/archive or contains a failure', refs=[kind])
        outcomes[kind] = sorted(expected)
        refs.append(ref)
    return {'observation_ref': reference, 'tested_revision': tested, 'target_revision': target_revision,
            'project_root': root, 'project_runs': project_runs, 'entry_policy': policy,
            'openspec_items': outcomes, 'input_refs': observed['input_refs'], 'evidence_refs': refs,
            'scope': 'actual local command and OpenSpec input/result checks; project-check completeness needs final Review; no hosted required-check claim'}
