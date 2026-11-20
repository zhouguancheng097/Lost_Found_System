'use strict';
const state = {user:null,csrf:'',categories:[],page:'home',searchPage:1,register:false,editing:null,images:[],total:0};
const element = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const labels = {PENDING:'待审核',REJECTED:'已驳回',OPEN:'进行中',HANDOVER:'交接中',CLAIMED:'已领取',RESOLVED:'已找回',CLOSED:'已关闭',APPROVED:'审核通过',WITHDRAWN:'已撤回',COMPLETED:'领取完成',CANCELLED:'已取消',ACTIVE:'正常',BANNED:'已封禁',DELETED:'已注销'};
const symbols = {'证件卡片':'▤','数码电子':'▣','钥匙':'⚿','包袋':'▱','衣物配饰':'♧','水杯餐具':'♜','雨伞':'☂','书籍文具':'▥','其他':'◇'};
const badge = status => `<span class="badge ${escapeHtml(status)}">${escapeHtml(labels[status] || status)}</span>`;
let toastTimer;
function toast(message,error=false){element('toast').textContent=message;element('toast').className=`toast${error?' error':''}`;clearTimeout(toastTimer);toastTimer=setTimeout(()=>element('toast').classList.add('hidden'),5000);}
async function api(path,options={}){
  const method=options.method||'GET';const headers={...options.headers};
  if(method!=='GET')headers['X-CSRF-Token']=state.csrf;
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response=await fetch(path,{...options,headers});let result;
  try{result=await response.json();}catch{throw new Error('服务返回异常，请稍后重试');}
  if(!response.ok){
    const authRequest=['/api/login','/api/register'].includes(path);
    if(response.status===401&&!authRequest){
      const message=state.user||result.error?.includes('过期')?'登录态过期，请重新登录后再操作':'请先登录后再操作';
      state.user=null;state.csrf='';renderAccount();
      try{await session();}catch{}
      showLogin(message);throw new Error(message);
    }
    throw new Error(result.error||'操作失败');
  }return result;
}
async function session(){const result=await api('/api/session');state.user=result.user;state.csrf=result.csrf;state.categories=result.categories;renderAccount();}
function renderAccount(){element('user-name').textContent=state.user?state.user.display_name:'';element('auth-button').classList.toggle('hidden',!!state.user);element('logout').classList.toggle('hidden',!state.user);document.querySelectorAll('.admin-only').forEach(node=>node.classList.toggle('hidden',state.user?.role!=='ADMIN'));}
function setAuthMode(register){state.register=register;element('auth-title').textContent=register?'加入拾光':'欢迎回到拾光';element('auth-submit').textContent=register?'创建账号':'登录';element('display-label').classList.toggle('hidden',!register);element('auth-form').elements.display_name.required=register;element('auth-toggle').textContent=register?'已有账号？返回登录':'还没有账号？立即注册';element('auth-form').elements.password.autocomplete=register?'new-password':'current-password';}
function authNotice(message=''){element('auth-notice').textContent=message;element('auth-notice').classList.toggle('hidden',!message);}
function showLogin(message=''){setAuthMode(false);authNotice(message);if(!element('auth-dialog').open)element('auth-dialog').showModal();}
async function requireLogin(){const wasLoggedIn=!!state.user;await session();if(state.user)return true;const message=wasLoggedIn?'登录态过期，请重新登录后再操作':'请先登录后再操作';showLogin(message);if(wasLoggedIn)toast(message,true);return false;}
function empty(title,description){return `<div class="empty"><span>⌕</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p><button class="button outline" data-action="publish">发布一份线索</button></div>`;}
function button(label,action,id,extra=''){return `<button class="button outline" data-action="${action}" data-id="${id}" ${extra}>${label}</button>`;}
function card(item,own=false){
  const image=item.images?.[0];const status=item.status==='OPEN'?(item.type==='LOST'?'寻找中':'待认领'):(labels[item.status]||item.status);
  let actions='';
  if(own){if(['PENDING','REJECTED','OPEN'].includes(item.status))actions+=button('编辑','edit',item.id);if(!['CLAIMED','RESOLVED','CLOSED'].includes(item.status))actions+=button('关闭','close',item.id);actions+=button('删除','delete',item.id);if(item.status==='OPEN'){actions+=button('查看匹配','matches',item.id);if(item.type==='LOST')actions+=button('已找回','resolve',item.id);}}
  return `<article class="item-card" data-open="${item.id}" tabindex="0" aria-label="查看${escapeHtml(item.title)}"><div class="card-visual" data-type="${escapeHtml(item.type)}">${image?`<img src="/media/${image}" alt="${escapeHtml(item.title)}" loading="lazy">`:`<span class="object-symbol">${symbols[item.category]||'◇'}</span>`}<span class="card-label ${item.type==='LOST'?'lost':''}">${item.type==='LOST'?'寻物启事':'招领启事'}</span></div><div class="card-body"><div class="card-title-row"><h3>${escapeHtml(item.title)}</h3><span class="badge ${escapeHtml(item.status)}">${escapeHtml(status)}</span></div><p class="card-description">${escapeHtml(item.description)}</p><div class="card-meta"><span>⌖ ${escapeHtml(item.location)}</span><span>${escapeHtml(item.event_date)}</span></div>${item.score!==undefined?`<div class="match-reasons">${item.nearby?'相近信息':'相关程度'} ${item.score} · ${escapeHtml((item.reasons||[]).join(' / '))}</div>`:''}<div class="card-bottom"><span>${escapeHtml(item.category)} · ${escapeHtml(item.owner_name||state.user?.display_name||'校园用户')}</span><span>查看详情 ↗</span></div>${actions?`<div class="card-actions">${actions}</div>`:''}</div></article>`;
}
function cards(items,own=false){return items.length?`<div class="cards">${items.map(item=>card(item,own)).join('')}</div>`:empty('线索还在路上','暂时没有相关记录。试试放宽条件，或发布信息让更多人看见。');}
function setTitle(title,info=''){element('section-title').textContent=title;element('result-info').textContent=info;}
async function navigate(page){
  if(page!=='home'&&!await requireLogin())return;
  state.page=page;document.querySelectorAll('.nav').forEach(node=>node.classList.toggle('active',node.dataset.page===page||(page.startsWith('admin-')&&node.dataset.page==='admin-items')));
  const home=page==='home';element('hero').classList.toggle('hidden',!home);element('search-panel').classList.toggle('hidden',!home);element('admin-tabs').classList.toggle('hidden',!page.startsWith('admin-'));element('account-actions').classList.toggle('hidden',page!=='mine'||state.user?.role==='ADMIN');element('pagination').innerHTML='';element('mode-note').textContent='';element('content').innerHTML='<div class="loading">正在整理线索…</div>';
  try{
    if(home){await loadSearch();return;}
    if(page==='mine'){const items=await api('/api/mine/items');setTitle('我的发布',`${items.length} 条记录`);element('content').innerHTML=cards(items,true);return;}
    if(page==='claims'){const claims=await api('/api/mine/claims');setTitle('我的申领',`${claims.length} 条申请`);element('content').innerHTML=claims.length?claims.map(claim=>claimRow(claim,false)).join(''):empty('还没有申领记录','在招领信息详情页提交证明，管理员审核通过后再安排交接。');return;}
    if(page==='notifications'){const messages=await api('/api/notifications');setTitle('站内消息',`${messages.filter(message=>!message.is_read).length} 条未读`);element('content').innerHTML=messages.length?button('全部标为已读','read','')+messages.map(message=>`<article class="list-row ${message.is_read?'':'unread'}"><p>${escapeHtml(message.message)}</p><span class="muted">${escapeHtml(new Date(message.created_at).toLocaleString())}</span></article>`).join(''):empty('暂时没有新消息','审核和申领有进展时，会在这里告诉你。');return;}
    await loadAdmin(page.replace('admin-',''));
  }catch(error){element('content').innerHTML=empty('暂时无法读取',error.message);toast(error.message,true);}
}
async function loadSearch(){
  const filters=new URLSearchParams(new FormData(element('search-form')));filters.set('page',state.searchPage);const result=await api('/api/items?'+filters);state.total=result.total;
  setTitle('正在寻找的相遇',`${result.total} 条线索`);element('content').innerHTML=cards(result.items);
  element('mode-note').textContent=result.mode==='hybrid'?'已过滤低相关结果 · 语义与关键词综合匹配，相关分仅供寻找参考':result.mode==='keyword'?'已过滤低相关结果 · 当前使用关键词检索，语义服务暂不可用。':'按最近更新展示 · 已领取信息可在状态筛选中查看';
  const hints=result.suggestions||{};const hintText=[hints.category,hints.location,hints.date].filter(Boolean).join(' · ');element('suggestions').classList.toggle('hidden',!hintText);element('suggestions').innerHTML=hintText?`识别到线索：${escapeHtml(hintText)} ${button('应用建议筛选','apply-hints','')}`:'';state.hints=hints;
  const pages=Math.ceil(result.total/result.pageSize);element('pagination').innerHTML=pages>1?`${button('上一页','prev','',state.searchPage===1?'disabled':'')}<span>${state.searchPage} / ${pages}</span>${button('下一页','next','',state.searchPage>=pages?'disabled':'')}`:'';
}
function claimRow(claim,admin){
  let actions=button('物品详情','detail',claim.item_id);
  if(!admin&&claim.status==='PENDING')actions+=button('撤回申请','withdraw',claim.id);
  if(admin&&claim.status==='PENDING')actions+=button('批准交接','claim-approve',claim.id)+button('驳回','claim-reject',claim.id);
  if(admin&&claim.status==='APPROVED')actions+=button('确认已交接','claim-complete',claim.id)+button('取消交接','claim-cancel',claim.id);
  return `<article class="list-row"><h3>${escapeHtml(claim.title)} ${badge(claim.status)}</h3><p class="muted">申请人：${escapeHtml(claim.applicant_name)} · ${escapeHtml(new Date(claim.created_at).toLocaleString())}</p><p>申领证明：${escapeHtml(claim.proof)}</p>${claim.proof_attachment_id?`<a href="/media/${claim.proof_attachment_id}" target="_blank" rel="noopener">查看受保护的证明图片 ↗</a>`:''}${claim.review_note?`<p>处理说明：${escapeHtml(claim.review_note)}</p>`:''}<div>${actions}</div></article>`;
}
async function loadAdmin(section){
  const rows=await api('/api/admin/'+section);const titles={items:'全部信息与审核',claims:'申领核验与交接',users:'账号管理',logs:'操作记录'};setTitle(titles[section],`${rows.length} 条记录`);
  element('content').innerHTML=rows.length?rows.map(row=>{
    if(section==='claims')return claimRow(row,true);
    if(section==='users')return `<article class="list-row"><h3>${escapeHtml(row.display_name)} ${badge(row.status)}</h3><p class="muted">${escapeHtml(row.username)} · ${row.role==='ADMIN'?'管理员':'普通用户'} · 编号 ${row.id}</p>${row.ban_reason?`<p>${escapeHtml(row.ban_reason)}</p>`:''}${row.role==='USER'&&row.status!=='DELETED'?button(row.status==='BANNED'?'解锁':'封禁',row.status==='BANNED'?'user-unlock':'user-ban',row.id)+button('注销账号','user-delete',row.id):''}</article>`;
    if(section==='logs')return `<article class="list-row"><h3>${escapeHtml(row.action)} <span class="muted">${escapeHtml(row.target_type)} #${row.target_id}</span></h3><p>${escapeHtml(row.actor_name)} · ${escapeHtml(new Date(row.created_at).toLocaleString())}</p><p>${escapeHtml(row.reason)}</p></article>`;
    return `<article class="list-row"><h3>${escapeHtml(row.title)} ${badge(row.status)}</h3><p class="muted">${escapeHtml(row.owner_name)} · ${escapeHtml(row.category)} · ${escapeHtml(row.location)}</p><p>${escapeHtml(row.description)}</p>${button('详情与隐藏特征','detail',row.id)}${button('编辑','edit',row.id)}${row.status==='PENDING'?button('审核通过','review-approve',row.id)+button('驳回','review-reject',row.id):''}${!['CLOSED','RESOLVED','CLAIMED'].includes(row.status)?button('关闭并结束申领','close',row.id):''}${button('删除','delete',row.id)}</article>`;
  }).join(''):empty('当前列表为空','新的发布、申请或管理记录会出现在这里。');
}
async function openDetail(id){
  const item=await api('/api/items/'+id);element('detail-content').innerHTML=`<div>${badge(item.status)} <span class="muted">${item.type==='LOST'?'寻物启事':'招领启事'} · ${escapeHtml(item.category)}</span></div><h3 class="detail-title">${escapeHtml(item.title)}</h3><div class="detail-meta"><span>⌖ ${escapeHtml(item.location)}</span><span>${escapeHtml(item.event_date)}</span><span>发布者：${escapeHtml(item.owner_name)}</span><span>${item.claim_count} 人次申领</span></div><div class="detail-photos">${(item.images||[]).map(image=>`<a href="/media/${image}" target="_blank" rel="noopener"><img src="/media/${image}" alt="物品公开图片"></a>`).join('')}</div><div class="detail-description">${escapeHtml(item.description)}</div>${item.contact?`<div class="private-info">联系方式：${escapeHtml(item.contact)}</div>`:'<p class="muted">联系方式将在申领审核通过后向申领人开放。</p>'}${item.hidden_features?`<div class="private-info">隐藏核验特征：${escapeHtml(item.hidden_features)}</div>`:''}${item.review_note?`<p class="muted">审核说明：${escapeHtml(item.review_note)}</p>`:''}${item.type==='FOUND'&&item.status==='OPEN'&&state.user?.id!==item.owner_id?`<form id="claim-form" class="stack" data-item="${id}"><h3>这是你遗失的物品？</h3><label>申领证明 · 仅本人和管理员可见<textarea name="proof" required minlength="10" maxlength="1500" rows="3" placeholder="请提供遗失时间、地点和未公开的特征，帮助管理员核验。"></textarea></label><label>证明图片（可选，JPEG / PNG）<input name="photo" type="file" accept="image/jpeg,image/png"></label><button class="button primary" type="submit">提交申领申请</button><p class="muted">同一物品可以有多位申请人，最终交接由管理员核验确认。</p></form>`:''}`;
  if(!element('detail-dialog').open)element('detail-dialog').showModal();
}
async function openPublish(id){if(!await requireLogin())return;const form=element('publish-form');form.reset();state.editing=id||null;state.images=[];element('publish-title').textContent=id?'修改信息 · 重新审核':'发布一份线索';if(id){const item=await api('/api/items/'+id);for(const key of ['type','category','title','description','location','event_date','contact','hidden_features'])form.elements[key].value=item[key]||'';state.images=item.images||[];}else form.elements.event_date.value=localDate();element('publish-dialog').showModal();}
function localDate(){const date=new Date();return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;}
async function upload(file,kind){if(file.size>5242880)throw new Error('单张图片不能超过 5MB');const data=new FormData();data.append('file',file);return (await api('/api/uploads?kind='+kind,{method:'POST',body:data})).id;}
async function action(action,id){
  if(action==='publish'){await openPublish();return;}if(action==='detail'){await openDetail(id);return;}if(action==='edit'){await openPublish(id);return;}
  if(action==='prev'||action==='next'){state.searchPage+=action==='prev'?-1:1;await loadSearch();return;}
  if(action==='apply-hints'){const form=element('search-form');for(const key of ['category','location'])if(state.hints[key])form.elements[key].value=state.hints[key];if(state.hints.date){form.elements.from.value=state.hints.date;form.elements.to.value=state.hints.date;}state.searchPage=1;await loadSearch();return;}
  if(action==='matches'){const result=await api('/api/items/'+id+'/matches');element('detail-content').innerHTML=`<p class="muted">根据类别、描述、地点与事件日期推荐，最终仍需核验。</p>${cards(result.items)}`;element('detail-dialog').showModal();return;}
  if(action==='read'){await api('/api/notifications/read',{method:'POST'});await navigate('notifications');return;}
  let path,method='POST',body={};
  if(['close','delete','resolve'].includes(action)){if(!confirm(action==='delete'?'确认删除这条信息？':'确认结束这条信息？关闭时管理员将同时结束未完成的申领。'))return;path='/api/items/'+id+(action==='delete'?'':'/'+action);if(action==='delete')method='DELETE';}
  else if(action==='withdraw'){if(!confirm('确认撤回申请？'))return;path='/api/claims/'+id+'/withdraw';}
  else if(action.startsWith('review-')){const approve=action==='review-approve';const reason=prompt(approve?'审核说明（可留空）':'请填写驳回原因','');if(reason===null)return;path='/api/admin/items/'+id+'/review';body={approve,reason};}
  else if(action.startsWith('claim-')){const operation=action.slice(6);if(operation==='complete'&&!confirm('请确认物品已经线下交接完成，再标记已领取。'))return;const reason=prompt('处理说明'+(['reject','cancel'].includes(operation)?'（必填）':'（可留空）'),'');if(reason===null)return;path='/api/admin/claims/'+id+'/'+operation;body={reason};}
  else if(action.startsWith('user-')){const reason=prompt('请填写账号处理原因。注销前必须先结束该用户进行中的业务。','');if(reason===null)return;path='/api/admin/users/'+id+'/'+action.slice(5);body={reason};}
  if(path){await api(path,{method,body});toast('操作已完成');await navigate(state.page);}
}
document.addEventListener('click',async event=>{try{const close=event.target.closest('[data-close]');if(close){element(close.dataset.close).close();return;}const page=event.target.closest('[data-page]');if(page){await navigate(page.dataset.page);return;}const control=event.target.closest('[data-action]');if(control){event.stopPropagation();await action(control.dataset.action,control.dataset.id);return;}const item=event.target.closest('[data-open]');if(item)await openDetail(item.dataset.open);}catch(error){toast(error.message,true);}});
document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches('[data-open]'))event.target.click();});
element('auth-button').onclick=async()=>{try{await session();showLogin();}catch(error){toast(error.message,true);}};
element('auth-toggle').onclick=()=>{setAuthMode(!state.register);authNotice();};
element('auth-form').onsubmit=async event=>{event.preventDefault();const submit=element('auth-submit');submit.disabled=true;authNotice();try{const data=Object.fromEntries(new FormData(event.target));const registering=state.register;await session();if(registering){await api('/api/register',{method:'POST',body:data});setAuthMode(false);authNotice('注册成功，正在登录');}const result=await api('/api/login',{method:'POST',body:data});state.user=result.user;state.csrf=result.csrf;renderAccount();element('auth-dialog').close();event.target.reset();toast(registering?'注册成功，登录成功':'登录成功');await navigate(state.page);}catch(error){authNotice(error.message);toast(error.message,true);}finally{submit.disabled=false;}};
element('logout').onclick=async()=>{try{await api('/api/logout',{method:'POST'});await session();await navigate('home');toast('已退出登录');}catch(error){toast(error.message,true);}};
element('search-form').onsubmit=async event=>{event.preventDefault();state.searchPage=1;try{await loadSearch();}catch(error){toast(error.message,true);}};
element('reset-search').onclick=async()=>{element('search-form').reset();state.searchPage=1;await navigate('home');};
element('publish-form').onsubmit=async event=>{event.preventDefault();const submit=event.target.querySelector('[type=submit]');submit.disabled=true;try{const form=new FormData(event.target);const files=event.target.elements.photos.files;if(files.length>3)throw new Error('最多上传三张图片');const images=files.length?await Promise.all([...files].map(file=>upload(file,'PUBLIC'))):state.images;form.delete('photos');const data={...Object.fromEntries(form),images};await api('/api/items'+(state.editing?'/'+state.editing:''),{method:state.editing?'PUT':'POST',body:data});element('publish-dialog').close();toast('提交成功，请等待管理员审核');await navigate(state.page.startsWith('admin-')?state.page:'mine');}catch(error){toast(error.message,true);}finally{submit.disabled=false;}};
document.addEventListener('submit',async event=>{if(event.target.id!=='claim-form')return;event.preventDefault();const submit=event.target.querySelector('[type=submit]');submit.disabled=true;try{if(!await requireLogin())return;const file=event.target.elements.photo.files[0];const body={proof:event.target.elements.proof.value};if(file)body.proof_attachment_id=await upload(file,'PROOF');await api('/api/items/'+event.target.dataset.item+'/claims',{method:'POST',body});element('detail-dialog').close();toast('申请已提交，审核结果会通过站内消息通知');await navigate('claims');}catch(error){toast(error.message,true);}finally{submit.disabled=false;}});
element('delete-account').onclick=async()=>{const password=prompt('注销后将匿名化账号，保留必要的业务记录。请先结束进行中的业务，并输入密码确认。');if(password===null)return;try{await api('/api/account',{method:'DELETE',body:{password}});await session();await navigate('home');toast('账号已注销');}catch(error){toast(error.message,true);}};
async function initialize(){try{await session();for(const category of state.categories){element('category-filter').add(new Option(category,category));element('publish-category').add(new Option(category,category));}element('publish-form').elements.event_date.max=localDate();await navigate('home');try{const health=await api('/api/health');element('ai-state').textContent=health.ai?'本地语义检索已连接':'关键词检索可用 · 语义服务未连接';}catch{element('ai-state').textContent='检索服务连接异常';}}catch(error){toast(error.message,true);element('content').innerHTML=empty('连接暂未建立',error.message);}}
initialize();
