#!/usr/bin/env python3
"""
Proactive PID Controller for OVS slices.

Uses feedback loop to maintain CPU around target value:
  - Measures current CPU for each OVS
  - Dynamically adjusts XDP PPS limit
  - PID controller for stable control

Example:
    controller = PidController("ovs-1", target_cpu=10.0)
    controller.start()  # starts background thread
    
    # Or as standalone:
    python3 pid_controller.py ovs-1 10
"""
import time
import threading
import subprocess
import logging
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pid_controller")

# XDP IP-based rate limiter (integrated in gRPC_o.py)
XDP_IP_AVAILABLE = False
_xdp_funcs = None

def init_xdp_functions(set_limit_func, remove_limit_func, get_ips_func):
    """Initialize XDP functions from gRPC_o.py"""
    global XDP_IP_AVAILABLE, _xdp_funcs
    _xdp_funcs = {
        'set_limit': set_limit_func,
        'remove_limit': remove_limit_func,
        'get_ips': get_ips_func
    }
    XDP_IP_AVAILABLE = True
    logger.info("XDP IP-based limiter initialized (per-slice isolation)")

# Configuration - PPS based
MIN_PPS = 1000                # Minimum PPS (doesn't go below)
MAX_PHYSICAL_PPS = 2000000    # Physical limit (~2M pps for 20 Gbps with small packets)
CONTROL_INTERVAL = 0.5        # How often we adjust (seconds)
SMOOTHING_WINDOW = 5          # Number of samples for smoothing
DEAD_ZONE = 0.5               # Dead zone for PID controller (±% CPU around target)

# CPU-PPS coefficient: OVS_CPU% = pps * CPU_PER_PPS
# This is CPU that OVS consumes for packet processing (not global CPU)
# Calibrated: 83K pps (1 Gbps @ 1500B) ≈ 7% CPU → 0.000084
# Can be dynamically adjusted through set_cpu_coefficient()
CPU_PER_PPS = 0.000084  # 1 pps = 0.000084% CPU

# PID parameters (tune as needed)
# Reduced parameters for more stable control
KP = 5.0    # Proportional gain (reduced from 10)
KI = 0.1    # Integral gain (reduced from 0.5)
KD = 1.0    # Derivative gain (reduced from 2)

# Mapping slice -> veth interface
SLICE_VETH_MAP = {
    "ovs-1": "veth-phy1",
    "ovs-2": "veth-phy2",
}

# Physical uplink where early drop should happen
UPLINK_IFACE = "ens19"

# Bridge that connects ens19 with veth-phyX
BRIDGE_IFACE = "br-phy"


class PIDController:
    """Simple PID controller"""
    
    def __init__(self, kp=KP, ki=KI, kd=KD, setpoint=0):
        self.kp = kp    # Proportional gain (5.0)
        self.ki = ki    # Integral gain (0.1)
        self.kd = kd    # Derivative gain (1.0)
        self.setpoint = setpoint    # Target CPU in %
        
        self.integral = 0   # Integral component
        self.prev_error = 0 # Previous error
        self.prev_time = time.time() # Previous time
        
    
    def update(self, measured_value):
        """
        Calculate output based on error.
        Returns adjustment (positive = increase bandwidth, negative = decrease)
        """
        now = time.time()
        dt = now - self.prev_time
        if dt <= 0:
            dt = 0.001
        
        # Error: positive if CPU is above target
        error = measured_value - self.setpoint
        
        # PID components
        p_term = self.kp * error
        
        self.integral += error * dt
        # Anti-windup
        self.integral = max(-100, min(100, self.integral))
        i_term = self.ki * self.integral
        
        d_term = self.kd * (error - self.prev_error) / dt
        
        self.prev_error = error
        self.prev_time = now
        
        # Output: negative if bandwidth needs to be reduced (CPU too high)
        output = -(p_term + i_term + d_term)
        
        return output


