import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

export function useEngagementOverview(engagementId) {
  const [data, setData] = useState(null); // { engagement, metrics, phases }
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    if (!engagementId) return;
    setLoading(true);
    setError(null);
    api(`/api/engagements/${engagementId}/overview`)
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [engagementId]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, loading, reload };
}
