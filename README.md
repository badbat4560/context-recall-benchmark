# Context Recall Benchmark

A small reproducible experiment: replace a conversation window with a compact handoff, retrieve relevant exact records, and compare answers against full history.

**The objective is a smaller active LLM context, not a smaller persistent database.** Every segment in this fixture is KEEP: exact content remains recoverable.

## Quick start (no dependencies or credentials)

Requires Python 3.12 or newer. From the repository root:

```sh
python benchmark.py offline
python -m unittest discover -s tests -v
python benchmark.py rescore --input results/original-run.json
```

Offline mode checks all 49 exact records and recomputes the published scores and token totals from the recorded answers. **It does not run an LLM.**

## Run a new live experiment

Use OpenAI-compatible chat and embedding endpoints. Set these environment variables (URLs should include `/v1` where your server requires it):

```sh
export CHAT_BASE_URL=https://your-chat-server.example/v1
export CHAT_MODEL=your-pinned-model
export CHAT_API_KEY=your-key
export EMBED_BASE_URL=https://your-embedding-server.example/v1
export EMBED_MODEL=your-pinned-embedding-model
export EMBED_API_KEY=your-key
python benchmark.py run --output results/my-run.json
```

In PowerShell use `$env:CHAT_MODEL = 'your-pinned-model'` and the same syntax for the other variables. Keys are optional for unauthenticated local endpoints. They are read from the environment and are not written to results. Live mode sends only the bundled synthetic fixture, questions, and generated handoff to your configured endpoints. It makes 36 sequential chat requests plus embedding requests; provider charges may apply.

The runner refuses to overwrite existing results. It checkpoints after each completed question. An interrupted run is partial: inspect `summary.n`; a complete run has 12. No automatic retry or resume is implemented.

## Protocol

- 49 synthetic tool-role records, including 36 distractors and a later correction.
- 12 fixed questions with predetermined expected values and designated evidence ordinals.
- Full history, handoff only, and handoff plus semantic top-5 recall.
- Same model, instructions, temperature 0, and 160 output-token limit for every arm.
- The question itself is the search query. Expected answers never enter the prompts or retrieval queries.
- Exact-match scoring after trimming whitespace/backticks, case folding, and removing a final period. No LLM judge.
- Input token totals use the endpoint's reported `usage.prompt_tokens`; missing usage is reported as unavailable, not zero.

Inspect `data/corpus.json` before running. Documentation IP ranges and `example` names are fictional. Gold answers are public evaluation data, not hidden from the person running the test.

## Original recorded result

| Arm | Correct |
|---|---:|
| Full history | 12/12 |
| Handoff only | 1/12 |
| Handoff + recall | 12/12 |

Designated evidence in top 5: 12/12. Exact-hash round trips: 49/49.

Reported input tokens: **96,819 full-history vs 22,296 recall**, or **76.97% fewer**, including retrieved records. This excludes compaction, embeddings, reranking, and output costs. It is not a price or complete-task cost benchmark.

## Portable runner: live validation

`results/portable-live.json` records a separate complete run of the bundled runner:

| Arm | Correct |
|---|---:|
| Full history | 12/12 |
| Handoff only | 2/12 |
| Handoff + recall | 12/12 |

Designated evidence in top 5: 12/12. Reported input tokens: **96,819 vs 14,208**, or **85.33% fewer**. The deterministic handoff exposes the first record, so handoff-only correctly answers that question as well as UNKNOWN. This is a different protocol variant from the original result above; do not mix their token totals.

Serving aliases are redacted and weight revisions were not captured. This validates that the public runner works against live endpoints, not that every model will reproduce these scores.

```sh
python benchmark.py rescore --input results/portable-live.json
```

## Reproduction boundary: original vs portable

`results/original-run.json` is evidence from the original deployment, **not an output of this portable implementation**. Private serving aliases have been redacted; answers, usage, ranks, and measurements are preserved.

| Component | Original recorded run | Portable runner |
|---|---|---|
| Exact store | Temporary PostgreSQL tables | In-memory SQLite |
| Vector search | Local Qdrant | Exhaustive cosine similarity |
| Embeddings | Deployment service | Your configured endpoint |
| Reranking | Configured production path | None |
| Handoff | Production summary/NLI path with fallback | Deterministic first-record excerpt + manifest |
| Answer model | Private serving alias; weights not pinned | Your configured endpoint/model |
| Agent | Harness-initiated query | Harness-initiated query |

The corpus, questions, answer instructions, scoring, and three-arm comparison are reproducible. Exact original model outputs, ranking, handoff, and token counts cannot be guaranteed: the original run did not capture model revisions or the complete handoff. This repository does not package the private production service or claim full-stack reproduction.

The portable runner is a transparent KEEP-only reference, not the full Compress v2 policy. It contains no GLiClass, LLMLingua, NLI, DROP route, or durable deletion-barrier implementation. Its SQLite store is ephemeral. Do not use it as a production memory service.

## Limits

One small synthetic corpus with named-entity queries and repeated filler is a smoke test, not proof of general lossless memory. The unknown-password question is intentionally unanswerable and accounts for one handoff-only success. No autonomous recall decisions, adversarial prompts, multi-compaction chains, production-sized retrieval index, HTTP authorization, or concurrency are tested. All records use KEEP, so this says nothing about compression or deletion-policy accuracy.

Pin your model weights, tokenizer, embedding model, server versions, and hardware separately when publishing a comparison. Temperature 0 alone does not guarantee determinism. New results include requested/returned model names and available system fingerprints, but an alias is not a weight revision.

## Files

- `benchmark.py`: dependency-free runner, exact store, search and scorer.
- `data/corpus.json`: complete source records and evaluation questions.
- `results/original-run.json`: sanitized original answers and measurements.
- `tests/test_benchmark.py`: protocol and scorer checks.

No private service addresses, credentials, user conversations, or production configuration are required.

## License

MIT; see LICENSE.

## Article and discussion

[Hashnode article](https://badbat4560.hashnode.dev/smaller-context-recoverable-history-inside-an-agent-memory-handoff) · [DEV mirror](https://dev.to/badbat4560/smaller-context-recoverable-history-inside-an-agent-memory-handoff-404j) · [Telegram discussion](https://t.me/badbat4560/12) · [Instagram](https://www.instagram.com/badbat4560/)
