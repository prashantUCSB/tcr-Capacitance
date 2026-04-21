"""
Streamlit GUI — Digital Lock-in CV Measurement Simulator.

Run from the repo root:
    streamlit run simulation/python/gui/app.py

All sidebar parameters live inside an st.form() so changes are batched —
nothing re-runs until you click "Apply Parameters".
Number inputs (st.number_input) are used for all precision values so you
can type exact numbers rather than dragging sliders.
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
from diagram import make_signal_chain_figure

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TCR Lock-in CV Simulator",
    page_icon="⚡",
    layout="wide",
)
st.title("TCR — Digital Lock-in CV Measurement Simulator")
st.caption(
    "Sub-pF capacitance extraction via digital I/Q demodulation  ·  "
    "All parameters in the sidebar — click **Apply Parameters** to update."
)

# ── Sidebar — all inputs inside one form ─────────────────────────────────────

with st.sidebar:
    with st.form("params_form"):

        # ── Device Under Test ─────────────────────────────────────────────────
        st.subheader("Device Under Test")

        area_um2 = st.number_input(
            "Gate area (µm²)", min_value=0.01, max_value=1e6,
            value=100.0, step=1.0, format="%.2f",
            help="Total MOS gate area. 100 µm² = 10×10 µm.")
        tox_nm = st.number_input(
            "Oxide thickness tox (nm)", min_value=1.0, max_value=2000.0,
            value=100.0, step=1.0, format="%.1f",
            help="Gate oxide thickness. Teaching fab: 50–200 nm typical.")

        col_na, col_na_exp = st.columns(2)
        Na_mantissa = col_na.number_input("Na mantissa", 1.0, 9.9, 1.0, 0.1, "%.1f")
        Na_exp      = col_na_exp.number_input("×10^  (cm⁻³)", 14, 19, 16, 1, "%d")
        Na_cm3 = Na_mantissa * 10 ** Na_exp

        Vfb = st.number_input(
            "Flat-band voltage Vfb (V)", min_value=-10.0, max_value=10.0,
            value=-0.5, step=0.01, format="%.2f",
            help="Flat-band voltage. Negative for p-Si with Al gate.")
        T_K = st.number_input(
            "Temperature (K)", min_value=77.0, max_value=500.0,
            value=300.0, step=1.0, format="%.0f")

        st.divider()
        st.subheader("Bias Sweep")

        col_v1, col_v2 = st.columns(2)
        V_start = col_v1.number_input("V start (V)", -30.0, 0.0, -3.0, 0.1, "%.1f")
        V_stop  = col_v2.number_input("V stop (V)",   0.0, 30.0,  3.0, 0.1, "%.1f")
        n_sweep_pts = st.select_slider(
            "Sweep points", options=[11, 21, 41, 61, 101, 201], value=41)

        st.divider()
        st.subheader("Lock-in Chain")

        f0_MHz = st.number_input(
            "Excitation frequency f₀ (MHz)", min_value=0.001, max_value=50.0,
            value=1.0, step=0.1, format="%.3f",
            help="1 MHz = HP4280 standard. Higher f → better C noise, worse series-R error.")
        f0 = f0_MHz * 1e6

        multitone = st.checkbox(
            "Enable 2nd tone at f₀ / 10", value=False,
            help="Adds a second tone for equivalent circuit fitting.")

        Vexc_mV = st.number_input(
            "Excitation amplitude (mV rms)", min_value=0.1, max_value=1000.0,
            value=30.0, step=0.5, format="%.1f",
            help="30 mV = HP4280 standard. Keep small for DUT linearity.")

        fs_MHz = st.number_input(
            "ADC sample rate fs (MHz)", min_value=1.0, max_value=500.0,
            value=125.0, step=5.0, format="%.1f",
            help="125 MHz = typical FMC ADC card (AD9643, ADS2S1000, etc.)")
        fs_in = fs_MHz * 1e6

        dec_options = [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]
        dec_idx = st.select_slider(
            "CIC decimation ratio R", options=dec_options, value=32,
            help="fs_out = fs / R.  Higher R → lower output rate, better anti-alias rejection.")

        lpf_bw_hz = st.number_input(
            "Lock-in bandwidth BW (Hz)", min_value=0.01, max_value=500e3,
            value=50e3, step=1.0, format="%.2f",
            help="Narrower BW → lower noise but slower. σ_C ∝ √BW.")

        st.divider()
        st.subheader("TIA (Transimpedance Amplifier)")

        Rf_kohm = st.number_input(
            "Feedback resistance Rf (kΩ)", min_value=0.001, max_value=100e3,
            value=10.0, step=1.0, format="%.3f",
            help="Higher Rf = more gain. Optimal Rf = Vn / In (typ. 0.1–10 MΩ).")
        Rf = Rf_kohm * 1e3

        col_in, col_vn = st.columns(2)
        In_fA = col_in.number_input(
            "In (fA/√Hz)", 0.01, 10000.0, 2.0, 0.1, "%.2f",
            help="Input current noise density. Electrometer grade: 0.5–5 fA/√Hz.")
        Vn_nV = col_vn.number_input(
            "Vn (nV/√Hz)", 0.1, 1000.0, 5.0, 0.1, "%.1f",
            help="Op-amp voltage noise. Dominates at low Rf.")

        st.divider()
        st.subheader("ADC")

        adc_bits = st.select_slider("ADC resolution (bits)", [10, 12, 14, 16, 18, 24], value=16)
        adc_vref = st.number_input(
            "ADC full-scale ±V", min_value=0.1, max_value=10.0,
            value=1.0, step=0.1, format="%.1f")

        st.divider()
        add_noise = st.toggle("Enable noise model", value=True)

        submitted = st.form_submit_button(
            "Apply Parameters", use_container_width=True, type="primary")

# ── Derived values (computed once from current form state) ────────────────────

device = MOSCapParams(
    area_m2=area_um2 * 1e-12,
    tox_m=tox_nm * 1e-9,
    Na_m3=Na_cm3 * 1e6,
    Vfb=Vfb,
    T_K=T_K,
)
Cox_fF    = device.Cox_F * 1e15
fs_out_hz = fs_in / dec_idx
omega     = 2 * np.pi * f0

# Theoretical noise budget
sigma_C_In  = 2 * (In_fA * 1e-15) * np.sqrt(lpf_bw_hz) / (Vexc_mV * 1e-3 * omega) * 1e15
sigma_C_Vn  = 2 * (Vn_nV * 1e-9)  * np.sqrt(lpf_bw_hz) / (Vexc_mV * 1e-3 * omega * Rf) * 1e15
lsb         = 2 * adc_vref / (2 ** adc_bits)
sigma_C_adc = 2 * (lsb / np.sqrt(12)) * np.sqrt(lpf_bw_hz / (fs_in / 2)) / (
              Vexc_mV * 1e-3 * omega * Rf) * 1e15
sigma_C_tot = np.sqrt(sigma_C_In**2 + sigma_C_Vn**2 + sigma_C_adc**2)

signal_V = Vexc_mV * 1e-3 * omega * device.Cox_F * Rf
snr_db   = 20 * np.log10(max(signal_V, 1e-20) / max(sigma_C_tot * 1e-15 * Vexc_mV * 1e-3 * omega * Rf / 2, 1e-20))

# ── Key metric row ────────────────────────────────────────────────────────────

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Cox",              f"{Cox_fF:.2f} fF")
m2.metric("fs_out",           f"{fs_out_hz/1e3:.2f} kHz")
m3.metric("σ_C total (1σ)",   f"{sigma_C_tot:.4f} fF")
m4.metric("Dominant noise",
          "Vn" if sigma_C_Vn > max(sigma_C_In, sigma_C_adc) else
          "In" if sigma_C_In > sigma_C_adc else "ADC")
m5.metric("TIA signal @ Cox", f"{signal_V*1e6:.2f} µV")
m6.metric("Rf optimal",
          f"{Vn_nV*1e-9 / (In_fA*1e-15) / 1e3:.0f} kΩ")

# ── Tab layout ────────────────────────────────────────────────────────────────

tab_cv, tab_diag, tab_filter, tab_noise, tab_chain = st.tabs(
    ["C-V Curve", "Signal Chain Diagram", "Filter Response", "Noise Budget", "Parameters"])

# ── Analytic C-V (always recomputed) ─────────────────────────────────────────

V_ref  = np.linspace(V_start, V_stop, 500)
C_ref, G_ref = cv_curve(V_ref, device)

# ── Tab: C-V Curve ────────────────────────────────────────────────────────────

with tab_cv:
    fig_cv = make_subplots(
        rows=2, cols=1,
        subplot_titles=("C-V Curve", "Extraction error vs. analytic model"),
        vertical_spacing=0.13,
    )
    fig_cv.add_trace(go.Scatter(
        x=V_ref, y=C_ref * 1e15, name="Analytic (ideal)",
        line=dict(color="black", width=2)), row=1, col=1)
    fig_cv.add_hline(y=Cox_fF, line_dash="dot", line_color="gray",
                     annotation_text=f"Cox = {Cox_fF:.2f} fF", row=1, col=1)

    run_col, hint_col = st.columns([1, 4])
    with run_col:
        run_sim = st.button("Run CV Simulation", type="primary", use_container_width=True)
    with hint_col:
        n_ind = max(1, int(np.round(500_000 * 2 * lpf_bw_hz / fs_in)))
        st.info(
            f"Est. ~{n_sweep_pts * 0.15:.0f}s · "
            f"~{n_ind} independent samples/block at {lpf_bw_hz:.1f} Hz BW · "
            f"σ_C ≈ {sigma_C_tot:.4f} fF (theory)"
        )

    if run_sim:
        frequencies = [f0, f0 / 10] if multitone else [f0]
        params = LockInChainParams(
            fs_in=fs_in,
            frequencies=frequencies,
            excitation_amplitude_V=Vexc_mV * 1e-3,
            post_dec_R=dec_idx,
            post_cic_stages=4,
            lpf_bw_hz=lpf_bw_hz,
            tia=TIAParams(Rf_ohm=Rf, input_noise_A_rHz=In_fA * 1e-15,
                          voltage_noise_V_rHz=Vn_nV * 1e-9),
            adc=ADCParams(bits=adc_bits, vref=adc_vref),
            add_noise=add_noise,
        )
        chain = LockInChain(params)
        V_sweep = np.linspace(V_start, V_stop, n_sweep_pts)
        C_meas  = np.zeros(n_sweep_pts)
        G_meas  = np.zeros(n_sweep_pts)
        C_meas2 = np.zeros(n_sweep_pts) if multitone else None

        prog = st.progress(0, text="Starting simulation…")
        for i, Vbias in enumerate(V_sweep):
            C_ana, Gp_ana = cv_curve(np.array([Vbias]), device)
            result = chain.measure(float(C_ana[0]), float(Gp_ana[0]))
            C_meas[i] = result[0]["C"]
            G_meas[i] = result[0]["G"]
            if multitone and len(result) > 1:
                C_meas2[i] = result[1]["C"]
            prog.progress((i + 1) / n_sweep_pts,
                          text=f"V={Vbias:+.2f}V  C={C_meas[i]*1e15:.2f}fF")
        prog.empty()

        st.session_state.update(
            C_meas=C_meas, G_meas=G_meas, V_sweep=V_sweep,
            C_meas2=C_meas2, last_f0_MHz=f0_MHz, last_Rf=Rf_kohm,
        )

    if "C_meas" in st.session_state:
        V_s = st.session_state["V_sweep"]
        C_s = st.session_state["C_meas"]
        lbl = f"Lock-in @ {st.session_state.get('last_f0_MHz', f0_MHz):.2f} MHz"
        fig_cv.add_trace(go.Scatter(
            x=V_s, y=C_s * 1e15, name=lbl,
            mode="markers+lines",
            marker=dict(color="red", size=6),
            line=dict(color="red", width=1, dash="dot")), row=1, col=1)
        if multitone and st.session_state.get("C_meas2") is not None:
            fig_cv.add_trace(go.Scatter(
                x=V_s, y=st.session_state["C_meas2"] * 1e15,
                name=f"Lock-in @ {f0_MHz/10:.2f} MHz (2nd tone)",
                mode="markers+lines",
                marker=dict(color="blue", size=6),
                line=dict(color="blue", width=1, dash="dot")), row=1, col=1)

        err_fF = (C_s - np.interp(V_s, V_ref, C_ref)) * 1e15
        fig_cv.add_trace(go.Scatter(
            x=V_s, y=err_fF, name="Error (fF)",
            mode="markers+lines", line=dict(color="steelblue")), row=2, col=1)
        rms = np.sqrt(np.mean(err_fF ** 2))
        for sign in (+1, -1):
            fig_cv.add_hline(y=sign * rms, line_dash="dash", line_color="red",
                             annotation_text=f"±RMS={rms:.3f}fF" if sign == 1 else "",
                             row=2, col=1)
        fig_cv.add_hline(y=0, line_color="black", line_width=0.5, row=2, col=1)

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("RMS error",    f"{rms:.3f} fF")
        e2.metric("Max error",    f"{np.max(np.abs(err_fF)):.3f} fF")
        e3.metric("Cox measured", f"{np.max(C_s)*1e15:.2f} fF")
        e4.metric("Cox true",     f"{Cox_fF:.2f} fF")

    fig_cv.update_xaxes(title_text="DC Bias (V)")
    fig_cv.update_yaxes(title_text="Capacitance (fF)", row=1, col=1)
    fig_cv.update_yaxes(title_text="Error (fF)",       row=2, col=1)
    fig_cv.update_layout(height=620, showlegend=True)
    st.plotly_chart(fig_cv, use_container_width=True)

# ── Tab: Signal Chain Diagram ─────────────────────────────────────────────────

with tab_diag:
    st.subheader("Complete Signal Chain with Parasitic Elements")

    fig_diag = make_signal_chain_figure(
        f0_MHz=f0_MHz,
        Rf_kohm=Rf_kohm,
        In_fA=In_fA,
        Vn_nV=Vn_nV,
        adc_bits=adc_bits,
        dec_R=dec_idx,
        lpf_bw_hz=lpf_bw_hz,
        Cox_fF=Cox_fF,
        area_um2=area_um2,
    )
    st.pyplot(fig_diag, use_container_width=True)
    plt_module = __import__("matplotlib.pyplot", fromlist=["close"])
    plt_module.close(fig_diag)

    st.divider()
    st.markdown("""
