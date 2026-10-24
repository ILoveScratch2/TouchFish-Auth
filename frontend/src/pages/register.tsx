import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Loader2 } from "lucide-react";

import { AuthForm, AuthItem, AuthLayout } from "@/pages/auth-layout";
import { Alert } from "@/components/ui/alert";
import { AnimatedButton, easings } from "@/components/ui/motion";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { CaptchaWidget } from "@/components/captcha";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useSiteConfig } from "@/lib/site";

export function RegisterPage() {
  const navigate = useNavigate();
  const { refresh } = useSession();
  const { config: site, loading: siteLoading } = useSiteConfig();
  const reduced = useReducedMotion();

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  // 邮箱验证阶段
  const [phase, setPhase] = useState<"form" | "verify">("form");
  const [verificationId, setVerificationId] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");

  const needCaptcha = Boolean(site?.captcha.enabled);
  const needEmail = Boolean(site?.email_verification);
  const blocked =
    site && !site.registration.allowed ? site.registration.reason : "";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    if (needCaptcha && !captchaToken) {
      setError("请先完成人机验证");
      return;
    }
    setError("");
    setPending(true);
    try {
      const result = await api.register({
        username,
        password,
        email: email || undefined,
        captcha_token: captchaToken ?? undefined,
      });
      if (result.pending_verification) {
        setVerificationId(result.verification_id ?? "");
        setMaskedEmail(result.email ?? "");
        setNotice("");
        setPhase("verify");
        return;
      }
      await refresh();
      navigate("/account", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "注册失败，请稍后重试");
      // token 一次性，失败后必须复位
      setCaptchaToken(null);
      setCaptchaReset((value) => value + 1);
    } finally {
      setPending(false);
    }
  }

  async function verify(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    setError("");
    setPending(true);
    try {
      await api.verifyEmail({ verification_id: verificationId, code });
      await refresh();
      navigate("/account", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "验证失败，请稍后重试");
      setCode("");
    } finally {
      setPending(false);
    }
  }

  async function resend() {
    if (pending) return;
    setPending(true);
    setError("");
    setNotice("");
    try {
      const result = await api.resendVerification({
        identifier: username,
        password,
      });
      setVerificationId(result.verification_id);
      setMaskedEmail(result.email);
      setNotice("验证码已重新发送");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "重发失败，请稍后重试");
    } finally {
      setPending(false);
    }
  }

  if (siteLoading) {
    return (
      <AuthLayout title="创建账号" description="正在读取站点配置…">
        <AuthItem>
          <div className="h-10" />
        </AuthItem>
      </AuthLayout>
    );
  }

  if (blocked) {
    return (
      <AuthLayout
        title="暂停注册"
        description="该服务器当前不接受新的平台账号"
        footer={
          <Link to="/login" className="underline-offset-4 hover:underline">
            返回登录
          </Link>
        }
      >
        <AuthItem>
          <Alert variant="warning">{blocked}</Alert>
        </AuthItem>
      </AuthLayout>
    );
  }

  if (phase === "verify") {
    return (
      <AuthLayout
        title="验证邮箱"
        description={`验证码已发送到 ${maskedEmail}`}
        footer={
          <button
            type="button"
            onClick={resend}
            className="underline-offset-4 hover:underline"
          >
            没收到？重新发送
          </button>
        }
      >
        <AuthForm onSubmit={verify}>
          {error ? (
            <motion.div
              initial={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
              animate={
                reduced ? { opacity: 1 } : { opacity: 1, height: "auto" }
              }
              transition={
                reduced
                  ? { duration: 0 }
                  : { duration: 0.2, ease: easings.easeOutExpo }
              }
              className="overflow-hidden"
            >
              <Alert variant="destructive">{error}</Alert>
            </motion.div>
          ) : null}
          <AnimatePresence initial={false}>
            {notice ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="overflow-hidden"
              >
                <Alert variant="success">{notice}</Alert>
              </motion.div>
            ) : null}
          </AnimatePresence>

          <AuthItem>
            <Field>
              <FieldLabel htmlFor="code">6 位验证码</FieldLabel>
              <Input
                id="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(event) =>
                  setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                }
                aria-invalid={Boolean(error)}
                placeholder="123456"
                className="font-mono tracking-[0.4em]"
                required
              />
              <FieldDescription>15 分钟内有效</FieldDescription>
            </Field>
          </AuthItem>

          <AuthItem>
            <AnimatedButton>
              <Button
                type="submit"
                variant="primary"
                className="w-full"
                disabled={pending || code.length !== 6}
              >
                {pending ? (
                  <>
                    <Loader2 className="animate-spin" />
                    正在验证…
                  </>
                ) : (
                  "验证并完成注册"
                )}
              </Button>
            </AnimatedButton>
          </AuthItem>
        </AuthForm>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="创建账号"
      description="注册后可连接你的 TouchFish 服务器账号"
      footer={
        <>
          已有账号？
          <Link to="/login" className="ml-1 underline-offset-4 hover:underline">
            去登录
          </Link>
        </>
      }
    >
      <AuthForm onSubmit={submit}>
        <AnimatePresence initial={false}>
          {error ? (
            <motion.div
              key="error"
              initial={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
              animate={
                reduced ? { opacity: 1 } : { opacity: 1, height: "auto" }
              }
              exit={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
              transition={
                reduced
                  ? { duration: 0 }
                  : { duration: 0.2, ease: easings.easeOutExpo }
              }
              className="overflow-hidden"
            >
              <Alert variant="destructive">{error}</Alert>
            </motion.div>
          ) : null}
        </AnimatePresence>

        <AuthItem>
          <Field>
            <FieldLabel htmlFor="username">用户名</FieldLabel>
            <Input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              aria-invalid={Boolean(error)}
              required
            />
            <FieldDescription>
              2–32 位，可用字母、数字、下划线、连字符或中文
            </FieldDescription>
          </Field>
        </AuthItem>

        <AuthItem>
          <Field>
            <FieldLabel htmlFor="email">
              邮箱{needEmail ? "" : "（可选）"}
            </FieldLabel>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(error)}
              required={needEmail}
            />
            {needEmail ? (
              <FieldDescription>该站点要求验证邮箱后才能登录</FieldDescription>
            ) : null}
          </Field>
        </AuthItem>

        <AuthItem>
          <Field>
            <FieldLabel htmlFor="password">密码</FieldLabel>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(error)}
              required
            />
            <FieldDescription>至少 8 位</FieldDescription>
          </Field>
        </AuthItem>

        {needCaptcha && site?.captcha.provider ? (
          <AuthItem>
            <CaptchaWidget
              provider={site.captcha.provider}
              siteKey={site.captcha.site_key}
              onToken={setCaptchaToken}
              resetSignal={captchaReset}
            />
          </AuthItem>
        ) : null}

        <AuthItem>
          <AnimatedButton>
            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={pending}
            >
              {pending ? (
                <>
                  <Loader2 className="animate-spin" />
                  正在创建…
                </>
              ) : (
                "创建账号"
              )}
            </Button>
          </AnimatedButton>
        </AuthItem>
      </AuthForm>
    </AuthLayout>
  );
}
