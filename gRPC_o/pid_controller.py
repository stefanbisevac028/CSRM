#!/usr/bin/env python3
"""
Proaktivni PID Controller za OVS slice-ove.

Koristi feedback loop za održavanje CPU oko target vrednosti:
  - Meri trenutni CPU za svaki OVS
  - Dinamički podešava XDP PPS limit
  - PID controller za stabilnu kontrolu

Primer:
    controller = PidController("ovs-1", target_cpu=10.0)
    controller.start()  # pokreće background thread
    
    # Ili kao standalone:
    python3 pid_controller.py ovs-1 10
"""
import time
import threading
import subprocess
import logging
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pid_controller")

# XDP IP-based rate limiter (integrisan u gRPC_o.py)
XDP_IP_AVAILABLE = False
_xdp_funcs = None

def init_xdp_functions(set_limit_func, remove_limit_func, get_ips_func):
    """Inicijalizuj XDP funkcije iz gRPC_o.py"""
    global XDP_IP_AVAILABLE, _xdp_funcs
    _xdp_funcs = {
        'set_limit': set_limit_func,
        'remove_limit': remove_limit_func,
        'get_ips': get_ips_func
    }
    XDP_IP_AVAILABLE = True
    logger.info("XDP IP-based limiter initialized (per-slice isolation)")

# Konfiguracija - PPS based
MIN_PPS = 1000                # Minimalni PPS (ne ide ispod)
MAX_PHYSICAL_PPS = 2000000    # Fizički limit (~2M pps za 20 Gbps sa malim paketima)
CONTROL_INTERVAL = 0.5        # Koliko često podešavamo (sekunde)
SMOOTHING_WINDOW = 5          # Broj uzoraka za smoothing
DEAD_ZONE = 0.5               # Dead zona za PID kontroler (±% CPU oko targeta)

# CPU-PPS koeficijent: OVS_CPU% = pps * CPU_PER_PPS
# Ovo je CPU koji OVS troši za obradu paketa (ne globalni CPU)
# Kalibrisano: 83K pps (1 Gbps @ 1500B) ≈ 7% CPU → 0.000084
# Može se dinamički podešavati kroz set_cpu_coefficient()
CPU_PER_PPS = 0.000084  # 1 pps = 0.000084% CPU

# PID parametri (tune po potrebi)
# Smanjeni parametri za stabilniju kontrolu
KP = 5.0    # Proportional gain (smanjeno sa 10)
KI = 0.1    # Integral gain (smanjeno sa 0.5)
KD = 1.0    # Derivative gain (smanjeno sa 2)

# Mapiranje slice -> veth interfejs
SLICE_VETH_MAP = {
    "ovs-1": "veth-phy1",
    "ovs-2": "veth-phy2",
}

# Fizički uplink gdje treba raditi early drop
UPLINK_IFACE = "ens19"

# Bridge koji povezuje ens19 sa veth-phyX
BRIDGE_IFACE = "br-phy"


class PIDController:
    """Jednostavan PID controller"""
    
    def __init__(self, kp=KP, ki=KI, kd=KD, setpoint=0):
        self.kp = kp    # Proporcinalno pojačanje (5.0)
        self.ki = ki    # Integralno pojačanje (0.1)
        self.kd = kd    # Derivativno pojačanje (1.0)
        self.setpoint = setpoint    # Ciljni CPU u %
        
        self.integral = 0   # Integralna komponenta
        self.prev_error = 0 # Prethodna greška
        self.prev_time = time.time() # Prethodno vreme
        
    
    def update(self, measured_value):
        """
        Izračunaj output na osnovu greške.
        Vraća adjustment (pozitivan = povećaj bandwidth, negativan = smanji)
        """
        now = time.time()
        dt = now - self.prev_time
        if dt <= 0:
            dt = 0.001
        
        # Error: pozitivan ako je CPU iznad targeta
        error = measured_value - self.setpoint
        
        # PID komponente
        p_term = self.kp * error
        
        self.integral += error * dt
        # Anti-windup
        self.integral = max(-100, min(100, self.integral))
        i_term = self.ki * self.integral
        
        d_term = self.kd * (error - self.prev_error) / dt
        
        self.prev_error = error
        self.prev_time = now
        
        # Output: negativan ako treba smanjiti bandwidth (CPU previsok)
        output = -(p_term + i_term + d_term)
        
        return output


