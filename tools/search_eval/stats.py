"""Confidence intervals and paired before/after tests for score.py outputs written with --rows.

    python -B tools/search_eval/stats.py kw.json                  # one run: every rate with its 95% interval
    python -B tools/search_eval/stats.py before.json after.json   # two runs on the same questions: what changed
    options: --md (markdown tables)  --json FILE (write the numbers)  --seed N (bootstrap seed, default 1)

One run. For each group of questions (a set, split by colour, typo version, counterexample, conversation kind, list
colour), each yes/no measure gets its count, rate and a Wilson 95% interval; "useful of 8" gets its mean and a
percentile bootstrap 95% interval (2,000 resamples of the questions, fixed seed, so the output is the same every run).

Two runs. Questions are matched by set and id (a question whose text differs between the runs is left out and
counted). For a yes/no measure: how many went no -> yes and yes -> no, and the exact McNemar p (two-sided binomial
on those discordant questions only; questions that did not change carry no information about the change). For
"useful of 8": the mean paired difference with a paired bootstrap 95% interval.

How to read it: a group of 5 questions gives an interval about 60 points wide; report it as "3 of 5", not 60%.
The p-values are not corrected for the many groups and measures: treat one measure, fixed beforehand (red questions'
first useful page, or red recall of the urgency check), as the main result and the rest as descriptive.
Standard library only.
"""
import argparse
import json
import math
import random
import sys

BINARY = ('first_ok', 'top3_ok', 'covered', 'zero_useful', 'cap_broken', 'wrong_sense_first')
LIST_BINARY = ('pages_shown', 'flagged', 'no_hits')
Z = 1.959963984540054
B = 2000


