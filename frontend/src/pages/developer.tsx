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
import { ApiError, api, type OidcClient } from "@/lib/api";
import { formatTime } from "@/lib/format";

const ALL_SCOPES = [
  { id: "openid", label: "openid", hint: "身份标识（必选）" },
  { id: "profile", label: "profile", hint: "用户名与昵称" },
  { id: "email", label: "email", hint: "邮箱地址与验证状态" },
];

type Policy = {
  self_service: boolean;
  max_per_user: number;
  used: number;
};

type FormState = {
  name: string;
  redirects: string;
  scopes: string[];
  isPublic: boolean;
};

const EMPTY: FormState = {
  name: "",
  redirects: "",
  scopes: ["openid", "profile", "email"],
  isPublic: true,
};

/**
 * 开发者页：本平台作为 OIDC 授权服务器时，让用户创建自己的应用并拿到接入信息。
 *
 * 自助创建受站点策略约束（`oauth_apps_self_service` / `oauth_apps_max_per_user`）；
 * 关闭时只展示已有应用与接入信息，创建入口置灰并提示联系管理员。
 */
export function DeveloperPage() {
  const [policy, setPolicy] = useState<Policy>({
    self_service: false,
    max_per_user: 0,
    used: 0,
  });
  const [apps, setApps] = useState<OidcClient[]>([]);
  const [summary, setSummary] = useState<{
    issuer: string;
    discovery_uri: string;
    jwks_uri: string;
    active_kid: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [copied, setCopied] = useState("");

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<OidcClient | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const [secretInfo, setSecretInfo] = useState<{
    clientId: string;
    secret: string;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<OidcClient | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [appsResult, summaryResult] = await Promise.all([
        api.developerApps(),
        api.developer(),
      ]);
      setPolicy({
        self_service: appsResult.self_service,
        max_per_user: appsResult.max_per_user,
        used: appsResult.used,
      });
      setApps(appsResult.apps);
      setSummary({
        issuer: summaryResult.issuer,
        discovery_uri: summaryResult.discovery_uri,
        jwks_uri: summaryResult.jwks_uri,
        active_kid: summaryResult.active_kid,
      });
    } catch (err) {
      setPageError(
        err instanceof ApiError ? err.message : "加载失败，请稍后重试",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function copy(value: string, key: string) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(""), 1500);
    } catch {
      /* 剪贴板不可用时静默失败 */
    }
  }

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setFormError("");
    setOpen(true);
  }

  function openEdit(app: OidcClient) {
    setEditing(app);
    setForm({
      name: app.name,
      redirects: app.redirect_uris.join("\n"),
      scopes: app.scopes,
      isPublic: app.is_public,
    });
    setFormError("");
    setOpen(true);
  }

  async function save() {
    if (saving) return;
    const redirectUris = form.redirects
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (!form.name.trim()) {
      setFormError("请填写应用名称");
      return;
    }
    if (redirectUris.length === 0) {
      setFormError("至少填写一个回调地址");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      if (editing) {
        await api.developerUpdateApp(editing.client_id, {
          name: form.name.trim(),
          redirect_uris: redirectUris,
          scopes: form.scopes,
        });
      } else {
        const result = await api.developerCreateApp({
          name: form.name.trim(),
          redirect_uris: redirectUris,
          scopes: form.scopes,
          public: form.isPublic,
        });
        if (result.client_secret) {
          setSecretInfo({
            clientId: result.app.client_id,
            secret: result.client_secret,
          });
        }
      }
      setOpen(false);
      await load();
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "保存失败，请稍后重试",
      );
    } finally {
      setSaving(false);
    }
  }

  async function rotate(app: OidcClient) {
    try {
      const result = await api.developerRotateSecret(app.client_id);
      setSecretInfo({ clientId: app.client_id, secret: result.client_secret });
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "重置密钥失败");
    }
  }

  async function toggleEnabled(app: OidcClient) {
    try {
      await api.developerUpdateApp(app.client_id, { enabled: !app.enabled });
      await load();
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "操作失败");
    }
  }

  async function remove() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try {
      await api.developerDeleteApp(deleteTarget.client_id);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "删除失败");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  const quotaFull = policy.self_service && policy.used >= policy.max_per_user;
  const issuer = summary?.issuer ?? "";

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader
        title="开发者"
        description="用 TouchFish Auth 登录你的应用：标准 OIDC 授权码流程，支持 PKCE"
        actions={
          policy.self_service ? (
            <StatusBadge tone="success">自助创建已开放</StatusBadge>
          ) : (
            <StatusBadge tone="warning">仅管理员可创建</StatusBadge>
          )
        }
      />

      {pageError ? <Alert variant="destructive">{pageError}</Alert> : null}

      <Card>
        <CardHeader>
          <CardTitle>接入信息</CardTitle>
          <CardDescription>
            应用侧按标准 OIDC 配置即可；回调地址必须与创建时填写的一致
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {[
            { label: "Issuer", value: issuer },
            { label: "发现文档", value: summary?.discovery_uri ?? "" },
            { label: "授权端点", value: issuer ? `${issuer}/authorize` : "" },
            { label: "令牌端点", value: issuer ? `${issuer}/token` : "" },
            {
              label: "用户信息",
              value: issuer ? `${issuer}/api/userinfo` : "",
            },
            { label: "公钥", value: summary?.jwks_uri ?? "" },
            { label: "当前密钥", value: summary?.active_kid ?? "" },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center justify-between gap-3 border-b border-border pb-2 last:border-0 last:pb-0"
            >
              <span className="shrink-0 text-xs font-medium text-muted-foreground">
                {item.label}
              </span>
              <button
                type="button"
                onClick={() => copy(item.value, item.label)}
                className="inline-flex min-w-0 items-center gap-1 font-mono text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              >
                {copied === item.label ? (
                  <Check className="size-3 shrink-0" />
                ) : (
                  <Copy className="size-3 shrink-0" />
                )}
                <span className="truncate">{item.value || "—"}</span>
              </button>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">我的应用</h2>
          {policy.self_service ? (
            <p className="mt-1 text-xs text-muted-foreground">
              已用 {policy.used} / {policy.max_per_user} 个
            </p>
          ) : null}
        </div>
        <Button
          variant="primary"
          onClick={openCreate}
          disabled={!policy.self_service || quotaFull}
        >
          <Plus />
          新建应用
        </Button>
      </div>

      {!policy.self_service && !loading ? (
        <Alert variant="info">
          本站未开放自助创建应用。需要接入的话，把应用名称、回调地址与所需 scope
          发给管理员即可；创建完成后应用会出现在下面的列表里。
        </Alert>
      ) : null}

      {quotaFull ? (
        <Alert variant="warning">
          已达本账号可创建的上限（{policy.max_per_user}{" "}
          个），请先删除不再使用的应用。
        </Alert>
      ) : null}

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : apps.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            还没有属于你的应用。
            {policy.self_service
              ? "点右上角「新建应用」即可开始。"
              : "管理员为你创建后会更现在这里。"}
          </CardContent>
        </Card>
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
          className="space-y-3"
        >
          {apps.map((app) => (
            <motion.div key={app.client_id} variants={listItemVariants}>
              <Card>
                <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{app.name}</span>
                      {app.is_public ? (
                        <StatusBadge tone="info">公开客户端</StatusBadge>
                      ) : (
                        <StatusBadge tone="neutral">机密客户端</StatusBadge>
                      )}
                      {app.enabled ? (
                        <StatusBadge tone="success">已启用</StatusBadge>
                      ) : (
                        <StatusBadge tone="warning">已停用</StatusBadge>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => copy(app.client_id, app.client_id)}
                      className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                    >
                      {copied === app.client_id ? (
                        <Check className="size-3" />
                      ) : (
                        <Copy className="size-3" />
                      )}
                      {app.client_id}
                    </button>
                    <div className="text-xs text-muted-foreground">
                      回调：{app.redirect_uris.join("、")}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      scope：{app.scopes.join(" ")} · 创建于{" "}
                      {formatTime(app.created_at)}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-wrap gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openEdit(app)}
                    >
                      编辑
                    </Button>
                    {app.is_public ? null : (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => rotate(app)}
                      >
                        <RotateCw />
                        重置密钥
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleEnabled(app)}
                    >
                      {app.enabled ? "停用" : "启用"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget(app)}
                    >
                      <Trash2 />
                      删除
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>换取令牌</CardTitle>
          <CardDescription>
            授权码 60 秒有效且只能用一次；公开客户端需带
            code_verifier，机密客户端用 secret
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-md border bg-muted/40 p-3 text-xs leading-relaxed">
            {`curl -s "${issuer}/token" \\
  -d grant_type=authorization_code \\
  -d client_id=$CLIENT_ID \\
  -d client_secret=$CLIENT_SECRET \\
  -d code=$CODE \\
  -d redirect_uri=$REDIRECT_URI`}
          </pre>
        </CardContent>
      </Card>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? `编辑 ${editing.name}` : "新建应用"}
        description={
          editing
            ? "改动回调地址会立即生效，注意不要漏掉旧地址"
            : "公开客户端（SPA / 桌面端）没有密钥，必须用 PKCE；服务端应用请选机密客户端"
        }
        className="max-w-xl"
        footer={
          <>
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
          </>
        }
      >
        <div className="space-y-4">
          {formError ? <Alert variant="destructive">{formError}</Alert> : null}

          <Field>
            <FieldLabel htmlFor="dev-app-name">应用名称</FieldLabel>
            <Input
              id="dev-app-name"
              value={form.name}
              placeholder="我的博客"
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="dev-app-redirects">
              回调地址（每行一个）
            </FieldLabel>
            <textarea
              id="dev-app-redirects"
              value={form.redirects}
              rows={3}
              placeholder="https://blog.example.com/auth/callback"
              onChange={(event) =>
                setForm({ ...form, redirects: event.target.value })
              }
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
            />
            <FieldDescription>
              逐字符精确匹配，不支持通配符；不要带 fragment
            </FieldDescription>
          </Field>

          <Field>
            <FieldLabel>允许申请的 scope</FieldLabel>
            <div className="space-y-2">
              {ALL_SCOPES.map((scope) => (
                <label
                  key={scope.id}
                  className="flex items-start gap-2 text-sm"
                >
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={form.scopes.includes(scope.id)}
                    disabled={scope.id === "openid"}
                    onChange={(event) => {
                      const next = event.target.checked
                        ? [...form.scopes, scope.id]
                        : form.scopes.filter((item) => item !== scope.id);
                      setForm({
                        ...form,
                        scopes: next.length ? next : ["openid"],
                      });
                    }}
                  />
                  <span>
                    <span className="font-mono">{scope.label}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {scope.hint}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </Field>

          {editing ? null : (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={form.isPublic}
                onChange={(event) =>
                  setForm({ ...form, isPublic: event.target.checked })
                }
              />
              <span>
                公开客户端（无 client_secret，强制 PKCE）
                <span className="ml-2 text-xs text-muted-foreground">
                  SPA、桌面端、移动端选它；有后端能保管密钥的服务端应用请取消勾选
                </span>
              </span>
            </label>
          )}
        </div>
      </Dialog>

      <Dialog
        open={secretInfo !== null}
        onClose={() => setSecretInfo(null)}
        title="密钥只显示这一次"
        description="关闭后无法再次查看。请立刻复制并配置到应用里，遗失只能重置。"
        footer={
          <Button variant="primary" onClick={() => setSecretInfo(null)}>
            我已保存
          </Button>
        }
      >
        <div className="space-y-3">
          <div>
            <div className="text-xs font-medium text-muted-foreground">
              client_id
            </div>
            <div className="mt-1 break-all font-mono text-sm">
              {secretInfo?.clientId}
            </div>
          </div>
          <div>
            <div className="text-xs font-medium text-muted-foreground">
              client_secret
            </div>
            <div className="mt-1 flex items-start gap-2">
              <code className="min-w-0 flex-1 rounded-md border bg-muted px-2 py-1 font-mono text-sm break-all">
                {secretInfo?.secret}
              </code>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => copy(secretInfo?.secret ?? "", "secret")}
              >
                {copied === "secret" ? <Check /> : <Copy />}
              </Button>
            </div>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={`删除 ${deleteTarget?.name ?? ""}`}
        description="该应用已签发的访问令牌与刷新令牌会立刻失效，且无法撤销。"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button variant="primary" onClick={remove} disabled={deleting}>
              {deleting ? "删除中…" : "确认删除"}
            </Button>
          </>
        }
      />
    </PageWrapper>
  );
}
