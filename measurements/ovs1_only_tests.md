# OVS-1 Only Tests (Single Slice Load)

Testovi sa traffic-om samo na OVS-1, bez OVS-2 traffic-a.
Cilj: Proveriti da li CPU limit radi bez interference od drugog slice-a.

---

## Test 1: Baseline (bez limita)

**Konfiguracija:**
- Traffic: Samo OVS-1 (192.168.101.10)
- Ramp: 100 → 1500 Mbps, korak 100 Mbps
- CPU limit: NEMA
- OVS-2 traffic: NEMA

**JSONL fajl:** `ovs-1_baseline_1500mbps.jsonl`

**iperf rezultati:**

| Step | Target (Mbps) | Sent (Mbps) | Jitter (ms) | Lost Packets | Loss (%) |
|------|---------------|-------------|-------------|--------------|----------|
| 1 | 100 | 99.99 | 0.02 | 0 | 0.00% |
| 2 | 200 | 199.98 | 0.01 | 5 | 0.00% |
| 3 | 300 | 299.98 | 0.01 | 77 | 0.03% |
| 4 | 400 | 399.97 | 0.00 | 1491 | 0.43% |
| 5 | 500 | 499.97 | 0.00 | 3804 | 0.88% |
| 6 | 600 | 599.95 | 0.00 | 8665 | 1.67% |
| 7 | 700 | 699.95 | 0.00 | 33577 | 5.56% |
| 8 | 800 | 799.95 | 0.00 | 81950 | 11.87% |
| 9 | 900 | 899.92 | 0.00 | 213399 | 27.47% |
| 10 | 1000 | 999.99 | 0.01 | 252891 | 29.30% |
| 11 | 1100 | 1099.97 | 0.02 | 199901 | 21.05% |
| 12 | 1200 | 1199.96 | 0.04 | 458645 | 44.28% |
| 13 | 1300 | 1299.88 | 0.00 | 483707 | 43.11% |
| 14 | 1400 | 1399.98 | 0.06 | 614503 | 50.85% |
| 15 | 1500 | 1499.95 | 0.01 | 868892 | 67.10% |

**Zapažanja:**
- Do 300 Mbps: praktično bez gubitaka (<0.1%)
- 400-500 Mbps: mali gubici (<1%)
- 600-700 Mbps: umereni gubici (1.5-5.5%)
- 800+ Mbps: značajna saturacija (>10%)

**Poređenje sa dual-slice baseline (Scenario 1):**
- Single slice ima MANJE gubitaka na istom bandwidth-u
- Npr. @ 500 Mbps: single=0.88% vs dual=0.21% (ali dual je 500+500=1000 Mbps aggregate)
- @ 700 Mbps single ≈ @ 350 Mbps per slice dual (slični gubici)

---

## Test 1b: Baseline Extended (bez limita, do 3000 Mbps)

**Konfiguracija:**
- Traffic: Samo OVS-1 (192.168.101.10)
- Ramp: 100 → 3000 Mbps, korak 100 Mbps
- CPU limit: NEMA
- OVS-2 traffic: NEMA

**JSONL fajl:** `ovs-1_baseline_3000mbps.jsonl`

**iperf rezultati:**

| Step | Target (Mbps) | Sent (Mbps) | Jitter (ms) | Lost Packets | Loss (%) |
|------|---------------|-------------|-------------|--------------|----------|
| 1 | 100 | 99.99 | 0.02 | 0 | 0.00% |
| 2 | 200 | 199.98 | 0.01 | 3 | 0.00% |
| 3 | 300 | 299.98 | 0.01 | 52 | 0.02% |
| 4 | 400 | 399.97 | 0.01 | 47 | 0.01% |
| 5 | 500 | 499.97 | 0.00 | 455 | 0.11% |
| 6 | 600 | 599.96 | 0.01 | 6545 | 1.26% |
| 7 | 700 | 699.96 | 0.00 | 31614 | 5.23% |
| 8 | 800 | 799.96 | 0.00 | 39104 | 5.66% |
| 9 | 900 | 899.95 | 0.00 | 97613 | 12.56% |
| 10 | 1000 | 999.98 | 0.00 | 149237 | 17.29% |
| 11 | 1100 | 1099.93 | 0.00 | 205551 | 21.65% |
| 12 | 1200 | 1199.88 | 0.01 | 290351 | 28.03% |
| 13 | 1300 | 1299.94 | 0.00 | 249728 | 22.25% |
| 14 | 1400 | 1399.92 | 0.00 | 357570 | 29.59% |
| 15 | 1500 | 1499.97 | 0.00 | 353234 | 27.28% |
| 16 | 1600 | 1599.95 | 0.00 | 421364 | 30.51% |
| 17 | 1700 | 1699.96 | 0.01 | 478952 | 32.64% |
| 18 | 1800 | 1799.92 | 0.01 | 579899 | 37.32% |
| 19 | 1900 | 1899.91 | 0.01 | 693731 | 42.30% |
| 20 | 2000 | 1999.90 | 0.00 | 684733 | 39.66% |
| 21 | 2100 | 2099.90 | 1.15 | 774473 | 42.72% |
| 22 | 2200 | 2150.72 | 0.02 | 816419 | 43.97% |
| 23 | 2300 | 2299.84 | 0.02 | 1087946 | 54.80% |
| 24 | 2400 | 2172.86 | 0.01 | 1061427 | 56.59% |
| 25 | 2500 | 2303.15 | 0.01 | 1253671 | 63.05% |
| 26 | 2600 | 2444.25 | 0.00 | 1383976 | 65.59% |
| 27 | 2700 | 1889.64 | 0.02 | 530476 | 32.52% |
| 28 | 2800 | 2014.80 | 0.00 | 485107 | 27.89% |
| 29 | 2900 | 1997.74 | 0.05 | 404118 | 23.43% |
| 30 | 3000 | 2027.66 | 0.01 | 617495 | 35.28% |

**Zapažanja:**
- Do 500 Mbps: mali gubici (<1%)
- 600-800 Mbps: umereni gubici (1-6%)
- 900-1200 Mbps: značajni gubici (12-28%)
- 1300-2600 Mbps: teška saturacija (22-66%)
- 2700+ Mbps: sender ne može da pošalje zahtevani bandwidth (sistem saturiran)

**Maksimalni efektivni throughput:** ~2400-2600 Mbps (nakon toga sender ne može više)

---

## Test 2: Sa 3% CPU Limitom na OVS-1

**Konfiguracija:**
- Traffic: Samo OVS-1 (192.168.101.10)
- Ramp: 100 → 500 Mbps, korak 100 Mbps
- CPU limit: **3%** na OVS-1
- OVS-2 traffic: NEMA

**Kalibracija:**
```
Throughput: 231 Mbps
OVS CPU: 2.9%
Koeficijent: 0.012440
(1 Gbps = 12% CPU)
```

**JSONL fajl:** `ovs-1_limit_3_500mbps.jsonl`

