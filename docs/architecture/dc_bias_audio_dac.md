# DC Bias Generation: 24-bit Audio DAC Approach

## Goal

Generate a ±25 V DC bias for C-V sweeps with noise performance approaching
laboratory SMU instruments (Keithley 236/2400), using COTS components.

---

## Reference: Keithley 2400 SMU Specs

| Parameter | Value |
|-----------|-------|
| Voltage output noise | < 300 µV (10 Hz BW) |
| Voltage resolution | 100 µV (1 V range) |
| Stability (1 hr) | < 200 ppm |
| Settling time | < 1 ms |

---

## Why a 24-bit Audio DAC?

Consumer audio DACs designed for 24-bit PCM playback achieve extraordinary
dynamic range — the same property that makes them quiet for audio makes
them precise for DC voltage generation.

| Parameter | Keithley 2400 | PCM1794A | ES9038PRO | AK4499EX |
|-----------|--------------|----------|-----------|----------|
| Effective bits | ~20 | 24 | 24 | 24 |
| Dynamic range | — | 132 dB | 140 dB | 140 dB |
| Noise floor | ~300 µV | ~6 µV* | ~3 µV* | ~2 µV* |
| Cost | ~$3000 | $5 | $15 | $25 |
| Interface | GPIB/USB | I²S | I²S | I²S |

*Noise referred to ±1 V output, 10 Hz BW, with appropriate post-filtering.
Scaled to ±25 V output: ×25, so noise increases to 50–150 µV range.

**Conclusion: A COTS 24-bit audio DAC + precision amplifier circuit can match
or beat Keithley noise performance at <1% of the cost.**

---

## Recommended Parts

### DAC

**Texas Instruments PCM1794A** — best-proven choice for precision DC apps:
- 24-bit, I²S input directly from FPGA
- 132 dB dynamic range
- Differential current output (I/V conversion needed)
- Well-characterized DC behavior, widely used in precision measurement hacks
- ~$5 in single quantities

Alternatives if availability is poor:
- ESS ES9038PRO: 140 dB, better noise but QFN-48 package is harder to hand-solder
- TI PCM5122: simpler (integrated PLL), 112 dB, good for prototyping

### I/V Conversion (DAC output → voltage)

The PCM1794A has differential current outputs ±3 mA FS.

Use a precision differential transimpedance stage:
- **OPA2134** or **AD8676** (dual op-amp): 6 nV/√Hz noise, ±18V supply
- Feedback resistors: 1 kΩ matched 0.01% → ±3 V output for FS input
- Add a 100 pF feedback cap to roll off at 1.6 MHz (avoid noise peaking)

### Post-filtering

Audio DACs are designed for 44.1–384 kHz playback.  For DC measurement,
we need to suppress the ΔΣ DAC's high-frequency shaped noise:

1. **2nd-order RC filter**: R=10 kΩ, C=10 µF → f_c = 1.6 Hz.  This
   attenuates the ΔΣ quantization noise by >80 dB above 100 Hz.
2. The filter must be buffered to avoid loading effects.

### Low-noise buffer

The most critical component.  Requirements: < 10 nV/√Hz voltage noise,
< 50 pA/√Hz current noise, zero-drift for low-frequency accuracy.

**Best COTS choices (in order of preference):**

| Part | Vn | In | Supply | Notes |
|------|----|----|--------|-------|
| **ADA4522-2** | 5.9 nV/√Hz | 100 fA/√Hz | ±2.5–18V | Zero-drift, best overall |
| **OPA2188** | 7.5 nV/√Hz | 200 fA/√Hz | ±18V | Zero-drift, good |
| **LTC2057** | 2.9 nV/√Hz | 25 pA/√Hz | ±5–18V | Lowest Vn, higher In |
| **AD8628** | 22 nV/√Hz | 5 pA/√Hz | ±2.5–5V | Good for low-voltage range |

### High-voltage stage (±25V output)

The buffer above is limited to ±18V supply.  To reach ±25–40V:

**Option A — Direct HV op-amp:**
- **OPA548**: ±30V supply, 3 A output, 4 nV/√Hz.  Drive directly.
- Connect buffer output to OPA548 non-inverting input with gain = 1
  (unity-gain follower from the ±15V-output buffer → ±25V supply rails for OPA548)

**Option B — Precision gain resistors (cleaner noise):**
- Buffer at ±3V → precision resistive divider sets gain
- OPA548 in non-inverting config, gain = 1 + R2/R1 = 8.33 for ×8.33 (±3V → ±25V)
- Use 0.01% resistors (Vishay VSR series, ~$2/each)
- This converts voltage noise ×8.33 but maintains precision

