#!/usr/bin/env python3
"""Offline SteamOS/Proton installer. Python 3.8+, standard library only."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import uuid

ORIGINAL = '94228016ffff8a0ba6325140f0cff6896e2bd0579bb2099d234508dede65923f'
FORMAL = 'e2920f56cf06705e3bf1943e2990e319f76c59a7f46cafd9e411666fc2e36f64'
TITLE = '0e44ea2a3d940ebc6f6561026a1c4476fd9ec52c8b21894316457ceee1567ad4'
LOCALE = '9b1081cda51fb9384571078c1ea97bf03a622dd5ead732ae2c4ea27474f2c42f'
FOOTER = 'a4f7c74d4b468e9bd94ad120442e5eb789ddd0e2e63a6c8e5278d791465498fb'
ASSISTANT_PROFILES = {
    'ba4946a2430da7d783b22a7f6f0cc0197bb7f0a9c6b5b55a757619d975c32c1e': TITLE,
    'd113161ccac9e010106d5c2c0d87b80455fde32d6eab3e858bec199e30b2e14e': LOCALE,
    'ee081e8cade83ac2df678a0e0467df5385510b9208252a2e306b07d5e1682409': FOOTER,
    # BUILD-ASSISTANT-PROFILES
}
MODES = ('01guardian1c', '02guardian1b', '03guardian1a', '04roomguardian3c',
         '05roomguardian3b', '06roomguardian3a', '07roomguardian2c', '08roomguardian2b',
         '09roomguardian2a', '10roomguardian1c', '11roomguardian1b', '12roomguardian1a')
ASSISTANT = {'lm_assistant.dll', 'data/language/chs/assistant-font.ttf'}
TITLE_TARGETS = {'data/language/chs/title01.png', 'data/language/chs/title.msd'}
SETTINGS = {'data/graphics/00/_banner.png', 'data/music/00/_banner.png'}
TITLE_BASELINES = {
    'data/graphics/00/title01.png': '0a6378cce5dc1bd1d16da29bb32c0e4820a6f30d37f7f058285845ff528a526c',
    'data/mapdata/title.msd': 'fdb67475730211d9909b6c728bdfd0c0635eed768bb73e9467d5c2ac897872b8',
}
# Original resource identities and backup names match Patch.ps1.
RESOURCES = {
    'data/graphics/00/_banner.png': ('fa05d6e4a27836cdcf7ef3d5e8a0ddbda2c4c25e2a07ab6674dc3fb0c3c960d2', 1316, 'original-graphics-banner.png'),
    'data/music/00/_banner.png': ('fa05d6e4a27836cdcf7ef3d5e8a0ddbda2c4c25e2a07ab6674dc3fb0c3c960d2', 1316, 'original-music-banner.png'),
    'data/graphics/00/eveg01.png': ('e3ff836d03cbbfdc12e9bcd8584972227bf23ddb77498d915d5abd5d75ce4faf', 93941, 'original-shared-eveg01.png'),
    'data/graphics/00/eveg18.png': ('8eaeffd17a4eeee23a086d02b19a119083aa196e740fdaf94e5ca12f008abe59', 89392, 'original-shared-eveg18.png'),
    'data/graphics/00/map01_1.png': ('3097c939bf6b25fc4845a0501a5e46e440572c9662eaa8891f55b9b9aaed7ca9', 386436, 'original-shared-map01_1.png'),
}
SHARED = set(RESOURCES) - SETTINGS
DIRECTORIES = {'data/language/chs'} | {'data/ex/' + m + '/language/chs' for m in MODES}
BASE_TARGETS = {'LaMulanaWin.exe'} | {'data/language/chs/' + n for n in (
    'script_code.dat', 'font00.png', 'font01.png', 'font02.png', 'grif.dat', '_banner.png', '01menu.png')}
BASELINES = {'LaMulanaWin.exe', 'data/graphics/00/01menu.png'} | {
    'data/language/jp/' + n for n in ('script_code.dat', 'font00.png', 'font01.png', 'font02.png', 'grif.dat')}
for _mode in MODES:
    for _name in ('script_code.dat', 'title.dat', 'font02.png'):
        BASE_TARGETS.add('data/ex/' + _mode + '/language/chs/' + _name)
        BASELINES.add('data/ex/' + _mode + '/language/jp/' + _name)
NATIVE_MESSAGE = ('The Windows build is required. In Steam > Properties > Compatibility, '
                  'force a Proton version and wait for the Windows download. Start the game '
                  'once from Steam, exit it, then run Install.sh again.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    with path.open('rb') as stream:
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def relative_parts(relative):
    require(isinstance(relative, str) and relative and not any(c in relative for c in ('\\', ':', '\0'))
            and not relative.startswith('/') and all(p not in ('', '.', '..') for p in relative.split('/')),
            'Invalid relative path: ' + str(relative))
    return relative.split('/')


def inside(root, relative):
    target = root
    for part in relative_parts(relative):
        target = target / part
        require(not target.is_symlink(), 'Symlink below selected directory: ' + str(target))
    require(target.resolve().is_relative_to(root.resolve()) if sys.version_info >= (3, 9)
            else os.path.commonpath([str(root.resolve()), str(target.resolve())]) == str(root.resolve()),
            'Path leaves selected directory: ' + relative)
    return target


def file_info(path):
    if not path.exists():
        return None
    require(path.is_file(), 'Expected a regular file: ' + str(path))
    return {'sha256': digest(path), 'bytes': path.stat().st_size}


def verify_file(path, expected):
    require(file_info(path) == {k: expected[k] for k in ('sha256', 'bytes')},
            'File missing or changed: ' + str(path))


def sync_directory(directory):
    if sys.platform == 'linux':
        fd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_bytes(path, data, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temp = tempfile.mkstemp(prefix='write-', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        # Windows can briefly hold an EXE while inspecting its new contents.
        # The production Linux path still performs one atomic rename.
        expected = file_info(path) if os.name == 'nt' else None
        delays = (0.04, 0.08, 0.12, 0.18, 0.26, 0.36, 0.5)
        for attempt in range(len(delays) + 1):
            try:
                os.replace(temp, str(path))
                break
            except PermissionError as exc:
                if os.name != 'nt' or exc.winerror not in (5, 32, 33) or attempt == len(delays):
                    raise
                time.sleep(delays[attempt])
                require(file_info(path) == expected, 'Atomic target changed while waiting for a file lock: ' + str(path))
        sync_directory(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def copy_verified(source, target, expected):
    verify_file(source, expected)
    atomic_bytes(target, source.read_bytes())


def profile(files):
    rows = {r['path']: r for r in files}
    require(len(rows) == len(files) and 'LaMulanaWin.exe' in rows, 'Missing or duplicate executable/targets')
    exe = rows['LaMulanaWin.exe']['sha256']
    base = ASSISTANT_PROFILES.get(exe, exe)
    require(base in (FORMAL, TITLE, LOCALE, FOOTER), 'Unsupported patch executable')
    targets, baselines = set(BASE_TARGETS), set(BASELINES)
    if base != FORMAL:
        targets |= TITLE_TARGETS
        baselines |= set(TITLE_BASELINES)
    if base == TITLE and SETTINGS.intersection(rows):
        targets |= SETTINGS
        baselines |= SETTINGS
    if SHARED.intersection(rows):
        targets |= SHARED
        baselines |= SHARED
    if exe in ASSISTANT_PROFILES:
        targets |= ASSISTANT
    require(set(rows) == targets, 'Incomplete or unexpected patch targets')
    for relative, row in rows.items():
        relative_parts(relative)
        require(re.fullmatch('[0-9a-f]{64}', row['sha256']) and isinstance(row['bytes'], int) and row['bytes'] > 0,
                'Invalid file identity: ' + relative)
        require(row['operation'] == ('replace' if relative == 'LaMulanaWin.exe' or relative in RESOURCES else 'add'),
                'Unexpected operation: ' + relative)
    return baselines


def validate_manifest(manifest, package, payloads=True):
    require(manifest['schema'] == 'lm1-chs-offline-package-v1' and manifest['app_id'] == 230700
            and manifest['original_exe_sha256'] == ORIGINAL, 'Unsupported patch package or game version')
    require(re.fullmatch('[0-9a-f]{64}', manifest['package_id']), 'Invalid package identity')
    expected = profile(manifest['files'])
    rows = {r['path']: r for r in manifest['baseline_files']}
    require(len(rows) == len(manifest['baseline_files']) and set(rows) == expected, 'Incomplete or unexpected baseline list')
    for relative, row in rows.items():
        inside(package, relative)
        require(re.fullmatch('[0-9a-f]{64}', row['sha256']) and isinstance(row['bytes'], int) and row['bytes'] > 0,
                'Invalid baseline identity')
        known = ORIGINAL if relative == 'LaMulanaWin.exe' else TITLE_BASELINES.get(relative)
        if relative in RESOURCES:
            known = RESOURCES[relative][0]
            require(row['bytes'] == RESOURCES[relative][1], 'Wrong resource size')
        require(known is None or row['sha256'] == known, 'Wrong supported baseline: ' + relative)
    if payloads:
        for row in manifest['files']:
            require(row['payload'] == 'payload/' + row['sha256'] + '.bin', 'Invalid payload path')
            verify_file(inside(package, row['payload']), row)


def parse_vdf(text):
    """Steam's quoted key/value and object syntax, including older library lists."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}]', re.sub(r'(?m)^\s*//[^\n]*', '', text))
    def unquote(token):
        require(token.startswith('"'), 'Malformed Steam VDF')
        return re.sub(r'\\([\\"])', r'\1', token[1:-1])
    def obj(pos, nested=False):
        result = {}
        while pos < len(tokens):
            if tokens[pos] == '}':
                require(nested, 'Unexpected VDF closing brace')
                return result, pos + 1
            key = unquote(tokens[pos])
            pos += 1
            require(pos < len(tokens), 'Incomplete Steam VDF')
            if tokens[pos] == '{':
                value, pos = obj(pos + 1, True)
            else:
                value = unquote(tokens[pos])
                pos += 1
            result[key] = value
        require(not nested, 'Unclosed Steam VDF object')
        return result, pos
    return obj(0)[0]


