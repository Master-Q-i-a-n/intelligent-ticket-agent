from workOrderAI.app.model.request import ReplySuggestRequest, ReplyMessage
from workOrderAI.app.model.response import ReplySuggestResponse
from workOrderAI.app.service.suggest_service import SuggestService
from workOrderAI.utils.logger_handler import logger
from workOrderAI.utils.config import config
from fastapi import APIRouter


api = APIRouter(prefix=config['router']['prefix'], tags=['reply_suggest'])

@api.post('/suggestion', response_model=ReplySuggestResponse)
async def get_suggestion(request: ReplySuggestRequest):

    logger.info(f"建议服务调用，工单ID: {request.id}")
    try:
        suggest_service = SuggestService()
        suggestion = await suggest_service.get_suggestion(request)
        logger.debug(f"建议服务返回: {suggestion}")
        
        return ReplySuggestResponse(suggested_reply=suggestion)

    except Exception as e:
        logger.error(f"建议服务调用失败: {e}")






