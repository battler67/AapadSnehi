import type {
  AllocationStrategyMetadata,
  Assignment,
  AssignmentInput,
  CitizenReport,
  Dashboard,
  DistributionInput,
  DistributionPlan,
  GovernmentSourceInput,
  Incident,
  IngestionRun,
  BlueskyScanResult,
  ReportSubmission,
  Source,
  Volunteer,
  VolunteerInput,
} from "../types";

export const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init?.signal || AbortSignal.timeout(8_000),
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : "The API is unreachable");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string | Array<{ msg?: string }> };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (Array.isArray(payload.detail) && payload.detail.length > 0) {
        message = payload.detail.map((err) => err.msg || JSON.stringify(err)).join("; ");
      }
    } catch {
      // Keep the HTTP fallback message.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  dashboard: () => request<Dashboard>("/api/dashboard"),
  incidents: (days = 30) => request<Incident[]>(`/api/incidents?days=${days}`),
  volunteers: () => request<Volunteer[]>("/api/volunteers"),
  assignments: () => request<Assignment[]>("/api/assignments"),
  sources: () => request<Source[]>("/api/sources"),
  runs: () => request<IngestionRun[]>("/api/ingestion/runs"),
  reports: () => request<CitizenReport[]>("/api/reports"),
  scanBlueskyAuthors: (query: string) =>
    request<BlueskyScanResult>("/api/bluesky/scan", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  suggestions: (incidentId: number) =>
    request<Volunteer[]>(`/api/incidents/${incidentId}/suggestions`),
  allocationStrategies: () =>
    request<AllocationStrategyMetadata[]>("/api/allocation-strategies"),
  createVolunteer: (payload: VolunteerInput) =>
    request<Volunteer>("/api/volunteers", { method: "POST", body: JSON.stringify(payload) }),
  createAssignment: (payload: AssignmentInput) =>
    request<Assignment>("/api/assignments", { method: "POST", body: JSON.stringify(payload) }),
  distributeVolunteers: (payload: DistributionInput) =>
    request<DistributionPlan>("/api/allocations/distribute", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  claimTask: (incidentId: number, volunteerId: number, service: string) =>
    request<Assignment>(`/api/tasks/${incidentId}/claim`, {
      method: "POST",
      body: JSON.stringify({ volunteer_id: volunteerId, service }),
    }),
  submitReport: (form: FormData) =>
    request<ReportSubmission>(
      "/api/reports",
      { method: "POST", body: form, signal: AbortSignal.timeout(60_000) },
    ),
  moderateReport: (trackingId: string, decision: "approve" | "reject", reviewerName = "Volunteer reviewer") =>
    request<CitizenReport>(`/api/reports/${encodeURIComponent(trackingId)}/moderation`, {
      method: "PATCH",
      body: JSON.stringify({ decision, reviewer_name: reviewerName }),
    }),
  addGovernmentSource: (payload: GovernmentSourceInput) =>
    request<Source>("/api/sources/government", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  runIngestion: (live = false) =>
    request<IngestionRun[]>("/api/ingestion/run", {
      method: "POST",
      body: JSON.stringify({ source_ids: [], live }),
    }),
};
