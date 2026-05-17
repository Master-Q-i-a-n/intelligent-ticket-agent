from collections import Counter
import re


REFUSAL_PHRASES = (
    "没有相关信息",
    "没有提供相关信息",
    "未找到相关信息",
    "没有找到相关信息",
    "参考资料中没有",
    "资料中没有提供",
    "没有提供关于",
)

PRIORITY_ORDER = ("低", "中", "高", "紧急")


def score_classification(actual: dict, expected: dict) -> dict:
    field_scores = {
        "problem_type": float(actual.get("problem_type") == expected.get("problem_type")),
        "priority": score_priority(actual.get("priority"), expected.get("priority")),
        "user_sentiment": float(actual.get("user_sentiment") == expected.get("user_sentiment")),
    }
    exact_matches = {
        "problem_type": actual.get("problem_type") == expected.get("problem_type"),
        "priority": actual.get("priority") == expected.get("priority"),
        "user_sentiment": actual.get("user_sentiment") == expected.get("user_sentiment"),
    }
    return {
        "passed": all(exact_matches.values()),
        "score": sum(field_scores.values()) / len(field_scores),
        "field_scores": field_scores,
        "exact_matches": exact_matches,
    }


def score_priority(actual: str | None, expected: str | None) -> float:
    if actual not in PRIORITY_ORDER or expected not in PRIORITY_ORDER:
        return 0.0
    distance = abs(PRIORITY_ORDER.index(actual) - PRIORITY_ORDER.index(expected))
    return 1.0 - (distance / (len(PRIORITY_ORDER) - 1))


def score_tool_usage(tool_trace: list[dict], expected_tools: list[str], forbidden_tools: list[str]) -> dict:
    names = [item.get("name", "") for item in tool_trace]
    counts = Counter(names)
    missing_tools = [name for name in expected_tools if counts[name] == 0]
    used_forbidden_tools = [name for name in forbidden_tools if counts[name] > 0]
    passed = not missing_tools and not used_forbidden_tools
    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "missing_tools": missing_tools,
        "forbidden_tools": used_forbidden_tools,
        "tool_names": names,
        "tool_call_count": len(names),
    }


def score_required_facts(answer: str, expected: dict) -> dict:
    answer = answer or ""
    normalized_answer = _normalize_fact_text(answer)
    required_facts = expected.get("required_facts", [])
    required_fact_groups = expected.get("required_fact_groups", [])
    must_not_contain = expected.get("must_not_contain", [])
    missing_facts = [fact for fact in required_facts if _normalize_fact_text(fact) not in normalized_answer]
    missing_fact_groups = [
        group
        for group in required_fact_groups
        if not any(_normalize_fact_text(fact) in normalized_answer for fact in group)
    ]
    forbidden_hits = [fact for fact in must_not_contain if _normalize_fact_text(fact) in normalized_answer]
    passed = not missing_facts and not missing_fact_groups and not forbidden_hits
    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "missing_facts": missing_facts,
        "missing_fact_groups": missing_fact_groups,
        "forbidden_hits": forbidden_hits,
    }


def score_reply_evidence_alignment(answer: str, tool_trace: list[dict]) -> dict:
    answer = answer or ""
    evidence_outputs = [
        str(item.get("output") or "")
        for item in tool_trace or []
        if item.get("output")
    ]
    normalized_outputs = [_normalize_fact_text(output) for output in evidence_outputs]
    normalized_answer = _normalize_fact_text(answer)

    months = sorted(set(re.findall(r"(?<!\d)\d{4}-\d{2}(?!\d)", normalized_answer)))
    weather_facts = _extract_weather_facts(answer)

    supported_months = [
        month
        for month in months
        if any(month in output for output in normalized_outputs)
    ]
    unsupported_months = [month for month in months if month not in supported_months]

    normalized_weather_outputs = [_normalize_weather_fact(output) for output in evidence_outputs]
    supported_weather_facts = [
        fact
        for fact in weather_facts
        if any(_normalize_weather_fact(fact) in output for output in normalized_weather_outputs)
    ]
    unsupported_weather_facts = [fact for fact in weather_facts if fact not in supported_weather_facts]

    return {
        "passed": not unsupported_months and not unsupported_weather_facts,
        "score": 1.0 if not unsupported_months and not unsupported_weather_facts else 0.0,
        "supported_months": supported_months,
        "unsupported_months": unsupported_months,
        "supported_weather_facts": supported_weather_facts,
        "unsupported_weather_facts": unsupported_weather_facts,
    }


