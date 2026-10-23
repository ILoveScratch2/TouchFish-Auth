import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { springs } from "@/components/ui/motion";
import type { User } from "@/lib/api";
import { useSession } from "@/lib/session";

export interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  /** 分组名。相邻项分组不同时插入小标题与分隔线 */
  group?: string;
}

interface AppShellProps {
  user: User;
  nav: NavItem[];
  children: ReactNode;
}

export function AppShell({ user, nav, children }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const { signOut } = useSession();
  const location = useLocation();
  const navigate = useNavigate();

  async function logout() {
    // 必须走 signOut 清会话
    await signOut().catch(() => undefined);
    navigate("/login", { replace: true });
  }

  const sidebar = (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out",
        collapsed ? "w-16" : "w-64",
        mobileOpen ? "w-64" : "hidden lg:flex",
      )}
    >
      <div className={cn("flex items-center gap-2 p-3", collapsed && "justify-center")}>
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-background p-1">
          <img src="/logo.png" alt="TouchFish" className="h-full w-full object-contain" />
        </div>
        {!collapsed && (
          <div className="min-w-0 flex-1 leading-none">
            <div className="truncate font-display text-sm font-semibold tracking-tight">
              TouchFish
            </div>
            <div className="mt-0.5 truncate text-xs text-muted-foreground">Auth</div>
          </div>
        )}
        {!collapsed && (
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0"
            aria-label="折叠侧栏"
            onClick={() => setCollapsed(true)}
          >
            <PanelLeftClose />
          </Button>
        )}
      </div>

      <div className="mx-3 h-px bg-sidebar-border" />

      <nav aria-label="主导航" className="flex-1 overflow-y-auto p-3">
        <ul className="space-y-1">
          {nav.map((item, index) => {
            const active =
              location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
            const showGroup =
              item.group && item.group !== nav[index - 1]?.group && !collapsed;
            return (
              <li key={item.to}>
                {showGroup ? (
                  <>
                    {index > 0 ? <div className="my-2 h-px bg-sidebar-border" /> : null}
                    <div className="px-2.5 pb-1 text-xs font-medium text-muted-foreground">
                      {item.group}
                    </div>
                  </>
                ) : null}
                <Link
                  to={item.to}
                  onClick={() => setMobileOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative flex items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
                    "hover:bg-sidebar-accent",
                    collapsed && "justify-center px-0",
                  )}
                >
                  {active && (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-0 rounded-md bg-sidebar-accent"
                      transition={springs.snappy}
                    />
                  )}
                  <span className={cn("relative [&_svg]:size-4", active && "text-primary")}>
                    {item.icon}
                  </span>
                  {!collapsed && <span className="relative truncate">{item.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-sidebar-border p-3">
        {collapsed ? (
          <Button variant="ghost" size="icon" aria-label="展开侧栏" onClick={() => setCollapsed(false)}>
            <PanelLeftOpen />
          </Button>
        ) : (
          <div className="flex items-center gap-2">
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{user.display_name ?? user.username}</div>
              <div className="truncate text-xs text-muted-foreground">{user.username}</div>
            </div>
            <Button variant="ghost" size="icon" aria-label="退出登录" onClick={logout}>
              <LogOut />
            </Button>
          </div>
        )}
      </div>
    </aside>
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {sidebar}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}
      {mobileOpen && <div className="fixed inset-y-0 left-0 z-30 lg:hidden">{sidebar}</div>}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2 lg:hidden">
          <Button variant="ghost" size="icon" aria-label="打开侧栏" onClick={() => setMobileOpen(true)}>
            <Menu />
          </Button>
          <img src="/logo.png" alt="" className="size-5 object-contain" />
          <span className="font-display text-sm font-semibold">TouchFish Auth</span>
          <div className="flex-1" />
          <Button variant="ghost" size="icon" aria-label="切换主题" onClick={toggle}>
            {theme === "dark" ? <Sun /> : <Moon />}
          </Button>
        </div>

        <main className="flex min-h-0 min-w-0 w-full flex-1 flex-col overflow-y-auto px-6 py-6 lg:px-8">
          <div className="mx-auto flex w-full min-w-0 max-w-6xl flex-1 flex-col gap-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

export function ShellThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <Button variant="ghost" size="icon" aria-label="切换主题" onClick={toggle}>
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
  );
}
