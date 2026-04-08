# gRPC OVS Monitor Server

gRPC server for real-time OVS (Open vSwitch) monitoring with eBPF-based CPU telemetry and XDP rate limiting.

## Overview

This component provides:
- **Real-time CPU monitoring** per OVS slice using eBPF probes
- **XDP-based rate limiting** with token bucket algorithm
- **gRPC API** for remote monitoring and control
- **Per-slice telemetry** including CPU%, packet rates, and bandwidth

## Files

| File | Description |
|------|-------------|
| `gRPC_o.py` | Main gRPC server with eBPF monitoring and XDP rate limiting |
| `ovs_cpu_full.bpf.c` | eBPF program for CPU time measurement |
| `ovs_monitor.proto` | gRPC protocol buffer definitions |
| `ovs_monitor_pb2.py` | Generated Python protobuf classes |
| `ovs_monitor_pb2_grpc.py` | Generated gRPC service stubs |
| `generate_proto.sh` | Script to regenerate protobuf files |
| `start_server.sh` | Script to start the gRPC server |

## Prerequisites

```bash
# Install dependencies
pip3 install grpcio grpcio-tools psutil bcc

# BCC (BPF Compiler Collection) must be installed
# Ubuntu/Debian:
sudo apt install bpfcc-tools python3-bpfcc
```

## Usage

### Start the gRPC Server

```bash
# Run as root (required for eBPF)
sudo python3 gRPC_o.py
```

The server listens on port `50051` by default.

### Configuration

Edit the configuration section in `gRPC_o.py`:

```python
INTERVAL = 1.0                    # Monitoring interval (seconds)
OVS_NAMESPACES = ["ovs-1", "ovs-2"]  # OVS namespace names
UPLINK_IFACE = "ens19"            # Physical uplink interface
```

### gRPC API

The server exposes the following RPC methods:

| Method | Description |
|--------|-------------|
| `StreamMetrics` | Stream real-time metrics for all slices |
| `GetMetrics` | Get current metrics snapshot |
| `SetSliceLimit` | Set CPU/bandwidth limit for a slice |
| `RemoveSliceLimit` | Remove limit from a slice |
| `GetSliceLimits` | Get current limits for all slices |

### Example Client

```python
import grpc
import ovs_monitor_pb2
import ovs_monitor_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = ovs_monitor_pb2_grpc.OvsMonitorStub(channel)

# Stream metrics
for metrics in stub.StreamMetrics(ovs_monitor_pb2.Empty()):
    print(f"Slice: {metrics.slice_id}, CPU: {metrics.cpu_percent}%")
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    gRPC Server                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ eBPF Probes │  │ XDP Limiter │  │ gRPC Service    │  │
│  │ (CPU time)  │  │ (token bucket)│ │ (StreamMetrics) │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
│         │                │                   │          │
│         └────────────────┴───────────────────┘          │
│                          │                              │
└──────────────────────────┼──────────────────────────────┘
                           │ gRPC (port 50051)
                           ▼
                    ┌──────────────┐
                    │ CSRM Client  │
                    │ (PID Control)│
                    └──────────────┘
```

## License

MIT License
