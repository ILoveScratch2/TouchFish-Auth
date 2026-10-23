import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Loader2 } from "lucide-react";

import { AuthForm, AuthItem, AuthLayout } from "@/pages/auth-layout";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError, api, type Connection, type Instance } from "@/lib/api";
import { deliverTicket, readQuery } from "@/lib/bridge";
import { useSession } from "@/lib/session";
import { IdentifierBlock } from "@/components/identifier-block";

type Phase = "checking" | "need-bind" | "ready" | "delivering" | "done";

export function AuthorizePage() {
  const navigate = useNavigate();
  const { user, loading } = useSession();

  const clientId = readQuery("client_id") ?? "touchfish";
  const state = readQuery("state");
  const target = readQuery("target");

  const [phase, setPhase] = useState<Phase>("checking");
  const [instance, setInstance] = useState<Instance | null>(null);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [ticket, setTicket] = useState("");
  const [bridged_done, setBridgeDone] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      const next = `${window.location.pathname}${window.location.search}`;
      navigate(`/login?next=${encodeURIComponent(next)}`, { replace: true });
    }
  }, [loading, user, navigate]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    (async () => {
      try {
        const [instancesResult, connectionsResult] = await Promise.all([
          api.instances(),
          api.connections(),
        ]);
        if (cancelled) return;
        const list = instancesResult.instances;
        const matched =
          list.find((item) => target && item.base_url.replace(/\/$/, "") === target.replace(/\/$/, "")) ??
          list[0] ??
          null;
        setInstance(matched);
        const conn = matched
          ? connectionsResult.connections.find((item) => item.instance_id === matched.id) ?? null
          : null;
        setConnection(conn);
        setPhase(conn ? "ready" : "need-bind");
      } catch {
        if (!cancelled) setPhase("need-bind");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, target]);

  async function bind(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError("");
    try {
      await api.bind({ identifier, password, instance_id: instance?.id });
      const result = await api.connections();
      const conn = result.connections.find((item) => item.instance_id === instance?.id) ?? null;
      setConnection(conn);
      setPassword("");
      setPhase(conn ? "ready" : "need-bind");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "绑定失败，请稍后重试");
    } finally {
      setPending(false);
    }
  }

  async function authorize() {
    if (pending) return;
    setPending(true);
    setError("");
    setPhase("delivering");
    try {
      const result = await api.authorizeComplete({
        client_id: clientId,
        state: state ?? undefined,
        target: instance?.base_url,
      });
      setTicket(result.ticket);
      const delivered = deliverTicket({
        type: "touchfish-auth:done",
        state: state,
        ticket: result.ticket,
        expires_in: result.expires_in,
      });
      setBridgeDone(delivered);
      setPhase("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "授权失败，请稍后重试");
      setPhase("ready");
    } finally {
      setPending(false);
    }
  }

  if (phase === "done") {
    return (
      <AuthLayout
        title="已返回应用"
        description={bridged_done ? "可以关闭此页面" : "请复制下面的票据返回应用"}
      >
        <div className="space-y-4">
          <div className="flex flex-col items-center gap-2 py-2 text-center">
            <CheckCircle2 className="size-4 text-success" />
            <p className="text-sm text-muted-foreground">
              已完成对 {instance?.display_name ?? "TouchFish"} 的授权
            </p>
          </div>
          {!bridged_done ? <IdentifierBlock label="一次性票据" value={ticket} /> : null}
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      eyebrow={instance ? `用于 ${instance.display_name}` : undefined}
      title={phase === "need-bind" ? "连接 TouchFish 账号" : "确认授权"}
      description={
        phase === "need-bind"
          ? "首次使用需要把平台账户与 TouchFish 账户关联"
          : `将向应用确认你的身份，并返回 ${instance?.display_name ?? "TouchFish"} 的登录凭据`
      }
      footer="授权完成后会自动返回原应用"
    >
      {error ? (
        <Alert variant="destructive" className="mb-4">
          {error}
        </Alert>
      ) : null}

      {phase === "checking" ? (
        <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          正在检查连接状态…
        </div>
      ) : null}

      {phase === "need-bind" ? (
        <AuthForm onSubmit={bind}>
          <AuthItem>
            <Field>
              <FieldLabel htmlFor="identifier">TouchFish 用户名或数字 ID</FieldLabel>
              <Input
                id="identifier"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                aria-invalid={Boolean(error)}
                required
              />
            </Field>
          </AuthItem>
          <AuthItem>
            <Field>
              <FieldLabel htmlFor="password">TouchFish 密码</FieldLabel>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(error)}
                required
              />
              <FieldDescription>仅用于向服务器验证，不会保存在本平台</FieldDescription>
            </Field>
          </AuthItem>
          <AuthItem>
            <Button type="submit" variant="primary" className="w-full" disabled={pending}>
              {pending ? (
                <>
                  <Loader2 className="animate-spin" />
                  正在连接…
                </>
              ) : (
                "连接并继续"
              )}
            </Button>
          </AuthItem>
        </AuthForm>
      ) : null}

      {(phase === "ready" || phase === "delivering") && connection ? (
        <div className="space-y-4">
          <AuthItem>
            <div className="rounded-lg border bg-muted px-4 py-3 text-sm">
              <div className="text-xs font-medium text-muted-foreground">已连接</div>
              <div className="mt-1">
                {connection.tfv5_username}
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  uid {connection.tfv5_uid}
                </span>
              </div>
            </div>
          </AuthItem>
          <AuthItem>
            <Button
              type="button"
              variant="primary"
              className="w-full"
              onClick={authorize}
              disabled={pending}
            >
              {pending ? (
                <>
                  <Loader2 className="animate-spin" />
                  正在授权…
                </>
              ) : (
                "继续"
              )}
            </Button>
          </AuthItem>
        </div>
      ) : null}
    </AuthLayout>
  );
}
