import { statusTone } from "./tone";
function Badge({ tone = "neutral", children }) {
  return <span className={`bl-badge bl-badge--${tone}`}>{children}</span>;
}
function StatusBadge({ status, label }) {
  return <Badge tone={statusTone(status)}>{label ?? status.replace(/_/g, " ")}</Badge>;
}
export {
  Badge,
  StatusBadge
};
