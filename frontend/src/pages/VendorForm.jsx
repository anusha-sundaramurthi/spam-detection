/**
 * Purpose: Renders the vendor-only service form, validates required and formatted
 * inputs, and submits data for private automatic background assessment.
 */

import {useState} from 'react';
import {Link} from 'react-router-dom';
import {CheckCircle2,Send} from 'lucide-react';
import {api} from '../api';
import {Field} from '../components';

const initial={name:'',phone:'',website:'',location:'',portfolio_link:'',service_title:'',description:'',category:'Venues',social_links:'',business_registration:'',package_name:'',package_details:'',price_or_range:'',delivery_timeline:'',special_offer:''};

// Validates every optional social link only when the vendor supplies one.
function invalidSocialLinks(value){return value.split('\n').map(x=>x.trim()).filter(Boolean).some(value=>{try{return !['http:','https:'].includes(new URL(value).protocol)}catch{return true}})}

// Collects vendor service data without displaying any private assessment score.
export default function VendorForm(){
  const[form,setForm]=useState(initial),[result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[attempted,setAttempted]=useState(false),[socialInvalid,setSocialInvalid]=useState(false);
  // Keeps controlled input state synchronized with the current field.
  const change=e=>{setForm({...form,[e.target.name]:e.target.value});if(e.target.name==='social_links')setSocialInvalid(false)};
  // Validates the form and starts automatic server-side screening on submission.
  async function submit(e){
    e.preventDefault();setAttempted(true);setError('');
    if(!e.currentTarget.checkValidity()){setError('Please correct the highlighted required fields or invalid formats.');e.currentTarget.querySelector(':invalid')?.focus();return}
    if(invalidSocialLinks(form.social_links)){setSocialInvalid(true);setError('Each social link must be a complete http:// or https:// URL.');return}
    setBusy(true);
    try{setResult(await api.vendorCreate({...form,website:form.website||null,social_links:form.social_links.split('\n').map(x=>x.trim()).filter(Boolean),business_registration:form.business_registration||null,special_offer:form.special_offer||null}))}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  if(result)return <div className="result-card"><CheckCircle2 size={40}/><h1>Submitted for review</h1><p>Your service was automatically screened for spam and trust signals. Internal scores remain visible only to administrators.</p><Link className="button primary" to="/vendor">View my submissions</Link></div>;
  return <><header><div><p className="eyebrow">VENDOR PORTAL</p><h1>Submit a service and offer</h1><p>Describe exactly what buyers receive. Fields marked <b className="required-star">*</b> are required. Screening runs privately in the background.</p></div></header>
    <form noValidate className={`panel form ${attempted?'validated':''}`} onSubmit={submit}>
      <div className="form-section"><h2>Business and service</h2><div className="grid">
        <Field required label="Business name"><input required minLength="2" name="name" value={form.name} onChange={change}/></Field>
        <Field required label="Category"><select required name="category" value={form.category} onChange={change}><option>Venues</option><option>Catering</option><option>Photography & Videography</option><option>Decor & Florist</option><option>Wedding Planning</option><option>DJ & Entertainment</option><option>Makeup & Bridal</option><option>Invitations & Stationery</option><option>Other</option></select></Field>
        <Field required label="Phone"><input required pattern="[0-9+()\-\s]{7,40}" title="Use 7–40 digits and common phone symbols" name="phone" value={form.phone} onChange={change}/></Field>
        <Field label="Website (optional)" className="wide"><input type="url" placeholder="https://example.com" name="website" value={form.website} onChange={change}/></Field>
        <Field required label="Service location (city)"><input required minLength="2" name="location" value={form.location} onChange={change} placeholder="e.g. Chennai"/></Field>
        <Field required label="Portfolio link"><input required type="url" name="portfolio_link" value={form.portfolio_link} onChange={change} placeholder="https://instagram.com/yourwork"/></Field>
        <Field required label="Service title" className="wide"><input required minLength="3" name="service_title" value={form.service_title} onChange={change}/></Field>
        <Field required label="Detailed service description" className="wide"><textarea required minLength="10" rows="6" name="description" value={form.description} onChange={change} placeholder="Explain process, deliverables, intended customer, and limitations."/></Field>
      </div></div>
      <div className="form-section package-section"><h2>Package / offer details <span>Required</span></h2><div className="grid">
        <Field required label="Package name"><input required minLength="2" name="package_name" value={form.package_name} onChange={change}/></Field>
        <Field required label="Price or price range"><input required name="price_or_range" value={form.price_or_range} onChange={change}/></Field>
        <Field required label="Delivery timeline"><input required minLength="2" name="delivery_timeline" value={form.delivery_timeline} onChange={change}/></Field>
        <Field label="Special offer (optional)"><input name="special_offer" value={form.special_offer} onChange={change}/></Field>
        <Field required label="Package inclusions and exclusions" className="wide"><textarea required minLength="10" rows="5" name="package_details" value={form.package_details} onChange={change}/></Field>
      </div></div>
      <div className="form-section"><h2>Optional verification signals</h2><div className="grid">
        <Field label="Social URLs (optional, one per line)" className={socialInvalid?'invalid-field':''}><textarea name="social_links" value={form.social_links} onChange={change} placeholder="https://linkedin.com/company/example"/></Field>
        <Field label="Business registration (optional)"><input name="business_registration" value={form.business_registration} onChange={change}/></Field>
      </div></div>
      {error&&<p className="error">{error}</p>}<div className="form-actions"><p>Automatic spam screening occurs privately after submission.</p><button disabled={busy} className="button primary"><Send size={18}/>{busy?'Submitting & screening…':'Submit service'}</button></div>
    </form></>;
}
