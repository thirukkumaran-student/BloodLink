function Input({ invalid = false, className, ...rest }) {
  return <input className={["bl-input", invalid ? "bl-input--invalid" : "", className ?? ""].filter(Boolean).join(" ")} {...rest} />;
}
export {
  Input
};
