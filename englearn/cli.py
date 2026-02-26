"""EngLearn CLI - Terminal frontend for the EngLearn web API."""
import argparse
import getpass
import re
import sys
from difflib import SequenceMatcher

from englearn.web_client import Client


def _ensure_login(client):
    """Ensure the client is authenticated. Prompt for setup if first time."""
    from englearn.web_client import _load_config, _save_config

    cfg = _load_config()

    # First launch: no server configured
    if not cfg.get('server'):
        print("\n  Welcome to EngLearn! First-time setup:")
        print("  ─────────────────────────────────────────")
        server = input("  Server URL (e.g. http://your-server:5555): ").strip()
        if not server:
            print("  Cancelled.\n")
            return False
        cfg['server'] = server
        _save_config(cfg)
        client.server = server

    # Quick check
    result = client.get_stats()
    if result is not None:
        return True

    print(f"\n  Login required. (Server: {client.server})")
    username = input("  Username: ").strip()
    password = getpass.getpass("  Password: ")
    if client.login(username, password):
        print("  Logged in.\n")
        return True
    else:
        print("  Login failed.\n")
        return False


def _normalize(s):
    return re.sub(r'[^a-z0-9\s]', '', s.lower().strip())


def _check_match(user_answer, correct_answer):
    u = _normalize(user_answer)
    c = _normalize(correct_answer)
    if u == c:
        return 'exact', 5
    sim = SequenceMatcher(None, u, c).ratio()
    if sim >= 0.95:
        return 'close', 3
    return 'wrong', 1


def _dim_bar(score, width=15):
    filled = int(score * width)
    return '█' * filled + '░' * (width - filled)


# ─── Commands ────────────────────────────────────────────────────────────────


def cmd_review(client, args):
    """Flashcard review via web API."""
    data = client.get_review_cards(deck=args.deck, limit=args.count)
    if not data:
        return
    cards = data['cards']

    if not cards:
        print("\n  No cards due!")
        print("  Come back later or try: englearn cards --all\n")
        return

    total = len(cards)
    correct = 0
    reviewed = 0
    failed = []

    deck_label = args.deck or "All Decks"
    print(f"\n  {'=' * 50}")
    print(f"  Review | {deck_label} | {total} cards due")
    print(f"  Type answer. 'q' quit, 's' skip.")
    print(f"  {'=' * 50}\n")

    try:
        for i, card in enumerate(cards):
            progress = int((i / total) * 30)
            bar = '█' * progress + '░' * (30 - progress)
            print(f"  [{bar}] {i + 1}/{total}")
            print(f"  {'─' * 50}")
            print(f"  {card['front']}")
            if card.get('hint'):
                print(f"  Hint: {card['hint']}")
            print()

            user_input = input("  Answer:").strip()
            if user_input.lower() == 'q':
                break
            if user_input.lower() == 's':
                print(f"  Skipped. Answer:{card['back']}")
                client.submit_review(card['id'], 1)
                reviewed += 1
                failed.append(card)
                print()
                continue

            match_type, rating = _check_match(user_input, card['back'])
            reviewed += 1

            if match_type == 'exact':
                print(f"  Correct!")
                correct += 1
            elif match_type == 'close':
                print(f"  Close! → {card['back']}")
                correct += 1
            else:
                print(f"  Wrong → {card['back']}")
                failed.append(card)

            # Map to web rating: exact→3(easy), close→2(hesitated), wrong→1(fail)
            web_rating = 3 if match_type == 'exact' else 2 if match_type == 'close' else 1
            client.submit_review(card['id'], web_rating)
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n  Interrupted.")

    print(f"\n  {'=' * 50}")
    print(f"  Done! {correct}/{reviewed} correct")
    if failed:
        print(f"  Failed: {len(failed)}")
    print(f"  {'=' * 50}\n")

    if failed:
        retry = input("  Retry failed? (y/n): ").strip().lower()
        if retry == 'y':
            _retry_review(client, failed)


def _retry_review(client, cards):
    total = len(cards)
    correct = 0
    print(f"\n  Retrying {total} cards...\n")
    try:
        for i, card in enumerate(cards):
            print(f"  [{i + 1}/{total}] {card['front']}")
            user_input = input("  Answer:").strip()
            if user_input.lower() == 'q':
                break
            match_type, _ = _check_match(user_input, card['back'])
            if match_type in ('exact', 'close'):
                print(f"  Correct!")
                correct += 1
                client.submit_review(card['id'], 3)
            else:
                print(f"  Wrong. → {card['back']}")
                client.submit_review(card['id'], 1)
            print()
    except (KeyboardInterrupt, EOFError):
        pass
    print(f"  Retry: {correct}/{total}\n")


