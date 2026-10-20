# vega-governance-feed-sdk — Specification

Spec v1.0 — 2026-10-19 — describes the published reference implementation as tested; where this document and the source disagree, the source wins.

## 1. Purpose and scope

This specification covers the `vega_feed` package (modules `feed` and `display`). It specifies the live governance feed: reading custody chains as they grow, producing credential-scrubbed summaries, and raising critical alarms on tamper (broken, shortened, rewritten chains). Out of scope: writing to chains, decision-making, authentication, encryption, UI panels, or any upper-layer SDK behavior (harness, reasoning, metacog, council, galaxy, umbrella).

## 2. Vocabulary

| Term | Definition |
|---|---|
| source | A named custody chain watched by the feed; configured as a list of replica file paths. |
| cursor | Per-source position: `(len, head_hash)` marking the last successfully read entry. |
| poll | One call to `Feed.poll()`: verifies all sources, returns new events + alarms, advances cursors for healthy sources. |
| alarm | A critical event emitted when a chain fails verification: `CHAIN_BROKEN`, `CHAIN_SHORTENED`, `CHAIN_REWRITTEN`. |
| summary | A dict derived from an entry's payload using the allow-list `SHOW`, with values escape-stripped, credential-scrubbed, clipped to 200 chars. |
| severity | Classification of an event kind: `critical` (chain alarms), `alert` (kinds containing `ALERT_WORDS`), `info` (all others). |
| state file | Optional JSON file persisting cursors across restarts; atomic write via `vega_custody.safepaths.atomic_write`. |
| subscriber | A callable registered via `Feed.subscribe(fn)`; receives each event dict after `poll()` returns. |

## 3. Components

### 3.1 `vega_feed.feed`

**Role** — The live feed: polls named custody chains, verifies integrity, emits new events and tamper alarms, persists cursors.

**Public interface** —
- `class FeedRefused(ValueError)` — raised on invalid construction or bad subscriber.
- `class Feed`
  - `__init__(sources: dict[str, list[path]], state_path: str | None = None)`
  - `subscribe(fn: Callable[[dict], None]) -> None`
  - `poll() -> list[dict]`
  - `snapshot() -> dict` — `{"cursor": {...}, "counters": {...}, "alarmed": [...]}`.
- `summarize(entry: dict) -> dict` — builds safe summary from allow-listed payload fields.
- `severity(kind: str) -> str` — returns `"critical"`, `"alert"`, or `"info"`.
- Module constants: `SHOW`, `ALERT_WORDS`, `MAX_SOURCES`, `_NAME` (name regex).

**Behavior** —
- Construction validates: non-empty sources dict, each name matches `_NAME`, each value is non-empty list of paths, total sources ≤ `MAX_SOURCES` (64). On failure: `FeedRefused`.
- Loads prior cursor from `state_path` if valid JSON with per-source `{"len": int, "head": str|null}`; corrupt/missing state → starts from zero (safe: re-reports).
- `poll()`: for each source, attempts `Chain(paths)` from `vega_custody.dag`.
  - On `ChainBroken` or unreadable: emits `CHAIN_BROKEN` alarm, cursor frozen.
  - If `len(rows) < cursor["len"]`: emits `CHAIN_SHORTENED`, cursor frozen.
  - If `cursor["len"] > 0` and `rows[cursor["len"]-1]["entry_hash"] != cursor["head"]`: emits `CHAIN_REWRITTEN`, cursor frozen.
  - On success: clears any prior alarm for that source; for each new entry, builds event dict with `source`, `seq`, `kind`, `severity`, `summary`, `entry_hash`; advances cursor; persists atomically.
- Alarms deduplicated by SHA256(kind + detail); same signature not re-emitted until cleared.
- `snapshot()` returns deep-copied cursor, counters, and sorted alarmed source names.
- Subscriber delivery: after `poll()` builds output list, each subscriber called in registration order; exceptions caught and ignored; feed's own counters updated before delivery.

