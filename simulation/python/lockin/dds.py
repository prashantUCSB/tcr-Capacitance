import numpy as np


class DDS:
    """
    Phase-accumulator DDS model matching FPGA behavior.

    Uses integer arithmetic identical to what the RTL will implement,
    so phase quantization errors are faithfully reproduced.
    """

    def __init__(
        self,
        fs: float,
        freq: float,
        phase_bits: int = 32,
        amplitude: float = 1.0,
        phase_offset_rad: float = 0.0,
    ):
        self.fs = fs
        self.phase_bits = phase_bits
        self.amplitude = amplitude
        self._N = np.int64(1) << phase_bits
        self._ftw = np.int64(round(freq * self._N / fs))
        self._phase_acc = np.int64(round(phase_offset_rad / (2 * np.pi) * self._N)) & (self._N - 1)

    @property
    def frequency(self) -> float:
        """Actual output frequency accounting for FTW quantization."""
        return float(self._ftw) * self.fs / float(self._N)

    @property
    def ftw(self) -> int:
        return int(self._ftw)

    def generate(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate n samples. Returns (cos_out, sin_out).
        Stateful — successive calls are phase-continuous.
        """
        sample_idx = np.arange(n, dtype=np.int64)
        phases = (self._phase_acc + sample_idx * self._ftw) & (self._N - 1)
        self._phase_acc = (self._phase_acc + np.int64(n) * self._ftw) & (self._N - 1)
        phi = phases.astype(np.float64) * (2.0 * np.pi / float(self._N))
        return self.amplitude * np.cos(phi), self.amplitude * np.sin(phi)

    def reset(self, phase_rad: float = 0.0):
        self._phase_acc = np.int64(round(phase_rad / (2 * np.pi) * self._N)) & (self._N - 1)


class MultitoneDDS:
    """
    N independent DDS channels sharing one master clock.
    All channels are phase-coherent (same clock, independent FTWs).
    """

    def __init__(
        self,
        fs: float,
        frequencies: list[float],
        phase_bits: int = 32,
        amplitudes: list[float] | None = None,
    ):
        if amplitudes is None:
            amplitudes = [1.0 / len(frequencies)] * len(frequencies)
        if len(amplitudes) != len(frequencies):
            raise ValueError("frequencies and amplitudes must have same length")

        self.channels = [
            DDS(fs, f, phase_bits=phase_bits, amplitude=a)
            for f, a in zip(frequencies, amplitudes)
        ]

    def generate_composite(self, n: int) -> np.ndarray:
        """Sum all tones into a single output waveform."""
        out = np.zeros(n)
        for ch in self.channels:
            cos_out, _ = ch.generate(n)
            out += cos_out
        return out

    def generate_references(self, n: int) -> list[tuple[np.ndarray, np.ndarray]]:
        """
        Returns list of (cos, sin) reference pairs without advancing channel state.
        Used when the same DDS serves as both excitation and demod reference.
        """
        refs = []
        saved = [ch._phase_acc for ch in self.channels]
        for ch in self.channels:
            refs.append(ch.generate(n))
        # restore state so references stay coherent with excitation
        for ch, acc in zip(self.channels, saved):
            ch._phase_acc = acc
        return refs

    def reset_all(self):
        for ch in self.channels:
            ch.reset()
