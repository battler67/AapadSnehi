import type { DistributionAllocation, Incident } from "../types";


export function distributionSelectionError(incidentIds: number[], volunteerIds: number[]): string {
  if (incidentIds.length < 2) return "Select at least two disaster places to distribute across.";
  if (incidentIds.length > 10) return "Select at most ten incidents per distribution run.";
  if (!volunteerIds.length) return "Select at least one currently available volunteer.";
  if (volunteerIds.length > 50) return "Select at most fifty volunteers per distribution run.";
  return "";
}


export function groupDistributionAllocations(
  incidentIds: number[],
  incidents: Array<Pick<Incident, "id" | "title" | "locationName">>,
  allocations: DistributionAllocation[],
) {
  return incidentIds.map((id) => {
    const incident = incidents.find((item) => item.id === id);
    return {
      id,
      title: incident?.title || `Incident ${id}`,
      location: incident?.locationName || "",
      allocations: allocations.filter((item) => item.incidentId === id),
    };
  });
}
