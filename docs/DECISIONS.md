# Technical Decisions

Notes on the non-obvious choices I made while building InsightHub, written so I
remember the reasoning during interviews and so anyone reading the code understands
the *why*, not just the *what*.

---

## Why I chose Azure SQL over PostgreSQL

I went with Azure SQL because the project is already entirely in Azure and the star
schema pattern fits a column-oriented workload better than a general-purpose OLTP
setup. Azure SQL also gave me Non-Clustered Columnstore Indexes (NCCI) out of the box
— one index on FactSales cut my aggregate query time from ~8s to under 1s on 119K rows.
Postgres would have worked, but I'd have had to reach for extensions like `timescaledb`
or `citus` to get the same analytics performance.

---

## Why I used a star schema instead of a normalised schema

The dashboards need to aggregate across multiple dimensions simultaneously — revenue by
region *and* product *and* date — which means lots of multi-table joins. A star schema
pre-joins the slow parts into dimension tables and keeps the fact table narrow, so
reporting queries are just one big scan rather than a chain of nested lookups. I stored
`DateKey` as an INT (`YYYYMMDD`) rather than a foreign key to a date string; that single
decision cut FactSales row size by about 4 bytes per row, which matters at 119K+ rows
and even more at production scale.

---

## The hardest bug I fixed

The toughest one was a silent geography key mismatch that left ~30,000 FactSales rows
with a NULL `GeographyKey`. The symptoms were weird: ETL succeeded, row counts looked
right, but 20% of rows disappeared from any geo-filtered report. The root cause was
that the old `fast_executemany` ODBC call padded empty state codes with spaces —
so `''` was stored as `'  '` (two spaces) in DimGeography. My lookup code was comparing
`''` against `'  '` and always missing. I found it by printing the raw bytes of a key
that *should* have matched: `b'\x20\x20'` versus `b''`. The fix was one line —
`.strip()` in the geo-map builder — but it took two hours to find because the data
*looked* correct in SSMS (it renders trailing spaces invisibly).

---

## Why hybrid search beats pure vector search for this use case

Pure vector search is great for semantic similarity but terrible for exact terms —
if someone asks "what is the Q3 2025 revenue?" a cosine similarity search will find
documents that *talk about revenue* but might completely miss the document that has the
exact number. Hybrid search combines BM25 keyword scoring with vector embeddings, then
Azure AI Search's semantic re-ranker does a final pass using a cross-encoder model.
The result is that both "find something that means X" and "find the document that
contains this exact term" queries work well. I measured this by running the same 10
test queries against pure-vector and hybrid; hybrid answered 8/10 correctly versus 5/10
for pure vector on the factual questions.

---

## How the RAG pipeline prevents hallucinations

The system prompt explicitly tells GPT-4o to answer *only* from the retrieved chunks
and to say "I don't have information on that" if the chunks don't cover the question.
The retrieved text is injected verbatim into the user turn, not the system turn, so
the model can distinguish "what I was told to believe" from "what was retrieved right
now." I also cap `max_tokens=1000` per insight call — truncated JSON is easier to
detect and fail fast on than a silently wrong long answer. For the AI Insights
specifically, I bake exact ISO date ranges and concrete SQL metrics into every prompt
so GPT-4o has no opportunity to invent numbers.

---

## What I would do differently next time

I'd decouple the ETL from direct Azure SQL writes and push data through Azure Event
Hubs instead, so the pipeline is resumable and observable rather than a 2-hour
black-box Python script. I'd also not store JWTs in `localStorage` — that's fine for
a demo but in production I'd use `httpOnly` cookies to protect against XSS. And I'd
start with proper test coverage from day one rather than debugging by reading raw
byte values at 1am.
