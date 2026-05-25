"""
auto_post.py
AI ニュース自動収集・記事生成スクリプト
GitHub Actions / 手動実行用

パイプライン:
  1. Reddit + HackerNews + RSS からニュース収集
  2. 重複排除 (data/used_urls.json)
  3. Claude Haiku: 翻訳・要点抽出 → JSON
  4. Claude Sonnet: 日本語記事生成 (copywriting)
  5. Claude Sonnet: 品質チェック・修正 (editor)
  6. src/content/news/ に MDファイルを保存
  7. used_urls.json を更新
  8. GitHub Actions 環境変数をセット (PRタイトル用)
"""

import datetime
import json
import os
import re
import sys
import time
import unicodedata

import anthropic
import feedparser
import requests

# ---- パス定数 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
NEWS_DIR = os.path.join(REPO_ROOT, "src", "content", "news")
DATA_DIR = os.path.join(REPO_ROOT, "data")
USED_URLS_PATH = os.path.join(DATA_DIR, "used_urls.json")

# ---- ニュースソース設定 ----
REDDIT_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ai-news-compass-bot/1.0)"}
REDDIT_SUBREDDITS = ["artificial", "MachineLearning", "ChatGPT", "LocalLLaMA", "Anthropic"]
REDDIT_MIN_SCORE = 100
REDDIT_MIN_COMMENTS = 10
REDDIT_FETCH_LIMIT = 20

HN_TOP_N = 30
HN_AI_KEYWORDS = [
    "AI", "LLM", "GPT", "Claude", "OpenAI", "Anthropic", "Gemini",
    "machine learning", "neural", "language model", "artificial intelligence",
    "Mistral", "DeepSeek", "Llama", "diffusion", "transformer", "foundation model",
]

RSS_FEEDS = [
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
]
RSS_AI_KEYWORDS = [kw.lower() for kw in HN_AI_KEYWORDS]

POSTS_PER_RUN = 2

# ---- Claude モデル ----
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

# ---- 利用可能タグリスト ----
VALID_TAGS = [
    "AIニュース", "Anthropic", "ChatGPT", "生成AI", "AIツール", "副業活用",
    "OpenAI", "DeepSeek", "Claude", "資金調達", "AI業界", "画像生成",
    "音声AI", "動画AI", "プログラミング", "規制・倫理", "ハードウェア",
]
VALID_TAGS_STR = ", ".join(VALID_TAGS)

# ---- プロンプト（静的ブロック: プロンプトキャッシュ対象）----

HAIKU_SYSTEM = (
    "You are a professional news analyst specializing in AI/tech news. "
    "Given a news item (title + text in English), extract the key information in Japanese. "
    "Return ONLY valid JSON with exactly these fields:\n"
    "{\n"
    '  "headline_ja": "日本語ヘッドライン（50字以内）",\n'
    '  "what_happened": "何が起きたか（100字以内）",\n'
    '  "key_facts": ["事実1", "事実2", ...],\n'
    '  "why_it_matters": "AI利用者/副業者に関係する理由（60字以内）",\n'
    '  "numbers": ["注目すべき数字・データ（例: 評価額9000億ドル = 約135兆円）"]\n'
    "}\n"
    "No explanation, no markdown, just the JSON object."
)

SONNET_COPYWRITER_SYSTEM = f"""あなたは「ai-news-compass.com」のAIニュースライターです。
AIの最新ニュースを副業・在宅ワーク・AI活用に関心がある日本人読者向けに書いてください。

【文体ルール】
- 本文300〜500字
- 読者に語りかける口語体（「〜ですよね」「〜感じです」「〜見えます」）
- 数字は初出で日本円換算を補足（例: 1B USD → 約1,500億円）
- 専門用語は初出時に簡単な説明を付ける（例: LLM（大規模言語モデル））
- 最後の段落は個人的コメント or 読者への問いかけで締める
- 参照元リンクを末尾に明記: **参照元：** [ソース名](URL)

【frontmatterルール】
- title: 40字以内の日本語タイトル
- description: 120字以内の要約
- pubDate: 今日の日付（YYYY-MM-DD形式）
- sourceName: ニュースソース名（例: TechCrunch, Hacker News, r/artificial）
- sourceUrl: 元記事URL
- tags: 以下から1〜4個（必ずリスト形式）
  利用可能: {VALID_TAGS_STR}
- affiliate: false（固定）

【出力形式】YAMLフロントマター + Markdown本文のみ出力。
---
title: "..."
description: "..."
pubDate: YYYY-MM-DD
pubTime: HH:mm
sourceName: "..."
sourceUrl: "..."
tags: ["...", "..."]
affiliate: false
---
本文...
"""

