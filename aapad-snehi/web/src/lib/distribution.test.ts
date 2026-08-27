import { describe, expect, it } from "vitest";
import { distributionSelectionError, groupDistributionAllocations } from "./distribution";
import type { DistributionAllocation } from "../types";


describe("automatic distribution UI helpers", () => {
  it("requires a bounded multi-place selection and a volunteer pool", () => {
    expect(distributionSelectionError([1], [1])).toContain("at least two");
    expect(distributionSelectionError([1, 2], [])).toContain("at least one");
    expect(distributionSelectionError([1, 2], [1])).toBe("");
    expect(distributionSelectionError(Array.from({ length: 11 }, (_, index) => index), [1])).toContain("at most ten");
  });

  it("keeps selected incidents visible even when they receive no allocation", () => {
    const allocation = {
      incidentId: 1,
      volunteerId: 7,
    } as DistributionAllocation;
    const groups = groupDistributionAllocations(
      [1, 2],
      [
        { id: 1, title: "Flood", locationName: "Assam" },
        { id: 2, title: "Landslide", locationName: "Uttarakhand" },
      ],
      [allocation],
    );

    expect(groups.map((item) => item.location)).toEqual(["Assam", "Uttarakhand"]);
    expect(groups[0]?.allocations).toEqual([allocation]);
    expect(groups[1]?.allocations).toEqual([]);
  });
});
