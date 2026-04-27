"""
STS2 Dashboard — fully interactive single-file HTML.
Filters: character, exclude-short-runs (<5m), basics toggle.
Charts: win rate, floors, cards, relics, run length, killers, progress, ascension.
"""
import json
from sts2_analysis.models.run import Run
from sts2_analysis.analysis.run_stats import runs_to_dataframe, win_rate_by, summary_stats

STARTER_CARDS = {
    "ASCENDERS_BANE", "BASH", "BODYGUARD",
    "DEFEND_DEFECT", "DEFEND_IRONCLAD", "DEFEND_NECROBINDER",
    "DEFEND_REGENT", "DEFEND_SILENT",
    "DUALCAST", "FALLING_STAR", "NEUTRALIZE",
    "STRIKE_DEFECT", "STRIKE_IRONCLAD", "STRIKE_NECROBINDER",
    "STRIKE_REGENT", "STRIKE_SILENT",
    "SURVIVOR", "UNLEASH", "VENERATE", "ZAP",
}

CHAR_COLORS = {
    "IRONCLAD":    "#e05252",
    "SILENT":      "#3ecf7a",
    "DEFECT":      "#4fa3e0",
    "NECROBINDER": "#b06ae8",
    "REGENT":      "#f09c3a",
    "All":         "#7c6af7",
}

TIME_BUCKETS = [
    ("< 5m",    0,  5),
    ("5–15m",   5,  15),
    ("15–30m",  15, 30),
    ("30–45m",  30, 45),
    ("45m+",    45, 9999),
]

SHORT_RUN_THRESHOLD = 5   # minutes — below this is almost always an early death
HIGH_ASC_THRESHOLD  = 10  # exclude everything below A10


def _clean(name: str) -> str:
    return name.replace("_", " ").title()


def _filter_char(runs: list[Run], char: str) -> list[Run]:
    if char == "All":
        return runs
    return [r for r in runs if r.character.replace("CHARACTER.", "") == char]


def _card_wr(runs: list[Run], exclude_basics: bool = True, min_appearances: int = 10) -> list[dict]:
    from collections import Counter
    wins: Counter = Counter()
    total: Counter = Counter()
    for r in runs:
        for c in set(card.id.replace("CARD.", "") for card in r.deck):
            if not c or (exclude_basics and c in STARTER_CARDS):  # Skip empty and basic cards (CORRUPT-6)
                continue
            total[c] += 1
            if r.win:
                wins[c] += 1
    return sorted(
        [{"card": _clean(c), "runs": total[c],
          "win_rate": round(wins[c] / total[c] * 100, 1)}
         for c in total if total[c] >= min_appearances],
        key=lambda x: -x["win_rate"]
    )[:20]


def _card_picks(runs: list[Run], exclude_basics: bool = True) -> list[dict]:
    from collections import Counter
    offered: Counter = Counter()
    picked: Counter = Counter()
    for r in runs:
        for ch in r.all_card_choices:
            cid = ch.card_id.replace("CARD.", "")
            if not cid or (exclude_basics and cid in STARTER_CARDS):  # Skip empty and basic cards (CORRUPT-6)
                continue
            offered[cid] += 1
            if ch.was_picked:
                picked[cid] += 1
    return sorted(
        [{"card": _clean(c), "offered": offered[c], "picked": picked[c],
          "pick_rate": round(picked[c] / offered[c] * 100, 1)}
         for c in offered if offered[c] >= 10],
        key=lambda x: -x["picked"]
    )[:20]


def _relic_wr(runs: list[Run], min_runs: int = 8) -> list[dict]:
    from collections import Counter
    wins: Counter = Counter()
    total: Counter = Counter()
    for r in runs:
        for rel in set(rr.id.replace("RELIC.", "") for rr in r.relics):
            total[rel] += 1
            if r.win:
                wins[rel] += 1
    return sorted(
        [{"relic": _clean(rel), "runs": total[rel],
          "win_rate": round(wins[rel] / total[rel] * 100, 1)}
         for rel in total if total[rel] >= min_runs],
        key=lambda x: -x["win_rate"]
    )[:20]


def _run_lengths(runs: list[Run]) -> list[dict]:
    return [{"run_time_min": round(r.run_time_minutes, 1), "win": r.win,
             "character": r.character.replace("CHARACTER.", ""),
             "floors": r.floors_reached}
            for r in runs]


def _time_bucket_stats(runs: list[Run]) -> list[dict]:
    result = []
    for label, lo, hi in TIME_BUCKETS:
        sub = [r for r in runs if lo <= r.run_time_minutes < hi]
        if not sub:
            continue
        wins = sum(1 for r in sub if r.win)
        result.append({
            "bucket": label, "lo": lo, "hi": hi,
            "count": len(sub), "wins": wins,
            "win_rate": round(wins / len(sub) * 100, 1),
            "avg_floors": round(sum(r.floors_reached for r in sub) / len(sub), 1),
        })
    return result


def _killers(runs: list[Run]) -> list[dict]:
    from collections import Counter
    ctr: Counter = Counter()
    for r in runs:
        if not r.win and not r.was_abandoned:
            # Combine encounter and event kills (WRONG-4)
            kb = (r.killed_by_encounter or r.killed_by_event or "").replace("ENCOUNTER.", "")
            if kb and kb != "NONE.NONE":
                ctr[kb] += 1
    return [{"killer": _clean(k), "count": v} for k, v in ctr.most_common(15)]


def _win_rate_blocks(runs: list[Run], block_size: int = 10) -> list[dict]:
    """Win rate in discrete chronological blocks of block_size runs."""
    from datetime import datetime as dt_cls
    try:
        sorted_runs = sorted(runs, key=lambda r: r.datetime if r.datetime else dt_cls.min)
    except Exception:
        sorted_runs = runs
    result = []
    for i in range(0, len(sorted_runs), block_size):
        block = sorted_runs[i:i + block_size]
        wins = sum(1 for r in block if r.win)
        result.append({
            "block_num":  i // block_size + 1,
            "label":      f"#{i + 1}–{i + len(block)}",
            "runs":       len(block),
            "wins":       wins,
            "win_rate":   round(wins / len(block) * 100, 1),
            "partial":    len(block) < block_size,
        })
    return result


