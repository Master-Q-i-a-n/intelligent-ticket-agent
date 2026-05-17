import argparse
import asyncio
import time
from datetime import datetime
from pathlib import Path

from workOrderAI.evals.datasets import TASK_FILES, load_dataset


async def collect_results(tasks: list[str], limit: int | None, skip_judge: bool) -> dict[str, list[dict]]:
    from workOrderAI.evals.runner import run_case

    results_by_task = {}
    for task in tasks:
        cases = load_dataset(task)
        if limit is not None:
            cases = cases[:limit]
        results = []
        for case in cases:
            started_at = time.perf_counter()
            try:
                results.append(await run_case(task, case, skip_judge=skip_judge))
            except Exception as exc:
                results.append(
                    {
                        "id": case["id"],
                        "task": task,
                        "input": case["input"],
                        "expected": case["expected"],
                        "actual": None,
                        "passed": False,
                        "score": 0.0,
                        "latency_seconds": time.perf_counter() - started_at,
                        "notes": [f"error: {type(exc).__name__}"],
                        "error": str(exc),
                    }
                )
        results_by_task[task] = results
    return results_by_task


async def run_local(tasks: list[str], limit: int | None, skip_judge: bool, output_dir: Path) -> tuple[Path, Path]:
    from workOrderAI.evals.reporting import build_summary, write_outputs

    results_by_task = await collect_results(tasks, limit=limit, skip_judge=skip_judge)
    summary = build_summary(results_by_task)
    return write_outputs(output_dir, summary, results_by_task)


def run_langsmith(tasks: list[str], sync_only: bool, skip_judge: bool, experiment_prefix: str | None):
    from workOrderAI.evals.langsmith_adapter import run_experiment, sync_dataset

    for task in tasks:
        if sync_only:
            sync_dataset(task)
        else:
            run_experiment(task, skip_judge=skip_judge, experiment_prefix=experiment_prefix)


def run_langsmith_from_results(results_by_task: dict[str, list[dict]], skip_judge: bool, experiment_prefix: str | None):
    from workOrderAI.evals.langsmith_adapter import run_experiment_from_results

    for task, results in results_by_task.items():
        run_experiment_from_results(
            task,
            results,
            skip_judge=skip_judge,
            experiment_prefix=experiment_prefix,
        )


def parse_args():
    parser = argparse.ArgumentParser(description="Run work order AI evaluations.")
    parser.add_argument("--suite", default="core", choices=["core"])
    parser.add_argument("--mode", default="local", choices=["local", "langsmith", "both"])
    parser.add_argument("--task", default="all", choices=["all", *TASK_FILES.keys()])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--sync-only", action="store_true")
    parser.add_argument("--experiment-prefix")
    parser.add_argument("--output-dir")
    return parser.parse_args()


def main():
    args = parse_args()
    tasks = list(TASK_FILES) if args.task == "all" else [args.task]
    if args.mode == "langsmith":
        run_langsmith(tasks, sync_only=args.sync_only, skip_judge=args.skip_judge, experiment_prefix=args.experiment_prefix)
        return
    if args.mode == "both" and args.sync_only:
        raise SystemExit("--sync-only is only supported with --mode langsmith")

    default_output_dir = Path(__file__).with_name("results") / datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir
    if args.mode == "both":
        from workOrderAI.evals.reporting import build_summary, write_outputs

        results_by_task = asyncio.run(
            collect_results(tasks, limit=args.limit, skip_judge=args.skip_judge)
        )
        summary = build_summary(results_by_task)
        summary_path, report_path = write_outputs(output_dir, summary, results_by_task)
        run_langsmith_from_results(
            results_by_task,
            skip_judge=args.skip_judge,
            experiment_prefix=args.experiment_prefix,
        )
    else:
        summary_path, report_path = asyncio.run(
            run_local(tasks, limit=args.limit, skip_judge=args.skip_judge, output_dir=output_dir)
        )
    print(f"summary: {summary_path}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
