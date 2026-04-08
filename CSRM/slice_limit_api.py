#!/usr/bin/env python3
"""
API for live control of CPU/bandwidth limits on OVS slices.
Used without traffic interruption - tc qdisc is atomically replaced.

Usage examples:
    # Set CPU limit to 10% for ovs-1
    set_cpu_limit("ovs-1", 10)
    
    # Set bandwidth limit to 100 Mbps
    set_bandwidth_limit("ovs-1", tx_mbps=100, rx_mbps=100)
    
    # Delete limit
    delete_limit("ovs-1")
    
    # Get current limit
    get_limit("ovs-1")
    
    # Interactive CLI
    python3 slice_limit_api.py
"""
import grpc
import sys
import ovs_monitor_pb2
import ovs_monitor_pb2_grpc

SERVER = "10.100.70.101:50051"

# Global stub (lazy init)
_channel = None
_stub = None

def _get_stub():
    global _channel, _stub
    if _stub is None:
        _channel = grpc.insecure_channel(SERVER)
        _stub = ovs_monitor_pb2_grpc.OvsMonitorStub(_channel)
    return _stub


def set_cpu_limit(slice_id, cpu_percent):
    """
    Set CPU limit for slice.
    CPU% is converted to bandwidth limit (10% CPU ~ 100 Mbps for 1Gbps link).
    
    Args:
        slice_id: "ovs-1" or "ovs-2"
        cpu_percent: 1-100
    
    Returns:
        (success, message, current_limit)
    """
    stub = _get_stub()
    req = ovs_monitor_pb2.SetSliceLimitRequest(
        slice_id=slice_id,
        action=ovs_monitor_pb2.SET,
        cpu_percent_limit=float(cpu_percent)
    )
    resp = stub.SetSliceLimit(req)
    
    current = None
    if resp.current_limit.slice_id:
        current = {
            "tx_mbps": resp.current_limit.nic_tx_limit_mbps,
            "rx_mbps": resp.current_limit.nic_rx_limit_mbps,
            "pkt_rate": resp.current_limit.pkt_rate_limit,
            "cpu_percent": resp.current_limit.cpu_percent_limit
        }
    
    return resp.success, resp.message, current


def set_bandwidth_limit(slice_id, tx_mbps=0, rx_mbps=0, pkt_rate=0):
    """
    Set direct bandwidth limit for slice.
    
    Args:
        slice_id: "ovs-1" or "ovs-2"
        tx_mbps: TX limit in Mbps (egress from OVS)
        rx_mbps: RX limit in Mbps (ingress to OVS)
        pkt_rate: Packet rate limit (packets/sec)
    
    Returns:
        (success, message, current_limit)
    """
    stub = _get_stub()
    req = ovs_monitor_pb2.SetSliceLimitRequest(
        slice_id=slice_id,
        action=ovs_monitor_pb2.SET,
        nic_tx_limit_mbps=float(tx_mbps),
        nic_rx_limit_mbps=float(rx_mbps),
        pkt_rate_limit=int(pkt_rate)
    )
    resp = stub.SetSliceLimit(req)
    
    current = None
    if resp.current_limit.slice_id:
        current = {
            "tx_mbps": resp.current_limit.nic_tx_limit_mbps,
            "rx_mbps": resp.current_limit.nic_rx_limit_mbps,
            "pkt_rate": resp.current_limit.pkt_rate_limit,
            "cpu_percent": resp.current_limit.cpu_percent_limit
        }
    
    return resp.success, resp.message, current


def delete_limit(slice_id):
    """
    Delete limit for slice (remove tc qdisc).
    
    Args:
        slice_id: "ovs-1" or "ovs-2"
    
    Returns:
        (success, message)
    """
    stub = _get_stub()
    req = ovs_monitor_pb2.SetSliceLimitRequest(
        slice_id=slice_id,
        action=ovs_monitor_pb2.DELETE
    )
    resp = stub.SetSliceLimit(req)
    return resp.success, resp.message


def get_limit(slice_id):
    """
    Get current limit for slice.
    
    Args:
        slice_id: "ovs-1" or "ovs-2"
    
    Returns:
        (success, message, current_limit or None)
    """
    stub = _get_stub()
    req = ovs_monitor_pb2.SetSliceLimitRequest(
        slice_id=slice_id,
        action=ovs_monitor_pb2.GET
    )
    resp = stub.SetSliceLimit(req)
    
    current = None
    if resp.current_limit.slice_id:
        current = {
            "tx_mbps": resp.current_limit.nic_tx_limit_mbps,
            "rx_mbps": resp.current_limit.nic_rx_limit_mbps,
            "pkt_rate": resp.current_limit.pkt_rate_limit,
            "cpu_percent": resp.current_limit.cpu_percent_limit
        }
    
    return resp.success, resp.message, current


