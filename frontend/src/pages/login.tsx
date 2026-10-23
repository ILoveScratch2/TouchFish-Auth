import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Eye, EyeOff, Loader2 } from "lucide-react";

import { AuthForm, AuthItem, AuthLayout } from "@/pages/auth-layout";
import { Alert } from "@/components/ui/alert";
import { AnimatedButton, easings } from "@/components/ui/motion";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { MethodButton, OrDivider } from "@/components/method-button";
import { ApiError, api, fetchAuthConfig, type AuthMethod } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useSiteConfig } from "@/lib/site";
import { CaptchaWidget } from "@/components/captcha";

type Mode = "platform" | "tfv5";

export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { user, loading, refresh } = useSession();
  const { config: site } = useSiteConfig();
  const reduced = useReducedMotion();

  const [mode, setMode] = useState<Mode>("platform");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [methods, setMethods] = useState<AuthMethod[]>([]);
  const [canRegister, setCanRegister] = useState(false);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);

  const needCaptcha = Boolean(site?.captcha.enabled && site.captcha.on_login);

  const next = params.get("next") ?? "/account";

  useEffect(() => {
    fetchAuthConfig()
      .then((config) => setMethods(config.methods.filter((m) => m.enabled)))
      .catch(() => setMethods([]));
    api
      .registrationStatus()
      .then((status) => setCanRegister(status.allowed))
      .catch(() => setCanRegister(false));
  }, []);

  useEffect(() => {
    if (!loading && user) navigate(next, { replace: true });
  }, [loading, user, navigate, next]);

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
      if (mode === "platform") {
        await api.login({
          identifier,
          password,
          captcha_token: captchaToken ?? undefined,
        });
      } else {
        await api.tfv5Login({
          identifier,
          password,
          captcha_token: captchaToken ?? undefined,
        });
      }
      await refresh();
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败，请稍后重试");
      // token 一次性
      setCaptchaToken(null);
      setCaptchaReset((value) => value + 1);
    } finally {
      setPending(false);
    }
  }

  const otherMethods = methods.filter((method) =>
    mode === "platform" ? method.kind === "tfv5" : method.kind === "password",
  );

  return (
    <AuthLayout
      title="登录"
      description={
        mode === "platform"
          ? "使用 TouchFish Auth 账号继续"
          : "使用 TouchFish 服务器账号登录"
      }
      footer={
        canRegister ? (
          <>
            还没有账号？
            <Link
              to="/register"
              className="ml-1 underline-offset-4 hover:underline"
            >
              创建一个
            </Link>
          </>
        ) : null
      }
    >
      <AuthForm onSubmit={submit}>
        {site?.announcement ? (
          <AuthItem>
            <Alert variant="info">{site.announcement}</Alert>
          </AuthItem>
        ) : null}

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
            <FieldLabel htmlFor="identifier">
              {mode === "platform"
                ? "用户名或邮箱"
                : "TouchFish 用户名或数字 ID"}
            </FieldLabel>
            <Input
              id="identifier"
              autoComplete="username"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              aria-invalid={Boolean(error)}
              required
            />
            {mode === "tfv5" ? (
              <FieldDescription>
                {site?.tfv5_login_auto_signup
                  ? "将用这组凭据向 TouchFish 服务器验证；未绑定过的账号会自动开通并绑定"
                  : "将用这组凭据向 TouchFish 服务器验证；该站点不接受自动开通，未绑定的账号需先用平台账号登录再绑定"}
              </FieldDescription>
            ) : null}
          </Field>
        </AuthItem>

        <AuthItem>
          <Field>
            <FieldLabel htmlFor="password">密码</FieldLabel>{" "}
            <div className="relative">
              <Input
                id="password"
                type={visible ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(error)}
                className="pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setVisible((value) => !value)}
                aria-label={visible ? "隐藏密码" : "显示密码"}
                className="absolute right-1 top-1 flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {visible ? (
                  <EyeOff className="size-4" />
                ) : (
                  <Eye className="size-4" />
                )}
              </button>
            </div>
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
                  正在登录…
                </>
              ) : (
                "登录"
              )}
            </Button>
          </AnimatedButton>
        </AuthItem>
      </AuthForm>

      {otherMethods.length > 0 ? (
        <AuthItem className="mt-4 space-y-2">
          <OrDivider />
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={mode}
              initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduced ? { opacity: 0 } : { opacity: 0, y: -8 }}
              transition={
                reduced
                  ? { duration: 0 }
                  : { duration: 0.2, ease: easings.easeOutExpo }
              }
              className="space-y-2"
            >
              {otherMethods.map((method) => (
                <MethodButton
                  key={method.id}
                  method={method}
                  disabled={pending}
                  onClick={() => {
                    setMode(method.kind === "tfv5" ? "tfv5" : "platform");
                    setError("");
                  }}
                />
              ))}
            </motion.div>
          </AnimatePresence>
        </AuthItem>
      ) : null}
    </AuthLayout>
  );
}
