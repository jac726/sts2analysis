# sts2-analysis — Code Review

Severity badges: **[CRASH]** = unhandled exception possible, **[CORRUPT]** = silently wrong aggregate stats, **[WRONG]** = wrong output but visible/recoverable, **[PERF]**, **[STYLE]**.

Files reviewed in full:
- `sts2_analysis/models/run.py`
- `sts2_analysis/parser/save_parser.py`
- `sts2_analysis/analysis/run_stats.py`
- `sts2_analysis/analysis/deck_analysis.py`
- `sts2_analysis/analysis/relic_tracker.py`
- `sts2_analysis/viz/dashboard.py`
- `scripts/analyze.py`
- `notebooks/exploration.py`

---

## 1. Crashes

### [CRASH-1] `Run.from_dict` blows up when JSON keys exist but are `None`
**File:** `sts2_analysis/models/run.py:159, 161, 176, 177, 181–183`

`data.get("players", [{}])` only uses the default when the key is *missing*. STS2 saves can legitimately serialize keys with explicit `null` (e.g. `"players": null` for an aborted run, or `"acts": null` very early). When that happens:

- Line 159: `data.get("players", [{}])[0]` → `None[0]` → `TypeError`
- Line 161: `data.get("map_point_history", [])` → `None` → `enumerate(None)` → `TypeError`
- Lines 176–177: `acts=data.get("acts", [])` may store `None`, breaking later `len(r.acts)` in `runs_to_dataframe` (`run_stats.py:15`) and `_act_progression` (`dashboard.py:194–197`).
- Lines 181–183: same for `deck`, `relics`, `potions`.

**Fix:** Use the `or` idiom for "missing-or-null":
```python
players = data.get("players") or [{}]
player = players[0] if players else {}
mph = data.get("map_point_history") or []
acts = data.get("acts") or []
deck = player.get("deck") or []
relics = player.get("relics") or []
potions = player.get("potions") or []
```

### [CRASH-2] `CardChoice.from_dict` crashes if the `card` field is explicitly `null`
**File:** `sts2_analysis/models/run.py:43`

`d.get("card", {}).get("id", "")` — if `"card"` key exists with value `None`, `.get` returns `None`, then `.get("id"…)` → `AttributeError`.

**Fix:** `card_id=(d.get("card") or {}).get("id", "")`. Same pattern is needed at `models/run.py:71` for `player_stats[0]` if any element is `None` (the truthiness guard catches `[]` and `None` lists, but not `[None]`).

### [CRASH-3] `summary_stats` raises `IndexError` on empty DataFrame
**File:** `sts2_analysis/analysis/run_stats.py:47`

`df["character"].value_counts().index[0]` indexes the first element of an empty index. Also relevant: lines 42, 44, 45 produce `NaN` on empty input. `NaN` survives `round()` → `json.dumps` emits literal `NaN` → JS `JSON.parse` cannot read it (it's not valid JSON; the inline `<script>` happens to allow it, but you'll still crash any `JSON.parse` of `ALL_DATA`).

`_slice_data` short-circuits empty `runs`, so the dashboard avoids it today, but a user calling `summary_stats(df)` on a filtered df from the notebook can hit it (e.g. `summary_stats(df[df.was_abandoned])` when no runs are abandoned).

**Fix:** Guard at the top:
```python
if df.empty:
    return {"total_runs": 0, "total_wins": 0, "win_rate_pct": 0.0,
            "total_hours": 0.0, "avg_run_time_min": 0.0, "avg_floors": 0.0,
            "characters_played": 0, "most_played_char": None}
```

### [CRASH-4] `card_win_rates` / `card_offer_vs_pick` / `relic_win_rates` raise `KeyError` on empty result
**Files:** `analysis/deck_analysis.py:34`, `analysis/deck_analysis.py:52`, `analysis/relic_tracker.py:20`

`pd.DataFrame([]).sort_values("win_rate")` raises `KeyError: 'win_rate'` because an empty list builds a 0-column frame. This will fire any time no card/relic clears the `min_appearances` / `min_runs` threshold (very plausible for a single-character filtered slice).

**Fix:** Either return early on empty:
```python
if not records:
    return pd.DataFrame(columns=["card", "runs", "wins", "win_rate"])
return pd.DataFrame(records).sort_values("win_rate", ascending=False)
```
or pass `columns=` to the empty DataFrame.

### [CRASH-5] Quadratic floor-offset uses `data["map_point_history"]` (not the safe `.get`)
**File:** `sts2_analysis/models/run.py:163`

