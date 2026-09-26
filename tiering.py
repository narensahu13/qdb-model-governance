"""Rule-based model risk tiering engine.

Each model is rated High / Medium / Low on three dimensions (materiality,
complexity, regulatory impact). Ratings map to points (High=3, Medium=2,
Low=1) and the composite score is their sum (range 3-9). Tier rules:

  Tier 1 — composite >= 7, OR Materiality = High, OR Regulatory Impact = High.
           The "highest-driver override" reflects standard MRM practice: a
           highly material or regulatory-critical model is always top tier.
  Tier 2 — composite >= 5 (and no Tier 1 trigger).
  Tier 3 — composite <= 4.

In this PoC the dimension ratings live in data/models.json (`tier_scores`);
the tier itself is always computed from them via `compute_tier`.
"""

LEVELS = ["High", "Medium", "Low"]

LEVEL_POINTS = {"High": 3, "Medium": 2, "Low": 1}

DIMENSION_LABELS = {
    "materiality": "Materiality",
    "complexity": "Complexity",
    "regulatory_impact": "Regulatory Impact",
}

# What qualifies as High / Medium / Low on each dimension.
CRITERIA = {
    "materiality": {
        "High": "Influences >10% of financing assets, reported ECL, regulatory "
                "ratios or the financial statements.",
        "Medium": "Influences 2-10% of exposures, or material management decisions.",
        "Low": "Influences <2% of exposures; advisory use only.",
    },
    "complexity": {
        "High": "Machine learning / black-box vendor model or heavy expert "
                "judgement; low transparency.",
        "Medium": "Standard statistical methods with judgement overlays.",
        "Low": "Deterministic, fully transparent rules or lookup tables.",
    },
    "regulatory_impact": {
        "High": "Output feeds financial statements, regulatory returns or "
                "statutory compliance (IFRS 9, ICAAP, LCR, AML).",
        "Medium": "Feeds internal limits / committees with regulatory visibility.",
        "Low": "Internal management information only.",
    },
}

TIER_RULES = [
    ("Tier 1", "Composite score \u2265 7, OR Materiality = High, OR Regulatory "
               "Impact = High (highest-driver override)."),
    ("Tier 2", "Composite score \u2265 5, with no Tier 1 trigger."),
    ("Tier 3", "Composite score \u2264 4."),
]


def compute_tier(materiality: str, complexity: str, regulatory_impact: str) -> dict:
    """Compute the model tier from the three dimension ratings.

    Returns a dict with keys: tier (1/2/3), composite (3-9), points
    (per-dimension points), explanation (which rule fired, human-readable).
    """
    ratings = {
        "materiality": materiality,
        "complexity": complexity,
        "regulatory_impact": regulatory_impact,
    }
    for dim, level in ratings.items():
        if level not in LEVEL_POINTS:
            raise ValueError(
                f"Invalid rating {level!r} for {DIMENSION_LABELS[dim]}; "
                f"expected one of {LEVELS}"
            )

    points = {dim: LEVEL_POINTS[level] for dim, level in ratings.items()}
    composite = sum(points.values())

    triggers = []
    if materiality == "High":
        triggers.append("Materiality is High")
    if regulatory_impact == "High":
        triggers.append("Regulatory Impact is High")
    if composite >= 7:
        triggers.append(f"composite score {composite} \u2265 7")

    if triggers:
        tier = 1
        explanation = (
            "Tier 1 — " + "; ".join(triggers)
            + ". A highly material or regulatory-critical model is always "
              "assigned the top tier (highest-driver override)."
        )
    elif composite >= 5:
        tier = 2
        explanation = (
            f"Tier 2 — composite score {composite} \u2265 5 and no Tier 1 "
            "trigger applies (materiality and regulatory impact are not High)."
        )
    else:
        tier = 3
        explanation = (
            f"Tier 3 — composite score {composite} \u2264 4 and no Tier 1 "
            "trigger applies."
        )

    return {
        "tier": tier,
        "composite": composite,
        "points": points,
        "explanation": explanation,
    }


def criteria_rows() -> list[dict]:
    """Criteria as rows for display in a table (one row per dimension)."""
    return [
        {
            "Dimension": DIMENSION_LABELS[dim],
            "High (3 pts)": CRITERIA[dim]["High"],
            "Medium (2 pts)": CRITERIA[dim]["Medium"],
            "Low (1 pt)": CRITERIA[dim]["Low"],
        }
        for dim in ("materiality", "complexity", "regulatory_impact")
    ]
