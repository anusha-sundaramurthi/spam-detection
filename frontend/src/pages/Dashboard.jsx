/**
 * Purpose: Lists every vendor submission with text scores, model provenance,
 * persisted image assessment totals, and admin review state.
 */
import {useEffect,useState} from 'react';
import {ArrowRight,Search} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api} from '../api';
import {Badge} from '../components';

// Loads and renders all joined submission and assessment records for administrators.
export default function Dashboard(){
  const[items,setItems]=useState([]),[query,setQuery]=useState(''),[error,setError]=useState('');
  useEffect(()=>{api.adminList().then(setItems).catch(e=>setError(e.message))},[]);
  const shown=items.filter(x=>`${x.name} ${x.email} ${x.service_title} ${x.scoring_model||''} ${x.feedback_verdict||''}`.toLowerCase().includes(query.toLowerCase()));
  return <><header><div><p className="eyebrow">ADMIN SPAM REVIEW</p><h1>AI-screened services</h1><p>Every submission includes stored text and image assessment status.</p></div></header>
    <section className="stats innovation-stats"><div><span>Total submissions</span><strong>{items.length}</strong></div><div><span>High AI spam risk</span><strong className="risk-text">{items.filter(x=>x.risk_level==='high').length}</strong></div><div><span>Visual spam images</span><strong>{items.reduce((n,x)=>n+(x.image_assessment_summary?.spam||0),0)}</strong></div><div><span>Vision unavailable</span><strong>{items.reduce((n,x)=>n+(x.image_assessment_summary?.unavailable||0),0)}</strong></div></section>
    <section className="panel"><div className="toolbar"><div className="search"><Search size={18}/><input aria-label="Search submissions" placeholder="Search vendor, service, model, or feedback" value={query} onChange={e=>setQuery(e.target.value)}/></div></div>{error?<p className="error">{error}</p>:<div className="table-wrap"><table><thead><tr><th>Vendor</th><th>Service / package</th><th>Trust</th><th>Spam risk</th><th>Image assessment</th><th>AI scorer</th><th>Feedback</th><th></th></tr></thead><tbody>{shown.map(x=>{const image=x.image_assessment_summary||{};return <tr key={x.id}><td><b>{x.name}</b><small>{x.email}</small></td><td>{x.service_title}<small>{x.category}</small></td><td>{x.trust_score??'—'} / 10</td><td>{x.risk_score==null?<span>AI unavailable</span>:<><b>{x.risk_score} / 10</b><Badge level={x.risk_level}/></>}</td><td><span className={`mini-status ${image.spam||image.irrelevant?'high':image.unavailable?'medium':'low'}`}>{image.total||0} image(s)</span><small>{image.spam||0} spam · {image.irrelevant||0} irrelevant · {image.duplicates||0} duplicate</small></td><td><span className={`mini-status ${x.fallback_used?'medium':x.scoring_model?'low':'high'}`}>{x.scoring_model||'Unavailable'}{x.fallback_used?' · fallback':''}</span></td><td>{x.feedback_verdict?.replaceAll('_',' ')||'Not reviewed'}</td><td><Link to={`/admin/submissions/${x.id}`} aria-label={`Review ${x.name}`}><ArrowRight size={19}/></Link></td></tr>})}</tbody></table></div>}</section></>
}
