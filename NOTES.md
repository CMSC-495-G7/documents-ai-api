# Stage 4 — Salvo: cutoff, timeout, errors and timing

Branch: `feat/ask-cutoff-and-timing`
Base: `origin/feat/ask-providers` (providers PR is not merged into `main` yet)
Previous commit: `253cbef` — `feat(ask): tune cutoff, enforce timeout, and log answer timing`

## Part 1 — Similarity cutoff

### Documents used

Five public HR/policy PDFs were uploaded through the API and processed with
`text-embedding-3-small` (1536 dimensions):

| Document | Pages | Chunks |
|---|---:|---:|
| FINA 2.30.015 Expense and Reimbursement CLEAN for Posting | 10 | 10 |
| Remote-Work-POLICY | 8 | 8 |
| staff-handbook-california | 57 | 70 |
| staff-loa-policy | 9 | 9 |
| wfp-onboarding-checklist | 8 | 8 |

Total: 105 chunks. All five documents reached `ready`.

`DatacapSetupGuide 1 1.pdf` was excluded. It is an internal work document, not
an HR policy, and it was not uploaded, committed, or sent to OpenAI.

### Measurements

The required set was 10 questions the documents answer and 5 questions they do
not answer. Top scores are cosine similarity (`1` = same meaning, `0` =
unrelated).

| Category | Question | Top score | Top document |
|---|---|---:|---|
| Answerable | How many days after an expense is incurred must it be submitted for reimbursement? | 0.576 | FINA 2.30.015 |
| Answerable | How far in advance should travel be booked? | 0.420 | FINA 2.30.015 |
| Answerable | How many days per week can employees work remotely? | 0.598 | Remote-Work-POLICY |
| Answerable | Who gives final approval for a remote work agreement? | 0.711 | Remote-Work-POLICY |
| Answerable | How much notice should departments give before terminating a remote work agreement? | 0.603 | Remote-Work-POLICY |
| Answerable | How many weeks of FMLA leave are eligible staff entitled to? | 0.610 | staff-handbook-california |
| Answerable | How long must an employee have worked to be eligible for FMLA? | 0.554 | staff-handbook-california |
| Answerable | How many weeks of paid parental leave are available to all parents? | 0.673 | staff-loa-policy |
| Answerable | Within how many days of hire must employment eligibility be verified? | 0.427 | staff-handbook-california |
| Answerable | What should be prepared before a new employee's first day? | 0.666 | wfp-onboarding-checklist |
| Off-topic | What is the capital of France? | 0.112 | staff-handbook-california |
| Off-topic | What is the CEO's salary? | 0.303 | staff-handbook-california |
| Off-topic | What is the office Wi-Fi password? | 0.265 | staff-handbook-california |
| Off-topic | How many students are enrolled at the university? | 0.358 | staff-handbook-california |
| Off-topic | What is the weather forecast for tomorrow? | 0.173 | staff-handbook-california |

Minimum required answerable score: `0.420`.
Maximum required off-topic score: `0.358`.

### Chosen cutoff

`ASK_SIMILARITY_CUTOFF=0.40` — between the answerable minimum (`0.420`) and the
off-topic maximum (`0.358`).

At this cutoff:

- Required answerable questions: 10 / 10 answered.
- Required off-topic questions: 5 / 5 returned `I couldn't find this in the documents`
  without calling the LLM.

Additional answerable questions were also measured. Two fell below `0.40`:
`What is the dress code?` (`0.331`) and `How do I request an accommodation?`
(`0.377`). This is the tradeoff for filtering all five required off-topic
questions. The full results are in `docs/ask-cutoff-results.xlsx`.

### Changed

- `config/settings.py` — cutoff default is `0.40`.
- `.env.example` — cutoff is `0.40`.
- `compose.yaml` — cutoff fallback is `0.40`.
- Local `.env` — cutoff is `0.40` (ignored by git).

## Part 2 — Clear errors and the 50 second limit

### Tests

Added to `core/tests/test_llm.py`:

- OpenAI answer timeout becomes `LLMError`.
- Gemini answer timeout becomes `LLMError`.
- Existing embedding timeout test continues to cover embeddings.

Added to `ask/tests/test_ask_api.py`:

- After a `/api/ask` 502, `GET /api/documents` still returns 200.

### Timeout behaviour

`core/llm.py` now creates both OpenAI and Gemini clients with
`max_retries=0`. Without this, the OpenAI SDK retries a timed-out request twice,
so a 50 second timeout could take about 150 seconds.

Manual checks:

- Wrong `OPENAI_API_KEY`: `/api/ask` returned
  `502 {"detail": "The answer service is unavailable. Please try again."}`.
- `LLM_TIMEOUT_SECONDS=1` with the correct key: `/api/ask` returned 502 in
  about 2.2 seconds, instead of about 5.3 seconds before `max_retries=0`.
- Both settings were restored afterwards; the real key and 50 second timeout
  were verified again.

## Part 3 — Answer timing log

`ask/api.py` now times `ask_question(...)` with `time.monotonic()` and logs:

```text
logger.info("Answer %s: %.1f s (%s)", answer.id, seconds, answer.model_name or "no LLM")
```

`logger = logging.getLogger(__name__)` is at the top of `ask/api.py`.

Config updates:

- `config/settings.py` — added the `"ask"` logger.
- `config/test_runner.py` — added `"ask"` to the log-suppression list.

Test added in `ask/tests/test_ask_api.py`:

- `self.assertLogs("ask.api", "INFO")` checks the line starts with `Answer ` and
  ends with `s (fake)`.

Verified in logs:

```text
INFO ask.api: Answer 100: 12.7 s (gpt-5-mini)
INFO ask.api: Answer 101: 0.6 s (no LLM)
```

## Tests

```bash
docker compose exec api python manage.py test
```

Result: **220 / 220 passed**.

## Result files and manual script

- `docs/ask-cutoff-results.xlsx` — cutoff measurements, required 15 questions,
  additional questions, document/chunk summary, and answer latency.
- `test-ask.sh` — updated for the providers architecture:
  - uses `core.llm` instead of `ask.providers`
  - uses `documents.Chunk` instead of `ask.Chunk`
  - checks `LLM_PROVIDER`, `OPENAI_API_KEY`, embedding model, chat model, and cutoff
  - seeds a document/chunk through `llm.embed`
  - checks an answerable question and an off-topic question through `/api/ask`

