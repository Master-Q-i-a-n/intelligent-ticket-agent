"""
Pydantic数据模型 - 请求体
定义所有API接口的请求参数结构
"""
from pydantic import BaseModel, Field
from typing import List, Optional


# ==========================================
# AI分类接口请求模型
# ==========================================
class ReplyMessage(BaseModel):
    """对话中的单条消息"""
    id: Optional[str] = None
    role: str                                           # 角色: user/service
    content: str                                        # 消息内容
    created_at: Optional[str] = None


class ClassifyRequest(BaseModel):
    """AI工单分类请求"""
    ticket_id: str                                      # 工单ID
    title: str                                          # 工单标题
    description: str                                    # 工单描述
    replies: List[ReplyMessage] = []                    # 历史回复记录
    update_category: bool = True                        # 是否更新分类；后续重算仅更新优先级和情绪


# ==========================================
# AI质检接口请求模型
# ==========================================
class TicketContext(BaseModel):
    """工单上下文信息"""
    title: str                                          # 工单标题
    description: str                                    # 工单描述
    all_replies: List[ReplyMessage]                     # 所有回复记录


class QualityCheckRequest(BaseModel):
    """AI质检评分请求"""
    reply_id: str                                       # 客服回复ID
    ticket_id: str                                      # 工单ID
    ticket_context: TicketContext                       # 工单上下文
    service_reply_content: str                          # 客服回复内容


# ==========================================
# 质检审核请求模型
# ==========================================
class QualityReviewRequest(BaseModel):
    """主管审核质检请求"""
    action: str                                         # 操作: approve(通过)/revised(修改)
    human_total_score: Optional[float] = None           # 人工总分(action=revised时必填)
    review_notes: Optional[str] = None                  # 审核备注


# ==========================================
# AI回复建议接口请求模型
# ==========================================
class ReplySuggestRequest(BaseModel):
    """AI智能回复建议请求"""
    id: str                                      # 工单ID
    title: str                                   # 工单标题
    description: str                             # 工单描述
    category: Optional[str] = None               # 分类: 技术文档/常见问题/操作指南/产品说明
    emotion: Optional[str] = None                # 情感: 正常/情感化
    owner_username: Optional[str] = None
    history: List[ReplyMessage]                  # 对话历史


class CaseMemoryUpsertRequest(BaseModel):
    """历史工单案例沉淀请求"""
    ticket_id: str
    ticket_code: str
    title: str
    description: str
    final_reply: Optional[str] = None
    status: str
    category: Optional[str] = None
    owner_username: Optional[str] = None
    history: List[ReplyMessage] = Field(default_factory=list)


# ==========================================
# 知识库管理请求模型
# ==========================================
class KnowledgeCreateRequest(BaseModel):
    """创建知识库文档请求"""
    title: str                                          # 文档标题
    content: str                                        # 文档内容
    category: Optional[str] = None                      # 分类: 技术文档/常见问题/操作指南/产品说明
    tags: List[str] = []                                # 标签列表
    author_id: str                                      # 创建者用户名


class KnowledgeQueryRequest(BaseModel):
    """知识库查询参数"""
    keyword: Optional[str] = None                       # 搜索关键词
    category: Optional[str] = None                      # 按分类筛选
    page: int = 1                                       # 页码
    page_size: int = 10                                 # 每页数量


class KnowledgeQARequest(BaseModel):
    """知识库问答请求"""
    question: str                                       # 用户问题


class KnowledgeUploadRequest(BaseModel):
    """知识库文档上传请求"""
    file_name: str                                      # 原始文件名
    content_type: Optional[str] = None                  # MIME 类型
    content_base64: str                                 # 文件内容 base64
    created_by: str                                     # 上传人
