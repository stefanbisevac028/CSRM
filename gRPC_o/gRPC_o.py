#!/usr/bin/env python3
"""
gRPC OVS Monitor - Final version with complete CPU measurement.

Measures CPU time through all packet processing phases:
  - ovs_dp_process_packet (OVS datapath)
  - veth_xmit (veth transfer)
  - netif_receive_skb (network stack receive)
  - dev_queue_xmit (device transmit)

Additionally uses cgroups for precise measurement if available.
"""
import os
import time
import subprocess
import socket
from collections import defaultdict
from concurrent import futures

import grpc
import psutil

import ovs_monitor_pb2
import ovs_monitor_pb2_grpc

# ---------------- CONFIG ----------------
INTERVAL = 1.0
OVS_NAMESPACES = ["ovs-1", "ovs-2"]
TEST_NAMESPACES = ["test-1", "test-2"]  # Test namespaces with iperf servers
ALL_NAMESPACES = OVS_NAMESPACES + TEST_NAMESPACES
FILTER_IFACES = None
BPF_SRC = "ovs_cpu_full.bpf.c"  # Extended measurement (ovs + veth + netif)

SLICE_VETH_MAP = {
    "ovs-1": "veth-phy1",
    "ovs-2": "veth-phy2",
}

# Mapping test namespaces to their veth interfaces (host side)
# These interfaces are inside OVS namespace, connected to test namespace
TEST_VETH_MAP = {
    "test-1": "veth-test1",  # ifindex 13 on host side (peer of ifindex 14 in test-1)
    "test-2": "veth-test2",  # ifindex 15 on host side (peer of ifindex 16 in test-2)
}
UPLINK_IFACE = "ens19"

import threading
active_slice_limits = {}
active_limits_lock = threading.Lock()

MAX_PHYSICAL_MBPS = 20000  # Physical limit of VM link (~20 Gbps)

# Proactive PID controllers
from pid_controller import PidController

active_pid_controllers = {}  # {slice_id: PidController}
pid_controllers_lock = threading.Lock()

# Saved CPU-PPS coefficients per-slice (survive controller restart)
# Format: {slice_id: coefficient}
# coefficient = CPU% per packet (e.g., 0.000084 means 83K pps = 7% CPU)
saved_cpu_coefficients = {}

# XDP Rate Limiter - integrated into server for BPF map access
import json
import socket
import struct

XDP_RATE_LIMIT_SRC = """
#include <uapi/linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/in.h>

struct rate_limit_entry {
    u64 rate_pps;      // Rate in packets per second
    u64 burst_pkts;    // Burst size in packets
    u64 tokens;        // Current tokens (packets)
    u64 last_update;   // Last update timestamp (ns)
};

// Rate limits by destination IP
BPF_HASH(xdp_rate_limits, u32, struct rate_limit_entry, 256);

// Statistics - drops and passes by IP (packet count)
BPF_HASH(xdp_drop_stats, u32, u64, 256);
BPF_HASH(xdp_pass_stats, u32, u64, 256);

// Byte statistics - for accurate throughput per slice
BPF_HASH(xdp_drop_bytes, u32, u64, 256);
BPF_HASH(xdp_pass_bytes, u32, u64, 256);

// Debug: counter of all packets and packets with limit
BPF_HASH(xdp_debug_total, u32, u64, 1);
BPF_HASH(xdp_debug_limited, u32, u64, 1);

int xdp_rate_limit(struct xdp_md *ctx)
{
    void *data_end = (void *)(long)ctx->data_end;
    void *data = (void *)(long)ctx->data;
    
    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end)
        return XDP_PASS;
    
    if (eth->h_proto != __constant_htons(ETH_P_IP))
        return XDP_PASS;
    
    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end)
        return XDP_PASS;
    
    // Debug: count all IP packets
    u32 zero = 0;
    u64 *total = xdp_debug_total.lookup(&zero);
    if (total) (*total)++;
    else { u64 one = 1; xdp_debug_total.update(&zero, &one); }
    
    u32 dst_ip = ip->daddr;
    struct rate_limit_entry *entry = xdp_rate_limits.lookup(&dst_ip);
    if (!entry)
        return XDP_PASS;
    
    // Debug: count packets that have limit
    u64 *limited = xdp_debug_limited.lookup(&zero);
    if (limited) (*limited)++;
    else { u64 one = 1; xdp_debug_limited.update(&zero, &one); }
    
    u64 now = bpf_ktime_get_ns();
    u64 elapsed = now - entry->last_update;
    u64 pkt_len = data_end - data;
    
    // Token bucket - PPS based (1 token = 1 packet)
    // new_tokens = tokens + (elapsed_ns * rate_pps / 1e9)
    u64 new_tokens = entry->tokens + (elapsed * entry->rate_pps / 1000000000ULL);
    if (new_tokens > entry->burst_pkts)
        new_tokens = entry->burst_pkts;
    
    if (new_tokens >= 1) {
        entry->tokens = new_tokens - 1;  // 1 token per packet
        entry->last_update = now;
        
        // Packet count
        u64 *passes = xdp_pass_stats.lookup(&dst_ip);
        if (passes) (*passes)++;
        else { u64 one = 1; xdp_pass_stats.update(&dst_ip, &one); }
        
        // Byte count for throughput metric
        u64 *pass_b = xdp_pass_bytes.lookup(&dst_ip);
        if (pass_b) (*pass_b) += pkt_len;
        else { xdp_pass_bytes.update(&dst_ip, &pkt_len); }
        
        return XDP_PASS;
    }
    
    // Drop
    entry->tokens = new_tokens;
    entry->last_update = now;
    
    // Packet count
    u64 *drops = xdp_drop_stats.lookup(&dst_ip);
    if (drops) (*drops)++;
    else { u64 one = 1; xdp_drop_stats.update(&dst_ip, &one); }
    
    // Byte count for throughput metric
    u64 *drop_b = xdp_drop_bytes.lookup(&dst_ip);
    if (drop_b) (*drop_b) += pkt_len;
    else { xdp_drop_bytes.update(&dst_ip, &pkt_len); }
    
    return XDP_DROP;
}
"""

