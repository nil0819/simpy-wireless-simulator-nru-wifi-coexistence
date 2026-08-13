# Rashed-Step pre_11.C-08-13-2026-start
"""
CAD paper's benign-scenario Discrete-Time Markov Chain (DTMC) model for
NR-U/Wi-Fi channel occupancy.

M. Rahman & M. Hossain, "Channel Access Deterrence Attack: An Attack
Against Spectrum Coexistence Between NR-U and Wi-Fi in the 5GHz Band,"
IEEE INFOCOM 2025. Benign scenario = attack probability pa=0 (Section
IV-A/IV-B, eq. 1-20 of the paper). Equations were extracted directly from
the uploaded PDF and cross-validated via two independent extraction
methods (raw text layout + word-position-sorted extraction) before being
implemented here - see "Project details/Step pre_11.txt" for the
extraction/derivation notes.

MODEL STRUCTURE
NR-U's own access cycle (backoff -> gap -> transmit, Category-3 LBT) is a
DTMC with states j = -ng, ..., -1, 0, 1, ..., Wo-1 (eq. 1-3): backoff
states 1..Wo-1 decrement each idle mini-slot and freeze (self-loop) with
probability pb when the channel is sensed busy; gap states -ng+1..-1 work
the same way with probability pg; b_{-ng} (eq. 3) is the transmission
state, and by eq. 6, NR-U's transmission probability tau_n = b_{-ng} = bo
(the same reference probability every other state is expressed as a
multiple of via the eq.5 normalization).

Wi-Fi's own transmission probability tau_w (eq. 7, cited from [23],[34]
in the paper - NOT the same formula as the classic Bianchi closed form in
bianchi.py, a different, paper-specific derivation) is a function of the
busy probability Wi-Fi itself senses.

These two chains are coupled: pb/pg sensed by NR-U = probability at least
one of w Wi-Fi APs is transmitting = 1-(1-tau_w)^w (eq. 8, "only one
NR-U user" simplification - NR-U can't sense its own transmission as
"busy"). The busy probability sensed by any ONE Wi-Fi AP = probability at
least one of the OTHER (w-1) Wi-Fi APs OR NR-U is transmitting =
1-(1-tau_w)^(w-1)*(1-tau_n) (this generalization to w>1 isn't spelled out
verbatim in the paper's text, which frames Wi-Fi's own tau_w formula as
external/cited - it's the natural w>1 extension of the w=1 case actually
worked with in the paper's own Fig. 8(a) validation, and reduces to
tau_n exactly at w=1). solve_fixed_point() below iterates both chains to
a joint (tau_w, tau_n).

Channel occupancy (Section IV-B, eq. 9-20) partitions time into 5
mutually-exclusive events (idle, Wi-Fi success, NR-U success, Wi-Fi-only
collision, Wi-Fi/NR-U collision) and reports NR-U's normalized channel
occupancy Cn as its share of the resulting mean interval. This model has
NO SINR/path-loss/capture-effect concept at all - every "collision" is a
purely combinatorial event, unlike this simulator's real PHY layer (see
Project details/Realism Validation Report.docx and Step 6.D/pre_11.txt
for the resulting, expected deviation from a real, PHY-augmented
simulator).
"""
from typing import Dict, Tuple


def wifi_tau(pb: float, Wo: int) -> float:
    """
    Eq. (7): Wi-Fi's own transmission probability given the busy
    probability pb it senses. NOT the same formula as bianchi.py's
    classic closed form - this is the CAD paper's own citation from
    [23],[34], reconstructed and cross-validated from the PDF (see
    module docstring).
    """
    num = 2.0 * (1.0 - pb)
    den = 2.0 * (1.0 - pb) ** 2 + Wo * pb + 1.0 + Wo - 2.0 * pb
    return num / den


def nru_tau(pb: float, pg: float, pa: float, ng: int, Wo: int) -> float:
    """
    Eq. (1)-(6): NR-U's own transmission probability tau_n = b_{-ng} = bo,
    solved via the eq.(5) normalization (sum of every backoff/gap state's
    probability, each expressed as a multiple of bo, equals 1).
    """
    pa_prime = pa + pg - pa * pg  # eq (4)
    # eq (1): b_j = (Wo-j)/(Wo*(1-pb)) * bo, j in [1, Wo-1]
    coef_backoff = sum((Wo - j) / (Wo * (1.0 - pb)) for j in range(1, Wo))
    # eq (2): b_j = [1-(1-pg)^(-j)] / {pg + (1-pa')[1-(1-pg)^(ng-1)]} * bo,
    # j in [-ng+1, -1]
    denom2 = pg + (1.0 - pa_prime) * (1.0 - (1.0 - pg) ** (ng - 1))
    coef_gap = sum((1.0 - (1.0 - pg) ** (-j)) / denom2 for j in range(-ng + 1, 0))
    # eq (3): b_{-ng} = bo ; plus the j=0 state itself = bo
    total_coef = 1.0 + coef_backoff + coef_gap + 1.0
    bo = 1.0 / total_coef
    return bo  # eq (6): tau_n = b_{-ng} = bo


