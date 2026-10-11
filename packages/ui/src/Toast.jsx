import { createContext, useCallback, useContext, useMemo, useState } from "react";
const ToastContext = createContext(null);
function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((toast) => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { ...toast, id }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 5200);
  }, []);
  const value = useMemo(
    () => ({
      push,
      success: (title, body) => push({ tone: "success", title, body }),
      error: (title, body) => push({ tone: "error", title, body })
    }),
    [push]
  );
  return <ToastContext.Provider value={value}>{children}<div className="bl-toasts" aria-live="polite">{toasts.map((toast) => <div key={toast.id} className={`bl-toast bl-toast--${toast.tone}`}><div className="bl-toast__title">{toast.title}</div>{toast.body ? <div className="bl-toast__body">{toast.body}</div> : null}</div>)}</div></ToastContext.Provider>;
}
function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return context;
}
export {
  ToastProvider,
  useToast
};
