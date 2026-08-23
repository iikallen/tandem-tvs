import Link from "@tiptap/extension-link";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  api,
  type Audience,
  type Category,
  type EditorialPublication,
  type RichTextNode,
} from "../../shared/api";
import { t } from "../../shared/i18n";
import { PageState } from "../../shared/ui/PageState";
import { RichTextRenderer } from "../../shared/ui/RichTextRenderer";
import { EditorialGuard } from "./EditorialGuard";

const EMPTY_BODY: RichTextNode = {
  type: "doc",
  content: [{ type: "paragraph", content: [] }],
};
type AudienceMode = "ALL" | "ORG_UNIT" | "EMPLOYEE" | "MODULE_ROLE";

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
    queryKey: ["editorial", publicationId],
    queryFn: () => api.editorialPublication(publicationId ?? ""),
    enabled: Boolean(publicationId),
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: api.categories,
  });
  if ((publicationId && existing.isPending) || categories.isPending)
    return <PageState kind="loading" />;
  if (existing.isError) return <PageState error={existing.error} />;
  if (categories.isError) return <PageState error={categories.error} />;
  return (
    <PublicationForm
      key={existing.data?.updated_at ?? "new"}
      initial={existing.data}
      categories={categories.data}
    />
  );
}

function initialAudience(publication?: EditorialPublication): Audience {
  return (
    publication?.audience ?? {
      everyone: false,
      org_units: [],
      employees: [],
      module_roles: [],
    }
  );
}

