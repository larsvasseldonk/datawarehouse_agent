from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class LocationSpecs(BaseModel):
    """
    Captures the geographic or spatial context of the safety incidents.
    An incident can happen at a station, on a specific train ride, or within a broad region.
    """
    stations: List[str] = Field(
        default=[],
        description="Exact station names (dienstregelpuntnaam) or shortcodes (e.g., ['Amsterdam Centraal', 'Utrecht Centraal'])."
    )
    train_numbers: List[int] = Field(
        default=[],
        description="Specific train series or train numbers where the incident occurred (e.g., [4000])."
    )
    regions: List[str] = Field(
        default=[],
        description="Operational or geographic regions (e.g., ['Noord-Oost', 'Randstad Zuid'])."
    )


class QueryFilter(BaseModel):
    column: str = Field(description="The exact database column name to filter on.")
    operator: str = Field(description="The SQL operator to use (e.g., '=', 'IN', 'LIKE').")
    value: str = Field(description="The filter value.")


class QuerySpecs(BaseModel):
    """
    Captures precise specifications for the target SQL query based on verified metadata.
    """
    fact_table: List[str] = Field(description="The target fact table(s) containing incident reports.")
    dimension_tables: List[str] = Field(default=[], description="Dimension tables required to join.")
    from_period: date = Field(description="The exact start date (YYYY-MM-DD).")
    to_period: date = Field(description="The exact end date (YYYY-MM-DD).")

    # Highly structured location object instead of a loose list
    location: LocationSpecs = Field(
        default_factory=LocationSpecs,
        description="The spatial filters for the query. Can combine stations, specific trains, or entire regions."
    )

    filters: List[QueryFilter] = Field(
        default=[],
        description="Non-spatial filters only (e.g., incident_type = 'Agressie', severity = 'Hoog')."
    )


class RAGResponse(BaseModel):
    """
    The final structured response delivered to the user. Ensures an audit trail
    between the generated SQL, the raw row metrics, and the natural language summary.
    """
    answer: str = Field(
        description="The clear, natural language summary of the data. If zero rows were returned, state clearly that no incidents matched the criteria."
    )
    query_executed_successfully: bool = Field(
        description="True if the SQL query ran without errors, even if it returned 0 rows. False if database error occurred."
    )
    row_count: int = Field(
        description="The exact number of rows returned by the SQL execution. Used to verify the 'answer' matches the dataset size."
    )
    query_specs: QuerySpecs = Field(
        description="The finalized specifications that were used to generate the SQL query."
    )
    sql_query: str = Field(
        description="The exact, clean SQL code that was executed against the database."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score (0.0 to 1.0). Deduct points if schemas were ambiguous or if complex business logic assumptions were made."
    )
    confidence_explanation: str = Field(
        description="Technical and functional justification for the confidence score. Must explain why the SQL logic perfectly maps to the user's safety query."
    )
    followup_questions: List[str] = Field(
        description="2-3 proactive, highly relevant follow-up questions that can be successfully answered using the available metadata."
    )
