import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  api,
  type EngagementSettings,
  type ReactionType,
} from "../../shared/api";
import { t } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";
import { EditorialGuard } from "./EditorialGuard";

const types: ReactionType[] = [
  "LIKE",
  "CELEBRATE",
  "SUPPORT",
  "INSIGHTFUL",
  "THANKS",
];
const labels: Record<ReactionType, ReturnType<typeof t>> = {
  LIKE: t("reactionLike"),
  CELEBRATE: t("reactionCelebrate"),
  SUPPORT: t("reactionSupport"),
  INSIGHTFUL: t("reactionInsightful"),
  THANKS: t("reactionThanks"),
};

export function EngagementSettingsPage() {
  return (
    <EditorialGuard>
      <SettingsContent />
    </EditorialGuard>
  );
}

function SettingsContent() {
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: ["engagement-settings"],
    queryFn: api.engagementSettings,
  });
  const [changes, setChanges] = useState<Partial<EngagementSettings>>({});
  const [word, setWord] = useState("");
  const form = { ...settings.data, ...changes } as EngagementSettings;
  const setForm = (next: EngagementSettings) => setChanges(next);
  const save = useMutation({
    mutationFn: () => api.updateEngagementSettings(form),
    onSuccess: (data) => {
      setChanges({});
      queryClient.setQueryData(["engagement-settings"], data);
    },
  });
  const addWord = useMutation({
    mutationFn: () => api.createStopWord(word),
    onSuccess: async () => {
      setWord("");
      await queryClient.invalidateQueries({
        queryKey: ["engagement-settings"],
      });
    },
  });
  const toggleWord = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.updateStopWord(id, { is_active: active }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["engagement-settings"] }),
  });
  if (settings.isPending || !form) return <PageState kind="loading" />;
  if (settings.isError) return <PageState error={settings.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("editorialSpace")}</p>
          <h1>{t("engagementSettings")}</h1>
          <p className="page-description">
            {t("engagementSettingsDescription")}
          </p>
        </div>
      </header>
      <Card>
        <h2>{t("discussionSettings")}</h2>
        <div className="settings-grid">
          <NumberField
            label={t("editWindow")}
            value={form.comment_edit_window_minutes}
            onChange={(value) =>
              setForm({ ...form, comment_edit_window_minutes: value })
            }
          />
          <NumberField
            label={t("deleteWindow")}
            value={form.comment_delete_window_minutes}
            onChange={(value) =>
              setForm({ ...form, comment_delete_window_minutes: value })
            }
          />
          <NumberField
            label={t("maxAttachments")}
            value={form.max_comment_attachments}
            onChange={(value) =>
              setForm({ ...form, max_comment_attachments: value })
            }
          />
          <NumberField
            label={t("uploadLimitBytes")}
            value={form.max_comment_attachment_bytes}
            min={1}
            onChange={(value) =>
              setForm({ ...form, max_comment_attachment_bytes: value })
            }
          />
          <NumberField
            label={t("messageRetentionDays")}
            value={form.message_retention_days}
            onChange={(value) =>
              setForm({ ...form, message_retention_days: value })
            }
          />
          <NumberField
            label={t("mediaRetentionDays")}
            value={form.media_retention_days}
            onChange={(value) =>
              setForm({ ...form, media_retention_days: value })
            }
          />
          <label>
            {t("allowedMediaExtensions")}
            <input
              value={form.allowed_media_extensions.join(", ")}
              onChange={(event) =>
                setForm({
                  ...form,
                  allowed_media_extensions: event.target.value
                    .split(",")
                    .map((value) => value.trim().toLowerCase())
                    .filter(Boolean),
                })
              }
            />
          </label>
        </div>
        <h2>{t("reactions")}</h2>
        <div className="settings-checks">
          {types.map((type) => (
            <label className="checkbox-row" key={type}>
              <input
                type="checkbox"
                checked={form.enabled_reaction_types.includes(type)}
                onChange={(event) =>
                  setForm({
                    ...form,
                    enabled_reaction_types: event.target.checked
                      ? [...form.enabled_reaction_types, type]
                      : form.enabled_reaction_types.filter(
                          (item) => item !== type,
                        ),
                  })
                }
              />
              {labels[type]}
            </label>
          ))}
        </div>
        <button
          className="button"
          disabled={save.isPending || !form.enabled_reaction_types.length}
          onClick={() => save.mutate()}
        >
          {t("save")}
        </button>
        {save.isError ? <PageState error={save.error} /> : null}
      </Card>
      <Card>
        <h2>{t("stopWords")}</h2>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (word.trim()) addWord.mutate();
          }}
        >
          <label>
            <span className="sr-only">{t("stopWord")}</span>
            <input
              value={word}
              onChange={(event) => setWord(event.target.value)}
            />
          </label>
          <button
            className="button"
            disabled={!word.trim() || addWord.isPending}
          >
            {t("add")}
          </button>
        </form>
        <div className="chip-list">
          {form.stop_words.map((item) => (
            <button
              className="attachment-chip"
              key={item.id}
              aria-pressed={item.is_active}
              onClick={() =>
                toggleWord.mutate({ id: item.id, active: !item.is_active })
              }
            >
              {item.value}
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

function NumberField({
  label,
  value,
  min = 0,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label>
      {label}
      <input
        type="number"
        min={min}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}
