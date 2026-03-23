## Gmail interview finder

This folder contains a small Python script that searches your recent Gmail inbox for interview-related emails and prints a list with sender, subject, and derived interview status. It can also export a CSV for a Streamlit dashboard.

### What you'll need (one-time)

- Python 3.10+ installed
- A Gmail account
- An app password generated from your Google Account security settings

### Authentication setup

The script connects to Gmail over IMAP and authenticates with your Gmail address plus an app password. For security, set them as environment variables instead of hardcoding them:

**Windows (Command Prompt):**
```cmd
set GMAIL_EMAIL=your_email@gmail.com
set GMAIL_APP_PASSWORD=your_app_password
```

**Windows (PowerShell):**
```powershell
$env:GMAIL_EMAIL="your_email@gmail.com"
$env:GMAIL_APP_PASSWORD="your_app_password"
```

**Mac / Linux / Git Bash:**
```bash
export GMAIL_EMAIL="your_email@gmail.com"
export GMAIL_APP_PASSWORD="your_app_password"
```

### Install dependencies

From this folder:

```bash
python -m pip install -r requirements.txt
```

### Run

```bash
python gmail_interviews.py
```

Common options:

```bash
python gmail_interviews.py --days 7 --max 100 --limit 30
python gmail_interviews.py --csv interviews.csv
python gmail_interviews.py --query "newer_than:30d (interview OR recruiter) -from:notifications@"
```

### How status is derived

- `Cancelled`: the message subject/body suggests cancellation, or the calendar invite is marked cancelled.
- `Scheduled`: the message includes a meeting link or invite and either the event time is in the future or no event time could be extracted.
- `Attended`: the message includes a calendar event and that event time is in the past.

This means the script prefers actual invite timing over the email send date, which avoids incorrectly marking old recruiter emails as attended.

### Notes

- The script uses IMAP in read-only mode on the inbox.
- No OAuth token file is used in the current implementation.
- The CSV includes both the email timestamp and, when available, the event timestamp from the invite.

### Dashboard

This project also includes a Streamlit dashboard to visualize the interview data.

**Run the dashboard:**

```bash
streamlit run dashboard.py
```

If the dashboard cannot read the CSV or the file is missing expected columns, it will show a clear error instead of failing silently.

### Tests

Run the parser tests with:

```bash
python -m unittest discover -s tests
```
