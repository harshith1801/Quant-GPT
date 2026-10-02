import {useEffect,useRef,useState} from 'react';
import {AreaSeries,ColorType,CrosshairMode,createChart,type Time} from 'lightweight-charts';
import type {Company} from '../types';
import {money} from '../api';
export function PriceChart({company,compact=false}:{company:Company|null;compact?:boolean}){
 const host=useRef<HTMLDivElement>(null);const [range,setRange]=useState(63);const [expanded,setExpanded]=useState(false);const [hover,setHover]=useState<{price:number;date:string}|null>(null);
 useEffect(()=>{if(!host.current||!company?.chart.length)return;
  const data=company.chart.slice(range===0?0:-range);
  const chart=createChart(host.current,{autoSize:true,height:compact&&!expanded?112:164,layout:{background:{type:ColorType.Solid,color:'transparent'},textColor:'#72838e',fontFamily:'IBM Plex Mono',fontSize:10,attributionLogo:true},grid:{vertLines:{visible:false},horzLines:{color:'#1d262e',style:2}},rightPriceScale:{borderVisible:false,scaleMargins:{top:.12,bottom:.12}},timeScale:{borderVisible:false,timeVisible:false,fixLeftEdge:true,fixRightEdge:true},crosshair:{mode:CrosshairMode.Normal,vertLine:{color:'#6d95a7',labelBackgroundColor:'#23333e',width:1,style:2},horzLine:{color:'#6d95a7',labelBackgroundColor:'#23333e',width:1,style:2}},handleScroll:{mouseWheel:false,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true}});
  const series=chart.addSeries(AreaSeries,{lineColor:'#8acde7',topColor:'rgba(116,184,213,.14)',bottomColor:'rgba(116,184,213,0)',lineWidth:2,priceLineVisible:false,lastValueVisible:true,crosshairMarkerRadius:4});
  series.setData(data.map(d=>({time:d.time as Time,value:d.value})));chart.timeScale().fitContent();
  chart.subscribeCrosshairMove(param=>{const point=param.seriesData.get(series);if(param.time&&point&&'value'in point)setHover({price:point.value,date:String(param.time)});else setHover(null)});
  // Refit the selected range when the responsive canvas changes size.
  const resize=new ResizeObserver(()=>chart.timeScale().fitContent());resize.observe(host.current);
  return()=>{resize.disconnect();chart.remove()};
 },[company,range,compact,expanded]);
 return <section className={`market-plot ${compact&&!expanded?'compact-plot':''}`} aria-label="Daily closing price chart">
  <div className="plot-toolbar"><div><span className="eyebrow">PRICE HISTORY</span><span className="plot-unit">USD · DAILY CLOSE</span></div><div className="ranges" aria-label="Chart time range">{compact&&<button aria-label={expanded?"Minimize chart":"Expand chart"} onClick={()=>setExpanded(!expanded)}>{expanded?"−":"+"}</button>}{[[21,'1M'],[63,'3M'],[0,'ALL']] .map(([v,label])=><button key={v} className={range===v||(range===90&&v===63)?'selected':''} onClick={()=>setRange(Number(v))}>{label}</button>)}</div></div>
  <div className="chart-wrap"><div ref={host} className="chart-host" style={{height:compact&&!expanded?112:164}}/>{!company?.chart.length&&<div className="chart-empty">{company?'Price history is unavailable for this company.':'Connecting to market data…'}</div>}{hover&&<div className="chart-tooltip" aria-live="off"><b>{money(hover.price)}</b><span>{hover.date}</span></div>}</div>
  <div className="plot-foot"><span>VOLUME <b>{company?.quote?.volume?.toLocaleString('en-US')||'—'}</b></span><span>DAILY OBSERVATIONS · <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">CHARTS BY TRADINGVIEW</a></span></div>
 </section>
}
