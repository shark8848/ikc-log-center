export interface LogEntry {
  ts: string | null;
  level: string | null;
  logger: string | null;
  message: string | null;
  trace_id: string | null;
  span_id: string | null;
  parent_id: string | null;
  payload: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface SearchResponse {
  status: string;
  count: number;
  items: LogEntry[];
}

export interface TokenInfo {
  prefix: string;
  description: string;
  created_at: string;
  active: boolean;
}

export interface TokenListResponse {
  status: string;
  tokens: TokenInfo[];
}

export interface TokenCreateResponse {
  status: string;
  token: string;
  prefix: string;
  description: string;
}

export interface StatsResponse {
  status: string;
  total: number;
  levels: Record<string, number>;
  trend: { time: string; count: number }[];
}

export interface AppInfo {
  name: string;
  log_count: number;
  error_count: number;
  last_active: string | null;
}

export interface NodeInfo {
  ip: string;
  apps: AppInfo[];
  log_count: number;
  error_count: number;
}

export interface NodesResponse {
  status: string;
  nodes: NodeInfo[];
}
