# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
# ---

# %% [markdown]
# # STS2 Run Analysis — Exploration Notebook
# Interactive exploration of your Slay the Spire 2 save data.

# %%
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(''), '..'))

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from collections import Counter

from sts2_analysis.parser.save_parser import load_all_runs
from sts2_analysis.models.run import Run
from sts2_analysis.analysis.run_stats import runs_to_dataframe, win_rate_by, summary_stats
from sts2_analysis.analysis.deck_analysis import card_pick_rates, card_win_rates, card_offer_vs_pick, deck_size_by_outcome
from sts2_analysis.analysis.relic_tracker import relic_win_rates, relic_frequency

sns.set_theme(style="darkgrid")
plt.rcParams["figure.figsize"] = (12, 5)

# %% [markdown]
# ## Load Your Saves
# Update `SAVES_DIR` to point to your history folder.

# %%
# SAVES_DIR = r"C:\Program Files (x86)\Steam\userdata\YOUR_STEAM_ID\2868840\remote\profile1\saves\history"
SAVES_DIR = r"C:\Program Files (x86)\Steam\userdata\137814448\2868840\remote\profile1\saves\history"

raw = load_all_runs(SAVES_DIR)
runs = [Run.from_dict(r) for r in raw]
df = runs_to_dataframe(runs)

print(f"Loaded {len(runs)} runs")
df.head()

# %% [markdown]
# ## Summary Stats

# %%
s = summary_stats(df)
for k, v in s.items():
    print(f"{k:30s}: {v}")

# %% [markdown]
# ## Win Rate by Character

# %%
wr = win_rate_by(df, "character").sort_values("win_rate")
fig, ax = plt.subplots()
bars = ax.barh(wr["character"], wr["win_rate"], color=sns.color_palette("RdYlGn", len(wr)))
ax.bar_label(bars, labels=[f'{v:.1f}%  ({r} runs)' for v, r in zip(wr["win_rate"], wr["runs"])], padding=4)
ax.set_xlabel("Win Rate (%)")
ax.set_title("Win Rate by Character")
ax.set_xlim(0, 60)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Win Rate Over Time (rolling 20-run window)

# %%
df_time = df.sort_values("start_time").copy()
df_time["rolling_wr"] = df_time["win"].rolling(20, min_periods=5).mean() * 100
fig, ax = plt.subplots()
ax.plot(df_time["start_time"], df_time["rolling_wr"], linewidth=2)
ax.axhline(df["win"].mean() * 100, color="gray", linestyle="--", label=f'Overall {df["win"].mean()*100:.1f}%')
ax.set_ylabel("Win Rate (%, 20-run window)")
ax.set_title("Win Rate Progression Over Time")
ax.legend()
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Deck Size Distribution (Wins vs Losses)

# %%
ds = deck_size_by_outcome(runs)
fig, ax = plt.subplots()
for won, color, label in [(True, "#4caf50", "Win"), (False, "#f44336", "Loss")]:
    sub = ds[ds["win"] == won]["deck_size"]
    ax.hist(sub, bins=range(10, 45), alpha=0.6, color=color, label=label, density=True)
ax.set_xlabel("Deck Size")
ax.set_ylabel("Density")
ax.set_title("Deck Size Distribution: Wins vs Losses")
ax.legend()
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Top Cards by Win Rate

# %%
cwr = card_win_rates(runs, min_appearances=20).head(20)
fig, ax = plt.subplots(figsize=(12, 7))
palette = sns.color_palette("RdYlGn", len(cwr))
bars = ax.barh(cwr["card"][::-1], cwr["win_rate"][::-1], color=palette)
ax.bar_label(bars, labels=[f'{v:.0f}%  (n={r})' for v, r in zip(cwr["win_rate"][::-1], cwr["runs"][::-1])], padding=4)
ax.set_xlabel("Win Rate (%)")
ax.set_title("Top 20 Cards by Win Rate (min 20 appearances)")
ax.set_xlim(0, 80)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Most-Picked Cards at Reward Screens

# %%
cop = card_offer_vs_pick(runs).head(20)
fig, ax = plt.subplots(figsize=(12, 7))
ax.barh(cop["card"][::-1], cop["pick_rate"][::-1], color=sns.color_palette("Blues_r", len(cop)))
ax.set_xlabel("Pick Rate (%)")
ax.set_title("Top 20 Cards by Pick Rate at Reward Screens")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Top Relics by Win Rate

# %%
rwr = relic_win_rates(runs, min_runs=15).head(20)
fig, ax = plt.subplots(figsize=(12, 7))
palette = sns.color_palette("RdYlGn", len(rwr))
bars = ax.barh(rwr["relic"][::-1], rwr["win_rate"][::-1], color=palette)
ax.bar_label(bars, labels=[f'{v:.0f}%  (n={r})' for v, r in zip(rwr["win_rate"][::-1], rwr["runs"][::-1])], padding=4)
ax.set_xlabel("Win Rate (%)")
ax.set_title("Top 20 Relics by Win Rate (min 15 appearances)")
ax.set_xlim(0, 100)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Worst Killers

# %%
losses = df[~df["win"]]
top_killers = losses["killed_by"].value_counts().head(15)
fig, ax = plt.subplots()
top_killers[::-1].plot(kind="barh", ax=ax, color="#f44336")
ax.set_xlabel("Times Killed")
ax.set_title("Top 15 Run Enders")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## HP Timeline for a Single Run

# %%
# Pick a winning run to visualize
winning_runs = [r for r in runs if r.win]
if winning_runs:
    sample = winning_runs[0]
    floors = [f.floor for f in sample.floor_history]
    hp = [f.current_hp for f in sample.floor_history]
    max_hp = [f.max_hp for f in sample.floor_history]
    dmg = [f.damage_taken for f in sample.floor_history]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
    ax1.fill_between(floors, max_hp, alpha=0.2, label="Max HP", color="blue")
    ax1.plot(floors, hp, marker="o", markersize=3, label="Current HP", color="green")
    ax1.set_ylabel("HP")
    ax1.set_title(f"Winning Run: {sample.character.replace('CHARACTER.', '')} — {sample.seed}")
    ax1.legend()
    
    ax2.bar(floors, dmg, color="#f44336", alpha=0.7)
    ax2.set_xlabel("Floor")
    ax2.set_ylabel("Damage Taken")
    ax2.set_title("Damage Per Floor")
    plt.tight_layout()
    plt.show()
