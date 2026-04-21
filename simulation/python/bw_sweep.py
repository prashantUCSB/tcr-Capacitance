"""
BW accuracy sweep: RMS extraction error vs. lock-in bandwidth.

Answers: what lock-in bandwidth is needed to reach sub-fF resolution?

For each BW point, 20 repeated measurements are taken at a fixed C (Cox, strong
accumulation) and G=0.  The std-dev of the extractions is the noise floor at that BW.

Also overlays the theoretical shot + thermal noise limit from the TIA model.

Run:
    python bw_sweep.py [--fast]  # --fast uses fewer repeats for quick testing
"""

import argparse
import time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys, os

sys.path.insert(0, os.path.dirname(__file__))

from lockin import LockInChain, LockInChainParams, TIAParams, ADCParams
from dut import MOSCapParams

# ── Config ────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--fast", action="store_true", help="Fewer repeats, coarser BW grid")
args = parser.parse_args()

device = MOSCapParams(
    area_m2=100e-12,     # 10×10 µm
    tox_m=100e-9,
    Na_m3=1e22,
    Vfb=-0.5,
)
C_test = device.Cox_F  # measure at accumulation — maximum C, easiest case

TIA = TIAParams(
    Rf_ohm=10e3,
    input_noise_A_rHz=2e-15,    # 2 fA/√Hz — electrometer-grade (e.g. OPA129)
    voltage_noise_V_rHz=5e-9,   # 5 nV/√Hz
)
ADC = ADCParams(bits=16, vref=1.0)
FREQ = 1e6
VEXC = 0.03
FS_IN = 125e6
DEC = 32   # CIC ratio — determines fs_out

# BW grid: 50 kHz down to 10 Hz (log-spaced)
if args.fast:
    bw_values = np.logspace(4, 1, 8)   # 10 kHz → 10 Hz, 8 points
    n_repeats = 5
else:
    bw_values = np.logspace(4.7, 1, 16)  # 50 kHz → 10 Hz, 16 points
    n_repeats = 20

print(f"BW sweep: {len(bw_values)} points, {n_repeats} repeats each")
print(f"TIA: Rf={TIA.Rf_ohm/1e3:.0f}kOhm, In={TIA.input_noise_A_rHz*1e15:.1f}fA/rtHz")
print(f"ADC: {ADC.bits}-bit, Vref={ADC.vref:.1f}V")

# ── Theoretical noise floor ────────────────────────────────────────────────────

def noise_budget_fF(bw_hz: float) -> dict:
    """
    Theoretical sigma_C breakdown from each noise source.

    Three independent contributions (added in quadrature for total):

    1. TIA current noise (In, A/rtHz):
       sigma_C = 2 * In * sqrt(BW) / (Vexc * omega)
       Dominates when Rf > Vn/In (crossover Rf = 2.5 MOhm at these defaults)

    2. Op-amp voltage noise (Vn, V/rtHz):
       Output noise density = Vn (nearly unity transfer for Zin << Rf)
       sigma_C = 2 * Vn * sqrt(BW) / (Vexc * omega * Rf)
       Dominates when Rf < Vn/In. At Rf=10kOhm, THIS is the dominant term.

    3. ADC quantization (bandwidth-weighted):
       Only noise in [0, BW] matters after lock-in filtering.
       sigma_C_adc = 2 * (LSB/sqrt(12)) * sqrt(BW/(fs/2)) / (Vexc * omega * Rf)
    """
    omega = 2 * np.pi * FREQ
    # 1. TIA current noise
    sc_In = 2 * TIA.input_noise_A_rHz * np.sqrt(bw_hz) / (VEXC * omega)
    # 2. Op-amp voltage noise
    sc_Vn = 2 * TIA.voltage_noise_V_rHz * np.sqrt(bw_hz) / (VEXC * omega * TIA.Rf_ohm)
    # 3. ADC quantization noise (in-band only)
    lsb = 2 * ADC.vref / (2 ** ADC.bits)
    sc_adc = 2 * (lsb / np.sqrt(12)) * np.sqrt(bw_hz / (FS_IN / 2)) / (VEXC * omega * TIA.Rf_ohm)
    sc_total = np.sqrt(sc_In**2 + sc_Vn**2 + sc_adc**2)
    return {
        "total": sc_total * 1e15,
        "In": sc_In * 1e15,
        "Vn": sc_Vn * 1e15,
        "adc": sc_adc * 1e15,
    }

def bw_for_target_fF(target_fF: float) -> float:
    """Bandwidth at which total theoretical sigma_C equals target_fF."""
    omega = 2 * np.pi * FREQ
    # Total noise: sqrt(A*BW + B*BW + C*BW) where each term scales as sqrt(BW)
    # sigma_C_total = sqrt(BW) * sqrt(A + B + C)
    A = (2 * TIA.input_noise_A_rHz / (VEXC * omega)) ** 2
    B = (2 * TIA.voltage_noise_V_rHz / (VEXC * omega * TIA.Rf_ohm)) ** 2
    C = (2 * (2*ADC.vref/(2**ADC.bits)/np.sqrt(12)) / (VEXC * omega * TIA.Rf_ohm * np.sqrt(FS_IN/2))) ** 2
    combined = np.sqrt(A + B + C)  # fF per sqrt(Hz)
    return (target_fF * 1e-15 / combined) ** 2

# ── Sweep ─────────────────────────────────────────────────────────────────────

rms_errors_fF = []
std_devs_fF = []
timings_s = []

