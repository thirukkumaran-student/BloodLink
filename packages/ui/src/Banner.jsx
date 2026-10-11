function Banner({
  tone = "info",
  title,
  children
}) {
  return <div className={`bl-banner bl-banner--${tone}`} role={tone === "danger" ? "alert" : "status"}>{title ? <strong>{title}</strong> : null}{title ? " " : null}{children}</div>;
}
export {
  Banner
};
