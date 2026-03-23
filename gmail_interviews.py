import argparse
import csv
import os
import imaplib
import email
import re
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _decode_hdr(header_val: str) -> str:
    if not header_val:
        return ""
    res = []
    for text, charset in decode_header(header_val):
        if isinstance(text, bytes):
            res.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            res.append(str(text))
    return "".join(res)


def _get_snippet(msg) -> str:
    snippet = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    snippet = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            snippet = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    
    snippet = " ".join(snippet.split())
    if len(snippet) > 100:
        return snippet[:100] + "..."
    return snippet


def _has_meeting_invite(msg) -> bool:
    meeting_domains = ["meet.google.com", "zoom.us", "teams.microsoft.com", "webex.com", "chime.aws"]
    for part in msg.walk():
        # Check for calendar invites
        if part.get_content_type() == "text/calendar" or "application/ics" in part.get_content_type():
            return True
        # Check body for common video conferencing links
        if part.get_content_type() in ["text/plain", "text/html"]:
            payload = part.get_payload(decode=True)
            if payload:
                text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore").lower()
                if any(domain in text for domain in meeting_domains):
                    return True
    return False


def _extract_calendar_text(part) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def _parse_ics_datetime(value: str) -> Optional[datetime]:
    value = value.strip()
    if not value:
        return None

    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        dt = datetime.strptime(value, "%Y%m%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _get_event_datetime(msg) -> Optional[datetime]:
    for part in msg.walk():
        if part.get_content_type() != "text/calendar" and "application/ics" not in part.get_content_type():
            continue

        calendar_text = _extract_calendar_text(part)
        if not calendar_text:
            continue

        for line in calendar_text.splitlines():
            normalized = line.strip()
            if normalized.startswith("DTSTART"):
                _, _, raw_value = normalized.partition(":")
                event_dt = _parse_ics_datetime(raw_value)
                if event_dt:
                    return event_dt
    return None


def _is_cancelled_message(subject: str, snippet: str, msg) -> bool:
    combined = f"{subject} {snippet}".lower()
    if re.search(r"\bcancel(?:led|ed|lation)?\b", combined):
        return True

    for part in msg.walk():
        if part.get_content_type() != "text/calendar" and "application/ics" not in part.get_content_type():
            continue

        calendar_text = _extract_calendar_text(part).lower()
        if "status:cancelled" in calendar_text or "method:cancel" in calendar_text:
            return True

    return False


def _derive_status(subject: str, snippet: str, msg, event_dt_utc: Optional[datetime], now_utc: Optional[datetime] = None) -> str:
    now_utc = now_utc or datetime.now(timezone.utc)

    if _is_cancelled_message(subject, snippet, msg):
        return "Cancelled"

    if event_dt_utc:
        return "Attended" if event_dt_utc < now_utc else "Scheduled"

    # Without an actual event time we keep the item as scheduled rather than
    # incorrectly marking a past email as attended.
    return "Scheduled"


def _build_default_query(days: int) -> str:
    # Gmail search syntax: https://support.google.com/mail/answer/7190
    return f"newer_than:{days}d (interview OR recruiter) -from:notifications@"


def _search_imap_gmail(mail, query: str, max_results: int) -> List[bytes]:
    # X-GM-RAW allows us to use the exact same Gmail search query format
    typ, data = mail.uid('SEARCH', 'X-GM-RAW', f'"{query}"')
    if typ != 'OK':
        print(f"IMAP search failed: {typ}")
        return []
    uids = data[0].split()
    return uids[-max_results:] if max_results else uids


def _get_message_summary(mail, uid: bytes) -> Dict[str, Any]:
    typ, data = mail.uid('FETCH', uid, '(RFC822)')
    if typ != 'OK' or not data or not data[0]:
        return {}
    
    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)
    
    # Skip emails that do not contain a calendar invite or a meeting link
    if not _has_meeting_invite(msg):
        return {}

    date_str = msg.get("Date")
    dt_utc = datetime.now(timezone.utc)
    if date_str:
        try:
            dt_parsed = parsedate_to_datetime(date_str)
            dt_utc = dt_parsed.astimezone(timezone.utc)
        except Exception:
            pass
            
    subject = _decode_hdr(msg.get("Subject", ""))
    frm = _decode_hdr(msg.get("From", ""))
    snippet = _get_snippet(msg)
    event_dt_utc = _get_event_datetime(msg)

    status = _derive_status(subject, snippet, msg, event_dt_utc)

    return {
        "id": uid.decode('utf-8'),
        "threadId": "",
        "date_utc": dt_utc,
        "event_date_utc": event_dt_utc,
        "from": frm,
        "subject": subject,
        "snippet": snippet,
        "status": status,
    }


