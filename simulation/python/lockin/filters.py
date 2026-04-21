"""
Filter models for the lock-in signal chain.

CIC decimation filter: models the FPGA-native hardware decimator.
FIR filters: compensation and post-demodulation low-pass.

The CIC is implemented as its exact FIR equivalent (N-fold convolution of
rectangular windows) so the transfer function is bit-accurate vs. the
analytic expression H(f) = [sin(πfRM/fs) / sin(πfM/fs)]^N.
"""

import numpy as np
from scipy import signal as sps


def cic_equivalent_taps(R: int, N: int, M: int = 1) -> np.ndarray:
    """
    Compute the FIR impulse response equivalent to a CIC decimator.

    R: decimation ratio
    N: number of integrator/comb stages
    M: differential delay (1 or 2)
    """
    h = np.ones(R * M, dtype=np.float64)
    for _ in range(N - 1):
        h = np.convolve(h, np.ones(R * M, dtype=np.float64))
    return h / h.sum()


class CICDecimator:
    """
    CIC decimation filter + downsampler.

    Internally uses the FIR-equivalent impulse response for simulation
    accuracy. The FPGA RTL will use the integrator/comb architecture
    with the same R, N, M parameters.
    """

    def __init__(self, R: int, N: int = 4, M: int = 1):
        self.R = R
        self.N = N
        self.M = M
        self._taps = cic_equivalent_taps(R, N, M)
        self._zi = sps.lfilter_zi(self._taps, [1.0]) * 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        """
        Filter x at input rate and decimate by R.
        Output length = len(x) // R.
        """
        y, self._zi = sps.lfilter(self._taps, [1.0], x, zi=self._zi)
        return y[self.R - 1 :: self.R]  # keep one sample per R input samples

    def reset(self):
        self._zi = sps.lfilter_zi(self._taps, [1.0]) * 0.0

    @property
    def group_delay_samples(self) -> float:
        """Group delay in input samples (linear-phase FIR)."""
        return (len(self._taps) - 1) / 2.0


def design_lowpass_fir(
    fs_dec: float,
    cutoff_hz: float,
    transition_hz: float = None,
    attenuation_db: float = 80.0,
) -> np.ndarray:
    """
    Design a Parks-McClellan equiripple FIR low-pass filter.

    fs_dec: sample rate at the decimated stage (Hz)
    cutoff_hz: -6 dB point (Hz)
    transition_hz: transition band width; defaults to cutoff_hz * 0.5
    attenuation_db: stop-band attenuation
    """
    if transition_hz is None:
        transition_hz = cutoff_hz * 0.5
    nyq = fs_dec / 2.0
    wp = (cutoff_hz - transition_hz / 2) / nyq
    ws = (cutoff_hz + transition_hz / 2) / nyq
    wp = np.clip(wp, 0.01, 0.99)
    ws = np.clip(ws, wp + 0.01, 0.99)
    n_taps, beta = sps.kaiserord(attenuation_db, ws - wp)
    if n_taps % 2 == 0:
        n_taps += 1
    taps = sps.firwin(n_taps, cutoff_hz / nyq, window=("kaiser", beta))
    return taps


class FIRFilter:
    """
    Stateful FIR filter for streaming simulation.
    Accepts arbitrary coefficient array (from design_lowpass_fir or scipy).
    """

    def __init__(self, taps: np.ndarray):
        self.taps = np.asarray(taps, dtype=np.float64)
        self._zi = sps.lfilter_zi(self.taps, [1.0]) * 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        y, self._zi = sps.lfilter(self.taps, [1.0], x, zi=self._zi)
        return y

    def reset(self):
        self._zi = sps.lfilter_zi(self.taps, [1.0]) * 0.0

    @property
    def group_delay_samples(self) -> float:
        return (len(self.taps) - 1) / 2.0


def cic_frequency_response(
    R: int, N: int, M: int, fs: float, n_points: int = 4096
) -> tuple[np.ndarray, np.ndarray]:
    """Return (freqs, magnitude_dB) for the CIC transfer function."""
    taps = cic_equivalent_taps(R, N, M)
    f, h = sps.freqz(taps, worN=n_points, fs=fs)
    h_db = 20 * np.log10(np.abs(h) + 1e-300)
    return f, h_db
