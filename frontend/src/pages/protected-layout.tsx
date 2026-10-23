import { Navigate, Outlet, useLocation } from "react-router-dom";
import {
  Code2,
  Link2,
  MonitorSmartphone,
  Plug,
  ScrollText,
  Settings2,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { AppShell, type NavItem } from "@/components/app-shell";
import { Skeleton } from "@/components/ui/primitives";
import { useSession } from "@/lib/session";

const accountNav: NavItem[] = [
  { to: "/account", label: "账户", icon: <UserRound />, group: "账户" },
  { to: "/account/connections", label: "已连接账户", icon: <Link2 />, group: "账户" },
  { to: "/account/sessions", label: "登录设备", icon: <MonitorSmartphone />, group: "账户" },
];

const integrationAdminNav: NavItem[] = [
  { to: "/admin/integration", label: "对接", icon: <Plug />, group: "集成" },
];
const integrationNav: NavItem[] = [
  { to: "/developer", label: "开发者", icon: <Code2 />, group: "集成" },
];

const adminNav: NavItem[] = [
  { to: "/admin", label: "管理", icon: <ShieldCheck />, group: "管理员" },
  { to: "/admin/settings", label: "站点配置", icon: <Settings2 />, group: "管理员" },
  { to: "/admin/audit", label: "审计日志", icon: <ScrollText />, group: "管理员" },
];

export function ProtectedLayout() {
  const { user, loading } = useSession();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex h-dvh items-center justify-center bg-background">
        <Skeleton className="h-8 w-40" />
      </div>
    );
  }

  if (!user) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  const nav: NavItem[] =
    user.role === "admin"
      ? [...accountNav, ...integrationAdminNav, ...integrationNav, ...adminNav]
      : [...accountNav, ...integrationNav];

  return (
    <AppShell user={user} nav={nav}>
      <Outlet />
    </AppShell>
  );
}
