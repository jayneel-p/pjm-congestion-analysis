import fs from 'node:fs/promises';
import {presentation,slide,text,table,chart,footer,colors,saveBlob,PresentationFile} from './deck_helpers.mjs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url));
if(!process.env.PJM_DECK_INPUT_DIR) throw new Error('Set PJM_DECK_INPUT_DIR to the frozen external authoring input. See presentation/README.md.');
const base=path.resolve(process.env.PJM_DECK_BUILD_DIR||path.join(here,'../build'));
const priv=path.join(base,'private'),out=path.join(base,'output');
await fs.mkdir(path.join(priv,'renders'),{recursive:true});await fs.mkdir(out,{recursive:true});
const manifest=JSON.parse(await fs.readFile(path.join(here,'input_manifest.json'),'utf8'));
for(const row of manifest.files){
 const bytes=await fs.readFile(path.join(process.env.PJM_DECK_INPUT_DIR,row.name));
 if(bytes.length!==row.bytes||createHash('sha256').update(bytes).digest('hex')!==row.sha256) throw new Error('Authoring input differs from publication snapshot: '+row.name);
 await fs.writeFile(path.join(priv,row.name),bytes);
}
const content=JSON.parse(await fs.readFile(priv+'/deck_content.json','utf8'));
const charts=[],tables=[],all=[];
for(const row of content.slides){
 const s=slide(row.title,row.subtitle);
 let longTable=false,tableBottom=0;
 for(const object of row.objects){
  if(object.type==='chart'){chart(s,object.data);charts.push({slide:row.slide,...object.data});}
  if(object.type==='table'){
   const opt={...object.data.options};
   if(opt.h>=350){opt.y=185;opt.h=415;longTable=true;}
   table(s,object.data.values,opt);tables.push({slide:row.slide,values:object.data.values,options:opt});tableBottom=opt.y+opt.h;
  }
 }
 if(row.body&&!longTable){const y=tableBottom?Math.max(535,tableBottom+15):530;text(s,row.body,75,y,1130,625-y,26,colors.ink,true);}
 footer(s,row.footer);
 all.push(row);
}
await fs.writeFile(priv+'/native_chart_data.json',JSON.stringify(charts,null,2));
await fs.writeFile(priv+'/native_table_data.json',JSON.stringify(tables,null,2));
await fs.writeFile(priv+'/deck_requirements.json',JSON.stringify({slides:all.length,chartOwners:charts.map(r=>r.slide),tableOwners:tables.map(r=>r.slide)},null,2));
for(let i=0;i<presentation.slides.items.length;i++)await saveBlob(priv+`/renders/slide-${String(i+1).padStart(2,'0')}.png`,await presentation.export({slide:presentation.slides.items[i],format:'png',scale:1}));
await(await PresentationFile.exportPptx(presentation)).save(priv+'/candidate.pptx');
console.log(JSON.stringify({slides:all.length,charts:charts.length,tables:tables.length}));
