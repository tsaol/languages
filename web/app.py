"""EngLearn Web UI - Flask application for English learning."""
import sys
import os
import random

# Add parent so we can import englearn
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta

from englearn.db.models import (
    get_due_flashcards,
    update_flashcard_sm2,
    get_deck_stats,
    record_daily_progress,
    record_quiz_result,
    get_progress_history,
    get_category_stats,
)
from englearn.db.database import get_connection

app = Flask(__name__)

# Rating map: UI button -> SM-2 quality
RATING_MAP = {1: 1, 2: 3, 3: 5}


def get_streak():
    """Calculate current study streak."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT date, cards_reviewed, quiz_taken FROM daily_progress ORDER BY date DESC LIMIT 60"
        ).fetchall()
        if not rows:
            return 0
        streak = 0
        today = datetime.now().date()
        for row in rows:
            d = datetime.strptime(row["date"], "%Y-%m-%d").date()
            expected = today - timedelta(days=streak)
            if d == expected and (row["cards_reviewed"] > 0 or row["quiz_taken"] > 0):
                streak += 1
            elif d < expected:
                break
            # skip if d > expected (future dates somehow)
        return streak
    finally:
        conn.close()


def get_today_progress():
    """Get today's progress record."""
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT * FROM daily_progress WHERE date = ?", (today,)
        ).fetchone()
        if row:
            return dict(row)
        return {
            "date": today,
            "cards_reviewed": 0,
            "cards_correct": 0,
            "quiz_taken": 0,
            "quiz_correct": 0,
        }
    finally:
        conn.close()


def get_weekly_activity():
    """Get activity for the past 7 days."""
    conn = get_connection()
    try:
        result = []
        today = datetime.now().date()
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT * FROM daily_progress WHERE date = ?", (d,)
            ).fetchone()
            if row:
                result.append(dict(row))
            else:
                result.append(
                    {
                        "date": d,
                        "cards_reviewed": 0,
                        "cards_correct": 0,
                        "quiz_taken": 0,
                        "quiz_correct": 0,
                    }
                )
        return result
    finally:
        conn.close()


