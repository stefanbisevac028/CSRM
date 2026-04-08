# CSRM: CPU-aware Slice Resource Manager for SDN

A closed-loop, CPU-aware traffic control framework for Software-Defined Networking (SDN) environments using eBPF/XDP and PID control.

## Overview

This framework provides real-time CPU-aware traffic management for multi-tenant Open vSwitch (OVS) dataplanes. It integrates:

- **eBPF-based telemetry** for fine-grained CPU monitoring per slice
- **XDP rate limiting** for early packet filtering at NIC ingress
- **PID controller** for closed-loop CPU target maintenance
- **gRPC communication** between data plane and control plane

## Repository Structure

```
csrm-repo/
├── gRPC_o/                 # Data Plane Agent (runs on OVS host)
│   ├── gRPC_o.py           # Main gRPC server with eBPF/XDP
│   ├── ovs_cpu_full.bpf.c  # eBPF program for CPU measurement
│   ├── ovs_monitor.proto   # gRPC protocol definitions
│   └── README.md           # Data plane documentation
│
├── CSRM/                   # Control Plane Client
│   ├── pid_controller.py   # PID controller for CPU regulation
│   ├── slice_limit_api.py  # CLI/API for slice management
│   ├── slice_config.json   # Slice configuration
│   └── README.md           # Control plane documentation
│
└── README.md               # This file
```

## Quick Start

### 1. Start the Data Plane Agent (on OVS host)

```bash
cd gRPC_o
sudo python3 gRPC_o.py
```

### 2. Start the PID Controller (on control host)

```bash
cd CSRM
python3 pid_controller.py ovs-1 3  # 3% CPU target for ovs-1
```

### 3. Manual Control (optional)

```bash
cd CSRM
python3 slice_limit_api.py
> set ovs-1 cpu 3
> get ovs-1
> quit
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Control Plane                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    CSRM Client                          │    │
│  │  ┌─────────────────┐    ┌─────────────────────────┐     │    │
│  │  │  PID Controller │    │    Slice Limit API      │     │    │
│  │  │  (closed-loop)  │    │    (manual control)     │     │    │
│  │  └────────┬────────┘    └────────────┬────────────┘     │    │
│  │           └──────────────────────────┘                  │    │
│  └──────────────────────────┬──────────────────────────────┘    │
└─────────────────────────────┼───────────────────────────────────┘
                              │ gRPC (port 50051)
┌─────────────────────────────┼───────────────────────────────────┐
│                         Data Plane                              │
│  ┌──────────────────────────┴──────────────────────────────┐    │
│  │                    gRPC_o Server                        │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │    │
│  │  │ eBPF Probes │  │ XDP Limiter │  │ gRPC Service    │  │    │
│  │  │ (CPU time)  │  │ (token bucket)│ │ (metrics/ctrl) │  │    │
│  │  └──────┬──────┘  └──────┬──────┘  └─────────────────┘  │    │
│  └─────────┼────────────────┼──────────────────────────────┘    │
│            │                │                                   │
│     ┌──────┴────────────────┴──────┐                            │
│     │     Open vSwitch Dataplane   │                            │
│     │  ┌─────────┐    ┌─────────┐  │                            │
│     │  │  OVS-1  │    │  OVS-2  │  │                            │
│     │  │ (slice) │    │ (slice) │  │                            │
│     │  └─────────┘    └─────────┘  │                            │
│     └──────────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Per-slice CPU monitoring** | eBPF probes track CPU time per OVS instance |
| **XDP rate limiting** | Token bucket at NIC ingress (~1-3 μs per packet) |
| **PID control** | Closed-loop maintains CPU below target |
| **Multi-tenant isolation** | Independent limits per slice |
| **Real-time telemetry** | gRPC streaming for live metrics |

## Performance

In our KVM/virtio-net testbed:

- **XDP processing**: ~1-3 μs per packet
- **Control interval**: 100-500 ms
- **CPU target accuracy**: Maintains below target (e.g., 1.58% for 3% target)
- **Slice isolation**: 3.5×-32× loss difference between limited/unlimited slices

## Requirements

- Linux kernel 5.4+ (for eBPF/XDP support)
- Python 3.8+
- BCC (BPF Compiler Collection)
- Open vSwitch 2.13+
- gRPC Python libraries

## Citation

If you use this code in your research, please cite:

```bibtex
@article{bisevac2026csrm,
  title={CPU-aware Traffic Control for SDN Dataplanes using eBPF/XDP and PID Control},
  author={Biševac, Stefan and Bojović, Živko and Bojović, Petar and Doknić, Ilija},
  journal={Applied Sciences},
  year={2026}
}
```

## License

MIT License
