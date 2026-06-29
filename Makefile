.PHONY: db app cli test eval-refinement eval-sql align label

db:
	uv run python -m src.db.setup_db

app:
	uv run python -m streamlit run src/agent/app.py

cli:
	uv run python -m src.agent.cli

test:
	uv run pytest src/agent/tests

# --- Evaluation ---

# Run the agents + LLM judges on a dataset -> results.json + judged.json.
eval-refinement:
	uv run python -m src.agent.evals.evals --dataset questions_refinement.csv --target refinement

eval-sql:
	uv run python -m src.agent.evals.evals --dataset questions_sql.csv --target sql

# Compare the LLM judges against human labels (no LLM calls).
align:
	uv run python -m src.agent.evals.align

# Streamlit tool to manually label results.json.
label:
	cd src/agent/evals && uv run streamlit run label_evals.py


