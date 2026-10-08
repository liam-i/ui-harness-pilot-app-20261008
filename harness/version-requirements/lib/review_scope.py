"""从权威对象计算 S1/S2/S3 审阅范围；不生成审阅结论、摘要或批准。"""
import re

from .assets import AssetIndex
from .core import canonical_bytes, digest
from .errors import CheckError, InputError
from .models import validate
from .questions import QuestionIndex
from .reviews import check_review
from .runtime import reviewed_implementation

GLOBAL_CHECKS = {'business-boundaries', 'flow-and-exceptions', 'cross-document-consistency',
                 'acceptance-feasibility', 'question-disposition'}
BATCH_CHECKS = {'source-fidelity', 'completeness-and-duplicates', 'consistency-and-testability',
                'asset-interpretation', 'question-application'}
ENGINEERING_CHECKS = {'engineering-context', 'delivery-coverage', 'dependency-dispositions',
                      'verification-responsibility', 'stage-feasibility', 'asset-adoption', 'question-applicability'}


class References:
    def __init__(self, context):
        self.context, self.store, self.values = context, context.store, {}
        self._expanded_sources = set()

    def add(self, ref):
        commit = ref.get('commit', self.context.content_commit)
        key = (commit, ref['path'])
        if key in self.values:
            if self.values[key]['sha256'] != ref['sha256']:
                raise CheckError('ref.digest', 'inconsistent digest for an already read fixed input', refs=[ref])
            return
        data = self.store.ref(ref, default_commit=self.context.content_commit)
        self.values[key] = {'commit': commit, 'path': ref['path'], 'sha256': digest(data)}

    def file(self, path, commit=None):
        commit = commit or self.context.content_commit
        if (commit, path) in self.values:
            return
        data = self.store.read(commit, path)
        self.values[(commit, path)] = {'commit': commit, 'path': path, 'sha256': digest(data)}

    def fixed(self, value):
        """只遍历已解析模型中的完整引用，不解析原稿/证据文字里的任意链接。"""
        if isinstance(value, dict):
            if {'commit', 'path', 'sha256'} <= value.keys():
                self.add(value)
                return
            for item in value.values():
                self.fixed(item)
        elif isinstance(value, list):
            for item in value:
                self.fixed(item)

    def result(self):
        return [self.values[key] for key in sorted(self.values)]


