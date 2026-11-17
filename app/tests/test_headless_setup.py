#!/usr/bin/env python3
"""packaging/docker/headless_setup.py stage: when it may reuse a library already in the target, and what it records.
Temporary folders and a stand-in for engine/setup's Setup only: nothing is downloaded.

  python3 -B app/tests/test_headless_setup.py [-v]

Never packaged."""
import argparse, hashlib, importlib.util, json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
os.environ['LASTBOOK_APP'] = str(ROOT)
_spec = importlib.util.spec_from_file_location('headless_setup', ROOT / 'packaging' / 'docker' / 'headless_setup.py')
hs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hs)

SMALL = {'id': 'small', 'title': 'Small', 'revision': 'r2', 'available': True,
         'files': [{'name': 'Lastbook-Small-r2.zip', 'size': 10, 'sha256': hashlib.sha256(b'small r2').hexdigest()}]}
ALL = {'id': 'all', 'title': 'All', 'available': True,
       'files': [{'name': 'Lastbook-All.zip', 'size': 10, 'sha256': hashlib.sha256(b'all, new release').hexdigest()}]}
OLD_ALL_FILES = [{'name': 'Lastbook-All.zip', 'size': 10, 'sha256': hashlib.sha256(b'all, old release').hexdigest()}]


def library(folder, name, revision=None, map_name=None, addresses=(), stamp_files=None):
    """A library as setup leaves one: catalog, pack.json, optionally a state map, address searches and our stamp."""
    (folder / 'library-data').mkdir(parents=True)
    (folder / 'library-data' / 'catalog.json').write_text('{}', encoding='utf-8')
    meta = {'name': name}
    if revision:
        meta['content_revision'] = revision
    (folder / 'pack.json').write_text(json.dumps(meta), encoding='utf-8')
    if map_name:
        (folder / 'map-set.json').write_text(json.dumps({'name': map_name, 'files': {}}), encoding='utf-8')
    for a in addresses:
        (folder / 'derived' / 'geo' / 'addresses').mkdir(parents=True, exist_ok=True)
        (folder / 'derived' / 'geo' / 'addresses' / f'{a}.sqlite').write_bytes(b'')
    if stamp_files is not None:
        (folder / hs.STAMP).write_text(json.dumps({'id': name, 'files': stamp_files, 'revision': revision or ''}), encoding='utf-8')
    return folder


def snapshot(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob('*')) if p.is_file()}


class FakeSetup:
    """engine/setup/api.Setup as stage uses it. start() records its call and builds the requested library in the target."""
    calls = []

    def __init__(self, mode, settings, parent, current=None, manifest=None):
        self.current = current
        self.manifest = mock.Mock()
        self.manifest.pack = lambda pid: {'small': SMALL, 'all': ALL}.get(pid)

    def current_info(self):
        return {'folder': str(self.current), 'pack': 'small', 'map': 'DC', 'address_indexes': ['DC']}

    def start(self, pack_id, folder=None, map_id=None, address_id=None):
        FakeSetup.calls.append({'pack': pack_id, 'folder': folder, 'map_id': map_id, 'address_id': address_id})
        p = {'small': SMALL, 'all': ALL}[pack_id]
        library(Path(folder) / 'LastbookData', pack_id, p.get('revision'), map_id, [address_id or map_id] if (address_id or map_id) else ())
        return {}


