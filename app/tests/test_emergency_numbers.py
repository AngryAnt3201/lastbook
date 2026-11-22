#!/usr/bin/env python3
"""content/emergency/<CC>.json: every number names its source and the day it was checked (format: content/emergency/SCHEMA.md).

  python3 -B -m unittest app.tests.test_emergency_numbers

Two parts: the real files are checked, and the checker itself is shown to fail on a row with no source, no date or a
number that is not a number, so a passing run means something.
"""
import copy, json, re, sys, unittest
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
DIR = Path(__file__).resolve().parents[2] / 'content' / 'emergency'

KINDS = {'general', 'ambulance', 'fire', 'police', 'poison', 'crisis', 'other'}
HOW = {'call', 'sms', 'chat', 'app'}
WORKS_FROM = {'mobile', 'landline', 'voip'}
VERIFIED = {'official', 'found_online'}
NUMBER = re.compile(r'^[+*]?[0-9][0-9 ]*$')
CALLING_CODE = re.compile(r'^\+[0-9]{1,4}$')
SOURCE = re.compile(r'^https?://[^\s/]+\.[^\s/]+\S*$')


def words(x):
    return isinstance(x, list) and bool(x) and all(isinstance(w, str) and w.strip() and w == w.lower() for w in x)


def problems(data, name, today=None):
    """What is wrong with one country's table, as a list of plain lines. Empty when it is sound."""
    today = today or date.today()
    out = []
    code = name[:-5] if name.endswith('.json') else name
    if not re.fullmatch(r'[A-Z]{2}', code):
        out.append(f'{name}: the file name must be the two-letter country code in capitals, such as CL.json')
    if data.get('code') != code:
        out.append(f'{name}: "code" is {data.get("code")!r}, but the file name says {code!r}')
    if not isinstance(data.get('country'), str) or not data['country'].strip():
        out.append(f'{name}: "country" is missing')
    if not CALLING_CODE.match(str(data.get('calling_code', ''))):
        out.append(f'{name}: "calling_code" must be + and digits, such as +56')
    services = data.get('services')
    if not isinstance(services, list) or not services:
        return out + [f'{name}: "services" must list at least one number']
    numbers = set()
    for i, s in enumerate(services):
        who = f'{name} services[{i}] ({s.get("name", "?") if isinstance(s, dict) else "?"})'
        if not isinstance(s, dict):
            out.append(f'{who}: not an object')
            continue
        if s.get('kind') not in KINDS:
            out.append(f'{who}: "kind" {s.get("kind")!r} is not one of {sorted(KINDS)}')
        if not isinstance(s.get('name'), str) or not s['name'].strip():
            out.append(f'{who}: "name" is missing')
        n = s.get('number')
        if not isinstance(n, str) or not NUMBER.match(n):
            out.append(f'{who}: "number" must be digits and spaces only (a leading + or * is allowed): {n!r}')
        else:
            numbers.add(n)
        v = s.get('how')
        if not isinstance(v, list) or not v or not set(v) <= HOW:
            out.append(f'{who}: "how" must be a non-empty list from {sorted(HOW)}')
        v = s.get('works_from')   # empty: the source does not say
        if not isinstance(v, list) or not set(v) <= WORKS_FROM:
            out.append(f'{who}: "works_from" must be a list from {sorted(WORKS_FROM)}, empty if the source does not say')
        k = s.get('keywords')
        if not isinstance(k, dict) or not words(k.get('local')) or not words(k.get('en')):
            out.append(f'{who}: "keywords" needs lower-case "local" and "en" word lists')
        if not isinstance(s.get('when'), str):
            out.append(f'{who}: "when" must be a string (empty if there is nothing to add)')
        if not isinstance(s.get('source'), str) or not SOURCE.match(s['source']):
            out.append(f'{who}: "source" must be the web address of the page the number was read from')
        c = s.get('checked_on')
        try:
            d = date.fromisoformat(c)
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', c):
                raise ValueError
            if d > today:
                out.append(f'{who}: "checked_on" {c} is in the future')
        except (TypeError, ValueError):
            out.append(f'{who}: "checked_on" must be a date as YYYY-MM-DD')
        if s.get('verified') not in VERIFIED:
            out.append(f'{who}: "verified" must be one of {sorted(VERIFIED)}')
    g = data.get('general')
    if g is not None and g not in numbers:
        out.append(f'{name}: "general" is {g!r}, which is not the number of any service')
    return out


