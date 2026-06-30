# Evaluation Pipeline

A minimal proof-of-concept for evaluating the two agents (refinement + SQL). It runs the
agents on a set of questions, has an LLM judge label each output `good`/`bad`, prints a
performance score per agent, and ships a small app to review the judge's labels and give
feedback. Agent and judge token usage is traced with Logfire.

## Structure

```text
evals/
├── data/
│   ├── questions_refinement.csv   # evaluation questions for the refinement agent
│   ├── questions_sql.csv          # evaluation questions for the SQL agent
│   ├── results.json               # agent outputs + judge labels + your feedback
│   └── user_feedback.json         # 👍/👎 feedback collected from the chat app
├── judges.py    # the refinement and SQL LLM judges
├── run.py       # run the agents + judges, write results.json, print the score
└── app.py       # review judge labels and give feedback
```

## Usage

Run from the project root.

```bash
# Refinement agent + judge
uv run python -m src.agent.evals.run --dataset questions_refinement.csv --target refinement

# SQL agent + judge
uv run python -m src.agent.evals.run --dataset questions_sql.csv --target sql

# Use --limit N to run a random subset of questions.
# Use --provider chatns to run the judges on ChatNS instead of OpenAI.

# Review the judge labels and give feedback
uv run streamlit run src/agent/evals/app.py
```

### Targets

`--target` selects which agent(s) run on the dataset:

- `refinement` — runs the refinement agent only and judges its routing decision.
- `sql` — runs the SQL agent **directly** on each question (no refinement step) and
  judges the generated query and answer.
- `both` — runs refinement, then the SQL agent on any question that is handed off.

Use the dataset that matches the target: `questions_refinement.csv` with `refinement`
and `questions_sql.csv` with `sql`.
