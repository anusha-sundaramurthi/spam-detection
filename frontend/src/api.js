/**
 * Purpose: Centralizes browser-to-FastAPI communication, bearer-token handling,
 * JSON request construction, and role-specific API operations.
 */
/**
 * Purpose: Centralizes FastAPI requests, bearer-token handling, JSON request
 * construction, and role-specific API operations.
 */
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
// Reads the current signed access token from session-scoped browser storage.
// Reads the current signed token from session-scoped browser storage.
const token = () => sessionStorage.getItem('token');
// Sends an authenticated request and converts API failures into usable errors.
// Sends an authenticated request and converts API failures into usable errors.
async function request(path, options={}) {
  const headers = {...options.headers, ...(token()?{Authorization:`Bearer ${token()}`}:{})};
  const response = await fetch(`${BASE}${path}`, {...options, headers});
  if (!response.ok) { const body=await response.json().catch(()=>({})); throw new Error(body.detail||'Request failed'); }
  return response.json();
}
// Builds the common JSON POST options used by authentication and submission calls.
// Builds common JSON POST options for login and submission operations.
const json = body => ({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const api = {
  login: data => request('/auth/login', json(data)),
  vendorList: () => request('/vendor/submissions'), vendorCreate: data => request('/vendor/submissions', json(data)),
  adminList: () => request('/admin/submissions'), adminGet: id => request(`/admin/submissions/${id}`),
  approve: id => request(`/admin/submissions/${id}/approve`, {method:'POST'}),
  feedback: (id, data) => request(`/admin/submissions/${id}/feedback`, json(data)),
};
