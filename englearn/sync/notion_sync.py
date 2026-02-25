"""Sync vocabulary from Notion English Vocabulary database into englearn flashcards."""
import json
import os
import urllib.request
from englearn.db import models
from englearn.db.database import get_connection


NOTION_DB_ID = "3121f4f8-e609-8076-b70c-d3163cf1c9cb"


def _get_notion_token():
    settings_path = os.path.expanduser("~/.claude/settings.json")
    with open(settings_path, 'r') as f:
        settings = json.load(f)
    for server in settings.get('mcpServers', {}).values():
        env = server.get('env', {})
        if 'NOTION_TOKEN' in env:
            return env['NOTION_TOKEN']
    return None


def fetch_notion_vocabulary():
    """Fetch all words from Notion English Vocabulary database."""
    token = _get_notion_token()
    if not token:
        print("  ERROR: NOTION_TOKEN not found.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    all_results = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        resp = json.loads(urllib.request.urlopen(req).read())

        all_results.extend(resp.get('results', []))
        has_more = resp.get('has_more', False)
        start_cursor = resp.get('next_cursor')

    words = []
    for page in all_results:
        props = page.get('properties', {})

        # Extract title (word)
        title_arr = props.get('名称', {}).get('title', [])
        word = ''.join(t.get('plain_text', '') for t in title_arr).strip()

        # Extract Chinese
        chinese_arr = props.get('Chinese', {}).get('rich_text', [])
        chinese = ''.join(t.get('plain_text', '') for t in chinese_arr).strip()

        # Extract Category
        cat_obj = props.get('Category', {}).get('select')
        category = cat_obj.get('name', '') if cat_obj else ''

        if word:
            words.append({
                'word': word,
                'chinese': chinese,
                'category': category,
                'page_id': page['id'],
            })

    return words


def sync_notion_to_flashcards():
    """Sync Notion vocabulary into englearn flashcard decks."""
    print("  Fetching vocabulary from Notion...")
    words = fetch_notion_vocabulary()

    if not words:
        print("  No words found in Notion.")
        return 0

    print(f"  Found {len(words)} words.")

    conn = get_connection()
    try:
        # Remove old notion-sourced vocab cards
        conn.execute("DELETE FROM flashcards WHERE deck IN ('vocab_en2cn', 'vocab_cn2en', 'vocab_use')")
        conn.commit()
    finally:
        conn.close()

    counts = {'vocab_en2cn': 0, 'vocab_cn2en': 0, 'vocab_use': 0}

    for w in words:
        word = w['word']
        chinese = w['chinese']
        category = w['category']

        if not chinese:
            continue

        # Deck 1: English → Chinese (看英文说中文)
        models.insert_flashcard(
            deck='vocab_en2cn',
            front=f"What does \"{word}\" mean?",
            back=chinese,
            hint=f"Category: {category}",
        )
        counts['vocab_en2cn'] += 1

        # Deck 2: Chinese → English (看中文说英文)
        models.insert_flashcard(
            deck='vocab_cn2en',
            front=f"How do you say \"{chinese}\" in English?",
            back=word,
            hint=f"Category: {category}",
        )
        counts['vocab_cn2en'] += 1

        # Deck 3: Use in a sentence (造句)
        models.insert_flashcard(
            deck='vocab_use',
            front=f"Use \"{word}\" ({chinese}) in a work sentence.",
            back=_generate_example(word, category),
            hint=f"Think about your daily work at AWS.",
        )
        counts['vocab_use'] += 1

    total = sum(counts.values())
    print(f"  Created {total} flashcards from Notion vocabulary:")
    for deck, count in counts.items():
        print(f"    {deck}: {count} cards")

    return total


def _generate_example(word: str, category: str) -> str:
    """Provide a simple example sentence for common work words."""
    examples = {
        "configure": "We need to configure the VPC settings before deployment.",
        "integrate": "Let's integrate the new API with our existing platform.",
        "establish": "We established a secure connection between the two regions.",
        "resolve": "I resolved the latency issue by switching to a closer region.",
        "collaborate": "We collaborate with the customer's DevOps team weekly.",
        "assist": "I assisted the customer in migrating their workloads to AWS.",
        "secure": "We secured the deal by demonstrating a 40% cost reduction.",
        "drive": "This initiative will drive adoption across the organization.",
        "accelerate": "Using CI/CD can accelerate the deployment process.",
        "replicate": "We replicated the database across three availability zones.",
        "expand": "The customer wants to expand their footprint to Asia Pacific.",
        "identify": "We identified a bottleneck in the data pipeline.",
        "mitigate": "We mitigated the risk by adding a failover mechanism.",
        "escalate": "I need to escalate this issue to the service team.",
        "troubleshoot": "Let me troubleshoot the connectivity issue first.",
        "enhance": "We enhanced the monitoring setup with CloudWatch alarms.",
        "streamline": "We streamlined the deployment process using CDK.",
        "convince": "I convinced the CTO to adopt a serverless architecture.",
        "demonstrate": "I demonstrated the solution in a live proof-of-concept.",
        "recommend": "I recommend using Aurora for this use case.",
        "facilitate": "I facilitated a workshop for the customer's engineering team.",
        "optimize": "We optimized their EC2 costs by 35% using Reserved Instances.",
        "implement": "We implemented auto-scaling to handle traffic spikes.",
        "achieve": "We achieved 99.99% availability for the production workload.",
        "scale": "The architecture can scale to handle millions of requests.",
        "provision": "We provisioned a new EKS cluster for the dev team.",
        "monitor": "We monitor all services using CloudWatch dashboards.",
        "maintain": "It's important to maintain security patches regularly.",
        "modernize": "The customer wants to modernize their legacy applications.",
        "significantly": "This change significantly reduced the response time.",
        "substantially": "Revenue increased substantially after the migration.",
        "however": "The solution works well. However, we need to address cost.",
        "therefore": "The current setup is unstable. Therefore, we need a redesign.",
        "look into": "I'll look into the error logs and get back to you.",
        "figure out": "Let me figure out why the deployment failed.",
        "come up with": "We came up with a hybrid architecture to reduce costs.",
        "follow up": "I'll follow up with the customer after the meeting.",
        "going forward": "Going forward, we'll use Terraform for all infrastructure.",
    }
    if word.lower() in examples:
        return examples[word.lower()]
    return f"(Try making a sentence using \"{word}\" in a work context.)"
