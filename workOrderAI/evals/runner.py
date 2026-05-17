import asyncio
import json
import time

from workOrderAI.agent.agent_context import get_tool_trace, reset_tool_trace, start_tool_trace
from workOrderAI.evals.judges import judge_knowledge, judge_refusal, judge_reply
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


async def run_case(task: str, case: dict, skip_judge: bool = False) -> dict:
    if task == "classification":
        return await _run_classification_case(case)
    if task == "reply_suggestion":
        return await _run_reply_suggestion_case(case, skip_judge=skip_judge)
    if task == "knowledge_qa":
        return await _run_knowledge_case(case, skip_judge=skip_judge)
    raise ValueError(f"unsupported eval task: {task}")


def run_case_sync(task: str, case: dict, skip_judge: bool = False) -> dict:
    return asyncio.run(run_case(task, case, skip_judge=skip_judge))


async def _run_classification_case(case: dict) -> dict:
    from workOrderAI.app.model.request import ClassifyRequest
    from workOrderAI.app.service.classify_service import ClassifyService

    started_at = time.perf_counter()
    request = ClassifyRequest(**case["input"])
    raw_output = ClassifyService().get_classification(request)
    actual = json.loads(raw_output)
    rule_score = score_classification(actual, case["expected"])
    latency = time.perf_counter() - started_at
    notes = [
        field
        for field, passed in rule_score["exact_matches"].items()
        if not passed
    ]
    return {
        "id": case["id"],
        "task": "classification",
        "input": case["input"],
        "expected": case["expected"],
        "actual": actual,
        "rule_score": rule_score,
        "passed": rule_score["passed"],
        "score": rule_score["score"],
        "latency_seconds": latency,
        "notes": notes,
    }


async def _run_reply_suggestion_case(case: dict, skip_judge: bool) -> dict:
    from workOrderAI.app.model.request import ReplySuggestRequest
    from workOrderAI.app.service.suggest_service import SuggestService

    started_at = time.perf_counter()
    request = ReplySuggestRequest(**case["input"])
    trace_token = start_tool_trace()
    try:
        answer = await SuggestService().get_suggestion(request)
        tool_trace = get_tool_trace()
    finally:
        reset_tool_trace(trace_token)

    tool_score = score_tool_usage(tool_trace, case["expected_tools"], case["forbidden_tools"])
    fact_score = score_required_facts(answer, case["expected"])
    evidence_score = score_reply_evidence_alignment(answer, tool_trace)
    judge_score = None if skip_judge else _safe_judge_reply(case["input"], answer, tool_trace, evidence_score)
    latency = time.perf_counter() - started_at

    component_scores = [tool_score["score"], fact_score["score"]]
    if judge_score is not None:
        component_scores.append(judge_score["average_score"] / 5.0)
    score = sum(component_scores) / len(component_scores)
    passed = tool_score["passed"] and fact_score["passed"] and (
        judge_score is None or judge_score.get("passed", False)
    )
    notes = []
    if tool_score["missing_tools"]:
        notes.append("missing tools: " + ", ".join(tool_score["missing_tools"]))
    if tool_score["forbidden_tools"]:
        notes.append("forbidden tools: " + ", ".join(tool_score["forbidden_tools"]))
    if fact_score["missing_facts"]:
        notes.append("missing facts: " + ", ".join(fact_score["missing_facts"]))
    if fact_score["missing_fact_groups"]:
        notes.append(
            "missing fact groups: "
            + "; ".join("/".join(group) for group in fact_score["missing_fact_groups"])
        )
    if fact_score["forbidden_hits"]:
        notes.append("forbidden facts: " + ", ".join(fact_score["forbidden_hits"]))
    if judge_score and judge_score.get("error"):
        notes.append("judge error")
    return {
        "id": case["id"],
        "task": "reply_suggestion",
        "input": case["input"],
        "expected": case["expected"],
        "actual": {"suggested_reply": answer, "tool_trace": tool_trace},
        "tool_score": tool_score,
        "fact_score": fact_score,
        "evidence_score": evidence_score,
        "judge_score": judge_score,
        "passed": passed,
        "score": score,
        "latency_seconds": latency,
        "notes": notes,
    }


async def _run_knowledge_case(case: dict, skip_judge: bool) -> dict:
    from workOrderAI.app.service.knowledge_service import KnowledgeService

    started_at = time.perf_counter()
    answer_payload = await KnowledgeService().answer(case["input"]["question"])
    answer = answer_payload.get("answer", "")
    sources = answer_payload.get("source_documents", [])
    source_score = score_knowledge_sources(sources, case["expected"])
    content_rule_score = score_answer_contains(answer, case["expected"])
    judge_score = None if skip_judge else _safe_judge_knowledge(case["input"]["question"], answer, sources)
    refusal_judge_score = None
    if case["expected"].get("should_refuse") and not skip_judge:
        refusal_judge_score = _safe_judge_refusal(case["input"]["question"], answer)
    content_judge_score = score_knowledge_content_judge(refusal_judge_score or judge_score, case["expected"])
    content_score = combine_knowledge_content_scores(
        content_rule_score,
        content_judge_score,
        case["expected"],
    )
    latency = time.perf_counter() - started_at

    component_scores = [source_score["score"], content_score["score"]]
    if judge_score is not None:
        component_scores.append(judge_score["average_score"] / 5.0)
    score = sum(component_scores) / len(component_scores)
    passed = source_score["passed"] and content_score["passed"] and (
        judge_score is None or judge_score.get("passed", False)
    )
    notes = []
    if source_score["missing_sources"]:
        notes.append("missing sources: " + ", ".join(source_score["missing_sources"]))
    if content_score["missing_terms"]:
        notes.append("missing terms: " + ", ".join(content_score["missing_terms"]))
    if not content_score["refusal_ok"]:
        notes.append("refusal mismatch")
    if judge_score and judge_score.get("error"):
        notes.append("judge error")
    if refusal_judge_score and refusal_judge_score.get("error"):
        notes.append("refusal judge error")
    return {
        "id": case["id"],
        "task": "knowledge_qa",
        "input": case["input"],
        "expected": case["expected"],
        "actual": answer_payload,
        "source_score": source_score,
        "content_score": content_score,
        "judge_score": judge_score,
        "returned_sources_on_refusal": source_score["returned_sources_on_refusal"],
        "passed": passed,
        "score": score,
        "latency_seconds": latency,
        "notes": notes,
    }


def _safe_judge_reply(
    input_payload: dict,
    answer: str,
    tool_trace: list[dict],
    evidence_score: dict,
) -> dict:
    try:
        return judge_reply(input_payload, answer, tool_trace, evidence_score)
    except Exception as exc:
        return {"passed": False, "average_score": 0.0, "error": str(exc)}


def _safe_judge_knowledge(question: str, answer: str, sources: list[dict]) -> dict:
    try:
        return judge_knowledge(question, answer, sources)
    except Exception as exc:
        return {"passed": False, "average_score": 0.0, "error": str(exc)}


def _safe_judge_refusal(question: str, answer: str) -> dict:
    try:
        return judge_refusal(question, answer)
    except Exception as exc:
        return {"is_refusal": False, "error": str(exc)}
