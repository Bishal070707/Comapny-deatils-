import os
import time
import traceback

from dotenv import load_dotenv

from send_email import Settings, send_email


def main() -> None:
    load_dotenv()
    interval = int(os.getenv("INTERVAL_SECONDS", "30"))
    if interval < 1:
        raise ValueError("INTERVAL_SECONDS must be at least 1")

    settings = Settings.from_environment()
    print(f"Email scheduler started; sending every {interval} seconds. Press Ctrl+C to stop.", flush=True)
    while True:
        started = time.monotonic()
        try:
            send_email(settings)
        except Exception:
            print("Email attempt failed:", flush=True)
            traceback.print_exc()
        elapsed = time.monotonic() - started
        time.sleep(max(0, interval - elapsed))


if __name__ == "__main__":
    main()
else:
    # This module is being imported, not run directly
    # Do nothing to prevent auto-execution
    pass