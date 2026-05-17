import json
import hashlib
import subprocess
import uuid

from langsmith import Client
from langsmith.evaluation import evaluate

from workOrderAI.evals.datasets import load_dataset
from workOrderAI.evals.judges import judge_knowledge, judge_refusal, judge_reply
from workOrderAI.evals.runner import run_case_sync
from workOrderAI.evals.scorers import (
    combine_knowledge_content_scores,
    score_answer_contains,
    score_classification,
    score_knowledge_content_judge,
    score_knowledge_sources,
    score_reply_evidence_alignment,
    score_required_facts,
    score_tool_usage,
)
from workOrderAI.utils.config import config
from workOrderAI.utils.prompt_builder import CLASSIFICATION_SYSTEM_PROMPT, RAG_SUMMARIZE_PROMPT, REPLY_SUGGESTION_AGENT_PROMPT


DATASET_PREFIX = "workorder-agent"


def dataset_name(task: str) -> str:
    return f"{DATASET_PREFIX}-{task}-v1"


def sync_dataset(task: str, client: Client | None = None) -> str:
    client = client or Client()
    name = dataset_name(task)
    try:
        client.read_dataset(dataset_name=name)
    except Exception:
        client.create_dataset(name, description=f"Work order agent {task} evaluation dataset.")

    examples = []
    for case in load_dataset(task):
        examples.append(
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}:{case['id']}")),
                "inputs": case["input"],
                "outputs": {
                    "id": case["id"],
                    "expected": case["expected"],
                    "expected_tools": case.get("expected_tools", []),
                    "forbidden_tools": case.get("forbidden_tools", []),
                    "tags": case.get("tags", []),
                },
                "metadata": {
                    "case_id": case["id"],
                    "tags": case.get("tags", []),
                },
            }
        )
    existing_example_ids = {
        str(example.id)
        for example in client.list_examples(dataset_name=name)
    }
    examples_to_create = [example for example in examples if example["id"] not in existing_example_ids]
    examples_to_update = [example for example in examples if example["id"] in existing_example_ids]
    if examples_to_create:
        client.create_examples(dataset_name=name, examples=examples_to_create)
    if examples_to_update:
        client.update_examples(dataset_name=name, updates=examples_to_update)
    return name


def run_experiment(task: str, skip_judge: bool = False, experiment_prefix: str | None = None):
    client = Client()
    name = sync_dataset(task, client=client)
    metadata = {
        "task": task,
        "git_commit": _git_commit(),
        "chat_model": config["model"]["chat_model"],
        "judge_model": config["model"].get("judge_model", config["model"]["chat_model"]),
        "prompt_fingerprint": _prompt_fingerprint(task),
    }
    return evaluate(
        lambda inputs: _predict(task, inputs),
        data=name,
        evaluators=_build_langsmith_evaluators(task, skip_judge=skip_judge),
        experiment_prefix=experiment_prefix or f"{DATASET_PREFIX}-{task}",
        metadata=metadata,
        client=client,
    )


def run_experiment_from_results(
    task: str,
    results: list[dict],
    skip_judge: bool = False,
    experiment_prefix: str | None = None,
):
    client = Client()
    name = sync_dataset(task, client=client)
    result_by_input = {
        _input_key(result["input"]): result.get("actual")
        for result in results
    }
    result_ids = {result["id"] for result in results}
    examples = [
        example
        for example in client.list_examples(dataset_name=name)
        if (example.outputs or {}).get("id") in result_ids
    ]
    metadata = {
        "task": task,
        "git_commit": _git_commit(),
        "chat_model": config["model"]["chat_model"],
        "judge_model": config["model"].get("judge_model", config["model"]["chat_model"]),
        "prompt_fingerprint": _prompt_fingerprint(task),
        "replayed_from_local_results": True,
    }
    return evaluate(
        lambda inputs: _predict_from_results(result_by_input, inputs),
        data=examples,
        evaluators=_build_langsmith_evaluators(task, skip_judge=skip_judge),
        experiment_prefix=experiment_prefix or f"{DATASET_PREFIX}-{task}",
        metadata=metadata,
        client=client,
    )


def _predict(task: str, inputs: dict) -> dict:
    synthetic_case = {
        "id": "langsmith-case",
        "input": inputs,
        "expected": {},
        "expected_tools": [],
        "forbidden_tools": [],
        "tags": [],
    }
    result = run_case_sync(task, synthetic_case, skip_judge=True)
    return result["actual"]


def _predict_from_results(result_by_input: dict[str, dict | None], inputs: dict) -> dict | None:
    return result_by_input[_input_key(inputs)]


def _input_key(inputs: dict) -> str:
    return json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_langsmith_evaluators(task: str, skip_judge: bool):
    return [_build_rule_evaluator(task, skip_judge=skip_judge)]


