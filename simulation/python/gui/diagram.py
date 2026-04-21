"""
Signal chain block diagram with parasitics.

Returns a matplotlib Figure showing the complete signal path from
FPGA DDS excitation through cables, probe, DUT, TIA, and back to ADC/demodulator.
Parasitic elements are annotated at each stage.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Arc
import matplotlib.patheffects as pe
import numpy as np


# ── colour palette ────────────────────────────────────────────────────────────
C_FPGA   = "#BBDEFB"   # blue-100 — digital domain
C_FPGA_B = "#1565C0"   # label colour
C_ANALOG = "#FFF9C4"   # yellow-100 — analog
C_PHYS   = "#C8E6C9"   # green-100 — physical / DUT
C_BLOCK  = "#FFFFFF"   # block fill
C_PARA   = "#B71C1C"   # parasitic annotation (red-900)
C_ARROW  = "#37474F"   # signal arrows
C_WARN   = "#E65100"   # warning / note


def _box(ax, x, y, w, h, label, sublabel="", fc=C_BLOCK, fontsize=8,
         label_color="black", border="#455A64"):
    """Draw a labelled rounded rectangle."""
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.04",
                          facecolor=fc, edgecolor=border, linewidth=1.2, zorder=3)
    ax.add_patch(rect)
    cy = y + h / 2 + (0.08 if sublabel else 0)
    ax.text(x + w / 2, cy, label, ha="center", va="center",
            fontsize=fontsize, fontweight="bold", color=label_color, zorder=4)
    if sublabel:
        ax.text(x + w / 2, y + h / 2 - 0.14, sublabel, ha="center", va="center",
                fontsize=6.5, color="#546E7A", zorder=4)


def _arrow(ax, x0, y0, x1, y1, color=C_ARROW, lw=1.4, style="->"):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw),
                zorder=5)


def _para(ax, x, y, text, ha="left", color=C_PARA, fontsize=7, rotation=0):
    """Red parasitic annotation."""
    ax.text(x, y, text, ha=ha, va="center", fontsize=fontsize,
            color=color, style="italic", rotation=rotation, zorder=6)


def _section(ax, x, y, w, h, label, fc, lc):
    rect = mpatches.FancyBboxPatch((x, y), w, h,
                                   boxstyle="round,pad=0.1",
                                   facecolor=fc, edgecolor=lc,
                                   linewidth=1.5, alpha=0.55, zorder=0)
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h - 0.18, label, ha="center", va="top",
            fontsize=8.5, fontweight="bold", color=lc, zorder=1)


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
) -> plt.Figure:
    """
    Build the signal chain figure.  Parameter values are overlaid on
    the relevant blocks so the diagram stays in sync with the GUI.
    """
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 7)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    # ── Section backgrounds ────────────────────────────────────────────────────

    _section(ax, 0.1,  0.3, 4.4, 6.4, "FPGA  ·  Digital Domain",       C_FPGA,   C_FPGA_B)
    _section(ax, 4.7,  0.3, 4.6, 6.4, "Analog Front-End",               C_ANALOG, "#827717")
    _section(ax, 9.5,  0.3, 5.3, 6.4, "Physical  ·  DUT + Probe Station", C_PHYS, "#1B5E20")

    # ── FPGA blocks ───────────────────────────────────────────────────────────

    # Excitation DDS
    _box(ax, 0.3, 5.2, 1.6, 0.7,
         "Excitation DDS",
         f"f₀ = {f0_MHz:.2f} MHz\n32-bit phase acc",
         fc="#FFF3E0")

    # Reference DDS (coherent)
    _box(ax, 0.3, 3.9, 1.6, 0.7,
         "Reference DDS",
         "cos/sin, same clock\nfully coherent",
         fc="#FFF3E0")

    # ADC (future)
    _box(ax, 0.3, 2.6, 1.6, 0.7,
         "ADC",
         f"{adc_bits}-bit  ·  fs_in\n(FMC card, TBD)",
         fc="#F3E5F5", border="#7B1FA2")

    # Pre-demod CIC
    _box(ax, 2.2, 2.6, 1.8, 0.7,
         "Pre-BW Filter",
         f"CIC  R={dec_R}",
         fc="#E8F5E9")

    # I/Q Demodulator
    _box(ax, 2.2, 3.9, 1.8, 0.7,
         "I/Q Demodulator",
         "I=x·cos  Q=x·sin",
         fc="#E8F5E9")

    # Post-demod LPF
    _box(ax, 2.2, 5.2, 1.8, 0.7,
         "Post-BW Filter",
         f"FIR LPF  BW={lpf_bw_hz/1e3:.1f} kHz",
         fc="#E8F5E9")

    # C/G extraction
    _box(ax, 2.2, 1.3, 1.8, 0.7,
         "C, G Extraction",
         "C = 2Q/(Vₑ·ω·Rf)\nG = −2I/(Vₑ·Rf)",
         fc="#E1F5FE", border="#0288D1")

    # ── FPGA internal arrows ──────────────────────────────────────────────────

    # Excit DDS → (right, to analog path) — drawn later
    # Ref DDS → I/Q demod
    _arrow(ax, 1.9, 4.25, 2.2, 4.25)
    # ADC → Pre-CIC
    _arrow(ax, 1.9, 2.95, 2.2, 2.95)
    # Pre-CIC → I/Q demod
    _arrow(ax, 3.1, 3.3, 3.1, 3.9)
    # I/Q demod → Post-LPF
    _arrow(ax, 3.1, 4.6, 3.1, 5.2)
    # Post-LPF → C/G
    ax.annotate("", xy=(3.1, 2.0), xytext=(3.1, 5.2),
                arrowprops=dict(arrowstyle="->", color=C_ARROW, lw=1.4,
                                connectionstyle="arc3,rad=0.0"),
                zorder=5)

    # ── Analog front-end ─────────────────────────────────────────────────────

    # BNC connector
    _box(ax, 4.85, 5.2, 0.8, 0.7, "BNC", "50 Ω\noutput", fc="#ECEFF1", fontsize=7)

    # Coax cable (excitation)
    ax.plot([5.65, 7.2], [5.55, 5.55], color="#455A64", lw=3, solid_capstyle="round", zorder=3)
    ax.plot([5.65, 7.2], [5.55, 5.55], color="#CFD8DC", lw=1.5, zorder=4, linestyle="--")
    _para(ax, 6.0, 5.80, "C_cable ≈ 100 pF/m", ha="center")
    _para(ax, 6.0, 5.68, "L_cable ≈ 250 nH/m", ha="center")

    # Bias Tee
    _box(ax, 7.2, 5.2, 1.0, 0.7, "Bias Tee", "DC block\n+ RF pass", fc="#ECEFF1", fontsize=7)

    # Excit DDS → BNC arrow (leave FPGA)
    _arrow(ax, 1.9, 5.55, 4.85, 5.55)
    ax.text(2.9, 5.70, "Vexc out", ha="center", fontsize=7, color="#455A64")

    # Bias DAC path
    _box(ax, 4.85, 0.6, 1.2, 0.7, "Bias DAC", f"PCM1794A\n24-bit I²S", fc="#FBE9E7", fontsize=7)
    _box(ax, 6.3,  0.6, 1.0, 0.7, "Low-pass\nFilter",   "RC 1.6 Hz\ncutoff", fc="#FBE9E7", fontsize=7)
    _box(ax, 7.5,  0.6, 1.0, 0.7, "HV amp",  "OPA548\n±25 V", fc="#FBE9E7", fontsize=7)
    _arrow(ax, 4.85, 0.95, 4.85, 1.0)  # placeholder — actual from FPGA not shown
    _arrow(ax, 6.05, 0.95, 6.3, 0.95)
    _arrow(ax, 7.3,  0.95, 7.5, 0.95)
    # Bias DAC cable to bias tee
    ax.annotate("", xy=(7.7, 5.2), xytext=(7.7, 1.3),
                arrowprops=dict(arrowstyle="->", color="#E65100", lw=1.2,
                                connectionstyle="arc3,rad=0.3"),
                zorder=5)
    ax.text(8.2, 3.2, "DC bias\ncable", ha="center", fontsize=7, color=C_WARN, style="italic")
    _para(ax, 8.25, 2.95, "V_bias = 0..±25V", ha="center", color=C_WARN, fontsize=6.5)

    # TIA block
    _box(ax, 4.85, 2.0, 1.8, 1.8,
         "TIA",
         f"Rf = {Rf_kohm:.0f} kΩ\nIn = {In_fA:.1f} fA/√Hz\nVn = {Vn_nV:.1f} nV/√Hz",
         fc="#FFCDD2", border="#C62828", fontsize=7.5)
    # Feedback annotation
    ax.annotate("", xy=(4.85, 3.3), xytext=(6.65, 3.3),
                arrowprops=dict(arrowstyle="->", color="#C62828", lw=1.0,
                                connectionstyle="arc3,rad=-0.4"),
                zorder=4)
    ax.text(5.75, 3.9, f"Rf={Rf_kohm:.0f}kΩ  Cf", ha="center", fontsize=6.5,
            color="#C62828", style="italic")

    # TIA input parasitic
    _para(ax, 4.75, 2.5, "C_in ≈ 2–5 pF\n(op-amp + stray)", ha="right", fontsize=6.5)

    # Cable from probe to TIA input
    ax.plot([4.85, 4.1], [2.9, 2.9], color="#455A64", lw=3, solid_capstyle="round", zorder=3)
    ax.plot([4.85, 4.1], [2.9, 2.9], color="#CFD8DC", lw=1.5, zorder=4, linestyle="--")
    _para(ax, 4.47, 2.68, "C_return ≈ 50 pF", ha="center")

    # TIA → ADC
    _arrow(ax, 4.85, 2.9, 1.9, 2.9)
    ax.text(3.4, 3.05, "V_TIA", ha="center", fontsize=7, color="#455A64")

    # ── Physical section — probe + DUT ────────────────────────────────────────

    # Probe arms (triangular needles)
    # Top probe (excitation)
    probe_top_x, probe_top_y = 10.3, 5.1
    ax.annotate("", xy=(probe_top_x, probe_top_y),
                xytext=(8.2, 5.55),
                arrowprops=dict(arrowstyle="-", color="#37474F", lw=2.5),
                zorder=5)
    ax.plot([probe_top_x], [probe_top_y], 'v', color="#37474F", markersize=10, zorder=6)
    _para(ax, probe_top_x + 0.15, probe_top_y + 0.2, "C_probe ≈ 1–5 pF", fontsize=6.5)

    # Bottom probe (return to TIA)
    probe_bot_x, probe_bot_y = 10.3, 1.8
    ax.annotate("", xy=(probe_bot_x, probe_bot_y),
                xytext=(4.1, 2.9),
                arrowprops=dict(arrowstyle="-", color="#37474F", lw=2.5),
                zorder=5)
    ax.plot([probe_bot_x], [probe_bot_y], '^', color="#37474F", markersize=10, zorder=6)
    _para(ax, probe_bot_x + 0.15, probe_bot_y - 0.2, "C_probe ≈ 1–5 pF", fontsize=6.5)

    # DUT cross section --------------------------------------------------------
    dut_x, dut_y0 = 10.6, 1.8
    dut_w = 3.8

    # Labels for layers
    layer_specs = [
        # (y_start, height, color,      edge,    label,           sublabel)
        (4.0, 0.5,  "#B0BEC5", "#607D8B", "Gate metal / pad",  f"Rc ≈ 1–50 Ω\nCpad ≈ 0.1–1 pF"),
        (3.4, 0.6,  "#FFCC02", "#F9A825", "Gate electrode",    "(poly-Si or Al)"),
        (3.1, 0.3,  "#90CAF9", "#1565C0", f"Gate oxide  Cox",  f"tox = ? nm\nCox={Cox_fF:.1f} fF"),
        (2.0, 1.1,  "#A5D6A7", "#2E7D32", "p-Si substrate",   "Cdep varies\nwith Vbias"),
        (1.5, 0.5,  "#FFAB91", "#BF360C", "Bulk contact",     "Rs_sub ≈ 10–1000 Ω"),
        (0.9, 0.6,  "#CFD8DC", "#546E7A", "Probe chuck (gnd)","Cchuck ≈ 10–100 pF"),
    ]

    for (ly, lh, lfc, lec, llab, lsub) in layer_specs:
        rect = FancyBboxPatch((dut_x, dut_y0 + ly - 1.8), dut_w, lh,
                              boxstyle="square,pad=0",
                              facecolor=lfc, edgecolor=lec, linewidth=1.0, zorder=3)
        ax.add_patch(rect)
        ax.text(dut_x + dut_w / 2, dut_y0 + ly - 1.8 + lh / 2,
                llab, ha="center", va="center",
                fontsize=7, fontweight="bold", color="black", zorder=4)
        ax.text(dut_x + dut_w / 2, dut_y0 + ly - 1.8 + lh / 2 - 0.17,
                lsub, ha="center", va="top",
                fontsize=6, color="#37474F", zorder=4)

    # Probe contact lines to DUT layers
    # Top probe → gate pad
    ax.plot([probe_top_x, dut_x], [probe_top_y, dut_y0 + 4.0 + 0.25 - 1.8],
            color="#37474F", lw=1.5, linestyle=":", zorder=2)
    # Bottom probe → bulk contact
    ax.plot([probe_bot_x, dut_x], [probe_bot_y, dut_y0 + 1.5 + 0.25 - 1.8],
            color="#37474F", lw=1.5, linestyle=":", zorder=2)

    # Cdep arrow (shows depletion capacitance varies with bias)
    ax.annotate("", xy=(dut_x - 0.5, dut_y0 + 3.1 - 1.8 - 0.1),
                xytext=(dut_x - 0.5, dut_y0 + 2.0 - 1.8 + 1.1),
                arrowprops=dict(arrowstyle="<->", color=C_PARA, lw=1.2),
                zorder=6)
    _para(ax, dut_x - 0.55, dut_y0 + 2.55 - 1.8, "Cdep\n(f(Vbias))", ha="right", fontsize=6.5)

    # Calibration note
    ax.text(12.5, 0.55, "Open/Short/Load calibration\nremoves Cprobe + Ccable from measurement",
            ha="center", va="center", fontsize=6.5, color="#1B5E20",
            bbox=dict(fc="#C8E6C9", ec="#1B5E20", boxstyle="round,pad=0.3"))

    # ── Legend / key ──────────────────────────────────────────────────────────

    legend_items = [
        (mpatches.Patch(fc=C_FPGA,   ec=C_FPGA_B, label="Digital (FPGA)")),
        (mpatches.Patch(fc=C_ANALOG, ec="#827717", label="Analog front-end")),
        (mpatches.Patch(fc=C_PHYS,   ec="#1B5E20", label="Physical / DUT")),
        (mpatches.Patch(fc="#FFCDD2", ec="#C62828", label="TIA (noise-critical)")),
    ]
    ax.legend(handles=legend_items, loc="lower left",
              fontsize=7, framealpha=0.9, ncol=2)

    # ── Title ─────────────────────────────────────────────────────────────────

    ax.set_title(
        f"Complete Signal Chain with Parasitics  ·  "
        f"f₀ = {f0_MHz:.2f} MHz  ·  Rf = {Rf_kohm:.0f} kΩ  ·  "
        f"ADC {adc_bits}-bit  ·  CIC ×{dec_R}  ·  LPF BW {lpf_bw_hz/1e3:.1f} kHz",
        fontsize=9, pad=8,
    )

    fig.tight_layout(pad=0.5)
    return fig
