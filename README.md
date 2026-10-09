# Demand Forecasting & Inventory Planning

**Demand forecasting is only useful if the replenishment decision improves.** This project applies time-series ML to the M5 retail dataset, then evaluates whether a simulated forecast-based replenishment policy can cut costs **without reducing customer availability**.

Vercel - https://demand-forecasting-inventory-planni.vercel.app/

[Interactive dashboard source](dashboard/) · [Standalone HTML preview](Dashboard_Preview.html) · [Clean notebook](Demand_Forecasting_Inventory_Planning.ipynb)

> **Results provenance:** The bundled dashboard JSON and HTML preview initially show original, **archived** notebook results. They are **not** outputs of the revised, stricter forecasting + optimization workflow. Source M5 CSVs are required to generate real revised results. A tiny synthetic fixture was used only to verify the new pipeline functions. The external M5 CSV download was not possible in this environment, so no new real-data savings are claimed. Inventory parameters and costs are always simulated.

## The business problem

| What | Why | How | Outcome |
|---|---|---|---|
| Forecast daily SKU/store sales and simulate replenishment. | A low prediction error does not guarantee low stockouts or good business decisions. | Compare four forecasting models; use separate chronological fitting, tuning and testing; optimize forecast demand cover and safety stock subject to a service requirement. | Report a transparent **adopt / do-not-adopt** result with historical test metrics and cost/service trade-offs. |

## What was wrong with the earlier result?

The original notebook reported a **4.27% reduction in synthetic modeled cost**, but simulated fill rate dropped from **96.18% to 93.17%** and lost sales rose. It also calculated lagged features using actual sales from earlier dates of the holdout. **Those figures cannot establish business value from a 28-day-ahead deployed policy.**

The new code **does not copy or quietly improve those figures**. It reruns the experiment and accepts the possibility that a simple baseline wins.

## Revised methodology

**Three sequential windows:**

```text
Historical M5 unit sales ... | FIT HISTORY | 28 days: MODEL + POLICY TUNING | 28 days: FINAL TEST |
                            ↑             ↑                                ↑
                  features & models   choose forecasting model        locked strategy,
                                      AND safety parameters           unbiased evaluation
```

1. **Select items using fit history only.** Top 75 products at CA_1, TX_1 and WI_1, giving up to 225 store-item combinations. The large unused DuckDB extract from the original notebook is removed.
2. **Leakage-safe demand forecasts.** Compare a seven-day moving average, linear regression, random forest, and XGBoost. Use past-only lag/rolling features and genuinely recursive, 28-day predictions. On validation/test horizons, freeze item prices at the latest pre-cutoff prices; use the calendar, SNAP and events as known inputs.
3. **Select the champion on tuning WAPE, not the final test.** Refit once on fit+tuning data to produce the final holdout predictions. Measure WAPE for all models on test **for reporting**, never to reselect.
4. **Fair daily-review inventory policies.** Both fixed and forecast-based strategies respect synthetic purchase-order lead time, inventory in transit, physical on-hand balances and daily ordering. The static baseline targets mean demand over lead time + review period **plus variability buffer**, not a deliberately weak seven-day constant.
5. **Lead-time demand + safety stock.** At the *end* of a day, the forecast-based policy targets `multiplier × sum(forecasts for next lead_time+1 days) + z × historical_std × sqrt(lead_time+1)`. Order = `max(0, target - on_hand - outstanding_orders)`.
6. **Constrained tuning only on validation.** Simulate **21** forecast candidate combinations (three bias multipliers × seven safety stock z-values) plus **one fixed baseline**. Select the lowest-cost policy with at least **96% modeled fill rate** (configurable). If none qualifies, select none. A fixed baseline can be selected if it wins.
7. **Untouched out-of-sample decision.** To accept the frozen tuned challenger, all three conditions must hold **on final test**: (a) fill ≥ 96%, (b) fill ≥ fixed baseline test fill, and (c) total synthetic cost < fixed baseline test cost. Otherwise explicitly recommend **no replacement**. A post-hoc test diagnostic sweep is saved separately and is **never used for policy selection**.

### Caveats, spelled out

- M5 provides realized **sales**, not necessarily true customer demand (stockouts may censor demand). Any simulated 'lost units' are counterfactual indicators, not observed retailer transactions.
- Actual on-hand stock, outstanding POs, supplier lead times, holding costs, stockout penalties and unit-level margins are **not available in M5**. These are simulated to compare methods. Costs are *arbitrary synthetic units*, not USD or booked savings.
- Synthetic beginning stock is based on the preceding seven days of sales; unit quantities can be fractional. Both are operational approximations, not deployment-ready rules.
- Future prices are held at last observed values rather than using hindsight-realized prices. This may be wrong during promotions; it avoids one easy evaluation leak.
- One 28-day final test is a pilot backtest, not multi-season reliability. For a production decision, add several historical rolling cutoffs, confidence intervals, cost sensitivity and service-level stress tests.
- Original 38.95% RF WAPE is **not directly comparable** to the revised recursive horizon backtest. Results will differ.

