"""
Airline Delay & Operations Performance Analytics — Analysis Script
Dataset: 2015 Flight Delays and Cancellations (Kaggle / US DOT)
Author: Afrin

Scope decision (documented, not hidden): flights.csv is 5.8M rows. Per the
project brief, filtered to Q1 2015 (Jan-Mar) — a real quarter, not a random
sample, so seasonal patterns within the quarter stay intact. This is ~1.4M
rows, which still exercises real joins across 3 tables without crashing a
laptop-scale pandas session.

Run: python3 analysis.py
Produces: cleaned_flights_q1_2015.csv (sampled further for the dashboard), data.json
"""
import pandas as pd
import numpy as np
import json
from scipy import stats

pd.set_option("display.width", 160)

# ---------------------------------------------------------------
# PHASE 1/2 — LOAD, FILTER, JOIN
# ---------------------------------------------------------------
airlines = pd.read_csv("airlines.csv")
airports = pd.read_csv("airports.csv")

# Delay rule, decided up front (Phase 1): a flight is "delayed" if
# ARRIVAL_DELAY >= 15 minutes — this is the standard DOT definition, not
# an arbitrary choice.
DELAY_THRESHOLD_MIN = 15

usecols = ["YEAR","MONTH","DAY","DAY_OF_WEEK","AIRLINE","FLIGHT_NUMBER",
           "ORIGIN_AIRPORT","DESTINATION_AIRPORT","SCHEDULED_DEPARTURE",
           "DEPARTURE_DELAY","SCHEDULED_ARRIVAL","ARRIVAL_DELAY","DISTANCE",
           "DIVERTED","CANCELLED","CANCELLATION_REASON",
           "AIR_SYSTEM_DELAY","SECURITY_DELAY","AIRLINE_DELAY",
           "LATE_AIRCRAFT_DELAY","WEATHER_DELAY"]

chunks = []
for chunk in pd.read_csv("flights.csv", usecols=usecols, chunksize=500_000):
    q1 = chunk[chunk["MONTH"].isin([1, 2, 3])]
    if len(q1):
        chunks.append(q1)
df = pd.concat(chunks, ignore_index=True)
print(f"Q1 2015 rows loaded: {len(df):,}")

# Join airline names + airport names (real multi-table join, not a flat CSV)
df = df.merge(airlines, left_on="AIRLINE", right_on="IATA_CODE", how="left", suffixes=("", "_air"))
df = df.rename(columns={"AIRLINE_air": "AIRLINE_NAME"})
df = df.drop(columns=["IATA_CODE"])

origin_airports = airports[["IATA_CODE", "AIRPORT", "CITY", "STATE", "LATITUDE", "LONGITUDE"]].rename(
    columns={"AIRPORT": "ORIGIN_AIRPORT_NAME", "CITY": "ORIGIN_CITY", "STATE": "ORIGIN_STATE",
             "LATITUDE": "ORIGIN_LATITUDE", "LONGITUDE": "ORIGIN_LONGITUDE"}
)
df = df.merge(origin_airports, left_on="ORIGIN_AIRPORT", right_on="IATA_CODE", how="left").drop(columns=["IATA_CODE"])

# ---------------------------------------------------------------
# CANCELLED VS DELAYED — TREATED SEPARATELY (Phase 2 decision)
# Cancelled flights have no ARRIVAL_DELAY value at all — including them in
# a delay average would silently distort it. They're tracked as their own
# cancellation-rate metric instead.
# ---------------------------------------------------------------
df["is_cancelled"] = df["CANCELLED"] == 1
flown = df[~df["is_cancelled"]].copy()
flown["is_delayed"] = flown["ARRIVAL_DELAY"] >= DELAY_THRESHOLD_MIN

CANCEL_REASON_MAP = {"A": "Airline/Carrier", "B": "Weather", "C": "National Air System", "D": "Security"}
df["cancellation_reason_label"] = df["CANCELLATION_REASON"].map(CANCEL_REASON_MAP)

df.to_csv("cleaned_flights_q1_2015_full.csv", index=False)
# a lighter sample for the dashboard/GitHub (full file is too big to publish comfortably)
flown.sample(min(50_000, len(flown)), random_state=42).to_csv("cleaned_flights_sample.csv", index=False)

