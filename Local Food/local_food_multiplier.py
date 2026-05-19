"""
StatCan Local Food Multiplier Engine
=====================================
Analysis-by-Parts (ABP) I-O pipeline for Direct-to-Consumer local food in Ontario.

Methodology:
  1. Custom DTC farm production function (Purchaser Prices)
  2. Margin deflation to Basic Prices (StatCan SUT architecture)
  3. Regional Purchase Coefficient (RPC) application
  4. Gross impact via sector-specific Simple multipliers
  5. Swenson net-impact counterfactual (import substitution)

Expert corrections applied:
  - Bottom-up vector shocks (no scalar adjustment to post-inversion multipliers)
  - Purchaser → Basic Price margin stripping
  - Simple multipliers only (Induced effects modeled manually)

Author: OFA Economic Analyst
Date: March 2026
"""

import pandas as pd
import numpy as np
from collections import OrderedDict


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 1: DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

def build_statcan_multipliers():
    """
    Mock StatCan Table 36-10-0595-01 — Ontario Provincial Simple Multipliers.
    
    These are "Simple" = Direct + Indirect ONLY (no Induced).
    Real values should be sourced from StatCan Table 36-10-0595-01.
    
    CORRECTION #6 (Round 2): StatCan publishes at S/L aggregation level.
    Check if L-level IOIC codes are granular enough. If BS1112 (Vegetable
    and melon farming) is not available separately, may need to submit a
    custom data request for W-level (suppressed) tables ($500-2000).
    
    Columns: Output ($ per $1 shock), GDP ($), Employment (jobs per $1M shock)
    """
    data = {
        "IOIC_Code": [
            "BS111",     # Crop production
            "BS112",     # Animal production  
            "BS311",     # Food manufacturing
            "BS4A0",     # Retail trade
            "BS4100",    # Wholesale trade
            "BS484",     # Truck transportation
            "BS3222",    # Paper/packaging manufacturing
            "BS3241",    # Petroleum & coal products
            "BS5400",    # Professional/scientific services
            "BS814",     # Private households (domestic services)
            "HH_CONS",   # Household final consumption (for Induced)
        ],
        "Sector": [
            "Crop Production",
            "Animal Production",
            "Food Manufacturing",
            "Retail Trade",
            "Wholesale Trade",
            "Truck Transportation",
            "Paper/Packaging Mfg",
            "Petroleum Products",
            "Professional Services",
            "Private Households",
            "Household Consumption",
        ],
        # Simple multipliers (Direct + Indirect only)
        "Output_Mult": [1.82, 2.15, 2.45, 1.55, 1.60, 1.75, 2.10, 1.45, 1.65, 1.10, 1.50],
        "GDP_Mult":    [0.45, 0.40, 0.35, 0.62, 0.55, 0.50, 0.42, 0.18, 0.70, 0.85, 0.52],
        "Jobs_per_M":  [8.5,  7.2,  6.8,  12.5, 7.0,  8.0,  5.5,  1.8,  9.5,  15.0, 7.8],
    }
    return pd.DataFrame(data).set_index("IOIC_Code")


def build_local_farm_budget():
    """
    How a local DTC farm spends $1.00 of revenue (PURCHASER PRICES).
    
    This is the custom "A-vector" — the production function for a direct-to-consumer
    farm that sells at farmers' markets, CSAs, or farm stands.
    
    Key differences vs. conventional: higher labor share, lower chemical inputs,
    farmer captures retail margin (no wholesale/retail leakage).
    
    TODO: Replace with real data from OMAFRA enterprise budgets + OFA member surveys.
    
    CORRECTION #4 (Round 2): When ingesting OMAFRA enterprise budgets:
      - STRIP Depreciation (non-cash) before converting to fractions
      - RECLASSIFY Imputed Operator Labor as Proprietor Income
      - I-O models require actual cash flow data only
    
    CORRECTION #8 (Round 2): OFA survey should ask expenditure PERCENTAGES,
    not absolute dollar amounts, for higher response rates and direct
    compatibility with this $1.00 vector format.
    """
    return OrderedDict([
        # ── Value Added (stays with farm household) ─────────────────
        ("hired_labor",       0.30),   # Higher than conventional (~15-20%)
        ("proprietor_income", 0.20),   # Farmer's return — captures retail margin
        
        # ── Physical inputs (need margin deflation) ─────────────────
        ("packaging",         0.08),   # Boxes, bags, labels — manufactured good
        ("fuel_energy",       0.05),   # Diesel, electricity — petroleum product
        ("ag_inputs_seed",    0.15),   # Seed, fertilizer, pest control — ag input
        
        # ── Services (no margin deflation needed) ───────────────────
        ("marketing_services", 0.10),  # Market stall fees, advertising, accounting
        
        # ── Fixed costs ─────────────────────────────────────────────
        ("taxes_land",        0.12),   # Property taxes, land costs, insurance
    ])


