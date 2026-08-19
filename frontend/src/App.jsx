/**
 * Purpose: Enforces role-aware routing and renders the shared authenticated
 * application shell, navigation, pages, and sign-out action.
 */
// App selects the vendor or admin route tree for the authenticated role.
// logout clears the browser session and returns the user to sign-in.
/**
 * Purpose: Enforces role-aware routing and renders the shared authenticated
 * application shell, navigation, pages, and sign-out action.
 */
// App selects the vendor or admin route tree for the authenticated role.
// logout clears the browser session and returns the user to sign-in.
import {useState} from 'react'; import {Navigate,NavLink,Route,Routes,useNavigate} from 'react-router-dom'; import {LayoutDashboard,ShieldCheck,Store,LogOut} from 'lucide-react';
import Dashboard from './pages/Dashboard'; import Detail from './pages/Detail'; import VendorForm from './pages/VendorForm'; import VendorHome from './pages/VendorHome'; import Login from './pages/Login';
export default function App(){const [auth,setAuth]=useState(sessionStorage.getItem('role'));const nav=useNavigate();function logout(){sessionStorage.clear();setAuth(null);nav('/login')}if(!auth)return <Routes><Route path="*" element={<Login setAuth={setAuth}/>}/></Routes>;return <div className="app"><aside><div className="brand"><span className="brand-icon"><ShieldCheck/></span><div>onivah<small>{auth} workspace</small></div></div><nav>{auth==='admin'?<NavLink to="/admin"><LayoutDashboard size={19}/>Admin queue</NavLink>:<><NavLink to="/vendor"><LayoutDashboard size={19}/>My submissions</NavLink><NavLink to="/vendor/submit"><Store size={19}/>Submit service</NavLink></>}<button className="nav-button" onClick={logout}><LogOut size={19}/>Sign out</button></nav></aside><main><Routes>{auth==='admin'?<><Route path="/admin" element={<Dashboard/>}/><Route path="/admin/submissions/:id" element={<Detail/>}/><Route path="*" element={<Navigate to="/admin"/>}/></>:<><Route path="/vendor" element={<VendorHome/>}/><Route path="/vendor/submit" element={<VendorForm/>}/><Route path="*" element={<Navigate to="/vendor"/>}/></>}</Routes></main></div>}
