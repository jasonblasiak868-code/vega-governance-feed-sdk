# vega-governance-feed-sdk — Capabilities

Per-capability inventory: capability / why a policy-or-prompt-level approach structurally cannot provide it / where enforced in this repo's code / which test file demonstrates it / honest limit.

## 1. Tamper-evident chain verification on every poll
- **Why no policy/prompt can provide it:** A policy is a statement of intent; it does not execute. A model prompted to "check the chain" can be subverted, hallucinate, or skip the check. Only code that *must* run and *fails closed* when verification fails provides assurance.
- **Where enforced:** `feed.py` `Feed.poll()` — calls `vega_custody.dag.Chain(paths)` which verifies hash chain integrity and replica agreement; on `ChainBroken` or any read error, emits `CHAIN_BROKEN` alarm and freezes cursor.
- **Test:** `test_feed.py::Tamper::test_an_edited_entry_raises_one_critical_alarm_and_clears_when_repaired`, `redteam_1_tampering.py::A_Alterations` (10 tests covering edits, deletions, reordering, replica disagreement, garbage).
- **Honest limit:** A chain replaced entirely before the feed's first poll is invisible — the feed needs its own prior cursor. The state file is not encrypted; a compromised state file claiming a longer chain triggers `CHAIN_SHORTENED` alarm, but a state file matching a truncated chain would not be detected until next poll.

## 2. Chain shortening detection (truncation)
- **Why no policy/prompt can provide it:** A prompt cannot reliably count entries across restarts or detect that the newest entries were cut. Only persistent cursor state with fail-closed comparison detects shortening.
- **Where enforced:** `feed.py` `Feed.poll()` — compares `len(rows) < cursor["len"]`; on true, emits `CHAIN_SHORTENED` alarm, cursor frozen.
- **Test:** `test_feed.py::Tamper::test_cutting_off_the_newest_entries_is_noticed`, `redteam_1_tampering.py::A_Alterations::test_truncation_to_zero_and_to_one`, `test_deleting_every_replica`.
- **Honest limit:** If the chain is shortened *and* the state file is simultaneously corrupted to match the shortened length, the feed would not alarm. The state file integrity is not cryptographically bound to the chain.

## 3. History rewrite detection (replacement at same position)
- **Why no policy/prompt can provide it:** A model cannot cryptographically verify that the entry at position N today is the same entry that was at position N yesterday. Only stored head-hash comparison detects replacement.
- **Where enforced:** `feed.py` `Feed.poll()` — checks `rows[cursor["len"]-1].get("entry_hash") != cursor["head"]`; on mismatch, emits `CHAIN_REWRITTEN` alarm, cursor frozen.
- **Test:** `test_feed.py::Tamper::test_replacing_history_with_another_valid_chain_is_noticed`, `redteam_1_tampering.py::A_Alterations::test_a_longer_replacement_chain_is_not_mistaken_for_growth`, `test_a_fork_at_the_same_length_is_noticed`.
- **Honest limit:** A rewrite that preserves the head hash at the cursor position (collision or targeted) would not be detected. SHA256 collision resistance is assumed, not proven.

## 4. Alarm once per distinct problem (no spam, no silence)
- **Why no policy/prompt can provide it:** A model prompted to "alert once" can forget, double-alert, or be manipulated into silence. Only deterministic deduplication with persisted signature provides this guarantee.
- **Where enforced:** `feed.py` `Feed._alarm()` — computes `sig = SHA256(kind + detail)`; checks `self._alarmed.get(name) == sig`; only emits if new signature. Clears on verified chain (`self._alarmed.pop(name, None)`).
- **Test:** `redteam_1_tampering.py::A_Alterations::test_a_new_alarm_for_a_different_problem_is_announced_after_the_first`, `redteam_2_content.py::C_Subscribers::test_alarms_are_counted_once`.
- **Honest limit:** Two distinct problems with identical `(kind, detail)` strings would be deduplicated (unlikely but possible). Alarm detail includes dynamic data (e.g., entry count) reducing collision chance.

## 5. Cursor freeze during alarm (no silent skip)
- **Why no policy/prompt can provide it:** A prompt cannot guarantee that the cursor stops advancing while a problem exists. Only code structure that branches on alarm state and `continue`s before cursor advance provides this.
- **Where enforced:** `feed.py` `Feed.poll()` — each alarm branch (`CHAIN_BROKEN`, `CHAIN_SHORTENED`, `CHAIN_REWRITTEN`) ends with `continue`, skipping cursor advance and `_save()`. Cursor only advances after all checks pass and `self._alarmed.pop(name, None)`.
- **Test:** `redteam_1_tampering.py::A_Alterations::test_nothing_is_skipped_while_in_alarm` — verifies that after alarm clears and chain is repaired, the new entry is reported.
- **Honest limit:** If the process crashes mid-poll after alarm but before `_save()`, the in-memory cursor is lost; on restart, state file reloads (or starts from zero). This is the safe direction (re-reports).

