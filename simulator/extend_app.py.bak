# -*- coding: utf-8 -*-
"""
extend_app.py  --  Workday Extend App Builder clone for the mock-workday tenant.

Replicates the real developer.workday.com/build/<refId>/... App Builder surface
shown in "Wake up with Workday": the dark App Builder shell + left nav tree, plus
the three editors the episode builds for the StockNotifications app:

  - Business Object  (StockData)  : Business Object / Fields / Derived Fields /
                                    Relationships tabs, Add Field drawer with
                                    Type, Decimals, and the enable toggles.
  - Security Domain  (StockDataSecurityDomain) : Page + Orchestration security.
  - Card             (stockCard)  : Header (icon/title/subtitle/indicator),
                                    Body (Simple Card value), Footer.

It links to the Orchestration Builder (orchestrate.py) for the StockRetrieval
orchestration, so both surfaces describe the SAME app.

INSTALL
-------
1. Drop this file next to workday_ui.py (and orchestrate.py).
2. In workday_ui.py, inside the `if __name__ == "__main__":` block, add ONE line
   next to your `import orchestrate` line:

       import extend_app     # noqa: F401  (registers Workday Extend App Builder)

3. Restart, Ctrl+F5, then open:  http://localhost:8443/build/stocknotifications_svfbfp
   (or type "Extend App Builder" in the tenant search bar)

Self-contained: only needs Flask + the `app` object from workday_ui.
"""

import os
import json
import datetime

from flask import request, Response

import workday_ui as wd
app = wd.app

ESTORE = "extend_store.json"
ORCH_STORE = "orchestrate_store.json"   # read-only, to list orchestrations

# show up in the tenant task search bar
try:
    if not any(t.get("url", "").startswith("/build/") for t in wd.TASKS):
        wd.TASKS.append({"name": "Extend App Builder",
                         "url": "/build/stocknotifications_svfbfp"})
except Exception:
    pass


# ===========================================================================
# Seed (StockNotifications app exactly as built in the episode)
# ===========================================================================
def seed():
    return {
        "apps": {
            "stocknotifications_svfbfp": {
                "refId": "stocknotifications_svfbfp",
                "name": "StockNotifications",
                "company": "HackTeam116",
                "orchAppId": "6f4026e444f4f3f37ac1d53d4a63a298",
                "businessObjects": {
                    "StockData": {
                        "name": "StockData",
                        "label": "Stock Data",
                        "collectionName": "stockData",
                        "collectionLabel": "Stock Data",
                        "collectionDescription": "Description for Stock Data.",
                        "securityDomains": ["StockDataSecurityDomain"],
                        "fields": [
                            {"name": "stockTicker", "label": "Stock Ticker", "type": "TEXT",
                             "description": "", "securityDomain": "StockDataSecurityDomain",
                             "decimals": 0, "refId": False, "displayName": True,
                             "purge": False, "indexing": False, "searching": True},
                            {"name": "currentPrice", "label": "Current Price", "type": "DECIMAL",
                             "description": "", "securityDomain": "StockDataSecurityDomain",
                             "decimals": 2, "refId": False, "displayName": False,
                             "purge": False, "indexing": False, "searching": False},
                        ],
                    }
                },
                "securityDomains": {
                    "StockDataSecurityDomain": {
                        "name": "StockDataSecurityDomain",
                        "label": "Stock Data Security Domain",
                        "pageSecurity": True,
                        "orchestrationSecurity": True,
                    }
                },
                "cards": {
                    "stockCard": {
                        "name": "stockCard",
                        "icon": "Chart Bar Arrow",
                        "title": "My Stock",
                        "subtitle": "stock",
                        "bodyValue": "My Simple Card Body",
                        "indicators": [],
                    }
                },
            }
        }
    }


