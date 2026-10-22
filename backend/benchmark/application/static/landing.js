const header=document.querySelector('.site-header');
const menu=document.querySelector('.menu-toggle');
menu.addEventListener('click',()=>{const open=header.classList.toggle('open');menu.setAttribute('aria-expanded',open);document.body.classList.toggle('menu-open',open)});
document.querySelectorAll('.site-nav a').forEach(link=>link.addEventListener('click',()=>{header.classList.remove('open');document.body.classList.remove('menu-open');menu.setAttribute('aria-expanded','false')}));

const revealObserver=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('visible');revealObserver.unobserve(entry.target)}}),{threshold:.13});
document.querySelectorAll('.reveal').forEach(el=>revealObserver.observe(el));

const agents={
  deviation:{name:'Deviation investigator',request:'Dissolved oxygen dropped below the action limit on Batch 24-091. Start the investigation.',title:'Tracing the deviation across your digital thread',steps:[['Historian queried','11-minute excursion isolated'],['Calibration checked','DO-PROBE-02 within tolerance'],['Correlating batch events','MES, CMMS, and operator records']],result:'Gas-delivery restriction is the leading cause. Two verification tasks drafted; batch hold requires QA approval.'},
  release:{name:'Batch release coordinator',request:'Prepare the release-readiness package for Batch 24-103 before the 14:00 QA review.',title:'Assembling the complete release record',steps:[['Batch record checked','All manufacturing steps complete'],['QC results reconciled','12 of 12 assays within specification'],['Verifying open exceptions','One minor review task remains']],result:'Release package is 96% complete. One training acknowledgement is routed to the area supervisor.'},
  maintenance:{name:'Maintenance intelligence',request:'Chromatography skid pressure is trending up. Assess batch impact and recommend next steps.',title:'Connecting asset condition to process risk',steps:[['CMMS history reviewed','Two related work orders found'],['Process trend compared','Pressure rise began 3 cycles ago'],['Assessing batch exposure','Current run remains within control limits']],result:'Inlet frit fouling is probable. Inspection is recommended after this run; no immediate batch hold indicated.'}
};
const nameEl=document.querySelector('#agentName'),requestEl=document.querySelector('#agentRequest'),titleEl=document.querySelector('#workflowTitle'),stepsEl=document.querySelector('#workflowSteps'),resultEl=document.querySelector('#agentResult');
function setAgentTab(tab){
  document.querySelectorAll('.agent-tab').forEach(t=>{t.classList.remove('active');t.setAttribute('aria-selected','false')});
  tab.classList.add('active');tab.setAttribute('aria-selected','true');
}
let runTimers=[],typeTimer=null,playedOnce=false;
function clearRun(){runTimers.forEach(clearTimeout);runTimers=[];if(typeTimer){clearInterval(typeTimer);typeTimer=null}}
function typeInto(el,text,speed,done){
  el.classList.add('typing');el.textContent='';
  if(reduceMotion){el.textContent=text;el.classList.remove('typing');done&&done();return}
  let i=0;typeTimer=setInterval(()=>{el.textContent=text.slice(0,++i);
    if(i>=text.length){clearInterval(typeTimer);typeTimer=null;el.classList.remove('typing');done&&done()}},speed);
}
function fillInstant(key){
  const tab=document.querySelector(`.agent-tab[data-agent="${key}"]`),data=agents[key];if(!tab||!data)return;
  setAgentTab(tab);requestEl.classList.remove('typing');resultEl.classList.remove('typing');
  requestEl.textContent=data.request;titleEl.textContent=data.title;
  stepsEl.innerHTML=data.steps.map((step,i)=>`<div class="${i<2?'done':'active'}"><i>${i<2?'✓':''}</i><span><b>${step[0]}</b><small>${step[1]}</small></span></div>`).join('');
  resultEl.textContent=data.result;
}
// A live run: prompt types out, steps execute one by one, artifact streams in.
function playRun(key){
  const tab=document.querySelector(`.agent-tab[data-agent="${key}"]`),data=agents[key];if(!tab||!data)return;
  clearRun();setAgentTab(tab);restartAgentProgress();
  nameEl.textContent=data.name;
  typeInto(requestEl,data.request,18,()=>{
    titleEl.textContent=data.title;
    stepsEl.innerHTML=data.steps.map(step=>`<div class="pending"><i></i><span><b>${step[0]}</b><small></small></span></div>`).join('');
    const rows=[...stepsEl.children];
    data.steps.forEach((step,i)=>{
      runTimers.push(setTimeout(()=>{
        rows[i].className='working';
        runTimers.push(setTimeout(()=>{
          rows[i].className=i<2?'done':'active';
          rows[i].querySelector('i').textContent=i<2?'✓':'';
          rows[i].querySelector('small').textContent=step[1];
          if(i===data.steps.length-1)typeInto(resultEl,data.result,12);
        },reduceMotion?0:650));
      },reduceMotion?0:i*700));
    });
  });
}
document.querySelectorAll('.agent-tab').forEach(tab=>tab.addEventListener('click',()=>{playedOnce=true;playRun(tab.dataset.agent);pokeAgentAutoplay()}));
document.querySelectorAll('.prompt-chips button').forEach(chip=>chip.addEventListener('click',()=>{playedOnce=true;playRun(chip.dataset.agent);pokeAgentAutoplay();document.querySelector('.agent-canvas').scrollIntoView({behavior:reduceMotion?'auto':'smooth',block:'center'})}));

