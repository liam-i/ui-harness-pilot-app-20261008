"""固定 S3 输入的分层阅读投影；复用检查器，不管理状态或判断当前释放。"""
from collections import Counter, defaultdict
from graphlib import CycleError, TopologicalSorter
import json

from .core import canonical_bytes, digest
from .delivery import DeliveryIndex
from .errors import CheckError, InputError
from .feasibility import build_stage_graph, check_feasibility
from .models import unique
from .relations import condition
from .rendering import fence
from .requirements import RequirementIndex
from .runtime import implementation_manifest

NOTICE = '固定 S3 规划视图；生成成功不是 G1 通过，不判断当前可用性、释放许可、并行组或工期。'
FILTERS = {'kind': {'implementation','integration','release'}, 'strength': {'hard','soft','informational'},
           'checkpoint': {'apply-start','integration','merge','completion','release'}}


def selected_filters(requirements, supplied):
    supplied = supplied or {}
    if set(supplied) - (FILTERS.keys() | {'acceptance'}):
        raise InputError('report.filter', 'unknown engineering filter')
    allowed = {**FILTERS, 'acceptance': {uid+'/'+ac for uid, row in requirements.records.items() for ac in row['acs']}}
    result = {}
    for key, values in supplied.items():
        if not isinstance(values, (list, tuple)) or not values or not all(isinstance(v, str) for v in values) or not set(values) <= allowed[key]:
            raise InputError('report.filter', 'filter must select existing current ACs or supported values', refs=[key])
        result[key] = sorted(set(values))
    return result


def applicability(store, entry, identity):
    try:
        return {'value': 'applies' if condition(store, entry, location=identity) else 'not-applicable'}
    except CheckError as error:
        return {'value': 'unreadable' if error.unreadable else 'unknown', 'diagnostic': error.diagnostic()}


def structural_metrics(edges):
    """Unweighted structure only; never infer duration or executable batches."""
    incoming, outgoing, graph = Counter(), Counter(), {}
    for row in edges:
        if row['strength'] != 'hard' or row['applicability']['value'] != 'applies':
            continue
        provider, consumer = row['provider'], row['consumer']
        incoming[consumer] += 1; outgoing[provider] += 1
        graph.setdefault(consumer, set()).add(provider); graph.setdefault(provider, set())
    depth, cycle = {}, []
    try:
        for node in TopologicalSorter(graph).static_order():
            depth[node] = max((depth[p]+1 for p in graph[node]), default=0)
    except CycleError as error:
        cycle = error.args[1]
    return {'edge_counts': {n:{'fan_in':incoming[n],'fan_out':outgoing[n]} for n in sorted(graph)},
            'dependency_depth': depth if not cycle else None, 'cycle': cycle,
            'meaning': '所选 active hard 边的无权结构；不是跨阶段可行性、关键路径工期或并行许可'}