def _fmt_local(dt_utc: datetime) -> str:
    # Convert to local timezone for display.
    return dt_utc.astimezone().strftime("%Y-%m-%d %H:%M")


def _print_rows(rows: List[Dict[str, Any]], limit: int) -> None:
    if not rows:
        print("No matching emails found.")
        return

    rows = rows[:limit]
    print("when | status | from | subject")
    print("---+---+---+---")
    for r in rows:
        print(f"{_fmt_local(r['date_utc'])} | {r['status']} | {r['from']} | {r['subject']}")

    print("\nDetails:")
    for i, r in enumerate(rows, start=1):
        print(f"\n[{i}] {_fmt_local(r['date_utc'])}  {r['subject']}")
        print(f"From: {r['from']}")
        print(f"Message ID: {r['id']}")
        print(f"Status: {r['status']}")
        if r["snippet"]:
            print(f"Snippet: {r['snippet']}")


def _write_csv(rows: List[Dict[str, Any]], out_path: str) -> None:
    fieldnames = ["when_local", "event_when_local", "status", "from", "subject", "snippet", "id", "threadId"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "when_local": _fmt_local(r["date_utc"]),
                    "event_when_local": _fmt_local(r["event_date_utc"]) if r.get("event_date_utc") else "",
                    "status": r["status"],
                    "from": r["from"],
                    "subject": r["subject"],
                    "snippet": r["snippet"],
                    "id": r["id"],
                    "threadId": r["threadId"],
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Search recent Gmail messages for interview-related emails."
    )
    ap.add_argument(
        "--days",
        type=int,
        default=30,
        help="How many days back to search for messages (default: 30).",
    )
    ap.add_argument(
        "--max",
        type=int,
        default=50,
        help="Max messages to fetch from Gmail search (default: 50).",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max messages to print (default: 20).",
    )
    ap.add_argument(
        "--query",
        type=str,
        default="",
        help="Optional Gmail search query. If omitted, a reasonable interview query is used.",
    )
    ap.add_argument(
        "--email",
        type=str,
        default=os.environ.get("GMAIL_EMAIL"),
        help="Gmail address. Can also be set via GMAIL_EMAIL environment variable.",
    )
    ap.add_argument(
        "--app-password",
        type=str,
        default=os.environ.get("GMAIL_APP_PASSWORD"),
        help="App password for Gmail. Can also be set via GMAIL_APP_PASSWORD env var.",
    )
    ap.add_argument(
        "--csv",
        type=str,
        default="",
        help="Optional path to write results to CSV.",
    )
    args = ap.parse_args()

    if args.max <= 0:
        raise SystemExit("--max must be > 0")
    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")
        
    if not args.email or not args.app_password:
        raise SystemExit(
            "Error: Missing credentials.\n"
            "Please provide --email and --app-password, or set GMAIL_EMAIL and GMAIL_APP_PASSWORD environment variables."
        )

    query = args.query.strip() or _build_default_query(args.days)

    print("Connecting to Gmail via IMAP...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(args.email, args.app_password)
    mail.select("inbox", readonly=True)

    uids = _search_imap_gmail(mail, query=query, max_results=args.max)
    rows = []
    for uid in uids:
        if uid:
            summary = _get_message_summary(mail, uid)
            if summary:
                rows.append(summary)
                
    mail.logout()

    # Sort newest first using Gmail internalDate.
    rows.sort(key=lambda r: r["date_utc"], reverse=True)

    _print_rows(rows, limit=args.limit)
    if args.csv:
        _write_csv(rows, args.csv)
        print(f"\nWrote CSV: {args.csv}")

    # Dashboard Summary
    total = len(rows)
    cancelled = sum(1 for r in rows if r["status"] == "Cancelled")
    attended = sum(1 for r in rows if r["status"] == "Attended")
    scheduled = sum(1 for r in rows if r["status"] == "Scheduled")

    print(f"\n--- Last {args.days} Days Dashboard Summary ---")
    print(f"Total Interviews : {total}")
    print(f"Attended        : {attended}")
    print(f"Cancelled       : {cancelled}")
    print(f"Scheduled       : {scheduled}")
    print(f"\nUsed Gmail query: {query}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
