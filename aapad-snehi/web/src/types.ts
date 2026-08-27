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
  matchedTerms: string[];
  capabilities: string[];
}

export interface BlueskyScanResult {
  query: string;
  scannedCount: number;
  matchCount: number;
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
