import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Button,
  Card,
  DataTable,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
  Tabs,
  useToast
} from "@bloodlink/ui";
import { adminApi } from "../../api/endpoints";
import { formatDate } from "../../lib/format";
function AdminOrganizationsPage({ user }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("PENDING");
  const query = useQuery({
    queryKey: ["admin", "organizations", filter],
    queryFn: () => adminApi.organizations(filter),
    enabled: Boolean(user)
  });
  async function act(id, action) {
    try {
      if (action === "verify") await adminApi.verify(id);
      else await adminApi.suspend(id);
      await queryClient.invalidateQueries({ queryKey: ["admin", "organizations"] });
      toast.success(action === "verify" ? "Organization verified" : "Organization suspended");
    } catch (caught) {
      toast.error("Action failed", caught.message);
    }
  }
  const columns = [
    { key: "name", header: "Organization", render: (row) => <strong>{row.name}</strong> },
    { key: "type", header: "Type", render: (row) => row.orgType.replace("_", " ") },
    { key: "location", header: "Locality", render: (row) => row.locationLabel ?? "\u2014" },
    { key: "status", header: "Verification", render: (row) => <StatusBadge status={row.verificationStatus} /> },
    { key: "created", header: "Registered", render: (row) => formatDate(row.createdAt) },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) => <span className="bl-row" style={{ justifyContent: "flex-end" }}>{row.verificationStatus !== "VERIFIED" ? <Button variant="success" size="sm" onClick={() => void act(row.id, "verify")}>
              Verify
            </Button> : null}{row.verificationStatus !== "SUSPENDED" ? <Button variant="outline" size="sm" onClick={() => void act(row.id, "suspend")}>
              Suspend
            </Button> : null}</span>
    }
  ];
  return <><PageHeader
    title="Organizations"
    subtitle="Verification is the switch that lets a hospital or blood centre operate on BloodLink."
  /><Card
    title="Onboarding queue"
    actions={<Tabs
      tabs={[
        { id: "PENDING", label: "Pending" },
        { id: "VERIFIED", label: "Verified" },
        { id: "SUSPENDED", label: "Suspended" }
      ]}
      active={filter}
      onChange={setFilter}
    />}
  >{query.isLoading ? <LoadingState /> : query.error ? <ErrorState message={query.error.message} onRetry={() => query.refetch()} /> : <DataTable
    columns={columns}
    rows={query.data?.items ?? []}
    rowKey={(row) => row.id}
    emptyTitle="Nothing in this state"
    emptyHint="Organizations appear here as soon as they register."
  />}</Card><div style={{ marginTop: "var(--bl-space-5)" }}><Card title="What verification means" subtitle="Spec §16."><ul className="bl-muted" style={{ paddingLeft: "var(--bl-space-5)" }}><li>Unverified organizations can sign in but every operational endpoint returns 403 ORGANIZATION_NOT_VERIFIED.</li><li>Suspension takes effect immediately for every member of the organization.</li><li>Both actions are written to the audit trail with the acting administrator.</li></ul></Card></div></>;
}
export {
  AdminOrganizationsPage
};
