"""Rebuild change impact from both fixed graphs; never approve or change state.

This is a review worklist, not an execution dependency graph. In particular,
parent/child and shared implementation propagation do not schedule work. Missing
Trace coverage remains explicit even when all known consumers were found.
"""
from collections import defaultdict, deque
from contextlib import ExitStack

from .core import canonical_bytes, digest, parse_yaml
from .errors import CheckError, InputError
from .models import validate
from .requirements import RequirementIndex
from .runtime import implementation_manifest


def fixed(store, commit, path):
    return {'commit': commit, 'path': path, 'sha256': digest(store.read(commit, path))}


class ImpactGraph:
    def __init__(self, context):
        self.context, self.store = context, context.store
        self.version = context.version['version']
        self.nodes, self.edges, self.path_nodes = {}, {}, defaultdict(set)
        self.diagnostics = []

    def node(self, identity, kind, value, refs=()):
        row = self.nodes.setdefault(identity, {'id': identity, 'kind': kind, 'values': [], 'refs': []})
        if row['kind'] != kind:
            raise CheckError('impact.identity', 'impact node has conflicting types', refs=[identity])
        if value not in row['values']:
            row['values'].append(value)
        for ref in refs:
            validate('ref', ref)
            self.store.ref(ref)
            if ref not in row['refs']:
                row['refs'].append(ref)
            self.path_nodes[ref['path']].add(identity)
        return identity

    def file(self, ref):
        return self.node('file:' + ref['path'], 'file', {'sha256': ref['sha256']}, [ref])

    def execution_file(self, ref):
        if 'content_ref' not in ref:
            return self.file(ref)
        identity = self.node('file:' + ref['path'], 'file',
                             {'sha256': ref['content_ref']['sha256']}, [ref['content_ref']])
        self.path_nodes[ref['path']].add(identity)
        return identity

    def edge(self, source, target, reason, *, propagate=True, detail=None):
        value = {'source': source, 'target': target, 'reason': reason,
                 'propagate': propagate, 'detail': detail}
        self.edges[digest(canonical_bytes(value))] = value

    def pair(self, left, right, reason):
        self.edge(left, right, reason)
        self.edge(right, left, reason)

    def requirement(self, uid):
        return 'requirement:' + self.version + '/' + uid

    def ac(self, uid, ac):
        return 'scope:' + self.version + '/' + uid + '/' + ac

    def provider(self, identity, candidates):
        return ('candidate:' if identity in candidates else 'provider:') + self.version + '/' + identity

    def _condition(self, row):
        when = row.get('when', 'always')
        if when == 'always':
            return True
        if when is None or when['outcome'] == 'unknown':
            self.diagnostics.append({'rule_id': 'impact.condition-unknown', 'object': row['id']})
            return True
        self.store.ref(when['decision_ref'])
        return when['outcome'] == 'true'

    def build(self):
        r = RequirementIndex(self.context)
        mapping = self.context.read('delivery-map.yaml', 'delivery_map')
        plan = self.context.read('verification-plan.yaml', 'verification_plan')
        if mapping['version'] != self.version or plan['version'] != self.version:
            raise CheckError('impact.owner', 'impact map/plan must belong to the selected Version')
        for uid, info in sorted(r.records.items()):
            rid = self.node(self.requirement(uid), 'requirement',
                            {'record': info['value'], 'membership': r.included[uid]},
                            [info['record_ref'], info['configuration_ref']])
            for aid, value in info['acs'].items():
                acid = self.node(self.ac(uid, aid), 'acceptance', value, [info['record_ref']])
                self.edge(rid, acid, 'requirement-acceptance')
            for source in info['value']['source_refs']:
                if source['role'] == 'origin':
                    unit = r.source_unit(source['unit'], info)
                    owner = r.context.at(info['record_ref']['commit'], unit['id'].split('/')[0])
                    sources = r.assets._source_index(owner)
                    self._unit(unit, sources)
                    sid = 'source:' + unit['id']
                else:
                    owner = r.context.at(info['record_ref']['commit'], source['decision'].split('/')[0])
                    questions = r.question_index(owner)
                    sid = self.file(fixed(self.store, owner.content_commit, questions.paths[source['decision']]))
                for aid in source.get('acceptance', info['acs']):
                    self.edge(sid, self.ac(uid, aid), 'source-obligation')
            for source in r.included[uid]['source_confirmations']:
                self._unit(r.sources.units[source['unit']], r.sources)
                for aid in source['acceptance']:
                    self.edge('source:' + source['unit'], self.ac(uid, aid), 'current-confirmation')
            for usage in info['value']['asset_refs']:
                value = r.assets.resolve_use(usage, owner=r.asset_owner(info),
                    acceptance=info['acs'], consumer={'requirement': uid})
                for aid in usage.get('acceptance', info['acs']):
                    self.edge(self.file(value['content_ref']), self.ac(uid, aid), 'asset-consumer')
            parent = info['value']['hierarchy']['parent']
            if parent is not None:
                parent_info, scope = r.relation_target(self.context, parent)
                pid = self._related(parent_info, scope)
                self.pair(rid, pid, 'hierarchy-review-only')
            for relation in info['value']['constraints'] + info['value']['relationships']:
                target, scope = r.relation_target(self.context, relation.get('target', relation.get('requirement')))
                tid = self._related(target, scope)
                kind = relation.get('type', 'constraint')
                informational = kind in ('related-to', 'conflicts-with')
                active = self._condition(relation) if not informational else False
                target_acs = relation.get('target_acceptance', relation.get('acceptance', target['acs']))
                for aid in relation.get('applies_to', info['acs']):
                    for tac in target_acs:
                        source_id = self.ac(target['uid'], tac) if tid == self.requirement(target['uid']) else tid
                        self.edge(source_id, self.ac(uid, aid), 'business-' + kind,
                                  propagate=active, detail=relation)
        # Unadopted source files still appear in the diff, without fabricated consumers.
        for unit in r.sources.units.values():
            self._unit(unit, r.sources)
        self._source_context(r.sources)
        for qid, question in r.questions.values.items():
            reference = fixed(self.store, self.context.content_commit, r.questions.paths[qid])
            qnode = self.node('question:' + qid, 'question', question, [reference])
            for uid in r.questions.impact(qid)['affected_requirements']:
                self.edge(qnode, self.requirement(uid), 'named-question-impact')
        candidates = {row['candidate_id']: row for row in mapping['candidates']}
        providers = {row['id']: row for row in mapping['endpoints']}
        if len(candidates) != len(mapping['candidates']) or len(providers) != len(mapping['endpoints']) or candidates.keys() & providers.keys():
            raise CheckError('impact.node-identity', 'delivery nodes must have unique identities')
        allocations = {}
        for cid, row in (candidates | providers).items():
            node = self.provider(cid, candidates)
            self.node(node, 'candidate' if cid in candidates else 'provider', row)
            if row.get('change_name'):
                change = self.node('change:' + row['change_name'], 'change', {'name': row['change_name']})
                self.pair(node, change, 'candidate-change')
            for allocation in row['allocation']:
                contribution = 'contribution:' + self.version + '/' + cid + '/' + allocation['id']
                self.node(contribution, 'contribution', allocation)
                allocations[cid + '/' + allocation['id']] = contribution
                self.pair(node, contribution, 'provider-contribution')
                # Historical endpoint allocation is not a current scoped obligation.
                if 'requirement_ref' in allocation:
                    target = r.historical(allocation['requirement_ref'])
                    self.pair(self._related(target, target['owner']), contribution, 'historical-provider')
                else:
                    for aid in allocation['acceptance']:
                        self.pair(self.ac(allocation['requirement'], aid), contribution, 'allocated-contribution')
            for capability in row.get('expected_capabilities', []):
                name = cid + '/capability:' + capability
                contribution = self.node('contribution:' + self.version + '/' + name,
                                         'contribution', {'capability': capability})
                allocations[name] = contribution
                self.pair(node, contribution, 'technical-contribution')
            for resource in row.get('shared_resources', []):
                shared = self.node('resource:' + resource, 'shared-resource', resource)
                self.pair(node, shared, 'shared-contract-review')
        for cid, row in candidates.items():
            for edge in row['predecessor_edges']:
                provider = edge.get('candidate', edge.get('endpoint'))
                self.edge(self.provider(provider, candidates), self.provider(cid, candidates),
                          'delivery-' + edge['kind'], propagate=self._condition(edge), detail=edge)
        for row in plan['obligations']:
            oid = self.node('obligation:' + self.version + '/' + row['id'], 'verification-obligation', row)
            for contribution in row.get('contributions', [row['capability_ref']] if 'capability_ref' in row else []):
                self.pair(allocations.get(contribution, 'missing-contribution:' + contribution), oid,
                          'verification-contribution')
        self._traces(r, candidates, allocations)
        # AssetIndex records the exact transitive inputs used by Version/Change derivation.
        outputs = {canonical_bytes({'identity': row['identity'], 'manifest_ref': row['manifest_ref']}): row['content_ref']
                   for row in r.assets._resolved.values()}
        for usage in r.assets.uses:
            owner = usage['consumer']
            output = outputs.get(canonical_bytes(owner))
            if output is not None:
                self.edge(self.file(usage['content_ref']), self.file(output), 'derived-input')
        for identity, row in self.nodes.items():
            row['values'].sort(key=canonical_bytes)
            row['refs'].sort(key=canonical_bytes)
        for edge in self.edges.values():
            for endpoint in (edge['source'], edge['target']):
                if endpoint not in self.nodes:
                    self.diagnostics.append({'rule_id': 'impact.unresolved-endpoint', 'object': endpoint})
        return self

    def _related(self, info, scope):
        if (scope.version['version'], scope.version['delivery_line'], scope.content_commit) == (
                self.version, self.context.version['delivery_line'], self.context.content_commit):
            return self.requirement(info['uid'])
        identity = 'historical:' + digest(canonical_bytes([info['record_ref'], info['configuration_ref'],
                    scope.version['version'], scope.version['delivery_line'], scope.content_commit]))
        self.node(identity, 'historical-requirement', {'requirement': info['uid'],
            'version': scope.version['version'], 'line': scope.version['delivery_line'],
            'scope_commit': scope.content_commit}, [info['record_ref'], info['configuration_ref']])
        return identity

    def _unit(self, unit, sources):
        identity = self.node('source:' + unit['id'], 'source-unit', unit)
        source = sources.files[unit['file']]
        self.edge(self.file(source['content_ref']), identity, 'source-fragment')
        for usage in unit['asset_context']:
            self.edge(self.file(sources.files[usage['asset']]['content_ref']), identity, 'document-asset-context')
        if unit.get('supersedes_unit'):
            self.pair(identity, 'source:' + unit['supersedes_unit'], 'source-replacement-review')
        if unit.get('duplicate_of'):
            self.pair(identity, 'source:' + unit['duplicate_of'], 'duplicate-interpretation-review')
        for uid in unit.get('context_requirements', []):
            self.edge(identity, self.requirement(uid), 'declared-source-context')

    def _source_context(self, sources):
        # A full new package can omit a former path; a delta can replace only a
        # referenced image. Neither operation changes the old promise by itself.
        # Logical package paths connect the two fixed inventories for review.
        latest = sources.manifest['intakes'][-1]['id']
        for path, identity in sorted(sources._namespaces[latest].items()):
            source = sources.files[identity]
            active = self.node('effective-source:' + path, 'effective-source',
                               {'identity': identity, 'sha256': source['sha256']})
            self.pair(active, self.file(source['content_ref']), 'effective-source-review')
        for intake in sources.intakes.values():
            for replacement in intake['replacements']:
                old = self.file(sources.files[replacement['previous']]['content_ref'])
                proposed = self.node('source-replacement:' + intake['id'] + '/' + replacement['previous'],
                                     'source-replacement', replacement, [replacement['decision_ref']])
                self.pair(proposed, old, 'source-replacement-review')
                if replacement['current'] is not None:
                    new = self.file(sources.files[replacement['current']]['content_ref'])
                    self.pair(proposed, new, 'source-replacement-review')
        for link in sources.effective_links:
            if link['target'] in sources.files:
                self.edge(self.file(sources.files[link['target']]['content_ref']),
                          self.file(sources.files[link['document']]['content_ref']),
                          'effective-document-link', detail=link)

    def _traces(self, r, candidates, allocations):
        revision = self.context.snapshot['metadata_revision']
        prefix = self.context.vr + '/trace/changes/'
        for path in sorted(self.store.tree(revision)):
            if not path.startswith(prefix) or not path.endswith('.yaml'):
                continue
            ref = fixed(self.store, revision, path)
            trace = validate('planning_trace', parse_yaml(self.store.ref(ref)), location=path)
            if (trace['version'], trace['delivery_line']) != (self.version, self.context.version['delivery_line']):
                raise CheckError('impact.trace-owner', 'Trace must retain its original Version/line', refs=[ref])
            cid = trace['candidate_id']
            if path != prefix + cid + '.yaml':
                raise CheckError('impact.trace-path', 'Trace path and candidate disagree', refs=[ref])
            change = self.node('change:' + trace['change'], 'change', {'name': trace['change']})
            tid = self.node('trace:' + self.version + '/' + cid, 'trace', trace, [ref])
            self.pair(tid, change, 'trace-change')
            self.pair(self.provider(cid, candidates), change, 'candidate-change')
            for link in trace['links']:
                contribution = allocations.get(link['contribution'], 'missing-contribution:' + link['contribution'])
                for spec in link['specs']:
                    self.pair(contribution, self.file(spec['file_ref']), 'trace-spec')
                for task in link['tasks']:
                    task_id = self.node('task:' + trace['change'] + '/' + task, 'task', task)
                    self.pair(contribution, task_id, 'trace-task')
                for oid in link['verification_obligations']:
                    self.pair(contribution, 'obligation:' + self.version + '/' + oid, 'trace-verification')
            delivery = trace.get('delivery', {})
            for implementation in delivery.get('implementations', []):
                for reference in implementation['file_refs']:
                    self.pair('task:' + trace['change'] + '/' + implementation['task_id'],
                              self.file(reference), 'trace-implementation')
            for verification in delivery.get('verification', []):
                evidence_ref = verification['verification_ref']
                record = validate('verification_record', parse_yaml(self.store.ref(evidence_ref)))
                eid = self.file(evidence_ref)
                self.pair('obligation:' + self.version + '/' + verification['obligation_id'], eid, 'trace-evidence')
                for case in record['cases']:
                    self.pair(eid, self.execution_file(case['definition_ref']), 'test-definition')
                for execution_input in record['input_refs']:
                    self.edge(self.execution_file(execution_input), eid, 'verification-input')
                for execution_identity in record['identities'].values():
                    self.edge(self.file(execution_identity), eid, 'verification-environment')
            for usage in trace['asset_uses']:
                if isinstance(usage['use']['ref'], str):
                    raise CheckError('impact.trace-asset-owner', 'engineering assets need exact owner references', refs=[ref])
                acceptance = usage['use'].get('acceptance')
                resolved = r.assets.resolve_use(usage['use'], acceptance=acceptance)
                self.edge(self.file(resolved['content_ref']), change, 'change-asset-consumer')
                for locator in usage['used_in']:
                    self.edge(self.file(resolved['content_ref']), self.file(locator), 'asset-used-in')
                    self.pair(self.file(locator), change, 'planning-artifact')


