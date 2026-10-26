import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Check, Copy, Loader2, Plus, RotateCw, Trash2 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  PageWrapper,
  listContainerVariants,
  listItemVariants,
} from "@/components/ui/motion";
import { Skeleton } from "@/components/ui/primitives";
import {
  ApiError,
  api,
  type OAuthProvider,
  type OAuthProviderInput,
  type OAuthTemplate,
} from "@/lib/api";
import { invalidateSiteConfig } from "@/lib/site";

type FormState = {
  provider_key: string;
  display_name: string;
  client_id: string;
  client_secret: string;
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
};

const EMPTY: FormState = {
  provider_key: "",
  display_name: "",
  client_id: "",
  client_secret: "",
  authorize_url: "",
  token_url: "",
  userinfo_url: "",
  emails_url: "",
  scope: "",
  token_auth_method: "post",
  uid_field: "id",
  username_field: "login",
  email_field: "email",
  allowed_hosts: "",
  enabled: true,
};

function fromProvider(item: OAuthProvider): FormState {
  return {
    provider_key: item.provider_key,
    display_name: item.display_name,
    client_id: item.client_id,
    client_secret: "",
    authorize_url: item.authorize_url,
    token_url: item.token_url,
    userinfo_url: item.userinfo_url,
    emails_url: item.emails_url,
    scope: item.scope,
    token_auth_method: item.token_auth_method,
    uid_field: item.uid_field,
    username_field: item.username_field,
    email_field: item.email_field,
    allowed_hosts: item.allowed_hosts,
    enabled: item.enabled,
  };
}

