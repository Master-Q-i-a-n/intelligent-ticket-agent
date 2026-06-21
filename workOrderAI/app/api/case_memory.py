from fastapi import APIRouter

from workOrderAI.app.model.request import CaseMemoryUpsertRequest
from workOrderAI.app.service.case_memory_service import CaseMemoryService
from workOrderAI.app.service.memory_consolidation_service import MemoryConsolidationService
from workOrderAI.app.service.ticket_memory_service import TicketMemoryService
from workOrderAI.utils.config import config


api = APIRouter(prefix=config["router"]["prefix"], tags=["case_memory"])


@api.post("/case-memory")
async def upsert_case_memory(request: CaseMemoryUpsertRequest):
    stored = await MemoryConsolidationService().sync_case(request)
    return {
        "stored": stored is not None,
        "case_id": stored["id"] if stored else "",
    }


@api.delete("/case-memory/{ticket_id}")
async def delete_case_memory(ticket_id: str):
    await CaseMemoryService().delete_case(ticket_id)
    TicketMemoryService().delete(ticket_id)
    return {"deleted": True, "ticket_id": ticket_id}
