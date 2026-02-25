"""LLM-based semantic scoring using Amazon Bedrock Claude."""
import json
import boto3

BEDROCK_MODEL = "us.anthropic.claude-opus-4-5-20251101-v1:0"
BEDROCK_REGION = "us-east-1"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _client


def score_response(context: str, pattern: str, ai_says: str,
                   user_answer: str, good_responses: list) -> dict:
    """Score a user's English response using Claude.

    Returns:
        {
            "score": float (0-1),
            "is_correct": bool,
            "feedback": str,
            "better_expression": str,
        }
    """
    examples = "\n".join(f"  - {r}" for r in good_responses)

    prompt = f"""You are an English tutor evaluating a Chinese learner's response in a work scenario.

Scenario: {context}
Target pattern: {pattern}
AI said: "{ai_says}"

Good example responses:
{examples}

Student's response: "{user_answer}"

Evaluate the student's response on these criteria:
1. Is it grammatically correct?
2. Does it convey the right meaning for this scenario?
3. Does it use appropriate vocabulary and tone for a work setting?

Respond in this exact JSON format only, no other text:
{{"score": <0.0 to 1.0>, "is_correct": <true if score >= 0.7>, "feedback": "<1 sentence feedback>", "better_expression": "<a more natural way to say it, or repeat their answer if already good>"}}"""

    try:
        client = _get_client()
        resp = client.invoke_model(
            modelId=BEDROCK_MODEL,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        body = json.loads(resp["body"].read())
        text = body["content"][0]["text"].strip()

        # Parse JSON from response
        if text.startswith("{"):
            result = json.loads(text)
        else:
            # Try to extract JSON from text
            start = text.find("{")
            end = text.rfind("}") + 1
            result = json.loads(text[start:end])

        return {
            "score": float(result.get("score", 0)),
            "is_correct": bool(result.get("is_correct", False)),
            "feedback": result.get("feedback", ""),
            "better_expression": result.get("better_expression", ""),
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
            "feedback": f"(Fallback scoring: {str(e)[:50]})",
            "better_expression": best_match,
        }
