# Disaster safety page styling

## Scope

- Branch: `feature/disaster-safety-styling`, created from the current
  `feature/rbac-authentication` commit without advancing or editing that branch.
- Restyle only the disaster safety page and its page-specific CSS.
- Preserve the existing safety video data, category/search/Hindi filters, featured
  player, emergency contacts, checklist, modal playback, routes, and navigation.
- Do not edit login, signup, authentication state, role handling, auth UI, or backend
  authentication code. Existing unrelated working-tree edits remain uncommitted.

## Design direction

- Use the repository's existing navy glass-panel system, cyan/violet accents,
  operational typography, spacing scale, and responsive breakpoints.
- Make emergency contacts immediately scannable without allowing them to overpower
  the educational content.
- Establish a clear sequence: safety status and contacts, featured official guide,
  searchable guide library, then actionable do/don't checklists.
- Replace inactive Tailwind utility strings with explicit, page-scoped CSS; do not
  add Tailwind or alter global component styling.
- Preserve keyboard focus states, descriptive labels, reduced-motion behavior, and
  mobile layouts down to 320px.

## Verification

- TypeScript check and Vite production build.
- Existing frontend tests.
- Inspect the rendered desktop and mobile safety routes if the local preview tooling
  is available.
- Confirm Git diff contains no edits to authentication files.

## Implementation record

- Rebuilt the page markup around semantic, page-scoped `safety-*` classes and the
  existing design tokens; no new styling dependency was introduced.
- Added a responsive preparedness hero, tappable emergency helplines, featured
  guide presentation, filter/search controls, guide cards, emergency checklists,
  and an accessible video dialog with Escape-key dismissal.
- Retained all seven official video records and the existing filtering, playback,
  checklist, and external-link behavior.
- Inspected the rendered `/safety` route in headless Edge at desktop and narrow
  viewport sizes.
- Verification completed on 2026-08-22: `npm test` passed 9 tests across 4 files;
  `npm run build` passed TypeScript checking and the Vite production build.
- Only `SafetyPage.tsx`, its page-scoped additions in `styles.css`, and this record
  are included in the implementation commit. Existing authentication and route
  working-tree edits were not staged.
