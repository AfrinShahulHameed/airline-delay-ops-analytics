# Airline Delay & Operations Performance Analytics

**Type:** Analyst case study · **Tools:** Tableau (calculated fields, cross-filtering dashboard), Python (pandas, SciPy) for data cleaning and statistical validation
**Dataset:** [2015 Flight Delays and Cancellations](https://www.kaggle.com/datasets/usdot/flight-delays) (Kaggle / US DOT) — `flights.csv` (5.8M rows), `airlines.csv`, `airports.csv`.

## Dashboard Preview

![Airline Delay Overview](screenshots/Airline%20Delay%20Overview.png)

---

## 1. Scope decision

`flights.csv` is 5.8M rows — too large to explore responsively. Per the brief, filtered to **Q1 2015 (Jan–Mar)**, a real calendar quarter rather than a random sample, so within-quarter seasonality (e.g. winter weather patterns) stays intact. That's **1,403,471 flights**, of which 1,359,970 actually flew (the rest were cancelled — see below).

## 2. Business Problem

Leadership on a network operations team wants to know which carriers, airports, and routes are actually driving delays and cancellations, what's causing them, and where an SLA renegotiation or infrastructure fix would pay off.

Three questions this had to answer:
1. Which carriers/airports have the worst on-time performance — and is it who you'd assume?
2. What's actually driving delays — carrier-controlled issues, or something structural?
3. What would fixing the worst segment be worth?

## 3. Methodology

- **Delay definition, fixed up front:** a flight is "delayed" if `ARRIVAL_DELAY >= 15 minutes` — the standard US DOT definition, not an arbitrary cutoff.
- **Cancelled flights handled separately from delayed ones.** A cancelled flight has no arrival-delay value; folding it into a delay average would silently distort the number. Cancellation rate is tracked as its own metric per carrier.
- **Real 3-table join**, not a flat CSV: `flights` joined to `airlines` (carrier code → name) and `airports` (origin airport code → name/city/lat/lon). One non-hand-held quirk resolved here: `airports.AIRPORT` and `flights.ORIGIN_AIRPORT` would silently collide and get mangled by pandas' auto-suffixing on merge if renamed carelessly — caught and fixed explicitly in `analysis.py`.
- **Cancellation reason codes decoded** from the DOT standard (A=Airline/Carrier, B=Weather, C=National Air System, D=Security) rather than left as opaque letters.

## 4. Key Findings (real numbers, computed from the data)

- **Baseline:** 78.9% on-time rate, 6.2 min average arrival delay (flown flights only), 3.1% cancellation rate across Q1 2015.
- **Headline / counter-intuitive finding:** Spirit Air Lines has the worst on-time *reputation* among flyers — but in this data, it isn't the worst performer. **Frontier Airlines** has the lowest on-time rate (65.0%), with **American Eagle Airlines** close behind (67.3%); Spirit actually ranks 4th-worst (71.9%), ahead of both JetBlue and American Eagle. A Welch's t-test on the gap between the two actual worst carriers (Frontier vs. American Eagle) confirms it's real: **t = 6.16, p < 0.000001** — not sampling noise.
- **The bigger structural finding:** delay-minutes broken down by cause show **Late Aircraft delay (a cascading delay from a previous flight) is the single largest cause nationally at 39.3%** of all delay-minutes — bigger than each airline's own controllable ("Airline/Carrier") delays at 31.7%. This reframes the fix: it's not primarily a discipline problem at any one airline, it's a network-scheduling problem where one late flight ripples into the next.
- **Cancellations are a different leaderboard entirely.** American Eagle has by far the worst cancellation rate (9.66%) — more than double the next-worst carrier (Atlantic Southeast, 4.58%) — while it wasn't the single worst on delay. Delay and cancellation are two separate operational problems, not one.
- **Worst routes are dominated by one hub:** of the 5 worst routes by average delay (XNA-ORD, OKC-ORD, RSW-LGA, DCA-JFK, ORD-BWI), **ORD (Chicago O'Hare) appears on 3 of the top 5** — as both an origin and destination chokepoint. This points at O'Hare itself as a systemic bottleneck rather than any single carrier or route.
- **Late-aircraft delay is moderately concentrated**, not evenly spread: the top 5 origin hubs by total late-aircraft delay-minutes (ORD, DFW, DEN, LGA, LAX) account for **22.7%** of all late-aircraft delay-minutes nationally, despite being a small fraction of all airports in the dataset.
- **Delay compounds through the day**, as the hourly trend shows — early-morning departures run close to on-time, and average delay climbs through the day as aircraft rotations fall further behind schedule (a direct visual companion to the Late Aircraft finding above).

### Quantifying the impact (external benchmark, clearly flagged as an assumption)
The dataset itself has no dollar-cost field, so this uses a widely-cited aviation-economics benchmark rather than inventing a number: the FAA/NEXTOR "Total Delay Impact Study" (Ball et al., 2010) estimates **~$75 per minute of flight delay** in combined airline and passenger costs. Applying that externally-sourced rate (not derived from this dataset) to this quarter's total delay-minutes across all causes (~16.5M minutes) gives a rough estimated cost of **~$1.24 billion for the quarter (~$412M/month)** — in the same order of magnitude as published national estimates, though this is an approximation, not a dataset-derived figure, and should be cited as such if used.

## 5. Recommendations

1. **Renegotiate ground-handling / turnaround SLAs at ORD specifically** — it's the common thread across 3 of the 5 worst routes, suggesting an airport-level bottleneck, not a carrier-level one.
2. **Target schedule buffer/recovery time on Frontier and American Eagle's tightest rotations** — they're the two statistically-confirmed worst performers, and the gap is real, not noise.
3. **Treat American Eagle's cancellation problem as separate from its delay problem** — a 9.66% cancellation rate needs its own root-cause review (likely fleet/staffing related), distinct from delay-minute fixes.
4. **Invest in schedule padding at the 5 highest late-aircraft-delay hubs** (ORD, DFW, DEN, LGA, LAX) — with 22.7% of national late-aircraft delay concentrated there, a small buffer change at these hubs would have outsized network-wide impact.

## 6. Limitations (what to validate with more time/data)

- **Q1-only sample.** Winter months (Jan–Mar) skew toward weather-driven delays; a summer quarter would likely show a different cause mix (more thunderstorm/ATC-driven Air System delays). The Late Aircraft finding should be checked against a second quarter before treating it as a year-round pattern.
- **The $75/minute cost figure is an external benchmark, not derived from this dataset** — real cost-per-minute varies heavily by aircraft type, route, and whether passengers miss connections. Treat the cost estimate as an order-of-magnitude illustration, not a precise number.
- **Cancellation reason codes are self-reported by carriers** — "Airline/Carrter" cancellations may sometimes be reclassified from weather in practice; this wasn't independently verified.
- **Route-level sample sizes vary** — routes were filtered to ≥200 flights in the quarter specifically to avoid a single bad day at a low-volume route looking like a systemic problem, but the "top 5 worst routes" list should still be sanity-checked against a full year before acting on it operationally.

## 7. Files in this repo

| File | What it is |
|---|---|
| `airlines.csv`, `airports.csv` | Original Kaggle reference tables, untouched |
| `flights.csv` | Original Kaggle export (not included in the delivered package — 570MB; re-download from Kaggle if rebuilding) |
| `analysis.py` | Full load/filter/join/KPI/stat-test pipeline (reproducible, prints every number in this README) |
| `cleaned_flights_sample.csv` | 50k-row sample of the cleaned, joined Q1 2015 data used to build the dashboard (full cleaned file omitted for size — regenerate with `analysis.py`) |
| `Airline_Delay_Dashboard.twbx` | The finished Tableau dashboard (packaged workbook, data included) — open in Tableau Desktop (free Public/Desktop trial works) |
| `screenshots/` | PNG exports of the dashboard, for anyone viewing the repo without Tableau installed |

To reproduce the data pipeline: `python3 analysis.py` (requires `flights.csv` from Kaggle in the same folder). To rebuild the dashboard, open `Airline_Delay_Dashboard.twbx` in Tableau Desktop.

## 8. Summary

Network ops wanted to know which carriers were really driving delays. Spirit has the worst reputation with flyers, but the data showed Frontier and American Eagle were actually the two worst performers — a gap confirmed statistically significant (p < 0.000001), not noise. The bigger finding was that the single largest delay cause nationally wasn't any airline's own operations — it was cascading "late aircraft" delay, bigger than every carrier's controllable delay combined. Three of the five worst routes all touched Chicago O'Hare, pointing at a hub-level bottleneck rather than a single carrier's problem. That changes the fix from "discipline this airline" to "fix schedule recovery time at this hub."
