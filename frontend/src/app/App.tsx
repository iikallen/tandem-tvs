import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { EmployeeDirectoryPage } from "../pages/employees/EmployeeDirectoryPage";
import { EditorialListPage } from "../pages/editorial/EditorialListPage";
import { HomePage } from "../pages/home/HomePage";
import { NewsDetailPage } from "../pages/news/NewsDetailPage";
import { NewsPage } from "../pages/news/NewsPage";
import { ProfilePage } from "../pages/profile/ProfilePage";
import { AppShell } from "../shared/ui/AppShell";
import { PageState } from "../shared/ui/PageState";

const PublicationEditorPage = lazy(() =>
  import("../pages/editorial/PublicationEditorPage").then((module) => ({
    default: module.PublicationEditorPage,
  })),
);

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
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<HomePage />} />
              <Route path="news" element={<NewsPage />} />
              <Route path="news/:publicationId" element={<NewsDetailPage />} />
              <Route path="employees" element={<EmployeeDirectoryPage />} />
              <Route path="profile" element={<ProfilePage />} />
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
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
