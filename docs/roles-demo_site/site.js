
(function(){
  var root=document.documentElement;
  // 主题
  var btn=document.getElementById('themeBtn');
  var saved=null; try{ saved=localStorage.getItem('doc-theme'); }catch(e){}
  if(saved==='light'||saved==='dark') root.dataset.theme=saved;
  function refresh(){ if(btn) btn.textContent=(root.dataset.theme==='dark')?'☀ 浅色':'🌙 深色'; }
  if(btn){ btn.addEventListener('click',function(){
    var cur=(root.dataset.theme==='dark')?'light':'dark';
    root.dataset.theme=cur; try{ localStorage.setItem('doc-theme',cur); }catch(e){}
    refresh();
  }); }
  refresh();
  // 目录分类抽屉：展开状态记忆
  var groups=[].slice.call(document.querySelectorAll('.toc-group'));
  var store=null; try{ store=JSON.parse(localStorage.getItem('doc-toc-open')||'null'); }catch(e){}
  if(store && Array.isArray(store)){
    groups.forEach(function(d,i){ d.open = store.indexOf(i)>=0 || d.open; });
  } else {
    // 首次访问默认全展开，便于看到完整目录
    groups.forEach(function(d){ d.open=true; });
  }
  groups.forEach(function(d,i){
    d.addEventListener('toggle',function(){
      var arr=groups.filter(function(x){return x.open;}).map(function(x){return groups.indexOf(x);});
      try{ localStorage.setItem('doc-toc-open', JSON.stringify(arr)); }catch(e){}
    });
  });
  // 当前页目录项尽量可见
  var cur=document.querySelector('#toc a.active');
  if(cur) setTimeout(function(){ cur.scrollIntoView({block:'nearest'}); },50);
  // 窄屏抽屉
  var tocBtn=document.getElementById('tocBtn');
  var backdrop=document.getElementById('tocBackdrop');
  function closeToc(){ document.body.classList.remove('toc-open'); }
  if(tocBtn){ tocBtn.addEventListener('click',function(){ document.body.classList.toggle('toc-open'); }); }
  if(backdrop) backdrop.addEventListener('click',closeToc);
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') closeToc(); });
  // 抽屉内点链接后自动收起（移动端）
  document.querySelectorAll('#toc a').forEach(function(a){
    a.addEventListener('click',function(){ if(window.innerWidth<=1100) closeToc(); });
  });
})();
// ============ 跨页搜索（search-index.js 提供 window.SEARCH_INDEX） ============
(function(){
  var input=document.getElementById('searchInput');
  var panel=document.getElementById('searchPanel');
  var box=document.getElementById('searchBox');
  var IDX=(typeof window.SEARCH_INDEX!=='undefined'&&window.SEARCH_INDEX)?window.SEARCH_INDEX:null;
  if(!input||!panel||!box) return;
  if(!IDX){ input.placeholder='搜索索引未加载'; return; }
  var timer=null, cur=-1, nav=[];
  function esc(s){ var d=document.createElement('div'); d.textContent=(s==null?'':s); return d.innerHTML; }
  function closeP(){ panel.style.display='none'; cur=-1; nav=[]; }
  function hl(s,q){
    var terms=q.split(/\s+/).filter(Boolean);
    if(!terms.length) return esc(s);
    var re=new RegExp('('+terms.map(function(t){return t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}).join('|')+')','gi');
    return esc(s).replace(re,'<mark>$1</mark>');
  }
  function snip(x,q){
    var low=x.toLowerCase(), terms=q.split(/\s+/), pos=-1;
    for(var i=0;i<terms.length;i++){ var p=low.indexOf(terms[i]); if(p>=0&&(pos<0||p<pos)) pos=p; }
    if(pos<0) pos=0;
    var st=Math.max(0,pos-46), en=Math.min(x.length,pos+88);
    return (st>0?'…':'')+x.slice(st,en)+(en<x.length?'…':'');
  }
  function run(){
    var q=input.value.trim();
    if(!q){ closeP(); return; }
    var terms=q.toLowerCase().split(/\s+/).filter(Boolean);
    var res=[];
    for(var i=0;i<IDX.length;i++){
      var pg=IDX[i], base=(pg.g+' '+(pg.t||'')).toLowerCase();
      for(var j=0;j<pg.a.length;j++){
        var sec=pg.a[j];
        var hay=(pg.g+' '+(pg.t||'')+' '+(sec.h||'')+' '+(sec.x||'')).toLowerCase();
        var ok=true, score=0;
        for(var k=0;k<terms.length;k++){
          var tm=terms[k];
          if(hay.indexOf(tm)<0){ ok=false; break; }
          if((sec.h||'').toLowerCase().indexOf(tm)>=0) score+=2;
          else if(base.indexOf(tm)>=0) score+=1.5;
          score+=1;
        }
        if(ok) res.push({f:pg.f,t:pg.t,g:pg.g,h:sec.h,id:sec.id,x:sec.x,s:score});
      }
    }
    res.sort(function(a,b){ return (b.s-a.s)||(a.f<b.f?-1:1); });
    var seen={}, out=[];
    for(var i=0;i<res.length&&out.length<40;i++){
      var r=res[i]; seen[r.f]=seen[r.f]||0;
      if(seen[r.f]<3){ seen[r.f]++; out.push(r); }
    }
    nav=out; cur=-1;
    if(!out.length){
      panel.innerHTML='<div class="s-empty">未找到与「'+esc(q)+'」匹配的内容，试试其他关键词</div>';
      panel.style.display='block'; return;
    }
    var h='<div class="s-head">'+out.length+' 条结果（跨页命中 '+res.length+' 处）</div>';
    for(var i=0;i<out.length;i++){
      var o=out[i];
      h+='<div class="s-item" data-f="'+esc(o.f)+'" data-id="'+esc(o.id||'')+'">'+
         '<div class="s-t">'+esc(o.t)+'<span class="s-g">'+esc(o.g)+'</span>'+
         (o.h?'<span class="s-h">'+esc(o.h)+'</span>':'')+'</div>'+
         (o.x&&o.x.length?'<div class="s-x">'+hl(snip(o.x,q),q)+'</div>':'')+'</div>';
    }
    panel.innerHTML=h; panel.style.display='block'; panel.scrollTop=0;
  }
  function move(d){
    if(!nav.length) return;
    cur+=d; if(cur<0) cur=nav.length-1; if(cur>=nav.length) cur=0;
    var its=panel.querySelectorAll('.s-item');
    for(var i=0;i<its.length;i++) its[i].classList.toggle('cur',i===cur);
    var el=its[cur]; if(el) el.scrollIntoView({block:'nearest'});
  }
  function jumpTo(r){ if(r) location.href=r.f+(r.id?'#'+r.id:''); }
  input.addEventListener('input',function(){ clearTimeout(timer); timer=setTimeout(run,140); });
  input.addEventListener('focus',function(){ if(input.value.trim()) run(); });
  input.addEventListener('blur',function(){ setTimeout(closeP,170); });
  input.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){ e.preventDefault(); move(1); }
    else if(e.key==='ArrowUp'){ e.preventDefault(); move(-1); }
    else if(e.key==='Enter'){ e.preventDefault(); jumpTo(cur>=0&&cur<nav.length?nav[cur]:nav[0]); }
    else if(e.key==='Escape'){ closeP(); }
  });
  panel.addEventListener('mousedown',function(e){
    var t=e.target; while(t&&t!==panel&&!(t.classList&&t.classList.contains('s-item'))) t=t.parentNode;
    if(t&&t!==panel){ e.preventDefault(); jumpTo(nav[Array.prototype.indexOf.call(panel.querySelectorAll('.s-item'),t)]); }
  });
  document.addEventListener('click',function(e){ if(!box.contains(e.target)) closeP(); });
})();

