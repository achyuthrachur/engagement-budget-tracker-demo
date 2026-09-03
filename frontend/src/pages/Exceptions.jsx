import { useCallback, useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { formatHours, formatMoney } from "../format";
import { api } from "../api";

function StatusBadge({ status }) {
  return <span className={`exception-status ${status}`}>{status}</span>;
}

function ExceptionRow({ exception, team, phases, closed, onResolved, onRuleCreated }) {
  const [memberId, setMemberId] = useState("");
  const [phaseId, setPhaseId] = useState(phases[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const actionable = exception.status === "pending" && !closed;
  const isWorkerException = exception.exception_code.startsWith("worker_");
  const isNewWorker = exception.exception_code === "worker_unknown";
  const isUnmatchedPhase = exception.exception_code === "unmatched_phase";

  async function run(action, body) {
    setBusy(true);
    setError(null);
    try {
      const response = await api(`/api/engagements/${exception.engagement_id}/exceptions/${exception.id}/${action}`, {
        method: "POST",
        body,
      });
      if (action === "assign-phase" && response?.offer_sticky_rule) {
        await offerStickyRule(response.offer_sticky_rule);
      }
      onResolved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function offerStickyRule({ team_member_id, phase_id }) {
    const declineKey = `declined-rule-${team_member_id}-${phase_id}`;
    if (sessionStorage.getItem(declineKey)) return;
    const memberName = team.find((m) => m.id === team_member_id)?.name || "This worker";
    const targetPhaseName = phases.find((p) => p.id === phase_id)?.phase_name || "this phase";
    if (!window.confirm(`Always assign ${memberName}'s uncoded entries to ${targetPhaseName} going forward?`)) {
      sessionStorage.setItem(declineKey, "1");
      return;
    }
    await api(`/api/engagements/${exception.engagement_id}/allocation-rules`, {
      method: "POST",
      body: { team_member_id, phase_id, created_from_exception_id: exception.id },
    });
    onRuleCreated();
  }

  function exclude() {
    if (!reason.trim()) {
      setError("Enter an exclusion reason");
      return;
    }
    if (!window.confirm("Exclude this charge? It will stop affecting hours, fees, realization, projections and exports.")) return;
    run("exclude", { reason });
  }

  return (
    <tr className={exception.status}>
      <td className="mono">{exception.transaction_id || ""}</td>
      <td>{exception.worker_name || ""}</td>
      <td>{formatHours(exception.hours)}</td>
      <td>{formatMoney(exception.fees_contract_rate)}</td>
      <td>{exception.exception_code.replaceAll("_", " ")}</td>
      <td>
        <StatusBadge status={exception.status} />
      </td>
      <td>
        {actionable && (
          <div className="exception-actions">
            {isWorkerException && (
              <>
                <select value={memberId} onChange={(e) => setMemberId(e.target.value)} disabled={busy}>
                  <option value="">Create imported worker</option>
                  {team.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.name}
                    </option>
                  ))}
                </select>
                <button
                  className="btn text"
                  disabled={busy}
                  onClick={() => run("assign-team", memberId ? { team_member_id: Number(memberId) } : {})}
                >
                  Assign team
                </button>
                {isNewWorker && (
                  <p className="hint allocation-memo-hint">
                    Not staffed on this engagement yet —{" "}
                    <a href={`/engagements/${exception.engagement_id}/team`}>open the team roster</a> to add them, then{" "}
                    <Link to={`/engagements/${exception.engagement_id}/phases`}>open a phase's forecast editor</Link> to
                    budget their hours so future weeks aren't flagged too.
                  </p>
                )}
              </>
            )}
            {isUnmatchedPhase && (
              <>
                {exception.phase_candidates?.length > 0 && (
                  <div className="allocation-candidates">
                    <span className="allocation-candidates-label">Likely — budgeted this week:</span>
                    {exception.phase_candidates.map((candidate) => (
                      <button
                        key={candidate.phase_id}
                        type="button"
                        className="btn text allocation-candidate"
                        disabled={busy}
                        onClick={() => setPhaseId(candidate.phase_id)}
                      >
                        {candidate.phase_name}
                      </button>
                    ))}
                  </div>
                )}
                {exception.memo && (
                  <p className="hint allocation-memo-hint">Memo: "{exception.memo}"</p>
                )}
                {exception.memo_suggestion && (
                  <p className="hint allocation-memo-hint">
                    Memo mentions "{exception.memo_suggestion.matched_text}" — possible match:{" "}
                    {exception.memo_suggestion.phase_name}
                    <button
                      type="button"
                      className="btn text"
                      disabled={busy}
                      onClick={() => setPhaseId(exception.memo_suggestion.phase_id)}
                    >
                      Use this
                    </button>
                  </p>
                )}
                <select value={phaseId} onChange={(e) => setPhaseId(e.target.value)} disabled={busy}>
                  {phases.map((phase) => (
                    <option key={phase.id} value={phase.id}>
                      {phase.phase_name}
                    </option>
                  ))}
                </select>
                <button className="btn text" disabled={busy || !phaseId} onClick={() => run("assign-phase", { phase_id: Number(phaseId) })}>
                  Assign phase
                </button>
              </>
            )}
            <input placeholder="Exclusion reason" value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} />
            <button className="btn text danger-text" disabled={busy} onClick={exclude}>
              Exclude
            </button>
          </div>
        )}
        {error && <p className="hint danger-text">{error}</p>}
      </td>
    </tr>
  );
}

function AllocationRulesSection({ engagementId, closed, version }) {
  const [rules, setRules] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(() => {
    api(`/api/engagements/${engagementId}/allocation-rules`).then(setRules).catch((err) => setError(err.message));
  }, [engagementId]);

  useEffect(() => {
    reload();
  }, [reload, version]);

  async function remove(ruleId) {
    setError(null);
    try {
      await api(`/api/engagements/${engagementId}/allocation-rules/${ruleId}`, { method: "DELETE" });
      reload();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!rules) return null;

  return (
    <section className="card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Applied automatically on future imports</span>
          <h2>Allocation rules</h2>
        </div>
        <span className="section-hint">{rules.length} active</span>
      </div>
      {error && <p className="hint danger-text">{error}</p>}
      {rules.length === 0 ? (
        <p className="hint">No allocation rules yet — accept a sticky-rule prompt from the exception queue to create one.</p>
      ) : (
        <ul className="allocation-rules-list">
          {rules.map((rule) => (
            <li key={rule.id}>
              <span>
                {rule.team_member_name}'s uncoded entries → {rule.phase_name}
              </span>
              {!closed && (
                <button className="btn text danger-text" onClick={() => remove(rule.id)}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function Exceptions() {
  const { engagementId, engagement, phases, reload: reloadOverview } = useOutletContext();
  const [exceptions, setExceptions] = useState(null);
  const [team, setTeam] = useState([]);
  const [error, setError] = useState(null);
  const [rulesVersion, setRulesVersion] = useState(0);

  const reloadExceptions = useCallback(() => {
    api(`/api/engagements/${engagementId}/exceptions`).then(setExceptions).catch((err) => setError(err.message));
  }, [engagementId]);

  const onResolved = useCallback(() => {
    reloadExceptions();
    reloadOverview(); // pending_exceptions_count shown on Overview/the topbar needs to reflect this
  }, [reloadExceptions, reloadOverview]);

  const onRuleCreated = useCallback(() => setRulesVersion((v) => v + 1), []);

  useEffect(() => {
    reloadExceptions();
    api(`/api/engagements/${engagementId}/team`).then(setTeam).catch(() => setTeam([]));
  }, [engagementId, reloadExceptions]);

  if (error) return <p className="hint danger-text">{error}</p>;
  if (!exceptions) return <p className="hint">Loading exceptions…</p>;

  const pendingCount = exceptions.filter((x) => x.status === "pending").length;

  return (
    <>
    <section className="card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Imported entries remain in totals</span>
          <h2>Exception queue</h2>
        </div>
        <span className="section-hint">{pendingCount} pending</span>
      </div>
      <p className="hint">
        Resolve legitimate time by assigning it. Exclude only an invalid charge; excluded entries remain auditable but stop affecting every
        calculation and export.
      </p>
      <div className="table-wrap">
        <table className="exceptions-table">
          <thead>
            <tr>
              <th>Transaction</th>
              <th>Worker</th>
              <th>Hours</th>
              <th>Fees</th>
              <th>Type</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {exceptions.length === 0 && (
              <tr>
                <td colSpan={7}>No import exceptions</td>
              </tr>
            )}
            {exceptions.map((exception) => (
              <ExceptionRow
                key={exception.id}
                exception={exception}
                team={team}
                phases={phases}
                closed={engagement.status === "closed"}
                onResolved={onResolved}
                onRuleCreated={onRuleCreated}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
    <AllocationRulesSection
      engagementId={engagementId}
      closed={engagement.status === "closed"}
      version={rulesVersion}
    />
    </>
  );
}
