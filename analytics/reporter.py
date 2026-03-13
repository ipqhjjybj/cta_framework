"""
Report generation for backtest results.

Supports:
  - Console output (via rich)
  - HTML report (via Jinja2 template)
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from analytics.performance import PerformanceMetrics
from analytics.trade_stats import TradeStatsCollector
from core.engine import BacktestResult


def _fmt(val: float, decimals: int = 2, suffix: str = "") -> str:
    return f"{val:,.{decimals}f}{suffix}"


class ConsoleReporter:
    """Prints a formatted performance summary to stdout using rich."""

    def report(
        self,
        result: BacktestResult,
        metrics: PerformanceMetrics,
        trade_collector: Optional[TradeStatsCollector] = None,
    ) -> None:
        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            self._rich_report(console, result, metrics, trade_collector)
        except ImportError:
            self._plain_report(result, metrics, trade_collector)

    def _rich_report(self, console, result, metrics, trade_collector) -> None:
        from rich.table import Table
        from rich import box

        console.rule(f"[bold blue]Backtest Report: {result.name}")

        # Performance table
        t = Table(title="Performance Metrics", box=box.SIMPLE, show_header=True,
                  header_style="bold cyan")
        t.add_column("Metric", style="dim", width=30)
        t.add_column("Value", justify="right")

        rows = [
            ("Period", f"{metrics.start.date()} → {metrics.end.date()}"),
            ("Duration (days)", _fmt(metrics.duration_days, 1)),
            ("Initial Capital", _fmt(result.initial_capital, 2, " USDT")),
            ("Final Equity", _fmt(result.final_equity, 2, " USDT")),
            ("Total Return", _fmt(metrics.total_return_pct, 2, "%")),
            ("CAGR", _fmt(metrics.cagr_pct, 2, "%")),
            ("Annual Volatility", _fmt(metrics.annual_volatility_pct, 2, "%")),
            ("Sharpe Ratio", _fmt(metrics.sharpe_ratio, 3)),
            ("Sortino Ratio", _fmt(metrics.sortino_ratio, 3)),
            ("Calmar Ratio", _fmt(metrics.calmar_ratio, 3)),
            ("Max Drawdown", _fmt(metrics.max_drawdown_pct, 2, "%")),
            ("VaR 95%", _fmt(metrics.var_95_pct, 2, "%")),
            ("VaR 99%", _fmt(metrics.var_99_pct, 2, "%")),
            ("Total Bars", str(result.total_bars)),
            ("Total Trades", str(result.total_trades)),
            ("Total Commission", _fmt(result.total_commission, 2, " USDT")),
            ("Elapsed", _fmt(result.elapsed_seconds, 2, "s")),
        ]

        for metric, value in rows:
            color = ""
            if "Return" in metric or "CAGR" in metric:
                color = "green" if float(value.replace("%", "").replace(",", "")) > 0 else "red"
            t.add_row(metric, f"[{color}]{value}[/{color}]" if color else value)

        console.print(t)

        # Trade summary
        if trade_collector and trade_collector.trades:
            summary = trade_collector.summary()
            ts = Table(title="Trade Statistics", box=box.SIMPLE, header_style="bold cyan")
            ts.add_column("Metric", style="dim", width=30)
            ts.add_column("Value", justify="right")
            ts.add_row("Total Trades", str(summary["total_trades"]))
            ts.add_row("Win Rate", f"{summary['win_rate_pct']:.1f}%")
            ts.add_row("Avg Win", _fmt(summary["avg_win"], 2, " USDT"))
            ts.add_row("Avg Loss", _fmt(summary["avg_loss"], 2, " USDT"))
            ts.add_row("Profit Factor", _fmt(summary["profit_factor"], 3))
            ts.add_row("Avg Duration (h)", _fmt(summary["avg_duration_hours"], 1))
            console.print(ts)

    def _plain_report(self, result, metrics, trade_collector) -> None:
        print(f"\n{'='*60}")
        print(f"  Backtest: {result.name}")
        print(f"{'='*60}")
        print(f"  Total Return : {metrics.total_return_pct:.2f}%")
        print(f"  Sharpe Ratio : {metrics.sharpe_ratio:.3f}")
        print(f"  Max Drawdown : {metrics.max_drawdown_pct:.2f}%")
        print(f"  Total Trades : {result.total_trades}")
        print(f"  Final Equity : {result.final_equity:,.2f}")
        print(f"{'='*60}\n")


class HTMLReporter:
    """Generates a self-contained HTML report."""

    _TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{{ name }} — Backtest Report</title>
  <style>
    body { font-family: 'Segoe UI', sans-serif; margin: 2rem; background: #f5f5f5; color: #333; }
    h1 { color: #1565C0; }
    table { border-collapse: collapse; width: 100%; max-width: 700px; background: white;
            box-shadow: 0 1px 4px rgba(0,0,0,.1); border-radius: 4px; margin-bottom: 2rem; }
    th, td { padding: .6rem 1rem; text-align: left; border-bottom: 1px solid #eee; }
    th { background: #1565C0; color: white; }
    .pos { color: #2e7d32; font-weight: bold; }
    .neg { color: #c62828; font-weight: bold; }
    img { max-width: 100%; margin: 1rem 0; }
  </style>
</head>
<body>
  <h1>{{ name }}</h1>
  <p>Generated: {{ generated }}</p>

  <h2>Performance Metrics</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    {% for k, v in metrics %}
    <tr><td>{{ k }}</td><td>{{ v }}</td></tr>
    {% endfor %}
  </table>

  {% if trade_rows %}
  <h2>Trade Statistics</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    {% for k, v in trade_rows %}
    <tr><td>{{ k }}</td><td>{{ v }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}

  {% if equity_img %}
  <h2>Equity Curve</h2>
  <img src="{{ equity_img }}" alt="Equity Curve">
  {% endif %}
</body>
</html>"""

    def report(
        self,
        result: BacktestResult,
        metrics: PerformanceMetrics,
        output_path: str = "results/report.html",
        trade_collector: Optional[TradeStatsCollector] = None,
        equity_img: Optional[str] = None,
    ) -> str:
        try:
            from jinja2 import Template
        except ImportError:
            raise ImportError("jinja2 is required for HTML reports: pip install jinja2")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        metric_rows = [
            ("Period", f"{metrics.start.date()} → {metrics.end.date()}"),
            ("Total Return", f"{metrics.total_return_pct:.2f}%"),
            ("CAGR", f"{metrics.cagr_pct:.2f}%"),
            ("Sharpe Ratio", f"{metrics.sharpe_ratio:.3f}"),
            ("Sortino Ratio", f"{metrics.sortino_ratio:.3f}"),
            ("Calmar Ratio", f"{metrics.calmar_ratio:.3f}"),
            ("Max Drawdown", f"{metrics.max_drawdown_pct:.2f}%"),
            ("Annual Volatility", f"{metrics.annual_volatility_pct:.2f}%"),
            ("Total Trades", str(result.total_trades)),
            ("Total Commission", f"{result.total_commission:,.2f}"),
            ("Final Equity", f"{result.final_equity:,.2f}"),
        ]

        trade_rows = []
        if trade_collector and trade_collector.trades:
            s = trade_collector.summary()
            trade_rows = [
                ("Total Trades", str(s["total_trades"])),
                ("Win Rate", f"{s['win_rate_pct']:.1f}%"),
                ("Profit Factor", f"{s['profit_factor']:.3f}"),
                ("Avg Win", f"{s['avg_win']:,.2f}"),
                ("Avg Loss", f"{s['avg_loss']:,.2f}"),
                ("Avg Duration (h)", f"{s['avg_duration_hours']:.1f}"),
            ]

        html = Template(self._TEMPLATE).render(
            name=result.name,
            generated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            metrics=metric_rows,
            trade_rows=trade_rows,
            equity_img=equity_img,
        )

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)

        return output_path
