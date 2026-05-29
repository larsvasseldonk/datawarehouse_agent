.PHONY: db agent

db:
	uv run python -m src.db.setup_db

agent:
	uv run python -m src.agent.agent
