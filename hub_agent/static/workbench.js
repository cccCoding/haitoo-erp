'use strict';
let csrf='', paused=false, page=1, total=0, detailId=null, busy=false;
let loggingIn=false, syncing=false, loginRequired=true;
function updateSyncButton(){const button=$('sync');button.disabled=syncing||loginRequired;button.textContent=syncing?'同步中…':'同步环境';button.classList.toggle('is-loading',syncing);button.setAttribute('aria-busy',String(syncing));}
const collapsedEnvironmentGroups=new Set();
const labels={queued:'排队中',running:'执行中',awaiting_attention:'待人工处理',completed:'已提交',failed:'失败',cancelled:'已取消',expired:'文件已过期'};
const stages={queued:'等待领取',claimed:'已领取',starting_environment:'启动环境',uploading:'上传表格',submitting:'正在提交',submitted:'已提交',manual_attention:'等待人工处理',connection_lost:'连接中断',upgrade_review:'升级后待核对',manually_confirmed:'人工确认已提交',cancelled:'已取消',expired:'文件已过期'};
const stage=value=>stages[value]||value;
const $=id=>document.getElementById(id);
function node(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=String(text??'—');return el;}
function time(value){return value?new Date(value).toLocaleString('zh-CN'):'—';}
async function api(path,method='GET',body){const headers={};if(method!=='GET'){headers['Content-Type']='application/json';headers['X-CSRF-Token']=csrf;}const r=await fetch('/api/'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});const text=await r.text();let data;try{data=JSON.parse(text);}catch{throw Error(text||'请求失败');}if(!r.ok)throw Error(data.detail||'请求失败');return data;}
function table(el,columns,rows){el.replaceChildren();const head=node('tr');columns.forEach(c=>head.append(node('th',c)));const thead=node('thead');thead.append(head);el.append(thead);const body=node('tbody');rows.forEach(cells=>{const row=node('tr');cells.forEach(value=>{const cell=node('td');cell.append(value instanceof Node?value:node('span',value));row.append(cell);});body.append(row);});if(!rows.length){const row=node('tr'),cell=node('td','暂无记录');cell.colSpan=columns.length;row.append(cell);body.append(row);}el.append(body);}
function button(text,action){const b=node('button',text);b.addEventListener('click',()=>run(action));return b;}
async function run(action){$('error').textContent='';try{await action();}catch(e){$('error').textContent=e.message;}}
async function renderEnvironments(){
  const items=await api('environments'),el=$('environments');
  const count=$('environment-count');
  if(count)count.textContent=`共 ${items.length} 个环境`;
  table(el,['序号','环境名称','分组','标签','自动上品'],[]);
  if(!items.length)return;
  el.querySelector('tbody').remove();
  const groups=new Map();
  for(const e of items){
    const group=String(e.metadata_fields?.group??'').trim()||'未分组';
    if(!groups.has(group))groups.set(group,[]);
    groups.get(group).push(e);
  }
  let index=0;
  for(const [group,environments] of groups){
    const heading=node('tbody'),groupRow=node('tr'),groupCell=node('td');
    groupRow.className='environment-group';groupCell.colSpan=5;
    const body=node('tbody');body.id='environment-group-'+index++;
    body.hidden=collapsedEnvironmentGroups.has(group);
    const toggle=node('button');toggle.type='button';toggle.className='group-toggle';
    toggle.setAttribute('aria-controls',body.id);
    const arrow=node('span');arrow.className='group-arrow';arrow.setAttribute('aria-hidden','true');
    toggle.append(arrow,node('span',`${group}（${environments.length}）`));
    function update(){toggle.setAttribute('aria-expanded',String(!body.hidden));arrow.textContent=body.hidden?'▸':'▾';}
    update();
    toggle.addEventListener('click',()=>{body.hidden=!body.hidden;if(body.hidden)collapsedEnvironmentGroups.add(group);else collapsedEnvironmentGroups.delete(group);update();});
    groupCell.append(toggle);groupRow.append(groupCell);heading.append(groupRow);el.append(heading,body);
    for(const e of environments){
      const metadata=e.metadata_fields||{},identity=node('div');identity.className='environment-identity';
      identity.append(node('span',metadata.serial_number??'—'));
      const id=node('small',e.container_code);id.className='environment-id';identity.append(id);
      const tags=node('div');tags.className='environment-tags';
      const values=Array.isArray(metadata.labels)?metadata.labels:(metadata.labels?[metadata.labels]:[]);
      if(values.length){for(const value of values){const tag=node('span',value);tag.className='badge';tags.append(tag);}}else tags.append(node('span','—'));
      const b=button(e.auto_upload_enabled?'已开启 · 关闭':'开启',async()=>{
        const enabled=!e.auto_upload_enabled;
        if(enabled&&!confirm('确认此环境属于 TikTok 店铺，并设为本机唯一自动上品环境？此前启用的环境会自动关闭。'))return;
        await api('environments/'+encodeURIComponent(e.container_code)+'/auto-upload','PUT',{enabled,confirmed_local:enabled});
        await renderEnvironments();
      });
      const row=node('tr');
      for(const value of [identity,e.name,group,tags,b]){const cell=node('td');cell.append(value instanceof Node?value:node('span',value));row.append(cell);}
      body.append(row);
    }
  }
}
async function renderTasks(){const filter=$('filter').value;const result=await api('tasks?page='+page+'&page_size=25'+(filter?'&status='+encodeURIComponent(filter):''));total=result.total;table($('tasks'),['任务','目标环境','状态 / 阶段','创建时间','执行电脑','异常原因','操作'],result.items.map(t=>{const status=node('div');status.append(node('span',labels[t.status]||t.status),node('small',stage(t.stage)));return['#'+t.id,t.environment_name||'等待本机选择环境',status,time(t.created_at),t.agent_name||'尚未领取',t.failure_reason||'—',button('查看日志',async()=>{detailId=t.id;await renderDetail();$('detail').scrollIntoView({behavior:'smooth',block:'start'});})];}));$('page').textContent=`第 ${page} 页 · ${total} 条`;$('previous').disabled=page<=1;$('next').disabled=page*25>=total;}
async function renderDetail(){if(!detailId)return;const t=await api('tasks/'+detailId);$('detail').hidden=false;$('detail-title').textContent=`任务 #${t.id} · ${labels[t.status]||t.status}`;const content=$('detail-content');content.replaceChildren(node('p',`${t.environment_name||'等待本机选择环境'} · ${t.export_filename}`));function logs(entries){return node('pre',(entries||[]).map(l=>`${time(l.at)} [${stage(l.stage)}] ${l.message}`).join('\n')||'暂无日志');}if(t.export_expires_at)content.append(node('p',`Excel 有效期至 ${time(t.export_expires_at)}${t.file_expired?'（已过期，请重新生成）':''}`));content.append(node('h3','任务日志'),logs(t.logs));for(const a of t.attempts||[]){content.append(node('h3',`第 ${a.number} 次执行 · ${a.environment_name||'历史环境'} · ${a.agent_name||'未知电脑'} · ${labels[a.status]||a.status}`),logs(a.logs));}if(t.resolved_at)content.append(node('p',`人工处理：账号 #${t.resolved_by} · ${time(t.resolved_at)}`));const actions=$('actions');actions.replaceChildren();async function act(action){const message=action==='retry'?'已核对平台，确认未重复提交并重新执行原 XLSX？':action==='confirm-submitted'?'已核对平台，确认这批商品已提交？':'确认取消此任务？';if(!confirm(message))return;await api('tasks/'+t.id+'/'+action,'POST',{confirmed_platform_checked:action!=='cancel'});await renderTasks();await renderDetail();}if(['awaiting_attention','failed'].includes(t.status)){if(!t.file_expired)actions.append(button('核对后重试',()=>act('retry')));actions.append(button('确认已提交',()=>act('confirm-submitted')));}if(['queued','awaiting_attention','failed'].includes(t.status))actions.append(button('取消任务',()=>act('cancel')));}
async function refresh(){if(busy)return;busy=true;try{const s=await api('status');csrf=s.csrf;paused=s.paused;$('login-section').hidden=!s.login_required;$('login-button').disabled=loggingIn;$('pause').disabled=!!s.login_required;loginRequired=!!s.login_required;updateSyncButton();$('filter').disabled=!!s.login_required;$('status').textContent=`${s.user?.name||'等待 ERP 登录'} · ${s.status||'正在启动'} · ERP ${s.erp_connected?'已连接':'未连接'} · HubStudio ${s.hub_connected?'已连接':'未连接'}`;$('pause').textContent=paused?'继续领取':'暂停领取';$('sync-status').textContent=s.sync_error||`最近完整同步：${time(s.sync_at)}`;await renderEnvironments();if(s.user&&!s.login_required){await renderTasks();await renderDetail();}else{detailId=null;$('detail').hidden=true;$('tasks').replaceChildren();$('page').textContent='登录后查看任务';$('previous').disabled=true;$('next').disabled=true;}$('logs').textContent=(await api('logs')).lines.join('\n');$('error').textContent='';}catch(e){$('error').textContent=e.message;}finally{busy=false;}}
$('login-form').onsubmit=async event=>{event.preventDefault();if(loggingIn||!csrf)return;loggingIn=true;$('login-button').disabled=true;$('login-button').textContent='正在登录…';$('login-error').textContent='';const password=$('password').value;$('password').value='';try{await api('login','POST',{email:$('email').value,password});await refresh();}catch(e){$('login-error').textContent=e.message;}finally{loggingIn=false;$('login-button').disabled=false;$('login-button').textContent='登录并授权';}};
$('sync').onclick=()=>run(async()=>{if(syncing||loginRequired)return;syncing=true;updateSyncButton();try{const r=await api('sync','POST',{});if(!r.ok)throw Error(r.detail||'环境刷新失败');await refresh();}finally{syncing=false;updateSyncButton();}});$('pause').onclick=()=>run(async()=>{await api('pause','POST',{paused:!paused});await refresh();});$('filter').onchange=()=>run(async()=>{page=1;await renderTasks();});$('previous').onclick=()=>run(async()=>{page--;await renderTasks();});$('next').onclick=()=>run(async()=>{page++;await renderTasks();});$('close-detail').onclick=()=>{detailId=null;$('detail').hidden=true;};refresh();setInterval(refresh,5000);
