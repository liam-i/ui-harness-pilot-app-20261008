"""逐 AC 字面渲染与独占输出；资格试验和业务报告共用，不解析业务状态。"""
from pathlib import Path
import re

import yaml


def fence(value, language='text'):
    delimiter = '`' * max(3, max((len(x) + 1 for x in re.findall(r'`+', value)), default=3))
    return delimiter + language + '\n' + value + ('' if value.endswith('\n') else '\n') + delimiter + '\n'


def render_records(records, metadata, assets_by_uid, *, title='Requirement 阅读报告', source_confirmations=None):
    parts = ['# ' + title + '\n', '本报告是固定输入的派生视图，不表示批准或 Gate 通过。\n',
             '## 固定输入\n', fence(yaml.safe_dump(metadata, allow_unicode=True, sort_keys=True), 'yaml')]
    for uid, record in sorted(records.items()):
        parts += [f'## {uid}\n', '### 标题\n', fence(record['header']),
                  '### 需求原文\n', fence(record['text'], 'markdown')]
        sources = record.get('source_refs', [])
        clarifications = [ref for ref in sources if ref['role'] == 'clarification']
        if clarifications:
            parts += ['R 级共享澄清（逐 AC 的适用条件仍需审阅）：\n',
                      fence(yaml.safe_dump(clarifications, allow_unicode=True, sort_keys=False), 'yaml')]
        for ac in record['acceptance']:
            # Project declared coverage only; never infer support from a shared
            # Requirement, chapter, or clarification reference.
            origin = [ref for ref in sources if ref['role'] == 'origin'
                      and ('acceptance' not in ref or ac['id'] in ref['acceptance'])]
            confirmation = [ref for ref in (source_confirmations or {}).get(uid, [])
                            if ac['id'] in ref['acceptance']]
            parts += [f"### {uid} / {ac['id']}\n", '条件：\n', fence(ac['condition']),
                      '预期结果：\n', fence(ac['expected']), '验证方式：\n',
                      fence(yaml.safe_dump({k: v for k, v in ac.items() if k not in ('condition', 'expected')}, allow_unicode=True), 'yaml'),
                      '来源关联（仅投影，不表示语义审定）：\n',
                      fence(yaml.safe_dump({'origin': origin, 'confirmation': confirmation},
                                           allow_unicode=True, sort_keys=False), 'yaml')]
        for asset in assets_by_uid.get(uid, []):
            parts += ['资产用途：\n', fence(asset['purpose']),
                      fence(yaml.safe_dump(asset['reference'], allow_unicode=True, sort_keys=True), 'yaml')]
            if asset.get('href'):
                parts += [f"[打开与固定引用字节一致的资产]({asset['href']})\n"]
            if asset.get('retrieve'):
                parts += ['需要独立取回时，在原业务仓库执行：\n', fence(asset['retrieve'], 'bash')]
        parts += ['### 完整字段快照\n', fence(yaml.safe_dump(record, allow_unicode=True, sort_keys=True), 'yaml')]
    return '\n'.join(parts)


def write_new_file(destination, output):
    """Only remove the file this call created; preserve the initiating failure."""
    destination = Path(destination)
    created = False
    try:
        with destination.open('x', encoding='utf-8') as stream:
            created = True
            stream.write(output)
            stream.flush()
    except BaseException as error:
        if created:
            try:
                destination.unlink(missing_ok=True)
            except OSError as cleanup:
                error.add_note('output cleanup failed: ' + str(cleanup))
        raise
