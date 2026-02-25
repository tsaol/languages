#!/usr/bin/env python3
"""
English Practice CLI Tool
Reads ~/english.log and provides interactive practice modes.
"""

import re
import os
import sys
import json
import random
import datetime
from collections import Counter, defaultdict

# ── ANSI Colors ──────────────────────────────────────────────────────────────
R = "\033[0m"       # Reset
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
DIM = "\033[2m"
BG_GREEN = "\033[42m"
BG_RED = "\033[41m"

LOG_PATH = os.path.expanduser("~/english.log")
HISTORY_PATH = os.path.expanduser("~/codes/languages/practice_history.json")


# ── Log Parsing ──────────────────────────────────────────────────────────────

def parse_log():
    """Parse english.log and return list of entry dicts."""
    if not os.path.exists(LOG_PATH):
        print(f"{RED}Error: {LOG_PATH} not found.{R}")
        sys.exit(1)

    entries = []
    pattern = re.compile(
        r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] '
        r'Original: \[(.+?)\] \| '
        r'Status: \[?(Correct|Incorrect)\]? \| '
        r'Corrected: \[?(.*?)\]? \| '
        r'Idiomatic: \[?(.*?)\]? \| '
        r'Explanation: \[?(.*?)\]? \| '
        r'Pattern: \[?(.*?)\]? \| '
        r'Tense: \[?(.*?)\]?\s*$'
    )

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = pattern.match(line)
            if m:
                entries.append({
                    "date": m.group(1),
                    "original": m.group(2),
                    "status": m.group(3),
                    "corrected": m.group(4).strip(),
                    "idiomatic": m.group(5).strip(),
                    "explanation": m.group(6).strip(),
                    "pattern": m.group(7).strip(),
                    "tense": m.group(8).strip(),
                })
    return entries


def get_errors(entries):
    """Return only incorrect entries with valid corrections."""
    errors = []
    for e in entries:
        if e["status"] == "Incorrect" and e["corrected"] not in ("N/A", "", "N/A (Chinese text)"):
            errors.append(e)
    return errors


def extract_misspellings(errors):
    """Extract misspelled words by comparing original vs corrected."""
    # Common English words that aren't typos, just grammar changes
    SKIP = {"the", "a", "an", "is", "are", "was", "were", "do", "does", "did",
            "have", "has", "had", "it", "its", "on", "in", "at", "to", "for",
            "of", "and", "or", "not", "don", "can", "could", "would", "should",
            "this", "that", "these", "those", "when", "what", "how", "why"}
    misspellings = []
    for e in errors:
        orig_words = re.findall(r'[a-zA-Z]+', e["original"].lower())
        corr_words = re.findall(r'[a-zA-Z]+', e["corrected"].lower())
        corr_set = set(corr_words)
        orig_set = set(orig_words)
        for ow in orig_words:
            if len(ow) < 3 or ow in SKIP:
                continue
            if ow not in corr_set:
                best_match = None
                best_dist = 999
                for cw in corr_words:
                    if len(cw) < 3 or cw in SKIP or cw in orig_set:
                        continue
                    d = _edit_dist(ow, cw)
                    if 0 < d <= 2 and d < best_dist:
                        best_dist = d
                        best_match = cw
                if best_match:
                    misspellings.append((ow, best_match, e["original"]))
    return misspellings


def _is_typo(a, b):
    """Simple edit distance check - true if likely a typo."""
    if a == b:
        return False
    if abs(len(a) - len(b)) > 2:
        return False
    # Levenshtein distance <= 2
    d = _edit_dist(a, b)
    return 0 < d <= 2


def _edit_dist(a, b):
    """Compute edit distance between two strings."""
    la, lb = len(a), len(b)
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            tmp = dp[j]
            if a[i-1] == b[j-1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j-1])
            prev = tmp
    return dp[lb]