# XDP global variables
xdp_bpf = None
xdp_attached = False
xdp_rate_limits_map = None
xdp_drop_stats_map = None
xdp_pass_stats_map = None
xdp_drop_bytes_map = None
xdp_pass_bytes_map = None

def load_slice_config():
    """Load slice_config.json"""
    config_path = os.path.join(os.path.dirname(__file__), "slice_config.json")
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except:
        return None

def get_slice_ips(slice_id):
    """Get IP addresses for slice from config file"""
    config = load_slice_config()
    if not config:
        return []
    return config.get("slices", {}).get(slice_id, {}).get("ips", [])

def attach_xdp_rate_limiter():
    """Attach XDP rate limiter to ens19"""
    global xdp_bpf, xdp_attached, xdp_rate_limits_map, xdp_drop_stats_map, xdp_pass_stats_map
    global xdp_drop_bytes_map, xdp_pass_bytes_map
    
    if xdp_attached:
        return True
    
    try:
        xdp_bpf = BPF(text=XDP_RATE_LIMIT_SRC)
        fn = xdp_bpf.load_func("xdp_rate_limit", BPF.XDP)
        xdp_bpf.attach_xdp(UPLINK_IFACE, fn, 0)
        
        xdp_rate_limits_map = xdp_bpf.get_table("xdp_rate_limits")
        xdp_drop_stats_map = xdp_bpf.get_table("xdp_drop_stats")
        xdp_pass_stats_map = xdp_bpf.get_table("xdp_pass_stats")
        xdp_drop_bytes_map = xdp_bpf.get_table("xdp_drop_bytes")
        xdp_pass_bytes_map = xdp_bpf.get_table("xdp_pass_bytes")
        
        xdp_attached = True
        print(f"XDP rate limiter attached to {UPLINK_IFACE}")
        return True
    except Exception as e:
        print(f"Failed to attach XDP: {e}")
        return False

def detach_xdp_rate_limiter():
    """Detach XDP rate limiter"""
    global xdp_bpf, xdp_attached
    
    if xdp_bpf and xdp_attached:
        try:
            xdp_bpf.remove_xdp(UPLINK_IFACE, 0)
            xdp_attached = False
            print(f"XDP rate limiter detached from {UPLINK_IFACE}")
        except:
            pass

def set_xdp_rate_limit(ip_addr, rate_pps, burst_pkts=1000):
    """Set XDP rate limit for IP address (PPS - packets per second)"""
    global xdp_rate_limits_map
    
    if not xdp_attached:
        if not attach_xdp_rate_limiter():
            return False
    
    # ip->daddr in XDP is __be32 (network byte order in memory)
    # But on x86, when BPF reads u32 from memory, it uses little-endian
    # So key must be little-endian interpretation of IP bytes
    ip_bytes = socket.inet_aton(ip_addr)
    ip_int = struct.unpack('<I', ip_bytes)[0]  # Little-endian!
    print(f"DEBUG: Setting XDP limit for {ip_addr} -> key={ip_int} (0x{ip_int:08x}), rate={rate_pps} pps")
    
    key = xdp_rate_limits_map.Key(ip_int)
    val = xdp_rate_limits_map.Leaf()
    val.rate_pps = int(rate_pps)
    val.burst_pkts = int(burst_pkts)
    val.tokens = val.burst_pkts
    val.last_update = 0
    
    xdp_rate_limits_map[key] = val
    return True

def remove_xdp_rate_limit(ip_addr):
    """Remove XDP rate limit for IP address"""
    global xdp_rate_limits_map
    
    if not xdp_rate_limits_map:
        return
    
    # Same byte order as set_xdp_rate_limit - little-endian!
    ip_bytes = socket.inet_aton(ip_addr)
    ip_int = struct.unpack('<I', ip_bytes)[0]
    key = xdp_rate_limits_map.Key(ip_int)
    
    try:
        del xdp_rate_limits_map[key]
        print(f"DEBUG: Removed XDP limit for {ip_addr} -> key={ip_int} (0x{ip_int:08x})")
    except Exception as e:
        print(f"DEBUG: Failed to remove XDP limit for {ip_addr}: {e}")

def get_xdp_drop_stats():
    """Get XDP drop statistics by IP address (packets and bytes)"""
    global xdp_drop_stats_map, xdp_pass_stats_map, xdp_drop_bytes_map, xdp_pass_bytes_map
    
    stats = {}
    if not xdp_drop_stats_map:
        return stats
    
    for k, v in xdp_drop_stats_map.items():
        # Use little-endian as in set/remove functions
        ip = socket.inet_ntoa(struct.pack("<I", k.value))
        if ip not in stats:
            stats[ip] = {"drops": 0, "passes": 0, "drop_bytes": 0, "pass_bytes": 0}
        stats[ip]["drops"] = v.value
    
    if xdp_pass_stats_map:
        for k, v in xdp_pass_stats_map.items():
            ip = socket.inet_ntoa(struct.pack("<I", k.value))
            if ip not in stats:
                stats[ip] = {"drops": 0, "passes": 0, "drop_bytes": 0, "pass_bytes": 0}
            stats[ip]["passes"] = v.value
    
    # Byte statistics for throughput metric
    if xdp_drop_bytes_map:
        for k, v in xdp_drop_bytes_map.items():
            ip = socket.inet_ntoa(struct.pack("<I", k.value))
            if ip in stats:
                stats[ip]["drop_bytes"] = v.value
    
    if xdp_pass_bytes_map:
        for k, v in xdp_pass_bytes_map.items():
            ip = socket.inet_ntoa(struct.pack("<I", k.value))
            if ip in stats:
                stats[ip]["pass_bytes"] = v.value
    
    return stats

