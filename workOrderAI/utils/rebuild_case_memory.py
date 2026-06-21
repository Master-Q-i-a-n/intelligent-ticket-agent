import asyncio

from workOrderAI.app.service.case_memory_service import CaseMemoryService


async def main():
    result = await CaseMemoryService().rebuild_vectors()
    print(f"案例向量重建完成：总记录 {result['total']}，启用记录 {result['active']}。")


if __name__ == "__main__":
    asyncio.run(main())
