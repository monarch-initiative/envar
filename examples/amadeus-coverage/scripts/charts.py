"""The two report charts: a Venn of EnVar slots vs Amadeus elements, and per-dataset counts (matplotlib)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Patch

BLUE, ORANGE, LIGHT, GREY, INK, QUIET = "#2B6FD6", "#EE8E66", "#B9D0F2", "#C5C2B8", "#1A1A1A", "#666666"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})


def _venn(ax, cx, cy, r, gap, nums, notes, labels, title, numsize=24):
    for x, col in ((cx - gap, BLUE), (cx + gap, ORANGE)):
        ax.add_patch(Circle((x, cy), r, facecolor=col, alpha=0.10, edgecolor="#9A968C", lw=1.2))
    xs = (cx - gap - r * 0.45, cx, cx + gap + r * 0.45)
    for x, n in zip(xs, nums):
        ax.text(x, cy, str(n), ha="center", va="center", fontsize=numsize, fontweight="bold", color=INK)
    if title:
        ax.text(cx, cy + r + 0.32 * r, title, ha="center", fontsize=12, fontweight="bold", color=INK)
    for x, lab in zip(xs, labels):
        if lab: ax.text(x, cy + r + 0.1 * r, lab, ha="center", fontsize=11, fontweight="bold", color=INK)
    left, mid, right = notes
    if mid: ax.text(cx, cy - 0.28 * r, mid, ha="center", va="top", fontsize=8.5, color=QUIET, wrap=True)
    if left: ax.text(cx - gap - r * 0.55, cy - r - 0.12 * r, left, ha="center", va="top", fontsize=9, color=QUIET)
    if right: ax.text(cx + gap + r * 0.55, cy - r - 0.12 * r, right, ha="center", va="top", fontsize=9, color=QUIET)


def venn(path, slots, datasets=None, heading=None, na_note=None):
    """slots = (envar_only, shared, amadeus_only, notes3); datasets = (envar_only, both, amadeus_only, notes3) or None."""
    w = 13 if datasets else 8
    fig, ax = plt.subplots(figsize=(w, 5.0), dpi=200)
    ax.set_xlim(0, w); ax.set_ylim(0.0, 5.0); ax.axis("off"); ax.set_aspect("equal")
    _venn(ax, 4.0, 2.55, 1.7, 1.05, slots[:3], slots[3], ("EnVar only", "Shared", "Amadeus only"), None, 26)
    if na_note: ax.text(4.0, 0.12, na_note, ha="center", fontsize=9, color=QUIET)
    if datasets:
        _venn(ax, 10.3, 2.55, 1.15, 0.62, datasets[:3], datasets[3], ("EnVar examples", "", "Amadeus"), "Datasets", 20)
    if heading:
        fig.text(0.02, 0.965, heading, fontsize=14, fontweight="bold", color=INK, va="top")
    fig.savefig(path, bbox_inches="tight", facecolor="white"); plt.close(fig)


def per_dataset(path, rows, heading, highlight=None):
    """rows: list of dict(ds, full, part, env, ama, key), drawn top to bottom; highlight = key drawn bold."""
    n = len(rows)
    fig, ax = plt.subplots(figsize=(10, 0.3 * n + 0.9), dpi=200)
    y = list(range(n))[::-1]
    full = [r["full"] for r in rows]; part = [r["part"] for r in rows]; env = [r["env"] for r in rows]
    alpha = [1.0 if highlight in (None, r["key"]) else 0.35 for r in rows]
    for yi, r, a in zip(y, rows, alpha):
        ax.barh(yi, -r["ama"], color=ORANGE, height=0.66, alpha=a)
        ax.barh(yi, r["full"], color=BLUE, height=0.66, alpha=a)
        ax.barh(yi, r["part"], left=r["full"], color=LIGHT, height=0.66, alpha=a)
        ax.barh(yi, r["env"], left=r["full"] + r["part"], color=GREY, height=0.66, alpha=a)
        bold = "bold" if highlight == r["key"] else "normal"
        ax.text(-r["ama"] - 0.8, yi, r["ds"], ha="right", va="center", fontsize=10, color=INK, fontweight=bold)
        ax.text(0.6, yi, str(r["full"]), ha="left", va="center", fontsize=8.5, color="white", fontweight=bold)
        ax.text(r["full"] + r["part"] + r["env"] + 0.6, yi, str(r["env"]), ha="left", va="center", fontsize=8.5, color=QUIET,
                fontweight=bold)
    ax.axvline(0, color="#888888", lw=1)
    ax.set_xlim(-max(r["ama"] for r in rows) - 1, max(r["full"] + r["part"] + r["env"] for r in rows) + 4)
    ax.set_ylim(-0.6, n - 0.4)
    ax.axis("off")
    ax.legend(handles=[Patch(color=ORANGE, label="Amadeus only"), Patch(color=BLUE, label="Shared, full"),
                       Patch(color=LIGHT, label="Shared, partial"), Patch(color=GREY, label="EnVar only (in Amadeus scope)")],
              loc="lower left", bbox_to_anchor=(-0.05, 1.0), ncol=4, frameon=False, fontsize=9.5)
    ax.set_title(heading, loc="left", fontsize=13, fontweight="bold", color=INK, pad=28, x=-0.05)
    fig.savefig(path, bbox_inches="tight", facecolor="white"); plt.close(fig)
