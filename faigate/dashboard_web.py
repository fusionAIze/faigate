"""Built-in operator dashboard HTML for fusionAIze Gate."""

# ruff: noqa: E501

DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>fusionAIze Gate</title>
<style>
:root{
  --bg:#07101d;
  --bg-2:#0d1730;
  --panel:#0d1830cc;
  --panel-strong:#101d38;
  --panel-soft:#12224480;
  --line:#26437B;
  --line-soft:#1b2d53;
  --text:#dbe6f5;
  --muted:#8ea7cc;
  --muted-soft:#6980a6;
  --brand:#0052CC;
  --brand-2:#54ABEE;
  --navy:#1F497D;
  --mid:#3663BE;
  --lime:#C4D900;
  --green:#2EA75D;
  --orange:#FFAA19;
  --danger:#ff7b7b;
  --shadow:0 30px 120px rgba(0,0,0,.45);
  --radius-xl:28px;
  --radius-lg:20px;
  --radius-md:14px;
  --radius-sm:10px;
  --mono:"SFMono-Regular","IBM Plex Mono","Menlo","Consolas",monospace;
  --body:"Avenir Next","Segoe UI","Helvetica Neue",sans-serif;
  --display:"Avenir Next Condensed","Gill Sans","Trebuchet MS",sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  min-height:100vh;
  color:var(--text);
  font-family:var(--body);
  background:
    radial-gradient(circle at 15% 20%, rgba(84,171,238,.16), transparent 28%),
    radial-gradient(circle at 82% 16%, rgba(196,217,0,.08), transparent 20%),
    radial-gradient(circle at 70% 85%, rgba(255,170,25,.08), transparent 24%),
    linear-gradient(180deg, #09111f 0%, #07101d 44%, #06101c 100%);
}
body::before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  background:
    linear-gradient(rgba(255,255,255,.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.02) 1px, transparent 1px);
  background-size:32px 32px;
  mask-image:radial-gradient(circle at center, black 40%, transparent 88%);
  opacity:.3;
}
a{color:inherit}
button,input,select{font:inherit}
button{
  border:0;
  cursor:pointer;
  transition:transform .18s ease, background .18s ease, border-color .18s ease, color .18s ease;
}
button:hover{transform:translateY(-1px)}
.shell{
  display:grid;
  grid-template-columns:280px minmax(0,1fr);
  gap:20px;
  min-height:100vh;
  padding:22px;
}
.rail{
  position:sticky;
  top:22px;
  height:calc(100vh - 44px);
  padding:22px 18px;
  border:1px solid rgba(84,171,238,.16);
  border-radius:var(--radius-xl);
  background:
    linear-gradient(180deg, rgba(16,29,56,.95), rgba(10,19,37,.92)),
    radial-gradient(circle at top left, rgba(84,171,238,.14), transparent 38%);
  box-shadow:var(--shadow);
  overflow:hidden;
}
.rail::after{
  content:"";
  position:absolute;
  inset:auto 16px 16px 16px;
  height:1px;
  background:linear-gradient(90deg, transparent, rgba(84,171,238,.35), transparent);
}
.brand{
  display:flex;
  align-items:flex-start;
  gap:14px;
  margin-bottom:26px;
}
.brand-mark{
  width:48px;
  height:48px;
  border-radius:16px;
  background:
    radial-gradient(circle at 30% 30%, rgba(84,171,238,.95), rgba(0,82,204,.55) 42%, rgba(13,23,48,.2) 70%),
    linear-gradient(135deg, rgba(196,217,0,.18), rgba(0,82,204,.1));
  box-shadow:0 0 0 1px rgba(84,171,238,.14), 0 0 26px rgba(0,82,204,.35);
  position:relative;
}
.brand-mark::before,
.brand-mark::after{
  content:"";
  position:absolute;
  inset:9px;
  border-radius:12px;
  border:1px solid rgba(225,233,243,.18);
}
.brand-mark::after{
  inset:17px;
  border-color:rgba(196,217,0,.3);
}
.brand-copy h1{
  margin:2px 0 6px;
  font:700 1.32rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:uppercase;
}
.brand-copy h1 .accent{color:var(--lime)}
.brand-copy p{
  margin:0;
  color:var(--muted);
  font-size:.88rem;
  line-height:1.45;
}
.rail-meta{
  display:grid;
  gap:10px;
  margin-bottom:24px;
}
.rail-stat{
  padding:12px 14px;
  border:1px solid rgba(84,171,238,.12);
  border-radius:var(--radius-md);
  background:rgba(7,16,29,.45);
}
.rail-stat .kicker{
  display:block;
  color:var(--muted-soft);
  font:600 .66rem/1 var(--mono);
  text-transform:uppercase;
  letter-spacing:.14em;
  margin-bottom:8px;
}
.rail-stat strong{
  display:block;
  font-size:1rem;
  letter-spacing:.02em;
}
.nav{
  display:grid;
  gap:8px;
}
.nav button{
  width:100%;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  padding:13px 14px;
  border:1px solid transparent;
  border-radius:14px;
  background:transparent;
  color:var(--muted);
  text-align:left;
}
.nav button .num{
  color:rgba(225,233,243,.45);
  font:600 .72rem/1 var(--mono);
}
.nav button .label{
  font-weight:600;
  letter-spacing:.02em;
}
.nav button.active{
  background:linear-gradient(90deg, rgba(0,82,204,.22), rgba(84,171,238,.1));
  color:#f4f8ff;
  border-color:rgba(84,171,238,.24);
  box-shadow:inset 0 1px 0 rgba(225,233,243,.06), 0 0 0 1px rgba(84,171,238,.08);
}
.nav button.active .num{color:var(--lime)}
.rail-note{
  margin-top:24px;
  padding:14px;
  border-radius:16px;
  background:linear-gradient(160deg, rgba(255,170,25,.12), rgba(255,170,25,.02));
  border:1px solid rgba(255,170,25,.14);
  color:#e7d8b6;
  font-size:.85rem;
  line-height:1.5;
}
.content{
  min-width:0;
  display:grid;
  gap:18px;
}
.hero{
  position:relative;
  overflow:hidden;
  padding:24px 24px 22px;
  border:1px solid rgba(84,171,238,.16);
  border-radius:var(--radius-xl);
  background:
    linear-gradient(145deg, rgba(18,34,68,.96), rgba(9,17,31,.96)),
    radial-gradient(circle at top right, rgba(84,171,238,.2), transparent 30%);
  box-shadow:var(--shadow);
}
.hero::before{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(90deg, rgba(84,171,238,.08), transparent 26%, transparent 74%, rgba(196,217,0,.06));
  pointer-events:none;
}
.hero-top{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:20px;
  margin-bottom:18px;
  flex-wrap:wrap;
}
.eyebrow{
  display:inline-flex;
  align-items:center;
  gap:10px;
  margin-bottom:12px;
  color:var(--muted);
  font:600 .73rem/1 var(--mono);
  letter-spacing:.16em;
  text-transform:uppercase;
}
.pulse{
  width:10px;
  height:10px;
  border-radius:50%;
  background:var(--lime);
  box-shadow:0 0 0 0 rgba(196,217,0,.45);
  animation:pulse 2.4s infinite;
}
@keyframes pulse{
  0%{box-shadow:0 0 0 0 rgba(196,217,0,.45)}
  70%{box-shadow:0 0 0 16px rgba(196,217,0,0)}
  100%{box-shadow:0 0 0 0 rgba(196,217,0,0)}
}
.hero h2{
  margin:0;
  max-width:13ch;
  font:700 clamp(2rem, 4vw, 3.3rem)/.96 var(--display);
  text-transform:uppercase;
  letter-spacing:.03em;
}
.hero h2 .accent{color:var(--lime)}
.hero p{
  margin:14px 0 0;
  max-width:72ch;
  color:var(--muted);
  line-height:1.6;
  font-size:1rem;
}
.hero-actions{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  align-items:center;
}
.btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:8px;
  min-height:42px;
  padding:0 14px;
  border-radius:999px;
  border:1px solid rgba(84,171,238,.18);
  background:rgba(9,17,31,.46);
  color:#dbe6f5;
}
.btn.primary{
  background:linear-gradient(135deg, rgba(0,82,204,.88), rgba(54,99,190,.88));
  border-color:rgba(84,171,238,.28);
}
.btn.secondary{
  background:rgba(255,255,255,.04);
}
.btn.ghost{
  color:var(--muted);
}
.hero-ribbon{
  display:grid;
  grid-template-columns:1.35fr .9fr;
  gap:16px;
}
.ribbon-panel{
  padding:18px;
  border-radius:20px;
  border:1px solid rgba(84,171,238,.14);
  background:rgba(7,16,29,.48);
  backdrop-filter:blur(10px);
}
.ribbon-title{
  margin-bottom:12px;
  color:var(--muted-soft);
  font:600 .72rem/1 var(--mono);
  letter-spacing:.14em;
  text-transform:uppercase;
}
.priority-title{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:12px;
}
.priority-title strong{
  font-size:1.04rem;
  letter-spacing:.02em;
}
.priority-title .state{
  padding:5px 8px;
  border-radius:999px;
  background:rgba(196,217,0,.12);
  color:var(--lime);
  font:600 .7rem/1 var(--mono);
  text-transform:uppercase;
  letter-spacing:.12em;
}
.priority-path{
  font:700 1.1rem/1.2 var(--display);
  text-transform:uppercase;
  letter-spacing:.05em;
}
.priority-why{
  margin-top:10px;
  color:var(--muted);
  line-height:1.55;
}
.priority-list{
  display:grid;
  gap:9px;
  margin-top:14px;
}
.priority-item{
  display:flex;
  align-items:flex-start;
  gap:10px;
  color:var(--muted);
  font-size:.9rem;
}
.priority-item::before{
  content:"";
  width:7px;
  height:7px;
  margin-top:.48rem;
  border-radius:50%;
  background:linear-gradient(135deg, var(--brand-2), var(--lime));
  flex:0 0 auto;
}
.stats-rack{
  display:grid;
  gap:10px;
}
.rack-row{
  display:grid;
  grid-template-columns:1fr auto;
  gap:16px;
  padding:11px 12px;
  border-radius:14px;
  background:rgba(17,29,56,.58);
  border:1px solid rgba(84,171,238,.09);
}
.rack-row .label{
  color:var(--muted);
  font-size:.88rem;
}
.rack-row strong{
  font:700 .98rem/1 var(--mono);
}
.toolbar{
  display:grid;
  gap:16px;
  padding:18px 20px;
  border:1px solid rgba(84,171,238,.12);
  border-radius:var(--radius-lg);
  background:var(--panel);
  box-shadow:var(--shadow);
}
.toolbar-head{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:16px;
  flex-wrap:wrap;
}
.toolbar-copy strong{
  display:block;
  margin-bottom:6px;
  font:700 1rem/1.1 var(--display);
  text-transform:uppercase;
  letter-spacing:.08em;
}
.toolbar-copy p{
  margin:0;
  color:var(--muted);
  line-height:1.5;
  max-width:72ch;
}
.filters{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:12px;
}
.field{
  display:grid;
  gap:7px;
}
.field span{
  color:var(--muted-soft);
  font:600 .7rem/1 var(--mono);
  letter-spacing:.14em;
  text-transform:uppercase;
}
.field input,
.field select{
  width:100%;
  min-height:42px;
  padding:0 12px;
  color:var(--text);
  background:rgba(9,17,31,.58);
  border:1px solid rgba(84,171,238,.14);
  border-radius:12px;
  outline:none;
}
.field input:focus,
.field select:focus{
  border-color:rgba(84,171,238,.34);
  box-shadow:0 0 0 3px rgba(0,82,204,.14);
}
.toolbar-meta{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  flex-wrap:wrap;
}
.toolbar-summary{
  color:var(--muted);
  font-size:.9rem;
}
.toolbar-actions{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
}
.view-panel{
  display:none;
  gap:18px;
}
.view-panel.active{display:grid}
.metrics-grid{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:14px;
}
.metric-card{
  position:relative;
  overflow:hidden;
  padding:18px 18px 16px;
  border-radius:20px;
  border:1px solid rgba(84,171,238,.12);
  background:
    linear-gradient(160deg, rgba(17,29,56,.92), rgba(10,18,35,.92)),
    radial-gradient(circle at top right, rgba(84,171,238,.14), transparent 35%);
  box-shadow:var(--shadow);
}
.metric-card::after{
  content:"";
  position:absolute;
  inset:auto 18px 0 18px;
  height:2px;
  border-radius:999px;
  background:linear-gradient(90deg, transparent, var(--tone, var(--brand-2)), transparent);
}
.metric-card .kicker{
  color:var(--muted-soft);
  font:600 .69rem/1 var(--mono);
  letter-spacing:.14em;
  text-transform:uppercase;
}
.metric-card .value{
  margin:12px 0 8px;
  font:700 clamp(1.55rem, 2vw, 2.4rem)/1 var(--display);
  letter-spacing:.03em;
}
.metric-card .detail{
  color:var(--muted);
  font-size:.88rem;
  line-height:1.45;
}
.metric-card[data-tone="lime"]{--tone:var(--lime)}
.metric-card[data-tone="orange"]{--tone:var(--orange)}
.metric-card[data-tone="blue"]{--tone:var(--brand-2)}
.metric-card[data-tone="green"]{--tone:var(--green)}
.metric-card[data-tone="danger"]{--tone:var(--danger)}
.columns{
  display:grid;
  grid-template-columns:1.12fr .88fr;
  gap:18px;
}
.panel{
  padding:20px;
  border-radius:var(--radius-lg);
  border:1px solid rgba(84,171,238,.12);
  background:var(--panel);
  box-shadow:var(--shadow);
}
.panel-header{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:16px;
  flex-wrap:wrap;
  margin-bottom:16px;
}
.panel-header h3{
  margin:0;
  font:700 1.02rem/1 var(--display);
  text-transform:uppercase;
  letter-spacing:.08em;
}
.panel-header p{
  margin:8px 0 0;
  color:var(--muted);
  max-width:60ch;
  line-height:1.5;
  font-size:.92rem;
}
.chip{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:8px 10px;
  border-radius:999px;
  border:1px solid rgba(84,171,238,.14);
  background:rgba(255,255,255,.03);
  color:var(--muted);
  font:600 .72rem/1 var(--mono);
  text-transform:uppercase;
  letter-spacing:.12em;
}
.chip strong{
  font:700 .84rem/1 var(--mono);
  color:var(--text);
}
.alert-stack,.stack-list,.integration-grid,.cards-3{
  display:grid;
  gap:12px;
}
.cards-3{
  grid-template-columns:repeat(3,minmax(0,1fr));
}
.focus-card,.integration-card,.catalog-card{
  padding:16px;
  border-radius:18px;
  border:1px solid rgba(84,171,238,.1);
  background:rgba(9,17,31,.48);
}
.focus-card strong,
.integration-card strong,
.catalog-card strong{
  display:block;
  margin-bottom:8px;
  font-size:.95rem;
  letter-spacing:.02em;
}
.focus-card p,
.integration-card p,
.catalog-card p{
  margin:0;
  color:var(--muted);
  line-height:1.5;
  font-size:.9rem;
}
.alert-card{
  padding:16px;
  border-radius:18px;
  border:1px solid rgba(84,171,238,.1);
  background:rgba(9,17,31,.48);
}
.alert-card[data-level="critical"]{border-color:rgba(255,123,123,.28);background:linear-gradient(145deg, rgba(255,123,123,.12), rgba(9,17,31,.52))}
.alert-card[data-level="warning"]{border-color:rgba(255,170,25,.24);background:linear-gradient(145deg, rgba(255,170,25,.12), rgba(9,17,31,.52))}
.alert-card[data-level="notice"]{border-color:rgba(84,171,238,.22)}
.alert-top{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:12px;
  margin-bottom:10px;
}
.alert-headline{
  font-weight:700;
  letter-spacing:.02em;
}
.alert-level{
  flex:0 0 auto;
  padding:5px 8px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  color:var(--muted);
  font:600 .68rem/1 var(--mono);
  text-transform:uppercase;
}
.alert-body{
  color:var(--muted);
  line-height:1.55;
  font-size:.92rem;
}
.alert-next{
  margin-top:10px;
  color:#f6f9ff;
  font:600 .84rem/1.45 var(--body);
}
.trend-card{
  padding:18px;
  border-radius:20px;
  border:1px solid rgba(84,171,238,.12);
  background:rgba(9,17,31,.52);
}
.trend-card + .trend-card{margin-top:12px}
.trend-top{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:12px;
  margin-bottom:12px;
}
.trend-top strong{
  font-size:.96rem;
  letter-spacing:.02em;
}
.trend-top span{
  color:var(--muted);
  font-size:.86rem;
}
.chart{
  width:100%;
  height:180px;
  overflow:hidden;
  border-radius:16px;
  border:1px solid rgba(84,171,238,.08);
  background:
    linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,0)),
    linear-gradient(rgba(84,171,238,.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(84,171,238,.04) 1px, transparent 1px);
  background-size:auto, auto 36px, 56px auto;
}
.chart svg{display:block;width:100%;height:100%}
.chart-empty{
  display:grid;
  place-items:center;
  color:var(--muted-soft);
  font-size:.88rem;
}
.bar-list{display:grid;gap:12px}
.bar-item{
  display:grid;
  gap:7px;
}
.bar-meta{
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:10px;
}
.bar-label{
  font-weight:600;
  letter-spacing:.02em;
}
.bar-detail{
  color:var(--muted);
  font-size:.83rem;
}
.bar-track{
  position:relative;
  height:10px;
  overflow:hidden;
  border-radius:999px;
  background:rgba(225,233,243,.08);
}
.bar-fill{
  position:absolute;
  inset:0 auto 0 0;
  width:0;
  border-radius:999px;
  background:linear-gradient(90deg, var(--brand), var(--brand-2));
}
.bar-fill[data-tone="lime"]{background:linear-gradient(90deg, #96a60a, var(--lime))}
.bar-fill[data-tone="orange"]{background:linear-gradient(90deg, #cf7b00, var(--orange))}
.bar-fill[data-tone="green"]{background:linear-gradient(90deg, #16653a, var(--green))}
.table-wrap{
  overflow:auto;
  border-radius:18px;
  border:1px solid rgba(84,171,238,.1);
  background:rgba(7,16,29,.45);
}
table{
  width:100%;
  min-width:860px;
  border-collapse:collapse;
}
th,td{
  padding:12px 14px;
  text-align:left;
  vertical-align:top;
}
th{
  position:sticky;
  top:0;
  z-index:1;
  background:rgba(10,18,35,.94);
  color:var(--muted-soft);
  font:600 .68rem/1 var(--mono);
  text-transform:uppercase;
  letter-spacing:.14em;
  border-bottom:1px solid rgba(84,171,238,.14);
}
td{
  border-top:1px solid rgba(84,171,238,.08);
  font-size:.92rem;
  line-height:1.45;
}
tr:hover td{background:rgba(84,171,238,.045)}
.mono{font-family:var(--mono)}
.muted{color:var(--muted)}
.pill{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:5px 9px;
  border-radius:999px;
  border:1px solid rgba(84,171,238,.14);
  background:rgba(255,255,255,.04);
  color:#edf4ff;
  font:600 .71rem/1 var(--mono);
  letter-spacing:.04em;
  white-space:nowrap;
}
.pill.ready{border-color:rgba(46,167,93,.24);color:#b7f0cb}
.pill.degraded{border-color:rgba(255,170,25,.24);color:#ffd99a}
.pill.fail{border-color:rgba(255,123,123,.24);color:#ffc1c1}
.pill.compat{border-color:rgba(84,171,238,.24);color:#b9d7ff}
.pill.subtle{color:var(--muted)}
.tiny{
  color:var(--muted-soft);
  font-size:.78rem;
  line-height:1.45;
}
.empty{
  display:grid;
  place-items:center;
  padding:28px 18px;
  color:var(--muted-soft);
  font-size:.9rem;
}
.code{
  display:block;
  margin-top:10px;
  padding:12px 14px;
  overflow:auto;
  border-radius:16px;
  border:1px solid rgba(84,171,238,.1);
  background:#081120;
  color:#dce8ff;
  font:500 .84rem/1.55 var(--mono);
  white-space:pre-wrap;
}
.foot-note{
  color:var(--muted-soft);
  font-size:.84rem;
  line-height:1.55;
}
@media (max-width: 1180px){
  .shell{grid-template-columns:1fr}
  .rail{
    position:relative;
    top:0;
    height:auto;
  }
  .metrics-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .columns,.hero-ribbon,.cards-3{grid-template-columns:1fr}
}
@media (max-width: 720px){
  .shell{padding:14px}
  .hero{padding:18px}
  .toolbar,.panel{padding:16px}
  .metrics-grid{grid-template-columns:1fr}
  .nav{grid-template-columns:1fr 1fr}
}
</style>
</head>
<body>
<div class="shell">
  <aside class="rail">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true"></div>
      <div class="brand-copy">
        <h1>fusion<span class="accent">AI</span>ze Gate</h1>
        <p>Local-first routing cockpit for direct providers, aggregators, and agent-native clients.</p>
      </div>
    </div>
    <div class="rail-meta" id="rail-meta">
      <div class="rail-stat">
        <span class="kicker">Request readiness</span>
        <strong id="rail-readiness">Loading…</strong>
      </div>
      <div class="rail-stat">
        <span class="kicker">Top pressure</span>
        <strong id="rail-pressure">Loading…</strong>
      </div>
      <div class="rail-stat">
        <span class="kicker">Priority next</span>
        <strong id="rail-next">Loading…</strong>
      </div>
    </div>
    <nav class="nav" aria-label="Dashboard sections">
      <button type="button" data-view="overview" class="active"><span class="label">Overview</span><span class="num">01</span></button>
      <button type="button" data-view="providers"><span class="label">Providers</span><span class="num">02</span></button>
      <button type="button" data-view="clients"><span class="label">Clients</span><span class="num">03</span></button>
      <button type="button" data-view="routes"><span class="label">Routes</span><span class="num">04</span></button>
      <button type="button" data-view="analytics"><span class="label">Analytics</span><span class="num">05</span></button>
      <button type="button" data-view="catalog"><span class="label">Catalog</span><span class="num">06</span></button>
      <button type="button" data-view="integrations"><span class="label">Integrations</span><span class="num">07</span></button>
    </nav>
    <div class="rail-note">
      <strong>Operator stance</strong><br>
      Trust the lane, inspect the route, and spend premium budget only where the request actually earns it.
    </div>
  </aside>

  <main class="content">
    <section class="hero">
      <div class="hero-top">
        <div>
          <div class="eyebrow"><span class="pulse" id="status-pulse"></span><span id="hero-status">Gateway health is loading</span></div>
          <h2>Dark-mode <span class="accent">operator cockpit</span></h2>
          <p>fusionAIze Gate now reads more like a live routing desk than a local admin page: health confidence first, spend pressure second, explainability always visible, and setup guidance close to the traffic it affects.</p>
        </div>
        <div class="hero-actions">
          <button class="btn primary" type="button" id="refresh-btn">Refresh now</button>
          <button class="btn secondary" type="button" id="apply-btn">Apply filters</button>
          <button class="btn ghost" type="button" id="clear-btn">Clear filters</button>
          <span class="chip">Updated <strong id="ago">—</strong></span>
        </div>
      </div>
      <div class="hero-ribbon">
        <div class="ribbon-panel">
          <div class="priority-title">
            <strong>Priority next</strong>
            <span class="state" id="priority-state">loading</span>
          </div>
          <div class="priority-path" id="priority-path">Loading priority path</div>
          <div class="priority-why" id="priority-why">The gateway is calculating the next safest operator move.</div>
          <div class="priority-list" id="priority-list"></div>
        </div>
        <div class="ribbon-panel">
          <div class="ribbon-title">Snapshot</div>
          <div class="stats-rack" id="snapshot-rack"></div>
        </div>
      </div>
    </section>

    <section class="toolbar">
      <div class="toolbar-head">
        <div class="toolbar-copy">
          <strong>Filters and live scope</strong>
          <p>Narrow the cockpit to one provider, one client family, one layer, or one success state. The same filter scope drives overview, tables, traces, and request history.</p>
        </div>
        <span class="chip" id="scope-chip">All traffic</span>
      </div>
      <div class="filters">
        <label class="field"><span>Provider</span><input id="filter-provider" placeholder="kilo-sonnet"></label>
        <label class="field"><span>Modality</span>
          <select id="filter-modality">
            <option value="">All modalities</option>
            <option value="chat">chat</option>
            <option value="image_generation">image_generation</option>
            <option value="image_editing">image_editing</option>
          </select>
        </label>
        <label class="field"><span>Client profile</span><input id="filter-profile" placeholder="claude"></label>
        <label class="field"><span>Client tag</span><input id="filter-client" placeholder="claude-code"></label>
        <label class="field"><span>Layer</span>
          <select id="filter-layer">
            <option value="">All layers</option>
            <option value="policy">policy</option>
            <option value="static">static</option>
            <option value="heuristic">heuristic</option>
            <option value="hook">hook</option>
            <option value="profile">profile</option>
            <option value="llm-classify">llm-classify</option>
            <option value="fallback">fallback</option>
            <option value="direct">direct</option>
          </select>
        </label>
        <label class="field"><span>Status</span>
          <select id="filter-success">
            <option value="">All</option>
            <option value="true">Success</option>
            <option value="false">Failure</option>
          </select>
        </label>
      </div>
      <div class="toolbar-meta">
        <div class="toolbar-summary" id="filter-summary">No active filters</div>
        <div class="toolbar-actions">
          <button class="btn secondary" type="button" data-target-view="providers">Go to providers</button>
          <button class="btn secondary" type="button" data-target-view="integrations">Open integrations</button>
        </div>
      </div>
    </section>

    <section class="view-panel active" id="view-overview">
      <div class="metrics-grid" id="overview-cards"></div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>What needs attention</h3>
              <p>High-signal guidance from health, route pressure, catalog freshness, and operator events.</p>
            </div>
            <span class="chip" id="focus-chip">Loading</span>
          </div>
          <div class="alert-stack" id="overview-alerts"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Spend and traffic</h3>
              <p>Lightweight built-in charts keep the overview tactile without introducing a frontend build stack.</p>
            </div>
          </div>
          <div id="overview-trends"></div>
        </div>
      </div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Lane families</h3>
              <p>Which canonical families are carrying traffic, under cooldown pressure, or due for strengthening.</p>
            </div>
          </div>
          <div class="bar-list" id="overview-families"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Recent request log</h3>
              <p>The shortest path from “something feels off” to a specific request, route, and status.</p>
            </div>
          </div>
          <div class="table-wrap"><table id="overview-recent"><thead><tr><th>Time</th><th>Provider</th><th>Lane</th><th>Client</th><th>Latency</th><th>Cost</th><th>Status</th></tr></thead><tbody></tbody></table></div>
        </div>
      </div>
    </section>

    <section class="view-panel" id="view-providers">
      <div class="cards-3" id="providers-summary"></div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3>Provider fleet</h3>
            <p>Request-readiness, billing mode, quota coupling, runtime penalties, and lane context in one table.</p>
          </div>
          <span class="chip" id="providers-chip">Inventory</span>
        </div>
        <div class="table-wrap"><table id="providers-table"><thead><tr><th>Provider</th><th>Status</th><th>Lane</th><th>Route</th><th>Billing + quota</th><th>Requests</th><th>Cost</th><th>Latency</th><th>Operator note</th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <section class="view-panel" id="view-clients">
      <div class="cards-3" id="clients-highlights"></div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3>Client posture</h3>
            <p>See which tools are expensive, slow, or failure-heavy, then decide where `coding-auto`, `eco`, or `premium` should really land.</p>
          </div>
        </div>
        <div class="table-wrap"><table id="clients-table"><thead><tr><th>Client</th><th>Profile</th><th>Requests</th><th>Success</th><th>Tokens</th><th>Cost</th><th>Cost / req</th><th>Latency</th><th>Providers</th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <section class="view-panel" id="view-routes">
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Selection paths</h3>
              <p>Same-lane, same-cluster, and fallback-chain behavior should be legible, not magical.</p>
            </div>
          </div>
          <div class="bar-list" id="routes-selection"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Route pressure</h3>
              <p>Cooldown and recovery signals reveal where resilience is real and where it still depends on operator help.</p>
            </div>
          </div>
          <div class="bar-list" id="routes-pressure"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3>Routing breakdown</h3>
            <p>Chosen rule, selected provider, canonical lane, and observed runtime state for successful traffic.</p>
          </div>
        </div>
        <div class="table-wrap"><table id="routes-table"><thead><tr><th>Layer</th><th>Rule</th><th>Provider</th><th>Lane family</th><th>Selection path</th><th>Requests</th><th>Cost</th><th>Latency</th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <section class="view-panel" id="view-analytics">
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>30-day cost trend</h3>
              <p>Financial-desk style long view of requests, spend, and failure pressure.</p>
            </div>
          </div>
          <div id="analytics-daily"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>24-hour traffic pulse</h3>
              <p>Short-window request flow for detecting fallbacks, spikes, and cold periods.</p>
            </div>
          </div>
          <div id="analytics-hourly"></div>
        </div>
      </div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Modality mix</h3>
              <p>How different request types distribute across providers and layers.</p>
            </div>
          </div>
          <div class="table-wrap"><table id="analytics-modalities"><thead><tr><th>Modality</th><th>Provider</th><th>Layer</th><th>Requests</th><th>Cost</th><th>Latency</th></tr></thead><tbody></tbody></table></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Operator actions</h3>
              <p>Update checks and local operator events, surfaced beside the traffic they affect.</p>
            </div>
          </div>
          <div class="table-wrap"><table id="analytics-operators"><thead><tr><th>Event</th><th>Action</th><th>Status</th><th>Target</th><th>Eligible</th><th>Events</th></tr></thead><tbody></tbody></table></div>
        </div>
      </div>
    </section>

    <section class="view-panel" id="view-catalog">
      <div class="cards-3" id="catalog-summary"></div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Catalog alerts</h3>
              <p>Freshness drift, source issues, and model mismatches should stay visible before they become routing debt.</p>
            </div>
          </div>
          <div class="alert-stack" id="catalog-alerts"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Refresh guidance</h3>
              <p>Where to review now, what to refresh soon, and which assumptions are still trustworthy.</p>
            </div>
          </div>
          <div class="bar-list" id="catalog-guidance"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3>Tracked provider assumptions</h3>
            <p>Configured model, recommended model, offer track, volatility, and evidence quality in one surface.</p>
          </div>
        </div>
        <div class="table-wrap"><table id="catalog-table"><thead><tr><th>Provider</th><th>Status</th><th>Configured</th><th>Recommended</th><th>Offer track</th><th>Volatility</th><th>Reviewed</th><th>Why it matters</th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <section class="view-panel" id="view-integrations">
      <div class="integration-grid">
        <div class="integration-card">
          <strong>Claude Code</strong>
          <p>Anthropic-compatible local endpoint for daily-use coding flows. Use `coding-auto` when you want cheapest-capable behavior, not a fixed premium provider.</p>
          <code class="code">export ANTHROPIC_BASE_URL=http://127.0.0.1:8090
export ANTHROPIC_AUTH_TOKEN=dummy-local-token
claude --model coding-auto</code>
        </div>
        <div class="integration-card">
          <strong>OpenAI-compatible tools</strong>
          <p>Cursor-style tools, Continue, Cline, scripts, and agent shells should point at one local endpoint and use Gate modes instead of raw provider names.</p>
          <code class="code">export OPENAI_BASE_URL=http://127.0.0.1:8090/v1
export OPENAI_API_KEY=dummy-local-token
# models: auto, coding-auto, coding-fast, coding-premium, eco, premium</code>
        </div>
        <div class="integration-card">
          <strong>Agent-native clients</strong>
          <p>Use client-aware entry points for `opencode`, `openclaw`, local automation, and future n8n flows. Keep the client identity visible so the router can treat them differently.</p>
          <code class="code">Recommended mental model

light coding       -> coding-auto
cheap background   -> eco
high-trust coding  -> coding-premium
manual hard task   -> premium</code>
        </div>
      </div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Why this surface is different</h3>
              <p>Not hosted-first. Not black-box stacks. Not provider-string roulette.</p>
            </div>
          </div>
          <div class="cards-3">
            <div class="focus-card">
              <strong>Local-first security</strong>
              <p>Your keys, routes, and request traces stay on your machine unless you explicitly wire in remote services.</p>
            </div>
            <div class="focus-card">
              <strong>Agent-native routing</strong>
              <p>Claude Code, opencode, openclaw, and OpenAI-compatible clients are traffic shapes with different economics, not identical callers.</p>
            </div>
            <div class="focus-card">
              <strong>Explainable by default</strong>
              <p>Lane family, selection path, route type, quota coupling, and freshness are visible in the same operator surface.</p>
            </div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Troubleshooting shortcuts</h3>
              <p>Short recovery paths for the things that break in the real world.</p>
            </div>
          </div>
          <div class="alert-stack" id="integration-alerts"></div>
          <p class="foot-note">If a model is unexpectedly expensive, first check the client model id, then the selected lane, then the actual route type. Gate can only be “cheapest capable” if the client enters through the right intent surface.</p>
        </div>
      </div>
    </section>
  </main>
</div>

<script>
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const VIEW_IDS = ['overview','providers','clients','routes','analytics','catalog','integrations'];
let currentView = 'overview';

const fmt = (n, d = 2) => n != null ? Number(n).toLocaleString('en', {minimumFractionDigits:d, maximumFractionDigits:d}) : '—';
const fmtUsd = n => n != null ? (Number(n) <= 0 ? '$0.00' : '$' + fmt(n, Number(n) < 0.01 ? 4 : 2)) : '—';
const fmtTok = n => n != null ? (n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'K' : '' + Number(n)) : '0';
const fmtMs = n => n != null ? fmt(n, 0) + 'ms' : '—';
const fmtPct = n => n != null ? fmt(n, 1) + '%' : '—';
const ago = ts => {
  if (!ts) return '—';
  const s = Math.max(0, Date.now() / 1000 - Number(ts));
  if (s < 60) return Math.round(s) + 's ago';
  if (s < 3600) return Math.round(s / 60) + 'm ago';
  if (s < 86400) return Math.round(s / 3600) + 'h ago';
  return Math.round(s / 86400) + 'd ago';
};
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

function currentFilters() {
  const params = new URLSearchParams();
  const mapping = {
    provider: $('#filter-provider').value.trim(),
    modality: $('#filter-modality').value.trim(),
    client_profile: $('#filter-profile').value.trim(),
    client_tag: $('#filter-client').value.trim(),
    layer: $('#filter-layer').value.trim(),
    success: $('#filter-success').value.trim(),
    view: currentView,
  };
  Object.entries(mapping).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params;
}

function syncStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  $('#filter-provider').value = params.get('provider') || '';
  $('#filter-modality').value = params.get('modality') || '';
  $('#filter-profile').value = params.get('client_profile') || '';
  $('#filter-client').value = params.get('client_tag') || '';
  $('#filter-layer').value = params.get('layer') || '';
  $('#filter-success').value = params.get('success') || '';
  setView(params.get('view') || 'overview', false);
}

function describeFilters(params) {
  const parts = [];
  for (const [key, value] of params.entries()) {
    if (key === 'view') continue;
    parts.push(key + '=' + value);
  }
  $('#filter-summary').textContent = parts.length ? 'Active scope: ' + parts.join(', ') : 'No active filters';
  $('#scope-chip').textContent = parts.length ? parts.join(' · ') : 'All traffic';
}

function persistState(params) {
  const qs = params.toString();
  const next = qs ? window.location.pathname + '?' + qs : window.location.pathname;
  window.history.replaceState({}, '', next);
  describeFilters(params);
}

function setView(view, persist = true) {
  currentView = VIEW_IDS.includes(view) ? view : 'overview';
  VIEW_IDS.forEach(id => {
    const panel = $('#view-' + id);
    if (panel) panel.classList.toggle('active', id === currentView);
  });
  $$('.nav button').forEach(button => button.classList.toggle('active', button.dataset.view === currentView));
  if (persist) persistState(currentFilters());
}

function applyFilters() {
  load();
}

function clearFilters() {
  ['#filter-provider', '#filter-modality', '#filter-profile', '#filter-client', '#filter-layer', '#filter-success'].forEach(sel => { $(sel).value = ''; });
  load();
}

function pill(label, kind = 'subtle') {
  return '<span class="pill ' + kind + '">' + esc(label) + '</span>';
}

function empty(label) {
  return '<div class="empty">' + esc(label) + '</div>';
}

function tableEmpty(colspan, label) {
  return '<tr><td colspan="' + colspan + '" class="empty">' + esc(label) + '</td></tr>';
}

function toneByAlertLevel(level) {
  if (level === 'critical') return 'danger';
  if (level === 'warning') return 'orange';
  if (level === 'notice') return 'blue';
  return 'green';
}

function readinessKind(status) {
  const s = String(status || '').toLowerCase();
  if (s === 'ready' || s === 'ready-verified') return 'ready';
  if (s === 'ready-compat') return 'compat';
  if (s === 'ready-degraded') return 'degraded';
  return 'fail';
}

function trendChart(values, opts = {}) {
  const width = 760;
  const height = opts.height || 180;
  const pad = 14;
  const tone = opts.tone || '#54ABEE';
  const fill = opts.fill || 'rgba(84,171,238,.16)';
  if (!values.length || values.every(v => !Number(v))) {
    return '<div class="chart"><div class="chart-empty">No trend data for the current scope</div></div>';
  }
  const nums = values.map(v => Number(v) || 0);
  const max = Math.max(...nums, 1);
  const min = Math.min(...nums, 0);
  const range = Math.max(1, max - min);
  const step = nums.length > 1 ? (width - pad * 2) / (nums.length - 1) : 0;
  const coords = nums.map((value, index) => {
    const x = pad + step * index;
    const y = height - pad - ((value - min) / range) * (height - pad * 2);
    return [x, y];
  });
  const line = coords.map(([x, y]) => x.toFixed(1) + ',' + y.toFixed(1)).join(' ');
  const area = 'M ' + coords[0][0].toFixed(1) + ' ' + (height - pad).toFixed(1)
    + ' L ' + coords.map(([x, y]) => x.toFixed(1) + ' ' + y.toFixed(1)).join(' L ')
    + ' L ' + coords[coords.length - 1][0].toFixed(1) + ' ' + (height - pad).toFixed(1) + ' Z';
  const labels = (opts.labels || []).filter(Boolean);
  const last = nums[nums.length - 1];
  const peak = Math.max(...nums);
  const avg = nums.reduce((sum, value) => sum + value, 0) / nums.length;
  return `
    <div class="trend-card">
      <div class="trend-top">
        <div>
          <strong>${esc(opts.title || 'Trend')}</strong>
          <span>${esc(opts.subtitle || '')}</span>
        </div>
        <div class="tiny mono">last ${esc(opts.format ? opts.format(last) : fmt(last, 0))} · avg ${esc(opts.format ? opts.format(avg) : fmt(avg, 0))} · peak ${esc(opts.format ? opts.format(peak) : fmt(peak, 0))}</div>
      </div>
      <div class="chart">
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${esc(opts.title || 'trend chart')}">
          <defs>
            <linearGradient id="fill-${esc((opts.title || 'trend').replace(/[^a-z0-9]+/gi,'-').toLowerCase())}" x1="0%" x2="0%" y1="0%" y2="100%">
              <stop offset="0%" stop-color="${tone}" stop-opacity=".35"></stop>
              <stop offset="100%" stop-color="${tone}" stop-opacity="0"></stop>
            </linearGradient>
          </defs>
          <path d="${area}" fill="url(#fill-${esc((opts.title || 'trend').replace(/[^a-z0-9]+/gi,'-').toLowerCase())})"></path>
          <polyline points="${line}" fill="none" stroke="${tone}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
          ${coords.map(([x, y], index) => index === coords.length - 1 ? '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="5" fill="' + tone + '"></circle>' : '').join('')}
        </svg>
      </div>
      ${labels.length ? '<div class="tiny" style="margin-top:10px">' + esc(labels[0]) + ' → ' + esc(labels[labels.length - 1]) + '</div>' : ''}
    </div>
  `;
}

function barList(rows, opts = {}) {
  if (!rows.length) return empty(opts.empty || 'No data');
  const max = Math.max(...rows.map(row => Number(opts.value(row)) || 0), 1);
  return rows.map(row => {
    const value = Number(opts.value(row)) || 0;
    const pct = Math.max(4, Math.round((value / max) * 100));
    return `
      <div class="bar-item">
        <div class="bar-meta">
          <div>
            <div class="bar-label">${esc(opts.label(row))}</div>
            <div class="bar-detail">${esc(opts.detail ? opts.detail(row) : '')}</div>
          </div>
          <div class="mono">${esc(opts.format ? opts.format(value, row) : fmt(value, 0))}</div>
        </div>
        <div class="bar-track"><div class="bar-fill" data-tone="${esc(opts.tone || 'blue')}" style="width:${pct}%"></div></div>
      </div>
    `;
  }).join('');
}

function metricCard({kicker, value, detail, tone}) {
  return `
    <article class="metric-card" data-tone="${esc(tone || 'blue')}">
      <div class="kicker">${esc(kicker)}</div>
      <div class="value">${esc(value)}</div>
      <div class="detail">${esc(detail)}</div>
    </article>
  `;
}

function alertCard(alert) {
  const level = alert.level || alert.severity || 'notice';
  return `
    <article class="alert-card" data-level="${esc(level)}">
      <div class="alert-top">
        <div class="alert-headline">${esc(alert.headline || alert.message || 'Operator alert')}</div>
        <span class="alert-level">${esc(level)}</span>
      </div>
      <div class="alert-body">${esc(alert.detail || alert.message || '')}</div>
      ${alert.suggestion ? '<div class="alert-next">Next: ' + esc(alert.suggestion) + '</div>' : ''}
    </article>
  `;
}

function integrationAlert(title, detail) {
  return `
    <article class="focus-card">
      <strong>${esc(title)}</strong>
      <p>${esc(detail)}</p>
    </article>
  `;
}

function topAlertBundle(bundle) {
  const alerts = [];
  if (bundle.update && (bundle.update.alert_level === 'critical' || bundle.update.alert_level === 'warning')) {
    alerts.push({
      level: bundle.update.alert_level,
      headline: 'Release update posture',
      detail: bundle.update.recommended_action || 'A release or channel review is recommended.',
      suggestion: bundle.update.latest_version ? 'Review ' + bundle.update.latest_version + ' before the next tuning pass.' : 'Review the release channel and update cadence.',
    });
  }
  (bundle.catalog.alerts || []).slice(0, 2).forEach(alert => {
    alerts.push({
      level: alert.severity || 'notice',
      headline: alert.provider ? alert.provider + ': ' + (alert.code || 'catalog alert') : (alert.code || 'catalog alert'),
      detail: alert.message || 'Provider catalog drift needs attention.',
      suggestion: alert.recommended_model ? 'Check the recommended model ' + alert.recommended_model + '.' : 'Refresh the provider catalog or review the source trail.',
    });
  });
  const unhealthy = (bundle.inventory.providers || []).filter(row => row.healthy === false);
  if (unhealthy.length) {
    const top = unhealthy[0];
    alerts.unshift({
      level: 'warning',
      headline: top.name + ' is currently unhealthy',
      detail: top.last_error || 'The route is failing live health checks or request-readiness checks.',
      suggestion: ((top.request_readiness || {}).operator_hint) || 'Inspect provider detail and recent route traces before sending more primary traffic here.',
    });
  }
  if (!alerts.length) {
    alerts.push({
      level: 'notice',
      headline: 'No active operator alert',
      detail: 'The gateway is currently healthy enough to focus on cost posture, client defaults, and lane hygiene.',
      suggestion: 'Inspect the highest-cost client and make sure it enters through coding-auto, eco, or premium on purpose.',
    });
  }
  return alerts;
}

function derivePriority(bundle) {
  const alerts = topAlertBundle(bundle);
  const providers = bundle.inventory.providers || [];
  const readiness = bundle.inventory.request_readiness || {};
  const clientHighlights = bundle.stats.client_highlights || {};
  const topCost = clientHighlights.top_cost;
  const fallbackRows = (bundle.stats.selection_paths || []).filter(row => String(row.selection_path || '').includes('fallback'));
  const fallbackRequests = fallbackRows.reduce((sum, row) => sum + (Number(row.requests) || 0), 0);
  const path = alerts.length ? 'Operator focus' : 'Healthy routing';
  let state = 'stable';
  let priorityPath = 'Tune client defaults';
  let why = 'The next best move is tightening entry intents so cheap-capable traffic does not accidentally land on premium routes.';
  if ((readiness.providers_not_ready || 0) > 0) {
    state = 'guard';
    priorityPath = 'Providers → request-readiness';
    why = 'At least one route is not request-ready, so the safest next move is checking live health, cooldown state, and quota coupling.';
  } else if (alerts[0] && (alerts[0].level === 'critical' || alerts[0].level === 'warning')) {
    state = alerts[0].level;
    priorityPath = 'Review top alert';
    why = alerts[0].detail || why;
  } else if (topCost && Number(topCost.cost_usd || 0) > 0.5) {
    state = 'spend';
    priorityPath = 'Clients → highest-cost profile';
    why = (topCost.client_tag || topCost.client_profile || 'The top-cost client') + ' is carrying real spend; confirm that it should be on a premium entry mode instead of coding-auto or eco.';
  } else if (fallbackRequests > 0) {
    state = 'fallback';
    priorityPath = 'Routes → selection paths';
    why = 'Fallback traffic is present. Validate whether the fallback share is desirable resilience or evidence that your primary defaults are still misaligned.';
  }
  const list = [
    'Cheapest-capable should come from client entry modes, not provider strings.',
    'If a route is premium, make the reason legible in the route and client views.',
    'Refresh stale catalog assumptions before reshaping high-traffic families.',
  ];
  return {state, path, why, list, ribbon: path};
}

function providerRow(row, metricsLookup) {
  const lane = row.lane || {};
  const transport = row.transport || {};
  const readiness = row.request_readiness || {};
  const runtime = row.route_runtime_state || {};
  const metric = metricsLookup[row.name] || {};
  const readinessLabel = readiness.status || (row.healthy ? 'ready' : 'degraded');
  const quotaBits = [];
  if (transport.billing_mode) quotaBits.push(transport.billing_mode);
  if (transport.quota_group) quotaBits.push('quota:' + transport.quota_group);
  if (transport.quota_isolated) quotaBits.push('isolated');
  return `
    <tr>
      <td>
        <strong>${esc(row.name)}</strong>
        <div class="tiny mono">${esc(row.model || 'n/a')} · ${esc(row.backend || 'n/a')}</div>
      </td>
      <td>${pill(readinessLabel, readinessKind(readinessLabel))}</td>
      <td>
        <strong>${esc(lane.canonical_model || lane.name || 'unclassified')}</strong>
        <div class="tiny">${esc(lane.family || 'no family')} · ${esc(lane.cluster || 'no cluster')}</div>
      </td>
      <td>
        <strong>${esc(lane.route_type || 'direct')}</strong>
        <div class="tiny">${esc(transport.profile || transport.compatibility || 'n/a')}</div>
      </td>
      <td class="tiny">${esc(quotaBits.join(' · ') || 'direct / uncoupled')}</td>
      <td class="mono">${fmtTok(metric.requests || 0)}</td>
      <td class="mono">${fmtUsd(metric.cost_usd || 0)}</td>
      <td class="mono">${fmtMs(row.avg_latency_ms || metric.avg_latency_ms || 0)}</td>
      <td class="tiny">${esc((readiness.operator_hint || row.last_error || runtime.last_issue_type || 'Healthy enough for current traffic')).slice(0, 180)}</td>
    </tr>
  `;
}

function recentRows(rows, limit = 8) {
  if (!rows.length) return tableEmpty(7, 'No requests for the current scope');
  return rows.slice(0, limit).map(row => `
    <tr>
      <td class="mono">${esc(ago(row.timestamp))}</td>
      <td>${esc(row.provider || '—')}</td>
      <td>${esc(row.canonical_model || row.rule_name || '—')}</td>
      <td>${esc(row.client_tag || row.client_profile || 'generic')}</td>
      <td class="mono">${fmtMs(row.latency_ms || 0)}</td>
      <td class="mono">${fmtUsd(row.cost_usd || 0)}</td>
      <td>${row.success ? pill('success', 'ready') : pill('failure', 'fail')}</td>
    </tr>
  `).join('');
}

function render(bundle) {
  const totals = bundle.stats.totals || {};
  const providers = bundle.inventory.providers || [];
  const providerMetrics = Object.fromEntries((bundle.stats.providers || []).map(row => [row.provider, row]));
  const clientTotals = bundle.stats.client_totals || [];
  const routing = bundle.stats.routing || [];
  const selectionPaths = bundle.stats.selection_paths || [];
  const laneFamilies = bundle.stats.lane_families || [];
  const recent = bundle.recent.requests || [];
  const traces = bundle.traces.traces || [];
  const catalogItems = bundle.catalog.items || [];
  const sourceCatalog = bundle.catalog.source_catalog || {};
  const catalogAlerts = (bundle.catalog.alerts || []).concat(bundle.catalog.source_alerts || []);
  const operatorRows = bundle.operators.events || [];
  const modalityRows = bundle.stats.modalities || [];
  const priority = derivePriority(bundle);
  const alerts = topAlertBundle(bundle);
  const readiness = bundle.inventory.request_readiness || {};

  $('#hero-status').textContent = (bundle.health.summary && bundle.health.summary.providers_unhealthy === 0) ? 'Gateway health looks stable' : 'Gateway has live pressure to inspect';
  $('#ago').textContent = ago(totals.last_request);
  $('#priority-state').textContent = priority.state;
  $('#priority-path').textContent = priority.path;
  $('#priority-why').textContent = priority.why;
  $('#priority-list').innerHTML = priority.list.map(item => '<div class="priority-item">' + esc(item) + '</div>').join('');
  $('#rail-readiness').textContent = (readiness.providers_ready || 0) + '/' + (readiness.providers_total || providers.length) + ' ready';
  $('#rail-pressure').textContent = alerts[0] ? alerts[0].headline : 'No active pressure';
  $('#rail-next').textContent = priority.path;
  $('#snapshot-rack').innerHTML = [
    ['Request-ready', (readiness.providers_ready || 0) + ' / ' + (readiness.providers_total || providers.length)],
    ['Healthy providers', (bundle.health.summary ? bundle.health.summary.providers_healthy : providers.filter(row => row.healthy).length) + ' / ' + providers.length],
    ['Fallback share', fmtPct(((selectionPaths.filter(row => String(row.selection_path || '').includes('fallback')).reduce((sum, row) => sum + (Number(row.requests) || 0), 0)) / Math.max(1, Number(totals.total_requests) || 1)) * 100)],
    ['Top lane family', laneFamilies.length ? (laneFamilies[0].lane_family || 'unclassified') : '—'],
    ['Top cost client', bundle.stats.client_highlights && bundle.stats.client_highlights.top_cost ? (bundle.stats.client_highlights.top_cost.client_tag || bundle.stats.client_highlights.top_cost.client_profile || 'generic') : '—'],
    ['Catalog due', String(sourceCatalog.due_sources || 0)],
  ].map(([label, value]) => `<div class="rack-row"><div class="label">${esc(label)}</div><strong>${esc(value)}</strong></div>`).join('');

  $('#overview-cards').innerHTML = [
    {kicker:'Requests', value:fmtTok(totals.total_requests || 0), detail:'Success ' + fmtPct(100 - ((Number(totals.total_failures || 0) / Math.max(1, Number(totals.total_requests || 1))) * 100)), tone:'blue'},
    {kicker:'Cost', value:fmtUsd(totals.total_cost_usd || 0), detail:fmtTok((totals.total_prompt_tokens || 0) + (totals.total_compl_tokens || 0)) + ' tokens total', tone:'orange'},
    {kicker:'Avg latency', value:fmtMs(totals.avg_latency_ms || 0), detail:'Last request ' + ago(totals.last_request), tone:'green'},
    {kicker:'Cache hit rate', value:fmtPct(totals.cache_hit_pct || 0), detail:fmtTok(totals.total_cache_hit || 0) + ' hit / ' + fmtTok(totals.total_cache_miss || 0) + ' miss', tone:'lime'},
    {kicker:'Fallback share', value:fmtPct((selectionPaths.filter(row => String(row.selection_path || '').includes('fallback')).reduce((sum, row) => sum + (Number(row.requests) || 0), 0) / Math.max(1, Number(totals.total_requests || 1))) * 100), detail:'Selection paths under fallback pressure', tone:'danger'},
    {kicker:'Request-ready', value:(readiness.providers_ready || 0) + '/' + (readiness.providers_total || providers.length), detail:String(readiness.providers_not_ready || 0) + ' not ready', tone:'blue'},
    {kicker:'Top client', value:esc(bundle.stats.client_highlights && bundle.stats.client_highlights.top_requests ? (bundle.stats.client_highlights.top_requests.client_tag || bundle.stats.client_highlights.top_requests.client_profile || 'generic') : '—'), detail:'Highest request volume right now', tone:'lime'},
    {kicker:'Catalog drift', value:String(bundle.catalog.alert_count || 0), detail:String(sourceCatalog.recent_changes || 0) + ' recent source changes', tone:'orange'},
  ].map(metricCard).join('');

  $('#focus-chip').innerHTML = alerts.length ? '<strong>' + esc(alerts.length) + '</strong> live callouts' : 'No active alert';
  $('#overview-alerts').innerHTML = alerts.map(alertCard).join('');

  $('#overview-trends').innerHTML = [
    trendChart((bundle.stats.daily || []).map(row => row.cost_usd || 0), {title:'Daily cost', subtitle:'30 day spend line', tone:'#FFAA19', format:fmtUsd, labels:(bundle.stats.daily || []).map(row => row.day || '')}),
    trendChart((bundle.stats.hourly || []).map(row => row.requests || 0), {title:'Hourly requests', subtitle:'24h traffic pulse', tone:'#54ABEE', format:value => fmt(value, 0), labels:(bundle.stats.hourly || []).map(row => row.hour_offset || '')}),
  ].join('');

  $('#overview-families').innerHTML = barList(laneFamilies.slice(0, 6), {
    label: row => row.lane_family || 'unclassified',
    detail: row => (row.providers || 0) + ' providers · ' + (row.cooldown_requests || 0) + ' cooldown req · ' + (row.recovered_requests || 0) + ' recovered',
    value: row => row.requests || 0,
    format: value => fmtTok(value),
    tone: 'blue',
    empty: 'No lane family data for the current scope',
  });
  $('#overview-recent tbody').innerHTML = recentRows(recent);

  $('#providers-summary').innerHTML = [
    {title:'Healthy vs total', body:(bundle.health.summary ? bundle.health.summary.providers_healthy : providers.filter(row => row.healthy).length) + ' healthy routes across ' + providers.length + ' configured providers.'},
    {title:'Request-readiness', body:(readiness.providers_ready || 0) + ' routes are request-ready, ' + (readiness.providers_not_ready || 0) + ' still need operator attention.'},
    {title:'Quota coupling', body:providers.filter(row => (row.transport || {}).quota_group).length + ' providers advertise quota grouping; keep coupled routes visible before they surprise the fallback chain.'},
  ].map(card => `<div class="catalog-card"><strong>${esc(card.title)}</strong><p>${esc(card.body)}</p></div>`).join('');
  $('#providers-chip').textContent = providers.length + ' providers';
  $('#providers-table tbody').innerHTML = providers.length ? providers.map(row => providerRow(row, providerMetrics)).join('') : tableEmpty(9, 'No provider inventory is available');

  const topCost = bundle.stats.client_highlights ? bundle.stats.client_highlights.top_cost : null;
  const slowest = bundle.stats.client_highlights ? bundle.stats.client_highlights.slowest_client : null;
  const failureHeavy = bundle.stats.client_highlights ? bundle.stats.client_highlights.highest_failure_rate : null;
  $('#clients-highlights').innerHTML = [
    {title:'Highest spend', body:topCost ? (topCost.client_tag || topCost.client_profile || 'generic') + ' at ' + fmtUsd(topCost.cost_usd || 0) + ' total.' : 'No cost-bearing client yet.'},
    {title:'Slowest client', body:slowest ? (slowest.client_tag || slowest.client_profile || 'generic') + ' averages ' + fmtMs(slowest.avg_latency_ms || 0) + '.' : 'No latency signal yet.'},
    {title:'Failure-heavy client', body:failureHeavy ? (failureHeavy.client_tag || failureHeavy.client_profile || 'generic') + ' is failing ' + fmtPct(100 - (failureHeavy.success_pct || 0)) + ' of requests.' : 'No client failures yet.'},
  ].map(card => `<div class="catalog-card"><strong>${esc(card.title)}</strong><p>${esc(card.body)}</p></div>`).join('');
  $('#clients-table tbody').innerHTML = clientTotals.length ? clientTotals.map(row => `
    <tr>
      <td><strong>${esc(row.client_tag || row.client_profile || 'generic')}</strong></td>
      <td>${esc(row.client_profile || 'generic')}</td>
      <td class="mono">${fmtTok(row.requests || 0)}</td>
      <td>${pill(fmtPct(row.success_pct || 0), Number(row.failures || 0) > 0 ? 'degraded' : 'ready')}</td>
      <td class="mono">${fmtTok(row.total_tokens || 0)}</td>
      <td class="mono">${fmtUsd(row.cost_usd || 0)}</td>
      <td class="mono">${fmtUsd(row.cost_per_request_usd || 0)}</td>
      <td class="mono">${fmtMs(row.avg_latency_ms || 0)}</td>
      <td class="tiny">${esc(row.providers || '—')}</td>
    </tr>
  `).join('') : tableEmpty(9, 'No client traffic for the current scope');

  $('#routes-selection').innerHTML = barList(selectionPaths.slice(0, 6), {
    label: row => row.selection_path || 'unclassified',
    detail: row => (row.lane_family || 'no family') + ' · ' + (row.runtime_window_state || 'clear'),
    value: row => row.requests || 0,
    format: value => fmtTok(value),
    tone: 'lime',
    empty: 'No selection-path data for the current scope',
  });
  $('#routes-pressure').innerHTML = barList((laneFamilies || []).slice(0, 6), {
    label: row => row.lane_family || 'unclassified',
    detail: row => (row.cooldown_requests || 0) + ' cooldown req · ' + (row.degraded_requests || 0) + ' degraded req · ' + (row.recovered_requests || 0) + ' recovered',
    value: row => (row.cooldown_requests || 0) + (row.degraded_requests || 0) + (row.recovered_requests || 0),
    format: value => fmtTok(value),
    tone: 'orange',
    empty: 'No pressure data for the current scope',
  });
  $('#routes-table tbody').innerHTML = routing.length ? routing.map(row => `
    <tr>
      <td>${pill(row.layer || 'n/a', 'subtle')}</td>
      <td class="mono">${esc(row.rule_name || '—')}</td>
      <td>${esc(row.provider || '—')}</td>
      <td>${esc(row.lane_family || '—')}</td>
      <td>${esc(row.selection_path || '—')}</td>
      <td class="mono">${fmtTok(row.requests || 0)}</td>
      <td class="mono">${fmtUsd(row.cost_usd || 0)}</td>
      <td class="mono">${fmtMs(row.avg_latency_ms || 0)}</td>
    </tr>
  `).join('') : tableEmpty(8, 'No routing rows for the current scope');

  $('#analytics-daily').innerHTML = trendChart((bundle.stats.daily || []).map(row => row.requests || 0), {
    title:'Requests by day',
    subtitle:'30 day traffic volume',
    tone:'#54ABEE',
    format:value => fmt(value, 0),
    labels:(bundle.stats.daily || []).map(row => row.day || ''),
  }) + trendChart((bundle.stats.daily || []).map(row => row.cost_usd || 0), {
    title:'Cost by day',
    subtitle:'30 day spend cadence',
    tone:'#FFAA19',
    format:fmtUsd,
    labels:(bundle.stats.daily || []).map(row => row.day || ''),
  });
  $('#analytics-hourly').innerHTML = trendChart((bundle.stats.hourly || []).map(row => (row.tokens || 0)), {
    title:'Tokens by hour',
    subtitle:'24h token pulse',
    tone:'#C4D900',
    format:fmtTok,
    labels:(bundle.stats.hourly || []).map(row => row.hour_offset || ''),
  });
  $('#analytics-modalities tbody').innerHTML = modalityRows.length ? modalityRows.map(row => `
    <tr>
      <td>${pill(row.modality || 'chat', 'subtle')}</td>
      <td>${esc(row.provider || '—')}</td>
      <td>${pill(row.layer || '—', 'subtle')}</td>
      <td class="mono">${fmtTok(row.requests || 0)}</td>
      <td class="mono">${fmtUsd(row.cost_usd || 0)}</td>
      <td class="mono">${fmtMs(row.avg_latency_ms || 0)}</td>
    </tr>
  `).join('') : tableEmpty(6, 'No modality rows for the current scope');
  $('#analytics-operators tbody').innerHTML = operatorRows.length ? operatorRows.map(row => `
    <tr>
      <td>${pill(row.event_type || 'update', 'subtle')}</td>
      <td>${esc(row.action || 'update-check')}</td>
      <td>${esc(row.status || '—')}</td>
      <td>${esc(row.target_version || row.update_type || '—')}</td>
      <td>${row.eligible ? pill('eligible', 'ready') : pill('blocked', 'degraded')}</td>
      <td class="mono">${fmtTok(row.events || 0)}</td>
    </tr>
  `).join('') : tableEmpty(6, 'No operator actions have been recorded');

  $('#catalog-summary').innerHTML = [
    {title:'Tracked providers', body:String(bundle.catalog.tracked_providers || 0) + ' of ' + String(bundle.catalog.total_providers || providers.length) + ' configured routes are in the curated catalog.'},
    {title:'Source refresh due', body:String(sourceCatalog.due_sources || 0) + ' sources are due for refresh and ' + String(sourceCatalog.error_sources || 0) + ' currently have refresh errors.'},
    {title:'Alert count', body:String(catalogAlerts.length) + ' catalog or source alerts are currently active.'},
  ].map(card => `<div class="catalog-card"><strong>${esc(card.title)}</strong><p>${esc(card.body)}</p></div>`).join('');
  $('#catalog-alerts').innerHTML = catalogAlerts.length ? catalogAlerts.slice(0, 5).map(alert => alertCard({
    level: alert.severity || 'notice',
    headline: alert.provider ? alert.provider + ': ' + (alert.code || 'catalog alert') : (alert.code || 'source alert'),
    detail: alert.message || alert.headline || 'Catalog drift alert',
    suggestion: alert.recommended_model ? 'Check ' + alert.recommended_model + ' and refresh evidence.' : 'Review the relevant source and refresh the catalog trail.',
  })).join('') : empty('No provider-catalog alerts right now');
  const sourceItems = sourceCatalog.items || [];
  $('#catalog-guidance').innerHTML = barList(sourceItems.slice(0, 6), {
    label: row => row.provider_id || row.provider || 'source',
    detail: row => (row.status || 'unknown') + ' · models ' + (row.models_count || 0) + ' · pricing ' + (row.pricing_count || 0),
    value: row => (row.models_count || 0) + (row.pricing_count || 0),
    format: value => fmt(value, 0),
    tone: 'green',
    empty: 'No source-catalog items available',
  });
  $('#catalog-table tbody').innerHTML = catalogItems.length ? catalogItems.map(row => `
    <tr>
      <td><strong>${esc(row.provider || '—')}</strong></td>
      <td>${pill(row.status || 'tracked', row.status === 'tracked' ? 'ready' : 'degraded')}</td>
      <td class="mono">${esc(row.configured_model || '—')}</td>
      <td class="mono">${esc(row.recommended_model || '—')}</td>
      <td>${esc(row.offer_track || '—')}</td>
      <td>${esc(row.volatility || '—')}</td>
      <td class="mono">${esc(row.last_reviewed || '—')}</td>
      <td class="tiny">${esc(row.notes || ((row.model_matches_recommendation === false) ? 'Configured model differs from the curated recommendation.' : 'Catalog guidance is aligned.')).slice(0, 180)}</td>
    </tr>
  `).join('') : tableEmpty(8, 'No provider catalog items are available');

  $('#integration-alerts').innerHTML = [
    integrationAlert('Model not found', 'Usually means the client entered through the wrong model id or the alias mapping still points at a raw provider instead of a Gate intent surface.'),
    integrationAlert('Provider unhealthy', 'Check Providers first, then Routes. Cooldown and quota-domain coupling should be visible before you chase client config.'),
    integrationAlert('Unexpected premium spend', 'If Sonnet or Opus spend spikes, confirm that the client is using coding-auto or eco where appropriate and that explicit model ids are not bypassing your cheapest-capable posture.'),
  ].join('');
}

async function load() {
  try {
    const params = currentFilters();
    persistState(params);
    const query = params.toString();
    const suffix = query ? '?' + query : '';
    const [health, stats, traces, recent, update, inventory, operators, catalog] = await Promise.all([
      fetch('/health').then(r => r.json()),
      fetch('/api/stats' + suffix).then(r => r.json()),
      fetch('/api/traces' + suffix + (suffix ? '&' : '?') + 'limit=20').then(r => r.json()),
      fetch('/api/recent' + suffix + (suffix ? '&' : '?') + 'limit=20').then(r => r.json()),
      fetch('/api/update').then(r => r.json()).catch(() => ({enabled:false,status:'unavailable'})),
      fetch('/api/providers').then(r => r.json()),
      fetch('/api/operator-events?limit=20').then(r => r.json()).catch(() => ({events: []})),
      fetch('/api/provider-catalog').then(r => r.json()).catch(() => ({items:[],alerts:[],source_catalog:{items:[],alerts:[]},source_alerts:[]})),
    ]);
    render({health, stats, traces, recent, update, inventory, operators, catalog});
  } catch (error) {
    console.error(error);
    $('#hero-status').textContent = 'Dashboard data failed to load';
    $('#overview-alerts').innerHTML = alertCard({
      level: 'critical',
      headline: 'Dashboard fetch failed',
      detail: 'The built-in dashboard could not load one or more API surfaces. Check the browser console and the local Gate logs.',
      suggestion: 'Verify /health, /api/stats, and /api/providers first.',
    });
  }
}

$$('.nav button').forEach(button => {
  button.addEventListener('click', () => setView(button.dataset.view || 'overview'));
});
$$('[data-target-view]').forEach(button => {
  button.addEventListener('click', () => setView(button.dataset.targetView || 'overview'));
});
$('#refresh-btn').addEventListener('click', load);
$('#apply-btn').addEventListener('click', applyFilters);
$('#clear-btn').addEventListener('click', clearFilters);
syncStateFromUrl();
load();
setInterval(load, 30000);
</script>
</body>
</html>
'''
