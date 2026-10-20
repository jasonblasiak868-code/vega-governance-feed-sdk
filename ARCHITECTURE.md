# vega-governance-feed-sdk — Architecture

## 1. The organism (family picture)

```
                 ┌──────────────────────────┐
                 │   THE HUMAN (the owner)  │  holds the only signing key;
                 │  authority starts here   │  spends it one action at a time
                 └────────────┬─────────────┘
                              v single-use signed commitments
 15 assemble   vega-umbrella-sdk        the family as one organism: one keyed
                                        ledger, one approval check, one anchor,
                                        registry + pre-deploy audit
 14 deliberate vega-council-sdk         multi-brain deliberation, design-first builder
               vega-galaxy-sdk          the galaxy view of the knowledge lattice:
                                        levels, convergence, futures above the present
 13 watch      >>> vega-governance-feed-sdk <<<  live view of every chain + tamper alarms
 12 verify     vega-metacog-sdk          evidence rungs and the completion gate
 11 reason     vega-reasoning-sdk        fidelity, forecasting, routing: the lattice
                                        that predicts steps ahead
 10 observe    vega-trace-sdk            telemetry of reasoning: layer traces, entropy,
                                        harmonic echo, reference signature
  9 interface  vega-terminal-sdk         gated command execution for people and agents
  8 learn      vega-train-sdk            governed training + freeze cards: records
                                        exactly what a model learned from
  7 knowledge  vega-dkg-lattice-sdk      the knowledge graph: every fact with origin
                                        and licence; repo-library processing
  6 conduct    vega-harness-sdk          deterministic workflow conduct, pre-registered
                                        predicted paths, library use gate
  5 memory     vega-librarian-sdk        lessons and memory of past incidents
  4 contain    vega-two-gate-sdk         containment between two gates + the hard stop
  3 adapt      vega-pareah-sdk           adapters, cards, quarantine of inbound code:
                                        the dead-end room for the unannounced
  2 seal       vega-superproof-sdk       layered sealing and proof tiers
  1 authority  vega-governance-jacket-sdk human-only actions, single-use signed
                                        commitments, entry and exit gates
  0 record     vega-custody-sdk          capsules, DAG, hash-chained ledger, safe paths,
                                        bounded processes — the foundation everything
                                        writes to
```

**What the layers below provide (custody, layer 0):** Tamper-evident hash-chained ledgers (Chain), safe path I/O (safepaths), credential detection (contains_credential), DAG structure with replica agreement. The feed reads these chains; it never writes.

**Who above consumes it (layers 14–15):** vega-council-sdk and vega-galaxy-sdk (layer 14 deliberate) and vega-umbrella-sdk (layer 15 assemble) may subscribe to the feed events and alarms for human-visible governance panels and cross-family audit. The feed pushes nothing upward; consumers poll or subscribe.

One family, one organism: every SDK owns exactly one concern and uses the owner of every other concern instead of growing its own copy.

## 2. Internal drawing: modules and flow

```
+---------------------------------------------------------------------+
|                         vega_feed (layer 13)                        |
+---------------------------------------------------------------------+
|                                                                     |
|  +----------------+     +----------------+     +------------------+  |
|  |  Feed(sources, |     |   Feed.poll()  |     | Feed.snapshot()  |  |
|  |   state_path)  |---->|                |---->|                  |  |
|  +-------+--------+     +-------+--------+     +------------------+  |
|          |                    |                                       |
|          |                    v                                       |
|          |            +------------------+                             |
|          |            | For each source: |                             |
|          |            |  Chain(paths)    |                             |
|          |            +--------+---------+                             |
|          |                     |                                      |
|          |         +-----------+-----------+                          |
|          |         v           v           v                          |
|          |    CHAIN_BROKEN  CHAIN_SHORTENED CHAIN_REWRITTEN           |
|          |         |           |           |                          |
|          |         +-----------+-----------+                          |
|          |                     v                                      |
|          |            +------------------+                             |
|          |            | _alarm()         |                             |
|          |            | (SHA256 dedup,   |                             |
|          |            |  cursor frozen)  |                             |
|          |            +--------+---------+                             |
|          |                     |                                      |
|          |                     v                                      |
|          |            +------------------+                             |
|          |            | New entries:     |                             |
|          |            | summarize()      |                             |
|          |            | severity()       |                             |
|          |            | cursor advance   |                             |
|          |            | _save() atomic   |                             |
|          |            +--------+---------+                             |
|          |                     |                                      |
|          |                     v                                      |
|          |            +------------------+                             |
|          |            | Subscribers      |                             |
|          |            | (crash isolation)|                             |
|          |            +------------------+                             |
|          |                     |                                      |
|          v                     v                                      |
|  +------------------------------------------------------------------+ |
|  |              display.plain(text)                                 | |
|  |  (ESC peel loop > control char replacement)                      | |
|  +------------------------------------------------------------------+ |
|                                                                     |
+---------------------------------------------------------------------+
```

**Authority flow** (human -> feed): None. The feed holds no authority; it only reads. Authority flows from human -> jacket -> two-gate -> custody. The feed observes the custody output.

