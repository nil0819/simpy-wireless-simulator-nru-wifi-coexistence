# Rashed-Step 13.C-08-23-2026-start
"""
Step 13.C: baseline + first learned model for SINR/channel-quality
prediction, trained on the dataset ml/generate_sinr_dataset.py (Step
13.B) built. See "Project details/Step 13.txt" for the full design.

FRAMING (Step 13.txt decision 3): pure lag-based/autoregressive - the
input is the last LAG_K measured SINR values on a given link (plus
which technology it is), the target is the NEXT measured SINR on that
same link. No per-packet contextual columns (distance, live
interferer count) - variation ACROSS the Step 13.B scenarios is what
this is meant to generalize over, not per-row context.

THE STATIC-LINK PROBLEM (found while inspecting the Step 13.B dataset,
not something this script discovered on its own): a link with no
mobility, no shadowing, and no interference overlap has a mathematically
CONSTANT SINR across every transmission - channel.shadow_db() caches
one shadow draw per (tx_id, rx_pos) and reuses it for the link's whole
life (Step 5.B), and path loss only depends on distance, which never
changes for a static pair. 8 of the Step 13.B dataset's 84 links are
exactly constant this way. A persistence baseline gets those exactly
right for free, which would make ANY model (or no model at all) look
artificially good if constant-link samples aren't separated out from
the real evaluation. This script tags every sample with whether its
link was constant across the WHOLE run (nunique(measured_sinr_db)==1
for that link) and reports metrics for "variable" links (the real,
non-trivial test) separately from "constant" links (reported only for
transparency, expected near-zero error, not the headline number).

TRAIN/TEST SPLIT (Step 13.txt decision 5): by SEED (=one full Step
13.B scenario), not by row - consecutive samples on the same link are
strongly autocorrelated, so a row-shuffled split would leak near-
identical adjacent-in-time samples across train/test. Stratified on
the manifest's mobility flag (12 static-scenario seeds, 12
mobile-scenario seeds in the Step 13.B grid) so both splits contain a
realistic mix of constant AND variable links, not e.g. a test set that
happens to be all-static by chance.

Run: `python3 ml/train_sinr_model.py` (after ml/generate_sinr_dataset.py
has produced ml/data/sinr_packets_*.csv + sinr_dataset_manifest.csv).

NOTE (2026-08-23): ml/generate_sinr_dataset.py originally wrote one
shared, appended-to packet CSV. Rashed asked for per-simulation
timestamped files instead (non-destructive - old sweeps aren't
overwritten by new ones). load_link_sequences() below GLOBS every
sinr_packets_*.csv under ml/data/ and concatenates them, so this
script picks up everything that's ever been generated there, from any
sweep session, with no other change to the modeling logic below.
"""
import glob
import os
import random
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PACKETS_CSV_GLOB = os.path.join(_DATA_DIR, "sinr_packets_*.csv")
MANIFEST_CSV_PATH = os.path.join(_DATA_DIR, "sinr_dataset_manifest.csv")
MODEL_PATH = os.path.join(_DATA_DIR, "sinr_model.joblib")

# Number of trailing measured_sinr_db values used as features to
# predict the next one. Small on purpose - median rows/link in the
# Step 13.B dataset is 285, but the minimum is 34, so a large window
# would silently drop the thinnest links entirely.
LAG_K = 3

TEST_FRACTION = 0.25
SPLIT_RNG_SEED = 42


def load_link_sequences(packets_csv_glob: str = PACKETS_CSV_GLOB) -> pd.DataFrame:
    """Globs every per-scenario packet CSV matching packets_csv_glob,
    concatenates them, and returns the result sorted into per-link
    chronological order (seed, technology, source, destination ==
    "link", ordered by created_at_us within each link) - the ordering
    every downstream step in this file assumes. Each file's own "seed"
    column is enough to keep different scenarios' rows from ever being
    mistaken for the same link, regardless of which physical file (i.e.
    which sweep session) they came from - grouping happens on
    (seed, technology, source, destination), never on filename."""
    paths = sorted(glob.glob(packets_csv_glob))
    if not paths:
        raise FileNotFoundError(
            f"No files matched {packets_csv_glob!r} - run "
            "ml/generate_sinr_dataset.py first."
        )
    df = pd.concat((pd.read_csv(p) for p in paths), ignore_index=True)
    df["measured_sinr_db"] = pd.to_numeric(df["measured_sinr_db"], errors="coerce")
    df = df.dropna(subset=["measured_sinr_db"])
    df = df.sort_values(["seed", "technology", "source", "destination", "created_at_us"])
    return df


def build_lag_samples(df: pd.DataFrame, lag_k: int = LAG_K) -> pd.DataFrame:
    """Builds one row per (link, position) sample with columns
    lag_1..lag_k (lag_1 = most recent), technology_is_wifi, seed,
    is_constant_link, and target (the next measured_sinr_db). A link
    with fewer than lag_k+1 observations contributes no samples at all
    (not enough history yet) - this is why lag_k is kept small (see
    module docstring)."""
    rows = []
    link_cols = ["seed", "technology", "source", "destination"]
    for _, link_df in df.groupby(link_cols, sort=False):
        sinr = link_df["measured_sinr_db"].to_numpy()
        if len(sinr) <= lag_k:
            continue
        is_constant_link = bool(np.unique(sinr).size == 1)
        seed = link_df["seed"].iloc[0]
        technology_is_wifi = 1 if link_df["technology"].iloc[0] == "WiFi" else 0
        for i in range(lag_k, len(sinr)):
            lags = sinr[i - lag_k:i][::-1]  # lag_1 = most recent (index i-1)
            rows.append({
                **{f"lag_{j + 1}": lags[j] for j in range(lag_k)},
                "technology_is_wifi": technology_is_wifi,
                "seed": seed,
                "is_constant_link": is_constant_link,
                "target": sinr[i],
            })
    return pd.DataFrame(rows)


