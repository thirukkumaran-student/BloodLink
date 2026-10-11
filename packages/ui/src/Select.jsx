function Select({ options, placeholder, invalid = false, className, ...rest }) {
  return <select
    className={["bl-select", invalid ? "bl-select--invalid" : "", className ?? ""].filter(Boolean).join(" ")}
    {...rest}
  >{placeholder ? <option value="" disabled>{placeholder}</option> : null}{options.map((option) => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>)}</select>;
}
export {
  Select
};