The loop on line 161 is guarded with `.get(..., [])`, but the prefix-sum on line 163 reaches into `data["map_point_history"]` directly. Today this is reachable only if the loop body executes, which means the key already exists — so it's safe in practice. But if anyone refactors line 161 to a local variable while leaving 163 alone, it becomes a `KeyError`. Replace with a precomputed array (also fixes a perf issue, see PERF-1).

---

## 2. Silent data corruption (high priority)

### [CORRUPT-1] `CardEntry.from_dict` silently drops the `upgraded` flag
**File:** `sts2_analysis/models/run.py:16–21`

The dataclass declares `upgraded: bool = False`, but `from_dict` never reads it. Every parsed card has `upgraded=False`. Any downstream analysis that distinguishes upgraded vs base cards (e.g., a future "upgraded card win rate" view) will be silently wrong.

**Fix:**
```python
return cls(
    id=d.get("id", ""),
    floor_added_to_deck=d.get("floor_added_to_deck", 0),
    upgraded=d.get("upgraded", False),
)
```

### [CORRUPT-2] Top-20 truncation in Python breaks JS sort toggles
**File:** `sts2_analysis/viz/dashboard.py:62–67, 82–87`

`_card_wr` sorts by `win_rate` and slices `[:20]`. The JS card panel lets the user re-sort by `runs` (`wrSort = 'runs'`) — but the JS only sees the top-20-by-WR. So "Sort: Count" displays the top-20-by-WR re-ordered by run count, **not** the top-20-by-run-count. Same problem in `_card_picks` (sorted by `picked` in Python; JS toggles to `pick_rate`).

This is a serious "the chart looks fine but is showing the wrong cards" bug.

**Fix:** Either send all cards above threshold and let JS slice the top 20 after sorting, or pre-compute both sort orders in Python and switch in JS. Cheapest: remove `[:20]` in Python and slice top-20 in JS *after* the user-selected sort.

### [CORRUPT-3] `_killers` filters `was_abandoned`, but `summary_stats`/`win_rate_by`/`_card_wr`/`_relic_wr` do not
**Files:** `analysis/run_stats.py:28–35, 38–48`, `viz/dashboard.py:51–67, 90–104`, `analysis/deck_analysis.py:20–34`, `analysis/relic_tracker.py:7–20`

Abandoned runs (`was_abandoned=True`) are pure win-rate poison: they're never wins, so each one drags every per-card / per-relic / per-character / per-block win-rate down. `_killers` correctly excludes them, but every other aggregation includes them. This produces silently low win rates and inconsistent numbers between tabs (an A20 win-streak character can look like 30% WR if the user abandoned a few low-asc warmups).

**Fix:** Add a single chokepoint early in `_slice_data` (and in `summary_stats`):
```python
runs = [r for r in runs if not r.was_abandoned]
```
Or expose abandoned-runs as a third toggle alongside short/A10. At minimum, document that win rates include abandoned runs.

### [CORRUPT-4] Multiplayer / co-op runs read `players[0]` blindly
**File:** `sts2_analysis/models/run.py:159` and `models/run.py:71`

In a co-op save, `players` has multiple entries. We always read index 0, so:
- The `character`, `deck`, `relics` of co-op runs may belong to a *different player*, polluting per-character stats.
- `FloorStats.from_dict` reads `player_stats[0]` per floor — same issue.

There's no UID match between the `Run` and "this user's player slot."

**Fix (pragmatic):** Either (a) skip co-op runs entirely:
```python
if data.get("game_mode") == "coop" or len(data.get("players") or []) > 1:
    return None  # or a flag, then filter in load_all_runs
```
or (b) match by Steam ID stored in the player node (if the schema has one).

### [CORRUPT-5] `renderWinRate` returns silently on empty rows, leaving stale chart
**File:** `sts2_analysis/viz/dashboard.py:710–712`

```js
if (!rows.length) return;
```
Every other render function replaces `el.innerHTML` with an "empty" message. `renderWinRate` does not, so when a filter combination produces no per-character data, the previously-rendered chart from the *previous filter state* stays on screen. The user sees outdated numbers and has no idea.

