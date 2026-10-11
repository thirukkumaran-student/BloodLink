function Card({ title, subtitle, actions, children, accent, flat, flush, className }) {
  const classes = [
    "bl-card",
    accent ? "bl-card--accent" : "",
    flat ? "bl-card--flat" : "",
    flush ? "bl-card--flush" : "",
    className ?? ""
  ].filter(Boolean).join(" ");
  return <section className={classes}>{title || actions ? <header className="bl-card__header"><div>{title ? <div className="bl-card__title">{title}</div> : null}{subtitle ? <div className="bl-card__subtitle">{subtitle}</div> : null}</div>{actions ? <div className="bl-row">{actions}</div> : null}</header> : null}{children}</section>;
}
function CardHeader({ children }) {
  return <div className="bl-card__header">{children}</div>;
}
function CardFooter({ children }) {
  return <div className="bl-card__footer">{children}</div>;
}
function StatCard({ label, value, hint }) {
  return <div className="bl-stat"><div className="bl-stat__label">{label}</div><div className="bl-stat__value">{value}</div>{hint ? <div className="bl-subtle">{hint}</div> : null}</div>;
}
export {
  Card,
  CardFooter,
  CardHeader,
  StatCard
};
