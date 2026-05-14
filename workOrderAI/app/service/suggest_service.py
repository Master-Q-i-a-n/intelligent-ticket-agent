from workOrderAI.utils.prompt_builder import REPLY_SUGGESTION_SYSTEM_PROMPT
from workOrderAI.models.factory import chat_model
from workOrderAI.agent.agent import ReactAgent
from workOrderAI.app.model.request import ReplySuggestRequest, ReplyMessage
from workOrderAI.app.model.response import ReplySuggestResponse



class SuggestService:
    def __init__(self):
        self.agent = ReactAgent(REPLY_SUGGESTION_SYSTEM_PROMPT)

    async def get_suggestion(self, work_order: ReplySuggestRequest):
        """
        获取工单建议
        """
        input = f'标题：{work_order.title}\n内容：{work_order.description}\n'
        input += '用户(user)和客服(service)的对话记录：\n'
        for reply in work_order.history:
            input += f'{reply.role}：{reply.content}\n'

        suggestion_reply = await self.agent.execute_invoke(input)

        return suggestion_reply

if __name__ == '__main__':
    import asyncio
    async def main():
        suggest_service = SuggestService()
        work_order = ReplySuggestRequest(
            id='123456',
            title='扫地机器人坏了',
            description='扫地机器人不能工作，怎么办？',
            category='咨询',
            emotion='愤怒',
            history=[
                ReplyMessage(role='service', content='我也不知道'),
                ReplyMessage(role='user', content='怎么当客服的？？？'),
            ]
        )
        suggestion = await suggest_service.get_suggestion(work_order)
        print(suggestion)

    asyncio.run(main())