class PidController:
    """
    Proaktivni PID controller za jedan OVS slice.
    Dinamički podešava PPS limit da održi CPU oko target vrednosti.
    """
    
    def __init__(self, slice_id, target_cpu, veth_iface=None):
        """
        Args:
            slice_id: "ovs-1", "ovs-2", itd.
            target_cpu: Target CPU% (npr. 10.0)
            veth_iface: Opciono, inače se izvodi iz slice_id
        """
        self.slice_id = slice_id
        self.target_cpu = target_cpu
        self.veth_iface = veth_iface or SLICE_VETH_MAP.get(slice_id, f"veth-phy{slice_id.split('-')[-1]}")
        
        self.pid = PIDController(setpoint=target_cpu)
        self.cpu_history = deque(maxlen=SMOOTHING_WINDOW)
        
        self._running = False
        self._thread = None
        
        # Za merenje CPU-a
        self._prev_cpu_ns = 0
        self._prev_time = time.time()
        
        # CPU-PPS koeficijent (mora biti pre _calc_safe_pps!)
        self.cpu_coefficient = CPU_PER_PPS
        
        # Inicijalni PPS - postavi na 0 da bi prvi apply_pps() uvek primenio limit
        self.current_pps = 0
    
    def _calc_safe_pps(self, target_cpu):
        """
        Izračunaj safe PPS za dati CPU target.
        Safe PPS = PPS koji daje target CPU (gornja granica safe zone).
        Ograničeno fizičkim limitom.
        """
        if self.cpu_coefficient > 0:
            safe_pps = target_cpu / self.cpu_coefficient
        else:
            safe_pps = MAX_PHYSICAL_PPS
        return min(safe_pps, MAX_PHYSICAL_PPS)
    
    def get_current_cpu(self):
        """
        Dohvati stvarnu CPU potrošnju za ovaj slice iz BPF merenja preko gRPC-a.
        BPF meri sve faze obrade paketa (ovs_dp_process_packet, veth_xmit, netif_receive_skb, dev_queue_xmit).
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
                    # Koristi kernel CPU (BPF merenje)
                    return ns.cpu_kernel
            
            return 0.0
        except Exception as e:
            logger.warning(f"[{self.slice_id}] Failed to get CPU from gRPC: {e}")
            # Fallback na PPS-based procjenu
            pps = self._get_veth_pps()
            return pps * self.cpu_coefficient
    
    def set_cpu_coefficient(self, coefficient):
        """
        Postavi CPU-PPS koeficijent.
        koefficient: CPU% po paketu (npr. 0.000084 znači 83K pps = 7% CPU)
        """
        self.cpu_coefficient = coefficient
        logger.info(f"[{self.slice_id}] CPU koefficient set to {coefficient} (100K pps = {coefficient*100000:.1f}% CPU)")
    
    def calibrate(self, duration=5):
        """
        Automatski kalibriraj CPU-throughput koeficijent.
        Meri throughput i OVS CPU tokom 'duration' sekundi i izračuna koeficijent.
        VAŽNO: Ovo treba pokrenuti dok iperf radi na punoj brzini BEZ limita!
        
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
        
        # Prikupi uzorke
        for i in range(duration * 2):  # 2 uzorka po sekundi
            time.sleep(0.5)
            
            # Dohvati OVS CPU iz gRPC
            try:
                req = ovs_monitor_pb2.OvsRequest()
                resp = stub.GetMetrics(req)
                
                ovs_cpu = 0
                for ns in resp.metrics.namespaces:
                    if ns.name == self.slice_id:
                        ovs_cpu = ns.cpu_kernel  # Kernel CPU je OVS CPU
                        break
                
                # Dohvati throughput
                throughput = self._get_veth_throughput()
                
                if throughput > 10:  # Ignoriši ako nema traffica
                    samples.append((throughput, ovs_cpu))
                    logger.debug(f"[{self.slice_id}] Sample: {throughput:.0f}Mbps, {ovs_cpu:.1f}% CPU")
            except Exception as e:
                logger.warning(f"Calibration sample failed: {e}")
        
        if len(samples) < 3:
            logger.warning(f"[{self.slice_id}] Not enough samples for calibration. Is iperf running?")
            return None, 0, 0
        
        # Izračunaj prosečni koeficijent
        avg_throughput = sum(s[0] for s in samples) / len(samples)
        avg_cpu = sum(s[1] for s in samples) / len(samples)
        
        if avg_throughput < 10:
            logger.warning(f"[{self.slice_id}] Throughput too low for calibration: {avg_throughput:.0f}Mbps")
            return None, avg_throughput, avg_cpu
        
        coefficient = avg_cpu / avg_throughput
        
        # Postavi novi koeficijent
        self.cpu_coefficient = coefficient
        logger.info(f"[{self.slice_id}] Calibration complete: {avg_throughput:.0f}Mbps = {avg_cpu:.1f}% CPU")
        logger.info(f"[{self.slice_id}] New coefficient: {coefficient:.6f} (1 Gbps = {coefficient*1000:.0f}% CPU)")
        
        return coefficient, avg_throughput, avg_cpu
    
    def _get_veth_throughput(self):
        """Mjeri trenutni throughput na veth interfejsu u Mbps"""
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
        """Mjeri trenutni PPS na veth interfejsu"""
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
        """Dohvati MAC adresu veth interfejsa"""
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
        Primijeni XDP PPS rate limit na ens19 za ovaj slice.
        XDP je jedini način za per-slice izolaciju bez backpressure.
        """
        safe_pps = self._calc_safe_pps(self.target_cpu)
        pps = max(MIN_PPS, min(safe_pps, pps))
        
        if abs(pps - self.current_pps) < 100:
            return  # Nema potrebe za promenom (manje od 100 pps razlike)
        
        try:
            # Koristi XDP na ens19 - bez backpressure
            self._apply_uplink_policing_pps(pps)
            
            self.current_pps = pps
            logger.info(f"[{self.slice_id}] XDP PPS set to {pps:.0f} pps")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to apply XDP: {e}")
    
    def _get_fdb_macs_for_veth(self):
        """
        Dohvati MAC adrese hostova IZA OVS-a (naučene na veth-phyX).
        Ovo su dst MAC adrese paketa koji dolaze na ens19 i idu ka ovom OVS-u.
        """
        macs = []
        try:
            out = subprocess.check_output(
                ["bridge", "fdb", "show", "br", BRIDGE_IFACE], text=True
            )
            for line in out.splitlines():
                # Tražimo MAC adrese naučene na OVOM veth-u (ne permanent)
                # Format: "56:04:e1:a2:85:75 dev veth-phy1 master br-phy"
                if self.veth_iface in line and "master" in line and "permanent" not in line:
                    mac = line.split()[0]
                    # Skip multicast i broadcast
                    if mac and ":" in mac and not mac.startswith("33:33") and not mac.startswith("01:00:5e") and not mac.startswith("ff:ff"):
                        macs.append(mac)
        except Exception as e:
            logger.warning(f"Failed to get FDB: {e}")
        
        logger.info(f"[{self.slice_id}] Found {len(macs)} MACs behind {self.veth_iface}: {macs}")
        return macs
    
    def _learn_destination_ips(self, duration=3):
        """
        Nauči destination IP adrese prateći traffic na veth interfejsu.
        Ovo su IP adrese paketa koji idu prema ovom OVS-u.
        
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
        Postavlja XDP PPS rate limiting na ens19 po DESTINATION IP adresi.
        Čita IP adrese iz slice_config.json za per-slice izolaciju.
        """
        # Koristi XDP IP-based limiter
        if XDP_IP_AVAILABLE and _xdp_funcs:
            ips = _xdp_funcs['get_ips'](self.slice_id)
            if not ips:
                logger.warning(f"[{self.slice_id}] No IPs in slice_config.json")
                return
            
            for ip in ips:
                _xdp_funcs['set_limit'](ip, rate_pps)  # PPS direktno
            
            logger.info(f"[{self.slice_id}] XDP rate limit set for {len(ips)} IPs at {rate_pps:.0f} pps: {ips}")
        else:
            logger.warning(f"[{self.slice_id}] XDP not available, skipping uplink policing")
    
    def control_loop(self):
        """Glavni control loop - PPS based"""
        logger.info(f"[{self.slice_id}] Starting CPU controller, target={self.target_cpu}%")
        
        # Inicijalno postavi limit na safe PPS (gornja granica safe zone)
        safe_pps = self._calc_safe_pps(self.target_cpu)
        logger.info(f"[{self.slice_id}] Safe PPS for {self.target_cpu}% CPU = {safe_pps:.0f} pps")
        self.apply_pps(safe_pps)
        
        while self._running:
            # 1. Meri CPU
            cpu = self.get_current_cpu()
            self.cpu_history.append(cpu)
            
            # Smoothing
            avg_cpu = sum(self.cpu_history) / len(self.cpu_history)
            
            # 2. Dead zone: ako je CPU blizu targeta, ne menjaj PPS
            error = avg_cpu - self.target_cpu
            
            if abs(error) <= DEAD_ZONE:
                # CPU je u prihvatljivom opsegu, resetuj integral i preskoči
                self.pid.integral = 0
                time.sleep(CONTROL_INTERVAL)
                continue
            
            # Ako je CPU ispod targeta, povećaj PPS
            safe_pps = self._calc_safe_pps(self.target_cpu)
            if error < -DEAD_ZONE:
                # CPU je prenizak, povećaj PPS proporcionalno grešci
                # Veća greška = veće povećanje (ali ograničeno)
                increase = min(10000, abs(error) * 2000)  # Max 10K pps po koraku
                new_pps = self.current_pps + increase
                new_pps = min(safe_pps, new_pps)
                if new_pps > self.current_pps:
                    self.apply_pps(new_pps)
                    logger.debug(f"[{self.slice_id}] CPU={avg_cpu:.1f}% < target={self.target_cpu}%, increasing PPS to {new_pps:.0f}")
                time.sleep(CONTROL_INTERVAL)
                continue
            
            # 3. PID izračun (CPU > target, treba smanjiti PPS)
            # PID adjustment je u % CPU, konvertujemo u PPS
            adjustment_cpu = self.pid.update(avg_cpu)
            adjustment_pps = adjustment_cpu / self.cpu_coefficient if self.cpu_coefficient > 0 else 0
            
            # 4. Izračunaj novi PPS (ograničen na safe zonu)
            new_pps = self.current_pps + adjustment_pps
            new_pps = max(MIN_PPS, min(safe_pps, new_pps))
            
            # 5. Primeni ako je značajna promjena (više od 500 pps)
            if abs(new_pps - self.current_pps) >= 500:
                old_pps = self.current_pps
                self.apply_pps(new_pps)
                direction = "↓" if new_pps < old_pps else "↑"
                logger.info(f"[{self.slice_id}] PID: CPU={avg_cpu:.1f}% (target={self.target_cpu}%), PPS: {old_pps:.0f} {direction} {new_pps:.0f} (adj={adjustment_pps:.0f})")
            
            # Log status svakih 5 sekundi ako nema promena
            elif len(self.cpu_history) % 10 == 0:
                logger.info(f"[{self.slice_id}] Status: CPU={avg_cpu:.1f}% (target={self.target_cpu}%), PPS={self.current_pps:.0f} (stable)")
            
            time.sleep(CONTROL_INTERVAL)
    
    def start(self):
        """Pokreni controller u background thread-u"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self.control_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Zaustavi controller i ukloni XDP limite"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        
        # Ukloni XDP limite za ovaj slice
        if XDP_IP_AVAILABLE and _xdp_funcs:
            ips = _xdp_funcs['get_ips'](self.slice_id)
            for ip in ips:
                _xdp_funcs['remove_limit'](ip)
            logger.info(f"[{self.slice_id}] XDP rate limits removed")
    
    def set_target(self, new_target):
        """Promeni target CPU%"""
        self.target_cpu = new_target
        self.pid.setpoint = new_target
        logger.info(f"[{self.slice_id}] Target changed to {new_target}%")


# Globalni registry controllera
_controllers = {}
_controllers_lock = threading.Lock()


def start_cpu_control(slice_id, target_cpu):
    """Pokreni CPU kontrolu za slice"""
    with _controllers_lock:
        if slice_id in _controllers:
            _controllers[slice_id].set_target(target_cpu)
        else:
            ctrl = CpuController(slice_id, target_cpu)
            ctrl.start()
            _controllers[slice_id] = ctrl
    return True, f"CPU control started for {slice_id}, target={target_cpu}%"


def stop_cpu_control(slice_id):
    """Zaustavi CPU kontrolu za slice"""
    with _controllers_lock:
        if slice_id in _controllers:
            _controllers[slice_id].stop()
            del _controllers[slice_id]
            return True, f"CPU control stopped for {slice_id}"
        return False, f"No controller for {slice_id}"


def get_cpu_control_status(slice_id=None):
    """Dohvati status controllera"""
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