**Reading the diagram**

| Colour | Domain |
|--------|--------|
| Blue background | FPGA (digital) |
| Yellow background | Analog front-end (PCB) |
| Green background | Physical — probe station + DUT |
| Red text | Parasitic elements that need calibration |

**Calibration strategy (Open / Short / Load)**
1. **Open** — probe needles up, record background admittance → removes cable + probe parasitics
2. **Short** — probe needles on a low-resistance short pad → removes series inductance and contact resistance
3. **Load** — probe needles on a known reference capacitor (e.g. 1 pF NPO) → verifies extraction accuracy
4. Subtract Open and apply Short correction in software after each sweep

**Most critical parasitics at sub-pF levels**
- Probe tip capacitance (1–5 pF) — **far larger than the DUT signal** — *must* be removed by Open calibration
- TIA input capacitance (2–5 pF) — limits TIA bandwidth; keep leads short
- Return cable (50–100 pF) — not in the signal path but loads the TIA input
""")

# ── Tab: Filter Response ──────────────────────────────────────────────────────

with tab_filter:
    st.subheader("CIC Decimation Filter Response")
    f_cic, h_cic = cic_frequency_response(R=dec_idx, N=4, M=1, fs=fs_in, n_points=8192)
    fig_cic = go.Figure()
    fig_cic.add_trace(go.Scatter(x=f_cic / 1e6, y=h_cic, name="CIC (N=4)",
                                 line=dict(color="royalblue")))
    fig_cic.add_vline(x=f0 / 1e6, line_dash="dash", line_color="red",
                      annotation_text=f"f₀={f0/1e6:.2f}MHz")
    fig_cic.add_vline(x=(fs_out_hz / 2) / 1e6, line_dash="dot", line_color="orange",
                      annotation_text=f"Nyquist out={fs_out_hz/2/1e6:.3f}MHz")
    fig_cic.add_hline(y=-40, line_dash="dot", line_color="gray", annotation_text="-40 dB")
    fig_cic.update_layout(
        title=f"CIC Filter  R={dec_idx}, N=4  |  fs_in={fs_in/1e6:.0f} MHz → fs_out={fs_out_hz/1e3:.1f} kHz",
        xaxis_title="Frequency (MHz)", yaxis_title="Magnitude (dB)",
        yaxis_range=[-120, 5], height=380)
    st.plotly_chart(fig_cic, use_container_width=True)

    st.subheader("Post-Demodulation FIR LPF")
    from scipy import signal as sps
    lpf_taps = design_lowpass_fir(fs_out_hz, lpf_bw_hz)
    f_lpf, h_lpf = sps.freqz(lpf_taps, worN=4096, fs=fs_out_hz)
    fig_lpf = go.Figure()
    fig_lpf.add_trace(go.Scatter(x=f_lpf, y=20 * np.log10(np.abs(h_lpf) + 1e-300),
                                 name="FIR LPF", line=dict(color="seagreen")))
    fig_lpf.add_vline(x=lpf_bw_hz, line_dash="dash", line_color="red",
                      annotation_text=f"BW={lpf_bw_hz:.1f}Hz")
    fig_lpf.update_layout(
        title=f"Post-demod LPF  BW={lpf_bw_hz:.1f}Hz  |  {len(lpf_taps)} taps  |  "
              f"group delay {(len(lpf_taps)-1)/2/fs_out_hz*1000:.2f}ms",
        xaxis_title="Frequency (Hz)", yaxis_title="Magnitude (dB)",
        yaxis_range=[-100, 5], height=380)
    st.plotly_chart(fig_lpf, use_container_width=True)
    st.caption(
        f"FIR taps: {len(lpf_taps)}  ·  Group delay: {(len(lpf_taps)-1)/2/fs_out_hz*1000:.2f} ms  ·  "
        f"Required block size: ≥ {int(np.ceil((len(lpf_taps)-1)/2*3))*dec_idx:,} input samples")

# ── Tab: Noise Budget ─────────────────────────────────────────────────────────

with tab_noise:
    st.subheader("Noise Budget vs. Lock-in Bandwidth")
    bw_range = np.logspace(-1, 5, 400)
    noise_In_arr  = 2*(In_fA*1e-15)*np.sqrt(bw_range)/(Vexc_mV*1e-3*omega)*1e15
    noise_Vn_arr  = 2*(Vn_nV*1e-9) *np.sqrt(bw_range)/(Vexc_mV*1e-3*omega*Rf)*1e15
    noise_adc_arr = 2*(lsb/np.sqrt(12))*np.sqrt(bw_range/(fs_in/2))/(Vexc_mV*1e-3*omega*Rf)*1e15
    noise_tot_arr = np.sqrt(noise_In_arr**2 + noise_Vn_arr**2 + noise_adc_arr**2)

    fig_nb = go.Figure()
    fig_nb.add_trace(go.Scatter(x=bw_range, y=noise_In_arr,  name=f"In = {In_fA:.1f} fA/√Hz",
                                line=dict(color="steelblue", dash="dash")))
    fig_nb.add_trace(go.Scatter(x=bw_range, y=noise_Vn_arr,  name=f"Vn = {Vn_nV:.1f} nV/√Hz",
                                line=dict(color="darkorange", dash="dash")))
    fig_nb.add_trace(go.Scatter(x=bw_range, y=noise_adc_arr, name=f"ADC {adc_bits}-bit quant.",
                                line=dict(color="purple", dash="dot")))
    fig_nb.add_trace(go.Scatter(x=bw_range, y=noise_tot_arr, name="Total (RSS)",
                                line=dict(color="crimson", width=3)))
    fig_nb.add_hline(y=1.0,  line_dash="dash", line_color="green",
                     annotation_text="1 fF target", annotation_position="right")
    fig_nb.add_hline(y=0.1,  line_dash="dash", line_color="limegreen",
                     annotation_text="0.1 fF target", annotation_position="right")
    fig_nb.add_vline(x=lpf_bw_hz, line_dash="solid", line_color="gray",
                     annotation_text=f"Current BW={lpf_bw_hz:.1f}Hz")
    # Rf crossover annotation
    Rf_opt = (Vn_nV * 1e-9) / (In_fA * 1e-15)
    if Rf < Rf_opt * 0.99:
        note = f"Rf < Rf_opt ({Rf_opt/1e3:.0f} kΩ) → Vn dominates"
    elif Rf > Rf_opt * 1.01:
        note = f"Rf > Rf_opt ({Rf_opt/1e3:.0f} kΩ) → In dominates"
    else:
        note = "Rf ≈ Rf_opt — equal noise contributions"
    fig_nb.add_annotation(x=1, y=0.8, text=note, xref="paper", yref="paper",
                          showarrow=False, bgcolor="white", bordercolor="gray",
                          font=dict(size=11))
    fig_nb.update_layout(
        title="Theoretical σ_C vs. Lock-in Bandwidth",
        xaxis_title="Lock-in Bandwidth (Hz)", yaxis_title="σ_C (fF)",
        xaxis_type="log", yaxis_type="log", height=500)
    st.plotly_chart(fig_nb, use_container_width=True)

    # Crossings table
    def bw_for_target(target_fF):
        combined_sq = ((2*(In_fA*1e-15)/(Vexc_mV*1e-3*omega))**2
                     + (2*(Vn_nV*1e-9)/(Vexc_mV*1e-3*omega*Rf))**2
                     + (2*(lsb/np.sqrt(12))/(Vexc_mV*1e-3*omega*Rf*np.sqrt(fs_in/2)))**2)
        return (target_fF * 1e-15) ** 2 / combined_sq

    nb1, nb2, nb3, nb4 = st.columns(4)
    nb1.metric("σ_C at current BW", f"{sigma_C_tot:.4f} fF")
    nb2.metric("BW for 1 fF",  f"{bw_for_target(1.0):.1f} Hz")
    nb3.metric("BW for 0.1 fF", f"{bw_for_target(0.1):.3f} Hz")
    nb4.metric("Optimal Rf",   f"{Rf_opt/1e3:.1f} kΩ")

# ── Tab: Signal Chain Parameters ─────────────────────────────────────────────

with tab_chain:
    st.subheader("Parameter Summary")

    def _fmt(v): return f"{v:,.4g}"

    param_table = {
        "Parameter": [
            "Excitation frequency f₀", "Excitation amplitude",
            "ADC sample rate fs", "CIC decimation R", "CIC stages N",
            "Output rate fs_out", "Lock-in bandwidth BW", "FIR taps (approx)",
            "FIR group delay", "Block size (approx)",
            "TIA feedback Rf", "TIA current noise In",
            "TIA voltage noise Vn", "Optimal Rf (Vn/In)",
            "ADC bits", "ADC full-scale ±V", "ADC LSB",
            "DDS FTW (32-bit)", "DDS frequency resolution",
            "TIA signal @ Cox", "Dominant noise source",
        ],
        "Value": [
            f"{f0_MHz:.3f} MHz", f"{Vexc_mV:.1f} mV rms",
            f"{fs_in/1e6:.1f} MHz", str(dec_idx), "4",
            f"{fs_out_hz/1e3:.3f} kHz", f"{lpf_bw_hz:.2f} Hz",
            f"~{len(design_lowpass_fir(fs_out_hz, lpf_bw_hz))}",
            f"{(len(design_lowpass_fir(fs_out_hz, lpf_bw_hz))-1)/2/fs_out_hz*1e3:.2f} ms",
            f"≥{int(np.ceil((len(design_lowpass_fir(fs_out_hz, lpf_bw_hz))-1)/2*3)*dec_idx):,}",
            f"{Rf_kohm:.3f} kΩ  ({20*np.log10(Rf):.0f} dBΩ)",
            f"{In_fA:.2f} fA/√Hz",
            f"{Vn_nV:.1f} nV/√Hz",
            f"{(Vn_nV*1e-9)/(In_fA*1e-15)/1e3:.1f} kΩ",
            f"{adc_bits} bit", f"±{adc_vref:.1f} V",
            f"{lsb*1e6:.2f} µV",
            f"{round(f0/fs_in * 2**32):,}",
            f"{fs_in/2**32*1e6:.3f} µHz / LSB",
            f"{signal_V*1e6:.3f} µV",
            "Vn" if sigma_C_Vn > max(sigma_C_In, sigma_C_adc) else
            "In" if sigma_C_In > sigma_C_adc else "ADC quant.",
        ],
    }
    st.table(param_table)

    st.subheader("Design Tradeoffs")
    st.markdown(f"""
