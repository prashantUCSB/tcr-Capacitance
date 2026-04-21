# TCR Capacitance — Sub-pF CV Measurement System

A cleanroom-grade Capacitance-Voltage (CV) measurement instrument based on a digital I/Q lock-in amplifier architecture, targeting sub-pF sensitivity.

## Hardware Targets

| Board | FPGA | Role |
|-------|------|------|
| Xilinx VC707 Evaluation Kit | Virtex-7 XC7VX485T | Primary development / high-resource target |
| Trenz TE0741 Module | TBD | Embedded / compact target |

## Architecture Overview

```
Excitation DDS ──► Analog Frontend (TIA) ──► ADC
                                               │
                                    Pre-BW Filter (CIC/FIR)
                                               │
                                    I/Q Demodulator
                                    (×cos, ×sin with ref DDS)
                                               │
                                    Post-BW Filter (CIC/FIR LPF)
                                               │
                                    Magnitude / Phase / C extraction
                                               │
                                    Host Interface (Ethernet/USB)
                                               │
                                    Frontend GUI
```

## Repository Structure

```
tcr-Capacitance/
├── fpga/
│   ├── vc707/          # Vivado project for VC707
│   └── te0741/         # Vivado project for TE0741
├── hdl/
│   ├── rtl/            # Synthesizable RTL (Verilog/VHDL)
│   └── sim/            # Testbenches
├── firmware/           # Embedded software (MicroBlaze / ARM PS)
├── frontend/           # Host GUI application
├── docs/
│   ├── PROMPTS.md      # Prompt engineering log
│   └── architecture/   # Design documents
├── scripts/            # Utility scripts (Python, TCL)
├── CHANGELOG.md
└── README.md
```

## Status

> Early design phase — architecture under discussion.

## License

TBD