// Autoplay the specialist demo while it is on screen; hover or a tap pauses the cycle.
const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
const agentCanvas=document.querySelector('.agent-canvas'),agentProgress=document.querySelector('#agentProgress');
let agentTimer=null,agentVisible=false;
function nextAgent(){const tabs=[...document.querySelectorAll('.agent-tab')];const i=tabs.findIndex(t=>t.classList.contains('active'));playRun(tabs[(i+1)%tabs.length].dataset.agent)}
function restartAgentProgress(){if(!agentProgress)return;agentProgress.classList.remove('playing');void agentProgress.offsetWidth;if(agentVisible&&!reduceMotion)agentProgress.classList.add('playing')}
function pokeAgentAutoplay(){clearInterval(agentTimer);if(reduceMotion)return;agentTimer=setInterval(()=>{if(agentVisible&&!document.hidden)nextAgent()},6500)}
new IntersectionObserver(es=>es.forEach(e=>{agentVisible=e.isIntersecting;
  if(e.isIntersecting&&!playedOnce&&!reduceMotion){playedOnce=true;playRun(document.querySelector('.agent-tab.active').dataset.agent)}
  restartAgentProgress()}),{threshold:.3}).observe(agentCanvas);
agentCanvas.addEventListener('pointerenter',()=>clearInterval(agentTimer));
agentCanvas.addEventListener('pointerleave',pokeAgentAutoplay);