def set_cpu_coefficient(slice_id, coefficient):
    """
    Set CPU-throughput coefficient for slice.
    
    Args:
        slice_id: "ovs-1" or "ovs-2"
        coefficient: CPU% per Mbps (e.g., 0.03 means 1 Gbps = 30% CPU)
    
    Returns:
        (success, message)
    """
    channel = grpc.insecure_channel(SERVER)
    stub = ovs_monitor_pb2_grpc.OvsMonitorStub(channel)
    
    try:
        req = ovs_monitor_pb2.SetSliceLimitRequest(
            slice_id=slice_id,
            action=ovs_monitor_pb2.SET,
            cpu_coefficient=coefficient
        )
        resp = stub.SetSliceLimit(req)
        return resp.success, f"CPU coefficient set to {coefficient} (1 Gbps = {coefficient*1000:.0f}% CPU)"
    except Exception as e:
        return False, f"Error: {e}"


def calibrate_slice(slice_id, duration=5):
    """
    Automatically calibrate CPU-throughput coefficient for slice.
    IMPORTANT: Iperf must be running at full speed WITHOUT limits!
    
    Args:
        slice_id: "ovs-1" or "ovs-2"
        duration: calibration duration in seconds
    
    Returns:
        (success, message, result_dict)
    """
    import time
    
    channel = grpc.insecure_channel(SERVER)
    stub = ovs_monitor_pb2_grpc.OvsMonitorStub(channel)
    
    # Mapping slice -> veth
    veth_map = {"ovs-1": "veth-phy1", "ovs-2": "veth-phy2"}
    veth = veth_map.get(slice_id)
    if not veth:
        return False, f"Unknown slice: {slice_id}", None
    
    samples = []
    
    for i in range(duration * 2):
        time.sleep(0.5)
        
        try:
            # Get metrics from server
            req = ovs_monitor_pb2.OvsRequest()
            resp = stub.GetMetrics(req)
            
            # Get OVS CPU
            ovs_cpu = 0
            for ns in resp.metrics.namespaces:
                if ns.name == slice_id:
                    ovs_cpu = ns.cpu_kernel
                    break
            
            # Get throughput from NIC statistics (server side)
            throughput = 0
            for nic in resp.metrics.nics:
                # Proto field is 'iface', but Python generates it as attribute
                nic_name = getattr(nic, 'iface', '') or getattr(nic, 'name', '')
                if nic_name == veth:
                    # rx_mbps + tx_mbps gives total throughput
                    throughput = nic.rx_mbps + nic.tx_mbps
                    break
            
            if throughput > 10:  # Ignore if no traffic
                samples.append((throughput, ovs_cpu))
                
        except Exception as e:
            pass
    
    if len(samples) < 3:
        return False, "Not enough samples. Is iperf running?", None
    
    avg_throughput = sum(s[0] for s in samples) / len(samples)
    avg_cpu = sum(s[1] for s in samples) / len(samples)
    
    if avg_throughput < 10:
        return False, f"Throughput too low: {avg_throughput:.0f}Mbps", None
    
    if avg_cpu < 0.1:
        return False, f"OVS CPU too low: {avg_cpu:.1f}%. Is BPF running?", None
    
    coefficient = avg_cpu / avg_throughput
    
    # Set coefficient through gRPC
    set_cpu_coefficient(slice_id, coefficient)
    
    return True, "Calibration successful", {
        "throughput": avg_throughput,
        "cpu": avg_cpu,
        "coefficient": coefficient
    }


