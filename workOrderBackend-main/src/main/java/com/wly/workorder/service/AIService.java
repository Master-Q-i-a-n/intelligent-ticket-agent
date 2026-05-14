package com.wly.workorder.service;
import java.util.concurrent.CompletableFuture;
import com.fasterxml.jackson.databind.JsonNode;

public interface AIService {
    public CompletableFuture<JsonNode> complete(String prompt);
    
}
