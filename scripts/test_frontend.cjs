'use strict';
// Run the real application handlers with controlled HTTP responses and a minimal DOM.
// This verifies feedback and draft retention; it does not replace browser layout checks.
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = readFileSync(require('node:path').join(__dirname, '../src/main/resources/static/app.js'), 'utf8');

function environment() {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) {
      const classes = new Set();
      nodes.set(id, {id, textContent:'', innerHTML:'', className:'', value:'', open:false, disabled:false,
        dataset:{}, elements:{}, attributes:{}, add(){}, reset(){}, focus(){}, querySelector(){return node(id+'-submit');},
        setAttribute(key,value){this.attributes[key]=value;},getAttribute(key){return this.attributes[key];},
        classList:{add(c){classes.add(c);},remove(c){classes.delete(c);}, toggle(c, force){if(force ?? !classes.has(c))classes.add(c);else classes.delete(c);}, contains(c){return classes.has(c);}},
        showModal(){this.open=true;}, close(){this.open=false;}});
    }
    return nodes.get(id);
  };
  for (const key of ['display_name','password','event_date','photos']) node('auth-form').elements[key]={};
  node('publish-form').elements.event_date={};
  node('publish-form').elements.location={};
  node('auth-form').data={username:'verify_user',display_name:'测试用户',password:'VerifyOnly123!'};
  node('search-form').data={q:''};
  const calls=[];
  const server={user:null, csrf:'fresh-csrf', failLogin:false, expireWrite:false, registrations:0};
  const user={id:7,username:'verify_user',display_name:'测试用户',role:'USER',phone:'',default_address:''};
  const fetch=async(path, options={})=>{
    calls.push({path,options});let status=200, result={};
    if(path==='/api/session')result={user:server.user,csrf:server.csrf,categories:[]};
    else if(path==='/api/register'){server.registrations++;result={id:7};}
    else if(path==='/api/login'){
      if(server.failLogin){status=401;result={error:'用户名或密码错误'};}
      else {server.user=user;server.csrf='logged-csrf';result={user,csrf:server.csrf};}
    }else if(path==='/api/account/profile'){
      if(options.method==='PUT'){const data=JSON.parse(options.body);Object.assign(server.user,data);delete server.user.current_password;}
      result=server.user;
    }else if(path==='/api/account/password'){server.user=null;server.csrf='after-password';result={ok:true};}
    else if(path==='/api/items'&&options.method==='POST'&&server.expireWrite){server.user=null;status=401;result={error:'登录态过期，请重新登录后再操作'};}
    else if(path.startsWith('/api/items?'))result={items:[],total:0,pageSize:10,mode:'recent'};
    else if(path==='/api/health')result={ai:true};
    else if(path==='/csrf-test'){status=403;result={error:'页面验证已失效，请刷新后重试'};}
    return {ok:status<400,status,json:async()=>result};
  };
  class FormData {constructor(form){this.values=Object.entries(form?.data||{});} [Symbol.iterator](){return this.values[Symbol.iterator]();}}
  const listeners={};const location={hash:''};const history={pushState(a,b,hash){location.hash=hash;}};
  const context=vm.createContext({document:{getElementById:node,querySelector:node,querySelectorAll:()=>[],addEventListener(name,handler){(listeners[name]??=[]).push(handler);}},window:{addEventListener(){}},location,history,fetch,FormData,URLSearchParams,Option:function(){},setTimeout:()=>1,clearTimeout(){},console});
  vm.runInContext(source,context);
  return {node,server,calls,listeners,location,run:code=>vm.runInContext(code,context),async ready(){await new Promise(resolve=>setImmediate(resolve));}};
}

