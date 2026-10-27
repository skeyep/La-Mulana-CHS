"""Portable installer regression tests; generated data, no game assets required."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('portable', Path(__file__).with_name('Patch.py'))
portable = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portable)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lm-chs-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.game = self.root / 'game 中文 space'
        self.game.mkdir()
        self.config = self.root / 'prefix/config.ini'
        self.config.parent.mkdir()
        self.before_config = b'\xef\xbb\xbf[System]\r\nLanguage=1\r\nVolume=25\r\nJoyJump=4\r\n'
        self.config.write_bytes(self.before_config)
        self.original_exe, self.pure_exe, self.full_exe = b'original executable fixture', b'pure executable fixture', b'full executable fixture'
        resources = {}
        for relative, (_, _, backup) in portable.RESOURCES.items():
            data = ('original:' + relative).encode()
            resources[relative] = (sha(data), len(data), backup)
        title_baselines = {p: sha(('original:' + p).encode()) for p in portable.TITLE_BASELINES}
        replacements = patch.multiple(portable, ORIGINAL=sha(self.original_exe), FOOTER=sha(self.pure_exe),
                                      ASSISTANT_PROFILES={sha(self.full_exe): sha(self.pure_exe)},
                                      RESOURCES=resources, TITLE_BASELINES=title_baselines)
        replacements.start()
        self.addCleanup(replacements.stop)
        baselines = []
        for relative in sorted(portable.BASELINES | set(title_baselines) | portable.SHARED):
            data = self.original_exe if relative == 'LaMulanaWin.exe' else ('original:' + relative).encode()
            target = self.game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            baselines.append({'path': relative, 'sha256': sha(data), 'bytes': len(data)})
        for name in ('en', 'ru', 'sp'):
            (self.game / 'data/language' / name).mkdir(exist_ok=True)
        (self.game / 'player.sav').write_bytes(b'player data sentinel')
        self.original = self.snapshot()
        self.pure, self.full = self.root / 'pure', self.root / 'full'
        for package, extra, exe in ((self.pure, set(), self.pure_exe), (self.full, portable.ASSISTANT, self.full_exe)):
            package.mkdir()
            (package / 'payload').mkdir()
            files = []
            for relative in sorted(portable.BASE_TARGETS | portable.TITLE_TARGETS | portable.SHARED | extra):
                data = exe if relative == 'LaMulanaWin.exe' else ('translated:' + relative).encode()
                payload = 'payload/' + sha(data) + '.bin'
                (package / payload).write_bytes(data)
                files.append({'path': relative, 'sha256': sha(data), 'bytes': len(data), 'payload': payload,
                              'operation': 'replace' if relative == 'LaMulanaWin.exe' or relative in resources else 'add'})
            manifest = {'schema': 'lm1-chs-offline-package-v1', 'app_id': 230700, 'label': 'test',
                        'release_version': 'test', 'installer_platform': 'linux-proton',
                        'variant': 'Full' if extra else 'Translation-Only', 'original_exe_sha256': sha(self.original_exe),
                        'package_id': sha(json.dumps(files).encode()), 'files': files, 'baseline_files': baselines}
            (package / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def snapshot(self, include_state=False):
        return {p.relative_to(self.game).as_posix(): p.read_bytes() for p in self.game.rglob('*')
                if p.is_file() and (include_state or '.lamulana-zh' not in p.relative_to(self.game).parts)}

    def run_action(self, action, package=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return portable.main(['--action', action, '--game-dir', str(self.game), '--package-dir', str(package or self.full),
                                  '--config-path', str(self.config), '--steam-root', str(self.root / 'no-steam')])

    def test_install_check_switch_restore(self):
        self.assertEqual(self.run_action('Check'), 0)
        self.assertEqual(self.snapshot(True), self.original)
        self.run_action('Install')
        self.assertEqual(self.config.read_bytes(), self.before_config.replace(b'Language=1', b'Language=2'))
        self.run_action('Check')
        installed = self.snapshot(True)
        self.run_action('Install')
        self.assertEqual(self.snapshot(True), installed)
        self.run_action('Install', self.pure)
        self.assertFalse((self.game / 'lm_assistant.dll').exists())
        self.run_action('Install')
        note = self.game / 'data/language/chs/note.txt'
        note.write_bytes(b'keep custom file')
        self.run_action('Restore', self.root / 'package-removed')
        expected = dict(self.original, **{'data/language/chs/note.txt': b'keep custom file'})
        self.assertEqual(self.snapshot(), expected)
        self.run_action('Restore')
        self.assertTrue((self.game / '.lamulana-zh/Restore.sh').is_file())

    def test_config_failure_restores_previous_variant(self):
        self.run_action('Install', self.pure)
        previous = self.snapshot()
        config = self.config.read_bytes()
        self.config.write_bytes(config.replace(b'Language=2', b'Language=1'))
        previous_config = self.config.read_bytes()
        apply = portable.Installer.apply_entry
        def failing(installer, work, entry, index, kind):
            apply(installer, work, entry, index, kind)
            if kind == 'after' and entry['scope'] == 'config':
                raise OSError('injected configuration-stage failure')
        with patch.object(portable.Installer, 'apply_entry', failing):
            with self.assertRaisesRegex(OSError, 'configuration-stage'):
                self.run_action('Install')
        self.assertEqual(self.snapshot(), previous)
        self.assertEqual(self.config.read_bytes(), previous_config)

    def test_interrupted_install_recovers_without_package(self):
        apply = portable.Installer.apply_entry
        def interrupted(installer, work, entry, index, kind):
            apply(installer, work, entry, index, kind)
            if index == 2 and kind == 'after':
                raise KeyboardInterrupt()
        with patch.object(portable.Installer, 'apply_entry', interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.run_action('Install')
        with self.assertRaisesRegex(ValueError, 'interrupted'):
            self.run_action('Check')
        self.run_action('Restore', self.root / 'missing-package')
        self.assertEqual(self.snapshot(), self.original)
        self.assertEqual(self.config.read_bytes(), self.before_config)

    def test_interrupted_restore_recovers(self):
        self.run_action('Install')
        apply = portable.Installer.apply_entry
        def interrupted(installer, work, entry, index, kind):
            apply(installer, work, entry, index, kind)
            if index == 2 and kind == 'after':
                raise KeyboardInterrupt()
        with patch.object(portable.Installer, 'apply_entry', interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.run_action('Restore')
        self.run_action('Restore')
        self.assertEqual(self.snapshot(), self.original)

    def test_modified_owned_file_stops_before_writes(self):
        self.run_action('Install')
        (self.game / 'lm_assistant.dll').write_bytes(b'user modification')
        before = self.snapshot(True)
        with self.assertRaises(ValueError):
            self.run_action('Restore')
        self.assertEqual(self.snapshot(True), before)

    def test_restore_accepts_missing_owned_file(self):
        self.run_action('Install')
        (self.game / 'lm_assistant.dll').unlink()
        self.run_action('Restore')
        self.assertEqual(self.snapshot(), self.original)

    def test_damaged_payload_stops_before_writes(self):
        manifest = json.loads((self.full / 'manifest.json').read_bytes())
        (self.full / manifest['files'][0]['payload']).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.run_action('Install')
        self.assertEqual(self.snapshot(True), self.original)

    def test_wrong_baseline_stops_before_writes(self):
        (self.game / 'LaMulanaWin.exe').write_bytes(b'unknown build')
        before = self.snapshot(True)
        with self.assertRaises(ValueError):
            self.run_action('Install')
        self.assertEqual(self.snapshot(True), before)

    def test_symlink_cannot_redirect_target(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.game / 'data/language/chs').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            self.run_action('Install')
        self.assertEqual(list(outside.iterdir()), [])

    def test_registered_sd_library_and_proton_config(self):
        steam, sd = self.root / 'Steam home', self.root / 'SD card'
        (steam / 'steamapps').mkdir(parents=True)
        game = sd / 'steamapps/common/La-Mulana'
        game.mkdir(parents=True)
        (steam / 'steamapps/libraryfolders.vdf').write_text('"libraryfolders" { "0" { "path" ' + json.dumps(str(steam)) + ' } "1" { "path" ' + json.dumps(str(sd)) + ' } }', encoding='utf-8')
        (sd / 'steamapps/appmanifest_230700.acf').write_text('"AppState" { "appid" "230700" "installdir" "La-Mulana" }', encoding='utf-8')
        documents = sd / 'steamapps/compatdata/230700/pfx/drive_c/users/steamuser/Documents/NIGORO/La-Mulana'
        documents.mkdir(parents=True)
        config = documents / 'config.ini'
        config.write_text('Language=1\n', encoding='utf-8')
        libraries = portable.steam_libraries([steam])
        self.assertEqual(libraries, [steam, sd])
        self.assertEqual(portable.game_candidates(libraries), [game])
        self.assertEqual(portable.select_config(game, libraries), config)
        self.assertEqual(portable.parse_vdf('"libraryfolders" { "1" "/run/media/deck/SD Card" }')['libraryfolders']['1'], '/run/media/deck/SD Card')

    def test_exclusive_operation_lock(self):
        with portable.operation_lock(self.game):
            with self.assertRaisesRegex(ValueError, 'Another patch operation'):
                with portable.operation_lock(self.game):
                    pass

    @unittest.skipUnless(sys.platform == 'linux', '/proc behavior requires Linux')
    def test_running_game_detection(self):
        process = subprocess.Popen([sys.executable, '-u', '-c', 'import time; print("ready"); time.sleep(30)', str(self.game / 'LaMulanaWin.exe')],
                                   cwd=self.game, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'ready')
            with self.assertRaisesRegex(ValueError, 'Close La-Mulana'):
                portable.check_game_process(self.game)
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
