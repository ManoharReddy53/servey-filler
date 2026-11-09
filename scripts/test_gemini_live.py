"""Live Gemini smoke test using only a harmless synthetic prompt."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.llm import GeminiLLMClient, LLMError


PROMPT = "Explain what an AI agent is in two sentences."


async def run() -> int:
    try:
        settings = get_settings()
        api_key = settings.gemini_api_key or settings.llm_api_key
        client = GeminiLLMClient(
            api_key=api_key or "",
            model=settings.gemini_model or settings.llm_model or "",
            timeout_seconds=settings.llm_timeout_seconds,
        )
        await client.verify_model()
        response = await client.suggest(PROMPT, [])
    except LLMError as error:
        print("STATUS: FAILURE")
        print(f"ERROR: {error}")
        return 1
    except (OSError, ValueError, RuntimeError):
        print("STATUS: FAILURE")
        print("ERROR: Gemini smoke test could not complete.")
        return 1

    print("STATUS: SUCCESS")
    print("MODEL_RESPONSE:")
    print(response.answer or response.rationale)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