def _progress(runs: list[Run], window: int = 10) -> list[dict]:
    """Rolling win rate over time, sorted chronologically. O(N) using deque instead of O(N*W)."""
    from datetime import datetime as dt_cls
    from collections import deque
    try:
        sorted_runs = sorted(runs, key=lambda r: r.datetime if r.datetime else dt_cls.min)
    except Exception:
        sorted_runs = runs
    result = []
    wins = 0
    window_q: deque = deque()
    for i, r in enumerate(sorted_runs):
        window_q.append(r.win)
        wins += int(r.win)
        if len(window_q) > window:
            wins -= int(window_q.popleft())
        wr = round(wins / len(window_q) * 100, 1)
        try:
            # Use ISO format for locale-independence; format in JS (CORRUPT-8)
            date_str = r.datetime.isoformat() if r.datetime else ""
        except Exception:
            date_str = ""
        result.append({
            "i": i + 1,
            "date": date_str,
            "win": r.win,
            "rolling_wr": wr,
        })
    return result


def _act_progression(runs: list[Run]) -> list[dict]:
    """% of runs that reached each act milestone. Computes once per checkpoint (PERF-5)."""
    total = len(runs)
    if not total:
        return []
    checkpoints = [
        ("Reached Act 2", lambda r: len(r.acts) >= 2),
        ("Reached Act 3", lambda r: len(r.acts) >= 3 or r.win),  # Winning runs may not list act 3 separately (WRONG-8)
        ("Victory",       lambda r: r.win),
    ]
    result = []
    for label, fn in checkpoints:
        count = sum(1 for r in runs if fn(r))
        result.append({
            "label": label,
            "count": count,
            "pct": round(count / total * 100, 1),
        })
    return result


def _slice_data(runs: list[Run]) -> dict:
    """All chart data for a filtered run slice."""
    # Filter out abandoned runs to prevent win-rate poisoning
    runs = [r for r in runs if not r.was_abandoned]

    if not runs:
        return {
            "summary": {}, "win_by_char": [],
            "card_wr": [], "card_wr_all": [],
            "card_picks": [], "card_picks_all": [],
            "relic_wr": [], "run_lengths": [],
            "killers": [], "floors": [],
            "progress": [], "act_progression": [],
        }
    df = runs_to_dataframe(runs)
    return {
        "summary":        summary_stats(df),
        "win_by_char":    win_rate_by(df, "character").to_dict("records"),
        "card_wr":        _card_wr(runs, exclude_basics=True),
        "card_wr_all":    _card_wr(runs, exclude_basics=False),
        "card_picks":     _card_picks(runs, exclude_basics=True),
        "card_picks_all": _card_picks(runs, exclude_basics=False),
        "relic_wr":       _relic_wr(runs),
        "run_lengths":    _run_lengths(runs),
        "killers":        _killers(runs),
        "floors":         [{"floors": r.floors_reached, "win": r.win} for r in runs],
        "progress":        _progress(runs),
        "win_blocks":      _win_rate_blocks(runs),
        "act_progression": _act_progression(runs),
    }


def overview_dashboard(runs: list[Run], output_path: str) -> None:
    characters = ["All"] + sorted(set(
        r.character.replace("CHARACTER.", "") for r in runs))

    # Slice keys (two independent boolean filters → 4 combinations):
    #   "raw"      — nothing excluded
    #   "no_short" — exclude runs < 5m
    #   "high_asc" — exclude A0–A4
    #   "filtered" — exclude both (default view)
    # "_buckets" always uses the full char slice for the run-length tab.
    all_data: dict = {}
    for char in characters:
        char_runs = _filter_char(runs, char)
        no_short  = [r for r in char_runs if r.run_time_minutes >= SHORT_RUN_THRESHOLD]
        high_asc  = [r for r in char_runs if (r.ascension or 0) >= HIGH_ASC_THRESHOLD]
        filtered  = [r for r in char_runs
                     if r.run_time_minutes >= SHORT_RUN_THRESHOLD
                     and (r.ascension or 0) >= HIGH_ASC_THRESHOLD]
        all_data[char] = {
            "raw":      _slice_data(char_runs),
            "no_short": _slice_data(no_short),
            "high_asc": _slice_data(high_asc),
            "filtered": _slice_data(filtered),
            "_buckets": _time_bucket_stats(char_runs),
        }

    data_json   = json.dumps(all_data)
    colors_json = json.dumps(CHAR_COLORS)
    chars_json  = json.dumps(characters)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>STS2 Run Analysis</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:         #080b14;
  --surface:    #0d1020;
  --card:       rgba(255,255,255,0.032);
  --border:     rgba(255,255,255,0.07);
  --border-hi:  rgba(124,106,247,0.35);
  --accent:     #7c6af7;
  --accent-dim: rgba(124,106,247,0.12);
  --text:       #e8e8f0;
  --muted:      #4a4d60;
  --subtle:     #1e2235;
  --win:        #22c55e;
  --loss:       #ef4444;
  --mid:        #f59e0b;
}}

body {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg); color: var(--text);
  min-height: 100vh; font-size: 14px; line-height: 1.5;
}}

