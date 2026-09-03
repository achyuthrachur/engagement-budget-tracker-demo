import { useEffect, useState } from "react";
import { api } from "../api";

export function useAppHealth() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api("/api/health").then(setHealth).catch(() => {});
  }, []);

  return health;
}
