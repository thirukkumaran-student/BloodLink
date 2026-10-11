function PageHeader({
  title,
  subtitle,
  actions
}) {
  return <div className="bl-row-between" style={{ marginBottom: "var(--bl-space-6)" }}><div><h1 className="bl-app__page-title">{title}</h1>{subtitle ? <div className="bl-app__page-sub">{subtitle}</div> : null}</div>{actions ? <div className="bl-row">{actions}</div> : null}</div>;
}
export {
  PageHeader
};
