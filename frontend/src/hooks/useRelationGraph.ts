import { useState, useEffect, useCallback } from "react";
import type { GraphData } from "../types/graph";

export function useRelationGraph(
  lambdaDecay: number,
  minStrength: number,
  corroboration: number,
  relationTypeFilter: string[],
) {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Serialize the filter array to a stable string for the dependency array.
  // Without this, a new array reference on every render would retrigger the fetch.
  const filterKey = relationTypeFilter.join(",");

  const fetchGraph = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        lambda_decay: String(lambdaDecay),
        min_strength: String(minStrength),
        corroboration: String(corroboration),
      });
      if (filterKey) {
        params.set("relation_types", filterKey);
      }
      const res = await fetch(`/api/graph/relations?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch graph");
    } finally {
      setLoading(false);
    }
  }, [lambdaDecay, minStrength, corroboration, filterKey]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  return { data, loading, error, refetch: fetchGraph };
}
