import {useEffect,useRef,useState} from 'react';
import {ExternalLink,X,ArrowUpRight} from 'lucide-react';
import {AnimatePresence,motion} from 'motion/react';
import {dateLabel,safeUrl} from '../api';
import type {Analysis,Company,Source} from '../types';
export function Evidence({analysis,company,selected,onSelect,tab,onTab,open,onClose}:{analysis:Analysis|null;company:Company|null;selected:string|null;onSelect:(id:string|null)=>void;tab:'filings'|'news';onTab:(t:'filings'|'news')=>void;open:boolean;onClose:()=>void}){
 const root=useRef<HTMLElement>(null);
 const [narrow,setNarrow]=useState(()=>window.matchMedia('(max-width:900px)').matches);
 const filings=analysis?.sources.filter(s=>s.filing_type)||[];const source=analysis?.sources.find(s=>s.source_id===selected);
 const modal=open&&narrow;
 useEffect(()=>{const media=window.matchMedia('(max-width:900px)');const update=()=>setNarrow(media.matches);media.addEventListener('change',update);return()=>media.removeEventListener('change',update)},[]);
 useEffect(()=>{
  if(!modal&&!source)return;
  const previous=document.activeElement as HTMLElement;
  const scope=source?root.current?.querySelector<HTMLElement>('.source-detail'):root.current;
  scope?.querySelector<HTMLButtonElement>('button')?.focus({preventScroll:true});
  const trap=(e:KeyboardEvent)=>{
   if(!modal||e.key!=='Tab')return;
   const nodes=Array.from(scope?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href]')||[]).filter(n=>n.offsetParent!==null);
   const first=nodes[0],last=nodes[nodes.length-1];
   if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}
   else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}
  };
  document.addEventListener('keydown',trap);
  return()=>{document.removeEventListener('keydown',trap);previous?.focus({preventScroll:true})};
 },[modal,source?.source_id]);
 return <aside ref={root} role={modal?'dialog':'complementary'} aria-modal={modal?true:undefined} className={`evidence-rail ${open?'mobile-open':''}`} aria-label="Evidence panel">
  <div className="rail-heading" inert={!!source}><div><span className="cross">+</span> EVIDENCE DESK</div><button className="mobile-close icon-button" onClick={onClose} aria-label="Close evidence"><X size={18}/></button><span className="rail-count">{filings.length.toString().padStart(2,'0')}</span></div>
  <div className="evidence-tabs" inert={!!source}><button className={tab==='filings'?'active':''} onClick={()=>onTab('filings')}>Filings <small>{filings.length}</small></button><button className={tab==='news'?'active':''} onClick={()=>onTab('news')}>News <small>{company?.news.articles.length||0}</small></button></div>
  <div className="evidence-body" inert={!!source}>
   {tab==='filings'?<><div className="rail-intro"><span className="eyebrow">PRIMARY SOURCES</span><p>{filings.length?'Every claim has a starting point. Follow the evidence.':'Your research trail starts here. Run an analysis to inspect the underlying filings.'}</p></div>
   {filings.map((s,i)=><button className={`source-row ${selected===s.source_id?'source-active':''}`} key={s.source_id} onClick={()=>onSelect(selected===s.source_id?null:s.source_id)}><div className="source-row-top"><span className="source-number">{String(i+1).padStart(2,'0')}</span><span className="form-label">{s.filing_type}</span><span>{dateLabel(s.filing_date)}</span><ArrowUpRight size={14}/></div><p>{s.text.replace(/\s+/g,' ').slice(0,145)}…</p><span className="source-ticker">{s.ticker} · SEC EDGAR</span></button>)}
   {!filings.length&&<div className="source-placeholder"><div className="evidence-diagram" aria-hidden="true"><i/><span/><i/><span/><i/></div><h3>Traceable by design.</h3><p>Filing dates, original excerpts and accession numbers stay attached to your analysis.</p>{company?.filings.map(f=><div className="available-filing" key={f.filing_type}><b>{f.filing_type}</b><span>{dateLabel(f.filing_date)}</span><small>IN INDEX</small></div>)}</div>}
   </>:<><div className="rail-intro"><span className="eyebrow">NEWS SIGNAL</span><p>{company?.news.status==='ok'?`${company.news.overall_sentiment_label} sentiment in the returned articles.`:company?.news.overall_sentiment_label||'Waiting for news.'}</p><small>{company?.news.fetched_at?`Checked ${dateLabel(company.news.fetched_at)}`:'Availability is reported explicitly.'}</small></div>{company?.news.articles.map((a,i)=><a className="news-row" href={safeUrl(a.url)} target="_blank" rel="noreferrer" key={i}><div><span>{a.source||'News source'}</span><ArrowUpRight size={13}/></div><h3>{a.title}</h3><p>{a.description}</p><small>{a.sentiment_label}</small></a>)}{!company?.news.articles.length&&<div className="source-placeholder"><h3>{company?.news.status==='rate_limited'?'News quota reached.':'No news evidence available.'}</h3><p>{company?.news.message||'Sentiment is not inferred when news is unavailable.'}</p></div>}</>}
  </div>
  <AnimatePresence>{source&&<motion.div className="source-detail" key={selected} initial={{opacity:0,x:12}} animate={{opacity:1,x:0}} exit={{opacity:0,x:12}} transition={{duration:.18}}><SourceDetail source={source} onClose={()=>onSelect(null)}/></motion.div>}</AnimatePresence>
  <div className="evidence-footer"><span className="tiny-dot"/> Evidence before inference.</div>
 </aside>
}
function SourceDetail({source,onClose}:{source:Source;onClose:()=>void}){return <><div className="detail-top"><span className="eyebrow">{source.ticker} / {source.source_id.split(':')[1]}</span><button className="icon-button" onClick={onClose} aria-label="Back to evidence list"><X size={16}/></button></div><h2>{source.filing_type?`${source.filing_type} filing`:source.kind==='market'?'Market observation':'News evidence'}</h2>{source.filing_type&&<><div className="detail-meta"><span>FILED</span><b>{dateLabel(source.filing_date)}</b><span>PERIOD END</span><b>{dateLabel(source.report_period_end)}</b></div><p className="accession">{source.accession}</p></>}<div className="excerpt"><span className="eyebrow">ORIGINAL EXCERPT</span><pre>{source.text}</pre></div>{safeUrl(source.url)&&<a className="sec-link" href={source.url} target="_blank" rel="noreferrer">Open original SEC document <ExternalLink size={14}/></a>}<small className="detail-path">{source.document||source.source_id}</small></>}