def build_margin_profiles():
    """
    Purchaser Price → Basic Price conversion profiles.
    
    When a farmer pays $100 for packaging at a store, the $100 breaks down:
      - $20 goes to the retail sector (retail margin)
      - $10 goes to the wholesale sector (wholesale margin)
      - $5 goes to trucking (transport margin)
      - $65 goes to the actual paper mill (basic price)
    
    This prevents overestimating the manufacturing shock.
    
    TODO: Source real margins from StatCan Supply and Use Tables (Table 36-10-0478-01).
    """
    return {
        "packaging": {
            "retail_margin":    0.20,
            "wholesale_margin": 0.10,
            "transport_margin": 0.05,
            "basic_price":      0.65,
            "basic_sector":     "BS3222",   # Paper/Packaging Mfg
        },
        "fuel_energy": {
            "retail_margin":    0.15,
            "wholesale_margin": 0.05,
            "transport_margin": 0.05,
            "basic_price":      0.75,
            "basic_sector":     "BS3241",   # Petroleum Products
        },
        "ag_inputs_seed": {
            "retail_margin":    0.15,
            "wholesale_margin": 0.10,
            "transport_margin": 0.05,
            "basic_price":      0.70,
            "basic_sector":     "BS111",    # Crop Production (inputs)
        },
    }


def build_ontario_rpcs():
    """
    Ontario Regional Purchase Coefficients.
    
    RPC = share of each input purchased from within Ontario.
    (1 - RPC) = import leakage (no local impact).
    
    TODO: Source real RPCs from StatCan interprovincial trade tables.
    
    CORRECTION #5 (Round 2): Must include INTERNATIONAL imports, not just
    interprovincial. Ontario imports heavily from USA/Mexico.
    Formula: True RPC = ON production in ON / (ON prod + interp imports + intl imports)
    Source both Table 36-10-0612-01 AND international import vectors from SUTs.
    """
    return {
        "hired_labor":        1.00,   # Workers live here
        "proprietor_income":  1.00,   # Farmer lives here
        "packaging":          0.25,   # Most packaging imported
        "fuel_energy":        0.25,   # Refined elsewhere, some local
        "ag_inputs_seed":     0.60,   # Mix — some local, some imported
        "marketing_services": 0.90,   # Local accountants, market stalls
        "taxes_land":         1.00,   # Government stays local
        # Margin sectors
        "retail_trade":       0.85,   # Local retailers
        "wholesale_trade":    0.50,   # Mix of local/national wholesalers
        "truck_transport":    0.80,   # Mostly provincial trucking
    }


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 2: MARGIN DEFLATION & RPC APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

