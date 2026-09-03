import { useEffect, useState } from "react";
import { api } from "../api";

export function usePortfolioMetrics() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api("/api/engagements")
      .then((data) => setMetrics(data.metrics))
      .catch(() => setMetrics(null))
      .finally(() => setLoading(false));
  }, []);

  return { metrics, loading };
}
