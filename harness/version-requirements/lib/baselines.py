"""G1 的内容检查与权威输入清单；不创建批准、BL 或发布 Git 引用。"""
from dataclasses import replace
from datetime import datetime
import re

from .control import read_control, require_reservation
from .core import canonical_bytes, digest, parse_json, parse_yaml
from .delivery import DeliveryIndex
from .errors import CheckError, InputError
from .feasibility import check_feasibility
from .requirements import RequirementIndex
from .models import check_requirement_ids, scope_requirement_ids, validate
from .review_scope import References, ReviewScope
from .sources import check_intake


def published_chain(context, target):
    prefix = context.vr + '/baselines/'
    rows, children = {}, {}
    for path in context.store.tree(target):
        if not path.startswith(prefix):
            continue
        value = validate('baseline', context.store.yaml(target, path), location=path)
        if value['version'] != context.version['version'] or path != prefix + value['id'] + '.yaml':
            raise CheckError('baseline.chain-identity', 'published baseline path/owner mismatch', refs=[path])
        rows[path] = value
    roots = []
    for path, value in rows.items():
        previous = value['supersedes']
        if previous is None:
            roots.append(path)
            continue
        parent = previous['path']
        if parent not in rows or parent == path:
            raise CheckError('baseline.chain-parent', 'published predecessor must exist in this Version chain', refs=[path])
        context.store.ref(previous)
        context.store.read(target, parent, previous['sha256'])
        if parent in children:
            raise CheckError('baseline.chain-fork', 'a Version has only one published baseline successor', refs=[parent])
        children[parent] = path
    if not rows:
        return rows, None
    if len(roots) != 1:
        raise CheckError('baseline.chain-root', 'published Version must have exactly one baseline root')
    visited, cursor = set(), roots[0]
    while cursor not in visited:
        visited.add(cursor)
        if cursor not in children:
            break
        cursor = children[cursor]
    if visited != rows.keys():
        raise CheckError('baseline.chain-cycle', 'published baseline chain must be connected and acyclic')
    return rows, cursor


class BaselineHistory:
    """One traversal of explicitly selected historical BL contexts; no state store."""
    def __init__(self, context):
        self.context = context
        self.entries, self.results, self.visiting = {}, {}, set()
        for entry in context.snapshot.get('baseline_contexts', []):
            key = canonical_bytes(entry['baseline_ref'])
            if key in self.entries:
                raise InputError('baseline.context-duplicate', 'one explicit publication context per fixed baseline')
            self.entries[key] = entry

    def run(self, context):
        key = canonical_bytes(context.snapshot['baseline_ref'])
        if key in self.visiting:
            raise CheckError('baseline.cycle', 'baseline inheritance/predecessor graph contains a cycle')
        if key in self.results:
            return self.results[key]
        if len(self.visiting) >= 64 or len(self.results) >= 128:
            raise InputError('baseline.history-limit', 'historical baseline traversal exceeds supported bounds')
        self.visiting.add(key)
        try:
            result = BaselineRecord(context, history=self).check()
            self.results[key] = result
            return result
        finally:
            self.visiting.remove(key)

    def check(self, reference):
        from .context import resolve
        key = canonical_bytes(reference)
        entry = self.entries.get(key)
        if entry is None:
            raise InputError('baseline.context-required', 'fixed historical target/control/publication context required', refs=[reference])
        baseline = validate('baseline', parse_yaml(self.context.store.ref(reference)))
        owner = self.context.at(baseline['content_commit'], baseline['version'])
        snapshot = {**self.context.snapshot, **entry, 'gate': 'G1', 'phase': 'effective',
                    'subject': 'baseline:' + baseline['id'], 'version': baseline['version'],
                    'delivery_line': owner.version['delivery_line'],
                    'metadata_revision': reference['commit'], 'head_revision': baseline['content_commit']}
        snapshot.pop('previous_control_revision', None)
        # resolve checks each actual source line/control in current mode. A
        # historical query keeps its fixed inputs and grants no current action.
        context = resolve(self.context.store, snapshot)
        return self.run(context)

    def content_references(self, references):
        refs = References(self.context)
        for reference in references.values():
            refs.add(reference)
            baseline = validate('baseline', parse_yaml(self.context.store.ref(reference)))
            for entry in baseline['content_manifest']:
                refs.add({**entry, 'commit': entry.get('commit', baseline['content_commit'])})
            refs.fixed(baseline['approvals'])
        # Current target/control and publication observations remain evaluation
        # context, not a moving input to an immutable approved content manifest.
        return refs.result()


