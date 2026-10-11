import { useQuery } from "@tanstack/react-query";
import { Badge, Banner, Card, DataTable, ErrorState, LoadingState, PageHeader } from "@bloodlink/ui";
import { platformApi } from "../../api/endpoints";
const OWNER_BLURB = {
  D1: "Platform foundation \u2014 auth, RBAC, contracts, design system, infrastructure.",
  D2: "Individual & PatientNeed \u2014 hospital discovery, submission, own history.",
  D3: "Hospital & BloodRequest \u2014 review gate, lifecycle, responder coordination, fulfilment.",
  D4: "Donor & coordination \u2014 matching, responses, notifications, threads, donations."
};
function PlatformPage() {
  const health = useQuery({ queryKey: ["platform", "health"], queryFn: platformApi.health });
  const modules = useQuery({ queryKey: ["platform", "modules"], queryFn: platformApi.modules });
  const columns = [
    { key: "key", header: "Module", render: (row) => <span className="bl-mono">{row.key}</span> },
    { key: "owner", header: "Owner", render: (row) => <Badge tone={row.owner === "D1" ? "primary" : "info"}>{row.owner}</Badge> },
    { key: "prefix", header: "API prefix", render: (row) => <span className="bl-mono">{row.prefix}</span> },
    {
      key: "status",
      header: "Foundation status",
      render: (row) => <Badge tone={row.status === "COMPLETE" ? "success" : row.status === "IMPLEMENTED" ? "accent" : "warning"}>{row.status}</Badge>
    },
    { key: "description", header: "Scope", render: (row) => <span className="bl-muted">{row.description}</span> }
  ];
  return <><PageHeader
    title="Modules & ownership"
    subtitle="The modular monolith, straight from the API's own registry — this page cannot drift from the code."
  />{health.data ? <div className="bl-row" style={{ marginBottom: "var(--bl-space-5)" }}><Badge tone={health.data.status === "ok" ? "success" : "warning"}>API {health.data.status}</Badge><Badge tone="neutral">v{health.data.version}</Badge><Badge tone="neutral">env {health.data.env}</Badge><Badge tone="neutral">database {health.data.database}</Badge><Badge tone="neutral">{health.data.moduleCount} modules</Badge></div> : <Banner tone="warning" title="API unreachable.">
          Start the FastAPI process and reload — the module map is read live from it.
        </Banner>}<Card title="Ownership map" subtitle="D1 builds the rails; D2/D3/D4 build features on them (spec §29).">{modules.isLoading ? <LoadingState /> : modules.error ? <ErrorState message={modules.error.message} onRetry={() => modules.refetch()} /> : <DataTable columns={columns} rows={modules.data?.modules ?? []} rowKey={(row) => row.key} />}</Card><div className="bl-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", marginTop: "var(--bl-space-5)" }}>{Object.entries(OWNER_BLURB).map(([owner, blurb]) => <Card key={owner} flat title={owner} subtitle={blurb}><p className="bl-subtle">{owner === "D1" ? "Owns: AGENTS.md, contracts, validation, config, design system, app shells, API client, Prisma-equivalent schema integration, CI rules." : `Owns the feature folders listed in the ownership map and must not modify other owners' implementations without coordination.`}</p></Card>)}</div></>;
}
export {
  PlatformPage
};
