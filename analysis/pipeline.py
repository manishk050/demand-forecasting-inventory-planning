"""Reproducible M5 forecasting + service-constrained inventory decision study.

Three disjoint periods: fit history, model/policy tuning (28 days), untouched test
(28 days). Inventory and lead times are synthetic; results are NOT ERP outcomes.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from xgboost import XGBRegressor

STORES = ('CA_1', 'TX_1', 'WI_1')
KEYS = ['item_id', 'store_id']
HORIZON = 28
FEATURES = [
    'lag_7', 'lag_14', 'lag_28', 'rolling_mean_7', 'rolling_mean_28',
    'day_of_week', 'month', 'week_of_year', 'is_weekend', 'sell_price',
    'price_change', 'snap_CA', 'snap_TX', 'snap_WI', 'has_event',
]
SAFETY_MULTIPLIERS = (0, .5, 1, 1.5, 2, 2.5, 3)
FORECAST_MULTIPLIERS = (.9, 1, 1.1)
MAX_LEAD_DAYS = 7
REVIEW_PERIOD_DAYS = 1


@dataclass(frozen=True)
class Config:
    data_dir: Path
    output_dir: Path = Path('dashboard/public/data')
    top_n: int = 75
    horizon: int = HORIZON
    min_fill_rate: float = 0.96
    random_state: int = 42


def wape(actual, predicted):
    a, p = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    denominator = np.abs(a).sum()
    return float(np.abs(a-p).sum()/denominator) if denominator else 0.0


def chronological_splits(data: pd.DataFrame, horizon: int = HORIZON):
    """Select disjoint fit, tuning and test windows. Never tune on test."""
    dates = pd.DatetimeIndex(sorted(data.date.unique()))
    if len(dates) < 2*horizon + 35:
        raise ValueError('Need at least 35 fit dates plus two 28-day holdouts.')
    tune_cutoff, test_cutoff = dates[-2*horizon], dates[-horizon]
    return (data[data.date < tune_cutoff].copy(),
            data[(data.date >= tune_cutoff) & (data.date < test_cutoff)].copy(),
            data[data.date >= test_cutoff].copy())


def load_m5(cfg: Config):
    if not 0 < cfg.min_fill_rate <= 1:
        raise ValueError('min_fill_rate must be between zero and one.')
    calendar = pd.read_csv(cfg.data_dir/'calendar.csv', parse_dates=['date'])
    prices = pd.read_csv(cfg.data_dir/'sell_prices.csv')
    sales = pd.read_csv(cfg.data_dir/'sales_train_validation.csv')
    sales = sales.loc[sales.store_id.isin(STORES)].copy()
    days = sorted((c for c in sales if c.startswith('d_')), key=lambda s:int(s[2:]))
    if len(days) < 2*cfg.horizon + 35:
        raise ValueError('M5 matrix has too few days for the fit/tune/test split.')
    # SKU selection restricted to the fit period, not tuning or final test.
    ranking = (sales.assign(fit_units=sales[days[:-2*cfg.horizon]].sum(axis=1))
               .groupby('item_id').fit_units.sum().nlargest(cfg.top_n).index)
    sales = sales.loc[sales.item_id.isin(ranking)]
    demand = sales.melt(id_vars=['item_id','dept_id','cat_id','store_id','state_id'],
                        value_vars=days, var_name='d', value_name='units_sold')
    demand = demand.merge(calendar[['d','date','wm_yr_wk','event_name_1',
                                    'snap_CA','snap_TX','snap_WI']], on='d',validate='many_to_one')
    demand = demand.merge(prices,on=['store_id','item_id','wm_yr_wk'],how='left',validate='many_to_one')
    if demand.date.isna().any() or demand.duplicated(KEYS+['date']).any():
        raise ValueError('Missing dates or duplicate item/store/day keys.')
    if (demand.units_sold < 0).any():
        raise ValueError('Negative sales are unsupported.')
    missing_price_sales = int((demand.sell_price.isna() & demand.units_sold.gt(0)).sum())
    if missing_price_sales:
        print(f'Warning: {missing_price_sales:,} sold rows without a matched price.')
    demand['sell_price'] = demand.sell_price.fillna(0)
    demand['units_sold'] = demand.units_sold.astype('float32')
    return demand.sort_values(KEYS+['date']).reset_index(drop=True), calendar, prices


def add_features(data):
    f = data.sort_values(KEYS+['date']).copy()
    g = f.groupby(KEYS,sort=False)
    for lag in (7,14,28):
        f[f'lag_{lag}'] = g.units_sold.shift(lag)
    for n in (7,28):
        f[f'rolling_mean_{n}'] = g.units_sold.transform(lambda x: x.shift(1).rolling(n).mean())
    f['day_of_week'] = f.date.dt.dayofweek
    f['month'] = f.date.dt.month
    f['week_of_year'] = f.date.dt.isocalendar().week.astype(int)
    f['is_weekend'] = (f.day_of_week >= 5).astype(int)
    f['price_change'] = g.sell_price.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan).fillna(0)
    f['has_event'] = f.event_name_1.notna().astype(int)
    return f.dropna(subset=['lag_28','rolling_mean_28'])


def candidate_models(seed=42):
    return {
        '7-Day Moving Average': None,
        'Linear Regression': LinearRegression(),
        'Random Forest': RandomForestRegressor(n_estimators=100,max_depth=15,
                        min_samples_leaf=5,n_jobs=-1,random_state=seed),
        'XGBoost': XGBRegressor(n_estimators=300,max_depth=6,learning_rate=.05,
                        subsample=.8,colsample_bytree=.8,objective='reg:squarederror',
                        n_jobs=-1,random_state=seed),
    }


def fit_models(history, seed=42):
    features = add_features(history)
    if features.empty:
        raise ValueError('Insufficient training data after 28-day lag features.')
    models = candidate_models(seed)
    for model in models.values():
        if model is not None:
            model.fit(features[FEATURES],features.units_sold)
    return models


def future_frame(history,calendar,dates):
    """Public calendar known ahead; hold sell prices at their last observed value.

    This avoids peeking at realized future M5 price data for both tuning and test.
    """
    dates = pd.DatetimeIndex(dates)
    items = history[['item_id','store_id']].drop_duplicates()
    cal = calendar.loc[calendar.date.isin(dates),['date','event_name_1',
                            'snap_CA','snap_TX','snap_WI']]
    if len(cal) != len(dates) or cal.date.nunique() != len(dates):
        raise ValueError('Calendar does not cover the required forecast dates.')
    last_prices = (history.sort_values('date').groupby(KEYS,sort=False)
                   .tail(1)[KEYS+['sell_price']])
    return (items.merge(cal,how='cross').merge(last_prices,on=KEYS,validate='many_to_one')
            .sort_values(['date']+KEYS).reset_index(drop=True))


def recursive_forecast(model,history,future):
    """No post-cutoff actual sales in any lag, rolling mean or price feature."""
    series = {(k[0],k[1]):[g.units_sold.to_numpy(float).tolist(),
                                g.sell_price.to_numpy(float).tolist()]
              for k,g in history.sort_values('date').groupby(KEYS,sort=False)}
    predictions=[]
    for day,frame in future.groupby('date',sort=True):
        rows = frame.copy()
        lagged=[]
        for r in rows.itertuples(index=False):
            h,p = series[(r.item_id,r.store_id)]
            if len(h) < 28:
                raise ValueError('Minimum history per store-SKU is 28 days.')
            change = (r.sell_price-p[-1])/p[-1] if p[-1] != 0 else 0
            lagged.append([h[-7],h[-14],h[-28],np.mean(h[-7:]),np.mean(h[-28:]),change])
        arr=np.asarray(lagged)
        for c,v in zip(('lag_7','lag_14','lag_28','rolling_mean_7',
                        'rolling_mean_28','price_change'),arr.T):
            rows[c]=v
        rows['day_of_week']=pd.Timestamp(day).dayofweek
        rows['month']=pd.Timestamp(day).month
        rows['week_of_year']=int(pd.Timestamp(day).isocalendar().week)
        rows['is_weekend']=int(pd.Timestamp(day).dayofweek>=5)
        rows['has_event']=rows.event_name_1.notna().astype(int)
        values=arr[:,3] if model is None else model.predict(rows[FEATURES])
        values=np.maximum(0,np.asarray(values,dtype=float))
        rows['predicted_demand']=values
        predictions.append(rows[['date']+KEYS+['predicted_demand']])
        for key,pr,price in zip(zip(rows.item_id,rows.store_id),values,rows.sell_price):
            series[key][0].append(float(pr))
            series[key][1].append(float(price))
    return pd.concat(predictions,ignore_index=True)


def forecast_models(models,history,calendar,forecast_dates,scoring_actuals):
    future=future_frame(history,calendar,forecast_dates)
    truth=scoring_actuals[KEYS+['date','units_sold']]
    ranking=[]
    forecasts={}
    for name,model in models.items():
        full=recursive_forecast(model,history,future)
        score=truth.merge(full,on=KEYS+['date'],validate='one_to_one')
        if len(score)!=len(truth):
            raise ValueError('Missing prediction during evaluation.')
        ranking.append({'model':name,'wape':wape(score.units_sold,score.predicted_demand),
                        'mae':float(mean_absolute_error(score.units_sold,score.predicted_demand))})
        forecasts[name]=full
    return pd.DataFrame(ranking).sort_values('wape').reset_index(drop=True),forecasts


def inventory_parameters(history,seed=42):
    """Reproducible synthetic conditions; same lead time per SKU across windows."""
    rng=np.random.default_rng(seed)
    g=history.sort_values('date').groupby(KEYS,sort=True)
    params=g.units_sold.agg(average_daily_demand='mean',demand_std='std').reset_index()
    params=params.merge(g.tail(7).groupby(KEYS).units_sold.sum().rename('starting_stock'),
                        on=KEYS,validate='one_to_one')
    params['lead_time_days']=rng.choice([3,5,7],len(params),p=[.3,.4,.3])
    params['holding_cost']=.02
    params['stockout_cost']=1.50
    params['demand_std']=params.demand_std.fillna(0)
    # Honest static base-stock benchmark: demand through lead time + daily review,
    # plus demand variability. Not a deliberately understocked straw-man.
    period=params.lead_time_days+REVIEW_PERIOD_DAYS
    params['fixed_target']=(params.average_daily_demand*period +
                            params.demand_std*np.sqrt(period)).clip(lower=0)
    return params


def simulate_policy(actuals,predictions,inventory,*,policy='forecast',z_score=0,
                    forecast_multiplier=1):
    """Daily order-up-to with on-order inventory, lead time & lost sales.

    Order at END of day t; arrival at START of t+lead_time.
    Forecast target sums days t+1..t+lead+1 (daily periodic review).
    Actual demand is NEVER used to choose an order, only to measure results.
    """
    if policy not in ('forecast','fixed'):
        raise ValueError('policy must be fixed or forecast')
    if z_score < 0 or forecast_multiplier <= 0:
        raise ValueError('Safety score cannot be negative; multiplier must be positive.')
    horizon_dates=set(pd.to_datetime(actuals.date))
    if actuals.duplicated(KEYS+['date']).any() or predictions.duplicated(KEYS+['date']).any():
        raise ValueError('Duplicate simulation keys.')
    values=actuals[KEYS+['date','units_sold']].merge(
        predictions[KEYS+['date','predicted_demand']],on=KEYS+['date'],
        validate='one_to_one',how='left')
    if values.predicted_demand.isna().any():
        raise ValueError('Every simulated date needs a forecast.')
    inputs=inventory.set_index(KEYS)
    records=[]
    for key,group in values.groupby(KEYS,sort=True):
        info=inputs.loc[key]
        on_hand=float(info.starting_stock)
        lead=int(info.lead_time_days)
        sigma=float(info.demand_std)
        outstanding=defaultdict(float)
        future=(predictions[(predictions.item_id==key[0]) &
                            (predictions.store_id==key[1])].set_index('date')
                            .predicted_demand.sort_index())
        for r in group.sort_values('date').itertuples(index=False):
            date=pd.Timestamp(r.date)
            on_hand+=outstanding.pop(date,0)
            actual=float(r.units_sold)
            served=min(on_hand,actual)
            on_hand-=served
            shortage=actual-served
            if policy=='fixed':
                target=float(info.fixed_target)
            else:
                next_days=pd.date_range(date+pd.Timedelta(days=1),periods=lead+1)
                if not set(next_days).issubset(future.index):
                    raise ValueError('Forecasts need lead time + review period lookahead.')
                target=(float(future.loc[next_days].sum())*forecast_multiplier+
                        z_score*sigma*np.sqrt(lead+1))
            in_transit=sum(outstanding.values())
            ordered=max(0.0,target-on_hand-in_transit)
            if ordered:
                outstanding[date+pd.Timedelta(days=lead)]+=ordered
            records.append({'date':date,'item_id':key[0],'store_id':key[1],
                 'policy':policy,'actual_demand':actual,'fulfilled':served,
                 'stockout_units':shortage,'ending_inventory':on_hand,
                 'order_qty':ordered,'holding_cost':on_hand*float(info.holding_cost),
                 'stockout_cost':shortage*float(info.stockout_cost)})
    return pd.DataFrame(records)


def summarize_policy(sim,label):
    demand=float(sim.actual_demand.sum())
    hold=float(sim.holding_cost.sum())
    loss=float(sim.stockout_cost.sum())
    shortage=float(sim.stockout_units.sum())
    return {'policy':label,'fill_rate':(1-shortage/demand if demand else 1.),
            'stockout_rate':float(sim.stockout_units.gt(0).mean()),
            'stockout_units':shortage,'average_inventory':float(sim.ending_inventory.mean()),
            'holding_cost':hold,'stockout_cost':loss,'total_inventory_cost':hold+loss,
            'total_ordered':float(sim.order_qty.sum())}


def evaluate_candidates(actuals,predictions,inventory,*,label):
    """Candidate metrics for ONE period, never selects using final test."""
    result=[]
    fixed=summarize_policy(simulate_policy(actuals,predictions,inventory,policy='fixed'),
                           'Fixed order-up-to baseline')
    result.append({**fixed,'strategy':'fixed','z_score':None,'forecast_multiplier':None,'period':label})
    for mult in FORECAST_MULTIPLIERS:
        for z in SAFETY_MULTIPLIERS:
            sim=simulate_policy(actuals,predictions,inventory,policy='forecast',
                                z_score=z,forecast_multiplier=mult)
            summary=summarize_policy(sim,f'Forecast ×{mult:g} / safety {z:g}')
            result.append({**summary,'strategy':'forecast','z_score':z,
                           'forecast_multiplier':mult,'period':label})
    return pd.DataFrame(result)


def choose_policy(validation_grid,required_fill):
    """Pick using validation ONLY; baseline is available but cannot be forced."""
    feasible=validation_grid[validation_grid.fill_rate >= required_fill].copy()
    if feasible.empty:
        return None
    # At equal cost and fill, prefer simpler fixed policy.
    feasible['tie_break']=feasible.strategy.eq('forecast').astype(int)
    return feasible.sort_values(['total_inventory_cost','tie_break','stockout_units']).iloc[0].to_dict()


def evaluate_selected(holdout,full_predictions,inventory,selection,required_fill):
    """Untouched test of fixed vs pre-chosen strategy. Never re-optimize here."""
    fixed=summarize_policy(simulate_policy(holdout,full_predictions,inventory,policy='fixed'),
                           'Fixed order-up-to baseline')
    result=[{**fixed,'strategy':'fixed','z_score':None,'forecast_multiplier':None}]
    if selection is not None and selection['strategy']=='forecast':
        chosen=summarize_policy(simulate_policy(
             holdout,full_predictions,inventory,policy='forecast',
             z_score=selection['z_score'],forecast_multiplier=selection['forecast_multiplier']),
             'Validation-selected forecast policy')
        result.append({**chosen,'strategy':'forecast','z_score':float(selection['z_score']),
                       'forecast_multiplier':float(selection['forecast_multiplier'])})
    reference=result[0]
    candidate=result[-1] if len(result)>1 else None
    passes_fill=candidate is not None and candidate['fill_rate'] >= required_fill
    passes_baseline=candidate is not None and candidate['fill_rate'] >= reference['fill_rate']
    saves_cost=candidate is not None and candidate['total_inventory_cost'] < reference['total_inventory_cost']
    approved=bool(passes_fill and passes_baseline and saves_cost)
    verdict=('Outperforms baseline on test' if approved else
             'No evidence to replace baseline on test')
    return result,{'status':verdict,'deployment_recommended':approved,
                   'minimum_fill_rate':required_fill,'passes_service_floor':bool(passes_fill),
                   'matches_or_exceeds_baseline_fill':bool(passes_baseline),
                   'lowers_modeled_cost':bool(saves_cost),
                   'selected_on':'validation only','evaluated_on':'untouched 28-day test'}


def inventory_recommendations(prediction,inventory,*,policy=None):
    """Forward planning signals from synthetic on-hand inventory, not live POs."""
    opts=policy or {}
    strategy=opts.get('strategy','forecast') if policy else 'fixed'
    if strategy not in ('forecast','fixed'):
        raise ValueError('Recommendations must use forecast or fixed policy.')
    z=float(opts.get('z_score') or 0)
    factor=float(opts.get('forecast_multiplier') or 1)
    grouped={key:g.sort_values('date') for key,g in prediction.groupby(KEYS)}
    records=[]
    for p in inventory.itertuples(index=False):
        series=grouped[(p.item_id,p.store_id)].predicted_demand
        lead=int(p.lead_time_days)
        if len(series)<lead+1:
            raise ValueError('Need enough future days for reorder planning')
        if strategy == 'fixed':
            expected=float(p.average_daily_demand)*(lead+1)
            target=float(p.fixed_target)
            safety=max(0.,target-expected)
        else:
            expected=float(series.iloc[:lead+1].sum())*factor
            safety=z*float(p.demand_std)*np.sqrt(lead+1)
            target=expected+safety
        # In a real system, use observed on-hand + on-order POs instead.
        quantity=max(0.,target-float(p.starting_stock))
        risk='High' if p.starting_stock < expected else ('Medium' if p.starting_stock < target else 'Low')
        records.append({'item_id':p.item_id,'store_id':p.store_id,'policy_strategy':strategy,
                        'simulated_on_hand':float(p.starting_stock),
                        'lead_time_days':lead,'lead_plus_review_demand':expected,
                        'safety_stock':safety,'target_inventory_position':target,
                        'illustrative_order_qty':quantity,'risk':risk})
    return pd.DataFrame(records)


def dates_with_lookahead(calendar,start_date,number_days):
    dates=pd.DatetimeIndex(sorted(calendar.loc[calendar.date >= start_date,'date'].unique()))
    needed=number_days+MAX_LEAD_DAYS+REVIEW_PERIOD_DAYS
    if len(dates)<needed:
        raise ValueError(f'Need {needed} calendar dates for {number_days}-day simulation + lookahead.')
    return dates[:needed]


def run(cfg: Config):
    demand,calendar,_=load_m5(cfg)
    fit,tuning,test=chronological_splits(demand,cfg.horizon)
    # First 28 days are used to select the model and the safety strategy.
    model_fit=fit_models(fit,cfg.random_state)
    tuning_dates=dates_with_lookahead(calendar,tuning.date.min(),cfg.horizon)
    tune_scores,tune_forecasts=forecast_models(model_fit,fit,calendar,tuning_dates,tuning)
    champion=tune_scores.iloc[0]['model']
    tune_params=inventory_parameters(fit,cfg.random_state)
    tuning_grid=evaluate_candidates(tuning,tune_forecasts[champion],tune_params,label='tuning')
    required_fill=cfg.min_fill_rate
    selected=choose_policy(tuning_grid,required_fill)

    # The final 28-day test remains untouched until model and policy are fixed.
    pretest=pd.concat([fit,tuning],ignore_index=True)
    test_models=fit_models(pretest,cfg.random_state)
    test_dates=dates_with_lookahead(calendar,test.date.min(),cfg.horizon)
    test_scores,test_forecasts=forecast_models(test_models,pretest,calendar,test_dates,test)
    test_params=inventory_parameters(pretest,cfg.random_state)
    test_policies,decision=evaluate_selected(test,test_forecasts[champion],test_params,
                                             selected,required_fill)
    # Diagnostic grids are permitted on the test window but MUST NOT choose the policy.
    test_sweep=evaluate_candidates(test,test_forecasts[champion],test_params,label='diagnostic_only')
    test_sweep['eligible_for_selection']=False

    # Produce new 28-day ahead forecast, independent of the historical test.
    complete_models=fit_models(demand,cfg.random_state)
    next_dates=pd.DatetimeIndex(sorted(calendar.loc[calendar.date > demand.date.max(),'date'].unique()))[:cfg.horizon]
    if len(next_dates)!=cfg.horizon:
        raise ValueError('Missing 28 future M5 calendar days.')
    next_prediction=recursive_forecast(complete_models[champion],demand,
                                      future_frame(demand,calendar,next_dates))
    # Never recommend orders from a policy that failed the untouched test.
    selected_opts=(selected if selected and selected['strategy']=='forecast'
                   and decision['deployment_recommended'] else None)
    recommendations=inventory_recommendations(next_prediction,
                                  inventory_parameters(demand,cfg.random_state),policy=selected_opts)
    selection_summary=({'strategy':selected['strategy'],'policy':selected['policy'],
                        'z_score':selected['z_score'],'forecast_multiplier':selected['forecast_multiplier'],
                        'tuning_fill_rate':selected['fill_rate'],
                        'tuning_cost':selected['total_inventory_cost']} if selected else None)
    benchmark=test_policies[0]
    challenger=test_policies[1] if len(test_policies)>1 else None
    delta=((benchmark['total_inventory_cost']-challenger['total_inventory_cost']) /
            benchmark['total_inventory_cost']) if challenger and benchmark['total_inventory_cost'] else None
    # A selected fixed baseline means the tuned decision IS to retain baseline.
    if selected is None:
        reason='No tuning candidate met the service floor.'
    elif selected['strategy']=='fixed':
        reason='Fixed baseline was cheapest among the tuning-feasible candidates.'
    elif decision['deployment_recommended']:
        reason='Selected forecast policy beat baseline cost and service on untouched test.'
    else:
        reason='Selected forecast policy did not clear all final-test cost and service gates.'
    decision['reason']=reason
    out=cfg.output_dir
    out.mkdir(parents=True,exist_ok=True)
    tune_scores.to_csv(out/'model_comparison_tuning.csv',index=False)
    test_scores.to_csv(out/'model_comparison_test.csv',index=False)
    tuning_grid.to_csv(out/'policy_tuning_grid.csv',index=False)
    test_sweep.to_csv(out/'policy_test_diagnostics_NOT_FOR_SELECTION.csv',index=False)
    pd.DataFrame(test_policies).to_csv(out/'policy_comparison.csv',index=False)
    next_prediction.to_csv(out/'forecast_28d.csv',index=False)
    recommendations.to_csv(out/'inventory_recommendations.csv',index=False)
    (out/'policy_selection.json').write_text(json.dumps({
        'selected_policy':selection_summary,'test_decision':decision},indent=2),encoding='utf-8')
    result={'meta':{'source':'Recomputed from M5 source files — chronological validation and untouched test',
            'validation':'fit / 28-day tuning / untouched 28-day test',
            'as_of':str(demand.date.max().date()),'horizon_days':cfg.horizon,
            'sample_skus':int(demand.item_id.nunique()),
            'store_product_pairs':int(demand[KEYS].drop_duplicates().shape[0]),
            'champion':champion,'required_fill_rate':required_fill,
            'recommendation_strategy':('forecast' if selected_opts else 'fixed'),
            'fit_end':str(fit.date.max().date()),'tuning_start':str(tuning.date.min().date()),
            'tuning_end':str(tuning.date.max().date()),'test_start':str(test.date.min().date()),
            'test_end':str(test.date.max().date()),
            'assumptions':'All on-hand inventory, lead times, holding costs, and stockout costs are simulated. Sales are a proxy for demand; future prices held at cutoff levels. No production claims.',
            'github_url':'https://github.com/manishk050/demand-forecasting-inventory-planning'},
            'models':test_scores.to_dict('records'),
            'models_tuning':tune_scores.to_dict('records'),
            'policies':test_policies,'decision':decision,
            'selected_policy':selection_summary,
            'cost_delta_fraction':delta,
            'risk':recommendations.risk.value_counts().to_dict(),
            'tuning_frontier':tuning_grid[['policy','strategy','z_score','forecast_multiplier',
                             'fill_rate','total_inventory_cost']].replace({np.nan:None}).to_dict('records'),
            'states':[]}
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,default=Path('dashboard/public/data'))
    parser.add_argument('--top-n',type=int,default=75)
    parser.add_argument('--min-fill-rate',type=float,default=.96)
    a=parser.parse_args()
    print(json.dumps(run(Config(data_dir=a.data_dir,output_dir=a.output_dir,
                                top_n=a.top_n,min_fill_rate=a.min_fill_rate)),indent=2))
