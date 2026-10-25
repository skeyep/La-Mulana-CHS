"""Check public translation/readings structure and optionally workspace parity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from export_sources import ABSOLUTE_PATH, build_export, normalized_png, read_json


def walk_strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)
    elif isinstance(value, str):
        yield value


def check_sources(root: Path, workspace: Path | None = None):
    translations = {}
    translation_files = sorted((root / 'translations').glob('*.json'))
    reading_files = sorted((root / 'readings').glob('*.json'))
    assert len(translation_files) == 20, 'Expected 19 main files and 1 EX file'
    assert len(reading_files) == 16, 'Expected 16 reading files'
    counts = {'main_translation_runs': 0, 'ex_translation_runs': 0, 'reading_runs': 0,
              'reading_units': 0, 'source_copy_units': 0, 'source_token_units': 0}
    for path in translation_files:
        data = read_json(path)
        assert data['schema'] == 'lm1-public-translations-v1'
        for record in data['records']:
            assert 'baseline' not in record and 'source_languages' not in record
            for run in record['translation_runs']:
                expected = f"{record['resource_id']}::s{run['source_segment_index']}"
                assert run['stable_key'] == expected
                assert expected not in translations, expected
                assert isinstance(run['zh'], str)
                translations[expected] = run
                counts['main_translation_runs' if data['namespace'] == 'main' else 'ex_translation_runs'] += 1
    reading_keys = set()
    allowed_routes = {'phonetic', 'literal', 'source-copy', 'source-token'}
    for path in reading_files:
        data = read_json(path)
        assert data['schema'] == 'lm1-public-readings-v1'
        for run in data['runs']:
            key = run['stable_key']
            assert key not in reading_keys, key
            reading_keys.add(key)
            assert key in translations, key
            assert run['zh'] == translations[key]['zh'], key
            assert ''.join(unit['character'] for unit in run['units']) == run['zh'], key
            assert run.get('source_tokens_sha256') == translations[key].get('source_tokens_sha256'), key
            for unit in run['units']:
                assert len(unit['character']) == 1, (key, unit)
                assert unit['route'] in allowed_routes, (key, unit)
                if unit['route'] == 'phonetic':
                    assert isinstance(unit['reading'], str) and unit['reading'][-1] in '12345', (key, unit)
                if unit['route'] == 'source-copy':
                    source_character = unit.get('source_character')
                    binding = data.get('source_symbols', {}).get(source_character, {})
                    source_token = unit.get('source_token', binding.get('token'))
                    assert isinstance(source_token, int) and source_character, (key, unit)
                    counts['source_copy_units'] += 1
                if unit['route'] == 'source-token':
                    assert isinstance(unit.get('source_token'), int), (key, unit)
                    counts['source_token_units'] += 1
                counts['reading_units'] += 1
            counts['reading_runs'] += 1
    assert counts['main_translation_runs'] == 7095, counts
    assert counts['ex_translation_runs'] == 118, counts
    assert len(translations) == 7213, counts
    assert counts['reading_runs'] == 5673, counts

    inventory = read_json(root / 'phonetic/inventory.json')
    stroke = read_json(root / 'phonetic/stroke-full-v1/mapping.json')
    codes = [entry['code'] for entry in stroke['entries']]
    assert len(codes) == len(set(codes)) == 2130
    assert {entry['base'] for entry in stroke['entries']} == set(stroke['base_components'])
    assert {entry['code'] for entry in inventory['entries']} == set(codes)
    for base in stroke['base_components']:
        assert {base + tone for tone in '12345'}.issubset(codes)
    assert len(stroke['base_components']) == 426
    for relative in ['phonetic/stroke-full-v1/catalog-alpha.png', 'phonetic/stroke-full-v1/catalog-mirror-alpha.png']:
        content = (root / relative).read_bytes()
        assert content == normalized_png(content), relative
        width, height = struct.unpack('>II', content[16:24])
        assert width >= 21 and height >= 21

    data_paths = [*translation_files, *reading_files, *sorted((root / 'phonetic').rglob('*.json'))]
    for path in data_paths:
        for text in walk_strings(read_json(path)):
            assert not ABSOLUTE_PATH.search(text), f'Absolute path in {path.relative_to(root)}'
    if workspace:
        expected_json, expected_png = build_export(workspace)
        for relative, data in expected_json.items():
            assert read_json(root / relative) == data, f'Workspace projection differs: {relative}'
        for relative, data in expected_png.items():
            assert (root / relative).read_bytes() == data, f'Workspace PNG differs: {relative}'
        counts['workspace_projection'] = 'equal'
    counts.update(translation_runs=len(translations), phonetic_bases=426, phonetic_codes=2130,
                  json_files=len(data_paths), png_metadata='normalized')
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--workspace', type=Path, help='Compare exact public projection with the working project')
    args = parser.parse_args()
    result = check_sources(args.data_root.resolve(), args.workspace.resolve() if args.workspace else None)
    print(json.dumps({'status': 'passed', **result}, ensure_ascii=False))


if __name__ == '__main__':
    main()
