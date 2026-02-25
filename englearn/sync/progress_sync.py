"""Sync study progress to/from Notion for cross-device support."""
import json
import os
import urllib.request
from datetime import datetime
from englearn.db.database import get_connection


NOTION_PROGRESS_DB_ID = "3121f4f8-e609-8185-a739-f67b44e093dc"


def _get_notion_token():
    settings_path = os.path.expanduser("~/.claude/settings.json")
    with open(settings_path, 'r') as f:
        settings = json.load(f)
    for server in settings.get('mcpServers', {}).values():
        env = server.get('env', {})
        if 'NOTION_TOKEN' in env:
            return env['NOTION_TOKEN']
    return None


def _notion_headers():
    token = _get_notion_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def push_progress():
    """Push today's local progress to Notion."""
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # Get today's progress
        row = conn.execute(
            "SELECT * FROM daily_progress WHERE date = ?", (today,)
        ).fetchone()

        # Get overall stats
        total_cards = conn.execute("SELECT COUNT(*) as c FROM flashcards").fetchone()['c']
        mastered = conn.execute(
            "SELECT COUNT(*) as c FROM flashcards WHERE repetitions >= 3"
        ).fetchone()['c']

        # Calculate streak
        from englearn.db.models import get_progress_history
        progress = get_progress_history(30)
        streak = 0
        from datetime import timedelta
        check_date = datetime.now()
        dates = {p['date'] for p in progress if p['cards_reviewed'] > 0 or p['quiz_taken'] > 0}
        for _ in range(365):
            if check_date.strftime("%Y-%m-%d") in dates:
                streak += 1
            else:
                break
            check_date -= timedelta(days=1)

    finally:
        conn.close()

    cards_reviewed = row['cards_reviewed'] if row else 0
    cards_correct = row['cards_correct'] if row else 0
    quiz_taken = row['quiz_taken'] if row else 0
    quiz_correct = row['quiz_correct'] if row else 0

    headers = _notion_headers()

    # Check if today's entry already exists in Notion
    query_url = f"https://api.notion.com/v1/databases/{NOTION_PROGRESS_DB_ID}/query"
    query_payload = {
        "filter": {
            "property": "Date",
            "title": {"equals": today}
        }
    }
    req = urllib.request.Request(query_url, data=json.dumps(query_payload).encode(),
                                 headers=headers, method='POST')
    resp = json.loads(urllib.request.urlopen(req).read())
    existing = resp.get('results', [])

    page_data = {
        "Date": {"title": [{"text": {"content": today}}]},
        "Cards Reviewed": {"number": cards_reviewed},
        "Cards Correct": {"number": cards_correct},
        "Quiz Taken": {"number": quiz_taken},
        "Quiz Correct": {"number": quiz_correct},
        "Vocab Mastered": {"number": mastered},
        "Total Cards": {"number": total_cards},
        "Streak": {"number": streak},
    }

    if existing:
        # Update existing entry
        page_id = existing[0]['id']
        update_url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {"properties": page_data}
        req = urllib.request.Request(update_url, data=json.dumps(payload).encode(),
                                     headers=headers, method='PATCH')
        urllib.request.urlopen(req)
        print(f"  Updated Notion progress for {today}")
    else:
        # Create new entry
        payload = {
            "parent": {"database_id": NOTION_PROGRESS_DB_ID},
            "properties": page_data,
        }
        req = urllib.request.Request("https://api.notion.com/v1/pages",
                                     data=json.dumps(payload).encode(),
                                     headers=headers, method='POST')
        urllib.request.urlopen(req)
        print(f"  Created Notion progress for {today}")


def pull_progress():
    """Pull progress from Notion and merge into local DB."""
    headers = _notion_headers()
    query_url = f"https://api.notion.com/v1/databases/{NOTION_PROGRESS_DB_ID}/query"
    req = urllib.request.Request(query_url, data=json.dumps({}).encode(),
                                 headers=headers, method='POST')
    resp = json.loads(urllib.request.urlopen(req).read())

    conn = get_connection()
    try:
        imported = 0
        for page in resp.get('results', []):
            props = page['properties']

            date_arr = props.get('Date', {}).get('title', [])
            date = ''.join(t.get('plain_text', '') for t in date_arr).strip()
            if not date:
                continue

            cards_reviewed = props.get('Cards Reviewed', {}).get('number') or 0
            cards_correct = props.get('Cards Correct', {}).get('number') or 0
            quiz_taken = props.get('Quiz Taken', {}).get('number') or 0
            quiz_correct = props.get('Quiz Correct', {}).get('number') or 0

            # Merge: keep the higher value (in case both local and remote have data)
            existing = conn.execute(
                "SELECT * FROM daily_progress WHERE date = ?", (date,)
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE daily_progress SET
                        cards_reviewed = MAX(cards_reviewed, ?),
                        cards_correct = MAX(cards_correct, ?),
                        quiz_taken = MAX(quiz_taken, ?),
                        quiz_correct = MAX(quiz_correct, ?)
                    WHERE date = ?""",
                    (cards_reviewed, cards_correct, quiz_taken, quiz_correct, date)
                )
            else:
                conn.execute(
                    """INSERT INTO daily_progress
                       (date, cards_reviewed, cards_correct, quiz_taken, quiz_correct)
                       VALUES (?, ?, ?, ?, ?)""",
                    (date, cards_reviewed, cards_correct, quiz_taken, quiz_correct)
                )
            imported += 1

        conn.commit()
        print(f"  Pulled {imported} days of progress from Notion")
    finally:
        conn.close()
