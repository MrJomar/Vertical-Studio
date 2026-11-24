"use strict";
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const ICONS={
 sparkle:'<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
 trophy:'<path d="M8 4h8v5a4 4 0 01-8 0zM8 6H5a3 3 0 003 4M16 6h3a3 3 0 01-3 4M12 13v4M8 20h8"/>',
 map:'<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14"/>',
 film:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 4v16M16 4v16M4 9h4M16 9h4M4 15h4M16 15h4"/>',
 shapes:'<circle cx="8" cy="8" r="4"/><rect x="13" y="4" width="7" height="7" rx="1"/><path d="M4 20l4-8 4 8z"/><circle cx="17" cy="17" r="3"/>',
 scissors:'<circle cx="6" cy="7" r="3"/><circle cx="6" cy="17" r="3"/><path d="M8.5 8.5L20 19M8.5 15.5L20 5"/>'};
const icon=(n,s=20)=>`<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[n]||ICONS.film}</svg>`;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const H={"X-VS-Token":window.VS_TOKEN,"Content-Type":"application/json"};
async function api(path,body){
  const r=await fetch(path,body===undefined?{headers:H}:{method:"POST",headers:H,body:JSON.stringify(body)});
  if(!r.ok){let m=r.statusText;try{m=(await r.json()).error||m}catch(e){}throw new Error(m)}
  return r;
}
const jget=async p=>(await api(p)).json(), jpost=async(p,b)=>(await api(p,b)).json();
function toast(m,err){const t=$("#toast");t.textContent=m;t.className="toast"+(err?" err":"");t.hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>t.hidden=true,err?6000:2800)}

const S={schema:null,project:{settings:{},scenes:[]},path:null,sel:-1,dirty:false,t:0,dur:5,playing:false,name:"Proyecto sin título",durs:{}};
const FILTER={media:"media",source:"video",audio:"audio",music:"audio",geojson:"geojson",media_dir:"dir"};

function markDirty(v=true){S.dirty=v;$("#dirty").hidden=!v}
function curScene(){return S.project.scenes[S.sel]}
function sceneTitle(sc){return sc.title||sc.hook||(sc.source&&sc.source.split(/[\\/]/).pop())||(sc.narration||"").slice(0,30)||"(sin título)"}

// ------------------------------------------------------------------ lista
function renderList(){
  const L=$("#list");L.innerHTML="";const sc=S.project.scenes;$("#count").textContent=sc.length?sc.length+" escenas":"";
  sc.forEach((s,i)=>{
    const ty=S.schema.types[s.type]||{label:s.type,icon:"film"};
    const d=document.createElement("div");d.className="sc"+(i===S.sel?" sel":"");
    const sub=s.type==="top_item"?`Puesto ${s.rank||""}`:ty.label;
    d.innerHTML=`<div class="ic">${icon(ty.icon,18)}</div><div class="tx"><div class="t1">${esc(sceneTitle(s))}</div><div class="t2">${esc(sub)}${S.durs[i]?` · ${S.durs[i].toFixed(1)} s`:""}</div></div>
      <div class="mv"><button data-m="up" title="Subir">↑</button><button data-m="dn" title="Bajar">↓</button><button data-m="dup" title="Duplicar">⧉</button><button data-m="del" title="Eliminar">✕</button></div>`;
    d.onclick=e=>{const m=e.target.dataset.m;if(m){e.stopPropagation();return moveScene(i,m)}select(i)};
    L.appendChild(d)});
  const empty=!sc.length;$(".work").classList.toggle("home",empty);$("#empty").hidden=!empty;$("#player").hidden=empty;$(".insp").style.visibility=empty?"hidden":"visible";
  if(empty)renderEmpty();
}
function moveScene(i,m){const a=S.project.scenes;S.durs={};
  if(m==="up"&&i>0){[a[i-1],a[i]]=[a[i],a[i-1]];S.sel=i-1}
  else if(m==="dn"&&i<a.length-1){[a[i+1],a[i]]=[a[i],a[i+1]];S.sel=i+1}
  else if(m==="dup"){a.splice(i+1,0,JSON.parse(JSON.stringify(a[i])));S.sel=i+1}
  else if(m==="del"){a.splice(i,1);S.sel=Math.min(S.sel,a.length-1)}
  markDirty();renderList();renderForm();refresh()}
function select(i){S.sel=i;S.t=1.6;renderList();renderForm();refresh()}
function addScene(type){const ty=S.schema.types[type];const sc={type};
  ty.fields.forEach(f=>{if(f.default!==""&&f.default!==undefined&&!(Array.isArray(f.default)&&!f.default.length))sc[f.key]=f.default});
  if(type==="top_item")sc.rank=String(S.project.scenes.filter(s=>s.type==="top_item").length+1);
  S.project.scenes.push(sc);S.sel=S.project.scenes.length-1;markDirty();renderList();renderForm();refresh()}

function renderEmpty(){
  const E=$("#empty");const ty=S.schema.types;
  E.innerHTML=`<h1>Tus proyectos</h1><p>Lo que sube la tarea diaria a GitHub y lo que abres o guardas, separado por estilo. Inicia todo lo pendiente con un clic.</p>
  <div id="dash"></div>
  <div class="sec" style="margin-top:34px">Crear algo nuevo</div>
  <div class="grid">${S.schema.order.map(k=>`<div class="tcard" data-add="${k}"><div class="ic">${icon(ty[k].icon,22)}</div><b>${esc(ty[k].label)}</b><span>${esc(ty[k].desc)}</span></div>`).join("")}</div>
  <div style="margin-top:20px;display:flex;gap:10px;flex-wrap:wrap"><button class="btn primary" data-act="examples">✨ Ver ejemplos de cada tipo</button><button class="btn" data-act="ai">🎨 Animación con IA</button><button class="btn" data-act="script">📝 Guion → escenas</button><button class="btn" data-act="autoclip">Sacar clips de un video largo</button><button class="btn" data-act="voices">🎙 Voces y perfiles</button><button class="btn" data-act="pieces">🧩 Piezas SVG</button></div>`;
  E.querySelectorAll("[data-add]").forEach(e=>e.onclick=()=>addScene(e.dataset.add));
  E.querySelectorAll("[data-act]").forEach(e=>e.onclick=()=>act(e.dataset.act));
  startDash();
  if(!window._synced){window._synced=1;jpost("/api/tablero_sync",{}).then(r=>{if(r&&r.nuevos)toast(r.nuevos+" proyecto(s) nuevo(s) de GitHub")}).catch(()=>{})}
}

// ------------------------------------------------------------------ formulario
function renderForm(){
  const sc=curScene(),F=$("#form"),Hd=$("#insp-head");
  if(!sc){F.innerHTML="";Hd.innerHTML="";return}
  const ty=S.schema.types[sc.type];
  Hd.innerHTML=`<span style="color:var(--acc2)">${icon(ty.icon,20)}</span>${esc(ty.label)}<span class="sp"></span>`;
  F.innerHTML="";
  ty.fields.forEach(f=>F.appendChild(fieldEl(f,sc,()=>{markDirty();changed(f.key)})));
}
function fieldEl(f,obj,onch,settings){
  const w=document.createElement("div");w.className="fld";const v=obj[f.key];const val=v===undefined?f.default:v;
  const set=x=>{obj[f.key]=x;onch()};
  const lab=`<label>${esc(f.label)}</label>`;
  if(f.kind==="bool"){w.className="";w.innerHTML=`<label class="chk"><input type="checkbox" ${val?"checked":""}><span>${esc(f.label)}</span></label>`;w.querySelector("input").onchange=e=>set(e.target.checked);return w}
  if(f.kind==="text"){w.innerHTML=lab+`<input type="text" value="${esc(val)}">`;w.querySelector("input").oninput=e=>set(e.target.value)}
  else if(f.kind==="multiline"){w.innerHTML=lab+`<textarea rows="3">${esc(val)}</textarea>`;w.querySelector("textarea").oninput=e=>set(e.target.value)}
  else if(f.kind==="json"){w.innerHTML=lab+`<textarea class="code" spellcheck="false">${esc(JSON.stringify(val??[],null,1))}</textarea><div class="hint">Elementos: esfera, villano, bacteria_mala, bacteria_buena, persona, medidor, puerta, cartel, etiqueta, banda, pez, gato, pastilla, hielo, olor, corazon, estrella, marca, nariz, pin, calendario, emoji… Usa «at» con una palabra de la narración para sincronizar.</div>`;
    const ta=w.querySelector("textarea");ta.oninput=()=>{try{const v=JSON.parse(ta.value||"[]");ta.classList.remove("bad");set(v)}catch(e){ta.classList.add("bad")}}}
  else if(f.kind==="number"){w.innerHTML=lab+`<input type="number" step="any" value="${esc(val)}">`;w.querySelector("input").oninput=e=>{const n=parseFloat(e.target.value);set(isNaN(n)?f.default:n)}}
  else if(f.kind==="choice"||f.kind==="theme"){
    w.innerHTML=lab+`<select>${f.choices.map(c=>`<option value="${esc(c.value)}" ${String(c.value)===String(val)?"selected":""}>${esc(c.label)}</option>`).join("")}</select>`;
    w.querySelector("select").onchange=e=>{const c=f.choices.find(c=>String(c.value)===e.target.value);set(c?c.value:e.target.value)}}
  else if(f.kind==="combo"){w.innerHTML=lab+`<input type="text" list="dl_${f.key}" value="${esc(val)}"><datalist id="dl_${f.key}">${f.choices.map(c=>`<option value="${esc(c.value)}">`).join("")}</datalist>`;w.querySelector("input").oninput=e=>set(e.target.value)}
  else if(f.kind==="file"){
    w.innerHTML=lab+`<div class="frow"><input class="inp" type="text" value="${esc(val)}" placeholder="(ninguno)"><button class="btn small">Elegir…</button></div>`;
    const inp=w.querySelector("input");inp.oninput=()=>set(inp.value);
    w.querySelector("button").onclick=async()=>{const kind=f.key==="media_dir"?"dir":"file";
      try{const r=await jpost("/api/pick",{kind,filter:FILTER[f.key]||"any"});if(r.paths.length){inp.value=r.paths[0];set(r.paths[0])}}catch(e){toast(e.message,1)}}}
  else if(f.kind==="files"){
    const draw=()=>{const arr=Array.isArray(obj[f.key])?obj[f.key]:(obj[f.key]=[]);
      w.innerHTML=lab+`<div class="files">${arr.map((p,i)=>`<div class="th" title="${esc(p)}"><img src="/api/thumb?k=${window.VS_TOKEN}&w=130&path=${encodeURIComponent(p)}" onerror="this.style.opacity=.2"><button data-i="${i}">✕</button></div>`).join("")}<button class="add" title="Añadir">＋</button></div>`;
      w.querySelectorAll(".th button").forEach(b=>b.onclick=()=>{arr.splice(+b.dataset.i,1);draw();onch()});
      w.querySelector(".add").onclick=async()=>{try{const r=await jpost("/api/pick",{kind:"files",filter:"media"});if(r.paths.length){arr.push(...r.paths);draw();onch()}}catch(e){toast(e.message,1)}}};
    draw()}
  return w}

