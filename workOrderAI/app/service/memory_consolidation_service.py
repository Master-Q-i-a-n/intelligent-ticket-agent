import json
import re

from workOrderAI.app.model.request import CaseMemoryUpsertRequest, ReplySuggestRequest
from workOrderAI.app.service.case_memory_service import CaseMemoryService
from workOrderAI.app.service.ticket_memory_service import EMPTY_TICKET_MEMORY, TicketMemoryService
from workOrderAI.app.service.user_memory_service import MEMORY_KEY_TYPES, UserMemoryService
from workOrderAI.models.factory import router_model
from workOrderAI.utils.logger_handler import logger


class MemoryConsolidationService:
    """Consolidates terminal ticket working memory into case and user memories."""

    def __init__(self, model=None):
        self.model = model or router_model
        self.ticket_memory_service = TicketMemoryService(model=self.model)
        self.case_memory_service = CaseMemoryService()
        self.user_memory_service = UserMemoryService()

    async def sync_case(self, request: CaseMemoryUpsertRequest) -> dict | None:
        status = str(request.status or "").upper()
        if status not in {"SOLVED", "CLOSED"}:
            return await self.case_memory_service.sync_case(request, None)

        ticket_memory = await self._load_or_refresh_ticket_memory(request)
        stored = await self.case_memory_service.sync_case(request, ticket_memory)
        if stored and request.owner_username:
            await self._consolidate_user_profile(request, ticket_memory)
        return stored

    async def _load_or_refresh_ticket_memory(self, request: CaseMemoryUpsertRequest) -> dict:
        try:
            work_order = ReplySuggestRequest(
                id=request.ticket_id,
                title=request.title,
                description=request.description,
                category=request.category,
                emotion=None,
                owner_username=request.owner_username,
                history=request.history,
            )
            return await self.ticket_memory_service.refresh(work_order)
        except Exception as exc:
            logger.warning("[memory-consolidation] ticket memory unavailable ticket_id=%s error=%s", request.ticket_id, exc)
            return dict(EMPTY_TICKET_MEMORY)

    async def _consolidate_user_profile(self, request: CaseMemoryUpsertRequest, ticket_memory: dict) -> None:
        user_messages = [item for item in request.history if str(item.role or "").lower() == "user"]
        if not user_messages:
            return
        prompt = f"""你是用户画像事实提取器。只提取用户明确表达、未来工单仍可能有用的稳定事实。

允许的 memory_key：{', '.join(MEMORY_KEY_TYPES)}。
规则：
1. 不提取耗材余量、清洁次数、当前故障状态、账号、姓名、联系方式。
2. 不把客服说法或模型推测当成用户事实。
3. 设备型号、地面类型、户型、宠物情况属于稳定事实。
4. 明确偏好可写 cleaning_preference；重复出现的问题可写 recurring_issue。
5. confidence 和 importance 范围0到1；证据不明确时不要输出。
6. 只输出严格 JSON：{{"items":[{{"memory_key":"floor_type","memory_value":"木地板","confidence":0.95,"importance":0.8}}]}}。

工单：{request.title}\n{request.description}
用户消息：
{json.dumps([item.content for item in user_messages], ensure_ascii=False)}
工作记忆：
{json.dumps(ticket_memory, ensure_ascii=False)}"""
        try:
            result = await self.model.ainvoke(prompt)
            payload = self._parse_json_object(getattr(result, "content", result))
            items = payload.get("items") if isinstance(payload.get("items"), list) else []
            source_reply_id = str(user_messages[-1].id or "")
            batch_id = f"ticket-{request.ticket_id}-{source_reply_id or request.status}-v{ticket_memory.get('version', 0)}"
            stored = self.user_memory_service.upsert_candidates(
                str(request.owner_username or ""),
                items,
                "EXPLICIT_USER",
                request.ticket_id,
                source_reply_id,
                batch_id,
            )
            logger.info("[memory-consolidation] profile candidates ticket_id=%s stored=%s", request.ticket_id, stored)
        except Exception as exc:
            logger.warning("[memory-consolidation] profile extraction skipped ticket_id=%s error=%s", request.ticket_id, exc)

    def _parse_json_object(self, content: object) -> dict:
        text = str(content or "")
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return {}
            try:
                value = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
        return value if isinstance(value, dict) else {}
