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

function initialAudience(publication?: EditorialPublication): {
  mode: AudienceMode;
  target: string;
} {
  const audience = publication?.audience;
  if (!audience || audience.everyone) return { mode: "ALL", target: "" };
  if (audience.org_units[0])
    return { mode: "ORG_UNIT", target: audience.org_units[0] };
  if (audience.employees[0])
    return { mode: "EMPLOYEE", target: audience.employees[0] };
  return { mode: "MODULE_ROLE", target: audience.module_roles[0] ?? "" };
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
  const initialTarget = initialAudience(initial);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [summary, setSummary] = useState(initial?.summary ?? "");
  const [category, setCategory] = useState(
    initial?.category ?? categories[0]?.slug ?? "",
  );
  const [body, setBody] = useState<RichTextNode>(initial?.body ?? EMPTY_BODY);
  const [audienceMode, setAudienceMode] = useState<AudienceMode>(
    initialTarget.mode,
  );
  const [audienceTarget, setAudienceTarget] = useState(initialTarget.target);
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
      attributes: { "aria-label": "Текст публикации", role: "textbox" },
    },
    onUpdate: ({ editor: current }) =>
      setBody(current.getJSON() as RichTextNode),
  });

  function audience(): Audience {
    return {
      everyone: audienceMode === "ALL",
      org_units:
        audienceMode === "ORG_UNIT" && audienceTarget ? [audienceTarget] : [],
      employees:
        audienceMode === "EMPLOYEE" && audienceTarget ? [audienceTarget] : [],
      module_roles:
        audienceMode === "MODULE_ROLE" && audienceTarget
          ? [audienceTarget]
          : [],
    };
  }

  async function save(publish: boolean) {
    setSaving(true);
    setError(undefined);
    try {
      const payload = { title, summary, category, body, audience: audience() };
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
          <p className="overline">Редакционное пространство</p>
          <h1>{initial ? "Редактирование публикации" : "Новая публикация"}</h1>
        </div>
      </header>
      {error ? <PageState error={error} /> : null}
      <form
        className="editor-form"
        onSubmit={(event) => event.preventDefault()}
      >
        <div className="editor-main">
          <label>
            Заголовок
            <input
              required
              maxLength={255}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={isPublished}
            />
          </label>
          <label>
            Краткое описание
            <textarea
              required
              maxLength={1000}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              disabled={isPublished}
            />
          </label>
          <div className="editor-field">
            <span className="field-label">Текст публикации</span>
            {!isPublished && <EditorToolbar editor={editor} />}
            <EditorContent editor={editor} className="tiptap-editor" />
          </div>
        </div>
        <aside className="editor-sidebar">
          <label>
            Категория
            <select
              required
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              disabled={isPublished}
            >
              <option value="">Выберите</option>
              {categories.map((item) => (
                <option key={item.slug} value={item.slug}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Аудитория
            <select
              value={audienceMode}
              onChange={(event) => {
                setAudienceMode(event.target.value as AudienceMode);
                setAudienceTarget("");
              }}
              disabled={isPublished}
            >
              <option value="ALL">Вся компания</option>
              <option value="ORG_UNIT">Подразделение</option>
              <option value="EMPLOYEE">Сотрудник</option>
              <option value="MODULE_ROLE">Роль модуля</option>
            </select>
          </label>
          {audienceMode === "ORG_UNIT" && (
            <label>
              Подразделение
              <select
                value={audienceTarget}
                onChange={(event) => setAudienceTarget(event.target.value)}
                disabled={isPublished}
              >
                <option value="">Выберите</option>
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
                Поиск сотрудника
                <input
                  value={employeeSearch}
                  onChange={(event) => setEmployeeSearch(event.target.value)}
                  placeholder="Введите минимум 2 символа"
                  disabled={isPublished}
                />
              </label>
              <label>
                Сотрудник
                <select
                  value={audienceTarget}
                  onChange={(event) => setAudienceTarget(event.target.value)}
                  disabled={isPublished}
                >
                  <option value="">Выберите</option>
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
              Роль модуля
              <input
                value={audienceTarget}
                onChange={(event) => setAudienceTarget(event.target.value)}
                placeholder="editor"
                disabled={isPublished}
              />
            </label>
          )}
          <button
            className="button button--secondary"
            type="button"
            onClick={() => setPreview(!preview)}
          >
            {preview ? "Скрыть предпросмотр" : "Предпросмотр"}
          </button>
          {!isPublished && (
            <>
              <button
                className="button button--secondary"
                type="button"
                disabled={saving}
                onClick={() => save(false)}
              >
                Сохранить черновик
              </button>
              <button
                className="button"
                type="button"
                disabled={saving}
                onClick={() => save(true)}
              >
                Опубликовать
              </button>
            </>
          )}
        </aside>
      </form>
      {preview && (
        <section className="preview">
          <h2>Предпросмотр</h2>
          <h1>{title || "Без заголовка"}</h1>
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
      "Адрес ссылки",
      editor.getAttributes("link").href as string,
    );
    if (href === null) return;
    if (!href) editor.chain().focus().unsetLink().run();
    else editor.chain().focus().setLink({ href }).run();
  };
  const buttons = [
    ["Абзац", () => editor.chain().focus().setParagraph().run()],
    ["H2", () => editor.chain().focus().toggleHeading({ level: 2 }).run()],
    ["H3", () => editor.chain().focus().toggleHeading({ level: 3 }).run()],
    ["Жирный", () => editor.chain().focus().toggleBold().run()],
    ["Курсив", () => editor.chain().focus().toggleItalic().run()],
    ["Список", () => editor.chain().focus().toggleBulletList().run()],
    ["Нумерация", () => editor.chain().focus().toggleOrderedList().run()],
    ["Цитата", () => editor.chain().focus().toggleBlockquote().run()],
    ["Ссылка", link],
  ] as const;
  return (
    <div
      className="editor-toolbar"
      role="toolbar"
      aria-label="Форматирование текста"
    >
      {buttons.map(([label, action]) => (
        <button key={label} type="button" onClick={action}>
          {label}
        </button>
      ))}
    </div>
  );
}