def steam_libraries(roots=None):
    home = Path.home()
    if not roots:
        roots = [home / '.local/share/Steam', home / '.steam/steam', home / '.steam/root',
                 home / '.var/app/com.valvesoftware.Steam/.local/share/Steam']
        if os.environ.get('XDG_DATA_HOME'):
            roots.append(Path(os.environ['XDG_DATA_HOME']) / 'Steam')
    libraries = []
    for root in roots:
        root = Path(root).expanduser().resolve()
        if root.is_dir() and root not in libraries:
            libraries.append(root)
        vdf = root / 'steamapps/libraryfolders.vdf'
        if vdf.is_file():
            data = parse_vdf(vdf.read_text(encoding='utf-8-sig'))
            for key, value in data.get('libraryfolders', data).items():
                path = value.get('path') if isinstance(value, dict) else value if key.isdigit() else None
                if path:
                    library = Path(path).expanduser().resolve()
                    if library.is_dir() and library not in libraries:
                        libraries.append(library)
    return libraries


def game_candidates(libraries):
    games = []
    for library in libraries:
        acf = library / 'steamapps/appmanifest_230700.acf'
        if not acf.is_file():
            continue
        app = parse_vdf(acf.read_text(encoding='utf-8-sig')).get('AppState', {})
        if app.get('appid') != '230700':
            continue
        name = app.get('installdir', '')
        require(name and not any(c in name for c in '/\\:') and name not in ('.', '..'), 'Invalid Steam installation directory')
        game = (library / 'steamapps/common' / name).resolve()
        if game.is_dir() and game not in games:
            games.append(game)
    return games


