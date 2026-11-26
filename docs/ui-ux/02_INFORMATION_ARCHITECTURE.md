# Information architecture

Organization context is the boundary for all workspace routes. Preserve existing URLs, permission checks and organization switching semantics.

- Workspace: Overview; Chatbots (list, create, editor including test and install); Knowledge (chatbot-scoped documents, websites and retrieval); Conversations (explicitly unavailable inbox); Analytics (unavailable).
- Organization: Team, Settings, Billing (unavailable).
- Account: profile and sessions; authentication and invitation routes outside the workspace.

The primary journey is create a draft chatbot → add and index knowledge → test with sources → configure verified origin and install → activate. Knowledge is attached after creation, not to an unsaved object. Checklist completion must rely on available server state. A successful upload is not equivalent to indexing. Keep restrictions and errors visible and preserve backend authorization as the authority.

The navigation must distinguish current functionality from future work. The playground may show only actual citation and usage data; the demo fixture must remain identified as such. Do not imply analytics, inbox, channels or billing exist.
