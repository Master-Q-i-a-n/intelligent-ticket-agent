import json
import re
from typing import Literal, TypedDict

from langchain.agents import create_agent
from langgraph.graph import END, START, StateGraph

from workOrderAI.agent.agent_context import get_tool_trace, record_tool_call
from workOrderAI.agent.agent_middleware import get_middleware
from workOrderAI.agent.agent_tools import fetch_current_user_records, get_current_weather, get_time_now, rag_summarize
from workOrderAI.app.model.request import ReplySuggestRequest
from workOrderAI.app.service.case_memory_service import CaseMemoryService
from workOrderAI.app.service.rag_service import RagService
from workOrderAI.models.factory import chat_model, router_model
from workOrderAI.utils.logger_handler import logger
from workOrderAI.utils.prompt_builder import AGENT_PROMPT


RouteName = Literal["DIRECT_KNOWLEDGE", "FAULT_DIAGNOSIS", "USER_RECORD", "CLARIFY", "OUT_OF_SCOPE"]
CheckStatus = Literal["PASS", "REVISE", "ESCALATE"]
VALID_ROUTES = {"DIRECT_KNOWLEDGE", "FAULT_DIAGNOSIS", "USER_RECORD", "CLARIFY", "OUT_OF_SCOPE"}
ROUTER_CONFIDENCE_THRESHOLD = 0.6


class ReplySuggestionState(TypedDict, total=False):
    work_order: ReplySuggestRequest
    ticket_text: str
    history_text: str
    case_memories: list[dict]
    route: RouteName
    branch_result: str
    branch_data: dict
    rag_sources: list[dict]
    draft_reply: str
    check_result: dict
    retry_count: int
    final_reply: str


USER_RECORD_AGENT_PROMPT = """你是用户使用记录查询子任务 Agent，只负责为客服回复建议准备事实依据。

你只能围绕当前工单所属用户查询记录，不允许查询其他用户。
可用工具仅限：
1. get_time_now：处理去年、上个月、最近等相对时间。
2. fetch_current_user_records：查询当前工单所属用户指定月份或全部月份记录。
3. rag_summarize：当用户要求“需要注意什么、是否正常、为什么、怎么优化”等分析建议时，补充专业依据。

输出要求：
- 只输出给主工作流使用的中文事实摘要。
- 如果未查到记录，必须明确说明“未查到对应时间的使用记录”。
- 不要编造清洁次数、耗材寿命、清洁效率或对比数据。
- 不要输出 owner_username、ticket_id、工具 trace 或数据库字段名。
"""


