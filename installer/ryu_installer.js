const labels=[['Welcome','Let’s get started'],['License','Agreement & terms'],['Location','Choose install folder'],['Components','Included features'],['Ready','Review and confirm'],['Install','Installing files'],['Complete','You’re all set!']];
const componentData=[
{id:'core',icon:'◆',name:'Dragon Studio Core',desc:'Library, chapter workflow, production engine and player'},
{id:'offline',icon:'◉',name:'Offline Narration Runtime',desc:'Bundled local voice runtimes and offline preview support'},
{id:'analysis',icon:'Aa',name:'Character & Pronunciation AI',desc:'Character detection and multilingual analysis tools'},
{id:'sound',icon:'♫',name:'Sound Design Tools',desc:'Background music, ambience, effects and chapter mixing'},
{id:'qwen',icon:'◇',name:'Qwen Voice Studio Support',desc:'CustomVoice, VoiceDesign and authorized voice-reference workflows'}
];
let step=0,installing=false,bridge=null,bridgeReady=false,environment={},environmentChecked=false,environmentRequest=0,lastStatus='idle',pollTimer=null;
const $=id=>document.getElementById(id),screens=[...document.querySelectorAll('.screen')];
function formatBytes(bytes){if(bytes===null||bytes===undefined||bytes==='')return'Checking…';const n=Number(bytes);if(!Number.isFinite(n)||n<0)return'Unavailable';if(n===0)return'0 B';const units=['B','KB','MB','GB','TB'];let v=n,i=0;while(v>=1024&&i<units.length-1){v/=1024;i++}return(i===0?String(Math.round(v)):v.toFixed(1))+' '+units[i]}
function renderSteps(){$('steps').innerHTML=labels.map((x,i)=>'<div class="step '+(i===step?'active':i<step?'done':'')+'"><div class="step-no">'+(i<step?'✓':i+1)+'</div><div><strong>'+x[0]+'</strong><small>'+x[1]+'</small></div></div>').join('')}
function renderComponents(){$('componentList').innerHTML=componentData.map(x=>'<div class="component selected" data-id="'+x.id+'" data-required="true"><div class="icon">'+x.icon+'</div><div><b>'+x.name+' · Included</b><p>'+x.desc+'</p></div><span>Included ✓</span></div>').join('')}
function showError(text){const n=$('reviewError');if(!n)return;n.textContent=String(text||'Installation could not be started.');n.style.display='block'}
function clearError(){const n=$('reviewError');if(n){n.textContent='';n.style.display='none'}}
function update(){
 screens.forEach((x,i)=>x.classList.toggle('active',i===step));renderSteps();
 $('back').classList.toggle('hidden',step===0||step>=5);$('cancel').classList.toggle('hidden',step===6);$('next').classList.toggle('hidden',step===5);
 const storageReady=environmentChecked&&Number(environment.free_space_bytes)>0&&Number(environment.required_size_bytes)>0&&environment.has_enough_space===true;
 $('next').disabled=(step===1&&!$('accept').checked)||(step===4&&(!bridgeReady||!storageReady));
 $('next').textContent=step===4?'Install':step===6?'Finish':'Next →';
 if(step===4){$('reviewPath').textContent=$('installPath').value;$('reviewComponents').textContent='Complete package · '+formatBytes(environment.required_size_bytes)+' · '+Number(environment.file_count||0).toLocaleString()+' files · '+componentData.length+' features'}
}
function updateEnvironment(path){
 if(!bridgeReady||!bridge)return;
 const request=++environmentRequest;environmentChecked=false;if(step===4)update();
 bridge.getEnvironmentForPath(String(path||$('installPath').value||''),function(raw){
  if(request!==environmentRequest)return;
  try{
   const info=JSON.parse(raw||'{}');environment=Object.assign({},environment,info);
   const free=Number(info.free_space_bytes||0),required=Number(info.required_size_bytes||0);
   $('freeSpace').textContent=free>0?formatBytes(free):'Unavailable';
   $('installSize').textContent=required>0?formatBytes(required):'Unavailable';
   $('packageFiles').textContent=Number(info.file_count||0)>0?Number(info.file_count).toLocaleString():'Unavailable';
   $('requiredSpace').textContent=required>0?formatBytes(required)+' package + 512 MB reserve':'Package size unavailable';
   $('versionLabel').textContent='Version '+String(info.version||'—');
   environmentChecked=free>0&&required>0&&info.has_enough_space===true&&!info.error;
   if(info.error){showError(info.error)}
   else if(free<=0){showError('Could not determine free space for this location. Choose an existing folder or drive.')}
   else if(required<=0){showError('The application package size is unavailable. Re-download Setup.')}
   else if(info.has_enough_space===false){showError('Not enough free space for the application package plus the 512 MB safety reserve. Choose another drive.')}
   else {clearError()}
   if(step===4)update();
  }catch(e){
   environmentChecked=false;showError('Could not read destination disk/package information. '+String(e));if(step===4)update();
  }
 })
}
function consumeStatus(status){
 if(!status||typeof status!=='object')return;lastStatus=String(status.state||lastStatus);
 if(status.install_path)environment.install_path=status.install_path;
 if(lastStatus==='running'){
  installing=true;$('phaseTitle').textContent=status.phase||'Installing application files';$('phaseText').textContent=status.message||'The Windows installer is working.';
  $('percent').textContent='Installing…';$('progressBar').classList.add('indeterminate');
  $('p1').classList.toggle('done',Boolean(status.files_started));$('p2').classList.toggle('done',Boolean(status.shortcuts_started));$('p3').classList.remove('done');
 }else if(lastStatus==='completed'){
  installing=false;$('phaseTitle').textContent='Installation complete';$('phaseText').textContent=status.message||'The Windows installer verified a successful exit.';
  $('percent').textContent='100%';$('progressBar').classList.remove('indeterminate');$('progressBar').style.width='100%';
  ['p1','p2','p3'].forEach(id=>$(id).classList.add('done'));step=6;update();
 }else if(lastStatus==='failed'||lastStatus==='cancelled'){
  installing=false;$('progressBar').classList.remove('indeterminate');$('percent').textContent='Not completed';step=4;update();
  showError(status.message||'Installation did not complete. Check permissions and free disk space.');
 }else if(lastStatus==='idle'&&status.message){$('phaseText').textContent=status.message}
}
function pollStatus(){if(!bridgeReady||!bridge)return;bridge.getStatus(function(raw){try{consumeStatus(JSON.parse(raw||'{}'))}catch(e){}})}
function connectBridge(){
 if(!window.QWebChannel||!window.qt||!qt.webChannelTransport){$('phaseText').textContent='Native setup bridge is unavailable. Close this window and restart Setup.';showError('The native setup service did not connect. Close and restart Setup.');update();return}
 new QWebChannel(qt.webChannelTransport,function(channel){
  bridge=channel.objects.ryuInstaller;bridgeReady=true;
  if(bridge.statusChanged)bridge.statusChanged.connect(function(raw){try{consumeStatus(JSON.parse(raw||'{}'))}catch(e){}});
  bridge.getEnvironment(function(raw){
   try{environment=JSON.parse(raw||'{}');$('installPath').value=environment.default_dir||$('installPath').value;
    $('versionLabel').textContent='Version '+String(environment.version||'—');renderComponents();updateEnvironment($('installPath').value);update();
   }catch(e){environmentChecked=false;showError('Package information could not be loaded. '+String(e));update()}
  });
  pollTimer=setInterval(pollStatus,600)
 })
}
function browseDirectory(){if(!bridgeReady||!bridge){showError('The native folder picker is not ready.');return}
 bridge.selectDirectory($('installPath').value,function(path){if(path){$('installPath').value=path;clearError();updateEnvironment(path)}})}