// ------------------------------------------------------------------ vista previa
let pt=null,pseq=0,lastUrl=null;
function changed(){clearTimeout(pt);pt=setTimeout(()=>{refresh();renderList()},350)}
async function refresh(){
  const sc=curScene();if(!sc)return;const my=++pseq;$("#spin").hidden=false;
  try{
    const r=await api("/api/preview",{project:S.project,path:S.path,scene:S.sel,t:S.t,w:S.playing?340:620});
    if(my!==pseq)return;
    S.dur=parseFloat(r.headers.get("X-Duration"))||S.dur;S.durs[S.sel]=S.dur;
    const w=decodeURIComponent(r.headers.get("X-Warn")||"");const wb=$("#warn");wb.hidden=!w;wb.textContent=w;
    const b=await r.blob();const u=URL.createObjectURL(b);$("#frame").src=u;if(lastUrl)URL.revokeObjectURL(lastUrl);lastUrl=u;
    updTime();
  }catch(e){if(my===pseq){const wb=$("#warn");wb.hidden=false;wb.textContent="Vista previa: "+e.message}}
  finally{if(my===pseq)$("#spin").hidden=true}
}
function updTime(){$("#time").textContent=`${S.t.toFixed(1)} / ${S.dur.toFixed(1)} s`;$("#seek").value=S.dur?Math.round(S.t/S.dur*1000):0}
$("#seek").oninput=e=>{S.t=e.target.value/1000*S.dur;stopPlay();clearTimeout(refresh.t);refresh.t=setTimeout(refresh,60)};
function stopPlay(){S.playing=false;$("#play").textContent="▶"}
$("#play").onclick=async()=>{
  if(S.playing)return stopPlay();S.playing=true;$("#play").textContent="❚❚";if(S.t>=S.dur-0.05)S.t=0;let last=performance.now();
  while(S.playing){const n=performance.now();S.t+=(n-last)/1000;last=n;if(S.t>=S.dur){S.t=S.dur;await refresh();stopPlay();break}await refresh()}
};

// ------------------------------------------------------------------ modales
function modal(html,cls=""){const m=$("#modal"),c=$("#card");c.className="card "+cls;c.innerHTML=html;m.hidden=false;
  c.querySelectorAll("[data-close]").forEach(e=>e.onclick=closeModal);return c}
function closeModal(){$("#modal").hidden=true;$("#card").innerHTML=""}
$("#modal").addEventListener("mousedown",e=>{if(e.target.id==="modal"&&!$("#card").dataset.lock)closeModal()});
async function poll(id,onp){for(;;){const j=await jget("/api/job?id="+id);onp&&onp(j);if(j.state!=="running")return j;await new Promise(r=>setTimeout(r,500))}}
const fmtT=s=>{s=Math.round(s);return Math.floor(s/60)+":"+String(s%60).padStart(2,"0")};

async function examplesModal(){
  const c=modal(`<div class="mh">Ejemplos de cada tipo de video<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb"><div class="exg" id="exg"></div></div>`);
  const list=await jget("/api/examples");const g=c.querySelector("#exg");
  const draw=()=>{g.innerHTML=list.map(e=>`<div class="ex" data-id="${e.id}"><div class="vid">${e.video?`<video src="${e.video}${e.video.includes('?')?'&':'?'}k=${window.VS_TOKEN}" muted loop playsinline controls></video>`:`<div class="nov">${icon(S.schema.types[e.type].icon,34)}<br><br>Este ejemplo usa mapas reales: se genera en tu PC (necesita internet) en menos de un minuto.</div>`}</div>
    <div class="bd"><b>${esc(e.title)}</b><span>${esc(e.desc)}</span><div style="display:flex;gap:8px">${e.video?"":`<button class="btn small" data-gen>Generar vista</button>`}<button class="btn small primary" data-use>Usar como base</button></div><div class="bar" hidden><i></i></div></div></div>`).join("");
    g.querySelectorAll(".ex").forEach(el=>{const e=list.find(x=>x.id===el.dataset.id);
      el.querySelector("[data-use]").onclick=()=>{loadProject(e.project,null,e.title);closeModal()};
      const gb=el.querySelector("[data-gen]");if(gb)gb.onclick=async()=>{gb.disabled=true;const bar=el.querySelector(".bar");bar.hidden=false;
        try{const {id}=await jpost("/api/example_render",{id:e.id});const j=await poll(id,j=>bar.firstChild.style.width=(j.frac*100)+"%");
          if(j.state==="done"){e.video=j.result.video+"?t="+Date.now();draw()}else{toast(j.error||"No se pudo generar",1);gb.disabled=false}}catch(x){toast(x.message,1);gb.disabled=false}};
      const v=el.querySelector("video");if(v){el.onmouseenter=()=>v.play().catch(()=>{});el.onmouseleave=()=>v.pause()}})};
  draw()}

function loadProject(p,path,name){
  S.project={settings:p.settings||{},scenes:p.scenes||[]};S.path=path;S.durs={};S.sel=S.project.scenes.length?0:-1;S.t=1.6;
  S.name=name||(path?path.split(/[\\/]/).pop().replace(/\.json$/i,""):"Proyecto sin título");$("#pname").value=S.name;markDirty(false);renderList();renderForm();refresh()}

function settingsModal(){
  const st=S.project.settings;const c=modal(`<div class="mh">Ajustes del proyecto<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb" id="sb"></div><div class="mf"><select id="pre" class="inp" style="width:170px"><option value="">Plantillas…</option></select><button class="btn small" id="pl">Aplicar</button><button class="btn small" id="ps">Guardar actual</button><span class="hint" style="flex:1">${S.schema.gpu?"✔ GPU detectada: "+S.schema.gpu:"GPU no detectada: se usará la CPU"}</span><button class="btn primary" data-close>Listo</button></div>`,"md");
  const b=c.querySelector("#sb");
  S.schema.settings.forEach(g=>{const h=document.createElement("div");h.className="sec";h.textContent=g.group;b.appendChild(h);
    g.fields.forEach(f=>{const ff={...f};if(f.kind==="file"&&f.key==="music"){}b.appendChild(fieldEl(ff,st,()=>{markDirty();S.durs={};clearTimeout(settingsModal.t);settingsModal.t=setTimeout(refresh,300)},true))})});
  (async()=>{const u=await jget("/api/update_check");const h=document.createElement("div");h.className="sec";h.textContent="Actualizaciones";b.appendChild(h);
    const w=document.createElement("div");w.innerHTML=`<label class="chk"><input type="checkbox" id="uc" ${u.enabled?"checked":""}><span>Buscar actualizaciones al iniciar</span></label>
    <label class="chk"><input type="checkbox" id="ua" ${u.auto?"checked":""}><span>Instalarlas automáticamente (si no tienes un proyecto abierto)</span></label>
    <div class="fld"><label>Repositorio de GitHub</label><input type="text" id="ur" value="${esc(u.repo)}"></div>
    <div class="fld"><label>Token de solo lectura (solo si el repositorio es privado; se guarda en este equipo)</label><input type="text" id="ut" placeholder="${u.has_token?"(guardado)":"github_pat_…"}"></div>
    <div class="frow"><button class="btn small" id="ub">Buscar ahora</button><span class="hint" id="us" style="align-self:center">Versión instalada: ${esc(u.current)}</span></div>`;b.appendChild(w);
    const save=async()=>{const body={check_updates:w.querySelector("#uc").checked,auto_update:w.querySelector("#ua").checked,update_repo:w.querySelector("#ur").value.trim()};const t=w.querySelector("#ut").value.trim();if(t)body.update_token=t;return jpost("/api/update_config",body)};
    w.querySelector("#ub").onclick=async()=>{const r=await save();w.querySelector("#us").textContent=r.error?r.error:(r.newer?"Hay una versión nueva: "+r.latest+" (usa «⟳ Actualizar» arriba)":"Estás al día ("+r.current+")")};
    w.querySelector("#uc").onchange=save;w.querySelector("#ua").onchange=save})();
  const sel=c.querySelector("#pre");let presets={};
  const fill=async()=>{presets=await jget("/api/presets");sel.innerHTML='<option value="">Plantillas…</option>'+Object.keys(presets).map(k=>`<option>${esc(k)}</option>`).join("")};fill();
  c.querySelector("#pl").onclick=()=>{const p=presets[sel.value];if(!p)return;Object.assign(S.project.settings,p);markDirty();closeModal();settingsModal();refresh()};
  c.querySelector("#ps").onclick=async()=>{const n=prompt("Nombre de la plantilla (p. ej. Randompedia):");if(!n)return;await jpost("/api/preset_save",{name:n,settings:S.project.settings});await fill();sel.value=n;toast("Plantilla guardada")};
}

