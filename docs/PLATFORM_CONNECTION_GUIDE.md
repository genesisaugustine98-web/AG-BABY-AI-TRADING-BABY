# Platform Connection Guide

The repository is the control plane. External platforms connect to this repository; the repository does not store their secrets.

## Connection order

1. **GitHub** — already connected with repository write access.
2. **Vercel** — connect the repository through Vercel's Git integration for the research/control-plane UI. Keep deployment credentials in Vercel/GitHub secrets.
3. **Supabase** — connect the project for durable Postgres/event metadata. Apply schema changes through versioned migrations; never store database passwords in Git.
4. **Render or DigitalOcean** — use one as the long-running compute/development target. Pull from `main` and use platform-native secret storage.
5. **AWS** — prefer GitHub Actions OIDC and a narrowly scoped IAM role instead of long-lived access keys.
6. **Hugging Face** — current ChatGPT connection is authenticated with `read-repos` and `jobs` scopes. This is sufficient for public-repo reads; Hub writes require an appropriately scoped write token. HF Jobs require an eligible paid plan.
7. **Kaggle / Colab** — connect through their own notebook/runtime authentication and clone this public GitHub repository. Do not commit notebook credentials.
8. **MT5 demo gateway** — keep credentials outside Git and require positive demo-account verification before any submission.

## GitHub -> external platform rule

Each deployment or research run should pin a commit SHA rather than silently following a moving branch. Record the SHA in the integration event envelope.

## External platform -> GitHub rule

External systems should report status using `repository_dispatch` with event type `integration-status` and the schema in `schemas/integration_event.schema.json`. Only `research`, `paper`, and `demo` environments are accepted by the repository dispatch workflow; `live` events are rejected.

## Minimum secret names

See `integrations/.env.integration.example`. These are placeholders only. Real values belong in GitHub Actions secrets, cloud secret stores, Vercel/Render/Supabase secret settings, or the relevant platform's credential store.

## Security boundary

Research/model-training/UI platforms must not receive broker execution credentials. The execution gateway remains a separate trust zone. The LLM remains outside direct execution authority.

## Current connection truth

- GitHub: connected and writable.
- Hugging Face: authenticated; current OAuth scopes include `read-repos` and `jobs`.
- Vercel/Supabase/Render/DigitalOcean: connector options are available but require the user to authorize/install them before they can be reported as connected.
- AWS/Kaggle/Colab: no direct account credential has been supplied through this workspace; repository-side integration contracts are prepared.