**iperf rezultati:**

| Step | Target (Mbps) | Sent (Mbps) | Jitter (ms) | Lost Packets | Loss (%) |
|------|---------------|-------------|-------------|--------------|----------|
| 1 | 100 | 99.99 | 0.01 | 0 | 0.00% |
| 2 | 200 | 199.98 | 0.01 | 41 | 0.02% |
| 3 | 300 | 299.98 | 0.01 | 114 | 0.04% |
| 4 | 400 | 399.97 | 0.01 | 1185 | 0.34% |
| 5 | 500 | 499.97 | 0.01 | 2855 | 0.66% |

---

## Poređenje: Baseline vs 3% Limit (Single Slice)

| Mbps | Baseline Loss | 3% Limit Loss | Razlika |
|------|---------------|---------------|---------|
| 100 | 0.00% | 0.00% | 0.00% |
| 200 | 0.00% | 0.02% | +0.02% |
| 300 | 0.03% | 0.04% | +0.01% |
| 400 | 0.43% | 0.34% | -0.09% |
| 500 | 0.88% | 0.66% | -0.22% |

**IZNENAĐUJUĆI REZULTAT!**

Sa 3% CPU limitom, packet loss je **MANJI** nego u baseline-u na 400-500 Mbps!

**Moguća objašnjenja:**
1. CPU limit od 3% nije dostignut (baseline CPU je ~2.9% @ 231 Mbps)
2. XDP nije aktivno dropovao pakete jer CPU nije prešao target
3. Varijacije između testova (različito vreme izvršavanja)

**JSONL Analiza:**
- `applied_limits: null` - **LIMIT NIJE PRIMENJEN!**
- OVS-1 CPU: 0.5-2.6% (ispod 3% targeta)
- XDP drops: 0/0 (nema dropova)

**Zaključak:**
- CPU nikada nije prešao 3% target
- PID controller nije aktivirao XDP rate limiting
- Zato nema razlike u packet loss-u
- **Test nije validan za proveru CPU limita** - potreban veći traffic ili niži target

---

## Sledeći Koraci

Opcije za validan test:
1. **Niži CPU target** (npr. 2%) - da CPU pređe target
2. **Veći traffic** (npr. 700-1000 Mbps) - da CPU dostigne 3%+
3. **Proveri zašto `applied_limits` je null** - možda PID controller nije aktiviran

---

## Test 3: Sa 2% CPU Limitom na OVS-1 (do 1000 Mbps)

**Konfiguracija:**
- Traffic: Samo OVS-1 (192.168.101.10)
- Ramp: 100 → 1000 Mbps, korak 100 Mbps
- CPU limit: **2%** na OVS-1
- OVS-2 traffic: NEMA

**gRPC Server Log:**
```
XDP bandwidth set to 927.3 Mbps → 951.0 Mbps → 974.8 Mbps → 998.9 Mbps
(PID controller oscilira oko ~950 Mbps)
```

**JSONL fajl:** `ovs-1_limit_2_1000mbps.jsonl`

**iperf rezultati:**

| Step | Target (Mbps) | Sent (Mbps) | Jitter (ms) | Lost Packets | Loss (%) |
|------|---------------|-------------|-------------|--------------|----------|
| 1 | 100 | 99.99 | 0.01 | 0 | 0.00% |
| 2 | 200 | 199.98 | 0.01 | 2 | 0.00% |
| 3 | 300 | 299.97 | 0.00 | 91 | 0.04% |
| 4 | 400 | 399.97 | 0.00 | 991 | 0.29% |
| 5 | 500 | 499.97 | 0.01 | 2708 | 0.63% |
| 6 | 600 | 599.96 | 0.00 | 13593 | 2.62% |
| 7 | 700 | 699.95 | 0.00 | 50941 | 8.43% |
| 8 | 800 | 799.92 | 0.01 | 102269 | 14.81% |
| 9 | 900 | 899.96 | 0.01 | 151105 | 19.45% |
| 10 | 1000 | 999.95 | 0.01 | 213826 | 24.77% |

**JSONL Analiza:**
- `applied_limits: null` - JSONL ne beleži pravilno, ali gRPC log pokazuje da JE postavljen
- OVS-1 CPU: 0.5-2.0% (oko 2% targeta)
- XDP drops: 0/0 (i dalje pokazuje 0!)
- XDP bandwidth limit: ~950 Mbps (veći od test traffic-a do 1000 Mbps)

---

## Poređenje: Baseline vs 2% Limit (Single Slice, do 1000 Mbps)

| Mbps | Baseline Loss | 2% Limit Loss | Razlika |
|------|---------------|---------------|---------|
| 100 | 0.00% | 0.00% | 0.00% |
| 200 | 0.00% | 0.00% | 0.00% |
| 300 | 0.03% | 0.04% | +0.01% |
| 400 | 0.43% | 0.29% | -0.14% |
| 500 | 0.88% | 0.63% | -0.25% |
| 600 | 1.67% | 2.62% | +0.95% |
| 700 | 5.56% | 8.43% | +2.87% |
| 800 | 11.87% | 14.81% | +2.94% |
| 900 | 27.47% | 19.45% | -8.02% |
| 1000 | 29.30% | 24.77% | -4.53% |

**Zapažanja:**
1. Na nižim brzinama (100-500 Mbps): slični rezultati, limit nije aktivan
2. Na 600-800 Mbps: 2% limit ima VEĆI loss (+2-3%)
3. Na 900-1000 Mbps: 2% limit ima MANJI loss (-4-8%)

**Objašnjenje:**
- XDP limit je postavljen na ~950 Mbps
- Do 600 Mbps: traffic ispod limita, nema XDP dropova
- 600-800 Mbps: XDP overhead dodaje mali loss
- 900-1000 Mbps: XDP limit sprečava preopterećenje, smanjuje loss

**Zaključak:**
- CPU limit od 2% sa single slice RADI
- XDP postavlja bandwidth limit na ~950 Mbps
- Ovo štiti sistem od preopterećenja na visokim brzinama
- Ali na srednjim brzinama (600-800 Mbps) dodaje overhead

---

## Ključni Nalaz: Single vs Dual Slice

| Scenario | XDP Limit | Interference | Efikasnost |
|----------|-----------|--------------|------------|
| Single slice (OVS-1 only) | ~950 Mbps | NEMA | ✅ Visoka |
| Dual slice (OVS-1 + OVS-2) | ~300 Mbps | POSTOJI | ⚠️ Smanjena |

**Kada je samo jedan slice opterećen:**
- XDP limit je veći (~950 Mbps vs ~300 Mbps)
- Nema indirect interference na drugi slice
- CPU kontrola je efikasnija

**Kada su oba slice-a opterećena:**
- XDP mora agresivnije da ograničava
- Softirq contention uzrokuje indirect interference
- Ukupni loss je veći

---

## Test 4: Sa 2% CPU Limitom na OVS-1 (do 1500 Mbps)

