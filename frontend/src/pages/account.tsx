import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Link2, Loader2, Unlink } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
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
import { ApiError, api, type OAuthAccountProvider } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";


const OAUTH_ERROR_TEXT: Record<string, string> = {
  access_denied: "你在第三方页面取消了授权",
  state_invalid: "授权已过期或被篡改，请重试",
  provider_unavailable: "该登录方式未启用或配置不完整，请联系管理员",
  bind_session_mismatch: "登录状态已变化，请重新登录后再绑定",
  provider_already_bound: "该第三方账号已绑定到另一个平台账号",
  provider_in_use: "本账号已绑定另一个同类第三方账号，请先解绑",
  bind_requires_login: "请先登录再绑定",
};

export function AccountPage() {
  const { user, refresh } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [params] = useSearchParams();
  const [providers, setProviders] = useState<OAuthAccountProvider[]>([]);
  const [hasPassword, setHasPassword] = useState(true);
  const [loadingProviders, setLoadingProviders] = useState(true);
  const [unlinking, setUnlinking] = useState("");
  const [unlinkTarget, setUnlinkTarget] = useState<OAuthAccountProvider | null>(
    null,
  );
  const [oauthNotice, setOauthNotice] = useState("");
  const [oauthError, setOauthError] = useState("");

  const loadProviders = useCallback(async () => {
    try {
      const result = await api.oauthAccounts();
      setProviders(result.providers);
      setHasPassword(result.has_password);
    } catch {
      setProviders([]);
    } finally {
      setLoadingProviders(false);
    }
  }, []);

  useEffect(() => {
    loadProviders();
  }, [loadProviders]);

  // ?oauth=linked 或 ?oauth_error=xxx
  useEffect(() => {
    const done = params.get("oauth");
    const failure = params.get("oauth_error");
    if (done === "linked") setOauthNotice("已绑定");
    if (failure) setOauthError(OAUTH_ERROR_TEXT[failure] ?? "绑定失败，请重试");
  }, [params]);

  if (!user) return null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    setMessage("");
    try {
      await api.changePassword({
        current_password: user!.has_password ? current : undefined,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      setMessage("密码已更新，其他设备已退出登录");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败，请稍后重试");
    } finally {
      setPending(false);
    }
  }

  function startBind(providerId: string) {
    window.location.href = `/api/auth/oauth/${providerId}/start?bind=1`;
  }

  async function doUnlink() {
    if (!unlinkTarget) return;
    setUnlinking(unlinkTarget.id);
    setOauthError("");
    setOauthNotice("");
    try {
      await api.oauthUnlink(unlinkTarget.id);
      setOauthNotice(`已解绑 ${unlinkTarget.name}`);
      await loadProviders();
    } catch (err) {
      setOauthError(
        err instanceof ApiError ? err.message : "解绑失败，请稍后重试",
      );
    } finally {
      setUnlinkTarget(null);
      setUnlinking("");
    }
  }

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader title="账户" description="管理你的 TouchFish Auth 身份" />

      <motion.div
        variants={listContainerVariants}
        initial="initial"
        animate="animate"
        className="grid gap-6 lg:grid-cols-2"
      >
        <motion.div variants={listItemVariants}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>基本信息</CardTitle>
              <CardDescription>这些信息用于向 TouchFish 标识你</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Row label="用户名" value={user.username} mono />
              <Row label="显示名" value={user.display_name ?? user.username} />
              <Row label="邮箱" value={user.email ?? "未设置"} />
              <Row label="创建时间" value={formatTime(user.created_at)} />
              <Row
                label="平台密码"
                value={user.has_password ? "已设置" : "未设置"}
              />
              <Row
                label="权限"
                value={user.role === "admin" ? "管理员" : "普通用户"}
              />
            </CardContent>
          </Card>
        </motion.div>

        <motion.div variants={listItemVariants}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>
                {user.has_password ? "修改密码" : "设置密码"}
              </CardTitle>
              <CardDescription>
                {user.has_password
                  ? "修改后其他设备会被退出登录"
                  : "当前账号只能通过 TouchFish 登录，设置密码后可直接登录"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={submit}>
                {error ? <Alert variant="destructive">{error}</Alert> : null}
                {message ? <Alert variant="success">{message}</Alert> : null}

                {user.has_password ? (
                  <Field>
                    <FieldLabel htmlFor="current">当前密码</FieldLabel>
                    <Input
                      id="current"
                      type="password"
                      autoComplete="current-password"
                      value={current}
                      onChange={(event) => setCurrent(event.target.value)}
                      required
                    />
                  </Field>
                ) : null}

                <Field>
                  <FieldLabel htmlFor="next">新密码</FieldLabel>
                  <Input
                    id="next"
                    type="password"
                    autoComplete="new-password"
                    value={next}
                    onChange={(event) => setNext(event.target.value)}
                    required
                  />
                  <FieldDescription>至少 8 位</FieldDescription>
                </Field>

                <Button type="submit" variant="primary" disabled={pending}>
                  {pending ? (
                    <>
                      <Loader2 className="animate-spin" />
                      正在保存…
                    </>
                  ) : (
                    "保存"
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          variants={listItemVariants}
          className={cn(
            "lg:col-span-2",
            // 未启用任何第三方平台时整块不显示
            !loadingProviders && providers.length === 0 && "hidden",
          )}
        >
          <Card>
            <CardHeader>
              <CardTitle>已关联的登录方式</CardTitle>
              <CardDescription>
                绑定第三方账号后可直接用它登录；解绑不影响已登录的会话
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {oauthNotice ? (
                <Alert variant="success">{oauthNotice}</Alert>
              ) : null}
              {oauthError ? (
                <Alert variant="destructive">{oauthError}</Alert>
              ) : null}

              {loadingProviders ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  正在读取…
                </div>
              ) : providers.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  管理员尚未启用任何第三方登录方式
                </p>
              ) : (
                <div className="divide-y divide-border">
                  {providers.map((provider) => (
                    <div
                      key={provider.id}
                      className="flex items-center justify-between gap-4 py-3"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-sm font-medium">
                          {provider.name}
                          {provider.orphan ? (
                            <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                              已停用
                            </span>
                          ) : null}
                        </div>
                        <p className="truncate text-xs text-muted-foreground">
                          {provider.linked
                            ? `已绑定 ${provider.login ?? provider.id}`
                            : "未绑定"}
                        </p>
                      </div>
                      {provider.linked ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={unlinking === provider.id}
                          onClick={() => setUnlinkTarget(provider)}
                        >
                          <Unlink />
                          解绑
                        </Button>
                      ) : provider.orphan ? null : (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => startBind(provider.id)}
                        >
                          <Link2 />
                          绑定
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {!hasPassword &&
              providers.filter((item) => item.linked).length <= 1 ? (
                <FieldDescription>
                  当前账号没有平台密码：唯一的登录方式不能解绑，请先在上方设置密码
                </FieldDescription>
              ) : null}
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>

      <Dialog
        open={unlinkTarget !== null}
        onClose={() => setUnlinkTarget(null)}
        title={`解绑 ${unlinkTarget?.name ?? ""}`}
        description="解绑后将无法再用该账号登录本平台，已登录的会话不受影响。"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUnlinkTarget(null)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={doUnlink}
              disabled={Boolean(unlinking)}
            >
              {unlinking ? "解绑中…" : "确认解绑"}
            </Button>
          </>
        }
      />
    </PageWrapper>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border pb-2 last:border-0 last:pb-0">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono text-sm" : "text-sm"}>{value}</span>
    </div>
  );
}
