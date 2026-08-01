#!/usr/bin/env python3
"""One-time setup: install deps, Playwright browsers, config dirs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    print("Setting up Event Concierge...\n")

    venv = PROJECT_ROOT / ".venv"
    if not venv.exists():
        print("Creating virtual environment...")
        for py in ("python3.12", "python3.11", sys.executable):
            try:
                subprocess.run([py, "-m", "venv", str(venv)], check=True)
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        else:
            raise RuntimeError("Could not create virtual environment")

    pip = venv / "bin" / "pip"
    python = venv / "bin" / "python"

    print("Installing dependencies...")
    subprocess.run([str(pip), "install", "-e", str(PROJECT_ROOT)], check=True)

    print("Installing Playwright browsers...")
    subprocess.run([str(python), "-m", "playwright", "install", "chromium"], check=True)

    config_dir = Path.home() / ".config/event-concierge"
    config_dir.mkdir(parents=True, exist_ok=True)

    env_example = PROJECT_ROOT / ".env.example"
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists() and env_example.exists():
        env_file.write_text(env_example.read_text())
        print(f"Created .env from template — edit with your credentials")

    data_dirs = ["processed", "sessions", "briefings", "state"]
    for d in data_dirs:
        (PROJECT_ROOT / "data" / d).mkdir(parents=True, exist_ok=True)

    print("\n✅ Setup complete!\n")
    print("Next steps:")
    print("  1. Edit .env with your name, email, and API keys")
    print("  2. Edit config/profile.yaml with your LinkedIn details")
    print("  3. Run: .venv/bin/event-concierge linkedin login")
    print("  4. Run: .venv/bin/event-concierge gmail auth")
    print("  5. Run: .venv/bin/event-concierge scan --dry-run")


if __name__ == "__main__":
    main()