# Previous XDP statistics for rate calculation
prev_xdp_stats = {}

def get_xdp_debug_stats():
    """Get XDP debug statistics"""
    global xdp_bpf
    if not xdp_bpf:
        return None
    
    try:
        total_map = xdp_bpf.get_table("xdp_debug_total")
        limited_map = xdp_bpf.get_table("xdp_debug_limited")
        
        total = 0
        limited = 0
        
        for k, v in total_map.items():
            total = v.value
        for k, v in limited_map.items():
            limited = v.value
        
        return {"total_pkts": total, "limited_pkts": limited}
    except:
        return None

# Initialize XDP functions in pid_controller
from pid_controller import init_xdp_functions
init_xdp_functions(set_xdp_rate_limit, remove_xdp_rate_limit, get_slice_ips)
# ---------------------------------------

# ---------------- BPF SETUP (FULL) ----------------
from bcc import BPF

bpf = BPF(src_file=BPF_SRC)

# OVS datapath
bpf.attach_kprobe(event="ovs_dp_process_packet", fn_name="trace_ovs_entry")
bpf.attach_kretprobe(event="ovs_dp_process_packet", fn_name="trace_ovs_return")

# Veth transfer
try:
    bpf.attach_kprobe(event="veth_xmit", fn_name="trace_veth_entry")
    bpf.attach_kretprobe(event="veth_xmit", fn_name="trace_veth_return")
except Exception as e:
    print(f"Warning: veth_xmit probe failed: {e}")

# Netif receive
try:
    bpf.attach_kprobe(event="netif_receive_skb", fn_name="trace_netif_entry")
    bpf.attach_kretprobe(event="netif_receive_skb", fn_name="trace_netif_return")
except Exception as e:
    print(f"Warning: netif_receive_skb probe failed: {e}")

# Dev queue xmit (often inlined, optional)
try:
    bpf.attach_kprobe(event="__dev_queue_xmit", fn_name="trace_xmit_entry")
    bpf.attach_kretprobe(event="__dev_queue_xmit", fn_name="trace_xmit_return")
except Exception:
    pass  # Optional

# BPF maps - extended measurement
cpu_map_ovs = bpf.get_table("cpu_time_ovs")
cpu_map_veth = bpf.get_table("cpu_time_veth")
cpu_map_netif = bpf.get_table("cpu_time_netif")
cpu_map_xmit = bpf.get_table("cpu_time_xmit")
cpu_map_total = bpf.get_table("cpu_time_total")

num_cpus = os.cpu_count()

# ---------------- GLOBAL STATE ----------------
prev_cpu_ovs = defaultdict(int)
prev_cpu_veth = defaultdict(int)
prev_cpu_netif = defaultdict(int)
prev_cpu_xmit = defaultdict(int)
prev_cpu_total = defaultdict(int)
prev_kernel = defaultdict(int)  # legacy compatibility
prev_user = defaultdict(int)
prev_nic = {}
prev_cgroup_cpu = {}  # for cgroups measurement

# Smoothing for CPU values (moving average)
from collections import deque
CPU_SMOOTHING_WINDOW = 5  # Number of samples for average
cpu_history = defaultdict(lambda: deque(maxlen=CPU_SMOOTHING_WINDOW))
global_cpu_history = deque(maxlen=CPU_SMOOTHING_WINDOW)

# ---------------- IFINDEX MAPPING ----------------
def build_ifindex_map():
    """
    Build mapping ifindex -> namespace/host.
    IMPORTANT: ifindex values are LOCAL per namespace, not global!
    BPF sees only HOST ifindex values, so we map only host interfaces.
    veth-phyX on host side is mapped to corresponding OVS namespace.
    """
    m = {}
    veth_to_ns = {}  # veth-phyX ifindex -> namespace
    
    # ONLY host interfaces - BPF sees only these ifindex values
    out = subprocess.check_output(["ip", "-o", "link"], text=True)
    for l in out.splitlines():
        parts = l.split(":")
        ifindex = int(parts[0])
        iface_name = parts[1].strip().split("@")[0]
        m[ifindex] = "host"
        
        # Mapping veth-phyX to namespace
        # These are host-side veth interfaces leading to OVS namespaces
        for ns, veth in SLICE_VETH_MAP.items():
            if iface_name == veth:
                veth_to_ns[ifindex] = ns
    
    # We do NOT read namespace ifindex values because BPF sees only host ifindex values
    # Namespace ifindex values are local and can overlap with host ifindex values
    
    return m, veth_to_ns

ifmap, veth_ns_map = build_ifindex_map()
print(f"ifmap: {ifmap}")
print(f"veth_ns_map: {veth_ns_map}")


