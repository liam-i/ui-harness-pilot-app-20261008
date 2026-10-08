"""Narrow fixed design-data classification; never an exemption for design/**.

Only the original engineering Review can nominate files. The shared checker
must validate their approved closure; runtime/build input use remains engineering.
This fixed classification is not a current observer or engineering permission.
"""
from collections import defaultdict
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from .errors import CheckError, InputError
from .ui_integration import load_record, UIFailure


def passive(path, raw, files):
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in ('.md', '.json', '.yaml', '.yml', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg') or raw.startswith(b'#!'):
        return False
    if suffix in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
        return True  # the common decoder already verified bytes and dimensions
    text = raw.decode('utf-8')
    if re.search(r'<\s*(?:script|iframe|object|embed|foreignObject)\b|\bon\w+\s*=|javascript:', text, re.I):
        return False
    if suffix == '.svg':
        if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b|@import', text, re.I):
            return False
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return False
        for node in root.iter():
            for key, value in node.attrib.items():
                if key.rsplit('}', 1)[-1].lower() in ('href', 'src', 'base') and not value.startswith('#'):
                    return False
            for value in [*node.attrib.values(), node.text or '']:
                if any(not target.strip(' \t\r\n\"\'').startswith('#')
                       for target in re.findall(r'url\s*\(([^)]*)\)', value, re.I)):
                    return False
    if suffix == '.md':
        from .markdown_source import parse_document
        parsed = parse_document(raw)
        if parsed['unsupported']:
            return False
        for link in parsed['links']:
            target = urlsplit(unquote(link['parsed_target']))
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target.path))
            if target.scheme or target.netloc or target.path.startswith('/') or target.query:
                return False
            if target.path and resolved not in files:
                return False
    if suffix in ('.json', '.yaml', '.yml'):
        from ui_design.models import parse
        def external_pointer(value):
            if isinstance(value, dict):
                return (isinstance(value.get('$ref'), str) and not value['$ref'].startswith('#')) or any(external_pointer(v) for v in value.values())
            return isinstance(value, list) and any(external_pointer(v) for v in value)
        if external_pointer(parse(raw, path)):
            return False
    return True


def reviewed_metadata(context, snapshot, review):
    selected = review['engineering'].get('ui_metadata_refs', [])
    if not selected:
        return {}
    if context.configuration['ui_design'] != 'enabled':
        raise CheckError('ui.metadata-adoption', 'design metadata exemption requires adopted UI')
    engineering = review['engineering']
    reject_build_use(review, [*([engineering['code_ref']] if 'code_ref' in engineering else []),
                             *engineering.get('spec_refs', []), *engineering.get('shared_contract_refs', [])])
    reference = review['engineering'].get('ui_inputs_ref')
    if reference is None or 'ui' not in snapshot:
        raise CheckError('ui.metadata-inputs', 'design metadata needs fixed reviewed UI inputs and explicit restored objects')
    data = load_record(context, reference)['document']
    from ui_design.models import parse, validate
    from ui_design.errors import CheckError as UIError
    from ui_design.api import check
    try:
        bindings = validate('bindings', parse(context.store.ref(data['bindings_ref']), str(data['bindings_ref'])), 'bindings')['bindings']
    except UIError as error:
        raise InputError('ui.metadata-bindings', str(error)) from error
    repositories = dict(snapshot['ui']['repositories'])
    repositories['project'] = str(context.store.root)
    groups = defaultdict(list)
    for binding in bindings:
        consumer = binding['consumer']
        kind = {'contribution': 'candidate', 'endpoint': 'scope'}.get(consumer['kind'], consumer['kind'])
        subject = consumer['subject'] if kind in ('task', 'change') else 'metadata:' + kind
        groups[kind, subject].append({'consumer': consumer, 'behaviors': [row['behavior_ref'] for row in binding['coverage']], 'consumption': 'new'})
    allowed = {}
    def local(ref):
        root = Path(repositories[ref['repository']])
        root = root if root.is_absolute() else context.store.root / root
        return root.resolve() == context.store.root.resolve()
    for (kind, subject), selections in groups.items():
        checked = check({'schema_version': 'ui-snapshot/1', 'mode': 'historical', 'action': 'propose',
            'rules': data['rules'], 'repositories': repositories,
            'policy_ref': {'repository': 'project', **data['policy_ref']},
            'bindings_ref': {'repository': 'project', **data['bindings_ref']},
            'authorities': data['authorities'], 'external_files': snapshot['ui']['external_files'],
            'subject': {'kind': kind, 'id': subject,
                        'head': {'repository': 'project', 'commit': context.content_commit}},
            'selections': selections}, context.store.root)
        if checked['result'] != 'PASS':
            raise UIFailure(checked)
        for package in checked['packages']:
            for ref in [package['package_ref'], *package['files']]:
                if local(ref):
                    allowed[(ref['path'], ref['sha256'])] = ref
        for ref in checked['inputs']:
            if local(ref) and re.fullmatch(r'design/units/[^/]+/decisions/[^/]+\.(?:yaml|yml|json)', ref['path']):
                raw = context.store.read(ref['commit'], ref['path'], ref['sha256'])
                value = parse(raw, ref['path'])
                if isinstance(value, dict) and value.get('schema_version') == 'ui-decision/1':
                    allowed[(ref['path'], ref['sha256'])] = ref
    paths = {path for path, _ in allowed}
    result = {}
    for ref in selected:
        path = ref['path']
        if (path, ref['sha256']) not in allowed or path in result:
            raise CheckError('ui.metadata-closure', 'only unique files in a validated approved UI closure can be design metadata', refs=[ref])
        raw = context.store.ref(ref)
        if context.store.tree(ref['commit'])[path][0] != '100644' or not passive(path, raw, paths):
            raise CheckError('ui.metadata-active', 'draft, executable, unsupported or escaping content stays an engineering input', refs=[ref])
        # The exact reviewed bytes must be materialized; this is not permission
        # to edit an approved design file under a directory-wide exemption.
        for revision in {context.content_commit, snapshot['metadata_revision'], snapshot['head_revision']}:
            context.store.read(revision, path, ref['sha256'])
        result[path] = ref['sha256']
    return result


def reject_build_use(review, inputs):
    metadata = {ref['path'] for ref in review['engineering'].get('ui_metadata_refs', [])}
    used = {ref['path'] for ref in inputs} & metadata
    if used:
        raise CheckError('ui.metadata-build-input', 'a directly consumed build/runtime file cannot be exempted as design metadata', refs=sorted(used))
