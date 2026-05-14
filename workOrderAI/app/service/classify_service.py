from workOrderAI.utils.prompt_builder import CLASSIFICATION_SYSTEM_PROMPT
from workOrderAI.models.factory import chat_model
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from workOrderAI.app.model.request import *


class ClassifyService:
    def __init__(self):
        self.prompt_text = CLASSIFICATION_SYSTEM_PROMPT
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = chat_model
        self.chain = self._init_chain()

    def _init_chain(self):
        return self.prompt_template | self.model | StrOutputParser()

    def get_classification(self, work_order: ClassifyRequest):
        """
        获取工单分类
        """
        input = f'标题：{work_order.title}\n内容：{work_order.description}\n'
        if work_order.category:
            input += f'分类：{work_order.category}\n'
        if work_order.emotion:
            input += f'情感：{work_order.emotion}\n'
        input += '用户(user)和客服(service)的对话记录：\n'
        for reply in work_order.history:
            input += f'{reply.role}：{reply.content}\n'
        return self.chain.invoke(
            {
                'input': input
            }
        )

if __name__ == '__main__':
    classify_service = ClassifyService()
    work_order = ClassifyRequest(
        ticket_id='123456',
        title='鼠标坏了',
        description='鼠标充不上电，着急用，怎么办？',
        # replies=[
        #     ChatMessage(role='user', content='用户咨询问题'),
        #     ChatMessage(role='service', content='客服回复问题'),
        # ]
    )
    classification = classify_service.get_classification(work_order)
    print(classification)


