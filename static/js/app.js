/* ============================================================
   Transmission Console — frontend logic
   Shared helpers + a tiny per-page router keyed on body[data-page].
   ============================================================ */

const api = {
  async get(url){ const r = await fetch(url); return r.json(); },
  async post(url, body, isForm){
    const opts = { method:"POST" };
    if (isForm){ opts.body = body; }
    else { opts.headers = {"Content-Type":"application/json"}; opts.body = JSON.stringify(body||{}); }
    const r = await fetch(url, opts); return { ok:r.ok, status:r.status, data: await r.json().catch(()=>({})) };
  },
  async put(url, body){
    const r = await fetch(url,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    return { ok:r.ok, data: await r.json().catch(()=>({})) };
  },
  async del(url){ const r = await fetch(url,{method:"DELETE"}); return { ok:r.ok, data: await r.json().catch(()=>({})) }; }
};

function toast(msg, isErr){
  const el = document.getElementById("toast");
  if(!el) return;
  el.textContent = msg; el.className = "toast show" + (isErr ? " err" : "");
  setTimeout(()=> el.className = "toast", 3200);
}

function fmtTime(iso){
  if(!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString([], {month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"});
}
function pill(status){ return `<span class="pill ${status}">${status}</span>`; }
function esc(s){ return (s||"").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

/* ---- transmission bar (all pages) ---- */
async function refreshTransmitBar(){
  try{
    const s = await api.get("/api/dashboard/summary");
    const sc = s.scheduler || {};
    const dot = document.getElementById("tx-dot");
    const state = document.getElementById("tx-state");
    const next = document.getElementById("tx-next");
    const mode = document.getElementById("tx-mode");
    if(sc.running){ dot.className="dot live"; state.textContent="ON AIR"; }
    else { dot.className="dot paused"; state.textContent="PAUSED"; }
    next.textContent = sc.next_run ? fmtTime(sc.next_run) : "none queued";
    if(mode) mode.textContent = "DB: " + ((s.db_mode||"").toUpperCase() || (window.__dbmode||"—"));
  }catch(e){ /* not logged in yet, ignore */ }
}

/* ---- nav highlight ---- */
function markNav(){
  const page = document.body.dataset.page;
  document.querySelectorAll(".nav a").forEach(a=>{
    if(a.dataset.nav === page) a.classList.add("active");
  });
}

/* =====================  DASHBOARD  ===================== */
async function initDashboard(){
  const s = await api.get("/api/dashboard/summary");
  document.getElementById("t-total").textContent = s.total;
  document.getElementById("t-queue").textContent = s.in_queue;
  document.getElementById("t-pub").textContent = s.published;
  document.getElementById("t-storage").textContent = s.storage_human;

  document.querySelectorAll(".tile").forEach(tile=>{
    tile.addEventListener("click", async ()=>{
      document.querySelectorAll(".tile").forEach(t=>t.classList.remove("active"));
      tile.classList.add("active");
      const key = tile.dataset.tile;
      const rows = await api.get("/api/dashboard/tile/"+key);
      const panel = document.getElementById("tile-panel");
      panel.style.display = "block";
      document.getElementById("tile-panel-title").innerHTML =
        `${tile.querySelector(".label").textContent} <span class="tag">${rows.length} ITEMS</span>`;
      document.getElementById("tile-panel-body").innerHTML = videoTable(rows);
    });
  });

  loadEngagement();
  document.getElementById("refresh-engagement").addEventListener("click", async (e)=>{
    e.target.disabled = true; e.target.textContent = "Refreshing…";
    const r = await api.post("/api/dashboard/engagement/refresh", {});
    e.target.disabled = false; e.target.textContent = "Refresh";
    if(r.ok){ toast(`Updated ${r.data.updated} videos`); loadEngagement(); }
    else toast(r.data.error || "Refresh failed", true);
  });

  loadRecent();
  let actPage = 0;
  async function loadActivity(){
    const a = await api.get("/api/dashboard/activity?page="+actPage);
    document.getElementById("activity-list").innerHTML = a.items.length
      ? a.items.map(i=>`<div class="log-item">
          <span class="log-time">${fmtTime(i.timestamp)}</span>
          <span><span class="log-actor">${esc(i.actor)}</span> — ${esc(i.action)}
          ${i.detail?`<span class="muted">· ${esc(i.detail)}</span>`:""}</span></div>`).join("")
      : `<div class="empty">No activity yet.</div>`;
    document.getElementById("act-page").textContent = "page " + (a.page+1);
    document.getElementById("act-prev").disabled = !a.has_prev;
    document.getElementById("act-next").disabled = !a.has_next;
  }
  document.getElementById("act-prev").addEventListener("click", ()=>{ actPage=Math.max(0,actPage-1); loadActivity(); });
  document.getElementById("act-next").addEventListener("click", ()=>{ actPage++; loadActivity(); });
  loadActivity();
}

async function loadEngagement(){
  const e = await api.get("/api/dashboard/engagement");
  const t = e.totals;
  document.getElementById("engagement-totals").innerHTML = `
    <div class="stat"><b>${t.views}</b><small>Views</small></div>
    <div class="stat"><b>${t.likes}</b><small>Likes</small></div>
    <div class="stat"><b>${t.comments}</b><small>Comments</small></div>
    <div class="stat"><b>${t.watch}</b><small>Watch min</small></div>`;
  document.getElementById("engagement-list").innerHTML = e.videos.length
    ? `<table><thead><tr><th>Video</th><th class="right">Views</th><th class="right">Likes</th><th class="right">Comments</th></tr></thead>
       <tbody>${e.videos.map(v=>`<tr>
         <td class="row-title">${esc(v.title)}</td>
         <td class="right mono">${v.views}</td><td class="right mono">${v.likes}</td>
         <td class="right mono">${v.comments}</td></tr>`).join("")}</tbody></table>`
    : `<div class="empty">No published videos yet.</div>`;
}

async function loadRecent(){
  const rows = await api.get("/api/dashboard/recent");
  document.getElementById("recent-list").innerHTML = videoTable(rows);
}

function videoTable(rows){
  if(!rows.length) return `<div class="empty">Nothing here yet.</div>`;
  return `<table><thead><tr><th>Title</th><th>Status</th><th>Scheduled</th><th></th></tr></thead>
    <tbody>${rows.map(v=>`<tr>
      <td class="row-title">${esc(v.title)}</td>
      <td>${pill(v.status)}</td>
      <td class="mono muted">${v.scheduled_time?fmtTime(v.scheduled_time):"—"}</td>
      <td class="right">${v.youtube_video_id?`<a class="mono" style="color:var(--cyan)" target="_blank" href="https://youtu.be/${v.youtube_video_id}">watch ↗</a>`:""}</td>
    </tr>`).join("")}</tbody></table>`;
}

/* =====================  VIDEOS  ===================== */
async function initVideos(){
  let tab = "all";
  async function load(){
    const rows = await api.get("/api/videos?tab="+tab);
    const el = document.getElementById("video-table");
    if(!rows.length){ el.innerHTML = `<div class="empty">No videos in “${tab}”.</div>`; return; }
    el.innerHTML = `<table><thead><tr><th>Title</th><th>Status</th><th>Privacy</th><th>Scheduled</th><th class="right">Actions</th></tr></thead>
      <tbody>${rows.map(v=>rowHtml(v)).join("")}</tbody></table>`;
    el.querySelectorAll("[data-edit]").forEach(b=> b.onclick=()=> openEdit(rows.find(r=>r.id==b.dataset.edit)));
    el.querySelectorAll("[data-del]").forEach(b=> b.onclick=()=> delVideo(b.dataset.del));
    el.querySelectorAll("[data-log]").forEach(b=> b.onclick=()=>{
      const box = document.getElementById("log-"+b.dataset.log);
      box.style.display = box.style.display==="none" ? "block":"none";
    });
  }
  function rowHtml(v){
    let extra = "";
    if(tab==="failed" && v.failure){
      extra = `<tr><td colspan="5"><div id="log-${v.id}" style="display:none">
        <div class="mono" style="color:var(--danger);margin-bottom:6px">${esc(v.failure.error_message)}</div>
        <pre class="mono muted" style="white-space:pre-wrap;font-size:11px;max-height:200px;overflow:auto">${esc(v.failure.log)}</pre>
      </div></td></tr>`;
    }
    return `<tr>
      <td class="row-title">${esc(v.title)}</td>
      <td>${pill(v.status)}</td>
      <td class="mono muted">${v.privacy}</td>
      <td class="mono muted">${v.scheduled_time?fmtTime(v.scheduled_time):"—"}</td>
      <td class="right">
        ${tab==="failed"&&v.failure?`<button class="btn ghost sm" data-log="${v.id}">Log</button>`:""}
        <button class="btn ghost sm" data-edit="${v.id}">Edit</button>
        <button class="btn danger sm" data-del="${v.id}">Delete</button>
      </td></tr>${extra}`;
  }

  document.querySelectorAll(".tabs button").forEach(b=>{
    b.onclick = ()=>{
      document.querySelectorAll(".tabs button").forEach(x=>x.classList.remove("active"));
      b.classList.add("active"); tab=b.dataset.tab; load();
    };
  });

  // add / edit modal
  const modal = document.getElementById("video-modal");
  const openAdd = ()=>{
    document.getElementById("vm-title").textContent="Add video";
    document.getElementById("vm-id").value="";
    ["vm-title-in","vm-desc","vm-tags"].forEach(i=>document.getElementById(i).value="");
    document.getElementById("vm-privacy").value="private";
    document.getElementById("vm-file-wrap").style.display="block";
    modal.classList.add("show");
  };
  window.__openEdit = (v)=>{
    document.getElementById("vm-title").textContent="Edit video";
    document.getElementById("vm-id").value=v.id;
    document.getElementById("vm-title-in").value=v.title;
    document.getElementById("vm-desc").value=v.description||"";
    document.getElementById("vm-tags").value=v.tags||"";
    document.getElementById("vm-privacy").value=v.privacy||"private";
    document.getElementById("vm-file-wrap").style.display="none";
    modal.classList.add("show");
  };
  function openEdit(v){ window.__openEdit(v); }
  async function delVideo(id){
    if(!confirm("Delete this video and its file?")) return;
    const r = await api.del("/api/videos/"+id);
    if(r.ok){ toast("Deleted"); load(); } else toast("Delete failed", true);
  }

  document.getElementById("btn-add").onclick = openAdd;
  document.getElementById("vm-cancel").onclick = ()=> modal.classList.remove("show");
  document.getElementById("vm-save").onclick = async ()=>{
    const id = document.getElementById("vm-id").value;
    const title = document.getElementById("vm-title-in").value.trim();
    if(!title){ toast("Title is required", true); return; }
    const payload = {
      title, description:document.getElementById("vm-desc").value,
      tags:document.getElementById("vm-tags").value,
      privacy:document.getElementById("vm-privacy").value
    };
    if(id){
      const r = await api.put("/api/videos/"+id, payload);
      if(r.ok){ toast("Saved"); modal.classList.remove("show"); load(); }
      else toast(r.data.error||"Save failed", true);
    } else {
      const fd = new FormData();
      Object.entries(payload).forEach(([k,v])=>fd.append(k,v));
      const file = document.getElementById("vm-file").files[0];
      if(file) fd.append("file", file);
      const r = await api.post("/api/videos", fd, true);
      if(r.ok){ toast("Video added"); modal.classList.remove("show"); load(); }
      else toast(r.data.error||"Save failed", true);
    }
  };

  document.getElementById("btn-export").onclick = ()=> window.location = "/api/videos/export.xlsx";
  document.getElementById("import-file").onchange = async (e)=>{
    const file = e.target.files[0]; if(!file) return;
    const fd = new FormData(); fd.append("file", file);
    const r = await api.post("/api/videos/import.xlsx", fd, true);
    if(r.ok){ toast(`Imported ${r.data.created} videos`); load(); }
    else toast(r.data.error||"Import failed", true);
    e.target.value="";
  };

  load();
}

/* =====================  SCHEDULE  ===================== */
async function initSchedule(){
  const today = new Date().toISOString().slice(0,10);
  document.getElementById("day-picker").value = today;
  document.getElementById("slot-date").value = today;

  async function loadDay(){
    const date = document.getElementById("day-picker").value;
    const d = await api.get("/api/schedule/day?date="+date);
    document.getElementById("day-scheduled").innerHTML = d.scheduled.length
      ? `<table><thead><tr><th>Scheduled</th><th>Title</th><th></th></tr></thead><tbody>
         ${d.scheduled.map(v=>`<tr><td class="mono muted">${fmtTime(v.scheduled_time)}</td>
           <td class="row-title">${esc(v.title)}</td>
           <td class="right"><button class="btn danger sm" data-unsch="${v.id}">Remove</button></td></tr>`).join("")}
         </tbody></table>`
      : `<div class="empty">Nothing scheduled on this day.</div>`;
    document.getElementById("day-available").innerHTML = d.available.length
      ? d.available.map(v=>`<label class="pick-item">
          <input type="checkbox" value="${v.id}" class="ind-pick"> ${esc(v.title)}</label>`).join("")
      : `<div class="empty">No draft videos with a file attached.</div>`;
    document.querySelectorAll("[data-unsch]").forEach(b=> b.onclick=async ()=>{
      const r = await api.del("/api/schedule/"+b.dataset.unsch);
      if(r.ok){ toast("Removed"); loadDay(); }
    });
  }
  document.getElementById("day-picker").onchange = loadDay;

  document.getElementById("ind-schedule").onclick = async ()=>{
    const date = document.getElementById("day-picker").value;
    const time = document.getElementById("ind-time").value;
    const picks = [...document.querySelectorAll(".ind-pick:checked")].map(c=>c.value);
    if(!picks.length){ toast("Select at least one video", true); return; }
    for(const id of picks){
      const localISO = new Date(`${date}T${time}`).toISOString();
      await api.post("/api/schedule/individual", {video_id:id, scheduled_time:localISO});
    }
    toast(`Scheduled ${picks.length} video(s)`); loadDay();
  };

  // slot mode
  let slots = ["08:00","12:00","18:00"];
  function renderSlots(){
    document.getElementById("slot-chips").innerHTML = slots.map((s,i)=>`
      <span class="slot-chip">${s}<button data-rm="${i}">×</button></span>`).join("");
    document.querySelectorAll("[data-rm]").forEach(b=> b.onclick=()=>{
      slots.splice(+b.dataset.rm,1); renderSlots();
    });
  }
  renderSlots();
  document.getElementById("slot-add").onclick = ()=>{
    const v = document.getElementById("slot-input").value;
    if(v && !slots.includes(v)){ slots.push(v); slots.sort(); renderSlots(); }
  };

  async function loadSlotAvailable(){
    const date = document.getElementById("slot-date").value;
    const d = await api.get("/api/schedule/day?date="+date);
    document.getElementById("slot-available").innerHTML = d.available.length
      ? d.available.map(v=>`<label class="pick-item">
          <input type="checkbox" value="${v.id}" class="slot-pick"> ${esc(v.title)}</label>`).join("")
      : `<div class="empty">No draft videos with a file attached.</div>`;
  }
  document.getElementById("slot-date").onchange = loadSlotAvailable;

  document.getElementById("slot-schedule").onclick = async ()=>{
    const date = document.getElementById("slot-date").value;
    const video_ids = [...document.querySelectorAll(".slot-pick:checked")].map(c=>c.value);
    if(!slots.length){ toast("Add at least one slot", true); return; }
    if(!video_ids.length){ toast("Select videos to queue", true); return; }
    const r = await api.post("/api/schedule/slots", {
      date, slots, video_ids, tz_offset_minutes: new Date().getTimezoneOffset()
    });
    if(r.ok){ toast(`Assigned ${r.data.assigned} videos to slots`); loadDay(); loadSlotAvailable(); }
    else toast(r.data.error||"Failed", true);
  };

  loadDay(); loadSlotAvailable();
}

/* =====================  ANALYTICS  ===================== */
async function initAnalytics(){
  async function run(params){
    const q = new URLSearchParams(params).toString();
    const d = await api.get("/api/analytics?"+q);
    if(d.error){ toast(d.error, true); return; }
    const t = d.totals;
    document.getElementById("a-totals").innerHTML = `
      <div class="stat"><b>${t.views}</b><small>Views</small></div>
      <div class="stat"><b>${t.watch_minutes}</b><small>Watch min</small></div>
      <div class="stat"><b>${t.likes}</b><small>Likes</small></div>
      <div class="stat"><b>${t.comments}</b><small>Comments</small></div>`;
    const max = Math.max(1, ...d.series.views);
    document.getElementById("a-bars").innerHTML = d.series.views.length
      ? d.series.views.map(v=>`<div class="bar" data-val="${v}" style="height:${(v/max*100).toFixed(1)}%"></div>`).join("")
      : `<div class="empty" style="width:100%">No data for this window (or YouTube not connected).</div>`;
    document.getElementById("a-labels").innerHTML = d.labels.map(l=>`<span>${l.slice(5)}</span>`).join("");
  }

  document.querySelectorAll("[data-preset]").forEach(b=>{
    b.onclick = ()=>{
      document.querySelectorAll("[data-preset]").forEach(x=>x.classList.remove("active"));
      b.classList.add("active"); run({preset:b.dataset.preset});
    };
  });
  document.getElementById("a-range").onclick = ()=>{
    const start=document.getElementById("a-start").value, end=document.getElementById("a-end").value;
    if(start&&end) run({start,end}); else toast("Pick both dates", true);
  };
  document.getElementById("a-days-btn").onclick = ()=>{
    const days=document.getElementById("a-days").value.trim();
    if(days) run({days}); else toast("Enter days", true);
  };
  run({preset:"weekly"});
}

/* =====================  INTEGRATIONS  ===================== */
async function initIntegrations(){
  let pending = null;
  async function load(){
    const d = await api.get("/api/integrations");
    window.__dbmode = (d.db_mode||"").toUpperCase();
    Object.entries(d.fields).forEach(([k,f])=>{
      const el = document.querySelector(`[data-field="${k}"]`);
      if(!el) return;
      if(f.secret){ el.placeholder = f.is_set ? "•••• set — leave blank to keep" : "not set"; }
      else if(el.tagName==="SELECT"){ el.value = f.value || "private"; }
      else { el.value = f.value || ""; }
    });
    document.getElementById("yt-status").innerHTML = d.youtube_connected
      ? `● <span style="color:var(--live)">YouTube connected</span>`
      : `● <span style="color:var(--danger)">not connected</span> — authorize below`;
    document.getElementById("db-mode-tag").textContent = (d.db_mode||"").toUpperCase();
    const sc = d.scheduler||{};
    document.getElementById("sched-status").textContent =
      `status: ${sc.running?"running":"paused"} · next: ${sc.next_run?fmtTime(sc.next_run):"none"}`;
  }

  function collectChanges(){
    const changes = {};
    document.querySelectorAll("[data-field]").forEach(el=>{
      const k = el.dataset.field;
      const isSecret = el.placeholder.includes("••••") || el.placeholder.includes("not set");
      // For secret inputs, only send when the operator typed something new
      if(isSecret && el.type!=="select-one"){ if(el.value.trim()!=="") changes[k]=el.value.trim(); }
      else changes[k] = el.value;
    });
    return changes;
  }

  document.getElementById("save-integrations").onclick = ()=>{
    pending = collectChanges();
    document.getElementById("safe-input").value="";
    document.getElementById("safe-modal").classList.add("show");
  };
  document.getElementById("safe-cancel").onclick = ()=> document.getElementById("safe-modal").classList.remove("show");
  document.getElementById("safe-confirm").onclick = async ()=>{
    const safeword = document.getElementById("safe-input").value;
    const r = await api.post("/api/integrations", {safeword, changes:pending});
    if(r.ok){ toast("Credentials updated"); document.getElementById("safe-modal").classList.remove("show"); load(); }
    else toast(r.data.error||"Rejected", true);
  };

  document.getElementById("sched-pause").onclick = async ()=>{ await api.post("/api/scheduler/pause",{}); toast("Scheduler paused"); load(); refreshTransmitBar(); };
  document.getElementById("sched-resume").onclick = async ()=>{ await api.post("/api/scheduler/resume",{}); toast("Scheduler resumed"); load(); refreshTransmitBar(); };

  load();
}

/* =====================  SETTINGS  ===================== */
async function initSettings(){
  const d = await api.get("/api/settings");
  document.getElementById("s-db").textContent = (d.db_mode||"").toUpperCase();
  document.getElementById("admins-body").innerHTML = d.admins.map(a=>`
    <tr><td class="row-title mono">${esc(a.username)}</td>
        <td class="mono muted">${a.created_at?fmtTime(a.created_at):"—"}</td></tr>`).join("");
}

/* ---- boot ---- */
document.addEventListener("DOMContentLoaded", ()=>{
  markNav();
  refreshTransmitBar();
  setInterval(refreshTransmitBar, 30000);
  const routes = {
    dashboard:initDashboard, videos:initVideos, schedule:initSchedule,
    analytics:initAnalytics, integrations:initIntegrations, settings:initSettings
  };
  const fn = routes[document.body.dataset.page];
  if(fn) fn();
});