class BaselineContent:
    def __init__(self, context, *, history=None, predecessor=None):
        self.context, self.store = context, context.store
        self.history = history or BaselineHistory(context)
        self.requirements = RequirementIndex(context)
        self.delivery = None
        self.reviews = None
        self.required = None
        self.predecessor = predecessor
        self.historical_refs = {}

    def _historical_baselines(self):
        references = dict(self.requirements.baseline_references)
        disposition_baselines = set()
        if self.predecessor is not None:
            references[canonical_bytes(self.predecessor)] = self.predecessor
            disposition_baselines.add(canonical_bytes(self.predecessor))
        self.historical_refs = references
        _, head = published_chain(self.context, self.context.snapshot['target_revision'])
        if head is not None:
            expected = digest(self.store.read(self.context.snapshot['target_revision'], head))
            matches = [entry['baseline_ref'] for entry in self.history.entries.values()
                       if entry['baseline_ref']['path'] == head and entry['baseline_ref']['sha256'] == expected]
            if len(matches) != 1:
                raise InputError('baseline.context-required', 'the actual published predecessor needs its exact original B and publication context', refs=[head])
            references[canonical_bytes(matches[0])] = matches[0]
            disposition_baselines.add(canonical_bytes(matches[0]))
        version = self.context.version
        previous = version.get('predecessor_baseline')
        if bool(previous) != bool(version.get('predecessor_version')):
            raise CheckError('version.predecessor', 'predecessor Version and fixed baseline must be supplied together')
        if previous:
            if version['predecessor_version'] == version['version']:
                raise CheckError('version.predecessor', 'a Version cannot inherit itself')
            references[canonical_bytes(previous)] = previous
            # Once this Version has its own predecessor, its approved scope
            # already accounts for the source Version. Do not resurrect older
            # obligations/revisions during later same-Version RCs.
            if not disposition_baselines:
                disposition_baselines.add(canonical_bytes(previous))
        if version.get('predecessor_candidate') and previous is None:
            raise CheckError('version.predecessor', 'predecessor candidate requires its Version/baseline')
        for reference in references.values():
            result = self.history.check(reference)
            if previous == reference and validate('baseline', parse_yaml(self.store.ref(reference)))['version'] != version['predecessor_version']:
                raise CheckError('version.predecessor', 'predecessor Version differs from the selected baseline owner')
            descriptor = validate('baseline', parse_yaml(self.store.ref(reference)))
            owner = self.context.at(descriptor['content_commit'], descriptor['version'])
            prior_scope = owner.read('scope.yaml', 'scope')
            prior_ids = scope_requirement_ids(prior_scope)
            check_requirement_ids(sorted(prior_ids), seen=self.requirements._identities)
            reused = [uid for uid, item in self.requirements.included.items()
                      if item['transition'] == 'added' and uid in prior_ids and descriptor['version'] != version['version']]
            if reused:
                raise CheckError('scope.reused-identity', 'an existing stable identity must use modified/inherited with its fixed predecessor, not added', refs=reused)
            if canonical_bytes(reference) in disposition_baselines:
                self._prior_obligations(reference, owner, prior_scope)

    def _prior_obligations(self, baseline, owner, prior_scope):
        """Selected predecessors define the old denominator, not every ancestor.

        Background references and absence from a new full PRD cannot retire an
        approved obligation. Existing Q/Review checks decide explicit exclusions.
        """
        excluded = {}
        for row in self.requirements.scope['excluded']:
            item = row.get('requirement')
            uid = item.get('requirement') if isinstance(item, dict) else item
            if uid is not None:
                excluded.setdefault(uid, []).append(row)
        missing = sorted({row['requirement'] for row in prior_scope['included']} -
                         (self.requirements.included.keys() | excluded.keys()))
        if missing:
            raise CheckError('scope.predecessor-unaccounted', 'approved predecessor obligations need explicit current membership or reviewed exclusion', refs=missing)
        for member in prior_scope['included']:
            uid = member['requirement']
            if uid in self.requirements.included:
                continue
            record = member.get('record_ref') or {'commit':owner.content_commit,
                'path':'requirements/items/'+uid+'.yml',
                'sha256':digest(self.store.read(owner.content_commit,'requirements/items/'+uid+'.yml'))}
            configuration = member.get('configuration_ref') or {'commit':owner.content_commit,
                'path':'requirements/items/.doorstop.yml',
                'sha256':digest(self.store.read(owner.content_commit,'requirements/items/.doorstop.yml'))}
            choices = [row.get('predecessor') or row.get('requirement') for row in excluded[uid]]
            if not any(isinstance(ref,dict) and ref.get('record_ref')==record and
                       ref.get('configuration_ref')==configuration for ref in choices):
                raise CheckError('scope.predecessor-disposition', 'exclusion must identify the actual selected predecessor record and original configuration', refs=[uid,baseline])


    def _manifest(self, intake_review):
        refs = References(self.context)
        required, contextual = self.reviews.inputs('engineering')
        for reference in required + contextual:
            refs.add(reference)
        refs.fixed(self.context.configuration)
        paths = ['reviews/intake.yaml', 'reviews/global.yaml', *self.reviews.batches, 'reviews/engineering.yaml']
        for path in paths:
            refs.file(self.context.vr + '/' + path)
            value = intake_review if path == 'reviews/intake.yaml' else self.context.read(path, 'review')
            refs.fixed(value)
            # Entries at C can omit commit before the author saves C. They must
            # still be in the BL closure, including legitimate extra context.
            for reference in value['reviewed_inputs'] + value['context_refs']:
                refs.add(reference)
        for reference in self.history.content_references(self.historical_refs):
            refs.add(reference)
        return refs.result()

    def check(self):
        content = self.requirements.check_content()
        intakes = []
        # G0 enters through current declarations and resolves each fixed delta
        # predecessor itself. An inherited package need not be redeclared at C.
        for entry in self.requirements.sources.manifest['intakes']:
            identity = entry['id']
            snapshot = {**self.context.snapshot, 'gate': 'G0', 'phase': 'intake', 'subject': 'intake:' + identity,
                        'baseline_ref': None}
            intake_context = replace(self.context, snapshot=snapshot, baseline=None)
            intakes.append(check_intake(intake_context))
        self.delivery = DeliveryIndex(self.requirements)
        delivery = self.delivery.check()
        feasibility = check_feasibility(self.delivery)
        self.reviews = ReviewScope(self.requirements, self.delivery)
        reviewed = self.reviews.check()
        self._historical_baselines()
        native = self.requirements.verify_native()
        self.required = self._manifest(self.context.read('reviews/intake.yaml', 'review'))
        return {'rule_id': 'G1.content', 'result': 'passed', 'object_refs': ['version:' + self.context.version['version']],
                'evidence': {'content_commit': self.context.content_commit, 'prospective_baseline': self.delivery.map['baseline'],
                             'content': content, 'intakes': [x['object_refs'][0] for x in intakes],
                             'delivery': delivery, 'feasibility': feasibility, 'reviews': reviewed, 'native': native,
                             'content_manifest': self.required,
                             'scope': 'content eligible for approval; no baseline record/publication or implementation permission'},
                'next_owner': 'integrator'}


