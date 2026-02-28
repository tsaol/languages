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
    insert_chat_message,
    get_chat_history,
    clear_chat_history,
    delete_chat_message,
    insert_flashcard,
    flashcard_exists,
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
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({"error": "unauthorized"}), 401
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


@app.route("/review/session", methods=["GET"])
@login_required
def review_session_load():
    """Load saved review session."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM sync_state WHERE key = 'review_session'").fetchone()
        if row:
            return jsonify(json.loads(row["value"]))
        return jsonify(None)
    finally:
        conn.close()


@app.route("/review/session", methods=["POST"])
@login_required
def review_session_save():
    """Save review session progress."""
    data = request.get_json()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES ('review_session', ?)",
            (json.dumps(data),)
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/daily/session", methods=["GET"])
@login_required
def daily_session_load():
    """Load saved daily session."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM sync_state WHERE key = 'daily_session'").fetchone()
        if row:
            return jsonify(json.loads(row["value"]))
        return jsonify(None)
    finally:
        conn.close()


@app.route("/daily/session", methods=["POST"])
@login_required
def daily_session_save():
    """Save daily session progress."""
    data = request.get_json()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES ('daily_session', ?)",
            (json.dumps(data),)
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


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
        "corrections": result.get("corrections", []),
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


@app.route("/vocab/translate", methods=["POST"])
@login_required
def vocab_translate():
    """Auto-translate an English word to Chinese using LLM."""
    data = request.get_json()
    word = data.get("word", "").strip()
    if not word:
        return jsonify({"chinese": ""})
    try:
        from englearn.scoring.llm_scorer import _invoke_model
        text = _invoke_model(
            f'Translate the English word "{word}" to Chinese. Reply with ONLY the Chinese translation (1-3 words), nothing else.',
            max_tokens=30,
        )
        return jsonify({"chinese": text.strip().strip('"').strip("'")})
    except Exception:
        return jsonify({"chinese": ""})