(async()=>{
  let passed=0;
  const check=async(name,body)=>{await body();passed++;console.log('PASS '+name);};
  await check('login shows success only after authentication',async()=>{
    const env=environment();await env.ready();env.run('showLogin()');
    await env.node('auth-form').onsubmit({preventDefault(){},target:env.node('auth-form')});
    assert.equal(env.node('toast').textContent,'登录成功');assert.equal(env.node('auth-dialog').open,false);
  });
  await check('registration shows successful automatic login',async()=>{
    const env=environment();await env.ready();env.run('setAuthMode(true)');
    await env.node('auth-form').onsubmit({preventDefault(){},target:env.node('auth-form')});
    assert.equal(env.node('toast').textContent,'注册成功，登录成功');assert.equal(env.server.registrations,1);
  });
  await check('failed automatic login can retry without registering twice',async()=>{
    const env=environment();await env.ready();env.server.failLogin=true;env.run('setAuthMode(true)');
    await env.node('auth-form').onsubmit({preventDefault(){},target:env.node('auth-form')});
    assert.equal(env.node('auth-notice').textContent,'用户名或密码错误');assert.equal(env.run('state.register'),false);
    env.server.failLogin=false;
    await env.node('auth-form').onsubmit({preventDefault(){},target:env.node('auth-form')});
    assert.equal(env.server.registrations,1);assert.equal(env.node('toast').textContent,'登录成功');
  });
  await check('expired page opens login before opening publish',async()=>{
    const env=environment();await env.ready();env.run("state.user={id:7};state.csrf='old'");
    await env.run('openPublish()');assert.equal(env.node('publish-dialog').open,false);
    assert.equal(env.node('auth-dialog').open,true);assert.match(env.node('auth-notice').textContent,/登录态过期/);
  });
  await check('expired submission refreshes session and preserves form draft',async()=>{
    const env=environment();await env.ready();env.server.expireWrite=true;
    env.node('publish-form').data={title:'已填写的雨伞线索'};env.node('publish-dialog').open=true;
    env.run("state.user={id:7};state.csrf='old'");
    await assert.rejects(env.run("api('/api/items',{method:'POST',body:{title:'草稿'}})"),/登录态过期/);
    assert.equal(env.node('publish-form').data.title,'已填写的雨伞线索');assert.equal(env.node('publish-dialog').open,true);
    assert.equal(env.node('auth-dialog').open,true);assert.equal(env.run('state.csrf'),'fresh-csrf');
    await env.node('auth-form').onsubmit({preventDefault(){},target:env.node('auth-form')});
    assert.equal(env.node('auth-dialog').open,false);assert.equal(env.node('publish-dialog').open,true);
  });
  await check('CSRF errors remain distinct from expired login',async()=>{
    const env=environment();await env.ready();
    await assert.rejects(env.run("api('/csrf-test',{method:'POST'})"),/页面验证已失效/);
    assert.equal(env.node('auth-dialog').open,false);
  });
  await check('six character admin password is allowed at login while registration requires eight',async()=>{
    const env=environment();await env.ready();env.run('showLogin()');assert.equal(env.node('auth-form').elements.password.minLength,1);
    env.run('setAuthMode(true)');assert.equal(env.node('auth-form').elements.password.minLength,8);
    env.run('setAuthMode(false)');assert.equal(env.node('auth-form').elements.password.minLength,1);
  });
  await check('account menu opens and closes after navigation',async()=>{
    const env=environment();await env.ready();env.node('user-toggle').onclick();assert.equal(env.node('user-toggle').getAttribute('aria-expanded'),'true');
    await env.run("navigate('home')");assert.equal(env.node('user-toggle').getAttribute('aria-expanded'),'false');assert.equal(env.node('user-menu').classList.contains('hidden'),true);
  });
  async function signedIn(){const env=environment();await env.ready();await env.node('auth-form').onsubmit({preventDefault(){},target:env.node('auth-form')});return env;}
  await check('profile is a separate view with optional phone, address and escaped fields',async()=>{
    const env=await signedIn();env.server.user.phone='+86 13800000000';env.server.user.display_name='<script>test</script>';
    await env.run("navigate('profile')");assert.equal(env.location.hash,'#profile');const html=env.node('content').innerHTML;
    assert.match(html,/name="username"/);assert.match(html,/name="phone" type="tel"/);assert.match(html,/name="default_address"/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>test/);
  });
  await check('profile save updates header and publishing prefills address but never phone',async()=>{
    const env=await signedIn();await env.run("navigate('profile')");env.node('profile-form').data={username:'verify_renamed',display_name:'新的昵称',phone:'13800000000',default_address:'图书馆二楼',current_password:'VerifyOnly123!'};
    await env.run("saveProfile(element('profile-form'))");assert.equal(env.node('user-name').textContent,'新的昵称');assert.match(env.node('profile-notice').textContent,/新的登录账号/);
    await env.run('openPublish()');assert.equal(env.node('publish-form').elements.location.value,'图书馆二楼');assert.equal(env.node('publish-form').elements.contact,undefined);
  });
  await check('password mismatch does not submit and successful change returns to login',async()=>{
    const env=await signedIn();env.node('password-form').data={current_password:'VerifyOnly123!',new_password:'UpdatedPass123',confirm_password:'mismatch'};
    await assert.rejects(env.run("savePassword(element('password-form'))"),/不一致/);assert.equal(env.calls.filter(call=>call.path==='/api/account/password').length,0);
    env.node('password-form').data.confirm_password='UpdatedPass123';await env.run("savePassword(element('password-form'))");
    assert.equal(env.run('state.user'),null);assert.equal(env.node('auth-dialog').open,true);assert.match(env.node('auth-notice').textContent,/新密码/);assert.equal(env.run('state.csrf'),'after-password');
  });
  await check('protected profile destination resumes after signing in',async()=>{
    const env=environment();await env.ready();env.location.hash='#profile-password';
    await env.run("navigate(routePage())");assert.equal(env.node('auth-dialog').open,true);
    await env.node('auth-form').onsubmit({preventDefault(){},target:env.node('auth-form')});
    assert.equal(env.location.hash,'#profile-password');assert.match(env.node('content').innerHTML,/id="password-form"/);
  });
  console.log(`${passed} frontend behavior checks passed (no browser visual validation).`);
})().catch(error=>{console.error(error);process.exitCode=1;});
