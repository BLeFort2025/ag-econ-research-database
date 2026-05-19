"""
Import Substitution Analysis: FCC $2.6B Scenario
==================================================

This script implements Steps 1-3 of the methodology to estimate the
economic impact of replacing $2.6 billion in U.S. food imports with
Canadian-sourced products, as proposed by Farm Credit Canada (Sept 2025).

Step 1: FCC's $2.6B target (given)
Step 2: Allocate across NAICS 311/312 sub-sectors using USDA trade data
Step 3: Apply commodity margins to isolate new Canadian producer value

The output is a sector-allocated, margined "shock table" ready to be
fed into the OFA IO Multiplier Engine.

Sources:
  - FCC (2025). The $12-billion trade shift. Farm Credit Canada.
  - USDA FAS GATS (2023). U.S. consumer-oriented agricultural exports to Canada.
  - Statistics Canada Supply & Use Tables (Table 36-10-0478-01).
  - Krasnoff, Schmit & Bilinski (2023). Food Policy, 121, 102545.
"""

import pandas as pd
import json

# ============================================================================
# STEP 1: FCC Target
# ============================================================================
FCC_IMPORT_SUBSTITUTION_CAD = 2_600_000_000  # $2.6 billion CAD

# Exchange rate context (2023 average): 1 USD = ~1.35 CAD
# USDA data is in USD; FCC target is in CAD
USD_TO_CAD = 1.35

# ============================================================================
# STEP 2: Sector Allocation Using USDA Trade Data
# ============================================================================
# Source: USDA Foreign Agricultural Service GATS database, 2023
# U.S. consumer-oriented food exports to Canada by category (USD millions)
# These represent what Canada actually imports from the U.S. by product type

usda_imports_usd_millions = {
    "Bakery Goods, Cereals & Pasta":       2768,
    "Fresh Vegetables":                     1958,
    "Fresh Fruit":                          1702,
    "Non-Alcoholic Beverages":              1458,
    "Food Preparations (soups, frozen)":    1359,
    "Dairy Products":                       1082,
    "Chocolate & Cocoa Products":            878,
    "Beef & Beef Products":                  877,
    "Pork & Pork Products":                  876,
    "Condiments & Sauces":                   839,
}

# NAICS mapping: Which NAICS 311/312 sub-sector does each USDA category map to?
usda_to_naics = {
    "Bakery Goods, Cereals & Pasta":       {"naics": "3118", "name": "Bakeries & tortilla mfg"},
    "Fresh Vegetables":                     {"naics": "1114/3114", "name": "Fruit & veg preserving / Greenhouse"},
    "Fresh Fruit":                          {"naics": "1114/3114", "name": "Fruit & veg preserving / Greenhouse"},
    "Non-Alcoholic Beverages":              {"naics": "3121", "name": "Beverage manufacturing"},
    "Food Preparations (soups, frozen)":    {"naics": "3119", "name": "Other food manufacturing"},
    "Dairy Products":                       {"naics": "3115", "name": "Dairy product manufacturing"},
    "Chocolate & Cocoa Products":           {"naics": "3113", "name": "Sugar & confectionery"},
    "Beef & Beef Products":                 {"naics": "3116", "name": "Meat product manufacturing"},
    "Pork & Pork Products":                 {"naics": "3116", "name": "Meat product manufacturing"},
    "Condiments & Sauces":                  {"naics": "3119", "name": "Other food manufacturing"},
}

# Substitutability score: How realistic is it that Canada can replace
# U.S. imports in this category with domestic production?
# 1.0 = fully substitutable, 0.0 = not substitutable
# Based on existing Canadian production capacity
substitutability = {
    "Bakery Goods, Cereals & Pasta":       0.85,  # Canada has massive grain/milling capacity
    "Fresh Vegetables":                     0.30,  # Seasonal constraint - winter imports necessary
    "Fresh Fruit":                          0.20,  # Citrus/tropical impossible; berries/apples feasible
    "Non-Alcoholic Beverages":              0.80,  # Processing capacity exists
    "Food Preparations (soups, frozen)":    0.85,  # Value-added processing opportunity
    "Dairy Products":                       0.90,  # Supply management - surplus capacity exists
    "Chocolate & Cocoa Products":           0.50,  # Cocoa imported but processing can be domestic
    "Beef & Beef Products":                 0.90,  # Canada is a net beef exporter
    "Pork & Pork Products":                 0.90,  # Canada is a net pork exporter
    "Condiments & Sauces":                  0.80,  # Food manufacturing capacity exists
}

