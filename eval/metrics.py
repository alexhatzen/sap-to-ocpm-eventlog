"""Eval metrics — computed against a planner-produced ProcessPlan and
an EvalCase's expected_tables.

Honesty note on scope: ProcessPlan tracks table-level selections, not
field-level ones, so "field precision" from the original design is not
computed here — table-level precision is used instead, and stated as
such rather than mislabeled. Extending ProcessPlan to track field
selections is a natural follow-up, not done yet.
"""
from __future__ import annotations

from pydantic import BaseModel

from sap_ocpm.agents.schemas import ProcessPlan
from sap_ocpm.tools import find_join_path, get_table_schema


class EvalMetrics(BaseModel):
    case_id: str
    table_recall: float  # |expected ∩ actual| / |expected|
    table_precision: float  # |expected ∩ actual| / |actual| — table-level, NOT field-level (see module docstring)
    actual_table_count: int  # denominator for aggregate()'s hallucinated_table_rate
    hallucinated_table_rate: float  # fraction of actual tables NOT found in the KB — must be 0
    hallucinated_tables: list[str]
    join_validity_rate: float | None  # fraction of table pairs in the plan with a declared join path
    invalid_join_pairs: list[tuple[str, str]]
    missing_tables: list[str]  # expected but not in the plan
    extra_tables: list[str]  # in the plan but not expected


def compute_metrics(case_id: str, expected_tables: list[str], plan: ProcessPlan) -> EvalMetrics:
    expected = {t.upper() for t in expected_tables}
    actual = {t.upper() for t in plan.tables_referenced}

    intersection = expected & actual
    table_recall = len(intersection) / len(expected) if expected else 1.0
    table_precision = len(intersection) / len(actual) if actual else 0.0

    hallucinated = sorted(t for t in actual if not get_table_schema(t).found)
    hallucinated_rate = len(hallucinated) / len(actual) if actual else 0.0

    # join validity: every declared pair of tables in the plan's activities
    # that share an activity should have SOME declared join path between them
    invalid_pairs: list[tuple[str, str]] = []
    checked = 0
    for activity in plan.activities:
        tables = [t.upper() for t in activity.source_tables if t.upper() in actual]
        for i in range(len(tables)):
            for j in range(i + 1, len(tables)):
                checked += 1
                result = find_join_path(tables[i], tables[j])
                if not result.found:
                    invalid_pairs.append((tables[i], tables[j]))
    join_validity_rate = (checked - len(invalid_pairs)) / checked if checked else None

    return EvalMetrics(
        case_id=case_id,
        table_recall=round(table_recall, 3),
        table_precision=round(table_precision, 3),
        actual_table_count=len(actual),
        hallucinated_table_rate=round(hallucinated_rate, 3),
        hallucinated_tables=hallucinated,
        join_validity_rate=round(join_validity_rate, 3) if join_validity_rate is not None else None,
        invalid_join_pairs=invalid_pairs,
        missing_tables=sorted(expected - actual),
        extra_tables=sorted(actual - expected),
    )


class AggregateMetrics(BaseModel):
    n_cases: int
    mean_table_recall: float
    mean_table_precision: float
    hallucinated_table_rate: float  # across ALL cases combined — must be 0, reported as 0
    mean_join_validity_rate: float | None


def aggregate(metrics: list[EvalMetrics]) -> AggregateMetrics:
    n = len(metrics)
    total_hallucinated = sum(len(m.hallucinated_tables) for m in metrics)
    total_tables = sum(m.actual_table_count for m in metrics)
    join_rates = [m.join_validity_rate for m in metrics if m.join_validity_rate is not None]
    return AggregateMetrics(
        n_cases=n,
        mean_table_recall=round(sum(m.table_recall for m in metrics) / n, 3) if n else 0.0,
        mean_table_precision=round(sum(m.table_precision for m in metrics) / n, 3) if n else 0.0,
        hallucinated_table_rate=round(total_hallucinated / total_tables, 3) if total_tables else 0.0,
        mean_join_validity_rate=round(sum(join_rates) / len(join_rates), 3) if join_rates else None,
    )