**Data flow** (custody -> feed -> consumers): Custody chain entries -> Chain(paths).entries() -> Feed.poll() verifies -> summarize() + severity() -> event dicts -> subscribers / snapshot -> upper layers.

## 3. Mermaid diagram

```mermaid
graph TD
    A[Feed(sources, state_path)] --> B[Load cursor from state_path]
    B --> C{poll() called}
    C --> D[For each source]
    D --> E[Chain(paths) from vega_custody]
    E --> F{ChainBroken or unreadable?}
    F -- Yes --> G[_alarm CHAIN_BROKEN]
    F -- No --> H{len(rows) < cursor.len?}
    H -- Yes --> I[_alarm CHAIN_SHORTENED]
    H -- No --> J{cursor.len>0 and head mismatch?}
    J -- Yes --> K[_alarm CHAIN_REWRITTEN]
    J -- No --> L[Clear alarm for source]
    L --> M[For each new entry]
    M --> N[summarize(entry)]
    N --> O[severity(kind)]
    O --> P[Build event dict]
    P --> Q[Advance cursor]
    Q --> R[_save atomic]
    G --> S[Cursor frozen]
    I --> S
    K --> S
    R --> T[Deliver to subscribers]
    S --> T
    T --> U[Update counters]
    U --> V[Return events]
    V --> W[snapshot() available]
    N --> X[display.plain()]
    X --> N
```

## 4. Sequence: main scenario — a poll cycle with tamper detection

```
Human/Operator          Feed                      Custody Chain (replicas)
    |                    |                              |
    |  1. Feed(sources,  |                              |
    |     state_path)    |                              |
    |<--- validated  --->|                              |
    |                    |                              |
    |  2. feed.poll()    |                              |
    |------------------->|                              |
    |                    |  3. Chain(paths)             |
    |                    |----------------------------->|
    |                    |  4. entries() = [e1,e2,e3]   |
    |                    |<-----------------------------|
    |                    |  5. verify integrity         |
    |                    |     - hash chain ok          |
    |                    |     - replicas agree         |
    |                    |     - len >= cursor.len      |
    |                    |     - head hash matches      |
    |                    |                              |
    |  (tamper occurs:   |                              |
    |   attacker edits   |                              |
    |   replica 0 entry 2)                              |
    |                    |                              |
    |  6. feed.poll()    |                              |
    |------------------->|                              |
    |                    |  7. Chain(paths)             |
    |                    |----------------------------->|
    |                    |  8. ChainBroken raised       |
    |                    |<-----------------------------|
    |                    |  9. _alarm(CHAIN_BROKEN)     |
    |                    |     - sig = SHA256(kind+detail)
    |                    |     - cursor frozen          |
    |                    |     - added to _alarmed      |
    |                    |                              |
    |  10. returns       |                              |
    |     [alarm event]  |                              |
    |<-------------------|                              |
    |                    |                              |
    |  (attacker repairs |                              |
    |   replicas)        |                              |
    |                    |                              |
    |  11. feed.poll()   |                              |
    |------------------->|                              |
    |                    |  12. Chain(paths) ok         |
    |                    |----------------------------->|
    |                    |  13. entries() = [e1,e2,e3,e4]|
    |                    |<-----------------------------|
    |                    |  14. _alarmed.pop(source)    |
    |                    |  15. summarize(e4)           |
    |                    |  16. advance cursor          |
    |                    |  17. _save() atomic          |
    |                    |                              |
    |  18. returns       |                              |
    |     [e4 event]     |                              |
    |<-------------------|                              |
```

## 5. Trust boundaries

| Boundary | From To | What enforces it |
|---|---|---|
| Human Feed | Operator configures sources | Feed.__init__ validates names, paths, count (FeedRefused) |
| Feed Custody | Feed reads chains | vega_custody.dag.Chain verifies hash chain, replica agreement; raises ChainBroken on failure |
| Feed Subscribers | Feed delivers events | Subscriber exceptions caught and ignored; feed continues; counters updated before delivery |
| Feed State file | Feed persists cursor | vega_custody.safepaths.atomic_write (atomic replace); corrupt state -> safe restart (re-reports) |
| Feed Upper layers | Events/alarms exposed via poll()/snapshot() | No trust required: alarms have entry_hash: null, seq: null; summaries allow-listed/scrubbed; counters monotonically non-decreasing per severity |
| Custody Feed | Chain as source of truth | Feed assumes custody chain integrity; if chain itself is compromised before first poll, feed cannot detect (documented limit) |

## 6. Computational workflow with fail-closed constraints

