'use strict';
let csrf='', paused=false, page=1, total=0, detailId=null, busy=false, logsVersion=0;
let loggingIn=false, syncing=false, environmentsLoading=true, loginRequired=true, activeTaskId=null, abortRequested=false;
function updateSyncButton(){const loading=syncing||environmentsLoading;const button=$('sync');button.disabled=loading||loginRequired;button.textContent=loading?'刷新中…':'刷新环境';button.classList.toggle('is-loading',loading);button.setAttribute('aria-busy',String(loading));$('environment-refreshing').hidden=!loading;$('environments').hidden=loading;$('environment-count').hidden=loading;$('active-environment').hidden=loading;if(loading)$('environments').replaceChildren();$('environments').setAttribute('aria-busy',String(loading));}
const collapsedEnvironmentGroups=new Set();
const labels={queued:'排队中',running:'执行中',awaiting_attention:'待人工处理',completed:'已完成',failed:'失败',cancelled:'已取消',expired:'文件已过期'};
const stages={queued:'等待领取',claimed:'已领取',reading_account:'读取环境绑定账号',starting_environment:'启动环境',opening_account:'打开 HubStudio 绑定账号',checking_login:'检查 TikTok 登录',logged_in:'登录成功',checking_language:'检查页面语言',switching_language:'切换简体中文',verifying_language:'核对切换后的语言',language_ready:'语言已就绪',language_failed:'语言检查失败',closing_account_menu:'关闭账号菜单',account_menu_closed:'账号菜单已关闭',upload_parsing:'等待表格解析',waiting_login:'等待 TikTok 登录',uploading:'上传表格',importing:'导入商品',imported:'导入成功',submitting:'正在提交',submitted:'已提交',manually_aborted:'人工中止',duplicate_file:'文件已存在，已中止',import_data_error:'添加商品失败（数据错误）',manual_attention:'等待人工处理',connection_lost:'连接中断',upgrade_review:'升级后待核对',manually_confirmed:'人工确认已提交',cancelled:'已取消',expired:'文件已过期'};
const stage=value=>stages[value]||value;
const $=id=>document.getElementById(id);
function node(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=String(text??'—');return el;}
function time(value){return value?new Date(value).toLocaleString('zh-CN'):'—';}
async function api(path,method='GET',body){const headers={};if(method!=='GET'){headers['Content-Type']='application/json';headers['X-CSRF-Token']=csrf;}const r=await fetch('/api/'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});const text=await r.text();let data;try{data=JSON.parse(text);}catch{throw Error(text||'请求失败');}if(!r.ok)throw Error(data.detail||'请求失败');return data;}
function table(el,columns,rows){el.replaceChildren();const head=node('tr');columns.forEach(c=>head.append(node('th',c)));const thead=node('thead');thead.append(head);el.append(thead);const body=node('tbody');rows.forEach(cells=>{const row=node('tr');cells.forEach(value=>{const cell=node('td');cell.append(value instanceof Node?value:node('span',value));row.append(cell);});body.append(row);});if(!rows.length){const row=node('tr'),cell=node('td','暂无记录');cell.colSpan=columns.length;row.append(cell);body.append(row);}el.append(body);}
function button(text,action){const b=node('button',text);b.addEventListener('click',()=>run(action));return b;}
async function run(action){$('error').textContent='';try{await action();}catch(e){$('error').textContent=e.message;}}
function renderActiveEnvironment(items){
  const summary=$('active-environment');
  summary.replaceChildren();
  const enabled=items.filter(e=>e.auto_upload_enabled);
  summary.classList.toggle('is-enabled',enabled.length>0);
  summary.append(node('span',enabled.length?'当前自动上品环境':'未开启自动上品'));
  for(const e of enabled){
    summary.append(node('strong',e.name||e.container_code));
    const serial=e.metadata_fields?.serial_number;
    summary.append(node('small',`${serial!=null?'序号：'+serial+' · ':''}环境 ID：${e.container_code}`));
    summary.append(node('div','账号：'+((e.account_names||[]).join('、')||'-')));
  }
  if(!enabled.length)summary.append(node('div','请在列表中开启一个环境后自动上品。'));
  summary.hidden=syncing||environmentsLoading;
}
async function renderEnvironments(){
  if(syncing)return;
  let items;
  try{items=await api('environments');}finally{environmentsLoading=false;updateSyncButton();}
  const el=$('environments');
  if(syncing)return;
  const count=$('environment-count');
  if(count)count.textContent=`共 ${items.length} 个环境`;
  renderActiveEnvironment(items);
  table(el,['序号','环境名称','账号','分组','自动上品'],[]);
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
      const b=button(e.auto_upload_enabled?'已开启':'已关闭',async()=>{
        const enabled=!e.auto_upload_enabled;
        if(enabled&&!confirm('确认此环境属于 TikTok 店铺，并设为本机唯一自动上品环境？此前启用的环境会自动关闭。'))return;
        await api('environments/'+encodeURIComponent(e.container_code)+'/auto-upload','PUT',{enabled,confirmed_local:enabled});
        await renderEnvironments();
      });
      b.className=e.auto_upload_enabled?'environment-enable':'environment-disable';
      b.title=e.auto_upload_enabled?'当前已开启，点击关闭':'当前已关闭，点击开启';
      const row=node('tr');
      if(e.auto_upload_enabled)row.className='environment-active';
      for(const value of [identity,e.name,(e.account_names||[]).join('、')||'-',group,b]){const cell=node('td');cell.append(value instanceof Node?value:node('span',value));row.append(cell);}
      body.append(row);
    }
  }
}
const pendingTaskActions=new Set();
async function actOnTask(t,action){
  if(pendingTaskActions.has(t.id))return;
  const message=action==='abort'?'停止任务 #'+t.id+' 并暂停领取新任务？平台可能已收到文件或导入，请在停止后核对结果。':action==='retry'?'已核对平台，确认未重复提交并重新执行原 XLSX？':action==='confirm-submitted'?'已核对平台，确认这批商品已提交？':'确认取消此任务？';
  if(!confirm(message))return;
  pendingTaskActions.add(t.id);
  try{await renderTasks();await api('tasks/'+t.id+'/'+action,'POST',action==='abort'?{}:{confirmed_platform_checked:action!=='cancel'});if(action==='abort')await refresh();}
  finally{pendingTaskActions.delete(t.id);await renderTasks();await renderDetail();}
}
async function renderTasks(){
  const filter=$('filter').value;
  const result=await api('tasks?page='+page+'&page_size=25'+(filter?'&status='+encodeURIComponent(filter):''));
  total=result.total;
  table($('tasks'),['任务','目标环境','创建时间','状态 / 阶段','异常原因','操作'],result.items.map(t=>{
    const status=node('div');status.append(node('span',t.stage==='imported'?'导入成功':(labels[t.status]||t.status)),node('small',stage(t.stage)));
    const actions=node('div');actions.className='task-actions';
    actions.append(button('详情',async()=>{detailId=t.id;await renderDetail();}));
    function addAction(label,action){const b=button(label,()=>actOnTask(t,action));b.disabled=pendingTaskActions.has(t.id);actions.append(b);}
    if(t.status==='running'){
      const local=String(t.id)===String(activeTaskId);
      const stopping=local&&(abortRequested||pendingTaskActions.has(t.id));
      const stop=button(stopping?'正在停止…':'停止',()=>actOnTask(t,'abort'));
      stop.disabled=!local||stopping;
      stop.title=local?'停止本机执行并暂停领取新任务':'请在执行此任务的电脑上停止';
      actions.append(stop);
    }
    if(['awaiting_attention','failed'].includes(t.status)){
      if(!t.file_expired&&t.stage!=='import_data_error')addAction('重试','retry');
      addAction('确认已提交','confirm-submitted');
    }
    if(['queued','awaiting_attention','failed'].includes(t.status))addAction('取消','cancel');
    return ['#'+t.id,t.environment_name||'等待本机选择环境',time(t.created_at),status,t.failure_reason||'—',actions];
  }));
  $('page').textContent=`第 ${page} 页 · ${total} 条`;$('previous').disabled=page<=1;$('next').disabled=page*25>=total;
}
async function renderDetail(){if(!detailId)return;const id=detailId;const t=await api('tasks/'+id);if(detailId!==id)return;if(!$('detail').open)$('detail').showModal();$('detail-title').textContent=`任务 #${t.id} · ${t.stage==='imported'?'导入成功':(labels[t.status]||t.status)}`;const content=$('detail-content');content.replaceChildren(node('p',`${t.environment_name||'等待本机选择环境'} · ${t.export_filename}`));function logs(entries){return node('pre',(entries||[]).map(l=>`${time(l.at)} [${stage(l.stage)}] ${l.message}`).join('\n')||'暂无日志');}if(t.export_expires_at)content.append(node('p',`Excel 有效期至 ${time(t.export_expires_at)}${t.file_expired?'（已过期，请重新生成）':''}`));content.append(node('h3','任务日志'),logs(t.logs));for(const a of t.attempts||[]){content.append(node('h3',`第 ${a.number} 次执行 · ${a.environment_name||'历史环境'} · ${a.agent_name||'未知电脑'} · ${a.stage==='imported'?'导入成功':(labels[a.status]||a.status)}`),logs(a.logs));}if(t.resolved_at)content.append(node('p',`人工处理：账号 #${t.resolved_by} · ${time(t.resolved_at)}`));}