@app.route("/vocab/add", methods=["POST"])
@login_required
def vocab_add():
    data = request.get_json()
    word = data.get("word", "").strip()
    chinese = data.get("chinese", "").strip()
    category = data.get("category", "").strip()

    if not word or not chinese:
        return jsonify({"error": "Word and Chinese meaning are required"}), 400

    # Generate a fill-in-the-blank sentence for precise testing
    front = f'How do you say "{chinese}" in English?'
    hint = f"Category: {category}" if category else ""
    try:
        from englearn.scoring.llm_scorer import _invoke_model
        prompt = (
            f'Create a single English sentence using the word "{word}" where the word is replaced by ___. '
            f'Add the Chinese meaning ({chinese}) in parentheses after the blank. '
            f'The sentence should make the answer unambiguous. '
            f'Reply with ONLY the sentence, nothing else. '
            f'Example: "The company decided to ___ the new policy. (实施)"'
        )
        sentence = _invoke_model(prompt, max_tokens=80).strip().strip('"')
        if '___' in sentence:
            front = sentence
    except Exception:
        pass

    card_id = insert_flashcard(
        deck='vocab',
        front=front,
        back=word,
        hint=hint,
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
        # Generate fill-in-the-blank for updated word
        front = f'How do you say "{chinese}" in English?'
        try:
            from englearn.scoring.llm_scorer import _invoke_model
            prompt = (
                f'Create a single English sentence using the word "{word}" where the word is replaced by ___. '
                f'Add the Chinese meaning ({chinese}) in parentheses after the blank. '
                f'Reply with ONLY the sentence, nothing else.'
            )
            sentence = _invoke_model(prompt, max_tokens=80).strip().strip('"')
            if '___' in sentence:
                front = sentence
        except Exception:
            pass
        conn.execute(
            """UPDATE flashcards SET
                front = ?, back = ?, hint = ?
               WHERE id = ? AND deck = 'vocab'""",
            (front, word,
             f"Category: {category}" if category else "", card_id)
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


# ─── Chat ────────────────────────────────────────────────────────────────────


@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", active_page="chat")


@app.route("/api/chat/roles")
@login_required
def api_chat_roles():
    """Get available chat roles with their scenarios."""
    from englearn.scoring.llm_scorer import CHAT_ROLES
    roles = {}
    for rid, role in CHAT_ROLES.items():
        roles[rid] = {
            "name": role["name"],
            "title": role["title"],
            "description": role["description"],
            "appearance": role.get("appearance", ""),
            "personality": role["personality"],
            "scenarios": [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "desc": s["desc"],
                    "difficulty": s["difficulty"],
                    "vocabulary": s.get("vocabulary", []),
                    "location": s.get("location", ""),
                    "attire": s.get("attire", ""),
                }
                for s in role.get("scenarios", [])
            ],
        }
    return jsonify({"roles": roles})


@app.route("/api/chat/send", methods=["POST"])
@login_required
def api_chat_send():
    data = request.get_json()
    role_id = data.get("role_id", "").strip()
    message = data.get("message", "").strip()
    scenario_id = data.get("scenario_id", "").strip() or None

    if not role_id or not message:
        return jsonify({"error": "role_id and message are required"}), 400

    from englearn.scoring.llm_scorer import CHAT_ROLES, chat_reply, get_chat_scenario
    if role_id not in CHAT_ROLES:
        return jsonify({"error": "Invalid role_id"}), 400

    # Look up scenario if provided
    scenario = None
    if scenario_id:
        scenario = get_chat_scenario(role_id, scenario_id)

    # Insert user message
    user_msg_id = insert_chat_message(role_id, "user", message, scenario_id=scenario_id)

    # Search for relevant memories
    memories = []
    try:
        from englearn.memory.chat_memory import search_memories, store_message
        memories = search_memories(user_id="default", query=message, limit=5)
        # Store user message to memory for future recall
        store_message(user_id="default", role_id=role_id, message=message)
    except Exception:
        pass

    # Fetch history for context (filtered by scenario)
    history = get_chat_history(role_id, limit=20, scenario_id=scenario_id)

    # Get AI reply with memory context and scenario
    result = chat_reply(role_id, message, history, memories=memories, scenario=scenario)

    # Insert AI reply (corrections NOT stored — they are from the independent teacher agent
    # and should not pollute conversation context)
    ai_msg_id = insert_chat_message(role_id, role_id, result["reply"],
                                    scenario_id=scenario_id)

    return jsonify({
        "reply": result["reply"],
        "corrections": result.get("corrections", []),
        "user_msg_id": user_msg_id,
        "ai_msg_id": ai_msg_id,
    })


@app.route("/api/chat/start", methods=["POST"])
@login_required
def api_chat_start():
    """Start a new chat session. Returns the AI's first message.

    For scenarios, returns the scenario's first_message.
    For free talk, returns the role's default first_message.
    Clears previous history for this role+scenario combination.
    """
    data = request.get_json()
    role_id = data.get("role_id", "").strip()
    scenario_id = data.get("scenario_id", "").strip() or None

    if not role_id:
        return jsonify({"error": "role_id is required"}), 400

    from englearn.scoring.llm_scorer import CHAT_ROLES, get_chat_scenario
    role = CHAT_ROLES.get(role_id)
    if not role:
        return jsonify({"error": "Invalid role_id"}), 400

    # Clear previous history for this role+scenario
    clear_chat_history(role_id, scenario_id=scenario_id)

    # Get first message
    if scenario_id:
        scenario = get_chat_scenario(role_id, scenario_id)
        if scenario:
            first_msg = scenario["first_message"]
        else:
            first_msg = role["first_message"]
    else:
        first_msg = role["first_message"]

    # Store the first message as AI message
    msg_id = insert_chat_message(role_id, role_id, first_msg, scenario_id=scenario_id)

    return jsonify({"first_message": first_msg, "msg_id": msg_id})


@app.route("/api/chat/history")
@login_required
def api_chat_history():
    role_id = request.args.get("role_id", "").strip()
    scenario_id = request.args.get("scenario_id", "").strip() or None
    limit = int(request.args.get("limit", 20))

    if not role_id:
        return jsonify({"error": "role_id is required"}), 400

    messages = get_chat_history(role_id, limit=limit, scenario_id=scenario_id)
    # Parse corrections JSON for each message
    for msg in messages:
        if msg.get("corrections"):
            try:
                msg["corrections"] = json.loads(msg["corrections"])
            except (json.JSONDecodeError, TypeError):
                msg["corrections"] = []
        else:
            msg["corrections"] = []

    return jsonify({"messages": messages})


@app.route("/api/chat/delete-message", methods=["POST"])
@login_required
def api_chat_delete_message():
    """Delete a single chat message by ID."""
    data = request.get_json()
    msg_id = data.get("message_id")
    if not msg_id:
        return jsonify({"error": "message_id is required"}), 400
    ok = delete_chat_message(msg_id)
    return jsonify({"ok": ok})


# ─── Stats Dashboard ─────────────────────────────────────────────────────────


@app.route("/stats")
@login_required
def stats():
    """Study progress dashboard."""
    conn = get_connection()
    try:
        # Deck stats
        deck_stats = get_deck_stats()
        total_cards = sum(d['total'] for d in deck_stats)
        total_mastered = sum(d['mastered'] for d in deck_stats)

        # Quiz accuracy
        quiz_total = conn.execute("SELECT COUNT(*) as c FROM quiz_results").fetchone()['c']
        quiz_correct = conn.execute("SELECT COALESCE(SUM(is_correct), 0) as c FROM quiz_results").fetchone()['c']
        quiz_pct = round(quiz_correct / quiz_total * 100) if quiz_total > 0 else 0

        # Weekly activity (last 7 days)
        from englearn.db.models import get_progress_history
        all_progress = get_progress_history(days=30)
        progress_map = {p['date']: p for p in all_progress}

        weekly = []
        for i in range(6, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            if d in progress_map:
                weekly.append(progress_map[d])
            else:
                weekly.append({'date': d, 'cards_reviewed': 0, 'cards_correct': 0, 'quiz_taken': 0, 'quiz_correct': 0})

        # Error categories
        from englearn.db.models import get_category_stats
        categories = get_category_stats()

        # Streak calculation
        streak = 0
        today = datetime.now().strftime("%Y-%m-%d")
        check_date = datetime.now()
        while True:
            d = check_date.strftime("%Y-%m-%d")
            if d in progress_map:
                p = progress_map[d]
                if p['cards_reviewed'] > 0 or p['quiz_taken'] > 0:
                    streak += 1
                    check_date -= timedelta(days=1)
                    continue
            break

        # Today's activity
        today_progress = progress_map.get(today, {
            'cards_reviewed': 0, 'cards_correct': 0,
            'quiz_taken': 0, 'quiz_correct': 0,
        })
        today_cards = today_progress['cards_reviewed']
        today_cards_correct = today_progress['cards_correct']
        today_quiz = today_progress['quiz_taken']
        today_quiz_correct = today_progress['quiz_correct']

        # Today's talk scenarios reviewed
        today_talk = conn.execute(
            "SELECT COUNT(*) as c FROM talk_scenarios WHERE last_review = ?", (today,)
        ).fetchone()['c']

        # Today's new vocab added
        today_vocab = conn.execute(
            "SELECT COUNT(*) as c FROM flashcards WHERE deck = 'vocab' AND next_review = ?", (today,)
        ).fetchone()['c']

    finally:
        conn.close()

    today_data = {
        'cards_reviewed': today_cards,
        'cards_correct': today_cards_correct,
        'cards_pct': round(today_cards_correct / today_cards * 100) if today_cards > 0 else 0,
        'talk_taken': today_quiz,
        'talk_correct': today_quiz_correct,
        'talk_pct': round(today_quiz_correct / today_quiz * 100) if today_quiz > 0 else 0,
        'talk_rounds': today_talk,
        'vocab_added': today_vocab,
        'total_actions': today_cards + today_quiz + today_talk,
    }

    return render_template("stats.html",
        total_cards=total_cards,
        total_mastered=total_mastered,
        accuracy={'total': quiz_total, 'correct': quiz_correct, 'pct': quiz_pct},
        weekly=weekly,
        progress=all_progress,
        categories=categories,
        streak=streak,
        today=today_data,
    )


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


# ─── Review Word Details ──────────────────────────────────────────────────────


@app.route("/review/word-details", methods=["POST"])
@login_required
def review_word_details():
    """Generate or return cached word details (syllables, roots, phonetic)."""
    data = request.get_json()
    card_id = data.get("card_id")
    word = data.get("word", "")
    chinese = data.get("chinese", "")

    if not card_id or not word:
        return jsonify({"error": "card_id and word required"}), 400

    # Check cache first
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT syllables, word_roots, phonetic FROM flashcards WHERE id = ?", (card_id,)
        ).fetchone()
        if row and row['syllables']:
            return jsonify({
                "syllables": row['syllables'] or "",
                "word_roots": row['word_roots'] or "",
                "phonetic": row['phonetic'] or "",
            })
    finally:
        conn.close()

    # Generate via LLM
    try:
        from englearn.scoring.llm_scorer import generate_word_details
        result = generate_word_details(word, chinese)
        syllables = result.get("syllables", "")
        word_roots = result.get("word_roots", "")
        phonetic = result.get("phonetic", "")
        if syllables:
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE flashcards SET syllables = ?, word_roots = ?, phonetic = ? WHERE id = ?",
                    (syllables, word_roots, phonetic, card_id)
                )
                conn.commit()
            finally:
                conn.close()
        return jsonify({"syllables": syllables, "word_roots": word_roots, "phonetic": phonetic})
    except Exception as e:
        return jsonify({"syllables": "", "word_roots": "", "phonetic": "", "error": str(e)[:100]})


