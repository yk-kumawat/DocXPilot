"""Gemini API client for DocXPilot.

Uses the official google-genai SDK. Includes retry logic, model fallback,
interactive API key prompt, and rate-limit handling with a clean interface.
"""

import os
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types as genai_types


def _load_env() -> None:
    """Best-effort loader for .env files without requiring python-dotenv."""
    locations = [
        Path(".env"),
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for loc in locations:
        if loc.is_file():
            try:
                for line in loc.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            except Exception:
                pass


_load_env()

_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
_FALLBACK_MODELS = [
    _DEFAULT_MODEL,
    "gemini-2.5-flash",
    "gemini-1.5-flash",
]
_MAX_RETRIES = 3
_RETRY_DELAY = 3  # seconds between retries


class GeminiClient:
    """Thin wrapper around the Gemini generative AI SDK.

    The API key is read from the ``GEMINI_API_KEY`` environment variable,
    ``.env`` file, or prompted interactively if missing.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        _load_env()
        key = api_key or os.environ.get("GEMINI_API_KEY", "")

        # If not provided and running interactively, prompt user directly
        if not key and sys.stdin.isatty():
            try:
                import questionary
                key = questionary.password("Gemini API key not found. Enter your Gemini API key:").ask()
                if key:
                    key = key.strip()
                    os.environ["GEMINI_API_KEY"] = key
            except Exception:
                pass

        if not key:
            raise EnvironmentError(
                "Gemini API key not found.\n"
                "Please set it using: $env:GEMINI_API_KEY=\"your_key\"\n"
                "Or pass it via: --api-key \"your_key\"\n"
                "Or create a .env file with: GEMINI_API_KEY=your_key"
            )

        self._model_name = model or _DEFAULT_MODEL
        self._client = genai.Client(api_key=key)

    def generate(self, prompt: str) -> str:
        """Send *prompt* to Gemini and return the response text.

        Retries on transient errors and handles model deprecation fallback.

        Args:
            prompt: The full prompt string.

        Returns:
            The generated text from the model.

        Raises:
            RuntimeError: If all retries and fallback models are exhausted.
        """
        # Determine candidate models to try
        candidates = [self._model_name]
        for m in _FALLBACK_MODELS:
            if m not in candidates:
                candidates.append(m)

        last_error: Exception | None = None

        for model in candidates:
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            temperature=0.7,
                            max_output_tokens=8192,
                        ),
                    )
                    # Cache the working model for future calls
                    self._model_name = model
                    return response.text or ""
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    err_str = str(exc).lower()

                    # If model not found or not available, do not retry this model; try next candidate
                    if "404" in err_str or "not_found" in err_str or "no longer available" in err_str:
                        break

                    # For transient errors (rate-limit, network, 5xx), back off and retry
                    if attempt < _MAX_RETRIES:
                        time.sleep(_RETRY_DELAY * attempt)

        raise RuntimeError(
            f"Gemini generation failed: {last_error}"
        ) from last_error