const architecture={
  connect:{step:'01 · VALIDATED INTEGRATION FABRIC',title:'Connect to manufacturing truth.',description:'Validated adapters collect source records, telemetry, events, and controlled documents without replacing the authoritative systems your teams already trust.',tags:['MES / eBR','Historian / PAT','LIMS / CDS','QMS','CMMS','ERP / WMS'],core:'VALIDATED<br>EVENT FABRIC',small:'APIs · events · CDC',sources:['MES','LIMS','QMS','PAT','CMMS','ERP']},
  understand:{step:'02 · REAL-TIME OPERATIONAL TWIN',title:'Understand the whole operation.',description:'Every batch, asset, material, test, person, schedule, recipe, and constraint is resolved into a live operational model with exact evidence lineage.',tags:['Batch genealogy','Asset state','Materials','QC capacity','Workforce skills','GMP constraints'],core:'OPERATIONAL<br>DIGITAL TWIN',small:'State · context · provenance',sources:['BATCH','ASSET','MATERIAL','QC','STAFF','PLAN']},
  decide:{step:'03 · AI OPERATIONS DECISION ENGINE',title:'Turn context into the best next move.',description:'The decision engine detects risk, investigates causal evidence, forecasts outcomes, optimizes constrained plans, and explains confidence and operational value.',tags:['Detect','Investigate','Predict','Optimize','Simulate','Value impact'],core:'DECISION<br>ENGINE',small:'Reason · optimize · explain',sources:['RISK','CAUSE','YIELD','PLAN','VALUE','CONF.']},
  act:{step:'04 · PERSISTENT OPERATING AGENTS',title:'Coordinate specialist work end to end.',description:'Persistent agents monitor their domains, assemble evidence, compare recovery plans, create human tasks, and prepare controlled actions around the clock.',tags:['Campaign recovery','QC flow','Maintenance','Materials','Deviation & quality','Capacity planning'],core:'AGENT<br>ORCHESTRATOR',small:'Route · coordinate · escalate',sources:['RECOVERY','QC','MAINT.','MATERIAL','QUALITY','CAPACITY']},
  govern:{step:'05 · HUMAN-GOVERNED CONTROL PLANE',title:'Keep authority where it belongs.',description:'Identity, risk policy, separation of duties, authority limits, and role-aware approvals determine what an agent may recommend and what a human must decide.',tags:['Identity','Authority limits','Risk policy','Separation of duties','Human approval','Audit record'],core:'CONTROL<br>PLANE',small:'Review · approve · audit',sources:['IDENTITY','LIMITS','RISK','DUTIES','APPROVE','AUDIT']},
  learn:{step:'06 · OUTCOME & LEARNING LOOP',title:'Learn from what actually happened.',description:'Authoritative acknowledgements and real outcomes are compared with projections to attribute value, calibrate models, monitor drift, and improve the next decision.',tags:['Observe outcome','Projected vs actual','Value attribution','Calibration','Safety monitoring','Performance'],core:'OUTCOME<br>LOOP',small:'Measure · calibrate · improve',sources:['OBSERVE','COMPARE','VALUE','TUNE','SAFETY','IMPROVE']}
};
const architectureStep=document.querySelector('#architectureStep'),architectureTitle=document.querySelector('#architectureTitle'),architectureDescription=document.querySelector('#architectureDescription'),architectureTags=document.querySelector('#architectureTags'),architectureVisual=document.querySelector('#architectureVisual');
document.querySelectorAll('.architecture-node').forEach(node=>node.addEventListener('click',()=>{document.querySelectorAll('.architecture-node').forEach(item=>item.classList.remove('active'));node.classList.add('active');const data=architecture[node.dataset.architecture];architectureStep.textContent=data.step;architectureTitle.textContent=data.title;architectureDescription.textContent=data.description;architectureTags.innerHTML=data.tags.map(tag=>`<span>${tag}</span>`).join('');architectureVisual.classList.remove('mode-transition');void architectureVisual.offsetWidth;architectureVisual.classList.add('mode-transition');architectureVisual.innerHTML=`<div class="source-grid">${data.sources.map(source=>`<span>${source}</span>`).join('')}</div><div class="flow-core"><i></i><strong>${data.core}</strong><small>${data.small}</small></div><div class="data-pulse p1"></div><div class="data-pulse p2"></div><div class="data-pulse p3"></div>`}));

const dialog=document.querySelector('#demoDialog');
document.querySelectorAll('.demo-trigger').forEach(button=>button.addEventListener('click',()=>dialog.showModal()));
document.querySelector('.dialog-close').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close()});
document.querySelector('#demoForm').addEventListener('submit',event=>{event.preventDefault();dialog.close();event.currentTarget.reset();const toast=document.querySelector('.toast');toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),3200)});
const problemForm=document.querySelector('#problemForm');
if(problemForm)problemForm.addEventListener('submit',event=>{event.preventDefault();event.currentTarget.reset();const toast=document.querySelector('.toast');toast.textContent='Thanks — your manufacturing challenge has been received.';toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),3800)});

const glow=document.querySelector('.cursor-glow');
window.addEventListener('pointermove',event=>{glow.style.left=`${event.clientX}px`;glow.style.top=`${event.clientY}px`;glow.style.opacity='1'});
const heroImage=document.querySelector('.hero-image'),ctaImage=document.querySelector('.cta-landscape'),cta=document.querySelector('.cta-section');
// rAF-throttled parallax: one style write per frame, skipped off-screen and under reduced motion.
let parallaxQueued=false;
function runParallax(){
  parallaxQueued=false;
  const y=window.scrollY,vh=window.innerHeight;
  if(y<vh*1.2)heroImage.style.transform=`scale(1.035) translateY(${y*.06}px)`;
  const ctaTop=cta.offsetTop;
  if(y+vh>ctaTop&&y<ctaTop+cta.offsetHeight)ctaImage.style.backgroundPosition=`center calc(52% + ${(y-ctaTop)*.02}px)`;
}
if(!reduceMotion)window.addEventListener('scroll',()=>{
  if(!parallaxQueued){parallaxQueued=true;requestAnimationFrame(runParallax)}
},{passive:true});