// ---- 图片点击放大（lightbox） ----
(function(){
  var mask=null;
  function closeLb(){ if(mask){ mask.remove(); mask=null; } }
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') closeLb(); });
  document.addEventListener('click',function(e){
    if(mask) return;
    var t=e.target;
    if(!t||t.tagName!=='IMG'||!t.closest||!t.closest('article')) return;
    mask=document.createElement('div'); mask.className='lb-mask';
    var im=document.createElement('img');
    im.src=t.currentSrc||t.src; im.alt=t.alt||'';
    mask.appendChild(im);
    var x=document.createElement('button'); x.type='button';
    x.className='lb-close'; x.setAttribute('aria-label','close');
    x.textContent='✕'; mask.appendChild(x);
    var cap=(t.getAttribute('alt')||'').trim();
    if(cap){ var c=document.createElement('div'); c.className='lb-cap'; c.textContent=cap; mask.appendChild(c); }
    mask.addEventListener('click',function(ev){ if(ev.target!==im) closeLb(); });
    document.body.appendChild(mask);
  });
})();

/* ===== 代码块复制按钮：事件委托 + clipboard/execCommand 双通道 ===== */
document.addEventListener('click', function(ev){
  var b = ev.target && ev.target.closest ? ev.target.closest('.hl-copy') : null;
  if(!b) return;
  var hl = b.closest('.hl');
  var codeEl = hl ? hl.querySelector('.hl-scroll pre:not(.hl-gutter) code') : null;
  var txt = codeEl ? codeEl.textContent : '';
  var orig = b.textContent;
  var restore = function(){ b.textContent = orig; };
  var ok = function(){ b.textContent = '已复制'; setTimeout(restore, 1500); };
  var fail = function(){ b.textContent = '复制失败'; setTimeout(restore, 1500); };
  var legacy = function(){
    var ta = document.createElement('textarea');
    ta.value = txt;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:0;left:-9999px;opacity:0';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    var r = false;
    try { r = document.execCommand('copy'); } catch(e) {}
    document.body.removeChild(ta);
    if(r) ok(); else fail();
  };
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(ok, legacy);
  } else { legacy(); }
}, false);