def update_limit(slice_id, cpu_percent=None, tx_mbps=None, rx_mbps=None, pkt_rate=None):
    """
    Update existing limit (merge with current).
    
    Args:
        slice_id: "ovs-1" or "ovs-2"
        cpu_percent: new CPU% limit (or None to keep)
        tx_mbps: new TX limit (or None to keep)
        rx_mbps: new RX limit (or None to keep)
        pkt_rate: new packet rate (or None to keep)
    
    Returns:
        (success, message, current_limit)
    """
    # Get current limit
    _, _, current = get_limit(slice_id)
    
    # Merge with new values
    new_cpu = cpu_percent if cpu_percent is not None else (current.get("cpu_percent", 0) if current else 0)
    new_tx = tx_mbps if tx_mbps is not None else (current.get("tx_mbps", 0) if current else 0)
    new_rx = rx_mbps if rx_mbps is not None else (current.get("rx_mbps", 0) if current else 0)
    new_pkt = pkt_rate if pkt_rate is not None else (current.get("pkt_rate", 0) if current else 0)
    
    # Set new limit
    stub = _get_stub()
    req = ovs_monitor_pb2.SetSliceLimitRequest(
        slice_id=slice_id,
        action=ovs_monitor_pb2.SET,
        cpu_percent_limit=float(new_cpu),
        nic_tx_limit_mbps=float(new_tx),
        nic_rx_limit_mbps=float(new_rx),
        pkt_rate_limit=int(new_pkt)
    )
    resp = stub.SetSliceLimit(req)
    
    updated = None
    if resp.current_limit.slice_id:
        updated = {
            "tx_mbps": resp.current_limit.nic_tx_limit_mbps,
            "rx_mbps": resp.current_limit.nic_rx_limit_mbps,
            "pkt_rate": resp.current_limit.pkt_rate_limit,
            "cpu_percent": resp.current_limit.cpu_percent_limit
        }
    
    return resp.success, resp.message, updated


# ============== CLI ==============
def print_help():
    print("""
Slice Limit API - Live control of CPU/bandwidth limits

Commands:
  cpu <slice_id> <percent>     - Set CPU limit (e.g.: cpu ovs-1 10)
  bw <slice_id> <tx> [rx]      - Set bandwidth limit in Mbps
  pps <slice_id> <rate>        - Set packet rate limit
  coef <slice_id> <value>      - Set CPU-throughput coefficient
                                 (e.g.: coef ovs-1 0.05 means 1 Gbps = 50% CPU)
  calibrate <slice_id> [sec]   - Automatically calibrate coefficient
                                 (run iperf at full speed WITHOUT limits!)
  del <slice_id>               - Delete limit
  get <slice_id>               - Show current limit
  get all                      - Show all limits
  help                         - Show help
  quit                         - Exit

Examples:
  cpu ovs-1 10                 - ovs-1 doesn't exceed 10% CPU
  bw ovs-1 100 100             - ovs-1 limited to 100 Mbps TX/RX
  del ovs-1                    - remove limit from ovs-1
""")


