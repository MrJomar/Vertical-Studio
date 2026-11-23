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
  const empty=!sc.length;$("#empty").hidden=!empty;$("#player").hidden=empty;$(".insp").style.visibility=empty?"hidden":"visible";
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
  E.innerHTML=`<h1>¿Qué video vamos a hacer hoy?</h1><p>Elige un tipo para empezar desde cero, o abre un ejemplo ya armado para ver cómo queda.</p>
  <div class="grid">${S.schema.order.map(k=>`<div class="tcard" data-add="${k}"><div class="ic">${icon(ty[k].icon,22)}</div><b>${esc(ty[k].label)}</b><span>${esc(ty[k].desc)}</span></div>`).join("")}</div>
  <div style="margin-top:26px;display:flex;gap:10px"><button class="btn primary" data-act="examples">✨ Ver ejemplos de cada tipo</button><button class="btn" data-act="autoclip">Sacar clips de un video largo</button></div>`;
  E.querySelectorAll("[data-add]").forEach(e=>e.onclick=()=>addScene(e.dataset.add));
  E.querySelectorAll("[data-act]").forEach(e=>e.onclick=()=>act(e.dataset.act));
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
  const st=S.project.settings;const c=modal(`<div class="mh">Ajustes del proyecto<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb" id="sb"></div><div class="mf"><select id="pre" class="inp" style="width:170px"><option value="">Plantillas…</option></select><button class="btn small" id="pl">Aplicar</button><button class="btn small" id="ps">Guardar actual</button><span class="hint" style="flex:1">${S.schema.nvenc?"✔ GPU NVIDIA detectada (NVENC)":"GPU NVENC no detectada: se usará la CPU"}</span><button class="btn primary" data-close>Listo</button></div>`,"md");
  const b=c.querySelector("#sb");
  S.schema.settings.forEach(g=>{const h=document.createElement("div");h.className="sec";h.textContent=g.group;b.appendChild(h);
    g.fields.forEach(f=>{const ff={...f};if(f.kind==="file"&&f.key==="music"){}b.appendChild(fieldEl(ff,st,()=>{markDirty();S.durs={};clearTimeout(settingsModal.t);settingsModal.t=setTimeout(refresh,300)},true))})});
  (async()=>{const u=await jget("/api/update_check");const h=document.createElement("div");h.className="sec";h.textContent="Actualizaciones";b.appendChild(h);
    const w=document.createElement("div");w.innerHTML=`<label class="chk"><input type="checkbox" id="uc" ${u.enabled?"checked":""}><span>Buscar actualizaciones al iniciar</span></label>
    <div class="fld"><label>Repositorio de GitHub</label><input type="text" id="ur" value="${esc(u.repo)}"></div>
    <div class="fld"><label>Token de solo lectura (solo si el repositorio es privado; se guarda en este equipo)</label><input type="text" id="ut" placeholder="${u.has_token?"(guardado)":"github_pat_…"}"></div>
    <div class="frow"><button class="btn small" id="ub">Buscar ahora</button><span class="hint" id="us" style="align-self:center">Versión instalada: ${esc(u.current)}</span></div>`;b.appendChild(w);
    const save=async()=>{const body={check_updates:w.querySelector("#uc").checked,update_repo:w.querySelector("#ur").value.trim()};const t=w.querySelector("#ut").value.trim();if(t)body.update_token=t;return jpost("/api/update_config",body)};
    w.querySelector("#ub").onclick=async()=>{const r=await save();w.querySelector("#us").textContent=r.error?r.error:(r.newer?"Hay una versión nueva: "+r.latest:"Estás al día ("+r.current+")")};
    w.querySelector("#uc").onchange=save})();
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

