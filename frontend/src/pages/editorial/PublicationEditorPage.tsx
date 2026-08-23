import { Node } from "@tiptap/core";
import Link from "@tiptap/extension-link";
import { TableKit } from "@tiptap/extension-table";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  ApiError,
  api,
  type Audience,
  type Category,
  type EditorialPublication,
  type Employee,
  type MediaAsset,
  type OrgUnitSummary,
  type PositionGroup,
  type RichTextNode,
  type Tag,
} from "../../shared/api";
import { t } from "../../shared/i18n";
import { PageState } from "../../shared/ui/PageState";
import { RichTextRenderer } from "../../shared/ui/RichTextRenderer";
import { EditorialGuard } from "./EditorialGuard";

const EMPTY_BODY: RichTextNode = {
  type: "doc",
  content: [{ type: "paragraph", content: [] }],
};
type AudienceMode =
  "ALL" | "ORG_UNIT" | "ORG_SUBTREE" | "EMPLOYEE" | "POSITION_GROUP";

const protectedNode = (name: string, tag: "img" | "video" | "a") =>
  Node.create({
    name,
    group: "block",
    atom: true,
    addAttributes: () => ({ asset_id: { default: null } }),
    parseHTML: () => [{ tag: `[data-node=${name}]` }],
    renderHTML: ({ node }) => {
      const id = String(node.attrs.asset_id);
      const common = { "data-node": name, "data-asset-id": id };
      if (tag === "img")
        return [
          "img",
          { ...common, src: `/api/v1/media/${id}/content`, alt: "" },
        ];
      if (tag === "video")
        return [
          "video",
          { ...common, src: `/api/v1/media/${id}/content`, controls: "true" },
        ];
      return [
        "a",
        { ...common, href: `/api/v1/media/${id}/content` },
        "Скачать вложение",
      ];
    },
  });

const AssetImage = protectedNode("assetImage", "img");
const InternalVideo = protectedNode("internalVideo", "video");
const Attachment = protectedNode("attachment", "a");

export function PublicationEditorPage() {
  return (
    <EditorialGuard>
      <PublicationLoader />
    </EditorialGuard>
  );
}

function PublicationLoader() {
  const { publicationId } = useParams();
  const existing = useQuery({
    queryKey: ["editorial-publication", publicationId],
    queryFn: () => api.editorialPublication(publicationId ?? ""),
    enabled: Boolean(publicationId),
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: api.categories,
  });
  const tags = useQuery({ queryKey: ["editorial-tags"], queryFn: api.tags });
  const media = useQuery({ queryKey: ["editorial-media"], queryFn: api.media });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  if (
    (publicationId && existing.isPending) ||
    categories.isPending ||
    tags.isPending ||
    media.isPending ||
    me.isPending
  )
    return <PageState kind="loading" />;
  if (existing.isError) return <PageState error={existing.error} />;
  if (categories.isError) return <PageState error={categories.error} />;
  if (tags.isError) return <PageState error={tags.error} />;
  if (media.isError) return <PageState error={media.error} />;
  if (me.isError) return <PageState error={me.error} />;
  return (
    <PublicationForm
      key={existing.data?.id ?? "new"}
      initial={existing.data}
      categories={categories.data}
      tags={Array.isArray(tags.data) ? tags.data : []}
      media={Array.isArray(media.data?.results) ? media.data.results : []}
      canPublish={me.data.module_roles.some((role) =>
        ["editor", "admin", "administrator"].includes(role),
      )}
    />
  );
}

function initialAudience(publication?: EditorialPublication): Audience {
  return (
    publication?.audience ?? {
      everyone: false,
      org_units: [],
      org_unit_subtrees: [],
      employees: [],
      module_roles: [],
      position_groups: [],
    }
  );
}

