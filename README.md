# STS2 Run Analyzer

A Python toolkit for analyzing your **Slay the Spire 2** save data — win rates, card performance, relic tracking, and interactive dashboards.

## Save File Location

Save files live at:
```
C:\Program Files (x86)\Steam\userdata\<steam_id>\2868840\remote\profile1\saves\history\
```
Each run is stored as a timestamped `.run` JSON file (e.g. `1772733327.run`).

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/sts2-analysis.git
cd sts2-analysis
pip install -r requirements.txt
```

## Quick Start

```bash
# Print a stats summary + generate an HTML dashboard
python scripts/analyze.py analyze \
  --saves-dir "C:\Program Files (x86)\Steam\userdata\YOUR_STEAM_ID\2868840\remote\profile1\saves\history" \
  --output dashboard.html

# Inspect raw keys of a single save file (useful for exploring new fields)
python scripts/analyze.py inspect \
  --saves-dir "C:\...\history"
```

Or open the Jupyter notebook for interactive exploration:
```bash
jupyter notebook notebooks/exploration.ipynb
```

## Data Available Per Run

| Field | Description |
|---|---|
| `win` | Whether the run was won |
| `ascension` | Ascension level |
| `game_mode` | `standard`, daily, etc. |
| `seed` | Run seed string |
| `run_time` | Total playtime in seconds |
| `start_time` | Unix timestamp |
| `killed_by_encounter` | What ended the run |
| `acts` | Act IDs traversed |
| `players[].character` | Character class |
| `players[].deck` | Final deck with per-card floor acquired |
| `players[].relics` | Relics with floor acquired |
| `map_point_history` | Full per-floor timeline |

### Per-floor data (`map_point_history`)
Each floor records: HP, gold, damage taken, card choices (offered + picked), cards gained, encounter ID, turns taken.

## Project Structure

```
sts2-analysis/
├── sts2_analysis/
│   ├── parser/        # Load .run JSON files
│   ├── models/        # Run, CardEntry, RelicEntry, FloorStats dataclasses
│   ├── analysis/      # run_stats, deck_analysis, relic_tracker
│   └── viz/           # Plotly dashboard generation
├── notebooks/
│   └── exploration.ipynb
├── scripts/
│   └── analyze.py     # CLI entry point
└── data/
    └── sample_saves/  # (gitignored) put .run files here for testing
```

## Sample Stats (445 runs, 196 hours)

| Metric | Value |
|---|---|
| Win rate | 29.7% |
| Avg run time | 26.4 min |
| Avg floors reached | 30.5 |
| Most played character | Regent |
| Best win-rate character | Silent (42.9%) |
| Top win-rate card | Backflip (64.5%, 31 appearances) |
| Top win-rate relic | Tungsten Rod (76.5%, 17 appearances) |

## Contributing

The save schema is versioned (`schema_version` field, currently v8). If you discover new fields after a patch, add them to `sts2_analysis/models/run.py` and open a PR.
