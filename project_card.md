# Capstone Project: GenAI Agent for Database Insights at the Dutch Railways

This projects implements a GenAI agent that can answer natural language questions about the Dutch Railways safety situation by generating SQL queries over a DuckDB warehouse that combines social media signals, news coverage, and internal incident logs.

## Problem Statement

The problem is threefold:
- Manual querying of structured data (incident logs) is time-consuming and requires SQL expertise, which makes it dependent on datateam support for insights.
- Information overload makes it more difficult to retrieve relevant information in a timely manner. In addition, this results in more ad-hoc requests to the datateam for insights that could be automated.
- Unstructured, safety-relevant information about Dutch railway stations (social media, news) are hard to access and analyze at scale, leading to missed early warnings and incomplete situational awareness for station safety teams.

## Objective

The objective of this project is to make it possible to ask questions in natural language about data related to Dutch railway station safety and receive accurate, traceable insights without needing SQL expertise. This results in faster information retrieval that is less dependent on datateam support. 

## Architecture

### Agent Workflow

The agent follows these steps to answer a user question:
1. User inputs a natural language question about station safety.
2. The agent retrieves relevant schema information and example NL-to-SQL pairs.
3. The agent checks whether the question can be answered with the available data and identifies relevant tables/columns. If not, it responds with a low-confidence warning and asks for clarification or suggests alternative questions.
4. If the question is answerable, the agent generates a candidate SQL query and tests it against the DuckDB warehouse.
5. The agent evaluates the results for correctness and confidence. If the confidence is low, it includes a warning in the response.
6. The agent returns the answer along with confidence and rationale, including referenced tables and generated SQL for traceability.

### Test Scenarios

Test scenario 1:
- If there is no data available for the questions, the agent should not run any SQL and tell the user that it cannot answer the question with the current data, and suggest alternative questions or ask for clarification.

Test scenario 2:
Tool call order: 1. get_db_metadata, 2. get_example_queries, 3. run_sql

Test scenario 3:
- output should include confidence indicators and rationale for the answer

Think about:
What output do you expect from the agent?
Which tools should be called and in what order?
What parameters are passed to the tools?
Are there scenarios where the agent doesn't behave as expected?


## Product Scope

### In Scope
- Natural-language Q&A over station safety data
- Daily shift briefing with overnight flagged items
- On-demand early-warning checks per station
- Correlation between social signals, news narratives, and internal incidents
- Trust signals (freshness, confidence, source mix, SQL traceability)

### Out of Scope
- Autonomous operational actions
- Automated enforcement or policing decisions
- Passenger-level profiling and unreviewed escalations

## Core Architecture

### Data Sources
1. X API data: posts mentioning stations, train safety, incidents, disruption, harassment
2. News scraping: national outlets, regional/local sites, hyperlocal sources
3. Internal incident logs: station security and safety reports

### DuckDB Warehouse Model
- `posts`: raw X posts and metadata
- `news_articles`: raw news article text, source, URL, publish date
- `stations`: station metadata (name, code, region)
- `incidents`: internal incident records
- `post_enrichment`: topic/risk labels, station mentions, confidence
- `news_enrichment`: topic/risk labels, station mentions, publication tier, confidence
- `daily_station_summary`: aggregates by station, time window, and source type

### Retrieval + Generation
Reuse the pattern from `notebooks/02-rag.ipynb`:
- schema document generation
- NL-to-SQL example retrieval corpus
- prompt assembly with schema + examples
- LLM SQL generation and execution in DuckDB
- trust object in final response

## Ingestion and Enrichment Strategy

### X Ingestion
- Batch mode: hourly or daily
- Filters: station names, NS, train safety-related terminology
- Enrichment: language, station mapping, topic classification, risk scoring, confidence bands

### News Ingestion
- Mode: on-demand full-text scraping
- Coverage: national + local + hyperlocal outlets
- Enrichment: station mentions, topic/risk tags, sentiment, publication tier, confidence
- Compliance: robots.txt checks, rate limits, source terms-of-service compliance

## RAG Corpus Focus
Use domain-specific NL-to-SQL examples for questions like:
- "What concerning posts and news mention Amsterdam Centraal in the last 24 hours?"
- "Which stations show rising concern in X + news but low incident reporting?"
- "Did media and social chatter increase before recorded incidents at station X?"

## Trust and Safety Layer
Every assistant answer should include:
- last refresh timestamp
- confidence bands
- row counts and source composition
- referenced tables and generated SQL
- low-confidence warning when applicable

## Agentic Workflows (Human-in-the-Loop)
1. Shift Briefing Agent
- Runs each morning
- Summarizes overnight station-level concerns from X + news
- Adds incident correlation and confidence indicators

2. Anomaly Alert Agent
- Flags urgent violence/threat signals for supervisor review
- Does not auto-escalate without human confirmation

3. Early-Warning Agent (On-Demand)
- User-triggered station check
- Highlights emerging narratives from X/news that are not yet reflected in incidents

4. Weekly Trend Agent
- Compares station and risk-type movement week-over-week

## Implementation Sequence
1. Replace demo schema with railway safety schema
2. Add X and news ingestion pipelines
3. Build enrichment and confidence labeling
4. Create multi-source NL-to-SQL retrieval examples
5. Extend trust object and response format
6. Add shift briefing and early-warning workflows
7. Validate on historical station cases
8. Add governance controls and rollout guardrails

## Evaluation
- Retrieval quality on representative railway safety questions
- SQL correctness and explainability
- False-positive/false-negative rates for alerts
- Lead-time benefit: whether social/news signals precede incidents
- Staff usability and trust acceptance in pilot stations

## Governance
- GDPR-aligned handling of social and news content
- Data retention and audit logging
- Manual review requirement for high-severity alerts
- Clear escalation protocol to security/police channels

## Success Criteria
- Faster station-level situational awareness for shift supervisors
- Reduced manual triage work
- Better early detection of rising safety narratives
- High trust through traceable, evidence-backed outputs