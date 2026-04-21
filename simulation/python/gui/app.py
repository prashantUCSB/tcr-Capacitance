"""
Streamlit GUI for the digital lock-in CV measurement simulator.

Run:
    streamlit run simulation/python/gui/app.py
    (from the repo root)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from lockin import LockInChain, LockInChainParams, TIAParams, ADCParams
from lockin.filters import cic_frequency_response, design_lowpass_fir
from dut import MOSCapParams, cv_curve

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TCR Lock-in CV Simulator",
    page_icon="⚡",
    layout="wide",
)
st.title("TCR — Digital Lock-in CV Measurement Simulator")
st.caption("Sub-pF capacitance extraction via digital I/Q demodulation")

# ── Sidebar — Device Under Test ────────────────────────────────────────────────

with st.sidebar:
    st.header("Device Under Test")

    area_um2 = st.slider("Gate area (µm²)", 1.0, 10000.0, 100.0, step=1.0,
                         help="Total MOS gate area. 100 µm² = 10×10 µm gate.")
    tox_nm = st.slider("Oxide thickness (nm)", 5.0, 500.0, 100.0, step=1.0,
                       help="Gate oxide thickness. Teaching fab: 50–200 nm typical.")
    Na_log = st.slider("p-type doping Na (log₁₀ cm⁻³)", 14.0, 18.0, 16.0, step=0.1,
                       help="Substrate doping. Typical: 1e15–1e17 cm⁻³.")
    Vfb = st.slider("Flat-band voltage Vfb (V)", -3.0, 3.0, -0.5, step=0.05,
                    help="Flat-band voltage. Negative for p-Si with Al gate (~-0.5 to -1 V).")
    T_K = st.slider("Temperature (K)", 200.0, 400.0, 300.0, step=5.0)
    V_start = st.slider("Bias sweep start (V)", -10.0, 0.0, -3.0, step=0.1)
    V_stop = st.slider("Bias sweep stop (V)", 0.0, 10.0, 3.0, step=0.1)
    n_sweep_pts = st.select_slider("Sweep points", [11, 21, 41, 61, 101], value=41)

    st.divider()
    st.header("Lock-in Chain")

    freq_options = {
        "100 kHz": 100e3,
        "500 kHz": 500e3,
        "1 MHz (HP4280)": 1e6,
        "2 MHz": 2e6,
        "5 MHz": 5e6,
    }
    freq_label = st.selectbox("Excitation frequency", list(freq_options.keys()),
                              index=2)
    f0 = freq_options[freq_label]

    multitone = st.checkbox("Enable 2nd tone (÷10 sub-harmonic)", value=False,
                            help="Adds a second tone at f0/10 for equivalent circuit fitting.")

    Vexc_mV = st.slider("Excitation amplitude (mV)", 1.0, 100.0, 30.0, step=1.0,
                        help="30 mV = HP4280 standard. Keep small for linearity.")

    fs_mhz_options = {"10 MHz": 10e6, "25 MHz": 25e6, "50 MHz": 50e6, "125 MHz": 125e6}
    fs_label = st.selectbox("ADC sample rate", list(fs_mhz_options.keys()), index=3)
    fs_in = fs_mhz_options[fs_label]

    dec_options = [8, 16, 32, 64, 128, 256, 512, 1024]
    dec_idx = st.select_slider("CIC decimation ratio", dec_options, value=32,
                               help="Higher = lower output rate, more rejection of out-of-band noise.")

    bw_options = {
        "50 kHz (fast demo)": 50e3,
        "10 kHz": 10e3,
        "1 kHz (DLTS range)": 1e3,
        "100 Hz": 100.0,
        "10 Hz": 10.0,
        "1 Hz (quasi-static)": 1.0,
        "0.1 Hz (ultra-narrow)": 0.1,
    }
    bw_label = st.selectbox("Lock-in bandwidth", list(bw_options.keys()), index=0,
                            help="Narrower = less noise but slower measurement.")
    lpf_bw = bw_options[bw_label]

    st.divider()
    st.header("TIA")

    Rf_options = {"1 kΩ": 1e3, "10 kΩ": 10e3, "100 kΩ": 100e3,
                  "1 MΩ": 1e6, "10 MΩ": 10e6}
    rf_label = st.selectbox("Feedback resistance Rf", list(Rf_options.keys()), index=1,
                            help="Higher Rf = more gain (better for small C) but lower TIA bandwidth.")
    Rf = Rf_options[rf_label]

    In_fA = st.slider("Input current noise (fA/√Hz)", 0.1, 100.0, 2.0, step=0.1,
                      help="Electrometer-grade: 0.5–5 fA/√Hz (OPA129, ADA4530, INA116).")
    Vn_nV = st.slider("Voltage noise (nV/√Hz)", 1.0, 50.0, 5.0, step=0.5,
                      help="Op-amp input voltage noise. Lower is better for high-Rf TIA.")

    st.divider()
    st.header("ADC")

    adc_bits = st.select_slider("ADC bits", [12, 14, 16, 18, 24], value=16)
    adc_vref = st.slider("ADC full-scale range ±V", 0.5, 5.0, 1.0, step=0.1)

    st.divider()
    add_noise = st.toggle("Enable noise model", value=True)

# ── Derived display values ────────────────────────────────────────────────────

col_info1, col_info2, col_info3 = st.columns(3)

device = MOSCapParams(
    area_m2=area_um2 * 1e-12,
    tox_m=tox_nm * 1e-9,
    Na_m3=10**Na_log * 1e6,
    Vfb=Vfb,
    T_K=T_K,
)
Cox_fF = device.Cox_F * 1e15
fs_out_hz = fs_in / dec_idx

with col_info1:
    st.metric("Cox", f"{Cox_fF:.2f} fF")
    st.metric("fs_out", f"{fs_out_hz/1e3:.1f} kHz")

with col_info2:
    omega = 2 * np.pi * f0
    sigma_C_theory = 2 * (In_fA * 1e-15) * np.sqrt(lpf_bw) / (Vexc_mV * 1e-3 * omega) * 1e15
    st.metric("Theoretical σ_C", f"{sigma_C_theory:.4f} fF")
    adc_floor_fF = 2 * (2 * adc_vref / 2**adc_bits / np.sqrt(12)) / (Vexc_mV * 1e-3 * omega * Rf) * 1e15
    st.metric("ADC quant. floor", f"{adc_floor_fF:.4f} fF")

with col_info3:
    # Estimate TIA BW limit (where Rf·Cf cutoff would be)
    tia_gain_bw = f0 * omega * Rf * device.Cox_F  # dimensionless signal level
    signal_V = Vexc_mV * 1e-3 * omega * device.Cox_F * Rf
    st.metric("TIA signal level", f"{signal_V*1e6:.2f} µV",
              help="Expected V_TIA amplitude for Cox at this frequency")
    snr_db = 20 * np.log10(signal_V / (In_fA * 1e-15 * np.sqrt(lpf_bw) * Rf + 1e-20))
    st.metric("SNR (estimate)", f"{snr_db:.1f} dB")

# ── Run simulation button ─────────────────────────────────────────────────────

run_col, hint_col = st.columns([1, 4])
with run_col:
    run_sim = st.button("Run CV Simulation", type="primary", use_container_width=True)
with hint_col:
    est_time_s = n_sweep_pts * 0.15
    st.info(f"Estimated time: ~{est_time_s:.0f}s for {n_sweep_pts} points at {lpf_bw/1e3:.1f} kHz BW. "
            f"Narrow BW (< 100 Hz) will be slower.")

# ── Tab layout ────────────────────────────────────────────────────────────────

tab_cv, tab_filter, tab_noise, tab_signal = st.tabs(
    ["C-V Curve", "Filter Response", "Noise Budget", "Signal Chain"]
)

# ── Analytic C-V (always shown) ───────────────────────────────────────────────

V_ref = np.linspace(V_start, V_stop, 500)
C_ref, G_ref = cv_curve(V_ref, device)

with tab_cv:
    fig_cv = make_subplots(
        rows=2, cols=1,
        subplot_titles=("C-V Curve", "Extraction Error (simulation vs analytic)"),
        vertical_spacing=0.12,
    )
    fig_cv.add_trace(
        go.Scatter(x=V_ref, y=C_ref * 1e15, name="Analytic (ideal)",
                   line=dict(color="black", width=2)),
        row=1, col=1,
    )
    fig_cv.add_hline(
        y=Cox_fF, line_dash="dot", line_color="gray",
        annotation_text=f"Cox = {Cox_fF:.2f} fF", row=1, col=1,
    )

    if run_sim:
        frequencies = [f0, f0 / 10] if multitone else [f0]
        params = LockInChainParams(
            fs_in=fs_in,
            frequencies=frequencies,
            excitation_amplitude_V=Vexc_mV * 1e-3,
            post_dec_R=dec_idx,
            post_cic_stages=4,
            lpf_bw_hz=lpf_bw,
            tia=TIAParams(
                Rf_ohm=Rf,
                input_noise_A_rHz=In_fA * 1e-15,
                voltage_noise_V_rHz=Vn_nV * 1e-9,
            ),
            adc=ADCParams(bits=adc_bits, vref=adc_vref),
            add_noise=add_noise,
        )
        chain = LockInChain(params)

        V_sweep = np.linspace(V_start, V_stop, n_sweep_pts)
        C_meas = np.zeros(n_sweep_pts)
        G_meas = np.zeros(n_sweep_pts)
        C_meas_2 = np.zeros(n_sweep_pts) if multitone else None

        progress = st.progress(0, text="Running simulation...")
        for i, Vbias in enumerate(V_sweep):
            C_ana, Gp_ana = cv_curve(np.array([Vbias]), device)
            result = chain.measure(Cp_F=float(C_ana[0]), Gp_S=float(Gp_ana[0]))
            C_meas[i] = result[0]["C"]
            G_meas[i] = result[0]["G"]
            if multitone and len(result) > 1:
                C_meas_2[i] = result[1]["C"]
            progress.progress((i + 1) / n_sweep_pts,
                              text=f"Point {i+1}/{n_sweep_pts} — V={Vbias:+.2f}V, C={C_meas[i]*1e15:.2f}fF")
        progress.empty()

        st.session_state["C_meas"] = C_meas
        st.session_state["G_meas"] = G_meas
        st.session_state["V_sweep"] = V_sweep
        st.session_state["C_meas_2"] = C_meas_2

    if "C_meas" in st.session_state:
        V_sweep = st.session_state["V_sweep"]
        C_meas = st.session_state["C_meas"]
        G_meas = st.session_state["G_meas"]

        fig_cv.add_trace(
            go.Scatter(x=V_sweep, y=C_meas * 1e15, name=f"Lock-in @ {f0/1e6:.1f}MHz",
                       mode="markers+lines",
                       marker=dict(color="red", size=6),
                       line=dict(color="red", width=1, dash="dot")),
            row=1, col=1,
        )
        if multitone and st.session_state["C_meas_2"] is not None:
            fig_cv.add_trace(
                go.Scatter(x=V_sweep, y=st.session_state["C_meas_2"] * 1e15,
                           name=f"Lock-in @ {f0/10/1e3:.0f}kHz",
                           mode="markers+lines",
                           marker=dict(color="blue", size=6),
                           line=dict(color="blue", width=1, dash="dot")),
                row=1, col=1,
            )

        error_fF = (C_meas - np.interp(V_sweep, V_ref, C_ref)) * 1e15
        fig_cv.add_trace(
            go.Scatter(x=V_sweep, y=error_fF, name="Error (fF)",
                       mode="markers+lines",
                       line=dict(color="blue", width=1)),
            row=2, col=1,
        )
        fig_cv.add_hline(y=0, line_color="black", line_width=0.5, row=2, col=1)
        rms_err = np.sqrt(np.mean(error_fF ** 2))
        fig_cv.add_hline(y=rms_err, line_dash="dash", line_color="red",
                         annotation_text=f"RMS={rms_err:.3f}fF", row=2, col=1)
        fig_cv.add_hline(y=-rms_err, line_dash="dash", line_color="red", row=2, col=1)

    fig_cv.update_xaxes(title_text="DC Bias (V)")
    fig_cv.update_yaxes(title_text="Capacitance (fF)", row=1, col=1)
    fig_cv.update_yaxes(title_text="Error (fF)", row=2, col=1)
    fig_cv.update_layout(height=600, showlegend=True)
    st.plotly_chart(fig_cv, use_container_width=True)

    if "C_meas" in st.session_state:
        m1, m2, m3, m4 = st.columns(4)
        error_fF = (st.session_state["C_meas"] - np.interp(
            st.session_state["V_sweep"], V_ref, C_ref)) * 1e15
        m1.metric("RMS error", f"{np.sqrt(np.mean(error_fF**2)):.3f} fF")
        m2.metric("Max error", f"{np.max(np.abs(error_fF)):.3f} fF")
        m3.metric("Cox measured", f"{np.max(st.session_state['C_meas'])*1e15:.2f} fF")
        m4.metric("Cox true", f"{Cox_fF:.2f} fF")

# ── Filter response tab ────────────────────────────────────────────────────────

with tab_filter:
    st.subheader("CIC Decimation Filter Frequency Response")
    f_cic, h_cic = cic_frequency_response(R=dec_idx, N=4, M=1, fs=fs_in, n_points=8192)
    nyq_out = fs_out_hz / 2

    fig_filt = go.Figure()
    fig_filt.add_trace(go.Scatter(x=f_cic / 1e6, y=h_cic, name="CIC (N=4)",
                                  line=dict(color="blue")))
    fig_filt.add_vline(x=f0 / 1e6, line_dash="dash", line_color="red",
                       annotation_text=f"f₀={f0/1e6:.1f}MHz")
    fig_filt.add_vline(x=nyq_out / 1e6, line_dash="dot", line_color="orange",
                       annotation_text=f"Nyquist out={nyq_out/1e6:.2f}MHz")
    fig_filt.add_hline(y=-40, line_dash="dot", line_color="gray",
                       annotation_text="-40 dB")
    fig_filt.update_layout(
        title=f"CIC Filter  R={dec_idx}, N=4, fs_in={fs_in/1e6:.0f}MHz",
        xaxis_title="Frequency (MHz)", yaxis_title="Magnitude (dB)",
        yaxis_range=[-120, 5], height=400,
    )
    st.plotly_chart(fig_filt, use_container_width=True)

    st.subheader("Post-Demodulation FIR Low-Pass Filter")
    lpf_taps = design_lowpass_fir(fs_out_hz, lpf_bw)
    from scipy import signal as sps
    f_lpf, h_lpf = sps.freqz(lpf_taps, worN=4096, fs=fs_out_hz)
    h_lpf_db = 20 * np.log10(np.abs(h_lpf) + 1e-300)

    fig_lpf = go.Figure()
    fig_lpf.add_trace(go.Scatter(x=f_lpf, y=h_lpf_db, name="FIR LPF",
                                 line=dict(color="green")))
    fig_lpf.add_vline(x=lpf_bw, line_dash="dash", line_color="red",
                      annotation_text=f"BW={lpf_bw:.1f}Hz")
    fig_lpf.update_layout(
        title=f"Post-demod LPF  BW={lpf_bw:.1f}Hz, taps={len(lpf_taps)}, fs={fs_out_hz/1e3:.0f}kHz",
        xaxis_title="Frequency (Hz)", yaxis_title="Magnitude (dB)",
        yaxis_range=[-100, 5], height=400,
    )
    st.plotly_chart(fig_lpf, use_container_width=True)
    st.caption(f"FIR taps: {len(lpf_taps)} — group delay: {(len(lpf_taps)-1)/2 / fs_out_hz * 1000:.2f} ms")

# ── Noise budget tab ───────────────────────────────────────────────────────────

with tab_noise:
    st.subheader("Noise Budget vs. Lock-in Bandwidth")

    bw_range = np.logspace(-1, 5, 300)
    omega_n = 2 * np.pi * f0

    noise_In = 2 * (In_fA * 1e-15) * np.sqrt(bw_range) / (Vexc_mV * 1e-3 * omega_n) * 1e15
    noise_Vn = 2 * (Vn_nV * 1e-9) * np.sqrt(bw_range) / (Vexc_mV * 1e-3 * omega_n * Rf) * 1e15
    noise_total = np.sqrt(noise_In**2 + noise_Vn**2 + adc_floor_fF**2)

    fig_noise = go.Figure()
    fig_noise.add_trace(go.Scatter(x=bw_range, y=noise_In, name=f"TIA current noise ({In_fA:.1f}fA/√Hz)",
                                   line=dict(color="blue", dash="dash")))
    fig_noise.add_trace(go.Scatter(x=bw_range, y=noise_Vn, name=f"TIA voltage noise ({Vn_nV:.1f}nV/√Hz)",
                                   line=dict(color="orange", dash="dash")))
    fig_noise.add_trace(go.Scatter(x=bw_range, y=[adc_floor_fF] * len(bw_range),
                                   name=f"ADC quant. floor ({adc_bits}b)",
                                   line=dict(color="purple", dash="dot")))
    fig_noise.add_trace(go.Scatter(x=bw_range, y=noise_total, name="Total (RSS)",
                                   line=dict(color="red", width=3)))
    fig_noise.add_hline(y=1.0, line_dash="dash", line_color="green",
                        annotation_text="1 fF", annotation_position="right")
    fig_noise.add_hline(y=0.1, line_dash="dash", line_color="lime",
                        annotation_text="0.1 fF", annotation_position="right")
    fig_noise.add_vline(x=lpf_bw, line_dash="solid", line_color="gray",
                        annotation_text=f"Current BW={lpf_bw:.1f}Hz")
    fig_noise.update_layout(
        title="Theoretical C Noise Floor (1σ) vs. Lock-in Bandwidth",
        xaxis_title="Lock-in Bandwidth (Hz)", yaxis_title="σ_C (fF)",
        xaxis_type="log", yaxis_type="log", height=500,
    )
    st.plotly_chart(fig_noise, use_container_width=True)

    # Noise crossings
    bw_for_1fF = (1e-15 / (2 * In_fA * 1e-15 / (Vexc_mV * 1e-3 * omega_n)))**2
    bw_for_01fF = bw_for_1fF / 100

    nc1, nc2, nc3 = st.columns(3)
    nc1.metric("BW for 1 fF resolution", f"{bw_for_1fF:.2f} Hz",
               help="From TIA current noise only")
    nc2.metric("BW for 0.1 fF resolution", f"{bw_for_01fF:.2f} Hz")
    nc3.metric("ADC quant. floor", f"{adc_floor_fF:.4f} fF",
               help="Bandwidth-independent floor from ADC LSB noise")

# ── Signal chain summary tab ──────────────────────────────────────────────────

with tab_signal:
    st.subheader("Signal Chain Parameter Summary")

    chain_data = {
        "Parameter": [
            "Excitation frequency f₀",
            "Excitation amplitude",
            "ADC sample rate fs_in",
            "CIC decimation ratio R",
            "CIC stages N",
            "Output rate fs_out",
            "Lock-in BW",
            "FIR taps (approx)",
            "TIA gain (Rf)",
            "TIA signal at Cox",
            "Dynamic range",
            "Phase bits (DDS)",
            "FTW (f₀)",
        ],
        "Value": [
            f"{f0/1e6:.2f} MHz",
            f"{Vexc_mV:.0f} mV",
            f"{fs_in/1e6:.0f} MHz",
            str(dec_idx),
            "4",
            f"{fs_out_hz/1e3:.1f} kHz",
            f"{lpf_bw:.2f} Hz",
            f"~{len(design_lowpass_fir(fs_out_hz, lpf_bw))}",
            f"{Rf/1e3:.1f} kΩ  ({20*np.log10(Rf):.0f} dBΩ)",
            f"{Vexc_mV*1e-3 * omega * device.Cox_F * Rf * 1e6:.2f} µV",
            f"{adc_bits} bit ({20*np.log10(2**adc_bits):.0f} dB)",
            "32 bits",
            f"{round(f0 / fs_in * 2**32):,}",
        ],
    }
    st.table(chain_data)

    st.subheader("Key Constraints & Tradeoffs")
    st.markdown(f"""
| Knob | Effect on noise | Effect on speed | Notes |
|------|----------------|-----------------|-------|
| Lock-in BW ↓ | σ_C ∝ √BW — halving BW → 3 dB better | 2× slower | Primary noise knob |
| Rf ↑ | Better current→voltage gain, more Johnson noise | No effect | Optimal Rf ≈ 1/(ω·C_min·√2) |
| f₀ ↑ | σ_C ∝ 1/ω — 10× f₀ → 20 dB better | Same speed | Limited by TIA BW, ADC rate |
| Vexc ↑ | σ_C ∝ 1/V — 10× more signal | Same | Limited by DUT linearity |
| ADC bits ↑ | Lower quant floor | Same | Diminishing returns above 16 b |
| Na ↑ | C_min/Cox ↓ (more depletion) | | Changes C range |

**Dominant noise source at current settings:**
- At BW={lpf_bw:.1f}Hz: σ_C(In) = {sigma_C_theory:.4f} fF, ADC floor = {adc_floor_fF:.4f} fF
- {"**TIA current noise dominates**" if sigma_C_theory > adc_floor_fF else "**ADC quantization dominates** — increase Rf or reduce BW"}
""")