# ---------------- CGROUPS CPU MEASUREMENT ----------------
def get_cgroup_cpu_usage(ns):
    """
    Get CPU usage from cgroups for namespace.
    Returns CPU time in nanoseconds.
    """
    cgroup_paths = [
        f"/sys/fs/cgroup/cpu/{ns}/cpuacct.usage",
        f"/sys/fs/cgroup/{ns}/cpu.stat",
        f"/sys/fs/cgroup/system.slice/netns-{ns}.slice/cpuacct.usage",
    ]
    
    for path in cgroup_paths:
        try:
            with open(path) as f:
                content = f.read().strip()
                if "usage_usec" in content:
                    for line in content.split("\n"):
                        if line.startswith("usage_usec"):
                            return int(line.split()[1]) * 1000  # usec -> ns
                else:
                    return int(content)
        except (FileNotFoundError, PermissionError):
            continue
    
    return None


def get_ovs_process_cpu(ns):
    """
    Get CPU time for all OVS processes in namespace.
    Tracks ovs-vswitchd (main CPU consumer) and ovsdb-server.
    """
    total_ns = 0
    hz = os.sysconf("SC_CLK_TCK")
    
    for proc_name in ["ovs-vswitchd", "ovsdb-server"]:
        try:
            out = subprocess.check_output(
                ["ip", "netns", "exec", ns, "pgrep", "-f", proc_name],
                text=True, stderr=subprocess.DEVNULL
            )
            for pid in out.split():
                try:
                    with open(f"/proc/{pid}/stat") as f:
                        d = f.read().split()
                        utime = int(d[13])
                        stime = int(d[14])
                        total_ticks = utime + stime
                        total_ns += (total_ticks * 1_000_000_000) // hz
                except (FileNotFoundError, IndexError, ProcessLookupError):
                    pass  # Process disappeared between pgrep and reading /proc
        except subprocess.CalledProcessError:
            pass
    
    return total_ns


def get_test_ns_process_cpu(ns):
    """
    Get CPU time for all processes in test namespace.
    Uses 'ip netns pids' to get PIDs that actually belong to the namespace.
    """
    total_ns = 0
    hz = os.sysconf("SC_CLK_TCK")
    
    try:
        # Get all PIDs in namespace
        out = subprocess.check_output(
            ["ip", "netns", "pids", ns],
            text=True, stderr=subprocess.DEVNULL
        )
        for pid in out.split():
            try:
                with open(f"/proc/{pid}/stat") as f:
                    d = f.read().split()
                    utime = int(d[13])
                    stime = int(d[14])
                    total_ticks = utime + stime
                    total_ns += (total_ticks * 1_000_000_000) // hz
            except (FileNotFoundError, IndexError, ProcessLookupError):
                pass
    except subprocess.CalledProcessError:
        pass
    
    return total_ns


# Global state for test namespace CPU measurement
prev_test_cpu = {}


# ---------------- TC RESOURCE CONTROL ----------------
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gRPC_o_final")

def slice_id_to_veth(slice_id):
    if slice_id in SLICE_VETH_MAP:
        return SLICE_VETH_MAP[slice_id]
    if "-" in slice_id:
        num = slice_id.split("-")[-1]
        return f"veth-phy{num}"
    return None

def apply_tc_limit(iface, tx_mbps=0, rx_mbps=0, pkt_rate=0):
    results = []
    
    if tx_mbps > 0:
        try:
            subprocess.run(["tc", "qdisc", "del", "dev", iface, "root"],
                          capture_output=True, check=False)
            subprocess.run([
                "tc", "qdisc", "add", "dev", iface, "root", "handle", "1:", "htb", "default", "10"
            ], check=True)
            subprocess.run([
                "tc", "class", "add", "dev", iface, "parent", "1:",
                "classid", "1:10", "htb", "rate", f"{tx_mbps}mbit", "ceil", f"{tx_mbps}mbit"
            ], check=True)
            subprocess.run([
                "tc", "qdisc", "add", "dev", iface, "parent", "1:10", "handle", "10:", "sfq", "perturb", "10"
            ], check=True)
            results.append(f"TX={tx_mbps}mbit")
            logger.info(f"Applied TX limit {tx_mbps}mbit on {iface}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to apply TX limit on {iface}: {e}")
            return False, str(e)
    
    if rx_mbps > 0:
        try:
            subprocess.run(["tc", "qdisc", "del", "dev", iface, "ingress"],
                          capture_output=True, check=False)
            subprocess.run([
                "tc", "qdisc", "add", "dev", iface, "handle", "ffff:", "ingress"
            ], check=True)
            rate_kbit = int(rx_mbps * 1000)
            subprocess.run([
                "tc", "filter", "add", "dev", iface, "parent", "ffff:",
                "protocol", "all", "prio", "1", "basic",
                "police", "rate", f"{rate_kbit}kbit", "burst", "64k", "drop"
            ], check=True)
            results.append(f"RX={rx_mbps}mbit")
            logger.info(f"Applied RX limit {rx_mbps}mbit on {iface}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to apply RX limit on {iface}: {e}")
            return False, str(e)
    
    if pkt_rate > 0:
        try:
            subprocess.run([
                "tc", "filter", "add", "dev", iface, "parent", "1:",
                "protocol", "all", "prio", "2", "basic",
                "police", "rate", f"{pkt_rate}pps", "burst", "1000", "drop"
            ], check=False)
            results.append(f"PPS={pkt_rate}")
            logger.info(f"Applied packet rate limit {pkt_rate}pps on {iface}")
        except Exception as e:
            logger.warning(f"Packet rate limit not applied on {iface}: {e}")
    
    if results:
        return True, f"{iface}: {', '.join(results)}"
    return True, f"{iface}: no limits applied"

def clear_tc_limits(iface):
    subprocess.run(["tc", "qdisc", "del", "dev", iface, "root"],
                  capture_output=True, check=False)
    subprocess.run(["tc", "qdisc", "del", "dev", iface, "ingress"],
                  capture_output=True, check=False)
    logger.info(f"Cleared tc limits on {iface}")