def cli_loop():
    print("Slice Limit API - Live control without traffic interruption")
    print("Enter 'help' for help\n")
    
    while True:
        try:
            line = input("limit> ").strip()
            if not line:
                continue
            
            parts = line.split()
            cmd = parts[0].lower()
            
            if cmd == "help":
                print_help()
                
            elif cmd == "quit" or cmd == "exit" or cmd == "q":
                print("Exiting...")
                break
                
            elif cmd == "cpu" and len(parts) >= 3:
                slice_id = parts[1]
                cpu_pct = float(parts[2])
                success, msg, current = set_cpu_limit(slice_id, cpu_pct)
                print(f"{'OK' if success else 'FAIL'}: {msg}")
                if current:
                    if 'XDP IP' in msg:
                        print(f"  XDP IP-BASED CONTROL: target CPU={current.get('cpu_percent', cpu_pct):.1f}%")
                        print(f"  (rate limiting by learned IP addresses, per-slice isolation)")
                    elif current.get('proactive') or 'Proactive' in msg:
                        print(f"  PROACTIVE CONTROL: target CPU={current.get('cpu_percent', cpu_pct):.1f}%")
                        print(f"  (bandwidth is dynamically adjusted to maintain CPU around target)")
                    else:
                        print(f"  Active limit: TX={current.get('tx_mbps', 0):.1f}Mbps, "
                              f"RX={current.get('rx_mbps', 0):.1f}Mbps, CPU={current.get('cpu_percent', 0):.1f}%")
                
            elif cmd == "bw" and len(parts) >= 3:
                slice_id = parts[1]
                tx = float(parts[2])
                rx = float(parts[3]) if len(parts) > 3 else tx
                success, msg, current = set_bandwidth_limit(slice_id, tx_mbps=tx, rx_mbps=rx)
                print(f"{'OK' if success else 'FAIL'}: {msg}")
                if current:
                    print(f"  Active limit: TX={current['tx_mbps']:.1f}Mbps, RX={current['rx_mbps']:.1f}Mbps")
                
            elif cmd == "pps" and len(parts) >= 3:
                slice_id = parts[1]
                pps = int(parts[2])
                success, msg, current = set_bandwidth_limit(slice_id, pkt_rate=pps)
                print(f"{'OK' if success else 'FAIL'}: {msg}")
                if current:
                    print(f"  Active limit: PPS={current['pkt_rate']}")
                
            elif cmd == "del" and len(parts) >= 2:
                slice_id = parts[1]
                success, msg = delete_limit(slice_id)
                print(f"{'OK' if success else 'FAIL'}: {msg}")
                
            elif cmd == "coef" and len(parts) >= 3:
                # Set CPU-throughput coefficient for slice
                # Example: coef ovs-1 0.05 (1 Gbps = 50% CPU)
                slice_id = parts[1]
                coefficient = float(parts[2])
                success, msg = set_cpu_coefficient(slice_id, coefficient)
                print(f"{'OK' if success else 'FAIL'}: {msg}")
                
            elif cmd == "calibrate" and len(parts) >= 2:
                # Automatic coefficient calibration
                # IMPORTANT: Run iperf at full speed WITHOUT limits before calibration!
                slice_id = parts[1]
                duration = int(parts[2]) if len(parts) > 2 else 5
                print(f"Calibrating {slice_id} ({duration}s)... Make sure iperf is running at full speed!")
                success, msg, result = calibrate_slice(slice_id, duration)
                print(f"{'OK' if success else 'FAIL'}: {msg}")
                if result:
                    print(f"  Throughput: {result['throughput']:.0f} Mbps")
                    print(f"  OVS CPU: {result['cpu']:.1f}%")
                    print(f"  Coefficient: {result['coefficient']:.6f}")
                    print(f"  (1 Gbps = {result['coefficient']*1000:.0f}% CPU)")
                
            elif cmd == "get":
                if len(parts) < 2 or parts[1] == "all":
                    for sid in ["ovs-1", "ovs-2"]:
                        success, msg, current = get_limit(sid)
                        if current:
                            if current.get('proactive'):
                                bw = current.get('current_bandwidth', '?')
                                print(f"{sid}: PROACTIVE target={current['cpu_percent']:.1f}%, current_bw={bw}Mbps")
                            else:
                                print(f"{sid}: TX={current['tx_mbps']:.1f}Mbps, "
                                      f"RX={current['rx_mbps']:.1f}Mbps, "
                                      f"CPU={current['cpu_percent']:.1f}%, "
                                      f"PPS={current['pkt_rate']}")
                        else:
                            print(f"{sid}: no limit")
                else:
                    slice_id = parts[1]
                    success, msg, current = get_limit(slice_id)
                    print(f"{msg}")
                    if current:
                        if current.get('proactive'):
                            bw = current.get('current_bandwidth', '?')
                            print(f"  PROACTIVE CONTROL: target={current['cpu_percent']:.1f}%")
                            print(f"  Current bandwidth: {bw}Mbps (dynamic)")
                        else:
                            print(f"  TX={current['tx_mbps']:.1f}Mbps, "
                                  f"RX={current['rx_mbps']:.1f}Mbps, "
                                  f"CPU={current['cpu_percent']:.1f}%, "
                                  f"PPS={current['pkt_rate']}")
            else:
                print("Unknown command. Enter 'help' for help.")
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except grpc.RpcError as e:
            print(f"gRPC error: {e.details()}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line
        cmd = sys.argv[1].lower()
        if cmd == "cpu" and len(sys.argv) >= 4:
            success, msg, _ = set_cpu_limit(sys.argv[2], float(sys.argv[3]))
            print(f"{'OK' if success else 'FAIL'}: {msg}")
        elif cmd == "bw" and len(sys.argv) >= 4:
            tx = float(sys.argv[3])
            rx = float(sys.argv[4]) if len(sys.argv) > 4 else tx
            success, msg, _ = set_bandwidth_limit(sys.argv[2], tx_mbps=tx, rx_mbps=rx)
            print(f"{'OK' if success else 'FAIL'}: {msg}")
        elif cmd == "del" and len(sys.argv) >= 3:
            success, msg = delete_limit(sys.argv[2])
            print(f"{'OK' if success else 'FAIL'}: {msg}")
        elif cmd == "get":
            slice_id = sys.argv[2] if len(sys.argv) > 2 else "all"
            if slice_id == "all":
                for sid in ["ovs-1", "ovs-2"]:
                    _, _, current = get_limit(sid)
                    if current:
                        print(f"{sid}: TX={current['tx_mbps']:.1f}, RX={current['rx_mbps']:.1f}, CPU={current['cpu_percent']:.1f}%")
                    else:
                        print(f"{sid}: no limit")
            else:
                _, msg, current = get_limit(slice_id)
                print(msg)
        else:
            print("Usage: slice_limit_api.py <cpu|bw|del|get> <slice_id> [args...]")
    else:
        cli_loop()
