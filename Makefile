.PHONY: db app cli test eval-refinement eval-sql eval-app

db:
	uv run python -m src.db.setup_db

app:
	uv run python -m streamlit run src/agent/app.py

cli:
	uv run python -m src.agent.cli

test:
	uv run pytest src/agent/tests

# --- Evaluation ---

# Run the agents + LLM judges on a dataset -> data/results.json + score.
eval-refinement:
	uv run python -m src.agent.evals.run --dataset questions_refinement.csv --target refinement

eval-sql:
	uv run python -m src.agent.evals.run --dataset questions_sql.csv --target sql

# Streamlit app to review judge labels and give feedback.
eval-app:
	uv run streamlit run src/agent/evals/app.py
