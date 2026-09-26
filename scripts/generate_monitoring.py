"""One-off generator for data/monitoring.csv.

Produces 8 quarters of mock performance-monitoring history per model metric.
Thresholds follow the convention: breach of `amber` = amber RAG, breach of
`red` = red RAG, direction given by `higher_is_better`.

Run from the project root:  python scripts/generate_monitoring.py
"""

import csv
import random
from pathlib import Path

random.seed(42)

QUARTERS = ["2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"]

# metric config: (model_id, metric, start, end, noise, amber, red, higher_is_better)
SERIES = [
    ("QDB-CR-001", "Gini", 0.58, 0.56, 0.010, 0.50, 0.45, True),
    ("QDB-CR-001", "PSI", 0.04, 0.09, 0.008, 0.10, 0.25, False),
    ("QDB-CR-002", "Gini", 0.55, 0.46, 0.012, 0.50, 0.45, True),
    ("QDB-CR-002", "PSI", 0.06, 0.13, 0.010, 0.10, 0.25, False),
    ("QDB-CR-003", "Gini", 0.52, 0.51, 0.015, 0.45, 0.40, True),
    ("QDB-CR-003", "Override Rate (%)", 28.0, 31.0, 1.5, 15.0, 25.0, False),
    ("QDB-CR-004", "Claims Ratio vs Expected (%)", 108.0, 142.0, 4.0, 115.0, 130.0, False),
    ("QDB-CR-005", "Gini", 0.71, 0.69, 0.012, 0.60, 0.55, True),
    ("QDB-CR-005", "PSI", 0.03, 0.06, 0.008, 0.10, 0.25, False),
    ("QDB-IF-001", "PD Backtest Ratio", 1.02, 1.06, 0.02, 1.20, 1.40, False),
    ("QDB-IF-001", "PSI", 0.04, 0.07, 0.008, 0.10, 0.25, False),
    ("QDB-IF-002", "LGD Backtest Ratio", 1.05, 1.12, 0.03, 1.15, 1.30, False),
    ("QDB-IF-003", "CCF Backtest Ratio", 0.92, 0.95, 0.02, 1.10, 1.25, False),
    ("QDB-IF-004", "Stage 2 Ratio (%)", 8.5, 9.8, 0.4, 14.0, 18.0, False),
    ("QDB-IF-004", "Staging Override Rate (%)", 3.5, 4.2, 0.4, 8.0, 12.0, False),
    ("QDB-IF-005", "Scenario Forecast Error (%)", 6.0, 9.5, 1.0, 10.0, 15.0, False),
    ("QDB-ML-001", "NII Forecast Error (%)", 3.0, 4.0, 0.6, 6.0, 10.0, False),
    ("QDB-ML-002", "VaR Backtesting Exceptions", 0.0, 1.0, 0.6, 3.0, 5.0, False),
    ("QDB-ML-003", "LCR Forecast Error (%)", 2.5, 4.5, 0.7, 5.0, 8.0, False),
    ("QDB-ML-004", "Price Verification Variance (%)", 0.25, 0.42, 0.05, 0.50, 0.80, False),
    ("QDB-OF-001", "False Positive Rate (%)", 96.0, 91.0, 0.8, 85.0, 92.0, False),
    ("QDB-OF-001", "SAR Conversion Rate (%)", 1.2, 2.1, 0.25, 1.5, 0.8, True),
    ("QDB-OF-002", "False Positive Rate (%)", 78.0, 72.0, 1.5, 80.0, 90.0, False),
    ("QDB-ST-001", "Capital Forecast Error (%)", 2.0, 2.8, 0.4, 5.0, 8.0, False),
    ("QDB-ST-003", "Margin Variance (%)", 4.0, 5.5, 0.7, 8.0, 12.0, False),
]


def rag(value, amber, red, higher_is_better):
    if higher_is_better:
        if value < red:
            return "Red"
        if value < amber:
            return "Amber"
        return "Green"
    if value > red:
        return "Red"
    if value > amber:
        return "Amber"
    return "Green"


def main():
    out = Path(__file__).resolve().parent.parent / "data" / "monitoring.csv"
    rows = []
    n = len(QUARTERS)
    for model_id, metric, start, end, noise, amber, red, hib in SERIES:
        for i, q in enumerate(QUARTERS):
            base = start + (end - start) * i / (n - 1)
            value = round(base + random.uniform(-noise, noise), 4)
            rows.append({
                "model_id": model_id,
                "metric": metric,
                "period": q,
                "value": value,
                "amber_threshold": amber,
                "red_threshold": red,
                "higher_is_better": hib,
                "rag": rag(value, amber, red, hib),
            })

    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
