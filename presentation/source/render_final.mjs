import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const b=path.resolve(process.env.PJM_DECK_BUILD_DIR||path.join(here,'../build'));
const p=await PresentationFile.importPptx(await FileBlob.load(b+'/output/PJM_GBE_Assessment.pptx'));
await fs.mkdir(b+'/private/final_renders',{recursive:true});
for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:2});
 await fs.writeFile(b+`/private/final_renders/slide-${String(i+1).padStart(2,'0')}.png`,new Uint8Array(await blob.arrayBuffer()));
}
console.log('Rendered '+p.slides.items.length+' finalized slides at 2560 × 1440');
