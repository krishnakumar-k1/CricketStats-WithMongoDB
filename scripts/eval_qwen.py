#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ask_cricket  # noqa: E402


DEFAULT_CASES = ROOT / "evals" / "qwen_eval_cases.json"
DEFAULT_TRACE_DIR = ROOT / "logs" / "eval_traces"
IPL_CASES = ROOT / "evals" / "qwen_ipl_eval_cases.json"
IPL_TRACE_DIR = ROOT / "logs" / "ipl" / "eval_traces"


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)
    if not isinstance(cases, list):
        raise ValueError(f"Expected a JSON list of eval cases: {path}")
    return cases


def normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def values_match(actual: Any, expected: Any) -> bool:
    if isinstance(expected, float):
        try:
            return math.isclose(float(actual), expected, rel_tol=0, abs_tol=0.001)
        except (TypeError, ValueError):
            return False
    return actual == expected


def check_case(case: dict[str, Any], output: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    sql = output["sql"]
    normalized = normalize_sql(sql)

    for snippet in case.get("sql_contains", []):
        if snippet not in sql and snippet not in normalized:
            failures.append(f"SQL missing expected snippet: {snippet}")

    for snippet in case.get("sql_not_contains", []):
        if snippet in sql or snippet in normalized:
            failures.append(f"SQL contains forbidden snippet: {snippet}")

    row_count_min = case.get("row_count_min")
    if row_count_min is not None and output["row_count"] < row_count_min:
        failures.append(
            f"Expected at least {row_count_min} row(s), got {output['row_count']}"
        )

    expected_first_row = case.get("first_row")
    if expected_first_row:
        if not output["rows"]:
            failures.append("Expected first row values, but query returned no rows")
        else:
            first_row = output["rows"][0]
            for column, expected in expected_first_row.items():
                actual = first_row.get(column)
                if not values_match(actual, expected):
                    failures.append(
                        f"First row {column!r}: expected {expected!r}, got {actual!r}"
                    )

    expected_rows = case.get("expected_rows", [])
    for expected_row in expected_rows:
        if not any(row_matches(row, expected_row) for row in output["rows"]):
            failures.append(f"Missing expected row values: {expected_row}")

    expected_scalar = case.get("scalar")
    if expected_scalar:
        if not output["rows"]:
            failures.append("Expected scalar value, but query returned no rows")
        else:
            first_row = output["rows"][0]
            column = expected_scalar["column"]
            expected = expected_scalar["value"]
            if expected_scalar.get("allow_any_numeric_column") and column not in first_row:
                actual = next(
                    (
                        value
                        for value in first_row.values()
                        if isinstance(value, int | float)
                    ),
                    None,
                )
            elif expected_scalar.get("allow_any_column") and column not in first_row:
                actual = next(iter(first_row.values()), None)
            else:
                actual = first_row.get(column)
            if not values_match(actual, expected):
                failures.append(
                    f"Scalar {column!r}: expected {expected!r}, got {actual!r}"
                )

    return failures


def row_matches(row: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(values_match(row.get(column), value) for column, value in expected.items())


def run_eval_case(
    case: dict[str, Any],
    schema: str,
    guide: str,
    player_names: list[str],
    trace_dir: Path | None,
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        output = ask_cricket.answer_question(
            case["question"],
            schema,
            guide,
            player_names,
            history,
            trace_dir=trace_dir,
            print_output=False,
        )
        failures = check_case(case, output)
        return {
            "name": case["name"],
            "question": case["question"],
            "status": "pass" if not failures else "fail",
            "failures": failures,
            "sql": output["sql"],
            "row_count": output["row_count"],
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        return {
            "name": case.get("name", "<unnamed>"),
            "question": case.get("question", ""),
            "status": "error",
            "failures": [f"{type(exc).__name__}: {exc}"],
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }


def print_result(result: dict[str, Any]) -> None:
    marker = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}[result["status"]]
    print(f"{marker} {result['name']} ({result['elapsed_ms']} ms)")
    if result.get("sql"):
        print("SQL:")
        print(result["sql"])
    for failure in result.get("failures", []):
        print(f"- {failure}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qwen SQL regression evals.")
    parser.add_argument(
        "--assistant",
        choices=("cricket", "ipl"),
        default="cricket",
        help="Select the database and prompt configuration.",
    )
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--trace", action="store_true", help="Write per-case traces.")
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        help="Run only the named case; may be supplied more than once.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Also write the JSON summary to this file.",
    )
    args = parser.parse_args()

    if args.assistant == "ipl":
        import ask_ipl

        ask_ipl.configure()
        cases_path = args.cases or IPL_CASES
        if args.trace_dir == DEFAULT_TRACE_DIR:
            args.trace_dir = IPL_TRACE_DIR
    else:
        cases_path = args.cases or DEFAULT_CASES

    cases = load_cases(cases_path)
    if args.name:
        requested = set(args.name)
        cases = [case for case in cases if case.get("name") in requested]
        missing = requested - {case.get("name") for case in cases}
        if missing:
            raise ValueError(f"Unknown eval case name(s): {', '.join(sorted(missing))}")
    schema = ask_cricket.get_schema()
    guide = ask_cricket.get_guide()
    player_names = ask_cricket.get_player_names()
    trace_dir = args.trace_dir if args.trace else None

    results = [
        run_eval_case(case, schema, guide, player_names, trace_dir)
        for case in cases
    ]

    passed = sum(1 for result in results if result["status"] == "pass")
    failed = len(results) - passed

    summary = {
        "passed": passed,
        "failed": failed,
        "total": len(results),
        "results": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for result in results:
            print_result(result)
        print(f"Summary: {passed}/{len(results)} passed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
