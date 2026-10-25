import { useState } from "react";
import { Link } from "react-router-dom";
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
import { useSiteConfig } from "@/lib/site";

export function ForgotPasswordPage() {
  const { config: site } = useSiteConfig();
  const reduced = useReducedMotion();

  const [identifier, setIdentifier] = useState("");
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const needCaptcha = Boolean(site?.captcha.enabled);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (needCaptcha && !captchaToken) {
      setError("请先完成人机验证");
      return;
    }
    setError("");
    setNotice("");
    setPending(true);
    try {
      const result = await api.forgotPassword({
        identifier: identifier.trim(),
        captcha_token: captchaToken ?? undefined,
      });
      setNotice(result.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "请求失败，请稍后重试");
      setCaptchaToken(null);
      setCaptchaReset((value) => value + 1);
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout
      title="找回密码"
      description="输入用户名或邮箱，我们会发送 6 位验证码"
      footer={
        <>
          想起来了？
          <Link to="/login" className="ml-1 underline-offset-4 hover:underline">
            返回登录
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

        <AnimatePresence initial={false}>
          {notice ? (
            <motion.div
              key="notice"
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
            <FieldLabel htmlFor="identifier">用户名或邮箱</FieldLabel>
            <Input
              id="identifier"
              autoComplete="username"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              placeholder="alice 或 alice@example.com"
              required
            />
            <FieldDescription>
              请注意，如果没有绑定邮箱则无法收到验证码
            </FieldDescription>
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
                  正在发送…
                </>
              ) : (
                "发送验证码"
              )}
            </Button>
          </AnimatedButton>
        </AuthItem>

        <AuthItem>
          <Link
            to="/reset-password"
            className="block text-center text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            已收到验证码，去重置密码
          </Link>
        </AuthItem>
      </AuthForm>
    </AuthLayout>
  );
}