class ReviewScope:
    def __init__(self, requirements, delivery):
        self.requirements, self.delivery = requirements, delivery
        self.context, self.store = requirements.context, requirements.store
        self.engineering_context = delivery.context
        self.engineering_questions = (requirements.questions if self.engineering_context.content_commit == self.context.content_commit
                                      else QuestionIndex(self.engineering_context, baseline_questions=requirements.questions))
        self.batches = {}
        prefix = self.context.vr + '/reviews/batches/'
        for path in sorted(self.store.tree(self.context.content_commit)):
            if not path.startswith(prefix):
                continue
            name = path[len(prefix):]
            if not name.startswith('B-') and not name.endswith('.yaml'):
                continue
            if not re.fullmatch(r'B-[0-9]{3,}\.yaml', name):
                raise CheckError('review.batch-path', 'one canonical B-NNN.yaml file per review batch', refs=[path])
            value = validate('review', self.store.yaml(self.context.content_commit, path), location=path)
            if value['id'] != name[:-5] or value['phase'] != 'batch' or 'reviewed_requirements' not in value:
                raise CheckError('review.batch-scope', 'batch ID/phase and explicit reviewed_requirements are required', refs=[path])
            if not set(value['reviewed_requirements']) <= requirements.records.keys():
                raise CheckError('review.batch-scope', 'batch scope cannot count contextual or absent Requirements', refs=[path])
            self.batches[path[len(self.context.vr) + 1:]] = value

    def _source(self, refs, source):
        for owner in source.owner_contexts.values():
            for path in ('version.yaml', 'source/manifest.yaml', 'source/units.yaml'):
                refs.file(owner.vr + '/' + path, owner.content_commit)
            identity = (owner.content_commit, owner.vr)
            if identity not in refs._expanded_sources:
                # Many R origins share these immutable documents. Expand once
                # per reference collection, only after successful validation;
                # another batch or nested audit still collects its own inputs.
                refs.fixed(owner.read('source/manifest.yaml', 'manifest'))
                refs.fixed(owner.read('source/units.yaml', 'units'))
                refs._expanded_sources.add(identity)
        for identity, entry in source.intakes.items():
            original_root = 'requirements/versions/' + identity.split('/')[0]
            for row in entry['files']:
                # Received "other" files are part of package retention too.
                refs.add({'commit': source.intake_commits[identity], 'path': original_root + '/' + entry['root'] + '/' + row['path'],
                          'sha256': row['sha256']})
        for item in source.files.values():
            refs.add(item['received_ref'])
            refs.add(item['content_ref'])

    def _questions(self, refs, questions):
        for identity, value in questions.values.items():
            refs.file(questions.paths[identity], questions.context.content_commit)
            refs.fixed(value)
            for applied in value['applied_to']:
                refs.add({**applied, 'commit': applied.get('commit', questions.application_commits[identity])})

    def _records(self, refs, selected, assets, *, follow_relations=True, scope=None):
        pending, visited = [(info, scope or info['owner']) for info in selected], set()
        while pending:
            info, relation_scope = pending.pop()
            key = canonical_bytes([info['record_ref'], info['configuration_ref'],
                                   info['owner'].content_commit, info['owner'].vr,
                                   relation_scope.content_commit, relation_scope.vr])
            if key in visited:
                continue
            if len(visited) >= 10000:
                raise InputError('review.context-limit', 'review Requirement context exceeds 10000 fixed nodes')
            visited.add(key)
            refs.add(info['record_ref'])
            refs.add(info['configuration_ref'])
            refs.fixed(info['value'])
            owner = info['owner']
            refs.file(owner.vr + '/version.yaml', owner.content_commit)
            refs.file(owner.vr + '/scope.yaml', owner.content_commit)
            refs.file(relation_scope.vr + '/version.yaml', relation_scope.content_commit)
            refs.file(relation_scope.vr + '/scope.yaml', relation_scope.content_commit)
            value = info['value']
            related = [value['hierarchy']['parent']]
            related += [x.get('target', x.get('requirement')) for x in value['relationships'] + value['constraints']]
            for name in ('derived_from', 'supersedes', 'retires'):
                related += value.get(name, [])
            for target in related if follow_relations else ():
                if target is not None:
                    pending.append(self.requirements.relation_target(relation_scope, target))
            for source in value['source_refs']:
                if source['role'] == 'origin':
                    unit = source['unit']
                    source_owner = self.context.at(info['record_ref']['commit'], unit.split('/', 1)[0])
                    self._source(refs, assets._source_index(source_owner))
            qids = value['question_refs'] + [x['decision'] for x in value['source_refs'] if x['role'] == 'clarification']
            for qid in qids:
                qowner = self.context.at(info['record_ref']['commit'], qid.split('/', 1)[0])
                self._questions(refs, self.requirements.question_index(qowner))
            for usage in value['asset_refs']:
                asset_owner = self.requirements.asset_owner(info)
                resolved = assets.resolve_use(usage, owner=asset_owner, acceptance=info['acs'])
                refs.fixed(resolved)

    def _assets(self, refs, assets):
        assets.check_manifest()
        # The declared derivation closure, not incidental historical reads made
        # while detecting overwrite, is what content reviews actually bind.
        for (commit, path), rows in assets._manifests.items():
            refs.file(path, commit)
            refs.fixed(list(rows.values()))
        for value in assets._resolved.values():
            for field in ('manifest_ref', 'received_ref', 'content_ref'):
                refs.add(value[field])
        for source in assets._sources.values():
            self._source(refs, source)

    def inputs(self, phase, selected=()):
        """Return exact required references, independent of authored Review claims.

        Hash lists can be prepared before C by omitting C on current-file entries;
        historical references must retain their real commit. This is a read-only
        mechanical inventory, not permission to update a stale review blindly.
        """
        if phase not in ('global', 'batch', 'engineering'):
            raise InputError('review.phase', 'unsupported upstream review scope')
        if (phase != 'batch' and selected) or not set(selected) <= self.requirements.records.keys():
            raise InputError('review.batch-scope', 'only batch accepts an explicit subset of current scoped Requirements')
        refs, contextual = References(self.context), References(self.context)
        self._source(refs, self.requirements.sources)
        self._questions(refs, self.requirements.questions)
        prefix = 'harness/version-requirements/'
        refs.file(prefix + 'config/project.yaml')
        for path in reviewed_implementation(self.context):
            refs.file(path)
        if phase != 'global':
            assets = AssetIndex(self.context, sources=self.requirements.sources)
            refs.file(self.context.vr + '/scope.yaml')
            refs.file(self.context.vr + '/reviews/global.yaml')
            self._records(refs, [self.requirements.records[uid] for uid in selected]
                          if phase == 'batch' else list(self.requirements.records.values()), assets, scope=self.context)
            # Bind the version-wide cancellation context already selected by
            # scope/Q, without turning discarded draft relations into active
            # dependencies or counting these records as reviewed obligations.
            self._records(refs, self.requirements.excluded_records, assets, follow_relations=False)
            self._assets(refs, assets)
        if phase == 'engineering':
            engineering_context = self.engineering_context
            # R/source/batch contexts stay on the selected BL. Only the
            # engineering map, plan and current rule implementation advance.
            for path in self.batches:
                refs.file(self.context.vr + '/' + path)
            refs.add(self.delivery.map_ref)
            refs.add(self.delivery.verification_plan_ref)
            if engineering_context.content_commit != self.context.content_commit:
                self._questions(refs, self.engineering_questions)
                refs.file(prefix + 'config/project.yaml', engineering_context.content_commit)
                for path in reviewed_implementation(engineering_context):
                    refs.file(path, engineering_context.content_commit)
            refs.fixed(self.delivery.map)
            refs.fixed(self.delivery.plan)
            engineering = self.delivery.review['engineering']
            contextual.fixed(engineering)
            from .ui_integration import review_refs
            for reference in review_refs(self.delivery, required=False):
                contextual.add(reference)
            from .ui_metadata import reviewed_metadata
            reviewed_metadata(engineering_context, engineering_context.snapshot, self.delivery.review)
            if engineering['code_ref']['commit'] != engineering_context.snapshot['target_revision']:
                raise CheckError('review.engineering-target', 'engineering code context must bind the actual target revision')
            for spec in engineering['spec_refs']:
                if spec['commit'] != engineering_context.snapshot['target_revision']:
                    raise CheckError('review.engineering-target', 'current main Spec must be read on the same target revision', refs=[spec])
        return refs.result(), contextual.result()

    def _check_issues(self, value, *, required=None, check_id=None, questions=None):
        questions = questions or self.requirements.questions
        declared = set()
        for qid in value['issue_refs']:
            declared.add(questions.resolve(qid)['id'])
        for check in value['checks']:
            actual = {questions.resolve(qid)['id'] for qid in check['issue_refs']}
            if not actual <= declared:
                raise CheckError('review.issue-coverage', 'check issues must appear in the Review issue set', refs=[value['id'], check['check_id']])
            if required is not None and check['check_id'] == check_id and not set(required) <= actual:
                raise CheckError('review.question-applicability', 'current Q applicability check omits a shared question/impact group', refs=sorted(set(required) - actual))

    def check(self):
        expected = set(self.requirements.sources.units)
        all_issues = set(self.requirements.questions.impacts)
        refs, contextual = self.inputs('global')
        global_review = check_review(self.context, 'reviews/global.yaml', 'global', (), required_refs=refs,
                                     required_context_refs=contextual, source_units=expected,
                                     required_checks=GLOBAL_CHECKS, roles={'product-owner', 'integrator'})
        self._source_scope(global_review, expected)
        self._check_issues(global_review, required=all_issues, check_id='question-disposition')
        covered_units, covered_requirements = set(), set()
        for path, batch in self.batches.items():
            if not set(batch['processed_units'] + batch['pending_units']) <= expected:
                raise CheckError('review.source-coverage', 'batch contains unknown source units', refs=[path])
            refs, contextual = self.inputs('batch', batch['reviewed_requirements'])
            value = check_review(self.context, path, 'batch', (), required_refs=refs, required_context_refs=contextual,
                                 source_units=batch['processed_units'], required_checks=BATCH_CHECKS,
                                 roles={'product-owner', 'engineering-owner', 'qa-owner'})
            self._check_issues(value)
            covered_units.update(value['processed_units'])
            covered_requirements.update(value['reviewed_requirements'])
        if covered_units != expected or covered_requirements != self.requirements.records.keys():
            raise CheckError('review.batch-coverage', 'batch reviews must explicitly cover every source unit and scoped Requirement',
                             refs=sorted((expected - covered_units) | (self.requirements.records.keys() - covered_requirements)))
        engineering = self.check_engineering()
        # Every selected Q file, answer, prior applied_to and current affected
        # scope/R/map is now bound. Whether the answer remains correctly applied
        # is an explicit human check, never inferred from a resolved string.
        return {'scope': 'S1/S2/S3 Review binding; not G1 publication or historical BL effectiveness',
                'global_review': global_review['id'], 'batches': [b['id'] for b in self.batches.values()],
                'engineering_review': engineering['id'], 'reviewed_requirements': sorted(covered_requirements)}

    def check_engineering(self):
        """Current engineering Review, independent of already approved S1/S2.

        The caller must first qualify the selected BL; this method does not
        create a baseline or assume that any unchanged content was approved.
        """
        expected = set(self.requirements.sources.units)
        self.engineering_questions.check_endpoints(expected, self.requirements.question_requirement_ids(), candidates=self.delivery.candidates)
        refs, contextual = self.inputs('engineering')
        from .ui_integration import enabled, CHECKS
        ui_checks = ({'ui-applicability'} | (set(CHECKS) if self.delivery.review['engineering'].get('ui_inputs_ref') else set())) if enabled(self.engineering_context) else set()
        if self.delivery.review['engineering'].get('ui_metadata_refs'):
            ui_checks.add('ui-design-metadata')
        engineering = check_review(self.engineering_context, 'reviews/engineering.yaml', 'engineering', (),
                                   required_refs=refs, required_context_refs=contextual, source_units=expected,
                                   required_checks=ENGINEERING_CHECKS | ui_checks, roles={'engineering-owner'})
        self._source_scope(engineering, expected)
        self._check_issues(engineering, required=set(self.engineering_questions.impacts), check_id='question-applicability',
                           questions=self.engineering_questions)
        return engineering

    def _source_scope(self, review, expected):
        if not set(review['processed_units'] + review['pending_units']) <= expected:
            raise CheckError('review.source-coverage', 'Review contains unknown source units', refs=[review['id']])
