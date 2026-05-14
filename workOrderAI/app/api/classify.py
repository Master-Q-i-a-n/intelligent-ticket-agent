"""
AI分类 API路由
提供工单自动分类接口
"""
from workOrderAI.utils.config import config
from workOrderAI.utils.logger_handler import logger
from workOrderAI.app.model.request import ClassifyRequest
import json
from workOrderAI.app.service.classify_service import ClassifyService
from workOrderAI.app.model.response import ClassifyResponse

from fastapi import APIRouter, Response
from workOrderAI.app.model.database import get_db_connection



api = APIRouter(prefix=config['router']['prefix'], tags=['classify'])

@api.post('/classify', response_model=ClassifyResponse)
def classify_work_order(request: ClassifyRequest):
    """
    工单分类接口
    """
    classify_service = ClassifyService()
    request_id = request.ticket_id
    logger.info(f"分类服务调用，工单ID: {request_id}")
    classification = classify_service.get_classification(request)
    res = json.loads(classification)

    problem_type = res['problem_type']
    priority = res['priority']
    user_sentiment = res['user_sentiment']
    confidence_score = res['confidence_score']
    analysis_reasoning = res['analysis_reasoning']
    logger.debug(f"分类结果: {problem_type}, {priority}, {user_sentiment}, {confidence_score}, {analysis_reasoning}")

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            logger.info(f"准备更新数据库: id={request_id}, problem_type={problem_type}")
            cursor.execute("UPDATE wo_feedback SET category = %s, priority = %s, emotion = %s WHERE id = %s", (problem_type, priority, user_sentiment, request_id))
            if cursor.rowcount > 0:
                logger.info(f"工单 {request_id} 已更新")
            else:
                logger.warning(f"工单 {request_id} 不存在，未更新")
        conn.commit()
    except Exception as e:
        logger.error(f"数据库更新失败: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

    return ClassifyResponse(
        problem_type=problem_type,
        priority=priority,
        user_sentiment=user_sentiment,
        confidence_score=confidence_score,
        analysis_reasoning=analysis_reasoning,
    )