# ─── Review Memory Tip ────────────────────────────────────────────────────────


@app.route("/review/memory-tip", methods=["POST"])
@login_required
def review_memory_tip():
    """Generate a memory tip for a misspelled word."""
    data = request.get_json()
    word = data.get("word", "")
    user_answer = data.get("user_answer", "")
    chinese = data.get("chinese", "")

    if not word or not user_answer:
        return jsonify({"error": "word and user_answer required"}), 400

    try:
        from englearn.scoring.llm_scorer import generate_memory_tip
        result = generate_memory_tip(word, user_answer, chinese)
        return jsonify({
            "tip": result.get("tip", ""),
            "error_analysis": result.get("error_analysis", ""),
        })
    except Exception as e:
        return jsonify({"tip": "", "error_analysis": "", "error": str(e)[:100]})


# ─── Chat → Review Pipeline ──────────────────────────────────────────────────


@app.route("/api/chat/save-correction", methods=["POST"])
@login_required
def api_chat_save_correction():
    """Save a chat correction as a flashcard in the daily deck."""
    data = request.get_json()
    wrong = data.get("wrong", "").strip()
    correct = data.get("correct", "").strip()
    idiomatic = data.get("idiomatic", "").strip()
    pattern = data.get("pattern", "").strip()
    tense = data.get("tense", "").strip()

    if not wrong or not correct:
        return jsonify({"error": "wrong and correct are required"}), 400

    # Dedup check
    if flashcard_exists(deck="daily", back=correct, front_contains=wrong):
        return jsonify({"ok": True, "duplicate": True})

    # Build flashcard
    front = f'Correct: "{wrong}"'
    back = correct
    hint_parts = []
    if pattern:
        hint_parts.append(f"Pattern: {pattern}")
    if tense:
        hint_parts.append(f"Tense: {tense}")
    hint = " | ".join(hint_parts)

    card_id = insert_flashcard(deck="daily", front=front, back=back, hint=hint)
    return jsonify({"ok": True, "card_id": card_id})


