"""Relic analysis."""
from collections import Counter
import pandas as pd
from sts2_analysis.models.run import Run


def relic_win_rates(runs: list[Run], min_runs: int = 5) -> pd.DataFrame:
    relic_wins: Counter = Counter()
    relic_runs: Counter = Counter()
    for run in runs:
        for relic_id in set(r.id for r in run.relics):
            relic_runs[relic_id] += 1
            if run.win:
                relic_wins[relic_id] += 1
    records = [
        {"relic": r.replace("RELIC.", ""), "runs": relic_runs[r],
         "wins": relic_wins[r], "win_rate": round(relic_wins[r] / relic_runs[r] * 100, 1)}
        for r in relic_runs if relic_runs[r] >= min_runs
    ]
    return pd.DataFrame(records).sort_values("win_rate", ascending=False)


def relic_frequency(runs: list[Run]) -> pd.DataFrame:
    counter: Counter = Counter()
    for run in runs:
        for relic_id in set(r.id for r in run.relics):
            counter[relic_id] += 1
    df = pd.DataFrame(counter.most_common(), columns=["relic", "count"])
    df["relic"] = df["relic"].str.replace("RELIC.", "")
    return df


def floor_acquired(runs: list[Run]) -> pd.DataFrame:
    """When (which floor) relics are typically acquired."""
    records = []
    for run in runs:
        for relic in run.relics:
            records.append({
                "relic": relic.id.replace("RELIC.", ""),
                "floor": relic.floor_added_to_deck,
                "character": run.character.replace("CHARACTER.", ""),
            })
    return pd.DataFrame(records)