function startInstall(){
 if(installing)return;if(!bridgeReady||!bridge){step=4;update();showError('The native installation service is unavailable. Restart Setup.');return}
 const destination=$('installPath').value.trim();if(!destination){step=4;update();showError('Choose an installation folder first.');return}
 if(environment.has_enough_space===false){step=4;update();showError('There may not be enough free space. Choose another destination.');return}
 clearError();installing=true;$('phaseTitle').textContent='Starting Windows installer';
 $('phaseText').textContent='Windows may ask for administrator approval before copying application files.';
 $('percent').textContent='Starting…';$('progressBar').classList.add('indeterminate');
 const payload={install_path:destination,desktop_shortcut:$('desktopShortcut').checked,start_menu:$('startMenu').checked,launch_after:$('launchAfter').checked};
 bridge.startInstall(JSON.stringify(payload),function(accepted){if(!accepted){installing=false;step=4;update();pollStatus()}});
}
function nextStep(){if(step===1&&!$('accept').checked)return;if(step===4){clearError();step=5;update();startInstall();return}
 if(step===6){if(bridgeReady&&bridge)bridge.finish(Boolean($('launchAfter').checked));return}step=Math.min(4,step+1);update()}
function openExit(){if(installing){$('phaseText').textContent='Installation is in progress; please let it finish before closing Setup.';return}$('exitModal').classList.add('show')}
function closeExit(){$('exitModal').classList.remove('show')}
$('componentList').onclick=function(e){const card=e.target.closest('.component');if(!card)return};
$('next').onclick=nextStep;$('back').onclick=function(){if(!installing){step=Math.max(0,step-1);clearError();update()}};
$('accept').onchange=update;$('browse').onclick=browseDirectory;
$('installPath').addEventListener('change',function(){clearError();updateEnvironment(this.value)});
$('installPath').addEventListener('blur',function(){updateEnvironment(this.value)});
$('cancel').onclick=openExit;$('topClose').onclick=openExit;const minimizeButton=$('topMinimize');if(minimizeButton)minimizeButton.onclick=function(){if(bridgeReady&&bridge)bridge.minimize();else showError('Window controls are not ready yet.')};
$('stay').onclick=closeExit;$('confirmExit').onclick=function(){closeExit();if(bridgeReady&&bridge)bridge.exitInstaller();else window.close()};
$('wave').innerHTML=Array.from({length:92},(_,i)=>'<i style="animation-delay:'+(-(i%13)/10)+'s"></i>').join('');
window.addEventListener('error',function(){const phase=$('phaseText');if(phase)phase.textContent='Setup encountered an interface error. Close and reopen Setup; no installation will begin until the controls are ready.';console.error('Ryu Setup interface error');});
renderComponents();update();connectBridge();
