import axios from 'axios';
import type { SearchResponse, StatsResponse, TokenCreateResponse, TokenListResponse, NodesResponse } from '../types';

const api = axios.create({
  baseURL: '',
  timeout: 10000,
});

// Request interceptor: attach Bearer token if stored
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('log_center_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function searchLogs(params: {
  trace_id?: string;
  level?: string;
  message_substr?: string;
  limit?: number;
}): Promise<SearchResponse> {
  const { data } = await api.get<SearchResponse>('/search', { params });
  return data;
}

export async function getStats(granularity: string = 'hour'): Promise<StatsResponse> {
  const { data } = await api.get<StatsResponse>('/api/stats', { params: { granularity } });
  return data;
}

export async function listTokens(): Promise<TokenListResponse> {
  const { data } = await api.get<TokenListResponse>('/api/tokens');
  return data;
}

export async function createToken(description: string): Promise<TokenCreateResponse> {
  const { data } = await api.post<TokenCreateResponse>('/api/tokens', { description });
  return data;
}

export async function revokeToken(prefix: string): Promise<void> {
  await api.delete(`/api/tokens/${prefix}`);
}

export async function getNodes(): Promise<NodesResponse> {
  const { data } = await api.get<NodesResponse>('/api/nodes');
  return data;
}

export async function getTraceChain(traceId: string): Promise<SearchResponse> {
  const { data } = await api.get<SearchResponse>(`/api/trace/${encodeURIComponent(traceId)}`);
  return data;
}

export default api;