## 6. Safe summaries: allow-listed fields, credential scrubbing, escape stripping, length clipping
- **Why no policy/prompt can provide it:** A model prompted to "scrub credentials" can miss patterns, be tricked by encoding, or leak nested structures. Only code with a fixed allow-list, credential detector, iterative escape peel, and hard clip provides structural assurance.
- **Where enforced:** `feed.py` `Feed.summarize()` → `Feed._clip()` + `display.plain()`. `SHOW` tuple (16 fields) is the only allow-list. `contains_credential` from custody detects credential shapes. `display.plain()` iteratively peels ANSI escapes until fixed point, then replaces control chars. Values clipped to 200 chars. Non-scalar values (dict, list) excluded.
- **Test:** `redteam_2_content.py::A_Content` — `test_only_allow_listed_fields_are_shown`, `test_long_values_are_cut_and_nested_values_are_not_shown`, `test_terminal_escape_sequences_in_a_value_cannot_reach_a_panel_unchanged`, `test_a_credential_shaped_value_is_masked_even_though_the_chain_stores_hashes_only`, `test_a_kind_named_like_an_alarm_is_still_just_its_own_severity`.
- **Honest limit:** `contains_credential` detects known patterns (API keys, tokens); novel credential formats may pass. Nested dicts/lists are excluded entirely (not serialized). The 200-char clip may truncate useful context. Escape stripping is regex-based; novel escape sequences may pass.

## 7. State persistence with safe restart semantics
- **Why no policy/prompt can provide it:** A model has no persistent memory across restarts. Only atomic disk writes with validation on read provide durable cursor state.
- **Where enforced:** `feed.py` `Feed.__init__` loads state; validates JSON structure, per-source `len` (int >= 0), `head` (str or null). On any error: `pass` — starts from zero (safe: re-reports). `Feed._save()` uses `vega_custody.safepaths.atomic_write`.
- **Test:** `redteam_1_tampering.py::B_State` — `test_a_missing_or_corrupt_state_file_starts_over_and_says_everything_again` (5 corruption variants), `test_a_state_file_claiming_more_than_the_chain_has_is_an_alarm_not_silence`, `test_a_state_file_with_the_wrong_head_is_an_alarm`.
- **Honest limit:** State file is plain JSON; no encryption, no MAC. An attacker with filesystem write access can forge a state file that claims a valid cursor for a compromised chain — but the chain verification at next poll will still detect the compromise.

## 8. Subscriber crash isolation (one bad callback ≠ feed stop)
- **Why no policy/prompt can provide it:** A model cannot structurally isolate callback failures. Only try/except around each subscriber call provides this.
- **Where enforced:** `feed.py` `Feed.poll()` delivery loop — `for fn in list(self._subs): try: fn(ev) except Exception: pass`. Counters updated *before* delivery so feed's own state stays correct even if subscriber mutates the event dict.
- **Test:** `test_feed.py::Basics::test_subscribers_get_events_and_one_crashing_does_not_stop_the_rest`, `redteam_2_content.py::C_Subscribers::test_a_subscriber_cannot_change_what_the_next_one_sees`, `test_counters_are_not_inflated_by_polling_again`.
- **Honest limit:** A subscriber that blocks indefinitely (deadlock, infinite loop) stalls the feed's delivery loop. No timeout or async delivery. Subscriber mutations affect the shared event dict (feed's counters are safe because computed first).

## 9. Configuration validation (deny-by-default construction)
- **Why no policy/prompt can provide it:** A model prompted to "validate config" can be social-engineered into accepting bad input. Only code that raises on invalid input before any operation provides this.
- **Where enforced:** `feed.py` `Feed.__init__` — validates `sources` is non-empty dict ≤64 entries, each name matches `_NAME` regex, each value is non-empty list of paths. Raises `FeedRefused` on any failure. `subscribe()` validates callable.
- **Test:** `redteam_2_content.py::B_Configuration::test_bad_sources_are_refused` (12 invalid variants), `test_a_subscriber_must_be_callable`.
- **Honest limit:** Path existence is *not* validated at construction (a source not yet written is valid). `MAX_SOURCES=64` is a hard constant, not configurable.

## 10. Non-existent source starts quiet, then works
- **Why no policy/prompt can provide it:** A model cannot guarantee idempotent handling of missing files across polls. Only code that checks `os.path.exists` and continues silently (if cursor.len==0) or alarms (if cursor.len>0) provides this.
- **Where enforced:** `feed.py` `Feed.poll()` — `if not any(os.path.exists(p) for p in paths): if cur["len"]: alarm(CHAIN_SHORTENED) else: continue`.
- **Test:** `redteam_2_content.py::B_Configuration::test_a_source_that_does_not_exist_yet_is_quiet_and_then_works`.
- **Honest limit:** If a source appears with a chain that has entries but the feed's cursor is at 0, the feed will read all entries as "new" (correct behavior, but may flood).

