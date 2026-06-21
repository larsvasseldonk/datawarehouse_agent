.PHONY: db app cli test eval

db:
	uv run python -m src.db.setup_db

app:
	cd src/agent && uv run streamlit run app.py

cli:
	cd src/agent && uv run python cli.py

test:
	uv run pytest src/agent/tests

eval:
	uv run python -m src.agent.evals.run_evals --questions questions_manual.csv
