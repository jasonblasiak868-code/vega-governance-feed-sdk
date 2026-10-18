# vega-governance-feed-sdk

![vega-governance-feed-sdk](assets/tile.svg)

Live governance feed: events read from custody chains as they grow, escape-stripped credential-scrubbed summaries, and alarms on broken, shortened or rewritten chains.

> **Licensing.** Source-available, not open source. Free for personal use; free for registered small businesses (under US$1M revenue and valuation); everyone else needs a commercial license (see LICENSE; for a commercial license write to jasonblasiak.ai.mail@gmail.com). Patent pending. Draft licence text, not yet reviewed by an attorney.

Package: `vega_feed` (src layout). Depends on: vega-custody-sdk.

## Modules

| Module | What it does |
|---|---|
| `feed` | Poll named chains; new events, and critical alarms for CHAIN_BROKEN, CHAIN_SHORTENED, CHAIN_REWRITTEN raised once per problem. |
| `display` | Safe-to-show text: escape sequences and control characters removed. |

## What it does NOT do (read this)

- It reads; it never writes to a chain or decides anything.
- A chain cut off entirely and replaced before the feed's first poll cannot be noticed: the feed needs its own earlier cursor, kept elsewhere.

## Status

See STATUS.md. Tests: 36 tests in 4 files, all passing.  See SECURITY.md for the threat model.

## Run the tests

Put `src` of this repo and of the repos it depends on on PYTHONPATH, then run each file in `tests/`.
