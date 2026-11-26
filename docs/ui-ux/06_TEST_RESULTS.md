# Test results

25 November 2026, local Windows workspace. Baseline checks were executed before the token edit using installed binaries because pnpm 11.25.0 fails the repository's >=11.28.0 engine check; Corepack could not resolve the registry. Commands below are direct equivalents of the web scripts, not a claim that the pnpm commands passed.

- Baseline `eslint .`: passed.
- Baseline `tsc --noEmit`: passed.
- Baseline `vitest run`: 24 files, 213 tests passed.
- After token edit: `eslint .` and `tsc --noEmit` passed.
- After token edit: `next build` compiled, typechecked and generated static pages, but failed at standalone packaging with Windows `EPERM` creating a symlink. Production build therefore did not pass.
- `playwright test --list` found five tests; this is discovery only, not execution. Docker API access was denied, so the required real-stack browser flows were not run.
- Responsive visual checks, screen reader checks, contrast audit, live provider, organization-switching browser checks and widget installation verification were not run. No WCAG compliance claim is made.

The original audit and remediation tracker contain historical results with different scopes; they are not a substitute for a current regression run.
