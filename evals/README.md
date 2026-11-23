# Evaluation set (Phase 4.6)

A repeatable check of answer quality: the same 20 questions, asked the same way, so
runs before and after a change (prompt, model, cutoff) can be compared.

## The questions

`questions.json` has 20 questions about the PDFs in `samples/`:

- **15 answerable** (`A01`–`A15`), each with the document and page(s) the answer is on.
  A **retrieval hit** means one of the answer's citations comes from that document and
  one of those pages.
- **5 unanswerable** (`U01`–`U05`). Correct means the similarity cutoff stopped it:
  *I couldn't find this in the documents*, without calling the LLM.

They come from the 27 hand-checked questions in `reports/ask-cutoff-results.xlsx`.
The expected pages were found by searching each PDF's text for the answer.

## Run it

Needs `LLM_PROVIDER=openai` and `OPENAI_API_KEY` in `.env`. The fake provider runs
too, but its scores mean nothing.

```sh
bash scripts/run-eval.sh
```

The script uploads the samples as the admin (only the ones not there yet), waits until
they're ready, and runs:

```sh
docker compose exec api python manage.py run_eval --commit $(git rev-parse --short HEAD)
```

Options: `--email` (who asks, default the seeded employee), `--questions`, `--out`,
`--keep-answers` (by default the 20 answers are removed from that user's history
afterwards; the report keeps them).

## Targets (PLAN.md 4.6)

| Measure | Target |
| --- | --- |
| Retrieval hits | 12 of 15 |
| "Not found" for unanswerable questions | 4 of 5 |
| Answers under 30 seconds | 9 of 10 |

Answer quality (is the text right?) is still graded by two people from the report's
`answer` column.

## Results

Each run writes:

- `results/<date>-<commit>.json`: the settings (commit, embedding model, answer model,
  cutoff, max chunks), the summary, and one row per question: the answer, its
  citations, the seconds it took, whether it hit, and `top_match` (the best chunk even
  under the cutoff, to see how close a miss was).
- `results/runs.csv`: one line per run, to compare runs at a glance.
