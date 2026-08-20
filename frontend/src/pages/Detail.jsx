/**
 * Purpose: Presents admin-only scoring, highlighted spam evidence,
 * counterfactuals, model disagreement, campaign matches, and review feedback.
 */
import {useEffect,useState} from 'react';
import {ArrowLeft,CheckCircle2,ShieldAlert} from 'lucide-react';
import {Link,useParams} from 'react-router-dom';
import {api} from '../api';
import {Badge,Score} from '../components';

// Renders one auditable score ledger with points and human-readable reasons.
function FactorTable({title,kind,items,total}){return <div className={`factor-panel ${kind}`}><div className="factor-title"><h2>{title}</h2><strong>{items.reduce((n,x)=>n+x.points,0).toFixed(1)} / {total}</strong></div>{items.map(x=><article key={x.code}><div><b>{x.label}</b><p>{x.reason}</p></div><span>{x.points.toFixed(1)} / {x.max_points}</span></article>)}</div>}

// Highlights exact rule evidence while preserving all original submitted text.
function EvidenceText({field,text,evidence}){const spans=evidence.filter(x=>x.field===field).sort((a,b)=>a.start-b.start);if(!spans.length)return <>{text||'Not supplied'}</>;const output=[];let cursor=0;spans.forEach((span,index)=>{if(span.start<cursor)return;output.push(text.slice(cursor,span.start));output.push(<mark title={span.reason} key={`${field}-${index}`}>{text.slice(span.start,span.end)}</mark>);cursor=span.end});output.push(text.slice(cursor));return <>{output}</>}