# ============================================================================
# STEP 2a: Calculate each category's share of total substitutable imports
# ============================================================================
print("=" * 80)
print("STEP 2: SECTOR ALLOCATION OF $2.6B IMPORT SUBSTITUTION TARGET")
print("=" * 80)

# Calculate substitutable value for each category
rows = []
for category, usd_val in usda_imports_usd_millions.items():
    cad_val = usd_val * USD_TO_CAD  # Convert to CAD
    sub_score = substitutability[category]
    substitutable_cad = cad_val * sub_score
    naics_info = usda_to_naics[category]
    
    rows.append({
        "Category": category,
        "US_Import_USD_M": usd_val,
        "US_Import_CAD_M": round(cad_val, 1),
        "Substitutability": sub_score,
        "Substitutable_CAD_M": round(substitutable_cad, 1),
        "NAICS": naics_info["naics"],
        "NAICS_Name": naics_info["name"],
    })

df = pd.DataFrame(rows)
total_substitutable = df["Substitutable_CAD_M"].sum()

# Scale each category so the total equals exactly $2.6B CAD
df["Share_of_Total"] = df["Substitutable_CAD_M"] / total_substitutable
df["Allocated_CAD_M"] = round(df["Share_of_Total"] * (FCC_IMPORT_SUBSTITUTION_CAD / 1_000_000), 1)

print(f"\nTotal U.S. food imports to Canada (top 10 categories): "
      f"${sum(usda_imports_usd_millions.values()):,.0f}M USD "
      f"(${sum(usda_imports_usd_millions.values()) * USD_TO_CAD:,.0f}M CAD)")
print(f"Total substitutable (weighted by feasibility):  ${total_substitutable:,.1f}M CAD")
print(f"FCC Target:                                     $2,600.0M CAD")
print(f"Implied overall substitution rate:               "
      f"{(FCC_IMPORT_SUBSTITUTION_CAD/1e6)/total_substitutable*100:.1f}% of substitutable imports")

print(f"\n{'Category':<40} {'Import':>10} {'Sub%':>6} {'Allocated':>10} {'NAICS':>8}")
print("-" * 80)
for _, r in df.iterrows():
    print(f"{r['Category']:<40} ${r['US_Import_CAD_M']:>8,.1f}M {r['Substitutability']:>5.0%} "
          f"${r['Allocated_CAD_M']:>8,.1f}M  {r['NAICS']:>7}")
print("-" * 80)
print(f"{'TOTAL':<40} ${df['US_Import_CAD_M'].sum():>8,.1f}M        "
      f"${df['Allocated_CAD_M'].sum():>8,.1f}M")

# ============================================================================
# STEP 2b: Aggregate to NAICS level (combine categories that share NAICS codes)
# ============================================================================
# For categories that map to the same NAICS, combine them
naics_agg = df.groupby(["NAICS", "NAICS_Name"]).agg(
    Allocated_CAD_M=("Allocated_CAD_M", "sum"),
    Share=("Share_of_Total", "sum"),
).reset_index().sort_values("Allocated_CAD_M", ascending=False)

print(f"\n{'='*80}")
print("STEP 2b: AGGREGATED TO NAICS SUB-SECTORS")
print(f"{'='*80}")
print(f"\n{'NAICS':<12} {'Industry':<35} {'Allocated':>12} {'Share':>8}")
print("-" * 70)
for _, r in naics_agg.iterrows():
    print(f"{r['NAICS']:<12} {r['NAICS_Name']:<35} ${r['Allocated_CAD_M']:>9,.1f}M  {r['Share']:>6.1%}")

# ============================================================================
# STEP 3: APPLY COMMODITY MARGINS
# ============================================================================
# Source: Statistics Canada Supply & Use Tables (Table 36-10-0478-01)
# These margins represent the typical cost structure for food products
# in Canada. The "producer value" is the portion that accrues to the
# manufacturer/farmer. Wholesale and transport margins are ALREADY in
# the Canadian economy even when we import, so they are NOT new activity.
#
# Margin estimates for food manufacturing (NAICS 311/312):
# Based on StatCan Supply & Use commodity margin data, food products
# typically have the following margin structure at the import/wholesale level:

