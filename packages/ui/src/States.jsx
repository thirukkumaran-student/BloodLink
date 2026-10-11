function LoadingState({ label = "Loading\u2026" }) {
  return <div className="bl-loading" role="status" aria-live="polite"><span className="bl-spinner" aria-hidden="true" /><span>{label}</span></div>;
}
function EmptyState({ title, hint, action }) {
  return <div className="bl-state"><div className="bl-state__title">{title}</div>{hint ? <p>{hint}</p> : null}{action ? <div className="bl-state__actions">{action}</div> : null}</div>;
}
function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  action
}) {
  return <div className="bl-state bl-state--error" role="alert"><div className="bl-state__title">{title}</div>{message ? <p>{message}</p> : null}<div className="bl-state__actions">{onRetry ? <button type="button" className="bl-button bl-button--outline bl-button--sm" onClick={onRetry}>
            Try again
          </button> : null}{action}</div></div>;
}
function Skeleton({ width = "100%" }) {
  return <div className="bl-skeleton" style={{ width }} />;
}
export {
  EmptyState,
  ErrorState,
  LoadingState,
  Skeleton
};
