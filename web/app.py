"""EngLearn Web UI - Flask application for English learning."""
import sys
import os
import random

# Add parent so we can import englearn
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
from functools import wraps

from englearn.db.models import (
    get_due_flashcards,
    update_flashcard_sm2,
    get_deck_stats,
    record_daily_progress,
    record_quiz_result,
)
from englearn.db.database import get_connection

app = Flask(__name__)
app.secret_key = 'englearn-secret-key-2026'

# Auth
AUTH_USER = 'cc6776'
AUTH_PASS = 'yjcsxd6'

# Rating map: UI button -> SM-2 quality
RATING_MAP = {1: 1, 2: 3, 3: 5}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ─── Auth ─────────────────────────────────────────────────────────────────────


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == AUTH_USER and password == AUTH_PASS:
            session['logged_in'] = True
            return redirect("/")
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


# ─── Pages ────────────────────────────────────────────────────────────────────


@app.route("/")
@login_required
def review():
    deck = request.args.get("deck", "")
    cards = get_due_flashcards(deck=deck if deck else None, limit=50)
    return render_template("review.html", deck=deck, cards=cards, total=len(cards))


@app.route("/review/answer", methods=["POST"])
@login_required
def review_answer():
    data = request.get_json()
    card_id = data.get("card_id")
    rating = data.get("rating")  # 1, 2, or 3

    if not card_id or rating not in (1, 2, 3):
        return jsonify({"error": "Invalid request"}), 400

    quality = RATING_MAP[rating]
    update_flashcard_sm2(card_id, quality)

    is_correct = 1 if rating >= 2 else 0
    record_daily_progress(cards_reviewed=1, cards_correct=is_correct)

    return jsonify({"ok": True, "quality": quality})


@app.route("/talk")
@login_required
def talk():
    from englearn.quiz.conversation import SCENARIO_TEMPLATES, _load_dynamic_scenarios
    all_scenarios = list(SCENARIO_TEMPLATES)
    dynamic = _load_dynamic_scenarios()
    all_scenarios.extend(dynamic)
    random.shuffle(all_scenarios)
    scenarios = all_scenarios[:10]
    return render_template("talk.html", scenarios=scenarios, total=len(scenarios))


@app.route("/talk/answer", methods=["POST"])
@login_required
def talk_answer():
    data = request.get_json()
    user_answer = data.get("answer", "").strip()
    good_responses = data.get("good_responses", [])
    context = data.get("context", "")
    pattern = data.get("pattern", "")
    ai_says = data.get("ai_says", "")

    from englearn.scoring.llm_scorer import score_response
    result = score_response(context, pattern, ai_says, user_answer, good_responses)

    best = result.get("better_expression", good_responses[0] if good_responses else "")

    record_quiz_result(
        quiz_type='conversation',
        question=context,
        user_answer=user_answer,
        correct_answer=best,
        is_correct=result["is_correct"],
    )
    record_daily_progress(quiz_taken=1, quiz_correct=1 if result["is_correct"] else 0)

    return jsonify({
        "ok": True,
        "score": result["score"],
        "is_correct": result["is_correct"],
        "best_response": best,
        "feedback": result.get("feedback", ""),
    })


@app.route("/vocab")
@login_required
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
            hint = w.get('hint', '')
            w['category'] = hint.replace('Category: ', '') if hint.startswith('Category:') else ''
    finally:
        conn.close()
    categories = sorted(set(w['category'] for w in words if w['category']))
    return render_template("vocab.html", words=words, categories=categories, total=len(words))


@app.route("/vocab/add", methods=["POST"])
@login_required
def vocab_add():
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
@login_required
def vocab_delete():
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
@login_required
def vocab_edit():
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


# ─── API ──────────────────────────────────────────────────────────────────────


@app.route("/api/sync-log", methods=["POST"])
def api_sync_log():
    """Receive incremental english.log lines and process into flashcards."""
    data = request.get_json()
    lines = data.get("lines", [])
    if not lines:
        return jsonify({"error": "no lines provided"}), 400

    from englearn.parser.log_parser import _parse_line
    from englearn.parser.categorizer import categorize
    from englearn.db.models import insert_entry, get_sync_state, set_sync_state
    from englearn.db.database import init_db
    from englearn.flashcard.deck_manager import generate_all_decks

    init_db()
    last_line = int(get_sync_state('last_line') or 0)

    imported = 0
    errors = 0
    for line in lines:
        last_line += 1
        entry = _parse_line(line, last_line)
        if entry:
            cats = categorize(entry)
            insert_entry(entry, cats)
            imported += 1
            if not entry.is_correct:
                errors += 1

    if imported > 0:
        set_sync_state('last_line', str(last_line))
        log_path = os.path.join(os.path.expanduser("~"), "english.log")
        with open(log_path, 'a', encoding='utf-8') as f:
            for line in lines:
                if line.strip():
                    f.write(line if line.endswith('\n') else line + '\n')
        try:
            generate_all_decks()
        except Exception:
            pass

    return jsonify({"ok": True, "imported": imported, "errors": errors})


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555, debug=True)
