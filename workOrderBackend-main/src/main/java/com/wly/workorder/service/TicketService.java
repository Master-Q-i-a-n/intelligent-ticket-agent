package com.wly.workorder.service;

import com.wly.workorder.common.PageResult;
import com.wly.workorder.model.TicketModels.*;

public interface TicketService {
  PageResult<Feedback> pageFeedback(String keyword, TicketStatus status, int pageNum, int pageSize);

  Feedback getFeedbackById(String id);

  Feedback createFeedback(CreateFeedbackRequest request);

  Feedback replyFeedback(String id, ReplyFeedbackRequest request);

  PageResult<WorkOrder> pageWorkOrders(String keyword, TicketCategory category, TicketPriority priority, TicketStatus status, int pageNum, int pageSize);

  WorkOrderSummary getWorkOrderSummary(String keyword, TicketStatus status);

  WorkOrder updateWorkOrderStatus(String id, UpdateWorkOrderStatusRequest request);
  
  WorkOrder queryWorkOrderById(String id);

  AISuggestion getSuggestion(String id);
}
