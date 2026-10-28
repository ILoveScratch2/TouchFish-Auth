import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";

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
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  PageWrapper,
  listContainerVariants,
  listItemVariants,
} from "@/components/ui/motion";
import { Skeleton } from "@/components/ui/primitives";
import { ApiError, api, type AdminSettings, type SettingSpec } from "@/lib/api";
import { invalidateSiteConfig } from "@/lib/site";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<string, string> = {
  general: "站点",
  security: "安全与令牌",
  captcha: "人机验证",
  email: "邮件与邮箱验证",
  oauth: "OAuth 应用",
};

const CATEGORY_DESC: Record<string, string> = {
  general: "站点名称与登录页公告",
  security: "注册策略与令牌有效期",
  captcha: "启用后注册/登录需要先通过 Turnstile 或 hCaptcha",
  email: "开启后新注册账户必须先验证邮箱才能登录",
  oauth: "本站作为 OAuth Provider 的策略（功能尚未实现",
};

const ENUM_LABEL: Record<string, string> = {
  follow_tfv5: "跟随 TouchFish 服务器",
  force_on: "始终允许",
  force_off: "始终禁止",
  turnstile: "Cloudflare Turnstile",
  hcaptcha: "hCaptcha",
};

export function SiteSettingsPage() {
  const [data, setData] = useState<AdminSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string | number | boolean>>(
    {},
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    api
      .adminSettings()
      .then((result) => {
        setData(result);
        setDraft({});
      })
      .catch(() => setError("读取配置失败，请确认你有管理员权限"));
  }, []);

  const grouped = useMemo(() => {
    if (!data) return [] as [string, SettingSpec[]][];
    const map = new Map<string, SettingSpec[]>();
    for (const spec of data._spec) {
      const category = spec.category ?? "general";
      if (!map.has(category)) map.set(category, []);
      map.get(category)!.push(spec);
    }
    return [...map.entries()];
  }, [data]);

  const dirty = Object.keys(draft).length > 0;

  function valueOf(spec: SettingSpec): string | number | boolean {
    if (spec.key in draft) return draft[spec.key];
    return (data?.[spec.key] ?? "") as string | number | boolean;
  }

  function setValue(key: string, value: string | number | boolean) {
    setDraft((current) => ({ ...current, [key]: value }));
    setNotice("");
  }

  async function save() {
    if (!dirty) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await api.adminUpdateSettings(draft);
      setData(result);
      setDraft({});
      setNotice("配置已保存，公开页面立即生效");
      invalidateSiteConfig();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader
        title="站点配置"
        description="改动即时生效；敏感值保存后不再回显"
        actions={
          <Button onClick={save} disabled={!dirty || saving}>
            {saving ? <Loader2 className="animate-spin" /> : null}
            {dirty ? `保存 ${Object.keys(draft).length} 项` : "保存"}
          </Button>
        }
      />

      {error ? <Alert variant="destructive">{error}</Alert> : null}
      {notice ? <Alert variant="success">{notice}</Alert> : null}

      {!data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
          className="flex flex-col gap-6"
        >
          {grouped.map(([category, specs]) => (
            <motion.div key={category} variants={listItemVariants}>
              <Card>
                <CardHeader>
                  <CardTitle>{CATEGORY_LABEL[category] ?? category}</CardTitle>
                  {CATEGORY_DESC[category] ? (
                    <CardDescription>{CATEGORY_DESC[category]}</CardDescription>
                  ) : null}
                </CardHeader>
                <CardContent className="space-y-5">
                  {specs.map((spec) => (
                    <SettingField
                      key={spec.key}
                      spec={spec}
                      value={valueOf(spec)}
                      hasSecret={Boolean(data[`has_${spec.key}`])}
                      changed={spec.key in draft}
                      onChange={(value) => setValue(spec.key, value)}
                    />
                  ))}
                  {category === "captcha" ? <CaptchaProbe /> : null}
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}
    </PageWrapper>
  );
}

function SettingField({
  spec,
  value,
  hasSecret,
  changed,
  onChange,
}: {
  spec: SettingSpec;
  value: string | number | boolean;
  hasSecret: boolean;
  changed: boolean;
  onChange: (value: string | number | boolean) => void;
}) {
  const label = spec.label ?? spec.key;
  const id = `setting-${spec.key}`;

  if (spec.type === "bool") {
    return (
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium">
            {label}
            {changed ? <Flag /> : null}
          </div>
        </div>
        <Toggle
          checked={Boolean(value)}
          onChange={(next) => onChange(next)}
          label={label}
        />
      </div>
    );
  }

  if (spec.type === "enum") {
    return (
      <Field>
        <FieldLabel htmlFor={id}>
          {label}
          {changed ? <Flag /> : null}
        </FieldLabel>
        <select
          id={id}
          value={String(value)}
          onChange={(event) => onChange(event.target.value)}
          className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm focus-visible:border-foreground/30 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          {(spec.options ?? []).map((option) => (
            <option key={option} value={option}>
              {ENUM_LABEL[option] ?? option}
            </option>
          ))}
        </select>
      </Field>
    );
  }

  if (spec.type === "text") {
    return (
      <Field>
        <FieldLabel htmlFor={id}>
          {label}
          {changed ? <Flag /> : null}
        </FieldLabel>
        <textarea
          id={id}
          value={String(value)}
          onChange={(event) => onChange(event.target.value)}
          rows={3}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:border-foreground/30 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </Field>
    );
  }

  if (spec.type === "secret") {
    return (
      <Field>
        <FieldLabel htmlFor={id}>
          {label}
          {changed ? <Flag /> : null}
        </FieldLabel>
        <Input
          id={id}
          type="password"
          autoComplete="new-password"
          value={String(value ?? "")}
          onChange={(event) => onChange(event.target.value)}
          placeholder={hasSecret ? "已配置，留空表示不修改" : "未配置"}
        />
        <FieldDescription>
          {hasSecret ? "已保存过值；只有填写新值才会覆盖" : "尚未配置"}
        </FieldDescription>
      </Field>
    );
  }

  return (
    <Field>
      <FieldLabel htmlFor={id}>
        {label}
        {changed ? <Flag /> : null}
      </FieldLabel>
      <Input
        id={id}
        type={spec.type === "int" ? "number" : "text"}
        value={String(value ?? "")}
        min={spec.min}
        max={spec.max}
        onChange={(event) =>
          onChange(
            spec.type === "int"
              ? Number(event.target.value || 0)
              : event.target.value,
          )
        }
      />
      {spec.type === "int" && spec.min !== undefined ? (
        <FieldDescription>
          允许范围 {spec.min}–{spec.max}
        </FieldDescription>
      ) : null}
    </Field>
  );
}

function Flag() {
  return (
    <span className="size-1.5 rounded-full bg-primary" aria-label="已修改" />
  );
}

/**
 * 用当前已保存的配置向服务商发一次探测。
 * 没有真实 token 时，正确配置会返回 invalid-input-response —— 借此区分
 * "Secret 配错"与"前端没把 token 传上来"。
 */
function CaptchaProbe() {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{
    hint: string;
    codes: string[];
    message: string;
  } | null>(null);
  const [error, setError] = useState("");

  async function probe() {
    setPending(true);
    setError("");
    setResult(null);
    try {
      const data = await api.adminCaptchaTest();
      setResult({ hint: data.hint, codes: data.codes, message: data.message });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "探测失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border bg-muted px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-medium">测试配置</div>
        <Button variant="outline" size="sm" onClick={probe} disabled={pending}>
          {pending ? <Loader2 className="animate-spin" /> : null}
          发一次探测
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        探测用假 token 请求服务商：Secret 正确会返回 token 无效；Secret
        错误会直接报错。
      </p>
      {error ? <p className="text-xs text-error-foreground">{error}</p> : null}
      {result ? (
        <div className="space-y-1">
          <p className="text-xs text-foreground">{result.hint}</p>
          {result.codes.length > 0 ? (
            <p className="font-mono text-[11px] text-muted-foreground">
              {result.codes.join(", ")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full border transition-colors",
        checked ? "border-primary bg-primary" : "border-border bg-muted",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 size-4.5 rounded-full bg-background shadow-sm transition-[left] duration-150",
          checked ? "left-[22px]" : "left-0.5",
        )}
        style={{ width: 18, height: 18 }}
      />
    </button>
  );
}
