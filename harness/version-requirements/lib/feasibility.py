"""S3 的有限阶段可行性证明，不是执行计划、实时调度或候选就绪判定。"""
from graphlib import CycleError, TopologicalSorter

from .errors import CheckError, InputError
from .models import unique
from .reviews import evidence

STAGES = ('start', 'contract', 'apply-start', 'implemented', 'integrated', 'merged')


def build_stage_graph(delivery):
    """Build the same planning milestones for validation and diagnostic views."""
    graph = {}
    for cid in delivery.active:
        previous = None
        for stage in STAGES:
            node = cid + '/' + stage
            graph[node] = {previous} if previous else set()
            previous = node
    graph['version/completion'] = {cid + '/merged' for cid in delivery.active}
    graph['version/release'] = {'version/completion'}
    for eid, edge in delivery.edges.items():
        row = edge['entry']
        kind, checkpoint, stage, satisfaction = (row[k] for k in ('kind', 'checkpoint', 'provider_stage', 'satisfied_when'))
        candidate = edge['provider'] in delivery.active
        if kind == 'implementation':
            valid = checkpoint == 'apply-start' and (
                (candidate and stage == 'merged' and satisfaction == 'merged-and-verified-on-integration-base') or
                (not candidate and (satisfaction == 'provider-available' or
                                    (satisfaction == 'merged-and-verified-on-integration-base' and stage == 'merged'))))
            # Execution release precedes Propose. Planning-only is not a waiver
            # and does not have to be used to prove baseline feasibility.
            consumer = edge['consumer'] + '/start'
        elif kind == 'integration':
            valid = checkpoint in ('integration', 'merge', 'completion') and satisfaction in ('integration-verified', 'provider-available')
            if satisfaction == 'integration-verified' and stage not in ('integrated', 'merged', 'released'):
                valid = False
            consumer = 'version/completion' if checkpoint == 'completion' else edge['consumer'] + '/' + {'integration': 'integrated', 'merge': 'merged'}.get(checkpoint, 'invalid')
        else:
            valid = checkpoint in ('completion', 'release') and satisfaction in ('release-combination', 'provider-available')
            consumer = 'version/' + checkpoint
            # Same-version release is a group condition, not mutual waiting for
            # another participant's earlier release. Local members reach merged.
            if candidate and satisfaction == 'release-combination':
                valid = valid and stage in ('merged', 'released')
                stage = 'merged'
        if not valid:
            raise CheckError('dependency.stage-contract', 'kind/checkpoint/provider stage/satisfaction contradict each other', refs=[eid])
        if not edge['active'] or row['strength'] == 'soft':
            continue
        if candidate:
            provider = 'version/release' if stage == 'released' else edge['provider'] + '/' + stage
            graph[consumer].add(provider)
        # External milestones are feasibility assumptions with named contracts,
        # owners and conditions, not evidence of present availability.
    return graph


def stage_graph(delivery):
    graph = build_stage_graph(delivery)
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise CheckError('dependency.stage-cycle', 'cross-stage waiting cycle', refs=error.args[1]) from error
    return graph


def _eligible(node, done, graph, active, capacity, resources):
    if not graph[node] <= done:
        return False
    if not node.endswith('/start'):
        return True
    candidate = node.removesuffix('/start')
    running = {cid for cid in active if cid + '/start' in done and cid + '/merged' not in done}
    return len(running) < capacity and not any(resources[candidate] & resources[cid] for cid in running)


def feasible_order(graph, active, capacity, resources, *, witness=None, search_limit=20000):
    """Produce/check one admissible finite ordering; exhausted search is unknown.

    Advancing a running milestone only adds evidence or frees capacity, so it can
    safely be saturated before branching on starts. Search never invents a new
    edge, drops a hard edge, or increases the approved capacity.
    """
    if witness is not None:
        if len(witness) != len(graph) or set(witness) != graph.keys():
            raise CheckError('dependency.stage-witness', 'stage_order must name every milestone exactly once')
        done = set()
        for node in witness:
            if not _eligible(node, done, graph, active, capacity, resources):
                raise CheckError('dependency.stage-witness', 'stage_order violates dependency, WIP or exclusive resource', refs=[node])
            done.add(node)
        return list(witness)
    pending = [(frozenset(), ())]
    seen = set()
    examined = 0
    while pending:
        fixed, prefix = pending.pop()
        if fixed in seen:
            continue
        seen.add(fixed)
        examined += 1
        if examined > search_limit:
            raise InputError('dependency.feasibility-unknown', 'bounded resource search exhausted; supply a reviewed stage_order witness or simplify the split')
        done, order = set(fixed), list(prefix)
        while True:
            progress = sorted(n for n in graph if n not in done and not n.endswith('/start') and graph[n] <= done)
            if not progress:
                break
            done.update(progress)
            order.extend(progress)
        if len(done) == len(graph):
            return order
        choices = sorted(n for n in graph if n not in done and n.endswith('/start') and
                         _eligible(n, done, graph, active, capacity, resources))
        for node in reversed(choices):
            pending.append((frozenset(done | {node}), tuple(order + [node])))
    raise CheckError('dependency.capacity-deadlock', 'stage graph has no ordering within the approved WIP/exclusive resources')


def check_feasibility(delivery):
    engineering = delivery.review['engineering']
    for ref in [engineering['code_ref'], engineering['build_evidence_ref'],
                *engineering['spec_refs'], *engineering['shared_contract_refs']]:
        evidence(delivery.store, ref)
    assumptions = unique(engineering['assumptions'], 'id', location='engineering.assumptions')
    for aid, item in assumptions.items():
        if item['resolution_ref']:
            evidence(delivery.store, item['resolution_ref'])
        elif item['blocking']:
            raise CheckError('engineering.unresolved-assumption', 'blocking feasibility assumption needs actual resolution', refs=[aid])
    if engineering['planning_limit'] > 1:
        raise CheckError('engineering.planning-limit', 'this route supports at most one additional planning-only Change')
    if engineering['wip_limit'] > 1 or engineering['planning_limit'] > 0:
        if not engineering['parallel_approval_ref']:
            raise CheckError('engineering.capacity-approval', 'non-default WIP/planning allowance needs an explicit reviewed authorization')
    if engineering['parallel_approval_ref']:
        evidence(delivery.store, engineering['parallel_approval_ref'])
    graph = stage_graph(delivery)
    resources = {cid: set(node['shared_resources']) for cid, node in delivery.active.items()}
    order = feasible_order(graph, delivery.active, engineering['wip_limit'], resources,
                           witness=engineering.get('stage_order'))
    return {'scope': 'S3 finite feasibility only; not a dispatch or present availability', 'stage_order': order,
            'wip_limit': engineering['wip_limit'], 'exclusive_resources': {cid: sorted(items) for cid, items in resources.items()}}
