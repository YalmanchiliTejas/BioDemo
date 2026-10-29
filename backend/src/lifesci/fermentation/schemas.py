from pydantic import Field
from ..process_engineering.schemas import StrictModel

class Assumptions(StrictModel):
    # Every default here is a scenario assumption, not an extracted measurement.
    gas_exponent: float = Field(default=.5, ge=0, le=1)
    power_screen_w_m3: float = Field(default=1000, ge=50, le=10000)
    selected_receiver_l: int = Field(default=20)
    rpm: float = Field(default=300, ge=20, le=1000)
    airflow_vvm: float = Field(default=.25, ge=.05, le=1)
    pressure_gauge_kpa: float = Field(default=100, ge=50, le=150)
    ambient_kpa: float = Field(default=101.325, ge=80, le=110)
    air_nm3_h: float = Field(default=36, ge=.1, le=1000)
    oxygen_nm3_h: float = Field(default=2, ge=0, le=100)
    compressor_efficiency: float = Field(default=.65, ge=.2, le=1)
    compressor_inlet_temperature_k: float = Field(default=303.15, ge=273.15, le=330)
    electricity_usd_kwh: float = Field(default=.12, ge=0, le=5)
    oxygen_usd_nm3: float = Field(default=.2, ge=0, le=10)
    comparison_hours: float = Field(default=120, ge=1, le=1000)
    # Common isothermal gas reference at ambient pressure. Not an inferred flow basis in the paper.
    air_saturation_mg_l: float = Field(default=7.5, gt=0, le=20)
    broth_solubility_factor: float = Field(default=.7, gt=0, le=1)
    kla_h_inv: float = Field(default=20, gt=0, le=1000)
    dissolved_oxygen_mg_l: float = Field(default=1.5, ge=0, le=30)
    our_mg_l_h: float = Field(default=50, gt=0, le=10000)
    extra_methanol_l: float | None = Field(default=None, ge=0, le=100000)
    methanol_usd_l: float = Field(default=.5, ge=0, le=100)

class EvaluateIn(StrictModel):
    site_id: str = Field(default='NF1', min_length=1, max_length=100)
    assumptions: Assumptions = Field(default_factory=Assumptions)

class ReviewIn(StrictModel):
    owner_id: str = Field(default='priya', min_length=1, max_length=100)
