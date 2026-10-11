function Button({
  variant = "primary",
  size = "md",
  block = false,
  loading = false,
  className,
  children,
  disabled,
  ...rest
}) {
  const classes = [
    "bl-button",
    `bl-button--${variant}`,
    size !== "md" ? `bl-button--${size}` : "",
    block ? "bl-button--block" : "",
    className ?? ""
  ].filter(Boolean).join(" ");
  return <button className={classes} disabled={disabled || loading} {...rest}>{loading ? <span className="bl-spinner" aria-hidden="true" /> : null}{children}</button>;
}
export {
  Button
};