for bw in bw_values:
    params = LockInChainParams(
        fs_in=FS_IN,
        frequencies=[FREQ],
        excitation_amplitude_V=VEXC,
        post_dec_R=DEC,
        post_cic_stages=4,
        lpf_bw_hz=bw,
        tia=TIA,
        adc=ADC,
        add_noise=True,
    )
    chain = LockInChain(params)

    measurements = []
    t0 = time.time()
    for _ in range(n_repeats):
        r = chain.measure(Cp_F=C_test, Gp_S=0.0)
        measurements.append(r[0]["C"])

    elapsed = time.time() - t0
    timings_s.append(elapsed / n_repeats)

    arr = np.array(measurements) * 1e15
    true_fF = C_test * 1e15
    rms = np.sqrt(np.mean((arr - true_fF) ** 2))
    std = np.std(arr)

    rms_errors_fF.append(rms)
    std_devs_fF.append(std)

    print(f"  BW={bw:8.1f}Hz  RMS={rms:.3f}fF  std={std:.3f}fF  "
          f"mean={np.mean(arr):.3f}fF  [{elapsed/n_repeats*1000:.0f}ms/pt]")

# ── Theoretical overlay ────────────────────────────────────────────────────────

bw_theory = np.logspace(np.log10(bw_values[-1]) - 0.5,
                        np.log10(bw_values[0]) + 0.5, 200)
theory = [noise_budget_fF(b) for b in bw_theory]
theory_total = np.array([t["total"] for t in theory])
theory_In    = np.array([t["In"]    for t in theory])
theory_Vn    = np.array([t["Vn"]    for t in theory])
theory_adc   = np.array([t["adc"]   for t in theory])

bw_1fF  = bw_for_target_fF(1.0)
bw_01fF = bw_for_target_fF(0.1)

budget = noise_budget_fF(bw_values[0])
print(f"\nNoise budget at BW={bw_values[0]:.0f} Hz:")
print(f"  sigma_C (total): {budget['total']:.4f} fF")
print(f"  from In:         {budget['In']:.4f} fF  (current noise)")
print(f"  from Vn:         {budget['Vn']:.4f} fF  (voltage noise -- DOMINANT at Rf=10kOhm)")
print(f"  from ADC:        {budget['adc']:.4f} fF  (quantization)")
print(f"\n1 fF resolution requires BW < {bw_1fF:.1f} Hz")
print(f"0.1 fF resolution requires BW < {bw_01fF:.3f} Hz")
print(f"\nNote: dominant noise at Rf=10kOhm is Vn (voltage noise).")
print(f"Crossover Rf where In=Vn: {TIA.voltage_noise_V_rHz/TIA.input_noise_A_rHz/1e3:.0f} kOhm")

# ── Plot ───────────────────────────────────────────────────────────────────────

fig, axes = plt.subplots(2, 1, figsize=(9, 8))
fig.suptitle("Lock-in Bandwidth vs. Capacitance Resolution\n"
             f"(f0={FREQ/1e6:.0f}MHz, Rf={TIA.Rf_ohm/1e3:.0f}kOhm, "
             f"Vexc={VEXC*1e3:.0f}mV, {ADC.bits}-bit ADC)", fontsize=12)

ax1 = axes[0]
ax1.loglog(bw_values, rms_errors_fF, 'ro-', label="Simulated RMS error", zorder=5)
ax1.loglog(bw_values, std_devs_fF, 'bs--', label="Simulated std dev", alpha=0.7, zorder=4)
ax1.loglog(bw_theory, theory_total, 'k-', linewidth=2.5, label="Theory total (RSS)")
ax1.loglog(bw_theory, theory_Vn, 'orange', linewidth=1.5, linestyle='--',
           label="Vn contribution (DOMINANT at Rf=10kOhm)")
ax1.loglog(bw_theory, theory_In, 'blue', linewidth=1.5, linestyle='--',
           label="In contribution (negligible here)")
ax1.loglog(bw_theory, theory_adc, 'purple', linewidth=1.5, linestyle=':',
           label="ADC quant. contribution")
ax1.axhline(1.0, color='green', linestyle='--', alpha=0.8, label="1 fF target")
ax1.axhline(0.1, color='limegreen', linestyle='--', alpha=0.8, label="0.1 fF target")
# Mark the simulation cap region
if len(bw_values) > 2:
    cap_bw = bw_values[bw_values < 200]
    if len(cap_bw) > 0:
        ax1.axvspan(bw_values[-1], cap_bw[0] if len(cap_bw) > 0 else bw_values[-1],
                    alpha=0.08, color='gray', label="Simulation block-cap region")
ax1.set_xlabel("Lock-in Bandwidth (Hz)")
ax1.set_ylabel("C resolution (fF, 1-sigma)")
ax1.set_title("Capacitance Noise Floor vs. Lock-in Bandwidth")
ax1.legend(fontsize=8)
ax1.grid(True, which='both', alpha=0.3)

ax2 = axes[1]
ax2.loglog(bw_values, [t * 1000 for t in timings_s], 'mo-', label="Measurement time / point")
# Annotate the 1 fF and 0.1 fF crossings
for target, color, label in [(1.0, 'green', '1 fF'), (0.1, 'orange', '0.1 fF')]:
    interp_bw = np.interp(target, theory_total[::-1], bw_theory[::-1])
    meas_time = 1.0 / (interp_bw * 2) * 1000  # approximate
    ax2.axvline(interp_bw, color=color, linestyle='--', alpha=0.7,
                label=f"{label}: BW={interp_bw:.2f}Hz")

ax2.set_xlabel("Lock-in Bandwidth (Hz)")
ax2.set_ylabel("Time per measurement point (ms)")
ax2.set_title("Measurement Time vs. Lock-in Bandwidth")
ax2.legend(fontsize=8)
ax2.grid(True, which='both', alpha=0.3)

plt.tight_layout()
plt.savefig("bw_sweep_result.png", dpi=150, bbox_inches='tight')
print("\nSaved bw_sweep_result.png")
