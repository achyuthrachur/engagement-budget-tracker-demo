// Generic weekly grid: given a week list, a row list and a cell renderer, draws
// the sticky-header/sticky-first-column table shared by every weekly
// budget/actual/forecast view (Phase Detail today; the New Engagement wizard
// and Proposal builder are meant to reuse it too - keep this component's
// contract limited to rows/weeks/rendering, no phase-detail-specific logic).
function formatWeekLabel(week) {
  return new Date(`${week}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function WeeklyGrid({ weeks, rows, rowKey, renderRowHeader, renderCell, cellClassName, cellTitle }) {
  return (
    <div className="weekly-grid-wrap">
      <table className="weekly-grid">
        <thead>
          <tr>
            <th>Team member</th>
            {weeks.map((week) => (
              <th key={week}>Week of {formatWeekLabel(week)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              <th>{renderRowHeader(row)}</th>
              {weeks.map((week, index) => (
                <td key={week} className={cellClassName?.(row, index) || undefined} title={cellTitle?.(row, index)}>
                  {renderCell(row, index)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