function autoclipModal(){
  let video="";
  const c=modal(`<div class="mh">Auto-clips desde un video largo<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb">
  <p class="hint">Transcribe el video con Whisper, elige los mejores momentos y los convierte en escenas verticales. La primera vez descarga el modelo (requiere internet).</p>
  <div class="fld"><label>Video</label><div class="frow"><input class="inp" id="v" placeholder="(elige un video)"><button class="btn small" id="pk">Elegir…</button></div></div>
  <div class="row2" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">
   <div class="fld"><label>Cantidad de clips</label><input type="number" id="n" value="5"></div>
   <div class="fld"><label>Mínimo (s)</label><input type="number" id="lo" value="20"></div>
   <div class="fld"><label>Máximo (s)</label><input type="number" id="hi" value="55"></div></div>
  <div class="fld"><label>Idioma (vacío = detectar)</label><input type="text" id="lang" value="es"></div>
  <div class="fld"><label>Clave de Gemini (opcional, mejora la selección)</label><input type="text" id="gk"></div>
  <div class="bar" id="bar" hidden><i></i></div><div class="hint" id="st"></div></div>
  <div class="mf"><button class="btn" data-close>Cancelar</button><button class="btn primary" id="go">Analizar</button></div>`,"md");
  c.querySelector("#pk").onclick=async()=>{try{const r=await jpost("/api/pick",{kind:"file",filter:"video"});if(r.paths.length){video=r.paths[0];c.querySelector("#v").value=video}}catch(e){toast(e.message,1)}};
  c.querySelector("#go").onclick=async()=>{video=c.querySelector("#v").value||video;if(!video)return toast("Elige un video",1);
    c.dataset.lock=1;const go=c.querySelector("#go");go.disabled=true;c.querySelector("#bar").hidden=false;
    try{const {id}=await jpost("/api/autoclip",{video,n:+c.querySelector("#n").value,lo:+c.querySelector("#lo").value,hi:+c.querySelector("#hi").value,language:c.querySelector("#lang").value,gemini_key:c.querySelector("#gk").value,settings:S.project.settings,fit:"blur"});
      const j=await poll(id,j=>{c.querySelector("#bar i").style.width=(j.frac*100)+"%";c.querySelector("#st").textContent=j.stage});
      delete c.dataset.lock;
      if(j.state==="done"){const first=S.project.scenes.length;S.project.scenes.push(...j.result.scenes);S.durs={};S.sel=first;markDirty();closeModal();renderList();renderForm();refresh();toast(j.result.scenes.length+" clips añadidos")}
      else{toast(j.error||"Cancelado",1);go.disabled=false}}catch(e){delete c.dataset.lock;toast(e.message,1);go.disabled=false}}}

function scriptModal(){
  const c=modal(`<div class="mh">Guion → escenas<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb">
  <p class="hint">Pega tu guion completo. Lo divide en escenas de B-roll por frases. Si eliges una carpeta de imágenes, las empareja por nombre de archivo (o en orden).</p>
  <div class="fld"><label>Título del video</label><input type="text" id="tt"></div>
  <div class="fld"><textarea id="tx" rows="11" placeholder="Pega aquí el guion…"></textarea></div>
  <div class="fld"><label>Carpeta de imágenes/videos (opcional)</label><div class="frow"><input class="inp" id="md"><button class="btn small" id="pk">Elegir…</button></div></div>
  </div>
  <div class="mf"><button class="btn" data-close>Cancelar</button><button class="btn primary" id="go">Crear escenas</button></div>`,"md");
  c.querySelector("#pk").onclick=async()=>{try{const r=await jpost("/api/pick",{kind:"dir"});if(r.paths.length)c.querySelector("#md").value=r.paths[0]}catch(e){toast(e.message,1)}};
  c.querySelector("#go").onclick=async()=>{const text=c.querySelector("#tx").value;if(!text.trim())return toast("Pega un guion",1);
    try{const r=await jpost("/api/script",{text,title:c.querySelector("#tt").value,media_dir:c.querySelector("#md").value });
      if(!r.scenes.length)return toast("No encontré contenido",1);
      const first=S.project.scenes.length;S.project.scenes.push(...r.scenes);S.durs={};S.sel=first;markDirty();closeModal();renderList();renderForm();refresh();toast(r.scenes.length+" escenas creadas")}catch(e){toast(e.message,1)}}}

async function applyUpdate(u){
  const box=$("#upd");box.innerHTML=`<b>Instalando la versión ${esc(u.latest)}…</b><div class="hint">No cierres la ventana. Se reiniciará sola.</div>`;box.hidden=false;
  try{const r=await jpost("/api/update_apply",{});box.innerHTML=`<b>✔ Actualizado (${r.files} archivos)</b><div class="hint">Reiniciando el programa…</div>`;
    await jpost("/api/restart",{});setTimeout(()=>{try{window.close()}catch(e){}box.innerHTML=`<b>Listo</b><div class="hint">Ya se abrió la versión nueva. Puedes cerrar esta ventana.</div>`},2500)}
  catch(e){box.innerHTML=`<b>No se pudo actualizar</b><div class="hint">${esc(e.message)}</div><div class="frow"><button class="btn small" id="ux">Cerrar</button></div>`;$("#ux").onclick=()=>box.hidden=true}}

async function checkUpdates(manual){
  try{const u=await jget("/api/update_check");const box=$("#upd");
    if(u.newer){
      if(u.auto&&!manual&&!S.dirty&&!S.project.scenes.length){applyUpdate(u);return u}
      box.innerHTML=`<b>🔔 Hay una versión nueva: ${esc(u.latest)}</b><div class="hint">Tienes la ${esc(u.current)}.${u.notes?" Novedad: "+esc(u.notes):""}</div><div class="frow"><button class="btn small primary" id="uo">Actualizar ahora</button><button class="btn small" id="ux">Luego</button></div>`;box.hidden=false;
      $("#uo").onclick=()=>{if(S.dirty&&!confirm("Hay cambios sin guardar; se perderán al reiniciar. ¿Actualizar ahora?"))return;applyUpdate(u)};$("#ux").onclick=()=>box.hidden=true}
    else if(manual){toast(u.error?u.error:"Ya tienes la última versión ("+u.current+")",!!u.error)}
    return u}catch(e){if(manual)toast("No se pudo comprobar: "+e.message,1)}}