class BaselineRecord:
    """核对 C/B/批准和实际发布；只读，不生成批准或获取/发布 Git 对象。"""
    def __init__(self, context, *, history=None):
        self.context, self.store = context, context.store
        self.history = history or BaselineHistory(context)
        self.baseline = context.baseline
        self.reference = context.snapshot['baseline_ref']
        self.refs = References(context)

    def _approvals(self):
        roles = {'product-owner', 'engineering-owner', 'qa-owner'}
        approvals = self.baseline['approvals']
        if len(approvals) != 3 or {a['role'] for a in approvals} != roles:
            raise CheckError('baseline.approval-roles', 'one explicit approval for each of the three roles is required')
        for approval in approvals:
            if (approval['actor'] != self.context.version['owners'][approval['role']] or
                    approval['content_commit'] != self.context.content_commit):
                raise CheckError('baseline.approval-binding', 'approval actor/role/content differs from the fixed Version and C')
            try:
                instant = datetime.fromisoformat(approval['at'])
                if instant.tzinfo is None:
                    raise ValueError('timezone required')
            except ValueError as error:
                raise CheckError('baseline.approval-time', 'approval requires an actual timestamp with timezone') from error
            if not self.store.ref(approval['evidence_ref']).strip():
                raise CheckError('baseline.approval-evidence', 'approval evidence must be readable and nonempty')
            self.refs.add(approval['evidence_ref'])
        # Evidence is a fixed human decision, not a signature authenticated by
        # this checker. The local trial still needs the configured owners' review.

    def _manifest(self, required):
        actual = {}
        for entry in self.baseline['content_manifest']:
            key = (entry.get('commit', self.context.content_commit), entry['path'])
            if key in actual:
                raise CheckError('baseline.manifest-duplicate', 'a fixed file may occur only once in the baseline manifest', refs=[entry])
            data = self.store.ref(entry, default_commit=self.context.content_commit)
            if 'revision' in entry:
                if not re.fullmatch(r'requirements/items/R-[0-9]{3,}\.yml', entry['path']):
                    raise CheckError('baseline.manifest-revision', 'manifest revision is only a Requirement revision', refs=[entry])
                record = validate('requirement', parse_yaml(data))
                if entry['revision'] != record['revision']:
                    raise CheckError('baseline.manifest-revision', 'manifest revision differs from the fixed Requirement', refs=[entry])
            actual[key] = digest(data)
            self.refs.add(entry)
        expected = {(entry['commit'], entry['path']): entry['sha256'] for entry in required}
        if actual != expected:
            raise CheckError('baseline.manifest-coverage', 'BL manifest must equal the complete reviewed content closure',
                             refs=[{'missing': sorted(set(expected) - set(actual)), 'extra': sorted(set(actual) - set(expected))}])

    def _control(self, requirements, *, origin_revision=None):
        revision = self.context.snapshot['control_revision']
        if revision is None:
            raise CheckError('baseline.control-required', 'first record requires an initialized control/ID history')
        control = read_control(self.store, revision, previous=self.context.snapshot.get('previous_control_revision'))
        config = self.context.configuration
        mode = config.get('id_allocation_mode', 'serial')
        allocation_revision = origin_revision or revision
        original = control if allocation_revision == revision else read_control(self.store, allocation_revision)
        allocations = original['allocations']
        used = {}
        continued = {}
        if self.baseline['supersedes'] is not None:
            continued = self.history.check(self.baseline['supersedes'])['evidence']['control']['requirements']
        for uid in requirements.records:
            # transition is relative to the previous Version, not to each BL.
            # Unchanged same-Version members may remain added/modified; their
            # existing identity does not need a new allocation after a policy change.
            if uid in continued:
                used[uid] = continued[uid]
                continue
            membership = requirements.included[uid]
            if membership['transition'] in ('inherited', 'modified'):
                prior = self.history.check(membership['predecessor']['baseline_ref'])
                identities = prior['evidence']['control']['requirements']
                if uid not in identities:
                    raise CheckError('ids.predecessor', 'original baseline does not establish this stable identity', refs=[uid])
                used[uid] = identities[uid]
                continue
            number = int(uid.split('-')[1])
            matching = [row for row in allocations.values() if row['start'] <= number <= row['end']]
            if matching:
                row = matching[0]
                used[uid] = require_reservation(original, uid, row['owner'], self.context.version['delivery_line'])
            elif mode == 'reserved':
                raise CheckError('ids.not-reserved', 'reserved allocation mode requires a consumed range for every new R', refs=[uid])
            else:
                used[uid] = 'serial-integrator'
        # The original observation fixes the allocation context. Appending a
        # range later cannot reserve an already established serial identity,
        # including identities continued through another baseline/Version.
        for uid, identity in used.items():
            number = int(uid.split('-')[1])
            for row in control['allocations'].values():
                if row['start'] <= number <= row['end'] and row['reservation_id'] != identity:
                    raise CheckError('ids.origin-conflict', 'current reservation conflicts with the original baseline identity allocation',
                                     refs=[uid, row['reservation_id']])
        for row in control['allocations'].values():
            self.refs.add(row['evidence_ref'])
        for item in control['events']:
            self.refs.add(item['event_ref'])
            self.refs.add(item['event']['evidence_ref'])
        return {'revision': revision, 'allocation_revision': allocation_revision, 'mode': mode, 'requirements': used,
                'scope': 'identity and immutable envelopes; no dispatch/hold permission'}

    @staticmethod
    def _metadata(path):
        # These inputs are separately bound and compared to C below. Do not
        # ignore src/tests/main Specs, CI, dependency locks or arbitrary paths.
        return (path.startswith('requirements/') or path.startswith('harness/version-requirements/') or
                path == 'scripts/requirements-check')

    def _engineering(self, origin, revision):
        before, after = self.store.tree(origin), self.store.tree(revision)
        from .runtime import reviewed_implementation
        from .ui_metadata import reviewed_metadata
        tool_metadata = reviewed_implementation(replace(self.context, content_commit=revision))
        design_metadata = reviewed_metadata(self.context, self.context.snapshot,
                                             self.context.read('reviews/engineering.yaml', 'review'))
        changed = [p for p in before.keys() | after.keys()
                   if not self._metadata(p) and p not in tool_metadata and p not in design_metadata and before.get(p) != after.get(p)]
        if changed:
            raise CheckError('baseline.engineering-changed', 'business code/Specs/config changed since the reviewed engineering origin; return to S3',
                             refs=sorted(changed))

    def _materialized(self, revision):
        # Approved content must survive metadata publication byte for byte.
        # RC/control records and later approvals are retained independently:
        # they may append after C and must not be frozen as approved content.
        # Historical content remains at its pinned commits, not copied here.
        current = self.store.tree(self.context.content_commit)
        for ref in self.baseline['content_manifest']:
            # Raw intake bytes may have been received before C. If C still
            # selects these bytes at this path, publication must preserve them
            # too. A different historical R at a reused path stays pinned.
            if (ref['path'] in current and
                    digest(self.store.read(self.context.content_commit, ref['path'])) == ref['sha256']):
                if re.fullmatch(re.escape(self.context.vr) + r'/change-requests/RC-[0-9]{3,}\.yaml', ref['path']):
                    # An explicit Review context may pin an early RC event.
                    # Retain those exact bytes at C; the live RC record may
                    # append later decisions, never rewrite the reviewed prefix.
                    actual = self.store.read(revision, ref['path'])
                    if digest(actual) != ref['sha256']:
                        from .control import check_source_append
                        validate('events', parse_yaml(self.store.ref(ref, default_commit=self.context.content_commit)))
                        validate('events', parse_yaml(actual))
                        check_source_append(self.store, {'commit':self.context.content_commit, **ref},
                                            {'commit':revision, 'path':ref['path'], 'sha256':digest(actual)})
                        continue
                self.store.read(revision, ref['path'], ref['sha256'])

    def _observation(self, publication):
        reference = self.context.snapshot['publication_evidence_ref']
        value = parse_json(self.store.ref(reference))
        expected = {'gate': 'G1', 'phase': 'effective', 'subject': 'baseline:' + self.baseline['id'],
                    'result': 'passed', 'exit_code': 0, 'evaluation_mode': 'current',
                    'version': self.context.version['version'], 'delivery_line': self.context.version['delivery_line'],
                    'head_revision': self.context.content_commit, 'target_revision': publication, 'baseline': self.reference}
        if not isinstance(value, dict) or any(value.get(k) != v for k, v in expected.items()):
            raise CheckError('baseline.publication-observation', 'publication observation belongs to a different phase, mode, Version/line or C/B/target')
        diagnostics = value.get('diagnostics')
        if (not isinstance(diagnostics, list) or len(diagnostics) != 1 or not isinstance(diagnostics[0], dict) or
                diagnostics[0].get('rule_id') != 'G1.effective' or diagnostics[0].get('result') != 'passed' or
                not isinstance(diagnostics[0].get('evidence'), dict) or
                diagnostics[0]['evidence'].get('publication_commit') != publication):
            raise CheckError('baseline.publication-observation', 'a direct current/effective publication observation is required')
        from .runtime import reviewed_implementation
        runtime = value.get('runtime')
        expected_rules = reviewed_implementation(replace(self.context))
        if not isinstance(runtime, dict) or runtime.get('implementation_files') != expected_rules:
            raise CheckError('baseline.publication-rules', 'original observation does not use the recognized reviewed rule snapshot')
        control = value.get('control_revision')
        if control is None or self.context.snapshot['control_revision'] is None or not self.store.ancestor(control, self.context.snapshot['control_revision']):
            raise CheckError('baseline.publication-control', 'original observed control is not retained in the selected control line')
        self.refs.add(reference)
        return control

    def _publication(self, origin):
        target = self.context.snapshot['target_revision']
        path = self.reference['path']
        if self.store.git('rev-parse', '--is-shallow-repository').strip() == b'true':
            raise InputError('git.shallow', 'complete integration history is required for baseline publication')
        chain, head = published_chain(self.context, target)
        predecessor = self.baseline['supersedes']
        prior_publication = None
        if predecessor is not None:
            prior = validate('baseline', parse_yaml(self.store.ref(predecessor)))
            if prior['version'] != self.baseline['version'] or prior['id'] == self.baseline['id']:
                raise CheckError('baseline.predecessor-owner', 'supersedes requires a different baseline of this same Version')
            checked = self.history.check(predecessor)
            prior_publication = checked['evidence']['publication_commit']
            self.refs.add(predecessor)
        if path not in chain and ((predecessor is None and head is not None) or
                (predecessor is not None and (head is None or predecessor['path'] != head or
                 digest(self.store.read(target, head)) != predecessor['sha256']))):
            raise CheckError('baseline.stale-predecessor', 'new baseline must extend the selected target current head')
        if path not in self.store.tree(target):
            if self.context.snapshot.get('publication_revision'):
                raise CheckError('baseline.published-rewrite', 'previously observed BL is missing from the current target')
            self._engineering(origin, target)
            if self.context.snapshot['phase'] == 'effective':
                raise CheckError('baseline.not-published', 'retained record has not been published to the selected integration line')
            return None
        published = self.context.snapshot.get('publication_revision') or target
        if not self.store.ancestor(published, target):
            raise CheckError('baseline.publication-ancestry', 'observed publication is not integrated in the selected target')
        # An ancestor containing B may never have been a remote branch tip.
        # Without an explicit earlier observation, check the actual target now.
        for revision in {published, target}:
            self.store.read(revision, path, self.reference['sha256'])
        if prior_publication is not None and (prior_publication == published or not self.store.ancestor(prior_publication, published)):
            raise CheckError('baseline.predecessor-publication', 'predecessor must actually be published before its successor')
        self._engineering(origin, published)
        self._materialized(published)
        for revision in self.store.git('rev-list', '--ancestry-path', published + '..' + target).decode().splitlines():
            if (path not in self.store.tree(revision) or
                    digest(self.store.read(revision, path)) != self.reference['sha256']):
                raise CheckError('baseline.published-rewrite', 'observed BL was removed or changed in subsequently integrated history')
        return published

    def _retention(self, publication=None):
        commits = {self.context.content_commit, self.reference['commit'], self.context.version['starting_commit']}
        if publication:
            commits.add(publication)
        commits.update(ref['commit'] for ref in self.refs.result())
        config = self.context.configuration
        names = [config['pin_namespace'] + c for c in sorted(commits)]
        actual = {}
        for start in range(0, len(names), 100):
            actual.update(self.store.remote_refs(config['authority_remote'], names[start:start + 100]))
        for commit in sorted(commits):
            name = config['pin_namespace'] + commit
            if actual.get(name) != commit:
                raise CheckError('baseline.retention', 'required authority pin is absent or does not point directly to its named commit', refs=[name])
        return {'authority_remote': config['authority_remote'], 'pins': names,
                'retrieval': 'all fixed files readable in supplied repository; independent fetch/clone is an operator prerequisite',
                'protection_scope': config['support']}

    def check(self):
        if self.baseline is None:
            raise CheckError('snapshot.baseline-required', 'record/effective require a fixed BL descriptor')
        number = self.baseline['id'].removeprefix('BL-' + self.context.version['version'] + '-')
        if not number.isdigit() or int(number) < 1:
            raise CheckError('baseline.identity', 'baseline number must be positive within its Version')
        if self.reference['path'] in self.store.tree(self.context.content_commit):
            raise CheckError('baseline.circular-content', 'C must precede its own BL descriptor; record B is saved separately')
        self._approvals()
        origin_control = None
        if self.context.snapshot.get('publication_revision'):
            origin_control = self._observation(self.context.snapshot['publication_revision'])
        if self.baseline['supersedes'] is not None:
            self.history.check(self.baseline['supersedes'])
        engineering = self.context.read('reviews/engineering.yaml', 'review')['engineering']
        origin = engineering['code_ref']['commit']
        snapshot = {**self.context.snapshot, 'phase': 'content', 'subject': 'version:' + self.context.version['version'],
                    'baseline_ref': None, 'metadata_revision': self.context.content_commit, 'target_revision': origin}
        snapshot.pop('publication_revision', None)
        snapshot.pop('publication_evidence_ref', None)
        content = BaselineContent(replace(self.context, snapshot=snapshot, baseline=None), history=self.history, predecessor=self.baseline['supersedes'])
        checked = content.check()
        if checked['evidence']['prospective_baseline'] != self.baseline['id']:
            raise CheckError('baseline.map-identity', 'the reviewed delivery map names a different prospective baseline')
        self._manifest(content.required)
        control = self._control(content.requirements, origin_revision=origin_control)
        from .requirement_changes import baseline_approval
        rc = baseline_approval(self.context, control_revision=origin_control or self.context.snapshot['control_revision'])
        if rc is not None:
            self.refs.fixed(rc)
        self.refs.add(self.reference)
        self.refs.fixed(self.context.configuration)
        for revision in {self.context.content_commit, self.reference['commit'], self.context.snapshot['metadata_revision']}:
            self._engineering(origin, revision)
            self._materialized(revision)
        published = self._publication(origin)
        retention = self._retention(published)
        return {'rule_id': 'G1.' + self.context.snapshot['phase'], 'result': 'passed',
                'object_refs': [self.context.snapshot['subject']],
                'evidence': {'content_commit': self.context.content_commit, 'baseline_ref': self.reference,
                             'engineering_origin': origin, 'publication_commit': published,
                             'target_revision': self.context.snapshot['target_revision'],
                             'content': checked['evidence'], 'control': control, 'retention': retention,
                             'approvals': self.baseline['approvals'],
                             'scope': 'fixed baseline checks in local-controlled-trial; human approval authenticity and target protection require operator review; no OpenSpec/Apply permission'},
                'next_owner': 'integrator'}


def check_baseline(context):
    if context.snapshot['phase'] == 'content':
        return BaselineContent(context).check()
    return BaselineHistory(context).run(context)