async function checkUpdates(manual){
  try{const u=await jget("/api/update_check");const box=$("#upd");
    if(u.newer){box.innerHTML=`<b>🔔 Hay una versión nueva: ${esc(u.latest)}</b><div class="hint">Tienes la ${esc(u.current)}.${u.notes?" Novedad: "+esc(u.notes):""}</div><div class="frow"><button class="btn small primary" id="uo">Abrir repositorio</button><button class="btn small" id="ux">Luego</button></div>`;box.hidden=false;
      $("#uo").onclick=()=>{jpost("/api/open_url",{url:u.url});box.hidden=true};$("#ux").onclick=()=>box.hidden=true}
    else if(manual){toast(u.error?u.error:"Ya tienes la última versión ("+u.current+")",!!u.error)}
    return u}catch(e){if(manual)toast("No se pudo comprobar: "+e.message,1)}}

function aiModal(){
  const c=modal(`<div class="mh">Animación con IA<span class="sp"></span><button class="x" data-close>✕</button></div><div class="mb">
  <p class="hint">Pega tu guion y una IA lo convierte en escenas animadas con los personajes y fondos del programa. Con una clave gratuita de Gemini se hace aquí mismo; si prefieres otra IA, copia las instrucciones, pégalas junto a tu guion y pega abajo el JSON que te devuelva.</p>
  <div class="fld"><label>Guion</label><textarea id="sc" rows="7" placeholder="¿Por qué huele a pescado? La culpable es la trimetilamina…"></textarea></div>
  <div class="fld"><label>Clave de Gemini (gratis en aistudio.google.com; se guarda solo en este equipo)</label><input type="text" id="gk"></div>
  <div class="frow" style="margin:6px 0 14px"><button class="btn small" id="cp">Copiar instrucciones para otra IA</button></div>
  <div class="fld"><label>…o pega aquí el JSON de escenas que devolvió otra IA</label><textarea id="js" rows="4" class="code" style="min-height:90px"></textarea></div>
  <div class="hint" id="st"></div></div>
  <div class="mf"><button class="btn" data-close>Cancelar</button><button class="btn" id="add">Añadir JSON pegado</button><button class="btn primary" id="go">Generar con Gemini</button></div>`,"md");
  const gk=c.querySelector("#gk");try{gk.value=localStorage.getItem("vs_gk")||""}catch(e){}
  const addScenes=(sc)=>{if(!Array.isArray(sc))sc=sc.scenes||[sc];sc.forEach(x=>x.type="vector");const first=S.project.scenes.length;S.project.scenes.push(...sc);S.durs={};S.sel=first;markDirty();closeModal();renderList();renderForm();refresh();toast(sc.length+" escenas añadidas")};
  c.querySelector("#cp").onclick=async()=>{const r=await jget("/api/ai_prompt");try{await navigator.clipboard.writeText(r.prompt);toast("Instrucciones copiadas")}catch(e){c.querySelector("#js").value=r.prompt}};
  c.querySelector("#add").onclick=()=>{try{addScenes(JSON.parse(c.querySelector("#js").value))}catch(e){toast("JSON no válido: "+e.message,1)}};
  c.querySelector("#go").onclick=async()=>{const script=c.querySelector("#sc").value.trim(),key=gk.value.trim();if(!script||!key)return toast("Falta el guion o la clave",1);
    try{localStorage.setItem("vs_gk",key)}catch(e){}
    const go=c.querySelector("#go");go.disabled=true;c.querySelector("#st").textContent="Generando escenas… puede tardar un minuto";
    try{const r=await jpost("/api/vector_ai",{script,key});addScenes(r.scenes)}catch(e){toast(e.message,1);go.disabled=false;c.querySelector("#st").textContent=""}}}

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
    out=c.querySelector("#o").value;const {id}=await jpost("/api/render",{project:S.project,path:S.path,out});
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
async function openProject(){try{const r=await jpost("/api/open_project",{});if(r.project)loadProject(r.project,r.path)}catch(e){toast(e.message,1)}}

function act(a){
  if(a==="new"){if(S.dirty&&!confirm("Hay cambios sin guardar. ¿Empezar un proyecto nuevo?"))return;loadProject({settings:{theme:"oscuro"},scenes:[]},null)}
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