```
+--------------------------------------------------------------------+
|                      FEED POLL COMPUTATIONAL WORKFLOW              |
|                    (fail-closed constraints marked with [FC])      |
+--------------------------------------------------------------------+

START: feed.poll()
  |
  +-> Acquire self._lock (thread safety)
  |
  +-> FOR each source in self.sources:
  |       |
  |       +-> CHECK: any replica exists?
  |       |       +--NO (but cursor.len > 0) --[FC]--> _alarm(CHAIN_SHORTENED, files gone)
  |       |                                   |       cursor frozen
  |       |                                   |       CONTINUE next source
  |       |
  |       +-> TRY: ch = Chain(paths)  [vega_custody.dag.Chain]
  |       |       +--EXCEPT ChainBroken --[FC]--> _alarm(CHAIN_BROKEN, exc)
  |       |       |                        |       cursor frozen
  |       |       |                        |       CONTINUE next source
  |       |       |
  |       |       +--EXCEPT (OSError, ValueError, DagError) [FC] _alarm(CHAIN_BROKEN)
  |       |       |                        |       cursor frozen
  |       |       |                        |       CONTINUE next source
  |       |       |
  |       |       +--SUCCESS: rows = ch.entries()
  |       |
  |       +-> CHECK: len(rows) < cursor[len]?
  |       |       +--YES --[FC]--> _alarm(CHAIN_SHORTENED, was X now Y)
  |       |                       |       cursor frozen
  |       |                       |       CONTINUE next source
  |       |
  |       +-> CHECK: cursor[len] > 0 AND rows[cursor[len]-1].entry_hash != cursor[head]?
  |       |       +--YES --[FC]--> _alarm(CHAIN_REWRITTEN, entry at pos N replaced)
  |       |                       |       cursor frozen
  |       |                       |       CONTINUE next source
  |       |
  |       +-> CLEAR: self._alarmed.pop(name, None)  [alarm cleared, cursor may advance]
  |       |
  |       +-> FOR each new entry in rows[cursor[len]:]:
  |       |       +-> summary = summarize(entry)  [allow-list, scrub, clip, plain()]
  |       |       +-> sev = severity(entry[kind])  [critical/alert/info]
  |       |       +-> BUILD event dict {source, seq, kind, severity, summary, entry_hash}
  |       |       +-> APPEND to output list
  |       |
  |       +-> ADVANCE cursor[len], cursor[head] = len(rows), rows[-1].entry_hash
  |       |
  |       +-> END FOR source
  |
  +-> _save()  [atomic_write state_path]  --[FC] on failure: cursor in memory only, next poll reloads
  |
  +-> RELEASE self._lock
  |
  +-> FOR each event in output:
  |       +-> UPDATE counters[severity]++
  |       +-> UPDATE counters[source:kind]++
  |       +-> FOR each subscriber in self._subs:
  |               +-> TRY: subscriber(event)
  |               +--EXCEPT Exception: PASS  [FC] [crash isolation: one bad sub != feed stop]
  |
  +-> RETURN output list

ALARM DEDUPLICATION (_alarm):
  sig = SHA256(kind + detail)
  IF self._alarmed.get(name) == sig: RETURN []  [FC] [same problem not re-announced]
  self._alarmed[name] = sig
  RETURN [alarm_event]  [entry_hash=null, seq=null, severity=critical]

STATE LOAD (constructor):
  IF state_path exists:
    TRY: load JSON, validate per-source {len: int>=0, head: str|null}
    EXCEPT (OSError, ValueError, PathRefused): PASS  [FC] [corrupt -> start from zero, re-report]
```

**Fail-closed constraint points (module + function):**

| # | Constraint | Mechanism | Location |
|---|---|---|---|
| 1 | Invalid constructor config | Raise FeedRefused (deny-default) | Feed.__init__ |
| 2 | Chain verification failure | Raise CHAIN_BROKEN alarm, freeze cursor | Feed.poll -> Chain(paths) |
| 3 | Chain shortened | Raise CHAIN_SHORTENED alarm, freeze cursor | Feed.poll -> len(rows) < cursor[len] |
| 4 | History rewritten | Raise CHAIN_REWRITTEN alarm, freeze cursor | Feed.poll -> head hash mismatch |
| 5 | Alarm deduplication | SHA256 signature; suppress duplicate | Feed._alarm |
| 6 | Cursor freeze during alarm | continue skips cursor advance | Feed.poll (three alarm branches) |
| 7 | Alarm clear only on verified chain | pop only after all checks pass | Feed.poll |
| 8 | Subscriber crash isolation | Bare except Exception: pass | Feed.poll delivery loop |
| 9 | State corruption -> safe restart | Catch all, start from zero | Feed.__init__ state load |
| 10 | State claims > chain has | CHAIN_SHORTENED alarm (not silence) | Feed.poll |
| 11 | State wrong head hash | CHAIN_REWRITTEN alarm | Feed.poll |
| 12 | Summary allow-list enforcement | Dict comprehension over SHOW | Feed.summarize |
| 13 | Credential scrubbing | contains_credential -> [REDACTED] | Feed._clip |
| 14 | Escape stripping | Iterative regex peel until fixed point | display.plain |
| 15 | Value clipping | [:200] after scrub | Feed._clip |
| 16 | Atomic state write | safepaths.atomic_write | Feed._save |

**Custom constraints:** This version publishes no user-defined constraint hooks; constraints are fixed by the module and the jurisdiction floor (vega-jurisdiction-sdk). The allow-list SHOW, ALERT_WORDS, MAX_SOURCES are module constants — not configurable at runtime. No registry entries, injected callables, config parameters, or subclass hooks exist in the published code.