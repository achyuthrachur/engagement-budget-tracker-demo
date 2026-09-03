import { STATUS_COLOR, TOKENS } from "../tokens";

export function StatusPill({ status, small }) {
  const color = STATUS_COLOR[status] || TOKENS.tintMid;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: small ? "3px 10px" : "5px 12px",
        borderRadius: 20,
        background: color + "1f",
        color: color,
        fontSize: small ? 11 : 12,
        fontWeight: 700,
        letterSpacing: "0.02em",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: color,
          display: "inline-block",
        }}
      />
      {status}
    </span>
  );
}
