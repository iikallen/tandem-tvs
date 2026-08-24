import { useQuery } from "@tanstack/react-query";

import { api } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";

export function MessengerAccessPage() {
  const access = useQuery({
    queryKey: ["messenger-access"],
    queryFn: api.messengerAccess,
  });
  if (access.isPending) return <PageState kind="loading" />;
  if (access.isError) return <PageState error={access.error} />;
  return (
    <Card>
      <p className="overline">{t("messenger")}</p>
      <h1>{t("messengerReady")}</h1>
      <p>{t("messengerStage7")}</p>
    </Card>
  );
}
