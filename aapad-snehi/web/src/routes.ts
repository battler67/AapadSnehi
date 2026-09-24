export const APP_ROUTES = {
  flood: "/flood",
  floodReport: "/flood/report",
  operations: "/",
  map: "/map",
  users: "/flood/report",
  volunteers: "/volunteers",
  safety: "/safety",
  admin: "/admin",
  blueskyHelpers: "/bluesky-helpers",
  pipeline: "/pipeline",
  edgeEarlyWarning: "/edge-early-warning",
  mlPredictions: "/ml-predictions",
} as const;

const LEGACY_ALIASES: Record<string, string> = {
  "/users": APP_ROUTES.floodReport,
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
