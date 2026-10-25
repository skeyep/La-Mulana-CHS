"""完整426基音×五调古字编码；使用公开定稿配方，不读取游戏原图。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image
from lm1_phonetic_stroke_v1 import (
    StrokeCodec as PosterCodec, DEFAULT_MAPPING, raster, union, smooth_knots,
)

INITIAL_NAMES = ['', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l', 'g', 'k', 'h',
                 'j', 'q', 'x', 'zh', 'ch', 'sh', 'r', 'z', 'c', 's', 'y', 'w']

SPECIALS = ['m', 'n', 'ng', 'hm', 'hng', 'ê']

ONSET_DONORS = {'':'jp-zero-balance','k':'jp-k','g':'jp-k','s':'jp-s','z':'jp-s','c':'jp-s',
               'j':'jp-s','x':'jp-s','sh':'jp-s','t':'jp-t','d':'jp-t','zh':'jp-t',
               'ch':'jp-t','q':'jp-t','n':'jp-n','h':'jp-h','b':'jp-h','p':'jp-h',
               'f':'jp-h','m':'jp-m','y':'jp-y','r':'jp-r','l':'jp-r','w':'jp-w'}

class FullStrokeCodec(PosterCodec):
    """Same finite component composition and encode return values as the game build."""

    def __init__(self, mapping_path=None):
        super().__init__(mapping_path)
        self.feature_inventory = self.mapping_data
        self.initials = {name: self.parts[name or 'zero'] for name in INITIAL_NAMES}
        self.rime_features = {}
        for base, features in self.feature_inventory['base_components'].items():
            if base not in SPECIALS:
                self.rime_features.setdefault(features['normalized_rime'], features)
        self.rimes = {name: self.make_rime(features) for name, features in self.rime_features.items()}
        self.allowed = {entry['code'] for entry in self.inventory['entries']}

    def make_rime(self, features):
        key = ('ligature-'+features['medial']+'-'+features['nucleus']) if features['medial'] else features['nucleus'].lower()
        layers = [self.parts[key]]
        if features['umlaut']:
            layers.append(self.parts['umlaut-spine'])
        if features['coda']:
            coda = features['coda']
            layers.append(self.parts[coda if coda in ('N', 'NG', 'U') else 'coda-'+coda])
        return union(layers)

    def special_layers(self, base):
        if base == 'ê':
            return self.initials[''], self.parts['open-e']
        onset = self.parts['h'] if base.startswith('h') else Image.new('L', (21, 21))
        if base.endswith('m'):
            rime = union([self.parts['nasal-M'], self.parts['syllabic-closure']])
        else:
            pieces = [self.parts['nasal-N'], self.parts['syllabic-closure']]
            if base.endswith('ng'):
                pieces.append(self.parts['nasal-G-branch'])
            rime = union(pieces)
        return onset, rime

    def encode(self, reading):
        if reading not in self.allowed:
            raise ValueError('Unknown inventory reading: '+reading)
        base, tone = reading[:-1], int(reading[-1])
        features = dict(self.feature_inventory['base_components'][base])
        if base in SPECIALS:
            onset, rime = self.special_layers(base)
        else:
            onset = self.initials[features['written_onset']]
            rime = self.rimes[features['normalized_rime']]
        layers = {'onset': onset.copy(), 'rime': rime.copy(), 'tone': self.parts['tone'+str(tone)].copy()}
        return union(layers.values()), layers, {**features, 'tone': tone, 'shape_scheme': 'stroke-full-v1',
                                               'phonetic_values': 'project-assigned Chinese; JP visual donors'}


StrokeCodec = FullStrokeCodec
Codec = FullStrokeCodec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reading', nargs='?', help='拼音音节与声调，如 kan4、lv4、ma5')
    parser.add_argument('--catalog', action='store_true', help='生成完整2130格alpha图集')
    parser.add_argument('--mapping', type=Path, default=DEFAULT_MAPPING)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.catalog == bool(args.reading):
        parser.error('请选择一个reading或--catalog')
    codec = Codec(args.mapping)
    if args.catalog:
        entries = codec.inventory['entries']
        columns = codec.mapping_data.get('catalog_columns', 48)
        rows = max(entry['catalog_index'] for entry in entries)//columns+1
        mask = Image.new('L', (columns*21, rows*21))
        for entry in entries:
            index = entry['catalog_index']
            mask.paste(codec.encode(entry['code'])[0], (index%columns*21, index//columns*21))
        summary = {'codes': len(entries), 'size': list(mask.size)}
    else:
        mask, _layers, features = codec.encode(args.reading)
        summary = {'reading': args.reading, 'size': list(mask.size), 'features': features}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mask.save(args.output)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
