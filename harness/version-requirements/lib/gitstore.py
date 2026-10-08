"""读取明确的 Git 对象；不 fetch、checkout、暂存、发布或自动回退。"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import re
import subprocess
import sys

from .core import digest, parse_yaml, relative_path
from .errors import CheckError, InputError

SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
BLOB_CACHE_BYTES = 16 * 1024 * 1024
BLOB_CACHE_MAX_ITEM = 1024 * 1024
YAML_CACHE_BYTES = 4 * 1024 * 1024
# A version-wide source index can occupy ~700 KiB after parsing. Keep it
# reusable without increasing the shared 4 MiB budget or caching verdicts.
YAML_CACHE_MAX_ITEM = 1024 * 1024
YAML_CACHE_ENTRIES = 256


def _yaml_size(value):
    """Bound retained parsed objects, including expanded strings and containers."""
    total, seen, pending = 0, set(), [value]
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        total += sys.getsizeof(item)
        if total > min(YAML_CACHE_MAX_ITEM, YAML_CACHE_BYTES):
            return total
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return total


class GitStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
        self.inputs = {}
        self._trees = {}
        self._commits = set()
        self._blobs = OrderedDict()
        self._blob_bytes = 0
        self._yaml_documents = OrderedDict()
        self._yaml_bytes = 0
        self._integrated_receipts = {}
        self._delivery_controls = {}
        actual = Path(self.git("rev-parse", "--show-toplevel").decode().strip()).resolve()
        if actual != self.root:
            raise InputError("git.root", "--root must name the repository root")

    @contextmanager
    def input_scope(self):
        """Isolate a nested decision's reads, then retain the complete audit.

        Replaying an older admission must not validate its caller's later
        control reads against the old control history. Repeated reads inside
        the nested decision still count even if the caller read them first.
        """
        outer = self.inputs
        self.inputs = {}
        try:
            yield
        finally:
            outer.update(self.inputs)
            self.inputs = outer

    def git(self, *args, ok=(0,)):
        try:
            process = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                                      "-c", "core.hooksPath=/dev/null", "-C", str(self.root), *args],
                                     env=self.env, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise InputError("git.unreadable", str(error)) from error
        if process.returncode not in ok:
            raise InputError("git.unreadable", process.stderr.decode(errors="replace").strip(), refs=list(args))
        return process.stdout

    def commit(self, revision):
        if not isinstance(revision, str) or not SHA.fullmatch(revision):
            raise InputError("git.fixed-commit", "full lowercase commit SHA required", refs=[str(revision)])
        if revision not in self._commits:
            kind = self.git("cat-file", "-t", revision).strip()
            if kind != b"commit":
                raise InputError("git.fixed-commit", "object is not a commit", refs=[revision])
            self._commits.add(revision)
        return revision

    def tree(self, revision):
        self.commit(revision)
        if revision not in self._trees:
            entries = {}
            for entry in self.git("ls-tree", "-r", "-z", "--full-tree", revision).split(b"\0"):
                if not entry:
                    continue
                metadata, path = entry.split(b"\t", 1)
                mode, kind, oid = metadata.decode("ascii").split()
                try:
                    path = path.decode("utf-8")
                except UnicodeError as error:
                    raise InputError("git.path-encoding", "Git paths must be UTF-8") from error
                entries[path] = (mode, kind, oid)
            self._trees[revision] = entries
        return self._trees[revision]

    def read(self, revision, path, sha256=None):
        relative_path(path)
        entry = self.tree(revision).get(path)
        if entry is None:
            raise CheckError("ref.missing", "file missing from fixed commit", refs=[{"commit": revision, "path": path}])
        mode, kind, oid = entry
        if mode not in ("100644", "100755") or kind != "blob":
            raise InputError("ref.file-kind", "symlinks and submodules are not source files", refs=[path])
        if oid in self._blobs:
            data = self._blobs[oid]
            self._blobs.move_to_end(oid)
        else:
            data = self.git("cat-file", "blob", oid)
            # Git object bytes are immutable. Reuse only bounded raw bytes
            # within this reader, never live refs or permissions. Every caller
            # still checks its digest and records
            # its own commit/path below, including inside input_scope().
            if len(data) <= min(BLOB_CACHE_MAX_ITEM, BLOB_CACHE_BYTES):
                while self._blob_bytes + len(data) > BLOB_CACHE_BYTES:
                    _, removed = self._blobs.popitem(last=False)
                    self._blob_bytes -= len(removed)
                self._blobs[oid] = data
                self._blob_bytes += len(data)
        actual = digest(data)
        if sha256 is not None:
            if not isinstance(sha256, str) or not HASH.fullmatch(sha256):
                raise InputError("ref.hash-shape", "full SHA-256 required", refs=[path])
            if actual != sha256:
                raise CheckError("ref.digest", "fixed content digest mismatch", refs=[{"commit": revision, "path": path}])
        self.inputs[(revision, path)] = actual
        return data

    def ref(self, value, *, default_commit=None):
        if not isinstance(value, dict) or not {"path", "sha256"} <= value.keys():
            raise InputError("ref.shape", "reference requires path and sha256")
        revision = value.get("commit", default_commit)
        return self.read(revision, value["path"], value["sha256"])

    def yaml(self, revision, path, sha256=None):
        # Read first even on reuse: each reference keeps its digest check and
        # commit/path audit, including nested input_scope() calls. Only parsed
        # fixed bytes are reused; Schema, semantic rules and Gates still run.
        raw = self.read(revision, path, sha256)
        identity = self.inputs[(revision, path)]
        if identity in self._yaml_documents:
            value, _ = self._yaml_documents[identity]
            self._yaml_documents.move_to_end(identity)
            return deepcopy(value)
        value = parse_yaml(raw)
        size = _yaml_size(value)
        if YAML_CACHE_ENTRIES > 0 and size <= min(YAML_CACHE_MAX_ITEM, YAML_CACHE_BYTES):
            while self._yaml_documents and (self._yaml_bytes + size > YAML_CACHE_BYTES or
                                           len(self._yaml_documents) >= YAML_CACHE_ENTRIES):
                _, (_, removed) = self._yaml_documents.popitem(last=False)
                self._yaml_bytes -= removed
            self._yaml_documents[identity] = (value, size)
            self._yaml_bytes += size
            # Never expose the retained object, including on the first read.
            # A caller may edit its own model without affecting a later read.
            return deepcopy(value)
        return value

    def ancestor(self, ancestor, descendant):
        self.commit(ancestor)
        self.commit(descendant)
        # --is-ancestor has no stdout; rev-list remains unambiguous in shallow repos.
        shallow = self.git("rev-parse", "--is-shallow-repository").strip() == b"true"
        if shallow:
            raise InputError("git.shallow", "complete ancestry required; explicitly deepen/fetch before checking")
        return ancestor in self.git("rev-list", descendant).decode().splitlines()

    def remote_refs(self, remote, names):
        if not isinstance(remote, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", remote):
            raise InputError("git.remote", "configured remote name required")
        for name in names:
            if not re.fullmatch(r"refs/(heads|tags)/[A-Za-z0-9._/-]+", name) or ".." in name:
                raise InputError("git.refname", "invalid explicit remote ref", refs=[name])
        configured = self.git("remote").decode().splitlines()
        if remote not in configured:
            raise InputError("git.remote", "remote is not configured", refs=[remote])
        rows = self.git("ls-remote", "--refs", "--", remote, *names).decode().splitlines()
        return {name: sha for sha, name in (row.split("\t") for row in rows)}

    def manifest(self):
        return [{"commit": commit, "path": path, "sha256": hash_}
                for (commit, path), hash_ in sorted(self.inputs.items())]
