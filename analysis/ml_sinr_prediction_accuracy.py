# Rashed-Step 13.F-08-29-2026-start
"""
Figure: SINR-prediction accuracy, persistence baseline vs the trained
HistGradientBoostingRegressor (Step 13.C), for the paper's ML-extension
performance-evaluation section.

This script does NOT re-derive the modeling logic - it imports
load_link_sequences()/build_lag_samples()/stratified_seed_split() from
ml/train_sinr_model.py directly (Step 13.C, already validated: by-
SCENARIO train/test split so consecutive, strongly-autocorrelated
samples on the same link never leak across the split - see that
module's own docstring for the full rationale) and re-fits the SAME
lightly-regularized HistGradientBoostingRegressor configuration
train_sinr_model.py's own main() uses, rather than depending on a
possibly-stale ml/data/sinr_model.joblib on disk. This is a report/
figure generator, not a new modeling step.

METRICS SHOWN: MAE and RMSE (2 separate bar figures - dB is the only
unit here, no need to force both onto one dual-axis chart), each
broken into 3 groups per Step 13.C's own reporting convention:
  - "All test samples"       - every held-out sample
  - "Variable-link"           - the REAL, non-trivial test (a link
    whose SINR genuinely changes over the run)
  - "Constant-link"           - reported for TRANSPARENCY only, not the
    headline number: a link with no mobility/shadowing/interference
    variation has a mathematically constant SINR, so persistence gets
    it exactly right (0.000 dB error) by construction - any model
    "beating" persistence on the unsplit aggregate would just mean it
    has more constant-link samples in its test set, not that it
    predicts better. Keeping this group visible (not just quietly
    dropped) is itself part of the honest reporting Step 13.C
    established.

EXPECTED RESULT (already documented in Step 13.C/Project details/
Step 13.txt - this script re-derives it from the same data+model
config for the PAPER FIGURE, it does not discover it fresh): on
variable-link samples, the model does NOT beat persistence on MAE
(persistence wins - simple last-observed is a strong baseline for this
lag-only feature set) but DOES have a lower RMSE (fewer large outlier
errors, slightly worse typical-case error) - the nuanced, non-
overclaiming finding this paper's ML-extension section is built around.

Run standalone: `python -m analysis.ml_sinr_prediction_accuracy` from
the repo root (requires ml/data/sinr_packets_*.csv + manifest to
already exist - run ml/generate_sinr_dataset.py first if not).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ml.train_sinr_model import (
    LAG_K,
    MANIFEST_CSV_PATH,
    PACKETS_CSV_GLOB,
    build_lag_samples,
    load_link_sequences,
    stratified_seed_split,
)
from analysis.plot_utils import save_bar_figure

CATEGORIES = ["All test\nsamples", "Variable-link\n(real test)", "Constant-link\n(reference only)"]


def _mae_rmse(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    return mae, rmse


def generate():
    df = load_link_sequences(PACKETS_CSV_GLOB)
    samples = build_lag_samples(df, LAG_K)
    train_seeds, test_seeds = stratified_seed_split(MANIFEST_CSV_PATH)

    train = samples[samples["seed"].isin(train_seeds)]
    test = samples[samples["seed"].isin(test_seeds)]

    feature_cols = [f"lag_{j + 1}" for j in range(LAG_K)] + ["technology_is_wifi"]
    X_train, y_train = train[feature_cols], train["target"]
    X_test, y_test = test[feature_cols], test["target"]

    baseline_pred = X_test["lag_1"]

    # Same lightly-regularized config as ml/train_sinr_model.py's own
    # main() - see that module's comments for why (default hyperparams
    # overfit: 4.18 dB train MAE but 5.64 dB test MAE, worse than
    # persistence; this config narrows but doesn't close the gap, and
    # is reported honestly rather than tuned further to force a win).
    model = HistGradientBoostingRegressor(
        random_state=0, max_leaf_nodes=7, learning_rate=0.05,
        min_samples_leaf=200, l2_regularization=1.0,
    )
    model.fit(X_train, y_train)
    model_pred = model.predict(X_test)

    is_var = (test["is_constant_link"] == False).to_numpy()  # noqa: E712
    is_const = (test["is_constant_link"] == True).to_numpy()  # noqa: E712

    groups = [slice(None), is_var, is_const]  # ALL, variable, constant
    baseline_mae, baseline_rmse, model_mae, model_rmse = [], [], [], []
    for mask in groups:
        yt = y_test.to_numpy()[mask] if not isinstance(mask, slice) else y_test.to_numpy()
        bp = baseline_pred.to_numpy()[mask] if not isinstance(mask, slice) else baseline_pred.to_numpy()
        mp = model_pred[mask] if not isinstance(mask, slice) else model_pred
        b_mae, b_rmse = _mae_rmse(yt, bp)
        m_mae, m_rmse = _mae_rmse(yt, mp)
        baseline_mae.append(b_mae)
        baseline_rmse.append(b_rmse)
        model_mae.append(m_mae)
        model_rmse.append(m_rmse)

    mae_paths = save_bar_figure(
        categories=CATEGORIES,
        series={"Persistence": baseline_mae, "Model": model_mae},
        xlabel="Test-sample group",
        ylabel="Mean Absolute Error (dB)",
        output_stem="ml_sinr_prediction_mae",
    )
    rmse_paths = save_bar_figure(
        categories=CATEGORIES,
        series={"Persistence": baseline_rmse, "Model": model_rmse},
        xlabel="Test-sample group",
        ylabel="Root Mean Squared Error (dB)",
        output_stem="ml_sinr_prediction_rmse",
    )

    return {
        "baseline_mae": baseline_mae, "model_mae": model_mae,
        "baseline_rmse": baseline_rmse, "model_rmse": model_rmse,
        "n_train_seeds": len(train_seeds), "n_test_seeds": len(test_seeds),
        "n_test_samples": len(test),
    }, {"mae": mae_paths, "rmse": rmse_paths}


if __name__ == "__main__":
    results, paths = generate()
    print(f"Train seeds: {results['n_train_seeds']}  Test seeds: {results['n_test_seeds']}  "
          f"Test samples: {results['n_test_samples']}")
    print()
    print(f"{'group':>28} | {'Persist MAE':>11} {'Model MAE':>10} | {'Persist RMSE':>12} {'Model RMSE':>10}")
    print("-" * 90)
    for cat, bm, mm, br, mr in zip(
        CATEGORIES, results["baseline_mae"], results["model_mae"],
        results["baseline_rmse"], results["model_rmse"],
    ):
        cat1 = cat.replace("\n", " ")
        print(f"{cat1:>28} | {bm:>11.3f} {mm:>10.3f} | {br:>12.3f} {mr:>10.3f}")
    print()
    print(f"Saved: {paths['mae']['pdf']}")
    print(f"Saved: {paths['mae']['jpg']}")
    print(f"Saved: {paths['rmse']['pdf']}")
    print(f"Saved: {paths['rmse']['jpg']}")
# Rashed-Step 13.F-08-29-2026-end
