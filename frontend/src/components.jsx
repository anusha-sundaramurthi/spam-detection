/**
 * Purpose: Provides reusable risk badges, score meters, and consistently
 * labelled form-field wrappers for vendor and administrator pages.
 */

// Renders a color-coded low, medium, or high risk label.
export function Badge({level}) { return <span className={`badge ${level}`}>{level} risk</span>; }

// Renders one score out of ten with a matching horizontal meter.
export function Score({label, value, type}) { return <div className="score"><span>{label}</span><strong className={type}>{value}<small>/10</small></strong><div className="meter"><i className={type} style={{width:`${value*10}%`}}/></div></div>; }

// Wraps form controls with a consistent accessible visible label.
export function Field({label, children, className='', required=false}) { return <label className={className}><span>{label}{required&&<b className="required-star" aria-hidden="true"> *</b>}</span>{children}</label>; }
