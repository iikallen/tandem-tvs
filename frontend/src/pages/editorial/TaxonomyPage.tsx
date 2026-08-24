import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";

import { api } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";
import { EditorialGuard } from "./EditorialGuard";

export function TaxonomyPage() {
  return (
    <EditorialGuard>
      <Taxonomy />
    </EditorialGuard>
  );
}

function Taxonomy() {
  const [categoryName, setCategoryName] = useState("");
  const [tagName, setTagName] = useState("");
  const queryClient = useQueryClient();
  const categories = useQuery({
    queryKey: ["editorial-categories"],
    queryFn: api.editorialCategories,
  });
  const tags = useQuery({ queryKey: ["editorial-tags"], queryFn: api.tags });
  const mutate = useMutation({
    mutationFn: async ({
      type,
      id,
      name,
      active,
      attachments,
    }: {
      type: "category" | "tag";
      id?: number;
      name?: string;
      active?: boolean;
      attachments?: boolean;
    }) => {
      if (type === "category") {
        if (id)
          return api.updateCategory(id, {
            ...(active === undefined ? {} : { is_active: active }),
            ...(attachments === undefined
              ? {}
              : { comment_attachments_enabled: attachments }),
          });
        return api.createCategory({
          name,
          slug: slug(name ?? ""),
          sort_order: 0,
        });
      }
      if (id) return api.updateTag(id, { is_active: active });
      return api.createTag({ name, slug: slug(name ?? "") });
    },
    onSuccess: async () => {
      setCategoryName("");
      setTagName("");
      await queryClient.invalidateQueries({
        queryKey: ["editorial-categories"],
      });
      await queryClient.invalidateQueries({ queryKey: ["editorial-tags"] });
    },
  });
  if (categories.isPending || tags.isPending)
    return <PageState kind="loading" />;
  if (categories.isError) return <PageState error={categories.error} />;
  if (tags.isError) return <PageState error={tags.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("editorial")}</p>
          <h1>{t("categoriesAndTags")}</h1>
        </div>
      </header>
      <div className="taxonomy-grid">
        <Card>
          <h2>{t("categories")}</h2>
          <InlineCreate
            value={categoryName}
            onChange={setCategoryName}
            onCreate={() =>
              mutate.mutate({ type: "category", name: categoryName })
            }
          />
          {categories.data.map((item) => (
            <Fragment key={item.id}>
              <TaxonomyRow
                name={item.name}
                active={item.is_active !== false}
                onToggle={() =>
                  mutate.mutate({
                    type: "category",
                    id: item.id,
                    active: item.is_active === false,
                  })
                }
              />
              <button
                className="text-button"
                type="button"
                onClick={() =>
                  mutate.mutate({
                    type: "category",
                    id: item.id,
                    attachments: !item.comment_attachments_enabled,
                  })
                }
              >
                {t(
                  item.comment_attachments_enabled
                    ? "disableCommentAttachments"
                    : "enableCommentAttachments",
                )}
              </button>
            </Fragment>
          ))}
        </Card>
        <Card>
          <h2>{t("tags")}</h2>
          <InlineCreate
            value={tagName}
            onChange={setTagName}
            onCreate={() => mutate.mutate({ type: "tag", name: tagName })}
          />
          {tags.data.map((item) => (
            <TaxonomyRow
              key={item.id}
              name={item.name}
              active={item.is_active}
              onToggle={() =>
                mutate.mutate({
                  type: "tag",
                  id: item.id,
                  active: !item.is_active,
                })
              }
            />
          ))}
        </Card>
      </div>
      {mutate.isError && (
        <p className="field-error" role="alert">
          {mutate.error.message}
        </p>
      )}
    </div>
  );
}

function InlineCreate({
  value,
  onChange,
  onCreate,
}: {
  value: string;
  onChange: (value: string) => void;
  onCreate: () => void;
}) {
  return (
    <div className="inline-create">
      <label>
        {t("name")}
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
      <button
        className="button"
        type="button"
        disabled={!value.trim()}
        onClick={onCreate}
      >
        {t("add")}
      </button>
    </div>
  );
}

function TaxonomyRow({
  name,
  active,
  onToggle,
}: {
  name: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="taxonomy-row">
      <span>{name}</span>
      <button
        className="button button--secondary"
        type="button"
        onClick={onToggle}
      >
        {t(active ? "deactivate" : "activate")}
      </button>
    </div>
  );
}

function slug(value: string) {
  return value
    .toLocaleLowerCase()
    .trim()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");
}
