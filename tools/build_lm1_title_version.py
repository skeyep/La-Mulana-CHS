"""Stamp release information beside the existing CHS title credit."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import struct

import pefile
from PIL import Image, ImageDraw, ImageFont
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

ROOT = Path(__file__).resolve().parents[1]
ATLAS_BOX = (720, 224, 1024, 240)
OLD_CREDIT_BOX = (720, 224, 836, 240)
OLD_X, OLD_WIDTH = 455, 116
NEW_WIDTH = 304
METADATA_X = 68


def identity(raw):
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def stamp_executable(raw):
    pe = pefile.PE(data=raw)
    section = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.lmcred')
    start = section.PointerToRawData
    length = section.Misc_VirtualSize
    code = raw[start:start + length]
    fp = lambda n: struct.unpack('<I', struct.pack('<f', n))[0]
    assembly = f'''pushfd
pushad
call current_pc
current_pc:
pop ebx
sub ebx, 0x{section.VirtualAddress + 7:x}
movzx ecx, word ptr [ebx+0x2deae8]
cmp ecx, 1
jb original
cmp ecx, 8
ja original
movzx eax, byte ptr [ebx+0x2e0e36]
cmp eax, ecx
jae original
mov eax, dword ptr [ebx+eax*4+0x2deb0c]
test eax, eax
jz original
cmp byte ptr [eax], 0x63
jne original
cmp byte ptr [eax+1], 0x68
jne original
cmp byte ptr [eax+2], 0x73
jne original
cmp byte ptr [eax+3], 0
jne original
mov ebp, esp
sub esp, 0x210
and esp, 0xfffffff0
fxsave [esp]
mov dword ptr [esp+0x200], ebp
'''
    # Keep the right-side author credit at its existing visible coordinates.
    for sx, width, dx in [(720, 200, METADATA_X), (927, 97, 474)]:
        assembly += f'''mov ebp, dword ptr [esp+0x200]
mov eax, dword ptr [ebp+68]
shr eax, 1
push eax
push dword ptr [ebp+64]
push 0x{fp(408):x}
push 0x{fp(dx):x}
push 0x{fp(16):x}
push 0x{fp(width):x}
push 0x{fp(224):x}
push 0x{fp(sx):x}
call 0x53610
add esp, 0x20
'''
    assembly += '''fxrstor [esp]
mov esp, dword ptr [esp+0x200]
original:
popad
popfd
jmp 0x53610
'''
    blob = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(assembly, addr=section.VirtualAddress)[0])
    original_layout = code != blob
    if original_layout:
        assert length == 167
        assert code.count(b'\x68' + struct.pack('<f', OLD_X)) == 1
        assert code.count(b'\x68' + struct.pack('<f', OLD_WIDTH)) == 1
    assert len(blob) <= section.SizeOfRawData
    result = bytearray(raw)
    result[start:start + section.SizeOfRawData] = blob + bytes(section.SizeOfRawData - len(blob))
    virtual_size_offset = section.get_field_absolute_offset('Misc_VirtualSize')
    result[virtual_size_offset:virtual_size_offset + 4] = struct.pack('<I', len(blob))
    changes = [{'offset': start, 'field': 'CHS title footer helper',
                'before_bytes': length, 'after_bytes': len(blob),
                'metadata_destination': [METADATA_X, 408], 'credit_destination': [474, 408]}]
    checksum_offset = pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum')
    checksum = pefile.PE(data=bytes(result)).generate_checksum()
    result[checksum_offset:checksum_offset + 4] = struct.pack('<I', checksum)
    new_pe = pefile.PE(data=bytes(result))
    assert new_pe.OPTIONAL_HEADER.AddressOfEntryPoint == pe.OPTIONAL_HEADER.AddressOfEntryPoint
    for before_section, after_section in zip(pe.sections, new_pe.sections):
        if before_section.Name != b'.lmcred\0':
            assert before_section.__pack__() == after_section.__pack__()
        else:
            assert before_section.VirtualAddress == after_section.VirtualAddress
            assert before_section.SizeOfRawData == after_section.SizeOfRawData
    return bytes(result), original_layout, changes


def stamp_atlas(path, font_path, version, updated, original_layout):
    image = Image.open(path).convert('RGBA')
    assert image.size == (1024, 256)
    if original_layout:
        assert not image.getchannel('A').crop((836, 224, 1024, 240)).getbbox()
        credit = image.crop(OLD_CREDIT_BOX)
    else:
        credit = Image.new('RGBA', (116, 16))
        credit.paste(image.crop((927, 224, 1024, 240)), (19, 0))
    strip = Image.new('RGBA', (NEW_WIDTH, 16))
    text = f'汉化版本 {version} · {updated}'
    font = ImageFont.truetype(str(font_path), 11, layout_engine=ImageFont.Layout.BASIC)
    bbox = font.getbbox(text)
    credit_ink = credit.getchannel('A').getbbox()
    assert credit_ink is not None
    assert credit_ink[0] == 19 and credit_ink[2] == 116
    credit_left = NEW_WIDTH - credit.width + credit_ink[0]
    assert bbox[2] - bbox[0] <= 200, 'Release label exceeds the footer space'
    height = bbox[3] - bbox[1]
    ImageDraw.Draw(strip).text((-bbox[0], (16 - height) // 2 - bbox[1]),
                               text, font=font, fill=(255, 255, 255, 255))
    strip.alpha_composite(credit, (NEW_WIDTH - credit.width, 0))
    image.paste(strip, ATLAS_BOX[:2])
    return image, strip, {'text': text, 'font_px': 11, 'source_xywh': [720, 224, 304, 16],
                          'metadata_destination_xy': [METADATA_X, 408],
                          'credit_destination_xy': [474, 408], 'credit_visible_right_x': 571,
                          'metadata_ink_width': bbox[2] - bbox[0],
                          'gap_to_credit_px': credit_left - (bbox[2] - bbox[0])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release-info', type=Path, default=ROOT / 'docs/release.json')
    parser.add_argument('--font', type=Path,
                        default=Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/LXGWZhenKaiGB-Regular.ttf')
    args = parser.parse_args()
    base, output = args.base.resolve(), args.output.resolve()
    assert base.is_dir() and not output.exists()
    release = json.loads(args.release_info.read_text(encoding='utf-8'))
    original = (base / 'LaMulanaWin.exe').read_bytes()
    updated_exe, original_layout, changes = stamp_executable(original)
    atlas, strip, layout = stamp_atlas(base / 'data/language/chs/font02.png', args.font,
                                      release['version'], release['updated'], original_layout)
    manifest = json.loads((base / 'build-manifest.json').read_text(encoding='utf-8'))
    shutil.copytree(base, output)
    (output / 'LaMulanaWin.exe').write_bytes(updated_exe)
    atlas.save(output / 'data/language/chs/font02.png')
    report = {'version': release['version'], 'updated': release['updated'], 'layout': layout,
              'source_executable': identity(original), 'output_executable': identity(updated_exe),
              'PE_changes': changes, 'source_candidate': str(base),
              'existing_credit_visual_position': 'unchanged; right edge x571',
              'runtime': 'pending-title-display'}
    report_path = output / 'title-version.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for relative in ['LaMulanaWin.exe', 'data/language/chs/font02.png', 'title-version.json']:
        manifest['output_files'][relative] = identity((output / relative).read_bytes())
    manifest.update(output_root=str(output), source_build_manifest=str(base / 'build-manifest.json'),
                    title_version={'version': release['version'], 'updated': release['updated'],
                                   'report': str(report_path)}, runtime='pending-title-display')
    (output / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    strip.save(output / 'title-footer-preview.png')
    preview = Image.new('RGBA', strip.size, (16, 16, 16, 255))
    preview.alpha_composite(strip)
    preview.resize((strip.width * 4, strip.height * 4), Image.Resampling.NEAREST).convert('RGB').save(
        output / 'title-footer-preview.jpg', quality=95)
    print(json.dumps({'candidate': str(output), 'version': release['version'],
                      'updated': release['updated'], 'layout': layout,
                      'executable': report['output_executable']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
