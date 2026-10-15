import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
if(!process.env.ARTIFACT_TOOL_UTILS||!process.env.PRESENTATIONS_SKILL_DIR||!process.env.RUNTIME_PYTHON) throw new Error('Set runtime utility, presentation skill and Python paths. See presentation/README.md.');
const {finalizePresentation}=await import(pathToFileURL(path.resolve(process.env.ARTIFACT_TOOL_UTILS)).href);
const skill=path.resolve(process.env.PRESENTATIONS_SKILL_DIR);
const here=path.dirname(fileURLToPath(import.meta.url));
const workspaceDir=path.resolve(here,'../..');
const base=path.resolve(process.env.PJM_DECK_BUILD_DIR||path.join(here,'../build'));
const requirements=JSON.parse(await fs.readFile(base+'/private/deck_requirements.json','utf8'));
execFileSync(process.env.RUNTIME_PYTHON,[path.join(here,'strip_notes.py'),base+'/private/candidate.pptx',base+'/private/clean_candidate.pptx'],{stdio:'pipe'});
const result=await finalizePresentation({workspaceDir,candidatePath:base+'/private/clean_candidate.pptx',finalPath:base+'/output/PJM_GBE_Assessment.pptx',
 pythonExecutable:process.env.RUNTIME_PYTHON,integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',
 requiredNativeTableOwnerSlides:requirements.tableOwners,requiredNativeChartOwnerSlides:requirements.chartOwners,
 materializeLiteralChartWorkbooks:true,nativeChartTargetApplication:'portable',
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...requirements.tableOwners.flatMap(n=>['--require-native-table-slide',String(n)])],
 fontPolicy:{basis:'design',families:['Helvetica Neue']},verifyArtifactToolImport:true,receiptPath:base+'/private/final_validation.json'});
console.log(JSON.stringify({finalPath:result.finalPath,sha256:result.finalSha256,warnings:result.presentationLayout.warnings}));
