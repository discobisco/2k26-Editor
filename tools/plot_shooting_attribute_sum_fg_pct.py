from __future__ import annotations

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
INPUTS = [
    (
        OUT / "shooting_attribute_sum_vs_live_fg_pct_1947.csv",
        OUT / "shooting_attribute_sum_vs_live_fg_pct_1947_scatter.png",
        OUT / "shooting_attribute_sum_vs_live_fg_pct_1947_scatter.svg",
        "All active players",
    ),
    (
        OUT / "shooting_attribute_sum_vs_live_fg_pct_1947_no_hawks.csv",
        OUT / "shooting_attribute_sum_vs_live_fg_pct_1947_no_hawks_scatter.png",
        OUT / "shooting_attribute_sum_vs_live_fg_pct_1947_no_hawks_scatter.svg",
        "Hawks excluded",
    ),
]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    if len(xs) < 2 or len(set(xs)) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    return slope, intercept


def plot_one(input_csv: Path, png_path: Path, svg_path: Path, title_suffix: str) -> dict[str, object]:
    rows = list(csv.DictReader(input_csv.open(newline="", encoding="utf-8")))
    xs_sum = [float(row["shooting_attribute_sum"]) for row in rows]
    xs_avg = [float(row["shooting_attribute_average"]) for row in rows]
    ys = [float(row["live_fg_percent"]) for row in rows]

    fig, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)
    fig.suptitle(f"Shooting attribute points mapped to live in-game FG% — 1947 ({title_suffix})", fontsize=15)

    panels = [
        (axes[0], xs_sum, "X = shooting attribute sum", "shooting_attribute_sum"),
        (axes[1], xs_avg, "X = shooting attribute average", "shooting_attribute_average"),
    ]

    for ax, xs, xlabel, field in panels:
        ax.scatter(xs, ys, s=34, alpha=0.72, color="#3568b7", edgecolors="white", linewidths=0.4)
        fit = linear_fit(xs, ys)
        if fit:
            slope, intercept = fit
            x0, x1 = min(xs), max(xs)
            ax.plot([x0, x1], [slope * x0 + intercept, slope * x1 + intercept], color="#cf3b32", linewidth=1.8, alpha=0.85)
        r = pearson(xs, ys)
        ax.set_title("X(sum), Y(FG%)" if field == "shooting_attribute_sum" else "X(average), Y(FG%)")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Y = live FG%")
        ax.set_ylim(-0.02, max(0.55, max(ys) + 0.03))
        ax.grid(True, alpha=0.25)
        ax.text(
            0.03,
            0.97,
            f"n={len(rows)}\nr={r:.3f}" if r is not None else f"n={len(rows)}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.9},
        )

        bob = next((row for row in rows if row["player"] == "Bob Feerick"), None)
        if bob:
            bob_x = float(bob[field])
            bob_y = float(bob["live_fg_percent"])
            ax.scatter([bob_x], [bob_y], s=95, color="#f2b705", edgecolors="black", linewidths=1.0, zorder=4)
            ax.annotate(
                f"Bob Feerick\n({bob_x:.2f}, {bob_y:.3f})",
                xy=(bob_x, bob_y),
                xytext=(8, 10),
                textcoords="offset points",
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.25", "facecolor": "#fff7cc", "edgecolor": "#c9a000", "alpha": 0.95},
                arrowprops={"arrowstyle": "->", "color": "#7a6500", "lw": 0.9},
            )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=180)
    fig.savefig(svg_path)
    plt.close(fig)
    return {
        "input": str(input_csv),
        "png": str(png_path),
        "svg": str(svg_path),
        "rows": len(rows),
        "sum_r": pearson(xs_sum, ys),
        "average_r": pearson(xs_avg, ys),
    }


def main() -> int:
    results = [plot_one(*item) for item in INPUTS]
    for result in results:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
