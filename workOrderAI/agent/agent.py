from langsmith.run_helpers import P
from workOrderAI.agent.agent_tools import get_tools
from workOrderAI.agent.agent_middleware import get_middleware
from workOrderAI.models.factory import chat_model
from workOrderAI.utils.prompt_builder import AGENT_PROMPT
from langchain.agents import create_agent
import asyncio


class ReactAgent:
    def __init__(self, prompt: str=AGENT_PROMPT):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=prompt,
            tools=get_tools(),
            middleware=get_middleware(),
    )

    async def execute_stream(self, query: str):
        input_dict = {
            "messages": [
                {"role": "user", "content": query},
            ]
        }

        async for chunk in self.agent.astream(input_dict, stream_mode="values", context={"report": False}):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"

    async def execute_invoke(self, query: str) -> str:
        input_dict = {
            "messages": [
                {"role": "user", "content": query},
            ]
        }

        result = await self.agent.ainvoke(input_dict, context={"report": False})
        latest_message = result["messages"][-1]
        return latest_message.content.strip() if latest_message.content else ""

if __name__ == '__main__':
    async def main():
        agent = ReactAgent()
        # async for chunk in agent.execute_stream("购买哪种机器人比较好？结果50字以内"):
        #     print(chunk, end="", flush=True)
        result = await agent.execute_invoke("购买哪种机器人比较好？结果50字以内")
        print(result)
  
    asyncio.run(main())
