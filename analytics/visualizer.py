"""
Chart generation for backtest results.

Produces:
  - Equity curve with drawdown overlay
  - Monthly returns heatmap
  - Trade P&L distribution

Uses matplotlib (saved to file) or plotly (interactive HTML).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


def plot_equity_curve(
    equity_curve: List[Tuple[datetime, float]],
    output_path: str = "results/equity_curve.png",
    title: str = "Equity Curve",
    initial_capital: Optional[float] = None,
) -> str:
    """
    Plot equity curve with drawdown panel.
    Returns the saved file path.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    _ensure_dir(output_path)
    timestamps = [t for t, _ in equity_curve]
    equities = [e for _, e in equity_curve]

    eq_arr = pd.Series(equities, index=timestamps)
    peak = eq_arr.cummax()
    drawdown = (eq_arr - peak) / peak * 100.0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})

    ax1.plot(eq_arr.index, eq_arr.values, color="#2196F3", linewidth=1.2, label="Equity")
    if initial_capital:
        ax1.axhline(initial_capital, color="#9E9E9E", linewidth=0.8, linestyle="--",
                    label=f"Initial capital ({initial_capital:,.0f})")
    ax1.set_ylabel("Portfolio Value")
    ax1.set_title(title)
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(drawdown.index, drawdown.values, 0, color="#F44336", alpha=0.5)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_monthly_returns(
    equity_curve: List[Tuple[datetime, float]],
    output_path: str = "results/monthly_returns.png",
    title: str = "Monthly Returns Heatmap",
) -> str:
    """
    Plot a monthly returns heatmap (years × months).
    Returns the saved file path.
    """
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    _ensure_dir(output_path)
    df = pd.DataFrame(equity_curve, columns=["timestamp", "equity"])
    df = df.set_index("timestamp")
    monthly = df["equity"].resample("ME").last()
    monthly_ret = monthly.pct_change().dropna() * 100.0

    pivot = monthly_ret.groupby([monthly_ret.index.year, monthly_ret.index.month]).mean()
    pivot = pivot.unstack(level=1)
    pivot.columns = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    fig, ax = plt.subplots(figsize=(14, max(4, len(pivot) * 0.8)))
    vmax = max(abs(pivot.values[~pd.isna(pivot.values)]).max(), 1e-6)
    cmap = plt.cm.RdYlGn

    im = ax.imshow(pivot.values, aspect="auto", cmap=cmap,
                   vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(12))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot)))
    ax.set_yticklabels(pivot.index)
    ax.set_title(title)

    for i in range(len(pivot)):
        for j in range(12):
            val = pivot.values[i, j]
            if not pd.isna(val):
                ax.text(j, i, f"{val:.1f}%", ha="center", va="center",
                        fontsize=8, color="black")

    plt.colorbar(im, ax=ax, label="Monthly Return (%)")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_trade_pnl(
    net_pnls: List[float],
    output_path: str = "results/trade_pnl.png",
    title: str = "Trade P&L Distribution",
) -> str:
    """Histogram of per-trade net P&L. Returns file path."""
    import matplotlib.pyplot as plt
    import numpy as np

    _ensure_dir(output_path)
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#4CAF50" if p > 0 else "#F44336" for p in net_pnls]
    ax.bar(range(len(net_pnls)), net_pnls, color=colors, alpha=0.7, edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Net P&L")
    ax.set_title(title)
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path