def extract_word_usage_errors(errors):
    """Extract word usage errors from explanations."""
    usage_errors = []
    # Skip meta/grammar words - we only want real word-level mistakes
    SKIP = {"comma", "english", "chinese", "full", "missing", "use", "the",
            "should", "needs", "mixed", "sentence", "entire", "question",
            "mark", "i", "a", "an", "on", "in", "to", "for", "of", "it",
            "is", "are", "was", "were", "be", "been", "not", "no"}
    # patterns like: word->correct_word, word should be correct_word
    arrow_pat = re.compile(r'["\']?(\b[a-zA-Z]{2,})["\']?\s*(?:->|-->|→)\s*["\']?(\b[a-zA-Z]{2,})["\']?')
    should_pat = re.compile(r'["\'](\b[a-zA-Z]{2,})["\']?\s+should be\s+["\']?(\b[a-zA-Z]{2,})["\']?')
    for e in errors:
        exp = e["explanation"]
        for m in arrow_pat.finditer(exp):
            w, c = m.group(1).lower(), m.group(2).lower()
            if w != c and len(w) >= 3 and w not in SKIP and c not in SKIP:
                usage_errors.append((w, c, exp))
        for m in should_pat.finditer(exp):
            w, c = m.group(1).lower(), m.group(2).lower()
            if w != c and len(w) >= 3 and w not in SKIP and c not in SKIP:
                usage_errors.append((w, c, exp))
    return usage_errors


def extract_patterns(errors):
    """Extract sentence patterns from log entries."""
    patterns = []
    for e in errors:
        p = e["pattern"]
        if p and p not in ("N/A", "imperative", "N/A (Chinese text)"):
            patterns.append({
                "pattern": p,
                "original": e["original"],
                "corrected": e["corrected"],
                "idiomatic": e["idiomatic"],
                "explanation": e["explanation"],
            })
    return patterns


# ── History ──────────────────────────────────────────────────────────────────

def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"sessions": []}


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def record_session(mode, correct, total, details=None):
    history = load_history()
    session = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "correct": correct,
        "total": total,
        "score": round(correct / total * 100, 1) if total > 0 else 0,
    }
    if details:
        session["details"] = details
    history["sessions"].append(session)
    save_history(history)


# ── UI Helpers ───────────────────────────────────────────────────────────────

def clear():
    os.system("clear" if os.name != "nt" else "cls")


def banner():
    print(f"""
{CYAN}{BOLD}{'=' * 60}
     English Practice Tool  /  英语练习工具
{'=' * 60}{R}
""")


