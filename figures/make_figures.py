#!/usr/bin/env python3
"""Render the corridor results from the COMMITTED derived data.

Usage: python3 figures/make_figures.py      (from the repo root)

WHAT THIS CAN AND CANNOT DRAW
    The raster fields (peak.npz, snaps.npz) were never committed — the study's
    .gitignore excludes *.npz deliberately — and the machine that held them has
    since been recycled. Inundation MAPS are therefore not reproducible from
    this repository. What is committed, and what these figures use, is the 60 s
    depth series at every corridor probe, which is the evidence the road-versus-
    channel finding actually rests on.

FIGURES
    fig1_road_vs_channel.png   the smearing mechanism as a time series: for each
                               corridor point, carriageway depth against the
                               depth in the channel beside it, with the caution
                               and impassable thresholds drawn.
    fig2_prediction_outcome.png  every one of the twelve corridor points placed
                               by its terrain-only freeboard prediction against
                               what the fine grid did, including the rows that
                               cannot be scored and why.
    fig3_numerical_health.png  the ten in-flight diagnostic samples from the
                               Franklinton run: Froude, conveyance depth,
                               domain volume and the outfall boundary velocity.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

CAUTION, IMPASS = 0.15, 0.30
T0_LABEL = "hours from 2026-08-19 18:00Z"

INK, FAINT, RULE = "#0F1C21", "#6C7F86", "#C6D0D3"
ROAD, CHAN = "#A8322B", "#1D5C6B"
GOOD, WARN = "#3F6B4A", "#9A6B1E"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": RULE, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": FAINT, "ytick.color": FAINT,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white",
})

TITLES = {
    "sr310_sf_crossing":      ("SR-310 at South Fork", "freeboard +3.44 m", "smearing confirmed"),
    "main_broad_pataskala":   ("Main St at Broad, Pataskala", "freeboard −0.18 m", "signal real"),
    "kirkersville_gauge_03144816": ("South Fork at Kirkersville", "freeboard −0.36 m", "signal real"),
    "us40_east":              ("US-40 east of Etna", "freeboard −0.55 m", "detour stayed passable"),
    "us40_etna":              ("US-40, Etna", "freeboard −3.18 m", "detour stayed passable"),
    "wbroad_hilltop":         ("W Broad St, Hilltop", "freeboard +4.15 m", "PREDICTION FAILED"),
    "franklinton_core":       ("Franklinton core", "freeboard −0.38 m", "signal real"),
    "olentangy_gauge_03227107": ("Olentangy at Columbus", "on the domain edge", "not usable"),
}
ORDER = ["sr310_sf_crossing", "main_broad_pataskala", "kirkersville_gauge_03144816",
         "us40_east", "us40_etna", "wbroad_hilltop", "franklinton_core",
         "olentangy_gauge_03227107"]


def load_series():
    out = {}
    for run in ("pataskala_c_B", "franklinton_c_B"):
        d = json.load(open(f"runs/{run}/probe_series.json"))
        t = np.asarray(d["t_s"], float) / 3600.0
        for g, v in d["groups"].items():
            out[g] = (t, np.asarray(v["depth_max_m"], float))
    return out


def fig1(S):
    keys = [k for k in ORDER if k in S]
    n = len(keys)
    ncol, nrow = 4, int(np.ceil(n / 4))
    fig, axes = plt.subplots(nrow, ncol, figsize=(14.5, 3.5 * nrow), sharex=True)
    axes = np.atleast_1d(axes).ravel()
    for ax, k in zip(axes, keys):
        t, road = S[k]
        ch = S.get(k + "__channel")
        name, fb, verdict = TITLES[k]
        if ch is not None and not np.allclose(ch[1], road):
            ax.fill_between(ch[0], 0, ch[1], color=CHAN, alpha=.16, lw=0, zorder=1)
            ax.plot(ch[0], ch[1], color=CHAN, lw=1.6, zorder=3, label="channel beside it")
        ax.plot(t, road, color=ROAD, lw=2.0, zorder=4, label="carriageway")
        ax.axhline(IMPASS, color=INK, lw=.9, ls="--", zorder=2)
        ax.axhline(CAUTION, color=FAINT, lw=.7, ls=":", zorder=2)
        pk = road.max()
        col = GOOD if "real" in verdict else (ROAD if "FAILED" in verdict else
                                             (FAINT if "not usable" in verdict else WARN))
        ax.set_title(f"{name}\n{fb}  ·  {verdict}", fontsize=9.5, color=col,
                     linespacing=1.5, pad=8)
        top = max(pk, (ch[1].max() if ch is not None else 0)) * 1.18 + .12
        ax.set_ylim(0, top)
        ax.set_xlim(0, 20)
        ax.text(.97, .93, f"road peak {pk:.2f} m", transform=ax.transAxes,
                ha="right", va="top", fontsize=8.5, color=ROAD, fontweight="bold")
        if ch is not None and not np.allclose(ch[1], road):
            ax.text(.97, .82, f"channel {ch[1].max():.2f} m", transform=ax.transAxes,
                    ha="right", va="top", fontsize=8.5, color=CHAN)
    for ax in axes[n:]:
        ax.axis("off")
    for ax in axes[max(0, n - ncol):n]:
        ax.set_xlabel(T0_LABEL)
    for i in range(0, n, ncol):
        axes[i].set_ylabel("water depth (m)")
    handles = [Line2D([], [], color=ROAD, lw=2.0, label="carriageway cells"),
               Line2D([], [], color=CHAN, lw=1.6, label="channel cells alongside"),
               Line2D([], [], color=INK, lw=.9, ls="--", label="impassable, 0.30 m"),
               Line2D([], [], color=FAINT, lw=.7, ls=":", label="caution, 0.15 m")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               bbox_to_anchor=(.5, -0.005), fontsize=9)
    fig.suptitle("Carriageway against the channel beside it, at 6–8 m resolution",
                 fontsize=14, y=.995, x=.5)
    fig.text(.5, .955, "Where the two lines separate, a 60 m cell averaging them "
             "together reports the road as flooded when it is not.",
             ha="center", fontsize=10, color=FAINT)
    fig.tight_layout(rect=[0, .035, 1, .945])
    fig.savefig("figures/fig1_road_vs_channel.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print("figures/fig1_road_vs_channel.png")


def fig2():
    ct = json.load(open("analysis/consolidated_table.json"))
    rows = sorted(ct["rows"], key=lambda r: -r["freeboard_to_pavement_m"])
    fig, ax = plt.subplots(figsize=(12.6, 6.6))
    y = np.arange(len(rows))[::-1]
    STYLE = (("CONFIRMED", GOOD, "prediction confirmed"),
             ("FAILED", ROAD, "prediction failed"),
             ("NOT RUN", "#B9C4C8", "nest not run (Buckeye, held)"),
             ("UNUSABLE", FAINT, "probe on the domain boundary"))
    used = []
    for yi, r in zip(y, rows):
        fb = r["freeboard_to_pavement_m"]
        out = r["outcome"]
        c, lab = WARN, "untestable — nothing to miss"
        for key, cc, ll in STYLE:
            if key in out:
                c, lab = cc, ll
                break
        if lab not in used:
            used.append(lab)
        ax.barh(yi, fb, color=c, height=.66, zorder=3)
        rp = r.get("nest_road_peak_m")
        txt = f"road {rp:.2f} m" if rp is not None else "not simulated"
        # value label always OUTSIDE the bar tip, in the direction the bar points
        off = .14 if fb >= 0 else -.14
        ax.text(fb + off, yi, txt, va="center",
                ha="left" if fb >= 0 else "right", fontsize=8.5,
                color=INK if rp is not None else FAINT)
    ax.axvline(0, color=INK, lw=1.1, zorder=4)
    ax.axvspan(0.5, 6.4, color=ROAD, alpha=.05, zorder=0)
    ax.axvspan(-7.4, -0.5, color=CHAN, alpha=.05, zorder=0)
    ax.set_yticks(y[::-1])
    ax.set_yticklabels([r["probe"] for r in rows][::-1], fontsize=9,
                       family="monospace")
    ax.tick_params(axis="y", length=0, pad=6)
    for t in ax.get_yticklabels():
        t.set_color(INK)
    ax.set_xlim(-7.4, 6.4)
    ax.set_ylim(-.85, len(rows) - .15)
    ax.text(3.4, len(rows) - .45, "coarse grid floods a road that may be dry",
            ha="center", fontsize=9.5, color=ROAD)
    ax.text(-3.9, len(rows) - .45, "coarse bed sits ABOVE the road — under-reports",
            ha="center", fontsize=9.5, color=CHAN)
    ax.set_xlabel("freeboard: surveyed pavement minus the 60 m grid's water surface "
                  "at \u201cimpassable\u201d (m)")
    ax.spines["left"].set_visible(False)
    order = [("prediction confirmed", GOOD), ("prediction failed", ROAD),
             ("untestable — nothing to miss", WARN),
             ("probe on the domain boundary", FAINT),
             ("nest not run (Buckeye, held)", "#B9C4C8")]
    handles = [Line2D([], [], marker="s", ls="", ms=9, color=c, label=l)
               for l, c in order if l in used]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8.8,
              borderpad=.2)
    ax.set_title("All twelve corridor points: what terrain alone predicted, "
                 "and what the fine grid did", fontsize=13.5, pad=30)
    fig.text(.5, .935, f"{ct['scoreable_rows']} of 12 are scoreable — "
             f"{ct['confirmed']} confirmed, {ct['failed']} failed. "
             "The other 7 are kept in, with the reason each cannot be scored.",
             ha="center", fontsize=10, color=FAINT)
    fig.tight_layout(rect=[0, 0, 1, .925])
    fig.savefig("figures/fig2_prediction_outcome.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print("figures/fig2_prediction_outcome.png")


def fig3():
    ff = [json.loads(l) for l in open("analysis/fast_face_log.jsonl") if l.strip()]
    fr = [d for d in ff if "frank" in d["run"]]
    t = np.array([d["t_h"] for d in fr])
    fig, axes = plt.subplots(1, 3, figsize=(13.8, 4.3))

    a = axes[0]
    froude = np.array([d["interior_median_froude_of_fast"] for d in fr])
    a.axhspan(1.0, 4.2, color=ROAD, alpha=.055, lw=0, zorder=0)
    a.plot(t, froude, "o-", color=ROAD, lw=1.9, ms=5, zorder=3)
    a.axhline(1.0, color=FAINT, lw=.9, ls=":", zorder=2)
    a.set_ylabel("median Froude of the fast faces")
    a.set_ylim(0, 4.2); a.set_xlim(13.9, 20.4)
    a.set_title("Froude falls as the rivers fill", fontsize=10.5, pad=8)
    a.text(20.25, 3.95, "above Fr 1 the local-inertial\nscheme omits the term\nthat matters",
           fontsize=8, color=ROAD, ha="right", va="top", linespacing=1.5)
    a.text(20.25, .28, "3.53 \u2192 1.68", fontsize=9.5, color=ROAD,
           ha="right", fontweight="bold")
    k = int(np.argmax(np.diff(froude) > 0)) + 1     # the single reversal
    a.annotate("one 0.02 reversal", xy=(t[k], froude[k]), xytext=(t[k] - .55, 2.75),
               fontsize=8, color=FAINT,
               arrowprops=dict(arrowstyle="->", color=FAINT, lw=.9,
                               connectionstyle="arc3,rad=-.25"))

    b = axes[1]
    vol = np.array([d["volume_m3"] / 1e6 for d in fr])
    b.plot(t, vol, "o-", color=CHAN, lw=1.9, ms=5)
    b.set_ylabel("water in the domain (10$^6$ m\u00b3)")
    b.set_xlim(13.9, 20.4)
    b.set_title("Volume rises monotonically", fontsize=10.5, pad=8)
    b.text(20.25, vol.min(), "every one of\nthe ten samples", fontsize=8,
           color=CHAN, ha="right", va="bottom", linespacing=1.5)

    c = axes[2]
    ghost = np.array([d["ghost_outfall_max_v_ms"] for d in fr])
    c.plot(t, ghost, "o-", color=WARN, lw=1.9, ms=5)
    c.set_ylabel("outfall boundary velocity (m/s)")
    c.set_ylim(0, 190); c.set_xlim(13.9, 20.4)
    c.set_title("The CFL throttle eases", fontsize=10.5, pad=8)
    c.text(20.25, 178, "169 \u2192 57 m/s at the\nfree-outfall boundary\n"
           "\u2014 this is ML-3, and it is\nwhat set the run's cost",
           fontsize=8, color=WARN, ha="right", va="top", linespacing=1.5)

    for ax in axes:
        ax.set_xlabel(T0_LABEL)
    fig.suptitle("Franklinton numerical health, sampled while the run was in progress",
                 fontsize=13.5, y=1.10)
    fig.text(.5, 1.035, "No cell is negative or non-finite in any sample. "
             "The high-Froude phase is transient, not divergence.",
             ha="center", fontsize=9.5, color=FAINT)
    fig.tight_layout()
    fig.savefig("figures/fig3_numerical_health.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print("figures/fig3_numerical_health.png")


if __name__ == "__main__":
    S = load_series()
    fig1(S); fig2(); fig3()
