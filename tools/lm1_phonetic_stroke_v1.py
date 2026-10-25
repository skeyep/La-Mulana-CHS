"""21px变宽笔锋绘制核心与18个已批准读音；读取公开定稿几何配方。"""
from __future__ import annotations
import argparse
import copy
import json
import math
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING = ROOT/'phonetic/stroke-full-v1/mapping.json'

SAMPLE = 12

SAMPLES = [
    ('看', 'kàn', 'kan4'), ('汝', 'rǔ', 'ru3'), ('手', 'shǒu', 'shou3'),
    ('中', 'zhōng', 'zhong1'), ('的', 'de', 'de5'), ('武', 'wǔ', 'wu3'),
    ('器', 'qì', 'qi4'), ('妈', 'mā', 'ma1'), ('麻', 'má', 'ma2'),
    ('马', 'mǎ', 'ma3'), ('骂', 'mà', 'ma4'), ('吗', 'ma', 'ma5'),
    ('行走', 'xíng', 'xing2'), ('银行', 'háng', 'hang2'), ('路', 'lù', 'lu4'),
    ('绿', 'lǜ', 'lv4'), ('山', 'shān', 'shan1'), ('伤', 'shāng', 'shang1'),
]

SUPPORTED = tuple(code for _han, _pinyin, code in SAMPLES)

def smooth_knots(knots):
    points = []
    for i in range(len(knots)-1):
        a, b, c, d = knots[max(0, i-1)], knots[i], knots[i+1], knots[min(len(knots)-1, i+2)]
        for step in range(24):
            t = step/24
            xy = [.5*((2*b[j])+(-a[j]+c[j])*t+(2*a[j]-5*b[j]+4*c[j]-d[j])*t*t+
                      (-a[j]+3*b[j]-3*c[j]+d[j])*t*t*t) for j in (0, 1)]
            width = b[2]+(c[2]-b[2])*t*t*(3-2*t)
            points.append((*xy, width))
    return points+[tuple(knots[-1])]

def raster(paths):
    high = Image.new('L', (21*SAMPLE, 21*SAMPLE))
    draw = ImageDraw.Draw(high)
    for knots in paths:
        points = smooth_knots(knots)
        left, right = [], []
        for i, (x, y, width) in enumerate(points):
            before, after = points[max(0, i-1)], points[min(len(points)-1, i+1)]
            dx, dy = after[0]-before[0], after[1]-before[1]
            length = math.hypot(dx, dy)
            nx, ny = -dy/length*width/2, dx/length*width/2
            left.append(((x+nx)*SAMPLE, (y+ny)*SAMPLE))
            right.append(((x-nx)*SAMPLE, (y-ny)*SAMPLE))
        draw.polygon(left+list(reversed(right)), fill=255)
    return high.resize((21, 21), Image.Resampling.BOX)

def union(images):
    result = Image.new('L', (21, 21))
    for image in images:
        result = ImageChops.lighter(result, image)
    return result

class StrokeCodec:
    """18-code interface using the same published final geometry and rasterizer."""

    def __init__(self, mapping_path=None):
        self.mapping_path = Path(mapping_path) if mapping_path is not None else DEFAULT_MAPPING
        self.mapping_data = json.loads(self.mapping_path.read_text(encoding='utf-8-sig'))
        self.inventory = self.mapping_data
        self.paths = copy.deepcopy(self.mapping_data['paths_final_xy_width'])
        self.parts = {name: raster(paths) for name, paths in self.paths.items()}

    def encode(self, reading):
        if reading not in SUPPORTED:
            raise ValueError('stroke-v1 supports only the 18 documented poster readings: '+reading)
        base, tone = reading[:-1], int(reading[-1])
        features = dict(self.inventory['base_components'][base])
        onset = self.parts[features['written_onset']].copy()
        rime_parts = [self.parts[features['nucleus'].lower()]]
        if features['umlaut']:
            rime_parts.append(self.parts['umlaut-spine'])
        if features['coda']:
            rime_parts.append(self.parts[features['coda']])
        layers = {'onset': onset, 'rime': union(rime_parts), 'tone': self.parts['tone'+str(tone)].copy()}
        assert not layers['onset'].crop((0, 17, 21, 21)).getbbox(), reading
        assert not layers['rime'].crop((0, 17, 21, 21)).getbbox(), reading
        assert not layers['tone'].crop((0, 0, 21, 17)).getbbox(), reading
        return union(layers.values()), layers, {**features, 'tone': tone,
                                               'shape_scheme': 'stroke-v1',
                                               'phonetic_values': 'project-assigned Chinese; JP visual donors'}


Codec = StrokeCodec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reading', help='拼音音节与声调，如 kan4、lv4、ma5')
    parser.add_argument('--mapping', type=Path, default=DEFAULT_MAPPING)
    parser.add_argument('--output', type=Path, required=True, help='21×21灰度alpha PNG的输出路径')
    args = parser.parse_args()
    mask, _layers, features = Codec(args.mapping).encode(args.reading)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mask.save(args.output)
    print(json.dumps({'reading': args.reading, 'size': list(mask.size), 'features': features}, ensure_ascii=False))


if __name__ == '__main__':
    main()
