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
  EdgeCatalog,
  EdgeRiskEvent,
  EdgeSimulationRun,
  EdgeSnapshot,
  MLModelCatalog,
  MLPredictionRequest,
  MLPredictionResult,
  MLSyntheticScenario,
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
    if (error instanceof DOMException && (error.name === "TimeoutError" || error.name === "AbortError")) {
      throw new ApiError("The hosted service took too long to respond. It may be waking from sleep; please retry.");
    }
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
      signal: AbortSignal.timeout(60_000),
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
  edgeCatalog: () => request<EdgeCatalog>("/api/edge/catalog"),
  edgeSnapshot: () => request<EdgeSnapshot>("/api/edge/snapshot"),
  edgeDeviceHistory: (deviceId: string, limit = 90) =>
    request<Array<{ timestamp: string; measurements: Record<string, { value: number; unit: string }> }>>(
      `/api/edge/devices/${encodeURIComponent(deviceId)}/observations?limit=${limit}`,
    ),
  startEdgeSimulation: (payload: { scenario: string; numberOfDevices: number; seed: number; region: string; speedMultiplier: number; timestepSeconds: number }) =>
    request<EdgeSimulationRun>("/api/edge/simulations", { method: "POST", body: JSON.stringify(payload) }),
  controlEdgeSimulation: (runId: string, action: "pause" | "resume" | "stop" | "reset") =>
    request<EdgeSimulationRun>(`/api/edge/simulations/${encodeURIComponent(runId)}/${action}`, { method: "POST" }),
  edgeEvent: (eventId: number) => request<EdgeRiskEvent>(`/api/edge/events/${eventId}`),
  mlModels: () => request<MLModelCatalog>("/api/v1/ml/models", { signal: AbortSignal.timeout(120_000) }),
  mlHealth: () => request<{ status: string; models: Record<string, { available: boolean; status: string; detail: string }>; loadedModelIds: string[] }>("/api/v1/ml/health", { signal: AbortSignal.timeout(30_000) }),
  mlScenario: (modelId: string, scenarioId: string) =>
    request<MLSyntheticScenario>(`/api/v1/ml/models/${encodeURIComponent(modelId)}/scenarios/${encodeURIComponent(scenarioId)}`, { signal: AbortSignal.timeout(60_000) }),
  mlPredict: (payload: MLPredictionRequest) =>
    request<MLPredictionResult>("/api/v1/ml/predict", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(120_000),
    }),
  reviewEdgeEvent: (eventId: number, action: "acknowledge" | "promote_to_incident" | "dismiss", reviewerName: string, confirmDemoOnly = false) =>
    request<EdgeRiskEvent>(`/api/edge/events/${eventId}/review`, {
      method: "POST",
      body: JSON.stringify({ action, reviewerName, confirmDemoOnly, note: "Reviewed in the Edge Early Warning demo console" }),
    }),
};
