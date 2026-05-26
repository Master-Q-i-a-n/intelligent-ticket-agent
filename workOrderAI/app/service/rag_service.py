import asyncio
import json
import os
import time

from langchain_core import runnables
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langsmith import traceable

from workOrderAI.models.factory import chat_model, reranker_model
from workOrderAI.utils.config import config
from workOrderAI.utils.logger_handler import logger
from workOrderAI.utils.prompt_builder import (
    HYDE_PROMPT_PRE,
    QUESTION_HYDE_PROMPT,
    RAG_SUMMARIZE_PROMPT,
    STATEMENT_HYDE_PROMPT,
)
from workOrderAI.utils.vector_store import VectorStoreService


HYDE_MAX_TOKENS = 200
KNOWLEDGE_NO_ANSWER_SUMMARY = "抱歉，当前知识库中没有相关信息，建议咨询人工客服。"


class RagService:
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.retriever = None
        self.prompt_template = PromptTemplate.from_template(RAG_SUMMARIZE_PROMPT)
        self.chat_model = chat_model
        self.reranker_model = reranker_model
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

    def _init_chain(self, prompt_template: PromptTemplate, model=None):
        return prompt_template | (model or self.chat_model) | StrOutputParser()

    async def hyde_pre(self, query: str) -> str:
        try:
            pre_result = await self.hyde_pre_chain.ainvoke({"query": query})
            pre_type = json.loads(pre_result)["type"]
            if pre_type not in ["Question", "Fault_Statement", "Narrative_Keyword", "Chitchat_Invalid"]:
                pre_type = "Chitchat_Invalid"
            logger.info("[HyDE] intent=%s", pre_type)
            return pre_type
        except Exception as e:
            logger.error("[HyDE] intent classification failed: %s", e)
            return query

    async def initialize_retriever(self, query: str = None):
        if self.retriever is None:
            self.retriever = await self.vector_store.get_retriever(query)

    def _rerank_candidate_k(self) -> int:
        return int(config["vector_store"].get("rerank_candidate_k") or config["vector_store"]["k"])

    def _rerank_top_k(self) -> int:
        return int(config["vector_store"].get("rerank_top_k") or config["vector_store"]["k"])

    async def rerank_documents(self, query: str, documents: list, top_k: int | None = None, log_prefix: str = "[RAG]") -> list:
        selected_k = top_k or self._rerank_top_k()
        if not documents:
            return []

        started_at = time.perf_counter()
        try:
            reranked = await self.reranker_model.acompress_documents(documents, query)
            selected = list(reranked)[:selected_k]
            logger.info(
                "%s rerank finished, candidates=%s, selected=%s, elapsed=%.2fs",
                log_prefix,
                len(documents),
                len(selected),
                time.perf_counter() - started_at,
            )
            return selected
        except Exception as e:
            logger.error("%s rerank failed: %s", log_prefix, e, exc_info=True)
            return list(documents)[:selected_k]

    @traceable
    async def generate_hypothetical_document(self, query: str, chain: runnables.Runnable) -> str:
        try:
            hypothetical_doc = await chain.ainvoke({"query": query})
            logger.info("[HyDE] hypothetical document:\n%s", hypothetical_doc)
            return hypothetical_doc
        except Exception as e:
            logger.error("[HyDE] hypothetical document generation failed: %s", e)
            return query

    @traceable
    async def retrieve_document(self, query: str) -> list:
        try:
            retriever = await self.vector_store.get_retriever(query)
            started_at = time.perf_counter()
            documents = await retriever.ainvoke(query)
            documents = documents[:self._rerank_candidate_k()]
            logger.info("[RAG] retrieved %s candidate documents, elapsed=%.2fs", len(documents), time.perf_counter() - started_at)
            return await self.rerank_documents(query, documents, self._rerank_top_k(), "[RAG]")
        except Exception as e:
            logger.error("[RAG] retrieve failed: %s", e)
            return []

    async def retrieve_direct_documents(self, query: str, limit: int | None = None) -> list:
        started_at = time.perf_counter()
        try:
            retriever = await self.vector_store.get_retriever(query)
            documents = await retriever.ainvoke(query)
            if limit is not None:
                documents = documents[:limit]
            elapsed = time.perf_counter() - started_at
            logger.info("[RAG-light] direct retrieval finished, hits=%s, elapsed=%.2fs", len(documents), elapsed)
            return documents
        except Exception as e:
            logger.error("[RAG-light] direct retrieval failed: %s", e, exc_info=True)
            return []

    async def retrieve_direct_document_matches(self, query: str, limit: int | None = None) -> list[tuple]:
        started_at = time.perf_counter()
        try:
            matches = await self.vector_store.similarity_search_with_relevance_scores(
                query,
                k=limit or config["vector_store"]["k"],
            )
            elapsed = time.perf_counter() - started_at
            logger.info("[RAG-light] scored retrieval finished, hits=%s, elapsed=%.2fs", len(matches), elapsed)
            return matches
        except Exception as e:
            logger.error("[RAG-light] scored retrieval failed: %s", e, exc_info=True)
            return []

    async def retrieve_direct_reranked_matches(self, query: str) -> list[tuple]:
        matches = await self.retrieve_direct_document_matches(query, limit=self._rerank_candidate_k())
        if not matches:
            return []

        score_by_key = {
            self._document_match_key(document): score
            for document, score in matches
        }
        documents = [document for document, _ in matches]
        reranked_documents = await self.rerank_documents(query, documents, self._rerank_top_k(), "[RAG-light]")
        return [
            (
                document,
                self._normalize_score(
                    (document.metadata or {}).get("relevance_score"),
                    fallback=score_by_key.get(self._document_match_key(document), 0.0),
                ),
            )
            for document in reranked_documents
        ]

    @traceable
    async def get_documents_and_summary(self, query: str) -> dict:
        try:
            pre_type = await self.hyde_pre(query)
            if pre_type == "Question":
                hypothetical_doc = await self.generate_hypothetical_document(query, self.question_hyde_chain)
                documents = await self.retrieve_document(hypothetical_doc)
            elif pre_type == "Fault_Statement":
                hypothetical_doc = await self.generate_hypothetical_document(query, self.statement_hyde_chain)
                documents = await self.retrieve_document(hypothetical_doc)
            elif pre_type == "Narrative_Keyword":
                documents = await self.retrieve_document(query)
            else:
                return {"documents": [], "source_documents": [], "summary": KNOWLEDGE_NO_ANSWER_SUMMARY}

            if not documents:
                return {"documents": [], "source_documents": [], "summary": "抱歉，我没有找到相关的信息。"}

            source_documents = self._build_source_documents(documents)
            try:
                max_documents = 3

                async def summarize_document(index, doc):
                    single_context = f"【参考资料{index}】{doc.page_content}\n"
                    started_at = time.perf_counter()
                    summary = await asyncio.wait_for(
                        self.chain.ainvoke({"input": query, "context": single_context}),
                        timeout=30.0,
                    )
                    logger.info("[RAG] document %s summary finished, elapsed=%.2fs", index, time.perf_counter() - started_at)
                    return summary

                summaries = await asyncio.gather(
                    *[
                        summarize_document(index, doc)
                        for index, doc in enumerate(documents[:max_documents], 1)
                    ]
                )

                if len(summaries) == 1:
                    return {
                        "documents": [doc.page_content for doc in documents],
                        "source_documents": source_documents,
                        "summary": summaries[0],
                    }

                combined_context = "以下是多个文档的摘要，请综合这些信息生成最终回答：\n\n"
                for index, summary in enumerate(summaries, 1):
                    combined_context += f"【文档{index}摘要】{summary}\n\n"

                final_summary = await asyncio.wait_for(
                    self.chain.ainvoke({"input": query, "context": combined_context}),
                    timeout=30.0,
                )
                return {
                    "documents": [doc.page_content for doc in documents],
                    "source_documents": source_documents,
                    "summary": final_summary,
                }
            except asyncio.TimeoutError:
                logger.error("[RAG] summary timeout")
                return {
                    "documents": [doc.page_content for doc in documents],
                    "source_documents": source_documents,
                    "summary": "抱歉，生成摘要超时，请稍后再试。",
                }
        except Exception as e:
            logger.error("[RAG] summary failed: %s", e, exc_info=True)
            return {"documents": [], "source_documents": [], "summary": "抱歉，处理您的请求时出现了错误。"}

    @traceable
    async def rag_summary(self, query: str) -> str:
        result = await self.get_documents_and_summary(query)
        return result.get("summary", "抱歉，处理您的请求时出现了错误。")

    @traceable
    async def rag_summary_for_suggestion(self, query: str) -> dict:
        matches = await self.retrieve_direct_reranked_matches(query)
        if not matches:
            return {"summary": "抱歉，我没有找到相关的信息。", "sources": []}

        documents = [document for document, _ in matches]
        context = "".join(
            f"【参考资料{index}】{doc.page_content}\n"
            for index, doc in enumerate(documents, 1)
        )
        sources = self._build_source_documents_from_matches(matches)
        started_at = time.perf_counter()
        try:
            summary = await asyncio.wait_for(
                self.chain.ainvoke({"input": query, "context": context}),
                timeout=30.0,
            )
            logger.info("[RAG-light] summary finished, elapsed=%.2fs", time.perf_counter() - started_at)
            return {"summary": summary, "sources": sources}
        except asyncio.TimeoutError:
            logger.error("[RAG-light] summary timeout")
            return {"summary": "抱歉，生成摘要超时，请稍后再试。", "sources": sources}
        except Exception as e:
            logger.error("[RAG-light] summary failed: %s", e, exc_info=True)
            return {"summary": "抱歉，处理您的请求时出现了错误。", "sources": sources}

    async def rag_qa(self, query: str) -> dict:
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
            chunk_id = metadata.get("vector_id") or metadata.get("chunk_id") or ""
            key = document_id or chunk_id or title
            if not key or key in seen:
                continue
            seen.add(key)
            relevance_score = self._normalize_score(
                metadata.get("relevance_score"),
                fallback=max(0.0, 1.0 - index * 0.1),
            )
            sources.append(
                {
                    "id": document_id or key,
                    "document_id": document_id or key,
                    "title": title or "知识库文档",
                    "chunk_id": str(chunk_id or ""),
                    "score": relevance_score,
                    "relevance_score": relevance_score,
                }
            )
        return sources

    def _build_source_documents_from_matches(self, matches: list[tuple]) -> list[dict]:
        sources = []
        seen = set()
        for document, score in matches:
            metadata = document.metadata or {}
            source = metadata.get("source") or ""
            document_id = metadata.get("document_id") or self._document_id_from_source(source)
            title = metadata.get("title") or self._title_from_source(source)
            chunk_id = metadata.get("vector_id") or metadata.get("chunk_id") or ""
            key = chunk_id or document_id or title
            if not key or key in seen:
                continue
            seen.add(key)
            relevance_score = self._normalize_score(score)
            sources.append(
                {
                    "id": document_id or key,
                    "document_id": document_id or key,
                    "title": title or "知识库文档",
                    "chunk_id": str(chunk_id or ""),
                    "score": relevance_score,
                    "relevance_score": relevance_score,
                }
            )
        return sources

    def _document_match_key(self, document) -> str:
        metadata = document.metadata or {}
        return str(
            metadata.get("vector_id")
            or metadata.get("chunk_id")
            or metadata.get("document_id")
            or metadata.get("source")
            or document.page_content
        )

    def _normalize_score(self, score, fallback: float = 0.0) -> float:
        try:
            return round(float(score), 4)
        except (TypeError, ValueError):
            return round(float(fallback), 4)

    def _document_id_from_source(self, source: str) -> str:
        base_name = os.path.basename(source or "")
        return base_name.split("__", 1)[0] if "__" in base_name else base_name

    def _title_from_source(self, source: str) -> str:
        base_name = os.path.basename(source or "")
        display_name = base_name.split("__", 1)[1] if "__" in base_name else base_name
        return os.path.splitext(display_name)[0] or "知识库文档"


if __name__ == "__main__":
    async def main():
        service = RagService()
        await service.initialize_retriever()
        result = await service.rag_summary("小户型适合什么扫地机器人")
        print(result)

    asyncio.run(main())
