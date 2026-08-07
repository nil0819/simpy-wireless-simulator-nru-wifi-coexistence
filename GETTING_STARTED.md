# Getting Started

A guided first run of this simulator: setup, then a short hands-on look at
each of the four scenarios it supports. Each section is a real command you
can copy-paste, followed by a sentence on what it's showing you. For the
full flag reference and design/verification history, see `readme.md` and
`Project details/`.

## 1. Setup

```bash
# (optional) isolate dependencies in a virtual env
python3 -m venv env && source env/bin/activate

# install dependencies
pip install -r requirements.txt
```

Confirm everything's working by running the test suite:

```bash
pip install pytest
pytest test/
```

You should see `83 passed`. If that's clean, you're ready to run simulations.

## 2. Scenario 1 - Wi-Fi + NR-U coexistence

This is the main scenario: Wi-Fi access points (CSMA/CA) and NR-U gNBs
(Cat-4 LBT) contending for the same 5 GHz unlicensed channel, with a real
physical layer (path loss, SINR-based success/failure) underneath.

```bash
python singleRun.py --ap-number 2 --gnb-number 2 -t 1 -r 1
```

This places 2 Wi-Fi APs (each with one associated STA) and 2 NR-U gNBs
(each with one associated UE) at random positions, runs 1 simulated second,
and prints: the topology (positions/distances), per-technology
success/failure counts, channel occupancy/efficiency/collision-probability
numbers, and (since Step 8/9) packet-level delivery/latency statistics
both aggregated and broken down per node. Try `--rogue True` to swap the
first AP for a CAD-attack rogue AP instead of a benign one, or
`--shadowing-sigma-db 4 --ap-mobility-speed-mps 1.4` to add realistic
shadow fading and node movement. Run `python singleRun.py --help` for
every available flag (grouped and explained in `readme.md`).

## 3. Scenario 2 - Licensed 5G NR (standalone)

A separate, standalone scenario: a full-scheduler licensed-spectrum NR
gNB/UE model (round-robin or proportional-fair resource-block scheduling,
no LBT/contention - licensed spectrum doesn't need it). Not integrated
with the Wi-Fi/NR-U coexistence scenario above; it's its own thing.

```bash
python singleRunNR.py --gnb-number 1 --ues-per-gnb 4 -t 1 --scheduler proportional_fair
```

Prints the topology and, per gNB, the fraction of scheduled slots that
succeeded and the resulting throughput in Mbps.

## 4. Scenario 3 - Spectrum analyzer

Drops passive sniffer nodes into a real Wi-Fi + NR-U topology and has them
periodically sample the channel - the same way a real spectrum analyzer
would (point-in-time energy readings, no privileged access to what's
"really" happening in the simulation).

```bash
python singleRunSpectrum.py --ap-number 2 --gnb-number 1 --sniffer-number 2 -t 1
```

Prints, per sniffer: how often it read the channel as busy (wideband and
in-band), the mean/min/max energy it measured, and a per-technology duty
cycle breakdown (what fraction of samples saw at least one Wi-Fi
transmission visible, versus NR-U).

## 5. Scenario 4 - Packet-level attacker

Drops an attacker node into a real Wi-Fi + NR-U topology and runs it
through three phases: passively capture real packets off the channel,
transmit forged-source ("spoofed") packets claiming to be a real AP, and
re-transmit ("replay") exact copies of packets it captured earlier - all
from its own real physical position and transmit power.

```bash
python singleRunAttacker.py --ap-number 2 --gnb-number 1 -t 0.1 --spoof-target "AP 1" --spoof-count 5 --replay-max 3
```

Prints the topology, then per attacker: how many packets it captured,
how many it spoofed (with the forged source name), how many it replayed,
and its own channel occupancy - followed by the real Wi-Fi/NR-U
success/failure counts, so you can see the attack ran alongside normal
traffic rather than instead of it.

## Where to go next

- `readme.md` - full flag reference (grouped by feature area) for all four
  scenarios, plus the project's structure and citation info.
- `Project details/STATUS - resume context.txt` - a single-file summary of
  everything that's been built and why.
- `Project details/Step N.txt` - the full design/verification log for
  every step, one file per major step, each with exact numbers.