SONNET_EDITOR_SYSTEM = f"""あなたはAIニュース記事のエディターです。
以下の観点でチェックして完成版のmarkdownを出力してください。

【チェック・修正項目】
1. 誤字脱字・表記揺れ（AI/A.I. → AI、ChatGPT統一）
2. AI生成っぽい機械的・硬直した文体を自然な口語体に修正
3. frontmatterのdescriptionが120字以内か（超えていれば削る）
4. frontmatterのtitleが40字以内か（超えていれば簡潔に）
5. tagsが利用可能リストのみか: {VALID_TAGS_STR}
6. pubTimeフィールドがあるか（なければ "09:00" を補完）
7. 本文が300〜500字の範囲内か（短すぎれば補足、長すぎれば削る）
8. 末尾に参照元リンクがあるか

【出力形式】完成版のmarkdown（frontmatter + 本文）のみ。
修正した場合は末尾に <!-- EDITOR: 修正内容 --> を追記。
問題なければそのまま出力。"""


# ===== ユーティリティ =====

def load_used_urls() -> set:
    if not os.path.exists(USED_URLS_PATH):
        return set()
    with open(USED_URLS_PATH, encoding="utf-8") as f:
        return set(json.load(f))


def save_used_urls(urls: set) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USED_URLS_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(urls), f, ensure_ascii=False, indent=2)


def make_slug(url: str, title: str = "") -> str:
    """URL or タイトルから URL-safe なスラッグを生成する。"""
    # URLのパス末尾から生成を試みる
    path_part = url.rstrip("/").split("/")[-1].split("?")[0]
    if path_part and len(path_part) > 8 and re.search(r"[a-z]", path_part.lower()):
        slug = re.sub(r"[^a-z0-9]+", "-", path_part.lower()).strip("-")
        if 5 < len(slug) < 70:
            return slug[:60]

    # タイトルから生成
    if title:
        normalized = unicodedata.normalize("NFD", title)
        normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
        if slug:
            return slug[:50]

    # フォールバック: タイムスタンプ
    return f"ai-news-{int(time.time())}"


def set_github_env(key: str, value: str) -> None:
    """GitHub Actions の環境変数ファイルに書き込む。"""
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
    else:
        print(f"  [ENV] {key}={value}")


def today_jst() -> str:
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(jst).strftime("%Y-%m-%d")


def current_time_jst() -> str:
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(jst).strftime("%H:%M")


# ===== ニュース取得 =====

def fetch_reddit(used_urls: set) -> list:
    """Reddit JSON API から AIニュース候補を取得する。"""
    candidates = []
    for subreddit in REDDIT_SUBREDDITS:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={REDDIT_FETCH_LIMIT}"
        try:
            resp = requests.get(url, headers=REDDIT_HEADERS, timeout=15)
            if resp.status_code == 429:
                print(f"  WARNING: r/{subreddit} レート制限、5秒待機...")
                time.sleep(5)
                resp = requests.get(url, headers=REDDIT_HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  WARNING: r/{subreddit} HTTP {resp.status_code} スキップ")
                continue
            data = resp.json()
        except Exception as e:
            print(f"  WARNING: r/{subreddit} 取得エラー: {e}")
            continue

        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            post_url = post.get("url", "")
            score = post.get("score") or 0
            num_comments = post.get("num_comments") or 0
            selftext = (post.get("selftext") or "").strip()
            if selftext in ("[removed]", "[deleted]"):
                selftext = ""

            if score < REDDIT_MIN_SCORE:
                continue
            if num_comments < REDDIT_MIN_COMMENTS:
                continue
            if post_url in used_urls:
                continue

            candidates.append({
                "source_name": f"r/{subreddit}",
                "source_url": post_url,
                "title": post.get("title", ""),
                "text": selftext[:600],
                "score": score,
            })
            used_urls.add(post_url)

        time.sleep(1)  # レート制限対策

    print(f"  Reddit: {len(candidates)}件取得")
    return candidates


def fetch_hackernews(used_urls: set) -> list:
    """Hacker News API から AI関連記事を取得する。"""
    candidates = []
    try:
        resp = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  WARNING: HN topstories HTTP {resp.status_code}")
            return []
        story_ids = resp.json()[:HN_TOP_N]
    except Exception as e:
        print(f"  WARNING: HN取得エラー: {e}")
        return []

    for story_id in story_ids:
        try:
            item_resp = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                timeout=10,
            )
            if item_resp.status_code != 200:
                continue
            item = item_resp.json()
        except Exception:
            continue

        title = item.get("title", "")
        item_url = item.get("url", "")
        score = item.get("score") or 0

        if not item_url or item_url in used_urls:
            continue

        title_lower = title.lower()
        if not any(kw.lower() in title_lower for kw in HN_AI_KEYWORDS):
            continue

        candidates.append({
            "source_name": "Hacker News",
            "source_url": item_url,
            "title": title,
            "text": "",
            "score": score,
        })
        used_urls.add(item_url)

    print(f"  HackerNews: {len(candidates)}件取得")
    return candidates