**Invariants** —
- Cursor never advances while a source is in alarm.
- Each distinct alarm emitted at most once until the underlying problem clears.
- Summaries contain only fields from `SHOW`; values are plain text (no escapes, no control chars), credential-shaped values masked, clipped ≤200 chars.
- Alarms have `"severity": "critical"`, `"seq": null`, `"entry_hash": null`.
- Thread-safe: all mutating operations under `self._lock`.

### 3.2 `vega_feed.display`

**Role** — Sanitize text for safe display: remove ANSI escape sequences and control characters.

**Public interface** —
- `plain(text: str) -> str`

**Behavior** —
- Iteratively applies regex `_ESC` to peel escape sequences until no change (prevents re-formation via nested escapes).
- Then replaces any remaining control characters (C0, C1, and common Unicode format controls) with a single space.

**Invariants** —
- Output contains no ANSI escape sequences.
- Output contains no raw control characters (bytes 0x00–0x1F, 0x7F–0x9F, and listed Unicode format controls).

## 4. Guarantees and non-guarantees

### Guarantees

| Guarantee | Module | Demonstrated by |
|---|---|---|
| Chain integrity verified on every poll | `feed` | `test_feed.py::Tamper::test_an_edited_entry_raises_one_critical_alarm_and_clears_when_repaired` |
| Chain shortening detected | `feed` | `test_feed.py::Tamper::test_cutting_off_the_newest_entries_is_noticed` |
| History rewrite detected | `feed` | `test_feed.py::Tamper::test_replacing_history_with_another_valid_chain_is_noticed` |
| Each distinct alarm raised once until cleared | `feed` | `redteam_1_tampering.py::A_Alterations::test_a_new_alarm_for_a_different_problem_is_announced_after_the_first` |
| Cursor frozen during alarm; no events skipped | `feed` | `redteam_1_tampering.py::A_Alterations::test_nothing_is_skipped_while_in_alarm` |
| Summaries allow-listed, credential-scrubbed, escape-stripped, clipped | `feed` + `display` | `redteam_2_content.py::A_Content::test_only_allow_listed_fields_are_shown`, `test_long_values_are_cut_and_nested_values_are_not_shown`, `test_terminal_escape_sequences_in_a_value_cannot_reach_a_panel_unchanged`, `test_a_credential_shaped_value_is_masked_even_though_the_chain_stores_hashes_only` |
| State file corruption/absence → safe restart (re-reports) | `feed` | `redteam_1_tampering.py::B_State::test_a_missing_or_corrupt_state_file_starts_over_and_says_everything_again` |
| Subscriber crash isolation | `feed` | `test_feed.py::Basics::test_subscribers_get_events_and_one_crashing_does_not_stop_the_rest` |
| Counters not inflated by re-polling | `feed` | `redteam_2_content.py::C_Subscribers::test_counters_are_not_inflated_by_polling_again` |
| Alarms counted once | `feed` | `redteam_2_content.py::C_Subscribers::test_alarms_are_counted_once` |
| Constructor rejects invalid config | `feed` | `redteam_2_content.py::B_Configuration::test_bad_sources_are_refused` |
| Non-existent source starts quiet, then works | `feed` | `redteam_2_content.py::B_Configuration::test_a_source_that_does_not_exist_yet_is_quiet_and_then_works` |

### Non-guarantees

| Non-guarantee | Explanation |
|---|---|
| Pre-first-poll chain replacement detected | Feed has no prior cursor; a chain swapped before first poll is invisible. |
| State file confidentiality | State file is JSON; no encryption. Integrity relies on chain verification at next poll. |
| Real-time delivery | Poll interval is caller-controlled; no push from chain to feed. |
| Subscriber ordering guarantees | Subscribers called sequentially; a slow subscriber delays subsequent ones. |
| Cross-source transactionality | Each source verified independently; no atomic multi-source snapshot. |

## 5. Failure modes

