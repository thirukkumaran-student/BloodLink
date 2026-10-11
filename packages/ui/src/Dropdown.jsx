import { useEffect, useRef, useState } from "react";
function Dropdown({ trigger, items }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onClick = (event) => {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);
  return <div className="bl-dropdown" ref={ref}><div onClick={() => setOpen((value) => !value)}>{trigger}</div>{open ? <div className="bl-dropdown__menu" role="menu">{items.map((item) => <button
    key={item.id}
    type="button"
    role="menuitem"
    className="bl-dropdown__item"
    onClick={() => {
      setOpen(false);
      item.onSelect();
    }}
  >{item.label}</button>)}</div> : null}</div>;
}
export {
  Dropdown
};
