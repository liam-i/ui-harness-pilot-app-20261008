"""按固定所有者解析附件与持久派生链；不复制、转换或批准业务文件。"""
from __future__ import annotations

from graphlib import CycleError, TopologicalSorter
import re

from .core import canonical_bytes, digest, parse_yaml, relative_path
from .errors import CheckError, InputError
from .models import validate
from .reviews import evidence
from .sources import SourceIndex, fragment

VERSION = r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?"
MANIFEST = re.compile(r"requirements/versions/(" + VERSION + r")/(source|derived-assets)/manifest\.yaml\Z")
DERIVED = re.compile(r"DAS-[0-9]{3,}@[1-9][0-9]*\Z")
SOURCE = re.compile(r"intake-[0-9]{3,}/(?:AST|DOC|SRC)-[0-9]{3,}\Z")


class AssetIndex:
    """每次检查共享一个解析器；跨版本/修订引用带 manifest 的固定提交。"""

    def __init__(self, context, *, sources=None):
        self.context, self.store = context, context.store
        self._contexts = {(context.content_commit, context.version['version']): context}
        self._sources = {}
        if sources is not None:
            self._sources[(context.content_commit, context.version['version'])] = sources
        self._manifests, self._resolved, self._visiting = {}, {}, set()
        self.graph, self.uses = {}, []
        self._histories = {}

    def _owner(self, commit, version):
        key = (commit, version)
        if key not in self._contexts:
            self._contexts[key] = self.context.at(commit, version)
        return self._contexts[key]

    def _source_index(self, owner):
        key = (owner.content_commit, owner.version['version'])
        if key not in self._sources:
            # This is retained provenance, possibly produced before S1 decisions.
            # Adoption in the current baseline is checked by its current Reviews.
            self._sources[key] = SourceIndex(owner, require_decisions=False)
        return self._sources[key]

    def _manifest(self, owner):
        path = owner.vr + '/derived-assets/manifest.yaml'
        key = (owner.content_commit, path)
        if key not in self._manifests:
            data = validate('derived_assets', self.store.yaml(owner.content_commit, path), location=path)
            if data['version'] != owner.version['version']:
                raise CheckError('asset.owner', 'derived manifest belongs to a different Version')
            records, paths = {}, set()
            for item in data['assets']:
                name = item['id'] + '@' + str(item['revision'])
                if name in records or item['path'] in paths:
                    raise CheckError('asset.duplicate', 'duplicate derived revision or output path', refs=[name])
                relative_path(item['path'])
                if not item['path'].startswith(item['id'] + '/r' + str(item['revision']) + '/'):
                    raise CheckError('asset.output-path', 'output must live in its own DAS revision directory', refs=[name])
                records[name] = item
                paths.add(item['path'])
            self._manifests[key] = records
        return self._manifests[key]

    def _reference(self, value, owner):
        if isinstance(value, dict) and 'manifest_ref' in value:
            reference = value['manifest_ref']
            if '/trace/changes/' in reference['path']:
                from .change_assets import resolve_change_asset
                return resolve_change_asset(self, value)
            match = MANIFEST.fullmatch(reference['path'])
            if not match:
                raise CheckError('asset.manifest-path', 'identity reference needs the owning source or derived manifest')
            self.store.ref(reference)
            version, category = match.groups()
            if not value['identity'].startswith(version + '/'):
                raise CheckError('asset.owner', 'fixed identity and manifest owner disagree')
            owner = self._owner(reference['commit'], version)
            name = value['identity'][len(version) + 1:]
            expected = 'derived-assets' if DERIVED.fullmatch(name) else 'source' if SOURCE.fullmatch(name) else None
            if expected != category:
                raise CheckError('asset.identity', 'identity kind and fixed manifest disagree')
            return self._identity(name, owner)
        if isinstance(value, str):
            name = value.removeprefix(owner.version['version'] + '/')
            if not (DERIVED.fullmatch(name) or SOURCE.fullmatch(name)):
                raise CheckError('asset.identity', 'use an owner-local identity, or a full identity with a fixed manifest')
            return self._identity(name, owner)
        # A file reference represents actual engineering/decision material. Source and
        # derived files must retain their owning identity and derivation, not just bytes.
        if (re.match(r'requirements/versions/[^/]+/(source|derived-assets)/', value['path']) or
                re.match(r'openspec/changes/(?:archive/)?[^/]+/assets/', value['path'])):
            raise CheckError('asset.identity-required', 'source/derived material needs its owning manifest identity')
        data = self.store.ref(value)
        return {'identity': None, 'content_ref': value, 'bytes': data}

    def _identity(self, name, owner):
        if DERIVED.fullmatch(name):
            return self._derived(name, owner)
        sources = self._source_index(owner)
        identity = owner.version['version'] + '/' + name
        unit = sources.units.get(identity)
        source = sources.files.get(unit['file'] if unit else identity)
        if source is None:
            raise CheckError('asset.missing-identity', 'source identity is absent from the fixed owner', refs=[identity])
        result = {'identity': identity, 'content_ref': source['content_ref'], 'bytes': source['bytes']}
        if unit:
            result['selector'] = unit['selector']
            result['fragment_sha256'] = unit['fragment_sha256']
        return result

    def resolve_use(self, usage, *, owner=None, consumer=None, acceptance=None):
        validate('asset_use', usage)
        owner = owner or self.context
        if 'acceptance' in usage and (acceptance is None or not set(usage['acceptance']) <= set(acceptance)):
            raise CheckError('asset.acceptance', 'asset use names acceptance criteria outside its consuming Requirement')
        value = self._reference(usage['ref'], owner)
        selector = usage.get('selector', value.get('selector', {'kind': 'whole-file', 'description': 'complete fixed file'}))
        if 'selector' in usage and 'selector' in value and usage['selector'] != value['selector']:
            raise CheckError('asset.unit-selector', 'a SRC reference cannot silently select another fragment')
        selected = fragment(value['bytes'], selector)
        result = {k: v for k, v in value.items() if k != 'bytes'}
        result.update(selector=selector, fragment_sha256=digest(selected), purpose=usage['purpose'])
        if 'acceptance' in usage:
            result['acceptance'] = usage['acceptance']
        if consumer is not None:
            self.uses.append({'consumer': consumer, **result})
        return result

    def _derived(self, name, owner):
        manifest_path = owner.vr + '/derived-assets/manifest.yaml'
        key = (owner.content_commit, manifest_path, name)
        if key in self._visiting:
            raise CheckError('asset.cycle', 'derived inputs form a cycle', refs=[name])
        if key in self._resolved:
            return self._resolved[key]
        item = self._manifest(owner).get(name)
        if item is None:
            raise CheckError('asset.missing-identity', 'derived revision is absent from the fixed manifest', refs=[name])
        self._visiting.add(key)
        try:
            self._history(owner, name, item)
            identity = owner.version['version'] + '/' + name
            manifest_ref = {'commit': owner.content_commit, 'path': manifest_path,
                            'sha256': digest(self.store.read(owner.content_commit, manifest_path))}
            path = owner.vr + '/derived-assets/' + item['path']
            received_ref = {'commit': owner.content_commit, 'path': path,
                            'sha256': item.get('received_sha256', item['sha256'])}
            # Reuse exactly the same external-byte/LFS rules as source receipt.
            from .sources import fixed_content
            data, content_ref = fixed_content(self.store, received_ref, item['sha256'], item.get('external'))
            if not data:
                raise CheckError('asset.empty-output', 'persistent derived output is empty', refs=[identity])
            consumer = {'identity': identity, 'manifest_ref': manifest_ref}
            self.derivation_inputs(item, owner=owner, consumer=consumer, node=key)
            value = {'identity': identity, 'content_ref': content_ref, 'received_ref': received_ref,
                     'manifest_ref': manifest_ref,
                     'node': list(key), 'bytes': data}
            self._resolved[key] = value
            return value
        finally:
            self._visiting.remove(key)

    def derivation_inputs(self, item, *, owner, consumer, node):
        """One provenance DAG for Version and Change-owned persistent outputs."""
        evidence(self.store, item['review_ref'])
        if 'script_ref' in item['transformation']:
            evidence(self.store, item['transformation']['script_ref'])
        if any(isinstance(usage['ref'], str) for usage in item['inputs']):
            raise CheckError('asset.fixed-input', 'persistent derivation inputs need fixed file or manifest references')
        inputs = [self.resolve_use(usage, owner=owner, consumer=consumer) for usage in item['inputs']]
        self.graph[node] = [tuple(value['node']) for value in inputs if value.get('node') is not None]
        # Content reuse is legal; the graph concerns owner/revision identities.
        try:
            tuple(TopologicalSorter(self.graph).static_order())
        except CycleError as error:
            raise CheckError('asset.cycle', 'derived inputs form a cycle') from error
        return inputs

    def _history(self, owner, name, item):
        """登记后的同一修订不可改写；登记前的草稿字节不构成已审版本。"""
        if self.store.git('rev-parse', '--is-shallow-repository').strip() == b'true':
            raise InputError('git.shallow', 'derived revision retention requires full reachable history')
        path = owner.vr + '/derived-assets/manifest.yaml'
        output = owner.vr + '/derived-assets/' + item['path']
        key = (owner.content_commit, path, output)
        if key not in self._histories:
            self._histories[key] = self.store.git('rev-list', '--full-history', owner.content_commit,
                                                '--', path, output).decode().splitlines()
        for commit in self._histories[key]:
            if path not in self.store.tree(commit):
                continue
            document = validate('derived_assets', parse_yaml(self.store.read(commit, path)), location=path)
            if document['version'] != owner.version['version']:
                raise CheckError('asset.owner', 'historical manifest owner and path disagree', refs=[path, commit])
            previous = [row for row in document['assets'] if row['id'] + '@' + str(row['revision']) == name]
            if not previous:
                continue
            if len(previous) != 1 or canonical_bytes(previous[0]) != canonical_bytes(item):
                raise CheckError('asset.revision-overwrite', 'registered derived revision changed; append a new revision', refs=[name, commit])
            self.store.read(commit, output, item.get('received_sha256', item['sha256']))

    def check_manifest(self):
        """校验当前登记的全部派生物；没有 manifest 是合法的零派生操作。"""
        path = self.context.vr + '/derived-assets/manifest.yaml'
        actual = {p for p in self.store.tree(self.context.content_commit)
                  if p.startswith(self.context.vr + '/derived-assets/')}
        if not actual:
            return []
        if path not in actual:
            raise CheckError('asset.manifest-required', 'persistent derived files exist without their manifest')
        records = self._manifest(self.context)
        expected = {self.context.vr + '/derived-assets/' + row['path'] for row in records.values()} | {path}
        if actual != expected:
            raise CheckError('asset.inventory', 'derived manifest and registered output files disagree', refs=sorted(actual ^ expected))
        result = []
        for name in sorted(records):
            value = self._derived(name, self.context)
            result.append({k: v for k, v in value.items() if k != 'bytes'})
        return result
