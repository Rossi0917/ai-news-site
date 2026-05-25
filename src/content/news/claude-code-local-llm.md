---
title: "ローカルLLM×Claude Codeで完全オフライン開発——実践セットアップ手順まとめ"
description: "OllamaとClaude Codeを組み合わせてオフライン環境でAI支援コーディングを行う方法が話題になっています。実際のフライト中でも動作した手順を紹介します。"
pubDate: 2026-05-24
sourceName: "Reddit r/ClaudeCode"
sourceUrl: "https://www.reddit.com/r/ClaudeCode/comments/1tkja8d/my_experience_using_claude_code_with_local_llm/"
tags: ["AIニュース", "Claude Code", "ローカルLLM", "Ollama", "AI開発"]
affiliate: false
---

「飛行機の中でもAIコーディング支援が使えた」——そんな体験報告がRedditのClaude Codeコミュニティで話題になっています。使ったのは「Ollama（オラマ）」というローカルLLM実行ツールとClaude Codeの組み合わせで、インターネット接続なしでAI支援開発ができるというものです。

ローカルLLMとは、ClaudeやChatGPTのようなクラウドAIではなく、自分のパソコン上で動かすAIモデルのこと。Ollamaを使えばLlamaやMistralといったオープンソースモデルを手元で動かせます。コードやデータがクラウドに送られないので、セキュリティやコスト面を気にする開発者にとって魅力的な選択肢です。

セットアップの流れはシンプルで、①事前にWi-Fi環境でモデルをダウンロードしておく（14Bモデルで約9GB、26Bで約17GB）、②Claude CodeのAPIエンドポイントをOllamaに向ける、③エイリアスを設定して使い分けやすくする——という手順です。「機内に入ってからダウンロードしようとしても遅い」という注意書きがリアルですね。

クラウドのClaude本体に比べると精度は落ちますが、オフライン・低コスト・プライバシー重視の用途では十分使えそうです。

---

「飛行機でコーディングしながらAIに相談できる」という発想自体が面白いですね。セキュリティの厳しい職場でのAI活用にも応用できそうで、開発者じゃなくても知っておくと役立つ話だと思いました。

**参照元：** [Reddit r/ClaudeCode 投稿](https://www.reddit.com/r/ClaudeCode/comments/1tkja8d/my_experience_using_claude_code_with_local_llm/)
