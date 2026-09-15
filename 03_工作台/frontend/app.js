const requestedParams = new URLSearchParams(location.search);
const requestedPage = requestedParams.get('page');
const requestedEditor = requestedParams.get('editor');
const todayEditorSurfaces = new Set(['copy','structure','topics','cases']);
const topicFreezePreferenceKey = 'aip-workbench-topic-columns-frozen';
const assetUpdateRangePreferenceKey = 'aip-workbench-asset-update-range';
const todaySnapshotStorageKey = 'aip-workbench-today-snapshot-v1';
const todaySnapshotMaxAgeMs = 30 * 60 * 1000;
const topicColumnsFrozen = () => {
  try { return localStorage.getItem(topicFreezePreferenceKey) !== 'false'; }
  catch (_) { return true; }
};
const assetUpdateRange = () => {
  try { return [7,30,90].includes(Number(localStorage.getItem(assetUpdateRangePreferenceKey))) ? Number(localStorage.getItem(assetUpdateRangePreferenceKey)) : 7; }
  catch (_) { return 7; }
};
const state = { data: null, page: ['today','pipeline','assets','team','data'].includes(requestedPage) ? requestedPage : 'today', type: 'dry-goods', typeMenuOpen:false, calendarDate: new Date(), planCalendar: null, selectedPlanDate: '', assetUpdateDays:assetUpdateRange(), dataAnimationRequested: true, motionReason: 'initial', pageLoading:false, todaySyncing:false, syncHighlights:{}, todayEditor: requestedPage==='today' && todayEditorSurfaces.has(requestedEditor) ? {surface:requestedEditor, files:[], activeFileId:'', file:null, filter:requestedEditor==='copy'?'written':'pending', saveState:'loading', saveTimer:0, requestId:0, catalogLoaded:false, catalogLoading:false,topicColumnsFrozen:topicColumnsFrozen(),focusMode:false,fileSidebarCollapsed:false} : null };
const todayCanvas = { width: 1920, height: 1080 };
let lastCanvasFitKey = '';
const portraitFiles = {xiaojiang:'xiaojiang-master.png',xiaoshen:'xiaoshen-v4.png',xiaoxi:'xiaoxi-v4.png',xiaochai:'xiaochai-v4.png',xiaojing:'xiaojing-v4.png',xiaoce:'xiaoce-v4.png',xiaoxie:'xiaoxie-v4.png',xiaotu:'xiaotu-v4.png',xiaoshu:'xiaoshu-v4.png',xiaojian:'xiaojian-v4.png',xiaofa:'xiaofa-v4.png'};
const teamRoles = {
  xiaojiang:{title:'总调度',summary:'接收需求、分配岗位、回收结果',detail:'识别业务需求，创建调度记录，分配专业岗位并统一回收审核结果。'},
  xiaoshen:{title:'质量审核',summary:'审核放行与退回把关',detail:'独立审核正式产物、执行回执与输出质量；未放行的内容不能进入正式输出。'},
  xiaoxi:{title:'原始资料入库',summary:'同步、标准化、分类入库',detail:'负责原始资料同步、命名清洗、标准化入库与资产盘点。'},
  xiaochai:{title:'内容拆解与结构',summary:'拆解内容模块、生成文案结构',detail:'负责好书、播客、今日复盘拆解，以及干货型文案结构生成。'},
  xiaojing:{title:'爆款开头研究',summary:'拆解开头模型与复用卡',detail:'负责研究爆款开头，形成可审核、可调用的开头卡。'},
  xiaoce:{title:'选题策略',summary:'对标分析、分类、维护选题',detail:'负责处理对标账号资料，提炼爆款选题并维护九列选题表。'},
  xiaoxie:{title:'文案生产',summary:'基于结构四生成正文成稿',detail:'读取已填写且通过校验的结构四，生成正文候选并提交小审审核。'},
  xiaotu:{title:'视觉生产',summary:'生成配图与视觉产物',detail:'负责将正式内容转化为可用配图和视觉类正式产物。'},
  xiaoshu:{title:'数据分析',summary:'数据分析与内容复盘',detail:'预留岗位，后续负责内容表现、生产数据与复盘洞察；当前不参与正式生产链。'},
  xiaojian:{title:'自动剪辑',summary:'自动剪辑与视频成片',detail:'预留岗位，后续负责视频剪辑、字幕处理与成片交付；当前不执行自动剪辑任务。'},
  xiaofa:{title:'自动发布',summary:'自动发布与运营跟进',detail:'预留岗位，后续负责发布准备、平台发布与运营跟进；当前不执行任何对外发布动作。'}
};
const $ = (s, root = document) => root.querySelector(s);
const esc = (value = '') => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nf = value => new Intl.NumberFormat('zh-CN').format(Number(value || 0));
const brandAsset = path => `/brand-assets/${path}`;
const brandIcon = (name, label = '') => `<img class="brand-icon brand-icon-${name}" src="${brandAsset(`icons/${name}.svg`)}" alt="${esc(label)}">`;
const brandNavIcons = {today:'nav-dashboard',pipeline:'nav-pipeline',assets:'nav-assets',team:'nav-team',data:'nav-data'};
const todayTaskIcons = {'fill-structure-four':'hand-writing','generate-structure':'copy-structure','select-topic':'selected-topic','refresh-topics':'target','break-review':'thinking-card'};
const todayTagTones = {'optimize-copy':'green','fill-structure-four':'purple','generate-structure':'orange','select-topic':'blue','refresh-topics':'orange','break-review':'blue'};
const todaySingleLineTitles = new Set(['fill-structure-four','generate-structure','select-topic']);
function fitWorkbenchCanvas(){
  const focusMode=state.page==='today'&&Boolean(state.todayEditor?.focusMode);
  const fitKey=`${focusMode}:${window.innerWidth}x${window.innerHeight}`;
  if(fitKey===lastCanvasFitKey)return;
  lastCanvasFitKey=fitKey;
  document.body.classList.toggle('today-editor-focus-mode',focusMode);
  document.documentElement.classList.toggle('today-editor-focus-root',focusMode);
  if(focusMode){
    document.body.classList.remove('workbench-canvas-fit','today-canvas-fit');
    document.documentElement.classList.remove('workbench-canvas-fit-root');
    document.documentElement.style.removeProperty('--workbench-canvas-scale');
    return;
  }
  const scale = Math.min(window.innerWidth / todayCanvas.width, window.innerHeight / todayCanvas.height);
  document.body.classList.add('workbench-canvas-fit');
  // Every workbench surface uses one desktop canvas.  Only this whole-canvas
  // transform may respond to the viewport; child layouts must not.
  document.body.classList.remove('today-canvas-fit');
  document.documentElement.classList.add('workbench-canvas-fit-root');
  document.documentElement.style.setProperty('--workbench-canvas-scale', String(Math.max(.01, scale)));
}
const svg = body => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const icons = {
  today:svg('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'),
  pipeline:svg('<circle cx="12" cy="4" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 6v5M12 11 5 17M12 11l7 6"/>'),
  assets:svg('<path d="M3 7h6l2 2h10v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 7V5a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v2"/>'),
  team:svg('<circle cx="9" cy="8" r="3"/><path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M18 21v-2a6 6 0 0 0-3-5.2"/>'),
  data:svg('<path d="M4 20V10h4v10M10 20V4h4v16M16 20v-7h4v7"/>'),
  file:svg('<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5M9 12h6M9 16h6"/>'),
  star:svg('<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z"/>'),
  mic:svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/>'),
  bolt:svg('<path d="m13 2-9 12h7l-1 8 10-13h-7z"/>'),
  folder:svg('<path d="M3 7h6l2 2h10v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  arrow:svg('<path d="m9 5 7 7-7 7"/>'),
  calendar:svg('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>'),
  inbox:svg('<path d="M4 5h16v14H4z"/><path d="m4 14 4 4h8l4-4M9 10h6"/>'),
  layers:svg('<path d="m12 3 8 4-8 4-8-4zM4 12l8 4 8-4M4 16l8 4 8-4"/>'),
  lightbulb:svg('<path d="M9 18h6M10 22h4M8 14.5A7 7 0 1 1 16 14.5c-1 1-1.4 1.8-1.4 3H9.4c0-1.2-.4-2-1.4-3z"/>'),
  puzzle:svg('<path d="M8 4h3a2 2 0 1 1 4 0h3v5a2 2 0 1 0 0 4v5h-5a2 2 0 1 1-4 0H4v-5a2 2 0 1 0 0-4V4z"/>'),
  play:svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3z"/>'),
  gallery:svg('<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m4 17 5-5 3 3 2-2 6 4"/>'),
  target:svg('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="m12 12 8-8"/>'),
  structure:svg('<rect x="4" y="4" width="5" height="5" rx="1"/><rect x="15" y="4" width="5" height="5" rx="1"/><rect x="4" y="15" width="5" height="5" rx="1"/><path d="M12 6h3M6 9v6M9 17h6"/>'),
  pencil:svg('<path d="m4 20 4.2-1 10-10a2.5 2.5 0 0 0-3.5-3.5l-10 10z"/><path d="m13 6 5 5M4 20l.8-4.8"/>'),
  audit:svg('<path d="M12 3 20 7v5c0 5-3.4 8-8 9-4.6-1-8-4-8-9V7z"/><path d="m8.5 12 2.2 2.2 4.7-5"/>'),
  check:svg('<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.2 2.2 4.7-5"/>'),
  output:svg('<path d="M5 7h14v13H5z"/><path d="M8 7V4h8v3M8 12h8M8 16h5"/>'),
  fullscreen:svg('<path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5"/>'),
  exitFullscreen:svg('<path d="M9 3v5H4M15 3v5h5M4 16h5v5M20 16h-5v5"/>')
  ,chat:svg('<path d="M5 5h14v11H9l-4 4z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/>')
};
const nav = [{id:'today',label:'今日工作',crumb:'AI爆款内容工厂 / 今日工作',icon:'today'}, {id:'pipeline',label:'爆款流水线',crumb:'内容生产 / 爆款流水线',icon:'pipeline'}, {id:'assets',label:'资产中心',crumb:'内容资产 / 资产中心',icon:'assets'}, {id:'team',label:'我的AI团队',crumb:'系统协作 / 我的AI团队',icon:'team'}, {id:'data',label:'数据中心',crumb:'系统数据 / 数据中心',icon:'data'}];
const fallbackTypes = [{id:'dry-goods',name:'干货型',available:true},{id:'recommend',name:'推荐型',available:false,memberOnly:true},{id:'acquisition',name:'获客型',available:false,memberOnly:true},{id:'hot-events',name:'热点事件型',available:false,memberOnly:true},{id:'podcast',name:'播客解读型',available:false,memberOnly:true}];

const API_TIMEOUT_MS = 20000;
async function api(path, options = {}) {
  const { timeoutMs = API_TIMEOUT_MS, headers: customHeaders = {}, signal: externalSignal, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let callerAborted = false;
  const abortFromCaller = () => { callerAborted=true; controller.abort(); };
  externalSignal?.addEventListener('abort', abortFromCaller, {once:true});
  try {
    const response = await fetch(path, {
      headers: {'Content-Type':'application/json', ...customHeaders},
      ...fetchOptions,
      signal: controller.signal
    });
    const raw = await response.text();
    let result = {};
    if (raw) {
      try { result = JSON.parse(raw); }
      catch (_) { throw new Error(response.ok ? '服务返回了无法识别的数据' : `请求失败 (${response.status})`); }
    }
    if (!response.ok) throw new Error(result.error || `请求失败 (${response.status})`);
    return result;
  } catch (error) {
    if (error?.name === 'AbortError' && callerAborted) throw error;
    if (error?.name === 'AbortError') throw new Error('请求超时，请检查本机工作台服务');
    throw error;
  } finally {
    window.clearTimeout(timeout);
    externalSignal?.removeEventListener('abort', abortFromCaller);
  }
}
function updateTodayEditorUrl(){
  const url=new URL(location.href);
  url.searchParams.set('page','today');
  if(state.todayEditor) url.searchParams.set('editor',state.todayEditor.surface); else url.searchParams.delete('editor');
  history.replaceState({},'',url);
}
function editorLabel(surface){ return ({copy:'正文成稿',structure:'爆款结构',topics:'爆款选题表',cases:'案例结构拆解'})[surface]||'今日工作编辑'; }
function isTodayDocumentSurface(surface){ return surface==='structure'||surface==='copy'||surface==='cases'; }
async function loadTodayEditorFile(fileId){
  const editor=state.todayEditor;
  if(!editor||!fileId)return;
  const requestId=++editor.requestId;
  editor.activeFileId=fileId;
  editor.file=null;
  editor.saveState='loading';
  render();
  try{
    const file=await api(`/api/today/editor/file?surface=${encodeURIComponent(editor.surface)}&id=${encodeURIComponent(fileId)}`);
    if(!state.todayEditor||state.todayEditor.requestId!==requestId)return;
    if(isTodayDocumentSurface(editor.surface)){
      file.structureDocument=parseStructureDocument(file.content||'');
      file.originalContent=file.content||'';
      file.originalLabel=file.label;
    }
    editor.file=file;
    editor.saveState='saved';
    render();
  }catch(error){
    if(state.todayEditor&&state.todayEditor.requestId===requestId){ editor.saveState='error'; editor.error=error.message||'读取编辑文件失败'; render(); }
  }
}
async function openTodayEditor(surface){
  if(state.type!=='dry-goods'){ toast('当前内容类型暂未开放网页内编辑'); return; }
  const editor={surface,files:[],activeFileId:'',file:null,filter:surface==='copy'?'written':'pending',saveState:'loading',saveTimer:0,requestId:0,catalogLoaded:false,catalogLoading:false,topicColumnsFrozen:topicColumnsFrozen(),editMode:false,draftDirty:false,focusMode:false,fileSidebarCollapsed:false};
  state.todayEditor=editor;
  updateTodayEditorUrl();
  render();
}
async function hydrateTodayEditor(editor=state.todayEditor){
  if(!editor||editor.catalogLoaded||editor.catalogLoading)return;
  editor.catalogLoading=true;
  try{
    const catalog=await api(`/api/today/editor?surface=${encodeURIComponent(editor.surface)}`);
    if(state.todayEditor!==editor)return;
    editor.files=catalog.files||[];
    editor.catalogLoaded=true;
    editor.catalogLoading=false;
    const preferred=editor.files.find(item=>item.pending)||editor.files[0];
    if(preferred) await loadTodayEditorFile(preferred.id); else { editor.saveState='empty'; render(); }
  }catch(error){
    if(state.todayEditor===editor){ editor.catalogLoaded=true; editor.catalogLoading=false; editor.saveState='error'; editor.error=error.message||'打开编辑器失败'; render(); }
  }
}
async function closeTodayEditor({refreshToday=true}={}){
  const editor=state.todayEditor;
  if(editor&&isTodayDocumentSurface(editor.surface)&&editor.editMode&&editor.draftDirty){
    const saved=await finishTodayEditorEdit({confirm:false});
    if(!saved)return false;
    toast('修改已自动保存');
  }
  if(editor?.saveTimer){
    window.clearTimeout(editor.saveTimer);
    editor.saveTimer=0;
    await saveTodayEditorFile();
    if(state.todayEditor!==editor||editor.saveState!=='saved')return false;
  }
  state.todayEditor=null;
  updateTodayEditorUrl();
  if(refreshToday&&state.page==='today') await refresh('editor-close');
  else render();
  return true;
}
function scheduleTodayEditorSave(){
  const editor=state.todayEditor;
  if(!editor?.file)return;
  if(editor.saveTimer) window.clearTimeout(editor.saveTimer);
  editor.saveState='pending';
  if(isTodayDocumentSurface(editor.surface)&&editor.editMode){
    editor.draftDirty=true;
    renderTodayEditorSaveState();
    return;
  }
  renderTodayEditorSaveState();
  editor.saveTimer=window.setTimeout(()=>saveTodayEditorFile().catch(()=>{}),800);
}
function renderTodayEditorSaveState(){
  const node=$('[data-editor-save-state]');
  if(!node||!state.todayEditor)return;
  const labels={loading:'读取中',pending:'等待保存',saving:'保存中',saved:'已保存',conflict:'文件已更新',error:'保存失败',empty:'暂无文件'};
  node.textContent=state.todayEditor.editMode&&state.todayEditor.draftDirty?'修改中，尚未覆盖原文':(labels[state.todayEditor.saveState]||'');
  node.dataset.state=state.todayEditor.saveState;
}
async function saveTodayEditorFile(options={}){
  const editor=state.todayEditor, file=editor?.file;
  if(!editor||!file)return;
  const documentSurface=isTodayDocumentSurface(editor.surface);
  const requestedRename=documentSurface&&Boolean(file.renameRequested||file.candidateFilename);
  editor.saveTimer=0;
  editor.saveState='saving';
  renderTodayEditorSaveState();
  const payload={surface:editor.surface,id:file.id,expectedSha256:file.sha256};
  if(editor.surface==='structure'){
    payload.content=serializeStructureDocument(file.structureDocument);
    if(requestedRename) payload.filename=file.label;
  }else if(editor.surface==='copy'){
    const input=$('#todayCopyMarkdownEditor');
    if(!input)return;
    file.content=input.value;
    payload.content=file.content;
    if(requestedRename) payload.filename=file.label;
  }else if(editor.surface==='cases'){
    payload.content=serializeStructureDocument(file.structureDocument);
    if(requestedRename) payload.filename=file.label;
  }else if(file.kind==='markdown'){
    const input=$('#todayMarkdownEditor');
    if(!input)return;
    payload.content=input.value;
  }else{
    payload.rows=file.table.rows;
  }
  try{
    const result=await api('/api/today/editor/file',{method:'PUT',body:JSON.stringify(payload)});
    if(!state.todayEditor||state.todayEditor!==editor||editor.file!==file)return;
    const previousId=file.id;
    file.id=result.id||file.id;
    file.label=result.label||file.label;
    file.pending=Boolean(result.pending);
    file.copyEditorStatus=result.copyEditorStatus||file.copyEditorStatus||'pending';
    file.sha256=result.sha256;
    file.modifiedAt=result.savedAt;
    file.candidateId=result.candidateId||'';
    file.candidateStatus=result.candidateStatus||'none';
    file.candidateFilename=result.candidateFilename||'';
    if(documentSurface){
      const catalogItem=editor.files.find(item=>item.id===previousId);
      if(catalogItem) Object.assign(catalogItem,{id:file.id,label:file.label,modifiedAt:file.modifiedAt,pending:file.pending,copyEditorStatus:file.copyEditorStatus,candidateId:file.candidateId,candidateStatus:file.candidateStatus,candidateFilename:file.candidateFilename});
      editor.activeFileId=file.id;
      file.renameRequested=false;
      file.originalContent=file.content;
      file.originalLabel=file.label;
      if(editor.surface==='copy') file.structureDocument=parseStructureDocument(file.content);
      editor.draftDirty=false;
      if(options.exitEdit)editor.editMode=false;
    }
    if(editor.surface==='structure'){
      file.structureFourFilled=Boolean(result.structureFourFilled);
      file.structureFourStatus=result.structureFourStatus||'未填写结构四';
      file.structureFourReason=result.structureFourReason||'';
      file.pending=!file.structureFourFilled;
      const catalogItem=editor.files.find(item=>item.id===previousId);
      if(catalogItem) Object.assign(catalogItem,{structureFourFilled:file.structureFourFilled,structureFourStatus:file.structureFourStatus,structureFourReason:file.structureFourReason,pending:file.pending,modifiedAt:file.modifiedAt});
    }
    editor.saveState='saved';
    if(editor.surface==='structure'||requestedRename||options.exitEdit) render();
    else renderTodayEditorSaveState();
  }catch(error){
    if(!state.todayEditor||state.todayEditor!==editor)return;
    editor.saveState=String(error.message||'').includes('重新加载')?'conflict':'error';
    editor.error=error.message||'保存失败';
    renderTodayEditorSaveState();
    toast(editor.error);
  }
}
async function finishTodayEditorEdit({confirm=true}={}){
  const editor=state.todayEditor;
  if(!editor||!isTodayDocumentSurface(editor.surface)||!editor.editMode)return true;
  if(!editor.draftDirty){ editor.editMode=false; render(); return true; }
  const ownerConfirmedCase=editor.surface==='cases'&&/^[√✓]/.test(String(editor.file?.label||'').trim());
  const prompt=ownerConfirmedCase?'标题已加 √：确认直接保存为正式案例拆解，并写入人工确认回执吗？':'确认保存编辑候选吗？正式文件不会被直接覆盖，需小审通过后才可发布。';
  if(confirm&&!window.confirm(prompt))return false;
  await saveTodayEditorFile({exitEdit:true});
  return state.todayEditor===editor&&editor.saveState==='saved';
}
let taskRefreshTimer = 0;
let manualRefreshInFlight = false;
let taskPollingFailureNotified = false;
let pageRequestVersion = 0;
let activePageRequestController = null;
let lastStablePageState = null;
let teamCycleStartTimer = 0;
let teamCycleInterval = 0;
const TEAM_ENTRANCE_DURATION_MS = 1200;
const TEAM_CYCLE_INTERVAL_MS = 3000;
const localDateKey = value => { const date=value instanceof Date?value:new Date(value); const offset=date.getTimezoneOffset()*60000; return new Date(date.getTime()-offset).toISOString().slice(0,10); };
const calendarMonthKey = () => `${state.calendarDate.getFullYear()}-${String(state.calendarDate.getMonth()+1).padStart(2,'0')}`;
async function loadPlanCalendar() {
  state.planCalendar = await api(`/api/plans?month=${calendarMonthKey()}`);
  const firstDate = `${calendarMonthKey()}-01`;
  if (!state.selectedPlanDate || !state.selectedPlanDate.startsWith(calendarMonthKey())) state.selectedPlanDate = state.calendarDate.getFullYear() === new Date().getFullYear() && state.calendarDate.getMonth() === new Date().getMonth() ? localDateKey(new Date()) : firstDate;
}
async function refresh(reason = 'local-update', {signal, requestVersion} = {}) {
  const page=state.page;
  const previousSnapshot = state.data?.snapshotId || '';
  const dashboardRequest=api(`/api/dashboard/page/${page}`,{signal});
  const calendarRequest=page==='today' ? api(`/api/plans?month=${calendarMonthKey()}`,{signal}).catch(error=>({error})) : Promise.resolve(null);
  const [dashboard, calendar] = await Promise.all([dashboardRequest,calendarRequest]);
  if(signal?.aborted || (requestVersion && requestVersion!==pageRequestVersion) || page!==state.page)return false;
  if(page==='today'){
    if(calendar?.error){
      // Calendar data must not take down the whole workbench when SQLite is
      // temporarily busy. Keep the last valid calendar until its next retry.
      if (!state.planCalendar) state.planCalendar = {plans:[], occurrences:[], summary:{}};
      console.warn('工作计划暂时不可用，将保留上次数据。', calendar.error);
    }else if(calendar){
      state.planCalendar=calendar;
      const firstDate = `${calendarMonthKey()}-01`;
      if (!state.selectedPlanDate || !state.selectedPlanDate.startsWith(calendarMonthKey())) state.selectedPlanDate = state.calendarDate.getFullYear() === new Date().getFullYear() && state.calendarDate.getMonth() === new Date().getMonth() ? localDateKey(new Date()) : firstDate;
    }
  }
  state.data = dashboard;
  state.todaySyncing=false;
  if(page==='today')persistTodaySnapshot(dashboard,state.planCalendar);
  const shouldAnimate = ['initial', 'page-switch', 'manual-refresh'].includes(reason);
  if (page === 'data' && shouldAnimate && (!previousSnapshot || previousSnapshot !== dashboard.snapshotId || reason === 'page-switch')) state.dataAnimationRequested = true;
  state.motionReason = shouldAnimate ? reason : 'none';
  state.pageLoading=false;
  lastStablePageState={page,stateData:state.data,planCalendar:state.planCalendar,selectedPlanDate:state.selectedPlanDate,todaySyncing:state.todaySyncing};
  render();
  document.getElementById('workbenchSplash')?.classList.add('is-hidden');
  return true;
}
async function navigateToPage(nextPage){
  if(nextPage===state.page)return;
  if(state.todayEditor&&!(await closeTodayEditor({refreshToday:false})))return;
  const previous=lastStablePageState||{page:state.page,stateData:state.data,planCalendar:state.planCalendar,selectedPlanDate:state.selectedPlanDate,todaySyncing:state.todaySyncing};
  const requestVersion=++pageRequestVersion;
  activePageRequestController?.abort();
  const controller=new AbortController();
  activePageRequestController=controller;
  state.page=nextPage;
  state.pageLoading=true;
  state.todaySyncing=false;
  if(nextPage==='data')state.dataAnimationRequested=true;
  render();
  try{
    await refresh('page-switch',{signal:controller.signal,requestVersion});
  }catch(error){
    if(controller.signal.aborted||requestVersion!==pageRequestVersion)return;
    state.page=previous.page;
    state.data=previous.stateData;
    state.planCalendar=previous.planCalendar;
    state.selectedPlanDate=previous.selectedPlanDate;
    state.todaySyncing=previous.todaySyncing;
    state.pageLoading=false;
    state.motionReason='none';
    render();
    toast(error.message||'页面暂时无法打开，请重试');
  }finally{
    if(requestVersion===pageRequestVersion)activePageRequestController=null;
  }
}
async function syncWorkbenchData() {
  if (manualRefreshInFlight) return;
  manualRefreshInFlight = true;
  const button = $('#refreshButton');
  if (button) {
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.title = '正在同步文件夹';
    button.classList.add('is-syncing');
  }
  try {
    if(state.page==='today')clearTodaySnapshot();
    const result = await api('/api/workbench/folder-sync', {method:'POST', body:JSON.stringify({page:state.page})});
    state.syncHighlights=Object.fromEntries(Object.entries(result.sync?.changes||{}).filter(([, change])=>Number(change.added||0)+Number(change.changed||0)>0).map(([moduleId])=>[moduleId,true]));
    state.data = result.dashboard;
    if(state.page==='today'){
      await loadPlanCalendar();
      persistTodaySnapshot(state.data,state.planCalendar);
    }
    state.dataAnimationRequested = true;
    state.motionReason = 'manual-refresh';
    render();
    const sync=result.sync?.changes||{}, totals=Object.values(sync).reduce((all,item)=>({added:all.added+Number(item.added||0),changed:all.changed+Number(item.changed||0),removed:all.removed+Number(item.removed||0)}),{added:0,changed:0,removed:0});
    toast(`已同步文件夹：新增 ${totals.added} · 变更 ${totals.changed} · 移除 ${totals.removed}`);
  } catch (error) {
    toast(error.message || '同步失败，已保留当前数据');
  } finally {
    manualRefreshInFlight = false;
    const activeButton = $('#refreshButton');
    if (activeButton) {
      activeButton.disabled = false;
      activeButton.removeAttribute('aria-busy');
      activeButton.title = '同步文件夹';
      activeButton.classList.remove('is-syncing');
    }
  }
}
function toast(message) { const node = $('#toast'); node.textContent = message; node.classList.add('show'); setTimeout(() => node.classList.remove('show'), 3200); }
async function requestDesktopFolder(endpoint,payload,label='本机资产目录'){
  const result=await api(endpoint,{method:'POST',body:JSON.stringify(payload)});
  if(result.status!=='queued-for-desktop'){
    throw new Error('桌面桥接未返回可核验的文件夹打开请求');
  }
  toast(`正在请求资源管理器打开：${label}`);
  for(let attempt=0;attempt<40;attempt+=1){
    await wait(250);
    const status=await api(`/api/desktop-bridge/folder-status?requestId=${encodeURIComponent(result.requestId)}`);
    if(status.status==='opened'){
      toast(`已确认在本机打开：${label}`);
      return status;
    }
    if(status.status==='failed')throw new Error(status.message||'本机文件夹未能打开');
    if(status.status==='claimed')toast('桌面桥接正在打开资源管理器…');
  }
  throw new Error('10 秒内未检测到可见资源管理器窗口，请检查桌面桥接状态');
}
async function openTodayFolder(button){
  if(button.disabled)return;
  button.disabled=true;
  try{
    await requestDesktopFolder('/api/today/open-folder',{key:button.dataset.todayFolder},button.dataset.todayFolderLabel||'今日工作目录');
  }catch(error){
    toast(error.message||'打开本机目录失败');
  }finally{
    button.disabled=false;
  }
}
function readTodaySnapshot(){
  try{
    const cached=JSON.parse(sessionStorage.getItem(todaySnapshotStorageKey)||'null');
    if(!cached||Date.now()-Number(cached.savedAt||0)>todaySnapshotMaxAgeMs)return null;
    if(!cached.data?.todayModules||!cached.planCalendar)return null;
    return cached;
  }catch(_){ return null; }
}
function persistTodaySnapshot(data,planCalendar){
  if(!data?.todayModules||!planCalendar)return;
  try{
    sessionStorage.setItem(todaySnapshotStorageKey,JSON.stringify({savedAt:Date.now(),data:{todayModules:data.todayModules,types:data.types||fallbackTypes,assets:data.assets||{},sessions:data.sessions||[],bridge:data.bridge||{},desktopNavigation:data.desktopNavigation||{}},planCalendar}));
  }catch(_){ /* Private mode or quota errors must not affect the workbench. */ }
}
function clearTodaySnapshot(){ try{sessionStorage.removeItem(todaySnapshotStorageKey);}catch(_){} }
function restoreTodaySnapshot(){
  if(state.page!=='today'||state.todayEditor)return false;
  const cached=readTodaySnapshot();
  if(!cached)return false;
  state.data=cached.data;
  state.planCalendar=cached.planCalendar;
  state.todaySyncing=true;
  state.motionReason='none';
  lastStablePageState={page:state.page,stateData:state.data,planCalendar:state.planCalendar,selectedPlanDate:state.selectedPlanDate,todaySyncing:state.todaySyncing};
  render();
  return true;
}
function task(id){ return state.data.tasks.find(item=>item.id===id) || {count:0,status:'暂无数据',title:id}; }
function hasTodayTaskData(){ return Array.isArray(state.data.todayTasks?.[state.type]) && state.data.todayTasks[state.type].length===6; }
function todayTask(id){ return (state.data.todayTasks?.[state.type]||[]).find(item=>item.id===id) || null; }
function types(){ return state.data?.types || fallbackTypes; }
function currentType(){ return types().find(item=>item.id===state.type) || types()[0]; }
function renderTypeMenu(){
  const menu=$('#typeMenu');
  if(!menu)return;
  menu.hidden=!state.typeMenuOpen;
  if(!state.typeMenuOpen){ menu.innerHTML=''; return; }
  menu.innerHTML=types().map(type=>`<button class="type-menu-item ${type.id===state.type?'active':''} ${type.available?'':'locked'}" data-type-menu="${esc(type.id)}" aria-current="${type.id===state.type?'true':'false'}"><span class="type-menu-dot"></span><span><b>${esc(type.name)}</b><small>${esc(type.available?(type.memberOnly?'已解锁':'已启用'):'会员专享')}</small></span>${type.available?'':`<em>${brandIcon('lock')}</em>`}</button>`).join('');
  const anchor=document.activeElement?.matches?.('#typePicker,#mobileTypePicker,#sideTypeButton')?document.activeElement:($('#typePicker')||$('#sideTypeButton'));
  if(!anchor){ state.typeMenuOpen=false; return; }
  if(anchor.id==='typePicker'){
    anchor.closest('.type-picker-wrap').appendChild(menu);
    menu.classList.remove('type-menu-floating');
    menu.style.top='';
    menu.style.left='';
    return;
  }
  document.body.appendChild(menu);
  menu.classList.add('type-menu-floating');
  const rect=anchor.getBoundingClientRect();
  menu.style.top=`${Math.min(window.innerHeight-18,rect.bottom+8)}px`;
  menu.style.left=`${Math.max(12,Math.min(window.innerWidth-330,rect.right-310))}px`;
}
function renderNav() { $('#nav').innerHTML = nav.map(item => { const navIcon = brandIcon(brandNavIcons[item.id], ''); return `<button class="nav-item ${item.id===state.page?'active':''}" data-page="${item.id}"><i>${navIcon}</i><span>${item.label}</span></button>`; }).join(''); const item=nav.find(x=>x.id===state.page); $('#crumb').textContent=item.crumb; }
function scheduleTaskRefresh(){
  window.clearTimeout(taskRefreshTimer);
  // The data center is a manual snapshot. Background task polling must not
  // redraw its charts or restart their entrance animations.
  if(state.page==='data') return;
  const active=(state.data.sessions||[]).some(session=>['creating-desktop-task','running','repairing','reconnecting','needs-user','waiting-audit'].includes(session.status));
  if(active) taskRefreshTimer=window.setTimeout(()=>pollActiveSessions().catch(error=>toast(error.message||'任务状态刷新失败')),5000);
}
async function pollActiveSessions(){
  try {
    const result=await api('/api/sessions?scope=active&limit=12');
    const before=(state.data.sessions||[]).map(item=>`${item.id}:${item.status}:${item.updated_at}`).join('|');
    const activeIds=new Set((result.sessions||[]).map(item=>item.id));
    const recent=(state.data.sessions||[]).filter(item=>!activeIds.has(item.id)&&!['creating-desktop-task','running','repairing','reconnecting','needs-user','waiting-audit'].includes(item.status));
    state.data.sessions=[...(result.sessions||[]),...recent].slice(0,12);
    const after=(state.data.sessions||[]).map(item=>`${item.id}:${item.status}:${item.updated_at}`).join('|');
    taskPollingFailureNotified=false;
    if(before!==after) render();
  } catch (error) {
    // Keep polling after transient local-service failures, but avoid a toast
    // every five seconds while the service is recovering.
    if (!taskPollingFailureNotified) toast(error.message||'任务状态暂时无法刷新，将自动重试');
    taskPollingFailureNotified=true;
  } finally {
    scheduleTaskRefresh();
  }
}
function animateDataMetrics(){
  document.querySelectorAll('[data-chart-count]').forEach(node=>{
    // Values must remain readable when Chromium throttles animation frames in
    // a scaled or background workbench. Visual motion is handled by chart CSS.
    node.textContent=nf(Number(node.dataset.chartCount||0));
  });
}
function clearTeamCycle(){ window.clearTimeout(teamCycleStartTimer); window.clearInterval(teamCycleInterval); teamCycleStartTimer=0; teamCycleInterval=0; }
function prefersReducedMotion(){ return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches); }
function setActiveTeamStage(root, stage){
  root.querySelectorAll('[data-team-stage]').forEach(node=>node.classList.toggle('is-cycle-active', Number(node.dataset.teamStage)===stage));
}
function scheduleTeamCycle(motionReason){
  clearTeamCycle();
  if(state.page!=='team')return;
  const root=$('.team-v10');
  if(!root||prefersReducedMotion())return;
  let stage=0;
  const advance=()=>{ setActiveTeamStage(root,stage); stage=(stage+1)%6; };
  const start=()=>{ advance(); teamCycleInterval=window.setInterval(advance,TEAM_CYCLE_INTERVAL_MS); };
  const hasEntrance=['initial','page-switch','manual-refresh'].includes(motionReason);
  teamCycleStartTimer=window.setTimeout(start,hasEntrance?TEAM_ENTRANCE_DURATION_MS:0);
}
function renderPageLoading(){
  const label=nav.find(item=>item.id===state.page)?.label||'工作台';
  return `<section class="workbench-page-loading" role="status" aria-live="polite"><div class="workbench-loading-mark"></div><p>正在打开${esc(label)}…</p></section>`;
}
function render(){ const motionReason=state.motionReason||'none'; document.body.dataset.page=state.page; document.body.classList.toggle('today-editor-open',state.page==='today'&&Boolean(state.todayEditor)); renderNav(); const type=currentType(); const typeName=$('#typeName'), mobileTypeName=$('#mobileTypeName'), sideType=$('#sideType'); if(typeName)typeName.textContent=type.name; if(mobileTypeName)mobileTypeName.textContent=type.name; if(sideType)sideType.textContent=type.name; renderTypeMenu(); const renderers={today:state.todayEditor?renderTodayEditor:renderToday,pipeline:renderPipeline,assets:renderAssets,team:renderTeam,data:renderData}; const app=$('#app'); app.dataset.motion=motionReason; app.innerHTML=state.pageLoading?renderPageLoading():renderers[state.page](); if(state.page==='data'&&state.dataAnimationRequested&&!state.pageLoading){ animateDataMetrics(); state.dataAnimationRequested=false; } state.motionReason='none'; bindPageEvents(); fitWorkbenchCanvas(); scheduleTaskRefresh(); scheduleTeamCycle(motionReason); if(state.page==='today'&&state.todayEditor&&!state.todayEditor.catalogLoaded)hydrateTodayEditor(state.todayEditor); }
function todayControl(item){
  if(item.target?.kind==='refresh') return `<button class="today-card-action refresh" type="button" data-today-refresh="${esc(item.target.action)}" aria-label="${esc(item.title)}"><img src="${brandAsset('icons/refresh.svg')}" alt=""></button>`;
  if(item.target?.kind==='folder'||item.target?.kind==='editor') return `<i class="today-card-action">${brandIcon('chevron-right')}</i>`;
  return `<i class="today-card-action locked">${brandIcon('lock')}</i>`;
}
function todayTitle(item){ const name=String(item.title||'').replace('干货型','干货型 '); return esc(name).replace(' ', '<br>'); }
function todayCardCopy(id,item){ const title=todaySingleLineTitles.has(id)?esc(item.title):todayTitle(item); return `<span class="today-card-copy"><span class="today-card-meta"><i class="today-stage-icon">${brandIcon(todayTaskIcons[id]||'document')}</i><b class="today-status-tag ${todayTagTones[id]||'orange'}">${esc(item.tag)}</b></span><strong>${title}</strong></span>`; }
function queueTask(id){ const item=todayTask(id), editor=item.target?.kind==='editor', folder=item.target?.kind==='folder', clickable=editor||folder, tag=clickable?'button':'article', attrs=editor?` data-today-editor="${esc(item.target.surface)}" type="button"`:folder?` data-today-folder="${esc(item.target.key)}" type="button"`:'', disabled=clickable&&item.locked?' disabled':''; return `<${tag} class="today-queue-task" data-today-card="${esc(id)}"${attrs}${disabled}>${todayCardCopy(id,item)}<em>${item.count===null?'--':nf(item.count)}</em><small class="today-card-note">${esc(item.status)}</small>${todayControl(item)}</${tag}>`; }
function minorTask(id){ const item=todayTask(id), folder=item.target?.kind==='folder', tag=folder?'button':'article', attrs=folder?` data-today-folder="${esc(item.target.key)}" type="button"`:'', disabled=folder&&item.locked?' disabled':'', centered=id==='refresh-topics'||id==='break-review'?' is-centered':'', idle=item.displayMode==='refresh', zero=item.displayMode==='zero', value=idle?`<span class="today-refresh-indicator" aria-label="当前没有待处理资料">${brandIcon('refresh')}</span>`:`<em${zero?' aria-label="今日已刷新，当前没有待处理资料"':''}>${item.count===null?'--':nf(item.count)}</em>`; return `<${tag} class="today-minor-task${idle?' is-idle-refresh':''}${zero?' is-refreshed-zero':''}"${attrs}${disabled}>${todayCardCopy(id,item)}${value}<small class="today-card-note${centered}">${esc(item.status)}</small>${todayControl(item)}</${tag}>`; }
const planTone = {"dry-goods":"orange",recommend:"blue",acquisition:"green",podcast:"purple","hot-events":"red"};
const weekdayLabels = ['周一','周二','周三','周四','周五','周六','周日'];
function planTypeName(typeId){ return types().find(item=>item.id===typeId)?.name||'内容类型'; }
function repeatLabel(plan){
  if(plan.repeat_rule==='daily') return '每天';
  if(plan.repeat_rule==='monthly') return `每月${Number(plan.monthly_day)||Number(String(plan.plan_date||'').slice(-2))||1}日`;
  if(plan.repeat_rule==='weekly') return `每周${(plan.weekdays||[]).map(day=>weekdayLabels[Number(day)]).filter(Boolean).join('、')}`;
  return '单次';
}
function planLabel(occurrence){ return `${planTypeName(occurrence.contentType)} · ${occurrence.targetCount}条`; }
function calendarHTML(){
  const date=state.calendarDate, year=date.getFullYear(), month=date.getMonth(), calendar=state.planCalendar||{occurrences:[],summary:{occurrenceCount:0,targetCount:0},plans:[]};
  const first=(new Date(year,month,1).getDay()+6)%7, days=new Date(year,month+1,0).getDate(), last=new Date(year,month,0).getDate();
  const byDate=(calendar.occurrences||[]).reduce((result,item)=>{(result[item.date]||=[]).push(item);return result;},{});
  const cells=[];
  for(let index=0;index<42;index++){
    const day=index-first+1, shownDay=day<1?last+day:day>days?day-days:day, muted=day<1||day>days;
    const key=`${year}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`, items=!muted?(byDate[key]||[]):[];
    const tones=[...new Set(items.map(item=>planTone[item.contentType]||'orange'))];
    cells.push(`<button class="${muted?'muted ':''}${items.length?'planned ':''}${state.selectedPlanDate===key?'selected':''}" ${muted?'disabled':''} data-plan-date="${key}" aria-label="${key} ${items.length?`${items.length} 项计划`:'无计划'}"><span>${shownDay}</span>${tones.length?`<i class="plan-dots">${tones.map(tone=>`<b class="${tone}"></b>`).join('')}</i>`:''}</button>`);
  }
  const selected=byDate[state.selectedPlanDate]||[];
  const rows=selected.length?selected.map(item=>{
    const plan=(calendar.plans||[]).find(entry=>entry.id===item.planId)||{};
    const tone=planTone[item.contentType]||'orange';
    return `<div class="plan-row${item.completed?' is-completed':''}"><button class="plan-complete" data-plan-completion="${esc(item.planId)}" data-plan-date="${esc(item.date)}" data-completed="${item.completed?'true':'false'}" aria-label="${item.completed?'标记为未完成':'标记为已完成'}" aria-pressed="${item.completed?'true':'false'}">${brandIcon('check-circle')}</button><i class="dot ${tone}"></i><span><b class="today-plan-item-tag ${tone}">${esc(planLabel(item))}</b></span><button class="plan-edit" data-edit-plan="${esc(item.planId)}" aria-label="编辑计划">${brandIcon('pencil')}</button><button class="plan-delete" data-delete-plan="${esc(item.planId)}" aria-label="删除计划">×</button></div>`;
  }).join(''):'<p>今天还没有安排工作</p>';
  return `<div class="today-calendar-head"><h2>${brandIcon('calendar')}<span>工作计划</span></h2><div class="today-month-nav"><button data-calendar-offset="-1" aria-label="上个月"><img src="${brandAsset('icons/chevron-right.svg')}" alt=""></button><b>${year}年${month+1}月</b><button data-calendar-offset="1" aria-label="下个月"><img src="${brandAsset('icons/chevron-right.svg')}" alt=""></button></div></div><div class="weekdays"><b>一</b><b>二</b><b>三</b><b>四</b><b>五</b><b>六</b><b>日</b></div><div class="calendar-days">${cells.join('')}</div><div class="today-plan-summary"><h3><span class="today-plan-tag">今日工作</span></h3><div class="plans-list">${rows}</div></div><button class="today-plan-button" data-action="plan" type="button">设置工作计划</button>`;
}
function editorPendingTopic(row, columns){
  const typeIndex=columns.findIndex(value=>/内容类型|结构类型/.test(value));
  const selectedIndex=columns.findIndex(value=>/是否选中/.test(value));
  return (typeIndex<0||!String(row[typeIndex]||'').trim()) && (selectedIndex<0||String(row[selectedIndex]||'').trim()!=='否');
}
function markdownTableCells(line){
  // 允许 Windows 文件中常见的 BOM、行尾缺失的竖线，以及编辑器留下的空白。
  // 预览必须比写入编辑器更宽容，不能因为一行格式轻微变化而回退成原始 | 文本。
  const text=String(line||'').replace(/^[\uFEFF\u200B]+/,'').trim().replace(/^\\\|/,'|');
  if(!text.startsWith('|'))return [];
  const body=text.endsWith('|')?text.slice(1,-1):text.slice(1);
  const cells=[], pushCell=()=>{ cells.push(cell.trim()); };
  let cell='', escaped=false;
  for(const char of body){
    if(escaped){ cell+=char; escaped=false; continue; }
    if(char==='\\'){ escaped=true; continue; }
    if(char==='|'){ pushCell(); cell=''; continue; }
    cell+=char;
  }
  if(escaped)cell+='\\';
  pushCell();
  return cells;
}
function markdownTableDivider(line, expectedColumns){
  const cells=markdownTableCells(line);
  return cells.length===expectedColumns&&cells.every(cell=>/^:?-{3,}:?$/.test(cell.replace(/\s/g,'')));
}
function markdownTableSpacer(line){
  // 部分历史拆解在表头与分隔线间留下空行或单独的 |；它们不应破坏表格识别。
  return /^\s*(?:\\?\|\s*)?$/.test(String(line||''));
}
function parseStructureDocument(content){
  const lines=String(content||'').replace(/\r\n/g,'\n').split('\n'), blocks=[], text=[];
  const flushText=()=>{ if(text.length){ blocks.push({kind:'text',content:text.join('\n')}); text.length=0; } };
  for(let index=0;index<lines.length;){
    const columns=markdownTableCells(lines[index]);
    let dividerIndex=index+1;
    while(dividerIndex<lines.length&&markdownTableSpacer(lines[dividerIndex]))dividerIndex+=1;
    if(columns.length>1&&markdownTableDivider(lines[dividerIndex],columns.length)){
      flushText();
      const rows=[];
      index=dividerIndex+1;
      while(index<lines.length){
        const row=markdownTableCells(lines[index]);
        if(row.length!==columns.length)break;
        rows.push(row);
        index+=1;
      }
      blocks.push({kind:'table',columns,divider:markdownTableCells(lines[index-1]),rows});
      continue;
    }
    text.push(lines[index]);
    index+=1;
  }
  flushText();
  return {blocks};
}
function serializeStructureDocument(structureDocument){
  const escapeCell=value=>String(value??'').replace(/\n/g,' ').replace(/\|/g,'\\|').trim();
  return (structureDocument?.blocks||[]).map(block=>{
    if(block.kind==='text')return block.content;
    const line=cells=>`| ${cells.map(escapeCell).join(' | ')} |`;
    return [line(block.columns),line(block.divider||block.columns.map(()=>'---')),...(block.rows||[]).map(line)].join('\n');
  }).join('\n');
}
function structureTextHTML(content,editable=true){
  const lines=String(content||'').split('\n'), html=[];
  for(const [lineIndex,line] of lines.entries()){
    const heading=line.match(/^(#{1,6})\s+(.+)$/);
    const listItem=line.match(/^[-*]\s+(.+)$/);
    const textLine=(tag,prefix,text,extra='')=>`<${tag} class="today-structure-text-line" ${editable?'contenteditable="true" spellcheck="false" data-structure-text-line data-line="'+lineIndex+'" data-prefix="'+esc(prefix)+'"':''} ${extra}>${structureInlineMarkdownHTML(text)}</${tag}>`;
    if(heading){ const level=Math.min(heading[1].length,4); html.push(textLine(`h${level}`,`${heading[1]} `,heading[2])); continue; }
    if(listItem){ html.push(textLine('div',line.slice(0,line.indexOf(listItem[1])),listItem[1],'data-list-item')); continue; }
    if(!line.trim()){ html.push(`<div class="today-structure-blank" ${editable?'contenteditable="true" spellcheck="false" data-structure-text-line data-line="'+lineIndex+'" data-prefix=""':''}><br></div>`); continue; }
    if(/^---+$/.test(line.trim())){ html.push('<hr>'); continue; }
    if(line.startsWith('> ')){ html.push(textLine('blockquote','> ',line.slice(2))); continue; }
    html.push(textLine('p','',line));
  }
  return html.join('');
}
function structureInlineMarkdownHTML(value){
  const fragments=[];
  const stash=html=>{ const token=`\u0000STRUCTURE_INLINE_${fragments.length}\u0000`; fragments.push(html); return token; };
  let safe=esc(String(value??''))
    .replace(/&lt;br\s*\/?\s*&gt;/gi,()=>stash('<br>'))
    .replace(/`([^`\n]+)`/g,(_match,body)=>stash(`<code>${body}</code>`))
    .replace(/\*\*([^\n]+?)\*\*/g,(_match,body)=>stash(`<strong>${body}</strong>`))
    .replace(/~~([^\n]+?)~~/g,(_match,body)=>stash(`<s>${body}</s>`))
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g,(_match,before,body)=>`${before}${stash(`<em>${body}</em>`)}`)
    .replace(/(^|[^_\w])_([^_\n]+)_(?![_\w])/g,(_match,before,body)=>`${before}${stash(`<em>${body}</em>`)}`)
    .replace(/\r?\n/g,()=>stash('<br>'));
  fragments.forEach((html,index)=>{ safe=safe.replaceAll(`\u0000STRUCTURE_INLINE_${index}\u0000`,html); });
  return safe;
}
function structureEditableMarkdown(element){
  const serialize=node=>{
    if(node.nodeType===Node.TEXT_NODE)return node.nodeValue||'';
    if(node.nodeType!==Node.ELEMENT_NODE)return '';
    const content=Array.from(node.childNodes).map(serialize).join('');
    if(node.tagName==='BR')return '<br>';
    if(node.tagName==='STRONG'||node.tagName==='B')return `**${content}**`;
    if(node.tagName==='EM'||node.tagName==='I')return `*${content}*`;
    if(node.tagName==='S'||node.tagName==='DEL')return `~~${content}~~`;
    if(node.tagName==='CODE')return `\`${content}\``;
    if(node.tagName==='DIV'||node.tagName==='P')return `${content}<br>`;
    return content;
  };
  return Array.from(element.childNodes).map(serialize).join('').replace(/\u00a0/g,' ').replace(/(?:<br>){2,}$/,'<br>');
}
function structureTableColumnWidths(count){
  if(count<2)return [100];
  const first=Math.min(20,Math.max(15,100/count));
  const remaining=(100-first)/(count-1);
  return Array.from({length:count},(_,index)=>index===0?first:remaining);
}
function structureDocumentHTML(file,{editable=true}={}){
  const structureDocument=file.structureDocument||parseStructureDocument(file.content||'');
  file.structureDocument=structureDocument;
  return `<article class="today-structure-editor">${structureDocument.blocks.map((block,blockIndex)=>{
    if(block.kind==='text')return `<section ${editable?`data-structure-text-block="${blockIndex}"`:''}>${structureTextHTML(block.content,editable)}</section>`;
    const widths=structureTableColumnWidths(block.columns.length);
    return `<div class="today-structure-table-wrap"><table class="today-structure-table"><colgroup>${widths.map(width=>`<col style="width:${width.toFixed(4)}%">`).join('')}</colgroup><thead><tr>${block.columns.map((column,columnIndex)=>`<th><div class="today-structure-cell" ${editable?`contenteditable="true" spellcheck="false" data-structure-header data-block="${blockIndex}" data-column="${columnIndex}"`:''}>${structureInlineMarkdownHTML(column)}</div></th>`).join('')}</tr></thead><tbody>${block.rows.map((row,rowIndex)=>`<tr>${row.map((value,columnIndex)=>`<td><div class="today-structure-cell" ${editable?`contenteditable="true" spellcheck="false" role="textbox" aria-multiline="true" data-structure-cell data-block="${blockIndex}" data-row="${rowIndex}" data-column="${columnIndex}" aria-label="${esc(block.columns[columnIndex])}"`:''}>${structureInlineMarkdownHTML(value)}</div></td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }).join('')}</article>`;
}
function todayEditorFileMatchesFilter(editor,item){
  if(editor.surface==='topics'||editor.filter==='all')return true;
  if(editor.surface==='cases'){
    if(editor.filter==='filled')return !item.pending;
    if(editor.filter.startsWith('type:'))return String(item.label||'').replace(/^[√✓]\s*/,'').startsWith(editor.filter.slice(5));
    return Boolean(item.pending);
  }
  if(editor.filter==='filled')return Boolean(item.structureFourFilled);
  if(editor.filter==='written')return !item.pending;
  return Boolean(item.pending);
}
function copyEditorStatusLabel(item){
  return item?.copyEditorStatus==='candidate-marked'?'已撰写 · 待小审':item?.pending?'待处理':'已撰写';
}
function editorTableHTML(file, filter){
  const table=file.table, editor=state.todayEditor, frozen=editor?.topicColumnsFrozen!==false, rows=(table?.rows||[]).map((row,index)=>({row,index})).filter(item=>filter==='all'||editorPendingTopic(item.row,table.columns));
  if(!table)return '<div class="today-editor-empty">正在读取选题表…</div>';
  const frozenClass=frozen?' is-columns-frozen':'';
  const headers=table.columns.map((column,index)=>{
    const freezeControl=index===1?`<button class="today-topic-freeze-toggle" data-topic-freeze type="button" aria-pressed="${frozen?'true':'false'}" title="${frozen?'取消冻结前两列':'冻结核心关键词和选题'}">${brandIcon('freeze-columns')}</button>`:'';
    return `<th class="today-topic-column-${index}${index===1?' today-topic-freeze-boundary':''}"><span>${esc(column)}</span>${freezeControl}</th>`;
  }).join('');
  const body=rows.map(({row,index})=>`<tr>${row.map((value,column)=>{ const cell=column===7?`<button class="today-topic-case-select ${value?'is-selected':''}" data-topic-case-select="${index}" type="button" aria-label="选择对标复刻拆解编号">${esc(value||'选择对标拆解')}</button>`:`<input data-topic-cell data-row="${index}" data-column="${column}" value="${esc(value)}" aria-label="${esc(table.columns[column])}">`; return `<td class="today-topic-column-${column}${column===1?' today-topic-freeze-boundary':''}">${cell}</td>`; }).join('')}</tr>`).join('');
  return `<div class="today-topic-table-wrap${frozenClass}" tabindex="0" aria-label="爆款选题表，可横向与纵向滚动"><table class="today-topic-table"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table>${rows.length?'':`<div class="today-editor-empty">当前筛选条件下没有选题。</div>`}</div>`;
}
function renderTodayEditor(){
  const editor=state.todayEditor, isTopics=editor.surface==='topics', isStructure=editor.surface==='structure', isCopy=editor.surface==='copy', isCases=editor.surface==='cases', isDocument=isStructure||isCopy||isCases, files=editor.files.filter(item=>todayEditorFileMatchesFilter(editor,item)), active=editor.file;
  const statusLabels={loading:'正在读取文件',pending:editor.editMode?'修改中，尚未覆盖原文':'将在停止输入后自动保存',saving:'正在自动保存',saved:'已保存',conflict:'文件已更新，请重新加载',error:editor.error||'保存失败',empty:'暂无可编辑文件'};
  const compare=active&&isDocument&&editor.editMode?`<div class="today-editor-compare"><section class="today-editor-pane is-original"><header><b>原文</b><small>只读快照</small></header>${structureDocumentHTML({content:active.originalContent||'',structureDocument:parseStructureDocument(active.originalContent||'')},{editable:false})}</section><section class="today-editor-pane is-draft"><header><b>修改稿</b><span class="today-editor-filename" contenteditable="true" spellcheck="false" role="textbox" aria-label="文件名" data-structure-filename>${esc(active.label)}</span></header>${isCopy?`<textarea id="todayCopyMarkdownEditor" class="today-copy-markdown-editor" spellcheck="false" aria-label="正文 Markdown 修改稿">${esc(active.content||'')}</textarea>`:structureDocumentHTML(active,{editable:true})}</section></div>`:'';
  const work=active?(isTopics?editorTableHTML(active,editor.filter):isDocument?(editor.editMode?compare:structureDocumentHTML(active,{editable:false})):`<textarea id="todayMarkdownEditor" class="today-markdown-editor" spellcheck="false">${esc(active.content||'')}</textarea>`):`<div class="today-editor-empty">${esc(statusLabels[editor.saveState]||'请选择一个文件')}</div>`;
  const filterLabel=isTopics?'待编辑':isStructure?'待编辑':isCases?'待编辑':'待编辑';
  const fileList=files.length?files.map(item=>{
    const fillStatus=isStructure?`<span class="today-editor-file-status ${item.structureFourFilled?'is-filled':'is-unfilled'}" title="${esc(item.structureFourReason||'')}">${esc(item.structureFourStatus||'未填写结构四')}</span>`:isCopy?`<span class="today-editor-file-status ${item.pending?'is-unfilled':'is-written'}">${copyEditorStatusLabel(item)}</span>`:isCases?`<span class="today-editor-file-status ${item.pending?'is-unfilled':'is-filled'}">${item.pending?'待编辑':'已确认'}</span>`:`<small>${item.pending?'待编辑':'已标记'}</small>`;
    return `<button class="${item.id===editor.activeFileId?'active':''}" data-editor-file="${esc(item.id)}"><b>${esc(item.label)}</b><span class="today-editor-file-meta">${fillStatus}<small>${esc(String(item.modifiedAt||'').slice(0,16).replace('T',' '))}</small></span></button>`;
  }).join(''):'<p>当前没有符合条件的文件。</p>';
  const activeStatus=isStructure&&active?`<span class="today-editor-document-status ${active.structureFourFilled?'is-filled':'is-unfilled'}" title="${esc(active.structureFourReason||'')}">${esc(active.structureFourStatus||'未填写结构四')}</span>`:isCopy&&active?`<span class="today-editor-document-status ${active.pending?'is-unfilled':'is-written'}">${copyEditorStatusLabel(active)}</span>`:isCases&&active?`<span class="today-editor-document-status ${active.pending?'is-unfilled':'is-filled'}">${active.pending?'待编辑':'已确认'}</span>`:'';
  const candidateAction=!['copy','topics','structure'].includes(editor.surface)&&active?.candidateId?`<button class="today-editor-candidate-submit" data-candidate-submit="${esc(active.candidateId)}" type="button">提交小审</button>`:'';
  const candidateHint=!['copy','topics','structure'].includes(editor.surface)&&active?.candidateId?`<small class="today-editor-candidate-state">候选已保存${active.candidateFilename?'（含文件名修改）':''}；正式文件需小审通过后才会更新。</small>`:'';
  const surfaceHint=isTopics?'你的手动修改会自动写回爆款选题表。':isStructure?'标题加 √ 即视为已填写，并自动写回正式爆款结构。':isCopy?'你的手动修改会直接写回正式正文文件。':'案例标题加 √ 即为已确认并直接保存；未加 √ 的修改仍先保存为候选。';
  const secondaryFilter=isStructure?`<button data-editor-filter="filled" class="${editor.filter==='filled'?'active':''}">已填写</button>`:isCopy?`<button data-editor-filter="written" class="${editor.filter==='written'?'active':''}">已撰写</button>`:isCases?['干货型','获客型','推荐型'].map(type=>`<button data-editor-filter="type:${type}" class="${editor.filter===`type:${type}`?'active':''}">${type}</button>`).join(''):'';
  const filters=isCases?`<button data-editor-filter="pending" class="${editor.filter==='pending'?'active':''}">待编辑</button><button data-editor-filter="filled" class="${editor.filter==='filled'?'active':''}">已确认</button>${secondaryFilter}<button data-editor-filter="all" class="${editor.filter==='all'?'active':''}">全部</button>`:`<button data-editor-filter="pending" class="${editor.filter==='pending'?'active':''}">${filterLabel}</button>${secondaryFilter}<button data-editor-filter="all" class="${editor.filter==='all'?'active':''}">全部</button>`;
  const documentTitle=`<span>${active?esc(active.label):'选择文件开始编辑'}</span>`;
  const modeControl=isDocument&&active?`<button class="today-editor-mode" data-editor-edit-mode type="button">${editor.editMode?'完成修改':'修改模式'}</button>`:'';
  // Case breakdown view keeps this toolbar intentionally minimal: only the
  // edit-mode toggle is user-facing. Save/audit hints remain in the workflow
  // state and are not repeated beside the document.
  const documentTools=isCases?modeControl:`${activeStatus}${modeControl}${candidateAction}${candidateHint}<small>${surfaceHint}</small>`;
  const pageEyebrow='';
  const focusControl=`<button class="today-editor-focus-toggle" data-editor-focus-mode type="button" aria-pressed="${editor.focusMode?'true':'false'}" title="${editor.focusMode?'退出全屏':'进入全屏'}"><i>${editor.focusMode?icons.exitFullscreen:icons.fullscreen}</i><span>${editor.focusMode?'退出全屏':'全屏'}</span></button>`;
  const filesControl=editor.focusMode?`<button class="today-editor-files-toggle" data-editor-files-toggle type="button" aria-expanded="${editor.fileSidebarCollapsed?'false':'true'}" title="${editor.fileSidebarCollapsed?'展开文件列表':'收起文件列表'}"><i>${icons.layers}</i><span>${editor.fileSidebarCollapsed?'展开文件':'收起文件'}</span></button>`:'';
  const headerMeta=active?`<div class="today-editor-save">${active.relativePath?`<small>${esc(active.relativePath)}</small>`:''}${editor.saveState==='conflict'||editor.saveState==='error'?'<button data-editor-reload type="button">重新加载</button>':''}</div>`:'';
  return `<section class="today-editor-workspace${editor.focusMode?' is-focus-mode':''}${editor.focusMode&&editor.fileSidebarCollapsed?' is-files-collapsed':''}" data-surface="${esc(editor.surface)}"><header class="today-editor-header"><div><button class="today-editor-back" data-editor-back type="button">${brandIcon('chevron-right')}<span>返回今日工作</span></button>${pageEyebrow}<h1>${esc(editorLabel(editor.surface))}</h1></div>${headerMeta}${filesControl}${focusControl}</header><div class="today-editor-layout"><aside class="today-editor-files"><div class="today-editor-filters">${filters}</div><div class="today-editor-file-list">${fileList}</div></aside><main class="today-editor-main"><div class="today-editor-document-head">${documentTitle}<div>${documentTools}</div></div>${work}</main></div></section>`;
}
function renderToday(){
  const groups=state.data.todayModules?.groups||[];
  const input=groups.find(group=>group.id==='input')||{modules:[]};
  const get=id=>(groups.find(group=>group.id===id)?.modules||[])[0]||{};
  const number=value=>nf(Number(value||0));
  const title=(label,icon)=>`<span class="today-library-title">${brandIcon(icon)}<span>${esc(label||'')}</span></span>`;
  const refreshControl=module=>module.refreshMode==='waiting-integration'?'<button disabled title="该模块尚未接入 Skill">等待接入</button>':module.skillAvailable===false?`<button data-skill-locked type="button" title="${esc(module.unlockReason||'会员专享 Skill 尚未解锁')}">${brandIcon('lock')} 未解锁</button>`:`<button data-module-refresh="${esc(module.id||'')}">刷新</button>`;
  const action=module=>`<div class="today-library-actions">${refreshControl(module)}${module.editable?`<button class="secondary" data-today-editor="${esc(module.surface||'')}">编辑</button>`:''}</div>`;
  const pendingClass=module=>state.syncHighlights[module.id]?'today-pending-count is-sync-highlight':'today-pending-count';
  const compact=module=>`<article class="today-input-item${module.refreshMode==='waiting-integration'?' is-waiting-integration':''}"><div><b>${esc(module.label||'')}</b><small class="${pendingClass(module)}">待刷新 ${number(module.refreshCount)}</small></div><strong>${number(module.currentCount)}</strong>${refreshControl(module)}</article>`;
  const library=(module,icon)=>`<article class="today-library-card" data-today-library="${esc(module.id||'')}" data-motion-entry="today-${esc(module.id||'library')}"><header>${title(module.label,icon)}<div class="today-library-counts"><span class="${pendingClass(module)}">待刷新 ${number(module.refreshCount)}</span><span class="today-pending-count">待编辑 ${number(module.editCount)}</span></div></header><strong>${number(module.currentCount)}</strong>${action(module)}</article>`;
  const gallery=get('gallery');
  const syncing=state.todaySyncing?'<span class="today-sync-state" role="status">正在同步</span>':'';
  return `<div class="today-library-grid">${syncing}<section class="today-calendar-card" data-motion-entry="today-calendar">${calendarHTML()}</section><section class="today-input-library" data-motion-entry="today-input"><header><h1>${title('输入库','inbox')}</h1><strong>${number((input.modules||[]).reduce((sum,module)=>sum+Number(module.currentCount||0),0))}</strong></header><div class="today-input-list">${(input.modules||[]).map(compact).join('')}</div></section><section class="today-library-stack today-core-stack">${library(get('topics'),'target')}${library(get('cases'),'layers')}</section><section class="today-output-library" data-motion-entry="today-output"><header><h1>${title('输出库','output')}</h1></header>${library(get('structures'),'structure')}${library(get('copies'),'document')}</section><article class="today-gallery-card" data-motion-entry="today-gallery"><header>${title('配图库','gallery')}<div class="today-library-counts"><span class="today-pending-count">待配图 ${number(gallery.pictureCount)}</span></div></header><strong>${number(gallery.currentCount)}</strong><div class="today-library-actions"><button data-gallery-select>生成配图</button></div></article></div>`;
}
const batchStatusLabel={pending:'准备中','creating-desktop-task':'正在创建 Codex 对话',submitted:'已投递，待 Codex 确认',running:'运行中',repairing:'小审退回并修复中',reconnecting:'连接恢复中', 'needs-user':'等待你的确认','waiting-audit':'等待小审',released:'已放行',completed:'已完成',rejected:'退回',failed:'创建失败',interrupted:'已中断',cancelled:'已取消',blocked:'已阻塞'};
function sessionDisplayStatus(session){return session.business_status||session.status;}
function sessionStatusText(session){const status=sessionDisplayStatus(session);return status==='rejected'&&session.status==='completed'?'已完成 · 小审退回':(batchStatusLabel[status]||status);}
const pipelineStageMeta={
  'source-knowledge':{tag:'已入库',tone:'blue',icon:'inbox',lines:['源知识库']},
  'content-modules':{tag:'已拆解',tone:'blue',icon:'layers',lines:['爆款内容模块']},
  topics:{tag:'已选定',tone:'orange',icon:'target',lines:['爆款选题']},
  cases:{tag:'已锁定',tone:'blue',icon:'layers',lines:['对标爆款']},
  'final-copy':{tag:'已生成',tone:'green',icon:'document',lines:['爆款成稿']},
  'case-cards':{tag:'已拆解',tone:'blue',icon:'layers',lines:['今日复盘','案例卡']},
  'featured-books':{tag:'已拆解',tone:'blue',icon:'featured-books',lines:['精选','好书']},
  'opening-cards':{tag:'已拆解',tone:'blue',icon:'opening-card',lines:['干货型','爆款开头']},
  'selected-topics':{tag:'已选定',tone:'orange',icon:'selected-topic',lines:['干货型','爆款选题']},
  'copy-structures':{tag:'已生成',tone:'green',icon:'copy-structure',lines:['干货型','文案结构']},
  'filled-structures':{tag:'已填写',tone:'purple',icon:'filled-structure',lines:['干货型','爆款结构']},
  'final-copies':{tag:'已生成',tone:'green',icon:'final-copy',lines:['正文','成稿']},
};
function renderPipeline(){
  const stages=state.data.pipeline?.stages||[];
  const meta={
    'source-knowledge':['已入库','blue','inbox'],
    'content-modules':['已拆解','blue','layers'],
    topics:['已选定','orange','target'],
    cases:['已锁定','blue','layers'],
    'filled-structures':['已填写','purple','filled-structure'],
    'final-copy':['已生成','green','document']
  };
  const cards=stages.map((stage,index)=>{const [tag,tone,icon]=meta[stage.id]||['现役','blue','layers'];return `${index?'<i class="pipeline-arrow" aria-hidden="true">→</i>':''}<article tabindex="0" data-pipeline-stage="${esc(stage.id||'')}" class="pipeline-stage-card ${tone}"><span class="pipeline-stage-tag ${tone}">${tag}</span><span class="pipeline-stage-icon">${brandIcon(icon)}</span><h3>${esc(stage.label||'')}</h3><strong class="pipeline-stage-value">${nf(Number(stage.count||0))}</strong><small>${esc(stage.formula||'')}</small></article>`;}).join('');
  const oneClick=state.data.pipeline?.oneClick||{};
  const reason=Array.isArray(oneClick.missing)&&oneClick.missing.length?oneClick.missing.join('、'):'开始现役正文生成';
  return `<div class="active-pipeline"><div class="active-pipeline-track">${cards}</div><div class="pipeline-action-slot"><button class="one-click-orb" data-one-click ${oneClick.enabled?'':'disabled'} title="${esc(reason)}"><i>${brandIcon('spark')}</i><span>一键成稿</span></button></div></div>`;
}
const newestFirst=items=>[...items].sort((left,right)=>{
  const delta=Date.parse(right.updatedAt||0)-Date.parse(left.updatedAt||0);
  return Number.isFinite(delta)&&delta!==0?delta:String(right.title||'').localeCompare(String(left.title||''),'zh-CN');
});
async function gallerySelectionModal(){
  try{
    const payload=await api('/api/today/gallery-candidates');
    const items=payload.candidates||[];
    const first=newestFirst(items.filter(item=>!item.generated));
    const redo=newestFirst(items.filter(item=>item.generated));
    const row=item=>`<label class="generation-select-row gallery-select-row"><input type="checkbox" value="${esc(item.id)}"><span><b>${esc(item.title)}</b></span><em class="generation-mode ${item.generationMode==='regenerate'?'is-regenerate':'is-initial'}">${esc(item.generationLabel||'首次生成')}</em></label>`;
    const section=(title,rows,empty)=>`<section class="generation-select-group"><h3>${esc(title)} <small>${rows.length}</small></h3>${rows.length?rows.map(row).join(''):`<p>${esc(empty)}</p>`}</section>`;
    modal(`<button class="close" data-close>×</button><section class="gallery-select-modal"><span class="eyebrow">配图库</span><h2>选择本次要生成的配图</h2><p>未生成：已打 √ 的正文成稿，但尚未生成对应配图。已生成：下方列出的选题已生成并落盘配图，可重新生成新版本。</p><div class="gallery-select-list">${section('未生成',first,'当前没有待生成配图的已确认正文。')}${section('已生成',redo,'当前没有可重新生成配图的正文。')}</div><footer><button class="outline-button" data-close type="button">取消</button><button class="orange-button" data-gallery-submit type="button" ${items.length?'':'disabled'}>生成配图</button></footer></section>`);
    document.querySelector('[data-gallery-submit]')?.addEventListener('click',async event=>{
      const selected=Array.from(document.querySelectorAll('.gallery-select-row input:checked')).map(input=>input.value);
      if(!selected.length){toast('请至少选择一篇正文');return;}
       try{const session=await api('/api/today/module-refresh',{method:'POST',body:JSON.stringify({moduleId:'gallery',selected})});closeModal();toast(`正在请求 Codex 独立任务：${session.title||''}`);await followVisibleTask(session,event.currentTarget);await refresh();}catch(error){toast(error.message||'配图任务创建失败');}
    });
  }catch(error){toast(error.message||'无法读取已确认正文');}
}
async function caseSelectionModal(){
  try{
    const payload=await api('/api/today/case-candidates');
    const items=payload.candidates||[];
    const first=newestFirst(items.filter(item=>!item.generated));
    const redo=newestFirst(items.filter(item=>item.generated));
    const row=item=>`<label class="generation-select-row case-select-row"><input type="checkbox" value="${esc(item.id)}"><span><b>${esc(item.title)}</b></span><em class="generation-mode ${item.generationMode==='regenerate'?'is-regenerate':'is-initial'}">${esc(item.generationLabel||'首次生成')}</em></label>`;
    const section=(title,rows,empty)=>`<section class="generation-select-group"><h3>${esc(title)} <small>${rows.length}</small></h3>${rows.length?rows.map(row).join(''):`<p>${esc(empty)}</p>`}</section>`;
    modal(`<button class="close" data-close>×</button><section class="generation-select-modal"><span class="eyebrow">案例库</span><h2>选择本次要刷新的对标视频</h2><p>未生成：尚未有对应拆解文件的原文。已生成：已有对应拆解文件，可选择重新生成新版本。两组均按最近生成时间排在前面。</p><div class="generation-select-list">${section('未生成',first,'当前没有待拆解的对标视频。')}${section('已生成',redo,'当前没有可重新生成的对标视频。')}</div><footer><button class="outline-button" data-close type="button">取消</button><button class="orange-button" data-case-generation-submit type="button" ${items.length?'':'disabled'}>开始刷新</button></footer></section>`);
    document.querySelector('[data-case-generation-submit]')?.addEventListener('click',async event=>{
      const selected=Array.from(document.querySelectorAll('.case-select-row input:checked')).map(input=>input.value);
      if(!selected.length){toast('请至少选择一条对标视频');return;}
      event.currentTarget.disabled=true;
      try{const session=await api('/api/today/module-refresh',{method:'POST',body:JSON.stringify({moduleId:'cases',selected})});closeModal();toast(`正在请求 Codex 独立任务：${session.title||''}`);await followVisibleTask(session,event.currentTarget);await refresh();}
      catch(error){toast(error.message||'案例库任务创建失败');event.currentTarget.disabled=false;}
    });
  }catch(error){toast(error.message||'无法读取对标视频清单');}
}
async function topicSelectionModal(){
  try{
    const payload=await api('/api/today/topic-candidates');
    const items=payload.candidates||[];
    const first=newestFirst(items.filter(item=>!item.generated));
    const redo=newestFirst(items.filter(item=>item.generated));
    const row=item=>`<label class="generation-select-row topic-select-row"><input type="checkbox" value="${esc(item.id)}"><span><b>${esc(item.title)}</b></span><em class="generation-mode ${item.generationMode==='regenerate'?'is-regenerate':'is-initial'}">${esc(item.generationLabel||'首次刷新')}</em></label>`;
    const section=(title,rows,empty)=>`<section class="generation-select-group"><h3>${esc(title)} <small>${rows.length}</small></h3>${rows.length?rows.map(row).join(''):`<p>${esc(empty)}</p>`}</section>`;
    modal(`<button class="close" data-close>×</button><section class="generation-select-modal"><span class="eyebrow">选题库</span><h2>选择本次要刷新的对标账号文件</h2><p>未生成：该对标账号文件尚未形成与其内容对应的选题表。已生成：已由选题拆解 Skill 生成并落盘选题表，可选择重新刷新；两组均按最近更新时间排在前面。</p><div class="generation-select-list">${section('未生成',first,'当前没有待首次刷新的对标账号文件。')}${section('已生成',redo,'当前没有可重新刷新的对标账号文件。')}</div><footer><button class="outline-button" data-close type="button">取消</button><button class="orange-button" data-topic-generation-submit type="button" ${items.length?'':'disabled'}>开始刷新</button></footer></section>`);
    document.querySelector('[data-topic-generation-submit]')?.addEventListener('click',async event=>{
      const selected=Array.from(document.querySelectorAll('.topic-select-row input:checked')).map(input=>input.value);
      if(!selected.length){toast('请至少选择一个对标账号文件');return;}
      event.currentTarget.disabled=true;
      try{const session=await api('/api/today/module-refresh',{method:'POST',body:JSON.stringify({moduleId:'topics',selected})});closeModal();toast(`正在请求 Codex 独立任务：${session.title||''}`);await followVisibleTask(session,event.currentTarget);await refresh();}
      catch(error){toast(error.message||'选题库刷新任务创建失败');event.currentTarget.disabled=false;}
    });
  }catch(error){toast(error.message||'无法读取对标账号文件清单');}
}
function generationCandidateRow(item){
  const disabled=!item.eligible;
  const status=disabled?item.reason:(item.generationLabel||'首次生成');
  return `<label class="generation-select-row${disabled?' is-disabled':''}"><input type="checkbox" value="${esc(item.id)}" data-fingerprint="${esc(item.fingerprint)}" ${disabled?'disabled':''}><span><b>${esc(item.title)}</b></span><em class="generation-mode ${item.generationMode==='regenerate'?'is-regenerate':'is-initial'}">${esc(status)}</em></label>`;
}
function bindGenerationSubmit(button){
  if(!button)return;
  button.onclick=async()=>{
    const selections=Array.from(document.querySelectorAll('.generation-select-row input:checked')).map(input=>({id:input.value,fingerprint:input.dataset.fingerprint||''}));
    if(!selections.length){toast('请至少选择一条内容');return;}
    const originalLabel=button.textContent;
    const feedback=document.querySelector('[data-generation-feedback]');
    button.disabled=true;
    button.textContent='正在提交…';
    if(feedback){feedback.hidden=true;feedback.textContent='';}
    try{
      const isPipeline=button.dataset.generationPipeline==='true';
      const body=isPipeline?{selections}:{moduleId:button.dataset.generationModule,selected:selections};
      const endpoint=isPipeline?'/api/pipeline/one-click':'/api/today/module-refresh';
      const session=await api(endpoint,{method:'POST',body:JSON.stringify(body)});
      closeModal();
      toast(`正在请求 Codex 独立任务：${session.title||''}`);
      await followVisibleTask(session,button);
      await refresh();
    }catch(error){
      const message=error.message||'生成任务创建失败';
      toast(message);
      if(feedback){feedback.textContent=`提交失败：${message}`;feedback.hidden=false;}
      button.disabled=false;
      button.textContent=originalLabel;
    }
  };
}
async function generationSelectionModal(moduleId,{pipeline=false}={}){
  try{
    const payload=await api(`/api/today/generation-candidates?moduleId=${encodeURIComponent(moduleId)}`);
    const items=payload.candidates||[];
    const first=newestFirst(items.filter(item=>!item.generated&&item.eligible));
    const redo=newestFirst(items.filter(item=>item.generated&&item.eligible));
    const section=(title,rows,empty)=>`<section class="generation-select-group"><h3>${esc(title)} <small>${rows.length}</small></h3>${rows.length?rows.map(generationCandidateRow).join(''):`<p>${esc(empty)}</p>`}</section>`;
    const label=payload.label||'内容';
    const action=pipeline?'确认并打开 Codex':'开始生成';
    modal(`<button class="close" data-close>×</button><section class="generation-select-modal"><span class="eyebrow">${esc(label)}</span><h2>选择本次要生成的内容</h2><p>未生成项会首次生成；已生成项会创建新版本重新生成。多项会在同一条任务中依次处理，并逐项经过小审。</p><p class="generation-submit-feedback" data-generation-feedback hidden></p><div class="generation-select-list">${section('未生成',first,'当前没有可首次生成的内容。')}${section('已生成',redo,'当前没有可重新生成的内容。')}</div><footer><button class="outline-button" data-close type="button">取消</button><button class="orange-button" data-generation-submit data-generation-module="${esc(moduleId)}" data-generation-pipeline="${pipeline?'true':'false'}" type="button" ${(first.length||redo.length)?'':'disabled'}>${esc(action)}</button></footer></section>`);
    bindGenerationSubmit(document.querySelector('#modal [data-generation-submit]'));
  }catch(error){toast(error.message||'无法读取生成候选');}
}
function renderAssets(){
  const catalog=Array.isArray(state.data.assets?.catalog)?state.data.assets.catalog:[];
  const flow=id=>catalog.find(section=>section.id===id)||{id,label:id,icon:'folder',count:0,items:[]};
  const displayLabel=value=>String(value||'').replace(/（会员专享）/g,'').trim();
  const directoryItem=(item,{showCount=true}={})=>{
    const action=item.id==='case-breakdowns'?`data-case-breakdowns="true"`:`data-asset-directory="${esc(item.id)}"`;
    const tail=item.memberOnly?`<em class="asset-member-tag">${brandIcon('lock')}会员专享</em>`:(showCount?`<strong>${nf(item.count)}</strong>`:'');
    const label=displayLabel(item.label);
    return `<button class="asset-map-item ${item.locked?'is-member':''}" ${action} ${item.locked?'data-asset-locked="会员专享目录尚未解锁"':''} title="${esc(item.memberOnly?`会员专享 · ${label}`:label)}"><span><b>${esc(label)}</b></span>${tail}</button>`;
  };
  const itemLayout=section=>section.items.length===2?'is-two-items':'is-scroll-list';
  const flowNode=(section,entry)=>`<section class="asset-orbit-node asset-orbit-${esc(section.id)} ${itemLayout(section)}" data-motion-entry="${entry}"><button class="asset-orbit-center" data-asset-section="${esc(section.id)}" aria-label="查看${esc(section.label)}目录明细"><i>${icons[section.icon]||icons.folder}</i><span>${esc(section.label)}</span><strong>${nf(section.count)}</strong></button><div class="asset-orbit-items">${section.items.map(directoryItem).join('')}</div></section>`;
  const folders=catalog.filter(section=>section.kind==='asset');
  const skills=catalog.find(section=>section.kind==='skills');
  const folderCard=(section,index,total)=>{
    const midpoint=(total-1)/2;
    const fan=index<midpoint?'left':index>midpoint?'right':'center';
    return `<section class="asset-map-card ${itemLayout(section)}" data-motion-entry="asset-map" data-motion-fan="${fan}" style="--asset-motion-delay:${280+index*70}ms"><header><i>${icons[section.icon]||icons.folder}</i><div><h2>${esc(section.label)}</h2></div></header><div class="asset-map-items">${section.items.map(directoryItem).join('')}</div></section>`;
  };
  return `<div class="asset-v10 asset-directory-map"><section class="asset-orbit-flow">${flowNode(flow('input'),'asset-flow-left')}<i class="asset-orbit-arrow" data-motion-entry="asset-arrow-left" aria-hidden="true">${icons.arrow}</i>${flowNode(flow('process'),'asset-flow-center')}<i class="asset-orbit-arrow" data-motion-entry="asset-arrow-right" aria-hidden="true">${icons.arrow}</i>${flowNode(flow('output'),'asset-flow-right')}</section><section class="asset-map-grid">${folders.map((section,index)=>folderCard(section,index,folders.length)).join('')}</section>${skills?`<section class="asset-skill-card" data-motion-entry="asset-skills"><header><i>${icons[skills.icon]||icons.puzzle}</i><div><h2>${esc(skills.label)}</h2></div><strong>${nf(skills.count)}</strong></header><div class="asset-skill-grid">${skills.items.map(item=>directoryItem(item,{showCount:false})).join('')}</div></section>`:''}</div>`;
}
function agentStatusLabel(status){ return {available:'当前可调度','needs-user':'等待用户确认','running':'执行中','repairing':'修复中','waiting-audit':'等待小审','released':'已放行','completed':'已完成',planned:'即将上线'}[status]||'状态同步中'; }
function teamMemberModal(agent){
  if(!agent)return;
  const role=teamRoles[agent.id]||{title:'AI员工',summary:'岗位职责待登记',detail:'当前岗位职责尚未登记。'};
  const file=portraitFiles[agent.id]||portraitFiles.xiaojiang;
  modal(`<button class="close" data-close>×</button><section class="team-profile-modal"><div class="team-profile-avatar"><img src="${brandAsset(`portraits/${file}`)}" alt="${esc(agent.name)}"></div><span class="eyebrow">AI 团队 / ${esc(role.title)}</span><h2>${esc(agent.name)}</h2><b class="team-profile-summary">${esc(role.summary)}</b><p>${esc(role.detail)}</p><div class="team-profile-meta"><span><i class="status ${esc(agent.status)}"></i>${esc(agentStatusLabel(agent.status))}</span>${agent.skill?`<span>${esc(agent.skill)}</span>`:''}</div></section>`);
}
function renderTeam(){
  const agents=state.data.agents;
  const actor=id=>agents.find(item=>item.id===id);
  const avatar=item=>{const file=portraitFiles[item?.id]||portraitFiles.xiaojiang;return `<img class="agent-avatar" src="${brandAsset(`portraits/${file}`)}" alt="${esc(item?.name||'小姜')}">`;};
  const employee=item=>{const role=teamRoles[item.id]||{summary:'岗位职责待登记'};return `<button class="employee" data-agent-detail="${esc(item.id)}"><div class="avatar">${avatar(item)}</div><b>${esc(item.name)}</b><small>${esc(role.summary)}</small><em class="status ${esc(item.status)}" title="${esc(agentStatusLabel(item.status))}"></em></button>`;};
  const stageAttr=index=>`data-team-stage="${index}" style="--team-stage-delay:${120+index*420}ms"`;
  const personStep=(item,klass,label,stage)=>{const role=teamRoles[item?.id]||{summary:label};return `<button class="team-step team-person-card ${klass}" ${stageAttr(stage)} data-agent-detail="${esc(item?.id||'xiaojiang')}">${avatar(item)}<b>${esc(item?.name||'小姜')}</b><small>${esc(role.summary)}</small><em class="status ${esc(item?.status||'available')}" title="${esc(agentStatusLabel(item?.status||'available'))}"></em></button>`;};
  const audit=actor('xiaoshen'), specialist=['xiaoxi','xiaochai','xiaojing','xiaoce','xiaoxie','xiaotu'].map(actor).filter(Boolean), planned=agents.filter(item=>item.availability!=='active');
  const rail=['用户对话','小姜总调度','专业AI员工','小审审核门禁','小姜回收结果','正式输出'];
  const animate=['initial','page-switch','manual-refresh'].includes(state.motionReason);
  return `<div class="team-v10" data-team-motion="${animate?'enter':'ready'}"><section class="team-rail">${rail.map((label,index)=>`<span ${stageAttr(index)}>${label}</span>`).join('')}</section><section class="team-flow"><div class="team-step user-step" ${stageAttr(0)}><i>${brandIcon('chat')}</i><b>你对话小姜</b><small>提出需求</small></div><i class="connector" ${stageAttr(1)}>→</i>${personStep(actor('xiaojiang'),'jiang','总调度入口',1)}<i class="connector" ${stageAttr(2)}>→</i><div class="specialists" ${stageAttr(2)}>${specialist.map(employee).join('')}</div><i class="connector" ${stageAttr(3)}>→</i><button class="audit-step team-person-card" ${stageAttr(3)} data-agent-detail="xiaoshen">${avatar(audit)}<b>小审</b><small>${esc(teamRoles.xiaoshen.summary)}</small><em>审核门禁</em></button><i class="connector" ${stageAttr(4)}>→</i>${personStep(actor('xiaojiang'),'receipt','回收整合结果',4)}<i class="connector" ${stageAttr(5)}>→</i><div class="team-step output" ${stageAttr(5)}><i>${brandIcon('output')}</i><b>正式输出</b><small>审核放行后输出</small></div></section><section class="planned-team"><h2>待加入团队</h2><div class="planned-members">${planned.map(employee).join('')}</div></section></div>`;
}
function assetUpdateHistory(){
  const updates=state.data?.metrics?.assetUpdates;
  return Array.isArray(updates)&&updates.length>=90?updates:state.data?.metrics?.weeklyUpdates||[];
}
function activeAssetUpdateRange(){
  const available=assetUpdateHistory().length>=90?[7,30,90]:[7];
  if(!available.includes(state.assetUpdateDays)) state.assetUpdateDays=7;
  return state.assetUpdateDays;
}
function assetTrendContentHTML(){
  const range=activeAssetUpdateRange(), history=assetUpdateHistory(), updates=history.slice(-range);
  const maxUpdate=Math.max(1,...updates.map(item=>Number(item.count||0)));
  const plot={left:34,right:456,top:18,bottom:146};
  const pointRadius=range>=90?2.4:range>=30?3.4:5;
  const dateInterval=range>=90?15:range>=30?5:1;
  const trendPoints=updates.map((item,index)=>{
    const x=updates.length>1?plot.left+(plot.right-plot.left)*index/(updates.length-1):(plot.left+plot.right)/2;
    const y=plot.bottom-(Number(item.count||0)/maxUpdate)*(plot.bottom-plot.top);
    return {...item,x,y};
  });
  const trendLine=trendPoints.map(item=>`${item.x.toFixed(1)},${item.y.toFixed(1)}`).join(' ');
  const trendArea=trendPoints.length?`M ${plot.left} ${plot.bottom} L ${trendPoints.map(item=>`${item.x.toFixed(1)} ${item.y.toFixed(1)}`).join(' L ')} L ${plot.right} ${plot.bottom} Z`:'';
  const hasFullHistory=history.length>=90;
  return `<header class="trend-card-head"><h2>近${range}日真实资产更新</h2><div class="trend-range-switch" role="group" aria-label="真实资产更新时间范围">${[7,30,90].map(days=>`<button type="button" data-asset-update-range="${days}" aria-pressed="${range===days?'true':'false'}" ${days>7&&!hasFullHistory?'disabled title="请先同步本机数据以生成90日统计"':''}>${days}天</button>`).join('')}</div></header><svg class="trend-chart" viewBox="0 0 490 190" role="img" aria-label="近${range}日真实资产更新趋势"><defs><linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#ee8216" stop-opacity=".28"/><stop offset="1" stop-color="#ee8216" stop-opacity="0"/></linearGradient></defs><g class="trend-grid"><line x1="34" y1="18" x2="456" y2="18"/><line x1="34" y1="82" x2="456" y2="82"/><line x1="34" y1="146" x2="456" y2="146"/></g>${trendArea?`<path class="trend-area" d="${trendArea}"/><polyline class="trend-line" points="${trendLine}"/>`:''}${trendPoints.map((item,index)=>{const showDate=index===0||index===trendPoints.length-1||index%dateInterval===0;const showValue=range===7||index===trendPoints.length-1;return `<g class="chart-point ${index===trendPoints.length-1?'latest':''}"><circle cx="${item.x}" cy="${item.y}" r="${pointRadius}"/>${showValue?`<text class="trend-value-static" x="${item.x}" y="${Math.max(14,item.y-12)}">${nf(item.count)}</text>`:`<text class="trend-hover-value" x="${item.x}" y="${Math.max(14,item.y-12)}">${nf(item.count)}</text>`}${showDate?`<text class="trend-date" x="${item.x}" y="174">${esc(String(item.date||'').slice(5))}</text>`:''}</g>`;}).join('')}</svg>`;
}
function renderAssetTrend(){
  const card=$('.trend-card');
  if(!card)return;
  card.classList.add('is-range-update');
  card.innerHTML=assetTrendContentHTML();
  bindAssetUpdateRangeControls(card);
}
function bindAssetUpdateRangeControls(root=document){
  root.querySelectorAll('[data-asset-update-range]').forEach(button=>button.onclick=()=>{
    const days=Number(button.dataset.assetUpdateRange);
    if(![7,30,90].includes(days)||button.disabled||days===activeAssetUpdateRange())return;
    state.assetUpdateDays=days;
    try { localStorage.setItem(assetUpdateRangePreferenceKey,String(days)); } catch (_) {}
    renderAssetTrend();
  });
}
function bindDistributionRing(){
  const visual=$('[data-distribution-visual]');
  if(!visual)return;
  const total=visual.querySelector('[data-distribution-total]');
  const label=visual.querySelector('[data-distribution-label]');
  const reset=()=>{
    total.textContent=nf(Number(visual.dataset.totalCount||0));
    label.textContent=visual.dataset.totalLabel||'当前可读资产';
    visual.classList.remove('is-segment-active');
  };
  visual.querySelectorAll('[data-distribution-segment]').forEach(segment=>{
    const activate=()=>{
      total.textContent=nf(Number(segment.dataset.libraryCount||0));
      label.textContent=`${segment.dataset.libraryLabel||''} · ${segment.dataset.libraryPercent||'0'}%`;
      visual.classList.add('is-segment-active');
    };
    segment.addEventListener('pointerenter',activate);
    segment.addEventListener('focus',activate);
    segment.addEventListener('blur',reset);
  });
  visual.addEventListener('pointerleave',reset);
}
function bindModuleRadar(){
  const visual=$('[data-module-radar]');
  if(!visual)return;
  const reset=()=>{
    visual.classList.remove('is-node-active');
    visual.querySelectorAll('.is-node-active').forEach(item=>item.classList.remove('is-node-active'));
  };
  visual.querySelectorAll('[data-module-radar-node]').forEach(node=>{
    const activate=()=>{
      reset();
      visual.classList.add('is-node-active');
      node.classList.add('is-node-active');
      visual.querySelector(`[data-module-radar-label][data-module-index="${node.dataset.moduleIndex}"]`)?.classList.add('is-node-active');
    };
    node.addEventListener('pointerenter',activate);
    node.addEventListener('focus',activate);
    node.addEventListener('blur',reset);
  });
  visual.addEventListener('pointerleave',reset);
}
function renderData(){
  const assets=state.data.assets||{stageTotals:{input:0,process:0,output:0},catalog:[]};
  const catalog=Array.isArray(assets.catalog)?assets.catalog:[];
  const pipeline=state.data.pipeline||{stages:[]};
  const planStats=state.data.planStats||{};
  const sixLibraryIds=['input','process','output','topics','cases','gallery'];
  const libraries=sixLibraryIds.map(id=>{
    const source=catalog.find(section=>section.id===id)||{};
    return {id,label:String(source.label||''),count:Number(source.count||0)};
  });
  const total=libraries.reduce((sum,library)=>sum+library.count,0);
  let segmentOffset=0;
  const distributionSegments=libraries.map((library,index)=>{
    const percentage=total?library.count/total*100:0;
    const offset=segmentOffset;
    segmentOffset+=percentage;
    if(!percentage)return '';
    const detail=`${library.label} ${nf(library.count)} 项，占比 ${percentage.toFixed(1)}%`;
    return `<circle class="distribution-segment library-tone-${index}" data-distribution-segment data-library-label="${esc(library.label)}" data-library-count="${library.count}" data-library-percent="${percentage.toFixed(1)}" cx="120" cy="120" r="84" pathLength="100" stroke-dasharray="${percentage.toFixed(4)} ${(100-percentage).toFixed(4)}" stroke-dashoffset="${(-offset).toFixed(4)}" transform="rotate(-90 120 120)" tabindex="0" role="img" aria-label="${esc(detail)}"><title>${esc(detail)}</title></circle>`;
  }).join('');
  const pipelineStages=pipeline.stages||[];
  const stageColors=['peach','tangerine','amber','orange','copper','deep-orange','sand'];
  const processCatalog=catalog.find(section=>section.id==='process');
  const processGroups=(processCatalog?.items||[]).map(item=>({title:String(item.label||''),count:Number(item.count||0)}));
  const moduleLabels=['观点','痛点','误区','解决方案','案例','推荐理由'];
  const moduleGroups=moduleLabels.map(label=>{
    const source=processGroups.find(group=>group.title.includes(label));
    return {label,count:Number(source?.count||0)};
  });
  const contentOutputs=Array.isArray(state.data.contentOutputStats)?state.data.contentOutputStats:[];
  const outputItems=[
    ...contentOutputs.map(item=>({...item,kind:'copy'})),
    {id:'copy-gallery',name:'成稿配图',count:Number(state.data.galleryOutputCount||0),deployed:true,kind:'gallery'}
  ].filter(item=>Number(item.count||0)>0);
  const outputMax=Math.max(1,...outputItems.map(item=>Number(item.count||0)));
  const planMetrics=[
    {tone:'orange',icon:'calendar',label:'总计划数',value:Number(planStats.totalDueOccurrences||0),unit:'项',progress:Number(planStats.completionRatePercent||0)},
    {tone:'deep',icon:'check-circle',label:'已完成计划数',value:Number(planStats.completedOccurrences||0),unit:'项',progress:Number(planStats.completionRatePercent||0)},
    {tone:'amber',icon:'list-check',label:'完成率',value:Number(planStats.completionRatePercent||0),unit:'%',progress:Number(planStats.completionRatePercent||0)}
  ];
  const funnelRows=pipelineStages.map((stage,index)=>{
    // All six rows are sourced from the active pipeline snapshot.  Do not
    // fall back to the retired structure-completion snapshot here: it can be
    // stale and previously made the same frozen-structure total disagree
    // between the pipeline and data-center pages.
    const value=nf(stage.count||0);
    const width=Math.max(56,100-index*7);
    return `<div class="conversion-stage ${stageColors[index]||'orange'}" style="--stage-width:${width}%"><span>${esc(stage.label)}</span><b>${value}</b></div>`;
  }).join('')||'<p class="chart-empty">暂无生产阶段数据</p>';
  const radarCenter={x:150,y:124},radarRadius=79;
  const radarPoint=(radius,index)=>{
    const angle=-Math.PI/2+index*Math.PI*2/moduleGroups.length;
    return {x:radarCenter.x+Math.cos(angle)*radius,y:radarCenter.y+Math.sin(angle)*radius};
  };
  const radarPoints=radius=>moduleGroups.map((_,index)=>{const point=radarPoint(radius,index);return `${point.x.toFixed(2)},${point.y.toFixed(2)}`;}).join(' ');
  const moduleMax=Math.max(1,...moduleGroups.map(group=>group.count));
  const modulePlot=moduleGroups.map((group,index)=>{
    const proportion=group.count>0?.15+Math.sqrt(group.count/moduleMax)*.85:0;
    const point=radarPoint(radarRadius*proportion,index);
    return {group,point};
  });
  const radarAxisLabel=(group,index)=>{
    const labelPositions=[
      {x:150,y:20}, {x:230,y:70}, {x:230,y:184},
      {x:150,y:218}, {x:70,y:184}, {x:70,y:70}
    ];
    const position=labelPositions[index];
    return `<text class="module-radar-axis-label" data-module-radar-label data-module-index="${index}" x="${position.x}" y="${position.y}" text-anchor="middle"><tspan x="${position.x}">${esc(group.label)}</tspan><tspan class="module-radar-axis-value" x="${position.x}" dy="17">${nf(group.count)}</tspan></text>`;
  };
  const moduleRadar=`<div class="module-radar" data-module-radar role="group" aria-label="内容模块雷达图：${moduleGroups.map(group=>`${group.label} ${nf(group.count)}`).join('，')}"><svg viewBox="0 0 300 250" aria-label="内容模块雷达图，悬停节点查看精确数量"><g class="module-radar-grid">${[.25,.5,.75,1].map(level=>`<polygon points="${radarPoints(radarRadius*level)}"/>`).join('')}${moduleGroups.map((_,index)=>{const point=radarPoint(radarRadius,index);return `<line x1="${radarCenter.x}" y1="${radarCenter.y}" x2="${point.x.toFixed(2)}" y2="${point.y.toFixed(2)}"/>`;}).join('')}</g><polygon class="module-radar-shape" points="${modulePlot.map(item=>`${item.point.x.toFixed(2)},${item.point.y.toFixed(2)}`).join(' ')}"/>${modulePlot.map((item,index)=>`<circle class="module-radar-node" data-module-radar-node data-module-index="${index}" cx="${item.point.x.toFixed(2)}" cy="${item.point.y.toFixed(2)}" r="5.2" tabindex="0" role="img" aria-label="${esc(`${item.group.label} ${nf(item.group.count)}`)}"><title>${esc(`${item.group.label} ${nf(item.group.count)}`)}</title></circle>${radarAxisLabel(item.group,index)}`).join('')}</svg></div>`;
  const outputColumns=outputItems.map((item,index)=>{
    const value=Number(item.count||0);
    const height=`${(value/outputMax*76).toFixed(2)}%`;
    const label=item.kind==='gallery'?'成稿配图':`${item.name}成稿`;
    return `<div class="output-column"><div class="output-plot"><div class="output-bar output-tone-${index%6}" style="--output-height:${height}"><b data-chart-count="${value}">${nf(value)}</b></div></div><span>${esc(label)}</span></div>`;
  }).join('');
  return `<div class="data-grid data-dashboard">
    <section class="chart-card distribution-card" style="--enter-delay:0ms">
      <h2>六库资产分布</h2>
      <div class="distribution-body is-visual" data-distribution-visual data-total-label="当前可读资产" data-total-count="${total}">
        <svg class="distribution-ring" viewBox="0 0 240 240" aria-label="六库资产分布圆环图"><circle class="distribution-track" cx="120" cy="120" r="84"/>${distributionSegments}</svg>
        <div class="distribution-readout" aria-live="polite"><strong data-distribution-total data-chart-count="${total}">${nf(total)}</strong><span data-distribution-label>当前可读资产</span></div>
      </div>
    </section>
    <section class="chart-card trend-card" style="--enter-delay:55ms">${assetTrendContentHTML()}</section>
    <section class="chart-card conversion-card" style="--enter-delay:110ms">
      <h2>内容生产转化</h2><div class="conversion-list">${funnelRows}</div>
    </section>
    <section class="chart-card composition-card" style="--enter-delay:165ms">
      <h2>内容模块</h2>${moduleRadar}
    </section>
    <section class="chart-card output-card" style="--enter-delay:220ms">
      <h2>累计产出</h2><div class="output-chart${outputItems.length?'':' is-empty'}" style="--output-count:${outputItems.length||1}">${outputColumns||'<p class="chart-empty">暂无已生成的成稿或成稿配图</p>'}</div>
    </section>
    <section class="chart-card plan-progress-card" style="--enter-delay:275ms">
      <h2>工作计划执行</h2><div class="plan-rings">${planMetrics.map((metric,index)=>`<div class="plan-metric" style="--metric-delay:${(.18+index*.14).toFixed(2)}s"><div class="plan-ring ${metric.tone}" style="--plan-ring-target:${(metric.progress/100*360).toFixed(2)}deg"><i>${brandIcon(metric.icon)}</i></div><span>${metric.label}</span><div class="plan-value"><strong data-chart-count="${metric.value}">${nf(metric.value)}</strong><em>${metric.unit}</em></div></div>`).join('')}</div>
    </section>
  </div>`;
}
let modalCloseTimer=0;
async function topicBenchmarkCaseModal(rowIndex){
  const editor=state.todayEditor, table=editor?.file?.table;
  if(!editor||editor.surface!=='topics'||!table||!table.rows?.[rowIndex])return;
  try{
    const payload=await api('/api/today/editor/benchmark-cases');
    const current=String(table.rows[rowIndex][7]||'').trim();
    const rows=(payload.cases||[]).map(item=>`<button class="topic-case-choice ${item.id===current?'is-selected':''}" data-topic-case-choice="${esc(item.id)}" type="button"><span><b>${esc(item.title)}</b><small>${esc(item.id)}${item.type?` · ${esc(item.type)}`:''}</small></span>${item.memberOnly?'<em class="asset-member-tag">🔒 会员专享</em>':''}</button>`).join('')||'<p>当前没有可用的已登记对标复刻拆解。</p>';
    modal(`<button class="close" data-close>×</button><section class="topic-case-modal"><span class="eyebrow">对标复刻拆解</span><h2>选择对标拆解</h2><p>选择后仅写入该行的编号；完整标题只在这里用于人工确认。</p><div class="topic-case-list">${rows}</div><div class="modal-actions"><button class="outline-button" data-topic-case-clear type="button" ${current?'':'disabled'}>清空选择</button><button class="outline-button" data-close type="button">取消</button></div></section>`);
    const updateSelectedCaseCell=value=>{
      const target=document.querySelector(`[data-topic-case-select="${rowIndex}"]`);
      if(!target)return;
      target.textContent=value||'选择对标拆解';
      target.classList.toggle('is-selected',Boolean(value));
    };
    document.querySelectorAll('#modal [data-topic-case-choice]').forEach(button=>button.onclick=()=>{
      const value=button.dataset.topicCaseChoice||'';
      table.rows[rowIndex][7]=value;
      updateSelectedCaseCell(value);
      scheduleTodayEditorSave();
      closeModal();
      toast(`已选择 ${value}`);
    });
    document.querySelector('#modal [data-topic-case-clear]')?.addEventListener('click',()=>{
      table.rows[rowIndex][7]='';
      updateSelectedCaseCell('');
      scheduleTodayEditorSave();
      closeModal();
      toast('已清空对标拆解编号');
    });
  }catch(error){ toast(error.message||'无法读取对标拆解候选'); }
}
function modal(content){ const node=$('#modal'); window.clearTimeout(modalCloseTimer); node.hidden=false; node.classList.remove('is-closing'); node.innerHTML=`<div class="modal-backdrop" data-close></div><section class="modal-card">${content}</section>`; }
function closeModal(){ const node=$('#modal'); if(node.hidden||node.classList.contains('is-closing'))return; node.classList.add('is-closing'); modalCloseTimer=window.setTimeout(()=>{node.hidden=true;node.classList.remove('is-closing');node.innerHTML='';},180); }
function typeModal(){ modal(`<button class="close" data-close>×</button><h2>选择内容类型</h2><div class="type-list">${types().map(type=>`<button data-type="${type.id}"><i>${icons[type.id==='dry-goods'?'file':type.id==='podcast'?'mic':type.id==='recommend'?'star':'bolt']}</i><b>${type.name}</b><span>${type.available?'已启用':'🔒 会员专享'}</span></button>`).join('')}</div>`); }
function toPlanDate(value){ return value ? String(value).slice(0,10) : localDateKey(new Date()); }
function planModal(plan=null){
  const isEditing=Boolean(plan), startDate=toPlanDate(plan?.start_date||plan?.plan_date), repeat=plan?.repeat_rule||'none', startWeekday=(new Date(`${startDate}T00:00:00`).getDay()+6)%7, startDay=Number(startDate.slice(-2));
  const weekdays=new Set((repeat==='weekly'?(plan?.weekdays||[]):[]).map(Number));
  if(repeat==='weekly'&&!weekdays.size) weekdays.add(startWeekday);
  const endDate=isEditing&&repeat!=='none'?toPlanDate(plan?.end_date||plan?.ends_at):'', monthlyDay=Number(plan?.monthly_day||plan?.monthlyDay)||startDay, planTypes=types();
  const typeOptions=planTypes.map(type=>`<option value="${esc(type.id)}" ${type.id===(plan?.content_type||state.type)?'selected':''}>${esc(type.name)}${type.memberOnly?'（会员专享）':''}</option>`).join('');
  const weekdayOptions=weekdayLabels.map((label,index)=>`<label><input type="checkbox" name="weekdays" value="${index}" ${weekdays.has(index)?'checked':''}><span>${label.replace('周','')}</span></label>`).join('');
  const monthlyOptions=Array.from({length:31},(_,index)=>`<option value="${index+1}" ${monthlyDay===index+1?'selected':''}>${index+1}日</option>`).join('');
  modal(`<button class="close" data-close>×</button><section class="plan-modal"><span class="eyebrow">工作计划</span><h2>${isEditing?'编辑工作计划':'设置工作计划'}</h2><form id="planForm" data-plan-id="${esc(plan?.id||'')}"><fieldset><legend>生产内容</legend><div class="plan-form-grid"><label>内容类型<select name="contentType">${typeOptions}</select></label><label>目标条数<input name="targetCount" type="number" min="1" max="999" value="${Number(plan?.target_count||1)}"><small>条</small></label></div></fieldset><fieldset><legend>执行规则</legend><div class="plan-form-grid"><label>开始日期<input name="startDate" type="date" value="${startDate}" required></label><label>执行频率<select name="repeatRule"><option value="none" ${repeat==='none'?'selected':''}>仅这一天</option><option value="daily" ${repeat==='daily'?'selected':''}>每天</option><option value="weekly" ${repeat==='weekly'?'selected':''}>每周</option><option value="monthly" ${repeat==='monthly'?'selected':''}>每月</option></select></label></div><div class="plan-weekdays" ${repeat==='weekly'?'':'hidden'}><span>每周执行日</span><div>${weekdayOptions}</div></div><div class="plan-month-day" ${repeat==='monthly'?'':'hidden'}><label>每月执行日<select name="monthlyDay">${monthlyOptions}</select></label><small>遇到短月时自动安排在当月最后一天。</small></div><div class="plan-end" ${repeat==='none'?'hidden':''}><label>重复至<input name="endsAt" type="date" value="${endDate}"></label></div></fieldset><output id="planPreview" class="plan-preview"></output><button class="orange-button" type="submit">${isEditing?'保存修改':'保存计划'}</button></form></section>`);
  const form=$('#planForm');
  const weekdayInputs=Array.from(form.querySelectorAll('input[name="weekdays"]')), monthlyDayInput=form.querySelector('select[name="monthlyDay"]'), endsAtInput=form.querySelector('input[name="endsAt"]'), repeatRuleInput=form.querySelector('select[name="repeatRule"]'), startDateInput=form.querySelector('input[name="startDate"]');
  let previousStartDay=startDay, previousRule=repeat, monthlyDayChanged=monthlyDay!==startDay;
  monthlyDayInput.addEventListener('change',()=>{monthlyDayChanged=true;});
  const sync=()=>{
    const rule=String(repeatRuleInput.value||'none'), start=String(startDateInput.value||startDate), currentStartDay=Number(start.slice(-2))||previousStartDay;
    const weekly=rule==='weekly', monthly=rule==='monthly', repeating=rule!=='none';
    $('.plan-weekdays',form).hidden=!weekly; $('.plan-month-day',form).hidden=!monthly; $('.plan-end',form).hidden=!repeating;
    weekdayInputs.forEach(input=>{input.disabled=!weekly;});
    if(weekly&&previousRule!=='weekly'&&!weekdayInputs.some(input=>input.checked)){
      const defaultWeekday=(new Date(`${start}T00:00:00`).getDay()+6)%7;
      const defaultInput=weekdayInputs.find(input=>Number(input.value)===defaultWeekday);
      if(defaultInput) defaultInput.checked=true;
    }
    monthlyDayInput.disabled=!monthly;
    endsAtInput.disabled=!repeating;
    endsAtInput.required=repeating;
    if(!monthlyDayChanged&&Number(monthlyDayInput.value)===previousStartDay) monthlyDayInput.value=String(currentStartDay);
    previousStartDay=currentStartDay;
    previousRule=rule;
    const values=new FormData(form), type=planTypeName(String(values.get('contentType')||'dry-goods')), count=Number(values.get('targetCount')||1);
    const selected=Array.from(form.querySelectorAll('input[name="weekdays"]:checked')).map(input=>weekdayLabels[Number(input.value)]).join('、')||'未选择';
    const frequency=rule==='none'?'仅此一天':rule==='daily'?'每天':rule==='weekly'?`每周${selected}`:`每月${monthlyDayInput.value}日`;
    $('#planPreview').textContent=rule==='none'?`${start}，仅此一天，计划生产 ${type}视频 ${count||1} 条。`:`${start} 起，${frequency}执行，重复至 ${endsAtInput.value||'请选择结束日期'}，计划生产 ${type}视频 ${count||1} 条。`;
  };
  form.addEventListener('input',sync); form.addEventListener('change',sync); sync();
}
function helpModal(){ const lines=state.data.assets.brand.lines.map(line=>`<p>• ${esc(line)}</p>`).join(''); modal(`<div class="help-modal"><button class="close" data-close>×</button><h1>帮助中心</h1><span class="help-title-rule" aria-hidden="true"></span><div class="help-lines">${lines}</div><div class="wechat"><small>添加我的微信</small><b>${esc(state.data.assets.brand.wechat)}</b><button data-copy="${esc(state.data.assets.brand.wechat)}">${brandIcon('copy')}复制微信号</button></div></div>`); }
function assetModal(group){ const sources=group.sources.map((source,index)=>`<article class="source-row"><div><b>${esc(source.label)}</b><small>${source.unlocked?nf(source.count)+' 项 · '+(source.latestAt?new Date(source.latestAt).toLocaleDateString('zh-CN'):'暂无更新'):'会员专享'}</small></div>${source.unlocked?`<button data-open="${group.id}:${index}">打开目录</button>`:'<span>🔒</span>'}</article>`).join(''); modal(`<button class="close" data-close>×</button><span class="eyebrow">${group.stageLabel} / ${group.eyebrow}</span><h2>${group.title}</h2><p>${group.description}</p><strong class="drawer-total">${nf(group.count)}</strong>${sources}`); }
function memberAccessModal(){ toast('会员专享，请解锁会员后查看'); assistantModal(); }
const wait=milliseconds=>new Promise(resolve=>window.setTimeout(resolve,milliseconds));
async function followVisibleTask(session,button){
  const original=button?.textContent||'刷新';
  if(button)button.disabled=true;
  try{
    for(let attempt=0;attempt<60;attempt+=1){
      const detail=await api(`/api/sessions/${encodeURIComponent(session.id)}`);
      const bridge=detail.bridge_status||'';
      const label=bridge==='desktop-bridge-user-agent'?'正在定位 Codex':bridge==='desktop-bridge-focusing'?'正在连接 Codex Desktop':bridge==='desktop-bridge-creating'?'正在新建任务':bridge==='desktop-native-thread-created'?'已在 Codex 中创建':bridge==='desktop-task-delivered-unconfirmed'?'已尝试输入，等待 Codex 确认':bridge==='desktop-task-input-unverified'?'已尝试输入，等待 Codex 确认':'正在打开 Codex';
      if(button)button.textContent=label;
      if(['failed','expired','blocked','cancelled'].includes(detail.status)){
        const failure=(detail.events||[]).find(event=>event.level==='warning'||event.level==='error');
        throw new Error(failure?.message||(detail.status==='expired'?'Codex 未在确认时限内回写任务启动状态，请重试。':'Codex 桌面任务创建失败'));
      }
      if(['submitted','running','repairing','needs-user','waiting-audit','completed'].includes(detail.status)){
        toast(detail.status==='submitted'&&bridge==='desktop-native-thread-created'?'已在 Codex 中创建独立任务':detail.status==='submitted'?'已尝试输入，等待 Codex 任务确认':'Codex 任务已开始');
        return detail;
      }
      await wait(500);
    }
    throw new Error('Codex 桌面任务创建超时，请检查桌面桥接状态');
  }finally{
    if(button){button.disabled=false;button.textContent=original;}
  }
}
async function openAssetDirectory(button){
  if(button.dataset.assetLocked){memberAccessModal();return;}
  try{
    await requestDesktopFolder('/api/open-asset-directory',{directoryId:button.dataset.assetDirectory},button.dataset.assetLabel||'资产目录');
  }catch(error){toast(error.message||'无法打开资产目录');}
}
function assetCatalogModal(section){ if(!section)return; const clean=value=>String(value||'').replace(/（会员专享）/g,'').trim(); const rows=(section.items||[]).map(item=>`<article class="source-row ${item.locked?'is-member':''}"><div><b>${esc(clean(item.label))}</b><small>${item.memberOnly?'会员专享':nf(item.count)+' 项'}</small></div><button data-asset-directory="${esc(item.id)}" ${item.locked?'data-asset-locked="会员专享目录尚未解锁"':''}>${item.locked?'解锁会员':'打开目录'}</button></article>`).join(''); modal(`<button class="close" data-close>×</button><span class="eyebrow">资产目录地图</span><h2>${esc(section.label)}</h2><strong class="drawer-total">${nf(section.count)}</strong>${rows}`); document.querySelectorAll('#modal [data-asset-directory]').forEach(button=>button.onclick=()=>openAssetDirectory(button)); }
async function caseBreakdownPreview(id){ try{ const item=await api(`/api/assets/case-breakdown?id=${encodeURIComponent(id)}`); const preview=structureDocumentHTML({content:item.content},{editable:false}); modal(`<section class="asset-case-dialog asset-case-document"><button class="close" data-close>×</button><span class="eyebrow">案例结构拆解</span><h2>${esc(item.title)}</h2><small class="asset-preview-path">${esc(item.relativePath)}</small><div class="asset-case-preview">${preview}</div></section>`); }catch(error){toast(error.message||'无法读取拆解内容');} }
async function caseBreakdownsModal(){ try{ const payload=await api('/api/assets/case-breakdowns'); const rows=(payload.items||[]).map(item=>`<article class="source-row ${item.locked?'is-member':''}"><div><b>${esc(item.title)}</b>${item.memberOnly?`<em class="asset-member-tag">${brandIcon('lock')}会员专享</em>`:''}</div><div class="asset-case-actions">${item.locked?`<button class="asset-case-open-tag is-locked" data-member-access>解锁会员</button>`:`<button class="asset-case-open-tag" data-case-breakdown="${esc(item.id)}">查看文案</button>`}</div></article>`).join('')||'<p>暂未找到已完成的案例结构拆解。</p>'; modal(`<section class="asset-case-dialog"><button class="close" data-close>×</button><span class="eyebrow">案例库</span><h2>案例结构拆解</h2><div class="asset-case-list">${rows}</div></section>`); document.querySelectorAll('#modal [data-case-breakdown]').forEach(button=>button.onclick=()=>caseBreakdownPreview(button.dataset.caseBreakdown)); document.querySelectorAll('#modal [data-member-access]').forEach(button=>button.onclick=memberAccessModal); }catch(error){toast(error.message||'无法读取案例结构拆解');} }
function sessionModal(action,title){ modal(`<button class="close" data-close>×</button><span class="eyebrow">小姜任务入口</span><h2>${title}</h2><p>任务会交给小姜创建调度记录；不会绕过小审，也不会立即写入资产。</p><label class="session-label">补充说明<textarea id="sessionMessage" placeholder="可补充选题、要求或上下文"></textarea></label><label class="attachment-label">补充附件（最多 5 个，每个小于 5MB）<input id="sessionAttachments" type="file" multiple accept=".txt,.md,.pdf,.doc,.docx,.xlsx,.csv,.mp3,.m4a,.wav,.mp4,.mov,.png,.jpg,.jpeg,.webp"></label><button class="orange-button" data-create-session="${action}">提交给小姜</button>`); }
function pipelineDetailModal(stageId){
  const pipeline=state.data.pipeline, item=(pipeline?.stages||[]).find(stage=>stage.id===stageId),meta=pipelineStageMeta[stageId];
  if(!item||!meta)return;
  const value=nf(item.count);
  modal(`<button class="close" data-close>×</button><span class="eyebrow">${esc(meta.tag)} / 干货型爆款流水线</span><h2>${brandIcon(meta.icon)}${esc(item.label)}</h2><strong class="drawer-total">${value}</strong><p>${esc(item.formula)}</p><div class="pipeline-detail-meta"><span>最近更新：${item.latestAt?new Date(item.latestAt).toLocaleString('zh-CN'):'暂无记录'}</span><code>${esc(item.location)}</code></div>`);
}
function approvalModal(session){ modal(`<button class="close" data-close>×</button><span class="eyebrow">小姜任务</span><h2>确认提交任务？</h2><div class="approval-summary"><b>${esc(session.title)}</b><span>该入口用于非流水线任务；一键成稿不会显示此确认步骤。</span></div><button class="orange-button" data-approve="${session.id}">提交任务</button>`); }
function approvalLabel(approval){ if(approval.method==='item/tool/requestUserInput') return '填写 Codex 请求的信息'; if(approval.method.includes('fileChange')) return '查看文件变更'; if(approval.method.includes('permissions')) return '查看权限请求'; return '查看命令或联网请求'; }
function userInputModal(approval){ const questions=(approval.params?.questions||[]).filter(question=>question&&question.id); const questionHTML=questions.map(question=>{const id=esc(question.id),options=Array.isArray(question.options)?question.options:[],secret=Boolean(question.isSecret),choice=options.map(option=>`<label class="task-input-option"><input type="radio" name="answer-${id}" value="${esc(option.label)}" data-question-id="${id}"><span><b>${esc(option.label)}</b><small>${esc(option.description||'')}</small></span></label>`).join(''),free=(!options.length||question.isOther)?`<input class="task-input-text" type="${secret?'password':'text'}" data-question-id="${id}" data-other="true" placeholder="${secret?'请输入，不会写入事件库':'请输入你的回答'}">`:'';return `<fieldset class="task-input-question"><legend>${esc(question.header||'需要你的输入')}</legend><p>${esc(question.question||'请补充信息')}</p>${choice}${free}</fieldset>`;}).join(''); modal(`<button class="close" data-close>×</button><span class="eyebrow">Codex 等待输入</span><h2>补充任务信息</h2><p>提交后会回传到同一个 Codex 线程；密码、令牌和附件正文不会记录到工作台事件库。</p><form id="userInputForm" data-approval-id="${approval.id}">${questionHTML}<button class="orange-button" type="submit">提交给 Codex</button></form>`); }
function taskApprovalModal(approval){ if(!approval)return; if(approval.method==='item/tool/requestUserInput'){userInputModal(approval);return;} const p=approval.params||{}, command=Array.isArray(p.command)?p.command.join(' '):(p.command||p.reason||'Codex 请求执行一项操作'),kind=approval.method.includes('fileChange')?'文件变更':approval.method.includes('permissions')?'权限请求':'命令或联网操作'; modal(`<button class="close" data-close>×</button><span class="eyebrow">${kind}</span><h2>等待你确认</h2><p>Codex 不会在未经确认的情况下执行此操作。</p><div class="approval-summary"><b>${esc(command)}</b><span>${esc(p.reason||p.cwd||'本次仅允许一次。')}</span></div><button class="orange-button" data-respond-approval="${approval.id}" data-decision="accept">允许一次</button><button class="outline-button" data-respond-approval="${approval.id}" data-decision="decline">拒绝</button>`); }
function taskEventHTML(event){ const detail=event.detail&&Object.keys(event.detail).length?`<details><summary>查看事件详情</summary><pre>${esc(JSON.stringify(event.detail,null,2))}</pre></details>`:''; return `<article class="task-console-event ${esc(event.level)}"><header><b>${esc(event.kind||'system')}</b><time>${new Date(event.created_at).toLocaleTimeString('zh-CN')}</time></header><p>${esc(event.message)}</p>${detail}</article>`; }
function batchWorkflowHTML(session){const items=session.batch||[];if(!items.length)return '';const rows=items.map(item=>{const current=item.currentAttempt||{},receipt=current.auditReceipt||current.executionReceipt||'';return `<article class="task-batch-item"><header><b>${esc(item.title)}</b><span class="tag ${esc(item.progress||'pending')}">${esc(batchStatusLabel[item.progress]||item.progress||'等待')}</span></header><small>第 ${Number(item.attempt||0)} 次执行</small><p>${esc(item.nextStep||'等待推进')}</p>${receipt?`<code>${esc(receipt)}</code>`:''}</article>`;}).join('');return `<section class="task-batch-workflow"><h3>本次选题</h3>${rows}</section>`;}
async function sessionDetailModal(session){
  const detail=await api(`/api/sessions/${session.id}`);
  const events=(detail.events||[]).slice().reverse(),status=sessionStatusText(detail);
  const recovery=detail.status==='reconnecting'?`<p class="task-recovery-note">自动恢复：${esc(detail.recovery_failure_class||'外部连接异常')}；下次尝试 ${esc(detail.recovery_next_at||'等待控制器写入时间')}。</p>`:'';
  modal(`<button class="close" data-close>×</button><section class="task-console"><span class="eyebrow">Codex 执行状态</span><h2>${esc(detail.title)}</h2><div class="approval-summary"><b>${esc(status)}</b><span>执行过程在 Codex 项目任务中进行；这里仅同步真实阶段。</span></div>${recovery}${batchWorkflowHTML(detail)}<section class="task-console-events"><h3>执行记录</h3>${events.length?events.map(taskEventHTML).join(''):'<p>等待 Codex 任务回写执行状态。</p>'}</section></section>`);
}
function assistantModal(){ modal(`<section class="community-modal" aria-label="姜来答疑社群介绍"><button class="close" data-close aria-label="关闭社群介绍">×</button><div class="community-gallery"><article class="community-slide community-slide--hero"><div><p class="community-kicker">姜来答疑社群</p><h1>姜来答疑社群</h1><h2><span>个人IP+AI智能体</span><span>把你的能力变成你的生意</span></h2></div><p class="community-entry">开启AI时代，财富入口 <b>▶</b><b>▶</b><b>▶</b></p></article><article class="community-slide community-slide--benefits"><h2>199元，你买到的包括：</h2><section><h3><b>1</b> 群内答疑</h3><p>有问题大家在群内@我，我看到就深度解答；</p><p class="is-red">不是AI解答，不是助理解答，是本人亲自解答；</p><p>提问范围不限：做IP定位、内容、AI相关、变现、商业、个人成长等问题；</p><p class="is-red">没有时间期限，群不会解散；</p></section><section><h3><b>2</b> 课程系统</h3><p>个人IP课：商业定位－内容定位－写文案－拍摄剪辑－直播；</p><p class="is-red">AI智能体课：搭建属于自己的AI员工团队；</p><p>AI一人公司课：一个人如何做一门小生意的商业通识课；</p></section><section><h3><b>3</b> 资料库</h3><p>AI爆款内容工厂操作系统，独家内部精选Skills武器库；</p><p class="is-red">所有内容是持续更新的；</p></section><footer>－ 以上所有内容，都是我一步步实操下来的总结，只讲能落地的实战干货 －</footer></article><article class="community-slide community-slide--audience"><h2>姜来的社群适合谁？</h2><h3>如果你有以下任一种情况：</h3><ul><li><em>想做个人IP</em>，但不知道怎么快速起号，也没有变现思路；</li><li><em>已开始做账号</em>，但是没爆款，变现难，客单价低，定位不准确；</li><li>有稳定工作，想<em>开启副业</em>，但不知道从哪里开始；</li><li><em>企业老板</em>想做账号获客，想做创始人IP；</li><li><em>一个人单干</em>，做视频、做直播、当客服，忙不过来；</li></ul><p class="community-closing">这个社群就是为你设计的！</p><img class="community-qr" src="${brandAsset('community/community-wechat-qr.jpg')}" alt="姜来已来微信社群二维码"></article></div></section>`); }
function bindPageEvents(){
  bindAssetUpdateRangeControls();
  bindDistributionRing();
  bindModuleRadar();
  document.querySelectorAll('[data-today-editor]').forEach(button=>button.onclick=async event=>{
    event.stopPropagation();
    await openTodayEditor(button.dataset.todayEditor);
  });
  document.querySelectorAll('[data-editor-back]').forEach(button=>button.onclick=()=>closeTodayEditor());
  document.querySelectorAll('[data-editor-focus-mode]').forEach(button=>button.onclick=()=>{
    const editor=state.todayEditor;
    if(!editor)return;
    editor.focusMode=!editor.focusMode;
    editor.fileSidebarCollapsed=editor.focusMode;
    render();
  });
  document.querySelectorAll('[data-editor-files-toggle]').forEach(button=>button.onclick=()=>{
    const editor=state.todayEditor;
    if(!editor?.focusMode)return;
    editor.fileSidebarCollapsed=!editor.fileSidebarCollapsed;
    render();
  });
  document.querySelectorAll('[data-editor-edit-mode]').forEach(button=>button.onclick=async()=>{
    const editor=state.todayEditor;
    if(!editor||!isTodayDocumentSurface(editor.surface)||!editor.file)return;
    if(editor.editMode){ await finishTodayEditorEdit(); return; }
    editor.editMode=true;
    editor.draftDirty=false;
    editor.file.originalContent=editor.file.content||'';
    editor.file.originalLabel=editor.file.label;
    render();
  });
  document.querySelectorAll('[data-editor-file]').forEach(button=>button.onclick=async()=>{
    const editor=state.todayEditor;
    if(editor?.editMode&&editor.draftDirty&&!(await finishTodayEditorEdit({confirm:false})))return;
    await loadTodayEditorFile(button.dataset.editorFile);
  });
  document.querySelectorAll('[data-editor-filter]').forEach(button=>button.onclick=async()=>{
    const editor=state.todayEditor;
    if(!editor)return;
    if(editor.editMode&&editor.draftDirty&&!(await finishTodayEditorEdit({confirm:false})))return;
    editor.filter=button.dataset.editorFilter;
    const visible=editor.files.filter(item=>todayEditorFileMatchesFilter(editor,item));
    if(visible.length&&!visible.some(item=>item.id===editor.activeFileId)) await loadTodayEditorFile(visible[0].id);
    else render();
  });
  document.querySelectorAll('[data-editor-reload]').forEach(button=>button.onclick=()=>loadTodayEditorFile(state.todayEditor?.activeFileId));
  document.querySelectorAll('[data-candidate-submit]').forEach(button=>button.onclick=async()=>{
    button.disabled=true;
    try{ const session=await api('/api/today/edit-candidate/submit',{method:'POST',body:JSON.stringify({candidateId:button.dataset.candidateSubmit})}); toast(`已提交小审：${session.title||'编辑候选'}`); await refresh(); }
    catch(error){ toast(error.message||'提交小审失败'); }
    finally{ button.disabled=false; }
  });
  document.querySelectorAll('[data-topic-freeze]').forEach(button=>button.onclick=()=>{
    const editor=state.todayEditor;
    if(!editor||editor.surface!=='topics')return;
    editor.topicColumnsFrozen=!(editor.topicColumnsFrozen!==false);
    try { localStorage.setItem(topicFreezePreferenceKey, String(editor.topicColumnsFrozen)); } catch (_) {}
    render();
  });
  const markdownEditor=$('#todayMarkdownEditor');
  if(markdownEditor) markdownEditor.oninput=()=>{
    if(state.todayEditor?.file) state.todayEditor.file.content=markdownEditor.value;
    scheduleTodayEditorSave();
  };
  const copyMarkdownEditor=$('#todayCopyMarkdownEditor');
  if(copyMarkdownEditor) copyMarkdownEditor.oninput=()=>{
    if(state.todayEditor?.file) state.todayEditor.file.content=copyMarkdownEditor.value;
    scheduleTodayEditorSave();
  };
  document.querySelectorAll('[data-structure-cell]').forEach(input=>input.oninput=()=>{
    const file=state.todayEditor?.file, block=file?.structureDocument?.blocks[Number(input.dataset.block)];
    if(!file||!block||block.kind!=='table')return;
    block.rows[Number(input.dataset.row)][Number(input.dataset.column)]=structureEditableMarkdown(input);
    file.content=serializeStructureDocument(file.structureDocument);
    scheduleTodayEditorSave();
  });
  document.querySelectorAll('[data-structure-header]').forEach(input=>input.oninput=()=>{
    const file=state.todayEditor?.file, block=file?.structureDocument?.blocks[Number(input.dataset.block)];
    if(!file||!block||block.kind!=='table')return;
    block.columns[Number(input.dataset.column)]=structureEditableMarkdown(input);
    file.content=serializeStructureDocument(file.structureDocument);
    scheduleTodayEditorSave();
  });
  document.querySelectorAll('[data-structure-text-line]').forEach(input=>input.oninput=()=>{
    const file=state.todayEditor?.file, section=input.closest('[data-structure-text-block]');
    const block=file?.structureDocument?.blocks[Number(section?.dataset.structureTextBlock)];
    if(!file||!block||block.kind!=='text')return;
    const lines=String(block.content||'').split('\n');
    lines[Number(input.dataset.line)]=`${input.dataset.prefix||''}${structureEditableMarkdown(input)}`;
    block.content=lines.join('\n');
    file.content=serializeStructureDocument(file.structureDocument);
    scheduleTodayEditorSave();
  });
  document.querySelectorAll('[data-structure-filename]').forEach(input=>input.oninput=()=>{
    const file=state.todayEditor?.file;
    if(!file)return;
    file.label=String(input.textContent||'').replace(/\r?\n/g,' ').trim();
    file.renameRequested=true;
    scheduleTodayEditorSave();
  });
  document.querySelectorAll('[data-topic-cell]').forEach(input=>input.oninput=()=>{
    const editor=state.todayEditor, file=editor?.file;
    if(!file?.table)return;
    file.table.rows[Number(input.dataset.row)][Number(input.dataset.column)]=input.value;
    scheduleTodayEditorSave();
  });
  document.querySelectorAll('[data-topic-case-select]').forEach(button=>button.onclick=()=>topicBenchmarkCaseModal(Number(button.dataset.topicCaseSelect)));
  document.querySelectorAll('button[data-page]').forEach(b=>b.onclick=()=>{ void navigateToPage(b.dataset.page); });
  document.querySelectorAll('[data-module-refresh]').forEach(button=>button.onclick=async()=>{
    const moduleId=button.dataset.moduleRefresh;
    if(moduleId==='structures'||moduleId==='copies'){
      await generationSelectionModal(moduleId);
      return;
    }
    if(moduleId==='cases'){
      await caseSelectionModal();
      return;
    }
    if(moduleId==='topics'){
      await topicSelectionModal();
      return;
    }
    try{ const session=await api('/api/today/module-refresh',{method:'POST',body:JSON.stringify({moduleId})}); toast(`正在请求 Codex 独立任务：${session.title||''}`); await followVisibleTask(session,button); await refresh(); }
    catch(error){ toast(error.message||'刷新任务创建失败'); }
  });
  document.querySelectorAll('[data-skill-locked]').forEach(button=>button.onclick=()=>toast(button.title||'会员专享 Skill 尚未解锁'));
  document.querySelectorAll('[data-gallery-select]').forEach(button=>button.onclick=gallerySelectionModal);
  document.querySelectorAll('[data-generation-submit]').forEach(bindGenerationSubmit);
  // 流水线阶段卡仅用于展示与动效；详情不在此页弹出，避免干扰一键成稿操作。
  document.querySelectorAll('[data-pipeline-stage]').forEach(b=>b.onclick=null);
  document.querySelectorAll('[data-one-click]').forEach(b=>b.onclick=async()=>{
    if(b.disabled)return;
    await generationSelectionModal('copies',{pipeline:true});
  });
  document.querySelectorAll('[data-agent-detail]').forEach(b=>b.onclick=()=>teamMemberModal((state.data.agents||[]).find(agent=>agent.id===b.dataset.agentDetail)));
  document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>assetModal(state.data.assets.groups.find(g=>g.id===b.dataset.group)));
  document.querySelectorAll('[data-asset-section]').forEach(b=>b.onclick=()=>assetCatalogModal((state.data.assets.catalog||[]).find(section=>section.id===b.dataset.assetSection)));
  document.querySelectorAll('[data-asset-directory]').forEach(b=>b.onclick=()=>openAssetDirectory(b));
  document.querySelectorAll('[data-case-breakdowns]').forEach(b=>b.onclick=()=>caseBreakdownsModal());
  document.querySelectorAll('[data-type-root]').forEach(b=>b.onclick=async()=>{try{await requestDesktopFolder('/api/open-type-root',{typeId:b.dataset.typeRoot,stage:b.dataset.typeRootStage},b.dataset.typeRootLabel||'内容类型目录');}catch(error){toast(error.message||'无法打开内容类型目录');}});
  document.querySelectorAll('[data-calendar-offset]').forEach(b=>b.onclick=async()=>{state.calendarDate=new Date(state.calendarDate.getFullYear(),state.calendarDate.getMonth()+Number(b.dataset.calendarOffset),1);await loadPlanCalendar();render();});
  document.querySelectorAll('[data-plan-date]').forEach(b=>b.onclick=async event=>{
    if (b.dataset.planCompletion) return;
    event.stopPropagation();
    state.selectedPlanDate=b.dataset.planDate;
    await loadPlanCalendar();
    render();
  });
  document.querySelectorAll('[data-plan-completion]').forEach(b=>b.onclick=async event=>{
    event.stopPropagation();
    const completed=b.dataset.completed!=='true';
    await api(`/api/plans/${b.dataset.planCompletion}/occurrences/${b.dataset.planDate}/completion`, {method:'POST', body:JSON.stringify({completed})});
    await loadPlanCalendar();
    await refresh();
    toast(completed?'已标记完成，数据中心已同步':'已恢复为待完成');
  });
  document.querySelectorAll('[data-action="plan"]').forEach(b=>b.onclick=planModal);
  document.querySelectorAll('[data-action="help"]').forEach(b=>b.onclick=helpModal);
  document.querySelectorAll('[data-edit-plan]').forEach(b=>b.onclick=()=>{const plan=(state.planCalendar?.plans||[]).find(item=>item.id===b.dataset.editPlan);if(plan)planModal(plan);});
  document.querySelectorAll('[data-delete-plan]').forEach(b=>b.onclick=async()=>{const plan=(state.planCalendar?.plans||[]).find(item=>item.id===b.dataset.deletePlan);const message=plan?.repeat_rule&&plan.repeat_rule!=='none'?'删除后将移除整条重复计划及未来日历标记，确定删除吗？':'确定删除这条工作计划吗？';if(!window.confirm(message))return;await api('/api/plans/'+b.dataset.deletePlan,{method:'DELETE'});await loadPlanCalendar();render();toast('工作计划已删除');});
}
async function encodeAttachments(){const files=Array.from($('#sessionAttachments')?.files||[]);if(files.length>5)throw new Error('一次最多上传 5 个附件');return Promise.all(files.map(file=>new Promise((resolve,reject)=>{if(file.size>5*1024*1024){reject(new Error('单个附件必须小于 5MB'));return;}const reader=new FileReader();reader.onload=()=>resolve({name:file.name,mime:file.type,data:String(reader.result).split(',').pop()});reader.onerror=()=>reject(new Error('附件读取失败'));reader.readAsDataURL(file)})));}
// The structure editor launches the same batch as the pipeline, but keeps the
// editor open so the user can continue reviewing the locked source document.
// The global refresh control sits outside page renders. Capture its click so a
// page-level overlay or delegated handler cannot prevent the unified refresh.
document.addEventListener('click', event=>{
  const refreshButton = event.target.closest('#refreshButton');
  if (!refreshButton) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  void syncWorkbenchData();
}, true);
document.addEventListener('click', event=>{
  const target=event.target.closest('#typePicker,#mobileTypePicker,#sideTypeButton,[data-type-menu]');
  if(!target)return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if(target.matches('#typePicker,#mobileTypePicker,#sideTypeButton')){
    state.typeMenuOpen=!state.typeMenuOpen;
    renderTypeMenu();
    return;
  }
  const type=types().find(item=>item.id===target.dataset.typeMenu);
  if(!type?.available){ toast(type?.unlockReason||'会员专享内容尚未解锁'); return; }
  state.type=type.id;
  state.typeMenuOpen=false;
  render();
}, true);
document.addEventListener('pointerdown', event=>{if(state.typeMenuOpen&&!event.target.closest('#typeMenu,#typePicker,#mobileTypePicker,#sideTypeButton')){state.typeMenuOpen=false;renderTypeMenu();}});
document.addEventListener('keydown', event=>{
  if(event.key!=='Escape'||!state.todayEditor?.focusMode||!$('#modal')?.hidden)return;
  event.preventDefault();
  state.todayEditor.focusMode=false;
  state.todayEditor.fileSidebarCollapsed=false;
  render();
});
document.addEventListener('click', async event=>{const target=event.target.closest('button,[data-close]'); if(!target)return; try{if(target.dataset.todayFolder){await openTodayFolder(target);return;} if(target.dataset.close!==undefined){closeModal();return;} if(target.id==='typePicker'||target.id==='mobileTypePicker'||target.id==='sideTypeButton'){typeModal();return;} if(target.id==='assistant'){await assistantModal();return;} if(target.dataset.type){const type=types().find(item=>item.id===target.dataset.type);if(!type.available){toast('会员专享内容尚未解锁');return;}state.type=type.id;closeModal();render();return;} if(target.dataset.copy){await navigator.clipboard.writeText(target.dataset.copy);toast('已复制');return;} if(target.dataset.openPipelineStage){return;}  if(target.dataset.createSession){const message=($('#sessionMessage')||$('#assistantMessage'))?.value||'';const attachments=await encodeAttachments();const session=await api('/api/sessions',{method:'POST',body:JSON.stringify({action:target.dataset.createSession,message,attachments,title:target.dataset.createSession==='general'?'小姜对话任务':undefined})});approvalModal(session);return;} if(target.dataset.approve){const session=await api('/api/sessions/'+target.dataset.approve+'/approve',{method:'POST',body:'{}'});await refresh();const updated=await api('/api/sessions/'+session.id);state.data.sessions=[updated];scheduleTaskRefresh();toast('任务已提交，等待 Codex 执行。');await sessionDetailModal(updated);return;} if(target.dataset.openApproval){const approvals=await api('/api/approvals');taskApprovalModal((approvals.approvals||[]).find(item=>item.id===target.dataset.openApproval));return;} if(target.dataset.respondApproval){await api('/api/approvals/'+target.dataset.respondApproval+'/respond',{method:'POST',body:JSON.stringify({decision:target.dataset.decision})});toast(target.dataset.decision==='accept'?'已允许本次操作':'已拒绝本次操作');closeModal();await refresh();return;} if(target.dataset.sessionDetail||target.dataset.sessionOpen){const id=target.dataset.sessionDetail||target.dataset.sessionOpen;const session=(state.data.sessions||[]).find(item=>item.id===id);if(session)await sessionDetailModal(session);return;} if(target.dataset.sessionCancel){await api('/api/sessions/'+target.dataset.sessionCancel+'/cancel',{method:'POST',body:'{}'});toast('任务已终止，历史记录已保留');closeModal();await refresh();return;} if(target.dataset.sessionApproval){approvalModal((state.data.sessions||[]).find(item=>item.id===target.dataset.sessionApproval));return;}}catch(error){toast(error.message||'操作失败');} });
document.addEventListener('submit', async event=>{if(event.target.id==='userInputForm'){event.preventDefault();try{const answers={};event.target.querySelectorAll('[data-question-id]').forEach(input=>{const id=input.dataset.questionId;if(input.type==='radio'&&!input.checked)return;if(input.dataset.other==='true'&&!input.value.trim())return;answers[id]=input.value;});const approvalId=event.target.dataset.approvalId;await api('/api/approvals/'+approvalId+'/respond',{method:'POST',body:JSON.stringify({answers})});toast('已将信息提交给 Codex');closeModal();await refresh();}catch(error){toast(error.message||'提交失败');}return;}if(event.target.id!=='planForm')return;event.preventDefault();try{const form=event.target, values=new FormData(form), repeatRule=String(values.get('repeatRule')||'none'), data={contentType:values.get('contentType'),targetCount:values.get('targetCount'),startDate:values.get('startDate'),repeatRule};if(repeatRule==='weekly')data.weekdays=Array.from(form.querySelectorAll('input[name="weekdays"]:checked')).map(input=>Number(input.value));if(repeatRule==='monthly')data.monthlyDay=values.get('monthlyDay');if(repeatRule!=='none')data.endsAt=values.get('endsAt');const id=form.dataset.planId;await api(id?'/api/plans/'+id:'/api/plans',{method:id?'PUT':'POST',body:JSON.stringify(data)});state.calendarDate=new Date(`${data.startDate}T00:00:00`);state.selectedPlanDate=data.startDate;await loadPlanCalendar();closeModal();render();toast(id?'工作计划已修改':'工作计划已保存到本机');}catch(error){toast(error.message||'保存工作计划失败');}});
let canvasResizeFrame=0;
window.addEventListener('resize',()=>{
  window.cancelAnimationFrame(canvasResizeFrame);
  canvasResizeFrame=window.requestAnimationFrame(fitWorkbenchCanvas);
},{passive:true});
restoreTodaySnapshot();
refresh('initial').catch(error=>{document.getElementById('workbenchSplash')?.classList.add('is-hidden');if(!state.data)$('#app').innerHTML=`<div class="error">工作台未能读取本机服务：${esc(error.message)}</div>`;else toast('本机数据暂时无法同步，正在显示上次有效数据');});