def get_overall_accuracy():
    """Get overall quiz accuracy."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as total, SUM(is_correct) as correct FROM quiz_results"
        ).fetchone()
        total = row["total"] or 0
        correct = row["correct"] or 0
        return {"total": total, "correct": correct, "pct": round(correct / total * 100) if total else 0}
    finally:
        conn.close()


def get_random_quiz_cards(quiz_type: str = "mixed", count: int = 10):
    """Get random flashcards for quiz."""
    conn = get_connection()
    try:
        if quiz_type == "mixed":
            rows = conn.execute(
                "SELECT * FROM flashcards ORDER BY RANDOM() LIMIT ?", (count,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM flashcards WHERE deck = ? ORDER BY RANDOM() LIMIT ?",
                (quiz_type, count),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Routes ───────────────────────────────────────────────────────────────────


@app.route("/")
def dashboard():
    decks = get_deck_stats()
    today = get_today_progress()
    streak = get_streak()
    total_due = sum(d["due"] for d in decks)
    total_cards = sum(d["total"] for d in decks)
    return render_template(
        "dashboard.html",
        decks=decks,
        today=today,
        streak=streak,
        total_due=total_due,
        total_cards=total_cards,
    )


@app.route("/review")
def review():
    deck = request.args.get("deck", "")
    cards = get_due_flashcards(deck=deck if deck else None, limit=50)
    return render_template("review.html", deck=deck, cards=cards, total=len(cards))


@app.route("/review/answer", methods=["POST"])
def review_answer():
    data = request.get_json()
    card_id = data.get("card_id")
    rating = data.get("rating")  # 1, 2, or 3

    if not card_id or rating not in (1, 2, 3):
        return jsonify({"error": "Invalid request"}), 400

    quality = RATING_MAP[rating]
    update_flashcard_sm2(card_id, quality)

    # Record progress
    is_correct = 1 if rating >= 2 else 0
    record_daily_progress(cards_reviewed=1, cards_correct=is_correct)

    return jsonify({"ok": True, "quality": quality})


@app.route("/quiz")
def quiz():
    quiz_type = request.args.get("type", "mixed")
    count = int(request.args.get("count", 10))
    cards = get_random_quiz_cards(quiz_type, count)
    return render_template("quiz.html", quiz_type=quiz_type, cards=cards, count=len(cards))


@app.route("/quiz/answer", methods=["POST"])
def quiz_answer():
    data = request.get_json()
    card_id = data.get("card_id")
    user_answer = data.get("answer", "").strip()
    correct_answer = data.get("correct_answer", "")
    question = data.get("question", "")
    quiz_type = data.get("quiz_type", "mixed")

    # Simple matching: case-insensitive, strip punctuation
    def normalize(s):
        import re
        return re.sub(r'[^\w\s]', '', s.lower()).strip()

    is_correct = normalize(user_answer) == normalize(correct_answer)

    # Also check partial match (80% similarity)
    if not is_correct:
        from difflib import SequenceMatcher
        ratio = SequenceMatcher(None, normalize(user_answer), normalize(correct_answer)).ratio()
        is_correct = ratio >= 0.80

    record_quiz_result(quiz_type, question, user_answer, correct_answer, is_correct, flashcard_id=card_id)
    record_daily_progress(quiz_taken=1, quiz_correct=1 if is_correct else 0)

    return jsonify({
        "ok": True,
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "user_answer": user_answer,
    })


@app.route("/stats")
def stats():
    progress = get_progress_history(30)
    categories = get_category_stats()
    weekly = get_weekly_activity()
    accuracy = get_overall_accuracy()
    decks = get_deck_stats()
    total_cards = sum(d["total"] for d in decks)
    total_mastered = sum(d["mastered"] for d in decks)
    return render_template(
        "stats.html",
        progress=progress,
        categories=categories,
        weekly=weekly,
        accuracy=accuracy,
        total_cards=total_cards,
        total_mastered=total_mastered,
    )


@app.route("/vocab")
def vocab():
    """Vocabulary management page."""
    conn = get_connection()
    try:
        words = conn.execute(
            """SELECT f.id, f.front, f.back, f.hint, f.ease_factor, f.repetitions,
                      f.next_review, f.interval_days
               FROM flashcards f WHERE f.deck = 'vocab' ORDER BY f.id DESC"""
        ).fetchall()
        words = [dict(w) for w in words]
        # Parse the word from front text "How do you say "X" in English?"
        for w in words:
            front = w['front']
            if '"' in front:
                parts = front.split('"')
                if len(parts) >= 2:
                    w['chinese'] = parts[1]
                else:
                    w['chinese'] = front
            else:
                w['chinese'] = front
            w['word'] = w['back']
            # category from hint
            hint = w.get('hint', '')
            w['category'] = hint.replace('Category: ', '') if hint.startswith('Category:') else ''
    finally:
        conn.close()
    categories = sorted(set(w['category'] for w in words if w['category']))
    return render_template("vocab.html", words=words, categories=categories, total=len(words))


@app.route("/vocab/add", methods=["POST"])
def vocab_add():
    """Add a new word to vocab deck."""
    data = request.get_json()
    word = data.get("word", "").strip()
    chinese = data.get("chinese", "").strip()
    category = data.get("category", "").strip()

    if not word or not chinese:
        return jsonify({"error": "Word and Chinese meaning are required"}), 400

    from englearn.db.models import insert_flashcard
    card_id = insert_flashcard(
        deck='vocab',
        front=f'How do you say "{chinese}" in English?',
        back=word,
        hint=f"Category: {category}" if category else "",
    )
    return jsonify({"ok": True, "id": card_id, "word": word, "chinese": chinese})


@app.route("/vocab/delete", methods=["POST"])
def vocab_delete():
    """Delete a word from vocab deck."""
    data = request.get_json()
    card_id = data.get("card_id")
    if not card_id:
        return jsonify({"error": "card_id required"}), 400

    conn = get_connection()
    try:
        conn.execute("DELETE FROM flashcards WHERE id = ? AND deck = 'vocab'", (card_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/vocab/edit", methods=["POST"])
def vocab_edit():
    """Edit an existing vocab word."""
    data = request.get_json()
    card_id = data.get("card_id")
    word = data.get("word", "").strip()
    chinese = data.get("chinese", "").strip()
    category = data.get("category", "").strip()

    if not card_id or not word or not chinese:
        return jsonify({"error": "card_id, word, and chinese are required"}), 400

    conn = get_connection()
    try:
        conn.execute(
            """UPDATE flashcards SET
                front = ?, back = ?, hint = ?
               WHERE id = ? AND deck = 'vocab'""",
            (f'How do you say "{chinese}" in English?', word,
             f"Category: {category}" if category else "", card_id)
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


# ─── API Routes ───────────────────────────────────────────────────────────────


@app.route("/api/decks")
def api_decks():
    return jsonify(get_deck_stats())


@app.route("/api/due")
def api_due():
    deck = request.args.get("deck")
    limit = int(request.args.get("limit", 20))
    cards = get_due_flashcards(deck=deck, limit=limit)
    return jsonify(cards)


@app.route("/api/progress")
def api_progress():
    days = int(request.args.get("days", 30))
    return jsonify(get_progress_history(days))


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555, debug=True)
