"""Conversation-based practice mode.

Instead of dry flashcards, this puts sentence patterns into realistic
work dialogue scenarios and lets the user practice through role-play.
"""
import os
import re
import random
import difflib
import sqlite3
from datetime import datetime
from collections import defaultdict
from englearn.config import DB_PATH
from englearn.db import models


# Work scenarios that map to common patterns
SCENARIO_TEMPLATES = [
    {
        "context": "You want your colleague to read a file for you.",
        "pattern": "Could you + verb + object?",
        "ai_says": "What do you need?",
        "good_responses": [
            "Could you read this file for me?",
            "Could you check this file?",
            "Can you take a look at this file?",
        ],
    },
    {
        "context": "You want to clone a repo to a specific folder.",
        "pattern": "Clone + something + to + path",
        "ai_says": "Where should I put the code?",
        "good_responses": [
            "Clone this repo to ~/codes/.",
            "Please clone it to the ~/codes directory.",
        ],
    },
    {
        "context": "The path is wrong and you need to correct it.",
        "pattern": "The X is wrong, it should be Y.",
        "ai_says": "I saved it to ~/codeS. Is that correct?",
        "good_responses": [
            "The path is wrong. It should be ~/codes/.",
            "Wrong path — it should be ~/codes/.",
            "That's incorrect. It should be ~/codes/.",
        ],
    },
    {
        "context": "You want to check if a GitHub repo exists.",
        "pattern": "Do I have a ... named/called ... on platform?",
        "ai_says": "What are you looking for on GitHub?",
        "good_responses": [
            "Do I have a repo called languages on GitHub?",
            "Do I have a repo named languages on GitHub?",
            "Is there a repo called languages in my GitHub account?",
        ],
    },
    {
        "context": "You need someone to install software on a machine.",
        "pattern": "Install + something + on + machine",
        "ai_says": "What do you need me to set up?",
        "good_responses": [
            "Install the CloudWatch agent on this machine.",
            "Please install the agent on the local machine.",
        ],
    },
    {
        "context": "You want to create a new feature.",
        "pattern": "I'd like to + verb + object",
        "ai_says": "Any new features you want to add?",
        "good_responses": [
            "I'd like to add Zhihu as a new publishing channel.",
            "I'd like to create a new feature for Zhihu publishing.",
        ],
    },
    {
        "context": "You want to ask if something has a certain feature.",
        "pattern": "Does it come with ...?",
        "ai_says": "I found a tool that might work.",
        "good_responses": [
            "Does it come with a web UI?",
            "Does it come with a user interface?",
            "Does it have a built-in dashboard?",
        ],
    },
    {
        "context": "You want someone to review your code.",
        "pattern": "Could you review + object?",
        "ai_says": "The code is ready. What's next?",
        "good_responses": [
            "Could you review the code and check for issues?",
            "Could you take a look at the code?",
            "Can you review it before I push?",
        ],
    },
    {
        "context": "You want to ask which region to use on AWS.",
        "pattern": "Does it matter which X I choose?",
        "ai_says": "You need to pick an AWS region.",
        "good_responses": [
            "Does it matter which region I choose?",
            "Is there a difference between regions?",
            "Does the region matter?",
        ],
    },
    {
        "context": "You want to focus on one project and ignore others.",
        "pattern": "Never mind + noun, let's focus on + topic",
        "ai_says": "There are several projects here. Which one?",
        "good_responses": [
            "Never mind the others, let's focus on ai-writing.",
            "Ignore the rest. Let's focus on ai-writing.",
            "Let's just focus on ai-writing for now.",
        ],
    },
    {
        "context": "You want to update a configuration key.",
        "pattern": "Please update + noun + to + value",
        "ai_says": "The current token seems expired.",
        "good_responses": [
            "Please update the token to the new value.",
            "Could you update the API key?",
            "Update the configuration key for me.",
        ],
    },
    {
        "context": "You want to check if something is already set up.",
        "pattern": "I have already set + something",
        "ai_says": "Do we need to configure the API keys?",
        "good_responses": [
            "I've already set the API key and base URL.",
            "I have already configured them.",
            "They're already set up.",
        ],
    },
    {
        "context": "You want to create a GitHub issue.",
        "pattern": "Create an issue + to + verb",
        "ai_says": "This bug needs to be tracked.",
        "good_responses": [
            "Create an issue to track this bug.",
            "Let's create an issue to investigate this.",
            "Please open an issue for this.",
        ],
    },
    {
        "context": "You want to know how a tool works.",
        "pattern": "How do I use X?",
        "ai_says": "Here's the new tool.",
        "good_responses": [
            "How do I use this tool?",
            "Can you walk me through how to use it?",
            "How does this work?",
        ],
    },
    {
        "context": "Something is not working and you need help.",
        "pattern": "X isn't working. Could you help me fix it?",
        "ai_says": "What seems to be the problem?",
        "good_responses": [
            "The deployment isn't working. Could you help me fix it?",
            "It's not working properly. Can you take a look?",
            "Something's broken. Could you help me debug it?",
        ],
    },
    {
        "context": "You want to check the progress of something.",
        "pattern": "How is X going? / What's the status of X?",
        "ai_says": "We started the evaluation yesterday.",
        "good_responses": [
            "How is the evaluation going?",
            "What's the status of the evaluation?",
            "Any updates on the evaluation?",
        ],
    },
    {
        "context": "You want to suggest an improvement.",
        "pattern": "I don't think X is ... enough. Could you ...?",
        "ai_says": "Here's the current design.",
        "good_responses": [
            "I don't think this is good enough. Could you improve it?",
            "I think we can do better. Could you revise it?",
            "This isn't quite right. Can you make it better?",
        ],
    },
    {
        "context": "You want to generate something.",
        "pattern": "Can you generate + object + for me?",
        "ai_says": "What do you need?",
        "good_responses": [
            "Can you generate a pre-signed URL for me?",
            "Could you generate a report for this?",
            "Please generate the output file.",
        ],
    },
    {
        "context": "You want to ask what someone recommends.",
        "pattern": "Are there any good ... for doing ...?",
        "ai_says": "I can help you find tools.",
        "good_responses": [
            "Are there any good tools for publishing articles?",
            "Are there any good libraries for this?",
            "Do you know any good open-source projects for this?",
        ],
    },
    {
        "context": "You want to commit and push code.",
        "pattern": "Please commit and push the changes.",
        "ai_says": "The code changes are ready.",
        "good_responses": [
            "Please commit and push the changes.",
            "Commit this and push to the remote.",
            "Go ahead and commit, then push.",
        ],
    },
]


