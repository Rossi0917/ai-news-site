# AIニュースサイト

GitHub Pages と Astro で運用する、AIニュース特化の静的サイトです。

## 開発

PowerShell で `npm` がブロックされる場合は `npm.cmd` を使います。

```bash
npm.cmd install
npm.cmd run dev
```

## 記事追加

記事は `src/content/news/` に Markdown で追加します。

```md
---
title: "記事タイトル"
description: "記事の短い説明"
pubDate: 2026-05-24
sourceName: "出典名"
sourceUrl: "https://example.com"
tags: ["AI", "生成AI"]
---

本文を書きます。
```

## 公開

GitHub の Pages 設定で Source を `GitHub Actions` にすると、`main` ブランチへの push で自動公開されます。