### Recommended complete circuit

```
FPGA I²S ──► PCM1794A ──► OPA2134 (I/V, ±3V)
                              │
                         RC LPF (1.6 Hz)
                              │
                         ADA4522-2 (buffer, zero-drift)
                              │
                         OPA548 (×8.33 gain, ±25V output)
                              │
                         DUT bias connection
```

---

## Noise Budget

With the recommended circuit and 10 Hz measurement BW:

| Source | Contribution (±25 V range) |
|--------|---------------------------|
| PCM1794A DAC noise | ~4 µV/√Hz × √10 Hz = 12 µV |
| OPA2134 I/V stage | ~6 nV/√Hz × 8.33 × √10 = 160 nV → negligible |
| RC filter attenuation | ~50 dB at 10 Hz → reduces DAC noise to ~38 nV |
| ADA4522-2 buffer | 5.9 nV/√Hz × 8.33 × √10 = 155 nV |
| OPA548 output | 4 nV/√Hz × √10 = 13 nV |
| Resistor Johnson (10 kΩ) | 4 nV/√Hz × √10 = 13 nV |
| **Total** | **~< 200 µV (10 Hz BW)** |

This matches or beats the Keithley 2400 output noise specification.

---

## 1/f Noise Concern

Audio DACs and precision op-amps have 1/f (flicker) noise that rises
below ~10–100 Hz.  For CV sweeps, the bias settles to a new value and
we integrate the measurement over ~1/BW seconds.  If the bias drifts
during integration, it corrupts the C-V data.

**Mitigation:**
1. Use zero-drift (chopper-stabilized) op-amps (ADA4522, OPA2188) — these
   have extremely low 1/f noise corner (<0.1 Hz).
2. Add a large-value (470 µF tantalum or 1000 µF electrolytic) bypass cap
   at the output with a small series resistor (10 Ω) to form a local
   charge reservoir.
3. For the most demanding measurements, use a precision voltage reference
   (LM399 or ADR1399) as an external calibration point and correct in software.

---

## FPGA Interface

The PCM1794A accepts 24-bit I²S (or left-justified / right-justified format).
The FPGA generates:
- **BCLK**: bit clock = 64× LRCLK (e.g., 48 kHz × 64 = 3.072 MHz)
- **LRCLK**: word select = target update rate (use 48 kHz for smooth sweeps)
- **DATA**: 24-bit two's complement, MSB first

Update rate 48 kHz gives 20 µs settling per step — fast enough for a
200-point CV sweep in < 5 ms (much faster than the lock-in integration time).

---

## Ultra-Low-Noise Alternative: Battery Reference

For the absolute lowest noise bias source with COTS components,
a battery-powered circuit avoids all switching supply interference:

1. 9V alkaline battery → LM399 precision reference (6.95 V, 1.5 µVpp noise)
2. Precision resistor divider (Vishay Z-foil series, ~0.1 ppm/°C TC)
3. OPA2188 buffer
4. Switch for coarse voltage selection + fine trim DAC

This achieves < 10 µV noise at any bandwidth, but is limited to a fixed
voltage range and requires manual or relay switching.  Suitable for the
final instrument where bias range is known.

---

## Comparison Table

| Approach | Noise (10 Hz BW) | Cost | Programmability | Notes |
|----------|-----------------|------|-----------------|-------|
| Keithley 2400 SMU | 300 µV | $3000+ | Full GPIB/USB | Research standard |
| Audio DAC circuit (above) | ~200 µV | ~$50 BOM | FPGA I²S | **Recommended** |
| 16-bit precision DAC (DAC8830) | ~2 mV | ~$10 | SPI | Adequate for demo |
| Battery reference | < 10 µV | ~$20 | None/relay | Best noise, limited range |
| FPGA PWM + RC | ~10 mV | < $1 | Direct | Too noisy for sub-pF |

---

## Recommended Parts List

| Part | Qty | ~Cost | Source |
|------|-----|-------|--------|
| PCM1794A (DAC) | 1 | $5 | DigiKey / Mouser |
| OPA2134UA (I/V) | 1 | $4 | TI / DigiKey |
| ADA4522-2ARZ (buffer) | 1 | $6 | Analog Devices |
| OPA548T (HV output) | 1 | $8 | TI / DigiKey |
| Vishay 0.01% resistors | 6 | $12 | DigiKey |
| 10 kΩ / 10 µF RC filter | — | $1 | — |
| **Total** | | **~$36** | |