**Fix:**
```js
if (!rows.length) {
  document.getElementById('ch-winrate').innerHTML = '<p class="empty">No data</p>';
  return;
}
```
(And consider calling `Plotly.purge('ch-winrate')` first to release the previous chart's memory.)

### [CORRUPT-6] Empty-string `card_id` aggregated as a real card
**File:** `sts2_analysis/models/run.py:43`, `analysis/deck_analysis.py:43`, `viz/dashboard.py:75`

When a card-choice entry is malformed (no `card.id`), `CardChoice.from_dict` returns `card_id=""`. Then `_card_picks` and `card_offer_vs_pick` happily aggregate `""` as if it were a card called "". After cleaning (`replace("CARD.", "")`) it stays `""` → shows up as a blank-named row in charts.

**Fix:** In aggregations, `if not cid: continue`.

### [CORRUPT-7] `floor_acquired` mixes starter relics and event/boss relics with `floor=0`
**File:** `sts2_analysis/analysis/relic_tracker.py:33–43`

Starter relics — and any relic where `floor_added_to_deck` defaults to 0 because the field was missing — pile up at `floor=0`, distorting "when relics are acquired" histograms.

**Fix:** Filter or partition: `if relic.floor_added_to_deck == 0: continue`, or add a `is_starter` flag and separate the two groups.

### [CORRUPT-8] Locale-dependent date strings in dashboard JSON
**File:** `sts2_analysis/viz/dashboard.py:176`

`r.datetime.strftime("%b %d, %Y")` uses the OS locale. On non-English Windows installs the user gets "abr 12, 2026" or similar in tooltips, and any text-matching code (or comparison across machines) breaks.

**Fix:** Hand-format with stable English abbreviations, or emit ISO and format in JS:
```python
"date": r.datetime.isoformat() if r.datetime else ""
```
JS: `new Date(p.date).toLocaleDateString('en-US', {month:'short',day:'numeric',year:'numeric'})`.

### [CORRUPT-9] `Run.datetime` is naive local time
**File:** `sts2_analysis/models/run.py:128–132`

`datetime.fromtimestamp(self.start_time)` produces a naive datetime in the local timezone. If the user moves machines / changes TZ / DST shift, sort orders flip near boundaries. `start_time` is presumably Unix epoch (UTC) — keep it that way.

**Fix:** `datetime.fromtimestamp(self.start_time, tz=timezone.utc)`.

---

## 3. Wrong output

### [WRONG-1] `wrGradient` and `renderCardPicks` divide by `Math.max(...) = 0`
**File:** `sts2_analysis/viz/dashboard.py:660` and `:775`

```js
const mx = Math.max(...values);
return values.map(v => { const t = v / mx; ... });
```
If every value is 0 (e.g., a slice where the only relics shown have 0% WR, or a slice where every offered card was rejected — pick-count for all=0), `mx=0` → `t=NaN` → `rgb(NaN,NaN,NaN)` → bars render colorless/invisible.

**Fix:** `const mx = Math.max(...values, 1);` or `if (mx === 0) return values.map(_ => DEFAULT);`.

### [WRONG-2] `_buckets` ignores both filter toggles
**File:** `sts2_analysis/viz/dashboard.py:260`

`"_buckets": _time_bucket_stats(char_runs)` is computed once on the unfiltered character slice. The "Run length" bar chart never reflects the short-run / A10 toggles, even though the scatter plot directly above it does. Comment claims this is intentional, but it produces user-visible inconsistency.

**Fix:** Either compute four `_buckets` slices (matching the slice keys) and select with `sliceKey()`, or visibly disable the toggles when this tab is active, or show a "filters not applied" badge on the card.

### [WRONG-3] `wrColor` thresholds (55 / 38) are arbitrary, hardcoded
**File:** `sts2_analysis/viz/dashboard.py:654–656`

A 55%+ WR is dark green, 38–55% amber, <38% red. These thresholds are character/asc-dependent in STS2 — A20 Defect at 30% might be excellent, while A0 Ironclad at 60% is mediocre. Hardcoded thresholds will mislead users on hard difficulty.

**Fix:** Either compute relative-to-mean, or expose them, or document.

### [WRONG-4] `_killers` keeps `"NONE.NONE"` if encounter id is `"NONE.NONE"` without prefix
**File:** `sts2_analysis/viz/dashboard.py:134–138`

The check `kb and kb != "NONE.NONE"` works after stripping `"ENCOUNTER."`. But if a save records `killed_by_encounter=""` for a normal-death loss (e.g., killed by HP loss from a curse), the run is dropped from killer stats — possibly missing real losses. Conversely, runs killed by events (with `killed_by_event` set, `killed_by_encounter=""`) are silently dropped.

**Fix:** Combine: `kb = (r.killed_by_encounter or r.killed_by_event).replace(...)`. Or split into "killed by enemy" vs "killed by event" tabs.

### [WRONG-5] `card_pick_rates` is mis-named
**File:** `sts2_analysis/analysis/deck_analysis.py:7–17`

This computes "% of runs where this card ended up in the final deck." Calling that `pick_rate` is confusing because `card_offer_vs_pick` (line 37) computes the *real* reward-screen pick rate. Rename to `card_appearance_rate` or `card_inclusion_rate`.

### [WRONG-6] `_card_wr` / `_relic_wr` truncate to top-20 without sending the runs-up text
The JS shows `r.runs` count next to win-rate label, which is good — but a card at #21 with 99% WR over 50 runs is hidden, and there's no UI clue that more cards exist. Mention it in a `card-note` ("top 20 of 87 eligible").

### [WRONG-7] `card_offer_vs_pick` uses threshold 5; `_card_picks` uses 10
**File:** `analysis/deck_analysis.py:50` vs `viz/dashboard.py:85`

CLI/notebook output and dashboard show different cards for "most picked." Pick one threshold and document it, or expose as a parameter.

### [WRONG-8] `_act_progression` is incorrect when `acts` is set but `win` is also true
**File:** `sts2_analysis/viz/dashboard.py:193–197`

`Reached Act 2/3` is `len(r.acts) >= 2/3`. If `r.acts` reflects acts *completed*, a Victory run with 4 completed acts shows up in all three checkpoints — fine. But if `r.acts` reflects acts *visited* and a winning run only "visits" 3 distinct acts (the schema may not include the boss-fight act as a separate entry), `Victory` could be true while `Reached Act 3` is false, producing the silly outcome of 100% Victory but 80% Reached Act 3.

Worth verifying against a real winning save. Defensively:
```python
("Reached Act 3", lambda r: len(r.acts) >= 3 or r.win),
```

---

## 4. Performance

### [PERF-1] Quadratic floor-index calculation
**File:** `sts2_analysis/models/run.py:163`

```python
global_floor = sum(len(a) for a in data["map_point_history"][:act_idx]) + floor_idx + 1
```
Recomputed every floor → O(F²) per run. Trivial for 60 floors, but trivially fixable:
```python
mph = data.get("map_point_history") or []
prefix = 0
for act_idx, act_floors in enumerate(mph):
    for floor_idx, floor_data in enumerate(act_floors):
        global_floor = prefix + floor_idx + 1
        floor_history.append(FloorStats.from_dict(floor_data, global_floor, act_idx + 1))
    prefix += len(act_floors)
```

### [PERF-2] `Run.raw=data` retains the entire raw JSON per Run forever
**File:** `sts2_analysis/models/run.py:186`

Storing the raw dict on every Run keeps every save's full content in memory. At ~50KB–200KB per save, 5,000 runs is ~1GB. The `raw` field is only used by the inspect-style notebook flow; the dashboard never touches it.

**Fix:** Make it opt-in:
```python
@classmethod
def from_dict(cls, data: dict, *, keep_raw: bool = False) -> "Run":
    ...
    raw=data if keep_raw else None,
```
Default `False`. Notebook callers that want it pass `keep_raw=True`.

### [PERF-3] JSON payload size grows with run count, with heavy duplication
**File:** `sts2_analysis/viz/dashboard.py:208–262`

Per-run arrays (`run_lengths`, `floors`, `progress`) are repeated across 4 slice keys × 6 chars = 24 copies of overlapping subsets. With 1,000 runs the HTML can run to several MB. With 10k runs (one prolific year) it'll cross the size where browsers start to choke on string-parsing the inline JSON.

**Fix options:**
- Send one canonical `runs[]` array plus 24 lightweight `{slice_key}` entries that reference *indices* into it.
- Or compute the slice client-side from the raw run array — Python sends `runs[]` once, JS does the filtering. (Big simplification: the 4-slice key matrix becomes redundant.)

### [PERF-4] `_progress` rolling-WR has an inner sum
**File:** `sts2_analysis/viz/dashboard.py:171–185`

```python
wslice = sorted_runs[start:i + 1]
wr = ... sum(1 for x in wslice if x.win) / len(wslice) ...
```
O(N × window) per slice; O(N × W × 24 slices). At W=10 and N=10k that's still fine. Easy to make true O(N) with a running win-counter:
```python
wins = 0
window_q = collections.deque()
for i, r in enumerate(sorted_runs):
    window_q.append(r.win); wins += r.win
    if len(window_q) > window:
        wins -= window_q.popleft()
    ...
```

### [PERF-5] `_act_progression` iterates `runs` twice per checkpoint
**File:** `sts2_analysis/viz/dashboard.py:198–205`

```python
"count": sum(1 for r in runs if fn(r)),
"pct":   round(sum(1 for r in runs if fn(r)) / total * 100, 1),
```
Compute once:
```python
count = sum(1 for r in runs if fn(r))
result.append({"label": label, "count": count, "pct": round(count/total*100, 1)})
```

### [PERF-6] `Plotly.newPlot` is called fresh on every render
**File:** `sts2_analysis/viz/dashboard.py:712 onward`

For interactive re-renders (filter toggle), `Plotly.react(id, traces, layout, config)` reuses the same DOM and is meaningfully faster — and prevents the gradual memory growth that `newPlot` causes when called repeatedly.

### [PERF-7] `inspect` loads every save just to print a few
**File:** `scripts/analyze.py:98–112`

`load_all_runs(saves_dir)` iterates the entire history folder before slicing `[:n]`. Cheap fix: stream from `Path(saves_dir).glob("*.run")` and break after `n`.

---

## 5. Style / minor

- **`parser/save_parser.py:31–41`** — `find_default_saves_dir` is Windows-only; on Mac/Linux it silently returns `None`. Add `~/Library/Application Support/Steam/...` and `~/.local/share/Steam/...` branches, or note "Windows only" in the docstring.
- **`parser/save_parser.py:27`** — `print("[warn] ...")` should go to `sys.stderr` (or use `logging.warning`); otherwise warnings interleave with table output.
- **`parser/save_parser.py:15`** — `data["_source_file"] = str(path)` mutates the parsed dict and then survives into `Run.raw` — fine, but a leading `_source_file` key in `inspect` output is the side effect. (You already filter it on `analyze.py:105`, so this is benign.)
- **`viz/dashboard.py:807`** — `_buckets || []` defaults to empty array on `null`/`undefined`, but the panel doesn't show the run-time *scatter* anywhere with a graceful empty state — `renderRunScatter` will plot empty traces; consider an empty placeholder.
- **`viz/dashboard.py:1065–1078`** — `renderActProgression` uses `colors.slice(0, rows.length)` so 1- or 2-row outputs never get red/green; that's intentional but worth a comment.
- **`scripts/analyze.py:13`** — `sys.path.insert(0, str(Path(__file__).parent.parent))` is fine for ad-hoc use, but a `pyproject.toml` with a console-script entry-point would be cleaner.
- **`notebooks/exploration.py:13`** — `os.path.dirname('')` returns `''`, so `sys.path.insert(0, '..')` is a relative path. Use `os.path.dirname(os.path.abspath('__file__'))` (or the jupytext-aware equivalent), or just `sys.path.insert(0, os.path.abspath('..'))`.
- **`notebooks/exploration.py:36`** — Real Steam ID committed; consider replacing with the env-var pattern shown in line 35.
- **`viz/dashboard.py:38`** — `HIGH_ASC_THRESHOLD = 10` is hardcoded; if STS2 ascension caps differently than STS1, this label ("A10 only") may be misleading. Make it a CLI arg.
- **`viz/dashboard.py:1014`** — `lastWin = prog[prog.length - 1].win` — variable name reads like "did the last win happen?" but value is the win/loss boolean of the last run. `lastOutcome` would read clearer.
- **`analysis/run_stats.py:16`** — `round(r.run_time_minutes, 1)` rounds in the dataframe, throwing away sub-minute precision permanently. If you ever want second-level precision later, rounding is purely presentational and belongs in formatting, not the model layer.

---

## Suggested fix order (highest leverage first)

1. CRASH-1 + CRASH-2 (5 minutes; the `or {}` / `or []` idiom across `from_dict`).
2. CORRUPT-3 (abandoned runs filter — single-line fix in `_slice_data`, biggest impact on accuracy).
3. CORRUPT-2 (top-20 truncation — move the slicing into JS).
4. CORRUPT-1 (parse `upgraded`).
5. CORRUPT-5 (renderWinRate stale chart).
6. CRASH-3 + CRASH-4 (empty-frame guards).
7. CORRUPT-4 (multiplayer detection).
8. PERF-2 + PERF-3 once you cross ~1,000 runs.
