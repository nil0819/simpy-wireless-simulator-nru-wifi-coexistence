# Rashed-Step 14.A-08-28-2026-start
"""
Figure-generation module for the paper's results section - separate from
model/ (analytical models + validation harness) and ml/ (SINR prediction).
Every script here reuses model/'s existing, already-validated comparison
machinery (model.sweep/model.compare/model.runner) rather than re-deriving
scenario setup by hand, then renders the results as publication-quality
figures via analysis/plot_utils.py into analysis/generated/.

Standalone toolkit - not imported by the simulator's own runtime, same
convention as model/compare.py, model/sweep.py, ml/predictor.py.
"""
# Rashed-Step 14.A-08-28-2026-end