// Fill the canvas instantly on load; the full animated run plays on first view.
fillInstant('deviation');
pokeAgentAutoplay();

// Layer-stack explorer (Pallet-style): scroll drives it, clicks override briefly.
const stackStep=document.querySelector('#stackStep'),stackTitle=document.querySelector('#stackTitle'),stackDesc=document.querySelector('#stackDesc');
const stackDetail=document.querySelector('.stack-detail');
let stackLockUntil=0;
function activateLayer(layer){
  if(!layer)return;
  document.querySelectorAll('.stack-layer').forEach(l=>{l.classList.remove('active');l.setAttribute('aria-selected','false')});
  layer.classList.add('active');layer.setAttribute('aria-selected','true');
  const data=architecture[layer.dataset.layer];if(!data)return;
  stackStep.textContent=data.step;stackTitle.textContent=data.title;stackDesc.textContent=data.description;
  if(stackDetail&&!reduceMotion){stackDetail.classList.remove('swap');void stackDetail.offsetWidth;stackDetail.classList.add('swap')}
}
document.querySelectorAll('.stack-layer').forEach(layer=>layer.addEventListener('click',()=>{stackLockUntil=Date.now()+4000;activateLayer(layer)}));
document.querySelectorAll('.stack-layer').forEach(layer=>new IntersectionObserver(es=>es.forEach(e=>{
  if(e.isIntersecting&&Date.now()>stackLockUntil)activateLayer(layer);
}),{rootMargin:'-40% 0px -40% 0px'}).observe(layer));
activateLayer(document.querySelector('.stack-layer.active'));

