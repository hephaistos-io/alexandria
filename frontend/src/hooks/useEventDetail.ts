import { useEffect, useState } from "react";
import type { DetectedEventDetail } from "../types/event";

export function useEventDetail(eventId: number | null) {
  const [detail, setDetail] = useState<DetectedEventDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (eventId === null) {
      setDetail(null);
      return;
    }

    let cancelled = false;
    setLoading(true);

    fetch(`/api/dashboard/events/${eventId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: DetectedEventDetail) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [eventId]);

  return { detail, loading };
}
