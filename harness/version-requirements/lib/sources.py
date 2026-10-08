"""PRD 包、DOC/AST/SRC、原字节和只读来源闭包。"""
from __future__ import annotations

import csv
import io
import re

from .core import canonical_bytes, digest, parse_yaml, relative_path
from .errors import CheckError, InputError
from .markdown_source import parse_document, raw_lines, resolve_link
from .models import unique, validate
from .reviews import check_review, decision, evidence


def fixed_content(store, received_ref, content_sha256, external=None):
    """原接收件与实际可读字节分别固定；不把 LFS 指针或网络 URL 当作内容。"""
    data = store.ref(received_ref)
    pointer = data.startswith(b"version https://git-lfs.github.com/spec/v1")
    if pointer and external is None:
        raise InputError("source.external-bytes", "Git LFS pointer is not the required source bytes; supply fixed retrieved content")
    content_ref = external["retrieval_ref"] if external else received_ref
    content = store.ref(content_ref) if external else data
    if digest(content) != content_sha256 or (external and content.startswith(b"version https://git-lfs.github.com/spec/v1")):
        raise CheckError("source.external-bytes", "retrieved content does not match the fixed asset")
    if pointer:
        oid = re.search(rb"^oid sha256:([0-9a-f]{64})$", data, re.M)
        size = re.search(rb"^size ([0-9]+)$", data, re.M)
        if not oid or not size or oid[1].decode() != content_sha256 or int(size[1]) != len(content):
            raise CheckError("source.external-pointer", "LFS pointer and actual retrieved bytes disagree")
    return content, content_ref


def fragment(data, selector):
    """文本/配置/CSV 可机械取片段；其他格式绑定原件和人工定位，不伪称裁剪。"""
    kind = selector["kind"]
    if kind in ("lines", "table"):
        lines = raw_lines(data)
        start, end = selector.get("start"), selector.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end <= len(lines):
            raise CheckError("source.selector", "line/table coordinates are outside the original file")
        return b"".join(lines[start - 1:end])
    if kind == "whole-file":
        return data
    if kind == "key":
        value = parse_yaml(data)
        if not selector.get("key_path"):
            raise CheckError("source.selector", "configuration selector requires key_path")
        try:
            for key in selector["key_path"]:
                if isinstance(value, list):
                    if not key.isdecimal():
                        raise ValueError("list selector requires a non-negative index")
                    value = value[int(key)]
                else:
                    value = value[key]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise CheckError("source.selector", "configuration key does not exist") from error
        return canonical_bytes(value)
    if kind == "records":
        try:
            rows = list(csv.reader(io.StringIO(data.decode(selector.get("encoding", "utf-8-sig")), newline=""),
                                   delimiter=selector.get("delimiter", ","), strict=True))
        except (UnicodeError, LookupError, csv.Error, TypeError) as error:
            raise InputError("source.csv", str(error)) from error
        start, end = selector.get("start"), selector.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end <= len(rows):
            raise CheckError("source.selector", "CSV record range is invalid (row 1 includes the header)")
        if selector.get("columns") and not set(selector["columns"]) <= set(rows[0]):
            raise CheckError("source.selector", "CSV columns do not exist")
        return canonical_bytes(rows[start - 1:end])
    if kind == "image":
        region, dimensions = selector.get("region", []), selector.get("dimensions", [])
        if len(region) != 4 or len(dimensions) != 2:
            raise CheckError("source.selector", "image region needs x/y/width/height and original dimensions")
        x, y, width, height = region
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > dimensions[0] or y + height > dimensions[1]:
            raise CheckError("source.selector", "image region exceeds declared original dimensions")
    elif kind == "cells":
        if not selector.get("sheet") or not re.fullmatch(r"[A-Z]+[1-9][0-9]*(?::[A-Z]+[1-9][0-9]*)?", selector.get("range", "")):
            raise CheckError("source.selector", "spreadsheet selector requires sheet and A1 range")
    elif kind == "time":
        start, end = selector.get("start_seconds"), selector.get("end_seconds")
        if start is None or end is None or start < 0 or start >= end:
            raise CheckError("source.selector", "media selector requires a valid time interval")
    elif kind == "object":
        if not selector.get("object_id"):
            raise CheckError("source.selector", "level/prototype selector requires an object identifier")
    else:
        raise InputError("source.selector-unsupported", "unsupported source fragment kind: " + kind)
    return canonical_bytes({"source_sha256": digest(data), "selector": selector})


