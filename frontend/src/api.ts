export async function api<T>(path:string, options:RequestInit={}):Promise<T> {
  const response=await fetch(`/api${path}`,{...options,headers:{'Content-Type':'application/json',...options.headers}});
  if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(typeof body.detail==='string'?body.detail:'The service is temporarily unavailable. Please try again.');}
  return response.json();
}
export const dateLabel=(value?:string|null)=>value?new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}).format(new Date(value.length===10?`${value}T12:00:00Z`:value)):'Date unavailable';
export const money=(v?:number)=>v===undefined?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2}).format(v);
export const safeUrl=(url?:string)=>{try{const u=new URL(url||'');return ['http:','https:'].includes(u.protocol)?u.href:undefined}catch{return undefined}};
