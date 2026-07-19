"""NL-to-BI — turn a natural-language question into a chart.

The SQL Agent generates and executes a safe, read-only query; this module
inspects the result shape and picks a sensible chart type (bar / line / pie /
table) with x/y mappings. Deterministic heuristics keep it demoable offline;
the LLM is only involved via the SQL Agent's own generation step.
"""
import re

_DATEISH = re.compile(r"(date|day|month|year|time|created|updated|_at)$", re.I)


def _is_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).replace(",", "").replace("%", "").strip())
        return True
    except (ValueError, AttributeError):
        return False


def _num(v):
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return 0


def infer_chart(question: str, columns: list[str], rows: list[list]) -> dict:
    """→ {type, x, series[], columns, rows, note}. type ∈ bar|line|pie|table."""
    if not columns or not rows:
        return {"type": "table", "x": None, "series": [], "columns": columns, "rows": rows,
                "note": "No rows returned."}

    n_cols = len(columns)
    # which columns are numeric (sampled over the first rows)?
    sample = rows[:20]
    numeric_idx = [
        i for i in range(n_cols)
        if sample and sum(1 for r in sample if i < len(r) and _is_number(r[i])) >= max(1, int(0.7 * len(sample)))
    ]
    q = question.lower()

    # single aggregate value (1 row, 1 numeric col) → table (a KPI card, really)
    if len(rows) == 1 and n_cols <= 2:
        return {"type": "table", "x": columns[0] if n_cols else None, "series": [],
                "columns": columns, "rows": rows, "note": "Single value."}

    # need a label (non-numeric) column + at least one numeric column
    label_idx = next((i for i in range(n_cols) if i not in numeric_idx), 0)
    value_idxs = [i for i in numeric_idx if i != label_idx] or (
        [i for i in range(n_cols) if i != label_idx][:1])
    if not value_idxs:
        return {"type": "table", "x": columns[label_idx], "series": [], "columns": columns, "rows": rows,
                "note": "No numeric column to plot."}

    x = columns[label_idx]
    series = [columns[i] for i in value_idxs]

    # choose type
    label_is_date = bool(_DATEISH.search(x)) or any(k in q for k in ("trend", "over time", "daily", "monthly", "timeline"))
    wants_pie = any(k in q for k in ("share", "proportion", "breakdown", "distribution", "percentage", "split"))
    if label_is_date and len(rows) >= 3:
        ctype = "line"
    elif wants_pie and len(series) == 1 and len(rows) <= 8:
        ctype = "pie"
    elif len(rows) > 40:
        ctype = "line" if label_is_date else "bar"
    else:
        ctype = "bar"

    # normalized rows for the chart: [{x: label, <series>: number, ...}]
    data = []
    for r in rows[:200]:
        row = {"x": str(r[label_idx]) if label_idx < len(r) else ""}
        for i in value_idxs:
            row[columns[i]] = _num(r[i]) if i < len(r) else 0
        data.append(row)

    return {"type": ctype, "x": x, "series": series, "columns": columns, "rows": rows, "data": data,
            "note": f"{ctype} chart · {len(rows)} rows"}