margin_structure = {
    # NAICS: (producer_value_share, wholesale_margin, transport_margin)
    # Producer value = the manufacturing/farm-gate share of the price
    # This is the share that shifts from U.S. to Canadian producers
    "3118":      (0.68, 0.22, 0.10),  # Bakery: higher producer share
    "1114/3114": (0.55, 0.30, 0.15),  # Fresh produce: high wholesale/transport
    "3121":      (0.65, 0.25, 0.10),  # Beverages
    "3119":      (0.62, 0.26, 0.12),  # Other food mfg (preparations, condiments)
    "3115":      (0.70, 0.20, 0.10),  # Dairy: high producer share
    "3113":      (0.60, 0.28, 0.12),  # Sugar/confectionery
    "3116":      (0.72, 0.18, 0.10),  # Meat: high producer share
}

print(f"\n{'='*80}")
print("STEP 3: MARGINED PRODUCER VALUE (NEW CANADIAN ECONOMIC ACTIVITY)")
print("=" * 80)
print(f"\nNote: Wholesale and transport margins (~30-45% of import value)")
print(f"are ALREADY in the Canadian economy. Only the PRODUCER VALUE")
print(f"represents genuinely new Canadian economic activity from substitution.")
print(f"(Methodology: Krasnoff, Schmit & Bilinski, 2023 - Food Policy)")

print(f"\n{'NAICS':<12} {'Industry':<30} {'Gross':>10} {'ProdVal%':>9} {'Net New':>10}")
print("-" * 75)

shock_table = []
total_gross = 0
total_net = 0

for _, r in naics_agg.iterrows():
    naics = r["NAICS"]
    gross_cad_m = r["Allocated_CAD_M"]
    prod_share, _, _ = margin_structure.get(naics, (0.65, 0.25, 0.10))
    net_new_cad_m = round(gross_cad_m * prod_share, 1)
    
    total_gross += gross_cad_m
    total_net += net_new_cad_m
    
    # For the IO engine, we need clean NAICS codes (no slashes)
    # Split combined codes
    clean_codes = [c.strip() for c in naics.split("/")]
    
    shock_table.append({
        "naics_codes": clean_codes,
        "industry_name": r["NAICS_Name"],
        "gross_import_value_cad_m": gross_cad_m,
        "producer_value_share": prod_share,
        "net_new_producer_value_cad_m": net_new_cad_m,
    })
    
    print(f"{naics:<12} {r['NAICS_Name']:<30} ${gross_cad_m:>8,.1f}M  {prod_share:>7.0%}  ${net_new_cad_m:>8,.1f}M")

print("-" * 75)
print(f"{'TOTAL':<12} {'':<30} ${total_gross:>8,.1f}M           ${total_net:>8,.1f}M")

print(f"\n{'='*80}")
print("SUMMARY: IO ENGINE INPUT (SHOCK TABLE)")
print("=" * 80)
print(f"\nFCC Import Substitution Target:     ${FCC_IMPORT_SUBSTITUTION_CAD/1e9:.1f}B CAD")
print(f"After Margining (Producer Value):   ${total_net/1e3:.2f}B CAD")
print(f"Margin Reduction:                   {(1 - total_net/total_gross)*100:.1f}%")
print(f"\nThis ${total_net/1e3:.2f}B is the 'direct shock' to feed into the IO engine.")
print(f"The engine will then calculate indirect + induced multiplier effects")
print(f"to produce total GDP, Employment, and Labour Income impacts.")

print(f"\n--- Shock Table for IO Engine ---")
for entry in shock_table:
    codes_str = ", ".join(entry["naics_codes"])
    print(f"  NAICS {codes_str:<12}: ${entry['net_new_producer_value_cad_m']:>8,.1f}M CAD "
          f"({entry['industry_name']})")

# Save shock table for use by IO engine
output = {
    "scenario": "FCC $2.6B Import Substitution",
    "source": "FCC (2025), USDA FAS GATS (2023), StatCan Supply & Use Tables",
    "methodology": "Krasnoff et al. (2023) margining approach",
    "total_gross_cad_millions": round(total_gross, 1),
    "total_net_producer_value_cad_millions": round(total_net, 1),
    "margin_reduction_pct": round((1 - total_net/total_gross)*100, 1),
    "sectors": shock_table,
}

import os
out_dir = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(out_dir, "shock_table_fcc_2_6b.json")
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nShock table saved to: {out_path}")
