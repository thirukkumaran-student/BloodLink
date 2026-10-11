import { EmptyState } from "./States";
function DataTable({
  columns,
  rows,
  emptyTitle = "Nothing here yet",
  emptyHint,
  rowKey,
  onRowClick
}) {
  if (!rows.length) return <EmptyState title={emptyTitle} hint={emptyHint} />;
  return <div className="bl-table-wrap"><table className="bl-table"><thead><tr>{columns.map((column) => <th key={column.key} style={column.align === "right" ? { textAlign: "right" } : void 0}>{column.header}</th>)}</tr></thead><tbody>{rows.map((row) => <tr
    key={rowKey(row)}
    onClick={onRowClick ? () => onRowClick(row) : void 0}
    style={onRowClick ? { cursor: "pointer" } : void 0}
  >{columns.map((column) => <td key={column.key} style={column.align === "right" ? { textAlign: "right" } : void 0}>{column.render(row)}</td>)}</tr>)}</tbody></table></div>;
}
export {
  DataTable
};
