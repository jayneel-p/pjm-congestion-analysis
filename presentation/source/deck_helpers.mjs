import fs from 'node:fs/promises';
import { Presentation, PresentationFile } from '@oai/artifact-tool';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
if(!process.env.ARTIFACT_TOOL_UTILS) throw new Error('Set ARTIFACT_TOOL_UTILS to the installed presentation artifact_tool_utils.mjs.');
const {applyPresentationChartFont,resolvePresentationFont}=await import(pathToFileURL(path.resolve(process.env.ARTIFACT_TOOL_UTILS)).href);

export { PresentationFile };
export const font=resolvePresentationFont();
export const colors={ink:'#15283B',muted:'#566777',grid:'#DCE2E7',A:'#176DA5',B:'#B07016',C:'#7051A1',grey:'#8D9AA5',red:'#B24238',paper:'#FFFFFF'};
export const presentation=Presentation.create({slideSize:{width:1280,height:720}});
presentation.theme.defaultFont=font;

export function text(slide,copy,x,y,w,h,size=28,color=colors.ink,bold=false){
  const s=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  s.text=copy;
  s.text.style={fontSize:size,typeface:font,color,bold,autoFit:'none',wrap:'square',insets:0,verticalAlignment:'top'};
  return s;
}
export function slide(title,subtitle='',gate=''){
  const s=presentation.slides.add();s.background.fill=colors.paper;
  text(s,title,56,36,1168,62,42,colors.ink,true);
  if(subtitle)text(s,subtitle,58,110,1160,56,23,colors.muted);
  text(s,`${String(presentation.slides.items.length).padStart(2,'0')}`,1150,675,75,24,17,colors.muted);
  return s;
}
export function footer(s,copy){text(s,copy,58,630,1080,55,18,colors.muted);}
export function table(s,values,{x=58,y=195,w=1165,h=365,widths,size=25,header=true}={}){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
 t.styleOptions={headerRow:header,bandedRows:false};
 t.borders.assign({fill:colors.grid,width:.6,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){
   const cell=t.getCell(r,c);cell.fill=r===0&&header?'#EEF2F5':'#FFFFFF';
   cell.text.style={typeface:font,fontSize:size,color:colors.ink,bold:r===0&&header,autoFit:'none',wrap:'square',insets:10};
 }
 return t;
}
export function chart(s,{kind='line',title='',cats=[],series,x=58,y=210,w=780,h=390,xTitle='',yTitle='',percent=false,yMin,yMax,xMin,xMax,xMajorUnit,legend=true,labels=false,labelSize=18,yFormat='0.0',xFormat,xLabelSize=20,barDirection='column',legendSize=20,scatterStyle='line'}){
 const ch=s.charts.add(kind,{position:{left:x,top:y,width:w,height:h},title,titleTextStyle:{fontSize:24,bold:true,fill:colors.ink},
  categories:cats,series:series.map((a,i)=>{const {color,...rest}=a;return {...rest,values:a.values?.map(v=>v===null?null:Number(v.toPrecision(14))),xValues:a.xValues?.map(v=>Number(v.toPrecision(14))),fill:a.fill||colors.grey,line:a.line||{fill:color||a.fill||colors.A,width:3,style:'solid'},marker:a.marker||{symbol:'none',size:4}};}),
  hasLegend:legend,legend:{position:'bottom',overlay:false,textStyle:{fontSize:legendSize,fill:colors.muted}},
  barOptions:{direction:barDirection,grouping:'clustered',gapWidth:80},scatterOptions:{style:scatterStyle},
  xAxis:{crossesAt:xMin??Math.min(...series.flatMap(r=>r.xValues||[0])),title:{text:xTitle,textStyle:{fontSize:22,fill:colors.muted}},textStyle:{fontSize:xLabelSize,fill:colors.muted},numberFormatCode:xFormat,line:{fill:colors.grid,width:1},min:xMin,max:xMax,majorUnit:xMajorUnit,majorGridlines:null,tickLabelPosition:'low'},
  yAxis:{crossesAt:0,title:{text:yTitle,textStyle:{fontSize:22,fill:colors.muted}},textStyle:{fontSize:20,fill:colors.muted},min:yMin,max:yMax,numberFormatCode:percent?'0%':yFormat,majorGridlines:{fill:colors.grid,width:.7}},
  dataLabels:{showValue:labels,position:'outEnd',numberFormatCode:percent?'0.0%':yFormat,textStyle:{fontSize:labelSize,fill:colors.ink}},chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0}});
  applyPresentationChartFont(ch,{fontFamily:font});return ch;
}
export async function saveBlob(path,blob){await fs.writeFile(path,new Uint8Array(await blob.arrayBuffer()));}