class SourceIndex:
    def __init__(self, context, *, intake=None, require_decisions=None, _lineage=()):
        self.context, self.store = context, context.store
        owner = (context.content_commit, context.version['version'])
        if owner in _lineage:
            raise CheckError('source.predecessor-cycle', 'cyclic cross-Version source lineage')
        self._lineage = (*_lineage, owner)
        if len(self._lineage) > 64:
            raise InputError('source.history-limit', 'source predecessor traversal exceeds supported bounds')
        self.owner_contexts = {owner: context}
        self._historical_units = set()
        self.require_decisions = context.snapshot['gate'] != 'G0' if require_decisions is None else require_decisions
        self.manifest = context.read("source/manifest.yaml", "manifest")
        if self.manifest["version"] != context.version["version"]:
            raise CheckError("source.version", "manifest is for a different Version")
        indexed = unique(self.manifest["intakes"], "id", location="source/manifest.yaml")
        self._declared = indexed
        if intake is not None and intake not in indexed:
            raise CheckError("source.intake", "selected intake is absent", refs=[intake])
        self.intakes, self.files, self.documents, self.assets, self.observed = {}, {}, {}, {}, {}
        self.intake_commits = {}
        self._namespaces, self._parsed = {}, {}
        self._visiting = set()
        for entry in indexed.values() if intake is None else [indexed[intake]]:
            self._intake(entry, context.content_commit)
        self.units_document = context.read("source/units.yaml", "units")
        if self.units_document["version"] != context.version["version"]:
            raise CheckError("source.version", "units are for a different Version")
        all_units = unique(self.units_document["units"], "id", location="source/units.yaml")
        if any(not identity.startswith(context.version['version'] + '/') for identity in all_units):
            raise CheckError('source.unit-owner', 'current units must keep this Version as owner; historical units remain in their fixed source manifest')
        self.units = {identity: unit for identity, unit in all_units.items()
                      if identity.rsplit("/", 1)[0] in self.intakes}
        if intake is None and set(self.units) != set(all_units):
            raise CheckError("source.unit-intake", "source unit belongs to an unknown intake")
        self.effective_links = self._effective_links(intake or self.manifest["intakes"][-1]["id"])
        self._units()
        self._relations()

    def _intake(self, entry, commit):
        validate("intake", entry)
        identity = entry["id"]
        current = self._declared.get(identity)
        if current is not None and current != entry:
            if current["root"] != entry["root"] or {f["path"]: f["sha256"] for f in current["files"]} != {f["path"]: f["sha256"] for f in entry["files"]}:
                raise CheckError("source.intake-overwrite", "current index changed received bytes", refs=[identity])
            # Metadata may be corrected without rewriting the package. The fixed current
            # manifest owns those corrections; predecessor read order must not select them.
            entry, commit = current, self.context.content_commit
        version = self.context.version["version"]
        if not re.fullmatch(re.escape(version) + r"/intake-[0-9]{3,}", identity):
            raise CheckError("source.intake-id", "intake identity does not belong to this Version", refs=[identity])
        if identity in self._visiting:
            raise CheckError("source.predecessor-cycle", "cyclic intake predecessor")
        if identity in self.intakes:
            old = self.intakes[identity]
            if old["root"] != entry["root"] or {f["path"]: f["sha256"] for f in old["files"]} != {f["path"]: f["sha256"] for f in entry["files"]}:
                raise CheckError("source.intake-overwrite", "received file identity/bytes cannot be overwritten", refs=[identity])
            return
        self._visiting.add(identity)
        predecessor = None
        if entry["input_mode"] == "delta":
            if not entry["predecessor"]:
                raise CheckError("source.delta-predecessor", "delta requires recoverable fixed predecessor")
            predecessor = validate("manifest", parse_yaml(self.store.ref(entry["predecessor"])))
            if predecessor['version'] != version:
                self._inherit_source(entry['predecessor'], predecessor)
            else:
                if entry["predecessor"]["path"] != self.context.vr + "/source/manifest.yaml":
                    raise CheckError('source.delta-version', 'same-Version delta needs its own fixed manifest')
                for previous in predecessor["intakes"]:
                    self._intake(previous, entry["predecessor"]["commit"])
        elif entry["predecessor"]:
            # Full deliveries can retain an explicit lineage; existence does not imply deletion approval.
            previous = validate("manifest", parse_yaml(self.store.ref(entry["predecessor"])))
            if previous["version"] != version or entry["predecessor"]["path"] != self.context.vr + "/source/manifest.yaml":
                raise CheckError("source.predecessor", "full intake lineage must identify this Version's fixed manifest")
        expected_root = "source/" + identity.rsplit("/", 1)[1]
        if entry["root"] != expected_root:
            raise CheckError("source.root", "intake root must preserve its own receiving directory")
        root = self.context.vr + "/" + entry["root"]
        files = unique(entry["files"], "path", location=identity)
        actual = {p[len(root) + 1:] for p in self.store.tree(commit) if p.startswith(root + "/")}
        if set(files) != actual:
            raise CheckError("source.inventory", "full package inventory differs from fixed files", refs=sorted(set(files) ^ actual))
        self._immutable(root, commit)
        docs = unique(entry["documents"], "id", location=identity)
        assets = unique(entry["assets"], "id", location=identity)
        document_paths = unique(entry["documents"], "path", location=identity)
        asset_paths = unique(entry["assets"], "path", location=identity)
        if set(document_paths) & set(asset_paths):
            raise CheckError("source.file-role", "one path cannot be both DOC and AST")
        if set(entry["entry_documents"]) != {d["id"] for d in docs.values() if d["role"] == "main"}:
            raise CheckError("source.entry", "entry documents must identify the declared main document set")
        decision(self.context, entry["provided"], roles={"product-owner", "integrator"})
        parsed = {}
        for path, file in files.items():
            relative_path(path)
            data = self.store.read(commit, root + "/" + path, file["sha256"])
            role = file["disposition"]
            record = document_paths.get(path) if role == "document" else asset_paths.get(path) if role == "asset" else None
            if role == "unclassified" or (role in ("document", "asset") and record is None):
                raise CheckError("source.unclassified", "every document/asset needs a classified identity", refs=[path])
            if path.lower().endswith(".md") and role != "document":
                raise CheckError("source.unlisted-document", "Markdown cannot be hidden as an unlinked other file", refs=[path])
            if record is None:
                continue
            if (not record.get("external") and record["sha256"] != file["sha256"]) or record.get("role") == "unclassified":
                raise CheckError("source.file-record", "document/asset identity or digest is inconsistent", refs=[path])
            key = identity + "/" + record["id"]
            received_ref = {"commit": commit, "path": root + "/" + path, "sha256": file["sha256"]}
            data, content_ref = fixed_content(self.store, received_ref, record["sha256"], record.get("external"))
            info = {**record, "id": key, "commit": content_ref["commit"], "repository_path": content_ref["path"],
                    "received_ref": received_ref, "content_ref": content_ref, "bytes": data}
            self.files[key] = info
            if role == "document":
                self.documents[key] = info
                if path.lower().endswith(".md"):
                    parsed[path] = parse_document(data)
                    self._parsed[key] = parsed[path]
            else:
                self.assets[key] = info
        if set(document_paths) | set(asset_paths) != {p for p, f in files.items() if f["disposition"] in ("document", "asset")}:
            raise CheckError("source.extra-identity", "DOC/AST does not match the complete inventory")
        self.intakes[identity] = entry
        self.intake_commits[identity] = commit
        namespace = dict(self._namespaces[predecessor["intakes"][-1]["id"]]) if predecessor else {}
        local = {path: identity + "/" + record["id"] for path, record in {**document_paths, **asset_paths}.items()}
        for path, key in local.items():
            old = namespace.get(path)
            if old is not None and old != key and not any(r["previous"] == old and r["current"] == key for r in entry["replacements"]):
                raise CheckError("source.delta-replacement", "overlapping delta path needs an explicit replacement identity", refs=[path])
        removed = {item["previous"] for item in entry["replacements"]}
        for path, key in list(namespace.items()):
            if key in removed:
                del namespace[path]
        for path in files:
            key = local.get(path)
            if namespace.get(path) is not None and namespace[path] != key:
                raise CheckError("source.delta-replacement", "overlapping delta path needs an explicit replacement identity", refs=[path])
            namespace[path] = key
        self._namespaces[identity] = namespace
        namespace_documents = {path: self._parsed[key] for path, key in namespace.items() if key in self._parsed}
        observed = []
        for path, document in parsed.items():
            for link in document["links"]:
                observed.append({"document": identity + "/" + document_paths[path]["id"], **link,
                                 "resolved": resolve_link(path, link["parsed_target"], namespace, namespace_documents)})
            for item in document["unsupported"]:
                observed.append({"document": identity + "/" + document_paths[path]["id"], "start": item["start"], "end": item["end"],
                                 "raw_target": item["syntax"], "source_syntax": item["syntax"], "parsed_target": item["syntax"],
                                 "source_excerpt": b"".join(raw_lines(self.files[identity + "/" + document_paths[path]["id"]]["bytes"])[item["start"] - 1:item["end"]]).decode("utf-8-sig"),
                                 "definition_excerpt": None,
                                 "resolved": {"status": "unsupported", "path": None, "anchor": None}})
        self.observed[identity] = observed
        self._links(entry, observed, namespace)
        self._visiting.remove(identity)

    def _inherit_source(self, reference, manifest):
        """Read the selected predecessor's package without moving its ownership.

        G0 checks this fixed lineage; G1 additionally verifies the original BL's
        approval/publication via BaselineContent. Imported units are historical
        provenance, not this Version's interpretation or obligation denominator.
        """
        version = self.context.version
        selected = version.get('predecessor_baseline')
        owner = manifest['version']
        path = 'requirements/versions/' + owner + '/source/manifest.yaml'
        if not selected or version.get('predecessor_version') != owner or reference['path'] != path:
            raise CheckError('source.delta-version', 'cross-Version delta needs the explicitly selected predecessor Version/BL and its fixed manifest')
        baseline = validate('baseline', parse_yaml(self.store.ref(selected)))
        if (baseline['version'] != owner or
                selected['path'] != 'requirements/versions/' + owner + '/baselines/' + baseline['id'] + '.yaml' or
                self.store.read(baseline['content_commit'], path) != self.store.ref(reference) or
                not self.store.ancestor(reference['commit'], baseline['content_commit'])):
            raise CheckError('source.delta-baseline', 'delta source must be the effective package selected by its predecessor BL')
        historical = SourceIndex(self.context.at(reference['commit'], owner), require_decisions=False,
                                 _lineage=self._lineage)
        self.owner_contexts.update(historical.owner_contexts)
        for name in ('intakes', 'files', 'documents', 'assets', 'observed', 'intake_commits', '_namespaces', '_parsed'):
            target = getattr(self, name)
            for identity, value in getattr(historical, name).items():
                if identity in target and target[identity] != value:
                    raise CheckError('source.predecessor-context', 'one fixed source identity has conflicting predecessor contexts', refs=[identity])
                target[identity] = value
        self._historical_units.update(historical.units)
        self._historical_units.update(historical._historical_units)

    def _effective_links(self, intake):
        """派生当前包引用语境；原 intake 的链接身份/解析结果仍保留。"""
        namespace = self._namespaces[intake]
        documents = {path: self._parsed[key] for path, key in namespace.items() if key in self._parsed}
        result = []
        for path, document in namespace.items():
            if document not in self._parsed:
                continue
            original = self.intakes[document.rsplit("/", 1)[0]]
            for link in original["links"]:
                if link["document"] != document:
                    continue
                resolved = ({"status": "unsupported", "path": None} if link["status"] == "unsupported" else
                            resolve_link(path, link["parsed_target"], namespace, documents))
                target = namespace.get(resolved["path"])
                # Explicitly admitted external content keeps its fixed original binding.
                if resolved["status"] == "external":
                    target = link["target"]
                readable = (resolved["status"] == "resolved" and (target is not None or not link["required"])) or (resolved["status"] == "external" and target is not None)
                if not readable and (link["required"] or link["disposition"] is None):
                    raise CheckError("source.effective-link", "current delta context makes a necessary reference unresolved", refs=[document, link["id"]])
                result.append({"intake": intake, "document": document, "link": link["id"], "target": target,
                               "original_target": link["target"], "status": resolved["status"],
                               "original_status": link["status"],
                               "target_selector": resolved.get("selector"),
                               "changed": target != link["target"] or resolved.get("selector") != link.get("target_selector") or resolved["status"] != link["status"]})
        return result

    def _immutable(self, root, commit):
        if self.store.git("rev-parse", "--is-shallow-repository").strip() == b"true":
            raise InputError("git.shallow", "intake immutability requires complete receiving history")
        expected = {p: row for p, row in self.store.tree(commit).items() if p.startswith(root + "/")}
        for previous in self.store.git("rev-list", "--full-history", commit, "--", root).decode().splitlines():
            actual = {p: row for p, row in self.store.tree(previous).items() if p.startswith(root + "/")}
            if actual != expected:
                raise CheckError("source.intake-overwrite", "received package was changed; use a new intake", refs=[root, previous])

    def _relations(self):
        endpoints = self.files.keys() | self.units.keys() | self._historical_units
        for entry in self.intakes.values():
            if not entry['id'].startswith(self.context.version['version'] + '/'):
                continue  # Checked in the original fixed owner's SourceIndex.
            for relation in entry["relations"]:
                if relation["from"] not in endpoints or relation["to"] not in endpoints or relation["from"] == relation["to"]:
                    raise CheckError("source.relation", "document/source relation endpoint is invalid")
                # G0 preserves an undecided semantic relationship for S1/Q; G1 must close it.
                if relation["status"] != "confirmed" and self.require_decisions:
                    raise CheckError("source.relation-unknown", "document relationship is undecided")
                evidence(self.store, relation["evidence_ref"])
            for replacement in entry["replacements"]:
                previous, current = replacement["previous"], replacement["current"]
                if previous not in endpoints or (current is not None and current not in endpoints) or current == previous:
                    raise CheckError("source.replacement", "replacement must resolve exact distinct source identities")
                evidence(self.store, replacement["decision_ref"])

    def _links(self, entry, observed, namespace):
        unique(entry["links"], "id", location=entry["id"])
        remaining = list(entry["links"])
        for item in observed:
            candidates = [link for link in remaining if link["document"] == item["document"] and
                          link["raw_target"] == item["raw_target"] and link["source_syntax"] == item["source_syntax"] and
                          link["selector"].get("start") == item["start"] and link["selector"].get("end") == item["end"]]
            if not candidates:
                raise CheckError("source.link-inventory", "parsed reference is absent or has lost original syntax/location", refs=[item])
            link = candidates[0]
            remaining.remove(link)
            if link["selector"]["kind"] != "lines" or any(link[key] != item[key] for key in ("source_excerpt", "parsed_target", "definition_excerpt")):
                raise CheckError("source.link-original", "link must retain original source and parser destination", refs=[link["id"]])
            if link["disposition"] is not None:
                decision(self.context, link["disposition"], roles={"product-owner", "integrator"})
            resolved = item["resolved"]
            target = namespace.get(resolved["path"])
            admitted_external = False
            if resolved["status"] == "external" and link["target"] is not None:
                external = self.assets.get(link["target"])
                if external and external.get("external", {}).get("uri") == item["parsed_target"] and link["disposition"] is not None:
                    decision(self.context, link["disposition"], roles={"product-owner", "integrator"})
                    target, admitted_external = link["target"], True
            if link["status"] != resolved["status"] or link["target"] != target:
                raise CheckError("source.link-resolution", "declared target/status differs from actual package resolution", refs=[link["id"]])
            if resolved.get("selector") != link.get("target_selector"):
                raise CheckError("source.link-anchor", "heading selector differs from resolved anchor", refs=[link["id"]])
            if resolved["status"] == "resolved" and link["required"] and target is None:
                raise CheckError("source.link-identity", "required reference points to an unindexed DOC/AST", refs=[link["id"]])
            if resolved["status"] != "resolved" and not admitted_external:
                if link["required"] or link["disposition"] is None:
                    raise CheckError("source.required-link", "necessary or undisposed reference cannot be resolved", refs=[link["id"]])
                decision(self.context, link["disposition"], roles={"product-owner", "integrator"})
        if remaining:
            raise CheckError("source.link-extra", "manifest contains references not present in the parsed Markdown", refs=[x["id"] for x in remaining])

    def _units(self):
        covered = {identity: [] for identity in self.files
                   if identity.startswith(self.context.version['version'] + '/')}
        for identity, unit in self.units.items():
            if not re.fullmatch(re.escape(identity.rsplit("/", 1)[0]) + r"/SRC-[0-9]{3,}", identity):
                raise CheckError("source.unit-id", "invalid full source-unit identity")
            source = self.files.get(unit["file"])
            if source is None or identity.rsplit("/", 1)[0] != unit["file"].rsplit("/", 1)[0] or unit["path"] != source["repository_path"] or unit["file_sha256"] != source["sha256"]:
                raise CheckError("source.unit-file", "SRC does not bind the original DOC/AST", refs=[identity])
            if digest(fragment(source["bytes"], unit["selector"])) != unit["fragment_sha256"]:
                raise CheckError("source.fragment", "source fragment digest mismatch", refs=[identity])
            reading = unit["reading"]
            if reading["status"] != "read" and (source["required"] or source.get("role") == "main"):
                raise CheckError("source.unread", "required source has not been read", refs=[identity])
            if reading["evidence_ref"] is None:
                raise CheckError("source.read-evidence", "readability or non-required disposition needs actual evidence", refs=[identity])
            evidence(self.store, reading["evidence_ref"])
            for usage in unit["asset_context"]:
                if usage["asset"] not in self.assets or usage["document"] not in self.documents:
                    raise CheckError("source.asset-context", "unknown document/asset use context", refs=[identity])
                intake = usage["document"].rsplit("/", 1)[0]
                matches = [link for link in self.intakes[intake]["links"] if link["id"] == usage["link"] and
                           link["document"] == usage["document"] and link["target"] == usage["asset"]]
                matches += [link for link in self.effective_links if link["link"] == usage["link"] and
                            link["document"] == usage["document"] and link["target"] == usage["asset"]]
                if not matches:
                    raise CheckError("source.asset-context", "asset use does not match the original link", refs=[identity])
            covered[unit["file"]].append(unit)
        for identity, units in covered.items():
            if not units:
                raise CheckError("source.coverage", "DOC/AST has no source unit", refs=[identity])
            source = self.files[identity]
            if identity in self.documents and source["path"].lower().endswith(".md"):
                expected = set(range(1, len(raw_lines(source["bytes"])) + 1))
                actual = set()
                for unit in units:
                    selector = unit["selector"]
                    if selector["kind"] == "whole-file":
                        actual |= expected
                    elif selector["kind"] in ("lines", "table"):
                        actual.update(range(selector["start"], selector["end"] + 1))
                    else:
                        raise CheckError("source.document-selector", "Markdown unit needs line/table or whole-file selector")
                if not expected or actual != expected:
                    raise CheckError("source.coverage", "complete Markdown intervals are not covered", refs=[identity])


def check_intake(context):
    from .runtime import reviewed_implementation
    identity = context.snapshot["subject"].removeprefix("intake:")
    sources = SourceIndex(context, intake=identity)
    required = {context.vr + "/" + path for path in ("version.yaml", "source/manifest.yaml", "source/units.yaml")}
    required |= {"harness/version-requirements/" + path for path in ("config/project.yaml", "config/runtime.json",
                                                                   "config/requirements.lock", "schemas/vr.schema.json")}
    for path in reviewed_implementation(context):
        required.add(path)
    check_review(context, "reviews/intake.yaml", "intake", required, source_units=sources.units,
                 roles={"integrator", "product-owner"},
                 required_checks={"package-boundary", "source-readability", "unparsed-references"})
    return {"rule_id": "G0.intake", "result": "passed", "object_refs": [identity],
            "evidence": {"intakes": sorted(sources.intakes), "documents": sorted(sources.documents),
                         "assets": sorted(sources.assets), "units": sorted(sources.units),
                         "changed_reference_contexts": [link for link in sources.effective_links if link["changed"]],
                         "review": context.vr + "/reviews/intake.yaml"}, "next_owner": "integrator"}
