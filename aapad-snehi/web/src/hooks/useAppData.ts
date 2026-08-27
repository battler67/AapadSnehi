import { useCallback, useEffect, useMemo, useState } from "react";
import { demoAssignments, demoDashboard, demoIncidents, demoRuns, demoSources, demoVolunteers } from "../data/demo";
import { api } from "../lib/api";
import type {
  Assignment,
  AssignmentInput,
  CitizenReport,
  Dashboard,
  DistributionInput,
  GovernmentSourceInput,
  Incident,
  IngestionRun,
  Source,
  Volunteer,
  VolunteerInput,
} from "../types";

export function useAppData() {
  const [dashboard, setDashboard] = useState<Dashboard>(demoDashboard);
  const [incidents, setIncidents] = useState<Incident[]>(demoIncidents);
  const [volunteers, setVolunteers] = useState<Volunteer[]>(demoVolunteers);
  const [assignments, setAssignments] = useState<Assignment[]>(demoAssignments);
  const [sources, setSources] = useState<Source[]>(demoSources);
  const [runs, setRuns] = useState<IngestionRun[]>(demoRuns);
  const [reports, setReports] = useState<CitizenReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [connection, setConnection] = useState<"api" | "demo">("demo");

  const reload = useCallback(async () => {
    try {
      const [nextDashboard, nextIncidents, nextVolunteers, nextAssignments, nextSources, nextRuns, nextReports] =
        await Promise.all([
          api.dashboard(),
          api.incidents(365),
          api.volunteers(),
          api.assignments(),
          api.sources(),
          api.runs(),
          api.reports(),
        ]);
      setDashboard(nextDashboard);
      setIncidents(nextIncidents);
      setVolunteers(nextVolunteers);
      setAssignments(nextAssignments);
      setSources(nextSources);
      setRuns(nextRuns);
      setReports(nextReports);
      setConnection("api");
    } catch {
      setConnection("demo");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const createVolunteer = useCallback(async (payload: VolunteerInput) => {
    try {
      const created = await api.createVolunteer(payload);
      setVolunteers((current) => [...current, created]);
      setConnection("api");
      return created;
    } catch {
      const local: Volunteer = {
        id: Date.now(),
        name: payload.name,
        phone: payload.phone,
        email: payload.email,
        homeLocation: payload.home_location,
        preferredPlaces: payload.preferred_places,
        latitude: payload.latitude,
        longitude: payload.longitude,
        services: payload.services,
        skills: payload.skills,
        languages: payload.languages,
        availability: payload.availability,
        verified: false,
        completedMissions: 0,
      };
      setVolunteers((current) => [...current, local]);
      setConnection("demo");
      return local;
    }
  }, []);

  const createAssignment = useCallback(async (payload: AssignmentInput) => {
    try {
      const created = await api.createAssignment(payload);
      setAssignments((current) => [created, ...current]);
      setConnection("api");
      return created;
    } catch {
      const incident = incidents.find((item) => item.id === payload.incident_id);
      const volunteer = volunteers.find((item) => item.id === payload.volunteer_id);
      if (!incident || !volunteer) throw new Error("Select a valid incident and volunteer");
      const local: Assignment = {
        id: Date.now(),
        incidentId: incident.id,
        incidentTitle: incident.title,
        volunteerId: volunteer.id,
        volunteerName: volunteer.name,
        service: payload.service,
        status: "assigned",
        note: payload.note,
        assignedBy: "Local demonstration",
        assignedAt: new Date().toISOString(),
        acceptedAt: null,
      };
      setAssignments((current) => [local, ...current]);
      setConnection("demo");
      return local;
    }
  }, [incidents, volunteers]);

  const claimTask = useCallback(async (incidentId: number, volunteerId: number, service: string) => {
    try {
      const created = await api.claimTask(incidentId, volunteerId, service);
      setAssignments((current) => [created, ...current]);
      return created;
    } catch {
      const incident = incidents.find((item) => item.id === incidentId);
      const volunteer = volunteers.find((item) => item.id === volunteerId);
      if (!incident || !volunteer) throw new Error("Unable to claim this mission");
      const local: Assignment = {
        id: Date.now(), incidentId, incidentTitle: incident.title, volunteerId,
        volunteerName: volunteer.name, service, status: "claimed", note: "",
        assignedBy: "Volunteer self-claim", assignedAt: new Date().toISOString(),
        acceptedAt: new Date().toISOString(),
      };
      setAssignments((current) => [local, ...current]);
      return local;
    }
  }, [incidents, volunteers]);

  const distributeVolunteers = useCallback(async (payload: DistributionInput) => {
    const plan = await api.distributeVolunteers(payload);
    if (plan.committed) await reload();
    return plan;
  }, [reload]);

  const runPipeline = useCallback(async () => {
    try {
      const next = await api.runIngestion(dashboard.mode === "live-enabled");
      setRuns((current) => [...next, ...current].slice(0, 30));
      await reload();
      return next;
    } catch {
      const now = new Date().toISOString();
      const next: IngestionRun[] = demoSources.map((source, index) => ({
        id: Date.now() + index,
        sourceId: source.id,
        sourceName: source.name,
        status: source.adapterType === "seed" ? "success" : "skipped",
        fetchedCount: source.adapterType === "seed" ? 3 : 0,
        acceptedCount: 0,
        duplicateCount: source.adapterType === "seed" ? 3 : 0,
        rejectedCount: 0,
        error: source.adapterType === "seed" ? "" : "Live ingestion disabled for this run",
        startedAt: now,
        completedAt: now,
      }));
      setRuns((current) => [...next, ...current].slice(0, 30));
      return next;
    }
  }, [dashboard.mode, reload]);

  const addGovernmentSource = useCallback(async (payload: GovernmentSourceInput) => {
    try {
      const created = await api.addGovernmentSource(payload);
      setSources((current) => [...current, created]);
      return created;
    } catch {
      const host = new URL(payload.endpoint).hostname;
      const allowed = ["mausam.imd.gov.in", "api.imd.gov.in", "cap-sources.s3.amazonaws.com", "sachet.ndma.gov.in", "ndma.gov.in"];
      if (!allowed.some((item) => host === item || host.endsWith(`.${item}`)) || !payload.endpoint.startsWith("https://")) {
        throw new Error("Use an approved HTTPS government host");
      }
      const local: Source = {
        id: Date.now(), slug: `government-${Date.now()}`, name: payload.name,
        adapterType: "government", endpoint: payload.endpoint, authority: payload.authority,
        sourceKind: "official", enabled: payload.enabled, status: "ready", lastRunAt: null, lastError: "",
      };
      setSources((current) => [...current, local]);
      return local;
    }
  }, []);

  const moderateReport = useCallback(async (trackingId: string, decision: "approve" | "reject", reviewerName = "Volunteer reviewer") => {
    const updated = await api.moderateReport(trackingId, decision, reviewerName);
    setReports((current) => current.map((item) => item.trackingId === trackingId ? updated : item));
    await reload();
    return updated;
  }, [reload]);

  const metrics = useMemo(() => ({
    activeIncidents: incidents.filter((item) => item.active).length,
    highPriority: incidents.filter((item) => item.severity >= 4).length,
    availableVolunteers: volunteers.filter((item) => item.availability === "available").length,
    activeAssignments: assignments.filter((item) => ["assigned", "accepted", "claimed"].includes(item.status)).length,
  }), [assignments, incidents, volunteers]);

  return {
    dashboard: { ...dashboard, metrics }, incidents, volunteers, assignments, sources, runs, reports,
    loading, connection, reload, createVolunteer, createAssignment, claimTask, distributeVolunteers, runPipeline,
    addGovernmentSource, moderateReport,
  };
}

export type AppData = ReturnType<typeof useAppData>;
