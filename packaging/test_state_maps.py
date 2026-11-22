"""Checks the country-publishing guard in state_maps.py without the source layers or the bucket.

  python3 -B packaging/test_state_maps.py

The build side is exercised with small SQLite files: one base-only set (what a US-only source snapshot yields for a
European country) and one with a row in every detailed layer. No network, no derived source, nothing written outside
the temporary folder.
"""
import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_state_maps():
    """state_maps.py imports r2_publish from the release folder, which is not part of this repository."""
    real = sys.modules.get('r2_publish')
    fake = types.ModuleType('r2_publish')
    fake.MULTIPART_OVER = fake.PART = 1
    fake.Context = object
    sys.modules['r2_publish'] = fake
    try:
        spec = importlib.util.spec_from_file_location('state_maps_under_test', HERE / 'state_maps.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if real is None:
            del sys.modules['r2_publish']
        else:
            sys.modules['r2_publish'] = real


SM = load_state_maps()


def make_set(root, detailed):
    geo = Path(root) / 'derived/geo'
    geo.mkdir(parents=True)

    def make(name, schema, rows=()):
        db = sqlite3.connect(geo / name)
        try:
            for sql in schema:
                db.execute(sql)
            for sql, values in rows:
                db.execute(sql, values)
            db.commit()
        finally:
            db.close()

    make('national.sqlite', ['CREATE TABLE feat(id INTEGER, minz INTEGER)', 'CREATE TABLE poi(id INTEGER)'],
         [('INSERT INTO feat(id, minz) VALUES(?, ?)', (1, 8))])
    make('water.sqlite', ['CREATE TABLE resource(id INTEGER)'])
    make('terrain.sqlite', ['CREATE TABLE tile(z INTEGER)'])
    make('buildings.sqlite', ['CREATE TABLE bldg(id INTEGER)'])
    make('crops.sqlite', ['CREATE TABLE resource(id INTEGER)'])
    make('places.sqlite', ['CREATE TABLE place(id INTEGER, source TEXT)'])
    if detailed:
        make('national.sqlite', ['CREATE TABLE IF NOT EXISTS feat(id INTEGER, minz INTEGER)', 'CREATE TABLE IF NOT EXISTS poi(id INTEGER)'],
             [('INSERT INTO feat(id, minz) VALUES(?, ?)', (2, 9)), ('INSERT INTO poi(id) VALUES(?)', (3,))])
        make('water.sqlite', ['CREATE TABLE IF NOT EXISTS resource(id INTEGER)'], [('INSERT INTO resource(id) VALUES(?)', (4,))])
        make('terrain.sqlite', ['CREATE TABLE IF NOT EXISTS tile(z INTEGER)'], [('INSERT INTO tile(z) VALUES(?)', (8,))])
        make('buildings.sqlite', ['CREATE TABLE IF NOT EXISTS bldg(id INTEGER)'], [('INSERT INTO bldg(id) VALUES(?)', (5,))])
        make('crops.sqlite', ['CREATE TABLE IF NOT EXISTS resource(id INTEGER)'], [('INSERT INTO resource(id) VALUES(?)', (6,))])
        make('places.sqlite', ['CREATE TABLE IF NOT EXISTS place(id INTEGER, source TEXT)'],
             [('INSERT INTO place(id, source) VALUES(?, ?)', (7, 'OpenStreetMap'))])


class CountryPublishing(unittest.TestCase):
    def setUp(self):
        self.old = SM.PUBLISHED_COUNTRIES
        self.old_states = SM.states

    def tearDown(self):
        SM.PUBLISHED_COUNTRIES = self.old
        SM.states = self.old_states

    def test_base_only_build_fails_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=False)
            self.assertEqual(set(SM.country_coverage(d)), set(SM.COVERAGE))

    def test_detail_in_every_layer_passes_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            self.assertEqual(SM.country_coverage(d), {})
            self.assertTrue(all(SM.coverage_counts(d).values()))

    def test_missing_layer_counts_as_no_detail(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            (Path(d) / 'derived/geo/buildings.sqlite').unlink()
            self.assertIn('buildings', SM.country_coverage(d))

    def test_country_must_be_opted_in_before_coverage_is_even_considered(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            SM.PUBLISHED_COUNTRIES = {}
            self.assertTrue(SM.country_publish_blockers(d, 'eu-se'))
            SM.PUBLISHED_COUNTRIES = {'eu-se': {}}
            self.assertEqual(SM.country_publish_blockers(d, 'eu-se'), [])

    def test_opted_in_but_base_only_country_is_still_refused(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=False)
            SM.PUBLISHED_COUNTRIES = {'eu-se': {}}
            blockers = SM.country_publish_blockers(d, 'eu-se')
            self.assertTrue(blockers)
            self.assertIn('no roads detail inside the country box', blockers)

    def test_regions_leave_countries_out_until_listed(self):
        SM.states = lambda: ['CA']
        SM.PUBLISHED_COUNTRIES = {}
        self.assertEqual(SM.regions(), ['CA'])
        SM.PUBLISHED_COUNTRIES = {'eu-se': {}}
        self.assertEqual(SM.regions(), ['CA', 'eu-se'])


if __name__ == '__main__':
    unittest.main()
