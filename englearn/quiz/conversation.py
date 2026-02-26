"""Conversation-based practice mode with LLM scoring.

Puts sentence patterns into realistic work dialogue scenarios
and lets the user practice through role-play. Uses the same
Kimi K2.5 LLM scorer as the web Talk page.
"""
import json
import random
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


def _score_with_llm(context, pattern, ai_says, user_input, good_responses):
    """Score using LLM (same as web). Falls back to similarity."""
    try:
        from englearn.scoring.llm_scorer import score_response
        return score_response(context, pattern, ai_says, user_input, good_responses)
    except Exception:
        from difflib import SequenceMatcher
        best_score = 0
        best_match = good_responses[0] if good_responses else ""
        user_clean = user_input.lower().strip().rstrip('.!?')
        for resp in good_responses:
            resp_clean = resp.lower().strip().rstrip('.!?')
            sim = SequenceMatcher(None, user_clean, resp_clean).ratio()
            if sim > best_score:
                best_score = sim
                best_match = resp
        return {
            "score": best_score,
            "is_correct": best_score >= 0.80,
            "dimensions": {},
            "feedback": "",
            "better_expression": best_match,
            "common_mistake": "",
            "corrections": [],
        }


def _dim_bar(score, width=15):
    """Render a dimension score as a mini bar."""
    filled = int(score * width)
    return '█' * filled + '░' * (width - filled)


def run_conversation(count: int = 10):
    """Run a conversation practice session with LLM scoring."""
    # Load from DB (SM-2 scheduled) first, then templates as fallback
    models.seed_talk_scenarios(SCENARIO_TEMPLATES)
    db_scenarios = models.get_due_talk_scenarios(limit=count)

    if db_scenarios:
        scenarios = db_scenarios
    else:
        all_scenarios = list(SCENARIO_TEMPLATES)
        random.shuffle(all_scenarios)
        scenarios = all_scenarios[:count]

    total = len(scenarios)
    score_total = 0
    answered = 0
    failed = []

    print()
    print("  ╔═══════════════════════════════════════════════════════╗")
    print("  ║        Conversation Practice / 对话练习               ║")
    print("  ╠═══════════════════════════════════════════════════════╣")
    print("  ║  I'll set up a work scenario.                        ║")
    print("  ║  You respond in English. LLM scores your answer.     ║")
    print("  ║  Type 'q' to quit, 's' to skip.                     ║")
    print("  ╚═══════════════════════════════════════════════════════╝")
    print()

    try:
        for i, scene in enumerate(scenarios):
            good_responses = scene.get('good_responses', [])
            if isinstance(good_responses, str):
                good_responses = json.loads(good_responses)

            print(f"  ── Round {i + 1}/{total} ──────────────────────────────────")
            print()
            print(f"  🤖 AI: \"{scene['ai_says']}\"")
            print()
            print(f"  📌 Scenario: {scene['context']}")
            print(f"  🎯 Pattern:  {scene['pattern']}")
            print()

            user_input = input("  👤 You: ").strip()

            if user_input.lower() == 'q':
                break
            if user_input.lower() == 's':
                print(f"\n  ⏭️  Skipped")
                print(f"  💡 Example: {good_responses[0] if good_responses else 'N/A'}")
                print()
                # Update SM-2 as failed
                if 'id' in scene and scene['id']:
                    models.update_talk_scenario_sm2(scene['id'], 0.0)
                continue

            answered += 1
            print("\n  Scoring...", end="", flush=True)

            result = _score_with_llm(
                scene['context'], scene['pattern'], scene['ai_says'],
                user_input, good_responses
            )

            score = result['score']
            score_total += score

            # Update SM-2
            if 'id' in scene and scene['id']:
                models.update_talk_scenario_sm2(scene['id'], score)

            print(f"\r  {'─' * 50}")
            print()

            # Result icon
            if score >= 0.70:
                print(f"  ✅ Excellent! ({score:.0%})")
            elif score >= 0.45:
                print(f"  ⚠️  Close! ({score:.0%})")
                failed.append(i)
            else:
                print(f"  ❌ Not quite. ({score:.0%})")
                failed.append(i)

            # Your answer with corrections
            print()
            corrections = result.get('corrections', [])
            if corrections:
                print(f"  Your answer: {user_input}")
                for c in corrections:
                    icon = {'grammar': '📝', 'spelling': '✏️', 'word_choice': '💬'}.get(c.get('type', ''), '•')
                    print(f"    {icon} \"{c.get('wrong', '')}\" → \"{c.get('correct', '')}\" ({c.get('type', '')})")
            else:
                print(f"  Your answer: {user_input}")

            # Better expression
            better = result.get('better_expression', '')
            if better:
                print(f"  Better:      {better}")

            # Dimensions
            dims = result.get('dimensions', {})
            if dims:
                print()
                labels = {'grammar': 'Grammar ', 'meaning': 'Meaning ', 'tone': 'Tone    ',
                          'fluency': 'Fluency ', 'pattern': 'Pattern ', 'vocabulary': 'Vocab   '}
                for k, v in dims.items():
                    s = v.get('score', 0) if isinstance(v, dict) else 0
                    note = v.get('note', '') if isinstance(v, dict) else ''
                    label = labels.get(k, k.ljust(8))
                    print(f"  {label} [{_dim_bar(s)}] {s:.0%}  {note}")

            # Feedback
            feedback = result.get('feedback', '')
            if feedback:
                print(f"\n  💡 {feedback}")

            # Common mistake
            mistake = result.get('common_mistake', '')
            if mistake:
                print(f"  ⚠  Common mistake: {mistake}")

            print()

            # Record
            models.record_quiz_result(
                quiz_type='conversation',
                question=scene['context'],
                user_answer=user_input,
                correct_answer=better or (good_responses[0] if good_responses else ''),
                is_correct=result.get('is_correct', False),
                flashcard_id=scene.get('id'),
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
        avg_score = score_total / answered
        print(f"  Avg Score: {avg_score:.0%}")
        correct_count = answered - len(failed)
        print(f"  Correct:   {correct_count}/{answered}")
        if avg_score >= 0.70:
            print(f"  Great conversational English!")
        elif avg_score >= 0.45:
            print(f"  Good effort! Keep practicing.")
        else:
            print(f"  Review the patterns and try again.")
    print(f"  ══════════════════════════════════════════")
    print()

    models.record_daily_progress(quiz_taken=answered, quiz_correct=answered - len(failed))