def load():
    if not os.path.exists(ESTORE):
        save(seed())
    try:
        with open(ESTORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return seed()


def save(data):
    with open(ESTORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_orchestrations(orch_app_id, app_name):
    """Read orchestrate_store.json (if present) to list the app's orchestrations."""
    try:
        with open(ORCH_STORE, "r", encoding="utf-8") as f:
            od = json.load(f)
        for a in od.get("apps", {}).values():
            if a.get("appId") == orch_app_id or a.get("name") == app_name:
                return {"appId": a.get("appId"),
                        "orchestrations": [{"name": n, "type": o.get("type", "")}
                                           for n, o in a.get("orchestrations", {}).items()]}
    except Exception:
        pass
    return {"appId": orch_app_id, "orchestrations": []}


# ===========================================================================
# Page (single client-rendered shell, data injected as JSON)
# ===========================================================================
PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 :root{--bg:#0c111b;--panel:#121927;--panel2:#0f1623;--line:#222d40;--line2:#1a2436;
       --mut:#8a94a6;--mut2:#5c6678;--txt:#e6ebf3;--accent:#3b82f6;--accent2:#2563eb;
       --orange:#d98a2b;--green:#2f9e44;--red:#e5484d}
 body{font-family:'Segoe UI',Roboto,Arial,sans-serif;background:var(--bg);color:var(--txt);font-size:14px}
 a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
 .top{display:flex;align-items:center;gap:14px;padding:12px 18px;border-bottom:1px solid var(--line);background:var(--panel2)}
 .top .wm{width:26px;height:26px;border-radius:50%;background:#0a2540;color:#f5b700;display:flex;align-items:center;justify-content:center;font-weight:800}
 .top .ham{color:var(--mut);font-size:20px;cursor:pointer}
 .top .app{font-weight:700}
 .top .saved{margin-left:auto;color:var(--mut);font-size:13px}
 .btn{border:1px solid var(--line);background:transparent;color:var(--txt);border-radius:20px;padding:7px 16px;cursor:pointer;font-weight:600;font-size:13px}
 .btn:hover{background:#192234}
 .btn.pri{background:#cfe0ff;color:#0c2a6b;border-color:#cfe0ff} .btn.pri:hover{background:#bcd4ff}
 .layout{display:flex;height:calc(100vh - 51px)}
 .nav{width:288px;border-right:1px solid var(--line);background:var(--panel2);overflow-y:auto;padding:8px 0}
 .nav .navhdr{display:flex;align-items:center;gap:8px;padding:8px 14px}
 .nav .plus{width:26px;height:26px;border:1px solid var(--line);border-radius:7px;color:var(--mut);display:flex;align-items:center;justify-content:center;cursor:pointer}
 .sec{padding:9px 14px;font-weight:700;color:#cdd5e2;cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px;border-radius:6px}
 .sec:hover{background:#161f30}
 .sec .car{color:var(--mut);font-size:11px;transition:transform .15s} .sec.col .car{transform:rotate(-90deg)}
 .item{padding:7px 14px 7px 34px;color:#aeb8c8;cursor:pointer;display:flex;align-items:center;gap:9px;font-size:13px}
 .item:hover{background:#161f30}
 .item.sel{background:#16263f;color:#fff;border-left:2px solid var(--accent);padding-left:32px}
 .item .ic{font-size:13px;opacity:.85}
 .sub{padding-left:50px}
 .main{flex:1;overflow-y:auto;background:var(--bg)}
 .mhead{display:flex;align-items:center;gap:12px;padding:16px 26px;border-bottom:1px solid var(--line2)}
 .mhead .ttl{font-size:18px;font-weight:700;display:flex;align-items:center;gap:10px}
 .mhead .kebab{color:var(--mut);cursor:pointer}
 .badge{background:var(--orange);color:#1c1205;font-weight:700;font-size:12px;border-radius:6px;padding:4px 9px;display:inline-flex;align-items:center;gap:6px}
 .mhead .right{margin-left:auto;display:flex;gap:10px}
 .tabs{display:flex;gap:26px;border-bottom:1px solid var(--line2);padding:0 26px}
 .tabs a{padding:14px 2px;color:var(--mut);font-weight:600;cursor:pointer;border-bottom:2px solid transparent}
 .tabs a.active{color:#fff;border-bottom-color:var(--accent)}
 .body{padding:26px}
 .lead{color:var(--mut);max-width:980px;line-height:1.6;margin-bottom:22px}
 .grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px 26px;max-width:980px}
 .fld label{display:block;font-weight:600;margin-bottom:7px;font-size:13px}
 .fld label .req{color:var(--red)}
 .fld input,.fld select,.fld textarea{width:100%;background:var(--panel);border:1px solid var(--line);color:var(--txt);
   border-radius:8px;padding:10px 12px;font-size:14px;font-family:inherit}
 .fld textarea{min-height:84px;resize:vertical}
 .fld input::placeholder,.fld textarea::placeholder{color:#566177}
 .fld{margin-bottom:18px}
 .chips{display:flex;flex-wrap:wrap;gap:8px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px}
 .chip{background:#1d2a40;border-radius:6px;padding:5px 10px;font-size:13px;display:inline-flex;align-items:center;gap:7px}
 .chip .x{cursor:pointer;color:var(--mut)}
 table.ftbl{width:100%;border-collapse:collapse;max-width:1100px}
 table.ftbl th{text-align:left;color:var(--mut);font-weight:600;font-size:13px;padding:10px 12px;border-bottom:1px solid var(--line2)}
 table.ftbl td{padding:12px;border-bottom:1px solid var(--line2);font-size:14px}
 table.ftbl td a{color:var(--accent)}
 .pill{display:inline-block;background:#1b2742;color:#cdd9f5;border-radius:5px;padding:2px 9px;font-size:12px;font-weight:600}
 .perm{color:var(--mut);font-size:13px;margin:6px 0 16px}
 .empty{text-align:center;color:var(--mut);padding:70px 0}
 .empty .big{font-size:18px;color:#cdd5e2;margin:14px 0 6px;font-weight:700}
 .lamp{font-size:54px}
 .addbtn{background:#cfe0ff;color:#0c2a6b;border:none;border-radius:20px;padding:9px 20px;font-weight:700;cursor:pointer}
 .ghost{background:transparent;border:1px solid var(--line);color:var(--txt);border-radius:20px;padding:9px 20px;font-weight:600;cursor:pointer}
 .chkrow{display:flex;align-items:center;gap:10px;margin:12px 0;font-size:14px}
 .chkrow input{width:17px;height:17px;accent-color:var(--accent)}
 /* right drawer */
 .drawer{position:fixed;top:0;right:0;width:520px;max-width:96vw;height:100vh;background:var(--panel2);
   border-left:1px solid var(--line);box-shadow:-8px 0 30px rgba(0,0,0,.4);z-index:80;display:none;overflow-y:auto}
 .drawer.show{display:block}
 .drawer .dh{display:flex;align-items:center;gap:12px;padding:18px 20px;border-bottom:1px solid var(--line2)}
 .drawer .dh .di{width:34px;height:34px;border-radius:8px;background:#1d2a40;display:flex;align-items:center;justify-content:center}
 .drawer .dh .x{margin-left:auto;color:var(--mut);font-size:20px;cursor:pointer}
 .drawer .dtabs{display:flex;gap:24px;padding:0 20px;border-bottom:1px solid var(--line2)}
 .drawer .dtabs a{padding:13px 2px;color:var(--mut);font-weight:600;cursor:pointer;border-bottom:2px solid transparent}
 .drawer .dtabs a.active{color:#fff;border-bottom-color:var(--accent)}
 .drawer .dbody{padding:20px}
 .drow{display:grid;grid-template-columns:1fr 1fr;gap:16px}
 .info{background:#13233f;border:1px solid #234063;border-radius:8px;padding:12px 14px;color:#c7d6f0;font-size:13px;display:flex;gap:10px;margin-top:16px}
 .dfoot{display:flex;gap:10px;margin-top:22px}
 /* modal */
 .mbg{position:fixed;inset:0;background:rgba(5,9,16,.6);display:none;align-items:center;justify-content:center;z-index:90}
 .mbg.show{display:flex}
 .modal{background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:26px;width:540px;max-width:92vw}
 .modal h3{font-size:22px;margin-bottom:8px}
 .warn{background:var(--orange);color:#1c1205;border-radius:8px;padding:14px;margin:14px 0;font-size:13px;line-height:1.5}
 .warn a{color:#1c1205;text-decoration:underline}
 .footbar{display:flex;gap:24px;padding:10px 26px;border-top:1px solid var(--line);color:var(--mut);font-size:13px;background:var(--panel2)}
 .footbar span{cursor:pointer} code{background:#1a2335;padding:2px 6px;border-radius:5px;color:#cdd9f5}
 .toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#1d2a40;border:1px solid var(--line);
   padding:10px 18px;border-radius:10px;opacity:0;transition:opacity .2s;z-index:120}
 .toast.show{opacity:1}
</style></head><body>
<div class="top">
  <div class="ham">&#9776;</div>
  <div class="app" id="appTitle"></div>
  <div class="saved" id="saved">Saved to session just now.</div>
  <div class="btn" onclick="toast('Validation passed')">Validate</div>
  <div class="btn" onclick="toast('Saved to App Hub')">Save to App Hub</div>
  <div class="btn pri" onclick="toast('Save and Deploy queued')">Save and Deploy</div>
</div>
<div class="layout">
  <div class="nav">
    <div class="navhdr"><div class="plus" title="Add Component" onclick="openAdd()">+</div></div>
    <div id="navTree"></div>
  </div>
  <div class="main" id="main"></div>
</div>
<div class="footbar"><span>Validations</span><span>Build Logs</span><span>App Logs</span></div>

<div class="drawer" id="drawer"><div id="drawerInner"></div></div>
<div class="mbg" id="mbg"><div class="modal" id="modal"></div></div>
<div class="toast" id="toast"></div>

<script>
const DATA = __DATA__;
const APP = DATA.app;
let sel = {kind:"businessobject", name:"StockData"};
let boTab = "businessobject";
let cardTab = "presentation";
let fieldEdit = null;     // index being edited, or -1 for new

const FIELD_TYPES = ["TEXT","MEMO","RICH_TEXT","NUMERIC","DECIMAL","PERCENT","CURRENCY",
                     "DATE","DATE_TIME","BOOLEAN","INSTANCE","MULTI_INSTANCE"];

function esc(t){return (t==null?"":String(t)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function jv(t){return (t==null?"":String(t)).replace(/'/g,"&#39;").replace(/"/g,"&quot;");}
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),1500);}

/* ---------- nav tree ---------- */
const SECTIONS = [
  ["App Configurations","cfg",[["App Metadata (AMD)","amd",[["__amdfile__","file"]]],
                               ["Site Metadata (SMD)","smd",[["__amdfile__","file"]]],
                               ["Attributes","attr",[]]]],
  ["Cards","cards","__cards__"],
  ["Security Domains","sd","__sd__"],
  ["Business Objects","bo","__bo__"],
  ["Orchestrations","orch",[["Orchestrations","orchlist"]]],
  ["Assets","assets",[["Images","images"]]],
  ["Pages","pages",[]],
  ["Page Configurations","pgc",[["Cards","pgc_cards"],["Reusable Pods","pods"],["Scripts","scripts"],["Translations","trans"]]],
  ["Tasks","tasks",[]],
  ["Queries","queries",[["Graph Queries","gq"],["WQL Queries","wql"]]],
  ["Card Tenant Settings","cts",[]],
  ["Attachments","att",[]],
  ["Business Processes","bp",[]],
  ["Reports","reports",[]],
  ["Testing","testing",[["Mock Data","mock"],["Mock Data Configuration","mockcfg"]]],
];
let collapsed = {};

function navTree(){
  let h="";
  SECTIONS.forEach(function(s){
    const key=s[1]; const col=collapsed[key]?" col":"";
    h+="<div class='sec"+col+"' onclick='toggleSec(\""+key+"\")'><span class='car'>&#9660;</span>"+s[0]+"</div>";
    if(collapsed[key]) return;
    let items=s[2];
    if(items==="__cards__") items=Object.keys(APP.cards).map(n=>[n,"card",null,"&#128468;"]);
    else if(items==="__sd__") items=Object.keys(APP.securityDomains).map(n=>[n,"securitydomain",null,"&#128274;"]);
    else if(items==="__bo__") items=Object.keys(APP.businessObjects).map(n=>[n,"businessobject",null,"&#128451;"]);
    (items||[]).forEach(function(it){
      const label=it[0]==="__amdfile__"?(APP.refId):it[0];
      const kind=it[1]; const icon=it[3]||"&#128196;";
      const isSel=(sameSel(kind,label));
      h+="<div class='item"+(isSel?" sel":"")+"' onclick='navClick(\""+kind+"\",\""+jv(label)+"\")'>"+
         "<span class='ic'>"+icon+"</span>"+esc(it[0]==="__amdfile__"?APP.refId:it[0])+"</div>";
      // nested file under amd/smd
      if(it[2] && it[2].length){ it[2].forEach(function(f){
        h+="<div class='item sub' onclick='navClick(\"file\",\""+APP.refId+"\")'><span class='ic'>&#128196;</span>"+esc(APP.refId)+"</div>";
      });}
    });
  });
  document.getElementById("navTree").innerHTML=h;
}
function sameSel(kind,name){
  if(kind==="businessobject"||kind==="securitydomain"||kind==="card") return sel.kind===kind && sel.name===name;
  if(kind==="orchlist") return sel.kind==="orchlist";
  return false;
}
function toggleSec(k){collapsed[k]=!collapsed[k];navTree();}
function navClick(kind,name){
  if(kind==="card"){sel={kind:"card",name:name};cardTab="presentation";}
  else if(kind==="securitydomain"){sel={kind:"securitydomain",name:name};}
  else if(kind==="businessobject"){sel={kind:"businessobject",name:name};boTab="businessobject";}
  else if(kind==="orchlist"){sel={kind:"orchlist"};}
  else {sel={kind:"placeholder",name:name};}
  closeDrawer();render();
}

/* ---------- render dispatch ---------- */
function render(){
  document.getElementById("appTitle").textContent=APP.name+" ("+APP.company+")";
  navTree();
  const m=document.getElementById("main");
  if(sel.kind==="businessobject") m.innerHTML=renderBO(APP.businessObjects[sel.name]);
  else if(sel.kind==="securitydomain") m.innerHTML=renderSD(APP.securityDomains[sel.name]);
  else if(sel.kind==="card") m.innerHTML=renderCard(APP.cards[sel.name]);
  else if(sel.kind==="orchlist") m.innerHTML=renderOrch();
  else m.innerHTML=renderPlaceholder();
  if(sel.kind==="businessobject" && boTab==="fields") wireFieldTable();
}

/* ---------- Business Object ---------- */
function renderBO(bo){
  let h="<div class='mhead'><div class='ttl'>&#128451; "+esc(bo.name)+" <span class='kebab'>&#8943;</span>"+
        "<span class='badge'>&#9201; Model Component</span></div></div>";
  h+="<div class='tabs'>"+
     boTabLink("businessobject","Business Object")+boTabLink("fields","Fields")+
     boTabLink("derived","Derived Fields")+boTabLink("relationships","Relationships")+"</div><div class='body'>";
  if(boTab==="businessobject") h+=boGeneral(bo);
  else if(boTab==="fields") h+=boFields(bo);
  else if(boTab==="derived") h+="<div class='empty'><div class='lamp'>&#128161;</div><div class='big'>No Derived Fields</div>"+
       "<div>Derived fields calculate values from other fields.</div></div>";
  else h+="<div class='empty'><div class='lamp'>&#128279;</div><div class='big'>No Relationships</div>"+
       "<div>Relationships link this object to other business objects.</div></div>";
  h+="</div>";
  return h;
}
function boTabLink(id,label){return "<a class='"+(boTab===id?"active":"")+"' onclick='boTab=\""+id+"\";render()'>"+label+"</a>";}

function boGeneral(bo){
  let h="<div class='lead'>The <b>Label</b>, <b>Default Collection Name</b>, and <b>Default Collection Label</b> "+
        "have been populated for you, based on the Business Object's <b>Name</b>. You can change these values.</div>";
  h+="<div class='grid2'>";
  h+=fld("Name","text",bo.name,"setBO('name',this.value)",true);
  h+=fld("Label","text",bo.label,"setBO('label',this.value)",false);
  h+=fld("Default Collection Name","text",bo.collectionName,"setBO('collectionName',this.value)",true);
  h+=fld("Default Collection Label","text",bo.collectionLabel,"setBO('collectionLabel',this.value)",false);
  // security domains chips
  let chips="<div class='fld'><label>Default Security Domains <span class='req'>*</span></label><div class='chips'>";
  (bo.securityDomains||[]).forEach((s,i)=>{chips+="<span class='chip'>"+esc(s)+" <span class='x' onclick='rmBOSD("+i+")'>&#10005;</span></span>";});
  chips+="<input style='flex:1;min-width:120px;background:transparent;border:none;color:var(--txt);outline:none' placeholder='' readonly></div></div>";
  h+=chips;
  h+="<div class='fld'><label>Default Collection Description</label><textarea oninput=\"setBO('collectionDescription',this.value)\" onchange='save()'>"+esc(bo.collectionDescription||"")+"</textarea></div>";
  h+="</div>";
  return h;
}
function setBO(k,v){APP.businessObjects[sel.name][k]=v;save();}
function rmBOSD(i){APP.businessObjects[sel.name].securityDomains.splice(i,1);render();save();}

function boFields(bo){
  const n=(bo.fields||[]).length;
  let h="<button class='addbtn' onclick='openField(-1)'>Add Field</button>";
  h+="<div class='perm'>Fields &nbsp; "+n+" of 50 Permitted</div>";
  if(!n){
    return "<div class='empty'><div class='lamp'>&#128161;</div><div class='big'>No Fields</div>"+
           "<div>You can add up to 50 Fields to represent different types of data.</div><br>"+
           "<button class='addbtn' onclick='openField(-1)'>Add Field</button></div>";
  }
  h+="<table class='ftbl'><tr><th>Name</th><th>Label</th><th>Security Domains</th><th>Type</th><th>Actions</th></tr>";
  bo.fields.forEach(function(f,i){
    h+="<tr><td><a onclick='openField("+i+")'>"+esc(f.name)+"</a></td>"+
       "<td>"+esc(f.label)+"</td><td>"+esc(f.securityDomain||"")+"</td>"+
       "<td><span class='pill'>"+esc(f.type)+(f.type==="DECIMAL"?(" ("+(f.decimals||0)+")"):"")+"</span></td>"+
       "<td><span class='kebab' style='cursor:pointer' onclick='delField("+i+")'>&#128465;</span></td></tr>";
  });
  h+="</table>";
  return h;
}
function wireFieldTable(){/* hooks live via inline handlers */}
function delField(i){if(!confirm("Delete this field?"))return;APP.businessObjects[sel.name].fields.splice(i,1);render();save();}

/* ---- Add / Edit Field drawer ---- */
function openField(i){
  fieldEdit=i;
  const bo=APP.businessObjects[sel.name];
  const f=(i>=0)?Object.assign({},bo.fields[i]):
    {name:"",label:"",type:"TEXT",description:"",decimals:2,securityDomain:(bo.securityDomains[0]||""),
     refId:false,displayName:false,purge:false,indexing:false,searching:false};
  window._fdraft=f;
  drawField();
  document.getElementById("drawer").classList.add("show");
}
function drawField(){
  const f=window._fdraft;
  let h="<div class='dh'><div class='di'>&#128202;</div><b>Add Field</b><span class='x' onclick='closeDrawer()'>&#10005;</span></div>";
  h+="<div class='dtabs'><a class='active'>Properties</a><a onclick='toast(\"Field-level security\")'>Security</a></div>";
  h+="<div class='dbody'>";
  h+="<p style='color:var(--mut);margin-bottom:16px'><a href='#'>See documentation</a> for restricted field names.</p>";
  h+="<div class='drow'>";
  h+=fld("Name","text",f.name,"_fdraft.name=this.value",true);
  h+=fld("Label","text",f.label,"_fdraft.label=this.value",false);
  h+="</div><div class='drow'>";
  // type select
  h+="<div class='fld'><label>Type <span class='req'>*</span></label><select onchange='_fdraft.type=this.value;drawField()'>"+
     FIELD_TYPES.map(t=>"<option"+(t===f.type?" selected":"")+">"+t+"</option>").join("")+"</select></div>";
  h+="<div class='fld'><label>Description</label><textarea style='min-height:60px' oninput='_fdraft.description=this.value'>"+esc(f.description||"")+"</textarea></div>";
  h+="</div>";
  if(f.type==="DECIMAL"||f.type==="PERCENT"||f.type==="CURRENCY"){
    h+=fld("Decimals","number",(f.decimals==null?2:f.decimals),"_fdraft.decimals=parseInt(this.value||'0')",true);
  }
  h+=chk("Enable Reference ID","refId",f.refId);
  h+=chk("Enable as Display Name","displayName",f.displayName);
  h+=chk("Enable for Purge","purge",f.purge);
  h+=chk("Enable for Field Indexing","indexing",f.indexing);
  h+=chk("Enable for Searching","searching",f.searching);
  h+="<div class='info'>&#9432; <div><b>Reference ID</b> and <b>Display Name</b> can only be used once per Business Object.</div></div>";
  h+="<div class='dfoot'><button class='addbtn' onclick='saveField()'>Done</button><button class='ghost' onclick='closeDrawer()'>Cancel</button></div>";
  h+="</div>";
  document.getElementById("drawerInner").innerHTML=h;
}
function chk(label,key,val){
  return "<div class='chkrow'><input type='checkbox' "+(val?"checked":"")+" onchange='_fdraft."+key+"=this.checked'> "+label+"</div>";
}
function saveField(){
  const f=window._fdraft;
  if(!f.name){toast("Name is required");return;}
  const bo=APP.businessObjects[sel.name];
  if(!f.securityDomain) f.securityDomain=bo.securityDomains[0]||"";
  if(fieldEdit>=0) bo.fields[fieldEdit]=f; else bo.fields.push(f);
  closeDrawer();render();save();toast("Field saved");
}

/* ---------- Security Domain ---------- */
function renderSD(sd){
  let h="<div class='mhead'><div class='ttl'>&#128274; "+esc(sd.name)+" <span class='kebab'>&#8943;</span>"+
        "<span class='badge'>&#9201; Model Component</span></div></div><div class='body'>";
  h+="<div class='lead'>Security Domains are utilized to secure app data and can provide page-level security. "+
     "Security policies are used in the same manner as the Workday application and existing security groups and "+
     "roles can be used to simplify access controls.</div>";
  h+="<div class='grid2'>"+fld("Name","text",sd.name,"setSD('name',this.value)",true)+
     fld("Label","text",sd.label,"setSD('label',this.value)",false)+"</div>";
  h+="<p style='color:var(--mut);margin:18px 0 10px'>Enable only if the domain is used for page and/or orchestration security.</p>";
  h+="<div style='font-weight:600;margin-bottom:8px'>Enabled For:</div>";
  h+="<div class='chkrow'><input type='checkbox' "+(sd.pageSecurity?"checked":"")+" onchange=\"setSD('pageSecurity',this.checked)\"> Page Security</div>";
  h+="<div class='chkrow'><input type='checkbox' "+(sd.orchestrationSecurity?"checked":"")+" onchange=\"setSD('orchestrationSecurity',this.checked)\"> Orchestration Security</div>";
  h+="</div>";
  return h;
}
function setSD(k,v){APP.securityDomains[sel.name][k]=v;save();if(k==="name")toast("Renamed (refresh nav)");}

/* ---------- Card ---------- */
function renderCard(c){
  let h="<div class='mhead'><div class='ttl'>&#128468; "+esc(c.name)+" <span class='kebab'>&#8943;</span></div></div>";
  h+="<div class='tabs'>"+
     "<a class='"+(cardTab==="presentation"?"active":"")+"' onclick='cardTab=\"presentation\";render()'>Presentation</a>"+
     "<a class='"+(cardTab==="cardload"?"active":"")+"' onclick='cardTab=\"cardload\";render()'>Card Load</a>"+
     "<a class='"+(cardTab==="scripts"?"active":"")+"' onclick='cardTab=\"scripts\";render()'>Scripts</a></div><div class='body'>";
  if(cardTab==="presentation"){
    h+="<h2 style='margin-bottom:14px'>Header</h2>";
    h+="<div style='background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;max-width:900px;margin-bottom:24px'>";
    h+=rowfld("Icon",fld_inline("text",c.icon,"setCard('icon',this.value)","Chart Bar Arrow"));
    h+=rowfld("Title",fld_inline("text",c.title,"setCard('title',this.value)","Title"));
    h+=rowfld("Subtitle",fld_inline("text",c.subtitle,"setCard('subtitle',this.value)","Subtitle"));
    h+=rowfld("Indicator","<button class='ghost' onclick='toast(\"Indicator added\")'>+ Add Indicator</button>");
    h+="</div>";
    h+="<h2 style='margin-bottom:14px'>Body</h2>";
    h+="<div style='background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;max-width:900px;margin-bottom:24px'>";
    h+="<div style='font-weight:700;margin-bottom:12px'>&#128468; Simple Card</div>";
    h+="<div style='display:flex;align-items:center;gap:10px'><label style='font-weight:600'>Value <span class='req' style='color:var(--red)'>*</span></label>"+
       "<input style='flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:9px 11px' "+
       "value='"+jv(c.bodyValue)+"' oninput=\"setCard('bodyValue',this.value)\" onchange='save()'></div>";
    h+="</div>";
    h+="<h2 style='margin-bottom:14px'>Footer</h2>";
    h+="<div style='background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;max-width:900px'>"+
       "<button class='ghost' onclick='toast(\"Footer item added\")'>+ Add Footer Item</button></div>";
  } else if(cardTab==="cardload"){
    h+="<div class='empty'><div class='lamp'>&#128229;</div><div class='big'>Card Load</div>"+
       "<div>Bind an orchestration or query to populate the card. Link <b>StockRetrieval</b> here.</div></div>";
  } else {
    h+="<div class='empty'><div class='lamp'>&#128221;</div><div class='big'>Scripts</div>"+
       "<div>Client-side PMD scripts for this card.</div></div>";
  }
  h+="</div>";
  return h;
}
function setCard(k,v){APP.cards[sel.name][k]=v;save();}
function rowfld(label,inner){return "<div style='display:flex;align-items:center;gap:18px;margin-bottom:14px'>"+
  "<div style='width:120px;color:var(--mut);font-weight:600'>"+label+"</div><div style='flex:1'>"+inner+"</div></div>";}
function fld_inline(type,val,handler,ph){return "<input type='"+type+"' style='width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:9px 11px' "+
  "value='"+jv(val)+"' placeholder='"+jv(ph||"")+"' oninput=\""+handler+"\" onchange='save()'>";}

/* ---------- Orchestrations list ---------- */
function renderOrch(){
  let h="<div class='mhead'><div class='ttl'>&#9095; Orchestrations</div></div><div class='body'>";
  const oid=DATA.orch.appId;
  h+="<button class='ghost' onclick=\"window.open('/orchestrate/app/"+oid+"/orchestrations','_blank')\">Add Orchestration &#8599;</button> "+
     "<button class='ghost' onclick='render()'>Refresh</button><div style='height:18px'></div>";
  if(!DATA.orch.orchestrations.length){
    h+="<div class='empty'><div class='lamp'>&#128161;</div><div class='big'>No Orchestrations</div>"+
       "<div>Adding a new orchestration opens the Orchestration Builder in a new tab.</div></div>";
  } else {
    DATA.orch.orchestrations.forEach(function(o){
      h+="<div style='display:flex;align-items:center;gap:10px;padding:12px 4px;border-bottom:1px solid var(--line2)'>"+
         "&#9998; <a href='/orchestrate/app/"+oid+"/development/orchestrations/"+encodeURIComponent(o.name)+"' target='_blank'>"+esc(o.name)+"</a>"+
         "<span style='color:var(--mut);margin-left:8px'>"+esc(o.type)+"</span></div>";
    });
  }
  h+="</div>";
  return h;
}

/* ---------- placeholder sections ---------- */
function renderPlaceholder(){
  return "<div class='mhead'><div class='ttl'>"+esc(sel.name||"Component")+"</div></div>"+
    "<div class='empty'><div class='lamp'>&#128161;</div><div class='big'>No Component Selected</div>"+
    "<div>This section is part of the App Builder shell. Pick Business Objects, Security Domains, Cards, or Orchestrations.</div></div>";
}

/* ---------- Add Component modal ---------- */
function openAdd(){
  const m=document.getElementById("modal");
  m.innerHTML="<h3>Add Component</h3><p style='color:var(--mut);margin-bottom:16px'>What do you want to create?</p>"+
    "<div style='display:flex;flex-direction:column;gap:10px'>"+
    "<button class='ghost' onclick='addThing(\"businessobject\")'>&#128451; Business Object</button>"+
    "<button class='ghost' onclick='addThing(\"securitydomain\")'>&#128274; Security Domain</button>"+
    "<button class='ghost' onclick='addThing(\"card\")'>&#128468; Card</button></div>"+
    "<div class='dfoot'><button class='ghost' onclick='closeModal()'>Cancel</button></div>";
  document.getElementById("mbg").classList.add("show");
}
function addThing(kind){
  const m=document.getElementById("modal");
  const titles={businessobject:"Add Business Object",securitydomain:"Add Security Domain",card:"Add Card"};
  m.innerHTML="<h3>"+titles[kind]+"</h3>"+
    "<div class='warn'>&#9201; Adding this component will queue all promotions to Implementation, Sandbox, "+
    "or Production tenants until the Friday Maintenance Window. <a href='#'>Learn More</a></div>"+
    "<div class='fld'><label>Name <span class='req'>*</span></label><input id='newName' placeholder='My"+
    (kind==="businessobject"?"BusinessObject":kind==="card"?"ComponentName":"SecurityDomain")+"'></div>"+
    "<div class='dfoot'><button class='addbtn' onclick='createThing(\""+kind+"\")'>Done</button>"+
    "<button class='ghost' onclick='closeModal()'>Cancel</button></div>";
}
function createThing(kind){
  const name=(document.getElementById("newName").value||"").trim();
  if(!name){toast("Name is required");return;}
  if(kind==="businessobject"){
    APP.businessObjects[name]={name:name,label:name,collectionName:name.charAt(0).toLowerCase()+name.slice(1),
      collectionLabel:name,collectionDescription:"",securityDomains:[],fields:[]};
    sel={kind:"businessobject",name:name};boTab="businessobject";
  } else if(kind==="securitydomain"){
    APP.securityDomains[name]={name:name,label:name,pageSecurity:false,orchestrationSecurity:false};
    sel={kind:"securitydomain",name:name};
  } else {
    APP.cards[name]={name:name,icon:"Chart Bar Arrow",title:"My "+name,subtitle:"",bodyValue:"",indicators:[]};
    sel={kind:"card",name:name};cardTab="presentation";
  }
  closeModal();render();save();toast("Created "+name);
}

/* ---------- drawer / modal / save ---------- */
function closeDrawer(){document.getElementById("drawer").classList.remove("show");}
function closeModal(){document.getElementById("mbg").classList.remove("show");}
document.getElementById("mbg").addEventListener("click",function(e){if(e.target.id==="mbg")closeModal();});
function save(){
  document.getElementById("saved").textContent="Saving...";
  fetch("/build/api/save",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({refId:APP.refId,app:APP})}).then(r=>r.json()).then(d=>{
      document.getElementById("saved").textContent="Saved to session "+(d.savedAt||"just now")+".";
    }).catch(()=>{document.getElementById("saved").textContent="Save failed";});
}

render();
</script>
</body></html>"""


# ===========================================================================
# Routes
# ===========================================================================
@app.route("/build/<refid>")
@app.route("/build/<refid>/<path:comp>")
def build_shell(refid, comp=None):
    d = load()
    a = d["apps"].get(refid)
    if not a:
        return Response("<h2 style='font-family:sans-serif'>Extend app not found: %s</h2>" % refid,
                        mimetype="text/html")
    orch = list_orchestrations(a.get("orchAppId", ""), a.get("name", ""))
    payload = {"refId": refid, "app": a, "orch": orch}
    html = PAGE.replace("__TITLE__", a["name"] + " - App Builder").replace("__DATA__", json.dumps(payload))
    return Response(html, mimetype="text/html")


@app.route("/build/api/save", methods=["POST"])
def build_save():
    data = request.get_json(force=True)
    d = load()
    if data.get("refId") in d["apps"]:
        d["apps"][data["refId"]] = data["app"]
        save(d)
    return {"ok": True, "savedAt": datetime.datetime.now().strftime("%I:%M %p")}
