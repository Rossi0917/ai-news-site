import { defineCollection } from "astro/content/config";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const news = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/news" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    pubTime: z.string().regex(/^\d{2}:\d{2}$/).optional(),
    updatedDate: z.coerce.date().optional(),
    sourceName: z.string(),
    sourceUrl: z.string().url(),
    tags: z.array(z.string()).default([]),
    affiliate: z.boolean().default(false)
  })
});

export const collections = { news };
