"""
High-frequency MOS capacitor C-V model.

Implements the ideal MOS-C curve (no interface traps, no fixed charge)
and an extended model with interface trap density (Dit) that modifies
the conductance-voltage curve at the measurement frequency.

Physical constants and formulae follow Sze & Ng, "Physics of
Semiconductor Devices", 3rd ed., Chapter 2.
"""

import numpy as np
from dataclasses import dataclass, field


q = 1.602e-19       # C
eps0 = 8.854e-12    # F/m
eps_si = 11.7       # relative permittivity of Si
eps_ox = 3.9        # relative permittivity of SiO2
k_B = 1.381e-23     # J/K
ni_300K = 1.5e16    # intrinsic carrier density Si at 300 K (m^-3)


@dataclass
class MOSCapParams:
    """
    Parameters for a MOS capacitor.
    All dimensions in SI units.
    """
    area_m2: float = 100e-12        # gate area (m^2) — 10x10 µm default
    tox_m: float = 100e-9           # gate oxide thickness (m)
    Na_m3: float = 1e22             # p-type doping density (m^-3) — 1e16 cm^-3
    Vfb: float = -0.5               # flat-band voltage (V)
    T_K: float = 300.0              # temperature (K)
    Dit_m2eV: float = 0.0           # interface trap density (m^-2 eV^-1) — 0 = ideal
    freq_Hz: float = 1e6            # measurement frequency for Gp calculation
    series_resistance: float = 0.0  # series resistance (Ω) — substrate + contact

    # Derived in __post_init__
    Cox_F: float = field(init=False)
    phi_t: float = field(init=False)
    phi_F: float = field(init=False)

    def __post_init__(self):
        self.Cox_F = eps0 * eps_ox * self.area_m2 / self.tox_m
        self.phi_t = k_B * self.T_K / q
        self.phi_F = self.phi_t * np.log(self.Na_m3 / ni_300K)


def _semiconductor_capacitance(phi_s: np.ndarray, p: MOSCapParams) -> np.ndarray:
    """
    Semiconductor capacitance Cs per unit area as function of surface potential φs.
    Uses full depletion approximation (valid for |φs| > a few φt).
    """
    # Depletion width: W = sqrt(2 * eps_si * eps0 * phi_s / (q * Na))
    # Only meaningful for phi_s > 0 (depletion/inversion for p-type)
    phi_s_dep = np.where(phi_s > 0, phi_s, 0.0)
    W = np.sqrt(2 * eps_si * eps0 * phi_s_dep / (q * p.Na_m3 + 1e-30))
    W = np.clip(W, 1e-12, 1e-3)  # physical bounds
    Cs_per_area = np.where(phi_s > 0, eps_si * eps0 / W, 1e6)  # large in accum
    return Cs_per_area


def cv_curve(
    V_bias: np.ndarray, params: MOSCapParams, high_frequency: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute C-V curve for a MOS capacitor.

    V_bias: array of DC bias voltages (V)
    params: MOSCapParams instance
    high_frequency: if True, use HF model (inversion layer charge cannot follow);
                    if False, use quasi-static (low-frequency) model

    Returns (C_F, Gp_S): capacitance and parallel conductance arrays in F and S.
    """
    Cox = params.Cox_F
    Cox_per_area = eps0 * eps_ox / params.tox_m

    C_out = np.zeros_like(V_bias, dtype=float)
    Gp_out = np.zeros_like(V_bias, dtype=float)

    for i, V in enumerate(V_bias):
        V_mos = V - params.Vfb  # voltage relative to flat-band

        if V_mos < 0:
            # Accumulation: majority carriers pile up at surface
            # C → Cox in strong accumulation
            # Use exponential model for smooth transition
            C_s = Cox * np.exp(-V_mos / params.phi_t) / params.area_m2
            Cs_F = min(C_s * params.area_m2, 100 * Cox)
            C_total = Cox * Cs_F / (Cox + Cs_F)

        else:
            # Depletion / inversion
            phi_s = V_mos  # approximate: phi_s ≈ V_mos in depletion
            # More accurate: solve self-consistently, but depletion approx is fine
            phi_s = max(phi_s, 1e-6)

            W = np.sqrt(2 * eps_si * eps0 * phi_s / (q * params.Na_m3))
            Cs_per_area = eps_si * eps0 / W
            Cs_F = Cs_per_area * params.area_m2

            if high_frequency and V_mos > 2 * params.phi_F:
                # Strong inversion, HF: inversion layer cannot respond
                # C stays at C_min
                W_max = np.sqrt(4 * eps_si * eps0 * params.phi_F / (q * params.Na_m3))
                Cs_min_F = eps_si * eps0 / W_max * params.area_m2
                Cs_F = Cs_min_F

            C_total = Cox * Cs_F / (Cox + Cs_F)

        C_out[i] = C_total

        # Interface trap conductance (simplified Nicollian-Brews model)
        if params.Dit_m2eV > 0:
            omega = 2 * np.pi * params.freq_Hz
            # Trap time constant peaks at mid-gap; approximate as single tau
            tau_it = 1.0 / (2 * np.pi * params.freq_Hz)  # resonance at freq
            Cit = q**2 * params.Dit_m2eV * params.area_m2 * 1e19  # eV -> J scale
            Gp = omega * Cit * omega * tau_it / (1 + (omega * tau_it) ** 2)
            Gp_out[i] = Gp

    return C_out, Gp_out


def print_device_summary(params: MOSCapParams):
    """Print key device parameters for sanity checking."""
    print("MOS Capacitor Summary")
    print(f"  Area:        {params.area_m2 * 1e12:.1f} um^2")
    print(f"  tox:         {params.tox_m * 1e9:.1f} nm")
    print(f"  Cox:         {params.Cox_F * 1e15:.3f} fF  ({params.Cox_F / params.area_m2 * 1e3:.2f} nF/cm^2)")
    print(f"  Na:          {params.Na_m3 * 1e-6:.2e} cm^-3")
    print(f"  phiF:        {params.phi_F * 1e3:.1f} mV")
    print(f"  Vfb:         {params.Vfb:.2f} V")
    W_max = np.sqrt(4 * eps_si * eps0 * params.phi_F / (q * params.Na_m3))
    C_min = params.Cox_F * (eps_si * eps0 / W_max * params.area_m2) / (
        params.Cox_F + eps_si * eps0 / W_max * params.area_m2
    )
    print(f"  C_max (accum): {params.Cox_F * 1e15:.3f} fF")
    print(f"  C_min (inv):   {C_min * 1e15:.3f} fF")
    print(f"  C_min/C_max:   {C_min / params.Cox_F:.3f}")
