"""Versioned source reconstruction. Every numeric input has explicit provenance."""
from copy import deepcopy

from .model import PAPER

INPUT_REVISION = "vanbillemont-reconstruction-1"


def source_config() -> dict:
    return {
        "input_revision": INPUT_REVISION,
        "product": {"id": "paper-BSA-sucrose-Tris-PS20", "fill_m3": 2.5e-6,
                    "inner_diameter_m": .020, "outer_diameter_m": .022, "porosity": .897,
                    "critical_temperature_c": -28., "rp0_m_s": 7000., "rp1_per_s": 2.77e8, "rp2_per_m": 451.},
        "equipment": {"site_id": "sending-pilot", "equipment_id": "Epsilon2-10D-reconstruction", "revision": "1",
                      "kv_a_w_m2_k": 2.57, "kv_b_w_m2_k_pa": 2.33, "kv_c_per_pa": .03, "kv_rsd": .151,
                      "max_vials": 1028, "shelf_area_m2": .56,
                      "vapor_capacity_kg_h": .33, "condenser_capacity_kg": 10.,
                      "utility_connections": [{"from": "thermal-fluid", "to": "shelves", "characterization": "Kv(P)"},
                                              {"from": "chamber", "to": "condenser", "capacity_key": "vapor_capacity_kg_h"}],
                      "missing_parameters": ["resolved condenser deposition-rate specification", "pressure-dependent vapor-capacity curve", "shared utility headroom"]},
        "load_vials": 1028, "duration_h": 75., "initial_dried_fraction": 0., "schedule_mode": "step",
        "schedule": [{"time_h": 0., "shelf_temperature_c": -24., "chamber_pressure_pa": 8.}],
    }


def receiving_config(*, shelf_c: float = -24., load_vials: int = 11000, capacity_kg_h: float = .65) -> dict:
    c = deepcopy(source_config())
    c["equipment"].update(site_id="receiving-reconstructed", equipment_id="Epsilon2-65D-derated-demonstration",
                          kv_a_w_m2_k=8.83, kv_b_w_m2_k_pa=.60, kv_c_per_pa=0., kv_rsd=.110,
                          max_vials=11000, shelf_area_m2=5.40, vapor_capacity_kg_h=capacity_kg_h, condenser_capacity_kg=30.)
    c["schedule"][0]["shelf_temperature_c"] = shelf_c
    c["load_vials"] = load_vials
    return c


def manifest(config: dict) -> list[dict]:
    """Units and extraction locations for EVERY scalar model input, including constants."""
    published = {
        "fill_m3": ("m³", "CMAs variability; 2.50 mL × 1e-6"),
        "inner_diameter_m": ("m", "Abbreviations / CMAs variability; 20 mm × 1e-3"),
        "outer_diameter_m": ("m", "Abbreviations / CMAs variability; 22 mm × 1e-3"),
        "porosity": ("1", "Materials"), "critical_temperature_c": ("°C", "Constraints estimations; formulation-specific"),
        "rp0_m_s": ("m/s", "Optimal cycle; Eq. 11 A"), "rp1_per_s": ("1/s", "Optimal cycle; Eq. 11 B"),
        "rp2_per_m": ("1/m", "Optimal cycle; Eq. 11 C"),
        "kv_a_w_m2_k": ("W/(m² K)", "CMAs variability; Eq. 9 A"),
        "kv_b_w_m2_k_pa": ("W/(m² K Pa)", "CMAs variability; Eq. 9 B"),
        "kv_c_per_pa": ("1/Pa", "CMAs variability; Eq. 9 C"), "kv_rsd": ("1", "CMAs variability RSD"),
        "max_vials": ("vial", "Table 2 maximum load"), "shelf_area_m2": ("m²", "Table 2"),
    }
    rows = []
    if config["equipment"]["site_id"] == "sending-pilot":
        published["vapor_capacity_kg_h"] = ("kg/h", "Constraints estimations; manufacturer deposition ceiling. Disputed pilot choked-flow slope is not used.")
    for block in ("product", "equipment"):
        for key, value in config[block].items():
            if isinstance(value, (float, int)):
                unit, loc = published.get(key, ("kg/h" if key == "vapor_capacity_kg_h" else "kg" if key == "condenser_capacity_kg" else "1", "Demonstration assumption; not characterized equipment"))
                rows.append({"parameter": f"{block}.{key}", "value": value, "unit": unit,
                             "category": "published" if key in published else "synthetic_assumption",
                             "source": PAPER if key in published else "BioDemo reconstruction", "location_or_transformation": loc})
    rows.extend([
        {"parameter": "rho_ice", "value": 918., "unit": "kg/m³", "category": "published", "source": PAPER, "location_or_transformation": "Abbreviations"},
        {"parameter": "rho_water", "value": 1000., "unit": "kg/m³", "category": "published", "source": PAPER, "location_or_transformation": "Abbreviations"},
        {"parameter": "H_sub", "value": 2.84e6, "unit": "J/kg", "category": "synthetic_assumption", "source": "constant approximation", "location_or_transformation": "replaces paper temperature-dependent Eq. 4"},
        {"parameter": "k_ice", "value": 2.4, "unit": "W/(m K)", "category": "synthetic_assumption", "source": "constant approximation", "location_or_transformation": "Fourier conduction replaces paper Eq. 3"},
    ])
    for key, unit in [("load_vials", "vial"), ("duration_h", "h"), ("initial_dried_fraction", "1")]:
        rows.append({"parameter": key, "value": config[key], "unit": unit, "category": "synthetic_assumption", "source": "BioDemo scenario", "location_or_transformation": "explicit scenario boundary"})
    for i, s in enumerate(config["schedule"]):
        for key, value in s.items():
            rows.append({"parameter": f"schedule[{i}].{key}", "value": value,
                         "unit": {"time_h": "h", "shelf_temperature_c": "°C", "chamber_pressure_pa": "Pa"}[key],
                         "category": "synthetic_assumption", "source": "BioDemo scenario", "location_or_transformation": "source starting setpoints from published pilot -24°C/8 Pa; changes reconstructed"})
    return rows
