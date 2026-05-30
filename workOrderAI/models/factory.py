from abc import ABC, abstractmethod
from typing import Any, Optional
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
    def __init__(self, model_name: str | None = None, top_p: float = 0.7, model_kwargs: dict[str, Any] | None = None):
        self.model_name = model_name or config['model']['chat_model']
        self.top_p = top_p
        self.model_kwargs = model_kwargs or {}

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """生成模型"""
        return ChatTongyi(
            model=self.model_name,
            streaming=False,
            top_p=self.top_p,
            model_kwargs=self.model_kwargs,
        )


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return DashScopeEmbeddings(model=config['model']['embedding_model'])



class RerankerModelFactory(BaseModelFactory):
    """重排序模型工厂"""
    def generator(self):
        return DashScopeRerank(model=config['model']['reranker_model'])


chat_model = ChatModelFactory().generator()
judge_model = ChatModelFactory(
    model_name=config["model"].get("judge_model", config["model"]["chat_model"]),
    top_p=0.2,
).generator()
router_model = ChatModelFactory(
    model_name=config["model"].get("router_model", "qwen3-32b"),
    top_p=0.1,
    model_kwargs={"enable_thinking": False},
).generator()
embed_model = EmbeddingsFactory().generator()
reranker_model = RerankerModelFactory().generator()