// Live-run video panel: a looping canvas reconstruction (24s). rAF-driven,
// paused off-screen, single static frame under reduced motion.
(function(){
  const canvas=document.querySelector('#runVideo');if(!canvas)return;
  const ctx=canvas.getContext('2d'),W=1280,H=520,LOOP=24,PADL=64,PADR=30,PADT=44,PADB=56;
  const caption=document.querySelector('#videoCaption'),prog=document.querySelector('#videoProgress'),
        toggle=document.querySelector('#videoToggle');
  const mDo=document.querySelector('#vmDo'),mPh=document.querySelector('#vmPh'),
        mTemp=document.querySelector('#vmTemp'),mClock=document.querySelector('#vmClock');
  const SCRIPT=[
    [0,'All systems streaming · 48 metrics unified'],
    [3,'Feed addition started · glucose set-point raised'],
    [8,'DO drifting below baseline — watching…'],
    [11,'Alert: DO 2.4σ below the prior 12-run mean · excursion isolated'],
    [14,'Agitation ↑ 180 → 220 rpm under approved response procedure'],
    [18,'DO recovering · probe calibration verified within tolerance'],
    [22,'Run back in envelope · evidence package assembled for QA'],
  ];
  const MARKS=[[3,'feed',0],[11,'DO −2.4σ',1],[14,'agit ↑',0]];
  const X=t=>PADL+(t/LOOP)*(W-PADL-PADR);
  const doV=t=>{let v=42+2*Math.sin(t*.9)+1.2*Math.sin(t*2.3+1);if(t>9&&t<19)v-=24*Math.sin((t-9)/10*Math.PI);return v};
  const phV=t=>7.02+.05*Math.sin(t*.7+.5)+.02*Math.sin(t*1.9);
  const tpV=t=>37+.25*Math.sin(t*.5+2)+.1*Math.sin(t*1.3);
  const doY=v=>PADT+(1-(v-8)/(52-8))*(H-PADT-PADB),
        phY=v=>PADT+(1-(v-6.85)/(7.2-6.85))*(H-PADT-PADB),
        tpY=v=>PADT+(1-(v-36.2)/(37.8-36.2))*(H-PADT-PADB);
  function trace(fn,y,color,until,alpha,width){
    ctx.beginPath();ctx.strokeStyle=color;ctx.globalAlpha=alpha;ctx.lineWidth=width;ctx.lineJoin='round';
    const steps=Math.max(2,Math.floor(until/LOOP*240));
    for(let i=0;i<=steps;i++){const t=i/240*LOOP,x=X(t),y0=y(fn(t));i?ctx.lineTo(x,y0):ctx.moveTo(x,y0)}
    ctx.stroke();ctx.globalAlpha=1;
  }
  function draw(t){
    ctx.clearRect(0,0,W,H);
    ctx.font='11px ui-monospace,Menlo,monospace';ctx.fillStyle='#718a82';ctx.lineWidth=1;
    for(let g=0;g<=4;g++){const y=PADT+g*(H-PADT-PADB)/4;
      ctx.strokeStyle='rgba(255,255,255,.07)';ctx.beginPath();ctx.moveTo(PADL,y);ctx.lineTo(W-PADR,y);ctx.stroke()}
    for(let s=0;s<=6;s++){const tt=s/6*LOOP;ctx.fillText('h'+(58+tt).toFixed(0),X(tt)-12,H-18)}
    const legend=[['#c9f75e','DO %'],['#56b6e1','pH'],['#f0a35e','Temp °C']];
    legend.forEach((l,i)=>{const x=PADL+i*110;
      ctx.strokeStyle=l[0];ctx.lineWidth=2.5;ctx.beginPath();ctx.moveTo(x,22);ctx.lineTo(x+26,22);ctx.stroke();
      ctx.fillStyle='#a7b7b1';ctx.fillText(l[1],x+32,26)});
    trace(doV,doY,'#c9f75e',LOOP,.28,1.5);trace(phV,phY,'#56b6e1',LOOP,.28,1.5);trace(tpV,tpY,'#f0a35e',LOOP,.28,1.5);
    const from=Math.max(0,t-6);
    ctx.save();ctx.beginPath();ctx.rect(X(from),0,X(t)-X(from)+2,H);ctx.clip();
    trace(doV,doY,'#c9f75e',t,1,2.5);trace(phV,phY,'#56b6e1',t,1,2.5);trace(tpV,tpY,'#f0a35e',t,1,2.5);
    ctx.restore();
    MARKS.forEach(m=>{if(m[0]>t)return;const x=X(m[0]);
      ctx.strokeStyle=m[2]?'rgba(240,68,56,.55)':'rgba(255,255,255,.22)';ctx.lineWidth=1.5;
      ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(x,PADT);ctx.lineTo(x,H-PADB);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=m[2]?'#f97066':'#a7b7b1';ctx.fillText(m[1],x+6,PADT+14)});
    const px=X(t);
    ctx.strokeStyle='rgba(255,255,255,.4)';ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(px,PADT-8);ctx.lineTo(px,H-PADB);ctx.stroke();
    [['#c9f75e',doY(doV(t))],['#56b6e1',phY(phV(t))],['#f0a35e',tpY(tpV(t))]].forEach(p=>{
      ctx.fillStyle=p[0];ctx.beginPath();ctx.arc(px,p[1],4.5,0,7);ctx.fill()});
    let cap=SCRIPT[0][1];SCRIPT.forEach(s=>{if(t>=s[0])cap=s[1]});
    if(caption.textContent!==cap)caption.textContent=cap;
    prog.style.width=(t/LOOP*100)+'%';
    const dv=doV(t).toFixed(1),pv=phV(t).toFixed(2),tv=tpV(t).toFixed(1),ck='h'+(58+t).toFixed(1);
    if(mDo.textContent!==dv)mDo.textContent=dv;
    if(mPh.textContent!==pv)mPh.textContent=pv;
    if(mTemp.textContent!==tv)mTemp.textContent=tv;
    if(mClock.textContent!==ck)mClock.textContent=ck;
  }
  let playing=true,visible=false,t0=null,elapsed=0;
  function frame(now){
    if(!playing)return;
    if(t0===null)t0=now;
    elapsed=((now-t0)/1000)%LOOP;
    if(visible)draw(elapsed);
    requestAnimationFrame(frame);
  }
  toggle.addEventListener('click',()=>{
    playing=!playing;
    toggle.textContent=playing?'❚❚':'▶';toggle.setAttribute('aria-label',playing?'Pause':'Play');
    if(playing){t0=null;requestAnimationFrame(frame)}
  });
  new IntersectionObserver(es=>es.forEach(e=>{visible=e.isIntersecting}),{threshold:.25})
    .observe(canvas.closest('.video-frame'));
  if(reduceMotion){draw(16);toggle.disabled=true}
  else requestAnimationFrame(frame);
})();