function PublicationForm({
  initial,
  categories,
  tags,
  media,
  canPublish,
}: {
  initial?: EditorialPublication;
  categories: Category[];
  tags: Tag[];
  media: MediaAsset[];
  canPublish: boolean;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const initialTargets = initialAudience(initial);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [summary, setSummary] = useState(initial?.summary ?? "");
  const [category, setCategory] = useState(
    initial?.category ?? categories[0]?.slug ?? "",
  );
  const [selectedTags, setSelectedTags] = useState(initial?.tags ?? []);
  const [cover, setCover] = useState(initial?.cover ?? "");
  const [attachments, setAttachments] = useState(
    initial?.media
      ?.filter((usage) => usage.purpose === "ATTACHMENT")
      .map((usage) => usage.asset.id) ?? [],
  );
  const [scheduledFor, setScheduledFor] = useState(
    toLocalInput(initial?.scheduled_for),
  );
  const [expiresAt, setExpiresAt] = useState(toLocalInput(initial?.expires_at));
  const [body, setBody] = useState<RichTextNode>(initial?.body ?? EMPTY_BODY);
  const [audienceMode, setAudienceMode] = useState<AudienceMode>(
    initialTargets.everyone
      ? "ALL"
      : initialTargets.employees.length
        ? "EMPLOYEE"
        : initialTargets.position_groups?.length
          ? "POSITION_GROUP"
          : initialTargets.org_unit_subtrees?.length
            ? "ORG_SUBTREE"
            : "ORG_UNIT",
  );
  const [audience, setAudience] = useState<Audience>(initialTargets);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveState, setSaveState] = useState(
    initial ? "Сохранено" : "Новый черновик",
  );
  const [revision, setRevision] = useState(initial?.edit_revision ?? 0);
  const revisionRef = useRef(initial?.edit_revision ?? 0);
  const [conflict, setConflict] = useState<ApiError>();
  const [error, setError] = useState<unknown>();
  const firstAutosave = useRef(true);
  const busy = useRef(false);
  const editable = initial?.status !== "ARCHIVED";
  const units = useQuery({ queryKey: ["org-units"], queryFn: api.orgUnits });
  const groups = useQuery({
    queryKey: ["position-groups"],
    queryFn: api.positionGroups,
  });
  const employees = useQuery({
    queryKey: ["employees", employeeSearch],
    queryFn: () => api.employees(employeeSearch),
    enabled: audienceMode === "EMPLOYEE" && employeeSearch.trim().length >= 2,
  });
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
        code: false,
        codeBlock: false,
        horizontalRule: false,
        strike: false,
        underline: false,
        link: false,
      }),
      Link.configure({ openOnClick: false, autolink: false }),
      TableKit.configure({ table: { resizable: false } }),
      AssetImage,
      InternalVideo,
      Attachment,
    ],
    content: initial?.body ?? EMPTY_BODY,
    editable,
    editorProps: {
      attributes: { "aria-label": t("publicationText"), role: "textbox" },
    },
    onUpdate: ({ editor: current }) =>
      setBody(current.getJSON() as RichTextNode),
  });

  const draft = useMemo(
    () => ({
      title,
      summary,
      category,
      tags: selectedTags,
      cover: cover || null,
      attachments,
      body,
      audience,
    }),
    [
      title,
      summary,
      category,
      selectedTags,
      cover,
      attachments,
      body,
      audience,
    ],
  );

  useEffect(() => {
    if (!initial || !editable) return;
    if (firstAutosave.current) {
      firstAutosave.current = false;
      return;
    }
    setSaveState("Есть несохранённые изменения");
    const timer = window.setTimeout(async () => {
      if (busy.current) return;
      busy.current = true;
      setSaveState("Автосохранение…");
      try {
        const saved = await api.updatePublication(initial.id, {
          ...draft,
          expected_revision: revisionRef.current,
          autosave: true,
        });
        const nextRevision = saved.edit_revision ?? revisionRef.current + 1;
        revisionRef.current = nextRevision;
        setRevision(nextRevision);
        setSaveState("Автосохранено");
        setConflict(undefined);
      } catch (caught) {
        if (caught instanceof ApiError && caught.code === "stale_revision")
          setConflict(caught);
        else setError(caught);
        setSaveState("Не сохранено");
      } finally {
        busy.current = false;
      }
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [draft, editable, initial]);

  async function save(action?: "publish" | "submit-review") {
    setSaving(true);
    setError(undefined);
    try {
      let publication = initial
        ? await api.updatePublication(initial.id, {
            ...draft,
            expected_revision: revisionRef.current,
            autosave: false,
          })
        : await api.createPublication(draft);
      const nextRevision = publication.edit_revision ?? revisionRef.current + 1;
      revisionRef.current = nextRevision;
      setRevision(nextRevision);
      if (action)
        publication = await api.transitionPublication(publication.id, action, {
          expected_revision: publication.edit_revision,
        });
      await queryClient.invalidateQueries({ queryKey: ["editorial"] });
      await queryClient.invalidateQueries({ queryKey: ["news"] });
      if (!initial || action) navigate("/editorial/publications");
      else setSaveState("Сохранено вручную");
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "stale_revision")
        setConflict(caught);
      else setError(caught);
    } finally {
      setSaving(false);
    }
  }

  async function schedule() {
    if (!initial || !scheduledFor) return;
    setSaving(true);
    setError(undefined);
    try {
      const saved = await api.updatePublication(initial.id, {
        ...draft,
        expected_revision: revisionRef.current,
        autosave: false,
      });
      await api.transitionPublication(initial.id, "schedule", {
        expected_revision: saved.edit_revision,
        scheduled_for: new Date(scheduledFor).toISOString(),
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      });
      await queryClient.invalidateQueries({ queryKey: ["editorial"] });
      navigate("/editorial/publications");
    } catch (caught) {
      setError(caught);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("editorialSpace")}</p>
          <h1>{initial ? t("editPublication") : t("newPublication")}</h1>
          <p className="page-description" role="status">
            {saveState} · rev. {revision}
          </p>
        </div>
      </header>
      {error ? <PageState error={error} /> : null}
      {conflict && (
        <div className="conflict-alert" role="alert">
          <strong>Конфликт изменений</strong>
          <p>
            На сервере уже revision {conflict.currentRevision}. Скопируйте
            нужный текст для сравнения или загрузите актуальную версию.
          </p>
          <button
            className="button"
            type="button"
            onClick={() => window.location.reload()}
          >
            Загрузить серверную версию
          </button>
        </div>
      )}
      <form
        className="editor-form"
        onSubmit={(event) => event.preventDefault()}
      >
        <div className="editor-main">
          <label>
            {t("title")}
            <input
              required
              maxLength={255}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={!editable}
            />
          </label>
          <label>
            {t("summary")}
            <textarea
              required
              maxLength={1000}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              disabled={!editable}
            />
          </label>
          <div className="editor-field">
            <span className="field-label">{t("publicationText")}</span>
            {editable && <EditorToolbar editor={editor} media={media} />}
            <EditorContent editor={editor} className="tiptap-editor" />
          </div>
        </div>
        <aside className="editor-sidebar">
          <label>
            {t("category")}
            <select
              required
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              disabled={!editable}
            >
              <option value="">{t("choose")}</option>
              {categories.map((item) => (
                <option key={item.slug} value={item.slug}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Теги
            <select
              multiple
              value={selectedTags}
              onChange={(event) =>
                setSelectedTags(
                  Array.from(
                    event.target.selectedOptions,
                    (option) => option.value,
                  ),
                )
              }
              disabled={!editable}
            >
              {tags
                .filter((tag) => tag.is_active)
                .map((tag) => (
                  <option key={tag.slug} value={tag.slug}>
                    {tag.name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Обложка
            <select
              value={cover ?? ""}
              onChange={(event) => setCover(event.target.value)}
              disabled={!editable}
            >
              <option value="">Без обложки</option>
              {media
                .filter((asset) => asset.kind === "IMAGE")
                .map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.original_name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Вложения
            <select
              multiple
              value={attachments}
              onChange={(event) =>
                setAttachments(
                  Array.from(
                    event.target.selectedOptions,
                    (option) => option.value,
                  ),
                )
              }
              disabled={!editable}
            >
              {media.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.original_name}
                </option>
              ))}
            </select>
          </label>
          {canPublish && (
            <>
              <label>
                Дата публикации
                <input
                  type="datetime-local"
                  value={scheduledFor}
                  min={toLocalInput(new Date().toISOString())}
                  onChange={(event) => setScheduledFor(event.target.value)}
                  disabled={!editable}
                />
              </label>
              <label>
                Снять после
                <input
                  type="datetime-local"
                  value={expiresAt}
                  onChange={(event) => setExpiresAt(event.target.value)}
                  disabled={!editable}
                />
              </label>
            </>
          )}
          <AudienceFields
            mode={audienceMode}
            setMode={setAudienceMode}
            audience={audience}
            setAudience={setAudience}
            units={units.data ?? []}
            groups={groups.data ?? []}
            employees={employees.data ?? []}
            employeeSearch={employeeSearch}
            setEmployeeSearch={setEmployeeSearch}
            disabled={!editable}
          />
          <button
            className="button button--secondary"
            type="button"
            onClick={() => setPreview(!preview)}
          >
            {preview ? t("hidePreview") : t("preview")}
          </button>
          {editable && (
            <>
              <button
                className="button button--secondary"
                type="button"
                disabled={saving}
                onClick={() => save()}
              >
                Сохранить
              </button>
              {(!initial || initial.status === "DRAFT") && (
                <button
                  className="button button--secondary"
                  type="button"
                  disabled={saving}
                  onClick={() => save("submit-review")}
                >
                  На согласование
                </button>
              )}
              {canPublish && scheduledFor && initial && (
                <button
                  className="button button--secondary"
                  type="button"
                  disabled={saving}
                  onClick={schedule}
                >
                  {initial.status === "SCHEDULED"
                    ? "Перенести публикацию"
                    : "Запланировать"}
                </button>
              )}
              {canPublish && (
                <button
                  className="button"
                  type="button"
                  disabled={saving}
                  onClick={() => save("publish")}
                >
                  Опубликовать
                </button>
              )}
            </>
          )}
        </aside>
      </form>
      {preview && (
        <section className="preview">
          <h2>{t("preview")}</h2>
          <h1>{title || t("untitled")}</h1>
          <p className="page-description">{summary}</p>
          <RichTextRenderer document={body} />
        </section>
      )}
    </div>
  );
}

function toLocalInput(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

function AudienceFields({
  mode,
  setMode,
  audience,
  setAudience,
  units,
  groups,
  employees,
  employeeSearch,
  setEmployeeSearch,
  disabled,
}: {
  mode: AudienceMode;
  setMode: (mode: AudienceMode) => void;
  audience: Audience;
  setAudience: (update: Audience | ((current: Audience) => Audience)) => void;
  units: OrgUnitSummary[];
  groups: PositionGroup[];
  employees: Employee[];
  employeeSearch: string;
  setEmployeeSearch: (value: string) => void;
  disabled: boolean;
}) {
  const values =
    mode === "ORG_SUBTREE"
      ? (audience.org_unit_subtrees ?? [])
      : audience.org_units;
  return (
    <>
      <label>
        {t("audience")}
        <select
          value={mode}
          disabled={disabled}
          onChange={(event) => {
            const next = event.target.value as AudienceMode;
            setMode(next);
            setAudience((current: Audience) =>
              next === "ALL"
                ? {
                    everyone: true,
                    org_units: [],
                    org_unit_subtrees: [],
                    employees: [],
                    module_roles: [],
                    position_groups: [],
                  }
                : { ...current, everyone: false },
            );
          }}
        >
          <option value="ORG_UNIT">Подразделение — точно</option>
          <option value="ORG_SUBTREE">Подразделение и дочерние</option>
          <option value="EMPLOYEE">Поимённо</option>
          <option value="POSITION_GROUP">Должностная группа</option>
          <option value="ALL">{t("audienceAll")}</option>
        </select>
      </label>
      {(mode === "ORG_UNIT" || mode === "ORG_SUBTREE") && (
        <label>
          Подразделения
          <select
            multiple
            value={values}
            disabled={disabled}
            onChange={(event) => {
              const selected = Array.from(
                event.target.selectedOptions,
                (option) => option.value,
              );
              setAudience((current: Audience) => ({
                ...current,
                [mode === "ORG_SUBTREE" ? "org_unit_subtrees" : "org_units"]:
                  selected,
              }));
            }}
          >
            {units.map((unit) => (
              <option key={unit.external_id} value={unit.external_id}>
                {unit.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {mode === "EMPLOYEE" && (
        <>
          <label>
            {t("employeeSearch")}
            <input
              value={employeeSearch}
              disabled={disabled}
              onChange={(event) => setEmployeeSearch(event.target.value)}
            />
          </label>
          <label>
            {t("audienceEmployee")}
            <select
              multiple
              value={audience.employees}
              disabled={disabled}
              onChange={(event) =>
                setAudience((current: Audience) => ({
                  ...current,
                  employees: Array.from(
                    event.target.selectedOptions,
                    (option) => option.value,
                  ),
                }))
              }
            >
              {employees.map((employee) => (
                <option key={employee.portal_id} value={employee.portal_id}>
                  {employee.full_name}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {mode === "POSITION_GROUP" && (
        <label>
          Должностные группы
          <select
            multiple
            value={(audience.position_groups ?? []).map(
              (group) => group.external_id,
            )}
            disabled={disabled}
            onChange={(event) => {
              const ids = new Set(
                Array.from(
                  event.target.selectedOptions,
                  (option) => option.value,
                ),
              );
              setAudience((current: Audience) => ({
                ...current,
                position_groups: groups.filter((group) =>
                  ids.has(group.external_id),
                ),
              }));
            }}
          >
            {groups.map((group) => (
              <option key={group.external_id} value={group.external_id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
      )}
    </>
  );
}

function EditorToolbar({
  editor,
  media,
}: {
  editor: ReturnType<typeof useEditor>;
  media: MediaAsset[];
}) {
  if (!editor) return null;
  const insert = (kind: "assetImage" | "internalVideo" | "attachment") => {
    const candidates = media.filter((asset) =>
      kind === "assetImage"
        ? asset.kind === "IMAGE"
        : kind === "internalVideo"
          ? asset.kind === "VIDEO"
          : true,
    );
    const id = window.prompt("Asset ID", candidates[0]?.id ?? "");
    if (id && candidates.some((asset) => asset.id === id))
      editor
        .chain()
        .focus()
        .insertContent({ type: kind, attrs: { asset_id: id } })
        .run();
  };
  const buttons: Array<[string, () => void]> = [
    [t("paragraph"), () => editor.chain().focus().setParagraph().run()],
    ["H2", () => editor.chain().focus().toggleHeading({ level: 2 }).run()],
    ["H3", () => editor.chain().focus().toggleHeading({ level: 3 }).run()],
    [t("bold"), () => editor.chain().focus().toggleBold().run()],
    [t("italic"), () => editor.chain().focus().toggleItalic().run()],
    [t("bulletList"), () => editor.chain().focus().toggleBulletList().run()],
    [t("orderedList"), () => editor.chain().focus().toggleOrderedList().run()],
    [t("quote"), () => editor.chain().focus().toggleBlockquote().run()],
    [
      "Таблица",
      () =>
        editor
          .chain()
          .focus()
          .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
          .run(),
    ],
    ["Изображение", () => insert("assetImage")],
    ["Видео", () => insert("internalVideo")],
    ["Файл", () => insert("attachment")],
  ];
  return (
    <div
      className="editor-toolbar"
      role="toolbar"
      aria-label={t("textFormatting")}
    >
      {buttons.map(([label, action]) => (
        <button key={label} type="button" onClick={action}>
          {label}
        </button>
      ))}
    </div>
  );
}
