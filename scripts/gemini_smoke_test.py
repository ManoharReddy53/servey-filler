"""Opt-in synthetic Gemini connectivity check; never accesses Panel Station."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.llm import GeminiLLMClient


async def run(model: str | None) -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not configured; no request was made.")
    client = GeminiLLMClient(
        api_key=api_key,
        model=model or os.getenv("GEMINI_MODEL", Settings().gemini_model),
    )
    await client.verify_model()
    answer = await client.suggest(
        "Which color is commonly associated with the sky on a clear day?",
        ["blue", "green"],
    )
    print(answer.model_dump_json())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    asyncio.run(run(args.model))
