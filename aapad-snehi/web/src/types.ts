export type VerificationStatus = "official" | "corroborated" | "community_reviewed" | "ai_screened" | "unverified";
export type ReportModerationStatus = "accepted" | "rejected" | "needs_volunteer_review" | "community_approved";
export interface PriorityBreakdown {
  severity: number;
  recency: number;
  affected: number;
  needs: number;
  trust: number;
  coverageGap: number;
}

export interface Incident {
  id: number;
  externalId: string;
  title: string;
  description: string;
  disasterType: string;
  severity: number;
  intensity: "critical" | "high" | "medium" | "low";
  latitude: number;
  longitude: number;
  locationName: string;
  occurredAt: string;
  sourceKind: string;
  verificationStatus: VerificationStatus;
  sourceName: string;
  sourceAuthority: string;
  sourceUrl: string;
  affectedEstimate: number;
  needs: string[];
  priorityScore: number;
  priorityBreakdown: PriorityBreakdown;
  responseCoverage: number;
  assignmentCount: number;
  active: boolean;
}

export interface CitizenReport {
  id: number;
  trackingId: string;
  moderationStatus: ReportModerationStatus;
  aiCaption: string;
  aiDecision: "accepted" | "rejected" | "needs_volunteer_review";
  aiReason: string;
  aiModel: string;
  aiProvider: string;
  aiPromptVersion: string;
  aiAnalysis: {
    disasterEvidence?: "yes" | "no" | "unclear";
    hazards?: string[];
    observations?: string[];
  };
  reviewedBy: string;
  reviewedAt: string | null;
  createdAt: string;
  imageAvailable: boolean;
  imageUrl: string;
  incident: Incident;
}

export interface ReportSubmission {
  trackingId: string;
  moderationStatus: "accepted" | "rejected" | "needs_volunteer_review";
  message: string;
  caption: string;
  triageReason: string;
  incident: Incident;
}

export interface Volunteer {
  id: number;
  name: string;
  phone: string;
  email: string;
  homeLocation: string;
  preferredPlaces: string[];
  latitude: number;
  longitude: number;
  services: string[];
  skills: string[];
  languages: string[];
  availability: string;
  verified: boolean;
  completedMissions: number;
  fitScore?: number;
  fitBreakdown?: Record<string, number>;
}

export interface Assignment {
  id: number;
  incidentId: number;
  incidentTitle: string;
  volunteerId: number;
  volunteerName: string;
  service: string;
  status: string;
  note: string;
  assignedBy: string;
  assignedAt: string;
  acceptedAt: string | null;
}

export interface Source {
  id: number;
  slug: string;
  name: string;
  adapterType: string;
  endpoint: string;
  authority: string;
  sourceKind: string;
  enabled: boolean;
  status: string;
  lastRunAt: string | null;
  lastError: string;
}

export interface IngestionRun {
  id: number;
  sourceId: number;
  sourceName: string;
  status: string;
  fetchedCount: number;
  acceptedCount: number;
  duplicateCount: number;
  rejectedCount: number;
  error: string;
  startedAt: string;
  completedAt: string | null;
}

export interface BlueskyAuthorMatch {
  id: string;
  handle: string;
  displayName: string;
  postUri: string;
  postUrl: string;
  postText: string;
  postedAt: string;
  disasterType: string;
  disasterContext: "post" | "query";
  intentCategory: "explicit_offer" | "active_assistance" | "institutional_support" | "fundraising_or_donation";
  confidence: "high" | "medium" | "low";
  matchedTerms: string[];
  capabilities: string[];
  sentiment: {
    label: "positive" | "neutral" | "negative" | "unavailable";
    score: number | null;
    model: string;
    status: "available" | "disabled" | "needs_config" | "provider_error" | "invalid_response" | "limit_reached" | "unavailable";
  };
}

export interface BlueskyScanResult {
  query: string;
  scannedCount: number;
  matchCount: number;
  sentimentSummary: Record<"positive" | "neutral" | "negative" | "unavailable", number>;
  authors: BlueskyAuthorMatch[];
}

export interface Dashboard {
  mode: string;
  metrics: {
    activeIncidents: number;
    highPriority: number;
    availableVolunteers: number;
    activeAssignments: number;
  };
  priorityIncidents: Incident[];
  externalIncidents: Incident[];
  sources: Source[];
}

export interface VolunteerInput {
  name: string;
  phone: string;
  email: string;
  home_location: string;
  preferred_places: string[];
  latitude: number;
  longitude: number;
  services: string[];
  skills: string[];
  languages: string[];
  availability: string;
}

export interface AssignmentInput {
  incident_id: number;
  volunteer_id: number;
  service: string;
  note: string;
}

export interface DistributionInput {
  incident_ids: number[];
  volunteer_ids: number[];
  strategy: string;
  commit: boolean;
  preview_token: string;
  note: string;
}

export interface AllocationStrategyMetadata {
  key: string;
  name: string;
  version: string;
  summary: string;
  bestFor: string;
}

export interface DistributionAllocation {
  incidentId: number;
  incidentTitle: string;
  incidentLocation: string;
  volunteerId: number;
  volunteerName: string;
  service: string;
  fitScore: number;
  allocationScore: number;
  breakdown: Record<string, number>;
}

export interface DistributionPlan {
  previewToken: string;
  strategy: AllocationStrategyMetadata;
  committed: boolean;
  summary: {
    selectedVolunteers: number;
    allocatedVolunteers: number;
    unassignedVolunteers: number;
    coveredIncidents: number;
  };
  allocations: DistributionAllocation[];
  unassigned: Array<{
    volunteerId: number;
    volunteerName: string;
    reason: string;
  }>;
  assignments: Assignment[];
}

