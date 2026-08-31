"""
Empirical Parameter Extractor Module
Extracts structured econometric and economic simulation parameters from agricultural economics papers using Gemini.
"""
import os
import json
import re
from db import get_connection, add_empirical_parameter, get_paper_by_id


def extract_parameters_from_text(text: str, title: str = "", api_key: str = None) -> list[dict]:
    """
    Extract structured empirical parameters from research paper text or abstract using Gemini.
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("A Gemini API Key is required for parameter extraction.")

    import google.generativeai as genai
    genai.configure(api_key=api_key)

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
    except Exception:
        model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""You are an agricultural economics research assistant specializing in econometric parameter calibration for the Ontario Federation of Agriculture (OFA).

Extract all quantitative empirical parameters reported in the following paper text (e.g. elasticities, pass-through rates, Input-Output multipliers, WTP estimates, price transmission elasticities, risk/financial thresholds).

PAPER TITLE: {title}
PAPER TEXT:
{text[:4000]}

Return a strict JSON array of objects. If no numerical parameters are reported in the text, return an empty array [].
Each object must follow this exact schema:
[
  {{
    "commodity": "Canola | Wheat | Cattle | Hogs | Dairy | Poultry | Primary Ag | Food Manufacturing | Local Food | General Ag",
    "parameter_type": "Tariff Pass-Through | Supply Elasticity | Demand Elasticity | IO Output Multiplier | IO Employment Multiplier | Price Transmission | DSCR Threshold | Willingness to Pay",
    "point_estimate": 0.85,
    "unit": "elasticity | multiplier | ratio | percentage | CAD/tonne | USD/cwt",
    "stat_lower": 0.75,
    "stat_upper": 0.95,
    "standard_error": 0.05,
    "time_horizon": "Short-run (1 yr) | Medium-run (3 yr) | Long-run (5+ yr)",
    "geography": "Ontario | Canada | US | North America | OECD | Global",
    "sample_period": "e.g. 2000-2024",
    "model_type": "Econometric / Time Series | Gravity Model | Input-Output | CGE | Translog System | Spatial Price Equilibrium",
    "notes": "Brief empirical explanation of identification strategy, methodology, or context."
  }}
]

Respond with ONLY the JSON array (enclosed in ```json ... ``` or plain JSON). Do not include extraneous commentary.
"""

    response = model.generate_content(prompt)
    raw_text = response.text.strip()

    # Extract JSON content
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw_text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = raw_text

    try:
        params_list = json.loads(json_str)
        if isinstance(params_list, list):
            return params_list
        return []
    except Exception as e:
        print(f"[EXTRACT] Failed to parse JSON: {e}\nRaw: {raw_text[:300]}")
        return []


def extract_and_save_paper_parameters(paper_id: int, project_id: int = None, api_key: str = None) -> list[int]:
    """Extract parameters from a paper stored in SQLite and save them directly to empirical_parameters."""
    conn = get_connection()
    paper = get_paper_by_id(conn, paper_id)
    if not paper:
        conn.close()
        raise ValueError(f"Paper ID {paper_id} not found.")

    text_to_scan = paper.get("full_text") or paper.get("abstract") or ""
    if not text_to_scan:
        conn.close()
        return []

    extracted = extract_parameters_from_text(text_to_scan, title=paper.get("title", ""), api_key=api_key)

    saved_ids = []
    for item in extracted:
        try:
            param_id = add_empirical_parameter(
                conn,
                commodity=item.get("commodity", "General Ag"),
                parameter_type=item.get("parameter_type", "Elasticity"),
                point_estimate=float(item.get("point_estimate", 0.0)),
                paper_id=paper_id,
                project_id=project_id,
                unit=item.get("unit", "elasticity"),
                stat_lower=float(item["stat_lower"]) if item.get("stat_lower") is not None else None,
                stat_upper=float(item["stat_upper"]) if item.get("stat_upper") is not None else None,
                standard_error=float(item["standard_error"]) if item.get("standard_error") is not None else None,
                time_horizon=item.get("time_horizon", "Short-run (1 yr)"),
                geography=item.get("geography", "Canada"),
                sample_period=item.get("sample_period"),
                model_type=item.get("model_type", "Econometric"),
                notes=item.get("notes", "")
            )
            saved_ids.append(param_id)
        except Exception as err:
            print(f"[EXTRACT] Error inserting parameter: {err}")

    conn.close()
    return saved_ids
