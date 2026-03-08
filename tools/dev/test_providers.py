#!/usr/bin/env python3
"""
Test all configured LLM providers using the existing ProviderManager.

This script:
- Loads .env from the project root into os.environ
- Normalizes legacy env var names to what the router expects
- Uses ProviderManager.test_provider for each entry in PROVIDER_REGISTRY
- Prints a JSON summary to stdout
"""

import json
import os
import sys
from pathlib import Path


def load_env_from_file(env_path: Path) -> None:
    """Minimal .env loader (no external deps)."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val:
            os.environ[key] = val


def main() -> None:
    # Resolve project root (two levels up from tools/dev)
    here = Path(__file__).resolve()
    root = here.parents[2]

    # Load .env from project root
    load_env_from_file(root / ".env")

    # Normalize legacy/alt env var names so the router can see them
    if "TOGETHER_API_KEY" in os.environ and "TOGETHERAI_API_KEY" not in os.environ:
        os.environ["TOGETHERAI_API_KEY"] = os.environ["TOGETHER_API_KEY"]
    if "PERPLEXITY_API_KEY" in os.environ and "PERPLEXITYAI_API_KEY" not in os.environ:
        os.environ["PERPLEXITYAI_API_KEY"] = os.environ["PERPLEXITY_API_KEY"]

    # Add src/services to sys.path so we can import providers
    services_dir = root / "src" / "services"
    sys.path.insert(0, str(services_dir))

    try:
        from providers import ProviderManager  # type: ignore
        from providers.router import PROVIDER_REGISTRY  # type: ignore
    except Exception as exc:  # pragma: no cover - dev helper
        print(
            json.dumps(
                {
                    "error": f"Failed to import providers: {exc}",
                },
                indent=2,
            )
        )
        sys.exit(1)

    pm = ProviderManager()
    results = []

    for env_var, model, group, display_name in PROVIDER_REGISTRY:
        key = os.environ.get(env_var, "")
        configured = bool(key and "your-" not in key)
        if not configured:
            results.append(
                {
                    "env_var": env_var,
                    "model": model,
                    "display_name": display_name,
                    "group": group,
                    "configured": False,
                    "success": False,
                    "message": "No key configured",
                }
            )
            continue

        test = pm.test_provider(model)
        results.append(
            {
                "env_var": env_var,
                "model": model,
                "display_name": display_name,
                "group": group,
                "configured": True,
                "success": bool(test.get("success")),
                "message": str(test.get("message", ""))[:200],
            }
        )

    summary = {
        "total_providers": len(results),
        "configured_providers": sum(1 for r in results if r["configured"]),
        "working_providers": sum(1 for r in results if r["configured"] and r["success"]),
        "results": results,
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

