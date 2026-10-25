import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Loader2 } from "lucide-react";

import { AuthForm, AuthItem, AuthLayout } from "@/pages/auth-layout";
import { Alert } from "@/components/ui/alert";
import { AnimatedButton, easings } from "@/components/ui/motion";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";

export function ResetPasswordPage() {
  const [search] = useSearchParams();
  const reduced = useReducedMotion();

  const [email, setEmail] = useState(search.get("email") ?? "");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      await api.resetPassword({
        email: email.trim(),
        code,
        new_password: password,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "重置失败，请稍后重试");
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <AuthLayout
        title="密码已重置"
        description="所有已登录设备都已被退出，请用新密码重新登录"
        footer={
          <>
            返回
            <Link
              to="/login"
              className="ml-1 underline-offset-4 hover:underline"
            >
              登录
            </Link>
          </>
        }
      >
        <AuthForm onSubmit={(event) => event.preventDefault()}>
          <AuthItem>
            <Alert variant="success">
              密码修改成功。为安全起见，其他设备上的会话已全部失效。
            </Alert>
          </AuthItem>
          <AuthItem>
            <AnimatedButton>
              <Link to="/login" className="block">
                <Button type="button" variant="primary" className="w-full">
                  去登录
                </Button>
              </Link>
            </AnimatedButton>
          </AuthItem>
        </AuthForm>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="重置密码"
      description="输入邮箱、验证码和新密码"
      footer={
        <>
          没收到验证码？
          <Link
            to="/forgot-password"
            className="ml-1 underline-offset-4 hover:underline"
          >
            重新发送
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
            <FieldLabel htmlFor="email">邮箱</FieldLabel>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </Field>
        </AuthItem>

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
              placeholder="123456"
              className="font-mono tracking-[0.4em]"
              required
            />
            <FieldDescription>15 分钟内有效</FieldDescription>
          </Field>
        </AuthItem>

        <AuthItem>
          <Field>
            <FieldLabel htmlFor="password">新密码</FieldLabel>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <FieldDescription>至少 8 位</FieldDescription>
          </Field>
        </AuthItem>

        <AuthItem>
          <AnimatedButton>
            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={pending || code.length !== 6 || password.length < 8}
            >
              {pending ? (
                <>
                  <Loader2 className="animate-spin" />
                  正在重置…
                </>
              ) : (
                "重置密码"
              )}
            </Button>
          </AnimatedButton>
        </AuthItem>
      </AuthForm>
    </AuthLayout>
  );
}
