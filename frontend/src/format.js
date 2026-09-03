export function formatHours(n) {
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}
export function formatMoney(n) {
  return "$" + Math.round(n).toLocaleString();
}
export function formatPct(n) {
  return (n * 100).toFixed(0) + "%";
}
