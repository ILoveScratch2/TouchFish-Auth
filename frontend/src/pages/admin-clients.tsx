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
  { id: "openid", label: "openid", hint: "身份标识（必选，id_token 的基础）" },
  { id: "profile", label: "profile", hint: "用户名与昵称" },
  { id: "email", label: "email", hint: "邮箱地址与验证状态" },
];

const ORIGIN = typeof window === "undefined" ? "" : window.location.origin;

const ENDPOINTS = [
  { label: "发现文档", value: `${ORIGIN}/.well-known/openid-configuration` },
  { label: "授权端点", value: `${ORIGIN}/authorize` },
  { label: "令牌端点", value: `${ORIGIN}/token` },
  { label: "用户信息", value: `${ORIGIN}/api/userinfo` },
  { label: "公钥", value: `${ORIGIN}/.well-known/jwks.json` },
];

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

export function OidcClientsPage() {
  const [clients, setClients] = useState<OidcClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");

  const [editing, setEditing] = useState<OidcClient | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<OidcClient | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [secretInfo, setSecretInfo] = useState<{
    clientId: string;
    secret: string;
  } | null>(null);
  const [copied, setCopied] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await api.adminOidcClients();
      setClients(result.clients);
    } catch (err) {
      setPageError(
        err instanceof ApiError ? err.message : "加载客户端失败，请稍后重试",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function copy(value: string, key: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(""), 1500);
    } catch {
      /* 剪贴板不可用时静默失败，用户仍可手动选中 */
    }
  }

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setFormError("");
    setOpen(true);
  }

  function openEdit(item: OidcClient) {
    setEditing(item);
    setForm({
      name: item.name,
      redirects: item.redirect_uris.join("\n"),
      scopes: item.scopes,
      isPublic: item.is_public,
    });
    setFormError("");
    setOpen(true);
  }

  function parseRedirects(raw: string): string[] {
    return raw
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }

  async function save() {
    if (saving) return;
    const redirectUris = parseRedirects(form.redirects);
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
        // 公开/机密在创建后不可改：改类型等于更换安全模型，应重建客户端
        await api.adminUpdateOidcClient(editing.client_id, {
          name: form.name.trim(),
          redirect_uris: redirectUris,
          scopes: form.scopes,
        });
      } else {
        const result = await api.adminCreateOidcClient({
          name: form.name.trim(),
          redirect_uris: redirectUris,
          scopes: form.scopes,
          public: form.isPublic,
        });
        if (result.client_secret) {
          setSecretInfo({
            clientId: result.client.client_id,
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

  async function toggleEnabled(item: OidcClient) {
    try {
      await api.adminUpdateOidcClient(item.client_id, {
        enabled: !item.enabled,
      });
      await load();
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "操作失败");
    }
  }

  async function rotate(item: OidcClient) {
    try {
      const result = await api.adminRotateOidcSecret(item.client_id);
      setSecretInfo({ clientId: item.client_id, secret: result.client_secret });
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "轮换密钥失败");
    }
  }

  async function remove() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try {
      await api.adminDeleteOidcClient(deleteTarget.client_id);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "删除失败");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <PageWrapper className="space-y-6">
      <PageHeader
        title="应用接入"
        description="TouchFish Auth 作为 OIDC 授权服务器授权"
      />

      {pageError ? <Alert variant="destructive">{pageError}</Alert> : null}

      <Card>
        <CardHeader>
          <CardTitle>接入信息</CardTitle>
          <CardDescription>
            应用侧按标准 OIDC 配置
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {ENDPOINTS.map((item) => (
            <div
              key={item.label}
              className="flex items-center justify-between gap-3 border-b border-border pb-2 last:border-0 last:pb-0"
            >
              <span className="text-xs font-medium text-muted-foreground">
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
                <span className="truncate">{item.value}</span>
              </button>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">已注册应用</h2>
        <Button variant="primary" onClick={openCreate}>
          <Plus />
          新建应用
        </Button>
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : clients.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            还没有注册任何应用。
          </CardContent>
        </Card>
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
          className="space-y-3"
        >
          {clients.map((item) => (
            <motion.div key={item.client_id} variants={listItemVariants}>
              <Card>
                <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{item.name}</span>
                      {item.is_public ? (
                        <StatusBadge tone="info">公开客户端</StatusBadge>
                      ) : (
                        <StatusBadge tone="neutral">机密客户端</StatusBadge>
                      )}
                      {item.enabled ? (
                        <StatusBadge tone="success">已启用</StatusBadge>
                      ) : (
                        <StatusBadge tone="warning">已停用</StatusBadge>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => copy(item.client_id, item.client_id)}
                      className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                    >
                      {copied === item.client_id ? (
                        <Check className="size-3" />
                      ) : (
                        <Copy className="size-3" />
                      )}
                      {item.client_id}
                    </button>
                    <div className="text-xs text-muted-foreground">
                      回调：{item.redirect_uris.join("、")}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      scope：{item.scopes.join(" ")} · 创建于{" "}
                      {formatTime(item.created_at)}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-wrap gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openEdit(item)}
                    >
                      编辑
                    </Button>
                    {item.is_public ? null : (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => rotate(item)}
                      >
                        <RotateCw />
                        重置密钥
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleEnabled(item)}
                    >
                      {item.enabled ? "停用" : "启用"}
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
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? `编辑 ${editing.name}` : "新建应用"}
        description={
          editing
            ? "改动回调地址会立即生效"
            : "服务端应用请选机密客户端"
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
            <FieldLabel htmlFor="client-name">应用名称</FieldLabel>
            <Input
              id="client-name"
              value={form.name}
              placeholder="公司内部工具"
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="client-redirects">
              回调地址（每行一个）
            </FieldLabel>
            <textarea
              id="client-redirects"
              value={form.redirects}
              rows={3}
              placeholder="https://app.example.com/auth/callback"
              onChange={(event) =>
                setForm({ ...form, redirects: event.target.value })
              }
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
            />
            <FieldDescription>
              逐字符精确匹配，不支持通配符
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
                  无密钥的客户端（如客户端应用）
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
        description="关闭后无法再次查看。请立刻复制并交给应用方，遗失只能重置。"
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
            <div className="mt-1 font-mono text-sm break-all">
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