# ---------------------------------------------------------------
# PHASE 3 — BASELINE + SEGMENTATION
# ---------------------------------------------------------------
overall_on_time_rate = 1 - flown["is_delayed"].mean()
overall_avg_delay = flown["ARRIVAL_DELAY"].mean()
overall_cancel_rate = df["is_cancelled"].mean()

by_carrier = flown.groupby("AIRLINE_NAME").agg(
    flights=("ARRIVAL_DELAY", "count"),
    avg_delay=("ARRIVAL_DELAY", "mean"),
    on_time_rate=("is_delayed", lambda x: 1 - x.mean()),
).reset_index().sort_values("on_time_rate")

cancel_by_carrier = df.groupby("AIRLINE_NAME").agg(
    total=("is_cancelled", "count"), cancelled=("is_cancelled", "sum")
).reset_index()
cancel_by_carrier["cancel_rate"] = cancel_by_carrier["cancelled"] / cancel_by_carrier["total"]

by_origin = flown.groupby(["ORIGIN_AIRPORT", "ORIGIN_CITY", "ORIGIN_LATITUDE", "ORIGIN_LONGITUDE"]).agg(
    flights=("ARRIVAL_DELAY", "count"), avg_delay=("ARRIVAL_DELAY", "mean"),
    on_time_rate=("is_delayed", lambda x: 1 - x.mean()),
).reset_index()
by_origin = by_origin[by_origin["flights"] >= 500].sort_values("avg_delay", ascending=False)

flown["route"] = flown["ORIGIN_AIRPORT"] + "-" + flown["DESTINATION_AIRPORT"]
by_route = flown.groupby("route").agg(
    flights=("ARRIVAL_DELAY", "count"), avg_delay=("ARRIVAL_DELAY", "mean"),
).reset_index()
by_route = by_route[by_route["flights"] >= 200].sort_values("avg_delay", ascending=False)

# Delay-cause breakdown (minutes), only among flights that actually had a recorded delay cause
cause_cols = ["AIR_SYSTEM_DELAY", "SECURITY_DELAY", "AIRLINE_DELAY", "LATE_AIRCRAFT_DELAY", "WEATHER_DELAY"]
cause_totals = flown[cause_cols].sum()
cause_totals.index = ["Air System (NAS)", "Security", "Airline/Carrier", "Late Aircraft", "Weather"]

