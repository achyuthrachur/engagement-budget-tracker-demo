import { useCountUp } from "../hooks/useCountUp";

export function MetricCard({ icon, label, value, sub, index, format, tone }) {
  const isNumeric = typeof value === "number";
  const animated = useCountUp(isNumeric ? value : 0, 850, isNumeric);
  return (
    <div
      className={`metric-card stagger-in${tone ? ` tone-${tone}` : ""}`}
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <div className="metric-card-head">
        <span className="metric-icon">{icon}</span>
        <span className="metric-label">{label}</span>
      </div>
      <strong className="metric-value">
        {isNumeric ? format(animated) : value}
      </strong>
      {sub && <small className="metric-sub">{sub}</small>}
    </div>
  );
}
