import os
import subprocess
import sys
from pathlib import Path


def test_development_settings_trust_documented_browser_origins():
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.development",
        "SENTRY_DSN": "",
    }
    script = """
from django.conf import settings

expected = {
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
}
assert expected <= set(settings.CORS_ALLOWED_ORIGINS)
assert expected <= set(settings.CSRF_TRUSTED_ORIGINS)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
