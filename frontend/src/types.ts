export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type IncidentStatus = 'open' | 'resolved';

export interface Incident {
  id: number;
  title: string;
  reporter_id?: number | null;
  created_by: string;
  severity: Severity;
  description: string;
  status: IncidentStatus;
  created_at: string;
}

export interface IncidentUpdate {
  id: number;
  incident_id: number;
  message: string;
  created_at: string;
}

export interface IncidentDetail extends Incident {
  updates: IncidentUpdate[];
}

export interface IncidentCreatePayload {
  title: string;
  created_by: string;
  severity: Severity;
  description: string;
}

export interface Reporter {
  id: number;
  name: string;
  created_at: string;
}

export interface Pagination {
  limit: number;
  offset: number;
  total: number;
}

export interface IncidentListResponse {
  items: Incident[];
  pagination: Pagination;
}
