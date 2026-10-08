"""Run the canonical requirement CI steps in an explicitly prepared trusted checkout.

This adapter installs nothing and grants no permission to merge or publish. The
host supplies the independently observed head and the required gate/phase. Gate
selection, workspace preparation and result checks remain in the single copied
workflow; the requirement checker remains the only business-rule implementation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import yaml


RUN_STEPS = (
    'Validate request', 'Read declared Python runtime',
    'Install exact requirement tools', 'Retrieve retained objects and current lines',
    'Prepare checked workspace', 'Run the selected gate',
)
EXECUTED_STEPS = tuple(name for name in RUN_STEPS if name != 'Install exact requirement tools')
ACTION_STEPS = ('actions/checkout@', 'actions/setup-python@', 'actions/upload-artifact@')


def fixed_sha(value):
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', value):
        raise ValueError('A full fixed commit SHA is required')
    return value


def read_request(raw, head, gate, phase):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate request key: ' + key)
            result[key] = value
        return result

    context = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(context, dict) or context.get('evaluation_mode') != 'current':
        raise ValueError('An explicit current snapshot is required')
    if (context.get('gate'), context.get('phase'), context.get('head_revision')) != (gate, phase, head):
        raise ValueError('Request differs from the host-required gate/phase or actual checked head')
    return context


def workflow_steps(path):
    data = yaml.safe_load(path.read_text())
    job = data['jobs']['requirements-gate']
    steps = job['steps']
    runs = [step for step in steps if 'run' in step]
    actions = [step for step in steps if 'uses' in step]
    # A new canonical step must never be silently skipped by an older adapter.
    if tuple(step.get('name') for step in runs) != RUN_STEPS:
        raise ValueError('Canonical CI steps changed; qualify this adapter before execution')
    if len(steps) != len(runs) + len(actions) or len(actions) != len(ACTION_STEPS):
        raise ValueError('Unexpected canonical CI action structure')
    if any(not isinstance(step.get('uses'), str) or not step['uses'].startswith(prefix)
           or not re.fullmatch(r'[0-9a-f]{40}', step['uses'][len(prefix):])
           for step, prefix in zip(actions, ACTION_STEPS)):
        raise ValueError('Expected the fixed checkout, Python setup and artifact actions')
    if any(step.get('shell') != 'bash' or not isinstance(step['run'], str) for step in runs):
        raise ValueError('Expected explicit Bash command bodies')
    return {step['name']: step['run'] for step in runs}


def execute(args):
    root = args.trusted_root.resolve(strict=True)
    if Path(__file__).resolve() != root / 'harness/version-requirements/ci.py':
        raise ValueError('Run the adapter installed in the reviewed trusted checkout')
    workflow = root / '.github/workflows/ci.yml'
    current = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if current != fixed_sha(args.checker_ref):
        raise ValueError('Trusted checkout does not match the reviewed checker SHA')
    subprocess.run(['git', '-C', str(root), 'ls-files', '--error-unmatch',
                    'harness/version-requirements/ci.py', '.github/workflows/ci.yml',
                    'scripts/requirements-check'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['git', '-C', str(root), 'diff', '--quiet', 'HEAD', '--',
                    'harness/version-requirements', 'scripts/requirements-check',
                    '.github/workflows/ci.yml'], check=True)
    head = fixed_sha(args.head)
    raw = args.context.read_text(encoding='utf-8')
    read_request(raw, head, args.gate, args.phase)
    bodies = workflow_steps(workflow)
    runtime = root / '.harness/version-requirements-venv/bin/python'
    if not runtime.is_file() or not os.access(runtime, os.X_OK):
        raise ValueError('Install the declared isolated Python runtime before invoking CI')
    declared = json.loads((root / 'harness/version-requirements/config/runtime.json').read_text())
    actual = subprocess.check_output([str(runtime), '-I', '-B', '-c',
        'import sys; assert sys.prefix != sys.base_prefix; print(".".join(map(str,sys.version_info[:2])))'],
        text=True).strip()
    if actual != declared['python_minor']:
        raise ValueError('Installed Python minor differs from the trusted runtime contract')
    run = args.run_dir.resolve()
    if run == root or run.is_relative_to(root):
        raise ValueError('Use a new output directory outside the trusted checkout')
    run.mkdir(parents=True, exist_ok=False, mode=0o700)
    output = run / 'version-requirement-gate'
    env = dict(os.environ, VR_CONTEXT_JSON=raw, VR_CHECKER_REF=current,
               RUNNER_TEMP=str(run), GITHUB_OUTPUT=str(run/'outputs'), VR_OUTPUT=str(output))
    record = {'scope': 'One current gate; host authorization and final control recheck remain separate',
              'checker_ref': current, 'head_revision': head, 'required_gate': args.gate,
              'required_phase': args.phase, 'workflow_sha256': hashlib.sha256(workflow.read_bytes()).hexdigest(),
              'request_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'steps': []}
    for index, name in enumerate(EXECUTED_STEPS, 1):
        prefix = f'{index:02d}-' + name.lower().replace(' ', '-')
        (run/(prefix+'.sh')).write_text(bodies[name])
        started = time.monotonic()
        timed_out = False
        # A fresh remote may transfer the complete retained source package.
        # Keep that bounded independently from the shorter local preparation.
        limit = 180 if name == 'Retrieve retained objects and current lines' else 60
        timeout = args.timeout if name == 'Run the selected gate' else min(args.timeout, limit)
        with (run/(prefix+'.stdout')).open('wb') as stdout, (run/(prefix+'.stderr')).open('wb') as stderr:
            process = subprocess.Popen(['bash', '-e', '-o', 'pipefail', '-s'], cwd=root, env=env,
                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                process.communicate(bodies[name].encode(), timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
        record['steps'].append({'name':name, 'exit_code':process.returncode, 'timed_out':timed_out,
                                'timeout_seconds':timeout,
                                'seconds':round(time.monotonic()-started, 6), 'log_prefix':prefix})
        record['status'] = 'failed' if process.returncode or timed_out else 'running'
        (run/'ci-adapter.json').write_text(json.dumps(record, indent=2)+'\n')
        if process.returncode or timed_out:
            return 124 if timed_out else process.returncode if 0 < process.returncode < 126 else 1
    record['status'] = 'passed'
    (run/'ci-adapter.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'result':'passed', 'checker_ref':current, 'head_revision':head,
                      'gate':args.gate, 'phase':args.phase, 'output':str(output)}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trusted-root', type=Path, required=True)
    parser.add_argument('--checker-ref', required=True)
    parser.add_argument('--head', required=True, help='Actual head observed by the host, not copied from context JSON')
    parser.add_argument('--gate', required=True, help='Gate required by the trusted host configuration')
    parser.add_argument('--phase', required=True, help='Phase required by the trusted host configuration')
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 600:
        parser.error('timeout must be between 1 and 600 seconds')
    try:
        return execute(args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print('CI preparation refused: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