**Konfiguracija:**
- Traffic: Samo OVS-1 (192.168.101.10)
- Ramp: 100 → 1500 Mbps, korak 100 Mbps
- CPU limit: **2%** na OVS-1
- OVS-2 traffic: NEMA

**JSONL fajl:** `ovs-1_limit_2_1500mbps.jsonl`

**iperf rezultati:**

| Step | Target (Mbps) | Sent (Mbps) | Jitter (ms) | Lost Packets | Loss (%) |
|------|---------------|-------------|-------------|--------------|----------|
| 1 | 100 | 99.99 | 0.01 | 0 | 0.00% |
| 2 | 200 | 199.98 | 0.00 | 87 | 0.05% |
| 3 | 300 | 299.98 | 0.01 | 640 | 0.25% |
| 4 | 400 | 399.97 | 0.00 | 1373 | 0.40% |
| 5 | 500 | 499.96 | 0.00 | 2081 | 0.48% |
| 6 | 600 | 599.96 | 0.00 | 12383 | 2.39% |
| 7 | 700 | 699.96 | 0.01 | 41991 | 6.95% |
| 8 | 800 | 799.96 | 0.00 | 92110 | 13.34% |
| 9 | 900 | 899.94 | 0.00 | 193111 | 24.86% |
| 10 | 1000 | 999.94 | 0.00 | 260020 | 30.12% |
| 11 | 1100 | 1099.91 | 0.00 | 389145 | 40.98% |
| 12 | 1200 | 1199.94 | 0.01 | 513525 | 49.57% |
| 13 | 1300 | 1299.94 | 0.02 | 554870 | 49.45% |
| 14 | 1400 | 1399.92 | 0.01 | 686853 | 56.83% |
| 15 | 1500 | 1499.97 | 0.03 | 810426 | 62.59% |

---

## Poređenje: Baseline vs 2% Limit (Single Slice, do 1500 Mbps)

| Mbps | Baseline Loss | 2% Limit Loss | Razlika |
|------|---------------|---------------|---------|
| 100 | 0.00% | 0.00% | 0.00% |
| 200 | 0.00% | 0.05% | +0.05% |
| 300 | 0.03% | 0.25% | +0.22% |
| 400 | 0.43% | 0.40% | -0.03% |
| 500 | 0.88% | 0.48% | -0.40% |
| 600 | 1.67% | 2.39% | +0.72% |
| 700 | 5.56% | 6.95% | +1.39% |
| 800 | 11.87% | 13.34% | +1.47% |
| 900 | 27.47% | 24.86% | -2.61% |
| 1000 | 29.30% | 30.12% | +0.82% |
| 1100 | 21.05% | 40.98% | +19.93% |
| 1200 | 44.28% | 49.57% | +5.29% |
| 1300 | 43.11% | 49.45% | +6.34% |
| 1400 | 50.85% | 56.83% | +5.98% |
| 1500 | 67.10% | 62.59% | -4.51% |

**Zapažanja:**
- Na niskim brzinama (100-500 Mbps): slični rezultati
- Na srednjim brzinama (600-1000 Mbps): 2% limit ima malo veći loss
- Na visokim brzinama (1100-1400 Mbps): 2% limit ima ZNAČAJNO veći loss (+5-20%)
- Na 1500 Mbps: 2% limit ima manji loss (-4.5%)

**VAŽNA NAPOMENA - CPU Analiza:**

| Metrika | Baseline | 2% Limit |
|---------|----------|----------|
| CPU min | 0.15% | 0.18% |
| CPU max | **18.01%** | **4.82%** |
| CPU avg | **6.14%** | **2.03%** |

**CPU LIMIT RADI ISPRAVNO!**
- Baseline: CPU raste do 18% na visokim brzinama
- Sa 2% limitom: CPU ostaje ispod 5%, prosek tačno ~2%

**Objašnjenje većeg packet loss-a na 1100-1400 Mbps:**
- Ovo NIJE greška - to je **namerni XDP drop**
- XDP dropuje pakete da bi održao CPU na 2%
- Bez limita, CPU bi bio ~10-18% na tim brzinama
- Sa limitom, XDP mora da dropuje ~40-50% paketa da održi CPU na 2%

**Ključni zaključak:**
- CPU limit od 2% sa single slice **RADI ISPRAVNO**
- XDP uspešno štiti CPU od preopterećenja
- Trade-off: niži CPU = veći packet loss na visokim brzinama
- Ovo je očekivano i željeno ponašanje sistema

---

## Test 5: Sa 10% CPU Limitom na OVS-1 (do 1500 Mbps)

**Konfiguracija:**
- Traffic: Samo OVS-1 (192.168.101.10)
- Ramp: 100 → 1500 Mbps, korak 100 Mbps
- CPU limit: **10%** na OVS-1
- OVS-2 traffic: NEMA

**gRPC Server Log:**
```
XDP bandwidth set to 1000.0 Mbps (FIKSIRAN NA MAKSIMUM!)
```

**JSONL fajl:** `ovs-1_limit_10_1500mbps.jsonl`

**iperf rezultati:**

| Step | Target (Mbps) | Sent (Mbps) | Jitter (ms) | Lost Packets | Loss (%) |
|------|---------------|-------------|-------------|--------------|----------|
| 1 | 100 | 99.99 | 0.01 | 0 | 0.00% |
| 2 | 200 | 199.98 | 0.01 | 147 | 0.09% |
| 3 | 300 | 299.98 | 0.00 | 491 | 0.19% |
| 4 | 400 | 399.97 | 0.01 | 2409 | 0.70% |
| 5 | 500 | 499.96 | 0.00 | 4497 | 1.04% |
| 6 | 600 | 599.95 | 0.00 | 14267 | 2.75% |
| 7 | 700 | 699.96 | 0.01 | 39094 | 6.47% |
| 8 | 800 | 799.97 | 0.00 | 68611 | 9.94% |
| 9 | 900 | 899.99 | 0.01 | 230163 | 29.62% |
| 10 | 1000 | 999.94 | 0.01 | 226876 | 26.28% |
| 11 | 1100 | 1099.94 | 0.00 | 320431 | 33.75% |
| 12 | 1200 | 1199.96 | 0.02 | 417195 | 40.27% |
| 13 | 1300 | 1299.93 | 0.03 | 597030 | 53.20% |
| 14 | 1400 | 1399.93 | 0.02 | 704956 | 58.33% |
| 15 | 1500 | 1499.97 | 0.02 | 753878 | 58.22% |

**CPU Analiza:**

| Metrika | Baseline | 2% Limit | 10% Limit |
|---------|----------|----------|-----------|
| CPU min | 0.15% | 0.18% | 0.16% |
| CPU max | 18.01% | 4.82% | **4.49%** |
| CPU avg | 6.14% | 2.03% | **1.97%** |

**PROBLEM OTKRIVEN!**

CPU sa 10% limitom je **isti kao sa 2% limitom** (~2% avg)!