def _build_rule_evaluator(task: str, skip_judge: bool = False):
    def evaluator(run, example):
        expected_bundle = example.outputs or {}
        expected = expected_bundle.get("expected", {})
        outputs = run.outputs or {}
        if task == "classification":
            score = score_classification(outputs, expected)
            return {
                "results": [
                    {"key": "problem_type_accuracy", "score": score["field_scores"]["problem_type"]},
                    {"key": "priority_accuracy", "score": score["field_scores"]["priority"]},
                    {"key": "user_sentiment_accuracy", "score": score["field_scores"]["user_sentiment"]},
                    {"key": "overall_score", "score": score["score"]},
                ]
            }
        if task == "reply_suggestion":
            tool_score = score_tool_usage(
                outputs.get("tool_trace", []),
                expected_bundle.get("expected_tools", []),
                expected_bundle.get("forbidden_tools", []),
            )
            fact_score = score_required_facts(outputs.get("suggested_reply", ""), expected)
            evidence_score = score_reply_evidence_alignment(
                outputs.get("suggested_reply", ""),
                outputs.get("tool_trace", []),
            )
            judge_score = None
            if not skip_judge:
                judge_score = judge_reply(
                    example.inputs or {},
                    outputs.get("suggested_reply", ""),
                    outputs.get("tool_trace", []),
                    evidence_score,
                )
            overall_score = _reply_overall_score(tool_score, fact_score, judge_score)
            return {
                "results": [
                    {
                        "key": "tool_score",
                        "score": tool_score["score"],
                        "comment": json.dumps(
                            {
                                "missing_tools": tool_score["missing_tools"],
                                "forbidden_tools": tool_score["forbidden_tools"],
                                "tool_names": tool_score["tool_names"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "key": "fact_score",
                        "score": fact_score["score"],
                        "comment": json.dumps(
                            {
                                "missing_facts": fact_score["missing_facts"],
                                "missing_fact_groups": fact_score["missing_fact_groups"],
                                "forbidden_hits": fact_score["forbidden_hits"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "key": "evidence_score",
                        "score": evidence_score["score"],
                        "comment": json.dumps(
                            {
                                "unsupported_months": evidence_score["unsupported_months"],
                                "unsupported_weather_facts": evidence_score["unsupported_weather_facts"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "key": "judge_score",
                        "score": None if judge_score is None else judge_score["average_score"] / 5.0,
                        "comment": "" if judge_score is None else judge_score.get("reason", ""),
                    },
                    {"key": "overall_score", "score": overall_score},
                ]
            }
        if task == "knowledge_qa":
            source_score = score_knowledge_sources(outputs.get("source_documents", []), expected)
            content_rule_score = score_answer_contains(outputs.get("answer", ""), expected)
            judge_score = None
            if not skip_judge:
                judge_score = judge_knowledge(
                    (example.inputs or {}).get("question", ""),
                    outputs.get("answer", ""),
                    outputs.get("source_documents", []),
                )
            content_judge_score = None if skip_judge else _knowledge_content_judge_score(
                example.inputs or {},
                outputs,
                expected,
                judge_score=judge_score,
            )
            content_score = combine_knowledge_content_scores(
                content_rule_score,
                content_judge_score,
                expected,
            )
            overall_score = _knowledge_overall_score(source_score, content_score, judge_score)
            return {
                "results": [
                    {
                        "key": "source_score",
                        "score": source_score["score"],
                        "comment": json.dumps(
                            {
                                "matched_sources": source_score["matched_sources"],
                                "missing_sources": source_score["missing_sources"],
                                "actual_titles": source_score["actual_titles"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "key": "content_score",
                        "score": content_score["score"],
                        "comment": json.dumps(
                            {
                                "missing_terms": content_score["missing_terms"],
                                "refusal_ok": content_score["refusal_ok"],
                                "returned_sources_on_refusal": source_score["returned_sources_on_refusal"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "key": "judge_score",
                        "score": None if judge_score is None else judge_score["average_score"] / 5.0,
                        "comment": "" if judge_score is None else judge_score.get("reason", ""),
                    },
                    {"key": "overall_score", "score": overall_score},
                ]
            }
        raise ValueError(f"unsupported eval task: {task}")

    return evaluator


def _knowledge_content_judge_score(
    inputs: dict,
    outputs: dict,
    expected: dict,
    judge_score: dict | None = None,
) -> dict | None:
    question = inputs.get("question", "")
    if expected.get("should_refuse"):
        refusal_scores = judge_refusal(
            question,
            outputs.get("answer", ""),
        )
        return score_knowledge_content_judge(refusal_scores, expected)
    knowledge_scores = judge_score or judge_knowledge(
        question,
        outputs.get("answer", ""),
        outputs.get("source_documents", []),
    )
    return score_knowledge_content_judge(knowledge_scores, expected)


def _reply_overall_score(tool_score: dict, fact_score: dict, judge_score: dict | None) -> float:
    component_scores = [tool_score["score"], fact_score["score"]]
    if judge_score is not None:
        component_scores.append(judge_score["average_score"] / 5.0)
    return sum(component_scores) / len(component_scores)


def _knowledge_overall_score(source_score: dict, content_score: dict, judge_score: dict | None) -> float:
    component_scores = [source_score["score"], content_score["score"]]
    if judge_score is not None:
        component_scores.append(judge_score["average_score"] / 5.0)
    return sum(component_scores) / len(component_scores)


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _prompt_fingerprint(task: str) -> str:
    prompt_map = {
        "classification": CLASSIFICATION_SYSTEM_PROMPT,
        "reply_suggestion": REPLY_SUGGESTION_AGENT_PROMPT,
        "knowledge_qa": RAG_SUMMARIZE_PROMPT,
    }
    payload = prompt_map.get(task, "")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
