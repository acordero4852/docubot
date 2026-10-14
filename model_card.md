# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**  
Answer developer questions about the sample app's docs (`docs/`), and only from those docs. It compares three ways of doing that: LLM alone, retrieval alone, and retrieval plus LLM (RAG).

> Goal: grounded answers, with "I do not know" when the docs don't cover the question.

**What inputs does DocuBot take?**  
For example: user question, docs in folder, environment variables.

> A question typed in the CLI, the `.md`/`.txt` files in `docs/`, and `GEMINI_API_KEY` (from `.env`) for modes 1 and 3.

**What outputs does DocuBot produce?**

> Mode 1: free-form LLM text. Mode 2: raw snippets labelled with filenames. Mode 3: a short LLM answer plus the files it relied on. Modes 2 and 3 return "I do not know" when nothing passes the evidence threshold.

---

## 2. Retrieval Design

**How does your retrieval system work?**  
Describe your choices for indexing and scoring.

- How do you turn documents into an index?
- How do you score relevance for a query?
- How do you choose top snippets?

> - **Index:** inverted index, word -> files containing it. Words are lowercased, split on `[a-z0-9_]+`, stopwords removed, and crudely stemmed (`generated`/`generation` -> `generat`).
> - **Snippets:** each doc is split on blank lines into paragraphs, and a lone `#` heading is glued to the paragraph after it.
> - **Score:** number of *distinct* query words in the snippet. Raw counts let a token checklist outrank the real answer.
> - **Selection:** the index finds candidate docs, every section is scored, and the top 3 with score >= `MIN_SCORE` (2) are returned.

**What tradeoffs did you make?**  
For example: speed vs precision, simplicity vs accuracy.

> Simplicity over accuracy. There is no TF-IDF or embeddings, so common words like "token" or "users" are not down-weighted, and synonyms are missed. Paragraph snippets are small enough to read but can split an answer across paragraphs (for example `DATABASE_URL` sits in a different paragraph from the Overview).

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**  
Briefly describe how each mode behaves.

- Naive LLM mode: calls the LLM with the full corpus text; no retrieval, no refusal rule.
- Retrieval only mode: never calls the LLM.
- RAG mode: calls the LLM only if retrieval returned snippets; otherwise it refuses without spending an API call.

**What instructions do you give the LLM to keep it grounded?**  
Summarize the rules from your prompt. For example: only use snippets, say "I do not know" when needed, cite files.

> The prompt tells the model to use only the snippets, not to invent functions/endpoints/config, to reply "I do not know based on the docs I have." when they are insufficient, and to name the files it relied on.

---

## 4. Experiments and Comparisons

Run the **same set of queries** in all three modes. Fill in the table with short notes.

You can reuse or adapt the queries from `dataset.py`.

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Where is the auth token generated? | Harmless but useless: asked which project/service, no answer | Helpful: `AUTH.md` "Token Generation" snippet (`generate_access_token` in `auth_utils.py`) | Helpful: one-sentence answer, cites `AUTH.md` | RAG easiest to trust |
| How do I connect to the database? | Harmful: confident, long answer with Postgres `DB_*` vars, Prisma and Go examples, none in the docs | Partly helpful: three DATABASE.md paragraphs (intro, overview, `db.py`); the `DATABASE_URL` paragraph is not in the top 3 | Partly harmful: grounded, but omits `DATABASE_URL` and the SQLite fallback | Retrieval ranking limits RAG |
| Which endpoint lists all users? | Harmful: guessed `GET /users` (docs say `GET /api/users`) | Helpful but noisy: right snippet first, plus `/api/projects` and `get_all_users()` | Helpful: `GET /api/users`, cites `API_REFERENCE.md` | |
| How do I reset a user's password? (not in docs) | Harmful: invented `POST /api/v1/users/{id}/password-reset` | Harmful-ish: returned an irrelevant `postgres://user:password@...` snippet | Helpful: "I do not know based on the docs I have." | Docs have no such feature |

