import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { ConfirmDialog } from "../../shared/ui/ConfirmDialog";
import { PageState } from "../../shared/ui/PageState";
import { EditorialGuard } from "./EditorialGuard";

export function MediaLibraryPage() {
  return (
    <EditorialGuard>
      <MediaLibrary />
    </EditorialGuard>
  );
}

function MediaLibrary() {
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState("");
  const [deleteId, setDeleteId] = useState<string>();
  const queryClient = useQueryClient();
  const media = useQuery({ queryKey: ["editorial-media"], queryFn: api.media });
  const upload = useMutation({
    mutationFn: api.uploadMedia,
    onSuccess: async () => {
      setMessage(t("fileUploaded"));
      await queryClient.invalidateQueries({ queryKey: ["editorial-media"] });
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteMedia,
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: ["editorial-media"] }),
  });
  if (media.isPending) return <PageState kind="loading" />;
  if (media.isError) return <PageState error={media.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("editorial")}</p>
          <h1>{t("mediaLibrary")}</h1>
          <p className="page-description">{t("mediaDescription")}</p>
        </div>
      </header>
      <Card className="file-upload">
        <input
          ref={input}
          type="file"
          accept=".png,.jpg,.jpeg,.gif,.webp,.mp4,.pdf,.docx,.xlsx"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) upload.mutate(file);
          }}
        />
        <button
          className="button"
          type="button"
          disabled={upload.isPending}
          onClick={() => input.current?.click()}
        >
          {t("chooseFile")}
        </button>
        <span>{t("dropFileHint")}</span>
        {upload.isError && (
          <p className="field-error" role="alert">
            {upload.error.message}
          </p>
        )}
        {message && <p role="status">{message}</p>}
      </Card>
      <div className="media-grid">
        {media.data.results.map((asset) => (
          <Card key={asset.id} className="media-card">
            {asset.kind === "IMAGE" && <img src={asset.content_url} alt="" />}
            {asset.kind === "VIDEO" && (
              <video controls preload="metadata" src={asset.content_url} />
            )}
            <div>
              <strong>{asset.original_name}</strong>
              <p>
                {asset.mime_type} · {formatSize(asset.size)}
              </p>
            </div>
            <div className="button-row">
              <a className="button button--secondary" href={asset.content_url}>
                {t("open")}
              </a>
              <button
                className="button button--danger"
                type="button"
                onClick={() => setDeleteId(asset.id)}
              >
                {t("delete")}
              </button>
            </div>
          </Card>
        ))}
      </div>
      <ConfirmDialog
        open={Boolean(deleteId)}
        title={t("deleteFileQuestion")}
        consequence={t("deleteFileConsequence")}
        confirmLabel={t("delete")}
        busy={remove.isPending}
        onCancel={() => setDeleteId(undefined)}
        onConfirm={() =>
          deleteId &&
          remove.mutate(deleteId, {
            onSuccess: () => setDeleteId(undefined),
          })
        }
      />
    </div>
  );
}

function formatSize(value: number) {
  return value < 1024 * 1024
    ? t("kilobytes", { size: Math.ceil(value / 1024) })
    : t("megabytes", { size: (value / 1024 / 1024).toFixed(1) });
}
