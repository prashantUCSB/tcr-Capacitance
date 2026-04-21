# Changelog

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added

- Initial repository scaffold
- Project structure for dual-FPGA lock-in amplifier CV measurement system
- Prompt engineering log (`docs/PROMPTS.md`)
- Python simulation framework (`simulation/python/`):
  - `lockin/dds.py` — phase-accumulator DDS model matching FPGA integer arithmetic
  - `lockin/filters.py` — CIC decimation filter (FIR-equivalent) and Kaiser FIR LPF designer
  - `lockin/demod.py` — multi-tone I/Q demodulator with pre/post filtering
  - `lockin/chain.py` — full lock-in chain: DDS → TIA → ADC → demod → C/G extraction
  - `dut/moscap.py` — high-frequency MOS capacitor C-V physics model (Sze & Ng)
  - `demo_cv.py` — end-to-end CV curve simulation demo (61-point sweep)
- Verified: 34.5 fF Cox extracted with 0.4 fF RMS error at 50 kHz lock-in bandwidth

### Architecture decisions recorded

- 2-tone baseline (1 MHz + 100 kHz), extensible to N tones
- 18-bit data path, 25-bit coefficients, 48-bit accumulators (DSP48E1 native)
- VC707 = prototype platform, TE0741 (XC7K70T-2IF Kintex-7) = deployable target
- Python simulation serves as golden reference for RTL verification
- Communication: Ethernet (target); UART for bring-up

---
