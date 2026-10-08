"""Package closure and consumer checks independent of Harness scheduling."""
from pathlib import PurePosixPath

from .errors import require
from .history import History
from . import media
from .models import parse
from .objects import key


def unique(items, field, code, source):
    keys = [x[field] for x in items]
    require(len(set(keys)) == len(keys), code, "duplicate " + field, source)


def refset(refs):
    return {key(r) for r in refs}


def consumer_key(consumer):
    return consumer["kind"], consumer["subject"], key(consumer["record_ref"]), consumer.get("identity_pointer")


def pointer(document, path):
    if not path.startswith("/"): return None
    try:
        for part in path[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(document, list):
                if not part.isdecimal() or str(int(part)) != part: return None
                document = document[int(part)]
            else:
                document = document[part]
        return document
    except (KeyError, IndexError, ValueError, TypeError):
        return None


class Validator:
    def __init__(self, store, snapshot, root):
        self.store = store; self.snapshot = snapshot; self.root = root
        self.bindings = store.document("bindings", snapshot["bindings_ref"])["bindings"]
        selected = {consumer_key(s["consumer"]) for s in snapshot["selections"]}
        self.requires_ui = any(b["applicability"] != "not-applicable" for b in self.bindings
                               if consumer_key(b["consumer"]) in selected)
        self.history = History(store, snapshot["policy_ref"], snapshot["authorities"], scan=self.requires_ui)
        require(not self.requires_ui or self.history.policy["adoption"]["ui"] == "enabled",
                "policy.adoption", "required/reuse consumer cannot disable UI adoption", str(snapshot["policy_ref"]))
        self.packages = {}; self.approvals = {}; self.identities = {}; self.stack = []
        self.external_objects = []; self.consumers = []

    def approval(self, ref):
        k = key(ref)
        require(k not in self.stack, "package.cycle", "recursive approved-release dependency", str(ref))
        if k in self.approvals: return self.approvals[k]
        decision = self.history.lookup(ref)
        require(decision["kind"] == "approve", "approval.kind", "consumer must select an approval", str(ref))
        package_ref = decision["package_ref"]
        if package_ref["repository"] == ref["repository"]:
            require(package_ref["commit"] != ref["commit"], "approval.order",
                    "approval must not refer to its own content commit", str(ref))
        self.stack.append(k)
        try:
            package = self.package(package_ref)
            child_refs = [x["approved_release_ref"] for x in package["document"]["dependencies"]]
            children = [self.approval(child) for child in child_refs]
            self.store.read(decision["engineering_review_ref"])
            required = set(package["document"]["acceptance"]["required_states"])
            approved = set(decision["scope"]["screen_states"])
            require(required <= approved <= package["states"], "approval.scope", "approval does not cover required states", str(ref))
            require(decision["scope"]["platforms"] == package["document"]["platforms"],
                    "approval.scope", "approval must cover the declared platform contract", str(ref))
            report = self.store.document("closure-report", decision["closure_ref"])
            require(report["content_commit"] == package_ref["commit"], "approval.closure", "reviewed D differs from approved D", str(ref))
            unique(report["packages"], "unit", "approval.closure", str(ref))
            entries = [x for x in report["packages"] if x["package_ref"] == package_ref and x["unit"] == package["document"]["unit"]]
            require(len(entries) == 1, "approval.closure", "review evidence does not name the exact package", str(ref))
            entry = entries[0]
            require(refset(entry["files"]) == refset(package["files"]) and
                    refset(entry["external_inputs"]) == refset(package["external_inputs"]) and
                    entry["dependencies"] == package["document"]["dependencies"] and
                    entry.get("external_objects", []) == package["document"]["external_objects"],
                    "approval.closure", "review evidence differs from the complete fixed input closure", str(ref))
            self.store.read(report["policy_ref"])
            require(report["policy_ref"] in [self.snapshot["policy_ref"], *self.history.policy["basis_refs"]],
                    "approval.policy", "closure review cites a policy outside the selected reviewed basis", str(ref))
            result = dict(ref=ref, decision=decision, package=package, children=children)
            self.approvals[k] = result
            return result
        finally:
            self.stack.pop()

    def package(self, ref):
        k = key(ref)
        if k in self.packages: return self.packages[k]
        doc = self.store.document("package", ref)
        logical = (doc["unit"], doc["release"])
        require(logical not in self.identities or self.identities[logical] == k,
                "package.identity", "same UI unit/release points to different fixed content", str(ref))
        self.identities[logical] = k
        directory = str(PurePosixPath(ref["path"]).parent)
        require(ref["path"] == f"design/units/{doc['unit']}/releases/{doc['release']}/manifest.yaml",
                "package.identity", "manifest path must match its UI identity", str(ref))
        unique(doc["files"], "path", "package.inventory", str(ref))
        tree = self.store.repo(ref["repository"]).tree(ref["commit"])
        declared = {directory + "/" + f["path"] for f in doc["files"]}
        pointer_paths = [x["pointer_path"] for x in doc["external_objects"] if "pointer_path" in x]
        require(len(pointer_paths) == len(set(pointer_paths)) and not
                set(pointer_paths).intersection(f["path"] for f in doc["files"]),
                "package.inventory", "an LFS entry has exactly one owner in external_objects", str(ref))
        declared.update(directory + "/" + p for p in pointer_paths)
        require(ref["path"] not in declared, "package.self-reference", "manifest cannot inventory itself", str(ref))
        actual = {p for p in tree if p.startswith(directory + "/")} - {ref["path"]}
        require(declared == actual, "package.inventory", "package file set mismatch; missing=" +
                str(sorted(declared - actual)) + "; unlisted=" + str(sorted(actual - declared)), str(ref))
        files = []
        for f in doc["files"]:
            file_ref = self.store.same_commit_ref(ref, directory + "/" + f["path"], f["sha256"])
            media.inspect(self.store.read(file_ref), f, str(file_ref)); files.append(file_ref)
        paths = {f["path"] for f in doc["files"]} | set(pointer_paths)
        used = [doc["brief_ref"], doc["producer"]["tool_observation_ref"], doc["acceptance"]["handoff_path"]]
        used += [x["handoff_path"] for x in doc["screens"]]
        used += [x["reference"] for x in doc["states"]]
        used += [x["review_path"] for x in doc["acceptance"]["allowed_differences"]]
        require(set(used) <= paths, "package.references", "handoff/state/producer reference not in inventory", str(ref))
        unique(doc["screens"], "id", "package.states", str(ref))
        unique(doc["states"], "id", "package.states", str(ref))
        unique(doc["flows"], "id", "package.flows", str(ref))
        unique(doc["coverage"], "behavior_ref", "package.coverage", str(ref))
        unique(doc["acceptance"]["allowed_differences"], "id", "package.coverage", str(ref))
        states = {x["id"] for x in doc["states"]}
        require(states == {s["id"] + "/" + name for s in doc["screens"] for name in s["states"]},
                "package.states", "screen and state identities differ", str(ref))
        require(set(doc["acceptance"]["required_states"]) <= states, "package.states", "unknown required state", str(ref))
        for item in doc["coverage"]:
            require(set(item["screen_states"]) <= states, "package.coverage", "coverage names unknown states", str(ref))
        for flow in doc["flows"]:
            require({flow["from"], flow["to"]} <= states, "package.flows", "flow names unknown state", str(ref))
        external_inputs = []
        for item in doc["requirement_refs"]:
            source = item.get("requirement_ref", item)
            self.store.read(source); external_inputs.append(source)
        expected = doc["acceptance"]["expected_ref"]
        self.store.read(expected); external_inputs.append(expected)
        outputs = set()
        for asset in doc["asset_inputs"]:
            self.store.read(asset["source_ref"]); external_inputs.append(asset["source_ref"])
            require(set(asset["outputs"]) <= paths and not outputs.intersection(asset["outputs"]),
                    "asset.owner", "output is unlisted or assigned to multiple production inputs", str(ref))
            outputs.update(asset["outputs"])
            if "owner" in asset:
                owner = asset["owner"]
                record = pointer(parse(self.store.read(owner["manifest_ref"]), str(owner["manifest_ref"])), owner["record_pointer"])
                require(isinstance(record, dict) and record.get("id") == owner["id"] and
                        record.get("sha256") == asset["source_ref"]["sha256"] and
                        owner["id"].startswith(owner["kind"] + "-"),
                        "asset.owner", "original owner identity/content not found at the fixed record pointer", str(ref))
                external_inputs.append(owner["manifest_ref"])
                for output in asset["outputs"]:
                    file = next(f for f in doc["files"] if f["path"] == output)
                    require(file["sha256"] != asset["source_ref"]["sha256"], "asset.owner",
                            "original AST/DAS bytes must keep their owner, not be registered as UI output", str(ref))
        unique(doc["external_objects"], "id", "media.identity", str(ref))
        for obj in doc["external_objects"]:
            if "pointer_path" in obj:
                self.store.lfs_pointer(ref, directory + "/" + obj["pointer_path"], obj)
            self.external_objects.append(media.external(obj, self.snapshot["external_files"], self.root))
        unique(doc["open_questions"], "id", "package.blocker", str(ref))
        for question in doc["open_questions"]:
            require(not question["blocker"] or "resolution_ref" in question,
                    "package.blocker", "unresolved blocking question " + question["id"], str(ref))
            if "resolution_ref" in question:
                self.store.read(question["resolution_ref"]); external_inputs.append(question["resolution_ref"])
        result = dict(ref=ref, document=doc, files=files, external_inputs=external_inputs, states=states)
        self.packages[k] = result
        return result

    def consumer(self, consumer):
        data = self.store.read(consumer["record_ref"])
        if consumer["kind"] in ("contribution", "endpoint"):
            doc = pointer(parse(data, str(consumer["record_ref"])), consumer["identity_pointer"])
            require(doc == consumer["subject"], "binding.identity", "identity not found in original contribution/endpoint record", str(consumer))
        if "association_ref" in consumer: self.store.read(consumer["association_ref"])

    def consume(self):
        snapshot = self.snapshot
        for name in ("head", "target"):
            if name in snapshot["subject"]:
                rev = snapshot["subject"][name]; self.store.repo(rev["repository"]).commit(rev["commit"])
        bindings = self.bindings
        keys = [consumer_key(b["consumer"]) for b in bindings]
        require(len(keys) == len(set(keys)), "binding.identity", "duplicate consumer in binding file")
        selections = snapshot["selections"]
        wanted = [consumer_key(s["consumer"]) for s in selections]
        require(len(wanted) == len(set(wanted)), "binding.identity", "duplicate consumer selection")
        allowed = {"candidate": {"contribution"}, "scope": {"endpoint"}, "task": {"task"}, "change": {"change"}}
        for selection in selections:
            consumer = selection["consumer"]
            require(consumer["kind"] in allowed[snapshot["subject"]["kind"]], "binding.subject", "consumer does not belong to this subject kind")
            if snapshot["subject"]["kind"] in ("task", "change"):
                require(consumer["subject"] == snapshot["subject"]["id"], "binding.subject", "task/Change identity differs from subject")
            self.consumer(consumer)
            matches = [b for b in bindings if consumer_key(b["consumer"]) == consumer_key(consumer)]
            require(len(matches) == 1 and matches[0]["consumer"] == consumer, "binding.missing", "exact selected consumer has no binding", str(consumer))
            binding = matches[0]
            self.store.read(binding["rationale_ref"])
            if binding["applicability"] == "not-applicable":
                require(not binding["approved_releases"] and not binding["coverage"] and not binding["allowed_differences"]
                        and not selection["behaviors"], "binding.applicability", "not-applicable cannot erase selected UI obligations", str(consumer))
            else:
                require(bool(binding["approved_releases"]), "binding.packages", "required/reuse needs fixed approvals", str(consumer))
                approvals = [self.approval(x["approved_release_ref"]) for x in binding["approved_releases"]]
                queue = list(approvals); all_approvals = {}
                while queue:
                    a = queue.pop(); k = key(a["ref"])
                    if k in all_approvals: continue
                    all_approvals[k] = a; queue.extend(a["children"])
                    self.history.permitted(a["package"]["ref"], selection["consumption"])
                unique(binding["coverage"], "behavior_ref", "binding.coverage", str(consumer))
                require(set(selection["behaviors"]) == {x["behavior_ref"] for x in binding["coverage"]} and bool(selection["behaviors"]),
                        "binding.coverage", "bound behavior coverage differs from independently selected obligations", str(consumer))
                for coverage in binding["coverage"]:
                    for state in coverage["screen_states"]:
                        matching = [a for a in all_approvals.values() if state in a["decision"]["scope"]["screen_states"] and
                                    ("unit" not in coverage or (coverage["unit"], coverage["release"]) ==
                                     (a["decision"]["unit"], a["decision"]["release"]))]
                        require(len(matching) == 1, "binding.coverage", "unknown, unapproved or ambiguous state " + state, str(consumer))
                unique(binding["allowed_differences"], "id", "binding.difference", str(consumer))
                for diff in binding["allowed_differences"]:
                    self.store.read(diff["review_ref"])
                    require(any(d["id"] == diff["id"] and d["basis"] == diff["basis"]
                                for a in all_approvals.values() for d in a["package"]["document"]["acceptance"]["allowed_differences"]),
                            "binding.difference", "consumer difference is not in approved design", str(consumer))
            self.consumers.append({"consumer": consumer, "applicability": binding["applicability"],
                                   "coverage": binding["coverage"], "allowed_differences": binding["allowed_differences"]})
