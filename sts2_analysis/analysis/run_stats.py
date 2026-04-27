"""High-level run statistics."""
import pandas as pd
from sts2_analysis.models.run import Run


def runs_to_dataframe(runs: list[Run]) -> pd.DataFrame:
    records = []
    for r in runs:
        records.append({
            "character": r.character.replace("CHARACTER.", ""),
            "win": r.win,
            "ascension": r.ascension,
            "game_mode": r.game_mode,
            "floors_reached": r.floors_reached,
            "acts_completed": len(r.acts),
            "run_time_min": round(r.run_time_minutes, 1),
            "deck_size": len(r.deck),
            "relic_count": len(r.relics),
            "seed": r.seed,
            "build_id": r.build_id,
            "killed_by": r.killed_by_encounter.replace("ENCOUNTER.", "") if not r.win else "—",
            "start_time": r.datetime,
            "was_abandoned": r.was_abandoned,
        })
    return pd.DataFrame(records)


def win_rate_by(df: pd.DataFrame, group_by: str) -> pd.DataFrame:
    return (
        df.groupby(group_by)["win"]
        .agg(wins="sum", runs="count")
        .assign(win_rate=lambda x: (x["wins"] / x["runs"] * 100).round(1))
        .sort_values("win_rate", ascending=False)
        .reset_index()
    )


def summary_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "total_runs": 0,
            "total_wins": 0,
            "win_rate_pct": 0.0,
            "total_hours": 0.0,
            "avg_run_time_min": 0.0,
            "avg_floors": 0.0,
            "characters_played": 0,
            "most_played_char": None,
        }
    return {
        "total_runs": len(df),
        "total_wins": int(df["win"].sum()),
        "win_rate_pct": round(df["win"].mean() * 100, 1),
        "total_hours": round(df["run_time_min"].sum() / 60, 1),
        "avg_run_time_min": round(df["run_time_min"].mean(), 1),
        "avg_floors": round(df["floors_reached"].mean(), 1),
        "characters_played": df["character"].nunique(),
        "most_played_char": df["character"].value_counts().index[0],
    }
