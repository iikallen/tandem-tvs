import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type NotificationPreference } from "../../shared/api";
import { t, type TranslationKey } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";

function decodeVapid(value: string) {
  const padded = `${value}${"=".repeat((4 - (value.length % 4)) % 4)}`;
  const binary = atob(padded.replaceAll("-", "+").replaceAll("_", "/"));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

const typeLabels: Record<string, TranslationKey> = {
  NEW_PUBLICATION: "notificationNewPublication",
  ACK_REQUIRED: "notificationAckRequired",
  COMMENT_REPLY: "notificationCommentReply",
  COMMENT_MENTION: "notificationCommentMention",
  NEW_MESSAGE: "notificationNewMessage",
  MESSAGE_MENTION: "notificationMessageMention",
  CHAT_ADDED: "notificationChatAdded",
};

export function NotificationSettingsPage() {
  const queryClient = useQueryClient();
  const [pushState, setPushState] = useState("");
  const settings = useQuery({
    queryKey: ["notification-settings"],
    queryFn: api.notificationSettings,
  });
  const pushConfig = useQuery({
    queryKey: ["push-config"],
    queryFn: api.pushConfig,
  });
  const save = useMutation({
    mutationFn: api.updateNotificationSettings,
    onSuccess: (data) =>
      queryClient.setQueryData(["notification-settings"], data),
  });
  if (settings.isPending) return <PageState kind="loading" />;
  if (settings.isError) return <PageState error={settings.error} />;

  const updatePreference = (
    current: NotificationPreference,
    field: "in_app_enabled" | "push_enabled" | "email_enabled",
    checked: boolean,
  ) => save.mutate({ preferences: [{ ...current, [field]: checked }] });

  const enablePush = async () => {
    if (!pushConfig.data?.enabled || !pushConfig.data.vapid_public_key) return;
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setPushState(t("pushPermissionDenied"));
        return;
      }
      const registration = await navigator.serviceWorker.register("/sw.js");
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: decodeVapid(pushConfig.data.vapid_public_key),
      });
      const json = subscription.toJSON();
      if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth)
        throw new Error();
      await api.savePushSubscription({
        endpoint: json.endpoint,
        p256dh: json.keys.p256dh,
        auth: json.keys.auth,
      });
      setPushState(t("pushEnabled"));
    } catch {
      setPushState(t("pushFailed"));
    }
  };

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <h1>{t("notificationSettings")}</h1>
          <p className="page-description">
            {t("notificationSettingsDescription")}
          </p>
        </div>
      </header>
      <Card>
        <label className="check-row">
          <input
            type="checkbox"
            checked={settings.data.enabled}
            onChange={(event) => save.mutate({ enabled: event.target.checked })}
          />
          <span>{t("notificationsEnabled")}</span>
        </label>
      </Card>
      <div
        className="settings-table"
        role="table"
        aria-label={t("notificationChannels")}
      >
        {settings.data.preferences.map((preference) => (
          <Card className="settings-row" key={preference.notification_type}>
            <strong>{t(typeLabels[preference.notification_type])}</strong>
            {(["in_app_enabled", "push_enabled", "email_enabled"] as const).map(
              (field) => (
                <label key={field} className="check-row">
                  <input
                    type="checkbox"
                    checked={preference[field]}
                    onChange={(event) =>
                      updatePreference(preference, field, event.target.checked)
                    }
                  />
                  <span>
                    {t(
                      field === "in_app_enabled"
                        ? "channelInApp"
                        : field === "push_enabled"
                          ? "channelPush"
                          : "channelEmail",
                    )}
                  </span>
                </label>
              ),
            )}
          </Card>
        ))}
      </div>
      <Card>
        <h2>{t("browserPush")}</h2>
        <p className="page-description">
          {pushConfig.data?.enabled
            ? t("pushDescription")
            : t("pushDisabledByPolicy")}
        </p>
        <button
          className="button button--secondary"
          type="button"
          disabled={!pushConfig.data?.enabled}
          onClick={enablePush}
        >
          {t("enablePush")}
        </button>
        {pushState && <p role="status">{pushState}</p>}
      </Card>
    </div>
  );
}