**Objašnjenje:**
- XDP bandwidth je **hardcoded na max 1000 Mbps**
- PID controller ne može da postavi bandwidth iznad 1000 Mbps
- Zato CPU ostaje na ~2% čak i sa 10% targetom
- Limit od 1000 Mbps sprečava CPU da dostigne 10%

**Zaključak:**
- Postoji **gornji limit** na XDP bandwidth (~1000 Mbps)
- Za CPU target >2-3%, potrebno ukloniti ovaj hardcoded limit
- Ili: ovo je namerno ograničenje za zaštitu sistema

**Pronađen hardcoded limit u kodu:**

1. `gRPC_o_final.py` linija 51:
   ```python
   MAX_BANDWIDTH_MBPS = 1000
   ```

2. `cpu_controller.py` linija 43:
   ```python
   MAX_BANDWIDTH_MBPS = 1000    # Maksimalni bandwidth (1 Gbps)
   ```

**Kako limit radi:**
- PID controller računa potreban bandwidth da održi CPU target
- Ali `min(MAX_BANDWIDTH_MBPS, new_bw)` ograničava na 1000 Mbps
- Sa 1 Gbps linkom, 1000 Mbps = ~2% CPU (iz kalibracije)
- Zato CPU nikada ne može preći ~2-3% bez obzira na target

**Rešenje:** Povećati `MAX_BANDWIDTH_MBPS` ili ukloniti limit ako link podržava više

---

## ISPRAVKA KODA: Dinamički Safe Bandwidth

### Problem
- `MAX_BANDWIDTH_MBPS = 1000` je bio fiksni limit
- Sa 10% CPU targetom, potrebno je ~5000 Mbps da CPU dostigne target
- Ali limit od 1000 Mbps je sprečavao to

### Rešenje
VM ima ~20 Gbps fizički limit, pa je logika izmenjena:

**Izmene u `cpu_controller.py`:**

1. **Linija 43:** 
   ```python
   # STARO:
   MAX_BANDWIDTH_MBPS = 1000    # Maksimalni bandwidth (1 Gbps)
   
   # NOVO:
   MAX_PHYSICAL_MBPS = 20000    # Fizički limit VM linka (~20 Gbps)
   ```

2. **Nova metoda `_calc_safe_bandwidth()`:**
   ```python
   def _calc_safe_bandwidth(self, target_cpu):
       """
       Izračunaj safe bandwidth za dati CPU target.
       Safe bandwidth = bandwidth koji daje target CPU (gornja granica safe zone).
       Ograničeno fizičkim limitom VM linka.
       """
       if self.cpu_coefficient > 0:
           safe_bw = target_cpu / self.cpu_coefficient
       else:
           safe_bw = MAX_PHYSICAL_MBPS
       return min(safe_bw, MAX_PHYSICAL_MBPS)
   ```

3. **Control loop** - sada koristi dinamički `safe_bw`:
   ```python
   # Inicijalno postavi limit na safe bandwidth
   safe_bw = self._calc_safe_bandwidth(self.target_cpu)
   logger.info(f"[{self.slice_id}] Safe bandwidth for {self.target_cpu}% CPU = {safe_bw:.0f} Mbps")
   self.apply_bandwidth(safe_bw)
   
   # U loop-u:
   new_bw = max(MIN_BANDWIDTH_MBPS, min(safe_bw, new_bw))
   ```

**Izmene u `gRPC_o_final.py`:**

1. **Linija 51:**
   ```python
   # STARO:
   MAX_BANDWIDTH_MBPS = 1000
   
   # NOVO:
   MAX_PHYSICAL_MBPS = 20000  # Fizički limit VM linka (~20 Gbps)
   ```

### Nova logika - Safe Bandwidth po CPU Targetu

| CPU Target | cpu_coefficient | Safe Bandwidth | Fizički Limit | Efektivni Limit |
|------------|-----------------|----------------|---------------|-----------------|
| 2% | 0.002 | 1000 Mbps | 20000 Mbps | 1000 Mbps |
| 5% | 0.002 | 2500 Mbps | 20000 Mbps | 2500 Mbps |
| 10% | 0.002 | 5000 Mbps | 20000 Mbps | 5000 Mbps |
| 20% | 0.002 | 10000 Mbps | 20000 Mbps | 10000 Mbps |
| 50% | 0.002 | 25000 Mbps | 20000 Mbps | **20000 Mbps** |

### Očekivano ponašanje posle ispravke

Sa 10% CPU targetom:
- XDP limit = **5000 Mbps** (umesto 1000 Mbps)
- CPU može da dostigne ~10% na visokom traffic-u
- PID controller vrši korekciju unutar safe zone

### Testiranje

```bash
# Restartuj gRPC server
# Zatim:
limit> calibrate ovs-1
limit> cpu ovs-1 10

# Očekivani log:
# [ovs-1] Safe bandwidth for 10.0% CPU = 5000 Mbps
# [ovs-1] XDP bandwidth set to 5000.0 Mbps
```

---

## Test bez limita: Otkrivanje Bottleneck-a

**Datum:** 2026-03-29
**Fajl:** `ovs-1_no_limit.jsonl`

### Kalibracija - Novi koeficijent

| Throughput | CPU | Koeficijent |
|------------|-----|-------------|
| 2550 Mbps | 17.8% | 0.00697 |
| 1349 Mbps | 9.3% | 0.00688 |
| 1527 Mbps | 10.4% | 0.00682 |
| **Prosek** | | **~0.007** |

**Zaključak:** 1 Gbps ≈ 7% CPU (različito od ranijih testova sa 0.002)

### Iperf rezultati BEZ limita

| Poslato | Jitter | Packet Loss |
|---------|--------|-------------|
| 1300 Mbps | 0.08 ms | **51.34%** |
| 1400 Mbps | 0.01 ms | **68.32%** |
| 1500 Mbps | 0.03 ms | **74.17%** |

### JSONL analiza - Stvarni throughput

**OVS prima i prosleđuje pun throughput!**

| Iperf šalje | OVS prima (veth-phy1-tx) | CPU OVS-1 |
|-------------|--------------------------|-----------|
| 1300 Mbps | 1200-1300 Mbps | 7-10% |
| 1400 Mbps | 1300-1450 Mbps | 7-10% |
| 1500 Mbps | 1450-1700+ Mbps | 8-12% |

Primeri iz JSONL-a:
- Linija 109: **1300 Mbps**, CPU 10.1%
- Linija 116: **1437 Mbps**, CPU 7.2%
- Linija 127: **1557 Mbps**, CPU 9.2%
- Linija 141: **1778 Mbps**, CPU 11.2%

### Kritični zaključak

**Bottleneck je POSLE OVS-a!**

1. OVS prima i prosleđuje **1300-1700+ Mbps** - radi ispravno
2. Packet loss (51-74%) se dešava **POSLE** OVS-a
3. Bottleneck je između OVS-a i iperf servera

