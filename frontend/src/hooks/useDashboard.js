import { useEffect, useState } from "react";
import { api } from "../api";

export function useDashboard() {
  const [data, setData] = useState(null); // { metrics, engagements }
  const [proposals, setProposals] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([api("/api/engagements"), api("/api/proposals").catch(() => ({ proposals: [] }))])
      .then(([engagementsData, proposalsData]) => {
        setData(engagementsData);
        setProposals(proposalsData.proposals || []);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  return { data, proposals, error, loading };
}