// ------------------------------------------------------------------ voces
const ENGINES=[["edge","Edge (gratis, internet)"],["gemini","Gemini (IA, necesita API key)"],["sapi","Local (voces de Windows, sin internet)"],["silencio","Sin voz"]];
const TOKQ=()=>"k="+encodeURIComponent(window.VS_TOKEN);
async function voicePicker(box,st,onch){
  /* st: {engine,voice,model,style,rate}; box: contenedor */
  box.innerHTML=`<div class="fld"><label>Motor de voz</label><select class="inp" id="vp_e">${ENGINES.map(e=>`<option value="${e[0]}">${esc(e[1])}</option>`).join("")}</select></div>
  <div id="vp_body"></div>`;
  const body=box.querySelector("#vp_body"),sel=box.querySelector("#vp_e");sel.value=st.engine||"edge";
  let cat=null,gen=0;
  const draw=async()=>{
    const my=++gen;
    st.engine=sel.value;onch&&onch();
    if(st.engine==="silencio"){body.innerHTML=`<div class="hint">El video se genera sin voz (tiempos estimados).</div>`;return}
    body.innerHTML=`<div class="hint">Cargando voces…</div>`;
    try{cat=await jget("/api/voices?engine="+st.engine)}catch(e){if(my===gen)body.innerHTML=`<div class="hint">${esc(e.message)}</div>`;return}
    if(my!==gen)return;
    const gem=st.engine==="gemini";
    if(gem&&!cat.config.has_key)body.innerHTML=`<div class="hint" style="color:#fbbf24">Falta la API key de Gemini: pégala en la sección «Gemini» de esta ventana.</div>`;else body.innerHTML="";
    const w=document.createElement("div");
    w.innerHTML=`${gem?`<div class="fld"><label>Modelo de audio${cat.gemini&&cat.gemini.live?" (lista real de tu cuenta)":""}</label><select class="inp" id="vp_m">${(cat.gemini?cat.gemini.models:[]).map(m=>`<option>${esc(m)}</option>`).join("")}</select></div>`:""}
    <div class="fld"><label>Voz — escribe para buscar (${cat.voices.length})</label><input class="inp" id="vp_q" placeholder="Buscar: es-MX, Dalia, cálida, femenina…"><select class="inp" id="vp_v" size="7" style="margin-top:6px"></select></div>
    ${gem?`<div class="fld"><label>Estilo o tono (opcional) — ej.: «Di con voz cálida y pausada»</label><input class="inp" id="vp_s" value="${esc(st.style||"")}"></div>`:""}
    <div class="fld"><label>Velocidad (%)</label><input class="inp" id="vp_r" type="number" value="${st.rate||0}"></div>
    <div class="frow"><button class="btn small" id="vp_t">▶ Probar voz</button><span class="hint" id="vp_st" style="align-self:center"></span></div>`;
    body.appendChild(w);
    const q=w.querySelector("#vp_q"),vs=w.querySelector("#vp_v");
    const fillV=()=>{const t=q.value.trim().toLowerCase();vs.innerHTML="";
      cat.voices.filter(v=>!t||(v.label+" "+v.locale+" "+v.gender).toLowerCase().includes(t)).slice(0,400).forEach(v=>{const o=document.createElement("option");o.value=v.id;o.textContent=v.label;if(v.id===st.voice)o.selected=true;vs.appendChild(o)});
      if(!vs.value&&vs.options.length&&!st.voice){}};
    fillV();q.oninput=fillV;
    vs.onchange=()=>{st.voice=vs.value;onch&&onch()};
    if(!st.voice&&cat.voices.length){st.voice=cat.voices[0].id;vs.value=st.voice}
    const m=w.querySelector("#vp_m");if(m){if(st.model&&[...m.options].some(o=>o.value===st.model))m.value=st.model;st.model=m.value;m.onchange=()=>{st.model=m.value;onch&&onch()}}
    const sty=w.querySelector("#vp_s");if(sty)sty.oninput=()=>{st.style=sty.value;onch&&onch()};
    w.querySelector("#vp_r").oninput=e=>{st.rate=+e.target.value||0;onch&&onch()};
    w.querySelector("#vp_t").onclick=async()=>{const stt=w.querySelector("#vp_st");stt.textContent="Generando…";
      try{const r=await jpost("/api/voice_test",{engine:st.engine,voice:st.voice,model:st.model,style:st.style,rate:st.rate});
        stt.textContent="";const a=new Audio("/api/voice_audio?f="+encodeURIComponent(r.file)+"&"+TOKQ());a.play()}catch(e){stt.textContent="";toast(e.message,1)}};
  };
  sel.onchange=()=>{st.voice="";st.model="";draw()};
  await draw();
}
const PROJ_VOICE=()=>{const s=S.project.settings;return {engine:s.tts_engine||"edge",voice:s.voice||"",model:s.voice_model||"",style:s.voice_style||"",rate:s.tts_rate||0}};
function applyProjVoice(v){const s=S.project.settings;s.tts_engine=v.engine;s.voice=v.voice;s.voice_model=v.model;s.voice_style=v.style;s.tts_rate=v.rate;markDirty()}

async function voicesModal(){
  const c=modal(`<div class="mh">🎙 Voces<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb" id="vb"></div><div class="mf"><button class="btn primary" data-close>Listo</button></div>`,"md");
  const b=c.querySelector("#vb");
  let cfg=await jget("/api/voice_config");
  const draw=async()=>{
    cfg=await jget("/api/voice_config");
    const names=Object.keys(cfg.profiles);const st=S.project.settings;
    b.innerHTML=`<div class="sec">Voz de este proyecto</div><div id="vpk"></div>
    <div class="fld"><label>Perfil de voz del proyecto (tiene prioridad sobre lo de arriba)</label><select class="inp" id="vprof"><option value="">— ninguno —</option>${names.map(n=>`<option ${st.voice_profile===n?"selected":""}>${esc(n)}</option>`).join("")}</select></div>
    <div class="sec">Guardar como perfil</div>
    <div class="frow"><input class="inp" id="pname2" placeholder="Nombre del perfil (ej.: Narrador serio)"><button class="btn" id="psave">Guardar</button></div>
    <div class="hint" id="phint">Guarda el motor, voz, modelo, estilo y velocidad de arriba. Si el nombre ya existe, lo actualiza.</div>
    <div class="sec">Mis perfiles</div>
    ${names.length?names.map(n=>{const p=cfg.profiles[n];return `<div class="frow" style="align-items:center;margin:4px 0"><div style="flex:1"><b>${esc(n)}</b> <span class="hint">${esc(p.engine)} · ${esc(p.voice)}${p.model?" · "+esc(p.model):""}</span></div><button class="btn small" data-edit="${esc(n)}">Editar</button><button class="btn small" data-use="${esc(n)}">Usar aquí</button><button class="btn small danger" data-del="${esc(n)}">Borrar</button></div>`}).join(""):`<div class="hint">Aún no tienes perfiles.</div>`}
    <div class="sec">Perfil por defecto según el tipo de video</div>
    ${["map","vector","broll","clip"].map(t=>`<div class="fld"><label>${esc((S.schema.types[t]||{label:t}).label)}</label><select class="inp" data-type="${t}"><option value="">— voz de los ajustes —</option>${names.map(n=>`<option ${cfg.type_defaults[t]===n?"selected":""}>${esc(n)}</option>`).join("")}</select></div>`).join("")}
    <div class="sec">Gemini (API key)</div>
    <div class="fld"><label>API key de Google AI Studio ${cfg.has_key?`<span class="hint">(guardada ${esc(cfg.key_hint)})</span>`:""}</label><div class="frow"><input class="inp" id="gkey" type="password" placeholder="${cfg.has_key?"•••• (escribe para reemplazar)":"Pega aquí tu API key"}"><button class="btn" id="gsave">Guardar</button>${cfg.has_key?`<button class="btn danger" id="gclear">Quitar</button>`:""}</div>
    <div class="hint">Se guarda solo en este equipo (cache/voices.json) y nunca va dentro de tus proyectos.</div></div>
    <div class="sec">API de imágenes y piezas SVG</div>
    <div class="fld"><label>API key para generar piezas e imágenes ${cfg.has_img_key?`<span class="hint">(guardada ${esc(cfg.img_key_hint)})</span>`:`<span class="hint">(vacía: usa la de Gemini de arriba)</span>`}</label><div class="frow"><input class="inp" id="ikey" type="password" placeholder="${cfg.has_img_key?"•••• (escribe para reemplazar)":"Opcional: otra API key"}"><button class="btn" id="isave">Guardar</button>${cfg.has_img_key?`<button class="btn danger" id="iclear">Quitar</button>`:""}</div></div>
    <div class="fld"><label>Modelo</label><div class="frow"><select class="inp" id="imodel"><option value="${esc(cfg.img_model||"")}">${esc(cfg.img_model||"(elige un modelo)")}</option></select><button class="btn" id="imsave">Guardar</button><button class="btn" id="itest">Probar conexión</button><button class="btn" id="imlist">Actualizar lista</button></div><div id="imlst" class="hint"></div>
    <div class="hint">Se usa para pedir piezas nuevas del kit. Es la API, con su propio cupo: no es lo mismo que tu plan de la app de Gemini.</div><div class="hint" id="ires"></div></div>`;
    await voicePicker(b.querySelector("#vpk"),PROJ_VOICE_ST,()=>applyProjVoice(PROJ_VOICE_ST));
    b.querySelector("#vprof").onchange=e=>{S.project.settings.voice_profile=e.target.value||undefined;if(!e.target.value)delete S.project.settings.voice_profile;markDirty()};
    b.querySelector("#psave").onclick=async()=>{const n=b.querySelector("#pname2").value.trim();if(!n)return toast("Ponle nombre al perfil",1);
      try{await jpost("/api/voice_save",{profile_name:n,profile:PROJ_VOICE_ST});toast("Perfil guardado");draw()}catch(e){toast(e.message,1)}};
    b.querySelectorAll("[data-del]").forEach(x=>x.onclick=async()=>{if(!confirm("¿Borrar el perfil «"+x.dataset.del+"»?"))return;await jpost("/api/voice_save",{delete_profile:x.dataset.del});draw()});
    b.querySelectorAll("[data-edit]").forEach(x=>x.onclick=async()=>{const n=x.dataset.edit,p=cfg.profiles[n];
      Object.assign(PROJ_VOICE_ST,{engine:p.engine||"edge",voice:p.voice||"",model:p.model||"",style:p.style||"",rate:p.rate||0});
      await voicePicker(b.querySelector("#vpk"),PROJ_VOICE_ST,()=>{});
      b.querySelector("#pname2").value=n;b.querySelector("#phint").textContent="Editando «"+n+"»: cambia voz, estilo o velocidad arriba y pulsa Guardar para actualizarlo.";
      b.scrollTop=0});
    b.querySelectorAll("[data-use]").forEach(x=>x.onclick=()=>{S.project.settings.voice_profile=x.dataset.use;markDirty();toast("Perfil «"+x.dataset.use+"» activo en este proyecto");draw()});
    b.querySelectorAll("[data-type]").forEach(x=>x.onchange=async()=>{const td={...cfg.type_defaults};if(x.value)td[x.dataset.type]=x.value;else delete td[x.dataset.type];await jpost("/api/voice_save",{type_defaults:td});cfg.type_defaults=td;toast("Guardado")});
    b.querySelector("#gsave").onclick=async()=>{const k=b.querySelector("#gkey").value.trim();if(!k)return;await jpost("/api/voice_save",{gemini_key:k});toast("API key guardada");draw()};
    const gc=b.querySelector("#gclear");if(gc)gc.onclick=async()=>{await jpost("/api/voice_clear_key",{});draw()};
    b.querySelector("#isave").onclick=async()=>{const k=b.querySelector("#ikey").value.trim();if(!k)return;await jpost("/api/voice_save",{img_key:k});toast("API key de imágenes guardada");draw()};
    const ic=b.querySelector("#iclear");if(ic)ic.onclick=async()=>{await jpost("/api/img_clear_key",{});draw()};
    b.querySelector("#imsave").onclick=async()=>{await jpost("/api/voice_save",{img_model:b.querySelector("#imodel").value.trim()});toast("Modelo guardado")};
    const loadModels=async(quiet)=>{const o=b.querySelector("#imlst"),sel=b.querySelector("#imodel");if(!quiet)o.textContent="Consultando…";
      try{const r=await jpost("/api/img_models",{key:b.querySelector("#ikey").value.trim()});if(!r.ok)throw new Error(r.error);
        const cur=cfg.img_model||"";const list=[...new Set([...(cur?[cur]:[]),...r.models])];
        sel.innerHTML=list.map(m=>`<option value="${esc(m)}"${m===cur?" selected":""}>${esc(m)}${m===cur?"  (actual)":""}</option>`).join("");
        o.textContent=r.models.length+" modelos disponibles con tu clave.";}
      catch(e){o.textContent=quiet?"":"✖ "+e.message}};
    b.querySelector("#imlist").onclick=()=>loadModels(false);
    b.querySelector("#imodel").onchange=async e=>{cfg.img_model=e.target.value;await jpost("/api/voice_save",{img_model:e.target.value});toast("Modelo «"+e.target.value+"» guardado")};
    loadModels(true);
    b.querySelector("#itest").onclick=async()=>{const o=b.querySelector("#ires");o.textContent="Probando…";try{const r=await jpost("/api/img_test",{key:b.querySelector("#ikey").value.trim(),model:b.querySelector("#imodel").value});o.textContent=r.ok?"✔ Conectado con "+r.model:"✖ "+r.error}catch(e){o.textContent="✖ "+e.message}};
  };
  window.PROJ_VOICE_ST=PROJ_VOICE();
  await draw();
}