class Files(unittest.TestCase):
    def test_every_file_is_sound(self):
        files = sorted(DIR.glob('*.json'))
        self.assertTrue(files, 'no country files in content/emergency/')
        for f in files:
            with self.subTest(f.name):
                data = json.loads(f.read_text(encoding='utf-8'))
                self.assertEqual(problems(data, f.name), [])


class Checker(unittest.TestCase):
    GOOD = {
        'country': 'Springfield', 'code': 'ZZ', 'calling_code': '+99', 'general': '911',
        'services': [{
            'kind': 'general', 'name': 'Emergency', 'number': '911', 'how': ['call'],
            'works_from': ['mobile', 'landline'], 'keywords': {'local': ['emergencia'], 'en': ['emergency']},
            'when': '', 'source': 'https://example.org/numbers', 'checked_on': '2026-11-01', 'verified': 'official'}],
    }

    def bad(self, **change):
        d = copy.deepcopy(self.GOOD)
        for k, v in change.items():
            if k.startswith('s_'):
                d['services'][0][k[2:]] = v
            else:
                d[k] = v
        return problems(d, 'ZZ.json', today=date(2026, 11, 21))

    def test_a_sound_table_passes(self):
        self.assertEqual(problems(self.GOOD, 'ZZ.json', today=date(2026, 11, 21)), [])

    def test_no_source_fails(self):
        self.assertTrue(self.bad(s_source=''))
        self.assertTrue(self.bad(s_source='not an address'))
        d = copy.deepcopy(self.GOOD)
        del d['services'][0]['source']
        self.assertTrue(problems(d, 'ZZ.json'))

    def test_no_date_fails(self):
        d = copy.deepcopy(self.GOOD)
        del d['services'][0]['checked_on']
        self.assertTrue(problems(d, 'ZZ.json'))
        self.assertTrue(self.bad(s_checked_on='yesterday'))
        self.assertTrue(self.bad(s_checked_on='2026-13-01'))
        self.assertTrue(self.bad(s_checked_on='20261101'))

    def test_a_date_in_the_future_fails(self):
        self.assertTrue(self.bad(s_checked_on='2026-12-01'))

    def test_a_number_that_is_not_a_number_fails(self):
        for n in ('', 'call 911', '9-1-1', '911.', None, 911):
            with self.subTest(n):
                self.assertTrue(self.bad(s_number=n))
        self.assertFalse(self.bad(s_number='+56 2 2635 3800', general=None))
        self.assertFalse(self.bad(s_number='*4141', general=None))

    def test_unknown_words_fail(self):
        self.assertTrue(self.bad(s_kind='hospital'))
        self.assertTrue(self.bad(s_verified='probably'))
        self.assertTrue(self.bad(s_how=['pigeon']))
        self.assertTrue(self.bad(s_works_from=['telepathy']))
        self.assertTrue(self.bad(s_how=[]))
        self.assertFalse(self.bad(s_works_from=[]))

    def test_the_file_name_must_match_the_code(self):
        self.assertTrue(problems(self.GOOD, 'zz.json', today=date(2026, 11, 21)))
        self.assertTrue(problems(self.GOOD, 'YY.json', today=date(2026, 11, 21)))

    def test_general_must_be_a_listed_number(self):
        self.assertTrue(self.bad(general='112'))

    def test_keywords_need_both_languages_in_lower_case(self):
        self.assertTrue(self.bad(s_keywords={'local': ['Emergencia'], 'en': ['emergency']}))
        self.assertTrue(self.bad(s_keywords={'local': ['emergencia']}))


if __name__ == '__main__':
    unittest.main()
