from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DATA = ROOT / "data_processed"


def svg_line(df: pd.DataFrame, x_col: str, y_col: str, title: str, path: Path, color: str = "#2563eb") -> None:
    values = df[[x_col, y_col]].dropna().reset_index(drop=True)
    width, height = 900, 360
    left, right, top, bottom = 70, 25, 45, 55
    plot_w, plot_h = width - left - right, height - top - bottom
    y_min, y_max = values[y_col].min(), values[y_col].max()
    if y_min == y_max:
        y_min -= 1
        y_max += 1
    pts = []
    for i, row in values.iterrows():
        x = left + (i / max(len(values) - 1, 1)) * plot_w
        y = top + (1 - (row[y_col] - y_min) / (y_max - y_min)) * plot_h
        pts.append(f"{x:.1f},{y:.1f}")
    labels = [values[x_col].iloc[0], values[x_col].iloc[len(values) // 2], values[x_col].iloc[-1]]
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<text x="{left}" y="28" font-family="Arial" font-size="20" font-weight="700">{title}</text>
<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#94a3b8"/>
<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#94a3b8"/>
<polyline fill="none" stroke="{color}" stroke-width="3" points="{' '.join(pts)}"/>
<text x="12" y="{top+8}" font-family="Arial" font-size="12" fill="#475569">{y_max:,.1f}</text>
<text x="12" y="{top+plot_h}" font-family="Arial" font-size="12" fill="#475569">{y_min:,.1f}</text>
<text x="{left}" y="{height-20}" font-family="Arial" font-size="12" fill="#475569">{labels[0]}</text>
<text x="{left+plot_w/2-25}" y="{height-20}" font-family="Arial" font-size="12" fill="#475569">{labels[1]}</text>
<text x="{left+plot_w-55}" y="{height-20}" font-family="Arial" font-size="12" fill="#475569">{labels[2]}</text>
</svg>"""
    path.write_text(svg, encoding="utf-8")


def svg_bar(df: pd.DataFrame, label_col: str, y_col: str, title: str, path: Path, color: str = "#0f766e") -> None:
    values = df[[label_col, y_col]].copy()
    width, height = 1000, 460
    left, top, bottom = 70, 50, 140
    plot_w, plot_h = width - left - 30, height - top - bottom
    y_min, y_max = min(0, values[y_col].min()), max(0, values[y_col].max())
    span = y_max - y_min or 1
    bar_w = plot_w / len(values) * 0.72
    zero_y = top + (1 - (0 - y_min) / span) * plot_h
    bars = []
    for i, row in values.iterrows():
        x = left + i * (plot_w / len(values)) + (plot_w / len(values) - bar_w) / 2
        y = top + (1 - (row[y_col] - y_min) / span) * plot_h
        h = abs(zero_y - y)
        rect_y = min(y, zero_y)
        label = str(row[label_col])[:18]
        bars.append(f'<rect x="{x:.1f}" y="{rect_y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}"/>')
        bars.append(f'<text transform="translate({x+bar_w/2:.1f},{height-95}) rotate(55)" font-family="Arial" font-size="11" fill="#334155">{label}</text>')
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<text x="{left}" y="30" font-family="Arial" font-size="20" font-weight="700">{title}</text>
<line x1="{left}" y1="{zero_y:.1f}" x2="{width-30}" y2="{zero_y:.1f}" stroke="#94a3b8"/>
{''.join(bars)}
<text x="12" y="{top+8}" font-family="Arial" font-size="12" fill="#475569">{y_max:,.2f}</text>
<text x="12" y="{top+plot_h}" font-family="Arial" font-size="12" fill="#475569">{y_min:,.2f}</text>
</svg>"""
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    quarterly = pd.read_csv(DATA / "quarterly_master.csv")
    scenarios = pd.read_csv(OUT / "scenario_results.csv")
    svg_line(quarterly, "period", "trm_avg_cop_per_usd", "TRM promedio trimestral", OUT / "trm_history.svg")
    svg_line(quarterly, "period", "gdp_real_cop_billion", "PIB real trimestral", OUT / "gdp_real_history.svg", "#7c3aed")
    svg_bar(scenarios, "scenario", "trm_change_pct", "Variacion de TRM por escenario (%)", OUT / "scenario_trm_change.svg")
    svg_bar(scenarios, "scenario", "current_account_usd_m", "Cuenta corriente por escenario (USD m)", OUT / "scenario_current_account.svg", "#b45309")
    (OUT / "charts_index.md").write_text(
        "# Graficos generados\n\n"
        "- `trm_history.svg`\n"
        "- `gdp_real_history.svg`\n"
        "- `scenario_trm_change.svg`\n"
        "- `scenario_current_account.svg`\n\n"
        "La tasa de politica y el precio del petroleo se muestran en la app interactiva; "
        "no se genero serie historica completa de petroleo porque FRED no resolvio DNS en esta sesion local.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
