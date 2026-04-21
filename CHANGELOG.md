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
- `bw_sweep.py` — BW accuracy sweep confirming sqrt(BW) noise scaling; results:
  - 1 fF resolution requires BW < 33.8 kHz; 0.1 fF requires BW < 338 Hz
  - Dominant noise at Rf=10 kohm is op-amp voltage noise Vn (not current noise In)
  - Theoretical crossover Rf (In=Vn) = 2.5 Mohm
- `docs/architecture/dc_bias_audio_dac.md` — complete 24-bit audio DAC bias circuit design:
  - PCM1794A + OPA2134 I/V + ADA4522-2 zero-drift buffer + OPA548 HV stage
  - ~200 uV noise at 10 Hz BW matches Keithley 2400 at ~$36 BOM
- `gui/diagram.py` — new matplotlib signal chain figure with three colour-coded sections:
  - FPGA digital domain (DDS, CIC, I/Q demod, FIR, C/G extraction)
  - Analog front-end (BNC, coax with C_cable/L_cable, bias tee, TIA, bias DAC chain)
  - Physical / DUT cross-section (gate pad, gate oxide Cox, Si substrate Cdep, bulk contact, chuck)
  - All parasitic elements annotated in red with typical values
  - Parameter values (f0, Rf, In, Vn, ADC bits, CIC R, LPF BW, Cox) injected from current GUI state
- `gui/app.py` — Streamlit GUI refactored:
  - All sidebar parameters wrapped in `st.form()` — changes batch until "Apply Parameters" clicked
  - All numeric inputs use `st.number_input()` for exact value entry (no sliders for precision params)
  - Na doping entered as mantissa + exponent (two-column layout)
  - New "Signal Chain Diagram" tab renders the complete parasitic diagram
  - 6-column metric row: Cox, fs_out, sigma_C total, dominant noise source, TIA signal, optimal Rf
  - Noise budget tab with Rf crossover annotation, BW-for-target metrics, and design tradeoffs table

### Architecture decisions recorded

- 2-tone baseline (1 MHz + 100 kHz), extensible to N tones
- 18-bit data path, 25-bit coefficients, 48-bit accumulators (DSP48E1 native)
- VC707 = prototype platform, TE0741 (XC7K70T-2IF Kintex-7) = deployable target
- Python simulation serves as golden reference for RTL verification
- Communication: Ethernet (target); UART for bring-up
- DC bias: 24-bit audio DAC (PCM1794A) approach recommended over PWM, discrete DAC, or SMU

---
