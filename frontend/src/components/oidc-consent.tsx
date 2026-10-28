import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, ShieldCheck } from "lucide-react";

import { AuthLayout } from "@/pages/auth-layout";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, api, type OidcRequestMeta } from "@/lib/api";
import { readQuery } from "@/lib/bridge";
import { useSession } from "@/lib/session";


const SCOPE_TEXT: Record<string, string> = {
  openid: "确认你的身份 ID",
  profile: "读取你的用户名与昵称",
  email: "读取你的邮箱地址与验证状态",
};

export function OidcConsent() {
  const navigate = useNavigate();
  const { user, loading } = useSession();

  const [meta, setMeta] = useState<OidcRequestMeta | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      const next = `${window.location.pathname}${window.location.search}`;
      navigate(`/login?next=${encodeURIComponent(next)}`, { replace: true });
    }
  }, [loading, user, navigate]);

  useEffect(() => {
    let cancelled = false;
    // 放进依赖会反复触发请求
    const query = new URLSearchParams(window.location.search);
    const params: Record<string, string> = {};
    for (const key of [
      "client_id",
      "redirect_uri",
      "response_type",
      "scope",
      "state",
      "nonce",
      "code_challenge",
      "code_challenge_method",
    ]) {
      const value = query.get(key);
      if (value) params[key] = value;
    }
    (async () => {
      try {
        const result = await api.oidcRequest(params);
        if (!cancelled) setMeta(result);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err.message
              : "授权请求无效，请回到应用重试",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function decide(decision: "allow" | "deny") {
    if (!meta || pending) return;
    setPending(true);
    setError("");
    try {
      const result = await api.oidcApprove({
        client_id: meta.client_id,
        redirect_uri: meta.redirect_uri,
        response_type: readQuery("response_type") ?? "code",
        scope: meta.scope,
        state: meta.state,
        nonce: readQuery("nonce"),
        code_challenge: readQuery("code_challenge"),
        code_challenge_method: readQuery("code_challenge_method"),
        decision,
      });
      // 回调地址由服务端校验过
      window.location.href = result.redirect;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
      setPending(false);
    }
  }

  const clientName = meta?.client_name ?? "该应用";

  return (
    <AuthLayout
      eyebrow="第三方授权"
      title={meta ? `${clientName} 请求访问你的账号` : "正在校验授权请求"}
      description={
        meta
          ? `授权后将返回 ${clientName}，第三方平台无法获得你的其他信息，也不能代表你进行任何操作`
          : undefined
      }
      footer="由 TouchFish Auth 提供账号服务"
    >
      {error ? (
        <Alert variant="destructive" className="mb-4">
          {error}
        </Alert>
      ) : null}

      {!meta && !error ? (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          正在校验客户端与回调地址…
        </div>
      ) : null}

      {meta ? (
        <div className="space-y-4">
          <div className="rounded-lg border bg-muted/40 px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="size-4" />
              将允许它：
            </div>
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {meta.scopes.map((scope) => (
                <li key={scope}>· {SCOPE_TEXT[scope] ?? scope}</li>
              ))}
            </ul>
          </div>

          <div className="text-xs text-muted-foreground">
            授权完成后会跳转到
            <span className="ml-1 break-all font-mono">
              {meta.redirect_uri}
            </span>
          </div>

          <div className="flex gap-2">
            <Button
              variant="ghost"
              className="flex-1"
              disabled={pending}
              onClick={() => decide("deny")}
            >
              拒绝
            </Button>
            <Button
              variant="primary"
              className="flex-1"
              disabled={pending}
              onClick={() => decide("allow")}
            >
              {pending ? (
                <>
                  <Loader2 className="animate-spin" />
                  正在返回…
                </>
              ) : (
                "允许授权"
              )}
            </Button>
          </div>
        </div>
      ) : null}
    </AuthLayout>
  );
}
