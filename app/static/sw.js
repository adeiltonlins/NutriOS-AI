const CACHE_NAME='nutrios-v30';
const API_CACHE='nutrios-api-v30';
const STATIC_ASSETS=['/static/manifest.json','/static/icons/icon-192.svg','/static/icons/icon-512.svg','/static/icons/icon-maskable-512.svg'];
const API_PATTERNS=[/^\/api\/me/,/^\/app\/api\//,/^\/paciente\/api\//];
const UI_NETWORK_FIRST=/\.(?:css|js|html)$/i;
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE_NAME).then(c=>c.addAll(STATIC_ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE_NAME&&k!==API_CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const u=new URL(event.request.url); if(event.request.method!=='GET'||u.origin!==location.origin)return;
 if(API_PATTERNS.some(p=>p.test(u.pathname))){event.respondWith(networkFirst(event.request,API_CACHE));return}
 if(u.pathname==='/app'||u.pathname.startsWith('/app/')||UI_NETWORK_FIRST.test(u.pathname)){
   event.respondWith(networkFirst(event.request,CACHE_NAME));return
 }
 if(u.pathname.startsWith('/static/')||u.pathname==='/') event.respondWith(staleWhileRevalidate(event.request,CACHE_NAME));
});
async function networkFirst(req,name){const c=await caches.open(name);try{const r=await fetch(req,{cache:'no-store'});if(r.ok)c.put(req,r.clone());return r}catch(e){return (await c.match(req))||new Response('Offline',{status:503})}}
async function staleWhileRevalidate(req,name){const c=await caches.open(name),cached=await c.match(req);const fresh=fetch(req).then(r=>{if(r.ok)c.put(req,r.clone());return r}).catch(()=>cached);return cached||fresh}
self.addEventListener('push',event=>{if(!event.data)return;const d=event.data.json();event.waitUntil(self.registration.showNotification(d.title||'NutriOS',{body:d.body||'Nova atualização no NutriOS',icon:'/static/icons/icon-192.svg',badge:'/static/icons/icon-192.svg',vibrate:[100,50,100],data:{url:d.url||'/app'},actions:[{action:'open',title:'Abrir'},{action:'dismiss',title:'Dispensar'}],requireInteraction:true}))});
self.addEventListener('notificationclick',event=>{event.notification.close();const url=event.notification.data?.url||'/app';event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{const w=list.find(c=>c.url.startsWith(location.origin));return w?w.focus().then(()=>w.navigate(url)):clients.openWindow(url)}))});
self.addEventListener('sync',event=>{if(event.tag==='nutrios-sync')event.waitUntil(Promise.resolve())});