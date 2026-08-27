import { describe, expect, it } from "vitest";
import { demoBlueskyAuthors, demoIncidents, demoSources, demoVolunteers } from "./demo";

describe("deterministic demonstration data", () => {
  it("keeps priority incidents ordered and score factors visible", () => {
    const scores = demoIncidents.map((incident) => incident.priorityScore);
    expect(scores).toEqual([...scores].sort((a, b) => b - a));
    expect(Object.keys(demoIncidents[0]!.priorityBreakdown)).toEqual([
      "severity",
      "recency",
      "affected",
      "needs",
      "trust",
      "coverageGap",
    ]);
  });

  it("does not label community evidence as official", () => {
    const community = demoIncidents.find((incident) => incident.sourceKind === "community");
    expect(community?.verificationStatus).toBe("unverified");
    expect(demoSources.some((source) => source.adapterType === "government")).toBe(true);
    expect(demoSources.some((source) => source.adapterType === "gdelt")).toBe(true);
    expect(demoSources.some((source) => source.adapterType === "sachet")).toBe(true);
    expect(demoSources.some((source) => source.adapterType === "bluesky" && source.sourceKind === "social")).toBe(true);
  });

  it("gives every demonstration volunteer preferred work areas", () => {
    expect(demoVolunteers).toHaveLength(12);
    expect(demoVolunteers.every((volunteer) => volunteer.preferredPlaces.length > 0)).toBe(true);
    expect(demoVolunteers.every((volunteer) => volunteer.preferredPlaces.length <= 5)).toBe(true);
  });

  it("uses unmistakably non-resolving IDs for sample Bluesky authors", () => {
    expect(demoBlueskyAuthors).toHaveLength(3);
    expect(demoBlueskyAuthors.every((author) => author.id.startsWith("did:example:"))).toBe(true);
    expect(demoBlueskyAuthors.every((author) => author.handle.endsWith(".invalid"))).toBe(true);
  });
});
