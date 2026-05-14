from abc import ABC, abstractmethod
from typing import Optional
from dotenv import load_dotenv

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.document_compressors.dashscope_rerank import DashScopeRerank
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
# from langchain_ollama import OllamaEmbeddings
from workOrderAI.utils.config import config



# 加载环境变量
load_dotenv()


class BaseModelFactory(ABC):
    """基础模型工厂"""

    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """生成模型"""
        pass


class ChatModelFactory(BaseModelFactory):
    """聊天模型工厂"""
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """生成模型"""
        return ChatTongyi(
            model=config['model']['chat_model'],
            streaming=True,
            top_p=0.7,
        )


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return DashScopeEmbeddings(model=config['model']['embedding_model'])



class RerankerModelFactory(BaseModelFactory):
    """重排序模型工厂"""
    def generator(self):
        return DashScopeRerank(model=config['model']['reranker_model'])


chat_model = ChatModelFactory().generator()
embed_model = EmbeddingsFactory().generator()
reranker_model = RerankerModelFactory().generator()
