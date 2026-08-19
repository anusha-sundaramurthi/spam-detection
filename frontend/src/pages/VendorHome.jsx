/**
 * Purpose: Lists only the authenticated vendor's submissions and public review
 * statuses without exposing internal scoring evidence.
 */
// VendorHome loads and renders the vendor's status-only submission list.
/**
 * Purpose: Lists only the authenticated vendor's submissions and public review
 * statuses without exposing internal scoring evidence.
 */
// VendorHome loads and renders the vendor's status-only submission list.
import {useEffect,useState} from 'react';import {Link} from 'react-router-dom';import {Plus} from 'lucide-react';import {api} from '../api';
export default function VendorHome(){const [items,setItems]=useState([]);useEffect(()=>{api.vendorList().then(setItems)},[]);return <><header><div><p className="eyebrow">VENDOR PORTAL</p><h1>My service submissions</h1><p>Track review status. Internal trust and risk scores are visible only to administrators.</p></div><Link className="button primary" to="/vendor/submit"><Plus size={18}/>New submission</Link></header><section className="panel"><table><thead><tr><th>Service</th><th>Category</th><th>Submitted</th><th>Status</th></tr></thead><tbody>{items.map(x=><tr key={x.id}><td><b>{x.service_title}</b></td><td>{x.category}</td><td>{new Date(x.created_at).toLocaleDateString()}</td><td><span className={`badge ${x.status==='approved'?'low':'medium'}`}>{x.status}</span></td></tr>)}</tbody></table></section></>}
