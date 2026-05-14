package com.wly.workorder.model;

import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.HashMap;
import java.util.Map;



public final class TicketModels {
  private TicketModels() {
  }

  public enum TicketStatus {
    PENDING,
    PROCESSING,
    SOLVED,
    CLOSED
  }

  public enum TicketPriority {
    低,
    中,
    高,
    紧急,
    UNKNOWN
  }

  public enum TicketCategory {
    技术故障,
    产品咨询,
    功能需求,
    投诉建议,
    账单问题,
    其他,
    UNKNOWN
  }

  public enum TicketEmotion {
    愤怒,
    焦虑,
    失望,
    急迫,
    困惑,
    满意,
    平静,
    UNKNOWN
  }

  public static final HashMap<String, String> priorityMap = new HashMap<>(Map.of(
      "LOW", "低",
      "MEDIUM", "中",
      "HIGH", "高",
      "URGENT", "紧急"
  ));

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class Attachment {
    private String uid;
    private String name;
    private String url;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class FeedbackReply {
    private String id;
    private String role;
    private String author;
    private String content;
    private String createdAt;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class WorkOrder {
    private String id;
    private String code;
    private String title;
    private String description;
    private TicketCategory category;
    private TicketPriority priority;
    private TicketEmotion emotion;
    private TicketStatus status;
    private String ownerUsername;
    private String accountName;
    private String assignee;
    private String createdAt;
    private String updatedAt;
    private List<String> images;
    private List<Attachment> attachments;
    private List<FeedbackReply> replies;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class Feedback {
    private String id;
    private String code;
    private String title;
    private String description;
    // private String category;
    // private TicketPriority priority;
    private TicketStatus status;
    private String ownerUsername;
    private String accountName;
    // private String assignee;
    private String createdAt;
    private String updatedAt;
    private List<String> images;
    private List<Attachment> attachments;
    private List<FeedbackReply> replies;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class AISuggestion {
    private String suggestedReply;

  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class WorkOrderSummary {
    private long total;
    private long pending;
    private long processing;
    private long solved;
    private long closed;
  }

  @Data
  @NoArgsConstructor
  @AllArgsConstructor
  public static class CreateFeedbackRequest {
    @NotBlank
    private String title;
    @NotBlank
    private String description;
    private String accountName;
    private List<String> images;
    private List<Attachment> attachments;
  }

  @Data
  @NoArgsConstructor
  @AllArgsConstructor
  public static class ReplyFeedbackRequest {
    @NotBlank
    private String content;

    private String author;
  }

  @Data
  @NoArgsConstructor
  @AllArgsConstructor
  public static class UpdateWorkOrderStatusRequest {
    @NotNull
    private TicketStatus status;

    private String remark;
  }
}
