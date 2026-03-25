import { useState, useEffect, useCallback } from "react";

/**
 * Generic CRUD hook for a REST resource at `baseUrl`.
 *
 * GET  baseUrl       — fetch all items
 * POST baseUrl       — create
 * PATCH baseUrl/:id  — update
 * DELETE baseUrl/:id — remove
 *
 * Each mutation returns true on success and false on failure (setting `error`).
 * After every successful mutation the list is re-fetched so local state stays
 * in sync with the server without optimistic updates.
 */
export function useCrudResource<T, CreatePayload, UpdatePayload>(baseUrl: string): {
  items: T[];
  loading: boolean;
  error: string | null;
  create: (payload: CreatePayload) => Promise<boolean>;
  update: (id: number, payload: UpdatePayload) => Promise<boolean>;
  remove: (id: number) => Promise<boolean>;
} {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch(baseUrl);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data: T[] = await res.json();
      setItems(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const create = useCallback(
    async (payload: CreatePayload): Promise<boolean> => {
      try {
        const res = await fetch(baseUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        await fetchAll();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
        return false;
      }
    },
    [baseUrl, fetchAll],
  );

  const update = useCallback(
    async (id: number, payload: UpdatePayload): Promise<boolean> => {
      try {
        const res = await fetch(`${baseUrl}/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        await fetchAll();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
        return false;
      }
    },
    [baseUrl, fetchAll],
  );

  const remove = useCallback(
    async (id: number): Promise<boolean> => {
      try {
        const res = await fetch(`${baseUrl}/${id}`, { method: "DELETE" });
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        await fetchAll();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
        return false;
      }
    },
    [baseUrl, fetchAll],
  );

  return { items, loading, error, create, update, remove };
}