// Loads the assessment and records approval or structured admin feedback.
export default function Detail(){
  const{id}=useParams();const[item,setItem]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const[feedback,setFeedback]=useState({verdict:'needs_review',notes:'',factor_codes:[]});
  useEffect(()=>{api.adminGet(id).then(setItem).catch(e=>setError(e.message))},[id]);
  // Records the administrator's human approval decision.
  async function approve(){setBusy(true);try{setItem(await api.approve(id))}catch(e){setError(e.message)}finally{setBusy(false)}}
  // Stores review feedback without automatically changing the scoring model.
  async function submitFeedback(e){e.preventDefault();setBusy(true);try{setItem(await api.feedback(id,feedback));setFeedback({...feedback,notes:''})}catch(e){setError(e.message)}finally{setBusy(false)}}
  // Toggles the risk factors the reviewer considers inaccurate or important.
  function toggleFactor(code){setFeedback({...feedback,factor_codes:feedback.factor_codes.includes(code)?feedback.factor_codes.filter(x=>x!==code):[...feedback.factor_codes,code]})}
  if(error&&!item)return <p className="error">{error}</p>;if(!item)return <p>Loading…</p>;
  const intel=item.intelligence||{};const disagreement=intel.disagreement||{};const campaign=item.campaign||{matches:[]};const evidence=intel.evidence_map||[];
  return <><Link className="back" to="/admin"><ArrowLeft size={17}/>Back to queue</Link>
    <header><div><p className="eyebrow">AUTOMATIC SPAM ASSESSMENT</p><h1>{item.name}</h1><p>{item.service_title} · {item.category}</p></div><div className="actions"><Badge level={item.risk_level}/>{item.status!=='approved'&&<button disabled={busy} className="button primary" onClick={approve}>{busy?'Saving…':'Approve service'}</button>}</div></header>
    {error&&<p className="error">{error}</p>}
    <section className="mandatory panel"><div><p className="eyebrow">MANDATORY SCORING SERVICES</p><h2>All automatic checks</h2></div>{item.mandatory_services.map(s=><span key={s.code}><CheckCircle2 size={16}/>{s.name}<b>Required</b></span>)}</section>
    <section className="score-panel panel"><Score label="Trust Score" value={item.trust_score} type="trust"/><Score label="Spam Risk Score" value={item.risk_score} type="risk"/><div className="confidence"><span>{item.combined_assessment.method}</span><strong>{item.confidence}% confidence</strong></div></section>
    <section className="intelligence-grid">
      <div className={`panel insight disagreement-${disagreement.level}`}><p className="eyebrow">MODEL DISAGREEMENT</p><h2>{disagreement.level||'Unknown'}</h2><p>Rules: <b>{disagreement.rule_risk??'—'}</b> · Local AI: <b>{disagreement.ai_risk??'—'}</b></p><small>{disagreement.reason}</small></div>
      <div className="panel insight"><p className="eyebrow">CAMPAIGN CLUSTER</p><h2>{campaign.campaign_id||'No related campaign'}</h2><p><b>{campaign.similar_count||0}</b> similar submission(s)</p><small>Based on content, phone, and website similarity.</small></div>
    </section>
    <section className="factor-grid"><FactorTable title="Spam Risk Factors" kind="risk" items={item.risk_factors} total={10}/><FactorTable title="Trust Score Factors" kind="trust" items={item.trust_factors} total={10}/></section>
    <section className="panel evidence-panel"><p className="eyebrow">SPAM EVIDENCE MAP</p><h2>Submitted content with exact rule matches</h2><p className="evidence-help">Highlighted phrases were found by deterministic rules. Local AI evidence is listed separately.</p><dl><dt>Title</dt><dd><EvidenceText field="service_title" text={item.service_title} evidence={evidence}/></dd><dt>Description</dt><dd><EvidenceText field="description" text={item.description} evidence={evidence}/></dd><dt>Package</dt><dd><EvidenceText field="package_details" text={item.package_details} evidence={evidence}/></dd><dt>Offer</dt><dd><EvidenceText field="special_offer" text={item.special_offer} evidence={evidence}/></dd></dl><h3>Local AI semantic evidence</h3><ul>{(intel.ai_evidence||[]).map((reason,index)=><li key={index}>{reason}</li>)}</ul></section>
    <section className="panel counterfactual"><p className="eyebrow">WHY THIS SCORE?</p><h2>Estimated risk without each triggered factor</h2>{(intel.counterfactuals||[]).length?<div className="counter-list">{intel.counterfactuals.map(x=><div key={x.factor_code}><span>{x.label}</span><b>{x.current_risk} → {x.estimated_risk_without_factor}</b><small>−{x.estimated_reduction} estimated</small></div>)}</div>:<p>No triggered deterministic risk factor to remove.</p>}</section>
    {campaign.matches?.length>0&&<section className="panel matches"><p className="eyebrow">RELATED SUBMISSIONS</p><h2>Possible coordinated campaign</h2>{campaign.matches.map(match=><Link key={match.id} to={`/admin/submissions/${match.id}`}><span><b>{match.name}</b><small>{match.service_title} · {match.reasons.join(', ')}</small></span><strong>{match.similarity}%</strong></Link>)}</section>}
    <section className="detail-grid"><div className="panel profile"><h2>Service and package</h2><dl><dt>Package</dt><dd>{item.package_name}</dd><dt>Price</dt><dd>{item.price_or_range}</dd><dt>Timeline</dt><dd>{item.delivery_timeline}</dd><dt>Website</dt><dd>{item.website||'Not supplied'}</dd><dt>Location</dt><dd>{item.location||'Not supplied'}</dd><dt>Portfolio</dt><dd>{item.portfolio_link?<a href={item.portfolio_link} target="_blank" rel="noreferrer">{item.portfolio_link}</a>:'Not supplied'}</dd></dl></div><div className="panel ai-card"><p className="eyebrow">LOCAL AI SPAM REVIEW</p><h2>{item.ai_assessment.model}</h2>{item.ai_assessment.status==='complete'?<><p><b>Spam probability: {item.ai_assessment.spam_probability}%</b></p><p>{item.ai_assessment.summary}</p></>:<p><ShieldAlert size={16}/> {item.ai_assessment.spam_indicators[0]}</p>}</div></section>
    <section className="panel feedback-panel"><p className="eyebrow">ADMIN FEEDBACK LOOP</p><h2>Record review quality</h2><p>This creates an audit record only; it does not silently retrain or change weights.</p><form onSubmit={submitFeedback}><select value={feedback.verdict} onChange={e=>setFeedback({...feedback,verdict:e.target.value})}><option value="needs_review">Needs review</option><option value="confirmed_spam">Confirmed spam</option><option value="false_positive">False positive</option><option value="accurate_low_risk">Accurate low risk</option></select><textarea maxLength="1000" placeholder="Reviewer notes" value={feedback.notes} onChange={e=>setFeedback({...feedback,notes:e.target.value})}/><div className="factor-picks">{item.risk_factors.filter(x=>x.triggered).map(x=><label key={x.code}><input type="checkbox" checked={feedback.factor_codes.includes(x.code)} onChange={()=>toggleFactor(x.code)}/>{x.label}</label>)}</div><button disabled={busy} className="button primary">Save feedback</button></form>{item.admin_feedback?.length>0&&<div className="feedback-history"><h3>History</h3>{[...item.admin_feedback].reverse().map((entry,index)=><article key={index}><b>{entry.verdict.replaceAll('_',' ')}</b><span>{entry.notes||'No notes'}</span><small>{new Date(entry.created_at).toLocaleString()}</small></article>)}</div>}</section>
  </>;
}