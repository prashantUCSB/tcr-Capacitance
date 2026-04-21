"""
Full lock-in amplifier signal chain simulation.

Signal flow:
  DDS excitation → DUT admittance model → TIA → ADC quantization
  → pre-filter CIC → I/Q demodulator × N tones → post-filter LPF
  → magnitude / phase → C, G extraction

C extraction (parallel Gp-Cp model):
  I_out = ½ × Vexc × Gp × Rf        (in-phase)
  Q_out = ½ × Vexc × ωCp × Rf       (quadrature)
  → Cp = 2 × Q_out / (Vexc × ω × Rf)
  → Gp = 2 × I_out / (Vexc × Rf)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from .dds import DDS
from .demod import DemodChannel, MultiToneDemodulator


@dataclass
class TIAParams:
    """Transimpedance amplifier parameters."""
    Rf_ohm: float = 10e3           # feedback resistance (Ω)
    Cf_F: float = 0.0              # feedback capacitance (F) — adds phase shift
    input_noise_A_rHz: float = 2e-15   # input current noise density (A/√Hz)
    voltage_noise_V_rHz: float = 5e-9  # op-amp voltage noise (V/√Hz)


@dataclass
class ADCParams:
    """ADC quantization model."""
    bits: int = 16
    vref: float = 1.0              # full-scale ± range (V)
    snr_db: float | None = None    # if set, adds quantization + thermal noise to match SNR


@dataclass
class LockInChainParams:
    fs_in: float = 125e6           # ADC sample rate (Hz)
    frequencies: list[float] = field(default_factory=lambda: [1e6])
    excitation_amplitude_V: float = 0.03   # 30 mV RMS like HP4280
    pre_dec_R: int = 1
    post_dec_R: int = 1024
    post_cic_stages: int = 4
    lpf_bw_hz: float = 10.0
    tia: TIAParams = field(default_factory=TIAParams)
    adc: ADCParams = field(default_factory=ADCParams)
    add_noise: bool = True


class LockInChain:
    """
    End-to-end lock-in amplifier chain.

    Usage:
        chain = LockInChain(params)
        # For each bias voltage point:
        results = chain.measure(admittance_Cp_F=1e-12, admittance_Gp_S=0.0)
        C, G = results[0]  # first tone
    """

    def __init__(self, params: LockInChainParams):
        self.p = params
        self.rng = np.random.default_rng(seed=42)

        # Excitation DDS instances (one per tone, all from same clock)
        self._exc_dds = [
            DDS(params.fs_in, f, amplitude=params.excitation_amplitude_V)
            for f in params.frequencies
        ]

        # Demodulator
        self._demod = MultiToneDemodulator.from_frequencies(
            fs_in=params.fs_in,
            frequencies=params.frequencies,
            post_dec_R=params.post_dec_R,
            lpf_bw_hz=params.lpf_bw_hz,
            pre_dec_R=params.pre_dec_R,
        )
        self.fs_out = self._demod.fs_out

        # Block size must be large enough that the FIR's group delay (half the tap count)
        # is fully elapsed before we start averaging.  Use 3× the group delay as the
        # settle window (1× to get past transient, 2× for averaging), capped at 500 k
        # input samples to keep simulation fast.
        ch0 = self._demod.channels[0]
        fir_group_delay_out = int(np.ceil(ch0._lpf_i.group_delay_samples))
        total_dec = params.post_dec_R * ch0._extra_dec
        settle_out = max(fir_group_delay_out * 3,
                         int(np.ceil(self.fs_out / params.lpf_bw_hz * 3)))
        self._block_size = min(max(settle_out * total_dec, 4096), 500_000)

    def _simulate_tia_output(
        self, n_samples: int, Cp_F: float, Gp_S: float, tone_idx: int
    ) -> np.ndarray:
        """
        Generate TIA output voltage for a parallel Gp-Cp DUT.
        V_tia(t) = -[Gp + jωCp] × Vexc × Rf  (assuming ideal TIA, Zin→0)
        In time domain: V = -Rf × [Gp × Vexc(t) + Cp × dVexc/dt]
        """
        dds = self._exc_dds[tone_idx]
        f0 = dds.frequency
        omega = 2 * np.pi * f0
        Rf = self.p.tia.Rf_ohm

        # Save DDS state, generate samples, restore
        saved_acc = dds._phase_acc
        cos_exc, sin_exc = dds.generate(n_samples)
        dds._phase_acc = saved_acc  # restore so demod references stay aligned

        # DUT current (admittance × excitation voltage):
        #   I_dut = G*A*cos(ωt) − ωC*A*sin(ωt)   [capacitor current = C*dV/dt]
        # Inverting TIA: V_tia = −Rf * I_dut
        #   = −A*Rf*G*cos(ωt) + A*Rf*ωC*sin(ωt)
        v_I = Rf * Gp_S * cos_exc       # in-phase (conductance) term
        v_Q = Rf * omega * Cp_F * sin_exc  # quadrature (capacitive) term

        v_tia = -v_I + v_Q  # inverting TIA: negate G term, capacitive sin term survives
        return v_tia

    def _add_noise(self, v: np.ndarray, n_samples: int) -> np.ndarray:
        """Add TIA input-referred noise and ADC noise."""
        tia = self.p.tia
        # TIA current noise → voltage noise at output
        i_noise_rms = tia.input_noise_A_rHz * np.sqrt(self.p.fs_in / 2)
        v_noise_tia = self.rng.normal(0, i_noise_rms * tia.Rf_ohm, n_samples)

        # Op-amp voltage noise
        v_noise_amp = self.rng.normal(0, tia.voltage_noise_V_rHz * np.sqrt(self.p.fs_in / 2), n_samples)

        # ADC quantization noise
        lsb = 2 * self.p.adc.vref / (2 ** self.p.adc.bits)
        v_noise_adc = self.rng.uniform(-lsb / 2, lsb / 2, n_samples)

        return v + v_noise_tia + v_noise_amp + v_noise_adc

    def _quantize(self, v: np.ndarray) -> np.ndarray:
        """Simulate ADC quantization (clipping + rounding)."""
        v_clip = np.clip(v, -self.p.adc.vref, self.p.adc.vref)
        lsb = 2 * self.p.adc.vref / (2 ** self.p.adc.bits)
        return np.round(v_clip / lsb) * lsb

    def measure(
        self, Cp_F: float, Gp_S: float = 0.0, n_averages: int = 1
    ) -> list[dict]:
        """
        Simulate a lock-in measurement at one bias point.

        Returns list of dicts (one per tone):
          {'freq': f0, 'I': I_dc, 'Q': Q_dc, 'C': C_F, 'G': G_S,
           'magnitude': mag, 'phase_deg': phi}
        """
        results_acc = [{} for _ in self.p.frequencies]

        for _ in range(n_averages):
            # Reset DDS + demod for coherent averaging
            for dds in self._exc_dds:
                dds.reset()
            self._demod.reset_all()

            # Build composite TIA output (sum over all tones)
            n = self._block_size
            v_total = np.zeros(n)
            for j, f in enumerate(self.p.frequencies):
                v_total += self._simulate_tia_output(n, Cp_F, Gp_S, j)

            if self.p.add_noise:
                v_total = self._add_noise(v_total, n)
            v_total = self._quantize(v_total)

            # Demodulate
            iq_list = self._demod.process(v_total)

            for j, (I_arr, Q_arr) in enumerate(iq_list):
                f0 = self.p.frequencies[j]
                omega = 2 * np.pi * f0
                Rf = self.p.tia.Rf_ohm
                Vexc = self.p.excitation_amplitude_V

                # Take DC average of the last half of the output (post-settle)
                half = len(I_arr) // 2
                I_dc = float(np.mean(I_arr[half:]))
                Q_dc = float(np.mean(Q_arr[half:]))

                # After LPF: I_dc = −A·Rf·G/2,  Q_dc = +A·Rf·ωC/2
                # → C = 2·Q_dc / (A·Rf·ω),  G = −2·I_dc / (A·Rf)
                C_meas = 2.0 * Q_dc / (Vexc * omega * Rf)
                G_meas = -2.0 * I_dc / (Vexc * Rf)

                mag = np.sqrt(I_dc**2 + Q_dc**2)
                phase_deg = np.degrees(np.arctan2(Q_dc, I_dc))

                if j not in results_acc[j]:
                    results_acc[j] = {
                        'freq': f0, 'I': 0.0, 'Q': 0.0,
                        'C': 0.0, 'G': 0.0,
                        'magnitude': 0.0, 'phase_deg': 0.0
                    }
                results_acc[j]['I'] += I_dc / n_averages
                results_acc[j]['Q'] += Q_dc / n_averages
                results_acc[j]['C'] += C_meas / n_averages
                results_acc[j]['G'] += G_meas / n_averages
                results_acc[j]['magnitude'] += mag / n_averages
                results_acc[j]['phase_deg'] += phase_deg / n_averages

        return results_acc
