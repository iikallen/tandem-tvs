import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { api } from "../../shared/api";
import { PageState } from "../../shared/ui/PageState";

export function EditorialGuard({ children }: { children: ReactNode }) {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  if (me.isPending) return <PageState kind="loading" />;
  if (me.isError) return <PageState error={me.error} />;
  if (
    !me.data.module_roles.some((role) =>
      ["author", "editor", "admin", "administrator"].includes(role),
    )
  ) {
    return <PageState error={new Error("Editorial role required")} />;
  }
  return children;
}
