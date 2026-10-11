function Tabs({ tabs, active, onChange }) {
  return <div className="bl-tabs" role="tablist">{tabs.map((tab) => <button
    key={tab.id}
    role="tab"
    aria-selected={tab.id === active}
    className={`bl-tabs__tab${tab.id === active ? " bl-tabs__tab--active" : ""}`}
    onClick={() => onChange(tab.id)}
    type="button"
  >{tab.label}{typeof tab.count === "number" ? ` (${tab.count})` : ""}</button>)}</div>;
}
export {
  Tabs
};
