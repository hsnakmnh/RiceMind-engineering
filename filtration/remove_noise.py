#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
"""Filter annotation copies using per-category external TSV blacklists.

Default: dict-dir/filtering/blacklists/*_blacklist.tsv. Exact ID+text rules
preserve other names of the same entity. An explicit --blacklist-file selects
only that file (legacy ID-only tables are supported). Never modifies inputs.
Python 3.8+; tqdm is optional. See dict-dir/filtering/README.md.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(items, **kwargs):
        return items

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from ricemind_config import (CLEANED_OUTPUT_ROOT, NOISE_BLACKLIST_DIR,
                             OGER_RESULT_DIR, PHRASE_OUTPUT_ROOT, SCISPACY_OUTPUT_ROOT)

CATEGORIES = ('gene', 'variety', 'co', 'go', 'to', 'rto')
TOOLS = ('phrasematcher', 'scispacy', 'oger')
TRUE_VALUES = {'1', 'true', 'yes', 'y', 'on'}
FALSE_VALUES = {'0', 'false', 'no', 'n', 'off'}
RULE_FIELDS = ['enabled', 'category', 'entity_id', 'match_type', 'matched_text',
               'standard_name', 'source']


class RuleSet:
    def __init__(self, paths, directory_mode=False):
        self.paths = paths
        self.snapshots = {str(p): p.read_bytes() for p in paths}
        self.rows = []
        self.by_id = {}
        self.by_text = {}
        self.hits = Counter()
        self.deleted_by_category = Counter()
        for path in paths:
            self._load(path, directory_mode)

    def _load(self, path, directory_mode):
        expected_category = path.name[:-len('_blacklist.tsv')] if directory_mode else None
        if directory_mode and expected_category not in CATEGORIES:
            raise ValueError('不支持的分类文件名: ' + str(path))
        with io.StringIO(self.snapshots[str(path)].decode('utf-8-sig'), newline='') as handle:
            reader = csv.DictReader((line for line in handle
                                     if line.strip() and not line.lstrip().startswith('#')),
                                    delimiter='\t')
            fields = [field.strip().casefold() for field in (reader.fieldnames or [])]
            if len(set(fields)) != len(fields) or not {'enabled', 'category', 'entity_id'} <= set(fields):
                raise ValueError('规则表须包含唯一列 enabled/category/entity_id: ' + str(path))
            reader.fieldnames = fields
            for index, raw in enumerate(reader, 1):
                location = '{}:record{}'.format(path.name, index)
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError('规则列数不一致: ' + location)
                row = {field: raw.get(field, '').strip() for field in RULE_FIELDS}
                enabled = row['enabled'].casefold()
                if enabled not in TRUE_VALUES | FALSE_VALUES:
                    raise ValueError('enabled 必须为 1 或 0: ' + location)
                row['enabled'] = '1' if enabled in TRUE_VALUES else '0'
                row['category'] = row['category'].casefold()
                if row['category'] not in CATEGORIES + (('any',) if not directory_mode else ()):
                    raise ValueError('无效的 category: ' + location)
                if expected_category and row['category'] != expected_category:
                    raise ValueError('category 与文件名不一致: ' + location)
                # Only missing columns in a legacy table default to ID matching.
                if 'match_type' not in fields:
                    row['match_type'] = 'id'
                if row['match_type'] not in ('id', 'id_text') or not row['entity_id']:
                    raise ValueError('须设置 entity_id 和 match_type=id/id_text: ' + location)
                if row['match_type'] == 'id_text' and not row['matched_text']:
                    raise ValueError('id_text 缺少 matched_text: ' + location)
                if row['match_type'] == 'id' and row['matched_text']:
                    raise ValueError('id 模式不允许 matched_text；请使用 id_text: ' + location)
                row['rule_key'] = location
                row['rule_file'] = path.name
                self.rows.append(row)
                if row['enabled'] == '0':
                    continue
                key = (row['category'], row['entity_id'])
                lookup = self.by_id
                if row['match_type'] == 'id_text':
                    key += (row['matched_text'],)
                    lookup = self.by_text
                if key in lookup:
                    raise ValueError('重复启用的规则: {} / {}'.format(lookup[key]['rule_key'], location))
                lookup[key] = row

    def blocked(self, tool, category, entity_id, matched_text):
        # Specific text rules take precedence; each deleted row is counted once.
        rule = (self.by_text.get((category, entity_id, matched_text))
                or self.by_text.get(('any', entity_id, matched_text))
                or self.by_id.get((category, entity_id))
                or self.by_id.get(('any', entity_id)))
        if rule is None:
            return False
        self.hits[(rule['rule_key'], tool)] += 1
        self.deleted_by_category[(category, tool)] += 1
        return True


def category_from_path(path):
    for part in reversed(path.parts):
        value = part.casefold()
        if value.startswith('rice-') and value.endswith('-annotation-dir'):
            return value[len('rice-'):-len('-annotation-dir')]
        if value.startswith('scispacy_') and value.endswith('_result'):
            return value[len('scispacy_'):-len('_result')]
        if value in CATEGORIES:
            return value
    return 'any'


def annotation_category(entity_id, label='', fallback='any'):
    label = label.strip().casefold()
    if label == 'gene' or entity_id.startswith(('OryzaGeneID:', 'Supplementary_geneID:')):
        return 'gene'
    if label == 'variety':
        return 'variety'
    for prefix, category in (('CO_', 'co'), ('GO:', 'go'), ('TO:', 'to'), ('RTO:', 'rto')):
        if entity_id.startswith(prefix):
            return category
    return label if label in CATEGORIES else fallback


def process_tsv_file(source, destination, rules, tool, write_output):
    removed = 0
    fallback = category_from_path(source)
    with source.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle, delimiter='\t')
        header = next(reader, None)
        if header is None or not {'Trait_ID', 'Matched_Text'} <= set(header):
            raise ValueError('TSV 缺少 Trait_ID/Matched_Text 表头: ' + str(source))
        id_column, text_column = header.index('Trait_ID'), header.index('Matched_Text')
        target = None
        try:
            if write_output:
                destination.parent.mkdir(parents=True, exist_ok=True)
                target = destination.open('w', encoding='utf-8', newline='')
                writer = csv.writer(target, delimiter='\t', lineterminator='\n')
                writer.writerow(header)
            for row in reader:
                if not row:
                    continue
                if len(row) != len(header):
                    raise ValueError('TSV 列数不一致: {}:{}'.format(source, reader.line_num))
                entity_id, matched = row[id_column].strip(), row[text_column].strip()
                category = annotation_category(entity_id, fallback=fallback)
                if rules.blocked(tool, category, entity_id, matched):
                    removed += 1
                elif target is not None:
                    writer.writerow(row)
        finally:
            if target is not None:
                target.close()
    return removed


def process_oger_file(source, destination, rules, tool, write_output):
    removed = 0
    target = None
    fallback = category_from_path(source)
    try:
        if write_output:
            destination.parent.mkdir(parents=True, exist_ok=True)
            target = destination.open('w', encoding='utf-8', newline='')
        with source.open(encoding='utf-8-sig', newline='') as handle:
            for line in handle:
                blocked = False
                stripped = line.rstrip('\r\n')
                # Preserve sentence text even if it happens to contain tabs.
                if stripped.strip() and not re.match(r'^[^|\t]+\|[^|\t]+\|', stripped):
                    parts = stripped.split('\t')
                    if len(parts) < 6:
                        raise ValueError('无法识别的 PubTator 行: ' + str(source))
                    int(parts[1]), int(parts[2])
                    entity_id = parts[5].strip()
                    category = annotation_category(entity_id, parts[4], fallback)
                    blocked = rules.blocked(tool, category, entity_id, parts[3].strip())
                if blocked:
                    removed += 1
                elif target is not None:
                    target.write(line)
    finally:
        if target is not None:
            target.close()
    return removed


def write_table(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fields, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def is_within(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def build_parser():
    parser = argparse.ArgumentParser(description='按分类黑名单清理三工具标注，保留原始结果。')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--blacklist-dir', type=Path, help='自动读取目录中的 *_blacklist.tsv')
    selection.add_argument('--blacklist-file', type=Path, help='只读取此单表，兼容旧格式')
    parser.add_argument('--phrase-root', type=Path, default=PHRASE_OUTPUT_ROOT)
    parser.add_argument('--scispacy-root', type=Path, default=SCISPACY_OUTPUT_ROOT)
    parser.add_argument('--oger-root', type=Path, default=OGER_RESULT_DIR)
    parser.add_argument('--output-root', type=Path, default=CLEANED_OUTPUT_ROOT)
    parser.add_argument('--dry-run', action='store_true', help='完整预览，不写文件')
    parser.add_argument('--in-place', action='store_true', help='已停用；请指定独立输出目录')
    return parser


def run(args):
    if args.in_place:
        raise ValueError('--in-place 已停用，以免截断原始结果。请指定新的 --output-root。')
    directory = args.blacklist_dir
    single = args.blacklist_file
    if directory is None and single is None:
        legacy = os.environ.get('RICEMIND_NOISE_BLACKLIST_FILE')
        if legacy:
            single = Path(legacy)
        else:
            directory = NOISE_BLACKLIST_DIR
    if single is not None:
        paths = [single.expanduser().resolve()]
        print('[INFO] 单文件模式（不加载分类目录）: {}'.format(paths[0]))
    else:
        directory = directory.expanduser().resolve()
        if not directory.is_dir():
            raise FileNotFoundError('黑名单目录不存在: ' + str(directory))
        paths = sorted(directory.glob('*_blacklist.tsv'))
        print('[INFO] 黑名单目录: {}'.format(directory))
    if not paths:
        raise ValueError('没有找到 *_blacklist.tsv 规则文件')
    rules = RuleSet(paths, directory_mode=single is None)
    for path in paths:
        enabled = sum(row['enabled'] == '1' for row in rules.rows if row['rule_file'] == path.name)
        print('[INFO] {}: 启用 {} 条规则'.format(path.name, enabled))

    output = args.output_root.expanduser().resolve()
    roots = {'phrasematcher': args.phrase_root.expanduser().resolve(),
             'scispacy': args.scispacy_root.expanduser().resolve(),
             'oger': args.oger_root.expanduser().resolve()}
    files = {}
    for tool, root in roots.items():
        if not root.is_dir():
            raise FileNotFoundError('输入目录不存在: ' + str(root))
        if is_within(output, root) or is_within(root, output):
            raise ValueError('输出目录必须与输入目录分离: ' + str(root))
        if tool == 'oger':
            files[tool] = sorted(p for p in root.rglob('*.txt') if p.parent.name == 'pubtator')
        else:
            files[tool] = sorted(root.rglob('*.tsv'))
        if not files[tool]:
            raise ValueError('未找到标注文件（OGER 需 pubtator 目录）: ' + str(root))
        for path in files[tool]:
            if not is_within(path, root):
                raise ValueError('输入文件指向根目录外: ' + str(path))
    for path in paths:
        if is_within(path, output):
            raise ValueError('输出目录不能包含规则文件: ' + str(output))
    if not args.dry_run:
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError('输出非空，请使用新目录以保留旧结果: ' + str(output))
        audit = output / '_audit'
        audit.mkdir(parents=True, exist_ok=True)
        snapshot_dir = audit / 'blacklists'
        snapshot_dir.mkdir()
        for path in paths:
            (snapshot_dir / path.name).write_bytes(rules.snapshots[str(path)])

    summary = {'status': 'running', 'dry_run': args.dry_run,
               'created_at': datetime.now().astimezone().isoformat(),
               'input_roots': {tool: str(root) for tool, root in roots.items()},
               'output_root': str(output), 'file_counts': {tool: len(v) for tool, v in files.items()},
               'rule_files': [{'path': str(p), 'sha256': hashlib.sha256(rules.snapshots[str(p)]).hexdigest()}
                              for p in paths],
               'notes': ['删除量为标注行数，OGER 含五轮重复；去重提及请运行 annotations-statistics。',
                         '同一行只计入一条规则，id_text 优先于 id；未改句子文本、ID、坐标。']}
    if args.dry_run:
        print('[INFO] dry-run：不写文件。')
    else:
        print('[INFO] 新清理结果目录: ' + str(output))
        (audit / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        for tool, root in roots.items():
            processor = process_oger_file if tool == 'oger' else process_tsv_file
            print('[INFO] {}: {} 个文件'.format(tool, len(files[tool])))
            for source in tqdm(files[tool], desc=tool):
                destination = output / tool / source.relative_to(root)
                processor(source, destination, rules, tool, not args.dry_run)
        summary['status'] = 'complete'
    except Exception as exc:
        summary['status'] = 'failed'
        summary['error'] = str(exc)
        raise
    finally:
        category_rows = [dict(category=category, tool=tool,
                              deleted_annotation_rows=rules.deleted_by_category[(category, tool)])
                         for category in CATEGORIES for tool in TOOLS]
        rule_rows = [dict(row, tool=tool, deleted_annotation_rows=rules.hits[(row['rule_key'], tool)])
                     for row in rules.rows for tool in TOOLS]
        summary['deleted_rows_by_tool'] = {
            tool: sum(count for (category, name), count in rules.deleted_by_category.items() if name == tool)
            for tool in TOOLS}
        if not args.dry_run:
            write_table(audit / 'category_statistics.tsv', ['category', 'tool', 'deleted_annotation_rows'], category_rows)
            write_table(audit / 'rule_statistics.tsv', ['rule_key', 'rule_file'] + RULE_FIELDS + ['tool', 'deleted_annotation_rows'], rule_rows)
            (audit / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    for category in CATEGORIES:
        print('[INFO] {}: {}'.format(category, ', '.join(
            '{}={:,}'.format(tool, rules.deleted_by_category[(category, tool)]) for tool in TOOLS)))
    print('[INFO] {}完成；删除标注行: {}'.format('预览' if args.dry_run else '去噪', summary['deleted_rows_by_tool']))
    return summary


def main():
    try:
        run(build_parser().parse_args())
        return 0
    except Exception as exc:
        print('[ERROR] ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
