export const APP_ROUTES = {
  operations: "/",
  map: "/map",
  users: "/users",
  volunteers: "/volunteers",
  safety: "/safety",
  admin: "/admin",
  blueskyHelpers: "/bluesky-helpers",
  pipeline: "/pipeline",
} as const;

const LEGACY_ALIASES: Record<string, string> = {
  "/report": APP_ROUTES.users,
  "/user": APP_ROUTES.users,
  "/volunteer": APP_ROUTES.volunteers,
  "/disaster-safety": APP_ROUTES.safety,
  "/preparedness": APP_ROUTES.safety,
};

export function normalizeAppPath(path: string): string {
  const withoutTrailingSlash = path !== "/" ? path.replace(/\/+$/, "") : path;
  return LEGACY_ALIASES[withoutTrailingSlash] ?? withoutTrailingSlash;
}
