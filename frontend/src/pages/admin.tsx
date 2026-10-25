import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Check,
  Copy,
  KeyRound,
  Loader2,
  RotateCw,
  Search,
  ShieldCheck,
  UserPlus,
} from "lucide-react";

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
import { ApiError, api } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Overview = Awaited<ReturnType<typeof api.adminOverview>>;
type AdminUser = Overview["users"][number];

const USER_FILTERS = [
  { key: "all", label: "全部" },
  { key: "admin", label: "管理员" },
  { key: "suspended", label: "已停用" },
] as const;

type UserFilter = (typeof USER_FILTERS)[number]["key"];

export function AdminPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  // 用户列表：搜索 + 状态筛选
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<UserFilter>("all");

  // 重置密码弹窗
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetResult, setResetResult] = useState<{
    temporary?: string;
    revoked: number;
  } | null>(null);
  const [resetError, setResetError] = useState("");
  const [copied, setCopied] = useState(false);

  // 创建用户弹窗
  const [createOpen, setCreateOpen] = useState(false);
  const [createUsername, setCreateUsername] = useState("");
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createRole, setCreateRole] = useState<"user" | "admin">("user");
  const [createError, setCreateError] = useState("");
  const [createResult, setCreateResult] = useState<{
    username: string;
    temporary?: string;
  } | null>(null);

  const load = useCallback(async () => {
    const result = await api.adminOverview();
    setData(result);
  }, []);

  useEffect(() => {
    load().catch(() => setData(null));
  }, [load]);

  const filteredUsers = useMemo(() => {
    const users = data?.users ?? [];
    const needle = query.trim().toLowerCase();
    return users.filter((user) => {
      if (filter === "admin" && user.role !== "admin") return false;
      if (filter === "suspended" && user.status !== "suspended") return false;
      if (!needle) return true;
      return (
        user.username.toLowerCase().includes(needle) ||
        (user.email ?? "").toLowerCase().includes(needle)
      );
    });
  }, [data, query, filter]);

  async function act(key: string, fn: () => Promise<unknown>, message: string) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await fn();
      await load();
      setNotice(message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
    } finally {
      setBusy("");
    }
  }

  function openReset(user: AdminUser) {
    setResetTarget(user);
    setResetPassword("");
    setResetResult(null);
    setResetError("");
    setCopied(false);
  }

  function closeReset() {
    setResetTarget(null);
    setResetPassword("");
    setResetResult(null);
    setResetError("");
    setCopied(false);
  }

  async function doReset() {
    if (!resetTarget) return;
    setBusy(`reset-${resetTarget.id}`);
    setResetError("");
    try {
      const result = await api.adminResetPassword(
        resetTarget.id,
        resetPassword.trim() || undefined,
      );
      setResetResult({
        temporary: result.temporary_password,
        revoked: result.revoked,
      });
      await load();
    } catch (err) {
      // 错误显示在弹窗内：页面顶部提示会被遮罩挡住
      setResetError(
        err instanceof ApiError ? err.message : "重置失败，请稍后重试",
      );
    } finally {
      setBusy("");
    }
  }

  function openCreate() {
    setCreateOpen(true);
    setCreateUsername("");
    setCreateEmail("");
    setCreatePassword("");
    setCreateRole("user");
    setCreateError("");
    setCreateResult(null);
    setCopied(false);
  }

  function closeCreate() {
    setCreateOpen(false);
    setCreateError("");
    setCreateResult(null);
  }

  async function doCreate() {
    setBusy("create-user");
    setCreateError("");
    try {
      const result = await api.adminCreateUser({
        username: createUsername.trim(),
        password: createPassword.trim() || undefined,
        email: createEmail.trim() || undefined,
        role: createRole,
      });
      setCreateResult({
        username: result.user.username,
        temporary: result.temporary_password,
      });
      await load();
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.message : "创建失败，请稍后重试",
      );
    } finally {
      setBusy("");
    }
  }

  async function copyText(text?: string) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 剪贴板不可用时用户仍可手动选中复制 */
    }
  }

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader
        title="管理"
        description="用户权限、实例与签名密钥。管理员由运维命令行授予。"
        actions={
          <Button
            variant="outline"
            disabled={busy === "rotate"}
            onClick={() =>
              act(
                "rotate",
                api.adminRotateKeys,
                "已轮换签名密钥，旧公钥保留 7 天",
              )
            }
          >
            {busy === "rotate" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <RotateCw />
            )}
            轮换密钥
          </Button>
        }
      />

      {error ? <Alert variant="destructive">{error}</Alert> : null}
      {notice ? <Alert variant="success">{notice}</Alert> : null}

      {!data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
          className="flex flex-col gap-6"
        >
          <motion.div
            variants={listItemVariants}
            className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5"
          >
            <Stat label="用户" value={data.stats.users} />
            <Stat label="管理员" value={data.stats.admins} />
            <Stat label="活跃会话" value={data.stats.active_sessions} />
            <Stat label="已绑定连接" value={data.stats.connections} />
            <Stat label="已绑定用户" value={data.stats.bound_users} />
          </motion.div>

          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>用户</CardTitle>
                <CardDescription>
                  停用会立刻吊销该用户的全部会话；管理员可在此授予或收回权限
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <div className="flex flex-col gap-3 border-b border-border px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="relative w-full sm:max-w-xs">
                    <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="搜索用户名或邮箱"
                      className="pl-9"
                      aria-label="搜索用户"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1 rounded-lg border border-border p-1">
                      {USER_FILTERS.map((item) => (
                        <button
                          key={item.key}
                          type="button"
                          onClick={() => setFilter(item.key)}
                          className={cn(
                            "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                            filter === item.key
                              ? "bg-primary text-primary-foreground"
                              : "text-muted-foreground hover:bg-muted hover:text-foreground",
                          )}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                    <Button variant="primary" size="sm" onClick={openCreate}>
                      <UserPlus className="size-3.5" />
                      创建用户
                    </Button>
                  </div>
                </div>
                <div className="divide-y divide-border">
                  {filteredUsers.map((user) => {
                    const isSelf = user.id === data.me.id;
                    return (
                      <div
                        key={user.id}
                        className="flex flex-wrap items-center justify-between gap-3 px-6 py-3"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 text-sm font-medium">
                            {user.username}
                            {user.role === "admin" ? (
                              <StatusBadge tone="info">
                                <ShieldCheck className="size-3" />
                                管理员
                              </StatusBadge>
                            ) : null}
                            {user.status === "suspended" ? (
                              <StatusBadge tone="danger">已停用</StatusBadge>
                            ) : null}
                            {isSelf ? (
                              <StatusBadge tone="neutral">我</StatusBadge>
                            ) : null}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            创建于 {formatTime(user.created_at)}
                            {user.email ? ` · ${user.email}` : ""}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isSelf || busy === `role-${user.id}`}
                            onClick={() =>
                              act(
                                `role-${user.id}`,
                                () =>
                                  api.adminSetRole(
                                    user.id,
                                    user.role === "admin" ? "user" : "admin",
                                  ),
                                user.role === "admin"
                                  ? "已收回管理员权限"
                                  : "已授予管理员权限",
                              )
                            }
                          >
                            {user.role === "admin" ? "收回权限" : "设为管理员"}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isSelf || busy === `status-${user.id}`}
                            onClick={() =>
                              act(
                                `status-${user.id}`,
                                () =>
                                  api.adminSetStatus(
                                    user.id,
                                    user.status === "active"
                                      ? "suspended"
                                      : "active",
                                  ),
                                user.status === "active"
                                  ? "已停用该用户"
                                  : "已恢复该用户",
                              )
                            }
                          >
                            {user.status === "active" ? "停用" : "恢复"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy === `logout-${user.id}`}
                            onClick={() =>
                              act(
                                `logout-${user.id}`,
                                () => api.adminLogoutAll(user.id),
                                "已使该用户全部会话失效",
                              )
                            }
                          >
                            强制下线
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={isSelf}
                            onClick={() => openReset(user)}
                          >
                            <KeyRound className="size-3.5" />
                            重置密码
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
                {filteredUsers.length === 0 ? (
                  <p className="px-6 py-10 text-center text-sm text-muted-foreground">
                    没有匹配的用户
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={listItemVariants}>
            <InstanceEditor
              existing={data.instances}
              busy={busy}
              onSave={(body) =>
                act(
                  `inst-${body.id}`,
                  () => api.adminUpsertInstance(body),
                  "实例已保存",
                )
              }
              onDelete={(id) =>
                act(
                  `del-${id}`,
                  () => api.adminDeleteInstance(id),
                  `已删除实例 ${id}`,
                )
              }
            />
          </motion.div>

          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>签名密钥</CardTitle>
                <CardDescription>
                  轮换后新 token 用新钥签发，旧公钥保留 7 天供对端缓存过期
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between gap-4">
                  <span className="text-xs font-medium text-muted-foreground">
                    当前 kid
                  </span>
                  <span className="font-mono">{data.keys.active_kid}</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-xs font-medium text-muted-foreground">
                    公钥数量
                  </span>
                  <span>{data.keys.all_kids.length}</span>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      )}

      <Dialog
        open={resetTarget !== null}
        onClose={closeReset}
        title="重置密码"
        description={
          resetTarget ? `为 ${resetTarget.username} 设置新密码` : undefined
        }
        footer={
          resetResult ? (
            <Button variant="primary" onClick={closeReset}>
              完成
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={closeReset}>
                取消
              </Button>
              <Button
                variant="primary"
                disabled={busy === `reset-${resetTarget?.id}`}
                onClick={doReset}
              >
                {busy === `reset-${resetTarget?.id}` ? (
                  <>
                    <Loader2 className="animate-spin" />
                    正在重置…
                  </>
                ) : (
                  "确认重置"
                )}
              </Button>
            </>
          )
        }
      >
        {resetError ? <Alert variant="destructive">{resetError}</Alert> : null}
        {resetResult ? (
          <div className="space-y-3 text-sm">
            <Alert variant="success">
              已重置密码，并吊销该用户 {resetResult.revoked} 个会话。
            </Alert>
            {resetResult.temporary ? (
              <div className="space-y-2">
                <p className="text-muted-foreground">
                  临时密码（仅显示这一次，请立即转告用户）：
                </p>
                <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2">
                  <code className="flex-1 break-all font-mono text-sm">
                    {resetResult.temporary}
                  </code>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyText(resetResult.temporary)}
                  >
                    {copied ? (
                      <Check className="size-3.5" />
                    ) : (
                      <Copy className="size-3.5" />
                    )}
                    {copied ? "已复制" : "复制"}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  建议用户登录后立即在账户页修改。
                </p>
              </div>
            ) : null}
          </div>
        ) : (
          <Field>
            <FieldLabel htmlFor="reset-password">新密码</FieldLabel>
            <Input
              id="reset-password"
              type="text"
              value={resetPassword}
              onChange={(event) => setResetPassword(event.target.value)}
              placeholder="留空则生成 16 位临时密码"
              autoComplete="new-password"
            />
            <FieldDescription>
              留空由系统生成随机临时密码；填写则至少 8
              位。两种方式都会吊销该用户全部会话。
            </FieldDescription>
          </Field>
        )}
      </Dialog>

      <Dialog
        open={createOpen}
        onClose={closeCreate}
        title="创建用户"
        description="管理员直接建号，账号立即生效，无需邮箱验证"
        footer={
          createResult ? (
            <Button variant="primary" onClick={closeCreate}>
              完成
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={closeCreate}>
                取消
              </Button>
              <Button
                variant="primary"
                disabled={
                  busy === "create-user" || createUsername.trim().length < 2
                }
                onClick={doCreate}
              >
                {busy === "create-user" ? (
                  <>
                    <Loader2 className="animate-spin" />
                    正在创建…
                  </>
                ) : (
                  "创建"
                )}
              </Button>
            </>
          )
        }
      >
        {createError ? (
          <Alert variant="destructive">{createError}</Alert>
        ) : null}
        {createResult ? (
          <div className="space-y-3 text-sm">
            <Alert variant="success">
              已创建用户 {createResult.username}。
            </Alert>
            {createResult.temporary ? (
              <div className="space-y-2">
                <p className="text-muted-foreground">
                  临时密码（仅显示这一次，请立即转告用户）：
                </p>
                <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2">
                  <code className="flex-1 break-all font-mono text-sm">
                    {createResult.temporary}
                  </code>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyText(createResult.temporary)}
                  >
                    {copied ? (
                      <Check className="size-3.5" />
                    ) : (
                      <Copy className="size-3.5" />
                    )}
                    {copied ? "已复制" : "复制"}
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-muted-foreground">
                密码由你指定，请直接告知用户。
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <Field>
              <FieldLabel htmlFor="new-username">用户名</FieldLabel>
              <Input
                id="new-username"
                value={createUsername}
                onChange={(event) => setCreateUsername(event.target.value)}
                placeholder="2–32 位，字母 / 数字 / 下划线 / 连字符 / 中文"
                autoComplete="off"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="new-email">邮箱（可选）</FieldLabel>
              <Input
                id="new-email"
                type="email"
                value={createEmail}
                onChange={(event) => setCreateEmail(event.target.value)}
                placeholder="留空则不绑定邮箱"
                autoComplete="off"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="new-password">密码（可选）</FieldLabel>
              <Input
                id="new-password"
                type="text"
                value={createPassword}
                onChange={(event) => setCreatePassword(event.target.value)}
                placeholder="留空则生成 16 位临时密码"
                autoComplete="new-password"
              />
              <FieldDescription>
                填写则至少 8 位；留空由系统生成，仅显示一次。
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel>角色</FieldLabel>
              <div className="flex gap-1 rounded-lg border border-border p-1">
                {(["user", "admin"] as const).map((role) => (
                  <button
                    key={role}
                    type="button"
                    onClick={() => setCreateRole(role)}
                    className={cn(
                      "flex-1 rounded-md px-3 py-1 text-xs font-medium transition-colors",
                      createRole === role
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {role === "admin" ? "管理员" : "普通用户"}
                  </button>
                ))}
              </div>
              <FieldDescription>
                管理员可访问「管理」页；建号后也能在列表中调整。
              </FieldDescription>
            </Field>
          </div>
        )}
      </Dialog>
    </PageWrapper>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function InstanceEditor({
  existing,
  busy,
  onSave,
  onDelete,
}: {
  existing: Overview["instances"];
  busy: string;
  onSave: (body: {
    id: string;
    base_url: string;
    display_name: string;
    audience?: string;
  }) => void;
  onDelete: (instanceId: string) => void;
}) {
  const first = existing[0];
  const [id, setId] = useState("main");
  const [baseUrl, setBaseUrl] = useState(
    first?.base_url ?? "http://127.0.0.1:7001",
  );
  const [name, setName] = useState(first?.display_name ?? "TouchFish");
  const [audience, setAudience] = useState(first?.audience ?? "");

  return (
    <Card>
      <CardHeader>
        <CardTitle>TouchFish 实例</CardTitle>
        <CardDescription>
          issuer 始终等于本平台地址；改动后需要同步更新服务器侧的
          jwt_external_issuers
        </CardDescription>
      </CardHeader>
      <CardContent>
        {existing.length > 0 ? (
          <div className="mb-4 space-y-2">
            {existing.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted px-4 py-2.5"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium">
                    {item.display_name}
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {item.id}
                    </span>
                  </div>
                  <div className="truncate font-mono text-xs text-muted-foreground">
                    {item.base_url}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy === `del-${item.id}`}
                  onClick={() => onDelete(item.id)}
                >
                  {busy === `del-${item.id}` ? (
                    <Loader2 className="animate-spin" />
                  ) : null}
                  删除
                </Button>
              </div>
            ))}
          </div>
        ) : null}

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSave({
              id,
              base_url: baseUrl,
              display_name: name,
              audience: audience || undefined,
            });
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="inst-id">实例 ID</FieldLabel>
              <Input
                id="inst-id"
                value={id}
                onChange={(event) => setId(event.target.value)}
                pattern="[a-z0-9_-]+"
                required
              />
              <FieldDescription>
                小写字母、数字、下划线或连字符
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="inst-name">显示名</FieldLabel>
              <Input
                id="inst-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </Field>
          </div>
          <Field>
            <FieldLabel htmlFor="inst-url">服务器地址</FieldLabel>
            <Input
              id="inst-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              required
            />
            <FieldDescription>
              例如 https://touchfish.xin，不带结尾斜杠
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="inst-aud">audience（可选）</FieldLabel>
            <Input
              id="inst-aud"
              value={audience}
              onChange={(event) => setAudience(event.target.value)}
            />
            <FieldDescription>
              须与服务器 jwt_external_issuers[].audience 一致
            </FieldDescription>
          </Field>
          <Button type="submit" disabled={busy === `inst-${id}`}>
            {busy === `inst-${id}` ? (
              <Loader2 className="animate-spin" />
            ) : null}
            保存实例
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
