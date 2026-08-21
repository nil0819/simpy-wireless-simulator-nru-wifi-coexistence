# Simpy Enabled Wireless Simulator

## Intro
Simulator created based on the master thesis `Jakub_Cichon_Master_s_Thesis.pdf` by Jakub Cichoń, which was based on two existing implementations:
* [Wi-Fi simulator](https://github.com/ToporPawel/DCF-Simpy)
* [NR-U simulator](https://github.com/marekzajac97/nru-channel-access)

This branch (`improved-simulator-2025`) extends that original process/collision-count-based simulator with a real physical layer (path loss, shadowing, SINR/capture-effect success decisions, per-technology MCS/frequency/bandwidth modeling, regulatory EIRP checks, node mobility), a shared real-packet abstraction (queueing/traffic models, retries, ACKs, latency/loss/jitter statistics), a protocol-agnostic generic wireless node usable as a spectrum analyzer or an attack base class, and packet-level attacker capabilities (spoofing, replay) - on top of the original Wi-Fi/NR-U CSMA/LBT coexistence logic, without changing that original access-protocol behavior. See "Project details/" for the full, chronological design/verification log of every change (one `Step N.txt` file per major step, each with a `DONE` section per sub-step listing exactly what changed and how it was verified).

**New here?** See [`GETTING_STARTED.md`](GETTING_STARTED.md) for a short, hands-on walkthrough of all four scenarios - the sections below are the full reference.

## Installation

- (Optional) Launch virtual env: `python3 -m venv env && source env/bin/activate`
- Install requirements: `pip install -r requirements.txt`
- Requirements (see `requirements.txt`):
  - click
  - simpy
  - pandas
  - matplotlib
  - scipy

## Structure

Four independent, runnable scenarios, each with its own CLI entry point and its own `simulation_*.py` driver. They share the same underlying PHY/channel model but are kept separate on purpose (a "standalone first" convention followed since Step 6.B), so extending one scenario never risks the others' already-verified behavior:

| Scenario | CLI entry point | Driver |
|---|---|---|
| Wi-Fi + NR-U unlicensed coexistence (the main scenario) | `singleRun.py` | `simulation.py` |
| Licensed 5G NR (standalone, full RB scheduler) | `singleRunNR.py` | `simulation_nr.py` |
| Passive spectrum-analyzer sniffers over real Wi-Fi/NR-U traffic | `singleRunSpectrum.py` | `simulation_spectrum.py` |
| Packet-level attacker (spoofing/replay) over real Wi-Fi/NR-U traffic | `singleRunAttacker.py` | `simulation_attacker.py` |

Code layout:
```
common/common.py       - shared constants, Pos type, rand_pos(), Frame, log()
common/common_phy.py   - path loss, shadowing, thermal noise, MCS/SINR tables,
                          spectral overlap, EIRP caps, WaypointMobility
common/packet.py        - Packet/TrafficConfig, latency/loss/jitter stats,
                          packet-level CSV export
channel/channel.py      - Channel: tx queues, ActiveTx, CCA/ED sensing, SINR
wifi/wifi.py, wifi/sta.py       - Wi-Fi AP + STA (CSMA/CA)
nru/nru.py, nru/ue.py           - NR-U gNB + UE (Cat-4 LBT, unlicensed)
nr/nr.py, nr/ue.py              - Licensed 5G NR gNB + UE (scheduled, no LBT)
generic/generic_device.py       - GenericWirelessDevice: protocol-agnostic
                                   sniff()/transmit() base class (spectrum
                                   analyzer, attacker base, or a custom-
                                   protocol node)
attacker/packet_attacker.py     - PacketAttacker (spoof/replay), built on
                                   GenericWirelessDevice
attacker/roguewificad.py,
attacker/roguewifijammer.py,
attacker/roguewifiselfbackoff.py - CAD-attack-paper-related attacker models
                                    (roguewificad.py is wired into
                                    singleRun.py's --rogue flag; the other
                                    two are standalone/not currently wired in)
test/                            - assert-based regression test suite
                                    (run via `pytest test/` or
                                    `python test/test_X.py` directly)
Project details/                 - design/verification log, one Step N.txt
                                    per major step, plus a top-level
                                    "STATUS - resume context.txt"
```

## Usage

Every scenario supports `--help` for its full, current flag list - the summaries below are grouped by feature area rather than reproduced in full, since the underlying flag set has grown substantially since Steps 5-9 and is easiest to keep accurate by reading directly from `--help`.

### Wi-Fi + NR-U coexistence (`singleRun.py`)

The main scenario: Wi-Fi APs (CSMA/CA) and NR-U gNBs (Cat-4 LBT) contending for the same 5 GHz unlicensed spectrum.

```bash
python singleRun.py --help
```

Flag groups (see `--help` for exact names/defaults/full descriptions):
- **Topology**: `--ap-number`/`--gnb-number` (required), `--area-w`/`--area-h`, `--ap-pos`/`--gnb-pos` (explicit placement), `--sta-radius`/`--ue-radius`
- **MAC parameters**: `--wifi_cw_min`/`--wifi_cw_max`/`--nru_cw_min`/`--nru_cw_max`, `--wifi_r_limit`/`--nru_r_limit`, `-m`/`--mcs-value`, `--mcot`, `-syn_slot`, `-max_des`/`-min_des`, `-nru_obser_slots`
- **PHY realism (Step 5)**: `--shadowing-sigma-db`, `--wifi-bandwidth-mhz`/`--nru-bandwidth-mhz`, `--wifi-noise-figure-db`/`--nru-noise-figure-db`, `--nru-mcs`, `--wifi-sinr-thr-db-override`/`--nru-sinr-thr-db-override`, `--wifi-freq-ghz`/`--nru-freq-ghz`, `--wifi-tx-power-dbm`/`--nru-tx-power-dbm` (checked against FCC U-NII EIRP caps at startup, warning only)
- **Mobility (Step 5.G)**: `--ap-mobility-speed-mps`, `--gnb-mobility-speed-mps`, `--sta-mobility-speed-mps`, `--ue-mobility-speed-mps`, `--mobility-pause-s`
- **Traffic model / real packets (Step 8)**: `--wifi-traffic-model`/`--nru-traffic-model` (`saturated`/`poisson`/`cbr`), `--wifi-arrival-rate-pps`/`--nru-arrival-rate-pps`, `--wifi-packet-size-bytes`/`--nru-packet-size-bytes`
- **Packet-level CSV export (Step 9.D/10.E)**: `--export-packets-csv <path>` - appends one row per packet (technology, node, id, source/destination, sizes, status, latency, traffic class) for offline analysis
- **QoS/QoE (Step 10.A-10.D, Wi-Fi)**: `--wifi-traffic-class-mix`/`--nru-traffic-class-mix` (repeatable `class=weight`, tags packets voice/video/best_effort/background), `--wifi-edca` (real 802.11e differentiated channel access per class, Wi-Fi only, requires `--wifi-traffic-model=saturated`) - printed per-class latency/loss/SLA-compliance stats and QoE scores (voice: real E-model MOS; video: a labeled heuristic proxy) come free once a class mix is set, no extra flag needed
- **Dynamic rate adaptation (Step 11)**: `--wifi-rate-adapt` (per-STA ARF - Auto Rate Fallback, Kamerman & Monteban 1997: step MCS up after 10 consecutive successes, down after 2 consecutive failures, no channel-state feedback), `--nru-rate-adapt` (per-UE CQI-style - picks the MCS whose required-SINR threshold best fits the most recently measured link SINR, approximating 3GPP UE-reported Channel Quality Indicator feedback). Both default off (`-m`/`--mcs-value` and `--nru-mcs` stay fixed for the whole run, unchanged from every pre-Step-11 run).
- **Rogue AP**: `--rogue True` (routes AP traffic through `attacker/roguewificad.py`'s CAD-attack model instead of benign Wi-Fi)

Example:
```bash
python singleRun.py --ap-number 2 --gnb-number 2 -t 1 -r 1
python singleRun.py --ap-number 1 --gnb-number 1 -t 1 -r 1 --mcot 10 -syn_slot 500 --rogue True
python singleRun.py --ap-number 2 --gnb-number 1 -t 0.1 --area-w 50 --area-h 50 --seed 1 --shadowing-sigma-db 4 --ap-mobility-speed-mps 1.4 --wifi-traffic-model poisson --export-packets-csv packets.csv
```
Sample output (2 AP / 2 gNB, defaults):
```
SEED = 1 N_stations:=2 N_gNB:=2  CW_MIN = 15 CW_MAX = 63 WiFi pcol:=0.1217 WiFi cot:=0.8879164 WiFi eff:=0.88074 gNB pcol:=0.0000 gNB cot:=0.0354 gNB eff:=0.0354  all cot:=0.9233164 all eff:=0.91614
 Wifi succ: 1631 fail: 226
 NR succ: 59 fail: 0
fairness: 0.5398053473945499
joint: 0.4984111300570852
```
(Plus, since Step 8.G/9.A, per-technology and per-node packet stats: delivery/loss counts, average/min/max/stddev/jitter/p50/p95/p99 latency. Since Step 10.C/10.D, also per-traffic-class stats with SLA-budget compliance and QoE scores - "best_effort" is the only class shown unless `--wifi/nru-traffic-class-mix` is set.)

### Licensed 5G NR, standalone (`singleRunNR.py`)

A full-scheduler licensed-spectrum NR gNB/UE model (round-robin or proportional-fair RB scheduling, numerology-based slot timing, no LBT) - built and verified standalone (Step 6.B), not integrated into the unlicensed coexistence scenario above.

```bash
python singleRunNR.py --help
python singleRunNR.py --gnb-number 1 --ues-per-gnb 4 -t 1 --scheduler proportional_fair
```

### Spectrum analyzer (`singleRunSpectrum.py`)

Drops passive `GenericWirelessDevice` sniffer nodes (Step 7.A/7.B) into a real Wi-Fi + NR-U topology and periodically samples the channel (wideband/in-band energy, busy fraction, per-technology duty cycle) - the same way a real spectrum analyzer would, with no privileged access to the simulator's internal bookkeeping.

```bash
python singleRunSpectrum.py --help
python singleRunSpectrum.py --ap-number 2 --gnb-number 1 --sniffer-number 2 -t 1
```

### Packet-level attacker (`singleRunAttacker.py`)

Drops `PacketAttacker` nodes (Step 9.C, built on `GenericWirelessDevice`) into a real Wi-Fi + NR-U topology, driven through a capture -> spoof -> replay timeline: passively sniffs real traffic, then transmits packets with a forged source identity and/or re-transmits exact captured content, from the attacker's own real physical position/power. Prints real Wi-Fi/NR-U succ/fail counts alongside the attack results, so the attack's actual channel-level impact (airtime, SINR degradation for legitimate traffic) is directly comparable to a no-attack run.

```bash
python singleRunAttacker.py --help
python singleRunAttacker.py --ap-number 2 --gnb-number 1 -t 0.1 --spoof-target "AP 1" --spoof-count 5 --replay-max 3
```

## Testing

Assert-based regression suite (no print-and-eyeball scripts for anything added since Step 5.H) - covers PHY primitives, the packet system, `GenericWirelessDevice`, and `PacketAttacker`:
```bash
pip install pytest
pytest test/
```
174 tests passing as of Step 11. Individual files are also runnable directly (`python test/test_phy_unit.py`, etc.) without pytest installed.

## Current Work Status

----> Step 1 — Add topology + distance (positions)
----> Step 2 — Add path loss + received power (RSSI)
----> Step 3 — Per-node CCA / ED-based channel sensing
----> Step 4 — Hidden/exposed terminal + SINR-based success/failure
----> Step pre_5 — Bug fixes: multi-AP/gNB topology, WiFi airtime reporting, MCS-based frame duration, rogue AP reconnected onto ED/SINR pipeline
----> Step 5 (5.A-5.I) — PHY realism: configurable placement, log-normal shadowing, real thermal noise floor, MCS-adaptive SINR thresholds, frequency/spectral-overlap-aware interference and CCA, per-technology tx queues, regulatory EIRP caps, node mobility, PHY unit test suite, GeneratorExit fix
----> Step 6 (6.A-6.E) — Real same-technology collisions (removed tx_queue serialization), standalone licensed 5G NR mode (full scheduler), airtime-undercounting-race bugfix, benign-scenario validation against a published CAD-paper DTMC model, full regression pass
----> Step 7 (7.A-7.C) — GenericWirelessDevice (protocol-agnostic sniff()/transmit() base class), spectrum-analyzer CLI scenario, shadowing/mobility/EIRP parity for that scenario
----> Step 8 (8.A-8.G) — Real Packet abstraction: Packet/TrafficConfig data structures, per-node queue with saturated/poisson/cbr traffic models, packet-size-driven Wi-Fi PPDU duration, NR-U retry-limit parity fix, r_limit-exceeded queue-routing fix, real ACK packets, latency/loss stats collector
----> Step 9 (9.A-9.D) — Extended traffic analytics (jitter/percentile latency/per-node breakdown), real Packet visibility wired into GenericWirelessDevice, packet-level attacker capabilities (spoofing + replay, PacketAttacker + a full runnable scenario), packet-level CSV export
----> Step pre_10 — readme.md full refresh to reflect Steps 5-9
----> Step 10 (10.A-10.E) — QoS/QoE: traffic-class tagging (voice/video/best_effort/background), real 802.11e EDCA differentiated channel access for Wi-Fi (per-AC virtual contention, opt-in via `--wifi-edca`), per-class latency/loss stats with SLA-budget compliance, QoE scoring (voice: real simplified ITU-T G.107 E-model MOS; video: a clearly-labeled heuristic proxy), traffic_class column added to the packet-level CSV export
----> Step pre_11 (A-E) — analytical validation `model/` package (Bianchi DCF + CAD-paper DTMC, plus a w=1..6 sweep harness), console-output cleanup (packet stats moved to `packet.log`), repo hygiene pass
----> Step 11 — dynamic per-link MCS rate adaptation: `--wifi-rate-adapt` (ARF - Auto Rate Fallback, Kamerman & Monteban 1997: blind consecutive-success/failure counters, matching real legacy 802.11 hardware), `--nru-rate-adapt` (CQI-style - picks the MCS that best fits the most recently measured link SINR, approximating 3GPP UE-reported Channel Quality Indicator feedback). Both opt-in, both default off (byte-identical to every pre-Step-11 run)

Full detail (design rationale, exact verified numbers, what was deliberately left out) for every sub-step above is in `Project details/Step N.txt`; `Project details/STATUS - resume context.txt` is the current single-file "start here" summary.

#### Citation


Please consider citing the following works if relevant to your research

- [1] Rahman, Md Rashedur, and Moinul Hossain. "Rancad: Random channel access deterrence attack against spectrum coexistence between nr-u and wi-fi on the 5ghz unlicensed band." ICC 2024-IEEE International Conference on Communications. IEEE, 2024.
- [2] Rahman, Md Rashedur, et al. "Channel Access Deterrence Attack: An Attack against Spectrum Coexistence between NR-U and Wi-Fi in the 5 GHz Band." Proceedings of IEEE INFOCOM 2025, IEEE, 2025.
- [3] J. Cichon. A Wi-Fi and NR-U Coexistence Channel Access Simulator based on the Python SimPy Library. [Online]. Available: https://github.com/CichonJakub/5G-Coexistence-SimPy.
