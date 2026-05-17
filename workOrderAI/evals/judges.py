import json

from langchain_core.prompts import PromptTemplate

from workOrderAI.models.factory import judge_model


REPLY_JUDGE_PROMPT = """你是客服 Agent 回复建议评审器。请根据输入工单、工具证据与回复建议评分。

评分维度：
1. task_completion：是否回答用户问题并贴合工单上下文，0-5分
2. groundedness：是否仅基于已知信息，不编造，0-5分
3. empathy：是否体现合适的客服语气和同理心，0-5分
4. actionability：是否提供可执行建议，0-5分
5. overreach：是否存在无依据扩写；无扩写记5分，严重扩写记0分

工单输入：
{input}

工具证据：
{tool_evidence}

规则校验：
{evidence_alignment}

回复建议：
{answer}

评分要求：
- 工具证据中已经出现的月份、天气、用户记录等事实，属于“有依据”，不得因为原始工单里没有写出就判为编造。
- 若规则校验显示某个结构化事实已被工具输出支持，应优先视为有依据。
- 只有回复中出现了工具证据和工单输入都无法支持的新事实时，才降低 groundedness 或 overreach。

请只返回 JSON：
{{
  "task_completion": 0,
  "groundedness": 0,
  "empathy": 0,
  "actionability": 0,
  "overreach": 0,
  "reason": "20字以内"
}}"""


KNOWLEDGE_JUDGE_PROMPT = """你是知识库问答评审器。请根据用户问题、答案和引用来源评分。

评分维度：
1. correctness：答案是否正确回答问题，0-5分
2. completeness：答案是否覆盖关键点，0-5分
3. citation_consistency：答案是否与来源一致、没有无来源扩写，0-5分

用户问题：
{question}

答案：
{answer}

引用来源：
{sources}

请只返回 JSON：
{{
  "correctness": 0,
  "completeness": 0,
  "citation_consistency": 0,
  "reason": "20字以内"
}}"""


def _invoke_json(prompt_text: str, values: dict) -> dict:
    prompt = PromptTemplate.from_template(prompt_text).format(**values)
    try:
        raw = judge_model.invoke(prompt)
    except Exception as exc:
        raise RuntimeError("judge model request failed") from exc

    raw_text = raw.content if hasattr(raw, "content") else raw
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge model returned invalid JSON: {raw_text}") from exc


def judge_reply(
    input_payload: dict,
    answer: str,
    tool_trace: list[dict] | None = None,
    evidence_alignment: dict | None = None,
) -> dict:
    scores = _invoke_json(
        REPLY_JUDGE_PROMPT,
        {
            "input": json.dumps(input_payload, ensure_ascii=False),
            "tool_evidence": json.dumps(tool_trace or [], ensure_ascii=False),
            "evidence_alignment": json.dumps(evidence_alignment or {}, ensure_ascii=False),
            "answer": answer,
        },
    )
    numeric_scores = [
        float(scores.get("task_completion", 0)),
        float(scores.get("groundedness", 0)),
        float(scores.get("empathy", 0)),
        float(scores.get("actionability", 0)),
        float(scores.get("overreach", 0)),
    ]
    scores["average_score"] = sum(numeric_scores) / len(numeric_scores)
    scores["passed"] = scores["average_score"] >= 4.0
    return scores


def judge_knowledge(question: str, answer: str, sources: list[dict]) -> dict:
    scores = _invoke_json(
        KNOWLEDGE_JUDGE_PROMPT,
        {
            "question": question,
            "answer": answer,
            "sources": json.dumps(sources or [], ensure_ascii=False),
        },
    )
    numeric_scores = [
        float(scores.get("correctness", 0)),
        float(scores.get("completeness", 0)),
        float(scores.get("citation_consistency", 0)),
    ]
    scores["average_score"] = sum(numeric_scores) / len(numeric_scores)
    scores["passed"] = scores["average_score"] >= 4.0
    return scores


REFUSAL_JUDGE_PROMPT = """You are evaluating whether an answer correctly refuses to answer from the available knowledge base.
Return JSON only.

Question: {question}
Answer: {answer}

Judge whether the answer clearly says the available materials do not contain enough information to answer the question.
Do not require any exact wording.

Return:
{{
  "is_refusal": false,
  "reason": "short explanation"
}}"""


def judge_refusal(question: str, answer: str) -> dict:
    return _invoke_json(
        REFUSAL_JUDGE_PROMPT,
        {
            "question": question,
            "answer": answer,
        },
    )