def prepare(context, *, filters=None):
    if (context.snapshot['gate'], context.snapshot['phase']) != ('G1','content'):
        raise InputError('report.snapshot', 'engineering view requires an explicit G1/content snapshot')
    r = RequirementIndex(context)
    filters = selected_filters(r, filters)
    mapping = context.read('delivery-map.yaml', 'delivery_map')
    plan = context.read('verification-plan.yaml', 'verification_plan')
    review = context.read('reviews/engineering.yaml', 'review')
    candidates = unique(mapping['candidates'], 'candidate_id', location='delivery-map')
    endpoints = unique(mapping['endpoints'], 'id', location='delivery-map')
    if candidates.keys() & endpoints.keys():
        raise CheckError('delivery.node-identity', 'candidate/endpoint IDs must not collide')
    checks, stages = [], {}
    def check(name, action):
        try:
            value = action()
            checks.append({'check':name, 'result':'passed', 'evidence':value})
            return True
        except CheckError as error:
            checks.append({'check':name, 'result':'unreadable' if error.unreadable else 'failed', 'diagnostic':error.diagnostic()})
            return False
    check('S2-content', r.check_content)
    delivery = None
    try:
        delivery = DeliveryIndex(r)
    except CheckError as error:
        checks.append({'check':'S3-structure', 'result':'unreadable' if error.unreadable else 'failed', 'diagnostic':error.diagnostic()})
    if delivery is not None and check('S3-structure', delivery.check):
        try:
            stages = build_stage_graph(delivery)
        except CheckError:
            # The common feasibility check below reports the exact rule. An
            # invalid stage contract must not be drawn as a valid stage graph.
            pass
        check('S3-feasibility', lambda: check_feasibility(delivery))
    else:
        checks.append({'check':'S3-feasibility', 'result':'not-run', 'reason':'S3 structure did not pass'})

    nodes, hierarchy, semantic, node_records = {}, [], [], {}
    def requirement_node(info, scope):
        identity = 'r:'+digest(canonical_bytes([info['uid'], info['record_ref'], info['configuration_ref'],
                                              info['owner'].content_commit, info['owner'].vr,
                                              scope.content_commit, scope.vr]))
        title = info['uid']+' @ '+info['owner'].version['version']+' / C '+info['owner'].content_commit[:8]
        if (scope.content_commit, scope.vr) != (info['owner'].content_commit, info['owner'].vr):
            title += ' / scope '+scope.version['version']+' C '+scope.content_commit[:8]
        nodes[identity] = {'id':identity, 'label':title,
                           'kind':'requirement', 'record_ref':info['record_ref'], 'configuration_ref':info['configuration_ref'],
                           'context_commit':info['owner'].content_commit, 'version':info['owner'].version['version'],
                           'delivery_line':info['owner'].version['delivery_line'],
                           'scope_commit':scope.content_commit, 'scope_version':scope.version['version'],
                           'scope_delivery_line':scope.version['delivery_line']}
        node_records[identity] = (info, scope)
        return identity
    def target(reference, owner=None):
        owner = owner or context
        try:
            info, scope = r.relation_target(owner, reference)
            return requirement_node(info, scope)
        except CheckError as error:
            identity = 'unresolved:'+digest(canonical_bytes([reference, owner.content_commit, owner.vr]))
            nodes[identity] = {'id':identity, 'label':reference if isinstance(reference,str) else reference['requirement'],
                               'kind':'unresolved', 'reference':reference, 'diagnostic':error.diagnostic()}
            return identity
    visited_parents = set()
    def parents(info):
        pending = [(info, context)]
        while pending:
            child, scope = pending.pop(); identity = requirement_node(child, scope)
            if identity in visited_parents:
                continue
            visited_parents.add(identity)
            reference = child['value']['hierarchy']['parent']
            if reference is not None:
                provider = target(reference,scope)
                hierarchy.append({'id':child['uid']+'/parent', 'provider':provider,'consumer':identity,
                                  'kind':'parent-to-child','origin_ref':child['record_ref']})
                if provider in node_records: pending.append(node_records[provider])
    selected_acs = set(filters.get('acceptance', []))
    for uid, info in sorted(r.records.items()):
        current = requirement_node(info, context)
        value = info['value']
        acs = {uid+'/'+ac for ac in info['acs']}
        if not selected_acs or selected_acs & acs:
            parents(info)
        for entry in value['relationships'] + value['constraints']:
            identity, kind = uid+'/'+entry['id'], entry.get('type','constraint')
            strength = entry.get('strength','informational')
            involved = {uid+'/'+ac for ac in entry.get('applies_to',info['acs'])}
            reference = entry.get('target',entry.get('requirement'))
            if isinstance(reference,str) and reference in r.records:
                involved |= {reference+'/'+ac for ac in entry.get('target_acceptance',entry.get('acceptance',r.records[reference]['acs']))}
            if selected_acs and not selected_acs & involved or filters.get('strength') and strength not in filters['strength']:
                continue
            semantic.append({'id':identity, 'provider':target(reference), 'consumer':current, 'kind':kind,
                'strength':strength, 'directed':kind not in ('related-to','conflicts-with'),
                'applicability':{'value':'informational'} if strength=='informational' else applicability(r.store,entry,identity),
                'origin_ref':info['record_ref'], 'source':entry})

    allocations = {key+'/'+row['id']:row for key,node in (candidates|endpoints).items() for row in node['allocation']}
    def allocation_acs(row, subset=None):
        uid = row['requirement']; current = r.records.get(uid)
        historical = row.get('requirement_ref')
        if current is None or historical and any(historical[k] != current[k] for k in ('record_ref','configuration_ref')):
            return set()
        return {uid+'/'+ac for ac in (row['acceptance'] if subset is None else subset)}
    delivery_nodes = {key:{'id':key,'label':key,'kind':'candidate' if key in candidates else node['kind'],
                           'version':node.get('version',context.version['version']),
                           'delivery_line':node.get('delivery_line',context.version['delivery_line']),
                           'source':node} for key,node in (candidates|endpoints).items()}
    execution = []
    for cid,node in sorted(candidates.items()):
        if node['disposition'] != 'planned':
            continue
        for edge in node['predecessor_edges']:
            provider = edge.get('candidate',edge.get('endpoint'))
            required = edge['required_contribution']
            acs = set()
            if required.get('allocation_ref') in allocations:
                acs |= allocation_acs(allocations[required['allocation_ref']],required['acceptance'])
            for ref in edge.get('consumer_contribution', [cid+'/'+a['id'] for a in node['allocation']]):
                if ref in allocations: acs |= allocation_acs(allocations[ref])
            if selected_acs and not selected_acs & acs or any(filters.get(k) and edge[k] not in filters[k] for k in FILTERS):
                continue
            execution.append({'id':edge['id'], 'provider':provider, 'consumer':cid, 'kind':edge['kind'],
                'strength':edge['strength'], 'checkpoint':edge['checkpoint'], 'provider_stage':edge['provider_stage'],
                'applicability':applicability(r.store,edge,edge['id']), 'availability':'not-evaluated-at-S3',
                'acceptance_refs':sorted(acs), 'source':edge})
            if provider not in delivery_nodes:
                delivery_nodes[provider] = {'id':provider,'label':provider,'kind':'unresolved'}
    if filters:
        visible = {e[k] for e in execution for k in ('provider','consumer')}
        if selected_acs and not any(filters.get(k) for k in FILTERS):
            visible |= {key for key,node in (candidates|endpoints).items() if any(selected_acs & allocation_acs(a) for a in node['allocation'])}
        delivery_nodes = {key:row for key,row in delivery_nodes.items() if key in visible}
    if selected_acs:
        visible = {e[k] for e in hierarchy+semantic for k in ('provider','consumer')}
        visible |= {requirement_node(info, context) for uid,info in r.records.items() if any(ac.startswith(uid+'/') for ac in selected_acs)}
        nodes = {key:row for key,row in nodes.items() if key in visible}
    resources = defaultdict(list)
    for cid,node in candidates.items():
        if node['disposition']=='planned':
            for resource in node['shared_resources']: resources[resource].append(cid)
    shared = {key:sorted(values) for key,values in sorted(resources.items()) if len(values)>1}
    issues = [{'id':qid,'status':r.questions.values[qid]['status'],
               'source_refs':sorted(group['source_refs']), 'affected_requirements':sorted(group['affected_requirements']),
               'blocking_for':sorted(group['blocking_for']), 'record_path':r.questions.paths[qid]}
              for qid,group in sorted(r.questions.impacts.items())]
    inputs = {'snapshot':context.snapshot, 'filters':filters, 'resolved_inputs':context.store.manifest(),
              'generator_manifest':implementation_manifest()}
    model = {'kind':'generated-s3-engineering-view', 'notice':NOTICE,
             'generated_from':{**inputs,'sha256':digest(canonical_bytes(inputs))},
             'version':context.version['version'],'delivery_line':context.version['delivery_line'],
             'filter_scope':'AC/strength filter requirement relations; all filters select delivery edges. Checks, Q, resources and stage graph remain whole-version.',
             'requirements':list(nodes.values()), 'hierarchy':hierarchy, 'semantic':semantic,
             'delivery_nodes':list(delivery_nodes.values()), 'delivery_edges':execution,
             'stage_predecessors':{key:sorted(values) for key,values in sorted(stages.items())},
             'checks':checks, 'questions':issues, 'shared_exclusive_resources':shared,
             'assumptions':review.get('engineering',{}).get('assumptions',[]),
             'verification_plan_ref':{'commit':context.content_commit,'path':context.vr+'/verification-plan.yaml',
                                      'sha256':digest(context.store.read(context.content_commit,context.vr+'/verification-plan.yaml'))},
             'structure':structural_metrics(execution), 'gate_evaluated':False}
    return model, {'engineering.json':json.dumps(model,ensure_ascii=False,sort_keys=True,indent=2)+'\n',
                   'engineering.md':render(model,styled=True), 'engineering-basic.md':render(model,styled=False)}