def wilson(k, n):
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_p(b, c):
    """Exact two-sided McNemar: binomial(b + c, 1/2), probability of a split at least this uneven."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def boot_mean(xs, rng):
    n = len(xs)
    if n == 0:
        return (float('nan'), float('nan'))
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return (means[int(0.025 * B)], means[int(0.975 * B) - 1])


def value(r, m):
    if m == 'zero_useful':
        return r.get('useful') == 0 if 'useful' in r else None
    if m == 'no_hits':
        return r.get('n_hits') == 0
    v = r.get(m)
    return None if v is None else bool(v)


def groups(rows):
    """(name, rows) for every group reported; a row can be in several groups."""
    out = {}

    def add(name, r):
        out.setdefault(name, []).append(r)
    for r in rows:
        s = r['set']
        if s.startswith('list'):
            add(f'{s} {r["triage"]}', r)
            if r['triage'] == 'green' and r.get('counter'):
                add(f'{s} green counterexamples', r)
            if s == 'list4':
                add(f'{s} {r["triage"]} ({r.get("lang", "en")[:2]})', r)
            continue
        if s == 'glued':
            if 'useful' in r:
                add(f'glued {r["kind"]}', r)
            continue
        if s == 'conversations':
            add('conversations all', r)
            add(f'conversations {r["kind"]}', r)
            continue
        if r.get('typo'):
            add(f'{s} typos', r)
            continue
        add(f'{s} clean', r)
        if r.get('counter'):          # as score.py's by_colour: counterexamples apart, not in their colour
            add(f'{s} counterexamples', r)
        elif r.get('colour'):
            add(f'{s} {r["colour"]}', r)
    return out


def measures(rs):
    if rs and rs[0]['set'].startswith('list'):
        return [m for m in LIST_BINARY if any(r.get(m) is not None for r in rs) or m == 'no_hits'], False
    return list(BINARY), True


def pct(x):
    return 'nan' if x != x else f'{100 * x:.0f}'


def one(rows, rng):
    res = {}
    for name, rs in sorted(groups(rows).items()):
        ms, has_useful = measures(rs)
        g = {'n': len(rs)}
        for m in ms:
            vals = [value(r, m) for r in rs]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            k = sum(vals)
            lo, hi = wilson(k, len(vals))
            g[m] = {'k': k, 'n': len(vals), 'rate': k / len(vals), 'ci': [lo, hi]}
        if has_useful:
            u = [r['useful'] for r in rs]
            g['useful'] = {'mean': sum(u) / len(u), 'ci': list(boot_mean(u, rng))}
        res[name] = g
    return res


def two(before, after, rng):
    a = {(r['set'], r['id']): r for r in before}
    b = {(r['set'], r['id']): r for r in after}
    keys = [k for k in a if k in b]
    differ = [k for k in keys if a[k].get('q') != b[k].get('q')]
    keys = [k for k in keys if k not in set(differ)]
    pairs = [(a[k], b[k]) for k in keys]
    res = {'_matched': len(keys), '_text_differs': len(differ), '_only_before': len(set(a) - set(b)),
           '_only_after': len(set(b) - set(a))}
    by = groups([p[1] for p in pairs])
    lookup = {id(p[1]): p for p in pairs}
    for name, rs in sorted(by.items()):
        ps = [lookup[id(r)] for r in rs]
        ms, has_useful = measures(rs)
        g = {'n': len(ps)}
        for m in ms:
            vv = [(value(x, m), value(y, m)) for x, y in ps]
            vv = [(x, y) for x, y in vv if x is not None and y is not None]
            if not vv:
                continue
            up = sum(1 for x, y in vv if not x and y)
            down = sum(1 for x, y in vv if x and not y)
            g[m] = {'before': sum(x for x, _ in vv), 'after': sum(y for _, y in vv), 'n': len(vv),
                    'no_to_yes': up, 'yes_to_no': down, 'p': mcnemar_p(up, down)}
        if has_useful:
            d = [y['useful'] - x['useful'] for x, y in ps]
            g['useful'] = {'before': sum(x['useful'] for x, _ in ps) / len(ps),
                           'after': sum(y['useful'] for _, y in ps) / len(ps),
                           'diff': sum(d) / len(d), 'ci': list(boot_mean(d, rng))}
        res[name] = g
    return res


def show_one(res, md):
    sep = ' | ' if md else '  '
    for name, g in res.items():
        cells = [f'{name} (n={g["n"]})']
        if 'useful' in g:
            u = g['useful']
            cells.append(f'useful {u["mean"]:.2f} [{u["ci"][0]:.2f}-{u["ci"][1]:.2f}]')
        for m, v in g.items():
            if isinstance(v, dict) and 'k' in v:
                cells.append(f'{m} {v["k"]}/{v["n"]} {pct(v["rate"])}% [{pct(v["ci"][0])}-{pct(v["ci"][1])}]')
        print(('| ' if md else '') + sep.join(cells) + (' |' if md else ''))


def show_two(res, md, alpha=0.05):
    print(f'matched {res["_matched"]} questions; text differs {res["_text_differs"]}, only before '
          f'{res["_only_before"]}, only after {res["_only_after"]} (left out)')
    sep = ' | ' if md else '  '
    for name, g in res.items():
        if name.startswith('_'):
            continue
        cells = [f'{name} (n={g["n"]})']
        if 'useful' in g:
            u = g['useful']
            cells.append(f'useful {u["before"]:.2f}->{u["after"]:.2f} diff {u["diff"]:+.2f} '
                         f'[{u["ci"][0]:+.2f} to {u["ci"][1]:+.2f}]')
        for m, v in g.items():
            if isinstance(v, dict) and 'no_to_yes' in v:
                mark = ' *' if v['p'] < alpha else ''
                cells.append(f'{m} {v["before"]}->{v["after"]} (+{v["no_to_yes"]}/-{v["yes_to_no"]}, p={v["p"]:.3g}){mark}')
        print(('| ' if md else '') + sep.join(cells) + (' |' if md else ''))
    print('* p < 0.05, exact McNemar, uncorrected for the number of groups and measures')


def load(path):
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    if 'rows' not in d:
        sys.exit(f'{path}: no per-question rows; run score.py with --rows')
    return d['rows']


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('runs', nargs='+', help='one or two score.py outputs written with --rows')
    ap.add_argument('--md', action='store_true')
    ap.add_argument('--json')
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    if len(a.runs) > 2:
        ap.error('one or two runs')
    rng = random.Random(a.seed)
    if len(a.runs) == 1:
        res = one(load(a.runs[0]), rng)
        show_one(res, a.md)
    else:
        res = two(load(a.runs[0]), load(a.runs[1]), rng)
        show_two(res, a.md)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=1)


if __name__ == '__main__':
    main()
