import type { EventLogEntry } from "../types/pipeline";

export const MOCK_EVENTS: EventLogEntry[] = [
  {
    timestamp: "14:22:01.03",
    level: "system",
    message: "_INITIATING_INGESTION: DATA_NODE_TX_92",
  },
  {
    timestamp: "14:22:01.44",
    level: "info",
    message: "RSS feed resolved: bbc_world [14 items queued]",
  },
  {
    timestamp: "14:22:02.11",
    level: "info",
    message: "Article Ingested: ID_10293 [SOURCE: Reuters]",
  },
  {
    timestamp: "14:22:02.88",
    level: "info",
    message: "Article Ingested: ID_10294 [SOURCE: AP_Wire]",
  },
  {
    timestamp: "14:22:03.52",
    level: "success",
    message: "NER pass complete: ID_10293 — 7 entities extracted",
  },
  {
    timestamp: "14:22:04.07",
    level: "success",
    message: "Actor Identified: Entity_X_Bravo [Confidence: 0.99]",
    highlight: "Entity_X_Bravo",
  },
  {
    timestamp: "14:22:04.90",
    level: "warning",
    message: "WARNING: LATENCY_SPIKE_DETECTED (+4ms)",
  },
  {
    timestamp: "14:22:05.31",
    level: "info",
    message: "Geolocation resolved: 'Azores' → [37.7412° N, 25.6756° W]",
  },
  {
    timestamp: "14:22:05.77",
    level: "success",
    message: "GeoAnchor written: UNDERSEA_CABLE_TAP [node: SP-04]",
    highlight: "UNDERSEA_CABLE_TAP",
  },
  {
    timestamp: "14:22:06.14",
    level: "error",
    message: "CRITICAL: NODE_FAILOVER_INITIATED [TX_91 → TX_92]",
  },
  {
    timestamp: "14:22:06.88",
    level: "system",
    message: "_RECONNECT: DATA_NODE_TX_92 — handshake OK",
  },
  {
    timestamp: "14:22:07.22",
    level: "info",
    message: "Article Ingested: ID_10295 [SOURCE: bbc_world]",
  },
  {
    timestamp: "14:22:07.91",
    level: "warning",
    message: "Dedup flag: ID_10295 content similarity 0.94 with ID_10281",
  },
  {
    timestamp: "14:22:08.55",
    level: "success",
    message: "Actor Identified: Org_Meridian_Data [Confidence: 0.97]",
    highlight: "Org_Meridian_Data",
  },
  {
    timestamp: "14:22:09.03",
    level: "system",
    message: "_CYCLE_COMPLETE: 3 articles committed, 1 flagged, 0 dropped",
  },
];