def _normalize_fact_text(text: str) -> str:
    normalized = str(text or "")

    def replace_cn_month(match: re.Match) -> str:
        year = match.group(1)
        month = int(match.group(2))
        return f"{year}-{month:02d}"

    return re.sub(r"(\d{4})年(\d{1,2})月", replace_cn_month, normalized)


def _extract_weather_facts(text: str) -> list[str]:
    patterns = (
        r"-?\d+(?:\.\d+)?\s*(?:°?C|℃)",
        r"\d+(?:\.\d+)?\s*%",
        r"\d+(?:\.\d+)?\s*(?:km/h|公里/小时)",
    )
    facts = []
    for pattern in patterns:
        facts.extend(match.group(0).replace(" ", "") for match in re.finditer(pattern, text or ""))
    return sorted(set(facts))


def _normalize_weather_fact(text: str) -> str:
    return (
        str(text or "")
        .replace(" ", "")
        .replace("°C", "C")
        .replace("℃", "C")
        .replace("公里/小时", "km/h")
    )


def score_knowledge_sources(actual_sources: list[dict], expected: dict) -> dict:
    actual_titles = [str(item.get("title", "")) for item in actual_sources or []]
    expected_sources = expected.get("expected_sources", [])
    should_refuse = bool(expected.get("should_refuse"))
    matched_sources = [
        expected_source
        for expected_source in expected_sources
        if any(expected_source in actual_title for actual_title in actual_titles)
    ]
    missing_sources = [source for source in expected_sources if source not in matched_sources]
    if should_refuse:
        passed = True
        score = 1.0
    elif expected_sources:
        passed = bool(matched_sources)
        score = len(matched_sources) / len(expected_sources)
    else:
        passed = not actual_titles
        score = 1.0 if passed else 0.0
    return {
        "passed": passed,
        "score": score,
        "matched_sources": matched_sources,
        "missing_sources": missing_sources,
        "actual_titles": actual_titles,
        "returned_sources_on_refusal": (actual_sources or []) if should_refuse else [],
    }


def score_answer_contains(answer: str, expected: dict) -> dict:
    answer = answer or ""
    required_terms = expected.get("answer_contains", [])
    should_refuse = bool(expected.get("should_refuse"))
    refusal_phrase_hits = [phrase for phrase in REFUSAL_PHRASES if phrase in answer]
    refusal_ok = not should_refuse or bool(refusal_phrase_hits)
    if should_refuse and refusal_ok:
        missing_terms = []
    else:
        missing_terms = [term for term in required_terms if term not in answer]
    passed = not missing_terms and refusal_ok
    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "missing_terms": missing_terms,
        "refusal_ok": refusal_ok,
        "refusal_phrase_hits": refusal_phrase_hits,
    }


def score_knowledge_content_judge(judge_score: dict | None, expected: dict) -> dict | None:
    if judge_score is None:
        return None
    if judge_score.get("error"):
        return {
            "passed": False,
            "score": 0.0,
            "refusal_ok": False,
            "error": judge_score["error"],
        }

    should_refuse = bool(expected.get("should_refuse"))
    if should_refuse:
        refusal_ok = bool(judge_score.get("is_refusal"))
        return {
            "passed": refusal_ok,
            "score": 1.0 if refusal_ok else 0.0,
            "refusal_ok": refusal_ok,
        }

    content_score = (
        float(judge_score.get("correctness", 0)) + float(judge_score.get("completeness", 0))
    ) / 10.0
    return {
        "passed": content_score >= 0.8,
        "score": content_score,
        "refusal_ok": True,
    }


def combine_knowledge_content_scores(
    rule_score: dict,
    judge_score: dict | None,
    expected: dict,
) -> dict:
    should_refuse = bool(expected.get("should_refuse"))
    refusal_ok = bool(rule_score.get("refusal_ok", not should_refuse))

    if should_refuse and judge_score is not None:
        refusal_ok = refusal_ok or bool(judge_score.get("refusal_ok"))

    if should_refuse and refusal_ok:
        missing_terms = []
    else:
        missing_terms = list(rule_score.get("missing_terms", []))

    passed = not missing_terms and refusal_ok
    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "missing_terms": missing_terms,
        "refusal_ok": refusal_ok,
    }
