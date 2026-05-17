# Agent Evaluation

This package contains the first evaluation suite for the work order AI service.

## Local run

```bash
python -m workOrderAI.evals.run --suite core --mode local
```

Useful smaller runs:

```bash
python -m workOrderAI.evals.run --task classification --limit 3 --skip-judge
python -m workOrderAI.evals.run --task reply_suggestion --limit 1
```

For the first baseline, `--skip-judge` is useful when you want a faster rule-only run:

```bash
python -m workOrderAI.evals.run --suite core --mode local --skip-judge
```

If one case fails because of a transient model or network error, the local runner records that case as failed and still writes the final report.

Local results are written to `workOrderAI/evals/results/<timestamp>/`:

- `summary.json`
- `report.md`

## LangSmith

Sync datasets only:

```bash
python -m workOrderAI.evals.run --mode langsmith --sync-only
```

Run experiments:

```bash
python -m workOrderAI.evals.run --mode langsmith --experiment-prefix workorder-agent
```

The LangSmith path uses the same JSONL datasets and rule scorers as the local runner.
Dataset sync is idempotent: rerunning it updates existing examples with the same stable IDs and creates only new ones.

## Local + LangSmith

Run once, write the local report, and replay the same outputs into a LangSmith experiment:

```bash
python -m workOrderAI.evals.run --mode both --experiment-prefix workorder-agent
```

`both` does not support `--sync-only`; use `--mode langsmith --sync-only` when you only want to refresh datasets.