def deflate_and_apply_rpcs(budget, margins, rpcs, shock_value=1_000_000):
    """
    Convert Purchaser Price budget to Basic Price shock vector with RPCs.
    
    For manufactured goods:
      1. Strip out retail/wholesale/transport margins
      2. Allocate margins to their own sectors
      3. Apply RPC to each component
    
    Returns:
        local_shock: dict mapping IOIC sector → local $ shock
        import_leakage: total $ leaking out of province
        detail_log: list of dicts showing the full decomposition
    """
    local_shock = {}
    import_leakage = 0.0
    detail_log = []
    
    # Items requiring margin deflation (physical manufactured goods)
    margin_items = set(margins.keys())
    
    for item, share in budget.items():
        purchaser_value = share * shock_value
        
        if item in margin_items:
            # ── MARGIN DEFLATION ─────────────────────────────────────
            profile = margins[item]
            
            # Strip margins from the manufactured good
            retail_margin_val    = purchaser_value * profile["retail_margin"]
            wholesale_margin_val = purchaser_value * profile["wholesale_margin"]
            transport_margin_val = purchaser_value * profile["transport_margin"]
            basic_price_val      = purchaser_value * profile["basic_price"]
            basic_sector         = profile["basic_sector"]
            
            # Verify margin decomposition sums to original
            margin_sum = retail_margin_val + wholesale_margin_val + transport_margin_val + basic_price_val
            assert abs(margin_sum - purchaser_value) < 0.01, \
                f"Margin decomposition error for {item}: {margin_sum} != {purchaser_value}"
            
            # Apply RPCs to each margin component
            components = [
                ("BS4A0",       retail_margin_val,    rpcs.get("retail_trade", 0.85)),
                ("BS4100",      wholesale_margin_val, rpcs.get("wholesale_trade", 0.50)),
                ("BS484",       transport_margin_val, rpcs.get("truck_transport", 0.80)),
                (basic_sector,  basic_price_val,      rpcs.get(item, 0.25)),
            ]
            
            for sector, value, rpc in components:
                local_val = value * rpc
                leaked = value * (1 - rpc)
                local_shock[sector] = local_shock.get(sector, 0) + local_val
                import_leakage += leaked
                
                detail_log.append({
                    "budget_item": item,
                    "component": sector,
                    "purchaser_$": round(value, 2),
                    "rpc": rpc,
                    "local_$": round(local_val, 2),
                    "leaked_$": round(leaked, 2),
                })
        
        elif item == "hired_labor":
            # Labor — no margin deflation, but goes to Induced calculation
            rpc = rpcs.get(item, 1.0)
            local_val = purchaser_value * rpc
            local_shock["VALUE_ADDED_LABOR"] = local_shock.get("VALUE_ADDED_LABOR", 0) + local_val
            import_leakage += purchaser_value * (1 - rpc)
            detail_log.append({
                "budget_item": item, "component": "VALUE_ADDED_LABOR",
                "purchaser_$": round(purchaser_value, 2), "rpc": rpc,
                "local_$": round(local_val, 2), "leaked_$": round(purchaser_value * (1 - rpc), 2),
            })
        
        elif item == "proprietor_income":
            rpc = rpcs.get(item, 1.0)
            local_val = purchaser_value * rpc
            local_shock["VALUE_ADDED_PROPRIETOR"] = local_shock.get("VALUE_ADDED_PROPRIETOR", 0) + local_val
            import_leakage += purchaser_value * (1 - rpc)
            detail_log.append({
                "budget_item": item, "component": "VALUE_ADDED_PROPRIETOR",
                "purchaser_$": round(purchaser_value, 2), "rpc": rpc,
                "local_$": round(local_val, 2), "leaked_$": round(purchaser_value * (1 - rpc), 2),
            })
        
        elif item == "marketing_services":
            rpc = rpcs.get(item, 0.90)
            local_val = purchaser_value * rpc
            local_shock["BS5400"] = local_shock.get("BS5400", 0) + local_val
            import_leakage += purchaser_value * (1 - rpc)
            detail_log.append({
                "budget_item": item, "component": "BS5400",
                "purchaser_$": round(purchaser_value, 2), "rpc": rpc,
                "local_$": round(local_val, 2), "leaked_$": round(purchaser_value * (1 - rpc), 2),
            })
        
        elif item == "taxes_land":
            rpc = rpcs.get(item, 1.0)
            local_val = purchaser_value * rpc
            local_shock["GOVT_TAXES"] = local_shock.get("GOVT_TAXES", 0) + local_val
            import_leakage += purchaser_value * (1 - rpc)
            detail_log.append({
                "budget_item": item, "component": "GOVT_TAXES",
                "purchaser_$": round(purchaser_value, 2), "rpc": rpc,
                "local_$": round(local_val, 2), "leaked_$": round(purchaser_value * (1 - rpc), 2),
            })
    
    return local_shock, import_leakage, detail_log


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 3: ANALYSIS-BY-PARTS (GROSS IMPACT)
# ═══════════════════════════════════════════════════════════════════════════

