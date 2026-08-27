import { describe, expect, it } from "vitest";
import { APP_ROUTES, normalizeAppPath } from "./routes";

describe("audience routes", () => {
  it("keeps each audience on a distinct canonical path", () => {
    expect(new Set([APP_ROUTES.users, APP_ROUTES.volunteers, APP_ROUTES.safety, APP_ROUTES.admin, APP_ROUTES.blueskyHelpers]).size).toBe(5);
    expect(APP_ROUTES.users).toBe("/users");
    expect(APP_ROUTES.volunteers).toBe("/volunteers");
    expect(APP_ROUTES.safety).toBe("/safety");
    expect(APP_ROUTES.admin).toBe("/admin");
    expect(APP_ROUTES.blueskyHelpers).toBe("/bluesky-helpers");
  });

  it("normalizes trailing slashes and legacy public links", () => {
    expect(normalizeAppPath("/users/")).toBe(APP_ROUTES.users);
    expect(normalizeAppPath("/report")).toBe(APP_ROUTES.users);
    expect(normalizeAppPath("/user/")).toBe(APP_ROUTES.users);
    expect(normalizeAppPath("/volunteer")).toBe(APP_ROUTES.volunteers);
    expect(normalizeAppPath("/disaster-safety")).toBe(APP_ROUTES.safety);
    expect(normalizeAppPath("/safety/")).toBe(APP_ROUTES.safety);
  });
});
