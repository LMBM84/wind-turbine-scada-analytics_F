"""
Multi-model anomaly detection for wind turbine SCADA data.

Models implemented:
  1. IsolationForest      — fast, unsupervised, good for multivariate outliers
  2. StatisticalDetector  — z-score + IQR, interpretable baseline
  3. PowerCurveDetector   — physics-based: deviation from expected power curve
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from shared.models.domain import AnomalyEvent, AnomalyType, AnomalySeverity
from shared.utils.logging import get_logger
# compute_kpis lives in its own module; re-export here for backwards compatibility
from analytics.kpis.kpis import compute_kpis, MULTIVARIATE_FEATURES  # noqa: F401

logger = get_logger(__name__)

# Features used for multivariate anomaly detection
MULTIVARIATE_FEATURES = [
    "wind_speed_ms",
    "active_power_kw",
    "rotor_rpm",
    "temp_gearbox_bearing_c",
    "temp_generator_bearing_c",
    "temp_main_bearing_c",
    "pitch_angle_deg",
]


# ─────────────────────────────────────────────────────────────
#  Isolation Forest Detector
# ─────────────────────────────────────────────────────────────

class IsolationForestDetector:
    """
    Unsupervised anomaly detection using scikit-learn's IsolationForest.
    Fits on historical data, scores new observations in real-time.
    """

    def __init__(
        self,
        contamination: float = 0.02,
        n_estimators: int = 200,
        random_state: int = 42,
        features: Optional[List[str]] = None,
    ):
        self.contamination = contamination
        self.features = features or MULTIVARIATE_FEATURES
        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,
        )
        self.scaler = StandardScaler()
        self._fitted = False
        self._score_min: float = 0.0   # decision_function min from training data
        self._score_max: float = 1.0   # decision_function max from training data

    def fit(self, df: pd.DataFrame) -> "IsolationForestDetector":
        """Train on historical SCADA data."""
        X = self._prepare_features(df)
        if X.empty:
            raise ValueError("No valid feature data for training")

        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        # Store decision_function range from training data so that inference-time
        # normalisation is stable and comparable across different score windows.
        train_raw = self.model.decision_function(X_scaled)
        self._score_min = float(train_raw.min())
        self._score_max = float(train_raw.max())
        self._fitted = True
        logger.info(
            "IsolationForest fitted",
            samples=len(X),
            features=self.features,
            contamination=self.contamination,
        )
        return self

    def score(self, df: pd.DataFrame) -> pd.Series:
        """
        Return anomaly scores in [0, 1] where higher = more anomalous.
        sklearn's decision_function returns negative scores; we normalise.
        """
        if not self._fitted:
            raise RuntimeError("Model not fitted. Call .fit() first.")

        X = self._prepare_features(df)
        scores = np.full(len(df), np.nan)

        if not X.empty:
            X_scaled = self.scaler.transform(X)
            raw = self.model.decision_function(X_scaled)
            # Normalise using training-time range so scores are comparable across
            # different inference windows (not just min/max of the current batch).
            score_range = (self._score_max - self._score_min) + 1e-9
            normalised = 1 - (raw - self._score_min) / score_range
            normalised = normalised.clip(0.0, 1.0)  # clamp — new data may exceed training range
            scores[X.index] = normalised

        return pd.Series(scores, index=df.index, name="anomaly_score")

    def predict(self, df: pd.DataFrame, threshold: float = 0.7) -> pd.Series:
        """Return boolean mask: True = anomaly detected."""
        scores = self.score(df)
        return scores > threshold

    def to_anomaly_events(
        self,
        df: pd.DataFrame,
        turbine_id: str,
        threshold: float = 0.7,
    ) -> List[AnomalyEvent]:
        """Convert scored DataFrame rows into AnomalyEvent objects."""
        scores = self.score(df)
        anomaly_mask = scores > threshold
        events = []

        for ts in df.index[anomaly_mask]:
            score_val = float(scores.loc[ts])
            severity = _score_to_severity(score_val)
            events.append(
                AnomalyEvent(
                    anomaly_id=str(uuid.uuid4()),
                    turbine_id=turbine_id,
                    detected_at=datetime.now(tz=timezone.utc),
                    interval_start=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    anomaly_type=AnomalyType.UNKNOWN,
                    severity=severity,
                    score=round(score_val, 4),
                    model_name="IsolationForest",
                    features_used=self.features,
                    description=f"Multivariate anomaly detected (score={score_val:.3f})",
                )
            )
        return events

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        available = [f for f in self.features if f in df.columns]
        X = df[available].copy()
        X = X.dropna()
        return X


# ─────────────────────────────────────────────────────────────
#  Statistical Detector (z-score / IQR per signal)
# ─────────────────────────────────────────────────────────────

class StatisticalDetector:
    """
    Per-signal z-score and IQR anomaly detection.
    Simple, fast, and fully interpretable — good baseline and for alerting.
    """

    def __init__(self, z_threshold: float = 3.5, iqr_multiplier: float = 3.0):
        self.z_threshold = z_threshold
        self.iqr_multiplier = iqr_multiplier
        self._stats: Dict[str, Dict[str, float]] = {}

    def fit(self, df: pd.DataFrame, signals: Optional[List[str]] = None) -> "StatisticalDetector":
        signals = signals or [c for c in df.select_dtypes("number").columns]
        for col in signals:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            q25, q75 = series.quantile([0.25, 0.75])
            self._stats[col] = {
                "mean": float(series.mean()),
                "std": float(series.std()),
                "q25": float(q25),
                "q75": float(q75),
                "iqr": float(q75 - q25),
            }
        logger.info("StatisticalDetector fitted", signals=len(self._stats))
        return self

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return a DataFrame of per-signal boolean anomaly flags.
        Columns: f"{signal}_anomaly"
        """
        result = pd.DataFrame(index=df.index)
        for col, stats in self._stats.items():
            if col not in df.columns:
                continue
            # Z-score method
            z_score = (df[col] - stats["mean"]) / (stats["std"] + 1e-9)
            # IQR method
            iqr_lower = stats["q25"] - self.iqr_multiplier * stats["iqr"]
            iqr_upper = stats["q75"] + self.iqr_multiplier * stats["iqr"]
            # Flag if either method fires
            flag = (z_score.abs() > self.z_threshold) | (df[col] < iqr_lower) | (df[col] > iqr_upper)
            result[f"{col}_anomaly"] = flag

        return result

    def anomaly_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return rows where any signal is anomalous, with the offending signals listed."""
        flags = self.detect(df)
        any_anomaly = flags.any(axis=1)
        summary = df[any_anomaly].copy()
        summary["anomalous_signals"] = flags[any_anomaly].apply(
            lambda row: [c.replace("_anomaly", "") for c in row.index if row[c]], axis=1
        )
        return summary



# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _score_to_severity(score: float) -> AnomalySeverity:
    if score >= 0.9:
        return AnomalySeverity.CRITICAL
    elif score >= 0.8:
        return AnomalySeverity.HIGH
    elif score >= 0.7:
        return AnomalySeverity.MEDIUM
    else:
        return AnomalySeverity.LOW
