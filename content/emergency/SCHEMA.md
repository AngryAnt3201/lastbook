# Emergency numbers (`content/emergency/<CC>.json`)

One file per country, named with the country's ISO 3166-1 alpha-2 code in capitals (`CL.json`). The table is read like
the guides: offline, no network. A wrong number in an emergency is worse than none, so every number carries where it
came from and when someone last checked it, and `app/tests/test_emergency_numbers.py` fails when one does not.

This folder holds the data and its format only. Nothing in the app reads it yet: choosing the country, the picker and
what to show when the country is unknown are still being discussed in the issue.

```json
{
  "country": "Chile",
  "code": "CL",
  "calling_code": "+56",
  "general": null,
  "services": [
    {
      "kind": "ambulance",
      "name": "SAMU",
      "number": "131",
      "how": ["call"],
      "works_from": ["mobile", "landline"],
      "keywords": {"local": ["ambulancia", "samu"], "en": ["ambulance"]},
      "when": "Free-text note: when to use this number, or where it applies.",
      "source": "https://example.gov/page",
      "checked_on": "2026-11-21",
      "verified": "official"
    }
  ]
}
```

## Country fields

| Field | Meaning |
| --- | --- |
| `country` | The country's name in English. |
| `code` | ISO 3166-1 alpha-2, capitals. Must match the file name. |
| `calling_code` | The country calling code, `+` and digits. |
| `general` | The `number` of the service that answers any emergency, or `null` when the country has none. It must match a `number` in `services`. |
| `services` | The list of numbers, most reliable first. At least one. |

## Service fields

| Field | Meaning |
| --- | --- |
| `kind` | `general`, `ambulance`, `fire`, `police`, `poison`, `crisis` (suicide and mental-health crisis lines) or `other`. |
| `name` | What the service is called locally (`SAMU`, `Bomberos`). |
| `number` | Digits, spaces, and a leading `+` or `*` only, as it is dialled. |
| `how` | One or more of `call`, `sms`, `chat`, `app`. |
| `works_from` | Any of `mobile`, `landline`, `voip`. List only what a source says; empty when the source does not say. |
| `keywords` | `{"local": [...], "en": [...]}`: words a person might type to find this service, in the local language and in English ("bomberos" / "fire"). Lower case. |
| `when` | A free-text note, in English: when this number is the right one, where it applies, whether it is free. Empty string if there is nothing to add. |
| `source` | The web address of the page the number was read from. A country's own government or the service's own page. |
| `checked_on` | `YYYY-MM-DD`, the day someone read the number on that page. Not in the future. |
| `verified` | `official`: seen on an official page. `found_online`: only found elsewhere. The app labels `found_online` numbers as unverified. |

A service whose `source` could not be reached is not added. A number nobody can source stays out of the table.

## Showing it (not part of this change)

The agreed idea: an urgent guide or answer shows two numbers, the one for this emergency plus the most reliable
fallback, with "See all numbers" for the rest; a calm question ("what's the police number in Chile?") shows the full
list. That is why `services` is ordered and why `verified` exists.
