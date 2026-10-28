import { Navigate, Route, Routes } from "react-router-dom";
import { MotionConfig } from "framer-motion";

import { SessionProvider } from "@/lib/session";
import { AccountPage } from "@/pages/account";
import { AdminPage } from "@/pages/admin";
import { AuditPage } from "@/pages/audit";
import { AuthorizePage } from "@/pages/authorize";
import { ConnectionsPage } from "@/pages/connections";
import { DeveloperPage } from "@/pages/developer";
import { ForgotPasswordPage } from "@/pages/forgot-password";
import { IntegrationPage } from "@/pages/integration";
import { LoginPage } from "@/pages/login";
import { OidcClientsPage } from "@/pages/admin-clients";
import { OAuthProvidersPage } from "@/pages/oauth-providers";
import { ProtectedLayout } from "@/pages/protected-layout";
import { RegisterPage } from "@/pages/register";
import { ResetPasswordPage } from "@/pages/reset-password";
import { SessionsPage } from "@/pages/sessions";
import { SiteSettingsPage } from "@/pages/site-settings";

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <SessionProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/authorize" element={<AuthorizePage />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/account" element={<AccountPage />} />
            <Route path="/account/connections" element={<ConnectionsPage />} />
            <Route path="/account/sessions" element={<SessionsPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/admin/settings" element={<SiteSettingsPage />} />
            <Route path="/admin/oauth" element={<OAuthProvidersPage />} />
            <Route path="/admin/clients" element={<OidcClientsPage />} />
            <Route path="/admin/audit" element={<AuditPage />} />
            <Route path="/admin/integration" element={<IntegrationPage />} />
            {/* 开发者对所有登录用户开放 */}
            <Route path="/developer" element={<DeveloperPage />} />
            <Route
              path="/admin/developer"
              element={<Navigate to="/developer" replace />}
            />
          </Route>
          <Route path="/" element={<Navigate to="/account" replace />} />
          <Route path="*" element={<Navigate to="/account" replace />} />
        </Routes>
      </SessionProvider>
    </MotionConfig>
  );
}
