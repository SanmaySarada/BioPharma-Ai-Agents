"""Generate a clean, professional ARCHITECTURE.png for omni-ai-agents."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
COLORS = {
    "input":       {"fill": "#DBEAFE", "edge": "#3B82F6", "text": "#1E3A5F"},  # blue
    "agent":       {"fill": "#D1FAE5", "edge": "#10B981", "text": "#064E3B"},  # green
    "output":      {"fill": "#FEF3C7", "edge": "#F59E0B", "text": "#78350F"},  # amber
    "comparison":  {"fill": "#EDE9FE", "edge": "#8B5CF6", "text": "#3B0764"},  # purple
    "decision":    {"fill": "#FEE2E2", "edge": "#EF4444", "text": "#7F1D1D"},  # red
    "pass":        {"fill": "#D1FAE5", "edge": "#10B981", "text": "#064E3B"},  # green
    "warning":     {"fill": "#FEF3C7", "edge": "#F59E0B", "text": "#78350F"},  # amber
    "halt":        {"fill": "#FEE2E2", "edge": "#EF4444", "text": "#7F1D1D"},  # red
    "stage_bg_a":  "#EFF6FF",   # light blue for Track A
    "stage_bg_b":  "#FFF7ED",   # light orange for Track B
    "section_line": "#94A3B8",
}

FONT = "Helvetica Neue"
FONT_FALLBACK = "sans-serif"

# ---------------------------------------------------------------------------
# Figure setup
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(16, 22))
ax.set_xlim(0, 16)
ax.set_ylim(0, 22)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("white")

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def draw_box(x, y, w, h, style, text, fontsize=8.5, bold=False, radius=0.15):
    """Draw a rounded rectangle with centered text."""
    c = COLORS[style]
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=c["fill"], edgecolor=c["edge"], linewidth=1.4,
        transform=ax.transData, zorder=3,
    )
    ax.add_patch(box)
    weight = "bold" if bold else "normal"
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center", fontsize=fontsize, color=c["text"],
        fontweight=weight, fontfamily=[FONT, FONT_FALLBACK],
        zorder=4, linespacing=1.4,
    )
    return box


def draw_diamond(cx, cy, rx, ry, style, text, fontsize=8):
    """Draw a diamond (decision) shape."""
    c = COLORS[style]
    verts = [(cx, cy + ry), (cx + rx, cy), (cx, cy - ry), (cx - rx, cy), (cx, cy + ry)]
    poly = plt.Polygon(verts, closed=True, facecolor=c["fill"],
                        edgecolor=c["edge"], linewidth=1.4, zorder=3)
    ax.add_patch(poly)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fontsize,
            color=c["text"], fontweight="bold", fontfamily=[FONT, FONT_FALLBACK],
            zorder=4, linespacing=1.35)


def arrow(x1, y1, x2, y2, color="#64748B", lw=1.2, style="-|>", label="",
          label_side="right", label_offset=0.12):
    """Draw an arrow between two points."""
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                        connectionstyle="arc3,rad=0"),
        zorder=2,
    )
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if label_side == "right":
            mx += label_offset
        elif label_side == "left":
            mx -= label_offset
        elif label_side == "above":
            my += label_offset
        ax.text(mx, my, label, fontsize=7, color=color, ha="center", va="center",
                fontfamily=[FONT, FONT_FALLBACK], fontstyle="italic", zorder=5)


def arrow_curved(x1, y1, x2, y2, color="#64748B", lw=1.2, rad=0.3, label="",
                 label_pos=None, label_fontsize=7):
    """Draw a curved arrow."""
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                        connectionstyle=f"arc3,rad={rad}"),
        zorder=2,
    )
    if label and label_pos:
        ax.text(label_pos[0], label_pos[1], label, fontsize=label_fontsize,
                color=color, ha="center", va="center",
                fontfamily=[FONT, FONT_FALLBACK], fontstyle="italic", zorder=5)


def section_label(y, text, fontsize=11):
    """Draw a centered stage label with subtle horizontal rules."""
    ax.text(8, y, text, ha="center", va="center", fontsize=fontsize,
            fontweight="bold", color="#334155", fontfamily=[FONT, FONT_FALLBACK],
            zorder=5)
    rule_w = 4.5
    lx = 8 - len(text) * 0.16 - rule_w - 0.3
    rx = 8 + len(text) * 0.16 + 0.3
    ax.plot([lx, lx + rule_w], [y, y], color=COLORS["section_line"],
            lw=0.6, zorder=1, alpha=0.5)
    ax.plot([rx, rx + rule_w], [y, y], color=COLORS["section_line"],
            lw=0.6, zorder=1, alpha=0.5)


def track_background(x, y, w, h, color, label, label_y_offset=0):
    """Draw a subtle background rectangle for a track."""
    bg = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.25",
        facecolor=color, edgecolor="#CBD5E1", linewidth=0.8,
        linestyle="--", alpha=0.5, zorder=1,
    )
    ax.add_patch(bg)
    ax.text(x + w / 2, y + h + 0.15 + label_y_offset, label,
            ha="center", va="bottom", fontsize=9.5, fontweight="bold",
            color="#475569", fontfamily=[FONT, FONT_FALLBACK], zorder=5)


# ===========================================================================
# TITLE
# ===========================================================================
ax.text(8, 21.5, "omni-ai-agents Pipeline", ha="center", va="center",
        fontsize=20, fontweight="bold", color="#0F172A",
        fontfamily=[FONT, FONT_FALLBACK])
ax.text(8, 21.1, "High-Level Architecture", ha="center", va="center",
        fontsize=11, color="#64748B", fontfamily=[FONT, FONT_FALLBACK])

# ===========================================================================
# PROTOCOL PARSING (optional)
# ===========================================================================
section_label(20.55, "Protocol Parsing (optional)")

bw, bh = 2.8, 0.7  # box width, height
draw_box(1.8, 19.6, bw, bh, "input",
         "Protocol Document\n(.docx)", fontsize=8.5, bold=True)
draw_box(6.6, 19.6, bw, bh, "agent",
         "Protocol Parser\nGemini", fontsize=8.5, bold=True)
draw_box(11.4, 19.6, bw, bh, "output",
         "config.yaml\nTrial Parameters", fontsize=8.5, bold=True)

arrow(1.8 + bw, 19.95, 6.6, 19.95)
arrow(6.6 + bw, 19.95, 11.4, 19.95)

# ===========================================================================
# STAGE 1 — DATA SIMULATION
# ===========================================================================
section_label(19.0, "Stage 1 \u2014 Data Simulation")

draw_box(5.6, 18.1, 4.8, 0.7, "agent",
         "Simulator Agent  \u2022  Gemini", fontsize=9, bold=True)
arrow(8, 19.0 - 0.22, 8, 18.1 + 0.7, color="#64748B")

draw_box(4.6, 17.1, 6.8, 0.7, "output",
         "Synthetic Trial Data  \u2022  300 patients \u00d7 26 visits", fontsize=9)
arrow(8, 18.1, 8, 17.1 + 0.7)

# ===========================================================================
# STAGE 2 — PARALLEL ANALYSIS
# ===========================================================================
section_label(16.45, "Stage 2 \u2014 Parallel Analysis")

# Track backgrounds
track_background(0.8, 11.5, 6.4, 4.5, COLORS["stage_bg_a"],
                 "Track A \u2014 Gemini 2.5 Pro")
track_background(8.8, 11.5, 6.4, 4.5, COLORS["stage_bg_b"],
                 "Track B \u2014 OpenAI o3")

# Fork arrows from synthetic data to both tracks
arrow(6, 17.1, 4.0, 16.0 + 0.02)
arrow(10, 17.1, 12.0, 16.0 + 0.02)

# --- Track A boxes ---
ta_x = 1.3
ta_w = 5.4
ta_bh = 0.65

# SDTM
draw_box(ta_x, 15.35, ta_w, ta_bh, "agent",
         "SDTM Agent\nMap raw data to CDISC format", fontsize=8)
draw_box(ta_x, 14.4, ta_w, ta_bh, "output",
         "DM.csv  +  VS.csv\nDemographics & Vital Signs", fontsize=8)
arrow(ta_x + ta_w/2, 15.35, ta_x + ta_w/2, 14.4 + ta_bh)

# ADaM
draw_box(ta_x, 13.45, ta_w, ta_bh, "agent",
         "ADaM Agent\nDerive ADSL + ADTTE datasets", fontsize=8)
arrow(ta_x + ta_w/2, 14.4, ta_x + ta_w/2, 13.45 + ta_bh)

draw_box(ta_x, 12.5, ta_w, ta_bh, "output",
         "ADSL.csv  +  ADTTE.rds\nSubject-Level + Time-to-Event", fontsize=8)
arrow(ta_x + ta_w/2, 13.45, ta_x + ta_w/2, 12.5 + ta_bh)

# Stats
draw_box(ta_x, 11.75, ta_w, 0.55, "agent",
         "Stats Agent  \u2022  Kaplan-Meier + Cox Regression", fontsize=7.5)
arrow(ta_x + ta_w/2, 12.5, ta_x + ta_w/2, 11.75 + 0.55)

# --- Track B boxes ---
tb_x = 9.3
tb_w = 5.4

draw_box(tb_x, 15.35, tb_w, ta_bh, "agent",
         "SDTM Agent\nMap raw data to CDISC format", fontsize=8)
draw_box(tb_x, 14.4, tb_w, ta_bh, "output",
         "DM.csv  +  VS.csv\nDemographics & Vital Signs", fontsize=8)
arrow(tb_x + tb_w/2, 15.35, tb_x + tb_w/2, 14.4 + ta_bh)

draw_box(tb_x, 13.45, tb_w, ta_bh, "agent",
         "ADaM Agent\nDerive ADSL + ADTTE datasets", fontsize=8)
arrow(tb_x + tb_w/2, 14.4, tb_x + tb_w/2, 13.45 + ta_bh)

draw_box(tb_x, 12.5, tb_w, ta_bh, "output",
         "ADSL.csv  +  ADTTE.rds\nSubject-Level + Time-to-Event", fontsize=8)
arrow(tb_x + tb_w/2, 13.45, tb_x + tb_w/2, 12.5 + ta_bh)

draw_box(tb_x, 11.75, tb_w, 0.55, "agent",
         "Stats Agent  \u2022  Kaplan-Meier + Cox Regression", fontsize=7.5)
arrow(tb_x + tb_w/2, 12.5, tb_x + tb_w/2, 11.75 + 0.55)

# Output rows beneath each track
draw_box(ta_x, 11.0, ta_w, 0.55, "output",
         "Tables + KM Plot + Results", fontsize=8)
arrow(ta_x + ta_w/2, 11.75, ta_x + ta_w/2, 11.0 + 0.55)

draw_box(tb_x, 11.0, tb_w, 0.55, "output",
         "Tables + KM Plot + Results", fontsize=8)
arrow(tb_x + tb_w/2, 11.75, tb_x + tb_w/2, 11.0 + 0.55)

# ===========================================================================
# STAGE 3 — CROSS-TRACK COMPARISON
# ===========================================================================
section_label(10.2, "Stage 3 \u2014 Cross-Track Comparison")

draw_box(4.0, 9.05, 8.0, 0.85, "comparison",
         "Stage Comparator\nCompare SDTM, ADaM, Stats outputs\nbetween Track A and Track B",
         fontsize=8.5, bold=True)

# Arrows from each track's output into comparator
arrow(ta_x + ta_w/2, 11.0, 6, 9.05 + 0.85)
arrow(tb_x + tb_w/2, 11.0, 10, 9.05 + 0.85)

# ===========================================================================
# STAGE 4 — RESOLUTION
# ===========================================================================
section_label(8.55, "Stage 4 \u2014 Resolution")

# Decision diamond
draw_diamond(3.5, 7.6, 1.6, 0.65, "decision", "Tracks\nAgree?", fontsize=8)
arrow(8, 9.05, 3.5, 7.6 + 0.65)

# Resolution loop box
draw_box(6.2, 7.1, 5.5, 0.9, "comparison",
         "Resolution Loop\nDiagnose failing track\nRetry with targeted hints (up to 2 iterations)",
         fontsize=8)

# Arrow from diamond "No" to resolution box
arrow(3.5 + 1.6, 7.6, 6.2, 7.55, label="No", label_side="above", label_offset=0.2)

# Arrow from resolution loop back to diamond
arrow_curved(6.2, 7.55, 3.5 + 1.6, 7.65, rad=-0.4,
             label="Retry", label_pos=(4.7, 8.15), label_fontsize=7)

# Outcomes row
outcome_y = 5.95
outcome_h = 0.65
outcome_w = 2.6

draw_box(2.2, outcome_y, outcome_w, outcome_h, "pass",
         "PASS", fontsize=12, bold=True)
draw_box(6.7, outcome_y, outcome_w, outcome_h, "warning",
         "WARNING", fontsize=12, bold=True)
draw_box(11.2, outcome_y, outcome_w, outcome_h, "halt",
         "HALT", fontsize=12, bold=True)

# Diamond → PASS (Yes)
arrow(3.5, 7.6 - 0.65, 3.5, outcome_y + outcome_h,
      label="Yes", label_side="left", label_offset=0.35)

# Resolution → WARNING / HALT
arrow(8.95, 7.1, 8.0, outcome_y + outcome_h,
      label="Diverge", label_side="left", label_offset=0.55)
arrow(11.7, 7.1, 12.5, outcome_y + outcome_h,
      label="Max retries\nexhausted", label_side="right", label_offset=0.7)

# ===========================================================================
# STAGE 5 — REPORTING
# ===========================================================================
section_label(5.35, "Stage 5 \u2014 Reporting")

draw_box(4.8, 4.3, 6.4, 0.7, "agent",
         "Medical Writer Agent  \u2022  Gemini\nGenerates Clinical Study Report",
         fontsize=8.5, bold=True)
arrow(8, outcome_y, 8, 4.3 + 0.7)

draw_box(3.0, 3.2, 10.0, 0.8, "output",
         "Clinical Study Report (.docx)\n"
         "Demographics Table  |  KM Analysis  |  Cox Regression  |  "
         "KM Survival Plot  |  Statistical Narrative  |  Verdict Status",
         fontsize=8)
arrow(8, 4.3, 8, 3.2 + 0.8)

# ===========================================================================
# LEGEND
# ===========================================================================
legend_y = 1.85
legend_h = 0.45
legend_w = 2.0
gap = 0.45
labels = [
    ("input",      "Input"),
    ("agent",      "LLM Agent"),
    ("output",     "Output"),
    ("comparison", "Comparison"),
    ("decision",   "Decision"),
]
total_w = len(labels) * legend_w + (len(labels) - 1) * gap
start_x = 8 - total_w / 2

ax.text(8, legend_y + legend_h + 0.35, "Legend", ha="center", va="center",
        fontsize=10, fontweight="bold", color="#334155",
        fontfamily=[FONT, FONT_FALLBACK])

for i, (style, label) in enumerate(labels):
    lx = start_x + i * (legend_w + gap)
    draw_box(lx, legend_y, legend_w, legend_h, style, label,
             fontsize=8.5, bold=True, radius=0.1)

# ===========================================================================
# FOOTNOTES
# ===========================================================================
fn_y = 1.15
ax.text(8, fn_y, "All R code executes inside isolated Docker containers (no host execution)",
        ha="center", va="center", fontsize=8, color="#64748B",
        fontfamily=[FONT, FONT_FALLBACK], fontstyle="italic")
ax.text(8, fn_y - 0.4,
        "Each agent:  Generate R code (LLM)  \u2192  Validate  \u2192  Execute (Docker)  \u2192  Retry on failure (up to 3\u00d7)",
        ha="center", va="center", fontsize=8, color="#64748B",
        fontfamily=[FONT, FONT_FALLBACK], fontstyle="italic")

# ===========================================================================
# Save
# ===========================================================================
fig.savefig("/Users/sanmaysarada/omni-ai-agents/ARCHITECTURE.png",
            dpi=180, bbox_inches="tight", pad_inches=0.4,
            facecolor="white", edgecolor="none")
plt.close(fig)
print("Done – saved ARCHITECTURE.png")
