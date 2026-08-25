import {
  useEffect,
  useState,
  type ComponentType,
  type FormEvent,
  type SVGProps,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "../api";
import { t } from "../i18n";
import { Avatar } from "./Avatar";
import {
  EditIcon,
  BellIcon,
  HomeIcon,
  MessageIcon,
  NewsIcon,
  SearchIcon,
  UserIcon,
  UsersIcon,
} from "./icons";

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
  icon: MessageIcon,
};
const platformLink: NavItem = {
  to: "/platform/users",
  label: t("userManagement"),
  icon: UsersIcon,
};
const auditLink: NavItem = {
  to: "/editorial/audit",
  label: t("auditLog"),
  icon: EditIcon,
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
  const isNewsAdmin = me.data?.access.news.includes("ADMIN");
  const allowedEditorialLinks = [
    ...editorialLinks,
    ...(isNewsAdmin ? [auditLink] : []),
  ];
  const expandedPortalLinks = [
    ...portalLinks,
    ...(canMessage ? [messengerLink] : []),
    ...(isPlatformAdmin ? [platformLink] : []),
  ];
  const mobileLinks = [
    ...portalLinks.slice(0, 3),
    ...(canMessage
      ? [messengerLink]
      : canEdit
        ? [editorialLinks[0]]
        : [portalLinks[3]]),
    portalLinks[4],
  ];
  const groups = mobile
    ? [{ label: "", links: mobileLinks }]
    : [
        { label: t("portalSection"), links: expandedPortalLinks },
        ...(canEdit
          ? [{ label: t("editorialSection"), links: allowedEditorialLinks }]
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
  const [search, setSearch] = useState("");
  const unread = useQuery({
    queryKey: ["notification-count"],
    queryFn: api.unreadNotificationCount,
    refetchInterval: 30_000,
  });
  const toggleLabel = theme === "light" ? t("themeDark") : t("themeLight");

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | undefined;
    let timer = 0;
    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notification-count"] });
    };
    const connect = async () => {
      try {
        const { ticket } = await api.notificationRealtimeTicket();
        if (stopped) return;
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(
          `${protocol}//${window.location.host}/ws/v1/notifications?ticket=${encodeURIComponent(ticket)}`,
        );
        socket.onopen = refresh;
        socket.onmessage = refresh;
        socket.onclose = (event) => {
          if (!stopped && event.code !== 4403)
            timer = window.setTimeout(connect, 3_000);
        };
        socket.onerror = () => socket?.close();
      } catch {
        if (!stopped) timer = window.setTimeout(connect, 5_000);
      }
    };
    void connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close(1000, "page left");
    };
  }, [queryClient]);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const query = search.trim();
    if (query) navigate(`/search?q=${encodeURIComponent(query)}`);
  };
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
        <div className="portal-toolbar">
          <form className="portal-search" role="search" onSubmit={submitSearch}>
            <SearchIcon aria-hidden="true" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("globalSearchPlaceholder")}
              aria-label={t("globalSearch")}
            />
          </form>
          <NavLink
            className="notification-bell"
            to="/notifications"
            aria-label={t("notifications")}
          >
            <BellIcon aria-hidden="true" />
            {!!unread.data?.unread_count && (
              <span
                aria-label={t("unreadNotificationCount", {
                  count: unread.data.unread_count,
                })}
              >
                {Math.min(unread.data.unread_count, 99)}
              </span>
            )}
          </NavLink>
        </div>
        <div className="page">
          <Outlet />
        </div>
      </main>
      <Navigation mobile />
    </div>
  );
}
