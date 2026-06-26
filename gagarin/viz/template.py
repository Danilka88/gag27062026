HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>TERCOM Навигация</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;line-height:1.5}
header{max-width:1200px;margin:0 auto;padding:24px 24px 0}
h1{font-size:22px;font-weight:600;margin-bottom:12px;letter-spacing:-0.3px}
.tabDesc{font-size:13px;color:#8b949e;margin-bottom:16px;padding:8px 14px;background:#161b22;border-radius:8px;border:1px solid #30363d;line-height:1.5}
.tabDesc b{color:#f0f6fc}
.tabs{display:flex;gap:8px;margin-bottom:8px}
.tab{padding:8px 20px;border-radius:20px;border:1px solid #30363d;background:0 0;color:#8b949e;font-size:14px;cursor:pointer;transition:.2s;font-family:inherit}
.tab:hover{color:#e6edf3;border-color:#58a6ff}
.tab.active{background:#58a6ff;color:#fff;border-color:#58a6ff}
.nav-links{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.nav-link{padding:6px 16px;border-radius:16px;border:1px solid #30363d;background:#161b22;color:#8b949e;font-size:13px;cursor:pointer;transition:.2s;text-decoration:none}
.nav-link:hover{color:#e6edf3;border-color:#58a6ff;background:#1c2333}
.summaries{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px;padding:12px 16px;background:#161b22;border-radius:8px;border:1px solid #30363d;font-size:13px;color:#8b949e;line-height:1.6}
.summary-line strong{color:#e6edf3}
main{max-width:1200px;margin:0 auto;padding:0 24px 48px;display:flex;flex-direction:column;gap:20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden}
.card-title{font-size:15px;font-weight:600;padding:14px 16px 0;color:#e6edf3;letter-spacing:-0.2px}
.chart-container{width:100%}
.chart-container .js-plotly-plot,.chart-container .plot-container,.chart-container .svg-container{width:100%!important}
.caption{padding:12px 16px 16px;font-size:14px;color:#c9d1d9;line-height:1.6;border-top:1px solid #1e252e}
.caption b{color:#f0f6fc}
.caption .ex{border-left:3px solid #58a6ff;margin-top:8px;padding:6px 12px;background:#0d1117;border-radius:4px;font-size:13px;color:#8b949e}
.caption .ex b{color:#58a6ff}
@media(max-width:768px){header{padding:16px 12px 0}main{padding:0 12px 24px;gap:12px}.summaries{flex-direction:column;gap:4px}}
</style>
</head>
<body>
<header>
<h1>TERCOM Навигация</h1>
<div class="nav-links">{NAV_LINKS}</div>
<div class="tabs">
<button class="tab active" data-tab="syn" onclick="switchTab('syn')">Synthetic</button>
<button class="tab" data-tab="dram" onclick="switchTab('dram')">Dramatic</button>
</div>
<div class="tabDesc" id="tabDesc"></div>
<div class="summaries">{SUMMARIES}</div>
</header>
<main>
{CARDS_HTML}
</main>
<script>
var CHARTS = {CHARTS_JSON};
var TAB_DESC = {
  syn:'<b>Synthetic DEM</b> — искусственный, плавный рельеф (высоты 101–600 м, σ=95 м). Создан для <b>отладки</b> алгоритма: холмы и впадины без резких перепадов. Если TERCOM работает на нём — базовая логика верна.',
  dram:'<b>Dramatic DEM</b> — искусственный, контрастный рельеф (высоты 10–3489 м, σ=687 м). Содержит <b>6 вулканов</b>, гребни и каньоны. Стресс-тест: проверяет, не теряется ли алгоритм на сложном рельефе.'
};
function renderCharts(tab){
  for(var i=0;i<CHARTS.length;i++){
    var c=CHARTS[i],vis=c[tab+'_vis'];
    var el=document.getElementById('chart-'+c.id);
    if(!el._plotted){
      Plotly.newPlot(el,c.figure,{responsive:true,displayModeBar:false});
      el._plotted=true;
    }else{
      Plotly.restyle(el,{visible:vis});
    }
  }
}
function switchTab(tab){
  var tabs=document.querySelectorAll('.tab');
  for(var i=0;i<tabs.length;i++)tabs[i].classList.remove('active');
  document.querySelector('.tab[data-tab="'+tab+'"]').classList.add('active');
  document.getElementById('tabDesc').innerHTML=TAB_DESC[tab];
  renderCharts(tab);
}
document.addEventListener('DOMContentLoaded',function(){renderCharts('syn');});
</script>
</body>
</html>"""
