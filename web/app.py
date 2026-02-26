"""EngLearn Web UI - Flask application for English learning."""
import sys
import os
import json
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
    seed_talk_scenarios,
    get_due_talk_scenarios,
    update_talk_scenario_sm2,
    insert_talk_scenario,
    get_recent_error_entries,
    cache_flashcard_example,
)
from englearn.db.database import get_connection, init_db

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
    # Count due talk scenarios for daily session button (#1)
    init_db()
    talk_due = 0
    try:
        from englearn.quiz.conversation import SCENARIO_TEMPLATES
        seed_talk_scenarios(SCENARIO_TEMPLATES)
        conn = get_connection()
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COUNT(*) as c FROM talk_scenarios WHERE next_review <= ?", (today,)
        ).fetchone()
        talk_due = row['c'] if row else 0
        conn.close()
    except Exception:
        pass
    return render_template("review.html", deck=deck, cards=cards, total=len(cards), talk_due=talk_due)


@app.route("/daily")
@login_required
def daily_session():
    """Unified daily session mixing review cards + talk scenarios (#1)."""
    init_db()
    from englearn.quiz.conversation import SCENARIO_TEMPLATES
    seed_talk_scenarios(SCENARIO_TEMPLATES)
    _generate_dynamic_scenarios()

    # Get 5-8 due flashcards
    cards = get_due_flashcards(limit=8)
    # Get 2-3 due talk scenarios
    scenarios = get_due_talk_scenarios(limit=3)
    random.shuffle(scenarios)

    return render_template("daily.html", cards=cards, scenarios=scenarios,
                           total_cards=len(cards), total_scenarios=len(scenarios))


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
    from englearn.quiz.conversation import SCENARIO_TEMPLATES
    # Ensure DB is up to date and seed templates
    init_db()
    seed_talk_scenarios(SCENARIO_TEMPLATES)
    # Generate dynamic scenarios from recent errors (#6)
    _generate_dynamic_scenarios()
    # Load due scenarios with SM-2 (#3)
    scenarios = get_due_talk_scenarios(limit=10)
    random.shuffle(scenarios)
    return render_template("talk.html", scenarios=scenarios, total=len(scenarios))


def _generate_dynamic_scenarios():
    """Generate new Talk scenarios from recent english.log errors (#6)."""
    from englearn.db.models import get_sync_state, set_sync_state
    # Rate limit: max 5 per day
    today = datetime.now().strftime("%Y-%m-%d")
    gen_key = f"scenarios_generated_{today}"
    count = int(get_sync_state(gen_key) or 0)
    if count >= 5:
        return

    entries = get_recent_error_entries(limit=5 - count)
    if not entries:
        return

    try:
        from englearn.scoring.llm_scorer import generate_scenario
        for entry in entries:
            scenario = generate_scenario(
                entry['original'], entry.get('corrected', ''), entry.get('pattern', '')
            )
            if scenario and scenario.get('context') and scenario.get('good_responses'):
                insert_talk_scenario(
                    context=scenario['context'],
                    pattern=scenario.get('pattern', entry.get('pattern', '')),
                    ai_says=scenario.get('ai_says', ''),
                    good_responses=scenario.get('good_responses', []),
                    source='generated',
                    source_entry_id=entry['id'],
                )
                count += 1
        set_sync_state(gen_key, str(count))
    except Exception:
        pass


@app.route("/talk/session", methods=["GET"])
@login_required
def talk_session_load():
    """Load saved talk session from DB."""
    import json
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM sync_state WHERE key = 'talk_session'"
        ).fetchone()
        if row:
            return jsonify(json.loads(row["value"]))
        return jsonify(None)
    finally:
        conn.close()


@app.route("/talk/session", methods=["POST"])
@login_required
def talk_session_save():
    """Save talk session progress to DB."""
    import json
    data = request.get_json()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES ('talk_session', ?)",
            (json.dumps(data),)
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/talk/answer", methods=["POST"])
@login_required
def talk_answer():
    data = request.get_json()
    user_answer = data.get("answer", "").strip()
    good_responses = data.get("good_responses", [])
    context = data.get("context", "")
    pattern = data.get("pattern", "")
    ai_says = data.get("ai_says", "")
    scenario_id = data.get("scenario_id")

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

    # Update SM-2 for talk scenario (#3)
    if scenario_id:
        try:
            update_talk_scenario_sm2(scenario_id, result["score"])
        except Exception:
            pass

    return jsonify({
        "ok": True,
        "score": result["score"],
        "is_correct": result["is_correct"],
        "best_response": best,
        "feedback": result.get("feedback", ""),
        "dimensions": result.get("dimensions", {}),
        "common_mistake": result.get("common_mistake", ""),
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


# ─── Review Example Sentence (#4) ────────────────────────────────────────────


@app.route("/review/example", methods=["POST"])
@login_required
def review_example():
    """Generate or return cached example sentence for a flashcard."""
    data = request.get_json()
    card_id = data.get("card_id")
    word = data.get("word", "")
    chinese = data.get("chinese", "")
    category = data.get("category", "")

    if not card_id:
        return jsonify({"error": "card_id required"}), 400

    # Check cache first
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT example_sentence, collocation FROM flashcards WHERE id = ?", (card_id,)
        ).fetchone()
        if row and row['example_sentence']:
            return jsonify({
                "sentence": row['example_sentence'],
                "collocation": row['collocation'] or "",
            })
    finally:
        conn.close()

    # Generate via LLM
    try:
        from englearn.scoring.llm_scorer import generate_example_sentence
        result = generate_example_sentence(word, chinese, category)
        sentence = result.get("sentence", "")
        collocation = result.get("collocation", "")
        if sentence:
            cache_flashcard_example(card_id, sentence, collocation)
        return jsonify({"sentence": sentence, "collocation": collocation})
    except Exception as e:
        return jsonify({"sentence": "", "collocation": "", "error": str(e)[:100]})


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