def cmd_talk(client, args):
    """Conversation practice via web API with LLM scoring."""
    include_all = getattr(args, 'all', False)
    data = client.get_talk_scenarios(limit=args.count, include_all=include_all)
    if not data:
        return
    scenarios = data['scenarios']

    if not scenarios:
        print("\n  All done for today! No scenarios due.")
        print("  Use 'englearn talk --all' to practice anyway.\n")
        return

    total = len(scenarios)
    score_total = 0
    answered = 0
    failed = []

    print()
    print("  ╔═══════════════════════════════════════════════════════╗")
    print("  ║          Talk Practice  (LLM Scored)                 ║")
    print("  ╠═══════════════════════════════════════════════════════╣")
    print("  ║  Respond in English. 'q' quit, 's' skip.            ║")
    print("  ╚═══════════════════════════════════════════════════════╝")
    print()

    try:
        for i, scene in enumerate(scenarios):
            good_responses = scene.get('good_responses', [])

            print(f"  ── Round {i + 1}/{total} ──────────────────────────────────")
            print()
            print(f"  AI: \"{scene['ai_says']}\"")
            print()
            print(f"  Scenario: {scene['context']}")
            print(f"  Pattern:  {scene['pattern']}")
            print()

            user_input = input("  You: ").strip()
            if user_input.lower() == 'q':
                break
            if user_input.lower() == 's':
                print(f"  Skipped. Example: {good_responses[0] if good_responses else 'N/A'}")
                print()
                continue

            answered += 1
            print("  Scoring...", end="", flush=True)

            result = client.submit_talk(
                answer=user_input,
                context=scene['context'],
                pattern=scene['pattern'],
                ai_says=scene['ai_says'],
                good_responses=good_responses,
                scenario_id=scene.get('id'),
            )

            score = result.get('score', 0)
            score_total += score

            print(f"\r  {'─' * 50}")
            print()

            if score >= 0.70:
                print(f"  Excellent! ({score:.0%})")
            elif score >= 0.45:
                print(f"  Close! ({score:.0%})")
                failed.append(i)
            else:
                print(f"  Not quite. ({score:.0%})")
                failed.append(i)

            # Corrections
            corrections = result.get('corrections', [])
            print()
            if corrections:
                print(f"  Your answer: {user_input}")
                for c in corrections:
                    print(f"    - \"{c.get('wrong', '')}\" -> \"{c.get('correct', '')}\"")
            else:
                print(f"  Your answer: {user_input}")

            better = result.get('best_response', '')
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

            feedback = result.get('feedback', '')
            if feedback:
                print(f"\n  Tip: {feedback}")

            mistake = result.get('common_mistake', '')
            if mistake:
                print(f"  Note: {mistake}")

            print()
            input("  Enter to continue...")
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n  Interrupted.")

    print()
    print(f"  ══════════════════════════════════════════")
    print(f"  Talk Practice Complete!")
    print(f"  ──────────────────────────────────────────")
    print(f"  Rounds: {answered}/{total}")
    if answered > 0:
        avg = score_total / answered
        print(f"  Score:  {avg:.0%}")
    print(f"  ══════════════════════════════════════════\n")