def solve_fixed_point(w: int, Wo: int, ng: int, pa: float = 0.0, iters: int = 300,
                       tol: float = 1e-13) -> Tuple[float, float]:
    """
    Jointly solves Wi-Fi's tau_w (eq. 7) and NR-U's tau_n (eq. 1-6, 8) via
    fixed-point iteration, for w Wi-Fi APs and 1 NR-U user (matching the
    paper's own "only one NR-U user" scope, Section IV-A). pa=0.0 is the
    benign scenario (no CAD attacker) - this module only implements the
    benign case (see Project details/Step pre_11.txt for scope).

    Returns (tau_w, tau_n).
    """
    tau_w = 0.1
    tau_n = 0.1
    for _ in range(iters):
        # Busy probability sensed by one Wi-Fi AP: at least one of the
        # OTHER (w-1) Wi-Fi APs, or NR-U, is transmitting.
        pb_wifi = 1.0 - ((1.0 - tau_w) ** (w - 1)) * (1.0 - tau_n)
        tau_w_new = wifi_tau(pb_wifi, Wo)

        # Busy probability sensed by NR-U: at least one of w Wi-Fi APs is
        # transmitting (eq. 8) - "unified" pb=pg per the paper's own
        # wording.
        pb_nru = 1.0 - (1.0 - tau_w_new) ** w
        tau_n_new = nru_tau(pb_nru, pb_nru, pa, ng, Wo)

        if abs(tau_w_new - tau_w) < tol and abs(tau_n_new - tau_n) < tol:
            tau_w, tau_n = tau_w_new, tau_n_new
            break
        tau_w, tau_n = tau_w_new, tau_n_new
    return tau_w, tau_n


def channel_occupancy(
    tau_w: float,
    tau_n: float,
    w: int,
    Twp_us: float,
    Tmcot_us: float,
    Td_us: float,
    sigma_us: float,
    Tsifs_us: float,
    Tack_us: float,
    Tdifs_us: float,
    Tnc_us: float = None,
) -> Dict[str, float]:
    """
    Eq. (9)-(20): channel occupancy from converged (tau_w, tau_n).
    Tnc_us (the paper's "Tn,c", used only in eq.18's max(Tw,c, Tn,c) for
    the Wi-Fi/NR-U collision duration) defaults to Tmcot_us - confirmed
    with Rashed in Step 6.D as the paper's intended value (NR-U doesn't
    abort mid-burst on collision, so a colliding NR-U transmission still
    occupies the channel for its full mcot).

    Returns a dict with Cn (NR-U's normalized channel occupancy, eq. 20),
    Cw (the analogous Wi-Fi-success-only share, NOT a numbered equation in
    the paper - provided here as a natural companion metric), and the
    intermediate P/T values for inspection.
    """
    if Tnc_us is None:
        Tnc_us = Tmcot_us

    Pidle = (1.0 - tau_n) * (1.0 - tau_w) ** w                          # eq 9
    Tidle = sigma_us                                                     # eq 10

    Pws = w * tau_w * (1.0 - tau_w) ** (w - 1) * (1.0 - tau_n)          # eq 11
    Tws = Twp_us + Tsifs_us + Tack_us + Tdifs_us + sigma_us              # eq 12

    Pns = tau_n * (1.0 - tau_w) ** w                                    # eq 13
    Tns = Tmcot_us + Td_us + sigma_us                                    # eq 14

    Pwc = (1.0 - tau_n) * (
        1.0 - (1.0 - tau_w) ** w - w * tau_w * (1.0 - tau_w) ** (w - 1)
    )                                                                     # eq 15
    Twc = Twp_us + Tdifs_us + sigma_us                                   # eq 16

    Pnwc = 1.0 - Pidle - Pws - Pns - Pwc                                 # eq 17
    Tnwc = max(Twc, Tnc_us)                                              # eq 18

    Tinterval = Pidle * Tidle + Pws * Tws + Pns * Tns + Pwc * Twc + Pnwc * Tnwc  # eq 19
    Cn = (Pns * Tns + Pnwc * Tnwc) / Tinterval                          # eq 20
    Cw = (Pws * Tws) / Tinterval

    return {
        "Cn": Cn, "Cw": Cw,
        "Pidle": Pidle, "Pws": Pws, "Pns": Pns, "Pwc": Pwc, "Pnwc": Pnwc,
        "Tinterval": Tinterval,
    }


def predict(w: int, Wo: int, ng: int, Twp_us: float, Tmcot_us: float,
            Td_us: float = 34.0, sigma_us: float = 9.0, Tsifs_us: float = 16.0,
            Tack_us: float = 44.0, Tdifs_us: float = 34.0, pa: float = 0.0) -> Dict[str, float]:
    """
    One-call convenience wrapper: solve the fixed point, then compute
    channel occupancy. Defaults for Td_us/sigma_us/Tsifs_us/Tack_us/
    Tdifs_us match this simulator's own Times.py constants (t_difs=34,
    t_sifs=16, ACK=44, minislot sigma=9 - the same physical slot Wi-Fi's
    own backoff uses) - override them if you're modeling a different PHY
    configuration.
    """
    tau_w, tau_n = solve_fixed_point(w, Wo, ng, pa=pa)
    result = channel_occupancy(tau_w, tau_n, w, Twp_us, Tmcot_us, Td_us, sigma_us,
                                Tsifs_us, Tack_us, Tdifs_us)
    result["tau_w"] = tau_w
    result["tau_n"] = tau_n
    return result


if __name__ == "__main__":
    # Reproduces this session's two reference points (Project details/
    # Step pre_11.txt): default 242us Wi-Fi frame, and the 5400us TXOP
    # experiment (both w=1, Wo=32, ng=55, Tmcot=6ms).
    for Twp in (242.0, 5400.0):
        r = predict(w=1, Wo=32, ng=55, Twp_us=Twp, Tmcot_us=6000.0)
        print(f"Twp={Twp:>7.0f}us  tau_w={r['tau_w']:.6f}  tau_n={r['tau_n']:.6f}  "
              f"Cn={r['Cn']:.4f}  Cw={r['Cw']:.4f}")
# Rashed-Step pre_11.C-08-13-2026-end
