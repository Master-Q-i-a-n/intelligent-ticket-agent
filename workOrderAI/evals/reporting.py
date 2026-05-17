import json
from datetime import datetime
from pathlib import Path


def build_summary(results_by_task: dict[str, list[dict]]) -> dict:
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tasks": {},
    }
    total_cases = 0
    total_passed = 0

    for task, results in results_by_task.items():
        task_summary = _build_task_summary(task, results)
        summary["tasks"][task] = task_summary
        total_cases += task_summary["case_count"]
        total_passed += task_summary["passed_count"]

    summary["overall"] = {
        "case_count": total_cases,
        "passed_count": total_passed,
        "pass_rate": _ratio(total_passed, total_cases),
    }
    return summary


def write_outputs(output_dir: Path, summary: dict, results_by_task: dict[str, list[dict]]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(json.dumps({"summary": summary, "results": results_by_task}, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_markdown_report(summary, results_by_task), encoding="utf-8")
    return summary_path, report_path


def render_markdown_report(summary: dict, results_by_task: dict[str, list[dict]]) -> str:
    lines = [
        "# Agent Evaluation Report",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Overall pass rate: `{summary['overall']['pass_rate']:.2%}`",
        "",
        "## Summary",
        "",
        "| Task | Cases | Passed | Pass Rate | Avg Score | Avg Latency (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for task, task_summary in summary["tasks"].items():
        lines.append(
            f"| {task} | {task_summary['case_count']} | {task_summary['passed_count']} | "
            f"{task_summary['pass_rate']:.2%} | {task_summary['average_score']:.2f} | "
            f"{task_summary['average_latency_seconds']:.2f} |"
        )

    for task, results in results_by_task.items():
        lines.extend(["", f"## {task}", ""])
        if task == "knowledge_qa":
            task_summary = summary["tasks"][task]
            lines.extend(
                [
                    f"- Refusal pass rate: `{task_summary['refusal_pass_rate']:.2%}`",
                    (
                        "- Refusal cases with returned candidate sources: "
                        f"`{task_summary['refusal_with_returned_sources_count']}`"
                    ),
                    "",
                ]
            )
        lines.append("| Case | Passed | Score | Latency (s) | Notes |")
        lines.append("| --- | --- | ---: | ---: | --- |")
        for result in results:
            notes = "; ".join(result.get("notes", [])) or "-"
            lines.append(
                f"| {result['id']} | {'yes' if result['passed'] else 'no'} | "
                f"{result['score']:.2f} | {result['latency_seconds']:.2f} | {notes} |"
            )
    lines.append("")
    return "\n".join(lines)


def _build_task_summary(task: str, results: list[dict]) -> dict:
    case_count = len(results)
    passed_count = sum(1 for item in results if item.get("passed"))
    summary = {
        "case_count": case_count,
        "passed_count": passed_count,
        "pass_rate": _ratio(passed_count, case_count),
        "average_score": _average([item.get("score", 0.0) for item in results]),
        "average_latency_seconds": _average([item.get("latency_seconds", 0.0) for item in results]),
        "error_count": sum(1 for item in results if item.get("error")),
    }

    if task == "classification":
        fields = ("problem_type", "priority", "user_sentiment")
        summary["field_accuracy"] = {
            field: _average(
                [
                    float(item.get("rule_score", {}).get("field_scores", {}).get(field, False))
                    for item in results
                ]
            )
            for field in fields
        }
    elif task == "reply_suggestion":
        summary["average_tool_calls"] = _average(
            [item.get("tool_score", {}).get("tool_call_count", 0) for item in results]
        )
        summary["tool_pass_rate"] = _average(
            [float(item.get("tool_score", {}).get("passed", False)) for item in results]
        )
    elif task == "knowledge_qa":
        summary["source_hit_rate"] = _average(
            [item.get("source_score", {}).get("score", 0.0) for item in results]
        )
        refusal_results = [
            item for item in results if item.get("expected", {}).get("should_refuse")
        ]
        summary["refusal_case_count"] = len(refusal_results)
        summary["refusal_pass_rate"] = _average(
            [float(item.get("content_score", {}).get("refusal_ok", False)) for item in refusal_results]
        )
        summary["refusal_with_returned_sources_count"] = sum(
            1 for item in refusal_results if item.get("returned_sources_on_refusal")
        )

    return summary


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
