#!/usr/bin/env python3
"""tools/search_eval/stats.py on made-up score.py rows: no library, no model.

  python3 -B -m unittest app.tests.test_search_eval_stats

Checks the interval and test formulas against values worked out by hand, and that questions are grouped and paired the
way score.py counts them.
"""
import json, random, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'search_eval'))
import stats  # noqa: E402


def row(i, colour='red', first=True, useful=5, counter=False, typo=False, q=None):
    return {'set': 'triage', 'id': f'{i:03d}', 'q': q or f'question {i}', 'colour': colour, 'counter': counter,
            'typo': typo, 'useful': useful, 'first_ok': first, 'top3_ok': first, 'covered': first,
            'cap_broken': False, 'wrong_sense_first': False, 'n_hits': 8}


class Formulas(unittest.TestCase):
    def test_wilson(self):
        lo, hi = stats.wilson(88, 131)       # worked by hand: 0.5875 to 0.7463
        self.assertAlmostEqual(lo, 0.5875, places=4)
        self.assertAlmostEqual(hi, 0.7463, places=4)
        lo, hi = stats.wilson(0, 5)          # no event in 5: from 0 up to about 43%
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.4345, places=4)
        lo, hi = stats.wilson(131, 131)
        self.assertEqual(hi, 1.0)
        self.assertGreater(lo, 0.97)

    def test_mcnemar_exact(self):
        self.assertAlmostEqual(stats.mcnemar_p(10, 2), 0.0386, places=4)   # 2 * P(X <= 2), X ~ Bin(12, 1/2)
        self.assertEqual(stats.mcnemar_p(0, 0), 1.0)
        self.assertEqual(stats.mcnemar_p(3, 3), 1.0)
        self.assertAlmostEqual(stats.mcnemar_p(5, 0), 0.0625, places=4)
        self.assertEqual(stats.mcnemar_p(1, 4), stats.mcnemar_p(4, 1))

    def test_bootstrap_is_fixed_by_seed(self):
        xs = [0, 1, 2, 3, 8, 8, 5, 4]
        a = stats.boot_mean(xs, random.Random(1))
        b = stats.boot_mean(xs, random.Random(1))
        self.assertEqual(a, b)
        self.assertLessEqual(a[0], sum(xs) / len(xs))
        self.assertGreaterEqual(a[1], sum(xs) / len(xs))
        self.assertEqual(stats.boot_mean([3, 3, 3], random.Random(1)), (3.0, 3.0))


class Grouping(unittest.TestCase):
    def test_counterexamples_and_typos_apart_as_in_score(self):
        rows = [row(0), row(1, 'green'), row(2, 'green', counter=True), row(3, typo=True)]
        g = stats.groups(rows)
        self.assertEqual(len(g['triage red']), 1)            # the typo version is not a clean red question
        self.assertEqual(len(g['triage green']), 1)          # the counterexample is not counted with its colour
        self.assertEqual(len(g['triage counterexamples']), 1)
        self.assertEqual(len(g['triage typos']), 1)
        self.assertEqual(len(g['triage clean']), 3)

    def test_lists_by_colour_with_language_for_list4(self):
        rows = [{'set': 'list4', 'id': 'list4.000', 'q': 'x', 'triage': 'red', 'lang': 'es', 'counter': False,
                 'flagged': True, 'pages_shown': True, 'n_hits': 3}]
        g = stats.groups(rows)
        self.assertIn('list4 red', g)
        self.assertIn('list4 red (es)', g)
        res = stats.one(rows, random.Random(1))
        self.assertEqual(res['list4 red']['flagged']['k'], 1)


class Paired(unittest.TestCase):
    def test_flips_counted_and_changed_text_left_out(self):
        before = [row(i, first=i < 5) for i in range(10)] + [row(10, q='old wording')]
        after = [row(i, first=i < 8) for i in range(10)] + [row(10, q='new wording')]
        res = stats.two(before, after, random.Random(1))
        self.assertEqual(res['_matched'], 10)
        self.assertEqual(res['_text_differs'], 1)
        f = res['triage red']['first_ok']
        self.assertEqual((f['before'], f['after'], f['no_to_yes'], f['yes_to_no']), (5, 8, 3, 0))
        self.assertAlmostEqual(f['p'], 0.25, places=6)
        self.assertEqual(res['triage red']['useful']['diff'], 0.0)

    def test_command_line_needs_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'summary-only.json'
            p.write_text(json.dumps({'summary': {}}), encoding='utf-8')
            r = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'search_eval' / 'stats.py'), str(p)],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('--rows', r.stderr)

    def test_command_line_two_runs(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.json', Path(d) / 'b.json'
            a.write_text(json.dumps({'rows': [row(i, first=i < 2) for i in range(6)]}), encoding='utf-8')
            b.write_text(json.dumps({'rows': [row(i, first=i < 4) for i in range(6)]}), encoding='utf-8')
            r = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'search_eval' / 'stats.py'), str(a), str(b)],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('first_ok 2->4 (+2/-0, p=0.5)', r.stdout)


if __name__ == '__main__':
    unittest.main()