def stratified_seed_split(manifest_csv_path: str, test_fraction: float = TEST_FRACTION,
                           rng_seed: int = SPLIT_RNG_SEED):
    """Splits the manifest's seeds into train/test, stratified on the
    "mobility" column so both splits get a realistic mix of static
    (constant-SINR-prone) and mobile (genuinely variable) scenarios -
    see module docstring's TRAIN/TEST SPLIT note for why this matters
    more than it would in a dataset without the static-link issue."""
    manifest = pd.read_csv(manifest_csv_path)
    rng = random.Random(rng_seed)
    train_seeds, test_seeds = [], []
    for _, group in manifest.groupby("mobility"):
        seeds = list(group["seed"])
        rng.shuffle(seeds)
        n_test = max(1, round(len(seeds) * test_fraction))
        test_seeds += seeds[:n_test]
        train_seeds += seeds[n_test:]
    return set(train_seeds), set(test_seeds)


def evaluate(y_true, y_pred, label: str):
    if len(y_true) == 0:
        print(f"  {label}: no samples")
        return
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    print(f"  {label}: n={len(y_true)}  MAE={mae:.3f} dB  RMSE={rmse:.3f} dB")
    return mae, rmse


def main():
    matched = sorted(glob.glob(PACKETS_CSV_GLOB))
    print(f"Loading {len(matched)} files matching {PACKETS_CSV_GLOB} ...")
    df = load_link_sequences(PACKETS_CSV_GLOB)
    print(f"  {len(df)} packet rows across "
          f"{df.groupby(['seed', 'technology', 'source', 'destination']).ngroups} links")

    samples = build_lag_samples(df, LAG_K)
    print(f"Built {len(samples)} lag-{LAG_K} samples "
          f"({samples['is_constant_link'].mean() * 100:.1f}% from constant links)")

    train_seeds, test_seeds = stratified_seed_split(MANIFEST_CSV_PATH)
    print(f"Train seeds ({len(train_seeds)}): {sorted(train_seeds)}")
    print(f"Test seeds  ({len(test_seeds)}): {sorted(test_seeds)}")

    train = samples[samples["seed"].isin(train_seeds)]
    test = samples[samples["seed"].isin(test_seeds)]

    feature_cols = [f"lag_{j + 1}" for j in range(LAG_K)] + ["technology_is_wifi"]
    X_train, y_train = train[feature_cols], train["target"]
    X_test, y_test = test[feature_cols], test["target"]

    # Persistence baseline: predict next = most recent (lag_1). The
    # standard bar for channel-prediction work (see Step 13.txt
    # decision 4) - if the learned model can't beat this, it isn't
    # earning its complexity.
    baseline_pred = X_test["lag_1"]

    # Lightly-regularized hyperparameters (shallower trees, higher
    # min_samples_leaf, nonzero L2) - default hyperparameters were
    # tried first and overfit badly: 4.18 dB train MAE vs 5.64 dB test
    # MAE, actually WORSE than persistence's 4.74 dB test MAE. This
    # regularized config narrows but does NOT close that gap (see the
    # printed comparison below) - reported honestly, not tuned further
    # to force a win. See Step 13.txt's DONE section / STATUS file for
    # the full writeup and what it implies for 13.E.
    model = HistGradientBoostingRegressor(
        random_state=0, max_leaf_nodes=7, learning_rate=0.05,
        min_samples_leaf=200, l2_regularization=1.0,
    )
    model.fit(X_train, y_train)
    model_pred = model.predict(X_test)

    test_variable = test["is_constant_link"] == False  # noqa: E712 (pandas bool mask)
    test_constant = test["is_constant_link"] == True  # noqa: E712

    print("\n=== Persistence baseline (predict next = last observed) ===")
    evaluate(y_test, baseline_pred, "ALL test samples")
    evaluate(y_test[test_variable], baseline_pred[test_variable], "VARIABLE-link samples (real test)")
    evaluate(y_test[test_constant], baseline_pred[test_constant], "constant-link samples (trivial, reference only)")

    print("\n=== HistGradientBoostingRegressor (lightly regularized) ===")
    evaluate(y_test, model_pred, "ALL test samples")
    evaluate(y_test[test_variable], model_pred[test_variable], "VARIABLE-link samples (real test)")
    evaluate(y_test[test_constant], model_pred[test_constant], "constant-link samples (trivial, reference only)")

    baseline_mae_var = mean_absolute_error(y_test[test_variable], baseline_pred[test_variable])
    model_mae_var = mean_absolute_error(y_test[test_variable], model_pred[test_variable])
    print("\n=== Honest verdict (VARIABLE-link samples, the real test) ===")
    if model_mae_var < baseline_mae_var:
        print(f"  Model MAE ({model_mae_var:.3f} dB) beats persistence ({baseline_mae_var:.3f} dB).")
    else:
        print(f"  Model MAE ({model_mae_var:.3f} dB) does NOT beat persistence ({baseline_mae_var:.3f} dB).")
        print("  Not tuned further to force a win - see this script's module docstring / Step 13.txt")
        print("  for why (train MAE beats persistence, test MAE doesn't - overfitting to only 18")
        print("  training scenarios with a lag-only feature set, caught precisely BECAUSE the")
        print("  train/test split is by scenario, not by shuffled row - see decision 5).")

    try:
        import joblib
        joblib.dump(model, MODEL_PATH)
        print(f"\nModel saved to {MODEL_PATH}")
    except ImportError:
        print("\n(joblib not installed - skipping model save, metrics above are still valid)")


if __name__ == "__main__":
    main()
# Rashed-Step 13.C-08-23-2026-end
