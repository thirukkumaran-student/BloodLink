import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AppShell, Banner, useToast } from "@bloodlink/ui";
import { ApiError, onSessionExpired, session } from "../api/client";
import { authApi, notificationApi } from "../api/endpoints";
import { useCurrentUser, useNotifications } from "./hooks";
import { navForUser } from "./navigation";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";
import { AccountPage } from "../features/auth/AccountPage";
import { NotificationPanel } from "../components/NotificationPanel";
import { IndividualNeedsPage } from "../features/individual/NeedsPage";
import { HospitalQueuePage } from "../features/hospital/QueuePage";
import { HospitalRequestsPage } from "../features/hospital/RequestsPage";
import { HospitalRequestDetailPage } from "../features/hospital/RequestDetailPage";
import { DonorOverviewPage } from "../features/donor/OverviewPage";
import { DonorProfilePage } from "../features/donor/ProfilePage";
import { DonorCommitmentsPage } from "../features/donor/CommitmentsPage";
import { SubscriptionsPage } from "../features/donor/SubscriptionsPage";
import { BloodCentrePage } from "../features/blood-centre/NearbyRequestsPage";
import { MessagesPage } from "../features/messages/MessagesPage";
import { AdminOrganizationsPage } from "../features/admin/OrganizationsPage";
import { AdminUsersPage } from "../features/admin/UsersPage";
import { AdminAuditPage } from "../features/admin/AuditPage";
import { PlatformPage } from "../features/admin/PlatformPage";
import { NotFoundPage, UnauthorizedPage } from "../components/FallbackPages";
function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isLoading, error, refetch } = useCurrentUser();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const notifications = useNotifications(Boolean(user));
  const authed = Boolean(user) || Boolean(session.accessToken());
  const handleNavigate = useCallback(
    (to) => navigate(to),
    [navigate]
  );
  const handleSignOut = useCallback(async () => {
    try {
      await authApi.logout(session.refreshToken());
    } catch {
    }
    session.clear();
    toast.push({ tone: "info", title: "Signed out", body: "Your session was ended on this device." });
    navigate("/login", { replace: true });
    window.location.reload();
  }, [navigate, toast]);
  const nav = useMemo(() => navForUser(user), [user]);
  // A token that the server rejects (expired, revoked, or the demo database was
  // reset) must return the user to sign-in rather than leaving a dead session in
  // localStorage that keeps retrying. The same signal fires when a background
  // request 401s while the app is open (see api/client.js).
  const unauthenticated = error instanceof ApiError && (error.status === 401 || error.code === "UNAUTHENTICATED" || error.code === "TOKEN_EXPIRED");
  useEffect(() => {
    return onSessionExpired(() => {
      session.clear();
      queryClient.clear();
      toast.push({
        tone: "warning",
        title: "Session ended",
        body: "Please sign in again.",
      });
    });
  }, [queryClient, toast]);
  useEffect(() => {
    if (!unauthenticated) return;
    session.clear();
    queryClient.clear();
    toast.push({
      tone: "warning",
      title: "Session ended",
      body: "Please sign in again.",
    });
  }, [unauthenticated, queryClient, toast]);
  if (!authed || location.pathname === "/login" || location.pathname === "/register") {
    return <Routes><Route path="/login" element={<LoginPage onDone={() => navigate("/", { replace: true })} />} /><Route path="/register" element={<RegisterPage onDone={() => navigate("/", { replace: true })} />} /><Route path="*" element={<Navigate to="/login" replace />} /></Routes>;
  }
  if (isLoading && !user) {
    return <div className="bl-auth"><div className="bl-auth__panel" style={{ gridColumn: "1 / -1" }}><div className="bl-loading"><span className="bl-spinner" aria-hidden="true" /><span>Loading your BloodLink workspace…</span></div></div></div>;
  }
  if (error && !user && !unauthenticated) {
    return <div className="bl-app__main"><Banner tone="danger" title="Cannot reach your workspace.">{error.message}
        </Banner><div style={{ marginTop: "var(--bl-space-4)" }}><button
      className="bl-button bl-button--primary"
      type="button"
      onClick={() => refetch()}
    >
            Try again
          </button><button
      className="bl-button bl-button--ghost"
      type="button"
      style={{ marginLeft: "var(--bl-space-2)" }}
      onClick={() => {
        session.clear();
        navigate("/login", { replace: true });
      }}
    >
            Sign in instead
          </button></div></div>;
  }
  const verificationNotice = user?.organization && user.organization.verificationStatus !== "VERIFIED" ? <Banner tone="warning" title="Verification pending.">{user.organization.name} cannot submit or respond to requests until BloodLink administration
        verifies it. You can still explore the workspace.
      </Banner> : null;
  return <AppShell
    nav={nav}
    activePath={location.pathname}
    onNavigate={handleNavigate}
    user={user ? {
      name: user.fullName,
      initials: user.initials,
      role: user.role,
      organization: user.organization?.name ?? null
    } : void 0}
    onSignOut={handleSignOut}
    verificationNotice={verificationNotice}
    headerExtras={<button
      type="button"
      className="bl-bell"
      title="Notifications"
      onClick={() => setNotificationsOpen((value) => !value)}
    >
          🔔
          {notifications.data?.unreadCount ? <span className="bl-bell__count">{notifications.data.unreadCount}</span> : null}</button>}
  >{notificationsOpen ? <NotificationPanel
    data={notifications.data}
    loading={notifications.isLoading}
    onClose={() => setNotificationsOpen(false)}
    onMarkAll={async () => {
      await notificationApi.markRead();
      await notifications.refetch();
      refetch();
    }}
  /> : null}<Routes><Route path="/" element={<HomeRedirect role={user?.role} />} /><Route path="/account" element={<AccountPage user={user} onSaved={refetch} />} /><Route path="/needs" element={<IndividualNeedsPage user={user} />} /><Route path="/hospital/queue" element={<HospitalQueuePage user={user} />} /><Route path="/hospital/requests" element={<HospitalRequestsPage user={user} />} /><Route path="/hospital/requests/:requestId" element={<HospitalRequestDetailPage user={user} />} /><Route path="/donor" element={<DonorOverviewPage user={user} />} /><Route path="/donor/profile" element={<DonorProfilePage user={user} />} /><Route path="/donor/commitments" element={<DonorCommitmentsPage user={user} />} /><Route path="/donor/hospitals" element={<SubscriptionsPage user={user} />} /><Route path="/blood-centre" element={<BloodCentrePage user={user} />} /><Route path="/messages" element={<MessagesPage />} /><Route path="/admin/organizations" element={<AdminOrganizationsPage user={user} />} /><Route path="/admin/users" element={<AdminUsersPage user={user} />} /><Route path="/admin/audit" element={<AdminAuditPage user={user} />} /><Route path="/platform" element={<PlatformPage />} /><Route path="/unauthorized" element={<UnauthorizedPage />} /><Route path="*" element={<NotFoundPage />} /></Routes></AppShell>;
}
function HomeRedirect({ role }) {
  const target = role === "HOSPITAL" ? "/hospital/queue" : role === "BLOOD_CENTRE" ? "/blood-centre" : role === "ADMIN" ? "/admin/organizations" : "/donor";
  return <Navigate to={target} replace />;
}
export {
  App
};
