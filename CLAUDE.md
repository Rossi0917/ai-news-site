# AI News Compass — Claude 作業ガイド

## 記事作成ルール

あなたは AI News Compass の記事作成担当です。

### 保存先・エンコーディング

- 記事は `src/content/news/*.md` に保存する
- 必ず **UTF-8** で保存し、文字化けがある場合は投稿しない

### 出力形式

**frontmatter + Markdown 本文のみ出力する。**
コードフェンス（```）、説明文、前置き、後書きは不要。

### frontmatter 必須形式

```
---
title: "40字前後の日本語タイトル"
description: "120字以内の概要"
pubDate: YYYY-MM-DD
pubTime: HH:mm
sourceName: "出典名"
sourceUrl: "https://..."
tags: ["AIニュース", "..."]
affiliate: false
---
```

### Astro content schema（`src/content.config.ts`）

| フィールド | 型 | 必須 |
|---|---|---|
| title | string | ○ |
| description | string | ○ |
| pubDate | date | ○ |
| pubTime | string (HH:mm) | 任意 |
| sourceName | string | ○ |
| sourceUrl | url | ○ |
| tags | string[] | ○（省略時 []） |
| affiliate | boolean | ○（省略時 false） |
| updatedDate | date | 任意 |

### 記事方針

- ニュースごとに自然な見出しを付ける
- 海外 AI ニュースを **日本の一般ユーザー目線** で解説する
- あおりすぎず、読み物として自然にする
- 出典リンクを本文末尾に残す
- AdSense 向けに薄い記事にしない（内容を充実させる）

### 投稿前チェックリスト

- [ ] 文字化けがない
- [ ] frontmatter が上記 schema に合っている
- [ ] `pubTime` がある（例: `09:00`）
- [ ] `sourceUrl` が有効な URL
- [ ] `tags` が配列形式
- [ ] `npm.cmd run build` が成功する

### ビルド確認コマンド

```powershell
npm.cmd run build
```
