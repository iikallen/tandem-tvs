import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";

import { api } from "../api";
import { t } from "../i18n";
import { EditIcon, HomeIcon, NewsIcon, UserIcon, UsersIcon } from "./icons";

const links = [
  { to: "/", label: t("home"), icon: HomeIcon, end: true },
  { to: "/news", label: t("news"), icon: NewsIcon },
  { to: "/employees", label: t("employees"), icon: UsersIcon },
  { to: "/profile", label: t("profile"), icon: UserIcon },
];

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const visibleLinks = me.data?.module_roles?.some((role) =>
    ["author", "editor", "admin", "administrator"].includes(role),
  )
    ? [
        ...links,
        {
          to: "/editorial/publications",
          label: t("editorial"),
          icon: EditIcon,
        },
      ]
    : links;
  return (
    <nav
      className={mobile ? "mobile-nav" : "nav"}
      aria-label={mobile ? t("mobileNavigation") : t("navigation")}
    >
      {visibleLinks.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} className="nav__link">
          <Icon className="nav__icon" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function AppShell() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const toggleLabel = theme === "light" ? t("themeDark") : t("themeLight");
  return (
    <div className="app-shell" data-theme={theme}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true" />
          <span>{t("appName")}</span>
        </div>
        <Navigation />
        <button
          className="theme-button"
          type="button"
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          aria-label={toggleLabel}
        >
          {toggleLabel}
        </button>
      </aside>
      <main className="main">
        <div className="page">
          <Outlet />
        </div>
      </main>
      <Navigation mobile />
    </div>
  );
}