def fetch_rss(used_urls: set) -> list:
    """RSS フィードから AI関連記事を取得する。"""
    candidates = []
    for feed_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"  WARNING: {feed_name} RSS取得エラー: {e}")
            continue

        for entry in feed.entries[:20]:
            entry_url = entry.get("link", "")
            title = entry.get("title", "")
            summary = entry.get("summary", "")

            if not entry_url or entry_url in used_urls:
                continue

            combined = (title + " " + summary).lower()
            if not any(kw in combined for kw in RSS_AI_KEYWORDS):
                continue

            candidates.append({
                "source_name": feed_name,
                "source_url": entry_url,
                "title": title,
                "text": summary[:600],
                "score": 50,  # RSS にはスコアがないので固定値
            })
            used_urls.add(entry_url)

    print(f"  RSS: {len(candidates)}件取得")
    return candidates


def sort_and_select(candidates: list, n: int) -> list:
    """スコア降順でソートして上位 n 件を返す。"""
    sorted_candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
    return sorted_candidates[:n]


# ===== Claude API 呼び出し =====

def call_claude_cached(client, model: str, system: str, user_content: str, max_tokens: int = 2048) -> str:
    """プロンプトキャッシュを使用した Claude API 呼び出し。"""
    response = client.beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        betas=["prompt-caching-2024-07-31"],
    )
    return response.content[0].text


def translate_summarize(item: dict, client) -> dict:
    """Claude Haiku で要点を抽出・翻訳して JSON を返す。"""
    user_content = json.dumps(
        {"title": item["title"], "text": item["text"]},
        ensure_ascii=False,
    )
    raw = call_claude_cached(client, HAIKU_MODEL, HAIKU_SYSTEM, user_content, max_tokens=1024)

    # JSON 部分だけ取り出す
    match = re.search(r"\{[\s\S]+\}", raw)
    if not match:
        return {
            "headline_ja": item["title"],
            "what_happened": item["title"],
            "key_facts": [],
            "why_it_matters": "",
            "numbers": [],
        }
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {
            "headline_ja": item["title"],
            "what_happened": item["title"],
            "key_facts": [],
            "why_it_matters": "",
            "numbers": [],
        }


def generate_article(item: dict, summary: dict, client) -> str:
    """Claude Sonnet で日本語記事（frontmatter + 本文）を生成する。"""
    user_content = f"""以下の情報をもとに記事を書いてください。

【ニュースソース】
- ソース名: {item["source_name"]}
- 元記事URL: {item["source_url"]}

【要点（Haiku抽出済み）】
- ヘッドライン: {summary["headline_ja"]}
- 概要: {summary["what_happened"]}
- 主要事実: {json.dumps(summary["key_facts"], ensure_ascii=False)}
- 重要な理由: {summary["why_it_matters"]}
- 注目数字: {json.dumps(summary["numbers"], ensure_ascii=False)}

【今日の日付】{today_jst()}
【現在時刻 (JST)】{current_time_jst()}

上記の情報を使って記事を生成してください。pubTime には現在時刻をそのまま使用してください。"""

    raw = call_claude_cached(client, SONNET_MODEL, SONNET_COPYWRITER_SYSTEM, user_content, max_tokens=2048)
    return clean_claude_output(raw)


