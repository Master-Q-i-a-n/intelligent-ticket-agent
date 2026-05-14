package com.wly.workorder.config;

import java.util.List;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "workorder")
public class WorkOrderAIProperties {

  private AIService aiService = new AIService();
  private AIClassification aiClassification = new AIClassification();
  private AIQualityCheck aiQualityCheck = new AIQualityCheck();
  private AIReplySuggestion aiReplySuggestion = new AIReplySuggestion();
  private KnowledgeBase knowledgeBase = new KnowledgeBase();

  @Data
  public static class AIService {
    private String baseUrl = "http://localhost:8003";
    private int timeout = 30000;
    private int retryCount = 2;
    private boolean asyncEnabled = true;
  }

  @Data
  public static class AIClassification {
    private boolean enabled = true;
    private boolean triggerOnCreate = true;
    private List<String> problemTypes = List.of("技术故障", "产品咨询", "功能需求", "投诉建议", "账单问题");
    private List<String> priorities = List.of("P0", "P1", "P2", "P3");
    private List<String> sentiments = List.of("正面", "中性", "负面", "愤怒");
  }

  @Data
  public static class AIQualityCheck {
    private boolean enabled = true;
    private boolean triggerOnReply = true;
    private List<String> autoTriggerRoles = List.of("admin", "supervisor");
    private int discrepancyThreshold = 20;
    private boolean reviewRequired = true;
  }

  @Data
  public static class AIReplySuggestion {
    private boolean enabled = true;
    private boolean ragEnabled = true;
    private int maxSuggestions = 1;
    private boolean showSource = true;
  }

  @Data
  public static class KnowledgeBase {
    private boolean enabled = true;
    private int maxContentLength = 5000;
    private List<String> supportedCategories = List.of("技术文档", "常见问题", "操作指南", "产品说明");
    private int chunkSize = 500;
    private int chunkOverlap = 50;
  }
}
