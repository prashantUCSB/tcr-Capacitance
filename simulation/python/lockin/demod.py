"""
Multi-tone I/Q demodulator.

Each tone channel performs:
  I = LPF( x(t) · cos(ω₀t) )
  Q = LPF( x(t) · sin(ω₀t) )

The post-multiplication LPF is a CIC decimator followed by an FIR
compensation/low-pass filter.  The pre-demodulation filter (anti-alias /
bandwidth limiter before the multiplier) is a CIC applied to the raw ADC
stream.

All frequencies in Hz, all signals as numpy arrays at the input sample rate.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from .dds import DDS
from .filters import CICDecimator, FIRFilter, design_lowpass_fir


@dataclass
class DemodChannel:
    """
    Single-tone I/Q demodulation channel.

    fs_in:       input sample rate (Hz)
    ref_freq:    reference / tone frequency (Hz)
    pre_dec_R:   CIC decimation before demodulation (anti-alias)
    post_dec_R:  CIC decimation after IQ multiply (integration filter)
    lpf_bw_hz:   final low-pass corner frequency (Hz) at output rate
    phase_bits:  DDS phase accumulator bits
    """

    fs_in: float
    ref_freq: float
    pre_dec_R: int = 1
    post_dec_R: int = 64
    post_cic_stages: int = 4
    lpf_bw_hz: float = 10.0
    phase_bits: int = 32

    # Built in __post_init__
    _ref_dds_i: DDS = field(init=False, repr=False)
    _ref_dds_q: DDS = field(init=False, repr=False)
    _pre_cic: CICDecimator | None = field(init=False, repr=False)
    _post_cic_i: CICDecimator = field(init=False, repr=False)
    _post_cic_q: CICDecimator = field(init=False, repr=False)
    _lpf_i: FIRFilter = field(init=False, repr=False)
    _lpf_q: FIRFilter = field(init=False, repr=False)
    fs_out: float = field(init=False)

    def __post_init__(self):
        # Single DDS per channel; generate() returns (cos(ωt), sin(ωt)) together,
        # so I and Q references are guaranteed phase-coherent with zero extra overhead.
        self._ref_dds = DDS(self.fs_in, self.ref_freq, self.phase_bits, amplitude=1.0)

        if self.pre_dec_R > 1:
            self._pre_cic = CICDecimator(self.pre_dec_R, N=4, M=1)
            fs_mid = self.fs_in / self.pre_dec_R
        else:
            self._pre_cic = None
            fs_mid = self.fs_in

        self._post_cic_i = CICDecimator(self.post_dec_R, N=self.post_cic_stages, M=1)
        self._post_cic_q = CICDecimator(self.post_dec_R, N=self.post_cic_stages, M=1)
        self.fs_out = fs_mid / self.post_dec_R

        lpf_taps = design_lowpass_fir(self.fs_out, self.lpf_bw_hz)
        self._lpf_i = FIRFilter(lpf_taps)
        self._lpf_q = FIRFilter(lpf_taps)

    def process(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Process one block of samples at fs_in.
        Returns (I_out, Q_out) at fs_out.
        """
        if self._pre_cic is not None:
            x = self._pre_cic.process(x)
            fs_mid = self.fs_in / self.pre_dec_R
        else:
            fs_mid = self.fs_in

        n = len(x)
        cos_ref, sin_ref = self._ref_dds.generate(n)  # (cos(ωt), sin(ωt))

        i_raw = x * cos_ref
        q_raw = x * sin_ref

        i_dec = self._post_cic_i.process(i_raw)
        q_dec = self._post_cic_q.process(q_raw)

        I_out = self._lpf_i.process(i_dec)
        Q_out = self._lpf_q.process(q_dec)

        return I_out, Q_out

    def reset(self):
        self._ref_dds.reset()
        if self._pre_cic:
            self._pre_cic.reset()
        self._post_cic_i.reset()
        self._post_cic_q.reset()
        self._lpf_i.reset()
        self._lpf_q.reset()


class MultiToneDemodulator:
    """
    Parallel I/Q demodulator for N simultaneous tones.
    All channels share the same input stream.
    """

    def __init__(self, channels: list[DemodChannel]):
        self.channels = channels

    @classmethod
    def from_frequencies(
        cls,
        fs_in: float,
        frequencies: list[float],
        post_dec_R: int = 64,
        lpf_bw_hz: float = 10.0,
        pre_dec_R: int = 1,
    ) -> MultiToneDemodulator:
        channels = [
            DemodChannel(
                fs_in=fs_in,
                ref_freq=f,
                pre_dec_R=pre_dec_R,
                post_dec_R=post_dec_R,
                lpf_bw_hz=lpf_bw_hz,
            )
            for f in frequencies
        ]
        return cls(channels)

    def process(self, x: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
        """
        Process one block. Returns list of (I, Q) per channel.
        """
        return [ch.process(x) for ch in self.channels]

    @property
    def fs_out(self) -> float:
        return self.channels[0].fs_out

    def reset_all(self):
        for ch in self.channels:
            ch.reset()
