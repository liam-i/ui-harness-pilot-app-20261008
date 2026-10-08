"""唯一检查 CLI；命令、快照与支持阶段必须匹配。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
# -I 隔离用户 site/PYTHONPATH；只显式加入这份可复制库的位置。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parser():
    result = argparse.ArgumentParser(description="只读 Version Requirement Gate；不写要求、批准或 Git 状态")
    result.add_argument("--root", required=True, type=Path)
    result.add_argument("--gate", required=True)
    result.add_argument("--phase", required=True)
    result.add_argument("--subject", required=True)
    result.add_argument("--context", required=True, type=Path)
    result.add_argument("--format", choices=("json", "text"), default="text")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    output = {"gate": args.gate, "phase": args.phase, "subject": args.subject,
              "result": "unreadable", "evaluation_mode": None, "input_digest": None,
              "version": None, "delivery_line": None, "baseline": None,
              "metadata_revision": None, "head_revision": None, "target_revision": None,
              "control_revision": None, "diagnostics": []}
    code = 2
    try:
        from lib.core import canonical_bytes, digest, parse_json, local_file
        from lib.context import phase_identity, resolve
        from lib.errors import CheckError, InputError
        from lib.gitstore import GitStore
        from lib.models import validate
        from lib.runtime import preflight, selected_runtime
    except Exception as error:
        output["diagnostics"].append({"rule_id": "runtime.unavailable", "result": "unreadable",
                                      "object_refs": [], "evidence": str(error), "next_owner": "integrator"})
    else:
        store = None
        try:
            output["runtime"] = preflight()
            context = validate("snapshot", parse_json(local_file(args.context.parent, args.context.name).read_bytes()),
                               location="context")
            for key in ("gate", "phase", "subject"):
                if context[key] != getattr(args, key):
                    raise InputError("snapshot.cli-mismatch", "CLI and snapshot disagree: " + key)
            for key in ("evaluation_mode", "version", "delivery_line", "metadata_revision", "head_revision",
                        "target_revision", "control_revision"):
                output[key] = context[key]
            output["baseline"] = context["baseline_ref"]
            phase_identity(context)
            store = GitStore(args.root)
            for key in ("metadata_revision", "head_revision", "target_revision"):
                store.commit(context[key])
            if context["control_revision"] is not None:
                store.commit(context["control_revision"])
            # Use the same fixed product context as the original Gate. Later
            # engineering policy is separately bound by its Review/result.
            output['runtime'] = selected_runtime(resolve(store, context))
            if context["gate"] == "G0":
                from lib.sources import check_intake
                output["diagnostics"].append(check_intake(resolve(store, context)))
                output["result"], code = "passed", 0
            elif context["gate"] == "G2":
                if context['phase'] == 'dispatch':
                    from lib.dispatch import check_dispatch
                    result = check_dispatch(store, context)
                elif context['phase'] == 'planning':
                    from lib.planning import check_planning
                    result = check_planning(store, context)
                else:
                    from lib.execution import check_apply
                    result = check_apply(store, context)
                output["diagnostics"].append(result)
                output["result"], code = "passed", 0
            elif context["gate"] == "G3":
                if context['subject'].startswith(('task:', 'pr:')):
                    from lib.tiny_delivery import check_tiny_pre_merge, check_tiny_integrated
                    result = (check_tiny_pre_merge if context['phase'] == 'pre-merge' else check_tiny_integrated)(store, context)
                elif context['subject'].startswith('scope:'):
                    from lib.scope_delivery import check_scope_delivery
                    result = check_scope_delivery(store, context)
                elif context['phase'] == 'pre-archive':
                    from lib.prearchive import check_pre_archive
                    result = check_pre_archive(store, context)
                elif context['phase'] == 'pre-merge':
                    from lib.premerge import check_pre_merge
                    result = check_pre_merge(store, context)
                else:
                    from lib.integrated import check_integrated
                    result = check_integrated(store, context)
                output["diagnostics"].append(result)
                output["result"], code = "passed", 0
            elif context['gate'] == 'G4':
                from lib.completion import check_version
                output['diagnostics'].append(check_version(store, context))
                output['result'], code = 'passed', 0
            else:
                from lib.baselines import check_baseline
                output["diagnostics"].append(check_baseline(resolve(store, context)))
                output["result"], code = "passed", 0
        except CheckError as error:
            code = 2 if error.unreadable else 1
            output["result"] = "unreadable" if error.unreadable else "failed"
            output["diagnostics"].append(error.diagnostic())
        except (OSError, ValueError) as error:
            output["diagnostics"].append(InputError("input.unreadable", str(error)).diagnostic())
        finally:
            if store is not None:
                output["resolved_inputs"] = store.manifest()
                output["input_digest"] = digest(canonical_bytes({"context": context, "files": store.manifest(),
                                                               "runtime": output["runtime"]}))
    output["exit_code"] = code
    if args.format == "json":
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"{args.gate}/{args.phase} {args.subject}: {output['result']} (exit {code})")
        for diagnostic in output["diagnostics"]:
            print(f"{diagnostic['rule_id']}: {diagnostic['evidence']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