| Failure mode | What happens | Test reference |
|---|---|---|
| Entry edited (any position) | `CHAIN_BROKEN` alarm; cursor frozen; clears on repair | `redteam_1_tampering.py::A_Alterations::test_editing_the_oldest_entry`, `test_editing_the_newest_entry` |
| Entry deleted from middle | `CHAIN_BROKEN` alarm | `redteam_1_tampering.py::A_Alterations::test_deleting_an_entry_from_the_middle` |
| Entries reordered | `CHAIN_BROKEN` alarm | `redteam_1_tampering.py::A_Alterations::test_reordering_entries` |
| One replica changed alone | `CHAIN_BROKEN` alarm (replica disagreement) | `redteam_1_tampering.py::A_Alterations::test_one_replica_changed_alone` |
| Garbage/binary in chain file | `CHAIN_BROKEN` alarm | `redteam_1_tampering.py::A_Alterations::test_garbage_and_binary_junk_in_the_file` |
| Chain truncated to zero/one entries | `CHAIN_SHORTENED` alarm | `redteam_1_tampering.py::A_Alterations::test_truncation_to_zero_and_to_one` |
| All replicas deleted | `CHAIN_SHORTENED` alarm | `redteam_1_tampering.py::A_Alterations::test_deleting_every_replica` |
| Replaced with longer valid chain | `CHAIN_REWRITTEN` alarm (not mistaken for growth) | `redteam_1_tampering.py::A_Alterations::test_a_longer_replacement_chain_is_not_mistaken_for_growth` |
| Replaced with fork at same length | `CHAIN_REWRITTEN` alarm | `redteam_1_tampering.py::A_Alterations::test_a_fork_at_the_same_length_is_noticed` |
| State file claims more entries than chain has | `CHAIN_SHORTENED` alarm (not silence) | `redteam_1_tampering.py::B_State::test_a_state_file_claiming_more_than_the_chain_has_is_an_alarm_not_silence` |
| State file has wrong head hash | `CHAIN_REWRITTEN` alarm | `redteam_1_tampering.py::B_State::test_a_state_file_with_the_wrong_head_is_an_alarm` |
| Hostile event content (non-allow-listed fields, long values, escapes, credential shapes) | Stripped/masked/clipped in summary; full entry stays on chain | `redteam_2_content.py::A_Content` (all 5 tests) |
| Event kind named like alarm (e.g., `CHAIN_BROKEN`) | Treated as critical severity but carries `entry_hash` and `seq` (distinguishes from real alarm) | `redteam_2_content.py::A_Content::test_a_kind_named_like_an_alarm_is_still_just_its_own_severity` |
| Real alarms never carry `entry_hash` or `seq` | Alarms have `entry_hash: null`, `seq: null` | `redteam_2_content.py::A_Content::test_real_alarms_never_carry_an_entry_hash` |
| Invalid constructor args | `FeedRefused` raised | `redteam_2_content.py::B_Configuration::test_bad_sources_are_refused` |
| Non-callable subscriber | `FeedRefused` raised | `redteam_2_content.py::B_Configuration::test_a_subscriber_must_be_callable` |
| Subscriber mutates event dict | Feed's own counters (computed before delivery) stay correct | `redteam_2_content.py::C_Subscribers::test_a_subscriber_cannot_change_what_the_next_one_sees` |

## 6. Dependencies and layer rules

**Registry entry (verbatim from ORGANISM_MAP.md):**
```
vega-governance-feed-sdk | 13 watch | custody
```

**Layer rule:** Dependencies point down layers only, never up or sideways. This SDK imports only `vega_custody` (layer 0). It does not import harness, reasoning, metacog, trace, terminal, train, dkg-lattice, librarian, pareah, two-gate, superproof, jacket, council, galaxy, or umbrella.

## 7. Conformance

A third party can verify conformance by:
1. Installing `vega-custody-sdk` and this SDK.
2. Running all test files in `tests/` (36 tests across 4 files).
3. All tests passing means: the feed verifies chain integrity, detects the three tamper classes, emits alarms once per problem, freezes cursors during alarms, produces safe summaries, persists/restores cursors safely, isolates subscriber crashes, and rejects invalid configuration.

**What passing does NOT mean:** Production readiness; independent security review; cryptographic expert review; resistance to side-channel or timing attacks; suitability for high-assurance deployments without further hardening.
