"""Bar charts for slides, rendered to PNG bytes that are identical on every run."""

import io

from aura.decks.palettes import Palette, unit


def bar_chart(chart: dict, colours: Palette, *, width_in: float = 4.2, height_in: float = 3.1) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=150)
    fig.patch.set_facecolor("white")
    bars = ax.bar(chart["labels"], chart["values"], color=unit(colours.primary), width=0.55)
    top = max(chart["values"]) or 1
    for bar, value in zip(bars, chart["values"], strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + top * 0.02, f"{value:g}",
                ha="center", va="bottom", fontsize=10, color=unit(colours.dark), fontweight="bold")
    ax.set_title(chart["title"], fontsize=11, color=unit(colours.dark), loc="left")
    ax.set_ylim(0, top * 1.2)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=unit(colours.dark), labelsize=9)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", metadata={"Software": None})  # no version stamp: stable bytes
    plt.close(fig)
    return buf.getvalue()