async function refresh(){if(busy)return;busy=true;try{const s=await api('status');csrf=s.csrf;paused=s.paused;activeTaskId=s.active_task_id;abortRequested=!!s.abort_requested;$('login-section').hidden=!s.login_required;$('login-button').disabled=loggingIn;$('pause').disabled=!!s.login_required;loginRequired=!!s.login_required;updateSyncButton();$('filter').disabled=!!s.login_required;$('status').textContent=`${s.user?.name||'等待 ERP 登录'} · ${s.status||'正在启动'} · ERP ${s.erp_connected?'已连接':'未连接'} · HubStudio ${s.hub_connected?'已连接':'未连接'}`;$('pause').textContent=paused?'继续领取':'暂停领取';$('sync-status').textContent=s.sync_error||`最近完整同步：${time(s.sync_at)}`;await renderEnvironments();if(s.user&&!s.login_required){await renderTasks();await renderDetail();}else{detailId=null;$('detail').close();$('tasks').replaceChildren();$('page').textContent='登录后查看任务';$('previous').disabled=true;$('next').disabled=true;}await renderLogs();$('error').textContent='';}catch(e){$('error').textContent=e.message;}finally{busy=false;}}
$('login-form').onsubmit=async event=>{event.preventDefault();if(loggingIn||!csrf)return;loggingIn=true;$('login-button').disabled=true;$('login-button').textContent='正在登录…';$('login-error').textContent='';const password=$('password').value;$('password').value='';try{await api('login','POST',{email:$('email').value,password});await refresh();}catch(e){$('login-error').textContent=e.message;}finally{loggingIn=false;$('login-button').disabled=false;$('login-button').textContent='登录并授权';}};
$('sync').onclick=()=>run(async()=>{if(syncing||loginRequired)return;syncing=true;updateSyncButton();try{const r=await api('sync','POST',{});if(!r.ok)throw Error(r.detail||'环境刷新失败');await refresh();}finally{syncing=false;updateSyncButton();await renderEnvironments();}});$('pause').onclick=()=>run(async()=>{await api('pause','POST',{paused:!paused});await refresh();});$('filter').onchange=()=>run(async()=>{page=1;await renderTasks();});$('previous').onclick=()=>run(async()=>{page--;await renderTasks();});$('next').onclick=()=>run(async()=>{page++;await renderTasks();});$('close-detail').onclick=()=>{detailId=null;$('detail').close();};$('detail').addEventListener('close',()=>{detailId=null;});$('detail').addEventListener('click',event=>{if(event.target===$('detail')){const box=$('detail').getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom){detailId=null;$('detail').close();}}});refresh();setInterval(refresh,5000);

$('copy-logs').onclick=()=>run(async()=>{await navigator.clipboard.writeText($('logs').textContent);$('log-feedback').textContent='运行日志已复制';});
$('clear-logs').onclick=()=>run(async()=>{const button=$('clear-logs');button.disabled=true;try{logsVersion++;await api('logs/clear','POST',{});await renderLogs();$('log-feedback').textContent='本机运行日志已清除';}finally{button.disabled=false;}});

async function renderLogs(){const version=logsVersion;const result=await api('logs');if(version===logsVersion)$('logs').textContent=result.lines.join('\n');}
