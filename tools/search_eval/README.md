# Library search test sets and scorer

A measuring tool, like the other scripts in `tools/`: it is not run by the unit tests. It scores what the library search
returns for a few thousand invented questions and messages, so a change to the search can be measured before and after.
It complements #241's tests, which check the guide search (`web/words.js`), and #302's emergency fallback.

The formulas, constants and how each number in the triage-based search proposal was measured are in
[docs/TRIAGE-SEARCH.md](../../docs/TRIAGE-SEARCH.md). `baseline-main.json` is the baseline recorded on `main`.

## What is here

| File | What it is |
|---|---|
| `data/patterns.json` | The pattern table: 157 regexes by key (`CPR`, `CHOKE`, `BLEED`, ...). A test case names keys; a page is useful if its title + excerpt matches one |
| `data/triage.json` | The triage set: 159 topics, 253 questions plus 109 typo versions (362). Red = act now, yellow = injury or illness without a danger sign, green = how-to; 22 counterexamples ("how to bleed the brakes") |
| `data/issue128.json` | #128's (and #126's) example questions, with its reviewer's counterexamples: 52 |
| `data/issue154.json` | Issue #154's 32 questions, each with a typo version, and #154's own topic regex |
| `data/issue241.json` | #241's 21 guide-search questions, scored here on the library's pages |
| `data/glued.json` | 48 messages typed with no spaces, keyboard mash, autocorrect slips, long real words |
| `data/conversations.json` | 52 conversations (follow-up, added danger, correction, new emergency, noise) |
| `lists/list1.jsonl` ... `list3.jsonl` | Three independent lists (690, 606, 531 messages), written by AI agents of one model family told not to open any project file, labelled red / yellow / green |
| `lists/list4.jsonl` | A fourth list (832 messages, 525 in Spanish) from Qwen3.5-9B, run locally |
| `score.py` | The scorer |

Each list's first line is a header: who wrote it, its size and colour counts, and for which fixes it is no longer blind.
The independent lists have no `need` patterns, so they measure urgency and pages shown, not which page comes first.

## How to run

From the repository root, with a library folder (a copy of a library pack; it is only read):

```
set LASTBOOK_DATA=<library folder>                  # export LASTBOOK_DATA=... on Linux and macOS
python -B tools/search_eval/score.py --mode keyword --out kw.json
python -B tools/search_eval/score.py --mode hybrid --out hy.json
```

- `--mode keyword` uses the library's own index only; `hybrid` adds meaning search (needs the pack's meaning model and index in `derived/`).
- `--search hybrid` (default) scores `assistant.hybrid(q, 8)`, what `/api/retrieve` and the chat's first search return; `--search find`
  scores the Library tab's search box (`server.find`), its first 8 documents.
- `--sets triage,lists` runs some sets only; `--rows` also writes every question's top 8; `--code <checkout>` measures another checkout.

Nothing is written into the library folder. A full keyword run takes a few minutes, hybrid about half an hour.

## What the measures mean

For the sets with patterns, on the first 8 results:

| Measure | Meaning |
|---|---|
| `useful_mean` | mean number of the 8 that match any of the question's needs |
| `first_ok` | questions whose first result matches the most urgent need (and, for a counterexample, is not about the emergency sense of the word) |
| `top3_ok` | questions with a useful page in the first 3 |
| `covered` | questions where every need appears somewhere in the 8 |
| `zero_useful` | questions with no useful page at all |
| `cap_broken` | questions where more than half the 8 match only the setting (the flood around the wire) and no need |
| `wrong_sense_first` | counterexamples whose first result is about the emergency sense ("bleed" in a first-aid book for "bleed the brakes") |
| `useful154` | #154's own count: pages of 8 matching each question's own topic regex, summed over its 32 questions |

Counts are reported for clean questions by colour, counterexamples and typo versions separately. Conversations are scored on the last
message; on `main` the chat searches that message alone.

For the independent lists, by colour (green also as counterexamples and mild lines; list 4 also by language):

| Measure | Meaning |
|---|---|
| `flagged_urgent` | lines the urgency check (`assistant.is_danger`) flags. `main` has none, so it is `n/a` until that module arrives |
| `pages_shown` | lines for which the chat would show pages. On `main` that is every line whose search finds something |
| `no_hits` | lines whose search finds nothing |

Red recall = red flagged / red lines; undertriage = 1 - red recall; overtriage = green flagged / green lines.