def _load_dynamic_scenarios():
    """Load additional scenarios from database entries."""
    extra = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT original, corrected, idiomatic, explanation, pattern
            FROM log_entries
            WHERE status = 'incorrect'
              AND pattern IS NOT NULL AND pattern != 'N/A' AND pattern != ''
              AND idiomatic IS NOT NULL AND idiomatic != 'N/A'
            ORDER BY RANDOM() LIMIT 30
        """).fetchall()
        conn.close()

        for r in rows:
            if any('\u4e00' <= c <= '\u9fff' for c in (r['idiomatic'] or '')):
                continue
            extra.append({
                "context": f"Your original attempt: \"{r['original'][:60]}\"",
                "pattern": r['pattern'],
                "ai_says": f"(Based on your past error) Try saying this correctly:",
                "good_responses": [r['idiomatic'], r['corrected']],
            })
    except Exception:
        pass
    return extra


def _score_response(user_input: str, good_responses: list) -> tuple:
    """Score user response against good responses. Returns (score, best_match)."""
    best_score = 0
    best_match = good_responses[0] if good_responses else ""
    user_clean = user_input.lower().strip().rstrip('.!?')

    for resp in good_responses:
        resp_clean = resp.lower().strip().rstrip('.!?')
        sim = difflib.SequenceMatcher(None, user_clean, resp_clean).ratio()
        if sim > best_score:
            best_score = sim
            best_match = resp
    return best_score, best_match


def run_conversation(count: int = 10):
    """Run a conversation practice session."""
    all_scenarios = list(SCENARIO_TEMPLATES)
    dynamic = _load_dynamic_scenarios()
    all_scenarios.extend(dynamic)
    random.shuffle(all_scenarios)

    scenarios = all_scenarios[:count]
    total = len(scenarios)
    score = 0
    answered = 0

    print()
    print("  ╔═══════════════════════════════════════════════════════╗")
    print("  ║        Conversation Practice / 对话练习               ║")
    print("  ╠═══════════════════════════════════════════════════════╣")
    print("  ║  I'll set up a work scenario.                        ║")
    print("  ║  You respond in English.                             ║")
    print("  ║  Type 'q' to quit, 'skip' to skip.                  ║")
    print("  ╚═══════════════════════════════════════════════════════╝")
    print()

    try:
        for i, scene in enumerate(scenarios):
            print(f"  ── Round {i + 1}/{total} ──────────────────────────────────")
            print()
            print(f"  📌 Scenario: {scene['context']}")
            print(f"  🎯 Pattern:  {scene['pattern']}")
            print()
            print(f"  🤖 AI: \"{scene['ai_says']}\"")
            print()

            user_input = input("  👤 You: ").strip()

            if user_input.lower() == 'q':
                break
            if user_input.lower() == 'skip':
                print(f"  💡 Example: {scene['good_responses'][0]}")
                print()
                continue

            answered += 1
            sim, best = _score_response(user_input, scene['good_responses'])

            print()
            if sim >= 0.80:
                print("  ✅ Excellent!")
                score += 1
            elif sim >= 0.55:
                print("  ⚠️  Close! But can be better.")
            else:
                print("  ❌ Not quite. Study the example below.")

            print()
            print(f"  Your answer:    {user_input}")
            print(f"  Best response:  {best}")
            if len(scene['good_responses']) > 1:
                print(f"  Also accepted:  {scene['good_responses'][1]}")
            print()

            # Record to quiz_results
            models.record_quiz_result(
                quiz_type='conversation',
                question=scene['context'],
                user_answer=user_input,
                correct_answer=best,
                is_correct=(sim >= 0.80),
            )

            input("  Press Enter to continue...")
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n\n  Session interrupted.")

    # Summary
    print()
    print(f"  ══════════════════════════════════════════")
    print(f"  Conversation Practice Complete!")
    print(f"  ──────────────────────────────────────────")
    print(f"  Rounds:   {answered}/{total}")
    if answered > 0:
        pct = score * 100 // answered
        print(f"  Score:    {score}/{answered} ({pct}%)")
        if pct >= 80:
            print(f"  Great conversational English!")
        elif pct >= 50:
            print(f"  Good effort! Keep practicing.")
        else:
            print(f"  Review the patterns and try again.")
    print(f"  ══════════════════════════════════════════")
    print()

    models.record_daily_progress(quiz_taken=answered, quiz_correct=score)