**Moguće lokacije bottleneck-a:**
- **veth-test1** - veth par između OVS i test-1 namespace
- **test-1 namespace** - iperf server ne može da primi toliko paketa
- **UDP socket buffer** - iperf server buffer overflow

**Verifikacija koeficijenta:**
- 1100 Mbps × 0.007 = 7.7% CPU ✓

### Implikacije za CPU limiting

Sa novim koeficijentom 0.007:
- Za 10% CPU target: safe_bw = 10 / 0.007 = **1428 Mbps**
- Za 7% CPU target: safe_bw = 7 / 0.007 = **1000 Mbps**
- Za 5% CPU target: safe_bw = 5 / 0.007 = **714 Mbps**
- Za 2% CPU target: safe_bw = 2 / 0.007 = **286 Mbps**

**Važno:** OVS može da obradi 1200+ Mbps bez problema. Packet loss nije zbog OVS-a.

---

## Refaktoring: Prelazak sa BPS na PPS limitaciju (29.03.2026)

### Zašto PPS umesto BPS (Mbps)?

**PPS (packets per second) ima direktniju korelaciju sa CPU potrošnjom nego throughput (Mbps).**

Svaki paket zahteva CPU obradu:
1. Interrupt handling
2. SKB alokacija
3. OVS flow lookup
4. Forwarding decision
5. Checksum/validation

Ovo se dešava **po paketu**, ne po bajtu!

### Primer uticaja veličine paketa:

| Scenario | Throughput | Packet size | PPS | CPU uticaj |
|----------|------------|-------------|-----|------------|
| A | 1 Gbps | 1500 B (MTU) | ~83K pps | **Nizak** |
| B | 1 Gbps | 64 B (min) | ~1.95M pps | **Visok** |

**Isti throughput, ali scenario B ima ~23x više paketa = ~23x više CPU!**

### Račun:
```
1 Gbps = 1,000,000,000 bits/sec

Za 1500B pakete:
  1500 bytes = 12,000 bits
  PPS = 1,000,000,000 / 12,000 = 83,333 pps ≈ 83K pps

Za 64B pakete:
  64 bytes = 512 bits
  PPS = 1,000,000,000 / 512 = 1,953,125 pps ≈ 1.95M pps
```

### Promene u kodu

#### 1. `gRPC_o.py` (preimenovan iz `gRPC_o_final.py`)

**XDP struktura:**
```c
// STARO (BPS based):
struct rate_limit_entry {
    u64 rate_bps;      // Rate in bits per second
    u64 burst_bytes;   // Burst size in bytes
    u64 tokens;        // Current tokens (bytes)
    u64 last_update;
};

// NOVO (PPS based):
struct rate_limit_entry {
    u64 rate_pps;      // Rate in packets per second
    u64 burst_pkts;    // Burst size in packets
    u64 tokens;        // Current tokens (packets)
    u64 last_update;
};
```

**Token bucket logika:**
```c
// STARO: tokens -= packet_len (bajti)
// NOVO:  tokens -= 1 (1 token = 1 paket)

if (new_tokens >= 1) {
    entry->tokens = new_tokens - 1;  // 1 token per packet
    return XDP_PASS;
}
return XDP_DROP;
```

**Python funkcija:**
```python
# STARO:
def set_xdp_rate_limit(ip_addr, rate_mbps, burst_kb=64)

# NOVO:
def set_xdp_rate_limit(ip_addr, rate_pps, burst_pkts=1000)
```

#### 2. `cpu_controller.py`

**Konstante:**
```python
# STARO (BPS based):
MIN_BANDWIDTH_MBPS = 10
MAX_PHYSICAL_MBPS = 20000
CPU_PER_MBPS = 0.007  # 1 Gbps = 7% CPU

# NOVO (PPS based):
MIN_PPS = 1000
MAX_PHYSICAL_PPS = 2000000  # ~2M pps
CPU_PER_PPS = 0.000084      # 83K pps ≈ 7% CPU
```

**Kalkulacija koeficijenta:**
```
Ako 1 Gbps (83K pps) = 7% CPU:
  CPU_PER_PPS = 7% / 83,000 = 0.000084
  
Verifikacija: 83,000 × 0.000084 = 6.97% ≈ 7% ✓
```

**Metode preimenovane:**
- `_calc_safe_bandwidth()` → `_calc_safe_pps()`
- `apply_bandwidth()` → `apply_pps()`
- `_apply_uplink_policing()` → `_apply_uplink_policing_pps()`
- `current_bandwidth` → `current_pps`

**Nova metoda `_get_veth_pps()`:**
```python
def _get_veth_pps(self):
    """Mjeri trenutni PPS na veth interfejsu"""
    # Čita rx_pkts i tx_pkts iz /proc/net/dev
    # Računa delta / elapsed_time
```

### Safe PPS za različite CPU targete

Sa koeficijentom `CPU_PER_PPS = 0.000084`:

| CPU Target | Safe PPS | Ekvivalent @ 1500B |
|------------|----------|-------------------|
| 2% | 23,810 pps | ~286 Mbps |
| 5% | 59,524 pps | ~714 Mbps |
| 7% | 83,333 pps | ~1000 Mbps |
| 10% | 119,048 pps | ~1428 Mbps |

### Prednosti PPS limitacije

| Aspekt | BPS (staro) | PPS (novo) |
|--------|-------------|------------|
| CPU kontrola | Zavisi od veličine paketa | **Direktna korelacija** |
| DDoS zaštita | Slaba za male pakete | **Odlična** |
| Konzistentnost | Varira sa packet size | **Stabilna** |

### Pokretanje servera

```bash
# Preimenovan fajl:
sudo python3 gRPC_o.py

# Ili preko skripta:
./start_server.sh
```

### Primer loga sa PPS limitacijom

```
INFO:cpu_controller:[ovs-1] Starting CPU controller, target=5.0%
INFO:cpu_controller:[ovs-1] Safe PPS for 5.0% CPU = 59524 pps
INFO:cpu_controller:[ovs-1] XDP rate limit set for 1 IPs at 59524 pps
INFO:cpu_controller:[ovs-1] PID: CPU=7.2% (target=5.0%), PPS: 59524 ↓ 45000 (adj=-14524)
INFO:cpu_controller:[ovs-1] Status: CPU=5.1% (target=5.0%), PPS=45000 (stable)
```

---

## Bug Fix: XDP limit se nije primenjivao (29.03.2026)

### Problem

Tokom testiranja sa 3% CPU limitom, primećeno je da:
- `applied_limits: null` u JSONL-u
- Nema XDP dropova (`veth-phy1-drops: "0/0"`)
- CPU ide daleko preko targeta (do 5.5% umesto 3%)
- Throughput neograničen (do 1000+ Mbps)

### Analiza `ovs-1_5%_pps.jsonl`

