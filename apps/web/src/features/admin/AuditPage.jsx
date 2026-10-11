import { useQuery } from "@tanstack/react-query";
import { Badge, Card, DataTable, ErrorState, LoadingState, PageHeader } from "@bloodlink/ui";
import { adminApi } from "../../api/endpoints";
import { formatDateTime } from "../../lib/format";
function AdminAuditPage({ user }) {
  const query = useQuery({
    queryKey: ["admin", "audit"],
    queryFn: () => adminApi.audit(),
    enabled: Boolean(user)
  });
  const columns = [
    { key: "when", header: "When", render: (row) => formatDateTime(row.createdAt) },
    { key: "action", header: "Action", render: (row) => <strong>{row.action}</strong> },
    { key: "actor", header: "Actor role", render: (row) => row.actorRole ?? "system" },
    { key: "entity", header: "Entity", render: (row) => row.entityType ?? "\u2014" },
    {
      key: "detail",
      header: "Detail",
      render: (row) => <span className="bl-mono">{row.detail ? JSON.stringify(row.detail) : "\u2014"}</span>
    }
  ];
  return <><PageHeader
    title="Audit trail"
    subtitle="Append-only record of consequential actions. Audit detail never contains patient information."
  /><Card
    title="Recent activity"
    actions={<Badge tone="neutral">append-only</Badge>}
  >{query.isLoading ? <LoadingState /> : query.error ? <ErrorState message={query.error.message} onRetry={() => query.refetch()} /> : <DataTable
    columns={columns}
    rows={query.data?.items ?? []}
    rowKey={(row) => row.id}
    emptyTitle="No audit entries yet"
  />}</Card></>;
}
export {
  AdminAuditPage
};
