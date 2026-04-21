"""
Demo: Simulated C-V curve using the digital lock-in amplifier chain.

Runs a sweep of bias voltages across a modeled p-type MOS capacitor,
extracts C and G at each point via the lock-in, and compares against
the analytic CV curve.

Run:
    python demo_cv.py
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — saves to file, no display required
import matplotlib.pyplot as plt
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from lockin import LockInChain, LockInChainParams, TIAParams, ADCParams
from dut import MOSCapParams, cv_curve, print_device_summary


# ── Device under test ────────────────────────────────────────────────────────

device = MOSCapParams(
    area_m2=100e-12,        # 10 × 10 µm gate
    tox_m=100e-9,           # 100 nm oxide (teaching cleanroom)
    Na_m3=1e22,             # 10^16 cm^-3 p-type doping
    Vfb=-0.5,               # flat-band voltage
    T_K=300.0,
)

print_device_summary(device)

# ── Lock-in chain configuration ───────────────────────────────────────────────

params = LockInChainParams(
    fs_in=125e6,            # 125 MHz ADC sample rate (typical for FMC ADC card)
    frequencies=[1e6],      # 1 MHz test tone (HP4280-style)
    excitation_amplitude_V=0.03,  # 30 mV RMS
    # Demo mode: post_dec_R=32 → fs_out ≈ 3.9 MHz, lpf_bw=50 kHz for fast run.
    # Research mode: post_dec_R=2048 → fs_out ≈ 61 kHz, lpf_bw=1–10 Hz for
    # sub-fF resolution.  Narrow BW measurements should use n_averages > 1.
    post_dec_R=32,
    post_cic_stages=4,
    lpf_bw_hz=50e3,
    tia=TIAParams(
        Rf_ohm=10e3,
        input_noise_A_rHz=2e-15,
        voltage_noise_V_rHz=5e-9,
    ),
    adc=ADCParams(bits=16, vref=1.0),
    add_noise=True,
)

chain = LockInChain(params)

# ── Bias sweep ────────────────────────────────────────────────────────────────

V_sweep = np.linspace(-3.0, 3.0, 61)   # ±3 V, 61 points

C_measured = np.zeros(len(V_sweep))
G_measured = np.zeros(len(V_sweep))

print(f"\nRunning CV sweep: {len(V_sweep)} points...")
print(f"  Lock-in BW: {params.lpf_bw_hz/1e3:.1f} kHz  "
      f"Decimation: {params.post_dec_R}x  "
      f"fs_out: {chain.fs_out/1e3:.1f} kHz  "
      f"block: {chain._block_size} samples")

for i, Vbias in enumerate(V_sweep):
    # Get analytic C at this bias point
    C_analytic, Gp_analytic = cv_curve(np.array([Vbias]), device)
    Cp = float(C_analytic[0])
    Gp = float(Gp_analytic[0])

    result = chain.measure(Cp_F=Cp, Gp_S=Gp)
    C_measured[i] = result[0]['C']
    G_measured[i] = result[0]['G']

    if (i + 1) % 10 == 0:
        print(f"  V={Vbias:+.2f}V  C_true={Cp*1e15:.2f}fF  C_meas={C_measured[i]*1e15:.2f}fF")

# ── Analytic reference curve ───────────────────────────────────────────────────

V_ref = np.linspace(-3.0, 3.0, 500)
C_ref, _ = cv_curve(V_ref, device)

# ── Plot ──────────────────────────────────────────────────────────────────────

fig, axes = plt.subplots(2, 1, figsize=(8, 8))
fig.suptitle("Simulated MOS-C CV Measurement via Digital Lock-in Amplifier", fontsize=13)

ax1 = axes[0]
ax1.plot(V_ref, C_ref * 1e15, 'k-', linewidth=2, label="Analytic (ideal)")
ax1.plot(V_sweep, C_measured * 1e15, 'ro', markersize=5, label="Lock-in extracted")
ax1.set_xlabel("DC Bias (V)")
ax1.set_ylabel("Capacitance (fF)")
ax1.set_title("C-V Curve")
ax1.legend()
ax1.grid(True, alpha=0.4)
ax1.axhline(device.Cox_F * 1e15, color='gray', linestyle='--', alpha=0.5, label='Cox')
ax1.annotate(f'Cox = {device.Cox_F*1e15:.1f} fF', xy=(V_sweep[0], device.Cox_F * 1e15),
             xytext=(0, 5), textcoords='offset points', fontsize=8, color='gray')

ax2 = axes[1]
error_fF = (C_measured - np.interp(V_sweep, V_ref, C_ref)) * 1e15
ax2.plot(V_sweep, error_fF, 'b.-', label="Measurement error (fF)")
ax2.axhline(0, color='k', linestyle='-', linewidth=0.5)
ax2.set_xlabel("DC Bias (V)")
ax2.set_ylabel("C error (fF)")
ax2.set_title("Lock-in Extraction Error vs Analytic Model")
ax2.legend()
ax2.grid(True, alpha=0.4)

plt.tight_layout()
plt.savefig("cv_simulation_result.png", dpi=150, bbox_inches='tight')
print("\nSaved cv_simulation_result.png")

# ── Summary statistics ────────────────────────────────────────────────────────

print(f"\nMeasurement statistics:")
print(f"  RMS error:  {np.sqrt(np.mean(error_fF**2)):.3f} fF")
print(f"  Max error:  {np.max(np.abs(error_fF)):.3f} fF")
print(f"  Cox meas:   {np.max(C_measured)*1e15:.2f} fF (true: {device.Cox_F*1e15:.2f} fF)")
