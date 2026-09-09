import argparse
import logging
import os
import time

from dotenv import load_dotenv

from inquiry_processor import GraphMailbox, InquiryStore, process_unread


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Continuously process Outlook inquiries")
    parser.add_argument("--data-dir", default=os.getenv("INQUIRY_DATA_DIR", "data"))
    parser.add_argument("--interval", type=int, default=int(os.getenv("INQUIRY_INTERVAL_SECONDS", "10")))
    args = parser.parse_args()
    if args.interval < 1:
        raise ValueError("--interval must be at least 1 second")
    logging.basicConfig(filename="inquiry_processor.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from send_email import Settings
    store = InquiryStore(args.data_dir)
    print(f"Inbox processor started; checking every {args.interval} seconds. Press Ctrl+C to stop.", flush=True)
    while True:
        started = time.monotonic()
        try:
            result = process_unread(GraphMailbox(Settings.from_environment()), store)
            print(
                f"Processed: {result.processed}, Inquiries: {result.inquiries}, "
                f"Auto-replies sent: {result.auto_replies_sent}, Errors: {result.errors}",
                flush=True,
            )
        except Exception:
            logging.exception("Inbox processing cycle failed; retrying on the next cycle")
            print("Inbox processing cycle failed; see inquiry_processor.log", flush=True)
        elapsed = time.monotonic() - started
        time.sleep(max(0, args.interval - elapsed))


if __name__ == "__main__":
    main()