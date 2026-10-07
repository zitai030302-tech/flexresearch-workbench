"""Validated experiment-id analysis and session state contracts."""

from pydantic import Field, field_validator, model_validator

from .agent import LabAgentResult
from .analysis_parameters import AnalysisParameters, FilterParameters
from .analysis_context import AnalysisContext
from .schemas import StrictModel


class AnalyzeExperimentInput(StrictModel):
    experiment_id: int = Field(gt=0)
    file_id: int | None = Field(default=None, gt=0)
    channel: str | None = Field(default=None, min_length=1, max_length=80)
    sample_rate: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    question: str = Field(default="读取并概览这个 CSV", min_length=1, max_length=1200)
    analysis_parameters: AnalysisParameters = Field(default_factory=AnalysisParameters)
    analysis_context: AnalysisContext = Field(default_factory=AnalysisContext)

    @field_validator("channel", mode="before", json_schema_input_type=str | int | None)
    @classmethod
    def normalize_channel_id(cls, value):
        # Providers commonly send JSON 4 for a channel ID; this is lossless,
        # unlike coercing floats, booleans, or invented acquisition parameters.
        if type(value) is int and value >= 0:
            return str(value)
        return value


class AnalyzeExperimentOutput(StrictModel):
    experiment_id: int
    file_id: int
    measurement_id: int
    result: LabAgentResult


class PendingSignalRequest(StrictModel):
    query: str = Field(min_length=1, max_length=1200)
    source_run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    experiment_id: int = Field(gt=0)
    file_id: int = Field(gt=0)
    filter: FilterParameters | None = None


class ExperimentSessionState(StrictModel):
    experiment_id: int = Field(gt=0)
    file_id: int | None = None
    channel: str | None = None
    sample_rate: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    last_analysis_run_id: str | None = None
    analysis_parameters: AnalysisParameters = Field(default_factory=AnalysisParameters)
    analysis_context: AnalysisContext = Field(default_factory=AnalysisContext)
    pending_request: PendingSignalRequest | None = None

    @model_validator(mode="after")
    def pending_scope_matches_selection(self):
        if self.pending_request and (self.pending_request.experiment_id != self.experiment_id or self.pending_request.file_id != self.file_id):
            raise ValueError("Pending request must belong to the selected experiment file")
        return self

