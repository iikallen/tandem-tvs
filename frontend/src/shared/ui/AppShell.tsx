import { useState, type ComponentType, type SVGProps } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "../api";
import { t } from "../i18n";
import { Avatar } from "./Avatar";
import { EditIcon, HomeIcon, NewsIcon, UserIcon, UsersIcon } from "./icons";

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  end?: boolean;
};

const portalLinks: NavItem[] = [
  { to: "/", label: t("home"), icon: HomeIcon, end: true },
  { to: "/news", label: t("news"), icon: NewsIcon },
  { to: "/employees", label: t("employees"), icon: UsersIcon },
  { to: "/profile", label: t("profile"), icon: UserIcon },
  { to: "/notifications", label: t("notifications"), icon: NewsIcon },
];

const messengerLink: NavItem = {
  to: "/messages",
  label: t("messenger"),
  icon: NewsIcon,
};
const platformLink: NavItem = {
  to: "/platform/users",
  label: t("userManagement"),
  icon: UsersIcon,
};

const editorialLinks: NavItem[] = [
  {
    to: "/editorial/publications",
    label: t("publications"),
    icon: EditIcon,
  },
  { to: "/editorial/moderation", label: t("moderation"), icon: NewsIcon },
  { to: "/editorial/analytics", label: t("analytics"), icon: HomeIcon },
  {
    to: "/editorial/settings/engagement",
    label: t("engagementSettings"),
    icon: EditIcon,
  },
  { to: "/editorial/review", label: t("review"), icon: NewsIcon },
  { to: "/editorial/media", label: t("media"), icon: HomeIcon },
  {
    to: "/editorial/taxonomy",
    label: t("categoriesAndTags"),
    icon: UsersIcon,
  },
];

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const canEdit = me.data?.access.news.some((role) =>
    ["AUTHOR", "EDITOR", "ADMIN"].includes(role),
  );
  const canMessage = Boolean(me.data?.access.messenger.length);
  const isPlatformAdmin = me.data?.access.platform.includes("ADMIN");
  const expandedPortalLinks = [
    ...portalLinks,
    ...(canMessage ? [messengerLink] : []),
    ...(isPlatformAdmin ? [platformLink] : []),
  ];
  const mobileLinks = canEdit
    ? [...expandedPortalLinks.slice(0, 3), editorialLinks[0], portalLinks[4]]
    : expandedPortalLinks.slice(0, 5);
  const groups = mobile
    ? [{ label: "", links: mobileLinks }]
    : [
        { label: t("portalSection"), links: expandedPortalLinks },
        ...(canEdit
          ? [{ label: t("editorialSection"), links: editorialLinks }]
          : []),
      ];
  return (
    <nav
      className={mobile ? "mobile-nav" : "nav"}
      aria-label={mobile ? t("mobileNavigation") : t("navigation")}
    >
      {groups.map((group) => (
        <div className="nav__group" key={group.label || "mobile"}>
          {group.label && <p className="nav__label">{group.label}</p>}
          {group.links.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className="nav__link">
              <Icon className="nav__icon" />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  );
}

export function AppShell() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toggleLabel = theme === "light" ? t("themeDark") : t("themeLight");
  return (
    <div className="app-shell" data-theme={theme}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true" />
          <span className="brand__copy">
            <strong>{t("appName")}</strong>
            <small>{t("workspace")}</small>
          </span>
        </div>
        <Navigation />
        <div className="sidebar__footer">
          {me.data && (
            <NavLink className="account-chip" to="/profile">
              <Avatar name={me.data.full_name} imageUrl={me.data.avatar_url} />
              <span>
                <small>{t("signedInAs")}</small>
                <strong>{me.data.full_name}</strong>
              </span>
            </NavLink>
          )}
          <button
            className="theme-button"
            type="button"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            aria-label={toggleLabel}
          >
            {toggleLabel}
          </button>
          <button
            className="theme-button"
            type="button"
            onClick={async () => {
              await api.logout();
              queryClient.setQueryData(["session"], {
                authenticated: false,
                user: null,
              });
              queryClient.removeQueries({
                predicate: (query) => query.queryKey[0] !== "session",
              });
              navigate("/login", { replace: true });
            }}
          >
            {t("logout")}
          </button>
        </div>
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
