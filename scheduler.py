import argparse
import logging
import os

from dotenv import load_dotenv

from inquiry_processor import GraphMailbox, InquiryStore, process_unread


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Process the Outlook inbox once")
    parser.add_argument("--data-dir", default=os.getenv("INQUIRY_DATA_DIR", "data"))
    args = parser.parse_args()
    logging.basicConfig(filename="inquiry_processor.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from send_email import Settings
    result = process_unread(GraphMailbox(Settings.from_environment()), InquiryStore(args.data_dir))
    print(f"Processed: {result.processed}, Inquiries: {result.inquiries}, Auto-replies sent: {result.auto_replies_sent}")


if __name__ == "__main__":
    main()