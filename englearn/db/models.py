"""Data access layer for EngLearn database."""
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from englearn.db.database import get_connection


def insert_entry(entry, categories: List[str]) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO log_entries
               (timestamp, original, status, corrected, idiomatic, explanation, pattern, tense, line_number)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry.timestamp.isoformat(), entry.original, entry.status,
             entry.corrected, entry.idiomatic, entry.explanation,
             entry.pattern, entry.tense, entry.line_number)
        )
        entry_id = cur.lastrowid
        if entry_id:
            for cat in categories:
                conn.execute(
                    "INSERT OR IGNORE INTO entry_categories (entry_id, category) VALUES (?, ?)",
                    (entry_id, cat)
                )
        conn.commit()
        return entry_id
    finally:
        conn.close()


def insert_flashcard(deck: str, front: str, back: str, hint: str = "",
                     source_entry_id: int = None) -> int:
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        cur = conn.execute(
            """INSERT INTO flashcards (deck, front, back, hint, source_entry_id, next_review)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (deck, front, back, hint, source_entry_id, today)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def flashcard_exists(deck: str, back: str, front_contains: str = None) -> bool:
    """Check if a flashcard already exists (for dedup)."""
    conn = get_connection()
    try:
        if front_contains:
            row = conn.execute(
                "SELECT 1 FROM flashcards WHERE deck = ? AND back = ? AND front LIKE ? LIMIT 1",
                (deck, back, f"%{front_contains}%")
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM flashcards WHERE deck = ? AND back = ? LIMIT 1",
                (deck, back)
            ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_due_flashcards(deck: str = None, limit: int = 20) -> List[dict]:
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        if deck:
            rows = conn.execute(
                """SELECT * FROM flashcards WHERE deck = ? AND next_review <= ?
                   ORDER BY ease_factor ASC, next_review ASC LIMIT ?""",
                (deck, today, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM flashcards WHERE next_review <= ?
                   ORDER BY ease_factor ASC, next_review ASC LIMIT ?""",
                (today, limit)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_flashcard_sm2(card_id: int, quality: int):
    """Update a flashcard using SM-2 algorithm. quality: 0-5."""
    from englearn.config import SM2_MIN_EASE
    conn = get_connection()
    try:
        card = dict(conn.execute("SELECT * FROM flashcards WHERE id = ?", (card_id,)).fetchone())
        ef = card['ease_factor']
        interval = card['interval_days']
        reps = card['repetitions']

        if quality >= 3:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 6
            else:
                interval = round(interval * ef)
            reps += 1
        else:
            reps = 0
            interval = 1

        ef = max(SM2_MIN_EASE, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        next_review = (datetime.now() + timedelta(days=interval)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")

        conn.execute(
            """UPDATE flashcards SET ease_factor=?, interval_days=?, repetitions=?,
               next_review=?, last_review=? WHERE id=?""",
            (ef, interval, reps, next_review, today, card_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_deck_names() -> List[str]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT deck FROM flashcards ORDER BY deck").fetchall()
        return [r['deck'] for r in rows]
    finally:
        conn.close()


def get_deck_stats() -> List[Dict]:
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT deck,
                      COUNT(*) as total,
                      SUM(CASE WHEN next_review <= ? THEN 1 ELSE 0 END) as due,
                      SUM(CASE WHEN repetitions >= 3 THEN 1 ELSE 0 END) as mastered
               FROM flashcards GROUP BY deck""",
            (today,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def record_daily_progress(cards_reviewed: int = 0, cards_correct: int = 0,
                          quiz_taken: int = 0, quiz_correct: int = 0,
                          new_errors: int = 0):
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute(
            """INSERT INTO daily_progress (date, cards_reviewed, cards_correct, quiz_taken,
                                           quiz_correct, new_errors_imported)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   cards_reviewed = cards_reviewed + ?,
                   cards_correct = cards_correct + ?,
                   quiz_taken = quiz_taken + ?,
                   quiz_correct = quiz_correct + ?""",
            (today, cards_reviewed, cards_correct, quiz_taken, quiz_correct, new_errors,
             cards_reviewed, cards_correct, quiz_taken, quiz_correct)
        )
        conn.commit()
    finally:
        conn.close()


def record_quiz_result(quiz_type: str, question: str, user_answer: str,
                       correct_answer: str, is_correct: bool, flashcard_id: int = None):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO quiz_results (quiz_type, question, user_answer, correct_answer,
                                         is_correct, flashcard_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (quiz_type, question, user_answer, correct_answer, int(is_correct), flashcard_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_sync_state(key: str) -> Optional[str]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else None
    finally:
        conn.close()


def set_sync_state(key: str, value: str):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()
    finally:
        conn.close()


def get_all_entries(status: str = None) -> List[dict]:
    conn = get_connection()
    try:
        if status:
            rows = conn.execute("SELECT * FROM log_entries WHERE status = ? ORDER BY id", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM log_entries ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_category_stats() -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT category, COUNT(*) as count
               FROM entry_categories WHERE category != 'correct'
               GROUP BY category ORDER BY count DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_progress_history(days: int = 30) -> List[Dict]:
    conn = get_connection()
    try:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT * FROM daily_progress WHERE date >= ? ORDER BY date", (since,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_weak_categories(limit: int = 5) -> List[Tuple[str, float]]:
    """Get categories with lowest quiz accuracy."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT ec.category,
                      COUNT(qr.id) as attempts,
                      SUM(qr.is_correct) as correct
               FROM quiz_results qr
               JOIN flashcards fc ON qr.flashcard_id = fc.id
               JOIN entry_categories ec ON fc.source_entry_id = ec.entry_id
               GROUP BY ec.category
               HAVING attempts >= 3
               ORDER BY (1.0 * correct / attempts) ASC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [(r['category'], r['correct'] / r['attempts']) for r in rows]
    finally:
        conn.close()


def search_entries(keyword: str) -> List[dict]:
    conn = get_connection()
    try:
        pattern = f"%{keyword}%"
        rows = conn.execute(
            """SELECT * FROM log_entries
               WHERE original LIKE ? OR corrected LIKE ? OR idiomatic LIKE ? OR explanation LIKE ?
               ORDER BY timestamp DESC LIMIT 50""",
            (pattern, pattern, pattern, pattern)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Talk Scenarios ──────────────────────────────────────────────────────────


def seed_talk_scenarios(templates: list):
    """Seed talk_scenarios table from SCENARIO_TEMPLATES if empty."""
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) as c FROM talk_scenarios WHERE source='template'").fetchone()['c']
        if count > 0:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        for t in templates:
            conn.execute(
                """INSERT INTO talk_scenarios (context, pattern, ai_says, good_responses, source, next_review)
                   VALUES (?, ?, ?, ?, 'template', ?)""",
                (t['context'], t['pattern'], t['ai_says'], json.dumps(t['good_responses']), today)
            )
        conn.commit()
    finally:
        conn.close()


def get_due_talk_scenarios(limit: int = 10, include_reviewed: bool = False) -> List[dict]:
    """Get talk scenarios due for review (SM-2 based).

    Excludes scenarios already reviewed today so multiple sessions
    in one day give fresh scenarios each time.
    If include_reviewed=True, returns random scenarios even if all done today.
    """
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # Due scenarios NOT reviewed today
        rows = conn.execute(
            """SELECT * FROM talk_scenarios
               WHERE next_review <= ?
                 AND (last_review IS NULL OR last_review < ?)
               ORDER BY ease_factor ASC, next_review ASC
               LIMIT ?""",
            (today, today, limit)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['good_responses'] = json.loads(d['good_responses'])
            result.append(d)

        # Fallback: not-yet-reviewed-today scenarios (any next_review)
        if len(result) < limit:
            existing_ids = [r['id'] for r in result]
            placeholders = ','.join('?' * len(existing_ids)) if existing_ids else '0'
            extra = conn.execute(
                f"""SELECT * FROM talk_scenarios
                    WHERE id NOT IN ({placeholders})
                      AND (last_review IS NULL OR last_review < ?)
                    ORDER BY next_review ASC, RANDOM()
                    LIMIT ?""",
                existing_ids + [today, limit - len(result)]
            ).fetchall()
            for r in extra:
                d = dict(r)
                d['good_responses'] = json.loads(d['good_responses'])
                result.append(d)

        # If all reviewed today and --all flag, return random scenarios
        if not result and include_reviewed:
            rows = conn.execute(
                """SELECT * FROM talk_scenarios
                   ORDER BY RANDOM()
                   LIMIT ?""",
                (limit,)
            ).fetchall()
            for r in rows:
                d = dict(r)
                d['good_responses'] = json.loads(d['good_responses'])
                result.append(d)

        return result
    finally:
        conn.close()


def update_talk_scenario_sm2(scenario_id: int, score: float):
    """Update a talk scenario using SM-2 algorithm based on LLM score."""
    from englearn.config import SM2_MIN_EASE
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM talk_scenarios WHERE id = ?", (scenario_id,)).fetchone()
        if not row:
            return
        card = dict(row)
        ef = card['ease_factor']
        interval = card['interval_days']
        reps = card['repetitions']

        # Map score to SM-2 quality
        if score >= 0.7:
            quality = 5
        elif score >= 0.45:
            quality = 3
        else:
            quality = 1

        if quality >= 3:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 6
            else:
                interval = round(interval * ef)
            reps += 1
        else:
            reps = 0
            interval = 1

        ef = max(SM2_MIN_EASE, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        next_review = (datetime.now() + timedelta(days=interval)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")

        conn.execute(
            """UPDATE talk_scenarios SET ease_factor=?, interval_days=?, repetitions=?,
               next_review=?, last_review=? WHERE id=?""",
            (ef, interval, reps, next_review, today, scenario_id)
        )
        conn.commit()
    finally:
        conn.close()


def insert_talk_scenario(context: str, pattern: str, ai_says: str,
                         good_responses: list, source: str = 'generated',
                         source_entry_id: int = None) -> int:
    """Insert a new talk scenario."""
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        cur = conn.execute(
            """INSERT INTO talk_scenarios (context, pattern, ai_says, good_responses, source, source_entry_id, next_review)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (context, pattern, ai_says, json.dumps(good_responses), source, source_entry_id, today)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_recent_error_entries(limit: int = 10) -> List[dict]:
    """Get recent incorrect entries that don't already have generated scenarios."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT le.* FROM log_entries le
               WHERE le.status = 'incorrect'
                 AND le.pattern IS NOT NULL AND le.pattern != 'N/A' AND le.pattern != ''
                 AND le.id NOT IN (SELECT source_entry_id FROM talk_scenarios WHERE source_entry_id IS NOT NULL)
               ORDER BY le.id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def cache_flashcard_example(card_id: int, sentence: str, collocation: str):
    """Cache example sentence and collocation for a flashcard."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE flashcards SET example_sentence=?, collocation=? WHERE id=?",
            (sentence, collocation, card_id)
        )
        conn.commit()
    finally:
        conn.close()


# ─── Chat Messages ───────────────────────────────────────────────────────────


def insert_chat_message(role_id: str, sender: str, message: str,
                        corrections: str = None, scenario_id: str = None) -> int:
    """Insert a chat message and return its ID."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO chat_messages (role_id, sender, message, corrections, scenario_id)
               VALUES (?, ?, ?, ?, ?)""",
            (role_id, sender, message, corrections, scenario_id)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_chat_history(role_id: str, limit: int = 20,
                     scenario_id: str = None) -> List[dict]:
    """Get chat history for a role + scenario, oldest first for display.

    If scenario_id is None, returns free-talk messages (where scenario_id IS NULL).
    If scenario_id is given, returns messages for that specific scenario.
    """
    conn = get_connection()
    try:
        if scenario_id:
            rows = conn.execute(
                """SELECT * FROM chat_messages WHERE role_id = ? AND scenario_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (role_id, scenario_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM chat_messages WHERE role_id = ? AND scenario_id IS NULL
                   ORDER BY id DESC LIMIT ?""",
                (role_id, limit)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def delete_chat_message(msg_id: int) -> bool:
    """Delete a single chat message by ID."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM chat_messages WHERE id = ?", (msg_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def clear_chat_history(role_id: str, scenario_id: str = None) -> None:
    """Clear chat messages for a role + scenario."""
    conn = get_connection()
    try:
        if scenario_id:
            conn.execute(
                "DELETE FROM chat_messages WHERE role_id = ? AND scenario_id = ?",
                (role_id, scenario_id))
        else:
            conn.execute(
                "DELETE FROM chat_messages WHERE role_id = ? AND scenario_id IS NULL",
                (role_id,))
        conn.commit()
    finally:
        conn.close()
