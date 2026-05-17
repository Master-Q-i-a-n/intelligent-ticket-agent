import asyncio
import os
import time
from langchain_core import runnables
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langsmith import traceable
import json
from workOrderAI.utils.vector_store import VectorStoreService
# from workOrderAI.app.service.reorder_service import reorder_service
from workOrderAI.models.factory import chat_model
from workOrderAI.utils.logger_handler import logger
from workOrderAI.utils.prompt_builder import HYDE_PROMPT_PRE, STATEMENT_HYDE_PROMPT, QUESTION_HYDE_PROMPT, RAG_SUMMARIZE_PROMPT


HYDE_MAX_TOKENS = 200
KNOWLEDGE_NO_ANSWER_SUMMARY = "抱歉，当前知识库中没有相关信息，建议咨询人工客服。"


class RagService:
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.retriever = None  # 延迟初始化
        self.prompt_text = RAG_SUMMARIZE_PROMPT
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.chat_model = chat_model
        self.hyde_model = self.chat_model.bind(max_tokens=HYDE_MAX_TOKENS)
        self.chain = self._init_chain(self.prompt_template)
        self.hyde_pre_prompt_template = PromptTemplate.from_template(HYDE_PROMPT_PRE)
        self.question_hyde_prompt_template = PromptTemplate.from_template(QUESTION_HYDE_PROMPT)
        self.statement_hyde_prompt_template = PromptTemplate.from_template(STATEMENT_HYDE_PROMPT)
        self.hyde_pre_chain = self._init_chain(self.hyde_pre_prompt_template)
        self.question_hyde_chain = self._init_chain(
            self.question_hyde_prompt_template,
            model=self.hyde_model,
        )
        self.statement_hyde_chain = self._init_chain(
            self.statement_hyde_prompt_template,
            model=self.hyde_model,
        )

    async def hyde_pre(self, query: str) -> str:
        """
        生成HyDE意图分类
        :param query: 用户查询
        :return: 意图分类
        """
        try:
            hyde_pre_chain = (
                self.hyde_pre_prompt_template
                | self.chat_model
                | StrOutputParser()
            )
            pre_result = await hyde_pre_chain.ainvoke({"query": query})
            pre_type = json.loads(pre_result)['type']

            if pre_type not in ['Question', 'Fault_Statement', 'Narrative_Keyword', 'Chitchat_Invalid']:
                pre_type = 'Chitchat_Invalid'

            logger.info(f"【HyDE】意图分类:{pre_type}")

            return pre_type

        except Exception as e:
            logger.error(f"【HyDE】生成意图分类失败: {e}")
            return query

    async def initialize_retriever(self, query: str = None):
        """
        初始化检索器
        :param query: 查询语句，用于动态调整权重
        """
        if self.retriever is None:
            self.retriever = await self.vector_store.get_retriever(query)


    def _init_chain(self, prompt_template: PromptTemplate, model=None):
        """初始化链"""
        chain = (
                prompt_template
                | (model or self.chat_model)
                | StrOutputParser()
        )
        return chain

    @traceable
    async def generate_hypothetical_document(self, query: str, chain: runnables.Runnable) -> str:
        """
        使用HyDE技术生成假设性文档
        :param query: 用户查询
        :param chain: Runnable链
        :return: 假设性文档内容
        """
        try:
            # hyde_chain = (
            #     prompt_template
            #     | self.chat_model
            #     | StrOutputParser()
            # )
            hypothetical_doc = await chain.ainvoke({"query": query})
            logger.info(f"【HyDE】生成的假设性文档:\n{hypothetical_doc}")
            return hypothetical_doc
        except Exception as e:
            logger.error(f"【HyDE】生成假设性文档失败: {e}")
            return query

    @traceable
    async def retrieve_document(self, query: str) -> list:
        """使用HyDE技术 从向量数据库里检索文档"""
        try:
            # 确保检索器已初始化，传递query参数
            if self.retriever is None:
                await self.initialize_retriever(query)
            
            # 使用HyDE技术生成假设性文档
            # logger.info(f"【HyDE】开始处理查询: {query}")
            # hypothetical_doc = await self.generate_hypothetical_document(query)
            
            # 使用假设性文档进行检索
            logger.info(f"【retrieve】使用假设性文档进行检索")
            documents = await self.retriever.ainvoke(query)
            logger.info(f"【retrieve】检索到 {len(documents)} 个相关文档")
            
            return documents
        except Exception as e:
            logger.error(f"【retrieve】检索文档失败: {e}")
            return []

    async def retrieve_direct_documents(self, query: str, limit: int | None = None) -> list:
        """直接使用原始 query 检索文档，供轻量 RAG 路径使用。"""
        started_at = time.perf_counter()
        try:
            retriever = await self.vector_store.get_retriever(query)
            documents = await retriever.ainvoke(query)
            if limit is not None:
                documents = documents[:limit]
            elapsed = time.perf_counter() - started_at
            logger.info(f"【RAG-light】直接检索完成，命中 {len(documents)} 个文档，耗时: {elapsed:.2f}秒")
            return documents
        except Exception as e:
            logger.error(f"【RAG-light】直接检索失败: {e}", exc_info=True)
            return []

    @traceable
    async def reorder_documents(self, query: str, documents: list) -> list:
        """
        对文档进行重排序
        :param query: 查询语句
        :param documents: 文档列表
        :return: 重排序后的文档列表
        """
        result = await reorder_service.reorder_documents(query, documents)
        if result["success"]:
            # 提取重排序后的文档内容
            reordered_documents = [doc.get("document", "") for doc in result["documents"]]
            logger.info(f"【RAG】文档重排序成功，返回 {len(reordered_documents)} 个文档")
            return reordered_documents
        else:
            logger.warning(f"【RAG】重排序失败: {result['error']}")
            return documents

    @traceable
    async def get_documents_and_summary(self, query: str) -> dict:
        """
        获取文档列表和摘要
        :param query: 查询语句
        :return: 包含文档列表和摘要的字典
        """
        try:
            # 先分类查询
            pre_type = await self.hyde_pre(query)
            hypothetical_doc = ""
            if pre_type == 'Question':
                hypothetical_doc = await self.generate_hypothetical_document(query, self.question_hyde_chain)
                documents = await self.retrieve_document(hypothetical_doc)
            elif pre_type == 'Fault_Statement':
                hypothetical_doc = await self.generate_hypothetical_document(query, self.statement_hyde_chain)
                documents = await self.retrieve_document(hypothetical_doc)
            elif pre_type == 'Narrative_Keyword':
                documents = await self.retrieve_document(query)
            else:
                return {
                    "documents": [],
                    "source_documents": [],
                    "summary": KNOWLEDGE_NO_ANSWER_SUMMARY,
                }

            # 对文档进行重排序
            # reordered_documents = await self.reorder_documents(query, document_contents)
            reordered_documents = documents

            # 如果没有检索到文档
            if not reordered_documents:
                return {
                    "documents": [],
                    "source_documents": [],
                    "summary": "抱歉，我没有找到相关的信息。"
                }

            source_documents = self._build_source_documents(reordered_documents)

            # 使用分批总结策略
            try:
                # 对每个文档单独总结（使用线程池并发处理）
                individual_summaries = []
                max_documents = 3  # 使用前3个最相关的文档
                
                # 定义单个文档总结函数
                async def summarize_document(i, doc):
                    logger.info(f"【RAG】正在总结第{i}个文档")
                    # 为单个文档构建上下文
                    single_context = f"【参考资料{i}】:{doc.page_content}\n"
                    # 生成单个文档的摘要
                    import time
                    start_time = time.time()
                    single_summary = await asyncio.wait_for(
                        self.chain.ainvoke({"input": query, "context": single_context}),
                        timeout=30.0  # 单个文档总结超时时间
                    )
                    end_time = time.time()
                    logger.info(f"【RAG】第{i}个文档总结耗时: {end_time - start_time:.2f}秒")
                    return single_summary
                
                # 使用线程池并发处理文档总结
                tasks = []
                for i, doc in enumerate(reordered_documents[:max_documents], 1):
                    tasks.append(summarize_document(i, doc))
                
                # 并发执行所有总结任务，最多5个线程
                import time
                start_time = time.time()
                individual_summaries = await asyncio.gather(*tasks)
                end_time = time.time()
                logger.info(f"【RAG】所有文档总结完成，总耗时: {end_time - start_time:.2f}秒")

                # 如果只有一个文档，直接返回其摘要
                if len(individual_summaries) == 1:
                    logger.info(f"【RAG】生成摘要成功")
                    return {
                        "documents": [doc.page_content for doc in reordered_documents],
                        "source_documents": source_documents,
                        "summary": individual_summaries[0]
                    }

                # 合并多个文档的摘要，生成最终总结
                combined_context = "以下是多个文档的摘要，请综合这些信息生成最终的回答：\n\n"
                for i, summary in enumerate(individual_summaries, 1):
                    combined_context += f"【文档{i}摘要】:{summary}\n\n"

                logger.info(f"【RAG】合并摘要完成，开始生成最终总结")
                
                # 生成最终总结
                final_summary = await asyncio.wait_for(
                    self.chain.ainvoke({"input": query, "context": combined_context}),
                    timeout=30.0  # 最终总结超时时间
                )
                
                logger.info(f"【RAG】生成摘要成功")
                return {
                    "documents": [doc.page_content for doc in reordered_documents],
                    "source_documents": source_documents,
                    "summary": final_summary
                }
            except asyncio.TimeoutError:
                logger.error(f"【RAG】生成摘要超时")
                return {
                    "documents": [doc.page_content for doc in reordered_documents],
                    "source_documents": source_documents,
                    "summary": "抱歉，生成摘要超时，请稍后再试。"
                }
        except Exception as e:
            logger.error(f"【RAG】生成摘要失败: {e}", exc_info=True)
            return {
                "documents": [],
                "source_documents": [],
                "summary": "抱歉，处理您的请求时出现了错误。"
            }

    @traceable
    async def rag_summary(self, query: str) -> str:
        """RAG 摘要"""
        result = await self.get_documents_and_summary(query)
        return result.get("summary", "抱歉，处理您的请求时出现了错误。")

    @traceable
    async def rag_summary_for_suggestion(self, query: str) -> str:
        """回复建议专用的轻量 RAG 摘要路径。"""
        documents = await self.retrieve_direct_documents(query, limit=2)
        if not documents:
            return "抱歉，我没有找到相关的信息。"

        context = "".join(
            f"【参考资料{i}】:{doc.page_content}\n"
            for i, doc in enumerate(documents, 1)
        )
        started_at = time.perf_counter()
        try:
            summary = await asyncio.wait_for(
                self.chain.ainvoke({"input": query, "context": context}),
                timeout=30.0,
            )
            elapsed = time.perf_counter() - started_at
            logger.info(f"【RAG-light】轻量总结完成，耗时: {elapsed:.2f}秒")
            return summary
        except asyncio.TimeoutError:
            logger.error("【RAG-light】轻量总结超时")
            return "抱歉，生成摘要超时，请稍后再试。"
        except Exception as e:
            logger.error(f"【RAG-light】轻量总结失败: {e}", exc_info=True)
            return "抱歉，处理您的请求时出现了错误。"

    async def rag_qa(self, query: str) -> dict:
        """RAG 问答，返回答案和引用来源。"""
        result = await self.get_documents_and_summary(query)
        return {
            "answer": result.get("summary", "抱歉，处理您的请求时出现了错误。"),
            "source_documents": result.get("source_documents", []),
        }

    def _build_source_documents(self, documents: list) -> list[dict]:
        sources = []
        seen = set()
        for index, doc in enumerate(documents):
            metadata = doc.metadata or {}
            source = metadata.get("source") or ""
            document_id = metadata.get("document_id") or self._document_id_from_source(source)
            title = metadata.get("title") or self._title_from_source(source)
            key = document_id or title
            if not key or key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "id": document_id or key,
                    "title": title or "知识库文档",
                    "relevance_score": max(0.0, 1.0 - index * 0.1),
                }
            )
        return sources

    def _document_id_from_source(self, source: str) -> str:
        base_name = os.path.basename(source or "")
        return base_name.split("__", 1)[0] if "__" in base_name else base_name

    def _title_from_source(self, source: str) -> str:
        base_name = os.path.basename(source or "")
        display_name = base_name.split("__", 1)[1] if "__" in base_name else base_name
        return os.path.splitext(display_name)[0] or "知识库文档"

if __name__ == '__main__':
    import asyncio
    
    async def main():
        service = RagService()
        await service.initialize_retriever()
        result = await service.rag_summary("小户型适合什么扫地机器人")
        print(result)
    
    asyncio.run(main())
