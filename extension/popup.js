'use strict';
const byId=id=>document.getElementById(id);
const statusNames={
 idle:'Готово к запуску',running:'Сбор выполняется в фоновых вкладках',
 stopped:'Остановлено. Частичный JSON сохранён.',
 completed:'Все карточки обработаны.',
 failed_catalog_mismatch:'Сбор остановлен: встроенный каталог изменился.',
 error:'Ошибка расширения'
};
let operation=false;
function render(job){
 job=job||{status:'idle',cursor:0,total:123,exact:0,needs_review:0,errors:0};
 const running=job.status==='running', stopped=job.status==='stopped';
 byId('start').hidden=running||stopped;
 byId('start').textContent=job.status==='completed'?'Повторить сбор всех 123 вин':'Собрать все 123 вина';
 byId('start').disabled=operation;
 byId('stop').hidden=!running;
 byId('resume').hidden=!stopped;
 byId('stop').disabled=operation;
 byId('resume').disabled=operation;
 byId('export').hidden=(!job.cursor||job.status==='idle');
 byId('export').disabled=operation;
 byId('phase').textContent=statusNames[job.status]||job.status;
 byId('progress').max=job.total||123;
 byId('progress').value=job.cursor||0;
 byId('count').textContent=(job.cursor||0)+' / '+(job.total||123);
 byId('exact').textContent='Точных: '+(job.exact||0);
 byId('review').textContent='Требуют проверки: '+(job.needs_review||0);
 byId('errors').textContent='Ошибок: '+(job.errors||0);
 byId('last').textContent=job.last?('Последнее: '+job.last.title+' - '+job.last.reason):'';
 const down=job.download_status;
 byId('download-status').textContent=down==='success'?'JSON автоматически сохранён в загрузки браузера.'
   :down==='failed'?'Автоскачивание не удалось: '+(job.download_error||'ошибка браузера')+'. Нажмите «Скачать JSON ещё раз».'
   :down==='pending'?'Формируется JSON для автоматического скачивания.':'';
}
async function refresh(){
 try{
  const response=await chrome.runtime.sendMessage({type:'wa_status'});
  if(response?.status==='error')throw Error(response.message);
  render(response);
 }catch(e){byId('message').textContent=String(e?.message||e);}
}
async function request(type){
 if(operation)return;
 operation=true;
 byId('message').textContent='';
 try{
  const response=await chrome.runtime.sendMessage({type});
  if(response?.status==='error')throw Error(response.message);
  render(response);
 }catch(e){byId('message').textContent='Ошибка: '+String(e?.message||e);}
 finally{operation=false;void refresh();}
}
byId('start').addEventListener('click',()=>request('wa_start'));
byId('stop').addEventListener('click',()=>request('wa_stop'));
byId('resume').addEventListener('click',()=>request('wa_resume'));
byId('export').addEventListener('click',()=>request('wa_export'));
chrome.storage.onChanged.addListener((changes,area)=>{
 if(area!=='local')return;
 if(changes.wineAtlasBatchDownloadV2){void refresh();return;}
 if(changes.wineAtlasBatchV2){void refresh();}
});
void refresh();