## Reproduce on M5 source files

Download and unzip [Kaggle M5 Forecasting — Accuracy](https://www.kaggle.com/competitions/m5-forecasting-accuracy) or the [Zenodo M5 archive](https://zenodo.org/records/10203108), following their applicable terms. Put `calendar.csv`, `sell_prices.csv` and `sales_train_validation.csv` in `data/m5/`.

```bash
pip install -r requirements.txt
python -m pytest -q
python -m analysis.pipeline --data-dir data/m5 --output-dir dashboard/public/data --min-fill-rate 0.96
```

Or run the [notebook](Demand_Forecasting_Inventory_Planning.ipynb) from the repository root. The M5 data is large: plan for RAM and potentially minutes of training.

**Generated files:**

| File (`dashboard/public/data/`) | Interpretation |
|---|---|
| `results.json` | Dashboard inputs, final model scores, frozen policy + honest decision |
| `model_comparison_tuning.csv` | Model selection scores; NOT final test scores |
| `model_comparison_test.csv` | Descriptive accuracy on untouched final holdout |
| `policy_tuning_grid.csv` | All 22 policies tested for *validation-only* selection |
| `policy_selection.json` | Frozen chosen policy and final test decision |
| `policy_comparison.csv` | Fixed versus locked challenger on final holdout (or fixed alone) |
| `policy_test_diagnostics_NOT_FOR_SELECTION.csv` | Sensitivity check on test; NEVER use to reselect |
| `forecast_28d.csv` | Subsequent historical-window 28-day SKU/store forecast |
| `inventory_recommendations.csv` | **Illustrative**, simulated reorder suggestions |

## Dashboard

A typography-led, restrained React/Vite operations dashboard with interactive Recharts benchmarking, service-constrained tuning exploration, locked holdout decision, policy comparisons, risk tiers and CSV export.

```bash
cd dashboard
npm install
npm run dev
# npm run build   (production)
```

For **Vercel**, use repository `dashboard` as the Root Directory, Vite as the framework, and `dist` as build output. Commit the **recomputed** `dashboard/public/data/results.json` to publish the real backtest. You do not need a Python server after exporting the JSON.

The archived [standalone HTML preview](Dashboard_Preview.html) opens without Node and intentionally identifies the earlier evaluation as **legacy/unoptimized**; it does not magically update when running Python. The React site loads new JSON automatically.

**Design stack (used with restraint):** Lenis for anchor scrolling, GSAP for entrance/section reveals, React Bits-inspired CountUp for KPI transitions, Vanta NET for an isolated desktop hero accent and Recharts for precise analytic charts. Reduced-motion and mobile fallbacks are included. No distracting perpetual page-wide animations.

Repository URL referenced by dashboard: **https://github.com/manishk050/demand-forecasting-inventory-planning** (create/push the repository for the link to resolve).

## Structure

```text
analysis/pipeline.py                   # leakage-safe forecasting + simulation + optimization
tests/test_pipeline.py                # deterministic leakage, accounting, decision tests
Demand_Forecasting_Inventory_Planning.ipynb
dashboard/src/main.jsx                # interactive React UI
dashboard/src/styles.css              # editorial design system
dashboard/public/data/results.json    # ORIGINAL ARCHIVE until pipeline is rerun
Dashboard_Preview.html               # offline-openable original archive preview
docs/original_notebook_results.json   # kept separately for provenance
```

### Engineering verification

- 13 Python unit tests including chronological split, no actual future demand/price leak, lead-time demand summation, inventory in-transit, fill constraint and out-of-sample rejection.
- End-to-end smoke test of pipeline using a **small synthetic M5-shaped input**. Any numbers from this fixture are **not real M5 results** and are not published as business evidence.
- The M5 original CSVs were not included with the notebook upload. **A full-size M5 performance rerun is pending.**

## Next production steps

Connect real stock and PO data, validate supplier service, model stockout-censored demand, introduce order pack/minimums, include procurement and fulfillment costs, and backtest multiple 28-day origins before deployment.

---

Historical dataset: [M5 competition](https://www.kaggle.com/competitions/m5-forecasting-accuracy) · Project: [GitHub](https://github.com/manishk050/demand-forecasting-inventory-planning)