def get_input(prompt=">>> "):
    """Get user input, return None if quit."""
    try:
        val = input(f"{YELLOW}{prompt}{R}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if val.lower() in ("q", "quit", "exit"):
        return None
    return val


def show_score(correct, total):
    if total == 0:
        return
    pct = correct / total * 100
    if pct >= 80:
        color = GREEN
        msg = "Great job! / 太棒了!"
    elif pct >= 60:
        color = YELLOW
        msg = "Not bad, keep going! / 继续加油!"
    else:
        color = RED
        msg = "Keep practicing! / 多多练习!"
    print(f"\n{color}{BOLD}Score: {correct}/{total} ({pct:.0f}%) - {msg}{R}")


def similarity_score(a, b):
    """Return similarity ratio between 0 and 1."""
    a, b = a.lower().strip().rstrip(".!?"), b.lower().strip().rstrip(".!?")
    if a == b:
        return 1.0
    words_a = set(re.findall(r'[a-z]+', a))
    words_b = set(re.findall(r'[a-z]+', b))
    if not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    return overlap / max(len(words_a), len(words_b))


def press_enter():
    get_input(f"{DIM}[Press Enter to continue / 按回车继续, q=quit]{R} ")


# ── Mode 1: Sentence Correction Drill ───────────────────────────────────────

def mode_sentence_correction(errors):
    clear()
    print(f"\n{MAGENTA}{BOLD}=== Mode 1: Sentence Correction Drill / 句子纠错练习 ==={R}")
    print(f"{DIM}Type the corrected sentence. Type 'q' to quit.{R}")
    print(f"{DIM}输入纠正后的句子。输入 'q' 退出。{R}\n")

    if not errors:
        print(f"{RED}No errors found in log. / 日志中没有找到错误记录。{R}")
        press_enter()
        return

    pool = random.sample(errors, min(10, len(errors)))
    correct_count = 0
    total = 0
    details = []

    for i, e in enumerate(pool):
        print(f"{CYAN}--- Question {i+1}/{len(pool)} ---{R}")
        print(f"{RED}{BOLD}Wrong sentence / 错误句子:{R}")
        print(f"  {RED}{e['original']}{R}\n")

        ans = get_input("Your correction / 你的纠正: ")
        if ans is None:
            break

        total += 1
        sim = similarity_score(ans, e["corrected"])
        is_correct = sim >= 0.85

        if is_correct:
            correct_count += 1
            print(f"\n  {GREEN}{BOLD}Correct! / 正确!{R}")
        else:
            print(f"\n  {RED}{BOLD}Not quite. / 还差一点。{R}")

        print(f"  {GREEN}Corrected  : {e['corrected']}{R}")
        if e["idiomatic"] and e["idiomatic"] != "N/A":
            print(f"  {BLUE}Idiomatic  : {e['idiomatic']}{R}")
        print(f"  {DIM}Explanation: {e['explanation']}{R}")

        details.append({
            "original": e["original"],
            "user_answer": ans,
            "expected": e["corrected"],
            "correct": is_correct,
        })
        print()

    show_score(correct_count, total)
    if total > 0:
        record_session("sentence_correction", correct_count, total, details)
    press_enter()


# ── Mode 2: Vocabulary Quiz ─────────────────────────────────────────────────

def mode_vocabulary_quiz(errors):
    clear()
    print(f"\n{MAGENTA}{BOLD}=== Mode 2: Vocabulary Quiz / 高频单词测试 ==={R}")
    print(f"{DIM}Type the correct spelling. Type 'q' to quit.{R}")
    print(f"{DIM}输入正确的拼写。输入 'q' 退出。{R}\n")

    misspellings = extract_misspellings(errors)
    usage_errors = extract_word_usage_errors(errors)

    # Deduplicate
    seen = set()
    quiz_items = []
    for wrong, right, ctx in misspellings:
        key = (wrong, right)
        if key not in seen:
            seen.add(key)
            quiz_items.append(("spell", wrong, right, ctx))
    for wrong, right, ctx in usage_errors:
        key = (wrong, right)
        if key not in seen:
            seen.add(key)
            quiz_items.append(("usage", wrong, right, ctx))

    if not quiz_items:
        print(f"{RED}No vocabulary errors found. / 没有找到词汇错误。{R}")
        press_enter()
        return

    random.shuffle(quiz_items)
    pool = quiz_items[:15]
    correct_count = 0
    total = 0

    for i, (qtype, wrong, right, ctx) in enumerate(pool):
        print(f"{CYAN}--- Question {i+1}/{len(pool)} ---{R}")
        if qtype == "spell":
            print(f"  {YELLOW}Misspelled word / 拼错的单词:{R} {RED}{BOLD}{wrong}{R}")
            print(f"  {DIM}Context: ...{ctx[:80]}...{R}")
            ans = get_input("Correct spelling / 正确拼写: ")
        else:
            print(f"  {YELLOW}Wrong usage / 错误用法:{R} {RED}{BOLD}{wrong}{R}")
            print(f"  {DIM}Hint: {ctx[:100]}{R}")
            ans = get_input("Correct word / 正确用词: ")

        if ans is None:
            break

        total += 1
        if ans.lower().strip() == right.lower():
            correct_count += 1
            print(f"  {GREEN}{BOLD}Correct! / 正确!{R}\n")
        else:
            print(f"  {RED}{BOLD}Wrong. / 错误。{R} Answer: {GREEN}{right}{R}\n")

    show_score(correct_count, total)
    if total > 0:
        record_session("vocabulary_quiz", correct_count, total)
    press_enter()


# ── Mode 3: Pattern Practice ────────────────────────────────────────────────

SCENARIOS = [
    ("请别人帮你检查一下代码", "ask someone to review your code"),
    ("询问某个功能是否已经完成", "ask if a feature has been completed"),
    ("请求别人把改动合并到主分支", "ask someone to merge changes into main"),
    ("询问这个项目还有什么需要处理的", "ask what else needs to be done on the project"),
    ("告诉别人路径搞错了，应该是另一个", "tell someone the path is wrong and give the correct one"),
    ("请别人帮你安装一个工具", "ask someone to install a tool for you"),
    ("询问为什么某个东西没有被用到", "ask why something wasn't used"),
    ("告诉别人你已经设置好了某个配置", "say you've already set up a configuration"),
    ("请别人帮你把文件同步过来", "ask someone to sync files over"),
    ("询问有没有更好的替代方案", "ask if there is a better alternative"),
]


def mode_pattern_practice(errors):
    clear()
    print(f"\n{MAGENTA}{BOLD}=== Mode 3: Pattern Practice / 句型填空练习 ==={R}")
    print(f"{DIM}Write an English sentence for each scenario. Type 'q' to quit.{R}")
    print(f"{DIM}根据场景写出英文句子。输入 'q' 退出。{R}\n")

    patterns = extract_patterns(errors)
    if not patterns:
        print(f"{RED}No patterns found. / 没有找到句型。{R}")
        press_enter()
        return

    pool = random.sample(patterns, min(5, len(patterns)))
    correct_count = 0
    total = 0

    for i, p in enumerate(pool):
        scenario = random.choice(SCENARIOS)
        print(f"{CYAN}--- Question {i+1}/{len(pool)} ---{R}")
        print(f"  {YELLOW}Pattern / 句型:{R} {BOLD}{p['pattern']}{R}")
        print(f"  {YELLOW}Scenario / 场景:{R} {scenario[0]}")
        print(f"  {DIM}({scenario[1]}){R}\n")

        ans = get_input("Your sentence / 你的句子: ")
        if ans is None:
            break

        total += 1
        # Check if they used a reasonable English sentence
        eng_words = re.findall(r'[a-zA-Z]+', ans)
        if len(eng_words) >= 3:
            correct_count += 1
            print(f"  {GREEN}{BOLD}Good attempt! / 不错的尝试!{R}")
        else:
            print(f"  {RED}{BOLD}Try writing a full English sentence. / 请写完整的英文句子。{R}")

        print(f"\n  {BLUE}Model answers / 参考答案:{R}")
        print(f"  {GREEN}Corrected : {p['corrected']}{R}")
        if p["idiomatic"] and p["idiomatic"] != "N/A":
            print(f"  {GREEN}Idiomatic : {p['idiomatic']}{R}")
        print(f"  {DIM}Pattern   : {p['pattern']}{R}")
        print()

    show_score(correct_count, total)
    if total > 0:
        record_session("pattern_practice", correct_count, total)
    press_enter()


# ── Mode 4: Daily Review ────────────────────────────────────────────────────

def mode_daily_review(errors):
    clear()
    print(f"\n{MAGENTA}{BOLD}=== Mode 4: Daily Review / 每日复习 ==={R}")
    print(f"{DIM}Review 5 random errors. Type 'q' to quit.{R}")
    print(f"{DIM}复习5个随机错误。输入 'q' 退出。{R}\n")

    if not errors:
        print(f"{RED}No errors found. / 没有找到错误。{R}")
        press_enter()
        return

    pool = random.sample(errors, min(5, len(errors)))
    correct_count = 0
    total = 0
    to_review = []

    for i, e in enumerate(pool):
        print(f"{CYAN}{'─' * 50}")
        print(f"  Review {i+1}/{len(pool)}{R}")
        print(f"  {RED}{BOLD}Wrong:{R} {e['original']}")
        print(f"  {DIM}Date: {e['date']}{R}\n")

        ans = get_input("Your correction / 你的纠正: ")
        if ans is None:
            break

        total += 1
        sim = similarity_score(ans, e["corrected"])
        is_correct = sim >= 0.85

        if is_correct:
            correct_count += 1
            print(f"  {GREEN}{BOLD}Correct!{R}")
        else:
            print(f"  {RED}{BOLD}Not quite.{R}")
            to_review.append(e)

        print(f"  {GREEN}Answer    : {e['corrected']}{R}")
        if e["idiomatic"] and e["idiomatic"] != "N/A":
            print(f"  {BLUE}Idiomatic : {e['idiomatic']}{R}")
        print(f"  {DIM}Explanation: {e['explanation']}{R}")
        if e["pattern"] and e["pattern"] != "N/A":
            print(f"  {DIM}Pattern   : {e['pattern']}{R}")
        print()

    show_score(correct_count, total)

    if to_review:
        print(f"\n{YELLOW}{BOLD}Sentences to review again / 需要再复习的句子:{R}")
        for j, e in enumerate(to_review, 1):
            print(f"  {j}. {RED}{e['original']}{R}")
            print(f"     {GREEN}{e['corrected']}{R}\n")

    if total > 0:
        record_session("daily_review", correct_count, total)
    press_enter()


# ── Mode 5: Progress Stats ──────────────────────────────────────────────────

def mode_progress_stats(entries, errors):
    clear()
    print(f"\n{MAGENTA}{BOLD}=== Mode 5: Progress Stats / 进度统计 ==={R}\n")

    total_entries = len(entries)
    total_errors = len(errors)
    total_correct = sum(1 for e in entries if e["status"] == "Correct")

    print(f"  {BOLD}Overall Stats / 总体统计{R}")
    print(f"  {'─' * 40}")
    print(f"  Total entries  / 总记录数 : {CYAN}{total_entries}{R}")
    print(f"  Correct        / 正确     : {GREEN}{total_correct}{R}")
    print(f"  Incorrect      / 错误     : {RED}{total_errors}{R}")
    if total_entries > 0:
        rate = total_correct / total_entries * 100
        color = GREEN if rate >= 60 else YELLOW if rate >= 40 else RED
        print(f"  Accuracy       / 正确率   : {color}{rate:.1f}%{R}")

    # Error trend by date
    date_errors = defaultdict(lambda: {"correct": 0, "incorrect": 0})
    for e in entries:
        day = e["date"][:10]
        if e["status"] == "Correct":
            date_errors[day]["correct"] += 1
        else:
            date_errors[day]["incorrect"] += 1

    dates = sorted(date_errors.keys())
    if dates:
        print(f"\n  {BOLD}Error Trend by Date / 每日错误趋势{R}")
        print(f"  {'─' * 40}")
        max_count = max(date_errors[d]["incorrect"] for d in dates) or 1
        for d in dates[-14:]:  # last 14 days
            c = date_errors[d]["correct"]
            ic = date_errors[d]["incorrect"]
            total_d = c + ic
            bar_len = int(ic / max_count * 25)
            bar = f"{RED}{'#' * bar_len}{R}"
            pct = ic / total_d * 100 if total_d else 0
            print(f"  {d}  {bar} {ic} errors ({pct:.0f}%) / {total_d} total")

        # Trend analysis
        if len(dates) >= 2:
            first_half = dates[:len(dates)//2]
            second_half = dates[len(dates)//2:]
            fh_rate = sum(date_errors[d]["incorrect"] for d in first_half) / max(1, sum(date_errors[d]["correct"] + date_errors[d]["incorrect"] for d in first_half))
            sh_rate = sum(date_errors[d]["incorrect"] for d in second_half) / max(1, sum(date_errors[d]["correct"] + date_errors[d]["incorrect"] for d in second_half))
            if sh_rate < fh_rate - 0.05:
                print(f"\n  {GREEN}{BOLD}Trend: Improving! Error rate is going down.{R}")
                print(f"  {GREEN}趋势: 在进步! 错误率在下降。{R}")
            elif sh_rate > fh_rate + 0.05:
                print(f"\n  {YELLOW}{BOLD}Trend: Error rate is going up. Keep practicing!{R}")
                print(f"  {YELLOW}趋势: 错误率在上升，继续练习!{R}")
            else:
                print(f"\n  {CYAN}{BOLD}Trend: Stable. Keep going!{R}")
                print(f"  {CYAN}趋势: 保持稳定，继续加油!{R}")

    # Common error categories
    categories = Counter()
    for e in errors:
        exp = e["explanation"].lower()
        if "chinese" in exp or "chinese" in exp:
            categories["Chinese text (used Chinese)"] += 1
        if "typo" in exp or "misspell" in exp:
            categories["Typos / Misspellings"] += 1
        if "missing" in exp and "article" in exp:
            categories["Missing articles (a/the)"] += 1
        if "tense" in exp or "past" in exp or "present" in exp:
            categories["Tense errors"] += 1
        if "preposition" in exp or "in->" in exp or "on->" in exp:
            categories["Preposition errors"] += 1
        if "capitalize" in exp or "capital" in exp:
            categories["Capitalization"] += 1
        if "mixed" in exp:
            categories["Mixed Chinese/English"] += 1

    if categories:
        print(f"\n  {BOLD}Common Error Categories / 常见错误类别{R}")
        print(f"  {'─' * 40}")
        for cat, count in categories.most_common(10):
            bar_len = min(count, 30)
            bar = f"{YELLOW}{'|' * bar_len}{R}"
            print(f"  {bar} {count:3d}  {cat}")

    # Practice history
    history = load_history()
    sessions = history.get("sessions", [])
    if sessions:
        print(f"\n  {BOLD}Practice History / 练习历史{R}")
        print(f"  {'─' * 40}")
        recent = sessions[-10:]
        for s in recent:
            color = GREEN if s["score"] >= 80 else YELLOW if s["score"] >= 60 else RED
            mode_label = {
                "sentence_correction": "Correction",
                "vocabulary_quiz": "Vocabulary",
                "pattern_practice": "Pattern",
                "daily_review": "Review",
            }.get(s["mode"], s["mode"])
            print(f"  {s['date']}  {mode_label:<12s}  {color}{s['correct']}/{s['total']} ({s['score']}%){R}")

        total_sessions = len(sessions)
        avg_score = sum(s["score"] for s in sessions) / total_sessions
        print(f"\n  Total sessions / 总练习次数: {CYAN}{total_sessions}{R}")
        print(f"  Average score  / 平均分数  : {CYAN}{avg_score:.1f}%{R}")

    press_enter()


# ── Main Menu ────────────────────────────────────────────────────────────────

def main():
    entries = parse_log()
    errors = get_errors(entries)

    while True:
        clear()
        banner()
        print(f"  {DIM}Log: {LOG_PATH}  |  {len(entries)} entries, {len(errors)} errors{R}\n")

        print(f"  {CYAN}1{R}. Sentence Correction Drill   / 句子纠错练习")
        print(f"  {CYAN}2{R}. Vocabulary Quiz              / 高频单词测试")
        print(f"  {CYAN}3{R}. Pattern Practice             / 句型填空练习")
        print(f"  {CYAN}4{R}. Daily Review                 / 每日复习")
        print(f"  {CYAN}5{R}. Progress Stats               / 进度统计")
        print(f"  {RED}q{R}. Quit                         / 退出\n")

        choice = get_input("Choose a mode / 选择模式: ")
        if choice is None:
            break

        if choice == "1":
            mode_sentence_correction(errors)
        elif choice == "2":
            mode_vocabulary_quiz(errors)
        elif choice == "3":
            mode_pattern_practice(errors)
        elif choice == "4":
            mode_daily_review(errors)
        elif choice == "5":
            mode_progress_stats(entries, errors)
        else:
            print(f"{RED}Invalid choice. / 无效选择。{R}")
            press_enter()

    print(f"\n{CYAN}{BOLD}Goodbye! Keep practicing! / 再见，继续加油!{R}\n")


if __name__ == "__main__":
    main()
