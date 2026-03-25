export interface ContainerStatus {
  name: string;
  instance: number; // container number within a scaled service (1-indexed)
  status: string; // "running", "exited", etc.
  health: string | null; // "healthy", "unhealthy", or null if no healthcheck
  uptime_seconds: number;
  restart_count: number;
}

export interface QueueStatus {
  name: string;
  messages: number;
  consumers: number;
  publish_rate: number;
  deliver_rate: number;
}

export interface ExchangeStatus {
  name: string;
  type: string;
  publish_rate: number;
}

export interface DbStatus {
  article_count: number;
  latest_insert: string | null;
  labelled_count: number;
}

export interface InfraStatus {
  containers: ContainerStatus[];
  queues: QueueStatus[];
  exchanges: ExchangeStatus[];
  db: DbStatus | null;
}
