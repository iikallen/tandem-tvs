import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../shared/api";
import { t } from "../../shared/i18n";

function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand">
          <span className="brand__mark" aria-hidden="true" />
          <strong>{t("appName")}</strong>
        </div>
        {children}
      </section>
    </main>
  );
}

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: ({ user }) => {
      queryClient.setQueryData(["session"], { authenticated: true, user });
      queryClient.setQueryData(["me"], user);
      navigate("/news", { replace: true });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate();
  };
  return (
    <AuthFrame>
      <header>
        <p className="overline">{t("localAccount")}</p>
        <h1>{t("signIn")}</h1>
        <p>{t("signInDescription")}</p>
      </header>
      <form className="auth-form" onSubmit={submit}>
        <label>
          {t("username")}
          <input
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
            autoFocus
          />
        </label>
        <label>
          {t("password")}
          <span className="password-field">
            <input
              type={visible ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <button type="button" onClick={() => setVisible(!visible)}>
              {visible ? t("hidePassword") : t("showPassword")}
            </button>
          </span>
        </label>
        {login.isError && (
          <p className="form-error" role="alert">
            {t("invalidCredentials")}
          </p>
        )}
        <button className="button button--primary" disabled={login.isPending}>
          {login.isPending ? t("signingIn") : t("signIn")}
        </button>
      </form>
      <Link to="/forgot-password">{t("forgotPassword")}</Link>
    </AuthFrame>
  );
}

function PasswordPairForm({
  title,
  description,
  submitLabel,
  submit,
}: {
  title: string;
  description: string;
  submitLabel: string;
  submit: (password: string, confirm: string) => Promise<unknown>;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mutation = useMutation({ mutationFn: () => submit(password, confirm) });
  return (
    <AuthFrame>
      <header>
        <h1>{title}</h1>
        <p>{description}</p>
      </header>
      <form
        className="auth-form"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <label>
          {t("newPassword")}
          <input
            type="password"
            autoComplete="new-password"
            minLength={15}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        <label>
          {t("confirmPassword")}
          <input
            type="password"
            autoComplete="new-password"
            minLength={15}
            maxLength={128}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            required
          />
        </label>
        <p className="field-hint">{t("passwordPolicy")}</p>
        {mutation.isError && (
          <p className="form-error" role="alert">
            {t("tokenInvalid")}
          </p>
        )}
        {mutation.isSuccess ? (
          <p role="status">{t("passwordSaved")}</p>
        ) : (
          <button
            className="button button--primary"
            disabled={mutation.isPending}
          >
            {submitLabel}
          </button>
        )}
      </form>
      <Link to="/login">{t("backToLogin")}</Link>
    </AuthFrame>
  );
}

export function ActivatePage() {
  const [params] = useSearchParams();
  return (
    <PasswordPairForm
      title={t("activateAccount")}
      description={t("activateDescription")}
      submitLabel={t("activateAccount")}
      submit={(password, confirm) =>
        api.activate(params.get("token") ?? "", password, confirm)
      }
    />
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  return (
    <PasswordPairForm
      title={t("resetPassword")}
      description={t("resetDescription")}
      submitLabel={t("savePassword")}
      submit={(password, confirm) =>
        api.resetPassword(params.get("token") ?? "", password, confirm)
      }
    />
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const mutation = useMutation({
    mutationFn: () => api.requestPasswordReset(email),
  });
  return (
    <AuthFrame>
      <header>
        <h1>{t("forgotPassword")}</h1>
        <p>{t("forgotDescription")}</p>
      </header>
      <form
        className="auth-form"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <label>
          {t("email")}
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        {mutation.isSuccess ? (
          <p role="status">{t("resetRequested")}</p>
        ) : (
          <button
            className="button button--primary"
            disabled={mutation.isPending}
          >
            {t("requestReset")}
          </button>
        )}
      </form>
      <Link to="/login">{t("backToLogin")}</Link>
    </AuthFrame>
  );
}

export function PasswordChangePage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const mutation = useMutation({
    mutationFn: () => api.changePassword(current, next),
  });
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("security")}</p>
          <h1>{t("changePassword")}</h1>
          <p>{t("passwordPolicy")}</p>
        </div>
      </header>
      <form
        className="card auth-form narrow-form"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <label>
          {t("currentPassword")}
          <input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            required
          />
        </label>
        <label>
          {t("newPassword")}
          <input
            type="password"
            autoComplete="new-password"
            minLength={15}
            maxLength={128}
            value={next}
            onChange={(event) => setNext(event.target.value)}
            required
          />
        </label>
        {mutation.isError && (
          <p className="form-error" role="alert">
            {t("passwordChangeFailed")}
          </p>
        )}
        {mutation.isSuccess && <p role="status">{t("passwordSaved")}</p>}
        <button
          className="button button--primary"
          disabled={mutation.isPending}
        >
          {t("savePassword")}
        </button>
      </form>
    </div>
  );
}
