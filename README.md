# Data Assistant Agent: Natural-Language Query Interface for Relational Data Warehouses

A data assitant that allows users to query a relational data warehouse using both natural language and reusable command shortcuts.

## The Problem

Business users cannot easily retrieve data from a complex data warehouse without relying on data engineers, due to the need for SQL and fragmented reporting tools. Data engineers spend significant time repeatedly answering similar questions and manually querying data, leading to inefficiency. There is no simple, trusted interface where users can quickly access validated data insights or reuse common queries.

## What It Does

The system processes user messages via WhatsApp, either as natural language queries or predefined commands (e.g., /today, /revenue).

### Input
User messages via WhatsApp, either as natural language queries or predefined commands (e.g., /today, /revenue).

### Processing
Classify user intent; retrieve relevant schema and similar past queries from a query memory system; generate and validate SQL using retrieval-augmented generation; execute queries in DuckDB; and compute trust signals based on similarity to previously validated queries.

### Output
Concise answers delivered in WhatsApp, including results, explanations, SQL traces, and trust indicators (e.g., similar queries, tables used).

### Success Metric
Reduction in repeated manual queries and improved user trust, measured by reuse of shortcuts and accuracy on predefined business questions.

## Setup

1. Install uv if you don't have it yet: https://docs.astral.sh/uv/getting-started/installation/

2. Clone this repository (or download the zip and extract it).

3. Create a `.env` file from the template and add your API key:

       cp .env.example .env

4. Install dependencies:

       uv sync

5. Start Jupyter:

       uv run jupyter notebook

## Notebooks

- `notebooks/01-setup.ipynb` - smoke test that confirms your environment works
- `notebooks/02-rag.ipynb` - a minimal RAG baseline you can adapt to your own data

## Data

Put your project data in the `data/` folder. See `notebooks/02-rag.ipynb` for how to load it.
