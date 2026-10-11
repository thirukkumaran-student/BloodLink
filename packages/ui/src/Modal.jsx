import { useEffect } from "react";
function Modal({ open, title, onClose, children, footer, wide }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return <div className="bl-modal__overlay" role="presentation" onClick={onClose}><div
    className={`bl-modal${wide ? " bl-modal--wide" : ""}`}
    role="dialog"
    aria-modal="true"
    aria-label={title}
    onClick={(event) => event.stopPropagation()}
  ><h3 className="bl-modal__title">{title}</h3><div className="bl-modal__body">{children}</div>{footer ? <div className="bl-modal__actions">{footer}</div> : null}</div></div>;
}
export {
  Modal
};
