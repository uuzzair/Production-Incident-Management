import axios from 'axios';
import type { AuthUser, Incident, IncidentCreatePayload, IncidentDetail, IncidentListResponse, IncidentUpdate, Reporter } from '@/types';

const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8001/api/v1';

const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  }
});

let csrfToken: string | null = null;

api.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase();
  if (csrfToken && method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    config.headers.set('X-CSRF-Token', csrfToken);
  }
  return config;
});

export function isUnauthorizedError(caught: unknown): boolean {
  return axios.isAxiosError(caught) && caught.response?.status === 401;
}

export function isForbiddenError(caught: unknown): boolean {
  return axios.isAxiosError(caught) && caught.response?.status === 403;
}

export function getApiErrorMessage(caught: unknown, fallback: string): string {
  if (axios.isAxiosError(caught)) {
    const payload = caught.response?.data as { error?: { message?: string } } | undefined;
    return payload?.error?.message ?? caught.message ?? fallback;
  }

  if (caught && typeof caught === 'object' && 'message' in caught) {
    return String((caught as { message: unknown }).message);
  }

  return fallback;
}

export interface IncidentFilters {
  status?: string;
  severity?: string;
  created_from?: string;
  created_to?: string;
  limit?: number;
  offset?: number;
}

export async function listIncidents(filters: IncidentFilters = {}): Promise<IncidentListResponse> {
  const response = await api.get<IncidentListResponse>('/incidents/', { params: filters });
  return response.data;
}

export async function getIncident(id: number): Promise<IncidentDetail> {
  const response = await api.get<IncidentDetail>(`/incidents/${id}`);
  return response.data;
}

export async function createIncident(payload: IncidentCreatePayload): Promise<Incident> {
  const response = await api.post<Incident>('/incidents/', payload);
  return response.data;
}

export async function addIncidentUpdate(id: number, message: string): Promise<IncidentUpdate> {
  const response = await api.post<IncidentUpdate>(`/incidents/${id}/updates`, { message });
  return response.data;
}

export async function resolveIncident(id: number): Promise<Incident> {
  const response = await api.patch<Incident>(`/incidents/${id}/resolve`);
  return response.data;
}

export async function listReporters(): Promise<Reporter[]> {
  const response = await api.get<Reporter[]>('/reporters/');
  return response.data;
}

export async function createReporter(name: string): Promise<Reporter> {
  const response = await api.post<Reporter>('/reporters/', { name });
  return response.data;
}

export async function getCurrentUser(): Promise<AuthUser> {
  const response = await api.get<AuthUser>('/auth/me');
  return response.data;
}

export async function refreshCsrfToken(): Promise<string> {
  const response = await api.get<{ csrf_token: string }>('/auth/csrf');
  csrfToken = response.data.csrf_token;
  return csrfToken;
}

export function clearCsrfToken(): void {
  csrfToken = null;
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout');
}

export function getLoginUrl(): string {
  return `${apiBaseUrl.replace(/\/$/, '')}/auth/login`;
}
