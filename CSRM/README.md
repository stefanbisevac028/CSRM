# CSRM - CPU-aware Slice Resource Manager

Client-side components for CPU-aware traffic control in SDN environments with OVS dataplanes.

## Overview

This component provides:
- **PID Controller** for closed-loop CPU regulation per slice
- **Slice Limit API** for setting CPU/bandwidth limits via gRPC
- **Configuration management** for slice definitions

## Files

| File | Description |
|------|-------------|
| `pid_controller.py` | PID controller for automatic CPU target maintenance |
| `slice_limit_api.py` | CLI and API for manual slice limit control |
| `slice_config.json` | Slice configuration (IP mappings, defaults) |
| `ovs_monitor.proto` | gRPC protocol buffer definitions |
| `ovs_monitor_pb2.py` | Generated Python protobuf classes |
| `ovs_monitor_pb2_grpc.py` | Generated gRPC service stubs |

## Prerequisites

```bash
# Install dependencies
pip3 install grpcio grpcio-tools
```

## Usage

### PID Controller (Automatic CPU Control)

The PID controller automatically adjusts XDP rate limits to maintain a target CPU utilization.

```bash
# Start PID controller for ovs-1 with 3% CPU target
python3 pid_controller.py ovs-1 3

# Start PID controller for ovs-2 with 5% CPU target
python3 pid_controller.py ovs-2 5
```

#### PID Parameters

Edit `pid_controller.py` to tune the controller:

```python
MIN_PPS = 1000              # Minimum packets per second
MAX_PHYSICAL_PPS = 2000000  # Maximum PPS limit
CONTROL_INTERVAL = 0.5      # Control loop interval (seconds)
SMOOTHING_WINDOW = 5        # Number of samples for smoothing
DEAD_ZONE = 0.5             # Dead zone around target (±% CPU)
```

#### Programmatic Usage

```python
from pid_controller import PidController

# Create controller
controller = PidController("ovs-1", target_cpu=3.0)

# Start background control loop
controller.start()

# Change target at runtime
controller.set_target(5.0)

# Stop controller
controller.stop()
```

### Slice Limit API (Manual Control)

Interactive CLI for manual slice limit management.

```bash
# Start interactive CLI
python3 slice_limit_api.py
```

#### CLI Commands

```
> set ovs-1 cpu 3        # Set 3% CPU limit on ovs-1
> set ovs-2 bw 100       # Set 100 Mbps bandwidth limit on ovs-2
> get ovs-1              # Get current limit for ovs-1
> delete ovs-1           # Remove limit from ovs-1
> list                   # List all active limits
> help                   # Show help
> quit                   # Exit
```

#### Programmatic Usage

```python
from slice_limit_api import set_cpu_limit, set_bandwidth_limit, delete_limit, get_limit

# Set CPU limit (3% CPU target)
set_cpu_limit("ovs-1", 3)

# Set bandwidth limit (100 Mbps)
set_bandwidth_limit("ovs-1", tx_mbps=100, rx_mbps=100)

# Get current limit
limit = get_limit("ovs-1")
print(f"Current limit: {limit}")

# Remove limit
delete_limit("ovs-1")
```

### Configuration

Edit `slice_config.json` to define slice mappings:

```json
{
  "slices": {
    "ovs-1": {
      "veth": "veth-phy1",
      "test_ns": "test-1",
      "ip_range": "10.0.1.0/24"
    },
    "ovs-2": {
      "veth": "veth-phy2", 
      "test_ns": "test-2",
      "ip_range": "10.0.2.0/24"
    }
  },
  "server": "10.100.70.101:50051"
}
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      CSRM Client                        │
│  ┌─────────────────┐       ┌─────────────────────────┐  │
│  │  PID Controller │       │    Slice Limit API      │  │
│  │  (auto control) │       │    (manual control)     │  │
│  └────────┬────────┘       └────────────┬────────────┘  │
│           │                             │               │
│           └──────────┬──────────────────┘               │
│                      │ gRPC                             │
└──────────────────────┼──────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  gRPC_o Server  │
              │  (Data Plane)   │
              └─────────────────┘
```

## Control Loop

The PID controller implements the following control loop:

1. **Measure**: Read current CPU% from gRPC server
2. **Compare**: Calculate error = target_cpu - current_cpu
3. **Compute**: PID output = Kp*error + Ki*integral + Kd*derivative
4. **Actuate**: Adjust XDP PPS limit based on PID output
5. **Repeat**: Every CONTROL_INTERVAL seconds

## License

MIT License
