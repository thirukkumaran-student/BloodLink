import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Button,
  Card,
  DataTable,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
  useToast
} from "@bloodlink/ui";
import { adminApi } from "../../api/endpoints";
import { formatDate } from "../../lib/format";
function AdminUsersPage({ user }) {
  const toast = useToast();
  const [role, setRole] = useState("");
  const query = useQuery({
    queryKey: ["admin", "users", role],
    queryFn: () => adminApi.users(role ? role : void 0),
    enabled: Boolean(user)
  });
  const columns = [
    { key: "name", header: "Name", render: (row) => <strong>{row.fullName}</strong> },
    { key: "email", header: "Email", render: (row) => row.email },
    { key: "role", header: "Role", render: (row) => <StatusBadge status={row.role} label={row.role.replace("_", " ")} /> },
    {
      key: "active",
      header: "State",
      render: (row) => <StatusBadge status={row.isActive ? "APPROVED" : "CANCELLED"} label={row.isActive ? "Active" : "Deactivated"} />
    },
    { key: "created", header: "Registered", render: (row) => formatDate(row.createdAt) },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) => <Button
        variant="outline"
        size="sm"
        disabled={!row.isActive || row.id === user?.id}
        onClick={async () => {
          try {
            await adminApi.deactivate(row.id);
            await query.refetch();
            toast.success("Account deactivated", `${row.email} can no longer sign in.`);
          } catch (caught) {
            toast.error("Action failed", caught.message);
          }
        }}
      >
          Deactivate
        </Button>
    }
  ];
  return <><PageHeader title="Accounts" subtitle="Every role signs in through the same account system." /><Card
    title="Platform accounts"
    actions={<div className="bl-row">{["", "INDIVIDUAL", "HOSPITAL", "BLOOD_CENTRE", "ADMIN"].map((value) => <Button
      key={value || "all"}
      size="sm"
      variant={role === value ? "primary" : "outline"}
      onClick={() => setRole(value)}
    >{value ? value.replace("_", " ") : "All"}</Button>)}</div>}
  >{query.isLoading ? <LoadingState /> : query.error ? <ErrorState message={query.error.message} onRetry={() => query.refetch()} /> : <DataTable
    columns={columns}
    rows={query.data?.items ?? []}
    rowKey={(row) => row.id}
    emptyTitle="No accounts in this role"
  />}</Card><div style={{ marginTop: "var(--bl-space-5)" }}><Card title="You cannot lock yourself out" subtitle="Enforced server-side."><p className="bl-muted">
            An administrator deactivating their own account is rejected with 409 by the API, so the
            platform always keeps at least one operator.
          </p></Card></div></>;
}
export {
  AdminUsersPage
};