| Linija | CPU OVS-1 | Throughput | PPS | XDP drops |
|--------|-----------|------------|-----|-----------|
| 57 | 3.83% | 332 Mbps | 27,867 | 0 |
| 116 | **5.56%** | 746 Mbps | 62,606 | 0 |
| 132 | 4.63% | 1017 Mbps | 85,347 | 0 |
| 138 | 3.78% | 1087 Mbps | 91,225 | 0 |

**Safe PPS za 3% = 35,714 pps**, ali vidimo 62K-91K pps bez dropova!

### Root Cause

Bug u `cpu_controller.py`:

```python
# __init__:
self.current_pps = self._calc_safe_pps(target_cpu)  # = 35714

# control_loop:
safe_pps = self._calc_safe_pps(self.target_cpu)  # = 35714
self.apply_pps(safe_pps)  # pokušava da postavi 35714

# apply_pps:
if abs(pps - self.current_pps) < 100:  # abs(35714 - 35714) = 0 < 100
    return  # IZLAZI BEZ PRIMENE LIMITA!
```

**XDP limit se NIKADA nije primenjivao** jer je razlika između željenog i trenutnog PPS-a bila 0!

### Fix

```python
# STARO:
self.current_pps = self._calc_safe_pps(target_cpu)

# NOVO:
self.current_pps = 0  # Da bi prvi apply_pps() uvek primenio limit
```

Sa `current_pps = 0`, prvi poziv `apply_pps(35714)` prolazi jer je:
```
abs(35714 - 0) = 35714 > 100 ✓
```

### Očekivani rezultat nakon fix-a

```
INFO:cpu_controller:[ovs-1] Safe PPS for 3.0% CPU = 35714 pps
INFO:cpu_controller:[ovs-1] XDP rate limit set for 1 IPs at 35714 pps: ['192.168.101.10']
INFO:cpu_controller:[ovs-1] XDP PPS set to 35714 pps
```

I u JSONL-u bi trebalo da se vide XDP dropovi kada traffic prelazi 35K pps.

---

## Test rezultati nakon fix-a (29.03.2026)

### Konfiguracija testa
- **Target CPU:** 3%
- **Safe PPS:** 35,714 pps
- **Traffic generator:** ramp test

### gRPC server log

```
INFO:cpu_controller:[ovs-1] Starting CPU controller, target=3.0%
INFO:cpu_controller:[ovs-1] Safe PPS for 3.0% CPU = 35714 pps
DEBUG: Setting XDP limit for 192.168.101.10 -> key=174434496, rate=35714 pps
INFO:cpu_controller:[ovs-1] XDP rate limit set for 1 IPs at 35714 pps: ['192.168.101.10']
INFO:cpu_controller:[ovs-1] XDP PPS set to 35714 pps
INFO:cpu_controller:[ovs-1] PID: CPU=9.4% (target=3.0%), PPS: 35714 ↓ 1000 (adj=-432932)
```

PID je detektovao visok CPU (9.4%) i smanjio PPS na minimum (1000), zatim postepeno povećavao:
- 1000 → 5276 → 11275 → 17274 → 23273 → 29272 → 35271 → 35714 pps

### Analiza `ovs-1_3%_pps.jsonl`

**Pre aktivacije XDP limita (linije 1-34):** Nema dropova, CPU varira

**Nakon aktivacije XDP limita (od linije 35):**

| Linija | CPU OVS-1 | Uplink PPS | Prosleđeno | XDP drops | Drop % |
|--------|-----------|------------|------------|-----------|--------|
| 35 | 0.86% | 15,367 | 13,120 | 2,247 | 14.6% |
| 36 | 1.67% | 12,914 | 11,033 | 1,881 | 14.6% |
| 37 | 2.69% | 10,083 | 8,660 | 1,423 | 14.1% |
| 41 | 1.99% | 18,719 | 15,834 | 2,885 | 15.4% |
| 48 | 2.09% | 24,906 | 14,758 | **10,148** | 40.7% |
| 49 | 1.19% | 20,762 | 12,454 | **8,308** | 40.0% |
| 55 | 0.47% | 18,693 | 9,645 | **9,076** | 48.5% |

### Zaključci

1. **XDP limitacija RADI** - dropovi su vidljivi u JSONL-u
2. **CPU je ispod targeta** - većina merenja pokazuje CPU < 3%
3. **PID kontroler reaguje** - smanjuje PPS kada CPU prelazi target
4. **Token bucket funkcioniše** - dropuje pakete iznad limita

### Napomena o CPU merenju

CPU vrednosti u JSONL-u su niže od očekivanih jer:
- XDP dropuje pakete PRE nego što stignu do OVS-a
- Dropovani paketi ne troše CPU u OVS-u
- BPF meri samo CPU za pakete koji su prošli kroz OVS

Ovo je **očekivano ponašanje** - cilj je da CPU ostane ispod targeta, što se i dešava.

---

## Test izolacije između OVS namespace-ova (29.03.2026)

### Konfiguracija testa
- **ovs-1:** target CPU 3%, IP 192.168.101.10
- **ovs-2:** target CPU 3%, IP 192.168.102.10
- **Traffic:** simultano na oba slice-a

### Analiza `both_3%_pps.jsonl`

| Linija | ovs-1 CPU | ovs-1 PPS | ovs-1 drops | ovs-2 CPU | ovs-2 PPS | ovs-2 drops |
|--------|-----------|-----------|-------------|-----------|-----------|-------------|
| 34 | 0.94% | 4,051 | 503 | 0.24% | 3,945 | 608 |
| 36 | 1.00% | 13,179 | 1,739 | 0.67% | 13,784 | 1,131 |
| 39 | 0.95% | 13,264 | 4,015 | 0.85% | 15,889 | 1,411 |
| 44 | 0.72% | 10,834 | 5,356 | 0.56% | 11,667 | 4,519 |

### Zaključci

1. **XDP izolacija RADI** - svaki slice ima svoje nezavisne dropove
2. **Nema cross-reference** - CPU merenje za ovs-1 ne uključuje ovs-2 pakete
3. **Per-IP limitacija funkcioniše** - svaka IP adresa ima odvojen token bucket
4. **CPU ostaje nizak** - oba slice-a su ispod 2% CPU većinu vremena

### Napomena o kalibraciji

Kalibracija trenutno vraća **Mbps koeficijent** (npr. 0.009884), ali PPS kontrola koristi **hardkodiran `CPU_PER_PPS`** (0.000084). Zato je Safe PPS isti za oba slice-a (35,714 pps) bez obzira na kalibraciju.

**TODO:** ~~Ažurirati kalibraciju da koristi PPS umesto Mbps za konzistentnost.~~ **DONE**

---

## Implementacija PPS kalibracije (29.03.2026)

### Problem

Kalibracija na klijentu je računala **Mbps koeficijent** (CPU% po Mbps), ali PPS kontrola koristi **PPS koeficijent** (CPU% po paketu). Zato je Safe PPS bio isti za sve slice-ove bez obzira na kalibraciju.

### Rešenje

