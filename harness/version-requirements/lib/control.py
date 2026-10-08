"""公共控制读取与编号完整性；不消费 hold/占额，不发布事件。"""
from .core import canonical_bytes
from .errors import CheckError, InputError
from .models import unique, validate

INDEX = "requirements/control/published.yaml"
ALLOCATIONS = "requirements/id-allocations.yaml"


def event(store, reference):
    validate("event_ref", reference)
    document = validate("events", store.yaml(reference["commit"], reference["path"], reference["sha256"]),
                        location=reference["path"])
    events = unique(document["events"], "event_id", location=reference["path"])
    if reference["event_id"] not in events:
        raise CheckError("control.event-missing", "referenced event_id not in fixed file", refs=[reference])
    value = events[reference["event_id"]]
    store.ref(value["evidence_ref"])
    return value


def reservations(store, revision):
    document = validate("id_allocations", store.yaml(revision, ALLOCATIONS), location=ALLOCATIONS)
    rows = unique(document["allocations"], "reservation_id", location=ALLOCATIONS)
    intervals = []
    for identity, row in rows.items():
        start, end = row["start"], row["end"]
        if end < start:
            raise CheckError("ids.range", "reservation end precedes start", refs=[identity])
        for prior_start, prior_end, prior_id in intervals:
            if max(start, prior_start) <= min(end, prior_end):
                raise CheckError("ids.overlap", "reserved IDs cannot be reused, including abandoned IDs", refs=[identity, prior_id])
        intervals.append((start, end, identity))
        used = [int(uid.split("-")[1]) for uid in row["used"]]
        if any(number < start or number > end for number in used) or len(set(used)) != len(used):
            raise CheckError("ids.used", "used IDs do not belong uniquely to reserved range", refs=[identity])
        if row["status"] == "reserved" and used:
            raise CheckError("ids.status", "used IDs require a consumed reservation", refs=[identity])
        store.ref(row["evidence_ref"])
    return rows


def read_control(store, revision, *, previous=None):
    """返回固定发布事件。重复投递同一 ref 合并；同 ID 不允许不同正文。"""
    store.commit(revision)
    if store.git("rev-parse", "--is-shallow-repository").strip() == b"true":
        raise InputError("control.shallow", "complete control history required before append-only verification")
    commits = store.git("rev-list", "--parents", revision).decode().splitlines()
    for row in commits:
        if len(row.split()) > 2:
            raise CheckError("control.merge", "control history must remain a single append-only line")
    if set(store.tree(revision)) != {INDEX, ALLOCATIONS}:
        raise CheckError("control.tree", "control root must contain only publication index and ID reservations")
    current = validate("published", store.yaml(revision, INDEX), location=INDEX)
    references = current["events"]
    allocated = reservations(store, revision)
    # A caller cannot omit previous to hide an intervening deletion/rewrite.
    history = [row.split()[0] for row in reversed(commits)]
    previous_index, previous_allocations = None, {}
    for historical in history:
        if set(store.tree(historical)) != {INDEX, ALLOCATIONS}:
            raise CheckError("control.tree", "control history contains non-control files")
        historical_index = validate("published", store.yaml(historical, INDEX), location=INDEX)["events"]
        historical_allocations = reservations(store, historical)
        if previous_index is not None and historical_index[:len(previous_index)] != previous_index:
            raise CheckError("control.append-only", "published history cannot be removed or rewritten")
        for identity, old in previous_allocations.items():
            new = historical_allocations.get(identity)
            stable = set(old) - {"used", "status"}
            if new is None or any(old[k] != new[k] for k in stable) or not set(old["used"]) <= set(new["used"]):
                raise CheckError("ids.rewrite", "reservation identity/range/evidence cannot be rewritten", refs=[identity])
            if old["status"] != "reserved" and new["status"] != old["status"]:
                raise CheckError("ids.rewrite", "terminal reservation status cannot revert", refs=[identity])
        previous_index, previous_allocations = historical_index, historical_allocations
    if previous:
        if not store.ancestor(previous, revision):
            raise CheckError("control.ancestry", "control history was rewritten")
    resolved, seen = [], {}
    for entry in references:
        reference = entry["event_ref"]
        identity = reference["event_id"]
        if identity in seen:
            if seen[identity] != reference:
                raise CheckError("control.duplicate-id", "event identity refers to different fixed bytes", refs=[identity])
            continue
        seen[identity] = reference
        resolved.append({"event_ref": reference, "event": event(store, reference)})
    return {"revision": revision, "events": resolved, "allocations": allocated,
            "semantics": "envelopes-only; no dispatch/hold/capacity permission"}


def require_reservation(control, uid, owner, line):
    for row in control["allocations"].values():
        if uid in row["used"] and row["owner"] == owner and row["line"] == line and row["status"] == "consumed":
            return row["reservation_id"]
    raise CheckError("ids.not-reserved", "record has no matching consumed reservation", refs=[uid])


def publication_points(store, revision):
    """First publication and its parent after read_control verified history."""
    result = {}
    rows = store.git('rev-list', '--reverse', '--parents', revision).decode().splitlines()
    for row in rows:
        commit, *parents = row.split()
        for item in store.yaml(commit, INDEX)['events']:
            key = canonical_bytes(item['event_ref'])
            if key not in result:
                result[key] = {'published_at': commit, 'previous': parents[0] if parents else None}
    return result


def published_events(store, revision):
    """Execution consumers share predecessor and source append-only checks.

    G1 still uses the mechanical envelope reader. Unsupported business kinds
    must be rejected by execution consumers rather than filtered out here.
    """
    control = read_control(store, revision)
    points = publication_points(store, revision)
    records = {}
    for row in control['events']:
        reference = row['event_ref']
        point = points[canonical_bytes(reference)]
        if point['previous'] is None or row['event'].get('based_on_control') != point['previous']:
            raise CheckError('control.stale-decision', 'new control event must name its actual publication predecessor', refs=[reference])
        check_source_append(store, records.get(reference['path']), reference)
        records[reference['path']] = reference
    return control['events']


def check_source_append(store, previous, reference):
    if previous is None:
        return
    old = store.yaml(previous['commit'], previous['path'])['events']
    new = store.yaml(reference['commit'], reference['path'])['events']
    if previous['path'] != reference['path'] or new[:len(old)] != old:
        raise CheckError('control.record-rewrite', 'published source record must append without rewriting prior events', refs=[reference])
