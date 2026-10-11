function formatDateTime(value) {
  if (!value) return "\u2014";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "\u2014";
  return date.toLocaleString(void 0, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}
function formatDate(value) {
  if (!value) return "\u2014";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "\u2014";
  return date.toLocaleDateString(void 0, { day: "2-digit", month: "short", year: "numeric" });
}
function relativeTime(value) {
  if (!value) return "\u2014";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "\u2014";
  const diffMinutes = Math.round((then - Date.now()) / 6e4);
  const abs = Math.abs(diffMinutes);
  if (abs < 1) return "just now";
  if (abs < 60) return diffMinutes > 0 ? `in ${abs} min` : `${abs} min ago`;
  const hours = Math.round(abs / 60);
  if (hours < 24) return diffMinutes > 0 ? `in ${hours} h` : `${hours} h ago`;
  const days = Math.round(hours / 24);
  return diffMinutes > 0 ? `in ${days} d` : `${days} d ago`;
}
function minutesUntil(value) {
  if (!value) return null;
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return null;
  return Math.round((time - Date.now()) / 6e4);
}
function dueLabel(value) {
  const minutes = minutesUntil(value);
  if (minutes === null) return "\u2014";
  if (minutes < 0) return `overdue by ${Math.abs(minutes)} min`;
  if (minutes < 120) return `due in ${minutes} min`;
  if (minutes < 60 * 36) return `due in ${Math.round(minutes / 60)} h`;
  return `due ${formatDateTime(value)}`;
}
function toLocalInputValue(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
function initialsOf(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || "?";
}
export {
  dueLabel,
  formatDate,
  formatDateTime,
  initialsOf,
  minutesUntil,
  relativeTime,
  toLocalInputValue
};