| Knob | Noise effect | Speed effect | Current setting |
|------|-------------|--------------|-----------------|
| BW ↓ 10× | σ_C ÷ 3.16 dB | 10× slower | {lpf_bw_hz:.1f} Hz |
| Rf ↑ 10× | Better if In-limited, worse if Vn-limited | — | {Rf_kohm:.1f} kΩ |
| f₀ ↑ 10× | σ_C ÷ 10 (all sources) | Same | {f0_MHz:.2f} MHz |
| Vexc ↑ 10× | σ_C ÷ 10 | Same | {Vexc_mV:.1f} mV |
| ADC bits +4 | ADC floor ÷ 16 | Same | {adc_bits} b |
| In ↑ (worse TIA) | σ_C_In ↑ | — | {In_fA:.1f} fA/√Hz |

**Current dominant noise: {'Vn (voltage)' if sigma_C_Vn > max(sigma_C_In, sigma_C_adc) else 'In (current)' if sigma_C_In > sigma_C_adc else 'ADC quantization'}**
- σ_C(In) = {sigma_C_In:.4f} fF
- σ_C(Vn) = {sigma_C_Vn:.4f} fF  ← {'← dominant ✓' if sigma_C_Vn > max(sigma_C_In, sigma_C_adc) else ''}
- σ_C(ADC) = {sigma_C_adc:.4f} fF
- **σ_C(total) = {sigma_C_tot:.4f} fF**
""")
