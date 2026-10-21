from flask import Blueprint, jsonify

from .. import auth
from ._util import body, fail, fnum

bp = Blueprint("business", __name__, url_prefix="/api/business")

# Device cost ranges (INR) copied from the pitch deck's solution-stack tables.
COSTS = {"accelerometer": (500, 15000), "strain": (500, 2000), "lvdt": (5000, 30000), "temperature": (200, 2000),
         "moisture": (200, 1000), "edge": (300, 1500), "cctv": (3000, 15000), "piezo": (50, 200), "wim": (500000, 2000000),
         "drone": (40000, 150000)}
KITS = {
    "basic": {"label": "Basic kit", "items": {"accelerometer": 2, "strain": 2, "temperature": 1, "moisture": 1, "edge": 1, "cctv": 1}},
    "standard": {"label": "Standard bridge kit", "items": {"accelerometer": 2, "strain": 3, "lvdt": 1, "temperature": 1, "moisture": 2, "edge": 1, "cctv": 1, "piezo": 2}},
    "extended": {"label": "Extended kit with WIM", "items": {"accelerometer": 3, "strain": 4, "lvdt": 2, "temperature": 1, "moisture": 3, "edge": 1, "cctv": 2, "piezo": 2, "wim": 1}},
}
BENCH = {"bhm_installed_low": 1500000, "bhm_installed_high": 3500000, "ndt_campaign_low": 500000, "ndt_campaign_high": 2000000}
DISCOUNTS = [(1, 0.0), (6, 0.10), (26, 0.20), (101, 0.30)]


@bp.get("/benchmarks")
@auth.require("viewer")
def benchmarks():
    return jsonify({
        "rows": [
            {"name": "Bihar State Bridge Management & Maintenance Policy 2025", "approach": "AI + drone inspection every 90 days",
             "notes": "Live Bridge Health Index with public ratings; 98.5% AI detection accuracy is the policy's own claim; IIT Delhi / IIT Patna partnership.",
             "kind": "Government benchmark", "check": "Verified in the team's dossier"},
            {"name": "Traditional BHM vendors (GEOKON, Campbell Scientific, HBK, Acellent)", "approach": "Wired sensor-based monitoring",
             "notes": "Full systems of 20-30 channels run about Rs 15-35 lakh installed; long-span systems exceed Rs 1 crore.", "kind": "Commercial incumbents",
             "check": "Cost range from the team's dossier"},
            {"name": "StructuraSense (proposed)", "approach": "Low-cost multimodal fusion with an engineer in the loop",
             "notes": "Piezo + vision + AI; targets mid-tier assets that cannot justify enterprise systems.", "kind": "This project", "check": "Prototype stage"},
        ],
        "positioning": "Low-cost multimodal niche against enterprise-only incumbents."})


@bp.get("/claims")
@auth.require("viewer")
def claims():
    return jsonify([
        {"claim": "Indian Railways has 1,63,810 bridges (1 April 2024)", "status": "verified", "basis": "Rajya Sabha reply of 4 April 2025, as checked in the team's dossier."},
        {"claim": "Railways inspect twice a year: before and after the monsoon", "status": "verified", "basis": "Same Rajya Sabha reply, per the dossier."},
        {"claim": "Bihar's 2025 policy requires AI + drone inspections every 90 days", "status": "verified", "basis": "Cited as real and current in the dossier. The 98.5% accuracy is the policy's claim, not ours."},
        {"claim": "MoRTH / IBMS: 1,72,517 structures (38,288 bridges + 1,34,229 culverts)", "status": "unverified", "basis": "The dossier could not find this exact figure. Use the 2017 sourced figure or add a caveat."},
        {"claim": "India SHM market of USD 150-200 million", "status": "unverified", "basis": "No India-specific source found. Use the global figure (about USD 2.4-5.7 billion, 2024-25, 10-20% CAGR) as global context only."},
        {"claim": "Inspection cost cut 60-70%, maintenance cost cut 30-50%, implementation 0.2-0.5% of structure value", "status": "hypothesis", "basis": "Target hypotheses pending a 3-structure field pilot. Do not present as facts."},
        {"claim": "Health bands 80 / 60 / 40", "status": "hypothesis", "basis": "The team's own proposed thresholds, to be calibrated against structure-specific baselines."},
        {"claim": ">=90% crack-detection precision and <10% false alarms", "status": "target", "basis": "Targets, not results. Our synthetic self-test passes them but says nothing about real concrete."},
        {"claim": "Piezo sensing detects micro-cracks like acoustic-emission systems", "status": "caution", "basis": "Proof of concept only. PZT sensing here is not equivalent to professional acoustic-emission equipment."},
        {"claim": "RF coil and tuning-fork sensing", "status": "future", "basis": "Experimental research modules, not features."},
        {"claim": "BridgePulse and Sanrachna Prahari as named competitors", "status": "removed", "basis": "Neither could be verified as real. Dropped from the benchmark."},
    ])


@bp.post("/imaas-quote")
@auth.require("viewer")
def quote():
    d = body()
    try:
        n = int(fnum(d.get("structures"), "Structures", 1, 1000, required=True))
        years = int(fnum(d.get("years"), "Contract years", 1, 15, default=5))
        base_fee = fnum(d.get("base_fee_inr"), "Base fee", 0, 1e7, default=40000)
        per_sensor = fnum(d.get("per_sensor_fee_inr"), "Per-sensor fee", 0, 1e6, default=3000)
        install_pct = fnum(d.get("install_pct"), "Installation %", 0, 200, default=20)
    except ValueError as e:
        return fail("invalid", str(e))
    kit = KITS.get(d.get("kit", "standard"))
    if not kit:
        return fail("invalid_kit", "Kit must be basic, standard or extended.")
    lo = sum(COSTS[k][0] * c for k, c in kit["items"].items())
    hi = sum(COSTS[k][1] * c for k, c in kit["items"].items())
    sensors = sum(c for k, c in kit["items"].items() if k not in ("edge", "cctv", "drone"))
    disc = max(p for lim, p in DISCOUNTS if n >= lim)
    fee = (base_fee + per_sensor * sensors) * (1 - disc)
    inst_lo, inst_hi = lo * install_pct / 100, hi * install_pct / 100
    capex_lo, capex_hi = lo + inst_lo, hi + inst_hi
    tco_lo, tco_hi = capex_lo + fee * years, capex_hi + fee * years
    return jsonify({
        "kit": kit["label"], "items": kit["items"], "sensors": sensors, "volume_discount": disc,
        "per_structure": {"hardware_low": lo, "hardware_high": hi, "install_low": inst_lo, "install_high": inst_hi,
                          "capex_low": capex_lo, "capex_high": capex_hi, "annual_service_fee": fee,
                          "tco_low": tco_lo, "tco_high": tco_hi, "years": years},
        "portfolio": {"structures": n, "capex_low": capex_lo * n, "capex_high": capex_hi * n, "annual_revenue": fee * n,
                      "tco_low": tco_lo * n, "tco_high": tco_hi * n},
        "reference": {"bhm_installed_low": BENCH["bhm_installed_low"], "bhm_installed_high": BENCH["bhm_installed_high"],
                      "note": "Commercial BHM systems of 20-30 channels cost about Rs 15-35 lakh installed (team dossier). Their running costs are not included."},
        "disclaimer": "Hardware ranges come from the pitch deck's device tables. Installation %, service fees and volume discounts are ILLUSTRATIVE assumptions to edit, not validated pricing. Savings claims remain hypotheses until the field pilot."})