def analyze(before, after, *, seeds=()):
    """Same Version/line assessment; cross-line effects need their own snapshots.

    Both contexts are explicit fixed inputs, not proof of BL effectiveness. A
    broken new graph is allowed only as visible diagnostics, never a green Gate.
    """
    with ExitStack() as stack:
        for store in {id(before.store): before.store, id(after.store): after.store}.values():
            stack.enter_context(store.input_scope())
        return _analyze(before, after, seeds=seeds)


def _analyze(before, after, *, seeds):
    if before.store.root != after.store.root or any(before.version[key] != after.version[key]
            for key in ('version', 'delivery_line')):
        raise InputError('impact.context', 'compare fixed snapshots of one Version and line; assess other lines separately')
    old, new = ImpactGraph(before).build(), ImpactGraph(after).build()
    nodes = old.nodes.keys() | new.nodes.keys()
    if set(seeds) - nodes:
        raise InputError('impact.seed', 'explicit impact seed is absent from both graphs', refs=sorted(set(seeds) - nodes))
    reasons = defaultdict(list)
    for identity in sorted(nodes):
        left, right = old.nodes.get(identity), new.nodes.get(identity)
        if left is None or right is None or left['values'] != right['values']:
            reasons[identity].append('added' if left is None else 'removed' if right is None else 'changed')
    for identity in seeds:
        reasons[identity].append('explicit-reviewed-trigger')
    # Deleted/replaced edges seed both former and new endpoints, not just the new graph.
    for key in sorted(old.edges.keys() ^ new.edges.keys()):
        edge = (old.edges | new.edges)[key]
        for endpoint in (edge['source'], edge['target']):
            reasons[endpoint].append('relationship-changed:' + key)
    diffs, unknown = [], []
    for group, before_commit, after_commit in (
            ('content', before.snapshot['head_revision'], after.snapshot['head_revision']),
            ('engineering-target', before.snapshot['target_revision'], after.snapshot['target_revision'])):
        left, right = before.store.tree(before_commit), after.store.tree(after_commit)
        for path in sorted(left.keys() | right.keys()):
            if left.get(path) == right.get(path):
                continue
            row = {'group': group, 'path': path,
                   'before_ref': fixed(before.store, before_commit, path) if path in left else None,
                   'after_ref': fixed(after.store, after_commit, path) if path in right else None}
            diffs.append(row)
            mapped = old.path_nodes[path] | new.path_nodes[path]
            if not mapped:
                unknown.append(row)
            for identity in mapped:
                reasons[identity].append('actual-diff:' + group + ':' + path)
    edges = old.edges | new.edges
    outgoing = defaultdict(list)
    for key, edge in sorted(edges.items()):
        if edge['propagate']:
            outgoing[edge['source']].append((key, edge))
    pending = deque(sorted(reasons))
    reached = set(pending)
    paths = {identity: [] for identity in pending}
    while pending:
        source = pending.popleft()
        for key, edge in outgoing[source]:
            target = edge['target']
            if target not in reached:
                reached.add(target)
                paths[target] = paths[source] + [key]
                pending.append(target)
    inputs = {'before': before.snapshot, 'after': after.snapshot,
              'explicit_seeds': sorted(set(seeds)), 'generator_manifest': implementation_manifest(),
              'resolved_inputs': sorted({canonical_bytes(ref): ref for ref in
                  before.store.manifest() + after.store.manifest()}.values(), key=canonical_bytes)}
    affected_requirements = sorted({identity.split('/')[1] for identity in reached
                                   if identity.startswith('scope:' + before.version['version'] + '/')})
    return {'kind': 'generated-requirement-impact',
            'notice': '影响审查清单；不是执行顺序、业务决定、控制发布或 Gate 通过。未映射 diff 须逐项处置。',
            'generated_from': {**inputs, 'sha256': digest(canonical_bytes(inputs))},
            'diff': diffs, 'unmapped_diff': unknown,
            'affected_requirements': affected_requirements,
            'diagnostics': old.diagnostics + new.diagnostics,
            'affected': [{'id': identity, 'triggers': sorted(set(reasons.get(identity, []))),
                          'propagation': paths[identity], 'before': old.nodes.get(identity),
                          'after': new.nodes.get(identity)} for identity in sorted(reached)],
            'edges': [{'id': key, **edge, 'present_in': [name for name, graph in (('before', old), ('after', new))
                                                       if key in graph.edges]} for key, edge in sorted(edges.items())]}
