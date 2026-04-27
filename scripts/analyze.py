#!/usr/bin/env python3
"""
CLI entry point for STS2 analysis.

Usage:
  python scripts/analyze.py analyze --saves-dir /path/to/history
  python scripts/analyze.py inspect --saves-dir /path/to/history
"""
import sys
from pathlib import Path
import click

sys.path.insert(0, str(Path(__file__).parent.parent))

from sts2_analysis.parser.save_parser import load_all_runs
from sts2_analysis.models.run import Run
from sts2_analysis.analysis.run_stats import runs_to_dataframe, win_rate_by, summary_stats
from sts2_analysis.analysis.deck_analysis import card_pick_rates, card_win_rates, card_offer_vs_pick
from sts2_analysis.analysis.relic_tracker import relic_win_rates

try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False


def _print_table(title, rows, cols):
    if USE_RICH:
        t = Table(title=title)
        for c in cols:
            t.add_column(c, style="cyan")
        for row in rows:
            t.add_row(*[str(v) for v in row])
        console.print(t)
    else:
        print(f"\n=== {title} ===")
        print("  ".join(f"{c:20s}" for c in cols))
        for row in rows:
            print("  ".join(f"{str(v):20s}" for v in row))


@click.group()
def cli():
    """STS2 Save File Analyzer"""
    pass


@cli.command()
@click.option("--saves-dir", required=True, help="Path to your STS2 history folder")
@click.option("--output", default="dashboard.html", help="Output HTML file for Plotly dashboard")
@click.option("--min-appearances", default=20, help="Min run count for card/relic stats")
def analyze(saves_dir, output, min_appearances):
    """Load saves, print stats, and (optionally) generate a Plotly dashboard."""
    print(f"Loading saves from: {saves_dir}")
    raw = load_all_runs(saves_dir)
    if not raw:
        print("No .run files found.")
        return

    # Skip co-op runs where we can't identify which player's data is ours (CORRUPT-4)
    runs = [Run.from_dict(r) for r in raw if not (r.get("game_mode") == "coop" or len(r.get("players", [])) > 1)]
    df = runs_to_dataframe(runs)
    s = summary_stats(df)

    _print_table("Summary", [(k, v) for k, v in s.items()], ["Metric", "Value"])

    wr = win_rate_by(df, "character")
    _print_table("Win Rate by Character",
                 [(r.character, r.wins, r.runs, f"{r.win_rate}%") for _, r in wr.iterrows()],
                 ["Character", "Wins", "Runs", "Win Rate"])

    cwr = card_win_rates(runs, min_appearances=min_appearances).head(15)
    _print_table(f"Top Cards by Win Rate (min {min_appearances})",
                 [(r.card, r.runs, r.wins, f"{r.win_rate}%") for _, r in cwr.iterrows()],
                 ["Card", "Runs", "Wins", "Win Rate"])

    rwr = relic_win_rates(runs, min_runs=15).head(15)
    _print_table("Top Relics by Win Rate (min 15 runs)",
                 [(r.relic, r.runs, r.wins, f"{r.win_rate}%") for _, r in rwr.iterrows()],
                 ["Relic", "Runs", "Wins", "Win Rate"])

    # Generate dashboard
    try:
        from sts2_analysis.viz.dashboard import overview_dashboard
        overview_dashboard(runs, output)
        print(f"\nDashboard saved to: {output}")
    except ImportError:
        print("\n[info] Install plotly to generate the HTML dashboard: pip install plotly")


@cli.command()
@click.option("--saves-dir", required=True, help="Path to your STS2 history folder")
@click.option("--n", default=1, help="Number of run files to inspect")
def inspect(saves_dir, n):
    """Print raw keys from save files — useful when exploring new schema fields."""
    # PERF-7: Stream from glob and break after n instead of loading all
    from sts2_analysis.parser.save_parser import load_run
    from pathlib import Path
    saves_dir = Path(saves_dir)
    count = 0
    for path in sorted(saves_dir.glob("*.run")):
        if count >= n:
            break
        try:
            run_data = load_run(path)
            count += 1
        except Exception as e:
            print(f"[warn] Could not parse {path.name}: {e}")
            continue
        # Move the loop body outside
        i = count - 1
        print(f"\n=== {Path(run_data.get('_source_file','')).name} ===")
        for k, v in run_data.items():
            if k == "_source_file":
                continue
            if isinstance(v, list):
                print(f"  {k}: list[{len(v)}]")
            elif isinstance(v, dict):
                print(f"  {k}: dict({list(v.keys())[:5]})")
            else:
                print(f"  {k}: {type(v).__name__} = {repr(v)[:80]}")


if __name__ == "__main__":
    cli()
