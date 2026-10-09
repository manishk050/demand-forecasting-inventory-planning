import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';
import * as THREE from 'three';
import CountUp from './components/CountUp.jsx';
import './styles.css';

gsap.registerPlugin(ScrollTrigger);

const PROJECT_URL = 'https://github.com/manishk050/demand-forecasting-inventory-planning';
const fmt = (num, max=0) => Number(num ?? 0).toLocaleString('en-US',{maximumFractionDigits:max});
const pct = value => `${(Number(value ?? 0)*100).toFixed(2)}%`;
const pp = value => `${(Number(value ?? 0)*100).toFixed(2)} pp`;
const miniMoney = value => fmt(value,0);
const isArchive = data => (data?.meta?.source || '').startsWith('Archived');

function Arrow({ angled=false }) {
  return <span aria-hidden="true" className="link-arrow">{angled?'↗':'→'}</span>;
}
function Header({ data }) {
  const nav = [['#overview','Overview'], ['#models','Forecasting'], ['#policies','Inventory'], ['#risk','Risk'], ['#lab','Decision lab']];
  return <aside className="sidebar">
    <a className="brand" href="#overview" aria-label="Supply Demand dashboard home">
      <span className="brand-mark" aria-hidden="true"><i/><i/><i/></span>
      <span>SUPPLY<span className="brand-dot">.</span>DEMAND<small>OPERATIONS RESEARCH</small></span>
    </a>
    <div className="nav-label">WORKSPACE / 01</div>
    <nav aria-label="Dashboard sections">{nav.map(([url,label],i)=><a key={url} href={url} className={i===0?'nav-first':''}><span className="nav-index">0{i+1}</span>{label}<span className="nav-arrow">↗</span></a>)}</nav>
    <div className="sidebar-bottom">
      <span className="tiny-pill"><span className="live-dot"/>{isArchive(data)?'ARCHIVED RUN':'RECOMPUTED'}</span>
      <div className="sidebar-bottom-desc">M5 forecasting case study<br/>Historical retail data · 2011–2016</div>
      <a href={PROJECT_URL} target="_blank" rel="noopener noreferrer" className="side-repo">View project repository <Arrow angled/></a>
    </div>
  </aside>;
}
function Kpi({label,value,sub,prefix='',suffix='',decimals=0,featured=false}) {
 return <article className={`kpi ${featured?'kpi-featured':''}`}>
  <div className="kpi-top"><span>{label}</span><span className="kpi-top-icon">↗</span></div>
  <div className="kpi-value">{value===null?"—":<CountUp value={value} prefix={prefix} suffix={suffix} decimals={decimals}/>}</div>
  <div className="kpi-sub">{sub}</div>
 </article>;
}
function CardHead({eyebrow,heading,aside}) { return <div className="card-head"><div><span className="section-kicker">{eyebrow}</span><h3>{heading}</h3></div>{aside && <div className="card-head-aside">{aside}</div>}</div> }
const tooltipStyle={border:'1px solid #e2e3dd', background:'#fff', borderRadius:4, boxShadow:'0 12px 25px #15231b10', color:'#24342d',fontFamily:'IBM Plex Mono',fontSize:11};
function ModelPerformance({data}) {
 const [measure, setMeasure] = useState('wape');
 const models = [...(data.models||[])].sort((a,b)=>a[measure]-b[measure]);
 const winner = (data.models||[]).find(m=>m.model===data.meta?.champion) || [...(data.models||[])].sort((a,b)=>a.wape-b.wape)[0];
 return <section id="models" className="section-block reveal">
  <div className="section-title-row"><div><span className="section-no">01 / FORECAST INTELLIGENCE</span><h2>Choosing the signal.</h2></div><p>Four forecasting approaches, evaluated with identical chronological windows and no post-cutoff actual demand in recursive features.</p></div>
  <div className="two-col model-grid">
   <article className="panel chart-panel">
    <CardHead eyebrow="MODEL BENCHMARK" heading="Error comparison" aside={<div className="seg-control" role="group" aria-label="Forecast error measure"><button type="button" aria-pressed={measure==='wape'} className={measure==='wape'?'on':''} onClick={()=>setMeasure('wape')}>WAPE</button><button type="button" aria-pressed={measure==='mae'} className={measure==='mae'?'on':''} onClick={()=>setMeasure('mae')}>MAE</button></div>}/>
    <div className="chart-wrap" aria-label={`Bar chart comparing model ${measure}`}>
     <ResponsiveContainer width="100%" height={265}>
      <BarChart data={models} layout="vertical" margin={{top:10,right:54,bottom:4,left:6}} barSize={20}>
       <CartesianGrid stroke="#ebece7" horizontal={false}/>
       <XAxis type="number" axisLine={false} tickLine={false} tick={{fill:'#85918b',fontSize:11}} domain={[0,'auto']} tickFormatter={v=>measure==='wape'?`${(v*100).toFixed(0)}%`:v.toFixed(1)}/>
       <YAxis type="category" dataKey="model" width={123} axisLine={false} tickLine={false} tick={{fill:'#435249',fontFamily:'DM Sans',fontSize:12}}/>
       <Tooltip contentStyle={tooltipStyle} formatter={v=>[measure==='wape'?pct(v):fmt(v,3),measure.toUpperCase()]} cursor={{fill:'#faf9f5'}} />
       <Bar dataKey={measure} radius={[0,3,3,0]} label={{position:'right',formatter:v=>measure==='wape'?`${(v*100).toFixed(1)}%`:v.toFixed(2),fontSize:11,fill:'#263b32',fontFamily:'IBM Plex Mono'}}>
        {models.map((row,i)=><Cell key={row.model} fill={row.model===winner.model?'#276b56':'#bfc8bf'}/>)}</Bar>
      </BarChart>
     </ResponsiveContainer>
    </div>
    <div className="panel-foot"><span className="legend-green"/> Lower is better <span className="foot-spacer"/> Source: model validation outputs</div>
   </article>
   <article className="panel insight-panel">
    <CardHead eyebrow="MODEL SELECTION" heading="The decision" />
    <div className="insight-winner"><div className="insight-badge">{isArchive(data)?"BEST ARCHIVED WAPE":"CHOSEN ON TUNING · TEST WAPE SHOWN"}</div><div className="insight-winner-name">{winner.model}</div><div className="winner-metric">{pct(winner.wape)}<span>weighted absolute percentage error</span></div></div>
    <div className="insight-note"><span className="insight-rule"/>The baseline is {pct((data.models||[]).find(x=>x.model.includes('Moving'))?.wape)} WAPE. Compare forecast error with inventory decisions: the lowest WAPE need not yield the best stock policy.</div>
    <div className="method-inline"><span>VALIDATION TYPE</span><strong>{isArchive(data)?'Rolling lagged / original notebook':'28-day untouched test / model chosen earlier'}</strong></div>
   </article>
  </div>
 </section>
}
function PolicyOutcomes({data}) {
 const [chosen,setChosen] = useState(0);
 const archived=isArchive(data);
 const policies = data.policies || [];
 const baseline=policies[0];
 const alternative=policies.length>1?policies[1]:null;
 const compared=alternative || baseline;
 const delta=alternative&&baseline?.total_inventory_cost?(baseline.total_inventory_cost-alternative.total_inventory_cost)/baseline.total_inventory_cost:0;
 const service=alternative?alternative.fill_rate-baseline.fill_rate:0;
 const approved=!archived && Boolean(data.decision?.deployment_recommended);
 const rejected=!archived && !approved;
 const ordered=alternative?[baseline,alternative]:[baseline];
 const active=ordered[chosen]||baseline;
 return <section id="policies" className="section-block reveal">
  <div className="section-title-row"><div><span className="section-no">02 / INVENTORY ECONOMICS</span><h2>Does it actually help?</h2></div><p>Cost is only a win when the service-level test passes. The policy was chosen before its final evaluation.</p></div>
  <div className={`decision-alert ${approved?'passed':rejected?'failed':'legacy'}`}>
    <div><span className="decision-label">{archived?'ARCHIVED STUDY / NOT A DECISION':approved?'HOLDOUT DECISION / PASSED':'HOLDOUT DECISION / NOT CLEARED'}</span>
      <h3>{archived?'The original forecast policy sacrificed availability.':approved?'Lower cost, with service preserved on test.':data.decision?.reason||'Keep the fixed-stock baseline.'}</h3>
      <p>{archived?'These are the original notebook results. The revised forecast and policy optimizer have not been run on the full M5 files yet. The figures below are historical findings, not the optimized result.':data.decision?.reason}</p>
    </div><div className="decision-symbol">{approved?'✓':archived?'!':'×'}</div>
  </div>
  {alternative && <div className="tradeoff-banner"><div className="tradeoff-icon">↘</div><div><span>MODELED COST DELTA</span><strong>{delta>=0?'-':'+'}{fmt(Math.abs(delta*100),2)}%</strong><small>{delta>=0?'lower':'higher'} cost vs baseline</small></div><div className="tradeoff-divider"/><div><span>FILL RATE DELTA</span><strong>{service>=0?'+':''}{pp(service)}</strong><small>challenger minus baseline</small></div><p>{archived?'Original result is NOT an improvement in service.':approved?'Validated on the untouched 28-day test only.':'Do not adopt a lower-cost policy if it fails service or baseline comparison.'}</p></div>}
  <div className="two-col policy-grid">
   <article className="panel"><CardHead eyebrow="COST & SERVICE" heading="Side-by-side comparison" aside={<span className="tiny-grey">{archived?'LEGACY SIMULATION':'UNTOUCHED HOLDOUT'}</span>}/>
    <div className="compare-metrics">{['total_inventory_cost','fill_rate','average_inventory','stockout_units'].map((metric,i)=><div className="compare-row" key={metric}>
     <div className="compare-row-head"><span>{['Total modeled cost','Demand fill rate','Average on-hand inventory','Unfulfilled units'][i]}</span><span className="mini-muted">{metric==='fill_rate'?'HIGHER BETTER':'LOWER BETTER'}</span></div>
     {ordered.map((item,j)=><div key={`${metric}-${j}`} className="compare-line"><span className="compare-policy-label">{j===0?'BASELINE':'CHALLENGER'}</span><div className="compare-track"><div style={{width:`${Math.max(1,(item[metric]||0)/Math.max(1,...ordered.map(x=>x[metric]||0))*100)}%`}} className={`compare-fill compare-fill-${j}`}/></div><strong>{metric==='fill_rate'?pct(item[metric]):fmt(item[metric],metric==='average_inventory'?1:0)}</strong></div>)}
    </div>)}</div>
   </article>
   <article className="panel policy-details"><CardHead eyebrow="SIMULATION DETAILS" heading="Inspect a strategy" />
    <div className="policy-tabs" role="group" aria-label="Choose policy">{ordered.map((item,i)=><button key={item.policy} type="button" aria-pressed={chosen===i} className={chosen===i?'active':''} onClick={()=>setChosen(i)}>{i===0?'Baseline':'Forecast + safety'}</button>)}</div>
    <div className="selected-policy"><div className="selected-policy-label">{active?.policy}</div><div className="selected-policy-number">{pct(active?.fill_rate)}<span>fill rate</span></div></div>
    <div className="stat-list"><div><span>Average inventory</span><b>{fmt(active?.average_inventory,1)} units</b></div><div><span>Stockout incidence</span><b>{pct(active?.stockout_rate)}</b></div><div><span>Lost sales proxy</span><b>{fmt(active?.stockout_units,0)} units</b></div><div><span>Modeled cost</span><b>{fmt(active?.total_inventory_cost,0)} units</b></div></div>
    <div className="note-strip">All on-hand quantities, lead times and cost units are simulated, not real financial savings.</div>
   </article>
  </div>
 </section>;
}
function RiskSection({data}) {
 const risks=['High','Medium','Low'].map((label)=>({label,count:Number(data.risk?.[label]||0)}));
 const total=risks.reduce((s,r)=>s+r.count,0)||1;
 const [selectedRegion,setSelectedRegion] = useState(data.states?.[0]?.state || 'California');
 const states=data.states||[];
 const totalUnits=states.reduce((s,r)=>s+r.units,0);
 return <section id="risk" className="section-block reveal">
  <div className="section-title-row"><div><span className="section-no">03 / REPLENISHMENT PRIORITIES</span><h2>Where to intervene.</h2></div><p>Planning signals translate forecasts into a prioritized list of potential stock risks.</p></div>
  <div className="two-col risk-grid">
   <article className="panel">
    <CardHead eyebrow="INVENTORY EXPOSURE" heading="Stock risk distribution" aside={<span className="tiny-grey">{fmt(total)} PAIRS</span>}/>
    <div className="risk-stacked" aria-label="Inventory risk levels">{risks.map(r=><div key={r.label} style={{width:`${r.count/total*100}%`}} className={`risk-segment risk-${r.label.toLowerCase()}`} title={`${r.label}: ${r.count}`}/>)}</div>
    <div className="risk-rows">{risks.map(r=><div key={r.label}><span className={`risk-color risk-${r.label.toLowerCase()}`}/><span>{r.label} risk</span><b>{r.count}</b><em>{fmt(r.count/total*100,1)}%</em></div>)}</div>
    <p className="small-note">Risk = relationship between available stock, expected lead-time demand, and the safety-stock threshold. Stock quantities are simulated.</p>
   </article>
   <article className="panel region-panel">
    <CardHead eyebrow="HISTORICAL FOOTPRINT" heading={states.length?'Unit sales by state':'Source coverage'} />
    {states.length?<><div className="region-bars">{states.map(s=><button type="button" key={s.state} className={`region-item ${selectedRegion===s.state?'selected':''}`} onClick={()=>setSelectedRegion(s.state)} aria-pressed={selectedRegion===s.state}>
      <span className="region-title"><strong>{s.state}</strong><span>{fmt(s.units)} units</span></span><span className="region-track"><i style={{width:`${s.units/totalUnits*100}%`}}/></span>
    </button>)}</div><div className="region-selected">{selectedRegion.toUpperCase()} <span>historical share</span> <strong>{fmt(states.find(s=>s.state===selectedRegion)?.units/totalUnits*100,1)}%</strong></div></>:
    <div className="no-region">Store-level historical rollups are not included in this results export. Recompute from M5 to obtain SKU-level forecast and inventory CSVs.</div>}
   </article>
  </div>
 </section>
}
function DecisionLab({data}) {
 const originalFloor=(data.meta?.required_fill_rate??.96)*100;
 const [target,setTarget]=useState(originalFloor);
 const grid=data.tuning_frontier||[];
 const isLegacy=isArchive(data);
 const eligible=grid.filter(p=>p.fill_rate*100>=target).sort((a,b)=>a.total_inventory_cost-b.total_inventory_cost);
 const hypothetical=eligible[0];
 const audit=data.decision;
 return <section id="lab" className="section-block reveal">
  <div className="section-title-row"><div><span className="section-no">04 / VALIDATION LAB</span><h2>Choose the service floor.</h2></div><p>Tune only on historical validation, lock the candidate, then judge it on a separate holdout.</p></div>
  <div className="audit-steps"><div><span>01 · FIT</span><b>Build demand forecasts</b><small>Only earlier history is visible</small></div><div><span>02 · TUNE</span><b>Choose safety stock</b><small>Meet the minimum fill rate</small></div><div><span>03 · TEST</span><b>Keep or reject</b><small>Holdout must beat baseline</small></div></div>
  <div className="lab-grid">
   <article className="lab-controls"><div className="lab-eyebrow">SCENARIO / EXPLORATORY</div><h3>Minimum fill-rate requirement</h3>
    <div className="slider-value">{target.toFixed(1)}<span>%</span></div>
    <input aria-label="Minimum fill rate to inspect tuning scenarios" type="range" min="90" max="99.5" step="0.5" value={target} onChange={e=>setTarget(Number(e.target.value))} disabled={isLegacy}/>
    <div className="range-labels"><span>90%</span><span>94.5%</span><span>99.5%</span></div>
    <div className="lab-caption">{isLegacy?'Run the new M5 pipeline to generate real tuning candidates. Historical notebook policies are not substitutes for an optimizer.':'This slider filters the RECORDED tuning simulations only. It does not retrain the model or change the policy already tested. Test results below are locked to the originally selected service floor.'}</div>
   </article>
   <article className="lab-result"><span className="lab-eyebrow">{isLegacy?'AWAITING REAL-DATA OPTIMIZATION':'VALIDATION-ONLY EXPLORATION'}</span>
    <div className="result-heading">{isLegacy?'No optimization results yet':hypothetical?'Lowest-cost tuning-feasible policy':'No feasible tuning policy'}</div>
    <div className="result-policy">{isLegacy?'Run the pipeline with M5 CSV files':hypothetical?.policy||'Do not lower the service requirement without a business decision'}</div>
    <div className="result-metrics"><div><span>TUNING FILL</span><strong>{hypothetical?pct(hypothetical.fill_rate):'—'}</strong></div><div><span>TUNING COST</span><strong>{hypothetical?fmt(hypothetical.total_inventory_cost,0):'—'}</strong></div></div>
    <div className="eligible-count">{isLegacy?'No candidates have been evaluated under the revised protocol.':`${eligible.length} of ${grid.length} policies meet this exploratory validation floor.`}</div>
   </article>
  </div>
  {!isLegacy && <div className="holdout-row"><div><span className="lab-eyebrow">LOCKED TEST VERDICT</span><b>{audit?.status||'Not evaluated'}</b></div><p>{audit?.reason} Required fill ≥ {pct(audit?.minimum_fill_rate)}. Observed test results must also match baseline availability and improve modeled cost to pass.</p></div>}
 </section>;
}
function downloadCsv(data) {
 const columns=['policy','fill_rate','stockout_rate','stockout_units','average_inventory','total_inventory_cost'];
 const rows=[columns,...data.policies.map(p=>columns.map(k=>p[k]))];
 const csv=rows.map(row=>row.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',')).join('\n');
 const a=document.createElement('a'); const href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));
 a.href=href; a.download='inventory_policy_comparison.csv'; a.click(); URL.revokeObjectURL(href);
}
function Footer({data}) {return <section className="methodology reveal" id="methods">
 <span className="section-no">05 / SOURCE & METHOD</span><div className="method-cols"><div><h2>Built for decisions.<br/>Clear about assumptions.</h2><p>This portfolio study uses the historical M5 forecasting dataset. All inventory, lead times and cost outcomes are simulated. The dashboard is not connected to any retailer's operating system.</p></div><div className="method-right"><dl><div><dt>DATA SOURCE</dt><dd>M5 Forecasting — Accuracy competition</dd></div><div><dt>FORECAST WINDOW</dt><dd>{data.meta?.forecast_period || `28 days beyond ${data.meta?.as_of || 'the training cutoff'}`}</dd></div><div><dt>VALIDATION</dt><dd>{isArchive(data)?'Archived original rolling-lag evaluation':'Leakage-safe recursive 28-day validation'}</dd></div><div><dt>PROVENANCE</dt><dd>{data.meta?.source}</dd></div></dl></div></div>
 <div className="footer-links"><a href={PROJECT_URL} rel="noopener noreferrer" target="_blank">GitHub repository <Arrow angled/></a><a href="https://www.kaggle.com/competitions/m5-forecasting-accuracy" rel="noopener noreferrer" target="_blank">M5 dataset <Arrow angled/></a><span>PORTFOLIO CASE STUDY · 2026</span></div>
 </section>}
