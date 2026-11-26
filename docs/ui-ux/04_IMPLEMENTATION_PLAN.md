# Implementation plan

1. Establish baseline and document source truth, existing changes and evidence limitations. Preserve all uncommitted work. Use a dedicated branch.
2. Foundation: align semantic theme tokens and shared primitive states, preserving class names and public component APIs; check contrast and reduced motion. Avoid changing business logic or widget protocol.
3. Shell and overview: preserve org identity, permissions and data resets; use only actual API data and honest unavailable states.
4. Chatbot list, wizard and editor: preserve validation, update payloads, lifecycle and unsaved-change warnings. Guide knowledge attachment after creation.
5. Knowledge, playground and installation: preserve per-bot scoping, indexing distinction, SSE, provenance and verified-origin rules. Validate real preview fidelity.
6. Team, account and auth: retain role guards and session behavior. Clarify restricted actions.
7. Responsive, keyboard and accessibility review at 375, 768, 1280 and 1440 pixels, followed by regression checks and evidence reports. No fabricated metrics or placeholder controls.

Each phase is independently reviewable and requires applicable lint, types, tests and visual checks. Real-stack Playwright needs API, database, Redis and Mailpit; real-provider evaluation and production assurance are separate gates. Keep backend feature expansion and deployment out of scope.
