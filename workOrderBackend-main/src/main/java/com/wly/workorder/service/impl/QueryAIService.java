package com.wly.workorder.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wly.workorder.config.WorkOrderAIProperties;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;
import com.wly.workorder.model.TicketModels.WorkOrder;

@Component
public class QueryAIService {
  private static final Logger log = LoggerFactory.getLogger(QueryAIService.class);

  private final WorkOrderAIProperties properties;
  private final RestTemplate restTemplate;
  private final Executor asyncExecutor;
  private final ObjectMapper objectMapper;

  public QueryAIService(WorkOrderAIProperties properties, ObjectMapper objectMapper) {
    this.properties = properties;
    this.restTemplate = new RestTemplate();
    this.asyncExecutor = Executors.newFixedThreadPool(5);
    this.objectMapper = objectMapper;
  }

  public CompletableFuture<JsonNode> classifyTicketAsync(String ticketId, String title, String description, List<Map<String, String>> replies) {
    if (!properties.getAiClassification().isEnabled() || !properties.getAiClassification().isTriggerOnCreate()) {
      return CompletableFuture.completedFuture(null);
    }
    return CompletableFuture.supplyAsync(() -> {
      try {
        Map<String, Object> requestBody = Map.of(
          "ticket_id", ticketId,
          "title", title,
          "description", description,
          "replies", replies
        );
        ResponseEntity<JsonNode> response = callAI("/ai/classify", requestBody);
        log.info("AI分类成功, ticketId: {}", ticketId);
        return response.getBody();
      } catch (Exception e) {
        log.error("AI分类失败, ticketId: {}", ticketId, e);
        return null;
      }
    }, asyncExecutor);
  }

  public CompletableFuture<JsonNode> qualityCheckAsync(String replyId, String ticketId, Map<String, Object> ticketContext, String serviceReplyContent) {
    if (!properties.getAiQualityCheck().isEnabled() || !properties.getAiQualityCheck().isTriggerOnReply()) {
      return CompletableFuture.completedFuture(null);
    }
    return CompletableFuture.supplyAsync(() -> {
      try {
        Map<String, Object> requestBody = Map.of(
          "reply_id", replyId,
          "ticket_id", ticketId,
          "ticket_context", ticketContext,
          "service_reply_content", serviceReplyContent
        );
        ResponseEntity<JsonNode> response = callAI("/api/v1/quality-check", requestBody);
        log.info("AI质检成功, replyId: {}", replyId);
        return response.getBody();
      } catch (Exception e) {
        log.error("AI质检失败, replyId: {}", replyId, e);
        return null;
      }
    }, asyncExecutor);
  }

  public JsonNode suggestReply(WorkOrder workorder) {
    if (!properties.getAiReplySuggestion().isEnabled()) {
      return null;
    }
    try {
      Map<String, Object> requestBody = Map.of(
        "id", workorder.getId(),
        "title", workorder.getTitle(),
        "description", workorder.getDescription(),
        "category", workorder.getCategory(),
        "emotion", workorder.getEmotion(),
        "history", workorder.getReplies()
      );
      ResponseEntity<JsonNode> response = callAI("/ai/suggestion", requestBody);
      log.info("AI回复建议生成成功, ticketId: {}", workorder.getId());
      return response.getBody();
    } catch (Exception e) {
      log.error("AI回复建议生成失败, ticketId: {}", workorder.getId(), e);
      return null;
    }
  }

  public JsonNode knowledgeQA(String question) {
    if (!properties.getKnowledgeBase().isEnabled()) {
      return null;
    }
    try {
      Map<String, Object> requestBody = Map.of("question", question);
      ResponseEntity<JsonNode> response = callAI("/api/v1/knowledge/qa", requestBody);
      return response.getBody();
    } catch (Exception e) {
      log.error("知识库问答失败", e);
      return null;
    }
  }

  public ResponseEntity<JsonNode> callAI(String path, Object requestBody) {
    String url = properties.getAiService().getBaseUrl() + path;
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    HttpEntity<Object> entity = new HttpEntity<>(requestBody, headers);

    int retryCount = 0;
    int maxRetries = properties.getAiService().getRetryCount();
    Exception lastException = null;

    while (retryCount <= 0) {
      try {
        return restTemplate.postForEntity(url, entity, JsonNode.class);
      } catch (Exception e) {
        lastException = e;
        retryCount++;
        if (retryCount <= maxRetries) {
          log.warn("AI服务调用失败, 第{}次重试: {}", retryCount, e.getMessage());
          try {
            Thread.sleep(1000 * retryCount);
          } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
          }
        }
      }
    }
    throw new RuntimeException("AI服务调用失败，已重试" + maxRetries + "次", lastException);
  }
}
