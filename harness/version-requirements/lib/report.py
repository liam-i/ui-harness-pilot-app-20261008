"""从同一固定 scope/R/来源生成 Catalog 与阅读报告；不执行或代替 G1。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys
from urllib.parse import quote

sys.dont_write_bytecode = True
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.context import resolve
from lib.core import canonical_bytes, digest, local_file, parse_json
from lib.errors import CheckError, InputError
from lib.gitstore import GitStore
from lib.rendering import render_records, write_new_file
from lib.requirements import RequirementIndex
from lib.runtime import implementation_manifest, preflight

import yaml


def output_directory(context, destination):
    destination = Path(destination).absolute()
    if any(p.is_symlink() for p in [destination, *destination.parents]):
        raise InputError('report.output-path', 'output directory must not traverse symlinks')
    destination = destination.resolve()
    if destination.exists():
        raise CheckError('report.output-exists', 'choose a new output directory; existing output is never replaced')
    permitted = context.store.root / context.vr / 'views'
    if destination.is_relative_to(context.store.root) and not destination.is_relative_to(permitted):
        raise CheckError('report.output-path', 'in-project reports belong under this Version views directory')
    if not destination.parent.is_dir():
        raise InputError('report.output-parent', 'prepare the explicit output parent before generating')
    return destination


def prepare(context, destination):
    if context.snapshot['gate'] != 'G1' or context.snapshot['phase'] != 'content':
        raise InputError('report.snapshot', 'use an explicit G1/content snapshot for this draft reading projection')
    model = RequirementIndex(context)
    asset_rows = {}
    entries = []
    for uid, info in sorted(model.records.items()):
        value = info['value']
        asset_rows[uid] = []
        for usage in value['asset_refs']:
            owner = model.asset_owner(info)
            resolved = model.assets.resolve_use(usage, owner=owner, acceptance=info['acs'], consumer={'requirement': uid})
            ref = resolved['content_ref']
            row = {'purpose': usage['purpose'], 'reference': {k: v for k, v in resolved.items() if k != 'bytes'},
                   'retrieve': 'git show ' + shlex.quote(ref['commit'] + ':' + ref['path'])}
            try:
                current = local_file(context.store.root, ref['path'])
                if digest(current.read_bytes()) == ref['sha256']:
                    row['href'] = quote(os.path.relpath(current, destination), safe='/.')
            except (OSError, CheckError):
                # A historical view must never link a current same-name asset
                # with different bytes. The fixed Git retrieval stays available.
                pass
            asset_rows[uid].append(row)
        entries.append({'requirement': uid, 'header': value['header'], 'kind': value['kind'], 'revision': value['revision'],
                        'record_ref': info['record_ref'], 'configuration_ref': info['configuration_ref'],
                        'source_refs': value['source_refs'], 'source_confirmations': model.included[uid]['source_confirmations']})
    inputs = {'snapshot': context.snapshot, 'resolved_inputs': context.store.manifest(),
              'generator_manifest': implementation_manifest()}
    generated_from = {**inputs, 'sha256': digest(canonical_bytes(inputs))}
    catalog = {'kind': 'generated-requirement-catalog', 'notice': '派生索引；不可编辑决定承诺、状态或批准。',
               'generated_from': generated_from, 'entries': entries}
    metadata = {'kind': 'fixed-content-reading-only', 'generated_from': generated_from,
                'questions': {k: v['status'] for k, v in model.questions.values.items()},
                'scope': sorted(model.records), 'notice': '生成成功不表示来源解释、Q、工程可行性或 G1 已通过。'}
    report = render_records({uid: info['value'] for uid, info in model.records.items()}, metadata, asset_rows,
                            source_confirmations={uid: model.included[uid]['source_confirmations']
                                                  for uid in model.records})
    return catalog, report


def generate(context, destination, *, view='requirements', filters=None, previous_context=None, impact_seeds=(), event_ref=None):
    destination = output_directory(context, destination)
    if event_ref is not None and view != 'changes':
        raise InputError('report.rc-inputs', 'event preview/confirmation belongs only to the changes view')
    if view != 'impact' and (previous_context is not None or impact_seeds):
        raise InputError('report.impact-inputs', 'previous context and impact seeds belong only to the impact view')
    if view == 'requirements':
        if filters:
            raise InputError('report.filter', 'engineering filters require the engineering view')
        catalog, report = prepare(context, destination)
        input_digest = catalog['generated_from']['sha256']
        content = {'catalog.yaml': yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), 'report.md': report}
    elif view == 'engineering':
        from lib.engineering_view import prepare as engineering
        model, content = engineering(context, filters=filters)
        input_digest = model['generated_from']['sha256']
    elif view == 'readiness':
        from lib.readiness import prepare as readiness
        with context.store.input_scope():
            model, content = readiness(context, filters=filters)
        input_digest = model['generated_from']['sha256']
    elif view == 'metrics':
        from lib.metrics import prepare as metrics
        with context.store.input_scope():
            model, content = metrics(context, filters=filters)
        input_digest = model['generated_from']['sha256']
    elif view == 'impact':
        from lib.impact import analyze
        if previous_context is None or filters:
            raise InputError('report.impact-inputs', 'impact requires a previous fixed context and cannot filter away affected obligations')
        model = analyze(previous_context, context, seeds=impact_seeds)
        input_digest = model['generated_from']['sha256']
        rows = ['# 需求变化影响审查', '', model['notice'], '',
                '生成依据：`' + input_digest + '`。完整对象、传播理由与固定引用见 `impact.json`。', '',
                '## 受影响对象', '']
        rows += ['- `' + row['id'] + '`' for row in model['affected']] or ['无已识别的影响；仍须核对未映射差异和诊断。']
        rows += ['', '## 尚未映射的实际差异', '']
        rows += ['- `' + row['group'] + '`：`' + row['path'] + '`' for row in model['unmapped_diff']] or ['无未映射差异。']
        rows += ['', '## 待处理诊断', '']
        rows += ['- `' + row['rule_id'] + '`：`' + row['object'] + '`' for row in model['diagnostics']] or ['无图解析诊断；不代表语义审阅通过。']
        content = {'impact.json': json.dumps(model, ensure_ascii=False, indent=2) + '\n',
                   'impact.md': '\n'.join(rows) + '\n'}
    elif view == 'changes':
        from lib.control import event
        from lib.control_delivery import read_delivery_control
        from lib.requirement_changes import KINDS as RC_KINDS
        if filters or context.snapshot['control_revision'] is None:
            raise InputError('report.rc-inputs', 'RC projection requires fixed published control and no engineering filters')
        control = read_delivery_control(context.store, context.snapshot['control_revision'], ui_context=context.snapshot)
        model = {'kind': 'published-requirement-changes', 'control_revision': control.revision,
                 'version': context.version['version'], 'delivery_line': context.version['delivery_line'],
                 'changes': control.changes.projections(version=context.version['version'], line=context.version['delivery_line'])}
        model['cancelled_reservations'] = [
            {'candidate_id': key[2], 'release_ref': row['release_ref'], 'disposition': row['receipt']}
            for key, row in sorted(control.cancelled.items())
            if key[:2] == (model['delivery_line'], model['version'])]
        if event_ref is not None:
            value = event(context.store, event_ref)
            cancellation = value['kind'] == 'slot-release' and value['payload'].get('outcome') == 'cancelled'
            if (value['kind'] not in RC_KINDS and not cancellation) or (value['version'], value['target_line']) != (model['version'], model['delivery_line']):
                raise InputError('report.rc-inputs', 'event must be a supported RC transition in this exact Version and line')
            if control.event_refs.get(event_ref['event_id']) == event_ref:
                model['event_check'] = {'scope': 'exact published RC reference confirmed; no engineering permission',
                    'control_revision': control.revision, 'event_ref': event_ref, 'published': True}
            else:
                if cancellation:
                    origin = parse_json(context.store.ref(value['payload']['cancellation']['context_ref']))
                    if any(origin[key] != context.snapshot[key] for key in ('target_revision', 'control_revision', 'baseline_ref')):
                        raise CheckError('cancellation.context', 'cancellation preview must observe the same current target, control and effective baseline')
                model['event_check'] = control.preview(context.store, event_ref)
        input_digest = digest(canonical_bytes(model))
        content = {'changes.json': json.dumps(model, ensure_ascii=False, indent=2) + '\n',
                   'changes.md': '# 已发布需求变更\n\n仅反映固定控制历史，不授予实施权限。\n\n' +
                       '\n'.join('- `' + row['id'] + '`：`' + row['status'] + '`；新 BL ' +
                                 ('已生效；已登记 ' + str(len(row.get('alignments', []))) + ' 项局部对齐，恢复须按对象和入口核对'
                                  if row['to_baseline'] else '尚未确认') for row in model['changes']) + '\n'}
        if event_ref is not None:
            content['changes.md'] += '\n指定事件：`' + event_ref['event_id'] + '`；' + (
                '已在所选控制提交发布。' if model['event_check']['published'] else '草稿预检通过，尚未发布。') + '\n'
    else:
        raise InputError('report.view', 'unknown reading view')
    # Serialize everything before the first write. The files are not a
    # filesystem transaction; on failure remove only outputs owned by this call.
    destination.mkdir()
    created = []
    try:
        for name, value in content.items():
            path = destination / name
            write_new_file(path, value)
            created.append(path)
    except BaseException as error:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError as cleanup:
                error.add_note('bundle cleanup failed: ' + str(cleanup))
        try:
            destination.rmdir()
        except OSError as cleanup:
            error.add_note('bundle directory retained: ' + str(cleanup))
        raise
    return {'kind': 'generated-reading-output', 'directory': str(destination),
            'input_digest': input_digest,
            'files': {name: digest(value.encode()) for name, value in content.items()}, 'gate_evaluated': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--view', choices=('requirements', 'engineering', 'readiness', 'metrics', 'impact', 'changes'), default='requirements')
    parser.add_argument('--previous-context', type=Path, help='impact: exact earlier snapshot; no floating BL selection')
    parser.add_argument('--impact-seed', action='append', default=[], help='impact: known graph object requiring reassessment; repeatable')
    parser.add_argument('--event-ref', type=Path, help='changes: exact RC event_ref JSON for readonly preview or publication confirmation')
    parser.add_argument('--ac', action='append', default=[], help='engineering: current scoped R-NNN/AC-NN; repeatable')
    parser.add_argument('--edge-kind', action='append', default=[], choices=('implementation','integration','release'))
    parser.add_argument('--strength', action='append', default=[], choices=('hard','soft','informational'))
    parser.add_argument('--checkpoint', action='append', default=[], choices=('apply-start','integration','merge','completion','release'))
    args = parser.parse_args(argv)
    try:
        preflight()
        snapshot = parse_json(local_file(args.context.parent, args.context.name).read_bytes())
        filters = {key: value for key, value in {'acceptance':args.ac,'kind':args.edge_kind,
                   'strength':args.strength,'checkpoint':args.checkpoint}.items() if value}
        previous = None
        if args.previous_context:
            previous_snapshot = parse_json(local_file(args.previous_context.parent, args.previous_context.name).read_bytes())
            previous = resolve(GitStore(args.root), previous_snapshot)
        event_ref = parse_json(local_file(args.event_ref.parent, args.event_ref.name).read_bytes()) if args.event_ref else None
        result = generate(resolve(GitStore(args.root), snapshot), args.output, view=args.view, filters=filters,
                          previous_context=previous, impact_seeds=args.impact_seed, event_ref=event_ref)
        code = 0
    except CheckError as error:
        result, code = {'diagnostic': error.diagnostic()}, 2 if error.unreadable else 1
    except (OSError, ValueError) as error:
        result, code = {'error': str(error), 'notes': getattr(error, '__notes__', [])}, 2
    print(json.dumps({**result, 'exit_code': code}, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