export interface GovernmentSourceInput {
  name: string;
  authority: string;
  endpoint: string;
  enabled: boolean;
}

export type EdgeHazard = "flood" | "landslide" | "tsunami";
export type EdgeRiskState = "NORMAL" | "WATCH" | "WARNING" | "CRITICAL" | "RECOVERY";

export interface EdgeDevice {
  deviceId: string;
  name: string;
  deviceType: "river_gauge" | "hillslope_station" | "coastal_buoy";
  installedPurposes: EdgeHazard[];
  capabilities: string[];
  regionId: string;
  location: { latitude: number; longitude: number; elevationM: number | null };
  expectedIntervalSeconds: number;
  simulationOnly: boolean;
  status: string;
  lastSeenAt: string | null;
  lastEventAt: string | null;
  batteryPct: number;
  signalQualityPct: number;
  trustScore: number;
}

export interface EdgeRiskAssessment {
  assessmentId: number;
  deviceId: string;
  hazard: EdgeHazard;
  asOf: string;
  probability: number;
  riskLevel: EdgeRiskState;
  confidence: number;
  modelVersion: string;
  modelStatus: string;
  topContributors: Array<{ feature: string; contribution: number }>;
  dataQuality: number;
  ruleScore: number;
  classifierProbability: number | null;
  anomalyScore: number;
  nearbyAgreement: number;
  simulated: true;
}

export interface EdgeRiskEvent {
  id: number;
  notice: "SIMULATED / DEMO ONLY";
  hazard: EdgeHazard;
  regionId: string;
  state: EdgeRiskState;
  probability: number;
  confidence: number;
  dataQuality: number;
  contributingDeviceIds: string[];
  simulated: true;
  active: boolean;
  reviewStatus: string;
  incidentId: number | null;
  firstSeenAt: string;
  lastTransitionAt: string;
  updatedAt: string;
  evidence?: Record<string, unknown>;
  transitions?: Array<{ id: number; fromState: EdgeRiskState; toState: EdgeRiskState; reason: string; probability: number; confidence: number; transitionedAt: string }>;
}

export interface EdgeSimulationRun {
  runId: string;
  scenario: string;
  region: string;
  status: string;
  cursorStep: number;
  totalSteps: number;
  emittedCount: number;
  rejectedCount: number;
  error: string;
}

export interface EdgeSnapshot {
  notice: string;
  cursor: string;
  transport: "polling";
  suggestedPollSeconds: number;
  devices: EdgeDevice[];
  risks: EdgeRiskAssessment[];
  events: EdgeRiskEvent[];
  simulations: EdgeSimulationRun[];
}

export interface EdgeCatalog {
  notice: string;
  schemaVersion: string;
  scenarios: Array<{ id: string; label: string; hazard: EdgeHazard | null; durationSteps: number }>;
  regions: Array<{ id: string; name: string; latitude: number; longitude: number }>;
  profiles: Record<string, { purposes: EdgeHazard[]; capabilities: string[] }>;
  properties: Record<string, { unit: string; min: number; max: number; warning?: number }>;
}

export interface MLFeatureDefinition {
  name: string;
  label: string;
  type: "number" | "string" | "number_grid" | "integer_grid";
  unit: string;
  minimum: number | null;
  maximum: number | null;
  shape?: [number, number];
  helperText: string;
  required: boolean;
  group: string;
}

export interface MLModelInfo {
  id: string;
  name: string;
  disaster: "flood" | "wildfire";
  target: string;
  description: string;
  version: string;
  inputMode: "engineered_row" | "spatial_grid";
  features: MLFeatureDefinition[];
  supportedOutput: string;
  limitations: string[];
  scenarios: Array<{ id: string; label: string; description: string }>;
  availability: { available: boolean; status: string; detail: string; sha256?: string };
  operationallyValidated: false;
}

export interface MLModelCatalog {
  apiVersion: string;
  notice: string;
  models: MLModelInfo[];
  unavailableModels: Array<{ id: string; reason: string }>;
  supportedSources: string[];
  futureSources: string[];
}

export interface MLSyntheticScenario {
  source: "synthetic";
  scenarioId: string;
  synthetic: true;
  features: Record<string, unknown>;
  unitsConfirmed: true;
  notes: string[];
}

export interface MLPredictionRequest {
  modelId: string;
  source: "manual" | "synthetic";
  features: Record<string, unknown>;
  unitsConfirmed: boolean;
}

export interface MLPredictionResult {
  status: "prediction";
  modelId: string;
  modelName: string;
  modelVersion: string;
  target: string;
  source: string;
  synthetic: boolean;
  predictionTime: string;
  horizon: string;
  predictedOutcome: string;
  confidence: number | null;
  riskLevel: string;
  classProbabilities: Record<string, number> | null;
  inputDataUsed: Record<string, unknown>;
  outputDetails: {
    dischargeM3S?: number;
    highFlowScore?: number;
    validationAlertCutoff?: number;
    reviewFlag?: boolean;
    scoreMap?: number[][];
    scoreSummary?: { minimum: number; maximum: number; mean: number };
    cellsAboveCutoff?: number;
    newlyActiveCandidateCells?: number;
    scoreMeaning?: string;
    uncertainty?: string;
  };
  validationWarnings: string[];
  limitations: string[];
  operationallyValidated: false;
  inferenceTimeMs: number;
}