def apply_slice_limits(slice_limits):
    results = []
    for sl in slice_limits:
        veth = slice_id_to_veth(sl.slice_id)
        if not veth:
            results.append(f"{sl.slice_id}: unknown veth mapping")
            continue
        
        tx_mbps = sl.nic_tx_limit_mbps
        rx_mbps = sl.nic_rx_limit_mbps
        if hasattr(sl, 'cpu_percent_limit') and sl.cpu_percent_limit > 0:
            # Use proactive CPU controller instead of static limit
            # This is legacy code - proactive control is done in CpuController
            bw_limit = (sl.cpu_percent_limit / 100.0) * MAX_PHYSICAL_MBPS
            tx_mbps = max(tx_mbps, bw_limit) if tx_mbps > 0 else bw_limit
            rx_mbps = max(rx_mbps, bw_limit) if rx_mbps > 0 else bw_limit
        
        success, msg = apply_tc_limit(
            veth,
            tx_mbps=tx_mbps,
            rx_mbps=rx_mbps,
            pkt_rate=sl.pkt_rate_limit
        )
        
        with active_limits_lock:
            active_slice_limits[sl.slice_id] = {
                "tx_mbps": tx_mbps,
                "rx_mbps": rx_mbps,
                "pkt_rate": sl.pkt_rate_limit,
                "cpu_percent": sl.cpu_percent_limit if hasattr(sl, 'cpu_percent_limit') else 0
            }
        
        results.append(msg)
    
    return results

def cpu_percent_to_bandwidth(cpu_percent):
    """Legacy function - proactive control uses CpuController._calc_safe_bandwidth()"""
    if cpu_percent <= 0:
        return 0
    return (cpu_percent / 100.0) * MAX_PHYSICAL_MBPS

def set_slice_limit_live(slice_id, action, cpu_percent=0, tx_mbps=0, rx_mbps=0, pkt_rate=0, cpu_coefficient=0):
    """
    Live set/delete limit on a single slice.
    This does NOT interrupt traffic - tc replace works atomically.
    
    If cpu_percent is specified, uses PROACTIVE control that
    dynamically adjusts bandwidth to maintain CPU around target value.
    
    cpu_coefficient: CPU% per Mbps (e.g., 0.03 means 1 Gbps = 30% CPU)
    """
    veth = slice_id_to_veth(slice_id)
    if not veth:
        return False, f"Unknown slice: {slice_id}", None
    
    if action == 'GET' or action == 2:
        with active_limits_lock:
            current = active_slice_limits.get(slice_id)
        # Add info about proactive controller
        with pid_controllers_lock:
            ctrl = active_pid_controllers.get(slice_id)
            if ctrl and current:
                current = dict(current)
                current["proactive"] = True
                current["current_bandwidth"] = ctrl.current_bandwidth
        if current:
            return True, f"Current limit for {slice_id}", current
        else:
            return True, f"No limit set for {slice_id}", None
    
    elif action == 'DELETE' or action == 1:
        # Stop proactive controller if exists
        with pid_controllers_lock:
            if slice_id in active_pid_controllers:
                active_pid_controllers[slice_id].stop()
                del active_pid_controllers[slice_id]
                logger.info(f"Stopped PID controller for {slice_id}")
        
        clear_tc_limits(veth)
        with active_limits_lock:
            if slice_id in active_slice_limits:
                del active_slice_limits[slice_id]
        return True, f"Limit removed for {slice_id} (veth: {veth})", None
    
    elif action == 'SET' or action == 0:
        # If only cpu_coefficient is specified, save it and update existing controller if exists
        if cpu_coefficient > 0 and cpu_percent == 0:
            # Save coefficient for future controllers
            saved_cpu_coefficients[slice_id] = cpu_coefficient
            logger.info(f"Saved CPU coefficient for {slice_id}: {cpu_coefficient} (100K pps = {cpu_coefficient*100000:.1f}% CPU)")
            
            with pid_controllers_lock:
                if slice_id in active_pid_controllers:
                    active_pid_controllers[slice_id].set_cpu_coefficient(cpu_coefficient)
                    return True, f"CPU coefficient set to {cpu_coefficient} (100K pps = {cpu_coefficient*100000:.1f}% CPU)", None
                else:
                    return True, f"CPU coefficient saved for {slice_id}: {cpu_coefficient} (will be used when CPU limit is set)", None
        
        # If cpu_percent is specified, use PROACTIVE control
        if cpu_percent > 0:
            with pid_controllers_lock:
                if slice_id in active_pid_controllers:
                    # Update existing controller
                    active_pid_controllers[slice_id].set_target(cpu_percent)
                    if cpu_coefficient > 0:
                        saved_cpu_coefficients[slice_id] = cpu_coefficient
                        active_pid_controllers[slice_id].set_cpu_coefficient(cpu_coefficient)
                else:
                    # Create new proactive controller
                    ctrl = PidController(slice_id, cpu_percent, veth)
                    
                    # Use saved coefficient if exists, otherwise use passed one
                    effective_coef = cpu_coefficient if cpu_coefficient > 0 else saved_cpu_coefficients.get(slice_id, 0)
                    if effective_coef > 0:
                        ctrl.set_cpu_coefficient(effective_coef)
                        logger.info(f"Using saved coefficient for {slice_id}: {effective_coef}")
                    
                    ctrl.start()
                    active_pid_controllers[slice_id] = ctrl
                    logger.info(f"Started PID controller for {slice_id}, target={cpu_percent}%")
            
            with active_limits_lock:
                active_slice_limits[slice_id] = {
                    "tx_mbps": 0,  # Dynamically adjusted
                    "rx_mbps": 0,
                    "pkt_rate": pkt_rate,
                    "cpu_percent": cpu_percent,
                    "proactive": True
                }
            
            return True, f"Proactive CPU control started for {slice_id}, target={cpu_percent}%", active_slice_limits[slice_id]
        
        # Static bandwidth limit (without proactive control)
        effective_tx = tx_mbps
        effective_rx = rx_mbps
        
        success, msg = apply_tc_limit(
            veth,
            tx_mbps=effective_tx,
            rx_mbps=effective_rx,
            pkt_rate=pkt_rate
        )
        
        if success:
            with active_limits_lock:
                active_slice_limits[slice_id] = {
                    "tx_mbps": effective_tx,
                    "rx_mbps": effective_rx,
                    "pkt_rate": pkt_rate,
                    "cpu_percent": cpu_percent
                }
            return True, msg, active_slice_limits[slice_id]
        else:
            return False, msg, None
    
    return False, f"Unknown action: {action}", None


