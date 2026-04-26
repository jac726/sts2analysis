"""
Visualization utilities for STS2 run data.
Uses plotly for interactive charts and matplotlib/seaborn for static plots.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_win_rate_by_character(df: pd.DataFrame) -> go.Figure:
    win_data = (
        df.groupby("character")["victory"]
        .agg(wins="sum", runs="count")
        .assign(win_rate=lambda x: x["wins"] / x["runs"] * 100)
        .reset_index()
        .sort_values("win_rate", ascending=True)
    )
    fig = px.bar(
        win_data, x="win_rate", y="character", orientation="h",
        title="Win Rate by Character",
        labels={"win_rate": "Win Rate (%)", "character": "Character"},
        color="win_rate", color_continuous_scale="RdYlGn",
        text=win_data["runs"].apply(lambda n: f"{n} runs"),
    )
    fig.update_traces(textposition="outside")
    return fig


def plot_floor_distribution(df: pd.DataFrame) -> go.Figure:
    fig = px.histogram(
        df, x="floor_reached", color="victory",
        title="Floor Reached Distribution",
        labels={"floor_reached": "Floor Reached", "count": "Runs"},
        barmode="overlay", opacity=0.75,
        color_discrete_map={True: "#4caf50", False: "#f44336"},
    )
    return fig


def plot_run_timeline(df: pd.DataFrame) -> go.Figure:
    """Win/loss over time (if timestamp available)."""
    if "timestamp" not in df.columns or df["timestamp"].isna().all():
        return go.Figure().update_layout(title="No timestamp data available")
    _df = df.copy()
    _df["date"] = pd.to_datetime(_df["timestamp"], unit="s")
    _df = _df.sort_values("date")
    _df["cumulative_wins"] = _df["victory"].cumsum()
    _df["cumulative_runs"] = range(1, len(_df) + 1)
    _df["rolling_wr"] = _df["victory"].rolling(10, min_periods=1).mean() * 100
    fig = px.line(
        _df, x="date", y="rolling_wr",
        title="Rolling Win Rate Over Time (10-run window)",
        labels={"rolling_wr": "Win Rate (%)", "date": "Date"},
    )
    return fig


def plot_card_frequencies(card_df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    top = card_df.head(top_n)
    fig = px.bar(
        top, x="pick_rate", y="card", orientation="h",
        title=f"Top {top_n} Most Picked Cards",
        labels={"pick_rate": "Pick Rate", "card": "Card"},
        color="pick_rate", color_continuous_scale="Blues",
    )
    return fig


def plot_relic_win_rates(relic_df: pd.DataFrame, min_runs: int = 5) -> go.Figure:
    filtered = relic_df[relic_df["runs"] >= min_runs].head(25)
    fig = px.bar(
        filtered, x="win_rate", y="relic", orientation="h",
        title=f"Relic Win Rates (min {min_runs} runs)",
        labels={"win_rate": "Win Rate", "relic": "Relic"},
        color="win_rate", color_continuous_scale="RdYlGn",
    )
    return fig


def overview_dashboard(df: pd.DataFrame, card_df: pd.DataFrame, relic_df: pd.DataFrame) -> go.Figure:
    """4-panel overview dashboard."""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=["Win Rate by Character", "Floor Distribution",
                        "Top 15 Cards", "Top Relic Win Rates"],
    )
    # panel 1: win rate by character
    wr = (
        df.groupby("character")["victory"]
        .agg(wins="sum", runs="count")
        .assign(win_rate=lambda x: x["wins"] / x["runs"] * 100)
        .reset_index()
    )
    fig.add_trace(go.Bar(x=wr["win_rate"], y=wr["character"], orientation="h",
                         name="Win Rate"), row=1, col=1)
    # panel 2: floor dist
    for won, color in [(True, "#4caf50"), (False, "#f44336")]:
        sub = df[df["victory"] == won]["floor_reached"].dropna()
        fig.add_trace(go.Histogram(x=sub, name="Win" if won else "Loss",
                                   marker_color=color, opacity=0.7), row=1, col=2)
    # panel 3: top cards
    top_cards = card_df.head(15)
    fig.add_trace(go.Bar(x=top_cards["pick_rate"], y=top_cards["card"],
                         orientation="h", name="Pick Rate"), row=2, col=1)
    # panel 4: relic win rates
    top_relics = relic_df[relic_df["runs"] >= 3].head(15)
    fig.add_trace(go.Bar(x=top_relics["win_rate"], y=top_relics["relic"],
                         orientation="h", name="Relic WR"), row=2, col=2)
    fig.update_layout(height=800, title_text="STS2 Run Analysis Dashboard", showlegend=False)
    return fig
