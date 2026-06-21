import asyncio

from workOrderAI.app.model.database import get_db_connection
from workOrderAI.app.model.request import CaseMemoryUpsertRequest, ReplyMessage, ReplySuggestRequest
from workOrderAI.app.service.case_memory_service import CaseMemoryService
from workOrderAI.app.service.memory_consolidation_service import MemoryConsolidationService
from workOrderAI.app.service.user_memory_service import UserMemoryService


def _load_tickets() -> list[CaseMemoryUpsertRequest]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select id, code, title, description, status, category, owner_username
                from wo_feedback order by created_at
                """
            )
            tickets = list(cursor.fetchall() or [])
            cursor.execute(
                """
                select feedback_id, id, role, content, created_at
                from wo_feedback_reply order by created_at
                """
            )
            replies = list(cursor.fetchall() or [])
    finally:
        conn.close()

    replies_by_ticket: dict[str, list[ReplyMessage]] = {}
    for row in replies:
        replies_by_ticket.setdefault(str(row["feedback_id"]), []).append(
            ReplyMessage(
                id=str(row.get("id") or ""),
                role=str(row.get("role") or "user"),
                content=str(row.get("content") or ""),
                created_at=str(row.get("created_at") or ""),
            )
        )

    requests = []
    for row in tickets:
        history = replies_by_ticket.get(str(row["id"]), [])
        final_reply = next(
            (item.content for item in reversed(history) if item.role == "service" and item.content.strip()),
            None,
        )
        requests.append(
            CaseMemoryUpsertRequest(
                ticket_id=str(row["id"]),
                ticket_code=str(row.get("code") or ""),
                title=str(row.get("title") or ""),
                description=str(row.get("description") or ""),
                final_reply=final_reply,
                status=str(row.get("status") or ""),
                category=str(row.get("category") or ""),
                owner_username=str(row.get("owner_username") or ""),
                history=history,
            )
        )
    return requests


async def rebuild_all_memories() -> dict:
    consolidation = MemoryConsolidationService()
    tickets = _load_tickets()
    cases = 0
    for request in tickets:
        await consolidation.ticket_memory_service.refresh(
            ReplySuggestRequest(
                id=request.ticket_id,
                title=request.title,
                description=request.description,
                category=request.category,
                owner_username=request.owner_username,
                history=request.history,
            )
        )
        if await consolidation.sync_case(request):
            cases += 1

    profiles = UserMemoryService().rebuild_from_user_records()
    vector_result = await CaseMemoryService().rebuild_vectors()
    return {
        "tickets": len(tickets),
        "cases": cases,
        "profiles": profiles,
        "vectors": vector_result,
    }


if __name__ == "__main__":
    print(asyncio.run(rebuild_all_memories()))