/* ── Header ── */
.header {{
  background: linear-gradient(135deg, #0d1020 0%, #10132a 100%);
  border-bottom: 1px solid var(--border);
  padding: 16px 32px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; flex-wrap: wrap;
  position: relative; overflow: hidden;
}}
.header::before {{
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, #7c6af7, #06b6d4, #22c55e, #7c6af7);
  background-size: 300% 100%;
  animation: shimmer 5s linear infinite;
}}
@keyframes shimmer {{ 0%{{background-position:0% 0%}} 100%{{background-position:300% 0%}} }}

.logo {{ font-size: 18px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }}
.logo em {{ font-style: normal; background: linear-gradient(90deg, #7c6af7, #06b6d4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}

.stats-row {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.stat {{
  background: rgba(255,255,255,0.04); border: 1px solid var(--border);
  border-radius: 10px; padding: 8px 16px; text-align: center;
  min-width: 80px; transition: border-color 0.2s;
}}
.stat:hover {{ border-color: var(--border-hi); }}
.stat-val {{ font-size: 20px; font-weight: 700; color: #fff; line-height: 1.1; letter-spacing: -0.5px; }}
.stat-label {{ font-size: 10px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.8px; margin-top: 2px; }}

/* ── Controls ── */
.controls {{
  background: var(--surface); border-bottom: 1px solid var(--border);
  padding: 10px 32px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}}
.ctrl-label {{ font-size: 10px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.8px; white-space: nowrap; }}
.ctrl-group {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.divider {{ width: 1px; height: 20px; background: var(--border); flex-shrink: 0; }}

.pill {{
  border: 1px solid var(--border); background: transparent; color: var(--muted);
  border-radius: 20px; padding: 4px 13px; font-size: 12px; font-weight: 500;
  font-family: inherit; cursor: pointer; transition: all 0.15s; white-space: nowrap;
}}
.pill:hover {{ border-color: rgba(255,255,255,0.2); color: var(--text); }}
.pill.active {{ background: var(--accent-dim); border-color: var(--accent); color: #c4bcff; font-weight: 600; }}
.pill.on-amber {{ background: rgba(245,158,11,0.1); border-color: var(--mid); color: var(--mid); }}
.pill.on-red   {{ background: rgba(239,68,68,0.1);  border-color: var(--loss); color: #fca5a5; }}

/* ── Tabs ── */
.tabs {{
  display: flex; background: var(--surface);
  border-bottom: 1px solid var(--border); padding: 0 28px; gap: 2px;
}}
.tab {{
  padding: 11px 16px; font-size: 13px; font-weight: 500; color: var(--muted);
  cursor: pointer; border-bottom: 2px solid transparent;
  transition: all 0.15s; letter-spacing: 0.1px; white-space: nowrap;
}}
.tab:hover {{ color: var(--text); }}
.tab.active {{ color: var(--accent); border-bottom-color: var(--accent); }}

/* ── Content ── */
.content {{ padding: 24px 32px; max-width: 1400px; }}
.panel {{ display: none; }}
.panel.active {{ display: block; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}

/* ── Cards ── */
.card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 20px;
  backdrop-filter: blur(12px);
  transition: border-color 0.25s, box-shadow 0.25s, transform 0.2s;
}}
.card:hover {{
  border-color: rgba(124,106,247,0.22);
  box-shadow: 0 6px 32px rgba(124,106,247,0.07), 0 0 0 1px rgba(124,106,247,0.07);
  transform: translateY(-1px);
}}

/* ── Streak widget ── */
.streak-grid {{ display: flex; flex-wrap: wrap; gap: 3px; padding: 4px 0; }}
.run-dot {{
  width: 12px; height: 12px; border-radius: 3px;
  display: inline-block; cursor: default; flex-shrink: 0;
  transition: transform 0.1s, opacity 0.1s;
  position: relative;
}}
.run-dot:hover {{ transform: scale(1.6); z-index: 10; }}
.run-dot.win  {{ background: #22c55e; }}
.run-dot.loss {{ background: #ef4444; opacity: 0.55; }}
.run-dot.in-streak {{ box-shadow: 0 0 5px 1px currentColor; opacity: 1 !important; }}

.streak-stat {{
  text-align: center; padding: 14px 10px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--border); border-radius: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}}
.streak-stat:hover {{
  border-color: rgba(124,106,247,0.25);
  box-shadow: 0 0 16px rgba(124,106,247,0.08);
}}
.streak-num {{
  font-size: 36px; font-weight: 800; letter-spacing: -2px; line-height: 1;
  background: linear-gradient(135deg, #7c6af7 0%, #06b6d4 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.streak-num.good {{
  background: linear-gradient(135deg, #22c55e 0%, #06b6d4 100%);
  -webkit-background-clip: text;
}}
.streak-num.bad {{
  background: linear-gradient(135deg, #ef4444 0%, #f59e0b 100%);
  -webkit-background-clip: text;
}}
.streak-label {{
  font-size: 10px; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.8px; margin-top: 6px;
}}
.card.wide {{ grid-column: 1 / -1; }}
.card-header {{
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px; gap: 10px; flex-wrap: wrap;
}}
.card-title {{ font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.9px; }}
.card-note  {{ font-size: 11px; font-weight: 400; color: #2e3248; }}

/* ── Sort toggle ── */
.sort-toggle {{ display: flex; background: rgba(255,255,255,0.04); border-radius: 6px; padding: 2px; gap: 1px; }}
.sort-btn {{
  background: transparent; border: none; color: var(--muted);
  font-size: 10px; font-weight: 600; padding: 3px 9px; border-radius: 4px;
  cursor: pointer; font-family: inherit; transition: all 0.15s; letter-spacing: 0.3px;
  text-transform: uppercase;
}}
.sort-btn.active {{ background: var(--accent-dim); color: #c4bcff; }}

.empty {{ color: #2a2d42; padding: 24px 0; font-size: 13px; }}

@media (max-width: 900px) {{
  .grid, .grid-3 {{ grid-template-columns: 1fr; }}
  .card.wide {{ grid-column: 1; }}
  .content, .controls, .header {{ padding-left: 16px; padding-right: 16px; }}
  .tabs {{ padding: 0 12px; overflow-x: auto; }}
}}
</style>
</head>
<body>

<div class="header">
  <div class="logo">STS2 <em>Run Analysis</em></div>
  <div class="stats-row" id="stats-row"></div>
</div>

<div class="controls">
  <div class="ctrl-group">
    <span class="ctrl-label">Character</span>
    <div id="char-btns" style="display:flex;gap:6px;flex-wrap:wrap;"></div>
  </div>
  <div class="divider"></div>
  <div class="ctrl-group">
    <button class="pill" id="short-btn" onclick="toggleShort()">Short runs excluded</button>
    <button class="pill" id="asc-btn"   onclick="toggleAsc()">A10 only</button>
  </div>
  <div class="divider"></div>
  <div class="ctrl-group">
    <button class="pill" id="basics-btn" onclick="toggleBasics()">Basics hidden</button>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('overview',this)">Overview</div>
  <div class="tab" onclick="showTab('cards',this)">Cards</div>
  <div class="tab" onclick="showTab('relics',this)">Relics</div>
  <div class="tab" onclick="showTab('runs',this)">Run length</div>
  <div class="tab" onclick="showTab('killers',this)">Run enders</div>
  <div class="tab" onclick="showTab('progress',this)">Progress</div>
</div>

<div class="content">

  <!-- Overview -->
  <div class="panel active" id="panel-overview">
    <div class="grid">
      <div class="card">
        <div class="card-header"><span class="card-title">Win rate by character</span></div>
        <div id="ch-winrate"></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Floors reached</span></div>
        <div id="ch-floors"></div>
      </div>
    </div>
  </div>

  <!-- Cards -->
  <div class="panel" id="panel-cards">
    <div class="grid">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Win rate</span>
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="card-note">≥ 10 appearances</span>
            <div class="sort-toggle">
              <button class="sort-btn active" id="wr-sort-wr"    onclick="setWRSort('win_rate')">Win %</button>
              <button class="sort-btn"        id="wr-sort-count" onclick="setWRSort('runs')">Count</button>
            </div>
          </div>
        </div>
        <div id="ch-cardwr"></div>
      </div>
      <div class="card">
        <div class="card-header">
          <span class="card-title">Most picked at rewards</span>
          <div class="sort-toggle">
            <button class="sort-btn active" id="pick-sort-picked"   onclick="setPickSort('picked')">Picked</button>
            <button class="sort-btn"        id="pick-sort-pickrate" onclick="setPickSort('pick_rate')">Pick %</button>
          </div>
        </div>
        <div id="ch-cardpick"></div>
      </div>
    </div>
  </div>

  <!-- Relics -->
  <div class="panel" id="panel-relics">
    <div class="grid">
      <div class="card wide">
        <div class="card-header">
          <span class="card-title">Relic win rates</span>
          <span class="card-note">≥ 8 appearances</span>
        </div>
        <div id="ch-relicwr"></div>
      </div>
    </div>
  </div>

  <!-- Run length -->
  <div class="panel" id="panel-runs">
    <div class="grid">
      <div class="card wide">
        <div class="card-header"><span class="card-title">Win rate by run length</span></div>
        <div id="ch-runlen"></div>
      </div>
      <div class="card wide">
        <div class="card-header"><span class="card-title">Run time vs floors reached</span></div>
        <div id="ch-runscatter"></div>
      </div>
    </div>
  </div>

  <!-- Run enders -->
  <div class="panel" id="panel-killers">
    <div class="grid">
      <div class="card wide">
        <div class="card-header"><span class="card-title">Top run enders</span></div>
        <div id="ch-killers"></div>
      </div>
    </div>
  </div>

  <!-- Progress -->
  <div class="panel" id="panel-progress">
    <div class="grid">
      <div class="card wide">
        <div class="card-header">
          <span class="card-title" id="blocks-title">Win rate per 5 runs</span>
          <div style="display:flex;align-items:center;gap:10px;">
            <span class="card-note">faded bar = incomplete batch</span>
            <div class="sort-toggle">
              <button class="sort-btn active" id="block-5"  onclick="setBlockSize(5)">5</button>
              <button class="sort-btn"        id="block-10" onclick="setBlockSize(10)">10</button>
              <button class="sort-btn"        id="block-20" onclick="setBlockSize(20)">20</button>
            </div>
          </div>
        </div>
        <div id="ch-blocks"></div>
      </div>
      <div class="card wide">
        <div class="card-header">
          <span class="card-title">Rolling win rate</span>
          <span class="card-note">10-run rolling average</span>
        </div>
        <div id="ch-progress"></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Run history</span><span class="card-note">recent 50 · hover for details</span></div>
        <div id="ch-streak"></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Act progression</span><span class="card-note">% of runs reaching each milestone</span></div>
        <div id="ch-acts"></div>
      </div>
    </div>
  </div>

</div>

<script>
const ALL_DATA    = {data_json};
const CHAR_COLORS = {colors_json};
const CHARS       = {chars_json};

// ── State ───────────────────────────────────────────────────────
let activeChar  = 'All';
let showBasics  = false;
let inclShort   = false;   // false = exclude runs < 5m  (default: excluded)
let inclLowAsc  = false;   // false = exclude A0–A4      (default: excluded)
let wrSort      = 'win_rate';
let pickSort    = 'picked';
let blockSize   = 5;

// Maps the two boolean toggles to a pre-computed slice key
const sliceKey = () => {{
  if ( inclShort &&  inclLowAsc) return 'raw';
  if (!inclShort &&  inclLowAsc) return 'no_short';
  if ( inclShort && !inclLowAsc) return 'high_asc';
  return 'filtered';  // default: both excluded
}};
const d = () => ALL_DATA[activeChar][sliceKey()];

// ── Plotly base layout ──────────────────────────────────────────
const L = {{
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor:  'rgba(0,0,0,0)',
  font: {{ family: "'Inter', sans-serif", color: '#4a4d60', size: 12 }},
  margin: {{ t: 8, b: 36, l: 160, r: 90 }},
  xaxis: {{
    gridcolor: 'rgba(255,255,255,0.04)',
    zerolinecolor: 'rgba(255,255,255,0.06)',
    tickfont: {{ color: '#4a4d60', size: 11 }},
  }},
  yaxis: {{
    gridcolor: 'rgba(255,255,255,0.04)',
    tickfont: {{ color: '#c8c8d8', size: 12 }},
    automargin: true,
  }},
  showlegend: false,
  hoverlabel: {{
    bgcolor: '#1a1d30', bordercolor: 'rgba(255,255,255,0.12)',
    font: {{ family: "'Inter', sans-serif", color: '#e8e8f0', size: 12 }},
  }},
}};
const CFG = {{ responsive: true, displayModeBar: false }};

// ── Color helpers ───────────────────────────────────────────────
const WIN_COLOR  = '#22c55e';
const LOSS_COLOR = '#ef4444';
const MID_COLOR  = '#f59e0b';

function wrColor(v) {{
  return v >= 55 ? WIN_COLOR : v >= 38 ? MID_COLOR : LOSS_COLOR;
}}

function wrGradient(values) {{
  const mx = Math.max(...values, 1);  // Ensure never divides by 0 (WRONG-1)
  return values.map(v => {{
    const t = v / mx;
    if (t < 0.5) {{
      const r = Math.round(239 + (245-239)*t*2), g = Math.round(68 + (158-68)*t*2), b = Math.round(68 + (11-68)*t*2);
      return `rgb(${{r}},${{g}},${{b}})`;
    }} else {{
      const tt = (t-0.5)*2;
      const r = Math.round(245 + (34-245)*tt), g = Math.round(158 + (197-158)*tt), b = Math.round(11 + (94-11)*tt);
      return `rgb(${{r}},${{g}},${{b}})`;
    }}
  }});
}}

// ── Generic horizontal bar ──────────────────────────────────────
function hbar(id, labels, values, text, colors, xTitle, height) {{
  // Use Plotly.react for efficient re-renders (PERF-6)
  Plotly.react(id, [{{
    type: 'bar', orientation: 'h',
    x: values, y: labels,
    marker: {{ color: colors, opacity: 0.92 }},
    text, textposition: 'outside',
    textfont: {{ color: '#4a4d60', size: 11, family: "'Inter', sans-serif" }},
    hovertemplate: '<b>%{{y}}</b><br>%{{x}}<extra></extra>',
    cliponaxis: false,
  }}], {{
    ...L,
    height: height || Math.max(280, labels.length * 36 + 60),
    margin: {{ ...L.margin, r: 110 }},
    xaxis: {{ ...L.xaxis, range: [0, Math.max(...values.map(v => +v||0)) * 1.28],
      title: {{ text: xTitle||'', font: {{ color: '#3a3d55', size: 11 }} }} }},
  }}, CFG);
}}

// ── Stats row ───────────────────────────────────────────────────
function renderStats() {{
  const s = d().summary;
  if (!s?.total_runs) {{ document.getElementById('stats-row').innerHTML = ''; return; }}
  const shortNote = inclShort ? '' : ' <span style="font-size:9px;color:#2a2d42;vertical-align:top;margin-left:2px" title="Runs under 5m excluded">excl. short</span>';
  document.getElementById('stats-row').innerHTML = [
    [s.total_runs,             'Runs'],
    [s.total_wins,             'Wins'],
    [s.win_rate_pct + '%',     'Win rate'],
    [s.total_hours + 'h',      'Played'],
    [s.avg_run_time_min + 'm', 'Avg run'],
    [s.avg_floors,             'Avg floors'],
  ].map(([v,l], i) =>
    `<div class="stat"><div class="stat-val">${{v}}${{i===0 ? shortNote : ''}}</div><div class="stat-label">${{l}}</div></div>`
  ).join('');
}}

// ── Win rate by character ────────────────────────────────────────
function renderWinRate() {{
  const rows = [...(d().win_by_char||[])].sort((a,b) => a.win_rate - b.win_rate);
  if (!rows.length) {{
    document.getElementById('ch-winrate').innerHTML = '<p class="empty">No data</p>';  // Clear stale chart (CORRUPT-5)
    return;
  }}
  Plotly.react('ch-winrate', [{{
    type: 'bar', orientation: 'h',
    x: rows.map(r => r.win_rate),
    y: rows.map(r => r.character),
    marker: {{ color: rows.map(r => CHAR_COLORS[r.character] || '#546e7a'), opacity: 0.85 }},
    text: rows.map(r => r.win_rate.toFixed(1) + '%  · ' + r.runs + ' runs'),
    textposition: 'outside',
    textfont: {{ color: '#4a4d60', size: 11 }},
    hovertemplate: '<b>%{{y}}</b><br>Win rate: %{{x:.1f}}%<extra></extra>',
    cliponaxis: false,
  }}], {{
    ...L, height: 280,
    margin: {{ t:8, b:36, l:120, r:140 }},
    xaxis: {{ ...L.xaxis, range: [0, 70],
      title: {{ text: 'Win rate %', font: {{ color:'#3a3d55', size:11 }} }} }},
  }}, CFG);
}}

// ── Floors histogram ─────────────────────────────────────────────
function renderFloors() {{
  const rows = d().floors || [];
  const wins   = rows.filter(r => r.win).map(r => r.floors);
  const losses = rows.filter(r => !r.win).map(r => r.floors);
  Plotly.react('ch-floors', [
    {{ type:'histogram', x: wins,   name:'Win',  marker:{{ color: WIN_COLOR,  opacity: 0.75 }},
       hovertemplate: 'Floor %{{x}}: %{{y}} wins<extra></extra>' }},
    {{ type:'histogram', x: losses, name:'Loss', marker:{{ color: LOSS_COLOR, opacity: 0.5  }},
       hovertemplate: 'Floor %{{x}}: %{{y}} losses<extra></extra>' }},
  ], {{
    ...L, barmode:'overlay', height: 280, showlegend: true,
    legend: {{ x:0.72, y:0.96, bgcolor:'rgba(0,0,0,0)', font:{{ color:'#888', size:12 }} }},
    margin: {{ t:8, b:36, l:40, r:20 }},
    xaxis: {{ ...L.xaxis, title:{{ text:'Floors', font:{{ color:'#3a3d55', size:11 }} }} }},
    yaxis: {{ ...L.yaxis, title:{{ text:'Runs',   font:{{ color:'#3a3d55', size:11 }} }} }},
  }}, CFG);
}}

// ── Card win rates ───────────────────────────────────────────────
function renderCardWR() {{
  const key = showBasics ? 'card_wr_all' : 'card_wr';
  const rows = d()[key] || [];
  const el = document.getElementById('ch-cardwr');
  if (!rows.length) {{ el.innerHTML = '<p class="empty">Not enough data</p>'; return; }}
  const sorted = [...rows].sort((a,b) => b[wrSort] - a[wrSort]).slice(0, 20);  // CORRUPT-2: Slice in JS after sorting
  const rev = [...sorted].reverse();
  const note = rows.length > 20 ? ` (top 20 of ${{rows.length}})` : '';  // WRONG-6
  hbar('ch-cardwr',
    rev.map(r => r.card),
    rev.map(r => r.win_rate),
    rev.map(r => r.win_rate.toFixed(1) + '%  · ' + r.runs),
    wrGradient(rev.map(r => r.win_rate)),
    'Win rate %'
  );
}}

// ── Card picks ───────────────────────────────────────────────────
function renderCardPicks() {{
  const key = showBasics ? 'card_picks_all' : 'card_picks';
  const rows = d()[key] || [];
  const el = document.getElementById('ch-cardpick');
  if (!rows.length) {{ el.innerHTML = '<p class="empty">Not enough data</p>'; return; }}
  const sorted = [...rows].sort((a,b) => b[pickSort] - a[pickSort]).slice(0, 20);  // CORRUPT-2: Slice in JS after sorting
  const rev = [...sorted].reverse();
  const max = Math.max(...rev.map(r => r[pickSort]), 1);  // WRONG-1: Ensure never divides by 0
  const colors = rev.map(r => {{
    const a = 0.35 + 0.65 * (r[pickSort] / max);
    return `rgba(124,106,247,${{a.toFixed(2)}})`;
  }});
  const note = rows.length > 20 ? ` (top 20 of ${{rows.length}})` : '';  // WRONG-6
  hbar('ch-cardpick',
    rev.map(r => r.card),
    rev.map(r => r.picked),
    rev.map(r => r.picked + '  (' + r.pick_rate + '%)'),
    colors,
    'Times picked'
  );
}}

// ── Relic win rates ──────────────────────────────────────────────
function renderRelicWR() {{
  const rows = d().relic_wr || [];
  const el = document.getElementById('ch-relicwr');
  if (!rows.length) {{ el.innerHTML = '<p class="empty">Not enough data</p>'; return; }}
  const sorted = [...rows].sort((a,b) => a.win_rate - b.win_rate);
  hbar('ch-relicwr',
    sorted.map(r => r.relic),
    sorted.map(r => r.win_rate),
    sorted.map(r => r.win_rate.toFixed(1) + '%  · ' + r.runs),
    wrGradient(sorted.map(r => r.win_rate)),
    'Win rate %',
    Math.max(320, sorted.length * 36 + 60)
  );
}}

// ── Run length — bucket bar ──────────────────────────────────────
function renderRunLength() {{
  const buckets = ALL_DATA[activeChar]._buckets || [];
  if (!buckets.length) {{
    document.getElementById('ch-runlen').innerHTML = '<p class="empty">No data</p>';
    return;
  }}
  Plotly.react('ch-runlen', [{{
    type: 'bar',
    x: buckets.map(b => b.bucket),
    y: buckets.map(b => b.win_rate),
    marker: {{ color: buckets.map(b => wrColor(b.win_rate)), opacity: 0.88 }},
    text: buckets.map(b => b.win_rate.toFixed(1) + '%<br>(' + b.count + ' runs)'),
    textposition: 'outside', textfont: {{ color: '#4a4d60', size: 11 }},
    hovertemplate: '<b>%{{x}}</b><br>Win rate: %{{y:.1f}}%<br>Runs: %{{customdata}}<extra></extra>',
    customdata: buckets.map(b => b.count),
    cliponaxis: false,
  }}], {{
    ...L, height: 300,
    margin: {{ t:8, b:50, l:40, r:20 }},
    xaxis: {{ ...L.xaxis, tickfont: {{ color:'#8880aa', size:13 }},
      title:{{ text:'Run length', font:{{ color:'#3a3d55', size:11 }} }} }},
    yaxis: {{ ...L.yaxis, range:[0, Math.max(...buckets.map(b=>b.win_rate))*1.25],
      title:{{ text:'Win rate %', font:{{ color:'#3a3d55', size:11 }} }} }},
  }}, CFG);
}}

// ── Run length — scatter ─────────────────────────────────────────
function renderRunScatter() {{
  const runLens = d().run_lengths || [];
  const wins   = runLens.filter(r => r.win);
  const losses = runLens.filter(r => !r.win);
  Plotly.react('ch-runscatter', [
    {{ type:'scatter', mode:'markers', name:'Win',
       x: wins.map(r => r.run_time_min), y: wins.map(r => r.floors),
       marker:{{ color: WIN_COLOR, size: 6, opacity: 0.75,
                 line:{{ color:'rgba(34,197,94,0.25)', width:1 }} }},
       hovertemplate: '<b>Win</b><br>%{{x}}m · %{{y}} floors<extra></extra>' }},
    {{ type:'scatter', mode:'markers', name:'Loss',
       x: losses.map(r => r.run_time_min), y: losses.map(r => r.floors),
       marker:{{ color: LOSS_COLOR, size: 6, opacity: 0.45,
                 line:{{ color:'rgba(239,68,68,0.15)', width:1 }} }},
       hovertemplate: '<b>Loss</b><br>%{{x}}m · %{{y}} floors<extra></extra>' }},
  ], {{
    ...L, height: 320, showlegend: true,
    legend:{{ x:0.85, y:0.05, bgcolor:'rgba(0,0,0,0)', font:{{ color:'#888', size:12 }} }},
    margin:{{ t:8, b:50, l:50, r:20 }},
    xaxis:{{ ...L.xaxis, title:{{ text:'Run time (m)', font:{{ color:'#3a3d55', size:11 }} }} }},
    yaxis:{{ ...L.yaxis, title:{{ text:'Floors reached', font:{{ color:'#3a3d55', size:11 }} }} }},
  }}, CFG);
}}

// ── Killers ──────────────────────────────────────────────────────
function renderKillers() {{
  const rows = d().killers || [];
  const el = document.getElementById('ch-killers');
  if (!rows.length) {{ el.innerHTML = '<p class="empty">No data</p>'; return; }}
  const sorted = [...rows].sort((a,b) => a.count - b.count);
  const max = Math.max(...sorted.map(r => r.count));
  const colors = sorted.map(r => {{
    const a = 0.4 + 0.6 * (r.count / max);
    return `rgba(239,68,68,${{a.toFixed(2)}})`;
  }});
  hbar('ch-killers',
    sorted.map(r => r.killer),
    sorted.map(r => r.count),
    sorted.map(r => String(r.count)),
    colors,
    'Times killed',
    Math.max(280, sorted.length * 36 + 60)
  );
}}

// ── Compute blocks from per-run progress data ────────────────────
function computeBlocks(prog, size) {{
  const blocks = [];
  for (let i = 0; i < prog.length; i += size) {{
    const slice = prog.slice(i, i + size);
    const wins  = slice.filter(r => r.win).length;
    blocks.push({{
      label:    '#' + (i + 1) + '–' + (i + slice.length),
      block_num: Math.floor(i / size) + 1,
      runs:     slice.length,
      wins,
      win_rate: +(wins / slice.length * 100).toFixed(1),
      partial:  slice.length < size,
    }});
  }}
  return blocks;
}}

// ── Block size toggle ────────────────────────────────────────────
function setBlockSize(n) {{
  blockSize = n;
  [5, 10, 20].forEach(s => {{
    document.getElementById('block-' + s).classList.toggle('active', s === n);
  }});
  document.getElementById('blocks-title').textContent = 'Win rate per ' + n + ' runs';
  renderBlocks();
}}

// ── Progress: per-N-run block bars ───────────────────────────────
function renderBlocks() {{
  const prog = d().progress || [];
  const blocks = computeBlocks(prog, blockSize);
  const el = document.getElementById('ch-blocks');
  if (!blocks.length) {{ el.innerHTML = '<p class="empty">Not enough data</p>'; return; }}

  // Moving average over the block win rates (window = 3, or fewer if not enough blocks)
  const winRates = blocks.map(b => b.win_rate);
  const maWindow = Math.min(3, blocks.length);
  const maValues = winRates.map((_, i) => {{
    const start = Math.max(0, i - maWindow + 1);
    const slice = winRates.slice(start, i + 1);
    return +(slice.reduce((a, b) => a + b, 0) / slice.length).toFixed(1);
  }});
  const labels = blocks.map(b => b.label);

  Plotly.react('ch-blocks', [
    // Bars
    {{
      type: 'bar',
      x: labels,
      y: winRates,
      marker: {{
        color:   blocks.map(b => wrColor(b.win_rate)),
        opacity: blocks.map(b => b.partial ? 0.45 : 0.78),
      }},
      text: blocks.map(b => b.win_rate.toFixed(0) + '%  (' + b.wins + '/' + b.runs + ')'),
      textposition: 'outside',
      textfont: {{ color: '#4a4d60', size: 11 }},
      customdata: blocks.map(b => [b.wins, b.runs]),
      hovertemplate: '<b>%{{x}}</b><br>%{{customdata[0]}}/%{{customdata[1]}} wins · %{{y:.1f}}%<extra></extra>',
      cliponaxis: false,
      showlegend: false,
    }},
    // Moving average line
    {{
      type: 'scatter', mode: 'lines+markers',
      x: labels, y: maValues,
      line: {{ color: '#7c6af7', width: 2.5, shape: 'spline', smoothing: 0.8 }},
      marker: {{ color: '#7c6af7', size: 7, symbol: 'circle',
                 line: {{ color: '#fff', width: 1 }} }},
      hovertemplate: '<b>%{{x}}</b><br>Moving avg: <b>%{{y:.1f}}%</b><extra></extra>',
      showlegend: false,
    }},
  ], {{
    ...L, height: 260,
    margin: {{ t: 16, b: 44, l: 50, r: 20 }},
    xaxis: {{ ...L.xaxis, tickfont: {{ color: '#8880aa', size: 12 }} }},
    yaxis: {{
      gridcolor: 'rgba(255,255,255,0.04)',
      tickfont: {{ color: '#c8c8d8', size: 11 }},
      autorange: false,
      range: [0, 110],
      dtick: 20,
      title: {{ text: 'Win rate %', font: {{ color: '#3a3d55', size: 11 }} }},
    }},
  }}, CFG);
}}

// ── Progress: rolling win rate line ──────────────────────────────
function renderProgress() {{
  const prog = d().progress || [];
  const el = document.getElementById('ch-progress');
  if (prog.length < 2) {{ el.innerHTML = '<p class="empty">Not enough data</p>'; return; }}

  const n = prog.length;
  Plotly.react('ch-progress', [
    // 50% reference
    {{ type:'scatter', mode:'lines',
       x:[1, n], y:[50, 50],
       line:{{ color:'rgba(255,255,255,0.07)', width:1, dash:'dot' }},
       hoverinfo:'skip', showlegend:false }},
    // Area fill
    {{ type:'scatter', mode:'none',
       x: prog.map(p => p.i), y: prog.map(p => p.rolling_wr),
       fill:'tozeroy', fillcolor:'rgba(124,106,247,0.07)',
       hoverinfo:'skip', showlegend:false }},
    // Line
    {{ type:'scatter', mode:'lines',
       x: prog.map(p => p.i), y: prog.map(p => p.rolling_wr),
       line:{{ color:'#7c6af7', width:2.5, shape:'spline', smoothing:0.5 }},
       customdata: prog.map(p => p.date),
       hovertemplate: 'Run %{{x}}<br>%{{customdata}}<br>Rolling WR: <b>%{{y:.1f}}%</b><extra></extra>',
       showlegend:false }},
  ], {{
    ...L, height: 260,
    margin: {{ t: 8, b: 44, l: 50, r: 20 }},
    xaxis: {{ ...L.xaxis, range: [1, n],
      title: {{ text: 'Run #', font: {{ color: '#3a3d55', size: 11 }} }} }},
    yaxis: {{
      gridcolor: 'rgba(255,255,255,0.04)',
      tickfont: {{ color: '#c8c8d8', size: 11 }},
      autorange: false,
      range: [0, 105],
      dtick: 20,
      title: {{ text: 'Win rate %', font: {{ color: '#3a3d55', size: 11 }} }},
    }},
  }}, CFG);
}}

// ── Run history streak widget ────────────────────────────────────
function renderStreakWidget() {{
  const prog = d().progress || [];
  const el = document.getElementById('ch-streak');
  if (!prog.length) {{ el.innerHTML = '<p class="empty">Not enough data</p>'; return; }}

  // Current streak (from end)
  const lastWin = prog[prog.length - 1].win;
  let curStreak = 0;
  for (let i = prog.length - 1; i >= 0 && prog[i].win === lastWin; i--) curStreak++;

  // Best win streak
  let bestStreak = 0, run = 0;
  for (const p of prog) {{
    run = p.win ? run + 1 : 0;
    bestStreak = Math.max(bestStreak, run);
  }}

  // Win rate last 10
  const last10 = prog.slice(-10);
  const wr10 = last10.length ? +(last10.filter(p => p.win).length / last10.length * 100).toFixed(0) : 0;

  // Dot grid — most recent 50
  const recent = prog.slice(-50);
  const streakStart = recent.length - curStreak;
  const dots = recent.map((p, i) => {{
    const inStreak = i >= streakStart;
    const color = p.win ? 'color:#22c55e' : 'color:#ef4444';
    const cls = 'run-dot ' + (p.win ? 'win' : 'loss') + (inStreak ? ' in-streak' : '');
    return `<div class="${{cls}}" style="${{color}}" title="${{p.win ? '✓ Win' : '✗ Loss'}}${{p.date ? ' · ' + p.date : ''}}"></div>`;
  }}).join('');

  const numClass = lastWin ? 'streak-num good' : 'streak-num bad';
  const streakLabel = (lastWin ? '🔥 Win' : '💀 Loss') + ' streak';

  el.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px">
      <div class="streak-stat">
        <div class="${{numClass}}">${{curStreak}}</div>
        <div class="streak-label">${{streakLabel}}</div>
      </div>
      <div class="streak-stat">
        <div class="streak-num">${{bestStreak}}</div>
        <div class="streak-label">Best win streak</div>
      </div>
      <div class="streak-stat">
        <div class="streak-num" style="background:${{wr10>=50?'linear-gradient(135deg,#22c55e,#06b6d4)':'linear-gradient(135deg,#ef4444,#f59e0b)'}};-webkit-background-clip:text">${{wr10}}%</div>
        <div class="streak-label">Last 10 win rate</div>
      </div>
    </div>
    <div class="streak-grid">${{dots}}</div>
    <div style="display:flex;justify-content:space-between;margin-top:10px">
      <span style="font-size:10px;color:#2a2d42;letter-spacing:0.5px">← older</span>
      <span style="font-size:10px;color:#2a2d42;letter-spacing:0.5px">recent →</span>
    </div>`;
}}

// ── Act progression ──────────────────────────────────────────────
function renderActProgression() {{
  const rows = d().act_progression || [];
  const el = document.getElementById('ch-acts');
  if (!rows.length) {{ el.innerHTML = '<p class="empty">No data</p>'; return; }}

  const colors = ['#4fa3e0', '#b06ae8', '#22c55e'];
  hbar('ch-acts',
    rows.map(r => r.label),
    rows.map(r => r.pct),
    rows.map(r => r.pct.toFixed(1) + '%  (' + r.count + ' runs)'),
    colors.slice(0, rows.length),
    '% of runs',
    Math.max(180, rows.length * 56 + 60)
  );
}}

// ── Render all ───────────────────────────────────────────────────
function renderAll() {{
  renderStats();
  renderWinRate();
  renderFloors();
  renderCardWR();
  renderCardPicks();
  renderRelicWR();
  renderRunLength();
  renderRunScatter();
  renderKillers();
  renderBlocks();
  renderProgress();
  renderStreakWidget();
  renderActProgression();
}}

// ── Character buttons ────────────────────────────────────────────
function setChar(char) {{
  activeChar = char;
  document.querySelectorAll('#char-btns .pill').forEach(b => {{
    const isActive = b.dataset.char === char;
    b.classList.toggle('active', isActive);
    if (isActive && CHAR_COLORS[char]) {{
      b.style.background = CHAR_COLORS[char] + '22';
      b.style.borderColor = CHAR_COLORS[char];
      b.style.color = CHAR_COLORS[char];
    }} else {{
      b.style.background = '';
      b.style.borderColor = '';
      b.style.color = '';
    }}
  }});
  renderAll();
}}

// ── Toggle: short run exclusion ──────────────────────────────────
function toggleShort() {{
  inclShort = !inclShort;
  const btn = document.getElementById('short-btn');
  btn.textContent = inclShort ? 'Short runs included' : 'Short runs excluded';
  btn.classList.toggle('on-red', inclShort);
  renderAll();
}}

// ── Toggle: A10-only filter ──────────────────────────────────────
function toggleAsc() {{
  inclLowAsc = !inclLowAsc;
  const btn = document.getElementById('asc-btn');
  btn.textContent = inclLowAsc ? 'All asc included' : 'A10 only';
  btn.classList.toggle('on-red', inclLowAsc);
  renderAll();
}}

// ── Toggle: basics ───────────────────────────────────────────────
function toggleBasics() {{
  showBasics = !showBasics;
  const btn = document.getElementById('basics-btn');
  btn.textContent = showBasics ? 'Basics shown' : 'Basics hidden';
  btn.classList.toggle('on-amber', showBasics);
  renderCardWR();
  renderCardPicks();
}}

// ── Sort toggles ─────────────────────────────────────────────────
function setWRSort(key) {{
  wrSort = key;
  document.getElementById('wr-sort-wr').classList.toggle('active', key === 'win_rate');
  document.getElementById('wr-sort-count').classList.toggle('active', key === 'runs');
  renderCardWR();
}}

function setPickSort(key) {{
  pickSort = key;
  document.getElementById('pick-sort-picked').classList.toggle('active', key === 'picked');
  document.getElementById('pick-sort-pickrate').classList.toggle('active', key === 'pick_rate');
  renderCardPicks();
}}

// ── Tab switching ────────────────────────────────────────────────
function showTab(tab, el) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('panel-' + tab).classList.add('active');
  el.classList.add('active');
}}

// ── Init ─────────────────────────────────────────────────────────
const charContainer = document.getElementById('char-btns');
CHARS.forEach(char => {{
  const btn = document.createElement('button');
  btn.className = 'pill' + (char === 'All' ? ' active' : '');
  btn.dataset.char = char;
  btn.textContent = char;
  if (char === 'All') {{
    btn.style.background = 'rgba(124,106,247,0.12)';
    btn.style.borderColor = '#7c6af7';
    btn.style.color = '#c4bcff';
  }}
  btn.onclick = () => setChar(char);
  charContainer.appendChild(btn);
}});

renderAll();
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