flown["hour"] = (flown["SCHEDULED_DEPARTURE"] // 100).clip(0, 23)
by_hour = flown.groupby("hour").agg(avg_delay=("ARRIVAL_DELAY", "mean"), flights=("ARRIVAL_DELAY", "count")).reset_index()
by_dow = flown.groupby("DAY_OF_WEEK").agg(avg_delay=("ARRIVAL_DELAY", "mean"), flights=("ARRIVAL_DELAY", "count")).reset_index()
by_day = flown.groupby(["MONTH", "DAY"]).agg(avg_delay=("ARRIVAL_DELAY", "mean"), flights=("ARRIVAL_DELAY", "count")).reset_index()
by_day["date"] = pd.to_datetime(dict(year=2015, month=by_day["MONTH"], day=by_day["DAY"])).dt.strftime("%Y-%m-%d")

# ---------------------------------------------------------------
# PHASE 7 — COUNTER-INTUITIVE FINDING + STAT TEST
# Hypothesis: which carrier "everyone assumes is worst" — Spirit (NK) has a
# famously bad reputation. Is it actually the worst by on-time rate, or is
# the real problem concentrated somewhere less obvious (a specific hub)?
# ---------------------------------------------------------------
worst_carrier_row = by_carrier.iloc[0]
best_carrier_row = by_carrier.iloc[-1]

spirit = by_carrier[by_carrier["AIRLINE_NAME"].str.contains("Spirit", na=False)]
worst_is_spirit = worst_carrier_row["AIRLINE_NAME"] == spirit["AIRLINE_NAME"].iloc[0] if len(spirit) else False

# stat test: is the on-time-rate gap between worst and 2nd-worst carrier real, or noise?
worst_name = worst_carrier_row["AIRLINE_NAME"]
second_worst_name = by_carrier.iloc[1]["AIRLINE_NAME"]
worst_delays = flown.loc[flown["AIRLINE_NAME"] == worst_name, "is_delayed"].astype(int)
second_delays = flown.loc[flown["AIRLINE_NAME"] == second_worst_name, "is_delayed"].astype(int)
t_stat, p_val = stats.ttest_ind(worst_delays, second_delays, equal_var=False)

# Late-aircraft delay concentration: what % of total late-aircraft minutes sits in top 5 hubs?
flown_valid_cause = flown.dropna(subset=["LATE_AIRCRAFT_DELAY"])
late_aircraft_by_airport = flown_valid_cause.groupby("ORIGIN_AIRPORT")["LATE_AIRCRAFT_DELAY"].sum().sort_values(ascending=False)
top5_hubs_late_aircraft = late_aircraft_by_airport.head(5)
top5_share = top5_hubs_late_aircraft.sum() / late_aircraft_by_airport.sum()

print("=== BASELINE ===")
print(f"On-time rate: {overall_on_time_rate:.2%}")
print(f"Avg arrival delay (flown only): {overall_avg_delay:.2f} min")
print(f"Cancellation rate: {overall_cancel_rate:.2%}")
print()
print("=== WORST / BEST CARRIER BY ON-TIME RATE ===")
print(by_carrier[["AIRLINE_NAME", "flights", "on_time_rate", "avg_delay"]].to_string())
print()
print(f"Worst carrier is Spirit? {worst_is_spirit}")
print(f"t-test worst vs 2nd-worst on-time gap: t={t_stat:.3f}, p={p_val:.6f}")
print()
print("=== TOP 5 WORST ORIGIN AIRPORTS BY AVG DELAY (>=500 flights) ===")
print(by_origin.head(5)[["ORIGIN_AIRPORT", "ORIGIN_CITY", "flights", "avg_delay", "on_time_rate"]])
print()
print("=== TOP 5 WORST ROUTES (>=200 flights) ===")
print(by_route.head(5))
print()
print("=== DELAY CAUSE BREAKDOWN (total minutes) ===")
print(cause_totals)
print(f"Share of total: \n{(cause_totals/cause_totals.sum()*100).round(1)}")
print()
print(f"Top-5-hub share of total late-aircraft delay minutes: {top5_share:.2%}")
print(top5_hubs_late_aircraft)
print()
print("=== CANCELLATION RATE BY CARRIER (top 5 worst) ===")
print(cancel_by_carrier.sort_values('cancel_rate', ascending=False).head(5))

output = {
    "overall_on_time_rate": round(float(overall_on_time_rate), 4),
    "overall_avg_delay": round(float(overall_avg_delay), 2),
    "overall_cancel_rate": round(float(overall_cancel_rate), 4),
    "delay_threshold_min": DELAY_THRESHOLD_MIN,
    "by_carrier": by_carrier.to_dict(orient="records"),
    "cancel_by_carrier": cancel_by_carrier.sort_values("cancel_rate", ascending=False).to_dict(orient="records"),
    "by_origin_top15": by_origin.head(15).to_dict(orient="records"),
    "by_route_top10": by_route.head(10).to_dict(orient="records"),
    "cause_totals": {k: round(float(v), 1) for k, v in cause_totals.items()},
    "by_hour": by_hour.to_dict(orient="records"),
    "by_dow": by_dow.to_dict(orient="records"),
    "by_day": by_day[["date", "avg_delay", "flights"]].to_dict(orient="records"),
    "stat_test": {
        "worst_carrier": worst_name, "second_worst_carrier": second_worst_name,
        "t_stat": round(float(t_stat), 3), "p_value": float(p_val),
    },
    "insight": {
        "worst_is_spirit": bool(worst_is_spirit),
        "worst_carrier": worst_name,
        "worst_on_time_rate": round(float(worst_carrier_row["on_time_rate"]), 4),
        "best_carrier": best_carrier_row["AIRLINE_NAME"],
        "best_on_time_rate": round(float(best_carrier_row["on_time_rate"]), 4),
        "top5_hub_late_aircraft_share": round(float(top5_share), 4),
        "top5_hubs": top5_hubs_late_aircraft.index.tolist(),
    },
    "row_count_q1": int(len(df)),
    "flown_count": int(len(flown)),
}
with open("data.json", "w") as f:
    json.dump(output, f, indent=2, default=str)
print("\nSaved data.json")
