/**
 * Purpose: Presents the administrator's automatically screened review queue,
 * summary counts, search, risk badges, and evidence links.
 */
// Dashboard loads, filters, summarizes, and renders admin submissions.
/**
 * Purpose: Presents the administrator's automatically screened review queue,
 * summary counts, search, risk badges, and evidence links.
 */
// Dashboard loads, filters, summarizes, and renders admin submissions.
import {useEffect,useState} from 'react';import {ArrowRight,Search} from 'lucide-react';import {Link} from 'react-router-dom';import {api} from '../api';import {Badge} from '../components';
export default function Dashboard(){const[items,setItems]=useState([]),[query,setQuery]=useState(''),[error,setError]=useState('');useEffect(()=>{api.adminList().then(setItems).catch(e=>setError(e.message))},[]);const shown=items.filter(x=>`${x.name} ${x.email} ${x.service_title}`.toLowerCase().includes(query.toLowerCase()));return <><header><div><p className="eyebrow">ADMIN SPAM REVIEW</p><h1>Automatically screened services</h1><p>Every submission is scored automatically. Open it for side-by-side spam risk and trust reasons.</p></div></header><section className="stats"><div><span>Total screened</span><strong>{items.length}</strong></div><div><span>High spam risk</span><strong className="risk-text">{items.filter(x=>x.risk_level==='high').length}</strong></div><div><span>Approved</span><strong>{items.filter(x=>x.status==='approved').length}</strong></div></section><section className="panel"><div className="toolbar"><div className="search"><Search size={18}/><input aria-label="Search submissions" placeholder="Search vendor or service" value={query} onChange={e=>setQuery(e.target.value)}/></div></div>{error?<p className="error">{error}</p>:<div className="table-wrap"><table><thead><tr><th>Vendor</th><th>Service / package</th><th>Trust</th><th>Spam risk</th><th>Status</th><th></th></tr></thead><tbody>{shown.map(x=><tr key={x.id}><td><b>{x.name}</b><small>{x.email}</small></td><td>{x.service_title}<small>{x.category}</small></td><td>{x.trust_score??'—'} / 10</td><td>{x.risk_level?<Badge level={x.risk_level}/>:<span>Screening…</span>}</td><td>{x.status}</td><td><Link to={`/admin/submissions/${x.id}`} aria-label={`Review ${x.name}`}><ArrowRight size={19}/></Link></td></tr>)}</tbody></table></div>}</section></>}