def label(value):
    return ''.join(' ' if c in '\r\n' else '#'+str(ord(c))+';' if c in '\\"[]{}<>&|`#' else c for c in str(value))


def diagram(nodes, edges, *, styled):
    ids = {row['id']:'n'+str(i) for i,row in enumerate(sorted(nodes,key=lambda row:row['id']))}
    if not ids:
        return '没有本筛选范围内的节点；不表示整个版本没有依赖。\n'
    lines = ['flowchart TB']
    for row in sorted(nodes,key=lambda row:row['id']):
        lines.append('    '+ids[row['id']]+'["'+label(row['label'])+'"]')
    for edge in edges:
        text = edge['id']+' '+edge.get('kind','')
        if 'strength' in edge: text += ' / '+edge['strength']+' / '+edge['applicability']['value']
        arrow = '-->' if edge.get('directed',True) else '---'
        lines.append('    '+ids[edge['provider']]+' '+arrow+'|"'+label(text)+'"| '+ids[edge['consumer']])
    if styled:
        lines += ['    classDef planned fill:#eff6ff,stroke:#2563eb,color:#1e3a8a',
                  '    classDef missing fill:#fef2f2,stroke:#dc2626,color:#7f1d1d']
        for row in sorted(nodes,key=lambda row:row['id']):
            lines.append('    class '+ids[row['id']]+' '+('missing' if row['kind']=='unresolved' else 'planned'))
    return fence('\n'.join(lines),'mermaid')


