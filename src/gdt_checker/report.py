"""Write the pass/fail report (Markdown) and the plot (PNG)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

from .checker import Result, Spec  # noqa: E402
from .geometry import DatumFrame, fit_circle  # noqa: E402

# Okabe-Ito colours: blue and vermilion stay distinct for most colour-blind readers.
PASS_COLOUR = "#0072B2"
FAIL_COLOUR = "#D55E00"


def _verdict(result: Result) -> str:
    return "PASS" if result.passed else "FAIL"


def write_markdown(spec: Spec, results: list[Result], path: str | Path) -> None:
    passed = sum(r.passed for r in results)
    lines = [
        f"# Inspection report: {spec.name}",
        "",
        f"Units: {spec.units}. Features checked: {len(results)}. "
        f"Passed: {passed}. Failed: {len(results) - passed}.",
        "",
        "| Feature | Type | Measured | Limit | Margin | Result | Notes |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.feature_id} | {r.fcf_type} | {r.measured:.4f} | {r.limit:.4f} "
            f"| {r.margin:+.4f} | {_verdict(r)} | {r.note} |"
        )
    lines += [
        "",
        "Limit for position includes the MMC bonus tolerance when it applies. "
        "Margin is limit minus measured; negative means the feature is out of tolerance.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_plot(
    spec: Spec,
    results: list[Result],
    frame: DatumFrame,
    points: dict[str, np.ndarray],
    path: str | Path,
) -> None:
    """Left: position map in datum coordinates with tolerance circles.
    Right: measured-to-limit ratio for every feature (1.0 is the limit)."""
    fig, (ax_map, ax_bar) = plt.subplots(
        1, 2, figsize=(11, 5), gridspec_kw={"width_ratios": [1.1, 1]}
    )
    # Each hole is drawn as its offset from its own nominal, so every tolerance
    # zone is centred on the origin and stays readable whatever the hole layout.
    position_results = [r for r in results if r.fcf_type == "position"]
    features = {f.id: f for f in spec.features}
    offsets = []
    for r in position_results:
        feature = features[r.feature_id]
        centre, _ = fit_circle(frame.to_frame(points[r.feature_id])[:, :2])
        offset = centre - np.array(feature.nominal)
        offsets.append((r, offset))
    reach = max(
        [r.limit / 2.0 for r, _ in offsets] + [float(np.abs(o).max()) for _, o in offsets] + [0.01]
    ) * 1.3
    for r, offset in offsets:
        colour = PASS_COLOUR if r.passed else FAIL_COLOUR
        marker = "o" if r.passed else "X"
        ax_map.add_patch(
            Circle((0, 0), r.limit / 2.0, fill=False, edgecolor=colour, linestyle="--", linewidth=1.2)
        )
        ax_map.scatter(*offset, color=colour, marker=marker, s=60, zorder=3)
        ax_map.annotate(r.feature_id, offset, textcoords="offset points", xytext=(6, 6), fontsize=9)
    ax_map.scatter(0, 0, color="black", marker="+", s=80, zorder=3)
    ax_map.set_xlim(-reach, reach)
    ax_map.set_ylim(-reach, reach)
    ax_map.set_aspect("equal")
    ax_map.set_xlabel(f"Offset in X from nominal ({spec.units})")
    ax_map.set_ylabel(f"Offset in Y from nominal ({spec.units})")
    ax_map.set_title("Position: each circle is that hole's zone (with MMC bonus)")
    ax_map.grid(True, linewidth=0.4, alpha=0.4)
    ax_map.legend(
        handles=[
            Line2D([], [], color="black", marker="+", linestyle="", label="Nominal"),
            Line2D([], [], color=PASS_COLOUR, marker="o", linestyle="", label="Pass (circle)"),
            Line2D([], [], color=FAIL_COLOUR, marker="X", linestyle="", label="Fail (cross)"),
        ],
        loc="lower right",
        fontsize=8,
    )

    names = [r.feature_id for r in results]
    ratios = [r.measured / r.limit for r in results]
    colours = [PASS_COLOUR if r.passed else FAIL_COLOUR for r in results]
    ax_bar.bar(names, ratios, color=colours)
    ax_bar.axhline(1.0, color="black", linewidth=1, linestyle="--")
    for i, (r, ratio) in enumerate(zip(results, ratios)):
        ax_bar.text(i, ratio, _verdict(r), ha="center", va="bottom", fontsize=8)
    ax_bar.set_ylabel("Measured / limit (1.0 = at limit)")
    ax_bar.set_title("Every feature against its limit")
    ax_bar.grid(True, axis="y", linewidth=0.4, alpha=0.4)
    ax_bar.legend(
        handles=[
            Line2D([], [], color=PASS_COLOUR, marker="s", linestyle="", label="Pass"),
            Line2D([], [], color=FAIL_COLOUR, marker="s", linestyle="", label="Fail"),
        ],
        loc="upper left",
        fontsize=8,
    )
    fig.suptitle(f"{spec.name}: GD&T check")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