// al abrir un JSON: elegir qué voz usar
async function voicePromptModal(){
  if(!S.project.scenes.some(s=>s.narration))return;
  try{if(localStorage.getItem("vs_no_voice_ask")==="1")return}catch(e){}
  const cfg=await jget("/api/voice_config");const names=Object.keys(cfg.profiles);const st=S.project.settings;
  // si ya hay perfil (del proyecto o por tipo de video) para todas las escenas con voz, no preguntar
  if(st.voice_profile&&cfg.profiles[st.voice_profile])return;
  const tipos=[...new Set(S.project.scenes.filter(s=>s.narration).map(s=>s.type))];
  if(tipos.length&&tipos.every(t=>cfg.profiles[cfg.type_defaults[t]]))return;
  const c=modal(`<div class="mh">¿Con qué voz quieres este proyecto?<span class="sp"></span><button class="x" data-close>✕</button></div>
  <div class="mb"><div class="hint">El proyecto trae ${S.project.scenes.filter(s=>s.narration).length} narraciones. Elige cómo generar la voz:</div>
  <div class="fld"><label>Motor</label><select class="inp" id="vq_e">${ENGINES.map(e=>`<option value="${e[0]}" ${(st.tts_engine||"edge")===e[0]?"selected":""}>${esc(e[1])}</option>`).join("")}</select></div>
  <div class="fld"><label>Perfil de voz</label><select class="inp" id="vq_p"><option value="">— voz de los ajustes —</option>${names.map(n=>`<option ${st.voice_profile===n?"selected":""}>${esc(n)}</option>`).join("")}</select></div>
  <div class="hint" id="vq_w"></div>
  <label class="hint" style="display:block;margin-top:8px"><input type="checkbox" id="vq_no"> No volver a preguntar al abrir un proyecto</label></div>
  <div class="mf"><button class="btn" data-close>Dejar como viene</button><button class="btn" id="vq_more">Más opciones…</button><button class="btn primary" id="vq_ok">Aplicar</button></div>`,"sm");
  const upd=()=>{const e=c.querySelector("#vq_e").value,p=c.querySelector("#vq_p").value;c.querySelector("#vq_w").textContent=(e==="gemini"||(p&&cfg.profiles[p]&&cfg.profiles[p].engine==="gemini"))&&!cfg.has_key?"⚠ Gemini necesita tu API key (botón «Más opciones…»).":""};
  c.querySelector("#vq_e").onchange=upd;c.querySelector("#vq_p").onchange=upd;upd();
  c.querySelector("#vq_no").onchange=e=>{try{localStorage.setItem("vs_no_voice_ask",e.target.checked?"1":"0")}catch(x){}};
  c.querySelector("#vq_ok").onclick=()=>{const e=c.querySelector("#vq_e").value,p=c.querySelector("#vq_p").value;st.tts_engine=e;if(p)st.voice_profile=p;else delete st.voice_profile;markDirty();closeModal();toast("Voz aplicada al proyecto")};
  c.querySelector("#vq_more").onclick=()=>{closeModal();voicesModal()};
}

