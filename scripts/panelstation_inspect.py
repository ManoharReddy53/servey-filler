"""User-triggered, non-submitting Panel Station inspection harness."""

import argparse
import asyncio
import json

from app.browser.session import PlaywrightBrowserSession
from app.services.classifier import classify_questions


async def inspect(url: str, storage_path: str) -> None:
    session = PlaywrightBrowserSession(storage_path)
    try:
        await session.start_authorized(url)
        input("Log in manually if needed, open a survey page, then press Enter to inspect: ")
        snapshot = await session.inspect_current_page()
        snapshot = snapshot.model_copy(update={"questions": classify_questions(snapshot.questions)})
        print(json.dumps(snapshot.model_dump(mode="json"), indent=2))
        print("No answers were filled and no submission action is available.")
    finally:
        await session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Explicit permitted survey URL to open.")
    parser.add_argument("--storage-path", default="./browser-state")
    args = parser.parse_args()
    asyncio.run(inspect(args.url, args.storage_path))


if __name__ == "__main__":
    main()
