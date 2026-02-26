"""LLM-based semantic scoring using Amazon Bedrock Kimi K2.5."""
import json
import boto3

BEDROCK_MODEL = "moonshotai.kimi-k2.5"
BEDROCK_CHAT_MODEL = "mistral.mistral-large-3-675b-instruct"
BEDROCK_REGION = "us-east-1"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _client


def _invoke_model(prompt: str, max_tokens: int = 400) -> str:
    """Invoke Kimi K2.5 on Bedrock and return text response."""
    client = _get_client()
    resp = client.invoke_model(
        modelId=BEDROCK_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }),
    )
    body = json.loads(resp["body"].read())
    return body["choices"][0]["message"]["content"].strip()


def _parse_json(text: str) -> dict:
    """Extract JSON from model response."""
    if text.startswith("{"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    return {}


def score_response(context: str, pattern: str, ai_says: str,
                   user_answer: str, good_responses: list) -> dict:
    """Score a user's English response using Kimi K2.5 with 6-dimension evaluation."""
    examples = "\n".join(f"  - {r}" for r in good_responses)

    prompt = f"""You are an English tutor evaluating a Chinese learner's response in a work scenario.

Scenario: {context}
Target pattern: {pattern}
AI said: "{ai_says}"

Good example responses:
{examples}

Student's response: "{user_answer}"

Evaluate on 6 dimensions (each 0.0-1.0):
1. grammar: Subject-verb agreement, tense, articles, prepositions
2. meaning: Does it address the scenario correctly?
3. tone: Appropriate politeness for workplace
4. fluency: Natural word order, not a direct Chinese translation
5. pattern: Did the user apply the target pattern?
6. vocabulary: Word choice precision

Also identify specific errors in the student's sentence. For each error, provide the exact wrong word/phrase, the correction, and the error type (grammar, spelling, or word_choice).

Respond in this exact JSON format only, no other text:
{{"score": <weighted average 0.0-1.0>, "is_correct": <true if score >= 0.7>, "dimensions": {{"grammar": {{"score": <0-1>, "note": "<brief>"}}, "meaning": {{"score": <0-1>, "note": "<brief>"}}, "tone": {{"score": <0-1>, "note": "<brief>"}}, "fluency": {{"score": <0-1>, "note": "<brief>"}}, "pattern": {{"score": <0-1>, "note": "<brief>"}}, "vocabulary": {{"score": <0-1>, "note": "<brief>"}}}}, "feedback": "<1 sentence overall feedback>", "better_expression": "<more natural way to say it>", "common_mistake": "<typical Chinese->English error relevant here>", "corrections": [<list of {{"wrong": "<exact wrong word/phrase from student>", "correct": "<corrected version>", "type": "<grammar|spelling|word_choice>"}}>, return empty list if no errors]}}"""

    try:
        text = _invoke_model(prompt)
        result = _parse_json(text)

        return {
            "score": float(result.get("score", 0)),
            "is_correct": bool(result.get("is_correct", False)),
            "dimensions": result.get("dimensions", {}),
            "feedback": result.get("feedback", ""),
            "better_expression": result.get("better_expression", ""),
            "common_mistake": result.get("common_mistake", ""),
            "corrections": result.get("corrections", []),
        }
    except Exception as e:
        # Fallback to simple matching
        from difflib import SequenceMatcher
        best_score = 0
        best_match = good_responses[0] if good_responses else ""
        user_clean = user_answer.lower().strip().rstrip(".!?")
        for resp in good_responses:
            resp_clean = resp.lower().strip().rstrip(".!?")
            sim = SequenceMatcher(None, user_clean, resp_clean).ratio()
            if sim > best_score:
                best_score = sim
                best_match = resp
        return {
            "score": best_score,
            "is_correct": best_score >= 0.80,
            "dimensions": {},
            "feedback": f"(Fallback: {str(e)[:60]})",
            "better_expression": best_match,
            "common_mistake": "",
            "corrections": [],
        }


def generate_example_sentence(word: str, chinese: str, category: str) -> dict:
    """Generate an example sentence and collocation tip for a vocab word."""
    prompt = f"""Generate a work-context example sentence using the English word "{word}" (meaning: {chinese}, category: {category}).

Respond in JSON only:
{{"sentence": "<1 example sentence using the word in a work context>", "collocation": "<common word combinations with this word, e.g. configure + settings/server>"}}"""

    try:
        text = _invoke_model(prompt, max_tokens=150)
        return _parse_json(text)
    except Exception:
        return {"sentence": "", "collocation": ""}


CHAT_ROLES = {
    "sarah": {
        "name": "Sarah",
        "desc": "You are Sarah, an American tech PM at a startup. You're friendly, direct, and use casual American English. You talk about work, projects, meetings, team dynamics. You occasionally use American slang and idioms. Keep responses under 80 words."
    },
    "james": {
        "name": "James",
        "desc": "You are James, a British English teacher. You're patient, encouraging, and use British English. You challenge the learner with idioms, phrasal verbs, and advanced vocabulary. You ask follow-up questions. Keep responses under 80 words."
    }
}


def chat_reply(role_id: str, user_message: str, history: list) -> dict:
    """Generate a chat reply from a role character with grammar corrections."""
    role = CHAT_ROLES.get(role_id)
    if not role:
        return {"reply": "Unknown role.", "corrections": []}

    role_name = role["name"]

    # Format conversation history (last 10 messages)
    recent = history[-10:] if len(history) > 10 else history
    conversation = ""
    for msg in recent:
        if msg["sender"] == "user":
            conversation += f"[User]: {msg['message']}\n"
        else:
            conversation += f"[{role_name}]: {msg['message']}\n"

    prompt = f"""{role['desc']}

You are having a conversation with a Chinese English learner. Stay in character.
Also check the user's English for grammar, spelling, and word choice errors.

Conversation so far:
{conversation}
[User]: {user_message}

Respond as JSON only:
{{"reply": "<your in-character response>", "corrections": [<list of {{"wrong": "<exact wrong text from user>", "correct": "<corrected version>", "type": "grammar|spelling|word_choice"}}>, return empty list if no errors]}}"""

    raw_text = ""
    try:
        client = _get_client()
        resp = client.invoke_model(
            modelId=BEDROCK_CHAT_MODEL,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.3,
            }),
        )
        body = json.loads(resp["body"].read())
        raw_text = body["choices"][0]["message"]["content"].strip()
        result = _parse_json(raw_text)
        return {
            "reply": result.get("reply", raw_text),
            "corrections": result.get("corrections", []),
        }
    except Exception:
        return {"reply": raw_text or "Sorry, I couldn't respond.", "corrections": []}


def generate_scenario(original: str, corrected: str, pattern: str) -> dict:
    """Generate a Talk scenario from an english.log error entry."""
    prompt = f"""A Chinese English learner made this error:
Original: "{original}"
Corrected: "{corrected}"
Pattern: {pattern}

Create a realistic work conversation scenario to practice this pattern.

Respond in JSON only:
{{"context": "<1 sentence describing the work situation>", "pattern": "{pattern}", "ai_says": "<what the AI colleague says to set up the scenario>", "good_responses": ["<best response>", "<alternative good response>"]}}"""

    try:
        text = _invoke_model(prompt, max_tokens=200)
        return _parse_json(text)
    except Exception:
        return {}