// ------------------------------------------------------------------ panel de inicio (trabajos y recientes)
let dashTimer=null;
const ago=ts=>{const m=Math.round((Date.now()/1000-ts)/60);return m<1?"ahora":m<60?m+" min":m<1440?Math.round(m/60)+" h":Math.round(m/1440)+" d"};
let TBF="all";
const ESTL={pendiente:"Pendiente",en_cola:"En cola",renderizando:"Renderizando",listo:"Listo",error:"Con error"};
const PUBL={subiendo:"subiendo el video…",enviando:"enviando a Buffer…",enviado:"enviado a Buffer",programado:"programado en Buffer",incierto:"estado incierto: revisa Buffer",error:"error al publicar"};
async function renderDash(){
  const box=$("#dash");if(!box)return;
  try{
    const t=await jget("/api/tablero");S.tb=t;
    const c=t.conteo,q=t.cola,pend=c.pendiente+c.error;
    const order={renderizando:0,en_cola:1,error:2,pendiente:3,listo:4};
    const items=t.items.filter(i=>TBF==="all"||i.estilo===TBF).sort((x,y)=>order[x.estado]-order[y.estado]||(y.fecha>x.fecha?1:y.fecha<x.fecha?-1:0)||x.id.localeCompare(y.id));
    const resume=q.pendientes>0&&!q.corriendo;
    const startLbl=resume?`▶ Continuar cola (${q.pendientes})`:`▶ Iniciar pendientes (${pend})`;
    const main=q.corriendo&&!q.pausada?`<button class="btn" data-tb="pause">⏸ Pausar después del actual</button>`
      :q.corriendo?`<button class="btn" disabled>Pausando… termina el actual</button>`
      :`<button class="btn primary" data-tb="start" ${pend+q.pendientes?"":"disabled"}>${startLbl}</button>`;
    const tabs=[["all","Todos",t.items.length],...t.estilos.map(s=>[s.id,s.label,s.count])].map(([k,l,n])=>`<button class="tab ${TBF===k?"on":""}" data-tab="${k}">${esc(l)} <span>${n}</span></button>`).join("");
    const cards=items.map(it=>{
      const job=q.actual===it.id?q.job:null,pb=it.pub&&it.pub.estado?it.pub:null;
      return `<div class="pcard st-${it.estado}" data-id="${esc(it.id)}">
        <div class="ph"><span class="badge b-${it.estado}">${ESTL[it.estado]}</span><span class="tag">${esc(it.estilo_label)}</span><span class="hint">${esc(it.fecha)}</span></div>
        <b>${esc(it.titulo)}</b>
        <div class="hint">${esc(it.tema||"")}${it.tema?" · ":""}${it.escenas} escenas · ~${it.segundos_aprox} s${it.modificado?" · modificado: hay que renderizar de nuevo":""}</div>
        ${it.estado==="renderizando"&&job?`<div class="bar"><i style="width:${Math.round(job.frac*100)}%"></i></div><div class="hint">${esc(job.stage)} · ${Math.round(job.frac*100)}% · ${fmtT(job.elapsed)}</div>`:""}
        ${it.estado==="en_cola"?`<div class="hint">En cola · lugar ${it.cola_pos||"?"}</div>`:""}
        ${it.estado==="error"?`<div class="hint errtxt">${esc(it.error)}</div>`:""}
        ${pb?`<div class="hint">📤 ${esc(PUBL[pb.estado]||pb.estado)}${pb.canal?" · "+esc(pb.canal):""}${pb.estado==="error"||pb.estado==="incierto"?` · ${esc(pb.detalle||"")}`:""}</div>`:""}
        <div class="pbtn">
          <button class="btn small" data-a="open">Abrir</button>
          ${["pendiente","error","listo"].includes(it.estado)?`<button class="btn small ${it.estado==="listo"?"":"primary"}" data-a="render">${it.estado==="listo"?"Renderizar otra vez":"Renderizar"}</button>`:""}
          ${it.estado==="en_cola"?`<button class="btn small" data-a="unqueue">Quitar de la cola</button>`:""}
          ${it.estado==="listo"?`<button class="btn small primary" data-a="play">▶ Ver</button><button class="btn small" data-a="reveal">Carpeta</button><button class="btn small" data-a="pub">📤 Publicar</button>`:""}
          ${pb&&["incierto","error"].includes(pb.estado)?`<button class="btn small" data-a="forget">Descartar aviso</button>`:""}
        </div></div>`}).join("");
    const html=`<div class="tbar"><div class="tsum"><b>${pend}</b> pendientes · <b>${c.en_cola+c.renderizando}</b> en cola · <b>${c.listo}</b> listos${c.error?` · <span class="errtxt">${c.error} con error</span>`:""}</div>
      <div class="tact">${main}<button class="btn" data-tb="sync">⟳ Buscar proyectos nuevos</button><button class="btn" data-tb="cfg">📤 Publicación</button></div></div>
      ${resume?`<div class="tban">Quedaron ${q.pendientes} proyecto(s) en cola. Pulsa «Continuar cola» para retomarlos.</div>`:""}
      <div class="ttabs">${tabs}</div>
      <div class="pgrid">${cards||`<div class="hint">Aún no hay proyectos aquí. Los que sube la tarea diaria a GitHub aparecen solos; también verás los que abras o guardes.</div>`}</div>`;
    if(box._h===html)return;box._h=html;box.innerHTML=html;
    box.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{TBF=b.dataset.tab;box._h="";renderDash()});
    box.querySelectorAll("[data-tb]").forEach(b=>b.onclick=async()=>{const k=b.dataset.tb;
      try{if(k==="start"){const r=await jpost("/api/cola_iniciar",{});toast(r.error||("Cola iniciada: "+r.encolados+" proyecto(s)"),!!r.error)}
        else if(k==="pause"){await jpost("/api/cola_pausar",{});toast("Se detendrá al terminar el proyecto actual")}
        else if(k==="sync"){b.disabled=true;const r=await jpost("/api/tablero_sync",{});toast(r.error||(r.nuevos?r.nuevos+" proyecto(s) nuevo(s)":"No hay proyectos nuevos"),!!r.error);b.disabled=false}
        else if(k==="cfg")publishModal(null)}catch(e){toast(e.message,1)}box._h="";renderDash()});
    box.querySelectorAll(".pcard [data-a]").forEach(b=>b.onclick=async()=>{const id=b.closest(".pcard").dataset.id,it=t.items.find(x=>x.id===id),a=b.dataset.a;
      try{
        if(a==="open"){if(S.dirty&&!confirm("Hay cambios sin guardar. ¿Abrir otro proyecto?"))return;const p=await jpost("/api/proyecto_abrir",{id});if(p.error)return toast(p.error,1);loadProject(p.project,it.origen==="local"?p.path:null,it.titulo);voicePromptModal()}
        else if(a==="render"){const r=await jpost("/api/cola_iniciar",{ids:[id]});toast("Añadido a la cola ("+r.encolados+")")}
        else if(a==="unqueue")await jpost("/api/cola_quitar",{id});
        else if(a==="play")playModal(it);
        else if(a==="reveal")jpost("/api/reveal",{path:it.video});
        else if(a==="pub")publishModal(it);
        else if(a==="forget"){if(confirm("¿Ya revisaste en Buffer que NO se publicó? Se podrá volver a enviar."))await jpost("/api/publicar_olvidar",{id})}
      }catch(e){toast(e.message,1)}box._h="";renderDash()});
  }catch(e){}
}
function playModal(it){modal(`<div class="mh">${esc(it.titulo)}<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb" style="text-align:center"><video src="/api/video?path=${encodeURIComponent(it.video)}&k=${window.VS_TOKEN}" controls autoplay style="max-height:70vh;max-width:100%;border-radius:10px"></video></div>`,"md")}

