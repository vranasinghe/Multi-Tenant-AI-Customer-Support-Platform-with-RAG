# Current state audit

Baseline: 25 November 2026. This is a source and existing-evidence audit, not a new production certification. Existing working-tree changes predate this work. No walkthrough video was found in the repository inventory. Prior browser evidence is in `docs/audit/evidence/`; it is historical and does not establish the current tree's visual state.

## Screens and capabilities

| Surface | Classification | Evidence and qualification |
| --- | --- | --- |
| Login, signup, verification, reset, invitations | Implemented and verified | Components and tests exist; historical local identity checks in `docs/audit/04_FUNCTIONAL_TEST_RESULTS.md`. Current browser run pending. |
| Organization creation, switching, settings, members, account | Implemented and verified | Existing guards, permission helpers and component tests; historical local role/tenant tests. Full current role matrix pending. |
| Overview | Implemented but not verified | API-backed overview component exists; current working tree has pre-existing modifications and has not been visually reviewed in this session. |
| Chatbot list, creation and editor | Implemented and verified | Historical fixture CRUD and browser flows; current wizard has five steps and creates before knowledge attachment. Current end-to-end rerun pending. |
| Documents, websites, reindex and retrieval test | Implemented and verified | Historical local ingestion/retrieval checks and components; real semantic provider quality remains unverified. Limits come from the API. |
| Playground, streaming, citations, feedback | Partially implemented | Local fixture transport and persistence were exercised historically; real AI quality, semantic citation correctness and refusal remain blocked on provider evaluation. |
| Widget preview, domain verification and installation | Partially implemented | Historical local embed and mobile checks; repeat initialization/teardown gap AUD-07 remains. Preview fidelity needs current verification. |
| Conversation inbox | Placeholder | Hardcoded empty state and disabled filters; persisted conversations exist elsewhere. Copy currently implies records will appear here, which is misleading. |
| Analytics and billing | Placeholder | Routes exist and label future functionality; no live metrics or billing should be invented. |
| Messaging channels | Not implemented | No corresponding application route in the inspected inventory; roadmap is not shipped functionality. |
| Dark theme | Partially implemented | Shared `.dark` tokens exist; no theme switch or comprehensive contrast validation established. |
| Responsive and accessibility coverage | Partially implemented | Mobile drawer, focus states and reduced motion exist; historical audit explicitly did not establish full WCAG/assistive technology coverage. |

## Architecture and risks

Next.js 16/React 19 web app, Tailwind 4 and shared `@acs/ui` primitives; Vite widget; FastAPI backend. API mirrors live in `apps/web/src/lib/api/types.ts`, calls in `lib/api`, guards in `components/auth/guards.tsx` and permissions in `lib/orgs.ts`. Knowledge workspace is keyed by chatbot; preserve that and organization scoping. Browser tests use a real local stack and Mailpit, not mocks. Unit tests use Vitest. Existing shared primitives include button, input, select, dialog, tabs, badges and skeletons; web kit adds toast and common states.

`docs/mvp-improvement/02_PROGRESS_TRACKER.md` supersedes the original audit for local remediation status: AUD-01 through AUD-03 have local validation; AUD-04 proxy trust, AUD-05 parser isolation, AUD-06 inbox and AUD-07 widget lifecycle remain. Overall MVP readiness remains NOT READY. UI work does not close these findings. `docs/CHAT_ENGINE.md` identifies demo output as a canned transport fixture and describes SSE and source boundaries; `docs/WIDGET_DEPLOYMENT.md` describes verified origins and public widget protocol.

## Baseline environment

Node 24.16.0 is available. The installed pnpm is 11.25.0; project requires 11.28.12 and Corepack could not resolve the registry. Direct installed binaries can provide partial checks; these are recorded separately. No current live-stack or visual validation is claimed.
