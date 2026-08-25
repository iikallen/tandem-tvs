import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
} from "react-router-dom";

import { EmployeeDirectoryPage } from "../pages/employees/EmployeeDirectoryPage";
import {
  EditorialListPage,
  EditorialReviewPage,
} from "../pages/editorial/EditorialListPage";
import { MediaLibraryPage } from "../pages/editorial/MediaLibraryPage";
import { TaxonomyPage } from "../pages/editorial/TaxonomyPage";
import { VersionHistoryPage } from "../pages/editorial/VersionHistoryPage";
import { HomePage } from "../pages/home/HomePage";
import { NewsDetailPage } from "../pages/news/NewsDetailPage";
import { NewsPage } from "../pages/news/NewsPage";
import { NotificationsPage } from "../pages/notifications/NotificationsPage";
import { NotificationSettingsPage } from "../pages/notifications/NotificationSettingsPage";
import { GlobalSearchPage } from "../pages/search/GlobalSearchPage";
import { ProfilePage } from "../pages/profile/ProfilePage";
import {
  ActivatePage,
  ForgotPasswordPage,
  LoginPage,
  PasswordChangePage,
  ResetPasswordPage,
} from "../pages/auth/AuthPages";
import { EditorialGuard } from "../pages/editorial/EditorialGuard";
import { PlatformUsersPage } from "../pages/platform/PlatformUsersPage";
import { MessengerAccessPage } from "../pages/messages/MessengerAccessPage";
import { api } from "../shared/api";
import { AnalyticsPage } from "../pages/editorial/AnalyticsPage";
import { EngagementSettingsPage } from "../pages/editorial/EngagementSettingsPage";
import { ModerationPage } from "../pages/editorial/ModerationPage";
import { AppShell } from "../shared/ui/AppShell";
import { PageState } from "../shared/ui/PageState";

const PublicationEditorPage = lazy(() =>
  import("../pages/editorial/PublicationEditorPage").then((module) => ({
    default: module.PublicationEditorPage,
  })),
);

function ModuleGuard({ module }: { module: "platform" | "messenger" }) {
  const session = useQuery({ queryKey: ["session"], queryFn: api.session });
  if (!session.data?.user?.access[module].length)
    return <Navigate to="/" replace />;
  return <Outlet />;
}

function AuthBoundary() {
  const session = useQuery({ queryKey: ["session"], queryFn: api.session });
  if (session.isPending) return <PageState kind="loading" />;
  const authenticated = Boolean(session.data?.authenticated);
  return (
    <Routes>
      <Route
        path="login"
        element={
          authenticated ? <Navigate to="/news" replace /> : <LoginPage />
        }
      />
      <Route path="activate" element={<ActivatePage />} />
      <Route path="forgot-password" element={<ForgotPasswordPage />} />
      <Route path="reset-password" element={<ResetPasswordPage />} />
      <Route
        element={
          authenticated ? <AppShell /> : <Navigate to="/login" replace />
        }
      >
        <Route index element={<HomePage />} />
        <Route path="news" element={<NewsPage />} />
        <Route path="news/:publicationId" element={<NewsDetailPage />} />
        <Route path="employees" element={<EmployeeDirectoryPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="profile/password" element={<PasswordChangePage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route
          path="settings/notifications"
          element={<NotificationSettingsPage />}
        />
        <Route path="search" element={<GlobalSearchPage />} />
        <Route
          element={
            <EditorialGuard>
              <Outlet />
            </EditorialGuard>
          }
        >
          <Route
            path="editorial/publications"
            element={<EditorialListPage />}
          />
          <Route
            path="editorial/publications/new"
            element={<PublicationEditorPage />}
          />
          <Route
            path="editorial/publications/:publicationId"
            element={<PublicationEditorPage />}
          />
          <Route path="editorial/review" element={<EditorialReviewPage />} />
          <Route path="editorial/media" element={<MediaLibraryPage />} />
          <Route path="editorial/taxonomy" element={<TaxonomyPage />} />
          <Route path="editorial/moderation" element={<ModerationPage />} />
          <Route path="editorial/analytics" element={<AnalyticsPage />} />
          <Route
            path="editorial/settings/engagement"
            element={<EngagementSettingsPage />}
          />
          <Route
            path="editorial/publications/:publicationId/versions"
            element={<VersionHistoryPage />}
          />
        </Route>
        <Route element={<ModuleGuard module="platform" />}>
          <Route path="platform/users" element={<PlatformUsersPage />} />
        </Route>
        <Route element={<ModuleGuard module="messenger" />}>
          <Route path="messages" element={<MessengerAccessPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
      }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<PageState kind="loading" />}>
          <AuthBoundary />
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
