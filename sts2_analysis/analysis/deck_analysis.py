"""Deck and card analysis."""
from collections import Counter
import pandas as pd
from sts2_analysis.models.run import Run

# Thresholds for card analysis (must match dashboard.py for consistency) (WRONG-7)
CARD_MIN_APPEARANCES_OFFER = 5  # For offer-vs-pick analysis
CARD_MIN_APPEARANCES_WIN_RATE = 10  # For final-deck win-rate analysis


def card_pick_rates(runs: list[Run]) -> pd.DataFrame:
    """How often each card ends up in the final deck. (Aka 'card appearance rate' or 'inclusion rate', not the pick rate at offer screens - see card_offer_vs_pick for that.) (WRONG-5)"""
    counter: Counter = Counter()
    for run in runs:
        for card_id in set(r.id for r in run.deck):
            counter[card_id] += 1
    total = len(runs)
    df = pd.DataFrame(counter.most_common(), columns=["card", "appearances"])
    df["pick_rate"] = (df["appearances"] / total * 100).round(1)
    df["card"] = df["card"].str.replace("CARD.", "")
    return df


def card_win_rates(runs: list[Run], min_appearances: int = 10) -> pd.DataFrame:
    """Win rate for runs containing each card."""
    card_wins: Counter = Counter()
    card_runs: Counter = Counter()
    for run in runs:
        for card_id in set(r.id for r in run.deck):
            card_runs[card_id] += 1
            if run.win:
                card_wins[card_id] += 1
    records = [
        {"card": c.replace("CARD.", ""), "runs": card_runs[c],
         "wins": card_wins[c], "win_rate": round(card_wins[c] / card_runs[c] * 100, 1)}
        for c in card_runs if card_runs[c] >= min_appearances
    ]
    if not records:
        return pd.DataFrame(columns=["card", "runs", "wins", "win_rate"])
    return pd.DataFrame(records).sort_values("win_rate", ascending=False)


def card_offer_vs_pick(runs: list[Run]) -> pd.DataFrame:
    """For cards offered at reward screens, how often were they picked?"""
    offered: Counter = Counter()
    picked: Counter = Counter()
    for run in runs:
        for choice in run.all_card_choices:
            cid = choice.card_id.replace("CARD.", "")
            if not cid:  # Skip empty card IDs (CORRUPT-6)
                continue
            offered[cid] += 1
            if choice.was_picked:
                picked[cid] += 1
    records = [
        {"card": c, "offered": offered[c], "picked": picked.get(c, 0),
         "pick_rate": round(picked.get(c, 0) / offered[c] * 100, 1)}
        for c in offered if offered[c] >= 5
    ]
    if not records:
        return pd.DataFrame(columns=["card", "offered", "picked", "pick_rate"])
    return pd.DataFrame(records).sort_values("pick_rate", ascending=False)


def deck_size_by_outcome(runs: list[Run]) -> pd.DataFrame:
    return pd.DataFrame([
        {"deck_size": len(r.deck), "win": r.win, "character": r.character.replace("CHARACTER.", "")}
        for r in runs
    ])