def select_game(explicit, candidates):
    if explicit:
        path = explicit
    elif len(candidates) == 1:
        path = str(candidates[0])
    else:
        for i, candidate in enumerate(candidates, 1):
            print('  {}. {}'.format(i, candidate))
        require(sys.stdin.isatty(), 'Specify the game directory with --game-dir PATH.')
        path = input('Game folder path' + (' or list number' if candidates else '') + ': ').strip()
        if path.isdigit() and 1 <= int(path) <= len(candidates):
            path = str(candidates[int(path) - 1])
        elif len(path) >= 2 and path[0] == path[-1] and path[0] in ('"', "'"):
            path = path[1:-1]
    game = Path(path).expanduser().resolve()
    require(game.is_dir(), 'Game folder not found: ' + str(game))
    require((game / 'LaMulanaWin.exe').is_file(), NATIVE_MESSAGE)
    return game


def config_candidates(game, libraries):
    associated = game.parent.parent.parent if game.parent.name == 'common' and game.parent.parent.name == 'steamapps' else None
    ordered = ([associated] if associated else []) + libraries
    result = []
    for library in ordered:
        users = library / 'steamapps/compatdata/230700/pfx/drive_c/users/steamuser'
        for documents in ('Documents', 'My Documents'):
            # My Documents is often an alias to Documents in a Wine prefix.
            path = users / documents / 'NIGORO/La-Mulana/config.ini'
            if users.is_dir() and path.resolve() not in result:
                result.append(path.resolve())
    return result