function PublicationForm({
  initial,
  categories,
}: {
  initial?: EditorialPublication;
  categories: Category[];
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const initialTargets = initialAudience(initial);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [summary, setSummary] = useState(initial?.summary ?? "");
  const [category, setCategory] = useState(
    initial?.category ?? categories[0]?.slug ?? "",
  );
  const [body, setBody] = useState<RichTextNode>(initial?.body ?? EMPTY_BODY);
  const [audienceMode, setAudienceMode] = useState<AudienceMode>(
    initialTargets.everyone
      ? "ALL"
      : initialTargets.employees.length
        ? "EMPLOYEE"
        : initialTargets.module_roles.length
          ? "MODULE_ROLE"
          : "ORG_UNIT",
  );
  const [audience, setAudience] = useState<Audience>(initialTargets);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>();
  const isPublished = initial?.status === "PUBLISHED";
  const units = useQuery({ queryKey: ["org-units"], queryFn: api.orgUnits });
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
    ],
    content: initial?.body ?? EMPTY_BODY,
    editable: !isPublished,
    editorProps: {
      attributes: { "aria-label": t("publicationText"), role: "textbox" },
    },
    onUpdate: ({ editor: current }) =>
      setBody(current.getJSON() as RichTextNode),
  });

  async function save(publish: boolean) {
    setSaving(true);
    setError(undefined);
    try {
      const payload = { title, summary, category, body, audience };
      const publication = initial
        ? await api.updatePublication(initial.id, payload)
        : await api.createPublication(payload);
      if (publish) await api.publishPublication(publication.id);
      await queryClient.invalidateQueries({ queryKey: ["editorial"] });
      await queryClient.invalidateQueries({ queryKey: ["news"] });
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
        </div>
      </header>
      {error ? <PageState error={error} /> : null}
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
              disabled={isPublished}
            />
          </label>
          <label>
            {t("summary")}
            <textarea
              required
              maxLength={1000}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              disabled={isPublished}
            />
          </label>
          <div className="editor-field">
            <span className="field-label">{t("publicationText")}</span>
            {!isPublished && <EditorToolbar editor={editor} />}
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
              disabled={isPublished}
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
            {t("audience")}
            <select
              value={audienceMode}
              onChange={(event) => {
                const mode = event.target.value as AudienceMode;
                setAudienceMode(mode);
                setAudience((current) =>
                  mode === "ALL"
                    ? {
                        everyone: true,
                        org_units: [],
                        employees: [],
                        module_roles: [],
                      }
                    : { ...current, everyone: false },
                );
              }}
              disabled={isPublished}
            >
              <option value="ORG_UNIT">{t("audienceOrgUnit")}</option>
              <option value="EMPLOYEE">{t("audienceEmployee")}</option>
              <option value="MODULE_ROLE">{t("audienceRole")}</option>
              <option value="ALL">{t("audienceAll")}</option>
            </select>
          </label>
          {audienceMode === "ORG_UNIT" && (
            <label>
              {t("audienceOrgUnit")}
              <select
                multiple
                size={Math.min(5, Math.max(2, units.data?.length ?? 2))}
                value={audience.org_units}
                onChange={(event) =>
                  setAudience((current) => ({
                    ...current,
                    org_units: Array.from(
                      event.target.selectedOptions,
                      (option) => option.value,
                    ),
                  }))
                }
                disabled={isPublished}
              >
                {units.data?.map((unit) => (
                  <option key={unit.external_id} value={unit.external_id}>
                    {unit.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {audienceMode === "EMPLOYEE" && (
            <>
              <label>
                {t("employeeSearch")}
                <input
                  value={employeeSearch}
                  onChange={(event) => setEmployeeSearch(event.target.value)}
                  placeholder={t("employeeSearchHint")}
                  disabled={isPublished}
                />
              </label>
              <label>
                {t("audienceEmployee")}
                <select
                  multiple
                  size={Math.min(5, Math.max(2, employees.data?.length ?? 2))}
                  value={audience.employees}
                  onChange={(event) =>
                    setAudience((current) => ({
                      ...current,
                      employees: Array.from(
                        event.target.selectedOptions,
                        (option) => option.value,
                      ),
                    }))
                  }
                  disabled={isPublished}
                >
                  {employees.data?.map((employee) => (
                    <option key={employee.portal_id} value={employee.portal_id}>
                      {employee.full_name}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          {audienceMode === "MODULE_ROLE" && (
            <label>
              {t("audienceRole")}
              <input
                value={audience.module_roles.join(", ")}
                onChange={(event) =>
                  setAudience((current) => ({
                    ...current,
                    module_roles: event.target.value
                      .split(",")
                      .map((role) => role.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="editor"
                disabled={isPublished}
              />
            </label>
          )}
          <p className="selected-targets">
            {t("selectedTargets", {
              count: audience.everyone
                ? 1
                : audience.org_units.length +
                  audience.employees.length +
                  audience.module_roles.length,
            })}
          </p>
          <button
            className="button button--secondary"
            type="button"
            onClick={() => setPreview(!preview)}
          >
            {preview ? t("hidePreview") : t("preview")}
          </button>
          {!isPublished && (
            <>
              <button
                className="button button--secondary"
                type="button"
                disabled={saving}
                onClick={() => save(false)}
              >
                {t("saveDraft")}
              </button>
              <button
                className="button"
                type="button"
                disabled={saving}
                onClick={() => save(true)}
              >
                {t("publish")}
              </button>
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

function EditorToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null;
  const link = () => {
    const href = window.prompt(
      t("linkAddress"),
      editor.getAttributes("link").href as string,
    );
    if (href === null) return;
    if (!href) editor.chain().focus().unsetLink().run();
    else editor.chain().focus().setLink({ href }).run();
  };
  const buttons = [
    [t("paragraph"), () => editor.chain().focus().setParagraph().run()],
    ["H2", () => editor.chain().focus().toggleHeading({ level: 2 }).run()],
    ["H3", () => editor.chain().focus().toggleHeading({ level: 3 }).run()],
    [t("bold"), () => editor.chain().focus().toggleBold().run()],
    [t("italic"), () => editor.chain().focus().toggleItalic().run()],
    [t("bulletList"), () => editor.chain().focus().toggleBulletList().run()],
    [t("orderedList"), () => editor.chain().focus().toggleOrderedList().run()],
    [t("quote"), () => editor.chain().focus().toggleBlockquote().run()],
    [t("link"), link],
  ] as const;
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