function VisualScene() {
 const element=useRef(null);
 useEffect(()=>{
   if(window.matchMedia('(prefers-reduced-motion: reduce)').matches || window.innerWidth<1100) return;
   let effect; let cancelled=false;
   // Load 3D only on desktops, isolated to the hero panel.
   import('vanta/dist/vanta.net.min').then(({default:NET})=>{
     if(cancelled || !element.current) return;
     try { effect=NET({el:element.current,THREE, mouseControls:false,touchControls:false,gyroControls:false,
       color:0xa2c2b2, backgroundColor:0x214b3b, points:8.00,maxDistance:18.00,spacing:19.00,
       showDots:true,scale:1.0,scaleMobile:1.0}); }
     catch(error){ console.warn('Decorative Vanta scene disabled:',error); }
   }).catch(()=>{});
   return ()=>{cancelled=true;effect?.destroy()};
 },[]);
 return <div className="hero-visual" aria-hidden="true"><div className="vanta-layer" ref={element}/><div className="hero-visual-inner"><div>RESEARCH NOTE <span>001 / 2026</span></div><div className="hero-visual-data"><strong>28<span>day</span></strong><small>HORIZON<br/>FORECAST & PLAN</small></div><div>DEMAND <span>→</span> DECISION</div></div></div>;
}
function App() {
 const [data,setData]=useState(null);
 const [error,setError]=useState(false);
 useEffect(()=>{fetch('/data/results.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(setData).catch(()=>setError(true))},[]);
 useEffect(()=>{
  if(!data) return;
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(reduced) return;
  const lenis=new Lenis({autoRaf:false,duration:1.08,anchors:true});
  lenis.on('scroll',ScrollTrigger.update);
  const tick=(t)=>lenis.raf(t*1000);
  gsap.ticker.add(tick); gsap.ticker.lagSmoothing(0);
  const intro=gsap.fromTo('.hero-copy > *',{opacity:0,y:18},{opacity:1,y:0,duration:.65,stagger:.09,ease:'power2.out',delay:.06});
  const triggers=gsap.utils.toArray('.reveal').map(el=>gsap.fromTo(el,{autoAlpha:0,y:30},{autoAlpha:1,y:0,duration:.8,ease:'power2.out',scrollTrigger:{trigger:el,start:'top 90%',once:true}}));
  return ()=>{intro.kill();triggers.forEach(t=>{t.scrollTrigger?.kill();t.kill()});gsap.ticker.remove(tick);lenis.destroy()};
 },[data]);
 if(error) return <main className="load-state">Could not load <code>/data/results.json</code>. Start the Vite app from the dashboard directory or check the exported data.</main>;
 if(!data) return <main className="load-state"><span className="loader-dot"/>Preparing demand intelligence…</main>;
 const best=(data.models||[]).find(m=>m.model===data.meta?.champion) || [...(data.models||[])].sort((a,b)=>a.wape-b.wape)[0];
 const baseline=data.policies.find(p=>p.policy.toLowerCase().includes('fixed'))||data.policies[0];
 const alternative=data.policies.length>1?data.policies[1]:null;
 const delta=baseline?.total_inventory_cost&&alternative?(baseline.total_inventory_cost-alternative.total_inventory_cost)/baseline.total_inventory_cost*100:0;
 return <div className="app-shell"><Header data={data}/><main id="overview" className="main-content">
  <header className="topbar"><div className="breadcrumb">RESEARCH <span>/</span> INVENTORY INTELLIGENCE <span>/</span> M5</div><div className="topbar-right"><span className="period">HISTORICAL DATA / 2011–2016</span><a href={PROJECT_URL} target="_blank" rel="noopener noreferrer" className="button-github">PROJECT CODE <Arrow angled/></a></div></header>
  <div className="main-inner">
   <section className="hero"><div className="hero-copy"><div className="hero-eyebrow"><span className="status-dot"/> APPLIED ANALYTICS / CASE STUDY</div><h1>Demand, translated<br/>into <em>decisions.</em></h1><p>From forecasting what customers will buy to understanding what should be on the shelf. A practical study in demand signals, inventory exposure and service-level trade-offs.</p><a href="#models" className="hero-explore">EXPLORE THE ANALYSIS <span>↓</span></a></div><VisualScene/></section>
   <div className="archive-notice"><span className="notice-icon">ⓘ</span><div><strong>{isArchive(data)?'Legacy M5 results · improved methodology awaiting rerun':'Recomputed · tuning and test separated'}</strong><span>{data.meta.assumptions} {isArchive(data)?'Previous cost savings are NOT an optimized or approved result.':'Forecast selection and policy optimization use tuning dates; test is never used to tune.'}</span></div></div>
   <section className="kpi-grid" aria-label="Key performance indicators"><Kpi label="BEST MODEL · WAPE" value={best.wape*100} decimals={2} suffix="%" sub={`${best.model} · ${isArchive(data)?"archived validation":"untouched test"}`} featured/><Kpi label="SKU–STORE PAIRS" value={data.meta.store_product_pairs} sub={`${data.meta.sample_skus} selected products · 3 stores`}/><Kpi label="FORECAST HORIZON" value={data.meta.horizon_days} suffix=" days" sub="Across the 28-day planning window"/><Kpi label={isArchive(data)?"LEGACY COST DELTA":"TEST COST DELTA"} value={alternative?Math.abs(delta):null} prefix={alternative?(delta>=0?"-":"+"):""} suffix={alternative?"%":""} decimals={2} sub={isArchive(data)?"Not deployable: service rate declined":data.decision?.deployment_recommended?"Passed fill and cost checks":"No validated replacement of baseline"}/></section>
   <ModelPerformance data={data}/><PolicyOutcomes data={data}/><RiskSection data={data}/><DecisionLab data={data}/>
   <div className="export-band reveal"><div><span>TAKE THE DATA WITH YOU</span><strong>Explore the underlying decisions.</strong><p>Get the policy comparison as a CSV, or review the full methodology in the notebook.</p></div><button type="button" onClick={()=>downloadCsv(data)} className="export-button">EXPORT POLICY CSV <Arrow angled/></button></div>
   <Footer data={data}/>
  </div>
 </main></div>
}
createRoot(document.getElementById('root')).render(<App/>);
