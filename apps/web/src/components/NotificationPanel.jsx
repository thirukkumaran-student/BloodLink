import { Badge, Button, Card, EmptyState, LoadingState } from "@bloodlink/ui";
import { relativeTime } from "../lib/format";
function NotificationPanel({ data, loading, onClose, onMarkAll }) {
  return <div style={{ marginBottom: "var(--bl-space-5)" }}><Card
    title="Notifications"
    subtitle="Operational alerts only — no patient information is ever included."
    actions={<><Button variant="outline" size="sm" onClick={() => void onMarkAll()}>
              Mark all read
            </Button><Button variant="ghost" size="sm" onClick={onClose}>
              Close
            </Button></>}
  >{loading ? <LoadingState label="Loading notifications…" /> : !data?.items.length ? <EmptyState title="No notifications yet" hint="Alerts appear here as requests, responses and messages happen." /> : <div className="bl-stack-sm">{data.items.slice(0, 12).map((item) => <div key={item.id} className="bl-row-between" style={{ alignItems: "flex-start" }}><div><div className="bl-row" style={{ gap: "var(--bl-space-2)" }}><strong>{item.title}</strong>{item.readAt ? null : <Badge tone="primary">New</Badge>}</div><div className="bl-muted">{item.body}</div><div className="bl-subtle">{String(item.data.distanceBand ?? "")} {relativeTime(item.createdAt)}</div></div></div>)}</div>}</Card></div>;
}
export {
  NotificationPanel
};
