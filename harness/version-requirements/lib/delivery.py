"""S3 的贡献、业务关系处置与验证责任；不判断 G1 生效或运行时就绪。"""
from collections import defaultdict
import re

from .core import digest, parse_yaml
from .errors import CheckError, InputError
from .models import unique, validate
from .relations import check_relations, condition
from .requirements import ac_subset
from .reviews import evidence


def same_record(left, right):
    return (left['uid'], left['record_ref'], left['configuration_ref']) == (
        right['uid'], right['record_ref'], right['configuration_ref'])


class DeliveryIndex:
    def __init__(self, requirements, *, engineering_context=None, map_ref=None, verification_plan_ref=None):
        self.requirements = requirements
        self.context, self.store = engineering_context or requirements.context, requirements.store
        if (self.context.store is not self.store or self.context.version != requirements.context.version or
                self.context.configuration != requirements.context.configuration):
            raise CheckError('delivery.engineering-context', 'current engineering view must preserve the selected baseline owner, line and authority')
        if engineering_context is None and (map_ref is not None or verification_plan_ref is not None):
            raise InputError('delivery.engineering-context', 'explicit current map/plan references need their engineering Review context')
        self.map, self.map_ref = self._input('delivery-map.yaml', 'delivery_map', map_ref)
        self.plan, self.verification_plan_ref = self._input('verification-plan.yaml', 'verification_plan', verification_plan_ref)
        self.review = self.context.read('reviews/engineering.yaml', 'review')
        for value in (self.map, self.plan):
            if value['version'] != self.context.version['version']:
                raise CheckError('delivery.version', 'map/verification plan belongs to another Version')
        if not re.fullmatch('BL-' + re.escape(self.context.version['version']) + r'-[0-9]{3,}', self.map['baseline']):
            raise CheckError('delivery.baseline-identity', 'map must name a baseline in this Version; reservation/effectiveness is checked separately')
        if self.review['phase'] != 'engineering' or 'engineering' not in self.review or 'dependency_dispositions' not in self.review:
            raise CheckError('delivery.review', 'S3 needs engineering context and explicit dependency dispositions')
        self.candidates = unique(self.map['candidates'], 'candidate_id', location='delivery-map')
        self.endpoints = unique(self.map['endpoints'], 'id', location='delivery-map')
        if self.candidates.keys() & self.endpoints.keys():
            raise CheckError('delivery.node-identity', 'candidate/endpoint IDs must not collide')
        self.active = {key: value for key, value in self.candidates.items() if value['disposition'] == 'planned'}
        self.allocations, self.capabilities, self.edges = {}, {}, {}
        self.coverage = defaultdict(set)
        self.dependencies = check_relations(requirements)

    def _input(self, relative, model, reference):
        path = self.context.vr + '/' + relative
        if reference is None:
            data = self.store.read(self.context.content_commit, path)
            reference = {'commit': self.context.content_commit, 'path': path, 'sha256': digest(data)}
        else:
            validate('ref', reference)
            if reference['path'] != path:
                raise CheckError('delivery.engineering-input', 'selected map/plan has the wrong owner or role', refs=[reference])
            data = self.store.ref(reference)
            # A Review can be recorded after the selected map/plan commit.
            # Preserve that exact reference while checking the reviewed view.
            self.store.read(self.context.content_commit, path, reference['sha256'])
        return validate(model, parse_yaml(data), location=path), reference

    def check(self):
        self.allocations.clear()
        self.capabilities.clear()
        self.edges.clear()
        self.coverage.clear()
        self._nodes()
        self._coverage()
        self._edges()
        from .availability import assessment_scope
        assessment_scope(self)
        from .planning_applicability import assessment_scope as planning_assessment_scope
        planning_assessment_scope(self)
        self._dispositions()
        self._technical_paths()
        self._verification()
        from .ui_integration import claims
        ui_claims = claims(self)
        # Complete Review binding and baseline publication are separate checks.
        return {'scope': 'S3 contribution/dependency/verification structure only',
                'candidates': sorted(self.active), 'endpoints': sorted(self.endpoints),
                'contributions': sorted(self.allocations), 'edges': sorted(self.edges), 'ui_applicability': ui_claims}

    def _nodes(self):
        names = [c['change_name'] for c in self.candidates.values() if c['change_name'] is not None]
        if len(names) != len(set(names)):
            raise CheckError('delivery.change-identity', 'multiple candidates cannot own the same logical OpenSpec Change')
        for key, node in self.candidates.items():
            evidence(self.store, node['approval_ref'])
            replacements = node.get('replaced_by', [])
            if node['disposition'] == 'superseded':
                if not replacements or key in replacements or not set(replacements) <= self.active.keys():
                    raise CheckError('delivery.replacement', 'superseded candidate needs explicit active replacements', refs=[key])
            elif replacements:
                raise CheckError('delivery.replacement', 'only superseded candidates have replacements', refs=[key])
        for key, node in self.endpoints.items():
            for ref in [node['contract_ref'], node['feasibility_ref'], *node['availability_refs']]:
                evidence(self.store, ref)
            if node['kind'] == 'existing' and (not node['availability_refs'] or node['target_line_path'] == 'port-planned'):
                raise CheckError('delivery.existing-availability', 'existing provider needs actual target-line/service availability; a future port is external', refs=[key])
        # Removed nodes retain their historical allocation, but cannot satisfy a
        # current obligation. Their old references belong to the old map review.
        for key, node in (self.active | self.endpoints).items():
            entries = unique(node['allocation'], 'id', location=key)
            for aid, row in entries.items():
                ref = key + '/' + aid
                if ref in self.allocations or ref in self.capabilities:
                    raise CheckError('delivery.contribution-identity', 'ambiguous contribution identity', refs=[ref])
                historical = row.get('requirement_ref')
                if historical is not None:
                    if key not in self.endpoints:
                        raise CheckError('delivery.historical-allocation', 'candidate allocation must select current scope; historical providers are endpoints', refs=[ref])
                    info = self.requirements.historical(historical)
                    if node['version'] != info['owner'].version['version'] or node['delivery_line'] != info['owner'].version['delivery_line']:
                        raise CheckError('delivery.historical-allocation', 'endpoint and historical provider owner disagree', refs=[ref])
                else:
                    info = self.requirements.records.get(row['requirement'])
                    if info is None:
                        raise CheckError('delivery.requirement', 'allocation is outside current scope', refs=[ref])
                if (info['uid'], info['value']['revision']) != (row['requirement'], row['revision']):
                    raise CheckError('delivery.revision', 'allocation differs from exact Requirement revision', refs=[ref])
                acs = set(ac_subset(row['acceptance'], info['acs'], ref))
                current = self.requirements.records.get(info['uid'])
                self.allocations[ref] = {'node': key, 'info': info, 'acceptance': acs, 'row': row}
                if current is not None and same_record(info, current):
                    for ac in acs:
                        self.coverage[(info['uid'], ac)].add(ref)
            for capability in node.get('expected_capabilities', []):
                ref = key + '/capability:' + capability
                if ref in self.capabilities or ref in self.allocations:
                    raise CheckError('delivery.contribution-identity', 'ambiguous capability identity', refs=[ref])
                self.capabilities[ref] = {'node': key, 'capability': capability}
            if not entries and not node.get('expected_capabilities'):
                raise CheckError('delivery.empty-node', 'provider has neither business allocation nor technical capability', refs=[key])
        self.requirements.questions.check_endpoints(self.requirements.sources.units,
                                                    self.requirements.question_requirement_ids(), candidates=self.candidates)

    def _coverage(self):
        for uid, info in self.requirements.records.items():
            mode = self.requirements.included[uid]['delivery']
            for ac in info['acs']:
                refs = self.coverage[(uid, ac)]
                if not refs:
                    raise CheckError('delivery.coverage', 'included AC has no active delivery contribution', refs=[uid, ac])
                nodes = {self.allocations[r]['node'] for r in refs}
                if mode == 'already-satisfied' and any(n not in self.endpoints or self.endpoints[n]['kind'] != 'existing' for n in nodes):
                    raise CheckError('delivery.scope-mode', 'already-satisfied obligation must use actual existing providers', refs=[uid, ac])
                if mode == 'external-deliverable' and any(n not in self.endpoints or self.endpoints[n]['kind'] != 'external' for n in nodes):
                    raise CheckError('delivery.scope-mode', 'external obligation must name its external delivery responsibility', refs=[uid, ac])
            if mode == 'change' and not any(self.allocations[r]['node'] in self.active
                                             for ac in info['acs'] for r in self.coverage[(uid, ac)]):
                raise CheckError('delivery.scope-mode', 'change delivery needs a real current candidate contribution', refs=[uid])

    def _node_contributions(self, node):
        allocated = {ref for ref, row in self.allocations.items() if row['node'] == node}
        return allocated or {ref for ref, row in self.capabilities.items() if row['node'] == node}

    def _edges(self):
        engineering_checks = unique(self.review['checks'], 'check_id', location='engineering review')
        for consumer, node in self.active.items():
            for entry in node['predecessor_edges']:
                eid = entry['id']
                if eid in self.edges:
                    raise CheckError('delivery.edge-identity', 'edge ID is unique in the Version map', refs=[eid])
                provider = entry.get('candidate', entry.get('endpoint'))
                registry = self.active if 'candidate' in entry else self.endpoints
                if provider not in registry or provider == consumer:
                    raise CheckError('delivery.edge-endpoint', 'edge needs a distinct active provider of the declared kind', refs=[eid])
                required = entry['required_contribution']
                if 'requirement' in required:
                    pref = required['allocation_ref']
                    allocation = self.allocations.get(pref)
                    if allocation is None or allocation['node'] != provider or allocation['info']['uid'] != required['requirement']:
                        raise CheckError('delivery.edge-contribution', 'provider contribution does not select its exact allocation', refs=[eid, pref])
                    pacs = set(ac_subset(required['acceptance'], allocation['acceptance'], eid))
                else:
                    pref = provider + '/capability:' + required['capability']
                    if pref not in self.capabilities:
                        raise CheckError('delivery.edge-contribution', 'technical capability is not declared by the provider', refs=[eid, pref])
                    pacs = set()
                consumers = set(entry.get('consumer_contribution', self._node_contributions(consumer)))
                allowed = self._node_contributions(consumer)
                if not consumers or not consumers <= allowed:
                    raise CheckError('delivery.edge-consumer', 'edge consumer subset must belong to its candidate', refs=[eid])
                active = condition(self.store, entry, location=eid)
                if entry['strength'] == 'soft':
                    if not entry.get('alternative') or not entry.get('review_ref'):
                        raise CheckError('dependency.soft-disposition', 'soft execution edge requires a reviewed fallback', refs=[eid])
                    evidence(self.store, entry['review_ref'])
                for origin in entry['origin_refs']:
                    if origin in self.dependencies:
                        dep = self.dependencies[origin]
                        if pref not in self.allocations or not same_record(self.allocations[pref]['info'], dep['target']) or not pacs <= set(dep['target_acceptance']):
                            raise CheckError('delivery.origin-provider', 'edge does not supply the exact business dependency target', refs=[eid, origin])
                        relevant = {ref for ref in consumers if ref in self.allocations and
                                    self.allocations[ref]['info']['uid'] == dep['consumer'] and
                                    self.allocations[ref]['acceptance'] & set(dep['applies_to'])}
                        if not relevant:
                            raise CheckError('delivery.origin-consumer', 'origin has no affected consumer contribution', refs=[eid, origin])
                    elif origin.startswith('engineering:') and origin.removeprefix('engineering:') in engineering_checks:
                        check = engineering_checks[origin.removeprefix('engineering:')]
                        if check['outcome'] != 'passed':
                            raise CheckError('delivery.engineering-origin', 'technical edge needs a passed engineering check', refs=[eid, origin])
                        evidence(self.store, check['evidence_ref'])
                    else:
                        raise CheckError('delivery.edge-origin', 'unknown business relation or engineering check', refs=[eid, origin])
                self.edges[eid] = {'consumer': consumer, 'provider': provider, 'provider_ref': pref,
                                   'provider_acceptance': pacs, 'consumers': consumers, 'active': active, 'entry': entry}

    def _dispositions(self):
        covered = defaultdict(set)
        used_edges = defaultdict(set)
        for entry in self.review['dependency_dispositions']:
            origin = entry['origin_ref']
            dep = self.dependencies.get(origin)
            if dep is None:
                raise CheckError('delivery.disposition-origin', 'disposition must identify a business dependency/constraint', refs=[origin])
            evidence(self.store, entry['evidence_ref'])
            consumers, providers = set(entry['consumer_contributions']), set(entry['provider_contributions'])
            expected = {ref for ac in dep['applies_to'] for ref in self.coverage[(dep['consumer'], ac)]}
            if not consumers <= expected or consumers & covered[origin]:
                raise CheckError('delivery.disposition-consumer', 'dependency dispositions must partition affected current contributions', refs=[origin])
            covered[origin] |= consumers
            for ref in providers:
                row = self.allocations.get(ref)
                if row is None or not same_record(row['info'], dep['target']) or not row['acceptance'] & set(dep['target_acceptance']):
                    raise CheckError('delivery.disposition-provider', 'disposition provider must supply the fixed target AC', refs=[origin, ref])
            kind = entry['disposition']
            if not dep['active']:
                if kind != 'no-wait' or entry['edge_refs']:
                    raise CheckError('delivery.inactive-disposition', 'false business condition has no active waiting obligation', refs=[origin])
                continue
            # A no-wait decision can discharge a condition/constraint without a
            # delivery edge. Its semantic validity is a mandatory Review duty.
            if kind == 'no-wait':
                if entry['edge_refs']:
                    raise CheckError('delivery.disposition-edge', 'no-wait cannot also claim execution edges', refs=[origin])
                continue
            provided_acs = set().union(*(self.allocations[r]['acceptance'] for r in providers))
            if not set(dep['target_acceptance']) <= provided_acs:
                raise CheckError('delivery.disposition-coverage', 'dependency target AC responsibility is incomplete', refs=[origin])
            if kind == 'execution-edge':
                matching = []
                for eid in entry['edge_refs']:
                    edge = self.edges.get(eid)
                    if edge is None or origin not in edge['entry']['origin_refs'] or edge['provider_ref'] not in providers:
                        raise CheckError('delivery.disposition-edge', 'disposition edge/provider/origin disagree', refs=[origin, eid])
                    if not edge['active'] or (dep['strength'] == 'hard' and edge['entry']['strength'] != 'hard'):
                        raise CheckError('delivery.dependency-downgrade', 'active hard business dependency cannot be mapped to an inactive/soft edge', refs=[origin, eid])
                    matching.append(edge)
                    used_edges[origin].add(eid)
                for ref in consumers:
                    supplied = set().union(*(e['provider_acceptance'] for e in matching if ref in e['consumers']))
                    if not set(dep['target_acceptance']) <= supplied:
                        raise CheckError('delivery.disposition-coverage', 'consumer lacks all declared target AC edge conditions', refs=[origin, ref])
                if {edge['provider_ref'] for edge in matching} != providers:
                    raise CheckError('delivery.disposition-edge', 'unused provider in execution-edge disposition', refs=[origin])
            else:
                if entry['edge_refs']:
                    raise CheckError('delivery.disposition-edge', 'non-edge disposition cannot claim edges', refs=[origin])
                for ref in consumers:
                    consumer = self.allocations[ref]['node']
                    if kind == 'internal':
                        available = [r for r in providers if self.allocations[r]['node'] == consumer]
                    else:  # existing-provider must prove current availability.
                        available = [r for r in providers if self.allocations[r]['node'] in self.endpoints and
                                     self.endpoints[self.allocations[r]['node']]['kind'] == 'existing']
                    acs = set().union(*(self.allocations[r]['acceptance'] for r in available))
                    if not set(dep['target_acceptance']) <= acs:
                        raise CheckError('delivery.disposition-path', 'internal/existing-provider path does not discharge the consumer condition', refs=[origin, ref])
        for origin, dep in self.dependencies.items():
            expected = {ref for ac in dep['applies_to'] for ref in self.coverage[(dep['consumer'], ac)]}
            if covered[origin] != expected:
                raise CheckError('delivery.disposition-missing', 'business dependency has undisposed consumer contributions', refs=[origin])
        for eid, edge in self.edges.items():
            for origin in edge['entry']['origin_refs']:
                if origin in self.dependencies and edge['active'] and eid not in used_edges[origin]:
                    raise CheckError('delivery.disposition-edge', 'active business-origin edge has no matching reviewed disposition', refs=[origin, eid])

    def _technical_paths(self):
        current = set().union(*self.coverage.values())
        useful = {self.allocations[ref]['node'] for ref in current}
        # Backward reachability from genuine Version obligations, not from an
        # arbitrary technical cycle which could justify itself.
        pending = list(useful)
        providers = defaultdict(set)
        for edge in self.edges.values():
            if edge['active']:
                providers[edge['consumer']].add(edge['provider'])
        while pending:
            for provider in providers[pending.pop()] - useful:
                useful.add(provider)
                pending.append(provider)
        disconnected = (self.active.keys() | self.endpoints.keys()) - useful
        if disconnected:
            raise CheckError('delivery.unused-provider', 'technical/historical node is disconnected from current obligations', refs=sorted(disconnected))

    def _verification(self):
        evidence(self.store, self.plan['approval_ref'])
        obligations = unique(self.plan['obligations'], 'id', location='verification-plan')
        responsibility, final, technical, edge_responsibility = defaultdict(set), set(), set(), set()
        levels = {'unit': 0, 'integration': 1, 'system': 2, 'acceptance': 3}
        for oid, item in obligations.items():
            for ref in item['evidence_refs']:
                evidence(self.store, ref)
            for eid in item.get('edge_refs', []):
                edge = self.edges.get(eid)
                if edge is None or not edge['active']:
                    raise CheckError('verification.edge', 'verification references an absent/inactive execution condition', refs=[oid, eid])
                checkpoint = {'apply-start': 'contribution', 'merge': 'integration'}.get(edge['entry']['checkpoint'], edge['entry']['checkpoint'])
                refs = {item['capability_ref']} if 'capability_ref' in item else set(item['contributions'])
                allowed = edge['consumers'] if edge['entry']['kind'] in ('integration', 'release') else edge['consumers'] | {edge['provider_ref']}
                minimum = {'implementation': 0, 'integration': 1, 'release': 2}[edge['entry']['kind']]
                if item['checkpoint'] != checkpoint or not refs & allowed or levels[item['level']] < minimum:
                    raise CheckError('verification.edge', 'edge verification needs a relevant contribution and its actual checkpoint', refs=[oid, eid])
                edge_responsibility.add(eid)
            if 'capability_ref' in item:
                ref = item['capability_ref']
                if ref not in self.capabilities:
                    raise CheckError('verification.capability', 'technical verification needs a declared capability', refs=[oid, ref])
                technical.add(ref)
                continue
            uid = item['requirement']
            info = self.requirements.records.get(uid)
            if info is None or info['value']['revision'] != item['revision']:
                raise CheckError('verification.requirement', 'verification must bind current scoped R revision', refs=[oid])
            acs = set(ac_subset(item['acceptance'], info['acs'], oid))
            refs = set(item['contributions'])
            for ref in refs:
                row = self.allocations.get(ref)
                if row is None or not same_record(row['info'], info) or not row['acceptance'] & acs:
                    raise CheckError('verification.contribution', 'verification contribution does not supply the selected obligation', refs=[oid, ref])
            for ac in acs:
                supplied = refs & self.coverage[(uid, ac)]
                if not supplied:
                    raise CheckError('verification.contribution', 'verification claims AC without a contributing path', refs=[oid, ac])
                responsibility[(uid, ac)] |= supplied
                if item['final']:
                    expected_level = info['acs'][ac]['level']
                    if supplied != self.coverage[(uid, ac)] or levels[item['level']] < levels[expected_level]:
                        raise CheckError('verification.final-coverage', 'final AC responsibility must cover the complete contribution set at required level', refs=[oid, ac])
                    if info['value']['kind'] in ('quality', 'constraint') and (item['checkpoint'] not in ('completion', 'release') or item['level'] not in ('system', 'acceptance')):
                        raise CheckError('verification.quality-final', 'cross-cutting quality/constraint requires final system/acceptance responsibility', refs=[oid, ac])
                    if len(self.coverage[(uid, ac)]) > 1 and item['checkpoint'] == 'contribution':
                        raise CheckError('verification.final-checkpoint', 'multi-contribution AC cannot finish at one contribution checkpoint', refs=[oid, ac])
                    final.add((uid, ac))
        for key, refs in self.coverage.items():
            if responsibility[key] != refs or key not in final:
                raise CheckError('verification.coverage', 'AC needs contribution responsibility and explicit final verification', refs=list(key))
        required = {edge['provider_ref'] for edge in self.edges.values() if edge['active'] and edge['provider_ref'] in self.capabilities}
        if not required <= technical:
            raise CheckError('verification.technical-coverage', 'technical providers need verification responsibility without inventing business R', refs=sorted(required - technical))
        due = {eid for eid, edge in self.edges.items() if edge['active'] and edge['entry']['strength'] == 'hard'
               and edge['entry']['kind'] in ('integration', 'release')}
        if not due <= edge_responsibility:
            raise CheckError('verification.edge-coverage', 'hard integration/release conditions need explicit checkpoint verification responsibility', refs=sorted(due - edge_responsibility))