class ReplySuggestionGraph:
    def __init__(self):
        self.chat_model = chat_model
        self.router_model = router_model
        self.case_memory_service = CaseMemoryService()
        self.user_record_agent = create_agent(
            model=chat_model,
            system_prompt=AGENT_PROMPT,
            tools=[get_time_now, fetch_current_user_records, rag_summarize],
            middleware=get_middleware(),
        )
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(ReplySuggestionState)
        graph.add_node("load_context", self.load_context)
        graph.add_node("retrieve_case_memory", self.retrieve_case_memory)
        graph.add_node("route_query", self.route_query)
        graph.add_node("direct_knowledge_branch", self.run_direct_knowledge_branch)
        graph.add_node("fault_diagnosis_branch", self.run_fault_branch)
        graph.add_node("user_record_branch", self.run_user_record_branch)
        graph.add_node("clarify_branch", self.clarify_branch)
        graph.add_node("out_of_scope_branch", self.out_of_scope_branch)
        graph.add_node("generate_reply", self.generate_reply)
        graph.add_node("self_check", self.self_check)
        graph.add_node("generate_reply_retry", self.generate_reply_retry)
        graph.add_node("safe_fallback_reply", self.safe_fallback_reply)

        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "route_query")
        graph.add_edge("route_query", "retrieve_case_memory")
        graph.add_conditional_edges(
            "retrieve_case_memory",
            self.route_to_branch,
            {
                "DIRECT_KNOWLEDGE": "direct_knowledge_branch",
                "FAULT_DIAGNOSIS": "fault_diagnosis_branch",
                "USER_RECORD": "user_record_branch",
                "CLARIFY": "clarify_branch",
                "OUT_OF_SCOPE": "out_of_scope_branch",
            },
        )
        graph.add_edge("direct_knowledge_branch", "generate_reply")
        graph.add_edge("fault_diagnosis_branch", "generate_reply")
        graph.add_edge("user_record_branch", "generate_reply")
        graph.add_edge("clarify_branch", "generate_reply")
        graph.add_edge("out_of_scope_branch", "generate_reply")
        graph.add_edge("generate_reply", "self_check")
        graph.add_conditional_edges(
            "self_check",
            self.after_self_check,
            {
                "end": END,
                "retry": "generate_reply_retry",
                "fallback": "safe_fallback_reply",
            },
        )
        graph.add_edge("generate_reply_retry", "self_check")
        graph.add_edge("safe_fallback_reply", END)
        return graph.compile()

    async def run(self, work_order: ReplySuggestRequest) -> dict:
        state = await self.graph.ainvoke({"work_order": work_order})
        return state

    async def load_context(self, state: ReplySuggestionState) -> dict:
        work_order = state["work_order"]
        ticket_text = f"标题：{work_order.title or ''}\n内容：{work_order.description or ''}".strip()
        history_lines = [
            f"{reply.role}：{reply.content}"
            for reply in (work_order.history or [])
            if str(reply.content or "").strip()
        ]
        return {
            "ticket_text": ticket_text,
            "history_text": "\n".join(history_lines),
            "retry_count": 0,
        }

    async def retrieve_case_memory(self, state: ReplySuggestionState) -> dict:
        route = state.get("route") or "DIRECT_KNOWLEDGE"
        if not self._should_retrieve_case_memory(state):
            logger.info("[reply-graph] skip case memory route=%s", route)
            return {"case_memories": []}

        try:
            cases = await self.case_memory_service.search_similar_cases(self._case_query(state["work_order"]))
        except Exception as exc:
            logger.error("[reply-graph] prefetch similar cases failed: %s", exc, exc_info=True)
            cases = []
        logger.info("[reply-graph] case memory hits=%s route=%s", len(cases), route)
        return {"case_memories": cases}

    async def route_query(self, state: ReplySuggestionState) -> dict:
        text = self._route_text(state["work_order"])
        route = await self._classify_route(text)
        logger.info("[reply-graph] route=%s", route)
        return {"route": route}

    def route_to_branch(self, state: ReplySuggestionState) -> RouteName:
        route = state.get("route") or "DIRECT_KNOWLEDGE"
        return route if route in VALID_ROUTES else "DIRECT_KNOWLEDGE"

    async def clarify_branch(self, state: ReplySuggestionState) -> dict:
        return {
            "branch_result": "当前信息还不足以判断具体问题，需要先向用户追问关键现象、设备型号或截图。",
            "branch_data": {"route_action": "clarify"},
            "rag_sources": [],
        }

    async def out_of_scope_branch(self, state: ReplySuggestionState) -> dict:
        return {
            "branch_result": "当前问题超出扫地/扫拖机器人知识库和工单处理范围，应礼貌说明无法基于现有资料回答。",
            "branch_data": {"route_action": "refuse"},
            "rag_sources": [],
        }

    async def run_direct_knowledge_branch(self, state: ReplySuggestionState) -> dict:
        query = self._case_query(state["work_order"])
        weather = ""
        if self._needs_weather_context(query):
            weather = await get_current_weather.ainvoke({})
            self._record_direct_tool("get_current_weather", {}, weather)
        result = await rag_summarize.ainvoke({"query": query})
        self._record_direct_tool("rag_summarize", {"query": query}, result)
        parsed = self._parse_json_object(result)
        summary = parsed.get("summary") or str(result or "")
        if weather:
            summary = f"当前环境信息：{weather}\n知识库摘要：{summary}"
        return {
            "branch_result": summary,
            "branch_data": {"weather": weather, "rag": parsed},
            "rag_sources": parsed.get("sources") if isinstance(parsed.get("sources"), list) else [],
        }

    async def run_fault_branch(self, state: ReplySuggestionState) -> dict:
        query = "扫地机器人故障排查：" + self._case_query(state["work_order"])
        result = await RagService().get_documents_and_summary(query)
        payload = {
            "summary": result.get("summary", ""),
            "sources": result.get("source_documents", []),
        }
        self._record_direct_tool("rag_summarize", {"query": query}, json.dumps(payload, ensure_ascii=False))
        return {
            "branch_result": payload["summary"],
            "branch_data": {"rag": payload},
            "rag_sources": payload["sources"],
        }

    async def run_user_record_branch(self, state: ReplySuggestionState) -> dict:
        prompt = self._build_user_record_agent_input(state)
        try:
            result = await self.user_record_agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                context={"report": False},
            )
            latest_message = result["messages"][-1]
            content = latest_message.content.strip() if latest_message.content else ""
        except Exception as exc:
            logger.error("[reply-graph] user record sub-agent failed: %s", exc, exc_info=True)
            content = "用户记录查询暂时失败，需要客服进一步核实后再回复。"
        return {
            "branch_result": content,
            "branch_data": {"user_record_summary": content},
            "rag_sources": self._sources_from_tool_trace(get_tool_trace()),
        }

    async def generate_reply(self, state: ReplySuggestionState) -> dict:
        route = state.get("route") or "DIRECT_KNOWLEDGE"
        if route == "OUT_OF_SCOPE":
            draft = "您好，当前问题超出了现有扫地/扫拖机器人知识库和工单处理范围。为了避免给您不准确的信息，建议您联系人工客服进一步确认。"
        elif route == "CLARIFY":
            draft = "您好，为了更准确地帮您排查，请您补充一下设备型号、具体异常现象、出现时间，以及是否有截图或报错提示。收到信息后我们会继续协助处理。"
        else:
            draft = await self._generate_reply_text(state)

        logger.info("[reply-graph] reply_draft draft=%s", draft)
        
        return {"draft_reply": draft, "final_reply": draft}

    async def generate_reply_retry(self, state: ReplySuggestionState) -> dict:
        retry_state = dict(state)
        retry_state["retry_count"] = int(state.get("retry_count") or 0) + 1
        draft = await self._generate_reply_text(retry_state, revision=True)
        return {
            "draft_reply": draft,
            "final_reply": draft,
            "retry_count": retry_state["retry_count"],
        }

    async def self_check(self, state: ReplySuggestionState) -> dict:
        draft = state.get("draft_reply") or ""
        work_order = state["work_order"]
        issues = []
        failed_dimensions = []

        if state.get("route") not in ["OUT_OF_SCOPE", "CLARIFY"]:
            privacy_issues = self._check_privacy(draft, work_order)
            if privacy_issues:
                failed_dimensions.append("privacy")
                issues.extend(privacy_issues)

            groundedness_issues = self._check_groundedness(draft, state)
            groundedness_issues.extend(await self._check_groundedness_by_model(draft, state))
            if groundedness_issues:
                failed_dimensions.append("groundedness")
                issues.extend(groundedness_issues)

            completeness_issues = self._check_completeness(draft, state)
            if completeness_issues:
                failed_dimensions.append("completeness")
                issues.extend(completeness_issues)

        status: CheckStatus = "PASS"
        if issues:
            status = "ESCALATE" if self._has_high_risk_issue(issues) else "REVISE"

        check_result = {
            "status": status,
            "failed_dimensions": failed_dimensions,
            "issues": issues,
            "revision_instruction": "；".join(issues),
        }
        logger.info("[reply-graph] self_check status=%s dimensions=%s issues=%s", status, failed_dimensions, str(issues))
        return {"check_result": check_result}

    def after_self_check(self, state: ReplySuggestionState) -> str:
        check = state.get("check_result") or {}
        status = check.get("status") or "PASS"
        if status == "PASS":
            return "end"
        if status == "REVISE" and int(state.get("retry_count") or 0) < 1:
            return "retry"
        return "fallback"

    async def safe_fallback_reply(self, state: ReplySuggestionState) -> dict:
        issues = "；".join((state.get("check_result") or {}).get("issues") or [])
        if "未查到" in issues or "编造" in issues:
            reply = "您好，目前系统未查询到足够的使用记录依据。为了避免给您不准确的信息，建议您确认查询时间或补充设备信息，我们会继续协助核实。"
        elif "隐私" in issues or "内部" in issues:
            reply = "您好，为保护账号与工单信息安全，当前问题需要客服进一步核实后再回复。请您补充必要的设备信息，我们会继续协助处理。"
        else:
            reply = "您好，关于您反馈的问题，目前还需要进一步核实设备状态和相关记录。建议您补充设备型号、具体异常现象或截图，我们会继续为您排查。"
        return {"final_reply": reply, "draft_reply": reply}

    async def _generate_reply_text(self, state: ReplySuggestionState, revision: bool = False) -> str:
        prompt = self._build_generate_prompt(state, revision=revision)
        try:
            result = await self.chat_model.ainvoke(prompt)
            return self._message_content(result)
        except Exception as exc:
            logger.error("[reply-graph] generate reply failed: %s", exc, exc_info=True)
            return "您好，关于您反馈的问题，目前还需要进一步核实。建议您补充更多设备信息，我们会继续协助处理。"

    def _build_generate_prompt(self, state: ReplySuggestionState, revision: bool = False) -> str:
        work_order = state["work_order"]
        cases = self._format_cases(state.get("case_memories") or [])
        evidence = self._format_evidence(state)
        revision_text = ""
        if revision:
            check = state.get("check_result") or {}
            revision_text = f"\n请根据以下检查意见重写，必须修正：{check.get('revision_instruction') or ''}\n"

        return f"""你是工单系统客服助手，请基于已给证据生成一段可直接给管理员参考的客服回复草稿。

要求：
1. 只能使用工单内容、历史对话、历史案例、工具结果和知识库摘要中的事实。
2. 不得输出 owner_username、ticket_id、数据库字段、工具 trace 等内部信息。
3. 查不到记录时要明确说明未查到，不得编造具体记录。
4. 必须回应用户核心诉求；信息不足时要追问关键补充信息。

工单：
标题：{work_order.title or ""}
内容：{work_order.description or ""}
分类：{work_order.category or ""}
情绪：{work_order.emotion or ""}

历史对话：
{state.get("history_text") or "无"}

可参考历史案例：
{cases or "无"}

本轮路由：{state.get("route") or ""}
分支处理结果：
{state.get("branch_result") or ""}

证据摘要：
{evidence or "无"}
{revision_text}
请输出最终客服回复草稿："""

    def _build_user_record_agent_input(self, state: ReplySuggestionState) -> str:
        work_order = state["work_order"]
        return f"""请处理当前工单中的用户使用记录查询需求。

工单标题：{work_order.title or ""}
工单内容：{work_order.description or ""}
历史对话：
{state.get("history_text") or "无"}

请根据用户问题决定是否需要 get_time_now、fetch_current_user_records、rag_summarize。
只输出本次查询和分析得到的事实摘要，不要输出完整客服话术。"""

    def _case_query(self, work_order: ReplySuggestRequest) -> str:
        return f"{work_order.title or ''}\n{work_order.description or ''}".strip()

    def _route_text(self, work_order: ReplySuggestRequest) -> str:
        history = "\n".join(f"{reply.role}:{reply.content}" for reply in (work_order.history or [])[-3:])
        return f"{work_order.title or ''}\n{work_order.description or ''}\n{history}".strip()

    async def _classify_route(self, text: str) -> RouteName:
        fallback_route = self._classify_route_by_rules(text)
        prompt = self._build_route_prompt(text)
        try:
            result = await self.router_model.ainvoke(prompt)
            payload = self._parse_json_object(self._message_content(result))
            route = payload.get("route")
            confidence = float(payload.get("confidence") or 0)
            reason = payload.get("reason") or ""
            if route not in VALID_ROUTES:
                logger.warning("[reply-graph] router returned invalid route=%s, fallback=%s", route, fallback_route)
                return fallback_route
            if confidence < ROUTER_CONFIDENCE_THRESHOLD:
                logger.info(
                    "[reply-graph] router confidence too low route=%s confidence=%.2f, fallback=%s",
                    route,
                    confidence,
                    fallback_route,
                )
                return fallback_route
            logger.info("[reply-graph] router model route=%s confidence=%.2f reason=%s", route, confidence, reason)
            return route
        except Exception as exc:
            logger.warning("[reply-graph] router model failed, fallback=%s, error=%s", fallback_route, exc)
            return fallback_route

    def _classify_route_by_rules(self, text: str) -> RouteName:
        normalized = str(text or "").lower()
        if self._is_too_vague(normalized):
            return "CLARIFY"
        if (
            self._contains_any(normalized, ["记录", "使用情况", "清洁效率", "去年", "上个月", "这个月", "本月", "最近"])
            or ("我" in normalized and self._contains_any(normalized, ["耗材", "剩余"]))
        ):
            return "USER_RECORD"
        if self._contains_any(normalized, ["坏", "故障", "不能", "无法", "异常", "报错", "不出水", "回不了充", "乱跑", "打转", "卡住", "失灵"]):
            return "FAULT_DIAGNOSIS"
        if self._contains_any(normalized, ["老板", "股票", "彩票", "写歌", "考试答案", "无关"]):
            return "OUT_OF_SCOPE"
        return "DIRECT_KNOWLEDGE"

    def _build_route_prompt(self, text: str) -> str:
        return f"""你是智能工单回复建议的路由器。请只根据当前工单内容判断应走哪条处理分支。

可选 route：
1. USER_RECORD：用户使用记录、耗材剩余、清洁效率、相对时间记录查询，例如去年、本月、最近、上个月。
2. FAULT_DIAGNOSIS：设备异常、故障、无法工作、报错、排障，例如不出水、回不了充、乱跑、卡住。
3. DIRECT_KNOWLEDGE：产品知识、保养、功能说明、一般建议。
4. CLARIFY：信息不足，需要先追问关键现象、设备型号、截图或报错。
5. OUT_OF_SCOPE：不属于扫地/扫拖机器人客服范围的问题。

判断要求：
- 如果用户同时提到“使用记录”和“注意事项/建议”，优先 USER_RECORD，因为需要先查记录。
- 如果只是问耗材怎么更换、如何保养，属于 DIRECT_KNOWLEDGE，不要误判为 USER_RECORD。
- 如果用户只是称呼“老板/客服”，但实际问题是机器人故障，不要因为称呼误判为 OUT_OF_SCOPE。
- confidence 表示你对 route 的置信度，范围 0 到 1。

只输出严格 JSON，不要输出 Markdown：
{{"route":"DIRECT_KNOWLEDGE","confidence":0.8,"reason":"一句话说明"}}

工单内容：
{text}
"""

    def _is_too_vague(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        if len(compact) <= 6 and self._contains_any(compact, ["坏了", "不好用", "有问题", "不行"]):
            return True
        return compact in {"坏了", "有问题", "不好用", "不行"}

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _needs_weather_context(self, text: str) -> bool:
        return self._contains_any(str(text or "").lower(), ["天气", "湿度", "潮湿", "下雨", "梅雨"])

    def _should_retrieve_case_memory(self, state: ReplySuggestionState) -> bool:
        route = state.get("route") or "DIRECT_KNOWLEDGE"
        if route in {"DIRECT_KNOWLEDGE", "FAULT_DIAGNOSIS"}:
            return True
        if route != "USER_RECORD":
            return False

        query = self._case_query(state["work_order"])
        return self._contains_any(
            query,
            ["需要注意", "注意什么", "建议", "是否正常", "怎么处理", "怎么优化"],
        )

    def _format_cases(self, cases: list[dict]) -> str:
        lines = []
        for index, case in enumerate(cases, 1):
            lines.append(
                f"{index}. 编号：{case.get('ticket_code') or case.get('ticket_id') or '--'}；"
                f"标题：{case.get('title') or '--'}；最终客服回复：{case.get('final_reply') or ''}"
            )
        return "\n".join(lines)

    def _format_evidence(self, state: ReplySuggestionState) -> str:
        trace = get_tool_trace()
        evidence = []
        if state.get("branch_result"):
            evidence.append(f"分支结果：{state['branch_result']}")
        for item in trace:
            evidence.append(
                f"工具 {item.get('name')} 参数 {item.get('args')} 返回：{self._truncate(item.get('output') or '', 1200)}"
            )
        return "\n".join(evidence)

    def _format_trusted_evidence(self, state: ReplySuggestionState) -> str:
        trace = get_tool_trace()
        evidence = []
        for item in trace:
            evidence.append(
                f"工具 {item.get('name')} 参数 {item.get('args')} 返回：{self._truncate(item.get('output') or '', 1200)}"
            )
        cases = self._format_cases(state.get("case_memories") or [])
        if cases:
            evidence.append(f"历史案例：\n{cases}")
        rag_sources = state.get("rag_sources") or []
        if rag_sources:
            evidence.append(f"RAG来源：{self._truncate(json.dumps(rag_sources, ensure_ascii=False), 1200)}")
        return "\n".join(evidence)

    def _check_privacy(self, draft: str, work_order: ReplySuggestRequest) -> list[str]:
        issues = []
        forbidden_terms = ["owner_username", "ticket_id", "tool_trace", "数据库字段", "内部字段"]
        if any(term in draft for term in forbidden_terms):
            issues.append("回复暴露了内部字段或工具信息，存在隐私风险")
        if work_order.owner_username and str(work_order.owner_username) in draft:
            issues.append("回复直接暴露了当前用户 username，存在隐私风险")
        if work_order.id and str(work_order.id) in draft:
            issues.append("回复直接暴露了内部工单 ID，存在隐私风险")
        return issues

    def _check_groundedness(self, draft: str, state: ReplySuggestionState) -> list[str]:
        issues = []
        trusted_evidence = self._format_trusted_evidence(state)
        no_records = "no records found" in trusted_evidence or '"found": false' in trusted_evidence or "未查到" in trusted_evidence
        if no_records:
            if not self._contains_any(draft, ["未", "没有", "暂无记录", "无法"]):
                issues.append("工具未查到记录，但回复没有明确说明未查到")
            if re.search(r"(清扫|清洁).{0,8}\d+\s*次", draft) or re.search(r"剩余\s*\d+", draft):
                issues.append("工具未查到记录，但回复出现了具体使用记录或耗材寿命，疑似编造")
        if state.get("route") == "USER_RECORD" and not trusted_evidence.strip():
            issues.append("用户记录问题缺少工具证据")
        return issues

    async def _check_groundedness_by_model(self, draft: str, state: ReplySuggestionState) -> list[str]:
        trusted_evidence = self._format_trusted_evidence(state)
        if not str(draft or "").strip() or not str(trusted_evidence or "").strip():
            return []

        model = getattr(self, "router_model", None)
        if model is None:
            logger.warning("[reply-graph] groundedness model is unavailable, skip model check")
            return []

        prompt = self._build_groundedness_check_prompt(
            draft=self._truncate(draft, 3000),
            trusted_evidence=self._truncate(trusted_evidence, 3000),
            branch_result=self._truncate(state.get("branch_result") or "", 2000),
            route=state.get("route") or "DIRECT_KNOWLEDGE",
        )
        try:
            result = await model.ainvoke(prompt)
            payload = self._parse_json_object(self._message_content(result))
        except Exception as exc:
            logger.warning("[reply-graph] groundedness model check failed: %s", exc)
            return []

        if "supported" not in payload:
            logger.warning("[reply-graph] groundedness model returned invalid payload=%s", payload)
            return []

        if self._is_supported_value(payload.get("supported")):
            return []

        unsupported_facts = payload.get("unsupported_facts") or []
        if isinstance(unsupported_facts, str):
            unsupported_facts = [unsupported_facts]
        unsupported_facts = [str(item).strip() for item in unsupported_facts if str(item or "").strip()]
        reason = str(payload.get("reason") or "").strip()
        if unsupported_facts:
            issue = f"回复中存在未被证据支持的事实：{'、'.join(unsupported_facts)}"
            if reason:
                issue += f"；原因：{reason}"
            return [issue]

        return [f"回复中存在未被证据支持的事实：{reason or '模型判断事实依据不足'}"]

    def _build_groundedness_check_prompt(self, draft: str, trusted_evidence: str, branch_result: str, route: str) -> str:
        return f"""你是客服回复事实依据检查器。请对比【可信证据】、【分支结果】和【回复草稿】，判断中间结果与最终回复里的具体事实是否都能被可信证据支持。

检查范围：
- 需要核验的具体事实包括：月份、清扫次数、清扫面积、百分比、剩余天数、耗材状态、天气数值、故障结论、来源标题等。
- 礼貌问候、追问、泛化建议不算具体事实。
- 【可信证据】是唯一事实来源。
- 【分支结果】是中间摘要，不是证据，也需要被核验。
- 如果可信证据明确显示未查到记录，分支结果和回复草稿不得写任何具体使用记录、清洁次数、耗材寿命或清洁效率。
- 只要分支结果或回复草稿中的具体事实无法在可信证据中找到，或与可信证据不一致，就判定 supported=false。

当前路由：{route}

可信证据：
{trusted_evidence}

分支结果：
{branch_result or "无"}

回复草稿：
{draft}

请只输出严格 JSON，不要输出 Markdown：
{{"supported":true,"unsupported_facts":[],"reason":"一句话说明"}}
"""

    def _is_supported_value(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return False

    def _check_completeness(self, draft: str, state: ReplySuggestionState) -> list[str]:
        issues = []
        route = state.get("route") or "DIRECT_KNOWLEDGE"
        query = self._route_text(state["work_order"])
        if len(draft.strip()) < 12:
            issues.append("回复过短，没有完整回应用户问题")

        if route == "USER_RECORD":
            if not self._contains_any(draft, ["记录", "查询", "未查到", "没有查到", "未查询到", "使用情况"]):
                issues.append("用户记录问题回复没有说明查询结果")
            if self._asks_for_advice(query) and not self._contains_any(draft, ["建议", "注意", "可以", "请", "需要"]):
                issues.append("用户记录问题同时询问建议或注意事项，但回复没有给出建议或追问")
            return issues

        if route == "FAULT_DIAGNOSIS":
            if not self._contains_any(draft, ["排查", "检查", "确认", "尝试", "补充", "设备型号", "截图", "报错", "异常", "请"]):
                issues.append("故障诊断问题回复没有给出排查步骤或追问故障细节")
            return issues
        
        if route == "DIRECT_KNOWLEDGE":
            if not self._contains_any(draft, ["建议", "注意", "可以", "请", "方法", "步骤", "说明", "更换", "保养", "检查"]):
                issues.append("知识问答回复没有给出实质性说明或可执行建议")
            return issues

        return issues

    def _asks_for_advice(self, text: str) -> bool:
        return self._contains_any(text, ["需要注意", "注意什么", "建议", "是否正常", "怎么优化"])

    def _has_high_risk_issue(self, issues: list[str]) -> bool:
        return any("隐私" in issue or "缺少工具证据" in issue for issue in issues)

    def _parse_json_object(self, content: str) -> dict:
        try:
            value = json.loads(content or "{}")
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", str(content or ""))
            if not match:
                return {}
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}

    def _sources_from_tool_trace(self, trace: list[dict]) -> list[dict]:
        for item in reversed(trace):
            if item.get("name") != "rag_summarize":
                continue
            payload = self._parse_json_object(item.get("output") or "{}")
            sources = payload.get("sources")
            if isinstance(sources, list):
                return sources
        return []

    def _record_direct_tool(self, name: str, args: dict, output: object) -> None:
        record_tool_call(name, args, output)

    def _message_content(self, result) -> str:
        return str(getattr(result, "content", result) or "").strip()

    def _truncate(self, content: object, limit: int) -> str:
        text = str(content or "")
        return text if len(text) <= limit else text[:limit] + "...[truncated]"