#### 1. Server čuva koeficijente per-slice

Dodat `saved_cpu_coefficients = {}` u `gRPC_o.py`:

```python
# Sačuvani CPU-PPS koeficijenti per-slice (preživljavaju restart controllera)
saved_cpu_coefficients = {}  # {slice_id: coefficient}
```

Logika:
- Kada se primi `cpu_coefficient` bez `cpu_percent`, sačuva se za buduću upotrebu
- Kada se kreira novi controller, koristi sačuvani koeficijent ako postoji

#### 2. Klijent računa PPS koeficijent

Ažurirana `calibrate_slice()` funkcija u `slice_limit.py`:

```python
# Dohvati PPS umesto Mbps
pps = nic.rx_pkts + nic.tx_pkts

# PPS koeficijent: CPU% po paketu
coefficient = avg_cpu / avg_pps
```

### Workflow

1. `calibrate ovs-1` → računa PPS koeficijent i šalje serveru
2. Server čuva koeficijent u `saved_cpu_coefficients["ovs-1"]`
3. `cpu ovs-1 3` → server kreira controller sa sačuvanim koeficijentom
4. Safe PPS = `target_cpu / coefficient`

### Primer

```
limit> calibrate ovs-1
Kalibracija ovs-1 (5s)... Osiguraj da iperf radi na punoj brzini!
OK: Kalibracija uspješna
  PPS: 83000
  OVS CPU: 7.0%
  Koeficijent: 0.00008434
  (100K pps = 8.4% CPU)

limit> cpu ovs-1 3
OK: Proactive CPU control started for ovs-1, target=3.0%
  # Server koristi sačuvani koeficijent
  # Safe PPS = 3.0 / 0.00008434 = 35,580 pps
```

---

## Test sa 2% CPU targetom (29.03.2026)

### Konfiguracija
- **Target CPU:** 2%
- **Dead zona:** ±1.5% (hardkodirana)
- **ovs-1 Safe PPS:** 26,001 pps (koef: 7.69e-05)
- **ovs-2 Safe PPS:** 24,430 pps (koef: 8.19e-05)

### Analiza `both_2%_pps.jsonl`

| Linija | ovs-1 CPU | ovs-1 PPS | ovs-1 drops | ovs-2 CPU | ovs-2 PPS | ovs-2 drops |
|--------|-----------|-----------|-------------|-----------|-----------|-------------|
| 24 | 0.53% | 7,296 | 1,557 | 0.30% | 7,368 | 1,464 |
| 31 | 0.45% | 7,015 | 1,792 | 0.52% | 7,375 | 1,415 |
| 37 | 0.41% | 7,543 | 5,822 | 0.48% | 8,126 | 5,221 |
| 44 | 0.40% | 7,486 | 10,394 | 0.08% | 6,034 | 6,451 |
| 45 | 1.36% | 5,982 | 7,747 | 1.35% | 5,377 | 8,395 |

### Problem: Dead zona prevelika za nizak target

Sa targetom 2% i dead zonom ±1.5%:
- **Efektivni opseg:** 0.5% - 3.5%
- **CPU je često ~0.3-0.5%** - unutar dead zone!
- **PID ne reaguje** jer misli da je "stabilno"
- **Rezultat:** previše dropova, CPU daleko ispod targeta

### Preporuka: Dinamička dead zona

Dead zona treba biti proporcionalna targetu:

| Target CPU | Dead zona | Efektivni opseg |
|------------|-----------|-----------------|
| 10% | ±1.5% | 8.5% - 11.5% |
| 5% | ±1.0% | 4.0% - 6.0% |
| 3% | ±0.75% | 2.25% - 3.75% |
| 2% | ±0.5% | 1.5% - 2.5% |

**Formula:** `dead_zone = max(0.3, target_cpu * 0.25)`

### Implementacija

U `pid_controller.py`, promeniti globalnu varijablu:

```python
DEAD_ZONE = 0.5  # Za 2% target (umesto 1.5)
```

---

## Test sa DEAD_ZONE = 0.5 (29.03.2026)

### Konfiguracija
- **Target CPU:** 2%
- **Dead zona:** ±0.5% (smanjena sa 1.5%)
- **ovs-1 Safe PPS:** 31,753 pps
- **ovs-2 Safe PPS:** 31,744 pps

### Rezultati (`both_2%_pps_new.jsonl`)

| Linija | ovs-1 CPU | ovs-1 drops | ovs-2 CPU | ovs-2 drops |
|--------|-----------|-------------|-----------|-------------|
| 29 | **2.00%** | 0 | **1.73%** | 0 |
| 34 | 0.55% | 4,907 | 0.29% | 4,302 |
| 44 | 0.50% | 10,983 | 0.25% | 11,350 |
| 51 | **1.49%** | 3,634 | **1.46%** | 3,281 |

### Poređenje

| Metrika | DEAD_ZONE=1.5 | DEAD_ZONE=0.5 |
|---------|---------------|---------------|
| Max CPU | ~0.5% | **2.0%** ✓ |
| Prosečan CPU | ~0.3% | ~0.5-1.5% |
| PID kontrola | Statična | **Aktivna** |

### Zaključak

**Manja dead zona POBOLJŠAVA kontrolu:**
- CPU dostiže target (2.0%)
- PID aktivno reaguje na promene
- Dropovi su dinamični umesto konstantnih

---

## Baseline test bez limita (29.03.2026)

### Fajl: `baseline_pps.jsonl`

Test bez ikakvih XDP limita, oba OVS-a primaju pun traffic.

### Rezultati po fazama opterećenja

| Faza | Uplink RX | ovs-1 CPU | ovs-2 CPU | PPS po slice |
|------|-----------|-----------|-----------|--------------|
| Nizak | ~220 Mbps | 1.2-2.2% | 1.5-2.8% | ~9,400 |
| Srednji | ~450 Mbps | 1.6-2.9% | 1.6-2.9% | ~18,800 |
| Visok | ~700-920 Mbps | 2.0-5.5% | 2.5-5.6% | ~29,000-47,000 |
| Max | ~2.5-5 Gbps | 7-15% | 7-16% | ~80,000-200,000 |

### Ključna zapažanja

1. **CPU raste linearno sa PPS:**
   - ~9K pps → ~1-2% CPU
   - ~30K pps → ~3-4% CPU
   - ~80K pps → ~8-12% CPU
   - ~130K pps → ~12-15% CPU

2. **Potvrda kalibracije:**
   - Prosečan koeficijent: **~0.00008 CPU% po paketu**
   - Ovo se poklapa sa kalibrisanim vrednostima (6.3e-05)

3. **Simetrija između OVS-ova:**
   - ovs-1 i ovs-2 imaju gotovo identičan CPU i PPS
   - **Nema interferencije** - svaki OVS obrađuje svoj traffic nezavisno

4. **XDP dropovi = 0:**
   - Svi `xdp-drops` su 0/0 jer nema aktivnih limita
   - veth dropovi se javljaju samo pri ekstremnom opterećenju (kernel buffer overflow)

