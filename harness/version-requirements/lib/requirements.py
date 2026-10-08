"""按 scope 解析确切 R/AC 与来源投影；本模块的通过不等于完整 G1。"""
from collections import defaultdict
from graphlib import CycleError, TopologicalSorter
import re

from .assets import AssetIndex
from .backend import verify_records
from .core import canonical_bytes, digest, parse_yaml
from .errors import CheckError
from .models import check_requirement_ids, scope_requirement_ids, unique, validate
from .questions import QuestionIndex
from .reviews import evidence
from .sources import SourceIndex


def ac_subset(value, acs, location):
    if not value or not set(value) <= set(acs):
        raise CheckError('requirement.acceptance-ref', 'unknown or empty acceptance subset', refs=[location])
    return sorted(value)


class RequirementIndex:
    def __init__(self, context):
        self.context, self.store = context, context.store
        self.sources = SourceIndex(context, require_decisions=False)
        self.assets = AssetIndex(context, sources=self.sources)
        self.scope = context.read('scope.yaml', 'scope')
        if self.scope['version'] != context.version['version']:
            raise CheckError('scope.version', 'scope and selected Version disagree')
        self._identities = check_requirement_ids(sorted(scope_requirement_ids(self.scope)))
        check_requirement_ids((path.rsplit('/', 1)[1][:-4] for path in sorted(self.store.tree(context.content_commit))
                               if re.fullmatch(r'requirements/items/R-[0-9]{3,}\.yml', path)), seen=self._identities)
        self.included = unique(self.scope['included'], 'requirement', location='scope.included')
        contexts = unique(self.scope['context_requirements'], 'requirement', location='scope.context_requirements')
        if self.included.keys() & contexts.keys():
            raise CheckError('scope.duplicate', 'a contextual Requirement cannot duplicate a member')
        self.records, self.context_records, self.all_records = {}, {}, {}
        self.excluded_records, self._native_records = [], set()
        self._questions, self._history = {}, {}
        self.baseline_references = {}
        self._scopes = {}
        self.questions = self.question_index(context)
        self.origins = defaultdict(list)
        self.confirmations = defaultdict(list)
        for uid, member in self.included.items():
            predecessor = self.historical(member['predecessor']) if 'predecessor' in member else None
            if member['transition'] == 'added' and predecessor is not None:
                raise CheckError('scope.predecessor', 'added membership cannot also claim a predecessor', refs=[uid])
            if member['transition'] in ('modified', 'inherited') and predecessor is None:
                raise CheckError('scope.predecessor', 'modified/inherited membership requires a fixed predecessor', refs=[uid])
            if predecessor is not None and predecessor['uid'] != uid:
                raise CheckError('scope.predecessor', 'stable identity differs from predecessor', refs=[uid])
            ref = member.get('record_ref') or self.current_ref('requirements/items/' + uid + '.yml')
            config = member.get('configuration_ref') or self.current_ref('requirements/items/.doorstop.yml')
            owner = predecessor['owner'] if member['transition'] == 'inherited' else context
            info = self.record(uid, ref, config, owner)
            if info['value']['revision'] != member['revision']:
                raise CheckError('scope.revision', 'scope revision differs from the exact record', refs=[uid])
            if member['transition'] == 'inherited' and (ref != predecessor['record_ref'] or config != predecessor['configuration_ref']):
                raise CheckError('scope.inherited-content', 'unchanged inheritance must select the fixed predecessor record/configuration', refs=[uid])
            if member['transition'] == 'modified' and info['value']['revision'] <= predecessor['value']['revision']:
                raise CheckError('scope.revision', 'modified Requirement must advance its predecessor revision', refs=[uid])
            self.records[uid] = info
        for uid, item in contexts.items():
            owner = context.at(item['record_ref']['commit'], item.get('version', context.version['version']))
            self.context_records[uid] = self.record(uid, item['record_ref'], item['configuration_ref'], owner)
        for excluded in self.scope['excluded']:
            reference = excluded.get('requirement')
            uid = reference.get('requirement') if isinstance(reference, dict) else reference
            if uid is not None and 'predecessor' in excluded and excluded['predecessor']['requirement'] != uid:
                raise CheckError('scope.excluded-identity', 'excluded Requirement differs from its fixed predecessor', refs=[uid])
            if uid in self.records:
                raise CheckError('scope.included-excluded', 'Requirement cannot be both included and excluded', refs=[uid])
            predecessor = self.historical(excluded['predecessor']) if 'predecessor' in excluded else None
            if isinstance(reference, dict):
                self.excluded_records.append(self.historical(reference))
            elif uid is not None:
                # A fixed predecessor names the cancelled obligation even if a
                # later draft with the same ID exists at the current commit.
                info = predecessor or self.context_records.get(uid)
                if info is None:
                    info = self.record(uid, self.current_ref('requirements/items/' + uid + '.yml'),
                                       self.current_ref('requirements/items/.doorstop.yml'), context, native=False)
                self.excluded_records.append(info)
            if predecessor is not None:
                self.excluded_records.append(predecessor)
        for info in self.records.values():
            self._origins(info)
        for uid, member in self.included.items():
            confirmed = set()
            for confirmation in member['source_confirmations']:
                unit = confirmation['unit']
                if unit in confirmed:
                    raise CheckError('scope.source-confirmation', 'combine confirmations of the same unit', refs=[uid, unit])
                confirmed.add(unit)
                if unit not in self.sources.units:
                    raise CheckError('scope.source-confirmation', 'confirmation must reference a current Version unit', refs=[unit])
                acs = ac_subset(confirmation['acceptance'], self.records[uid]['acs'], uid)
                evidence(self.store, confirmation['decision_ref'])
                self.confirmations[unit].append({'requirement': uid, 'revision': member['revision'], 'acceptance': acs, 'role': 'confirmation'})

    def current_ref(self, path):
        data = self.store.read(self.context.content_commit, path)
        return {'commit': self.context.content_commit, 'path': path, 'sha256': digest(data)}

    def question_index(self, owner):
        key = (owner.content_commit, owner.version['version'])
        if key not in self._questions:
            self._questions[key] = QuestionIndex(owner)
        return self._questions[key]

    def record(self, uid, ref, config_ref, owner, *, native=True):
        check_requirement_ids([uid], seen=self._identities)
        if ref['path'] != 'requirements/items/' + uid + '.yml' or config_ref['path'] != 'requirements/items/.doorstop.yml':
            raise CheckError('requirement.path', 'R and original Doorstop configuration need canonical paths', refs=[uid])
        key = (ref['commit'], ref['path'], ref['sha256'], config_ref['commit'], config_ref['sha256'],
               owner.content_commit, owner.version['version'])
        # Local cancelled drafts need recoverable typed bytes, not an invented
        # approval. Any active/contextual reuse still requires native checking;
        # a later cancellation read cannot remove that obligation on a cache hit.
        if native:
            self._native_records.add(key)
        if key in self.all_records:
            return self.all_records[key]
        data, configuration = self.store.ref(ref), self.store.ref(config_ref)
        value = validate('requirement', parse_yaml(data), location=ref['path'])
        config = parse_yaml(configuration)
        required = {'schema_version', 'revision', 'kind', 'owner', 'source_refs', 'asset_refs', 'acceptance',
                    'hierarchy', 'constraints', 'relationships', 'derived_from', 'question_refs'}
        required |= {'supersedes', 'retires'} & value.keys()
        attributes = config.get('attributes') if isinstance(config, dict) else None
        reviewed = attributes.get('reviewed') if isinstance(attributes, dict) else None
        if not isinstance(reviewed, list) or not all(isinstance(x, str) for x in reviewed) or not required <= set(reviewed):
            raise CheckError('requirement.configuration', 'original configuration does not review all used semantic fields', refs=[uid])
        if value['owner'] not in owner.version['owners']:
            raise CheckError('requirement.owner', 'Requirement owner is not a declared responsibility', refs=[uid])
        acs = unique(value['acceptance'], 'id', location=uid)
        metric_fields = {'metric', 'threshold', 'unit', 'load', 'environment', 'observation_window'}
        for ac in acs.values():
            if metric_fields & ac.keys() and not metric_fields <= ac.keys():
                raise CheckError('requirement.measurement', 'quantitative acceptance needs all measurement conditions', refs=[uid, ac['id']])
        info = {'uid': uid, 'bytes': data, 'configuration': configuration, 'value': value, 'acs': acs,
                'record_ref': ref, 'configuration_ref': config_ref, 'owner': owner}
        self.all_records[key] = info
        return info

    def historical(self, reference):
        # Target references additionally carry a line/availability; historical
        # derivation references carry a reason/decision. Both bind the same BL.
        key = canonical_bytes(reference)
        baseline_ref = reference['baseline_ref']
        self.baseline_references[canonical_bytes(baseline_ref)] = baseline_ref
        if key in self._history:
            return self._history[key]
        bl = validate('baseline', parse_yaml(self.store.ref(reference['baseline_ref'])))
        version, uid = reference['version'], reference['requirement']
        expected_path = 'requirements/versions/' + version + '/baselines/' + bl['id'] + '.yaml'
        if bl['version'] != version or reference['baseline_ref']['path'] != expected_path:
            raise CheckError('requirement.historical-baseline', 'historical baseline owner/path mismatch', refs=[uid])
        owner = self.context.at(bl['content_commit'], version)
        if 'delivery_line' in reference and owner.version['delivery_line'] != reference['delivery_line']:
            raise CheckError('requirement.historical-line', 'historical target belongs to a different delivery line', refs=[uid])
        entries = {}
        for entry in bl['content_manifest']:
            identity = (entry.get('commit', bl['content_commit']), entry['path'])
            if identity in entries:
                raise CheckError('requirement.historical-manifest', 'duplicate baseline manifest entry', refs=[entry])
            self.store.ref(entry, default_commit=bl['content_commit'])
            entries[identity] = entry
        scope_path = owner.vr + '/scope.yaml'
        scope_ref = entries.get((bl['content_commit'], scope_path))
        if scope_ref is None:
            raise CheckError('requirement.historical-manifest', 'baseline omits its exact scope')
        scope = validate('scope', parse_yaml(self.store.ref(scope_ref, default_commit=bl['content_commit'])))
        check_requirement_ids(sorted(scope_requirement_ids(scope)), seen=self._identities)
        members = unique(scope['included'], 'requirement', location=scope_path)
        member = members.get(uid)
        if scope['version'] != version or member is None:
            raise CheckError('requirement.historical-scope', 'Requirement was not a member of the fixed baseline', refs=[uid])
        for label, path in [('record_ref', 'requirements/items/' + uid + '.yml'),
                            ('configuration_ref', 'requirements/items/.doorstop.yml')]:
            selected = member.get(label)
            if selected is None:
                item = entries.get((bl['content_commit'], path))
                if item is None:
                    raise CheckError('requirement.historical-manifest', 'baseline omits record/configuration', refs=[path])
                selected = {'commit': bl['content_commit'], 'path': path, 'sha256': item['sha256']}
            bound = entries.get((selected['commit'], selected['path']))
            if selected != reference[label] or bound is None or bound['sha256'] != selected['sha256']:
                raise CheckError('requirement.historical-selection', 'historical reference differs from the BL selection', refs=[uid, label])
        info = self.record(uid, reference['record_ref'], reference['configuration_ref'], owner)
        if info['value']['revision'] != member['revision']:
            raise CheckError('requirement.historical-selection', 'historical revision mismatch', refs=[uid])
        for key_ in ('decision_ref', 'availability_ref'):
            if key_ in reference:
                evidence(self.store, reference[key_])
        self._history[key] = info
        return info

    def source_unit(self, identity, info):
        version = identity.split('/', 1)[0]
        owner = self.context.at(info['record_ref']['commit'], version)
        sources = self.assets._source_index(owner)
        if identity not in sources.units:
            raise CheckError('requirement.source', 'origin unit is absent from the record snapshot', refs=[info['uid'], identity])
        return sources.units[identity]

    def asset_owner(self, info):
        """Local asset names belong to the unchanged record, not a later BL owner.

        Keep info.owner for that BL's scope/relations. Only the asset-reading
        context follows exact inherited selections back to the record's owner.
        Never infer ownership from source_refs or a same-name current asset.
        """
        visited = set()
        while True:
            owner = info['owner']
            key = canonical_bytes([info['record_ref'], info['configuration_ref'],
                                   owner.content_commit, owner.vr])
            if key in visited:
                raise CheckError('requirement.inheritance-cycle', 'asset ownership inheritance contains a cycle')
            if len(visited) >= 64:
                raise CheckError('requirement.inheritance-limit', 'asset ownership inheritance exceeds 64 fixed contexts')
            visited.add(key)
            if owner.content_commit == info['record_ref']['commit']:
                return owner
            scope = owner.read('scope.yaml', 'scope')
            members = unique(scope['included'], 'requirement', location=owner.vr + '/scope.yaml')
            member = members.get(info['uid'])
            if member is None or member['transition'] != 'inherited':
                return self.context.at(info['record_ref']['commit'], owner.version['version'])
            if 'predecessor' not in member:
                raise CheckError('scope.predecessor', 'inherited asset context requires a fixed predecessor', refs=[info['uid']])
            predecessor = self.historical(member['predecessor'])
            if predecessor['uid'] != info['uid'] or any(info[field] != predecessor[field]
                                                       for field in ('record_ref', 'configuration_ref')):
                raise CheckError('scope.inherited-content', 'inherited asset context must keep exact predecessor content/configuration', refs=[info['uid']])
            info = predecessor

    def _origins(self, info):
        value, uid = info['value'], info['uid']
        seen = set()
        for reference in value['source_refs']:
            key = reference.get('unit', reference.get('decision'))
            if key in seen:
                raise CheckError('requirement.source-duplicate', 'combine repeated origin/decision references', refs=[uid, key])
            seen.add(key)
            if reference['role'] == 'origin':
                unit = self.source_unit(reference['unit'], info)
                acs = ac_subset(reference.get('acceptance', list(info['acs'])), info['acs'], uid)
                row = {'requirement': uid, 'revision': value['revision'], 'acceptance': acs, 'role': 'origin'}
                self.origins[unit['id']].append(row)
                if unit['id'] in self.sources.units:
                    current = self.sources.units[unit['id']]
                    if any(current[k] != unit[k] for k in ('file', 'file_sha256', 'selector', 'fragment_sha256')):
                        raise CheckError('requirement.source-context', 'current unit reinterprets a retained origin; use a distinct unit identity', refs=[unit['id']])
            else:
                qid = reference['decision']
                owner = self.context.at(info['record_ref']['commit'], qid.split('/', 1)[0])
                self.question_index(owner).resolve(qid)

    def source_targets(self, identity):
        return sorted(self.origins[identity] + self.confirmations[identity], key=canonical_bytes)

    def scope_record(self, owner, uid):
        if (owner.content_commit, owner.vr) == (self.context.content_commit, self.context.vr):
            return self.target(uid)
        key = (owner.content_commit, owner.vr)
        if key not in self._scopes:
            scope = owner.read('scope.yaml', 'scope')
            check_requirement_ids(sorted(scope_requirement_ids(scope)), seen=self._identities)
            if scope['version'] != owner.version['version']:
                raise CheckError('scope.version', 'historical scope owner mismatch')
            members = unique(scope['included'], 'requirement', location=owner.vr)
            contexts = unique(scope['context_requirements'], 'requirement', location=owner.vr)
            if members.keys() & contexts.keys():
                raise CheckError('scope.duplicate', 'historical scope repeats a contextual member')
            self._scopes[key] = members | contexts
        member = self._scopes[key].get(uid)
        if member is None:
            raise CheckError('requirement.target', 'target is absent from its owning fixed scope', refs=[uid])
        refs = []
        for field, path in [('record_ref', 'requirements/items/' + uid + '.yml'),
                            ('configuration_ref', 'requirements/items/.doorstop.yml')]:
            ref = member.get(field)
            if ref is None:
                ref = {'commit': owner.content_commit, 'path': path,
                       'sha256': digest(self.store.read(owner.content_commit, path))}
            refs.append(ref)
        record_owner = owner
        if 'transition' not in member:  # context_requirements selects its own fixed record/Version.
            record_owner = self.context.at(refs[0]['commit'], member.get('version', owner.version['version']))
        info = self.record(uid, *refs, record_owner)
        if 'revision' in member and member['revision'] != info['value']['revision']:
            raise CheckError('scope.revision', 'historical scope revision mismatch', refs=[uid])
        return info

    def relation_target(self, owner, reference):
        """Resolve both the exact record and the scope interpreting its outgoing relations.

        Inherited current members keep their original record owner, but local
        relations select current scope revisions. Explicit history/background
        references resume in their own fixed scope.
        """
        if isinstance(reference, dict):
            info = self.historical(reference)
            return info, info['owner']
        info = self.scope_record(owner, reference)
        key = (owner.content_commit, owner.vr)
        if key == (self.context.content_commit, self.context.vr):
            contextual = reference in self.context_records
        else:
            contextual = 'transition' not in self._scopes[key][reference]
        return info, info['owner'] if contextual else owner

    def check_graph(self, relation):
        """Traverse exact historical endpoints too; R ID alone is not a node identity."""
        graph = {}
        pending = [(info, self.context) for info in self.records.values()]
        while pending:
            info, owner = pending.pop()
            key = (owner.content_commit, owner.vr, info['record_ref']['commit'], info['uid'])
            if key in graph:
                continue
            if len(graph) >= 10000:
                raise CheckError('requirement.graph-limit', 'relation closure exceeds the supported 10000 nodes')
            graph[key] = []
            refs = [info['value']['hierarchy']['parent']] if relation == 'hierarchy' else info['value']['derived_from']
            for ref in refs:
                if ref is None:
                    continue
                target, target_owner = self.relation_target(owner, ref)
                target_key = (target_owner.content_commit, target_owner.vr, target['record_ref']['commit'], target['uid'])
                graph[key].append(target_key)
                pending.append((target, target_owner))
        try:
            tuple(TopologicalSorter(graph).static_order())
        except CycleError as error:
            raise CheckError('requirement.' + relation + '-cycle', relation + ' contains a cycle') from error
        return len(graph)

    def check_supersession(self, unit):
        identity = unit['id']
        reference = unit.get('previous_ref')
        if not reference or reference['path'] != self.context.vr + '/source/units.yaml':
            raise CheckError('source.supersession-history', 'superseded unit needs the fixed prior units snapshot', refs=[identity])
        if reference['commit'] == self.context.content_commit or not self.store.ancestor(reference['commit'], self.context.content_commit):
            raise CheckError('source.supersession-history', 'previous source snapshot must precede this content', refs=[identity])
        self.store.ref(reference)
        owner = self.context.at(reference['commit'], self.context.version['version'])
        previous_sources = self.assets._source_index(owner)
        previous = previous_sources.units.get(identity)
        if previous is None or any(previous[k] != unit[k] for k in ('file', 'file_sha256', 'selector', 'fragment_sha256', 'targets')):
            raise CheckError('source.supersession-history', 'historical identity/mapping was not preserved', refs=[identity])
        if previous['disposition'] == 'superseded':
            raise CheckError('source.supersession-history', 'retain the original mapping before replacement', refs=[identity])
        if previous['targets']:
            old = RequirementIndex(owner)
            if sorted(previous['targets'], key=canonical_bytes) != old.source_targets(identity):
                raise CheckError('source.supersession-history', 'historical targets were not an authoritative projection', refs=[identity])
        successors = unit.get('successors', [])
        if not successors or not unit.get('scope_decision') or not unit.get('decision_ref'):
            raise CheckError('source.supersession-decision', 'replacement needs an explicit successor and product decision', refs=[identity])
        q = self.questions.require_resolved(unit['scope_decision'], scope_decision=True)
        evidence(self.store, unit['decision_ref'])
        if unit['decision_ref'] != q['response']['evidence_ref'] or identity not in self.questions.impact(q['id'])['source_refs']:
            raise CheckError('source.supersession-decision', 'replacement must bind the actual answer and affected source', refs=[identity])
        for successor in successors:
            if '/Q-' in successor:
                if self.questions.require_resolved(successor, scope_decision=True)['id'] != q['id']:
                    raise CheckError('source.supersession-decision', 'decision successor and scope decision disagree', refs=[identity])
            elif successor not in self.sources.units or successor == identity:
                raise CheckError('source.supersession-successor', 'source successor is absent or self-referencing', refs=[identity])

    def target(self, reference):
        if isinstance(reference, dict):
            return self.historical(reference)
        value = self.records.get(reference) or self.context_records.get(reference)
        if value is None:
            raise CheckError('requirement.target', 'target is outside the selected scope/context; use a fixed external reference', refs=[reference])
        return value

    def question_requirement_ids(self):
        """Q 可保留已排除/背景对象的历史；这些身份不构成当前交付分母。"""
        named = self.records.keys() | self.context_records.keys()
        for item in self.scope['excluded']:
            reference = item.get('requirement')
            if reference is not None:
                named.add(reference if isinstance(reference, str) else reference['requirement'])
        return named

    def check_source_relations(self):
        for intake in self.sources.intakes.values():
            if not intake['id'].startswith(self.context.version['version'] + '/'):
                continue  # The predecessor BL owns historical source decisions.
            if any(row['status'] != 'confirmed' for row in intake['relations']):
                raise CheckError('source.relation-unknown', 'current source relationships need a resolved decision')

    def check_source_cycles(self):
        replacement_graph = {identity: [s for s in u.get('successors', []) if s in self.sources.units]
                             for identity, u in self.sources.units.items()}
        duplicate_graph = {identity: [u['duplicate_of']] if 'duplicate_of' in u else []
                           for identity, u in self.sources.units.items()}
        for name, graph in [('supersession', replacement_graph), ('duplicate', duplicate_graph)]:
            try:
                tuple(TopologicalSorter(graph).static_order())
            except CycleError as error:
                raise CheckError('source.' + name + '-cycle', 'source ' + name + ' contains a cycle') from error

    def check_content(self):
        """S2 内容/来源闭合；工程分配、阶段死锁、Review 和 BL 仍由 G1 另检。"""
        self.check_source_relations()
        exclusions = {}
        for excluded in self.scope['excluded']:
            q = self.questions.require_resolved(excluded['decision_ref'], scope_decision=True)
            impact = self.questions.impact(q['id'])
            if 'source_unit' in excluded:
                unit = excluded['source_unit']
                if unit not in self.sources.units or unit in exclusions:
                    raise CheckError('scope.excluded-source', 'excluded source is unknown or duplicated', refs=[unit])
                if unit not in impact['source_refs']:
                    raise CheckError('scope.excluded-decision', 'scope decision does not cover the excluded source', refs=[unit, q['id']])
                exclusions[unit] = q['id']
            if 'requirement' in excluded:
                uid = excluded['requirement'] if isinstance(excluded['requirement'], str) else excluded['requirement']['requirement']
                if uid not in impact['affected_requirements']:
                    raise CheckError('scope.excluded-decision', 'scope decision does not cover the cancelled Requirement', refs=[uid, q['id']])
        for identity, unit in self.sources.units.items():
            state, targets = unit['disposition'], self.source_targets(identity)
            if state != 'duplicate' and 'duplicate_of' in unit:
                raise CheckError('source.duplicate-state', 'duplicate_of belongs only to duplicate source disposition', refs=[identity])
            if state != 'context' and unit.get('context_requirements'):
                raise CheckError('source.context-role', 'context associations only belong to contextual units', refs=[identity])
            if state != 'superseded' and any(k in unit for k in ('previous_ref', 'successors')):
                raise CheckError('source.supersession-state', 'historical replacement fields require superseded disposition', refs=[identity])
            if 'supersedes_unit' in unit:
                old = self.sources.units.get(unit['supersedes_unit'])
                if old is None or old['disposition'] != 'superseded' or identity not in old.get('successors', []):
                    raise CheckError('source.supersession-successor', 'replacement direction disagrees with the historical unit', refs=[identity])
            if state == 'pending':
                raise CheckError('source.pending', 'source interpretation is incomplete', refs=[identity])
            if state in ('mapped', 'duplicate'):
                if not targets or sorted(unit['targets'], key=canonical_bytes) != targets:
                    raise CheckError('source.mapping', 'source targets must be the reverse projection of R origins/scope confirmations', refs=[identity])
                duplicate = unit.get('duplicate_of')
                if duplicate and (duplicate == identity or duplicate not in self.sources.units or
                                  {t['requirement'] for t in self.source_targets(duplicate)} != {t['requirement'] for t in targets}):
                    raise CheckError('source.duplicate-target', 'duplicate does not name the same mapped obligation', refs=[identity])
            elif state == 'excluded':
                if targets or unit['targets'] or identity not in exclusions or not unit.get('scope_decision') or self.questions.resolve(unit['scope_decision'])['id'] != exclusions[identity]:
                    raise CheckError('source.exclusion', 'source exclusion must match the authoritative product scope decision', refs=[identity])
            elif state == 'context':
                if targets or unit['targets']:
                    raise CheckError('source.context-obligation', 'mapped obligations cannot be hidden as contextual material', refs=[identity])
                for uid in unit.get('context_requirements', []):
                    self.target(uid)
            else:
                self.check_supersession(unit)
        self.check_source_cycles()
        if set(exclusions) - {x for x, u in self.sources.units.items() if u['disposition'] == 'excluded'}:
            raise CheckError('scope.exclusion', 'scope excludes a source whose disposition disagrees')
        self.questions.check_endpoints(self.sources.units, self.question_requirement_ids())
        self.questions.check_baseline(self.records)
        for uid, info in self.records.items():
            value = info['value']
            for name in ('derived_from', 'supersedes', 'retires'):
                for reference in value.get(name, []):
                    self.historical(reference)
            for reference in value['source_refs']:
                if reference['role'] == 'clarification':
                    qid = reference['decision']
                    owner = self.context.at(info['record_ref']['commit'], qid.split('/', 1)[0])
                    self.question_index(owner).require_resolved(qid)
            for qid in value['question_refs']:
                owner = self.context.at(info['record_ref']['commit'], qid.split('/', 1)[0])
                self.question_index(owner).resolve(qid)
            for usage in value['asset_refs']:
                asset_owner = self.asset_owner(info)
                self.assets.resolve_use(usage, owner=asset_owner, consumer={'requirement': uid, 'record_ref': info['record_ref']}, acceptance=info['acs'])
        self.check_graph('hierarchy')
        self.check_graph('derived_from')
        return {'included': sorted(self.records), 'acceptance_count': sum(len(x['acs']) for x in self.records.values()),
                'source_units': len(self.sources.units), 'questions': len(self.questions.values),
                'scope': 'S2 content/source only; not G1'}

    def verify_native(self):
        groups = defaultdict(dict)
        for identity, info in self.all_records.items():
            if identity not in self._native_records:
                continue
            # Same stable R ID may occur at different historical snapshots. Those
            # records must not overwrite one another in a Doorstop projection.
            key = (info['record_ref']['commit'], info['configuration_ref']['commit'], info['configuration_ref']['sha256'])
            groups[key][info['uid']] = info
        return [result for group in groups.values() for result in verify_records(group)]
