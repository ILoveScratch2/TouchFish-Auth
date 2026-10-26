export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)tf_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = csrfToken();
  if (token && init.method && init.method !== "GET") {
    headers.set("X-CSRF-Token", token);
  }
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "same-origin",
  });

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string } })
      ?.error;
    throw new ApiError(
      error?.code ?? "request_failed",
      error?.message ?? `请求失败（${response.status}）`,
      response.status,
    );
  }
  return payload as T;
}

export type User = {
  id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  has_password: boolean;
  role: "user" | "admin";
  status: "active" | "suspended";
  created_at: number;
};

export type Connection = {
  id: string;
  instance_id: string;
  instance_name: string;
  instance_url: string;
  tfv5_uid: number;
  tfv5_username: string;
  bind_channel: "platform" | "legacy";
  bound_at: number;
  last_login_at: number | null;
  has_cached_session: boolean;
};

export type Instance = {
  id: string;
  base_url: string;
  display_name: string;
  issuer: string;
  audience: string | null;
};

export type SessionRow = {
  id: string;
  created_at: number;
  last_seen_at: number | null;
  expires_at: number;
  ip: string | null;
  user_agent: string | null;
  current: boolean;
};

export type OAuthAccountProvider = {
  id: string;
  name: string;
  linked: boolean;
  login: string | null;
  orphan?: boolean;
};

export type AuthMethod = {
  id: string;
  kind: "password" | "tfv5" | "oauth2";
  display_name: string;
  enabled: boolean;
  hint?: string;
};

export type RegisterResult = {
  user?: User;
  pending_verification?: boolean;
  verification_id?: string;
  email?: string;
};

export type SiteConfig = {
  site_name: string;
  announcement: string;
  captcha: {
    enabled: boolean;
    on_login: boolean;
    provider: "turnstile" | "hcaptcha" | null;
    site_key: string;
  };
  email_verification: boolean;
  tfv5_login_auto_signup: boolean;
  oauth_providers: { id: string; name: string }[];
  oauth_apps: {
    implemented: boolean;
    self_service: boolean;
    max_per_user: number;
  };
  registration: { allowed: boolean; reason: string };
  instance: Instance | null;
};

export type OAuthProvider = {
  id: string;
  provider_key: string;
  display_name: string;
  client_id: string;
  client_secret_set: boolean;
  authorize_url: string;
  token_url: string;
  userinfo_url: string;
  emails_url: string;
  scope: string;
  token_auth_method: "post" | "basic";
  uid_field: string;
  username_field: string;
  email_field: string;
  allowed_hosts: string;
  enabled: boolean;
  complete: boolean;
  linked_accounts: number;
};

export type OAuthTemplate = Record<string, string>;

export type OAuthProviderInput = {
  provider_key?: string;
  display_name?: string;
  client_id?: string;
  client_secret?: string;
  authorize_url?: string;
  token_url?: string;
  userinfo_url?: string;
  emails_url?: string;
  scope?: string;
  token_auth_method?: "post" | "basic";
  uid_field?: string;
  username_field?: string;
  email_field?: string;
  allowed_hosts?: string;
  enabled?: boolean;
};

export type SettingSpec = {
  key: string;
  type: "bool" | "int" | "str" | "text" | "enum" | "secret";
  label?: string;
  category?: string;
  options?: string[];
  min?: number;
  max?: number;
};

export type AdminSettings = Record<string, string | number | boolean> & {
  _spec: SettingSpec[];
};

export type AuditEntry = {
  id: string;
  at: number;
  event: string;
  user_id: string | null;
  ip: string | null;
  user_agent: string | null;
  detail: string | null;
};

