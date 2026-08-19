/**
 * Purpose: Establishes the demo browser session and redirects authenticated
 * users to the correct role workspace.
 */
// Login renders authentication state and the role-aware redirect workflow.
// submit exchanges credentials for a signed API token and stores the session.
/**
 * Purpose: Establishes the demo browser session and redirects authenticated
 * users to the correct role workspace.
 */
// Login renders authentication state and the role-aware redirect workflow.
// submit exchanges credentials for a signed API token and stores the session.
import {useState} from 'react'; import {useNavigate} from 'react-router-dom'; import {api} from '../api';
export default function Login({setAuth}){const [form,setForm]=useState({username:'',password:''}),[error,setError]=useState('');const nav=useNavigate();async function submit(e){e.preventDefault();try{const r=await api.login(form);sessionStorage.setItem('token',r.access_token);sessionStorage.setItem('role',r.role);setAuth(r.role);nav(r.role==='admin'?'/admin':'/vendor')}catch(e){setError(e.message)}}return <div className="result-card"><p className="eyebrow">SECURE DEMO LOGIN</p><h1>ClearVendor</h1><form onSubmit={submit} className="login-form"><input placeholder="Email" value={form.username} onChange={e=>setForm({...form,username:e.target.value})}/><input type="password" placeholder="Password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/>{error&&<p className="error">{error}</p>}<button className="button primary">Sign in</button></form><small>Vendor and admin accounts are configured separately in the backend environment.</small></div>}
