"""Only local, exact Git objects. Never fetch, checkout, filter or lazy-fetch."""
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess

from .errors import CheckError, require
from .models import parse, validate

MAX_BLOB = 128 * 1024 * 1024


def key(ref):
    return tuple(ref[x] for x in ("repository", "commit", "path", "sha256"))


class Repository:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1",
                        GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.trees = {}; self.commits = set()
        require(self.path.is_dir(), "object.repository", "local repository is missing", path)
        git_dir = Path(self.git("rev-parse", "--absolute-git-dir").decode().strip())
        require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false",
                "history.incomplete", "shallow history is unsupported; explicitly restore full objects", path)
        require(not (git_dir / "info/grafts").exists(), "history.replacement", "Git grafts are forbidden", path)
        require(not self.git("for-each-ref", "--format=%(refname)", "refs/replace").strip(),
                "history.replacement", "Git replace refs are forbidden", path)
        partial = self.git("config", "--local", "--get-regexp", r"^(extensions\.partialClone|remote\..*\.promisor)$", ok=(0, 1))
        require(not partial, "history.incomplete", "partial/promisor repositories are unsupported", path)

    def git(self, *args, ok=(0,)):
        try:
            p = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                "-c", "core.hooksPath=" + os.devnull, "-c", "protocol.allow=never", "-C", str(self.path), *args],
                env=self.env, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CheckError("object.unreadable", str(error), self.path) from error
        require(p.returncode in ok, "object.unreadable", p.stderr.decode(errors="replace").strip(),
                str(self.path) + " :: " + " ".join(args))
        return p.stdout

    def commit(self, commit):
        validate("revision", {"repository": "local", "commit": commit}, self.path)
        if commit not in self.commits:
            require(self.git("cat-file", "-t", commit).strip() == b"commit", "object.commit",
                    "a full commit object is required", commit)
            self.commits.add(commit)

    def tree(self, commit):
        self.commit(commit)
        if commit not in self.trees:
            result = {}
            for line in self.git("ls-tree", "-rz", "--full-tree", commit).split(b"\0"):
                if not line: continue
                metadata, path = line.split(b"\t", 1)
                mode, kind, oid = metadata.decode().split(" ")
                try: path = path.decode("utf-8")
                except UnicodeError as error:
                    raise CheckError("object.path", "non-UTF-8 Git path", commit) from error
                result[path] = (mode, kind, oid)
            self.trees[commit] = result
        return self.trees[commit]

    def read(self, commit, path):
        entry = self.tree(commit).get(path)
        require(entry is not None, "object.missing", "fixed file is missing", f"{commit}:{path}")
        mode, kind, oid = entry
        require(mode in ("100644", "100755") and kind == "blob", "object.mode",
                "symlinks and submodules are not fixed file content", f"{commit}:{path}")
        size = int(self.git("cat-file", "-s", oid))
        require(size <= MAX_BLOB, "object.size", "object exceeds supported 128 MiB limit", f"{commit}:{path}")
        data = self.git("cat-file", "blob", oid)
        require(len(data) == size, "object.truncated", "Git returned truncated bytes", f"{commit}:{path}")
        return data

    def ancestor(self, older, newer):
        self.commit(older); self.commit(newer)
        # rev-list exits nonzero on absent history; an empty range alone is not proof.
        return older in self.git("rev-list", newer).decode().splitlines()


class Store:
    def __init__(self, repositories, root):
        self.mapping = repositories; self.root = Path(root)
        self.repositories = {}; self.inputs = {}; self.documents = {}; self.bytes = {}

    def repo(self, identity):
        require(identity in self.mapping, "object.repository", "repository has no explicit local mapping", identity)
        if identity not in self.repositories:
            path = Path(self.mapping[identity])
            self.repositories[identity] = Repository(path if path.is_absolute() else self.root / path)
        return self.repositories[identity]

    def read(self, ref):
        validate("ref", ref, str(ref))
        k = key(ref)
        if k not in self.bytes:
            data = self.repo(ref["repository"]).read(ref["commit"], ref["path"])
            require(sha256(data).hexdigest() == ref["sha256"], "object.digest", "SHA-256 mismatch", str(ref))
            require(not data.startswith(b"version https://git-lfs.github.com/spec/v1"),
                    "media.pointer", "LFS pointer is not the required media bytes; restore the declared external object", str(ref))
            self.bytes[k] = data
        self.inputs[k] = dict(ref)
        return self.bytes[k]

    def document(self, kind, ref):
        k = (kind, key(ref))
        if k not in self.documents:
            self.documents[k] = validate(kind, parse(self.read(ref), str(ref)), str(ref))
        return self.documents[k]

    def lfs_pointer(self, base, path, declaration):
        data = self.repo(base["repository"]).read(base["commit"], path)
        ref = self.same_commit_ref(base, path, sha256(data).hexdigest())
        validate("ref", ref, str(ref))
        match = re.fullmatch(rb"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?", data)
        require(match is not None and match[1].decode() == declaration["sha256"] and
                int(match[2]) == declaration["bytes"], "media.pointer", "LFS pointer does not bind declared media bytes", str(ref))
        self.inputs[key(ref)] = ref
        return ref

    def same_commit_ref(self, base, path, digest):
        return dict(repository=base["repository"], commit=base["commit"], path=path, sha256=digest)
