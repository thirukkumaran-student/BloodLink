function FormField({ label, htmlFor, required, hint, error, children }) {
  return <div className="bl-field"><label className="bl-label" htmlFor={htmlFor}>{label}{required ? <span className="bl-label__required">*</span> : null}</label>{children}{error ? <span className="bl-error-text" role="alert">{error}</span> : hint ? <span className="bl-hint">{hint}</span> : null}</div>;
}
export {
  FormField
};
