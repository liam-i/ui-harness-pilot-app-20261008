"""Verify all reachable parent edges, not only the final decision directory."""
from hashlib import sha256
from pathlib import PurePosixPath

from .errors import require
from .models import parse, validate
from .objects import key
from .runtime import policy_capabilities


def decision_path(path):
    parts = path.split("/")
    return len(parts) >= 5 and parts[:2] == ["design", "units"] and parts[3] == "decisions"


class History:
    def __init__(self, store, policy_ref, snapshot, scan=True):
        self.store = store; self.policy_ref = policy_ref
        self.policy = store.document("policy", policy_ref)
        policy_capabilities(self.policy)
        self.decisions = {}; self.ids = {}; self.authorities = {}; self.audit = []; self.unclassified = []
        actors = self.policy["actors"]
        require(len({x["actor"] for x in actors}) == len(actors), "policy.actor", "duplicate actor", str(policy_ref))
        self.actors = {x["actor"]: x for x in actors}
        for ref in self.policy["basis_refs"]: store.read(ref)
        for actor in actors:
            for ref in actor["evidence_refs"]: store.read(ref)
        policies = self.policy["authorities"]
        require(len({x["repository"] for x in policies}) == len(policies), "policy.authority", "duplicate authority", str(policy_ref))
        require(len(snapshot) == len(policies), "history.authority", "selected authorities must exactly match policy", str(policy_ref))
        require(len({x["repository"] for x in snapshot}) == len(snapshot), "history.authority", "duplicate selected authority")
        for p in policies:
            matches = [x for x in snapshot if x["repository"] == p["repository"]]
            require(len(matches) == 1 and matches[0]["ref"] == p["ref"], "history.authority", "authority/ref differs from fixed policy", str(p))
            selected = matches[0]
            require(selected["history_root"] == p["history_root"], "history.root", "history root differs from reviewed policy", str(selected))
            self.authorities[p["repository"]] = selected
            if scan: self.scan(selected)
        for ref, decision in self.decisions.values():
            self.reviewers(ref, decision)
            package = store.document("package", decision["package_ref"])
            require((package["unit"], package["release"]) == (decision["unit"], decision["release"]),
                    "approval.identity", "decision unit/release differs from package", str(ref))
            require(ref["path"].split("/")[2] == decision["unit"], "approval.identity", "decision is filed under another unit", str(ref))
            if decision["kind"] != "approve":
                target = self.lookup(decision["approved_release_ref"])
                require(target["kind"] == "approve" and target["package_ref"] == decision["package_ref"],
                        "approval.target", "restriction must target its exact approval and package", str(ref))
                if decision["kind"] == "supersede":
                    replacement = self.lookup(decision["replacement_ref"])
                    require(replacement["kind"] == "approve" and replacement["package_ref"] != decision["package_ref"],
                            "approval.target", "supersession needs a different fixed approved package", str(ref))
        require(not self.unclassified, "history.unclassified", "decision domain contains unreferenced non-decision files", str(self.unclassified))

    def scan(self, selected):
        identity = selected["repository"]; repo = self.store.repo(identity)
        root, tip = selected["history_root"], selected["commit"]
        require(repo.ancestor(root, tip), "history.root", "declared root is not reachable from selected commit", str(selected))
        commits = [root] + repo.git("rev-list", "--reverse", "--topo-order", root + ".." + tip).decode().splitlines()
        included = set(commits); trees = {}; parsed = {}; all_proofs = set()
        for commit in commits:
            tree = {p: v for p, v in repo.tree(commit).items() if decision_path(p)}
            if commit != root:
                parents = repo.git("rev-list", "--parents", "-n", "1", commit).decode().split()[1:]
                for parent in parents:
                    require(parent in included, "history.root", "merge introduces history outside declared root", commit)
                    require(parent in trees, "history.incomplete", "parent history not traversed", parent)
                    for path, entry in trees[parent].items():
                        require(tree.get(path) == entry, "history.append-only", "decision or proof deleted/moved/overwritten", f"{commit}:{path}")
            trees[commit] = tree
            for path, (mode, kind, oid) in tree.items():
                require(mode == "100644" and kind == "blob", "object.mode", "decision domain permits regular non-executable files only", f"{commit}:{path}")
                if (path, oid) in parsed: continue
                data = repo.read(commit, path)
                ref = dict(repository=identity, commit=commit, path=path, sha256=sha256(data).hexdigest())
                doc = parse(data, str(ref)) if path.endswith((".json", ".yaml", ".yml")) else None
                is_decision = path.endswith((".yaml", ".yml")) or isinstance(doc, dict) and doc.get("schema_version") == "ui-decision/1"
                if is_decision:
                    self.store.read(ref)
                    validate("decision", doc, str(ref))
                    previous = self.ids.get(doc["decision_id"])
                    same_observed_authority = False
                    if previous and previous["repository"] != identity:
                        old = self.authorities[previous["repository"]]
                        endpoints = {p["repository"]: p["remote"] for p in self.policy["authorities"]}
                        same_observed_authority = (endpoints[identity] == endpoints[previous["repository"]] and
                            all(old[k] == selected[k] for k in ("ref", "history_root", "commit")) and
                            previous["path"] == path and previous["sha256"] == ref["sha256"])
                    require(previous is None or same_observed_authority, "history.id", "decision ID reused across paths/bytes", str(ref))
                    if previous is None: self.ids[doc["decision_id"]] = ref
                    self.decisions[(identity, path, ref["sha256"])] = (ref, doc)
                    for reviewer in doc["reviewers"]:
                        proof = str(PurePosixPath(path).parent / reviewer["evidence_path"])
                        all_proofs.add(proof)
                parsed[(path, oid)] = is_decision
        final = trees[tip]
        self.unclassified.extend(p for p, v in final.items() if p not in all_proofs and not parsed[(p, v[2])])
        self.audit.append({**selected, "commits": commits, "decision_files": len(final)})

    def lookup(self, ref):
        self.store.read(ref)
        authority = self.authorities.get(ref["repository"])
        require(authority is not None, "history.authority", "approval repository has no declared authority", str(ref))
        require(self.store.repo(ref["repository"]).ancestor(ref["commit"], authority["commit"]),
                "history.unreachable", "approval is not in selected authority history", str(ref))
        item = self.decisions.get((ref["repository"], ref["path"], ref["sha256"]))
        require(item is not None, "history.unreachable", "exact decision is absent from declared history", str(ref))
        return item[1]

    def reviewers(self, ref, decision):
        seen = set(); roles = set()
        for reviewer in decision["reviewers"]:
            actor = reviewer["actor"]
            require(actor in self.actors and actor not in seen, "approval.actor", "actor undeclared or repeated", str(ref))
            seen.add(actor)
            require(set(reviewer["roles"]) <= set(self.actors[actor]["roles"]), "approval.roles", "role not granted by fixed policy", str(ref))
            roles.update(reviewer["roles"])
            path = str(PurePosixPath(ref["path"]).parent / reviewer["evidence_path"])
            self.store.read(self.store.same_commit_ref(ref, path, reviewer["evidence_sha256"]))
        require(set(self.policy["required_roles"][decision["kind"]]) <= roles,
                "approval.roles", "required review roles missing", str(ref))

    def permitted(self, package_ref, consumption):
        for ref, decision in self.decisions.values():
            if decision["kind"] == "approve" or decision["package_ref"] != package_ref: continue
            field = "prohibit_existing_consumers" if consumption == "existing" else "prohibit_new_consumers"
            require(not decision[field], "approval.restricted", "fixed-time decision prohibits this consumption", str(ref))