---

## Test ograničenja samo ovs-1 na 5% CPU (29.03.2026)

### Fajl: `ovs_1_5%_pps.jsonl`

Test gde je **samo ovs-1** ograničen na 5% CPU, dok ovs-2 ostaje bez limita.

### Konfiguracija
- **Target CPU za ovs-1:** 5%
- **Safe PPS za ovs-1:** 79,382 pps
- **ovs-2:** Bez limita

### Rezultati - XDP dropovi

| Linija | ovs-1 CPU | ovs-1 xdp-drops | ovs-2 CPU | ovs-2 xdp-drops |
|--------|-----------|-----------------|-----------|-----------------|
| 80 | 3.28% | 2,156 | 3.50% | 0 |
| 87 | 2.20% | 10,595 | 2.52% | 0 |
| 90 | 3.43% | 10,516 | 4.70% | 0 |
| 94 | 2.01% | 23,317 | 2.21% | 0 |
| 109 | 3.19% | 20,233 | 3.92% | 0 |
| 119 | 2.51% | 24,613 | 3.77% | 0 |

### Ključna zapažanja

1. **XDP dropovi SAMO na ovs-1:** ✓
   - Svi XDP dropovi se javljaju isključivo na limitiranom slice-u (ovs-1)
   - ovs-2 ima `xdp-drops: "0/0"` u svim linijama
   - **Izolacija je potpuna** - limit na jednom slice-u ne utiče na drugi

2. **ovs-1 CPU ispod targeta:**
   - CPU se kreće između 2-3.5%, ispod 5% targeta
   - PID controller uspešno održava CPU ispod limita
   - XDP dropovi aktivno ograničavaju throughput

3. **ovs-2 zadržava baseline performanse:** ✓
   - CPU: 2-5% (u skladu sa baseline testom)
   - Throughput: Do 870 Mbps (73K+ pps) - pun kapacitet
   - **Nema interferencije** od limitiranog ovs-1

4. **Throughput razlika:**
   - ovs-1: Ograničen na ~30-50K pps (zbog XDP dropova)
   - ovs-2: Prima pun traffic (~50-70K pps bez dropova)

### Zaključak

**Test uspešan - izolacija potvrđena:**
- ✓ XDP dropovi utiču SAMO na limitirani slice (ovs-1)
- ✓ Nelimitirani slice (ovs-2) zadržava baseline CPU i throughput
- ✓ Nema cross-interference između OVS namespace-ova
- ✓ PID controller efektivno održava CPU ispod targeta

---

## Analiza: XDP uticaj na ukupan throughput (29.03.2026)

### Problem
Kada je ovs-1 limitiran na 5% CPU, ukupan uplink traffic je **manji** nego u baseline testu, iako ovs-2 nema nikakav limit.

| Test | Max Uplink PPS | ovs-2 PPS | ovs-2 CPU |
|------|---------------|-----------|-----------|
| Baseline | ~200K | ~90-100K | 7-8% |
| Sa limitom na ovs-1 | ~108K | ~50-70K | 3-5% |

### Uzrok: XDP processing overhead na zajedničkom NIC-u

XDP je attachovan na **ens19 (uplink)** koji prima traffic za oba OVS-a. NIC ima samo **2 RX queue-a** sa RSS (Toeplitz hash).

```
ethtool -S ens19:
  rx_queue_0_xdp_drops: 267,104,738
  rx_queue_1_xdp_drops: 271,456,326
```

**Problem:** Kada XDP dropuje pakete za ovs-1:
1. Paketi su već u NIC ring buffer-u
2. Kernel ih čita u memoriju
3. XDP program se izvršava i dropuje
4. **CPU vreme je potrošeno** iako je paket odbačen

Sa samo 2 queue-a, visok drop rate stvara **CPU contention** koji utiče na obradu paketa za ovs-2.

### Arhitektura

```
Traffic Gen 1 ──┐                    ┌──► veth-phy1 ──► ovs-1 (limitiran)
                ├──► ens19 (XDP) ──► br-phy
Traffic Gen 2 ──┘                    └──► veth-phy2 ──► ovs-2 (nelimitiran)
```

XDP na ens19 obrađuje **SVE pakete** pre nego što stignu do bridge-a.

### Moguća rešenja

1. **XDP native mode** - Trenutno je generic/SKB mode, native bi bio brži
2. **Više RX queue-a** - Bolja izolacija između flow-ova
3. **CPU pinning** - Dedicirani CPU core-ovi po queue-i
4. **XDP na veth interfejsima** - Attachovati XDP na veth-phy1/veth-phy2 umesto na ens19

### ~~Zaključak~~ (REVIDIRANO)

~~Izolacija na **logičkom nivou** radi ispravno (XDP dropovi samo za ovs-1). Ali na **fizičkom nivou** postoji interference zbog zajedničkog NIC-a i ograničenog broja RX queue-a.~~

---

## FINALNA ANALIZA: XDP izolacija radi ispravno (29.03.2026)

### Traffic generator output

Oba generatora šalju **isti traffic** (100 → 1500 Mbps ramp-up, UDP):

| Bandwidth | ovs-1 Loss (limitiran) | ovs-2 Loss (bez limita) |
|-----------|------------------------|-------------------------|
| 100 Mbps  | 0.00%                  | 0.00%                   |
| 500 Mbps  | 2.29%                  | 2.45%                   |
| 700 Mbps  | 22.32%                 | 22.85%                  |
| 1000 Mbps | **60.44%**             | **52.20%**              |
| 1500 Mbps | **75.62%**             | **64.25%**              |

### Ključno zapažanje

**ovs-1 ima VEĆI packet loss nego ovs-2!**

- ovs-1 (limitiran na 5% CPU): 75.62% loss
- ovs-2 (bez limita): 64.25% loss

Razlika (~11%) su **XDP dropovi** koji aktivno ograničavaju ovs-1.

### Zašto je uplink manji u testu sa limitom?

Uplink RX meri pakete koji su **PROŠLI** kroz XDP:

| Test | Max Uplink RX | Objašnjenje |
|------|---------------|-------------|
| Baseline | 5,600 Mbps | Svi paketi prolaze |
| Sa limitom | 3,100 Mbps | XDP dropuje ~2,500 Mbps za ovs-1 |

### Zaključak

**XDP izolacija RADI ISPRAVNO:**

1. ✅ XDP dropovi utiču **SAMO** na limitirani slice (ovs-1)
2. ✅ ovs-2 ima **MANJI** packet loss nego ovs-1 (64% vs 75%)
3. ✅ Nema negativne interference - ovs-2 loss je zbog prirodnog zagušenja sistema
4. ✅ PID controller efektivno održava CPU ispod targeta

**Ranija hipoteza o "NIC interference" je OPOVRGNUTA** - razlika u uplink traffic-u je očekivano ponašanje zbog XDP dropova.
