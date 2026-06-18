from datetime import date
from typing import List
from pydantic import BaseModel, Field

class QueryFilter(BaseModel):
    """
    Represents an arbitrary key-value or categorical condition mapping to column operations.
    Use this to dynamically capture filters on dimensions or metrics without locking down keys.
    Examples:
        column="hoofdsoort", operator="=", value="Agressie tegen medewerker"
        column="ind_agressie", operator="=", value="1"
        column="abc_categorie", operator="IN", value="A,B"
    """
    column: str = Field(
        description="The target table column name to filter on (e.g., 'hoofdsoort', 'ind_letsel', 'abc_categorie')."
    )
    operator: str = Field(
        description="The comparison operator for the clause constraint (e.g., '=', 'IN', 'LIKE', '>', '<')."
    )
    value: str = Field(
        description="The value payload for the restriction predicate. Separate multiple options using commas for 'IN' operators."
    )


class LocationSpecs(BaseModel):
    """
    Captures polymorphic location and spatial filters present in the network dimensions.
    This structure isolates geographical entities to streamline complex join evaluations.
    """
    stations: List[str] = Field(
        default_factory=list,
        description=(
            "Exact station names or system codes mapping to dimdienstregelpunt indicators. "
            "Applies to 'dienstregelpunt_naam' (e.g., 'Utrecht Centraal') or 'dienstregelpunt_code' (e.g., 'Ut')."
        )
    )
    train_numbers: List[str] = Field(
        default_factory=list,
        description="Identifies single unique train runs using dimtreinnummer_treinserie.treinnummer strings (e.g., ['3742'])."
    )
    train_series: List[str] = Field(
        default_factory=list,
        description="Identifies entire operational route frameworks via dimtreinnummer_treinserie.treinserie strings (e.g., ['2400'])."
    )
    regions: List[str] = Field(
        default_factory=list,
        description=(
            "Generic bucket for geographic zones. Covers RSV regions ('regio_rsv_naam' like 'Noord-Oost') "
            "or SSVO regions ('regio_ssvo_naam' like 'PE Noord')."
        )
    )
    location_types: List[str] = Field(
        default_factory=list,
        description="Limits context boundaries using dimlocatietype.locatietype descriptor strings (e.g., ['Station', 'Trein'])."
    )


class DateRange(BaseModel):
    """
    Explicit date range for querying incident data.
    Both dates are required before SQL handoff.
    """
    from_date: date | None = Field(
        default=None,
        description="The starting calendar boundary window date (YYYY-MM-DD format)."
    )
    to_date: date | None = Field(
        default=None,
        description="The ending calendar boundary window date (YYYY-MM-DD format)."
    )


class QuerySpecs(BaseModel):
    """
    The formal structural query contract generated during the conversation phase.
    This object acts as a generic configuration mapping entirely to the Star Schema metrics layout.
    """
    fact_table: str = Field(
        default="factincidentmkns",
        description="The core transactional target fact volume tracking log events."
    )
    dimension_tables: List[str] = Field(
        default_factory=list,
        description="A dynamic collection of secondary descriptive tables needing join predicates for property constraints."
    )
    from_date: date | None = Field(
        default=None,
        description="The formal, validated starting calendar boundary window date object (YYYY-MM-DD format). Use the RefinementResponse.date_range as the authoritative source."
    )
    to_date: date | None = Field(
        default=None,
        description="The formal, validated ending calendar boundary window date object (YYYY-MM-DD format). Use the RefinementResponse.date_range as the authoritative source."
    )
    time_blocks: List[str] = Field(
        default_factory=list,
        description="Captures specific hour intervals, shift descriptions, or peak tracking attributes from dimtijd (e.g., ['Dag', '14:00-15:00'])."
    )
    location_context: LocationSpecs = Field(
        default_factory=LocationSpecs,
        description="Polymorphic network spatial boundary definitions isolating execution metrics regions."
    )
    categorical_filters: List[QueryFilter] = Field(
        default_factory=list,
        description="Dynamic properties collection tracking indicators, severity levels, types, or reporting classes."
    )


class RefinementResponse(BaseModel):
    """
    The refinement stage output used by main.py to decide whether to keep
    asking clarifying questions or hand off to the SQL agent.
    """

    ready_for_sql: bool = Field(
        description="True only when date_range is complete AND refined question and specs are sufficient for SQL execution."
    )
    clarification_question: str | None = Field(
        default=None,
        description="Single follow-up question shown to the user when more detail is needed."
    )
    refined_question: str = Field(
        description="Canonical question text that the SQL agent should execute."
    )
    date_range: DateRange | None = Field(
        description="Explicit required date range. Must be filled before ready_for_sql=true."
    )
    query_specs: QuerySpecs = Field(
        description="Best-known structured specification collected during refinement."
    )


class RAGResponse(BaseModel):
    """
    The absolute structured model payload returned to the runner layers.
    It links natural descriptions to code signatures and metric audit logs to maintain data integrity.
    """
    answer: str = Field(
        description="The natural language answer text explaining the target metrics. Must note clearly if row tracking shows 0 instances."
    )
    query_executed_successfully: bool = Field(
        description="True if the database successfully parsed, checked, and completed execution processing without any errors."
    )
    row_count: int = Field(
        description="The volume magnitude tracking measurement defining exactly how many database rows were pulled by execution."
    )
    query_specs: QuerySpecs = Field(
        description="The snapshot configuration model specifying how the dynamic constraints were filled."
    )
    sql_query: str = Field(
        description="The verified, safe, executable SQL text generated to compute database metrics values."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="An objective certainty factor tracking code precision vs user intent alignment (0.0 to 1.0)."
    )
    confidence_explanation: str = Field(
        description="A textual assessment outlining why the confidence rating was given based on matching schema rules."
    )
    followup_questions: List[str] = Field(
        description="2-3 highly distinct analytical follow-up questions completely answerable by checking the metadata structure."
    )