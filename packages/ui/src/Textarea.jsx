function Textarea({ invalid = false, className, ...rest }) {
  return <textarea
    className={["bl-textarea", invalid ? "bl-textarea--invalid" : "", className ?? ""].filter(Boolean).join(" ")}
    {...rest}
  />;
}
export {
  Textarea
};