def quality_check(draft: str, client) -> str:
    """Claude Sonnet で品質チェック・修正を行い、完成版を返す。"""
    raw = call_claude_cached(client, SONNET_MODEL, SONNET_EDITOR_SYSTEM, draft, max_tokens=2048)
    return clean_claude_output(raw)


# ===== MD 保存 =====

def clean_claude_output(text: str) -> str:
    """Claude出力からコードフェンスを除去してmarkdownだけを取り出す。
    Claudeが ```yaml や ```markdown で囲んで出力することがあるため。
    """
    text = text.strip()
    # 先頭の ```yaml / ```markdown / ``` を除去
    text = re.sub(r'^```(?:yaml|markdown|md)?\s*\n', '', text)
    # 末尾の ``` を除去
    text = re.sub(r'\n```\s*$', '', text)
    text = text.strip()
    # frontmatter の --- で始まることを確認（前置きテキストがある場合は除去）
    if not text.startswith('---'):
        match = re.search(r'^---', text, re.MULTILINE)
        if match:
            text = text[match.start():]
    return text


def extract_frontmatter_title(markdown: str) -> str:
    """frontmatter の title フィールドを取り出す。"""
    match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', markdown, re.MULTILINE)
    return match.group(1).strip() if match else ""


def save_markdown(content: str, item: dict) -> str:
    """生成された markdown を src/content/news/ に保存する。"""
    os.makedirs(NEWS_DIR, exist_ok=True)

    # frontmatter から title を取得してスラッグ生成
    fm_title = extract_frontmatter_title(content)
    slug = make_slug(item["source_url"], fm_title or item["title"])

    # 同名ファイルが既に存在する場合はサフィックスを付ける
    filepath = os.path.join(NEWS_DIR, f"{slug}.md")
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(NEWS_DIR, f"{slug}-{counter}.md")
        counter += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  保存: {os.path.basename(filepath)}")
    return filepath


# ===== メイン =====

def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY が設定されていません")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print("=== AI News Compass 自動投稿スクリプト ===")
    print(f"実行日時 (JST): {today_jst()} {current_time_jst()}")

    # 1. 重複排除リストを読み込む
    used_urls = load_used_urls()
    print(f"\n[1] 投稿済みURL数: {len(used_urls)}")

    # 2. ニュース収集
    print("\n[2] ニュース収集...")
    candidates = []
    candidates.extend(fetch_reddit(used_urls))
    candidates.extend(fetch_hackernews(used_urls))
    candidates.extend(fetch_rss(used_urls))
    print(f"  合計候補: {len(candidates)}件")

    if not candidates:
        print("\nニュース候補が見つかりませんでした。終了します。")
        set_github_env("POST_DATE", today_jst())
        set_github_env("POST_TIME", current_time_jst())
        return

    # 3. スコア順で上位 POSTS_PER_RUN 件を選択
    selected = sort_and_select(candidates, POSTS_PER_RUN)
    print(f"\n[3] 選択: {len(selected)}件")
    for i, item in enumerate(selected, 1):
        print(f"  {i}. [{item['source_name']}] {item['title'][:60]}")

    # 4. 各記事を生成
    saved_urls = set()
    for i, item in enumerate(selected, 1):
        print(f"\n[4-{i}] 記事生成: {item['title'][:50]}...")

        # Step A: 翻訳・要点抽出 (Haiku)
        print("  Step A: 翻訳・要点抽出 (Haiku)...")
        summary = translate_summarize(item, client)

        # Step B: 記事生成 (Sonnet / copywriting)
        print("  Step B: 記事生成 (Sonnet)...")
        draft = generate_article(item, summary, client)

        # Step C: 品質チェック (Sonnet / editor)
        print("  Step C: 品質チェック (Sonnet)...")
        final = quality_check(draft, client)

        # Step D: 保存
        save_markdown(final, item)
        saved_urls.add(item["source_url"])

    # 5. used_urls.json を更新
    used_urls.update(saved_urls)
    save_used_urls(used_urls)
    print(f"\n[5] used_urls.json 更新: {len(used_urls)}件")

    # 6. GitHub Actions 環境変数をセット
    set_github_env("POST_DATE", today_jst())
    set_github_env("POST_TIME", current_time_jst())

    print(f"\n=== 完了: {len(saved_urls)}記事を生成しました ===")


if __name__ == "__main__":
    main()
