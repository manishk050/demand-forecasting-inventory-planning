"""Deterministic tests of data boundaries, policy accounting and decision rules."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis.pipeline import (
    wape, add_features, future_frame, recursive_forecast, chronological_splits,
    simulate_policy, summarize_policy, choose_policy, evaluate_selected,
    inventory_recommendations, inventory_parameters,
)


def make_history(n=100, start='2016-01-01'):
    dates=pd.date_range(start,periods=n)
    return pd.DataFrame({'date':dates,'item_id':['A']*n,'store_id':['CA_1']*n,
         'units_sold':np.arange(n,dtype=float),'sell_price':[3.0]*n,
         'event_name_1':[None]*n,'snap_CA':[0]*n,'snap_TX':[0]*n,'snap_WI':[0]*n})


def make_case(demand=(10,10,10), pred=(10,10,10,10,10,10,10), lead=2, start=0):
    dates=pd.date_range('2016-03-01',periods=len(demand))
    val=pd.DataFrame({'date':dates,'item_id':'A','store_id':'CA_1','units_sold':demand})
    fc=pd.DataFrame({'date':pd.date_range('2016-03-01',periods=len(pred)),
                     'item_id':'A','store_id':'CA_1','predicted_demand':pred})
    inv=pd.DataFrame({'item_id':['A'],'store_id':['CA_1'],
               'starting_stock':[start],'lead_time_days':[lead],
               'holding_cost':[.02],'stockout_cost':[1.5],
               'demand_std':[0.], 'average_daily_demand':[5.], 'fixed_target':[20.]})
    return val,fc,inv


def test_wape_and_zero():
    assert wape([10,20],[9,19]) == 2/30
    assert wape([0,0],[0,0]) == 0


def test_features_exclude_today_and_tomorrow():
    featured=add_features(make_history(90))
    row=featured.iloc[0]
    assert row.units_sold==28 and row.lag_7==21 and row.lag_14==14
    assert row.lag_28==0 and row.rolling_mean_7==np.mean(range(21,28))


def test_splits_disjoint_and_consecutive():
    f,t,e=chronological_splits(make_history(100))
    assert len(t)==len(e)==28 and len(f)==44
    assert f.date.max() < t.date.min() and t.date.max() < e.date.min()
    with pytest.raises(ValueError):
        chronological_splits(make_history(80))


def test_future_prices_frozen_at_cutoff():
    history=make_history(60)
    future_days=pd.date_range(history.date.max()+pd.Timedelta(days=1),periods=3)
    calendar=pd.DataFrame({'date':future_days,'event_name_1':[None]*3,
                          'snap_CA':[0]*3,'snap_TX':[0]*3,'snap_WI':[0]*3})
    frame=future_frame(history,calendar,future_days)
    assert frame.sell_price.tolist()==[3.,3.,3.]
    assert 'units_sold' not in frame.columns
    pred=recursive_forecast(None,history,frame)
    assert len(pred)==3 and pred.predicted_demand.notna().all()


def test_simulator_never_reorders_in_transit_inventory():
    actuals,fc,inv=make_case(demand=(0,0,0,0,0),pred=(10,)*10,lead=3)
    result=simulate_policy(actuals,fc,inv,policy='forecast',z_score=0)
    assert result.order_qty.iloc[0]==40
    assert result.order_qty.iloc[1]==0
    assert result.order_qty.iloc[2]==0
    assert result.ending_inventory.iloc[3]==40
    assert summarize_policy(result,'check')['fill_rate']==1


def test_forecast_uses_next_lead_plus_review_days_not_one_day_times_lead():
    actuals,fc,inv=make_case(demand=(0,),pred=(100,1,2,3,4),lead=2)
    sim=simulate_policy(actuals,fc,inv,policy='forecast',z_score=0)
    # At end of day 0, replenishment covers days 1,2,3 = 1+2+3.
    assert sim.order_qty.iloc[0]==6


def test_nonnegativity_conservation_and_cost_breakdown():
    val,fc,inv=make_case(demand=(10,8,3,5),pred=(6,)*10,lead=2,start=0)
    sim=simulate_policy(val,fc,inv,policy='forecast',z_score=1.)
    np.testing.assert_allclose(sim.actual_demand,sim.fulfilled+sim.stockout_units)
    assert (sim.ending_inventory >= 0).all()
    assert (sim.order_qty >= 0).all()
    metrics=summarize_policy(sim,'run')
    assert abs(metrics['total_inventory_cost']-metrics['holding_cost']-metrics['stockout_cost'])<1e-8


def test_simulator_rejects_missing_lookahead():
    val,fc,inv=make_case(demand=(0,0,0),pred=(3,)*3,lead=2)
    with pytest.raises(ValueError,match='lookahead'):
        simulate_policy(val,fc,inv,policy='forecast')


def test_choose_policy_only_feasible_and_no_forced_success():
    grid=pd.DataFrame([
        {'strategy':'fixed','policy':'Fixed','fill_rate':.965,'total_inventory_cost':120.,'z_score':None,'forecast_multiplier':None,'stockout_units':8},
        {'strategy':'forecast','policy':'cheap','fill_rate':.92,'total_inventory_cost':80.,'z_score':0.,'forecast_multiplier':.9,'stockout_units':20},
        {'strategy':'forecast','policy':'safe','fill_rate':.97,'total_inventory_cost':115.,'z_score':2.,'forecast_multiplier':1.,'stockout_units':7},
    ])
    chosen=choose_policy(grid,.96)
    assert chosen['policy']=='safe'
    assert choose_policy(grid,.99) is None


def test_held_out_failure_vetoes_validation_selection():
    val,fc,inv=make_case(demand=(10,10,10),pred=(2,)*10,lead=2,start=0)
    selected={'strategy':'forecast','z_score':0.,'forecast_multiplier':1.}
    policies,decision=evaluate_selected(val,fc,inv,selected,.96)
    assert len(policies)==2
    assert not decision['deployment_recommended']
    assert decision['selected_on']=='validation only'


def test_recommendations_and_risk_are_simulated():
    _,fc,inv=make_case(demand=(0,),pred=(5,5,5,5,5),lead=2,start=4)
    result=inventory_recommendations(fc,inv,policy={'z_score':0,'forecast_multiplier':1})
    assert result.risk.iloc[0]=='High'
    assert result.illustrative_order_qty.iloc[0]==11
    assert result.target_inventory_position.iloc[0]==15


def test_steady_demand_fixed_baseline_has_lead_aware_stock_target():
    history=make_history(100).assign(units_sold=10.)
    inv=inventory_parameters(history)
    assert inv.fixed_target.iloc[0]==10*(inv.lead_time_days.iloc[0]+1)


def test_rejected_forecast_does_not_drive_default_reorder_recommendations():
    _,fc,inv=make_case(demand=(0,),pred=(50,50,50,50,50),lead=2,start=4)
    result=inventory_recommendations(fc,inv)
    assert result.policy_strategy.iloc[0]=='fixed'
    assert result.target_inventory_position.iloc[0]==20
    assert result.illustrative_order_qty.iloc[0]==16