## 11. Real alarms distinguishable from alarm-named events
- **Why no policy/prompt can provide it:** A model cannot structurally distinguish a real alarm from an event whose `kind` happens to be `CHAIN_BROKEN`. Only code that sets `entry_hash: null` and `seq: null` on real alarms provides this.
- **Where enforced:** `feed.py` `Feed._alarm()` returns events with `"entry_hash": None, "seq": None`. Real chain entries always have both. `severity()` treats any `CHAIN_*` kind as critical, but the null fields distinguish.
- **Test:** `redteam_2_content.py::A_Content::test_a_kind_named_like_an_alarm_is_still_just_its_own_severity`, `test_real_alarms_never_carry_an_entry_hash`.
- **Honest limit:** An attacker who manually crafts a chain entry with `entry_hash: null` and `seq: null` could spoof an alarm structure — but the chain itself would reject such an entry (custody requires valid hashes).

## 12. Thread-safe operation
- **Why no policy/prompt can provide it:** A model has no concept of thread safety. Only `threading.Lock` around all mutable state provides this.
- **Where enforced:** `feed.py` `Feed.__init__` creates `self._lock = threading.Lock()`; `poll()` and `snapshot()` use `with self._lock:`.
- **Test:** No dedicated concurrency test; structural guarantee from code review.
- **Honest limit:** `snapshot()` holds lock during deep copy; `poll()` holds lock for entire verification + cursor update + `_save()`. Long chains may block subscribers. No read-write lock optimization.

---

## DKG + Lattice Integration

This SDK (layer 13 watch) does not directly import or consume the DKG lattice (layer 7 knowledge) or the predictive lattice (layer 11 reason, `vega-reasoning-sdk` predict.py / galaxy). Its role in the predictive loop is **upstream**:

1. **Records → Feed:** Custody chains (layer 0 record) grow as the governed system acts. The feed reads these chains in real time.
2. **Feed → Lessons:** The feed's alarms and event summaries are consumable by `vega-librarian-sdk` (layer 5 memory) for distillation into lessons.
3. **Lessons → DKG:** Librarian writes lessons to the DKG lattice (layer 7 knowledge) with origin and licence metadata.
4. **DKG → Reasoning:** The reasoning SDK (layer 11) queries the lattice for foresight (predict.py, galaxy).
5. **Reasoning → Harness:** Predicted paths are pre-registered in harness (layer 6 conduct).
6. **Harness → Metacog:** Metacog (layer 12 verify) gates completion on evidence.
7. **Metacog → Feed/Galaxy:** Results flow back to feed/galaxy (layer 13/14) for human visibility.
8. **Human decides:** The human operator sees the live feed, alarms, and lattice-informed foresight, then signs the next commitment.

This SDK publishes no direct DKG/lattice imports. It provides the **live observational layer** that feeds the loop. The wiring is: `vega_custody` (chain) → `vega_feed` (this SDK) → `vega_librarian` (lessons) → `vega_dkg_lattice` (graph) → `vega_reasoning` (predict) → `vega_harness` (predicted paths) → `vega_metacog` (evidence gate) → back to feed/galaxy.

---

## A category of its own

The governance feed is not a log viewer, a SIEM, or a dashboard widget. It is the **watch layer** of the organism:

- **Governance-first (authority outside the model):** The feed holds no authority; it only observes the custody chains that *are* the authority record. No model can suppress, alter, or fabricate what the feed reports without breaking the chain.
- **Deterministic verification (no model in the loop):** Chain verification, alarm logic, cursor management, and summary construction are pure code — no LLM, no prompt, no probabilistic check.
- **Pre-registered predicted paths (via family):** While this SDK does not register paths, the alarms it raises (CHAIN_BROKEN, etc.) are deterministic event kinds that upper layers (harness, metacog) can pre-register predicted responses for.
- **Single-use human commitments (via family):** The feed observes the *result* of commitments (entries on the chain). It does not verify commitments — that is jacket's job (layer 1). It verifies the chain that *records* them.
- **Chain-of-custody by default:** Every event the feed reports comes from a hash-chained, replica-agreed custody chain. The feed adds no new custody; it reads the existing one.
- **Lattice-informed foresight (via family):** The feed does not forecast. It provides the real-time ground truth (events + alarms) that the lattice reasons over. The foresight comes from reasoning/galaxy; the feed provides the observational anchor.

Every differentiation claim above describes what *this design does* — authority held outside the model, deterministic verification, chain-of-custody by default — not what competitors cannot do. The architectural argument that authority outside the model cannot be replicated by prompt-level policy follows from the white paper (section 1): a policy is a promise; a gate with a key the model never holds is a mechanism.