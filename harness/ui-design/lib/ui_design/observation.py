"""Read declared remote refs, never fetch/push or accept cached observation JSON."""
from datetime import datetime, timezone
import os
import re
import subprocess
from urllib.parse import urlsplit

from .errors import CheckError, require
from .models import validate
from .objects import Store
from .runtime import identity, policy_capabilities


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def endpoint(remote, ref):
    require(not any(ord(c) < 32 for c in remote), "observation.endpoint", "control character in remote", remote)
    if not remote.startswith("/"):
        url = urlsplit(remote)
        require(url.scheme in ("file", "https", "ssh") and not url.query and not url.fragment and
                url.password is None and (url.scheme == "ssh" or url.username is None),
                "observation.endpoint", "use an explicit credential-free file/https/ssh endpoint, never an alias/helper", "policy/remote")
        require((url.scheme == "file" and not url.netloc and url.path.startswith("/")) or
                (url.scheme != "file" and bool(url.hostname) and bool(url.path)),
                "observation.endpoint", "endpoint is incomplete", "policy/remote")
    require(ref.startswith("refs/") and not any(x in ref for x in ["..", "@{", "//", "\\", "*", "?", "[", ":", " "])
            and all(p and not p.startswith(".") and not p.endswith((".", ".lock")) for p in ref.split("/"))
            and not any(ord(c) < 32 or ord(c) == 127 for c in ref),
            "observation.ref", "an exact full ref is required", "policy/ref")


def query(remote, ref):
    endpoint(remote, ref)
    command = ["git", "--no-optional-locks", "-c", "core.hooksPath=" + os.devnull,
               "-c", "core.fsmonitor=false", "-c", "credential.helper=", "-c", "core.askPass=",
               "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
               "-c", "protocol.https.allow=always", "-c", "protocol.ssh.allow=always",
               "ls-remote", "--exit-code", "--refs", remote, ref]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
               GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0",
               GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=yes")
    record = dict(remote=remote, ref=ref, started_at=timestamp(), command=command, cwd="/",
                  actual_commit=None, exit_code=None, stdout="", stderr="")
    try:
        p = subprocess.run(command, cwd="/", env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30, check=False)
        record.update(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        lines = p.stdout.splitlines()
        if p.returncode == 0 and len(lines) == 1:
            fields = lines[0].split("\t")
            if len(fields) == 2 and fields[1] == ref and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields[0]):
                record["actual_commit"] = fields[0]
    except (OSError, subprocess.TimeoutExpired) as error:
        record["stderr"] = str(error)
        if isinstance(error, subprocess.TimeoutExpired):
            record["stdout"] = (error.stdout or b"").decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
            record["stderr"] += "\n" + ((error.stderr or b"").decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or "")
    record["finished_at"] = timestamp()
    return record


def current(snapshot, root, fixed):
    result = dict(fixed)
    result.update(mode="current", result="UNKNOWN", fixed_result=fixed, observations=[], diagnostics=[],
                  action=snapshot.get("action"), policy_ref=snapshot.get("policy_ref"), current_checked=False,
                  proof_scope="one live UI ref observation and fixed-content verification; no continuing lock or engineering permission")
    try:
        rules = identity()
        validate("snapshot", snapshot, "snapshot")
        require(snapshot["rules"] == rules, "rules.identity", "snapshot rules differ from the reviewed installation", "snapshot/rules")
        store = Store(snapshot["repositories"], root)
        policy = store.document("policy", snapshot["policy_ref"])
        policy_capabilities(policy)
        # Only a completed check of the fixed applicability and independent
        # behavior denominator may skip a UI query. Invalid/missing bindings cannot.
        if fixed["result"] == "PASS" and fixed.get("ui_required") is False:
            result.update(result="PASS", ui_applicability="not-applicable",
                          proof_scope="fixed reviewed non-UI applicability only; no UI authority observation needed")
            return result
        selected = snapshot["authorities"]
        require(len(selected) == len(policy["authorities"]) and
                len({s["repository"] for s in selected}) == len(selected),
                "history.authority", "selected authorities must exactly match fixed policy", "snapshot/authorities")
        cache = {}  # Deliberately local to this invocation; no replayable cache input.
        for authority in policy["authorities"]:
            matches = [s for s in selected if s["repository"] == authority["repository"]]
            require(len(matches) == 1 and matches[0]["ref"] == authority["ref"] and
                    matches[0]["history_root"] == authority["history_root"],
                    "history.authority", "selection differs from fixed policy", "snapshot/authorities")
            chosen = matches[0]; k = (authority["remote"], authority["ref"])
            if k not in cache:
                cache[k] = len(result["observations"])
                result["observations"].append({**query(*k), "selections": []})
            observed = result["observations"][cache[k]]
            observed["selections"].append(chosen)
            if observed["actual_commit"] is None:
                result["diagnostics"].append(dict(code="observation.query", source=authority["repository"], location=authority["ref"],
                    message="cannot establish the declared current UI ref; restore access separately, never fetch or fall back"))
            elif chosen["commit"] != observed["actual_commit"]:
                result["diagnostics"].append(dict(code="observation.stale", source=authority["repository"], location=authority["ref"],
                    message="selected commit differs from actual UI authority; reassess original bindings/review/request"))
        result["current_checked"] = not result["diagnostics"] and bool(result["observations"])
        result["diagnostics"].extend(fixed["diagnostics"])
        if result["current_checked"] and fixed["result"] == "PASS":
            result["result"] = "PASS"
        elif result["current_checked"] and any(d["code"] in ("approval.restricted", "history.append-only", "history.id")
                                               for d in fixed["diagnostics"]):
            result["result"] = "FAIL"
    except CheckError as error:
        result["diagnostics"].append(error.diagnostic)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["diagnostics"].append(dict(code="observation.unavailable", message=str(error), source="current", location=""))
    return result