def render(model, *, styled):
    parts = ['# S3 分层依赖与待处理事项\n',NOTICE+'\n',
             '版本：'+model['version']+'；交付线：'+model['delivery_line']+'。\n',
             '输入摘要：'+model['generated_from']['sha256']+'。完整固定引用、筛选条件与原始边见 [结构化视图](engineering.json)。\n',
             '筛选只改变展示；检查、Q、资源竞争和阶段图仍覆盖整个版本。不存在的 AC 筛选拒绝生成。\n',
             '## 需求层级\n','箭头为父项 → 子项；不代表等待或实施顺序。\n',
             diagram(model['requirements'],model['hierarchy'],styled=styled),
             '## 业务关系\n','有向边为提供方 → 消费方，信息关联使用无向线；语义环不自动表示交付死锁。\n',
             diagram(model['requirements'],model['semantic'],styled=styled),
             '## 交付条件\n','箭头为提供方 → 消费候选；边名、强度与适用性不证明当前已满足。\n',
             diagram(model['delivery_nodes'],model['delivery_edges'],styled=styled)]
    parts += ['## 全版本检查与待处理事项\n',
              '下列结果复用 S2/S3 检查，不含完整 Review、原生检查、BL 批准或实时证据判定。失败时保留诊断，不以报告生成成功放行。\n',
              fence(json.dumps({key:model[key] for key in ('checks','questions','assumptions','shared_exclusive_resources')},ensure_ascii=False,indent=2),'json'),
              '## 结构瓶颈\n','深度、扇入与扇出来自所选 hard 且适用的边；没有工期或可并行保证。\n',
              fence(json.dumps(model['structure'],ensure_ascii=False,indent=2),'json'),
              '## 全版本阶段等待图\n','复用可行性检查的抽象里程碑；不替代既有 Propose、Apply、验证、Archive、CI 和 Merge。\n']
    graph = model['stage_predecessors']
    nodes = [{'id':key,'label':key,'kind':'milestone'} for key in graph]
    edges = [{'id':'等待','provider':parent,'consumer':key} for key,values in graph.items() for parent in values]
    parts.append(diagram(nodes,edges,styled=styled) if graph else '阶段图未生成：先处理上方 S3 结构/阶段合同诊断，不绘制推测的有效顺序。\n')
    return '\n'.join(parts)