async function publishModal(it){
  const stt=await jget("/api/publicar_estado");
  const c=modal(`<div class="mh">${it?"Publicar: "+esc(it.titulo):"Publicación (Buffer)"}<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb" id="pb"></div><div class="mf" id="pf"></div>`,"md");
  const B=c.querySelector("#pb"),F=c.querySelector("#pf");let canales=[],canal=null;
  const chip=(ok,l)=>`<span class="badge ${ok?"b-listo":"b-error"}">${ok?"✔":"✖"} ${l}</span> `;
  const cfg=()=>{
    B.innerHTML=`<p class="hint">Las claves se guardan en el almacén seguro de Windows, nunca en archivos del proyecto. Si ya las configuraste en DiffStudio, se detectan solas.</p>
    <div>${chip(stt.keyring,"Almacén seguro")}${chip(stt.buffer,"Buffer")}${chip(stt.cloudinary_secret,"Cloudinary (secreto)")}${chip(!!stt.api_key,"Cloudinary (API key)")}${chip(!!stt.cloud_name,"Nombre de nube")}</div>
    <div class="fld"><label>Cloudinary · nombre de la nube</label><input type="text" id="cn" value="${esc(stt.cloud_name)}"></div>
    <div class="fld"><label>Cloudinary · API key ${stt.api_key?"("+esc(stt.api_key)+" guardada; déjalo vacío para conservarla)":""}</label><input type="text" id="ck" autocomplete="off"></div>
    <div class="fld"><label>Cloudinary · API secret ${stt.cloudinary_secret?"(guardado)":""}</label><input type="password" id="cs" autocomplete="off" placeholder="${stt.cloudinary_secret?"•••••• (vacío = conservar)":""}"></div>
    <div class="fld"><label>Buffer · clave personal ${stt.buffer?"(guardada)":""}</label><input type="password" id="bt" autocomplete="off" placeholder="${stt.buffer?"•••••• (vacío = conservar)":""}"></div>
    <div class="fld"><label>Canal de Buffer</label><select id="ch"><option value="">— carga los canales —</option></select><div class="hint" id="chh"></div></div>`;
    F.innerHTML=`<button class="btn" id="lc">Cargar canales</button><span style="flex:1"></span><button class="btn" data-close>Cerrar</button><button class="btn primary" id="sv">Guardar${it?" y continuar":""}</button>`;
    const sel=B.querySelector("#ch"),h=B.querySelector("#chh");
    const fill=()=>{sel.innerHTML='<option value="">— elige un canal —</option>'+canales.map(x=>`<option value="${esc(x.id)}" ${x.soportado?"":"disabled"} ${x.id===stt.channel_id?"selected":""}>${esc(x.nombre)} · ${esc(x.servicio)}${x.soportado?"":" (aún no verificado)"}</option>`).join("")};
    if(stt.channel_id){sel.innerHTML=`<option value="${esc(stt.channel_id)}" selected>${esc(stt.channel_name||stt.channel_id)}</option>`}
    F.querySelector("#lc").onclick=async()=>{await save(true);const r=await jpost("/api/publicar_canales",{});if(r.error)return toast(r.error,1);canales=r.canales;fill();h.textContent=canales.length?"Solo TikTok está verificado por ahora; los demás canales aparecen pero no se envían.":"Buffer no devolvió canales."};
    const save=async(quiet)=>{const body={cloud_name:B.querySelector("#cn").value.trim(),buffer_token:B.querySelector("#bt").value.trim(),cloudinary_secret:B.querySelector("#cs").value.trim()};
      const k=B.querySelector("#ck").value.trim();if(k)body.api_key=k;const v=sel.value;if(v){const ch=canales.find(x=>x.id===v);body.channel_id=v;if(ch)body.channel_name=ch.nombre}
      const r=await jpost("/api/publicar_guardar",body);if(r.error){toast(r.error,1);throw new Error(r.error)}Object.assign(stt,r);if(!quiet)toast("Guardado");return r};
    F.querySelector("#sv").onclick=async()=>{try{await save();if(it&&stt.listo)send();else if(!it)closeModal()}catch(e){}};
  };
  const send=()=>{
    const tags=(it.hashtags||[]).map(h=>"#"+String(h).replace(/^#/,"").replace(/\s/g,"")).join(" ");
    const base=[it.titulo,it.descripcion,tags].filter(Boolean).join("\n\n");
    B.innerHTML=`<div class="fld"><label>Canal</label><div><b>${esc(stt.channel_name||stt.channel_id)}</b> <button class="btn small" id="cc">Cambiar</button></div></div>
    <div class="fld"><label>Descripción de la publicación</label><textarea id="tx" rows="6">${esc(base)}</textarea></div>
    <div class="fld"><label>¿Cuándo?</label><label class="chk"><input type="radio" name="w" value="now" checked><span>Publicar ahora</span></label><label class="chk"><input type="radio" name="w" value="later"><span>Programar</span></label><input type="datetime-local" id="dt" disabled></div>
    <div class="hint">Todavía no se envía nada: primero verás un resumen para confirmar.</div>`;
    F.innerHTML=`<button class="btn" data-close>Cancelar</button><span style="flex:1"></span><button class="btn primary" id="rv">Revisar y confirmar</button>`;
    B.querySelector("#cc").onclick=cfg;
    B.querySelectorAll("[name=w]").forEach(r=>r.onchange=()=>{B.querySelector("#dt").disabled=B.querySelector("[name=w]:checked").value!=="later"});
    F.querySelector("#rv").onclick=async()=>{
      let sched=null;if(B.querySelector("[name=w]:checked").value==="later"){const v=B.querySelector("#dt").value;if(!v)return toast("Elige la fecha y hora",1);sched=new Date(v).toISOString()}
      const ch=(canales.find(x=>x.id===stt.channel_id)||{});
      const r=await jpost("/api/publicar_preparar",{id:it.id,channel_id:stt.channel_id,channel_name:stt.channel_name,service:ch.servicio||"tiktok",text:B.querySelector("#tx").value,scheduled:sched});
      if(r.error)return toast(r.error,1);confirmar(r)};
  };
  const confirmar=r=>{const s=r.resumen;
    B.innerHTML=`<p><b>Revisa antes de enviar:</b></p><div class="dcard"><b>${esc(s.titulo)}</b><div class="hint">Canal: ${esc(s.canal)} (${esc(s.servicio)}) · ${s.mb} MB</div><div class="hint">${s.programado?"Programado para "+esc(s.programado):"Se publica AHORA"}</div><pre class="code" style="white-space:pre-wrap;margin-top:8px">${esc(s.texto)}</pre></div>
    <p class="hint">El video se sube a Cloudinary y Buffer lo publica en TikTok. Una vez enviado no se puede deshacer desde aquí.</p>`;
    F.innerHTML=`<button class="btn" data-close>Cancelar</button><span style="flex:1"></span><button class="btn" id="bk">Volver</button><button class="btn primary" id="go">✔ Confirmar y enviar</button>`;
    F.querySelector("#bk").onclick=send;
    F.querySelector("#go").onclick=async()=>{F.querySelector("#go").disabled=true;
      const j=await jpost("/api/publicar_confirmar",{confirm:r.confirm});if(j.error){toast(j.error,1);return send()}
      B.innerHTML=`<div class="bar"><i id="pbar" style="width:5%"></i></div><div class="hint" id="pst">Enviando…</div>`;F.innerHTML="";
      const done=await poll(j.id,x=>{const b=B.querySelector("#pbar");if(b)b.style.width=Math.max(5,x.frac*100)+"%";const t=B.querySelector("#pst");if(t)t.textContent=x.stage});
      if(done.state==="done"){B.innerHTML=`<p>✔ <b>${done.result.estado==="programado"?"Programado":"Enviado"} a Buffer.</b></p><div class="hint">ID: ${esc(done.result.buffer_id)}. Comprueba la publicación en tu panel de Buffer y en la red.</div>`;F.innerHTML=`<button class="btn primary" data-close>Listo</button>`}
      else{B.innerHTML=`<p>✖ No se completó el envío.</p><div class="hint errtxt">${esc(done.error||"error")}</div><div class="hint">Si dice «incierto», revisa Buffer antes de reintentar para no duplicar.</div>`;F.innerHTML=`<button class="btn primary" data-close>Cerrar</button>`}
      renderDash()}};
  if(it&&stt.listo)send();else cfg();
}
function startDash(){clearInterval(dashTimer);renderDash();dashTimer=setInterval(()=>{if($("#empty").hidden){clearInterval(dashTimer);return}renderDash()},3000)}

function aiModal(){
  const c=modal(`<div class="mh">Animación con IA<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb">
  <p class="hint">Pega tu guion y una IA lo convierte en escenas animadas con los personajes y fondos del programa. Con una clave gratuita de Gemini se hace aquí mismo; si prefieres otra IA, copia las instrucciones, pégalas junto a tu guion y pega abajo el JSON que te devuelva.</p>
  <div class="fld"><label>Estilo</label><select id="stl"><option value="">(sin estilo)</option></select></div>
  <div class="fld"><label>Guion</label><textarea id="sc" rows="7" placeholder="¿Por qué huele a pescado? La culpable es la trimetilamina…"></textarea></div>
  <div class="fld"><label>Clave de Gemini (gratis en aistudio.google.com; se guarda solo en este equipo)</label><input type="text" id="gk"></div>
  <div class="frow" style="margin:6px 0 14px"><button class="btn small" id="cp">Copiar instrucciones para otra IA</button> <button class="btn small" id="cg">Copiar prompt para escribir el guion</button> <button class="btn small" id="ck">Copiar prompt de IA diaria (kit SVG)</button></div>
  <div class="fld"><label>…o pega aquí el JSON de escenas que devolvió otra IA</label><textarea id="js" rows="4" class="code" style="min-height:90px"></textarea></div>
  <div class="hint" id="st"></div></div>
  <div class="mf"><button class="btn" data-close>Cancelar</button><button class="btn" id="add">Añadir JSON pegado</button><button class="btn primary" id="go">Generar con Gemini</button></div>`,"md");
  const gk=c.querySelector("#gk");try{gk.value=localStorage.getItem("vs_gk")||""}catch(e){}
  const stl=c.querySelector("#stl");jget("/api/styles?tipo=vector").then(r=>{(r.styles||[]).forEach(x=>{const o=document.createElement("option");o.value=x.id;o.textContent=x.nombre;stl.appendChild(o)});try{stl.value=localStorage.getItem("vs_stl")||(r.styles[0]||{}).id||""}catch(e){}}).catch(()=>{});
  c.querySelector("#cg").onclick=async()=>{const r=await jget("/api/script_prompt?style="+encodeURIComponent(stl.value)+"&tema="+encodeURIComponent(c.querySelector("#sc").value.slice(0,300)));try{await navigator.clipboard.writeText(r.prompt);toast("Prompt de guion copiado")}catch(e){c.querySelector("#js").value=r.prompt}};
  const addScenes=(sc)=>{if(!Array.isArray(sc))sc=sc.scenes||[sc];sc.forEach(x=>x.type="vector");const first=S.project.scenes.length;S.project.scenes.push(...sc);S.durs={};S.sel=first;markDirty();closeModal();renderList();renderForm();refresh();toast(sc.length+" escenas añadidas")};
  c.querySelector("#ck").onclick=async()=>{const r=await jget("/api/kit_prompt?style="+encodeURIComponent(stl.value));try{await navigator.clipboard.writeText(r.prompt);toast("Prompt de IA diaria copiado")}catch(e){c.querySelector("#js").value=r.prompt}};
  c.querySelector("#cp").onclick=async()=>{const r=await jget("/api/ai_prompt?style="+encodeURIComponent(stl.value));try{await navigator.clipboard.writeText(r.prompt);toast("Instrucciones copiadas")}catch(e){c.querySelector("#js").value=r.prompt}};
  c.querySelector("#add").onclick=()=>{try{addScenes(JSON.parse(c.querySelector("#js").value))}catch(e){toast("JSON no válido: "+e.message,1)}};
  c.querySelector("#go").onclick=async()=>{const script=c.querySelector("#sc").value.trim(),key=gk.value.trim();if(!script||!key)return toast("Falta el guion o la clave",1);
    try{localStorage.setItem("vs_gk",key)}catch(e){}
    const go=c.querySelector("#go");go.disabled=true;c.querySelector("#st").textContent="Generando escenas… puede tardar un minuto";
    try{const r=await (()=>{try{localStorage.setItem("vs_stl",stl.value)}catch(e){}return jpost("/api/vector_ai",{script,key,style:stl.value})})();addScenes(r.scenes)}catch(e){toast(e.message,1);go.disabled=false;c.querySelector("#st").textContent=""}}}

function addModal(){const ty=S.schema.types;
  const c=modal(`<div class="mh">Añadir escena<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb"><div class="grid">${S.schema.order.map(k=>`<div class="tcard" data-add="${k}"><div class="ic">${icon(ty[k].icon,22)}</div><b>${esc(ty[k].label)}</b><span>${esc(ty[k].desc)}</span></div>`).join("")}</div></div>`,"md");
  c.querySelectorAll("[data-add]").forEach(e=>e.onclick=()=>{closeModal();addScene(e.dataset.add)})}

async function exportModal(){
  if(!S.project.scenes.length)return toast("Añade al menos una escena",1);
  let out=(await jget("/api/default_out?name="+encodeURIComponent(S.name))).path;
  const c=modal(`<div class="mh">Exportar video<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb">
  <div class="fld"><label>Guardar en</label><div class="frow"><input class="inp" id="o" value="${esc(out)}"><button class="btn small" id="pk">Cambiar…</button></div></div>
  <p class="hint">Se exporta en 1080×1920, ${S.project.settings.fps||30} fps. Puedes cambiar calidad, voz y música en Ajustes.</p>
  <div class="bar" id="bar" hidden><i></i></div><div class="hint" id="st"></div><div class="warnlist" id="wl"></div></div>
  <div class="mf"><button class="btn" id="cancel" data-close>Cerrar</button><button class="btn primary" id="go">Renderizar</button></div>`,"md");
  c.querySelector("#pk").onclick=async()=>{try{const r=await jpost("/api/pick",{kind:"save",filter:"mp4",initial:c.querySelector("#o").value});if(r.paths.length)c.querySelector("#o").value=r.paths[0]}catch(e){toast(e.message,1)}};
  c.querySelector("#go").onclick=async()=>{const go=c.querySelector("#go"),cancel=c.querySelector("#cancel");go.disabled=true;c.dataset.lock=1;c.querySelector("#bar").hidden=false;
    out=c.querySelector("#o").value;const {id}=await jpost("/api/render",{project:S.project,path:S.path,out,name:S.name});
    cancel.textContent="Cancelar render";cancel.onclick=async()=>{await jpost("/api/cancel",{id})};
    const j=await poll(id,j=>{c.querySelector("#bar i").style.width=(j.frac*100)+"%";c.querySelector("#st").textContent=`${j.stage} · ${Math.round(j.frac*100)}% · ${fmtT(j.elapsed)}`});
    delete c.dataset.lock;
    if(j.state==="done"){c.querySelector("#st").textContent="✔ Listo: "+out;const w=(j.result&&j.result.warnings)||[];c.querySelector("#wl").innerHTML=w.map(x=>"⚠ "+esc(x)).join("<br>");
      c.querySelector(".mf").innerHTML=`<button class="btn" data-close>Cerrar</button><button class="btn" id="sh">Mostrar en carpeta</button><button class="btn primary" id="pl">Reproducir</button>`;
      c.querySelector("[data-close]").onclick=closeModal;c.querySelector("#sh").onclick=()=>jpost("/api/reveal",{path:out});c.querySelector("#pl").onclick=()=>jpost("/api/reveal",{path:out,play:true})}
    else{c.querySelector("#st").textContent=j.state==="cancelled"?"Cancelado.":"Error: "+j.error;go.disabled=false;cancel.textContent="Cerrar";cancel.onclick=closeModal}}}

async function saveProject(){
  try{const r=await jpost("/api/save_project",{project:S.project,path:S.path,suggest:S.name+".json"});
    if(r.path){S.path=r.path;markDirty(false);toast("Proyecto guardado")}}catch(e){toast(e.message,1)}}
async function openProject(){try{const r=await jpost("/api/open_project",{});if(r.project){loadProject(r.project,r.path);voicePromptModal()}}catch(e){toast(e.message,1)}}

async function piecesModal(){
  const c=modal(`<div class="mh">🧩 Piezas SVG con Gemini<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb" id="pb"></div><div class="mf"><button class="btn primary" data-close>Listo</button></div>`,"md");
  const b=c.querySelector("#pb");
  const sugg=[];(S.project.scenes||[]).forEach(sc=>(sc.piezas_nuevas||[]).forEach(p=>sugg.push(p)));
  const prev=svg=>"data:image/svg+xml;utf8,"+encodeURIComponent(svg.replace(/\{\{\s*[\w-]+\s*(?:\|([^}]*))?\}\}/g,(m,d)=>d||"0"));
  const draw=async()=>{
    const r=await jget("/api/kit_pending");
    b.innerHTML=`<div class="hint">Describe la pieza, Gemini la dibuja y TÚ decides si entra al kit. Usa tu API key de «Voces → API de imágenes y piezas SVG».</div>
    ${sugg.length?`<div class="sec">Piezas que pide este proyecto</div>${sugg.map((p,i)=>`<div class="frow" style="align-items:center;margin:3px 0"><div style="flex:1"><b>${esc(p.id)}</b> <span class="hint">${esc(p.descripcion)}</span></div><button class="btn small" data-sg="${i}">Usar</button></div>`).join("")}`:""}
    <div class="sec">Pieza nueva</div>
    <div class="fld"><label>Nombre corto (opcional)</label><input class="inp" id="pg_id" placeholder="ej.: estomago"></div>
    <div class="fld"><label>¿Qué debe dibujar?</label><textarea class="inp" id="pg_d" rows="3" placeholder="Ej.: estómago humano translúcido visto de frente, con pared muscular y pliegues internos, tonos rosados"></textarea></div>
    <div class="frow"><button class="btn primary" id="pg_go">Generar</button><span class="hint" id="pg_st"></span></div>
    <div class="sec">Pendientes de aprobar</div>
    ${r.pendientes.length?r.pendientes.map(p=>`<div class="card" style="padding:10px;margin:8px 0;border:1px solid var(--line,#333);border-radius:10px"><div class="frow" style="gap:12px;align-items:flex-start">
      <div style="width:170px;height:200px;background:#10131a;border-radius:8px;display:flex;align-items:center;justify-content:center"><img src="${prev(p.svg)}" style="max-width:100%;max-height:100%"></div>
      <div style="flex:1"><div class="fld"><label>Nombre</label><input class="inp" data-n="${esc(p.id)}" value="${esc(p.id.replace(/_/g," "))}"></div>
      <div class="fld"><label>Para qué sirve (lo lee la IA diaria)</label><input class="inp" data-u="${esc(p.id)}" value="${esc(p.descripcion)}"></div>
      <div class="hint">Partes: ${esc(p.grupos.join(", ")||"una sola pieza")}</div>
      <div class="frow" style="margin-top:6px"><button class="btn primary small" data-ok="${esc(p.id)}">Aprobar y añadir al kit</button><button class="btn small danger" data-no="${esc(p.id)}">Descartar</button></div></div></div></div>`).join(""):`<div class="hint">Nada pendiente.</div>`}`;
    b.querySelectorAll("[data-sg]").forEach(x=>x.onclick=()=>{const p=sugg[+x.dataset.sg];b.querySelector("#pg_id").value=p.id||"";b.querySelector("#pg_d").value=p.descripcion||""});
    b.querySelector("#pg_go").onclick=async()=>{const st=b.querySelector("#pg_st");st.textContent="Dibujando… (puede tardar un minuto)";
      try{const r=await jpost("/api/kit_generate",{id:b.querySelector("#pg_id").value,descripcion:b.querySelector("#pg_d").value});
        if(!r.ok)throw new Error(r.error);draw()}catch(e){st.textContent="";toast(e.message,1)}};
    b.querySelectorAll("[data-ok]").forEach(x=>x.onclick=async()=>{const id=x.dataset.ok;
      const r=await jpost("/api/kit_approve",{id,nombre:b.querySelector(`[data-n="${id}"]`).value,usos:b.querySelector(`[data-u="${id}"]`).value,descripcion:b.querySelector(`[data-u="${id}"]`).value});
      if(!r.ok)return toast(r.error,1);toast("Pieza «"+r.id+"» añadida al kit");draw()});
    b.querySelectorAll("[data-no]").forEach(x=>x.onclick=async()=>{await jpost("/api/kit_reject",{id:x.dataset.no});draw()});
  };
  await draw();
}

function act(a){
  if(a==="new"){if(S.dirty&&!confirm("Hay cambios sin guardar. ¿Empezar un proyecto nuevo?"))return;loadProject({settings:{theme:"oscuro"},scenes:[]},null)}
  else if(a==="home"){if(S.dirty&&!confirm("Volver al menú principal. Los cambios sin guardar se perderán. ¿Continuar?"))return;loadProject({settings:{...S.project.settings},scenes:[]},null)}
  else if(a==="update")checkUpdates(true);else if(a==="voices")voicesModal();else if(a==="pieces")piecesModal();
  else if(a==="open")openProject();else if(a==="save")saveProject();else if(a==="examples")examplesModal();
  else if(a==="settings")settingsModal();else if(a==="export")exportModal();else if(a==="add")addModal();
  else if(a==="script")scriptModal();else if(a==="ai")aiModal();else if(a==="autoclip")autoclipModal()}
$$("[data-act]").forEach(b=>b.onclick=()=>act(b.dataset.act));
$("#pname").oninput=e=>{S.name=e.target.value;markDirty()};
document.addEventListener("keydown",e=>{if(e.ctrlKey&&e.key==="s"){e.preventDefault();saveProject()}if(e.key==="Escape"&&!$("#card").dataset.lock)closeModal()});
window.addEventListener("beforeunload",e=>{if(S.dirty){e.preventDefault();e.returnValue=""}});

(async()=>{
  S.schema=await jget("/api/schema");S.project.settings={...S.schema.defaults};
  renderList();setInterval(()=>api("/api/ping").catch(()=>{}),5000);api("/api/ping").catch(()=>{});
  checkUpdates(false);
  if(location.hash==="#examples")examplesModal();
})();