# ─── API ──────────────────────────────────────────────────────────────────────


@app.route("/api/sync-log", methods=["POST"])
@login_required
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


# ─── CLI API endpoints ───────────────────────────────────────────────────────


@app.route("/api/review/cards")
@login_required
def api_review_cards():
    """Get due flashcards as JSON for CLI."""
    deck = request.args.get("deck", "")
    limit = int(request.args.get("limit", 20))
    cards = get_due_flashcards(deck=deck if deck else None, limit=limit)
    return jsonify({"cards": cards, "total": len(cards)})


@app.route("/api/talk/scenarios")
@login_required
def api_talk_scenarios():
    """Get due talk scenarios as JSON for CLI."""
    from englearn.quiz.conversation import SCENARIO_TEMPLATES
    init_db()
    seed_talk_scenarios(SCENARIO_TEMPLATES)
    _generate_dynamic_scenarios()
    limit = int(request.args.get("limit", 10))
    include_all = request.args.get("all", "0") == "1"
    scenarios = get_due_talk_scenarios(limit=limit, include_reviewed=include_all)
    random.shuffle(scenarios)
    return jsonify({"scenarios": scenarios, "total": len(scenarios)})


@app.route("/api/stats")
@login_required
def api_stats():
    """Get stats as JSON for CLI."""
    conn = get_connection()
    try:
        deck_stats = get_deck_stats()
        total_cards = sum(d['total'] for d in deck_stats)
        total_mastered = sum(d['mastered'] for d in deck_stats)

        quiz_total = conn.execute("SELECT COUNT(*) as c FROM quiz_results").fetchone()['c']
        quiz_correct = conn.execute("SELECT COALESCE(SUM(is_correct), 0) as c FROM quiz_results").fetchone()['c']
        quiz_pct = round(quiz_correct / quiz_total * 100) if quiz_total > 0 else 0

        from englearn.db.models import get_progress_history, get_category_stats
        all_progress = get_progress_history(days=30)
        progress_map = {p['date']: p for p in all_progress}

        weekly = []
        for i in range(6, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            weekly.append(progress_map.get(d, {'date': d, 'cards_reviewed': 0, 'cards_correct': 0, 'quiz_taken': 0, 'quiz_correct': 0}))

        today = datetime.now().strftime("%Y-%m-%d")
        tp = progress_map.get(today, {'cards_reviewed': 0, 'cards_correct': 0, 'quiz_taken': 0, 'quiz_correct': 0})
        today_talk = conn.execute("SELECT COUNT(*) as c FROM talk_scenarios WHERE last_review = ?", (today,)).fetchone()['c']

        # Streak
        streak = 0
        check_date = datetime.now()
        while True:
            d = check_date.strftime("%Y-%m-%d")
            if d in progress_map:
                p = progress_map[d]
                if p['cards_reviewed'] > 0 or p['quiz_taken'] > 0:
                    streak += 1
                    check_date -= timedelta(days=1)
                    continue
            break
    finally:
        conn.close()

    return jsonify({
        "total_cards": total_cards,
        "total_mastered": total_mastered,
        "accuracy": {"total": quiz_total, "correct": quiz_correct, "pct": quiz_pct},
        "weekly": weekly,
        "today": {
            "cards_reviewed": tp['cards_reviewed'],
            "cards_correct": tp['cards_correct'],
            "talk_taken": tp['quiz_taken'],
            "talk_correct": tp['quiz_correct'],
            "talk_rounds": today_talk,
        },
        "streak": streak,
        "decks": deck_stats,
        "categories": get_category_stats(),
    })


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555, debug=True)