export function OAuthProvidersPage() {
  const [providers, setProviders] = useState<OAuthProvider[] | null>(null);
  const [callbackBase, setCallbackBase] = useState("");
  const [templates, setTemplates] = useState<OAuthTemplate[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<OAuthProvider | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  const [deleteTarget, setDeleteTarget] = useState<OAuthProvider | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [copiedKey, setCopiedKey] = useState("");

  const load = useCallback(async () => {
    const result = await api.adminOauthProviders();
    setProviders(result.providers);
    setCallbackBase(result.callback_base);
  }, []);

  useEffect(() => {
    load().catch(() => setProviders(null));
    api
      .adminOauthTemplates()
      .then((result) => setTemplates(result.templates))
      .catch(() => setTemplates([]));
  }, [load]);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setFormError("");
    setOpen(true);
  }

  function openEdit(item: OAuthProvider) {
    setEditing(item);
    setForm(fromProvider(item));
    setFormError("");
    setOpen(true);
  }

  function applyTemplate(key: string) {
    const template = templates.find((item) => item.key === key);
    if (!template) return;
    setForm((current) => ({
      ...current,
      provider_key: template.provider_key ?? current.provider_key,
      display_name: template.display_name ?? current.display_name,
      authorize_url: template.authorize_url ?? "",
      token_url: template.token_url ?? "",
      userinfo_url: template.userinfo_url ?? "",
      emails_url: template.emails_url ?? "",
      scope: template.scope ?? "",
      token_auth_method:
        template.token_auth_method === "basic" ? "basic" : "post",
      uid_field: template.uid_field ?? "id",
      username_field: template.username_field ?? "login",
      email_field: template.email_field ?? "email",
      allowed_hosts: template.allowed_hosts ?? "",
    }));
  }

  async function save() {
    if (saving) return;
    setSaving(true);
    setFormError("");
    const body: OAuthProviderInput = { ...form };
    if (editing && !form.client_secret.trim()) delete body.client_secret;
    try {
      if (editing) {
        await api.adminUpdateOauthProvider(editing.id, body);
        setNotice(`已更新 ${form.display_name}`);
      } else {
        await api.adminCreateOauthProvider(body);
        setNotice(`已添加 ${form.display_name}`);
      }
      setOpen(false);
      // 登录页用的是缓存过的站点配置，改完要让下次渲染重新拉
      invalidateSiteConfig();
      await load();
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "保存失败，请稍后重试",
      );
    } finally {
      setSaving(false);
    }
  }

  async function remove(force: boolean) {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setError("");
    try {
      await api.adminDeleteOauthProvider(deleteTarget.id, force);
      setNotice(`已删除 ${deleteTarget.display_name}`);
      setDeleteTarget(null);
      invalidateSiteConfig();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败，请稍后重试");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  async function copyCallback(item: OAuthProvider) {
    const value = `${callbackBase}/${item.provider_key}/callback`;
    try {
      await navigator.clipboard.writeText(value);
      setCopiedKey(item.id);
      window.setTimeout(() => setCopiedKey(""), 1500);
    } catch {
    }
  }

  return (
    <PageWrapper className="space-y-6">
      <PageHeader
        title="第三方登录"
        description="把 GitHub、GitLab、Google 或任意标准 OAuth2/OIDC 平台接入本站登录；客户端会自动显示这些入口"
      />

      {error ? <Alert variant="destructive">{error}</Alert> : null}
      {notice ? <Alert variant="info">{notice}</Alert> : null}

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>已接入的平台</CardTitle>
            <CardDescription>
              凭证不全或已停用的平台不会出现在登录页。secret 只保存不回显。
            </CardDescription>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setError("");
                load().catch(() => setError("刷新失败"));
              }}
            >
              <RotateCw />
              刷新
            </Button>
            <Button variant="primary" size="sm" onClick={openCreate}>
              <Plus />
              添加平台
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {providers === null ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : providers.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              还没有接入任何第三方平台。点「添加平台」从模板开始。
            </div>
          ) : (
            <motion.div
              variants={listContainerVariants}
              initial="initial"
              animate="animate"
              className="divide-y divide-border"
            >
              {providers.map((item) => (
                <motion.div
                  key={item.id}
                  variants={listItemVariants}
                  className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{item.display_name}</span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {item.provider_key}
                      </span>
                      {item.enabled ? (
                        <StatusBadge tone="success">已启用</StatusBadge>
                      ) : (
                        <StatusBadge tone="neutral">已停用</StatusBadge>
                      )}
                      {item.complete ? null : (
                        <StatusBadge tone="warning">配置不完整</StatusBadge>
                      )}
                      {item.linked_accounts > 0 ? (
                        <StatusBadge tone="info">
                          {item.linked_accounts} 个账号已绑定
                        </StatusBadge>
                      ) : null}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Client ID：{item.client_id || "未填写"} · Secret：
                      {item.client_secret_set ? "已配置" : "未配置"}
                    </div>
                    <button
                      type="button"
                      onClick={() => copyCallback(item)}
                      className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                    >
                      {copiedKey === item.id ? (
                        <Check className="size-3" />
                      ) : (
                        <Copy className="size-3" />
                      )}
                      回调地址 {callbackBase}/{item.provider_key}/callback
                    </button>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openEdit(item)}
                    >
                      编辑
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget(item)}
                    >
                      <Trash2 />
                      删除
                    </Button>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? `编辑 ${editing.display_name}` : "添加第三方平台"}
        description="端点、scope 与字段映射都可在「高级」里调整；不同平台返回结构不一样时改这里。"
        className="max-w-xl"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button variant="primary" onClick={save} disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="animate-spin" />
                  保存中…
                </>
              ) : (
                "保存"
              )}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          {formError ? <Alert variant="destructive">{formError}</Alert> : null}

          {!editing && templates.length > 0 ? (
            <Field>
              <FieldLabel htmlFor="template">从模板开始</FieldLabel>
              <select
                id="template"
                defaultValue=""
                onChange={(event) => applyTemplate(event.target.value)}
                className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm"
              >
                <option value="">选择模板（可留空手填）</option>
                {templates.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.display_name || item.key}
                  </option>
                ))}
              </select>
              <FieldDescription>
                模板只填端点与常见字段名，凭证仍需你自己申请
              </FieldDescription>
            </Field>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="provider_key">标识</FieldLabel>
              <Input
                id="provider_key"
                value={form.provider_key}
                placeholder="github"
                onChange={(event) =>
                  setForm({ ...form, provider_key: event.target.value })
                }
              />
              <FieldDescription>
                小写字母/数字/下划线，出现在回调地址里；已绑定账号时不能改
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="display_name">显示名</FieldLabel>
              <Input
                id="display_name"
                value={form.display_name}
                placeholder="GitHub"
                onChange={(event) =>
                  setForm({ ...form, display_name: event.target.value })
                }
              />
              <FieldDescription>登录页按钮上的文字</FieldDescription>
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="client_id">Client ID</FieldLabel>
              <Input
                id="client_id"
                value={form.client_id}
                onChange={(event) =>
                  setForm({ ...form, client_id: event.target.value })
                }
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="client_secret">Client Secret</FieldLabel>
              <Input
                id="client_secret"
                type="password"
                value={form.client_secret}
                placeholder={
                  editing?.client_secret_set ? "已配置，留空不修改" : "尚未配置"
                }
                onChange={(event) =>
                  setForm({ ...form, client_secret: event.target.value })
                }
              />
            </Field>
          </div>

          {/* 两列排 */}
          <div className="grid gap-4 sm:grid-cols-2">
            {(
              [
                ["authorize_url", "授权地址"],
                ["token_url", "令牌地址"],
                ["userinfo_url", "用户资料地址"],
                ["emails_url", "邮箱列表地址（可选）"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key}>
                <FieldLabel htmlFor={key}>{label}</FieldLabel>
                <Input
                  id={key}
                  value={form[key]}
                  placeholder="https://"
                  onChange={(event) =>
                    setForm({ ...form, [key]: event.target.value })
                  }
                />
              </Field>
            ))}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="scope">Scope</FieldLabel>
              <Input
                id="scope"
                value={form.scope}
                placeholder="read:user user:email"
                onChange={(event) =>
                  setForm({ ...form, scope: event.target.value })
                }
              />
            </Field>

            <Field>
              <FieldLabel htmlFor="token_auth_method">
                令牌端点认证方式
              </FieldLabel>
              <select
                id="token_auth_method"
                value={form.token_auth_method}
                onChange={(event) =>
                  setForm({
                    ...form,
                    token_auth_method:
                      event.target.value === "basic" ? "basic" : "post",
                  })
                }
                className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm"
              >
                <option value="post">
                  client_secret_post（表单，GitHub 等）
                </option>
                <option value="basic">
                  client_secret_basic（Basic 头，严格 OIDC）
                </option>
              </select>
            </Field>
          </div>
          <FieldDescription>
            令牌端点被对方以 401 / invalid_client
            拒绝时，通常就是「认证方式」选错了
          </FieldDescription>
          <details className="rounded-lg border border-border px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium">
              高级：字段映射与第三方域名
            </summary>
            <div className="mt-4 space-y-4">
              <div className="grid gap-4 sm:grid-cols-3">
                {(
                  [
                    ["uid_field", "标识字段", "id"],
                    ["username_field", "用户名字段", "login"],
                    ["email_field", "邮箱字段", "email"],
                  ] as const
                ).map(([key, label, placeholder]) => (
                  <Field key={key}>
                    <FieldLabel htmlFor={key}>{label}</FieldLabel>
                    <Input
                      id={key}
                      value={form[key]}
                      placeholder={placeholder}
                      onChange={(event) =>
                        setForm({ ...form, [key]: event.target.value })
                      }
                    />
                  </Field>
                ))}
              </div>
              <Field>
                <FieldLabel htmlFor="allowed_hosts">第三方域名</FieldLabel>
                <Input
                  id="allowed_hosts"
                  value={form.allowed_hosts}
                  placeholder="github.com,api.github.com"
                  onChange={(event) =>
                    setForm({ ...form, allowed_hosts: event.target.value })
                  }
                />
                <FieldDescription>
                  逗号分隔。客户端用它识别"这是预期的第三方跳转"（如
                  github.com），
                  仅作诊断记录——导航本身不再按域名拦截，否则验证码、企业 SSO
                  这类任意域名的中间页会把登录卡死。票据交接仍由 JS 桥同源 +
                  state 校验保护。
                </FieldDescription>
              </Field>
            </div>
          </details>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) =>
                setForm({ ...form, enabled: event.target.checked })
              }
            />
            启用（关闭后登录页不再显示该入口）
          </label>
        </div>
      </Dialog>

      <Dialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={`删除 ${deleteTarget?.display_name ?? ""}`}
        description={
          deleteTarget && deleteTarget.linked_accounts > 0
            ? `有 ${deleteTarget.linked_accounts} 个账号绑定了这个平台，删除后他们将无法再用它登录（账号本身还在）。`
            : "删除后登录页会立刻移除该入口。"
        }
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => remove((deleteTarget?.linked_accounts ?? 0) > 0)}
              disabled={deleting}
            >
              {deleting ? (
                <>
                  <Loader2 className="animate-spin" />
                  删除中…
                </>
              ) : (
                "确认删除"
              )}
            </Button>
          </div>
        }
      >
        <p className="text-sm text-muted-foreground">
          想临时关闭入口而不是删配置，可以把「启用」取消勾选。
        </p>
      </Dialog>
    </PageWrapper>
  );
}
