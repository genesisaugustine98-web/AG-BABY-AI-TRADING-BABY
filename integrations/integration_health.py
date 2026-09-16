from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class IntegrationStatus:
    name: str
    configured: bool
    environment: str
    mode: str


# Presence checks only. Never print secret values.
CHECKS = {
    "github": ["GITHUB_REPOSITORY"],
    "huggingface": ["HF_TOKEN"],
    "kaggle": ["KAGGLE_USERNAME", "KAGGLE_KEY"],
    "colab": ["COLAB_ENABLED"],
    "aws": ["AWS_ROLE_ARN"],
    "vercel": ["VERCEL_TOKEN", "VERCEL_PROJECT_ID"],
    "supabase": ["SUPABASE_URL"],
    "render": ["RENDER_API_KEY", "RENDER_SERVICE_ID"],
    "digitalocean": ["DIGITALOCEAN_TOKEN"],
    "mt5_demo": ["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"],
}


def status_for(name: str) -> IntegrationStatus:
    required = CHECKS[name]
    configured = all(os.getenv(k) for k in required)
    environment = os.getenv("EXECUTION_ENV", "research")
    mode = "configured" if configured else "not_configured"
    if name == "mt5_demo" and environment != "demo":
        mode = "blocked_outside_demo"
        configured = False
    return IntegrationStatus(name, configured, environment, mode)


def main() -> int:
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": os.getenv("GITHUB_REPOSITORY", "unknown"),
        "commit_sha": os.getenv("GITHUB_SHA", "unknown"),
        "integrations": [asdict(status_for(k)) for k in CHECKS],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
