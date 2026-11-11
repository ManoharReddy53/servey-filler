from fastapi.responses import HTMLResponse


def dashboard_page() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Panel Station Survey Assistant</title>
<style>
body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17202a}
button,input{font:inherit;padding:.45rem;margin:.2rem}button{cursor:pointer}
section{border:1px solid #ccd5dc;border-radius:8px;padding:1rem;margin:1rem 0}
.stop{color:#a00;font-weight:600}.question{border-top:1px solid #ddd;padding:.6rem 0}
</style></head><body>
<h1>Panel Station Survey Assistant</h1>
<section><label>Survey URL <input id="url" type="url" size="60" placeholder="https://approved-domain/..."></label>
<label>API token <input id="token" type="password" autocomplete="off"></label>
<button id="connect">Connect</button><button id="inspect">Inspect</button>
<button id="generate">Generate and fill</button><button id="disconnect">Disconnect</button>
<p id="status">Loading...</p><p id="stop" class="stop"></p></section>
<section><h2>Questions</h2><div id="questions"></div></section>
<section><h2>Activity history</h2><div id="activity"></div></section>
<script>
const $=id=>document.getElementById(id);
const headers=()=>({"Authorization":"Bearer "+$("token").value,"Content-Type":"application/json"});
const show=(value, fallback="")=>String(value??fallback);
function render(state){
 $("status").textContent=`Status: ${show(state.status)} — ${show(state.detail)}`;
 $("stop").textContent=state.stop_reason?`Safety interruption: ${state.stop_reason}`:"";
 const answers=new Map((state.intelligence?.suggestions||[]).map(x=>[x.question_id,x.suggestion]));
 $("questions").replaceChildren(...(state.questions||[]).map(q=>{
   const row=document.createElement("div"); row.className="question";
   const title=document.createElement("strong"); title.textContent=show(q.text); row.append(title);
   const answer=answers.get(q.id); const detail=document.createElement("p");
   detail.textContent=answer?.answer?`Generated answer: ${answer.answer}`:"Pending user input or unavailable";
   row.append(detail); return row;
 }));
 $("activity").replaceChildren(...(state.activity||[]).map(entry=>{
   const row=document.createElement("p");
   row.textContent=`${show(entry.action)} — ${show(entry.question_id,"workflow")} — ${show(entry.answer,entry.reason)}`;
   return row;
 }));
}
async function call(path, options={}){
 const response=await fetch(path,{...options,headers:headers()});
 if(!response.ok) throw new Error(await response.text());
 return response.json();
}
async function refresh(){
 try{
   const [state,activity]=await Promise.all([call("/workflow/state"),call("/activity/history")]);
   state.activity=activity; render(state);
 }catch(error){$("status").textContent="Error: "+error.message;}
}
async function action(path, body){
 try{await call(path,{method:"POST",body:body?JSON.stringify(body):undefined});await refresh();}
 catch(error){$("status").textContent="Error: "+error.message;}
}
$("connect").onclick=()=>action("/workflow/connect",{url:$("url").value});
$("inspect").onclick=()=>action("/workflow/inspect");
$("generate").onclick=()=>action("/workflow/generate");
$("disconnect").onclick=()=>action("/workflow/close");
refresh();
</script></body></html>"""
    )