# ---------------- HELPERS ----------------
def get_tc_drops(iface):
    """Get tc ingress policing drops for interface"""
    try:
        result = subprocess.run(
            ["tc", "-s", "filter", "show", "dev", iface, "ingress"],
            capture_output=True, text=True, check=False
        )
        # Parse "dropped X" from output
        for line in result.stdout.split('\n'):
            if 'dropped' in line:
                # Format: "Sent 28700 bytes 66 pkts (dropped 0, overlimits 0)"
                import re
                match = re.search(r'dropped\s+(\d+)', line)
                if match:
                    return int(match.group(1))
    except:
        pass
    return 0

# Cache for previous tc drops values
prev_tc_drops = {}

def read_proc_net_dev():
    stats = {}
    with open("/proc/net/dev") as f:
        for line in f.readlines()[2:]:
            if ":" not in line:
                continue
            iface, data = line.split(":")
            iface = iface.strip()
            if FILTER_IFACES and iface not in FILTER_IFACES:
                continue
            fields = data.split()
            stats[iface] = {
                "rx_bytes": int(fields[0]),
                "rx_pkts": int(fields[1]),
                "rx_errs": int(fields[2]),
                "rx_drops": int(fields[3]),
                "tx_bytes": int(fields[8]),
                "tx_pkts": int(fields[9]),
                "tx_errs": int(fields[10]),
                "tx_drops": int(fields[11]),
            }
    return stats

def read_global_cpu():
    return psutil.cpu_percent(interval=None)

def read_global_ram():
    vm = psutil.virtual_memory()
    return {
        "total_gb": vm.total / 1024**3,
        "used_gb": vm.used / 1024**3,
        "free_gb": vm.available / 1024**3,
        "percent": vm.percent,
    }

def read_namespace_ram_percent(ns):
    total_rss = 0
    total_mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    for proc_name in ["ovs-vswitchd", "ovsdb-server"]:
        try:
            out = subprocess.check_output(
                ["ip", "netns", "exec", ns, "pgrep", "-f", proc_name],
                text=True, stderr=subprocess.DEVNULL
            )
            for pid in out.split():
                try:
                    with open(f"/proc/{pid}/statm") as f:
                        rss = int(f.read().split()[1])
                        total_rss += rss * os.sysconf("SC_PAGE_SIZE")
                except Exception:
                    pass
        except subprocess.CalledProcessError:
            pass
    return (total_rss / total_mem * 100) if total_mem else 0.0


def collect_bpf_cpu_by_namespace():
    """
    Collect BPF CPU measurements and aggregate by namespace.
    Uses cpu_time_total map that aggregates ALL packet processing phases:
    - ovs_dp_process_packet (OVS datapath)
    - veth_xmit (veth transfer)
    - netif_receive_skb (netif receive)
    - dev_queue_xmit (dev xmit)
    Returns dict: {namespace: cpu_pct} with smoothing (moving average)
    """
    global prev_cpu_total
    
    raw_result = {ns: 0.0 for ns in OVS_NAMESPACES}
    
    for k, v in cpu_map_total.items():
        ifindex = k.ifindex
        ns = ifmap.get(ifindex)
        
        # Check veth-phyX mapping as well
        if ns == "host" and ifindex in veth_ns_map:
            ns = veth_ns_map[ifindex]
        
        if ns not in OVS_NAMESPACES:
            continue
        
        prev = prev_cpu_total.get(ifindex, v.value)
        delta = v.value - prev
        prev_cpu_total[ifindex] = v.value
        
        if delta > 0:
            cpu_pct = (delta / (INTERVAL * 1e9)) * 100 / num_cpus
            raw_result[ns] += cpu_pct
    
    # Smoothing: add to history and return average
    result = {}
    for ns, cpu in raw_result.items():
        cpu_history[ns].append(cpu)
        if len(cpu_history[ns]) > 0:
            result[ns] = sum(cpu_history[ns]) / len(cpu_history[ns])
        else:
            result[ns] = cpu
    
    return result


def collect_process_cpu_by_namespace():
    """
    Collect CPU measurements from /proc for OVS processes.
    This is an alternative/supplementary measurement.
    """
    global prev_cgroup_cpu
    
    result = {}
    hz = os.sysconf("SC_CLK_TCK")
    
    for ns in OVS_NAMESPACES:
        current_ns = get_ovs_process_cpu(ns)
        prev_ns = prev_cgroup_cpu.get(ns, current_ns)
        delta_ns = current_ns - prev_ns
        prev_cgroup_cpu[ns] = current_ns
        
        if delta_ns > 0:
            cpu_pct = (delta_ns / (INTERVAL * 1e9)) * 100
        else:
            cpu_pct = 0
        
        result[ns] = cpu_pct
    
    return result


