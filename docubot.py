"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import re
import glob

# Common words that match every doc and say nothing about relevance.
STOPWORDS = {"the", "a", "an", "is", "are", "of", "to", "in", "on", "for", "and",
             "or", "do", "i", "how", "where", "which", "what", "does", "it", "be"}

# A snippet must match at least this many distinct query words to count as evidence.
MIN_SCORE = 2


def sections(text):
    """Split on blank lines; glue a lone '#' heading onto the paragraph after it."""
    out, heading = [], ""
    for block in (b.strip() for b in text.split("\n\n")):
        if not block:
            continue
        if block.startswith("#") and "\n" not in block:
            heading = block + "\n"
            continue
        out.append(heading + block)
        heading = ""
    return out


def words(text):
    """Lowercase, punctuation-free words minus stopwords."""
    found = re.findall(r"[a-z0-9_]+", text.lower())
    return [stem(w) for w in found if w not in STOPWORDS]


def stem(w):
    """Crude suffix strip so 'generated' and 'generation' both become 'generat'."""
    for suffix in ("ion", "ed", "ing", "es", "s"):
        if w.endswith(suffix) and len(w) > len(suffix) + 3:
            return w[: -len(suffix)]
    return w


class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}
        for filename, text in documents:
            for w in set(words(text)):
                index.setdefault(w, []).append(filename)
        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        # Score = number of DISTINCT query words present, so a snippet covering
        # more of the question beats one repeating a single word.
        return len(set(words(query)) & set(words(text)))

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select top_k relevant document snippets.

        Return a list of (filename, text) sorted by score descending.
        """
        # The index narrows to docs with a query word; then we score each section.
        candidates = {f for w in words(query) for f in self.index.get(w, [])}
        scored = [(self.score_document(query, sec), f, sec)
                  for f, text in self.documents if f in candidates
                  for sec in sections(text)]
        scored.sort(key=lambda t: t[0], reverse=True)
        # Guardrail: weak matches are not evidence, so return [] ("I do not know").
        return [(f, sec) for score, f, sec in scored[:top_k] if score >= MIN_SCORE]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