def cmd_stats(client, args):
    """Show stats from web API."""
    data = client.get_stats()
    if not data:
        return

    today = data.get('today', {})
    print()
    print(f"  ╔═══════════════════════════════════════════════════════╗")
    print(f"  ║                    EngLearn Stats                    ║")
    print(f"  ╚═══════════════════════════════════════════════════════╝")
    print()

    # Today
    tc = today.get('cards_reviewed', 0)
    tq = today.get('talk_taken', 0)
    tt = today.get('talk_rounds', 0)
    if tc + tq + tt > 0:
        print(f"  Today")
        print(f"  {'─' * 45}")
        if tc:
            tc_correct = today.get('cards_correct', 0)
            pct = round(tc_correct / tc * 100) if tc > 0 else 0
            print(f"    Cards:  {tc_correct}/{tc} ({pct}%)")
        if tq:
            tq_correct = today.get('talk_correct', 0)
            pct = round(tq_correct / tq * 100) if tq > 0 else 0
            print(f"    Talk:   {tq_correct}/{tq} ({pct}%)")
        if tt:
            print(f"    Talk:   {tt} rounds")
        print()

    # Overall
    acc = data.get('accuracy', {})
    print(f"  Overall")
    print(f"  {'─' * 45}")
    print(f"    Total Cards:  {data.get('total_cards', 0)}")
    print(f"    Mastered:     {data.get('total_mastered', 0)}")
    print(f"    Talk Answers: {acc.get('total', 0)}")
    print(f"    Accuracy:     {acc.get('pct', 0)}%")
    print(f"    Streak:       {data.get('streak', 0)} days")
    print()

    # Last 7 Days (reverse chronological)
    weekly = data.get('weekly', [])
    if weekly:
        print(f"  Last 7 Days")
        print(f"  {'─' * 45}")
        for day in reversed(weekly):
            d = day.get('date', '')[-5:]
            total = day.get('cards_reviewed', 0) + day.get('talk_taken', 0)
            bar = '█' * min(total, 20) + '░' * max(0, 20 - total)
            print(f"    {d} [{bar}] {total}")
        print()

    # Decks
    decks = data.get('decks', [])
    if decks:
        print(f"  Decks")
        print(f"  {'─' * 45}")
        print(f"    {'Name':<14} {'Total':>6} {'Due':>6} {'Mastered':>10}")
        for d in decks:
            print(f"    {d['deck']:<14} {d['total']:>6} {d['due']:>6} {d['mastered']:>10}")
        print()

    # Categories
    cats = data.get('categories', [])
    if cats:
        print(f"  Error Categories")
        print(f"  {'─' * 45}")
        for cat in cats[:8]:
            name = cat['category'].replace('_', ' ')
            print(f"    {name:<25} {cat['count']}")
        print()


def cmd_vocab(client, args):
    """Save a word to vocab via web API."""
    word = args.word.strip()
    if not word:
        print("  Usage: englearn vocab <word>")
        return

    # Auto-translate
    print(f"  Translating '{word}'...", end="", flush=True)
    tr = client.translate_word(word)
    chinese = tr.get('chinese', '')
    print(f" → {chinese}" if chinese else " (failed)")

    if not chinese:
        chinese = input("  Chinese meaning: ").strip()
    else:
        override = input(f"  Chinese [{chinese}]: ").strip()
        if override:
            chinese = override

    if not chinese:
        print("  Cancelled.\n")
        return

    result = client.save_vocab(word, chinese, category=args.category or "cli")
    if result.get('ok'):
        print(f"  Saved '{word}' ({chinese})\n")
    else:
        print(f"  Error: {result.get('error', 'Failed')}\n")


def cmd_config(client, args):
    """Show or set configuration."""
    from englearn.web_client import _load_config, _save_config
    cfg = _load_config()

    if args.key and args.value:
        cfg[args.key] = args.value
        _save_config(cfg)
        # Update client if server changed
        if args.key == 'server':
            client.server = args.value
        print(f"  {args.key} = {args.value}\n")
    elif args.key:
        print(f"  {args.key} = {cfg.get(args.key, '(not set)')}\n")
    else:
        print(f"\n  EngLearn Config (~/.englearn_cli.json)")
        print(f"  {'─' * 45}")
        print(f"    server  = {cfg.get('server', '(not set)')}")
        logged_in = bool(cfg.get('cookies'))
        print(f"    login   = {'yes' if logged_in else 'no'}")
        print()
        print(f"  Usage:")
        print(f"    englearn config server http://your-server:5555")
        print()


def cmd_login(client, args):
    """Login to web server."""
    if args.server:
        client.server = args.server
        from englearn.web_client import _load_config, _save_config
        cfg = _load_config()
        cfg['server'] = args.server
        _save_config(cfg)
    username = input("  Username: ").strip()
    password = getpass.getpass("  Password: ")
    if client.login(username, password):
        print(f"  Logged in to {client.server}\n")
    else:
        print(f"  Login failed.\n")