class PidController:
    """
    Proactive PID controller for a single OVS slice.
    Dynamically adjusts PPS limit to maintain CPU around target value.
    """
    
    def __init__(self, slice_id, target_cpu, veth_iface=None):
        """
        Args:
            slice_id: "ovs-1", "ovs-2", etc.
            target_cpu: Target CPU% (e.g., 10.0)
            veth_iface: Optional, otherwise derived from slice_id
        """
        self.slice_id = slice_id
        self.target_cpu = target_cpu
        self.veth_iface = veth_iface or SLICE_VETH_MAP.get(slice_id, f"veth-phy{slice_id.split('-')[-1]}")
        
        self.pid = PIDController(setpoint=target_cpu)
        self.cpu_history = deque(maxlen=SMOOTHING_WINDOW)
        
        self._running = False
        self._thread = None
        
        # For CPU measurement
        self._prev_cpu_ns = 0
        self._prev_time = time.time()
        
        # CPU-PPS coefficient (must be before _calc_safe_pps!)
        self.cpu_coefficient = CPU_PER_PPS
        
        # Initial PPS - set to 0 so first apply_pps() always applies limit
        self.current_pps = 0
    
    def _calc_safe_pps(self, target_cpu):
        """
        Calculate safe PPS for given CPU target.
        Safe PPS = PPS that gives target CPU (upper bound of safe zone).
        Limited by physical limit.
        """
        if self.cpu_coefficient > 0:
            safe_pps = target_cpu / self.cpu_coefficient
        else:
            safe_pps = MAX_PHYSICAL_PPS
        return min(safe_pps, MAX_PHYSICAL_PPS)
    
    def get_current_cpu(self):
        """
        Get actual CPU consumption for this slice from BPF measurements via gRPC.
        BPF measures all packet processing phases (ovs_dp_process_packet, veth_xmit, netif_receive_skb, dev_queue_xmit).
        """
        import grpc
        import ovs_monitor_pb2
        import ovs_monitor_pb2_grpc
        
        try:
            channel = grpc.insecure_channel("localhost:50051")
            stub = ovs_monitor_pb2_grpc.OvsMonitorStub(channel)
            req = ovs_monitor_pb2.OvsRequest()
            resp = stub.GetMetrics(req)
            
            for ns in resp.metrics.namespaces:
                if ns.name == self.slice_id:
                    # Use kernel CPU (BPF measurement)
                    return ns.cpu_kernel
            
            return 0.0
        except Exception as e:
            logger.warning(f"[{self.slice_id}] Failed to get CPU from gRPC: {e}")
            # Fallback to PPS-based estimation
            pps = self._get_veth_pps()
            return pps * self.cpu_coefficient
    
    def set_cpu_coefficient(self, coefficient):
        """
        Set CPU-PPS coefficient.
        coefficient: CPU% per packet (e.g., 0.000084 means 83K pps = 7% CPU)
        """
        self.cpu_coefficient = coefficient
        logger.info(f"[{self.slice_id}] CPU coefficient set to {coefficient} (100K pps = {coefficient*100000:.1f}% CPU)")
    
    def calibrate(self, duration=5):
        """
        Automatically calibrate CPU-throughput coefficient.
        Measures throughput and OVS CPU during 'duration' seconds and calculates coefficient.
        IMPORTANT: This should be run while iperf is running at full speed WITHOUT limits!
        
        Returns:
            (coefficient, throughput_mbps, cpu_percent)
        """
        import grpc
        import ovs_monitor_pb2
        import ovs_monitor_pb2_grpc
        
        logger.info(f"[{self.slice_id}] Starting calibration for {duration}s...")
        
        samples = []
        channel = grpc.insecure_channel("localhost:50051")
        stub = ovs_monitor_pb2_grpc.OvsMonitorStub(channel)
        
        # Collect samples
        for i in range(duration * 2):  # 2 samples per second
            time.sleep(0.5)
            
            # Get OVS CPU from gRPC
            try:
                req = ovs_monitor_pb2.OvsRequest()
                resp = stub.GetMetrics(req)
                
                ovs_cpu = 0
                for ns in resp.metrics.namespaces:
                    if ns.name == self.slice_id:
                        ovs_cpu = ns.cpu_kernel  # Kernel CPU is OVS CPU
                        break
                
                # Get throughput
                throughput = self._get_veth_throughput()
                
                if throughput > 10:  # Ignore if no traffic
                    samples.append((throughput, ovs_cpu))
                    logger.debug(f"[{self.slice_id}] Sample: {throughput:.0f}Mbps, {ovs_cpu:.1f}% CPU")
            except Exception as e:
                logger.warning(f"Calibration sample failed: {e}")
        
        if len(samples) < 3:
            logger.warning(f"[{self.slice_id}] Not enough samples for calibration. Is iperf running?")
            return None, 0, 0
        
        # Calculate average coefficient
        avg_throughput = sum(s[0] for s in samples) / len(samples)
        avg_cpu = sum(s[1] for s in samples) / len(samples)
        
        if avg_throughput < 10:
            logger.warning(f"[{self.slice_id}] Throughput too low for calibration: {avg_throughput:.0f}Mbps")
            return None, avg_throughput, avg_cpu
        
        coefficient = avg_cpu / avg_throughput
        
        # Set new coefficient
        self.cpu_coefficient = coefficient
        logger.info(f"[{self.slice_id}] Calibration complete: {avg_throughput:.0f}Mbps = {avg_cpu:.1f}% CPU")
        logger.info(f"[{self.slice_id}] New coefficient: {coefficient:.6f} (1 Gbps = {coefficient*1000:.0f}% CPU)")
        
        return coefficient, avg_throughput, avg_cpu
    
    def _get_veth_throughput(self):
        """Measure current throughput on veth interface in Mbps"""
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    if self.veth_iface in line:
                        parts = line.split()
                        rx_bytes = int(parts[1])
                        tx_bytes = int(parts[9])
                        
                        now = time.time()
                        elapsed = now - self._prev_time
                        
                        if elapsed > 0 and hasattr(self, '_prev_rx_bytes'):
                            rx_delta = rx_bytes - self._prev_rx_bytes
                            tx_delta = tx_bytes - self._prev_tx_bytes
                            total_mbps = (rx_delta + tx_delta) * 8 / elapsed / 1_000_000
                        else:
                            total_mbps = 0
                        
                        self._prev_rx_bytes = rx_bytes
                        self._prev_tx_bytes = tx_bytes
                        self._prev_time = now
                        
                        return total_mbps
        except Exception as e:
            logger.warning(f"Failed to get throughput: {e}")
        return 0.0
    
    def _get_veth_pps(self):
        """Measure current PPS on veth interface"""
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    if self.veth_iface in line:
                        parts = line.split()
                        rx_pkts = int(parts[2])
                        tx_pkts = int(parts[10])
                        
                        now = time.time()
                        elapsed = now - getattr(self, '_prev_pps_time', now)
                        
                        if elapsed > 0 and hasattr(self, '_prev_rx_pkts'):
                            rx_delta = rx_pkts - self._prev_rx_pkts
                            tx_delta = tx_pkts - self._prev_tx_pkts
                            total_pps = (rx_delta + tx_delta) / elapsed
                        else:
                            total_pps = 0
                        
                        self._prev_rx_pkts = rx_pkts
                        self._prev_tx_pkts = tx_pkts
                        self._prev_pps_time = now
                        
                        return total_pps
        except Exception as e:
            logger.warning(f"Failed to get PPS: {e}")
        return 0.0
    
    def get_veth_mac(self):
        """Get MAC address of veth interface"""
        try:
            out = subprocess.check_output(
                ["ip", "link", "show", self.veth_iface], text=True
            )
            for line in out.splitlines():
                if "link/ether" in line:
                    return line.split()[1]
        except:
            pass
        return None
    
    def apply_pps(self, pps):
        """
        Apply XDP PPS rate limit on ens19 for this slice.
        XDP is the only way for per-slice isolation without backpressure.
        """
        safe_pps = self._calc_safe_pps(self.target_cpu)
        pps = max(MIN_PPS, min(safe_pps, pps))
        
        if abs(pps - self.current_pps) < 100:
            return  # No need for change (less than 100 pps difference)
        
        try:
            # Use XDP on ens19 - without backpressure
            self._apply_uplink_policing_pps(pps)
            
            self.current_pps = pps
            logger.info(f"[{self.slice_id}] XDP PPS set to {pps:.0f} pps")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to apply XDP: {e}")
    
    def _get_fdb_macs_for_veth(self):
        """
        Get MAC addresses of hosts BEHIND OVS (learned on veth-phyX).
        These are dst MAC addresses of packets arriving on ens19 going to this OVS.
        """
        macs = []
        try:
            out = subprocess.check_output(
                ["bridge", "fdb", "show", "br", BRIDGE_IFACE], text=True
            )
            for line in out.splitlines():
                # Looking for MAC addresses learned on THIS veth (not permanent)
                # Format: "56:04:e1:a2:85:75 dev veth-phy1 master br-phy"
                if self.veth_iface in line and "master" in line and "permanent" not in line:
                    mac = line.split()[0]
                    # Skip multicast and broadcast
                    if mac and ":" in mac and not mac.startswith("33:33") and not mac.startswith("01:00:5e") and not mac.startswith("ff:ff"):
                        macs.append(mac)
        except Exception as e:
            logger.warning(f"Failed to get FDB: {e}")
        
        logger.info(f"[{self.slice_id}] Found {len(macs)} MACs behind {self.veth_iface}: {macs}")
        return macs
    
    def _learn_destination_ips(self, duration=3):
        """
        Learn destination IP addresses by monitoring traffic on veth interface.
        These are IP addresses of packets going towards this OVS.
        
        Returns:
            set: Set of destination IP addresses
        """
        ips = set()
        try:
            # Capture packets for duration seconds
            result = subprocess.run(
                ["timeout", str(duration), "tcpdump", "-i", self.veth_iface, "-n", 
                 "-c", "500", "-q", "ip"],
                capture_output=True, text=True
            )
            
            # Parse output to extract destination IPs
            # Format: "IP src > dst: ..."
            for line in result.stdout.splitlines():
                if " > " in line and "IP " in line:
                    parts = line.split(" > ")
                    if len(parts) >= 2:
                        dst_part = parts[1].split(":")[0].strip()
                        # Remove port if present (format: ip.port)
                        if "." in dst_part:
                            segments = dst_part.rsplit(".", 1)
                            if len(segments) == 2 and segments[1].isdigit():
                                dst_part = segments[0]
                        # Validate IP format
                        if dst_part.count(".") == 3:
                            ips.add(dst_part)
            
            logger.info(f"[{self.slice_id}] Learned {len(ips)} destination IPs from {self.veth_iface}: {ips}")
        except Exception as e:
            logger.warning(f"[{self.slice_id}] Failed to learn IPs from {self.veth_iface}: {e}")
        
        return ips
    
    def _apply_uplink_policing_pps(self, rate_pps):
        """
        Set XDP PPS rate limiting on ens19 by DESTINATION IP address.
        Reads IP addresses from slice_config.json for per-slice isolation.
        """
        # Use XDP IP-based limiter
        if XDP_IP_AVAILABLE and _xdp_funcs:
            ips = _xdp_funcs['get_ips'](self.slice_id)
            if not ips:
                logger.warning(f"[{self.slice_id}] No IPs in slice_config.json")
                return
            
            for ip in ips:
                _xdp_funcs['set_limit'](ip, rate_pps)  # PPS directly
            
            logger.info(f"[{self.slice_id}] XDP rate limit set for {len(ips)} IPs at {rate_pps:.0f} pps: {ips}")
        else:
            logger.warning(f"[{self.slice_id}] XDP not available, skipping uplink policing")
    
    def control_loop(self):
        """Main control loop - PPS based"""
        logger.info(f"[{self.slice_id}] Starting CPU controller, target={self.target_cpu}%")
        
        # Initially set limit to safe PPS (upper bound of safe zone)
        safe_pps = self._calc_safe_pps(self.target_cpu)
        logger.info(f"[{self.slice_id}] Safe PPS for {self.target_cpu}% CPU = {safe_pps:.0f} pps")
        self.apply_pps(safe_pps)
        
        while self._running:
            # 1. Measure CPU
            cpu = self.get_current_cpu()
            self.cpu_history.append(cpu)
            
            # Smoothing
            avg_cpu = sum(self.cpu_history) / len(self.cpu_history)
            
            # 2. Dead zone: if CPU is close to target, don't change PPS
            error = avg_cpu - self.target_cpu
            
            if abs(error) <= DEAD_ZONE:
                # CPU is in acceptable range, reset integral and skip
                self.pid.integral = 0
                time.sleep(CONTROL_INTERVAL)
                continue
            
            # If CPU is below target, increase PPS
            safe_pps = self._calc_safe_pps(self.target_cpu)
            if error < -DEAD_ZONE:
                # CPU is too low, increase PPS proportionally to error
                # Larger error = larger increase (but limited)
                increase = min(10000, abs(error) * 2000)  # Max 10K pps per step
                new_pps = self.current_pps + increase
                new_pps = min(safe_pps, new_pps)
                if new_pps > self.current_pps:
                    self.apply_pps(new_pps)
                    logger.debug(f"[{self.slice_id}] CPU={avg_cpu:.1f}% < target={self.target_cpu}%, increasing PPS to {new_pps:.0f}")
                time.sleep(CONTROL_INTERVAL)
                continue
            
            # 3. PID calculation (CPU > target, need to reduce PPS)
            # PID adjustment is in % CPU, convert to PPS
            adjustment_cpu = self.pid.update(avg_cpu)
            adjustment_pps = adjustment_cpu / self.cpu_coefficient if self.cpu_coefficient > 0 else 0
            
            # 4. Calculate new PPS (limited to safe zone)
            new_pps = self.current_pps + adjustment_pps
            new_pps = max(MIN_PPS, min(safe_pps, new_pps))
            
            # 5. Apply if significant change (more than 500 pps)
            if abs(new_pps - self.current_pps) >= 500:
                old_pps = self.current_pps
                self.apply_pps(new_pps)
                direction = "↓" if new_pps < old_pps else "↑"
                logger.info(f"[{self.slice_id}] PID: CPU={avg_cpu:.1f}% (target={self.target_cpu}%), PPS: {old_pps:.0f} {direction} {new_pps:.0f} (adj={adjustment_pps:.0f})")
            
            # Log status every 5 seconds if no changes
            elif len(self.cpu_history) % 10 == 0:
                logger.info(f"[{self.slice_id}] Status: CPU={avg_cpu:.1f}% (target={self.target_cpu}%), PPS={self.current_pps:.0f} (stable)")
            
            time.sleep(CONTROL_INTERVAL)
    
    def start(self):
        """Start controller in background thread"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self.control_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop controller and remove XDP limits"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        
        # Remove XDP limits for this slice
        if XDP_IP_AVAILABLE and _xdp_funcs:
            ips = _xdp_funcs['get_ips'](self.slice_id)
            for ip in ips:
                _xdp_funcs['remove_limit'](ip)
            logger.info(f"[{self.slice_id}] XDP rate limits removed")
    
    def set_target(self, new_target):
        """Change target CPU%"""
        self.target_cpu = new_target
        self.pid.setpoint = new_target
        logger.info(f"[{self.slice_id}] Target changed to {new_target}%")


# Global registry of controllers
_controllers = {}
_controllers_lock = threading.Lock()


def start_cpu_control(slice_id, target_cpu):
    """Start CPU control for slice"""
    with _controllers_lock:
        if slice_id in _controllers:
            _controllers[slice_id].set_target(target_cpu)
        else:
            ctrl = CpuController(slice_id, target_cpu)
            ctrl.start()
            _controllers[slice_id] = ctrl
    return True, f"CPU control started for {slice_id}, target={target_cpu}%"


def stop_cpu_control(slice_id):
    """Stop CPU control for slice"""
    with _controllers_lock:
        if slice_id in _controllers:
            _controllers[slice_id].stop()
            del _controllers[slice_id]
            return True, f"CPU control stopped for {slice_id}"
        return False, f"No controller for {slice_id}"


def get_cpu_control_status(slice_id=None):
    """Get controller status"""
    with _controllers_lock:
        if slice_id:
            ctrl = _controllers.get(slice_id)
            if ctrl:
                return {
                    "slice_id": slice_id,
                    "target_cpu": ctrl.target_cpu,
                    "current_bandwidth": ctrl.current_bandwidth,
                    "running": ctrl._running
                }
            return None
        else:
            return {
                sid: {
                    "target_cpu": c.target_cpu,
                    "current_bandwidth": c.current_bandwidth,
                    "running": c._running
                }
                for sid, c in _controllers.items()
            }


# ============== CLI ==============
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python3 cpu_controller.py <slice_id> <target_cpu%>")
        print("Example: python3 cpu_controller.py ovs-1 10")
        sys.exit(1)
    
    slice_id = sys.argv[1]
    target_cpu = float(sys.argv[2])
    
    print(f"Starting proactive CPU controller for {slice_id}")
    print(f"Target: {target_cpu}% CPU")
    print(f"Interface: veth-phy{slice_id.split('-')[-1]}")
    print("Press Ctrl+C to stop")
    print()
    
    ctrl = CpuController(slice_id, target_cpu)
    
    try:
        ctrl._running = True
        ctrl.control_loop()  # Run in foreground
    except KeyboardInterrupt:
        print("\nStopping...")
        ctrl.stop()
