"""Export editable Chinese, readings and finite phonetic data from a workspace."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import struct

MAIN_FILES = [
    'core-ui.json', 'guidance-gate.json', 'guidance-later.json',
    'items-software.json', 'main-early-gaps.json', 'pilot.json',
    'reader-bilingual.json', 'room-names.json', 'ruins-117-166.json',
    'ruins-167-216.json', 'ruins-217-266.json', 'ruins-267-316.json',
    'ruins-317-366.json', 'ruins-367-416.json', 'ruins-417-466.json',
    'ruins-467-566.json', 'ruins-567-666.json', 'ruins-667-866.json',
    'ruins-867-1095.json',
]
READING_FILES = [
    'pilot-reading.json', 'guidance-gate-reading.json',
    'guidance-later-reading.json', 'reader-bilingual-reading.json',
    'main-early-gaps-reading.json', 'ruins-117-166-reading.json',
    'ruins-167-216-reading.json', 'ruins-217-266-reading.json',
    'ruins-267-316-reading.json', 'ruins-317-366-reading.json',
    'ruins-367-416-reading.json', 'ruins-417-466-reading.json',
    'ruins-467-566-reading.json', 'ruins-567-666-reading.json',
    'ruins-667-866-reading.json', 'ruins-867-1095-reading.json',
]
EX_SOURCE = 'localization/translations/drafts/ex-modes.json'
ABSOLUTE_PATH = re.compile(r'(?i)(?:\b[A-Z]:[\\/]|file:///|\\\\[^\\\s]+\\)')
DROP_KEYS = {
    'inputs', 'outputs', 'galleries', 'verification', 'validation', 'runtime',
    'review', 'independent_review', 'evidence', 'evidence_kind', 'reason',
    'reasons', 'control_review', 'source_run_text', 'source_text',
    'path', 'source_path', 'parsed_path', 'dictionary_source', 'source_section',
    'excerpt', 'source_artifacts', 'source_policy', 'tool_versions',
    'source_symbol_scope_audit', 'shared_source_symbol_checks',
    'compile_status',
}
IDENTITY_FIELDS = [
    'semantic_decisions', 'literal_identity_requirements',
    'source_identity_requirements_snapshot', 'literal_glyph_sources',
    'original_blank_literal_occurrences', 'new_literal_glyphs_required',
    'cross_segment_source_bindings', 'damaged_tablet_layout_bindings',
]


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def clean_data(value, *, keep_status=False):
    """Keep rule data while removing local provenance and review-only fields."""
    if isinstance(value, dict):
        return {
            key: clean_data(item, keep_status=keep_status)
            for key, item in value.items()
            if key not in DROP_KEYS and (keep_status or key != 'status')
            and not (isinstance(item, str) and ABSOLUTE_PATH.search(item))
        }
    if isinstance(value, list):
        return [clean_data(item, keep_status=keep_status) for item in value
                if not (isinstance(item, str) and ABSOLUTE_PATH.search(item))]
    return copy.deepcopy(value)


def normalized_png(data: bytes) -> bytes:
    """Keep image chunks and transparency; remove comments and private metadata."""
    signature = b'\x89PNG\r\n\x1a\n'
    if data[:8] != signature:
        raise ValueError('Expected a PNG image')
    out = bytearray(signature)
    pos = 8
    seen_end = False
    while pos < len(data):
        length = struct.unpack_from('>I', data, pos)[0]
        end = pos + length + 12
        if end > len(data):
            raise ValueError('Truncated PNG chunk')
        kind = data[pos + 4:pos + 8]
        if kind in {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS'}:
            out.extend(data[pos:end])
        if kind == b'IEND':
            seen_end = True
            if end != len(data):
                raise ValueError('Unexpected data after PNG end')
        pos = end
    if not seen_end:
        raise ValueError('Missing PNG end')
    return bytes(out)


def project_translation(data, source_name, namespace):
    records = []
    for source_record in data['records']:
        resource_id = source_record['resource_id']
        record = {
            'resource_id': resource_id,
            'block_index': source_record['block_index'],
            'translation_runs': [],
        }
        for key in ['resource', 'ex_mode', 'content_category']:
            if key in source_record:
                record[key] = source_record[key]
        for source_run in source_record['translation_runs']:
            run = {
                'stable_key': f"{resource_id}::s{source_run['source_segment_index']}",
                'source_segment_index': source_run['source_segment_index'],
                'zh': source_run['zh'],
            }
            for key in ['source_token_offset', 'source_tokens_sha256', 'source_kind', 'disposition']:
                if key in source_run:
                    run[key] = source_run[key]
            record['translation_runs'].append(run)
        records.append(record)
    result = {
        'schema': 'lm1-public-translations-v1',
        'target_language': 'zh-CN',
        'namespace': namespace,
        'source_name': source_name,
        'credit': 'Skeyep_目目',
        'records': records,
    }
    if 'game_build_id' in data:
        result['game_build_id'] = data['game_build_id']
    if 'source_identity_requirements' in data:
        result['source_identity_requirements'] = clean_data(data['source_identity_requirements'])
    return result


def project_readings(data, source_name):
    runs = []
    for source_run in data['runs']:
        resource_id = source_run.get('resource_id') or f"data/language/script_code.dat::block:{source_run['block_index']:04d}"
        run = {
            'stable_key': f"{resource_id}::s{source_run['source_segment_index']}",
            'resource_id': resource_id,
            'block_index': source_run['block_index'],
            'source_segment_index': source_run['source_segment_index'],
            'zh': source_run['zh'],
            'units': copy.deepcopy(source_run['units']),
        }
        if 'source_tokens_sha256' in source_run:
            run['source_tokens_sha256'] = source_run['source_tokens_sha256']
        runs.append(run)
    result = {'schema': 'lm1-public-readings-v1', 'target_language': 'zh-CN',
              'source_name': source_name, 'runs': runs}
    symbols = data.get('source_artifacts', {}).get('symbol_sources', {})
    if symbols:
        result['source_symbols'] = clean_data(symbols)
    for key in IDENTITY_FIELDS:
        if key in data:
            result[key] = clean_data(data[key])
    if data.get('context_dictionary_attestations'):
        fields = {
            'block_index', 'source_segment_index', 'unit_index0', 'character',
            'reading', 'route', 'lexeme', 'lexeme_readings',
            'lexeme_unit_start0', 'lexeme_unit_end_exclusive0',
            'catalog_dictionary_attested', 'catalog_index', 'catalog_alpha_sha256',
            'source_tokens_sha256',
        }
        result['context_dictionary_attestations'] = [
            {key: copy.deepcopy(value) for key, value in row.items() if key in fields}
            for row in data['context_dictionary_attestations']
        ]
    return result


def build_export(workspace: Path):
    """Return public relative paths and content without writing the workspace."""
    json_files = {}
    png_files = {}
    for name in MAIN_FILES:
        source = workspace / 'localization/translations' / name
        json_files[f'translations/{name}'] = project_translation(read_json(source), name, 'main')
    json_files['translations/ex-modes.json'] = project_translation(
        read_json(workspace / EX_SOURCE), 'ex-modes.json', 'ex')
    for name in READING_FILES:
        data = read_json(workspace / 'localization/translations' / name)
        json_files[f'readings/{name}'] = project_readings(data, name)

    root = workspace / 'localization/font/phonetic'
    inventory = read_json(root / 'mapping-v1/mapping.json')
    json_files['phonetic/inventory.json'] = {
        'schema': 'lm1-public-phonetic-inventory-v1',
        **{key: clean_data(inventory[key], keep_status=True) for key in
           ['counts', 'cell', 'catalog_columns', 'tones', 'base_components', 'entries']},
    }
    stroke = read_json(root / 'shape-redesign/stroke-full-v1/mapping.json')
    json_files['phonetic/stroke-full-v1/mapping.json'] = {
        'schema': 'lm1-public-phonetic-strokes-v1',
        **{key: clean_data(stroke[key], keep_status=True) for key in
           ['cell', 'catalog_file', 'catalog_columns', 'counts', 'base_components',
            'entries', 'paths_final_xy_width', 'onset_donors', 'construction']},
    }
    for name in ['catalog-alpha.png', 'catalog-mirror-alpha.png']:
        png_files[f'phonetic/stroke-full-v1/{name}'] = normalized_png(
            (root / 'shape-redesign/stroke-full-v1' / name).read_bytes())
    preservation = read_json(root / 'semantic-v1/preservation.json')
    json_files['phonetic/preservation.json'] = {
        'schema': 'lm1-public-symbol-preservation-v1',
        **{key: clean_data(preservation[key], keep_status=True) for key in
           ['priority', 'source_groups', 'literal_sequences', 'protected_tokens',
            'chinese_binding_proposals', 'seal_names', 'graphic_policy', 'counts']},
    }
    components = read_json(root / 'shape-redesign/source-components.json')
    component_fields = {
        'id', 'role', 'source_family', 'source_character', 'source_token',
        'source_cell_box_xyxy', 'source_grif_crop_x', 'source_grif_width',
        'clean_reference_character', 'clean_reference_token',
        'selected_reference_parts', 'bbox_xyxy', 'bbox_size',
        'nonzero_count', 'nonzero_pixels_xy_alpha', 'description',
    }
    json_files['phonetic/source-components.json'] = {
        'schema': 'lm1-public-source-components-v1',
        'components': [
            {key: clean_data(value) for key, value in component.items() if key in component_fields}
            for component in components['components']
        ],
    }
    return json_files, png_files


def write_export(workspace: Path, output: Path):
    json_files, png_files = build_export(workspace)
    for relative, data in json_files.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for relative, data in png_files.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {'json_files': len(json_files), 'png_files': len(png_files),
            'main_translation_runs': sum(len(r['translation_runs']) for name, data in json_files.items() if name.startswith('translations/') and data['namespace'] == 'main' for r in data['records']),
            'ex_translation_runs': sum(len(r['translation_runs']) for name, data in json_files.items() if name.startswith('translations/') and data['namespace'] == 'ex' for r in data['records']),
            'reading_runs': sum(len(data['runs']) for name, data in json_files.items() if name.startswith('readings/'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path, help='Existing localization workspace')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1], help='Public data repository')
    args = parser.parse_args()
    print(json.dumps(write_export(args.workspace.resolve(), args.output.resolve()), ensure_ascii=False))


if __name__ == '__main__':
    main()