class Stage(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='lastbook-stage-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = library(self.tmp / 'LastbookData', 'small', 'r1', 'DC', ['DC'], stamp_files=[])
        (self.data / 'derived' / 'lan-key').write_text('the-key', encoding='utf-8')
        self.into = self.tmp / 'next'
        self.target = self.into / 'LastbookData'
        FakeSetup.calls = []
        for p in (mock.patch.object(hs, 'DATA', self.data), mock.patch.object(hs, 'SETTINGS', self.tmp / 'config'),
                  mock.patch.object(hs, 'manifest', lambda: None), mock.patch.object(hs.api, 'Setup', FakeSetup),
                  mock.patch.object(hs, 'run', lambda setup, start: start()),
                  mock.patch.object(hs.api, 'startup', lambda settings: (None, None)),
                  mock.patch.object(hs.api, 'opened', lambda *a: None), mock.patch.object(hs, 'log', lambda *a: None)):
            p.start()
            self.addCleanup(p.stop)

    def stage(self, pack, map_id=None):
        hs.cmd_stage(argparse.Namespace(into=str(self.into), pack=pack, map=map_id))

    def stamp(self):
        return json.loads((self.target / hs.STAMP).read_text(encoding='utf-8'))

    def refused(self, pack, words):
        before = snapshot(self.target)
        with self.assertRaises(SystemExit) as e:
            self.stage(pack)
        self.assertIn(words, str(e.exception))
        self.assertEqual(FakeSetup.calls, [], 'nothing may be downloaded over a library that is not the requested one')
        self.assertEqual(snapshot(self.target), before, 'the library there and its metadata stay as they were')

    def test_small_target_requested_as_all(self):
        library(self.target, 'small', 'r2', 'DC', ['DC'], stamp_files=SMALL['files'])
        self.refused('all', "holds the 'small' pack, not 'all'")

    def test_older_revision_requested_as_newer(self):
        library(self.target, 'small', 'r1', 'DC', ['DC'], stamp_files=[dict(SMALL['files'][0], sha256='0' * 64)])
        self.refused('small', "revision 'r1', not 'r2'")

    def test_older_release_of_a_pack_without_revisions(self):
        library(self.target, 'all', None, None, ['DC'], stamp_files=OLD_ALL_FILES)
        self.refused('all', 'records another release')

    def test_pack_without_revisions_and_no_stamp(self):
        library(self.target, 'all', None, None, ['DC'])
        self.refused('all', 'has no docker-pack.json')

    def test_matching_target_with_another_map(self):
        library(self.target, 'small', 'r2', 'TX', ['DC'])
        self.refused('small', "its map is 'TX', not 'DC'")

    def test_matching_target_is_reused(self):
        library(self.target, 'small', 'r2', 'DC', ['DC'])
        before = snapshot(self.target)
        self.stage('small')
        self.assertEqual(FakeSetup.calls, [])
        after = snapshot(self.target)
        self.assertEqual({k: v for k, v in after.items() if k not in (hs.STAMP, 'derived/lan-key')}, before, 'the library itself is untouched')
        self.assertEqual(self.stamp()['revision'], 'r2')
        self.assertEqual(self.stamp()['files'], SMALL['files'])
        self.assertEqual((self.target / 'derived' / 'lan-key').read_text(encoding='utf-8'), 'the-key')

    def test_matching_release_of_a_pack_without_revisions_is_reused(self):
        library(self.target, 'all', None, None, ['DC'], stamp_files=ALL['files'])
        stamp = (self.target / hs.STAMP).read_bytes()
        self.stage('all')
        self.assertEqual(FakeSetup.calls, [])
        self.assertEqual((self.target / hs.STAMP).read_bytes(), stamp, 'an existing matching stamp is not rewritten')

    def test_fresh_target_installs_with_map_address_search_and_key(self):
        self.stage('small')
        self.assertEqual(FakeSetup.calls, [{'pack': 'small', 'folder': str(self.into), 'map_id': 'DC', 'address_id': 'DC'}])
        self.assertEqual(self.stamp()['files'], SMALL['files'])
        self.assertEqual((self.target / 'derived' / 'lan-key').read_text(encoding='utf-8'), 'the-key')
        self.assertIsNone(hs.same_pack(self.target, SMALL, 'DC', 'DC'))

    def test_another_pack_brings_its_own_map(self):
        """Staging All from a Small library with a state map: All keeps its own maps; the address search still comes along."""
        self.stage('all')
        self.assertEqual(FakeSetup.calls, [{'pack': 'all', 'folder': str(self.into), 'map_id': None, 'address_id': 'DC'}])

    def test_status_after_reuse_follows_the_stamp(self):
        """The reported bug's end: after a swap, status must still see an update when the library is an older release."""
        library(self.target, 'all', None, None, ['DC'], stamp_files=OLD_ALL_FILES)
        with self.assertRaises(SystemExit):
            self.stage('all')
        self.assertEqual(json.loads((self.target / hs.STAMP).read_text(encoding='utf-8'))['files'], OLD_ALL_FILES)


if __name__ == '__main__':
    unittest.main()