def calculate_gross_impact(local_shock, multipliers_df, shock_value=1_000_000):
    """
    Calculate Gross Local Food Impact using Analysis-by-Parts.
    
    1. Direct: The initial $1M shock
    2. Indirect: Each locally-retained input × its Simple multiplier
    3. Induced: Value Added × (1 - tax/savings leakage) × Household Consumption multiplier
    
    Uses SIMPLE multipliers only to avoid double-counting induced effects.
    """
    TAX_SAVINGS_LEAKAGE = 0.25  # 25% of income leaks to taxes and savings
    
    # ── Direct Impact ────────────────────────────────────────────────
    direct = {
        "output": shock_value,
        "gdp":    0.0,  # GDP from direct = value added (calculated below)
        "jobs":   0.0,  # Direct farm jobs (calculated below)
    }
    
    # ── Indirect Impact (supply chain ripples) ───────────────────────
    indirect = {"output": 0.0, "gdp": 0.0, "jobs": 0.0}
    indirect_detail = []
    
    for sector, local_val in local_shock.items():
        if sector.startswith("VALUE_ADDED") or sector == "GOVT_TAXES":
            continue  # These don't generate supply chain multiplier effects
        
        if sector in multipliers_df.index:
            row = multipliers_df.loc[sector]
            # Simple multiplier already includes direct + indirect for that sector
            # But we only want the indirect portion (the ripples from our shock)
            # Since our shock IS the direct, the multiplied value minus the shock = indirect
            sector_output  = local_val * (row["Output_Mult"] - 1.0)  # Subtract 1 to get indirect only
            sector_gdp     = local_val * row["GDP_Mult"]
            sector_jobs    = local_val / 1_000_000 * row["Jobs_per_M"]
            
            indirect["output"] += sector_output
            indirect["gdp"]    += sector_gdp
            indirect["jobs"]   += sector_jobs
            
            indirect_detail.append({
                "sector": row["Sector"],
                "local_shock_$": round(local_val, 2),
                "indirect_output_$": round(sector_output, 2),
                "indirect_gdp_$": round(sector_gdp, 2),
                "indirect_jobs": round(sector_jobs, 4),
            })
    
    # ── Value Added (Direct GDP and Jobs) ────────────────────────────
    va_labor = local_shock.get("VALUE_ADDED_LABOR", 0)
    va_proprietor = local_shock.get("VALUE_ADDED_PROPRIETOR", 0)
    total_value_added = va_labor + va_proprietor
    
    direct["gdp"] = total_value_added
    # Estimate direct farm jobs: assume avg farm wage of ~$45K
    avg_farm_wage = 45_000
    direct["jobs"] = va_labor / avg_farm_wage if va_labor > 0 else 0
    # Add proprietor as 1 job equivalent per ~$60K income
    direct["jobs"] += va_proprietor / 60_000 if va_proprietor > 0 else 0
    
    # ── Induced Impact (household respending) ────────────────────────
    disposable_income = total_value_added * (1 - TAX_SAVINGS_LEAKAGE)
    
    induced = {"output": 0.0, "gdp": 0.0, "jobs": 0.0}
    if "HH_CONS" in multipliers_df.index:
        hh = multipliers_df.loc["HH_CONS"]
        induced["output"] = disposable_income * (hh["Output_Mult"] - 1.0)
        induced["gdp"]    = disposable_income * hh["GDP_Mult"]
        induced["jobs"]   = disposable_income / 1_000_000 * hh["Jobs_per_M"]
    
    # ── Gross Total ──────────────────────────────────────────────────
    gross = {
        "output": direct["output"] + indirect["output"] + induced["output"],
        "gdp":    direct["gdp"]    + indirect["gdp"]    + induced["gdp"],
        "jobs":   direct["jobs"]   + indirect["jobs"]    + induced["jobs"],
    }
    
    return {
        "direct": direct,
        "indirect": indirect,
        "induced": induced,
        "gross": gross,
        "indirect_detail": indirect_detail,
        "value_added": total_value_added,
        "disposable_income": disposable_income,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 4: SWENSON NET-IMPACT COUNTERFACTUAL
# ═══════════════════════════════════════════════════════════════════════════

def calculate_displaced_impact(multipliers_df, shock_value=1_000_000):
    """
    What economic activity is DISPLACED when $1M shifts from conventional
    grocery to local food? This is the opportunity cost.
    
    Conventional $1 grocery purchase (Purchaser Price) decomposes into:
      - Retail margin: 0.30 (corporate grocery store)
      - Wholesale/transport: 0.15 (distribution chain)
      - Farm-gate/processor: 0.55 (basic price of food)
    
    Key insight: Conventional grocery has MASSIVE import leakage.
    ~80% of farm-gate value is imported from outside Ontario.
    """
    # Conventional grocery margin structure
    conv_retail     = shock_value * 0.30   # Grocery store margin
    conv_wholesale  = shock_value * 0.15   # Distribution chain
    conv_farm_basic = shock_value * 0.55   # Farm-gate + processor (basic price)
    
    # Conventional RPCs (much higher import leakage)
    # CORRECTION #7 (Round 2): "Leaky Counterfactual" - Loblaws/Metro actually
    # procure significant Ontario food (greenhouse tomatoes, dairy, poultry).
    # Must use Ontario agricultural self-sufficiency ratios to set Farm-Gate RPC.
    # Current 0.20 may be too low; real value likely 0.30-0.45 for Ontario.
    # This will reduce net impact but make it peer-review defensible.
    conv_rpcs = {
        "retail":    0.85,   # Local store, but corporate HQ profits leak
        "wholesale": 0.50,   # National/international distribution
        "farm_gate": 0.20,   # TODO: Replace with ON self-sufficiency ratio
    }
    
    # Build conventional local shock vector
    conv_local_shock = {}
    conv_local_shock["BS4A0"]  = conv_retail * conv_rpcs["retail"]
    conv_local_shock["BS4100"] = conv_wholesale * conv_rpcs["wholesale"]
    conv_local_shock["BS311"]  = conv_farm_basic * conv_rpcs["farm_gate"]
    
    # Value added from conventional (much less stays local)
    # Conventional retail employees earn wages locally
    conv_labor = conv_retail * conv_rpcs["retail"] * 0.40  # ~40% of retail margin = labor
    conv_va_total = conv_labor
    
    # Calculate displaced indirect impacts
    displaced = {"output": 0.0, "gdp": 0.0, "jobs": 0.0}
    
    for sector, local_val in conv_local_shock.items():
        if sector in multipliers_df.index:
            row = multipliers_df.loc[sector]
            displaced["output"] += local_val * (row["Output_Mult"] - 1.0)
            displaced["gdp"]    += local_val * row["GDP_Mult"]
            displaced["jobs"]   += local_val / 1_000_000 * row["Jobs_per_M"]
    
    # Add direct conventional impact
    conv_local_total = sum(conv_local_shock.values())
    displaced["output"] += conv_local_total  # Direct spending
    displaced["gdp"]    += conv_va_total     # Direct VA
    displaced["jobs"]   += conv_labor / 35_000  # Retail jobs (~$35K avg wage)
    
    # Add displaced induced effects
    TAX_SAVINGS_LEAKAGE = 0.25
    conv_disposable = conv_va_total * (1 - TAX_SAVINGS_LEAKAGE)
    if "HH_CONS" in multipliers_df.index:
        hh = multipliers_df.loc["HH_CONS"]
        displaced["output"] += conv_disposable * (hh["Output_Mult"] - 1.0)
        displaced["gdp"]    += conv_disposable * hh["GDP_Mult"]
        displaced["jobs"]   += conv_disposable / 1_000_000 * hh["Jobs_per_M"]
    
    return displaced, conv_local_shock


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 5: REPORTING
# ═══════════════════════════════════════════════════════════════════════════

def calculate_naive_baseline(multipliers_df, shock_value=1_000_000):
    """
    Naive baseline: Apply generic StatCan Crop Production multiplier.
    This is what most studies do WRONG — treats local food like commodity farming.
    """
    crop = multipliers_df.loc["BS111"]
    return {
        "output": shock_value * crop["Output_Mult"],
        "gdp":    shock_value * crop["GDP_Mult"],
        "jobs":   shock_value / 1_000_000 * crop["Jobs_per_M"],
    }


def format_currency(val):
    """Format as currency string."""
    if abs(val) >= 1_000_000:
        return f"${val/1_000_000:,.2f}M"
    elif abs(val) >= 1_000:
        return f"${val/1_000:,.1f}K"
    else:
        return f"${val:,.2f}"


def generate_report(shock_value=1_000_000):
    """Run the full pipeline and generate the comparison report."""
    
    print("=" * 78)
    print("  STATCAN LOCAL FOOD MULTIPLIER ENGINE")
    print("  Analysis-by-Parts with Swenson Net-Impact Correction")
    print("  Ontario, Canada — March 2026")
    print("=" * 78)
    
    # ── Initialize ───────────────────────────────────────────────────
    multipliers = build_statcan_multipliers()
    budget = build_local_farm_budget()
    margins = build_margin_profiles()
    rpcs = build_ontario_rpcs()
    
    # Validate budget sums to 1.0
    budget_total = sum(budget.values())
    assert abs(budget_total - 1.0) < 0.001, f"Budget doesn't sum to 1.0: {budget_total}"
    
    print(f"\n  Initial shock: {format_currency(shock_value)}")
    print(f"  Budget validation: {budget_total:.2f} (OK)\n")
    
    # ── Phase 2: Margin deflation & RPCs ─────────────────────────────
    print("-" * 78)
    print("  PHASE 2: MARGIN DEFLATION & RPC APPLICATION")
    print("-" * 78)
    
    local_shock, import_leakage, detail_log = deflate_and_apply_rpcs(
        budget, margins, rpcs, shock_value
    )
    
    detail_df = pd.DataFrame(detail_log)
    print(f"\n{detail_df.to_string(index=False)}\n")
    
    local_retained = sum(local_shock.values())
    print(f"  Local retained:   {format_currency(local_retained)}")
    print(f"  Import leakage:   {format_currency(import_leakage)}")
    print(f"  Retention rate:   {local_retained/shock_value:.1%}")
    
    # ── Phase 3: Gross impact ────────────────────────────────────────
    print(f"\n{'-' * 78}")
    print("  PHASE 3: ANALYSIS-BY-PARTS (GROSS IMPACT)")
    print("-" * 78)
    
    gross_results = calculate_gross_impact(local_shock, multipliers, shock_value)
    
    print(f"\n  Value Added (farm income):  {format_currency(gross_results['value_added'])}")
    print(f"  Disposable income (75%):    {format_currency(gross_results['disposable_income'])}")
    
    print(f"\n  {'Component':<20} {'Output':>15} {'GDP':>15} {'Jobs':>10}")
    print(f"  {'-'*60}")
    for comp in ["direct", "indirect", "induced", "gross"]:
        r = gross_results[comp]
        label = comp.upper() if comp == "gross" else f"  {comp.capitalize()}"
        print(f"  {label:<20} {format_currency(r['output']):>15} "
              f"{format_currency(r['gdp']):>15} {r['jobs']:>10.1f}")
    
    # ── Phase 4: Swenson counterfactual ──────────────────────────────
    print(f"\n{'-' * 78}")
    print("  PHASE 4: SWENSON NET-IMPACT COUNTERFACTUAL")
    print("-" * 78)
    
    displaced, conv_shock = calculate_displaced_impact(multipliers, shock_value)
    
    print(f"\n  Conventional grocery local shock:")
    for sector, val in conv_shock.items():
        name = multipliers.loc[sector, "Sector"] if sector in multipliers.index else sector
        print(f"    {name}: {format_currency(val)}")
    
    print(f"\n  Displaced activity:")
    print(f"    Output:     {format_currency(displaced['output'])}")
    print(f"    GDP:        {format_currency(displaced['gdp'])}")
    print(f"    Jobs:       {displaced['jobs']:.1f}")
    
    # ── Phase 5: Final comparison ────────────────────────────────────
    print(f"\n{'=' * 78}")
    print("  FINAL COMPARISON: NAIVE vs. GROSS vs. NET LOCAL FOOD IMPACT")
    print(f"  (Per {format_currency(shock_value)} of consumer food spending)")
    print("=" * 78)
    
    naive = calculate_naive_baseline(multipliers, shock_value)
    gross = gross_results["gross"]
    net = {
        "output": gross["output"] - displaced["output"],
        "gdp":    gross["gdp"]    - displaced["gdp"],
        "jobs":   gross["jobs"]   - displaced["jobs"],
    }
    
    # Build comparison DataFrame
    comparison = pd.DataFrame({
        "Metric": ["Total Output", "GDP Contribution", "Jobs Supported",
                    "Output Multiplier", "GDP Multiplier", "Jobs per $1M"],
        "Naive StatCan": [
            format_currency(naive["output"]),
            format_currency(naive["gdp"]),
            f"{naive['jobs']:.1f}",
            f"{naive['output']/shock_value:.2f}x",
            f"{naive['gdp']/shock_value:.2f}x",
            f"{naive['jobs']:.1f}",
        ],
        "Gross Local Food": [
            format_currency(gross["output"]),
            format_currency(gross["gdp"]),
            f"{gross['jobs']:.1f}",
            f"{gross['output']/shock_value:.2f}x",
            f"{gross['gdp']/shock_value:.2f}x",
            f"{gross['jobs']:.1f}",
        ],
        "Net Local Food": [
            format_currency(net["output"]),
            format_currency(net["gdp"]),
            f"{net['jobs']:.1f}",
            f"{net['output']/shock_value:.2f}x",
            f"{net['gdp']/shock_value:.2f}x",
            f"{net['jobs']:.1f}",
        ],
    })
    
    print(f"\n{comparison.to_string(index=False)}\n")
    
    # ── Diagnostic ───────────────────────────────────────────────────
    print("=" * 78)
    print("  ANALYTICAL DIAGNOSTIC")
    print("=" * 78)
    
    print(f"""
  WHY LOCAL FOOD HAS A HIGHER EMPLOYMENT MULTIPLIER:

  1. LABOUR INTENSITY: Local DTC farms allocate ~30% of revenue to hired labor
     vs. ~15-20% for conventional commodity farms. This directly creates more
     jobs per dollar of output.

  2. MARGIN CAPTURE: When a farmer sells direct-to-consumer, they capture the
     retail margin (~30%) and wholesale margin (~15%) that would otherwise leak
     to corporate supply chains. This retained income stays in the local economy.

  3. IMPORT SUBSTITUTION: Conventional grocery supply chains source ~80% of
     farm-gate product from outside Ontario. Local food replaces these imports
     with provincial production, keeping spending within the regional economy.

  EVEN AFTER the Swenson net-impact correction (subtracting the displaced
  conventional grocery activity), local food generates a NET POSITIVE impact
  of {format_currency(net['output'])} in output and {net['jobs']:.1f} net jobs
  per {format_currency(shock_value)} redirected from conventional to local purchasing.

  KEY CAVEAT: These results use MOCK multipliers and proxy RPCs. Before
  publication or policy use, replace with real StatCan Table 36-10-0595-01
  multipliers and Ontario-specific Regional Purchase Coefficients.
""")
    
    return {
        "naive": naive,
        "gross": gross,
        "net": net,
        "displaced": displaced,
        "gross_results": gross_results,
        "comparison": comparison,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    results = generate_report(shock_value=1_000_000)