**What patterns did you notice?**  

- When does naive LLM look impressive but untrustworthy?  
- When is retrieval only clearly better?  
- When is RAG clearly better than both?

> - **Naive LLM:** most confident when it is least grounded. The database answer reads as authoritative and is generic boilerplate; the password-reset answer is a fabricated endpoint. On the auth question it asked for context instead of reading the docs it was given.
> - **Retrieval only:** accurate and traceable (right file and paragraph), but you have to read raw markdown and pick the answer yourself, as with the three-snippet auth result. It can also return weak matches, like the password snippet.
> - **RAG:** clearest when the answer sits in one snippet (auth, users): short, cited, and it refuses when there is nothing to use. It is only as good as retrieval.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**  
For each one, say:

- What was the question?  
- What did the system do?  
- What should have happened instead?

> **Failure case 1 (RAG): "How do I connect to the database?"** RAG answered from the `db.py` and Overview snippets ("use `db.py`... PostgreSQL via a connection string") and never mentioned `DATABASE_URL` or the SQLite fallback to `app.db`. Those facts are in DATABASE.md, but that paragraph scored no higher than the intro paragraphs (ties at 2 distinct words) and missed the top 3. The LLM was faithful to its context; the context was incomplete. It should have surfaced the `DATABASE_URL` paragraph.

> **Failure case 2 (retrieval only): "How do I reset a user's password?"** The docs don't cover this, but a code-fence snippet containing `user:password@localhost` matched two query words and passed `MIN_SCORE`. It should have refused. RAG caught it because the LLM judged the snippet irrelevant, so the LLM acted as a second guardrail.

**When should DocuBot say “I do not know based on the docs I have”?**  
Give at least two specific situations.

> - The question is about something the docs don't contain (password reset, "meaning of life"), so no snippet reaches the evidence threshold.
> - The retrieved snippets match on incidental words but don't answer the question (the `user:password` URL snippet).
> - The question needs a fact that is only partly in the docs (for example a missing environment variable), and the docs only give the general shape.

**What guardrails did you implement?**  
Examples: refusal rules, thresholds, limits on snippets, safe defaults.

> - `MIN_SCORE = 2` distinct query words, checked in `retrieve`, so modes 2 and 3 both refuse on weak evidence.
> - RAG skips the LLM when retrieval is empty.
> - The prompt restricts the LLM to the snippets and requires an explicit refusal and file citations.
> - Top-3 cap on snippets.

---

## 6. Limitations and Future Improvements

**Current limitations**  
List at least three limitations of your DocuBot system.

1. Word-overlap scoring only: no synonyms, and the stemmer is crude (`users`/`user` work; irregular forms don't).
2. Ties between snippets are broken by document order, not relevance, so the best paragraph can miss the top 3.
3. A fixed threshold of 2 words can't refuse a short query on a covered topic and can't reject an incidental two-word match.

**Future improvements**  
List two or three changes that would most improve reliability or usefulness.

1. Weight rare words (TF-IDF) so "database" counts for more than "token" or "users".
2. Retrieve a snippet plus its neighbours/heading so answers aren't split across paragraphs.
3. Add a small eval set of question -> expected file/snippet and measure top-3 hit rate when changing scoring.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
Think about wrong answers, missing information, or over trusting the LLM.

> A developer who trusts a naive answer could follow invented config or call a nonexistent endpoint. A grounded-looking RAG answer can also be incomplete (the `DATABASE_URL` case) and still read as authoritative.

**What instructions would you give real developers who want to use DocuBot safely?**  
Write 2 to 4 short bullet points.

- Treat answers as pointers to the cited doc and check the source before acting on them.
- Prefer RAG over naive generation for anything about this codebase, and treat "I do not know" as a real result.
- Re-check retrieval (modes 2/3) whenever docs change, since a missing snippet silently produces an incomplete answer.

---
