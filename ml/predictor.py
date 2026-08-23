# Rashed-Step 13.D-08-23-2026-start
"""
Step 13.D: thin wrapper around the joblib model ml/train_sinr_model.py
(Step 13.C) saves, exposing a small duck-typed interface
(lag_k / predict_next()) that nru.py's rate-adaptation code can call
without importing sklearn, pandas, or this module directly - only the
CLI wiring (singleRun.py) imports SinrPredictor, keeping the
simulator core ML-agnostic (Step 13.txt design decision 6).

HONEST CONTEXT (read this before assuming this predictor "helps"):
Step 13.C's own evaluation found the lag-3 gradient-boosting model did
NOT beat a naive persistence baseline (predict next = last observed)
on MAE for held-out scenarios (5.620 dB vs 5.214 dB), though it did
beat it on RMSE (8.678 dB vs 9.678 dB - fewer large outlier errors, at
the cost of slightly worse typical-case error). This wrapper doesn't
change that result - it just makes the SAME model usable as a
rate-adaptation input instead of only an offline evaluation target.
Step 13.D's own empirical comparison (heuristic vs ML-driven NR-U rate
adaptation) is expected, going in, to show a neutral-to-mixed result
for the same reason - see "Project details/Step 13.txt"'s 13.D section
for what was actually found once that comparison ran.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


class SinrPredictor:
    """
    Loads a trained model (ml/train_sinr_model.py's MODEL_PATH output)
    and predicts the next measured_sinr_db from a short trailing
    history of past values, using the exact same lag-window framing
    the model was trained on.

    lag_k is read from ml.train_sinr_model.LAG_K (not hardcoded here a
    second time) so this wrapper can never silently drift out of sync
    with how the model was actually trained.
    """

    def __init__(self, model_path: str):
        # joblib AND the LAG_K import are both done here, not at module
        # level, so importing this FILE doesn't require sklearn/pandas
        # unless a predictor is actually constructed - matches the
        # "opt-in, zero-cost when unused" convention every other
        # feature in this codebase follows. LAG_K comes from
        # ml.train_sinr_model (not duplicated here) so this wrapper can
        # never silently drift out of sync with how the model was
        # actually trained.
        import joblib
        from ml.train_sinr_model import LAG_K
        self.model = joblib.load(model_path)
        self.lag_k = LAG_K

    def predict_next(self, history: list, technology_is_wifi: int = 0) -> float:
        """
        history: past measured_sinr_db values for one link, OLDEST
        FIRST (history[-1] is the most recent measurement - "lag_1" in
        training terms). Must have at least self.lag_k entries; the
        caller (nru.Gnb.current_mcs_for_link()) is responsible for
        falling back to non-predictor behavior when it doesn't, same
        as the model itself was never asked to predict from a link
        with too little history during training (Step 13.C's
        build_lag_samples() skips any link with <= lag_k observations).
        technology_is_wifi: 0 for NR-U (13.D's only real use site), 1
        if this is ever reused for Wi-Fi's ARF path (13.E, not built
        yet) - matches the model's own training feature.
        """
        import pandas as pd

        recent = history[-self.lag_k:]
        lags = list(reversed(recent))  # lags[0] = most recent = "lag_1"
        row = {f"lag_{i + 1}": lags[i] for i in range(self.lag_k)}
        row["technology_is_wifi"] = technology_is_wifi
        X = pd.DataFrame([row])
        return float(self.model.predict(X)[0])
# Rashed-Step 13.D-08-23-2026-end