def collect_test_ns_cpu():
    """
    Collect CPU measurements for test namespaces (iperf servers).
    Returns CPU percentage as fraction of one CPU (not total system).
    """
    global prev_test_cpu
    
    result = {}
    
    for ns in TEST_NAMESPACES:
        current_ns = get_test_ns_process_cpu(ns)
        prev_ns = prev_test_cpu.get(ns, current_ns)
        delta_ns = current_ns - prev_ns
        prev_test_cpu[ns] = current_ns
        
        if delta_ns > 0:
            # delta_ns is in nanoseconds, INTERVAL is in seconds
            # Divide by num_cpus to get percentage of total CPU
            cpu_pct = (delta_ns / (INTERVAL * 1e9)) * 100 / num_cpus
        else:
            cpu_pct = 0
        
        result[ns] = cpu_pct
    
    return result


# ---------------- gRPC SERVICER ----------------
class OvsMonitorServicer(ovs_monitor_pb2_grpc.OvsMonitorServicer):
    def GetMetrics(self, request, context):
        global prev_nic

        status = "OK"

        # -------- APPLY LIMITS --------
        limit_messages = []
        try:
            if request.slice_limits:
                slice_results = apply_slice_limits(request.slice_limits)
                limit_messages.extend(slice_results)
                status = "LIMIT_APPLIED"
            
            if request.nic_iface and (request.nic_tx_limit_mbps or request.nic_rx_limit_mbps):
                success, msg = apply_tc_limit(
                    request.nic_iface,
                    tx_mbps=request.nic_tx_limit_mbps,
                    rx_mbps=request.nic_rx_limit_mbps
                )
                limit_messages.append(msg)
                status = "LIMIT_APPLIED"
            
            if request.cpu_limit_percent > 0:
                subprocess.run(
                    ["systemctl", "set-property", "ovs-vswitchd.service", f"CPUQuota={request.cpu_limit_percent}%"],
                    check=False
                )
                limit_messages.append(f"userspace CPU={request.cpu_limit_percent}%")
                status = "LIMIT_APPLIED"
            if request.ram_limit_percent > 0:
                subprocess.run(
                    ["systemctl", "set-property", "ovs-vswitchd.service", f"MemoryMax={int(request.ram_limit_percent)}%"],
                    check=False
                )
                limit_messages.append(f"userspace RAM={request.ram_limit_percent}%")
                status = "LIMIT_APPLIED"
                
            if limit_messages:
                status = f"LIMIT_APPLIED: {'; '.join(limit_messages)}"
        except Exception as e:
            status = f"ERROR: {e}"

        # -------- COLLECT METRICS --------
        
        # BPF CPU measurements (kernel + veth + netif + xmit)
        bpf_cpu = collect_bpf_cpu_by_namespace()
        
        # Process CPU measurements (userspace ovs-vswitchd + ovsdb-server)
        proc_cpu = collect_process_cpu_by_namespace()
        
        # Test namespace CPU measurements (iperf servers)
        test_cpu = collect_test_ns_cpu()

        # Namespace stats
        namespaces = []
        for ns in OVS_NAMESPACES:
            # Kernel CPU = BPF measurement (ovs_dp_process_packet)
            cpu_kernel = bpf_cpu.get(ns, 0)
            
            # Userspace CPU = process-based measurement
            cpu_user = proc_cpu.get(ns, 0)
            
            namespaces.append(
                ovs_monitor_pb2.NamespaceStats(
                    name=ns,
                    cpu_kernel=cpu_kernel,
                    cpu_user=cpu_user,
                    cpu_total=cpu_kernel + cpu_user,
                    ram_percent=read_namespace_ram_percent(ns),
                )
            )
        
        # Test namespace stats (iperf servers)
        for ns in TEST_NAMESPACES:
            cpu_user = test_cpu.get(ns, 0)
            namespaces.append(
                ovs_monitor_pb2.NamespaceStats(
                    name=ns,
                    cpu_kernel=0,  # We don't measure kernel CPU for test namespace
                    cpu_user=cpu_user,
                    cpu_total=cpu_user,
                    ram_percent=0,  # Optional: we can add RAM measurement
                )
            )

        # NIC stats
        nics = []
        now_nic = read_proc_net_dev()
        for iface, cur in now_nic.items():
            prev = prev_nic.get(iface)
            if not prev:
                continue
            # Use max(0, ...) to prevent negative values (counter reset)
            nics.append(
                ovs_monitor_pb2.NicStats(
                    iface=iface,
                    rx_mbps=max(0, (cur['rx_bytes']-prev['rx_bytes'])*8/1e6),
                    tx_mbps=max(0, (cur['tx_bytes']-prev['tx_bytes'])*8/1e6),
                    rx_pkts=max(0, cur['rx_pkts']-prev['rx_pkts']),
                    tx_pkts=max(0, cur['tx_pkts']-prev['tx_pkts']),
                    rx_drops=max(0, cur['rx_drops']-prev['rx_drops']),
                    tx_drops=max(0, cur['tx_drops']-prev['tx_drops']),
                    rx_errs=max(0, cur['rx_errs']-prev['rx_errs']),
                    tx_errs=max(0, cur['tx_errs']-prev['tx_errs']),
                )
            )
        prev_nic = now_nic

        # Add XDP drop statistics PER-SLICE
        global prev_xdp_stats
        xdp_stats = get_xdp_drop_stats()
        if xdp_stats:
            # Map IP -> slice
            config = load_slice_config()
            ip_to_slice = {}
            if config:
                for slice_id, slice_cfg in config.get("slices", {}).items():
                    for ip in slice_cfg.get("ips", []):
                        ip_to_slice[ip] = slice_id
            
            # Group statistics by slice (packets and bytes)
            slice_stats = {}
            for ip, stats in xdp_stats.items():
                slice_id = ip_to_slice.get(ip, f"unknown-{ip}")
                if slice_id not in slice_stats:
                    slice_stats[slice_id] = {"drops": 0, "passes": 0, "drop_bytes": 0, "pass_bytes": 0}
                slice_stats[slice_id]["drops"] += stats["drops"]
                slice_stats[slice_id]["passes"] += stats["passes"]
                slice_stats[slice_id]["drop_bytes"] += stats.get("drop_bytes", 0)
                slice_stats[slice_id]["pass_bytes"] += stats.get("pass_bytes", 0)
            
            # Add virtual NIC for each slice with XDP statistics
            for slice_id, stats in slice_stats.items():
                prev_key = f"xdp_{slice_id}"
                prev_drops = prev_xdp_stats.get(f"{prev_key}_drops", stats["drops"])
                prev_passes = prev_xdp_stats.get(f"{prev_key}_passes", stats["passes"])
                prev_drop_bytes = prev_xdp_stats.get(f"{prev_key}_drop_bytes", stats["drop_bytes"])
                prev_pass_bytes = prev_xdp_stats.get(f"{prev_key}_pass_bytes", stats["pass_bytes"])
                
                drop_rate = max(0, stats["drops"] - prev_drops)
                pass_rate = max(0, stats["passes"] - prev_passes)
                # Throughput in Mbps (bytes * 8 / 1e6)
                drop_mbps = max(0, (stats["drop_bytes"] - prev_drop_bytes) * 8 / 1e6)
                pass_mbps = max(0, (stats["pass_bytes"] - prev_pass_bytes) * 8 / 1e6)
                
                prev_xdp_stats[f"{prev_key}_drops"] = stats["drops"]
                prev_xdp_stats[f"{prev_key}_passes"] = stats["passes"]
                prev_xdp_stats[f"{prev_key}_drop_bytes"] = stats["drop_bytes"]
                prev_xdp_stats[f"{prev_key}_pass_bytes"] = stats["pass_bytes"]
                
                nics.append(
                    ovs_monitor_pb2.NicStats(
                        iface=f"XDP:{slice_id}",
                        rx_mbps=pass_mbps,      # How much PASSED through XDP (Mbps)
                        tx_mbps=drop_mbps,      # How much was DROPPED at XDP (Mbps)
                        rx_pkts=pass_rate,      # Packets that passed
                        tx_pkts=drop_rate,      # Packets that were dropped
                        rx_drops=drop_rate,     # Backward compatibility
                        tx_drops=0,
                        rx_errs=0,
                        tx_errs=0,
                    )
                )

        # Global stats with smoothing
        global_mem = read_global_ram()
        raw_global_cpu = read_global_cpu()
        global_cpu_history.append(raw_global_cpu)
        smoothed_global_cpu = sum(global_cpu_history) / len(global_cpu_history) if global_cpu_history else raw_global_cpu
        
        global_stats = ovs_monitor_pb2.GlobalStats(
            cpu_total=smoothed_global_cpu,
            ram_used_gb=global_mem["used_gb"],
            ram_total_gb=global_mem["total_gb"],
            ram_percent=global_mem["percent"],
            hostname=socket.gethostname()
        )

        metrics = ovs_monitor_pb2.OvsMetrics(
            namespaces=namespaces,
            nics=nics,
            global_stats=global_stats
        )

        return ovs_monitor_pb2.OvsResponse(metrics=metrics, status=status)

    def SetSliceLimit(self, request, context):
        slice_id = request.slice_id
        action = request.action
        
        success, message, current = set_slice_limit_live(
            slice_id=slice_id,
            action=action,
            cpu_percent=request.cpu_percent_limit,
            tx_mbps=request.nic_tx_limit_mbps,
            rx_mbps=request.nic_rx_limit_mbps,
            pkt_rate=request.pkt_rate_limit,
            cpu_coefficient=request.cpu_coefficient
        )
        
        response = ovs_monitor_pb2.SetSliceLimitResponse(
            success=success,
            message=message
        )
        
        if current:
            response.current_limit.CopyFrom(ovs_monitor_pb2.SliceResourceLimit(
                slice_id=slice_id,
                nic_tx_limit_mbps=current.get("tx_mbps", 0),
                nic_rx_limit_mbps=current.get("rx_mbps", 0),
                pkt_rate_limit=current.get("pkt_rate", 0),
                cpu_percent_limit=current.get("cpu_percent", 0)
            ))
        
        return response


# ---------------- RUN SERVER ----------------
def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    ovs_monitor_pb2_grpc.add_OvsMonitorServicer_to_server(OvsMonitorServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    print("gRPC OVS Monitor (FINAL) running on port 50051...")
    print(f"BPF probes: ovs_dp_process_packet, veth_xmit, netif_receive_skb, dev_queue_xmit")
    print(f"Monitoring namespaces: {OVS_NAMESPACES}")
    print("XDP MAC-based rate limiting: AVAILABLE")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        # Cleanup
        print("\nShutting down...")
        
        # Stop PID controllers
        with pid_controllers_lock:
            for ctrl in active_pid_controllers.values():
                ctrl.stop()
            active_pid_controllers.clear()
        
        server.stop(0)
        print("Server stopped")


if __name__ == "__main__":
    serve()