def select_config(game, libraries, explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidates = config_candidates(game, libraries)
    existing = [p for p in candidates if p.is_file()]
    return existing[0] if existing else candidates[0] if candidates else None


def chinese_config(game, config):
    require(config is not None, 'Proton prefix not found. ' + NATIVE_MESSAGE)
    # Wine sorts FindFirstFile directory results; the game reserves en/jp first.
    names = sorted({p.name for p in (game / 'data/language').iterdir() if p.is_dir() and p.name not in ('en', 'jp')} | {'chs'}, key=str.upper)
    codes = ['en', 'jp'] + names[:6]
    require('chs' in codes, 'CHS is outside the eight language slots; remove unused third-party language packs first.')
    before = config.read_bytes() if config.is_file() else None
    text = (before or b'').decode('utf-8-sig')
    pattern = r'(?m)^Language=[^\r\n]*'
    replacement = 'Language=' + str(codes.index('chs'))
    if re.search(pattern, text):
        text = re.sub(pattern, replacement, text)
    else:
        newline = '\r\n' if '\r\n' in text else '\n'
        text += (newline if text and not text.endswith('\n') else '') + replacement + newline
    after = (b'\xef\xbb\xbf' if before and before.startswith(b'\xef\xbb\xbf') else b'') + text.encode('utf-8')
    return before, after, codes.index('chs')


def check_game_process(game):
    if sys.platform != 'linux':
        return
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            matching = [a.decode('utf-8', 'replace') for a in args if a.lower().replace(b'\\', b'/').endswith(b'/lamulanawin.exe') or a.lower() == b'lamulanawin.exe']
            if matching:
                cwd = (proc / 'cwd').resolve()
                if cwd == game or any(str(game).lower() in a.replace('\\', '/').lower() for a in matching):
                    raise ValueError('Close La-Mulana in the selected game folder before changing files (PID ' + proc.name + ').')
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue


@contextlib.contextmanager
def operation_lock(game):
    # Lock identity prevents concurrent writers without adding files to the game.
    key = hashlib.sha256(str(game).encode('utf-8')).hexdigest()
    path = Path(tempfile.gettempdir()) / ('lamulana-chs-' + key + '.lock')
    with path.open('a+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0)
                if not stream.read(1):
                    stream.write(b'0')
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Another patch operation is running for this game directory.')
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


class Installer:
    def __init__(self, game, package, config=None):
        self.game, self.package, self.config = game, package, config
        self.state_dir = inside(game, '.lamulana-zh')
        self.state_file = inside(self.state_dir, 'state.json')
        self.journal = inside(self.state_dir, 'portable-upgrade.json')

    def backup(self, relative):
        return inside(self.state_dir, 'original-LaMulanaWin.exe' if relative == 'LaMulanaWin.exe' else RESOURCES[relative][2])

    def validate_state(self, state):
        require(state['schema'] == 'lm1-chs-install-state-v1' and state['original_exe_sha256'] == ORIGINAL
                and state['status'] in ('installed', 'restored'), 'Unsupported or incomplete installation receipt')
        require(re.fullmatch('[0-9a-f]{64}', state['package_id']) and re.fullmatch('stage-[0-9a-f]{32}', state['stage']), 'Invalid receipt identity')
        profile(state['files'])
        require(set(state['created_directories']) <= DIRECTORIES, 'Unexpected created directory in receipt')
        require(digest(self.backup('LaMulanaWin.exe')) == ORIGINAL, 'Original executable backup changed')
        for row in state['files']:
            if row['path'] in RESOURCES:
                h, size, _ = RESOURCES[row['path']]
                verify_file(self.backup(row['path']), {'sha256': h, 'bytes': size})

    def state(self):
        if self.state_file.exists():
            state = read_json(self.state_file)
            self.validate_state(state)
            return state
        return None

    def baseline(self, manifest, state):
        owned = {r['path'] for r in state['files']} if state and state['status'] == 'installed' else set()
        for row in manifest['baseline_files']:
            relative = row['path']
            path = self.backup(relative) if relative in owned and (relative in RESOURCES or relative == 'LaMulanaWin.exe') else inside(self.game, relative)
            verify_file(path, row)

    def installed(self, state):
        if state['status'] == 'installed':
            for row in state['files']:
                verify_file(inside(self.game, row['path']), row)

    def mod_compatibility(self):
        anchors = {'data/mapdata/map00.msd': '3829c4a6718c87da9da20eaccb9c8a8397bf6168e49f3aeaef489b7c81dc684e',
                   'data/mapdata/script.rcd': 'd09c6e2e6357843080f24040d53a9611b4cfc6366ee78a20c19318a4ae369616'}
        for relative, h in anchors.items():
            path = inside(self.game, relative)
            require(not path.is_file() or digest(path) != h,
                    'La-Mulana EX Map Port is unsupported. Keep your EX game and saves separately. '
                    'Move the EX folder out of the Steam library, use Steam > Properties > Installed Files > '
                    'Verify integrity to obtain clean original files, then run Install.sh. Detected: ' + relative)
        graphics = inside(self.game, 'data/graphics')
        if graphics.is_dir() and any(p.is_dir() and p.name != '00' and (p / '_banner.png').is_file() for p in graphics.iterdir()):
            print('NOTE: Extra graphics packs will be kept. Select the original graphics pack for translated image text.')

    def prepare(self, manifest, state):
        self.baseline(manifest, state)
        if state:
            self.installed(state)
            if state['status'] == 'installed' and state['package_id'] == manifest['package_id']:
                signature = lambda rows: sorted((r['path'], r['sha256'], r['bytes'], r['operation']) for r in rows)
                require(signature(state['files']) == signature(manifest['files']), 'The same package identity now has different files')
        elif self.state_dir.exists():
            known = {'original-LaMulanaWin.exe'} | {v[2] for v in RESOURCES.values()}
            require(all(p.is_file() and not p.is_symlink() and (p.name in known or re.fullmatch(r'write-.*\.tmp', p.name))
                        for p in self.state_dir.iterdir()), 'Reserved backup folder exists without a valid receipt')
        owned = {r['path'] for r in state['files']} if state and state['status'] == 'installed' else set()
        for row in manifest['files']:
            relative = row['path']
            path = inside(self.game, relative)
            require(relative in owned or relative == 'LaMulanaWin.exe' or relative in RESOURCES or not path.exists(),
                    'Unowned CHS target exists: ' + relative)
        for relative in ['LaMulanaWin.exe'] + [r['path'] for r in manifest['files'] if r['path'] in RESOURCES]:
            backup = self.backup(relative)
            source = inside(self.game, relative)
            if not backup.exists():
                info = next(r for r in manifest['baseline_files'] if r['path'] == relative)
                copy_verified(source, backup, info)
        if state is None:
            state = {'schema': 'lm1-chs-install-state-v1', 'status': 'restored', 'package_id': manifest['package_id'],
                     'original_exe_sha256': ORIGINAL, 'files': manifest['files'], 'created_directories': [],
                     'stage': 'stage-' + uuid.uuid4().hex}
            atomic_json(self.state_file, state)
        self.validate_state(state)
        return state

    def save_recovery(self):
        source = Path(__file__).resolve()
        target = inside(self.state_dir, 'Restore.py')
        if source != target:
            atomic_bytes(target, source.read_bytes())
        launcher = ('#!/bin/bash\nset -u\nbase="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1\n'
                    'python3 "$base/Restore.py" --action Restore --game-dir "$base/.." "$@"\n'
                    'status=$?\nif [[ -t 0 && -z "${LM_CHS_NO_PAUSE:-}" ]]; then read -r -p "Press Enter to close..." _; fi\nexit "$status"\n')
        atomic_bytes(inside(self.state_dir, 'Restore.sh'), launcher.encode('ascii'), 0o755)

    def operation_path(self, entry):
        if entry['scope'] == 'game':
            return inside(self.game, entry['path'])
        require(entry['scope'] == 'config' and self.config is not None and entry['path'] == str(self.config),
                'Proton configuration path differs. Rerun with --config-path pointing to the original Proton config.ini.')
        return self.config

    def read_transaction(self):
        journal = read_json(self.journal)
        require(journal['schema'] == 'lm1-chs-portable-transaction-v1' and re.fullmatch('[0-9a-f]{32}', journal['id']), 'Invalid Linux recovery journal')
        work = inside(self.state_dir, 'portable/tx-' + journal['id'])
        require(digest(inside(work, 'plan.json')) == journal['plan_sha256'], 'Linux recovery plan changed')
        plan = read_json(work / 'plan.json')
        self.validate_state(plan['previous_state'])
        self.validate_state(plan['next_state'])
        require(plan['action'] in ('Install', 'Restore'), 'Invalid transaction action')
        allowed = {r['path'] for r in plan['previous_state']['files']} | {r['path'] for r in plan['next_state']['files']}
        seen = set()
        for i, entry in enumerate(plan['operations']):
            require((entry['scope'], entry['path']) not in seen, 'Duplicate transaction target')
            seen.add((entry['scope'], entry['path']))
            require(entry['scope'] != 'game' or entry['path'] in allowed, 'Unexpected recovery target')
            self.operation_path(entry)
            for kind in ('before', 'after'):
                if entry[kind] is not None:
                    verify_file(inside(work, kind + '/{:03d}.bin'.format(i)), entry[kind])
        require(set(plan['created_directories']) <= DIRECTORIES, 'Unexpected transaction directory')
        return work, plan

    def rollback_pending(self):
        work, plan = self.read_transaction()
        # Validate all live targets before restoring the first one.
        for entry in plan['operations']:
            require(file_info(self.operation_path(entry)) in (entry['before'], entry['after']),
                    'File changed outside interrupted transaction: ' + entry['path'])
        for i in range(len(plan['operations']) - 1, -1, -1):
            self.apply_entry(work, plan['operations'][i], i, 'before')
        atomic_json(self.state_file, plan['previous_state'])
        for relative in sorted(plan['created_directories'], key=len, reverse=True):
            path = inside(self.game, relative)
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        self.journal.unlink()
        sync_directory(self.state_dir)
        print('PASS: interrupted operation rolled back to the previous installation.')

    def apply_entry(self, work, entry, index, kind):
        path = self.operation_path(entry)
        actual, wanted = file_info(path), entry[kind]
        if actual == wanted:
            return
        require(actual in (entry['before'], entry['after']), 'Target changed during operation: ' + entry['path'])
        if wanted is None:
            path.unlink()
            sync_directory(path.parent)
        else:
            copy_verified(inside(work, kind + '/{:03d}.bin'.format(index)), path, wanted)

    def transaction(self, action, state, next_state, wanted, config_bytes=None):
        ident = uuid.uuid4().hex
        work = inside(self.state_dir, 'portable/tx-' + ident)
        operations = []
        for relative, source in wanted.items():
            target = inside(self.game, relative)
            before, after = file_info(target), file_info(source) if source else None
            if before == after:
                continue
            operations.append(({'scope': 'game', 'path': relative, 'before': before, 'after': after}, target, source))
        if config_bytes is not None:
            before, after = config_bytes
            require((self.config.read_bytes() if self.config.is_file() else None) == before,
                    'Proton configuration changed during installation; rerun Install.sh.')
            if before != after:
                target = self.config
                info = {'sha256': hashlib.sha256(after).hexdigest(), 'bytes': len(after)}
                operations.append(({'scope': 'config', 'path': str(target), 'before': file_info(target), 'after': info}, target, after))
        created = [d for d in DIRECTORIES if action == 'Install' and not inside(self.game, d).is_dir()]
        next_state = dict(next_state, stage='stage-' + ident)
        for i, (entry, target, source) in enumerate(operations):
            if entry['before'] is not None:
                copy_verified(target, inside(work, 'before/{:03d}.bin'.format(i)), entry['before'])
            if entry['after'] is not None:
                blob = inside(work, 'after/{:03d}.bin'.format(i))
                if isinstance(source, bytes):
                    atomic_bytes(blob, source)
                else:
                    copy_verified(source, blob, entry['after'])
        plan = {'action': action, 'previous_state': state, 'next_state': next_state,
                'created_directories': created, 'operations': [e[0] for e in operations]}
        atomic_json(inside(work, 'plan.json'), plan)
        self.save_recovery()
        atomic_json(self.journal, {'schema': 'lm1-chs-portable-transaction-v1', 'id': ident,
                                   'plan_sha256': digest(work / 'plan.json')})
        try:
            for i, entry in enumerate(plan['operations']):
                self.apply_entry(work, entry, i, 'after')
                # TEST-BOUNDARY: portable-operation-complete
            for entry in plan['operations']:
                require(file_info(self.operation_path(entry)) == entry['after'], 'Transaction result changed: ' + entry['path'])
            if action == 'Install':
                self.installed(next_state)
            atomic_json(self.state_file, next_state)
            # TEST-BOUNDARY: portable-state-committed
            self.journal.unlink()
            sync_directory(self.state_dir)
        except Exception:
            self.rollback_pending()
            raise
        if action == 'Restore':
            for relative in sorted(state['created_directories'], key=len, reverse=True):
                path = inside(self.game, relative)
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()

    def install(self, manifest):
        before, after, index = chinese_config(self.game, self.config)
        state = self.prepare(manifest, self.state())
        if state['status'] == 'installed' and state['package_id'] == manifest['package_id'] and before == after:
            self.save_recovery()
            print('PASS: this package is already installed; startup language is chs (index {}).'.format(index))
            return
        if before is not None and not inside(self.state_dir, 'config-before-chs.ini').exists():
            atomic_bytes(inside(self.state_dir, 'config-before-chs.ini'), before)
        wanted = {r['path']: inside(self.package, r['payload']) for r in manifest['files']}
        new_paths = set(wanted)
        if state['status'] == 'installed':
            for row in state['files']:
                if row['path'] not in new_paths:
                    wanted[row['path']] = self.backup(row['path']) if row['path'] in RESOURCES else None
        created = set(state['created_directories']) | {d for d in DIRECTORIES if not inside(self.game, d).is_dir()}
        next_state = dict(state, status='installed', package_id=manifest['package_id'], files=manifest['files'], created_directories=sorted(created))
        self.transaction('Install', state, next_state, wanted, (before, after))
        print('PASS: installed {} {}. Startup language: chs (index {}).'.format(
            manifest.get('release_version', manifest['label']), manifest['variant'], index))
        print('Start La-Mulana from Steam with Proton. Keep .lamulana-zh for updates and restoration.')

    def restore(self):
        state = self.state()
        require(state is not None, 'No installation receipt; nothing to restore.')
        if state['status'] == 'restored':
            print('PASS: already restored.')
            return
        for row in state['files']:
            relative = row['path']
            allowed = [None, {k: row[k] for k in ('sha256', 'bytes')}]
            if relative == 'LaMulanaWin.exe' or relative in RESOURCES:
                allowed.append(file_info(self.backup(relative)))
            require(file_info(inside(self.game, relative)) in allowed,
                    'File changed after installation; preserve it before restoring: ' + relative)
        wanted = {r['path']: self.backup(r['path']) if r['path'] == 'LaMulanaWin.exe' or r['path'] in RESOURCES else None for r in state['files']}
        self.transaction('Restore', state, dict(state, status='restored'), wanted)
        print('PASS: original replaced files restored; owned CHS files removed. Save files were not accessed.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', help='game folder (optional when Steam is detected)')
    parser.add_argument('--action', choices=('Install', 'Check', 'Restore'), default='Install')
    parser.add_argument('--game-dir')
    parser.add_argument('--package-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--steam-root', action='append', type=Path, help='additional/explicit Steam root; may be repeated')
    parser.add_argument('--config-path', help='explicit Proton config.ini path')
    parser.add_argument('--list', action='store_true', help='list Steam app 230700 game directories as JSON')
    args = parser.parse_args(argv)
    libraries = steam_libraries(args.steam_root)
    candidates = game_candidates(libraries)
    if args.list:
        print(json.dumps([str(p) for p in candidates], ensure_ascii=False))
        return 0
    game = select_game(args.game_dir or args.directory, candidates)
    package = args.package_dir.resolve()
    config = select_config(game, libraries, args.config_path)
    installer = Installer(game, package, config)
    manifest = None
    if args.action != 'Restore':
        manifest = read_json(inside(package, 'manifest.json'))
        validate_manifest(manifest, package)
    with operation_lock(game):
        require(not inside(installer.state_dir, 'upgrade.json').exists(),
                'An interrupted Windows installation is present. Complete Install.cmd or Restore.cmd on Windows before transferring this game folder.')
        if installer.journal.exists():
            require(args.action != 'Check', 'An interrupted Linux operation is present. Run Install.sh or Restore.sh to recover.')
            check_game_process(game)
            installer.rollback_pending()
        if args.action != 'Restore':
            installer.mod_compatibility()
        if args.action == 'Check':
            state = installer.state()
            installer.baseline(manifest, state)
            if state:
                installer.installed(state)
            print('PASS: {} files and game baseline match.'.format('installed' if state and state['status'] == 'installed' else 'original'))
            return 0
        check_game_process(game)
        if args.action == 'Restore':
            installer.restore()
        else:
            require(config is not None, 'Proton prefix not found. ' + NATIVE_MESSAGE)
            installer.install(manifest)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, EOFError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
