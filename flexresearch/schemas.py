"""Typed contracts shared by the Agent and deterministic lab tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProvenanceRef(StrictModel):
    experiment_id: int | None = None
    source_file: str
    source_sha256: str | None = None
    timestamp: str
    channel: str | None = None
    processing_method: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    tool_run_id: str


class ColumnStats(StrictModel):
    count: int
    mean: float | None = None
    std: float | None = None
    minimum: float | None = None
    maximum: float | None = None


class ColumnQuality(StrictModel):
    total_points: int
    valid_points: int
    nan_count: int
    inf_count: int
    finite_fraction: float = Field(ge=0, le=1)


class LoadCSVInput(StrictModel):
    file_path: str
    max_rows: int = Field(default=200_000, ge=1, le=1_000_000)


class LoadCSVOutput(StrictModel):
    shape: tuple[int, int]
    columns: list[str]
    numeric_columns: list[str]
    missing_counts: dict[str, int]
    basic_stats: dict[str, ColumnStats]
    data_quality: dict[str, ColumnQuality]
    cleaning_policy: str
    data: dict[str, list[float | int | str | None]]
    truncated: bool
    source_file: str
    source_sha256: str


class FilterSignalInput(StrictModel):
    signal: list[float] = Field(min_length=8)
    sample_rate: float = Field(gt=0)
    low_cut: float | None = Field(default=None, gt=0)
    high_cut: float | None = Field(default=None, gt=0)
    order: int = Field(default=4, ge=1, le=10)

    @model_validator(mode="after")
    def validate_band(self) -> "FilterSignalInput":
        if self.low_cut is None and self.high_cut is None:
            raise ValueError("low_cut or high_cut is required")
        if self.low_cut is not None and self.high_cut is not None and self.low_cut >= self.high_cut:
            raise ValueError("low_cut must be smaller than high_cut")
        nyquist = self.sample_rate / 2
        if self.high_cut is not None and self.high_cut >= nyquist:
            raise ValueError("high_cut must be below Nyquist frequency")
        if self.low_cut is not None and self.low_cut >= nyquist:
            raise ValueError("low_cut must be below Nyquist frequency")
        return self


class FilterSignalOutput(StrictModel):
    filtered_signal: list[float]
    parameters: dict[str, float | int | str | None]
    point_count: int


class SpectralAnalysisInput(StrictModel):
    signal: list[float] = Field(min_length=8)
    sample_rate: float = Field(gt=0)
    max_peaks: int = Field(default=3, ge=1, le=10)
    min_frequency: float = Field(default=0.1, ge=0)
    max_frequency: float | None = Field(default=None, gt=0)
    estimate_pulse_rate: bool = False


class SpectralPeak(StrictModel):
    frequency_hz: float
    amplitude: float


class SpectralAnalysisOutput(StrictModel):
    peaks: list[SpectralPeak]
    dominant_frequency_hz: float | None
    frequency_resolution_hz: float
    sample_rate: float
    point_count: int
    algorithm_version: Literal["fft-mean-removal-v1"] = "fft-mean-removal-v1"
    pulse_rate_bpm: float | None = Field(default=None, gt=0)
    pulse_rate_method: Literal["dominant-frequency-hz-times-60-v1"] | None = None


class BioZFeaturesInput(StrictModel):
    frequency_hz: list[float] = Field(min_length=2)
    real_ohm: list[float] = Field(min_length=2)
    imaginary_ohm: list[float] = Field(min_length=2)
    channel: str | None = None

    @model_validator(mode="after")
    def validate_lengths(self) -> "BioZFeaturesInput":
        if len({len(self.frequency_hz), len(self.real_ohm), len(self.imaginary_ohm)}) != 1:
            raise ValueError("frequency, real and imaginary arrays must have equal length")
        return self


class BioZFeaturesOutput(StrictModel):
    frequency_hz: list[float]
    magnitude_ohm: list[float]
    phase_deg: list[float]
    magnitude_mean_ohm: float
    magnitude_std_ohm: float
    phase_mean_deg: float
    frequency_min_hz: float
    frequency_max_hz: float
    point_count: int
    channel: str | None = None
    quality_metrics: dict[str, float | int | str]


class PlotSignalInput(StrictModel):
    x: list[float] = Field(min_length=2)
    y: list[float] = Field(min_length=2)
    output_dir: str
    title: str = "Signal"
    x_label: str = "x"
    y_label: str = "y"
    filename_prefix: str = "signal"
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_lengths(self) -> "PlotSignalInput":
        if len(self.x) != len(self.y):
            raise ValueError("x and y must have equal length")
        return self


class PlotSignalOutput(StrictModel):
    plot_path: str
    metadata: dict[str, str | int]


class ExportSignalInput(StrictModel):
    x: list[float] = Field(min_length=2)
    signal: list[float] = Field(min_length=2)
    axis_name: Literal["time_s", "sample_index"]
    source_file: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_dir: str
    channel: str
    experiment_id: int | None = None
    input_tool_run_id: str = Field(min_length=1)
    processing_parameters: dict[str, Any]

    @model_validator(mode="after")
    def aligned_arrays(self):
        if len(self.x) != len(self.signal):
            raise ValueError("axis and signal must have equal length")
        return self


class ExportSignalOutput(StrictModel):
    file_path: str
    metadata: dict[str, Any]


class CompareExperimentsInput(StrictModel):
    baseline: list[float] = Field(min_length=2)
    comparison: list[float] = Field(min_length=2)
    metric_name: str = "signal"

    @model_validator(mode="after")
    def validate_lengths(self) -> "CompareExperimentsInput":
        if len(self.baseline) != len(self.comparison):
            raise ValueError("baseline and comparison must have equal length")
        return self


class CompareExperimentsOutput(StrictModel):
    point_count: int
    mean_baseline: float
    mean_comparison: float
    mean_delta: float
    relative_change_percent: float | None
    rmse: float
    correlation: float | None
    metric_name: str


class SearchKnowledgeBaseInput(StrictModel):
    query: str = Field(min_length=2, max_length=1200)
    limit: int = Field(default=6, ge=1, le=20)


class KnowledgeChunk(StrictModel):
    citation: str
    document_id: int
    chunk_index: int
    title: str
    locator: str
    excerpt: str
    retrieval_mode: str
    vector_score: float
    lexical_rank: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchKnowledgeBaseOutput(StrictModel):
    items: list[KnowledgeChunk]
    query: str
    embedding_model: str
    private_data_sent_externally: bool = False


class SearchExperimentInput(StrictModel):
    experiment_id: int | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, min_length=1, max_length=160)
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def require_lookup_key(self) -> "SearchExperimentInput":
        if self.experiment_id is None and not (self.query or "").strip():
            raise ValueError("experiment_id or query is required")
        return self


class ExperimentSummary(StrictModel):
    experiment_id: int
    project_id: int | None = None
    project_name: str | None = None
    name: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: str | None = None


class SearchExperimentOutput(StrictModel):
    items: list[ExperimentSummary]
    requested_experiment_id: int | None = None
    query: str | None = None


class LoadExperimentDataInput(StrictModel):
    experiment_id: int = Field(gt=0)


class ExperimentFileSummary(StrictModel):
    file_id: int
    measurement_id: int | None = None
    document_id: int | None = None
    source_file: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    file_type: str
    immutable: bool
    available: bool
    shape: tuple[int, int] | None = None
    columns: list[str] = Field(default_factory=list)
    basic_stats: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    measurement_type: str | None = None
    stored_metrics: list[dict[str, Any]] = Field(default_factory=list)


class LoadExperimentDataOutput(StrictModel):
    experiment: ExperimentSummary
    files: list[ExperimentFileSummary]
    raw_data_modified: bool = False


ToolStatus = Literal["complete", "error", "timeout"]

