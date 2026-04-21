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

*Subsequent sessions and prompts will be appended below.*
