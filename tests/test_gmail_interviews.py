import unittest
from datetime import datetime, timezone
from email.message import EmailMessage

from gmail_interviews import _derive_status, _get_event_datetime, _is_cancelled_message


def build_message(subject="Interview Invite", body="Please join the interview.", calendar_text=None):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "recruiter@example.com"
    msg["To"] = "candidate@example.com"
    msg.set_content(body)

    if calendar_text:
        msg.add_attachment(
            calendar_text.encode("utf-8"),
            maintype="text",
            subtype="calendar",
            filename="invite.ics",
        )

    return msg


class GmailInterviewParsingTests(unittest.TestCase):
    def test_extracts_event_datetime_from_calendar_attachment(self):
        msg = build_message(
            calendar_text="BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260325T103000Z\nEND:VEVENT\nEND:VCALENDAR"
        )

        self.assertEqual(
            _get_event_datetime(msg),
            datetime(2026, 3, 25, 10, 30, tzinfo=timezone.utc),
        )

    def test_detects_cancelled_calendar_invite(self):
        msg = build_message(
            calendar_text="BEGIN:VCALENDAR\nMETHOD:CANCEL\nBEGIN:VEVENT\nSTATUS:CANCELLED\nEND:VEVENT\nEND:VCALENDAR"
        )

        self.assertTrue(_is_cancelled_message("Interview Update", "", msg))

    def test_marks_future_event_as_scheduled(self):
        msg = build_message()
        event_dt = datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc)

        self.assertEqual(
            _derive_status("Interview Invite", "", msg, event_dt, now_utc=datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc)),
            "Scheduled",
        )

    def test_marks_past_event_as_attended(self):
        msg = build_message()
        event_dt = datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc)

        self.assertEqual(
            _derive_status("Interview Invite", "", msg, event_dt, now_utc=datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc)),
            "Attended",
        )

    def test_defaults_to_scheduled_without_event_time(self):
        msg = build_message(body="Zoom link: https://zoom.us/j/123")

        self.assertEqual(
            _derive_status("Recruiter reaching out", "Zoom link included", msg, None, now_utc=datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc)),
            "Scheduled",
        )


if __name__ == "__main__":
    unittest.main()