export const api = {
  site: () => request<SiteConfig>("/api/site"),
  me: () => request<{ user: User | null }>("/api/auth/me"),
  registrationStatus: () =>
    request<{ allowed: boolean; reason: string; mode: string }>(
      "/api/auth/registration",
    ),
  register: (body: {
    username: string;
    password: string;
    email?: string;
    captcha_token?: string;
  }) =>
    request<RegisterResult>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  login: (body: {
    identifier: string;
    password: string;
    captcha_token?: string;
  }) =>
    request<{ user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  verifyEmail: (body: { verification_id: string; code: string }) =>
    request<{ user: User }>("/api/auth/verify-email", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resendVerification: (body: { identifier: string; password: string }) =>
    request<{ verification_id: string; email: string }>(
      "/api/auth/resend-verification",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  logout: () =>
    request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  changePassword: (body: { current_password?: string; new_password: string }) =>
    request<{ ok: boolean }>("/api/auth/password", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** 请求密码重置验证码。后端返回 202 */
  forgotPassword: (body: { identifier: string; captcha_token?: string }) =>
    request<{ ok: boolean; message: string }>("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resetPassword: (body: {
    email: string;
    code: string;
    new_password: string;
  }) =>
    request<{ ok: boolean; revoked: number }>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  instances: () => request<{ instances: Instance[] }>("/api/instances"),
  connections: () => request<{ connections: Connection[] }>("/api/connections"),
  bind: (body: {
    identifier: string;
    password: string;
    instance_id?: string;
  }) =>
    request<{
      connection: { channel: string; tfv5_uid: number; tfv5_username: string };
    }>("/api/connections/bind", { method: "POST", body: JSON.stringify(body) }),
  tfv5Login: (body: {
    identifier: string;
    password: string;
    instance_id?: string;
    captcha_token?: string;
  }) =>
    request<{ user: User; tfv5_uid: number }>("/api/connections/tfv5-login", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  unbind: (instanceId: string) =>
    request<{ ok: boolean }>(`/api/connections/${instanceId}`, {
      method: "DELETE",
    }),

  sessions: () => request<{ sessions: SessionRow[] }>("/api/auth/sessions"),
  revokeSession: (id: string) =>
    request<{ ok: boolean }>(`/api/auth/sessions/${id}`, { method: "DELETE" }),

  oauthAccounts: () =>
    request<{ providers: OAuthAccountProvider[]; has_password: boolean }>(
      "/api/auth/oauth/accounts",
    ),
  oauthUnlink: (providerId: string) =>
    request<{ ok: boolean }>(`/api/auth/oauth/accounts/${providerId}`, {
      method: "DELETE",
    }),

  authorizeComplete: (body: {
    client_id: string;
    state?: string;
    target?: string;
  }) =>
    request<{ ticket: string; expires_in: number; state?: string }>(
      "/api/authorize/complete",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  developer: () =>
    request<{
      issuer: string;
      jwks_uri: string;
      discovery_uri: string;
      auth_config_uri: string;
      active_kid: string;
      active_fingerprint: string;
      all_kids: string[];
      token_ttl: number;
      ticket_ttl: number;
      registration_mode: string;
      instances: Instance[];
    }>("/api/developer/summary"),

  adminOverview: () =>
    request<{
      me: { id: string; username: string; role: string };
      stats: {
        users: number;
        admins: number;
        active_sessions: number;
        connections: number;
        bound_users: number;
      };
      users: User[];
      instances: Instance[];
      keys: { active_kid: string; all_kids: string[] };
      registration_mode: string;
    }>("/api/admin/overview"),
  adminSetRole: (userId: string, role: "user" | "admin") =>
    request<{ ok: boolean }>(`/api/admin/users/${userId}/role`, {
      method: "POST",
      body: JSON.stringify({ role }),
    }),
  adminSetStatus: (userId: string, status: "active" | "suspended") =>
    request<{ ok: boolean }>(`/api/admin/users/${userId}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  adminUpsertInstance: (body: {
    id: string;
    base_url: string;
    display_name: string;
    audience?: string;
  }) =>
    request<{ instance: Instance }>(`/api/admin/instances/${body.id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  adminRotateKeys: () =>
    request<{ active_kid: string; all_kids: string[] }>(
      "/api/admin/keys/rotate",
      {
        method: "POST",
      },
    ),
  adminDeleteInstance: (instanceId: string) =>
    request<{ ok: boolean }>(`/api/admin/instances/${instanceId}`, {
      method: "DELETE",
    }),
  adminLogoutAll: (userId: string) =>
    request<{ ok: boolean; revoked: number }>(
      `/api/admin/users/${userId}/logout-all`,
      {
        method: "POST",
      },
    ),
  /** 不传 newPassword 时后端生成一次性临时密码，仅在本次响应里返回。 */
  adminResetPassword: (userId: string, newPassword?: string) =>
    request<{ ok: boolean; revoked: number; temporary_password?: string }>(
      `/api/admin/users/${userId}/reset-password`,
      {
        method: "POST",
        body: JSON.stringify({ new_password: newPassword ?? null }),
      },
    ),
  /** 第三方登录平台（本平台作为 client） */
  adminOauthProviders: () =>
    request<{ providers: OAuthProvider[]; callback_base: string }>(
      "/api/admin/oauth/providers",
    ),
  adminOauthTemplates: () =>
    request<{ templates: OAuthTemplate[] }>("/api/admin/oauth/templates"),
  adminCreateOauthProvider: (body: OAuthProviderInput) =>
    request<{ ok: boolean; provider_key: string }>(
      "/api/admin/oauth/providers",
      { method: "POST", body: JSON.stringify(body) },
    ),
  adminUpdateOauthProvider: (id: string, body: OAuthProviderInput) =>
    request<{ ok: boolean; provider_key: string }>(
      `/api/admin/oauth/providers/${id}`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  adminDeleteOauthProvider: (id: string, force = false) =>
    request<{ ok: boolean; provider_key: string; linked_accounts: number }>(
      `/api/admin/oauth/providers/${id}${force ? "?force=1" : ""}`,
      { method: "DELETE" },
    ),
  /** 管理员直接建号。不传 password 时后端生成一次性临时密码。 */
  adminCreateUser: (body: {
    username: string;
    password?: string;
    email?: string;
    role?: "user" | "admin";
  }) =>
    request<{ ok: boolean; user: User; temporary_password?: string }>(
      "/api/admin/users",
      {
        method: "POST",
        body: JSON.stringify({
          username: body.username,
          password: body.password ?? null,
          email: body.email ?? null,
          role: body.role ?? "user",
        }),
      },
    ),
  adminSettings: () => request<AdminSettings>("/api/admin/settings"),
  adminCaptchaTest: () =>
    request<{
      ok: boolean;
      codes: string[];
      message: string;
      reachable: boolean;
      detail: string;
      hint: string;
      provider: string;
    }>("/api/admin/captcha/test", { method: "POST" }),
  adminUpdateSettings: (values: Record<string, string | number | boolean>) =>
    request<AdminSettings>("/api/admin/settings", {
      method: "PUT",
      body: JSON.stringify({ values }),
    }),
  adminAudit: (limit = 100, event = "") =>
    request<{ entries: AuditEntry[] }>(
      `/api/admin/audit?limit=${limit}${event ? `&event=${encodeURIComponent(event)}` : ""}`,
    ),
};

export async function fetchAuthConfig(): Promise<{
  issuer: string;
  authorization_endpoint: string;
  methods: AuthMethod[];
}> {
  const response = await fetch("/.well-known/auth-config", {
    credentials: "same-origin",
  });
  return response.json();
}
