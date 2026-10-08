"""Fixed execution evidence: parse actual reports without running tests or granting a Gate.

The caller supplies the tested revision and execution identities it needs. Evidence
from another revision is not implicitly promoted by ancestry or an old PASS.
Semantic coverage and any later applicability decision remain Review duties.
"""
from datetime import datetime
from pathlib import PurePosixPath
import re
from xml.etree import ElementTree

from .core import MAX_DOCUMENT_BYTES, canonical_bytes, digest, parse_json, parse_yaml
from .errors import CheckError, InputError
from .models import unique, validate
from .reviews import decision, evidence
from .worktree import read_capture


def junit(data):
    """Read a bounded UTF-8 JUnit report; count leaf results, not XML summaries."""
    try:
        raw = data.decode('utf-8-sig')
        if len(data) > MAX_DOCUMENT_BYTES or re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', raw, re.I):
            raise ValueError('oversized report or DTD/entity declaration')
        root = ElementTree.fromstring(raw)
    except (UnicodeError, ValueError, ElementTree.ParseError) as error:
        raise InputError('verification.report-unreadable', str(error)) from error
    if root.tag not in ('testsuites', 'testsuite'):
        raise InputError('verification.report-format', 'expected an unnamespaced JUnit testsuites/testsuite root')
    cases = {}

    def walk(node, depth=0):
        if depth > 64:
            raise InputError('verification.report-unreadable', 'JUnit nesting exceeds 64')
        counts = {'discovered': 0, 'executed': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
        for child in node:
            if child.tag in ('testsuites', 'testsuite'):
                nested = walk(child, depth + 1)
                for key in counts:
                    counts[key] += nested[key]
            elif child.tag == 'testcase':
                key = (child.get('classname', ''), child.get('name'), child.get('file'))
                if not key[1] or key in cases:
                    raise CheckError('verification.case-identity', 'missing or duplicate report selector', refs=[list(key)])
                tags = [x.tag for x in child]
                if any(tag not in ('skipped', 'failure', 'error', 'system-out', 'system-err', 'properties') for tag in tags):
                    raise InputError('verification.report-format', 'unsupported testcase result element', refs=[list(key)])
                if child.get('status', 'run') not in ('run', 'passed', 'failed', 'skipped', 'notrun'):
                    raise InputError('verification.report-format', 'unsupported testcase status', refs=[list(key)])
                skipped = 'skipped' in tags or child.get('status') in ('skipped', 'notrun')
                failed = 'failure' in tags or 'error' in tags or child.get('status') == 'failed'
                if skipped and failed:
                    raise CheckError('verification.report-result', 'one testcase is both skipped and failed', refs=[list(key)])
                state = 'skipped' if skipped else 'failed' if failed else 'passed'
                cases[key] = state
                counts['discovered'] += 1
                counts[state] += 1
                counts['executed'] += int(not skipped)
            elif child.tag not in ('properties', 'system-out', 'system-err'):
                raise InputError('verification.report-format', 'unsupported JUnit element: ' + child.tag)
        # Counters, when present, cannot hide missing/failed leaf cases. Failure
        # and error counts are combined because both are unsuccessful execution.
        for name, expected in (('tests', counts['discovered']), ('skipped', counts['skipped'])):
            if name in node.attrib and node.attrib[name] != str(expected):
                raise CheckError('verification.report-count', 'JUnit summary differs from actual cases', refs=[name])
        if 'failures' in node.attrib and 'errors' in node.attrib:
            values = [node.attrib[x] for x in ('failures', 'errors')]
            if any(not re.fullmatch(r'[0-9]+', x) for x in values) or sum(map(int, values)) != counts['failed']:
                raise CheckError('verification.report-count', 'JUnit unsuccessful count differs from actual cases')
        return counts

    counts = walk(root)
    return cases, counts


def _time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError('timezone required')
        return result
    except ValueError as error:
        raise CheckError('verification.time', 'execution time must be an ISO timestamp with timezone') from error


def automatic_receipt(store, record, data):
    """Bind the E index to original captured process metadata and its report.

    Authentic capture/CI provenance remains the controlled runner's duty. This
    check rejects relabeling an existing receipt, not deliberate fabrication of
    every input by an actor who also controls the claimed evidence source.
    """
    receipt = validate('execution_receipt', parse_json(data), location=record['execution_ref']['path'])
    for key in ('tested_revision', 'identities', 'started_at', 'finished_at', 'actor'):
        if receipt[key] != record[key]:
            raise CheckError('verification.receipt-binding', 'E differs from original execution metadata: ' + key)
    def fixed(ref):
        return {**ref, 'commit': ref.get('commit', record['execution_ref']['commit'])} if ref is not None else None
    if fixed(receipt['worktree_diff_ref']) != record['worktree_diff_ref']:
        raise CheckError('verification.receipt-binding', 'E differs from the original worktree input reference')
    inputs = [{**item, 'content_ref': fixed(item['content_ref'])} if 'content_ref' in item else item for item in receipt['input_refs']]
    if sorted(map(canonical_bytes, inputs)) != sorted(map(canonical_bytes, record['input_refs'])):
        raise CheckError('verification.receipt-binding', 'E relabels the original tested input files')
    run = record['automatic']
    for key in ('command', 'cwd', 'source_root', 'format', 'exit_code'):
        if receipt[key] != run[key]:
            raise CheckError('verification.receipt-binding', 'E differs from original process/report context: ' + key)
    report = {**receipt['report_ref'], 'commit': receipt['report_ref'].get('commit', record['execution_ref']['commit'])}
    if report != run['report_ref']:
        raise CheckError('verification.receipt-binding', 'E selects another report than its original execution receipt')
    store.ref(report)


def check_execution(context, reference, *, tested_revision, identities, worktree_diff_ref=None, require_pass=True, engineering_review=None):
    """Validate one immutable E against explicit caller expectations.

    This does not decide BL effectiveness, integration, dependency readiness,
    approval, or whether the chosen tests substantiate an AC's meaning.
    """
    store = context.store
    validate('ref', reference)
    data = store.ref(reference)
    record = validate('verification_record', parse_yaml(data), location=reference['path'])
    if engineering_review is not None:
        from .ui_metadata import reject_build_use
        reject_build_use(engineering_review, [*record['input_refs'], *record['identities'].values()])
    expected_path = context.vr + '/trace/verification/' + record['id'] + '.yaml'
    if (reference['path'] != expected_path or record['version'] != context.version['version'] or
            record['delivery_line'] != context.version['delivery_line']):
        raise CheckError('verification.owner', 'E identity, owning Version and delivery line disagree')
    for revision in store.git('log', '--format=%H', reference['commit'], '--', expected_path).decode().splitlines():
        if expected_path in store.tree(revision) and digest(store.read(revision, expected_path)) != reference['sha256']:
            raise CheckError('verification.history', 'an existing E was rewritten; a new execution needs a new E ID')
    store.commit(tested_revision)
    store.commit(record['tested_revision'])
    if record['tested_revision'] != tested_revision:
        raise CheckError('verification.stale-revision', 'execution does not target the requested tested revision')
    if record['worktree_diff_ref'] != worktree_diff_ref:
        raise CheckError('verification.stale-worktree', 'execution does not target the explicitly requested worktree snapshot; dirty PASS is not committed PASS')
    captured = read_capture(store, worktree_diff_ref, base_revision=tested_revision) if worktree_diff_ref is not None else None
    if _time(record['finished_at']) < _time(record['started_at']):
        raise CheckError('verification.time', 'execution finishes before it starts')
    validate('execution_identities', identities)
    if identities != record['identities']:
        raise CheckError('verification.stale-identities', 'build, dependencies, configuration, environment or data identities differ')
    for ref in record['identities'].values():
        evidence(store, ref)
    execution_data = evidence(store, record['execution_ref'])
    inputs = unique(record['input_refs'], 'path', location=record['id'])
    for ref in inputs.values():
        if 'content_ref' in ref:
            if captured is None or captured['contents'].get(ref['path']) != ref['content_ref']:
                raise CheckError('verification.captured-input', 'input does not select the captured bytes at this actual runtime path', refs=[ref])
            if captured['files'][ref['path']]['mode'] not in ('100644', '100755'):
                raise InputError('verification.symlink-input', 'captured symlink text cannot establish the executed source or test definition bytes', refs=[ref])
            store.ref(ref['content_ref'])
        else:
            if ref['commit'] != tested_revision:
                raise CheckError('verification.input-revision', 'code/test/config inputs must come from the tested commit', refs=[ref])
            store.ref(ref)
            if captured is not None and (ref['path'] not in captured['files'] or
                    captured['files'][ref['path']]['sha256'] != ref['sha256'] or ref['path'] in captured['contents']):
                raise CheckError('verification.captured-input', 'base commit reference hides a changed/deleted captured input', refs=[ref])
    cases = unique(record['cases'], 'id', location=record['id'])
    for item in cases.values():
        if item['definition_ref'] not in record['input_refs']:
            raise CheckError('verification.definition', 'case definition is absent from the fixed tested inputs', refs=[item['id']])
    for item in record['coverage']:
        if not set(item['case_ids']) <= cases.keys():
            raise CheckError('verification.coverage-case', 'coverage references an undeclared test/step ID')
        if 'requirement' in item:
            r = validate('requirement', parse_yaml(store.ref(item['record_ref'])))
            store.ref(item['configuration_ref'])
            if r['revision'] != item['revision'] or item['record_ref']['path'] != 'requirements/items/' + item['requirement'] + '.yml':
                raise CheckError('verification.requirement', 'coverage must select the exact R identity and revision')
            if not set(item['acceptance']) <= {x['id'] for x in r['acceptance']}:
                raise CheckError('verification.acceptance', 'coverage contains an absent acceptance criterion')
    for item in record.get('task_coverage', []):
        if not set(item['case_ids']) <= cases.keys():
            raise CheckError('verification.coverage-case', 'task coverage references an undeclared test/step ID')
        association = validate('tiny_association', parse_json(store.ref(item['tiny_ref'])))
        if (association['subject'] != item['subject'] or
                (association['version'], association['delivery_line']) != (record['version'], record['delivery_line']) or
                not set(item['ui_behaviors']) <= set(association.get('ui_behaviors', []))):
            raise CheckError('verification.task-identity', 'task evidence must select its actual association and reviewed UI behaviors')
        for ref in (item['tiny_ref'], association['task_ref']):
            if inputs.get(ref['path'], {}).get('sha256') != ref['sha256']:
                raise CheckError('verification.task-inputs', 'actual task evidence must execute with its fixed task and association inputs')
    if record['kind'] == 'automatic':
        if 'automatic' not in record or 'manual' in record or any('selector' not in item for item in cases.values()):
            raise CheckError('verification.kind', 'automatic evidence requires selectors and the automatic report contract')
        run = record['automatic']
        if run['format'] != 'junit':
            raise InputError('verification.report-format', 'unsupported automatic report format')
        automatic_receipt(store, record, execution_data)
        source_root = PurePosixPath(run['source_root'])
        if not source_root.is_absolute() or str(source_root) != run['source_root'] or '..' in source_root.parts or '\\' in run['source_root']:
            raise InputError('verification.report-root', 'this report reader requires the canonical POSIX execution source root')
        results, counts = junit(evidence(store, run['report_ref']))
        if counts != run['counts']:
            raise CheckError('verification.report-count', 'E counts differ from actual report cases')
        def selector(item):
            return (item['selector']['classname'], item['selector']['name'],
                    str(source_root / item['definition_ref']['path']))
        selectors = [selector(item) for item in cases.values()]
        if len(selectors) != len(set(selectors)):
            raise CheckError('verification.case-alias', 'different stable IDs cannot duplicate one report selector')
        selected = {item['id']: results.get(selector(item), 'not-found')
                    for item in cases.values()}
        passed = (run['exit_code'] == 0 and counts['executed'] > 0 and counts['failed'] == 0 and
                  all(state == 'passed' for state in selected.values()))
    else:
        if 'manual' not in record or 'automatic' in record or any('selector' in item for item in cases.values()):
            raise CheckError('verification.kind', 'manual evidence requires actual observations and no automatic selectors')
        run = record['manual']
        decision(context, run['acceptance'], roles={'qa-owner', 'product-owner'})
        observations = unique(run['observations'], 'case_id', location=record['id'])
        if observations.keys() != cases.keys():
            raise CheckError('verification.manual-coverage', 'manual observations must match all declared step IDs')
        for item in observations.values():
            evidence(store, item['evidence_ref'])
        selected = {key: value['result'] for key, value in observations.items()}
        counts = None
        passed = all(value == 'passed' for value in selected.values())
    if (record['result'] == 'passed') != passed:
        raise CheckError('verification.result', 'recorded result disagrees with the actual required cases')
    if require_pass and not passed:
        raise CheckError('verification.not-passed', 'required execution is failed, skipped or absent', refs=[record['id'], selected])
    return {'record': record, 'reference': reference, 'cases': selected, 'counts': counts,
            'scope': 'fixed execution only; coverage meaning and current delivery applicability require separate checks'}
