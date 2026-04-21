"""
Signal chain block diagram — clean two-row layout, no crossing arrows.

Row 1 (top):  Excitation path  Exc DDS -> BNC -> coax -> DUT -> TIA
Row 2 (bottom): Digital path   ADC <- CIC <- I/Q Demod <- FIR <- C/G
                                                ^
                                           Ref DDS (below)
Bias chain: small row at the very bottom, arrow up into DUT.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

# Colours
_FPGA   = "#DDEEFF"   # light blue — digital
_ANALOG = "#FFFACD"   # light yellow — analog
_DUT    = "#DDFFDD"   # light green — device
_TIA    = "#FFE4E1"   # light red — noise-critical
_PARA   = "#C0392B"   # red — parasitic annotations
_ARROW  = "#2C3E50"   # dark arrow colour
_WARN   = "#D35400"   # bias / warning colour

_EDGEF  = "#1A5276"   # FPGA border
_EDGEA  = "#7D6608"   # analog border
_EDGED  = "#1E8449"   # DUT border
_EDGET  = "#922B21"   # TIA border


def _box(ax, cx, cy, w, h, label, sub="", fc=_FPGA, ec=_EDGEF, fs=8):
    """Centred rounded box."""
    rect = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.05",
        facecolor=fc, edgecolor=ec, linewidth=1.3, zorder=3,
    )
    ax.add_patch(rect)
    dy = 0.10 if sub else 0
    ax.text(cx, cy + dy, label, ha="center", va="center",
            fontsize=fs, fontweight="bold", color="black", zorder=4)
    if sub:
        ax.text(cx, cy - 0.17, sub, ha="center", va="center",
                fontsize=6.2, color="#555555", zorder=4)


def _arrow(ax, x0, y, x1, color=_ARROW, lw=1.5):
    """Horizontal arrow."""
    ax.annotate("", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw), zorder=5)


def _varrow(ax, x, y0, y1, color=_ARROW, lw=1.5):
    """Vertical arrow."""
    ax.annotate("", xy=(x, y1), xytext=(x, y0),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw), zorder=5)


def _para(ax, x, y, text, ha="center", fs=6.5):
    ax.text(x, y, text, ha=ha, va="center", fontsize=fs,
            color=_PARA, fontstyle="italic", zorder=6)


def _coax(ax, x0, x1, y, label_above="", label_below=""):
    """Thick coax line with optional annotations."""
    ax.plot([x0, x1], [y, y], color="#455A64", lw=4,
            solid_capstyle="round", zorder=2)
    ax.plot([x0, x1], [y, y], color="#CFD8DC", lw=1.8,
            linestyle="--", zorder=3)
    mid = (x0 + x1) / 2
    if label_above:
        _para(ax, mid, y + 0.22, label_above)
    if label_below:
        _para(ax, mid, y - 0.22, label_below)


def make_signal_chain_figure(
    f0_MHz: float = 1.0,
    Rf_kohm: float = 10.0,
    In_fA: float = 2.0,
    Vn_nV: float = 5.0,
    adc_bits: int = 16,
    dec_R: int = 32,
    lpf_bw_hz: float = 50e3,
    Cox_fF: float = 34.5,
    area_um2: float = 100.0,
    extra_dec: int = 1,
) -> plt.Figure:

    fig, ax = plt.subplots(figsize=(14, 5.2))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    # ── Row centres ──────────────────────────────────────────────────────────
    Y1   = 3.8    # excitation / analog path
    Y2   = 2.3    # digital processing path
    Y3   = 0.7    # ref DDS + bias chain
    BH   = 0.72   # standard box height
    BHS  = 0.55   # small box height (bias chain)

    # ── Row 1 — Excitation path (left → right) ───────────────────────────────

    # Exc DDS
    _box(ax, 1.0,  Y1, 1.5, BH, "Exc DDS",
         f"f₀={f0_MHz:.2f} MHz\n32-bit FTW", fc=_FPGA, ec=_EDGEF)
    _arrow(ax, 1.75, Y1, 2.2)

    # BNC connector
    _box(ax, 2.6,  Y1, 0.7, BH, "BNC", "50 Ω", fc=_ANALOG, ec=_EDGEA)
    # Coax line  BNC → DUT
    _coax(ax, 2.95, 5.1, Y1,
          label_above="C₋ₜₐₙ ≈ 100 pF/m",
          label_below="L₋ₜₐₙ ≈ 250 nH/m")

    # DUT box
    _box(ax, 5.8, Y1, 1.35, BH, "DUT",
         f"Cox = {Cox_fF:.1f} fF\nCₙₛₒ₂ₑₐ ≈ 2–5 pF",
         fc=_DUT, ec=_EDGED)
    # Cable DUT → TIA
    _coax(ax, 6.47, 7.85, Y1,
          label_below="Cₚₚₑ ≈ 50 pF·m⁻¹")

    # TIA
    _box(ax, 8.85, Y1, 1.9, BH, "TIA",
         f"Rf={Rf_kohm:.0f} kΩ  In={In_fA:.1f} fA/√Hz  Vn={Vn_nV:.1f} nV/√Hz",
         fc=_TIA, ec=_EDGET, fs=7.5)

    # TIA input cap annotation (below TIA)
    _para(ax, 8.85, Y1 - 0.53, "Cᵢₙ ≈ 2–5 pF  (op-amp input + stray)")

    # ── Vertical connector TIA → ADC ─────────────────────────────────────────
    _varrow(ax, 9.5, Y1 - BH / 2, Y2 + BH / 2)

    # ── Row 2 — Digital processing (right → left) ───────────────────────────

    # ADC
    _box(ax, 9.5, Y2, 1.9, BH, "ADC",
         f"{adc_bits}-bit\nfs={int(round(125e6/1e6))} MS/s",
         fc=_FPGA, ec=_EDGEF)
    _arrow(ax, 8.55, Y2, 7.85)

    # CIC
    dec_fs_khz = 125e3 / dec_R
    _box(ax, 7.2, Y2, 1.25, BH, "CIC",
         f"R={dec_R}×{extra_dec} N=4\n→{dec_fs_khz/extra_dec:.0f} kHz",
         fc=_FPGA, ec=_EDGEF)
    _arrow(ax, 6.58, Y2, 5.95)

    # I/Q Demodulator
    _box(ax, 5.3, Y2, 1.25, BH, "I/Q Demod",
         "I = x·cos ωt\nQ = x·sin ωt",
         fc=_FPGA, ec=_EDGEF)
    _arrow(ax, 4.67, Y2, 4.1)

    # FIR LPF
    n_fir_approx = int(round(125e3 / dec_R / extra_dec / lpf_bw_hz * 11))
    n_fir_approx = max(11, min(n_fir_approx, 2001))
    bw_label = f"{lpf_bw_hz/1e3:.1f} kHz" if lpf_bw_hz >= 1000 else f"{lpf_bw_hz:.1f} Hz"
    _box(ax, 3.45, Y2, 1.25, BH, "FIR LPF",
         f"BW = {bw_label}\n≈ {n_fir_approx} taps",
         fc=_FPGA, ec=_EDGEF)
    _arrow(ax, 2.82, Y2, 2.2)

    # C/G Extraction
    _box(ax, 1.45, Y2, 1.4, BH, "C,G Extract",
         "C=2Q/(VₑωRf)\nG=−2I/(VₑRf)",
         fc=_FPGA, ec=_EDGEF, fs=7.5)

    # ── Row 3 — Ref DDS and Bias chain ───────────────────────────────────────

    # Ref DDS (feeds I/Q demod from below)
    _box(ax, 5.3, Y3, 1.25, BHS, "Ref DDS",
         "coherent cos/sin", fc=_FPGA, ec=_EDGEF, fs=7.5)
    _varrow(ax, 5.3, Y3 + BHS / 2, Y2 - BH / 2)

    # Bias chain
    _box(ax, 8.0, Y3, 1.1, BHS, "Bias DAC",
         "PCM1794A\n24-bit I²S", fc=_ANALOG, ec=_EDGEA, fs=7)
    _arrow(ax, 8.55, Y3, 8.9)
    _box(ax, 9.25, Y3, 0.6, BHS, "LPF", "1.6 Hz\nRC", fc=_ANALOG, ec=_EDGEA, fs=7)
    _arrow(ax, 9.55, Y3, 9.9)
    _box(ax, 10.3, Y3, 0.7, BHS, "HV Amp",
         "±25 V\nOPA548", fc=_ANALOG, ec=_EDGEA, fs=7)

    # Bias arrow: HV Amp → DUT (goes up)
    ax.annotate("", xy=(5.8, Y1 - BH / 2),
                xytext=(10.3, Y3 + BHS / 2),
                arrowprops=dict(
                    arrowstyle="->", color=_WARN, lw=1.6,
                    connectionstyle="arc3,rad=-0.25",
                ), zorder=5)
    ax.text(10.6, (Y1 + Y3) / 2 + 0.2, "Vₛᵢₐₑ\n±25 V",
            ha="left", va="center", fontsize=7, color=_WARN, fontstyle="italic")

    # ── Calibration note ─────────────────────────────────────────────────────
    ax.text(1.45, 1.45,
            "Open / Short / Load calibration removes Cₚₚₒₓₑ + C₋ₜₐₙ",
            ha="center", va="center", fontsize=7, color=_EDGED,
            bbox=dict(fc=_DUT, ec=_EDGED, boxstyle="round,pad=0.25", lw=0.8))

    # ── Legend ───────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(fc=_FPGA,   ec=_EDGEF, label="FPGA / Digital"),
        mpatches.Patch(fc=_ANALOG, ec=_EDGEA, label="Analog"),
        mpatches.Patch(fc=_DUT,    ec=_EDGED, label="DUT"),
        mpatches.Patch(fc=_TIA,    ec=_EDGET, label="TIA (noise-critical)"),
    ]
    ax.legend(handles=legend_items, loc="lower right",
              fontsize=7.5, framealpha=0.9, ncol=2,
              bbox_to_anchor=(1.0, 0.01))

    # ── Title ────────────────────────────────────────────────────────────────
    ax.set_title(
        f"Signal Chain  ·  f₀={f0_MHz:.2f} MHz"
        f"  ·  Rf={Rf_kohm:.0f} kΩ"
        f"  ·  {adc_bits}-bit ADC"
        f"  ·  CIC×{dec_R}"
        f"  ·  Extra dec×{extra_dec}"
        f"  ·  LPF {bw_label}",
        fontsize=9.5, pad=6,
    )

    fig.tight_layout(pad=0.4)
    return fig