def _show_welcome(client):
    """Show welcome screen with features and quick stats."""
    print()
    from englearn import __version__
    title = f"EngLearn v{__version__}"
    pad = (53 - len(title)) // 2
    print("  ╔═══════════════════════════════════════════════════════╗")
    print(f"  ║{' ' * pad}{title}{' ' * (53 - pad - len(title))}║")
    print("  ╚═══════════════════════════════════════════════════════╝")
    print()
    print("  Commands:")
    print("  ─────────────────────────────────────────────────────────")
    print("    englearn cards             Flashcard practice (type answers)")
    print("    englearn cards -d vocab    Vocab deck only")
    print("    englearn cards -d daily    Pattern deck only")
    print("    englearn talk              Conversation practice (LLM scored)")
    print("    englearn talk -n 5         Talk with 5 rounds")
    print("    englearn stats             View learning statistics")
    print("    englearn vocab <word>      Save a word (auto-translates)")
    print("    englearn config            Show/set config (server URL)")
    print("    englearn login             Login to server")
    print()
    print("  Features:")
    print("  ─────────────────────────────────────────────────────────")
    print("    Typing-based cards      Type answers, auto-compare")
    print("    LLM conversation score  6 dimensions: grammar, meaning,")
    print("                            tone, fluency, pattern, vocabulary")
    print("    One-tap vocab save      Tap any word to save with auto-translate")
    print("    Spaced repetition       SM-2 algorithm schedules cards")
    print("    Session persistence     Resume where you left off")
    print()

    # Try to show quick stats if logged in
    try:
        data = client.get_stats()
        if data:
            today = data.get('today', {})
            tc = today.get('cards_reviewed', 0)
            tq = today.get('talk_taken', 0)
            tt = today.get('talk_rounds', 0)
            streak = data.get('streak', 0)

            print("  Today:")
            print("  ─────────────────────────────────────────────────────────")
            if tc + tq + tt > 0:
                parts = []
                if tc:
                    parts.append(f"{tc} cards")
                if tq:
                    parts.append(f"{tq} talk")
                if tt:
                    parts.append(f"{tt} talk rounds")
                print(f"    {' | '.join(parts)}", end="")
                if streak > 0:
                    print(f"  {streak}-day streak")
                else:
                    print()
            else:
                print("    No activity yet. Start learning!")
            print()
    except Exception:
        from englearn.web_client import _load_config
        if not _load_config().get('server'):
            print("  Get started:")
            print("  ─────────────────────────────────────────────────────────")
            print("    englearn config server http://your-server:5555")
            print("    englearn login")
        else:
            print("  Not logged in. Run: englearn login")
        print()


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog='englearn',
        description='EngLearn CLI - English Learning Terminal Frontend'
    )
    parser.add_argument('--server', '-s', type=str, default=None,
                        help='Web server URL (or set via: englearn config server <url>)')
    sub = parser.add_subparsers(dest='command')

    # config
    p_config = sub.add_parser('config', help='Show or set configuration')
    p_config.add_argument('key', nargs='?', type=str, default=None, help='Config key (e.g. server)')
    p_config.add_argument('value', nargs='?', type=str, default=None, help='Value to set')

    # login
    p_login = sub.add_parser('login', help='Login to web server')
    p_login.add_argument('--server', type=str, default=None, help='Server URL')

    # cards
    p_review = sub.add_parser('cards', help='Flashcard practice (type answers)')
    p_review.add_argument('--deck', '-d', type=str, default=None,
                          help='Deck name (daily/express/vocab)')
    p_review.add_argument('--count', '-n', type=int, default=30, help='Number of cards')

    # talk
    p_talk = sub.add_parser('talk', help='Conversation practice (LLM scored)')
    p_talk.add_argument('--count', '-n', type=int, default=20, help='Number of rounds')
    p_talk.add_argument('--all', '-a', action='store_true', default=False, help='Include already-reviewed scenarios')

    # stats
    sub.add_parser('stats', help='Show learning statistics')

    # vocab
    p_vocab = sub.add_parser('vocab', help='Save a word to vocab')
    p_vocab.add_argument('word', type=str, help='English word to save')
    p_vocab.add_argument('--category', '-c', type=str, default=None, help='Category')

    args = parser.parse_args()

    client = Client(server=args.server)

    if args.command == 'config':
        cmd_config(client, args)
        return

    if args.command == 'login':
        cmd_login(client, args)
        return

    if not args.command:
        _show_welcome(client)
        return

    if not _ensure_login(client):
        return

    commands = {
        'cards': cmd_review,
        'talk': cmd_talk,
        'stats': cmd_stats,
        'vocab': cmd_vocab,
    }

    if args.command in commands:
        commands[args.command](client, args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
