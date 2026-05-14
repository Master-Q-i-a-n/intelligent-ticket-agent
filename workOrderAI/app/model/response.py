"""
Pydantic数据模型 - 响应体
定义所有API接口的响应数据结构
"""
from pydantic import BaseModel, Field
from typing import List, Optional


# ==========================================
# AI分类接口响应模型
# ==========================================
class ClassifyResponse(BaseModel):
    """AI工单分类响应"""
    problem_type: str                                   # 问题类型: 技术故障/产品咨询/功能需求/投诉建议/账单问题
    priority: str                                       # 优先级: P0/P1/P2/P3
    user_sentiment: str                                 # 用户情绪: 正面/中性/负面/愤怒
    confidence_score: float                             # AI置信度 (0.0-1.0)
    analysis_reasoning: str                             # AI分析依据


# ==========================================
# AI质检接口响应模型
# ==========================================
class QualityCheckResponse(BaseModel):
    """AI质检评分响应"""
    inspection_id: str                                  # 质检记录ID
    ai_total_score: float                               # AI总分 (0-100)
    ai_problem_understanding: float                     # AI评分-问题理解 (0-25)
    ai_solution: float                                  # AI评分-解决方案 (0-40)
    ai_info_accuracy: float                             # AI评分-信息准确 (0-20)
    ai_service_attitude: float                          # AI评分-服务态度 (0-15)
    ai_reasoning: str                                   # AI评分依据
    improvement_suggestions: str                        # AI改进建议
    discrepancy_flag: bool                              # 差异标记 (AI与人工分差>20)


# ==========================================
# 质检审核响应模型
# ==========================================
class QualityReviewResponse(BaseModel):
    """质检审核响应"""
    inspection_id: str                                  # 质检记录ID
    final_score: float                                  # 最终确认分数
    review_status: str                                  # 审核状态: pending/approved/revised
    discrepancy_flag: bool                              # 差异标记


# ==========================================
# 知识库引用来源模型
# ==========================================
class SourceDocument(BaseModel):
    """知识库引用文档"""
    id: str                                             # 知识库文档ID
    title: str                                          # 文档标题
    relevance_score: float                              # 相关度分数


class SourceTemplate(BaseModel):
    """历史工单模板引用"""
    ticket_id: str                                      # 历史工单ID
    similarity_score: float                             # 相似度分数


# ==========================================
# AI回复建议接口响应模型
# ==========================================
class ReplySuggestResponse(BaseModel):
    """AI智能回复建议响应"""
    suggested_reply: str                                # AI建议回复内容
    source_documents: List[SourceDocument] = []         # 引用知识库文档列表


# ==========================================
# 知识库管理响应模型
# ==========================================
class KnowledgeResponse(BaseModel):
    """知识库文档响应"""
    id: str                                             # 文档ID
    title: str                                          # 文档标题
    content: str                                        # 文档内容
    category: Optional[str] = None                      # 分类
    tags: List[str] = []                                # 标签列表
    author_id: str                                      # 创建者
    status: str                                         # 状态: active/archived/draft
    created_at: str                                     # 创建时间


class KnowledgeListResponse(BaseModel):
    """知识库列表响应"""
    total: int                                          # 总记录数
    items: List[KnowledgeResponse]                      # 文档列表


class KnowledgeQAResponse(BaseModel):
    """知识库问答响应"""
    answer: str                                         # AI回答内容
    source_documents: List[SourceDocument] = []         # 引用来源
