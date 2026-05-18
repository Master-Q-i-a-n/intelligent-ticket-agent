package com.wly.workorder.auth;

import com.wly.workorder.common.ApiResponse;
import com.wly.workorder.model.TicketModels.ServiceGroup;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class DefaultAuthService implements AuthService {
  private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
  private final JdbcTemplate jdbcTemplate;
  private final Map<String, AuthSession> sessions = new ConcurrentHashMap<>();

  public DefaultAuthService(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  @Override
  public LoginResponse register(RegisterRequest request) {
    String username = request.getUsername().trim();
    String displayName = request.getDisplayName().trim();
    String avatarUrl = request.getAvatarUrl() == null ? "" : request.getAvatarUrl().trim();
    ServiceGroup serviceGroup = resolveServiceGroup(request.getRole(), request.getServiceGroup());

    Integer exists = jdbcTemplate.queryForObject(
      "select count(*) from wo_user where username = ?",
      Integer.class,
      username
    );
    if (exists != null && exists > 0) {
      throw new AuthException(ApiResponse.withCode(400, "username already exists", null));
    }

    String now = now();
    jdbcTemplate.update(
      "insert into wo_user (id, username, password, display_name, avatar_url, role, service_group, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
      "user-" + UUID.randomUUID().toString().substring(0, 8),
      username,
      request.getPassword(),
      displayName,
      avatarUrl,
      request.getRole().name(),
      serviceGroup == null ? "" : serviceGroup.name(),
      now,
      now
    );

    AuthSession session = new AuthSession(UUID.randomUUID().toString(), username, displayName, avatarUrl, request.getRole(), serviceGroup);
    sessions.put(session.getToken(), session);
    return new LoginResponse(session.getToken(), toProfile(session));
  }

  @Override
  public LoginResponse login(LoginRequest request) {
    AuthUser user = jdbcTemplate.query(
      "select username, password, display_name, avatar_url, role, service_group from wo_user where username = ?",
      rs -> rs.next()
        ? new AuthUser(
          rs.getString("username"),
          rs.getString("password"),
          rs.getString("display_name"),
          rs.getString("avatar_url"),
          AuthRole.valueOf(rs.getString("role")),
          readServiceGroup(rs.getString("service_group"))
        )
        : null,
      request.getUsername()
    );
    if (user == null || !user.getPassword().equals(request.getPassword())) {
      throw new AuthException(ApiResponse.withCode(401, "invalid username or password", null));
    }
    AuthSession session = new AuthSession(UUID.randomUUID().toString(), user.getUsername(), user.getDisplayName(), user.getAvatarUrl(), user.getRole(), user.getServiceGroup());
    sessions.put(session.getToken(), session);
    return new LoginResponse(session.getToken(), toProfile(session));
  }

  @Override
  public UserProfile me() {
    AuthSession session = requireSession();
    return toProfile(session);
  }

  @Override
  public DemoAccountResponse getDemoAccount(String username) {
    String normalized = normalizeDemoUsername(username);
    if (normalized == null) {
      throw new AuthException(ApiResponse.withCode(400, "unsupported demo account", null));
    }
    AuthUser user = jdbcTemplate.query(
      "select username, password, display_name, avatar_url, role, service_group from wo_user where username = ?",
      rs -> rs.next()
        ? new AuthUser(
          rs.getString("username"),
          rs.getString("password"),
          rs.getString("display_name"),
          rs.getString("avatar_url"),
          AuthRole.valueOf(rs.getString("role")),
          readServiceGroup(rs.getString("service_group"))
        )
        : null,
      normalized
    );
    if (user == null) {
      throw new AuthException(ApiResponse.withCode(404, "demo account not found", null));
    }
    return new DemoAccountResponse(user.getUsername(), user.getPassword());
  }

  @Override
  public UserProfile updateProfile(UpdateProfileRequest request) {
    AuthSession session = requireSession();
    String avatarUrl = request.getAvatarUrl() == null ? "" : request.getAvatarUrl().trim();
    jdbcTemplate.update(
      "update wo_user set display_name = ?, avatar_url = ?, updated_at = ? where username = ?",
      request.getDisplayName().trim(),
      avatarUrl,
      now(),
      session.getUsername()
    );
    updateSessions(session.getUsername(), updatedSession -> {
      updatedSession.setDisplayName(request.getDisplayName().trim());
      updatedSession.setAvatarUrl(avatarUrl);
    });
    return me();
  }

  @Override
  public UserProfile updatePassword(UpdatePasswordRequest request) {
    AuthSession session = requireSession();
    AuthUser user = jdbcTemplate.query(
      "select username, password, display_name, avatar_url, role, service_group from wo_user where username = ?",
      rs -> rs.next()
        ? new AuthUser(
          rs.getString("username"),
          rs.getString("password"),
          rs.getString("display_name"),
          rs.getString("avatar_url"),
          AuthRole.valueOf(rs.getString("role")),
          readServiceGroup(rs.getString("service_group"))
        )
        : null,
      session.getUsername()
    );
    if (user == null || !user.getPassword().equals(request.getOldPassword())) {
      throw new AuthException(ApiResponse.withCode(400, "old password is incorrect", null));
    }
    jdbcTemplate.update(
      "update wo_user set password = ?, updated_at = ? where username = ?",
      request.getNewPassword(),
      now(),
      session.getUsername()
    );
    return me();
  }

  @Override
  public void deleteAccount() {
    AuthSession session = requireSession();
    String username = session.getUsername();
    int deleted = jdbcTemplate.update("delete from wo_user where username = ?", username);
    if (deleted == 0) {
      throw new AuthException(ApiResponse.withCode(404, "account not found", null));
    }
    sessions.entrySet().removeIf(entry -> username.equals(entry.getValue().getUsername()));
  }

  @Override
  public AuthSession requireSession() {
    String token = AuthTokenResolver.resolve();
    AuthSession session = sessions.get(token);
    if (session == null) {
      throw new AuthException(ApiResponse.withCode(401, "unauthorized", null));
    }
    return session;
  }

  public void logout(String token) {
    sessions.remove(token);
  }

  private UserProfile toProfile(AuthSession session) {
    return new UserProfile(session.getUsername(), session.getDisplayName(), session.getAvatarUrl(), session.getRole(), session.getServiceGroup());
  }

  private void updateSessions(String username, java.util.function.Consumer<AuthSession> consumer) {
    sessions.values().stream()
      .filter(session -> username.equals(session.getUsername()))
      .forEach(consumer);
  }

  private String normalizeDemoUsername(String username) {
    String normalized = String.valueOf(username == null ? "" : username).trim().toLowerCase();
    if ("user".equals(normalized) || "admin".equals(normalized)) {
      return normalized;
    }
    return null;
  }

  private ServiceGroup resolveServiceGroup(AuthRole role, ServiceGroup serviceGroup) {
    if (role == AuthRole.ADMIN) {
      if (serviceGroup == null) {
        throw new AuthException(ApiResponse.withCode(400, "admin service group is required", null));
      }
      return serviceGroup;
    }
    return null;
  }

  private ServiceGroup readServiceGroup(String value) {
    if (value == null || value.isBlank()) {
      return null;
    }
    return ServiceGroup.valueOf(value);
  }

  private static String now() {
    return LocalDateTime.now().format(FMT);
  }
}
