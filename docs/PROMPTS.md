# Prompt Engineering Log

This document records all significant prompts and responses in the development of the TCR Capacitance CV measurement system. It serves as a design rationale trail and reference for future AI-assisted development sessions.

---

## Session 001 — 2026-04-21

### Prompt 1 — Project Kickoff

**User:**
> I want to design a CV measurement device for my cleanroom that measures sub pF level capacitance. The brain of the architecture involves creating a digital I/Q demodulator with pre and post bandwidth limiting filters. I would like to implement this on a VC707 evaluation kit and simultaneously on a trenz TE0741 FPGA module. My goal for this sub-project to demonstrate a working lock-in simulation. Ask me a ton of questions regarding this entire project, make suggestions, create a github project under prashantUCSB, make a changelog and prompt engineering doc to record all prompts and responses (basically the entire conversation). We also need a front end to talk to these FPGAs.

**Assistant Actions:**
- Initialized git repository and GitHub remote `prashantUCSB/tcr-Capacitance`
- Created project scaffold: README, CHANGELOG, PROMPTS.md, .gitignore, directory structure
- Asked comprehensive architecture, hardware, DSP, and software questions (see below)

**Key Design Decisions Pending (awaiting user answers):**
- Excitation frequency and ADC/DAC selection
- HDL language choice
- Frontend framework
- Communication interface (Ethernet vs USB vs PCIe)
- DC bias source for CV sweep

---

---

### Prompt 2 — Python Simulation + GUI + DC Bias

**User:**
> Let us work on the python simulator first. Implement option 2. Did you make a GUI where I can tune the inputs? What parameter knobs do I have to play with? Do not forget to push to git and update all docs. For the DC bias generation, why not use a 24-bit audio DAC? Is there a way to achieve Keithley level of bias performance with COTS components?

**Assistant Actions:**

- Built full Python lock-in simulation (dds, filters, demod, chain, dut modules)
- Fixed 3 physics/math bugs in C/G extraction (DDS quadrature, TIA sign, extraction sign)
- Fixed block size calculation to use FIR group delay x3 (prevents under-settled extraction)
- Created `bw_sweep.py` — bandwidth vs. noise floor sweep, confirmed sqrt(BW) scaling
- Created `docs/architecture/dc_bias_audio_dac.md` — PCM1794A + OPA548 circuit ($36 BOM, 200 uV noise)
- Created initial Streamlit GUI with sliders

**Key findings:**

- Dominant noise at Rf=10 kohm is Vn (voltage noise), not In (current noise)
- Crossover Rf = Vn/In = 5 nV/rtHz / 2 fA/rtHz = 2.5 Mohm
- Audio DAC approach matches Keithley 2400 noise at 1% of the cost

---

### Prompt 3 — GUI Refinement: Number Inputs, Signal Chain Diagram

**User:**
> Refine the simulation. I want to be able to enter numbers on the web-app. Would you recommend switching to PyQt instead? Can you make a diagram on the app showing the complete signal chain, including the cables where parasitics might arise?

**Assistant Actions:**

- Recommended staying with Streamlit: st.form() + st.number_input() gives exact value entry without framework switch
- Refactored gui/app.py: all sidebar params in st.form("params_form"), all precision values use st.number_input()
- Na doping input split into mantissa + exponent columns
- Created gui/diagram.py: matplotlib figure with 3 colour-coded sections (FPGA/Analog/Physical)
  - Probe tips, coax cable (C_cable, L_cable), bias tee, TIA, bias DAC chain, DUT cross-section
  - All parasitic elements in red with typical values; current GUI parameters injected into blocks
- Added "Signal Chain Diagram" tab to the GUI (5 tabs total)
- Added calibration guidance (Open/Short/Load strategy) to diagram tab

**Design decisions:**

- Streamlit retained over PyQt: zero deployment overhead, shareable URL, adequate for lab use
- st.form() pattern prevents partial re-renders during multi-parameter changes
- Diagram updates live with each "Apply Parameters" to stay in sync with current settings

*Subsequent sessions and prompts will be appended below.*
