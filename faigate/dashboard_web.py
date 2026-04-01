"""Built-in operator dashboard HTML for fusionAIze Gate."""

import re
from pathlib import Path

from . import __version__

# ruff: noqa: E501

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "brand"


def _read_vendor_asset(name: str) -> str:
    """Return one vendored dashboard asset as text."""

    try:
        return (_VENDOR_DIR / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_brand_asset(name: str) -> str:
    """Return one brand asset as text."""

    try:
        return (_ASSET_DIR / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def _inline_svg(name: str) -> str:
    """Return one SVG asset sanitized for inline HTML embedding."""

    svg = _read_brand_asset(name)
    if not svg:
        return ""
    svg = svg.replace('<?xml version="1.0" encoding="UTF-8"?>', "").strip()
    fill_rules = {
        cls: fill
        for cls, fill in re.findall(
            r"\.(st\d+)\s*\{[^{}]*fill:\s*([^;]+);[^{}]*\}",
            svg,
            flags=re.DOTALL,
        )
    }
    for cls, fill in fill_rules.items():
        svg = re.sub(
            rf'\sclass="{re.escape(cls)}"',
            f' fill="{fill.strip()}"',
            svg,
        )
    svg = re.sub(r"<defs>.*?</defs>", "", svg, flags=re.DOTALL).strip()
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.DOTALL).strip()
    return svg


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>fusionAIze Gate</title>
<style>
/*__UPLOT_CSS__*/
@font-face{
  font-family:"Gate Display";
  src:url("/dashboard/assets/fonts/Montserrat/Montserrat-VariableFont_wght.ttf") format("truetype");
  font-weight:100 900;
  font-style:normal;
  font-display:swap;
}
@font-face{
  font-family:"Gate Body";
  src:url("/dashboard/assets/fonts/Open-Sans/OpenSans-VariableFont_wdth,wght.ttf") format("truetype");
  font-weight:300 800;
  font-style:normal;
  font-display:swap;
}
@font-face{
  font-family:"Gate Body";
  src:url("/dashboard/assets/fonts/Open-Sans/OpenSans-Italic-VariableFont_wdth,wght.ttf") format("truetype");
  font-weight:300 800;
  font-style:italic;
  font-display:swap;
}
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
  --shadow:0 20px 56px rgba(2,8,19,.28);
  --radius-xl:28px;
  --radius-lg:20px;
  --radius-md:14px;
  --radius-sm:10px;
  --mono:"SFMono-Regular","IBM Plex Mono","Menlo","Consolas",monospace;
  --body:"Gate Body","Open Sans","Segoe UI","Helvetica Neue",sans-serif;
  --display:"Gate Display","Montserrat","Avenir Next","Segoe UI",sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  min-height:100vh;
  color:var(--text);
  font-family:var(--body);
  background:
    radial-gradient(circle at 15% 20%, rgba(84,171,238,.07), transparent 30%),
    radial-gradient(circle at 82% 16%, rgba(196,217,0,.03), transparent 18%),
    radial-gradient(circle at 70% 85%, rgba(255,170,25,.025), transparent 22%),
    linear-gradient(180deg, #09111f 0%, #08111f 44%, #07101b 100%);
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
  opacity:.07;
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
  border:1px solid rgba(84,171,238,.09);
  border-radius:var(--radius-xl);
  background:
    linear-gradient(180deg, rgba(15,27,50,.95), rgba(10,18,33,.94)),
    radial-gradient(circle at top left, rgba(84,171,238,.055), transparent 40%);
  box-shadow:0 16px 42px rgba(2,8,19,.24);
  overflow:hidden;
}
.rail::after{
  content:"";
  position:absolute;
  inset:auto 16px 16px 16px;
  height:1px;
  background:linear-gradient(90deg, transparent, rgba(84,171,238,.2), transparent);
}
.brand{
  display:grid;
  gap:11px;
  margin-bottom:22px;
}
.brand-lockup{
  display:flex;
  flex-direction:column;
  align-items:flex-start;
  gap:10px;
}
.brand-wordmark{
  display:flex;
  align-items:center;
  width:100%;
  min-height:0;
}
.brand-wordmark svg{
  display:block;
  width:242px;
  max-width:100%;
  height:auto;
}
.brand-product{
  display:flex;
  align-items:baseline;
  gap:9px;
}
.brand-gate{
  color:#f4f8ff;
  font:650 1.02rem/1 var(--display);
  letter-spacing:.1em;
  text-transform:uppercase;
}
.brand-version{
  color:var(--muted-soft);
  font:500 .68rem/1 var(--body);
  letter-spacing:.02em;
}
.rail-meta{
  display:grid;
  gap:8px;
  margin-bottom:22px;
}
.rail-stat{
  padding:10px 13px;
  border:1px solid rgba(84,171,238,.07);
  border-radius:16px;
  background:rgba(255,255,255,.018);
}
.rail-stat .kicker{
  display:block;
  color:var(--muted-soft);
  font:600 .63rem/1 var(--mono);
  text-transform:uppercase;
  letter-spacing:.09em;
  margin-bottom:7px;
}
.rail-stat strong{
  display:block;
  font:600 .94rem/1.2 var(--display);
  letter-spacing:0;
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
  padding:12px 14px;
  border:1px solid transparent;
  border-radius:16px;
  background:transparent;
  color:var(--muted);
  text-align:left;
}
.nav button .num{
  color:rgba(225,233,243,.45);
  font:600 .72rem/1 var(--mono);
}
.nav button .label{
  font:600 .9rem/1.1 var(--display);
  letter-spacing:0;
}
.nav button.active{
  background:linear-gradient(90deg, rgba(54,99,190,.16), rgba(84,171,238,.04));
  color:#f4f8ff;
  border-color:rgba(84,171,238,.1);
  box-shadow:inset 0 1px 0 rgba(225,233,243,.03), 0 0 0 1px rgba(84,171,238,.03);
}
.nav button.active .num{color:var(--lime)}
.rail-note{
  margin-top:20px;
  padding:12px 13px;
  border-radius:16px;
  background:linear-gradient(160deg, rgba(255,255,255,.025), rgba(255,255,255,.01));
  border:1px solid rgba(84,171,238,.06);
  color:var(--muted);
  font-size:.8rem;
  line-height:1.5;
}
.rail-note strong{
  color:#dbe6f5;
  font:600 .8rem/1.2 var(--display);
  letter-spacing:.01em;
}
.content{
  min-width:0;
  display:grid;
  gap:18px;
}
.hero{
  position:relative;
  overflow:hidden;
  padding:11px 16px 12px;
  border:1px solid rgba(84,171,238,.08);
  border-radius:18px;
  background:linear-gradient(180deg, rgba(16,28,50,.9), rgba(10,18,33,.9));
  box-shadow:0 10px 24px rgba(2,8,19,.16);
}
.hero::before{
  content:none;
  position:absolute;
  inset:0;
  background:linear-gradient(90deg, rgba(84,171,238,.02), transparent 24%, transparent 76%, rgba(196,217,0,.015));
  pointer-events:none;
}
.hero-top{
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:10px 14px;
  flex-wrap:wrap;
}
.hero-top > *{
  min-width:0;
}
.hero-head{
  display:grid;
  gap:2px;
  min-width:0;
}
.eyebrow{
  display:inline-flex;
  align-items:center;
  gap:7px;
  color:var(--muted);
  font:600 .68rem/1.2 var(--body);
  letter-spacing:.01em;
  text-transform:none;
  opacity:.92;
}
.pulse{
  width:6px;
  height:6px;
  border-radius:50%;
  background:var(--lime);
  box-shadow:0 0 0 3px rgba(196,217,0,.08);
}
.hero h2{
  margin:0;
  max-width:none;
  display:flex;
  align-items:baseline;
  gap:.28rem;
  flex-wrap:nowrap;
  white-space:nowrap;
  font:600 clamp(1rem, 1.18vw, 1.18rem)/1.04 var(--display);
  text-transform:none;
  letter-spacing:-.012em;
}
.hero h2 .title-line{
  display:inline;
}
.hero h2 .accent{color:var(--lime)}
.hero p{
  margin:0;
  max-width:56ch;
  color:var(--muted);
  line-height:1.32;
  font-size:.79rem;
}
.hero-actions{
  display:flex;
  flex-wrap:wrap;
  gap:7px;
  align-items:center;
  justify-content:flex-end;
  min-width:0;
  max-width:100%;
}
.hero-actions .btn{
  min-height:34px;
  padding:0 11px;
  border-radius:999px;
  border:1px solid rgba(225,233,243,.06);
  background:rgba(255,255,255,.03);
  color:#e5edf7;
  box-shadow:none;
  font:600 .8rem/1 var(--body);
}
.hero-actions .btn.primary{
  background:linear-gradient(135deg, rgba(0,82,204,.54), rgba(54,99,190,.48));
  border-color:rgba(84,171,238,.14);
}
.hero-actions .btn.secondary{
  background:rgba(255,255,255,.035);
}
.hero-actions .btn.ghost{
  color:var(--muted);
}
.hero-actions .chip{
  min-height:34px;
  padding:0 11px;
  border-radius:999px;
  border:1px solid rgba(225,233,243,.07);
  background:rgba(255,255,255,.025);
  color:var(--muted);
  font:600 .76rem/1 var(--body);
  text-transform:none;
  letter-spacing:.01em;
}
.hero-actions .chip strong{
  font:700 .76rem/1 var(--mono);
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
  font:700 1rem/1.18 var(--display);
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
.priority-actions{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:14px;
}
.stats-rack{
  display:grid;
  gap:10px;
  margin-top:14px;
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
  gap:10px;
  padding:13px 14px;
  border:1px solid rgba(84,171,238,.09);
  border-radius:18px;
  background:linear-gradient(180deg, rgba(12,22,42,.9), rgba(8,16,29,.9));
  box-shadow:0 12px 28px rgba(2,8,19,.14);
}
.toolbar-head{
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:10px 14px;
  flex-wrap:wrap;
}
.toolbar-head-right{
  display:flex;
  align-items:flex-end;
  gap:8px;
  flex-wrap:wrap;
}
.toolbar-head-right .field{
  min-width:172px;
  max-width:212px;
}
.toolbar-copy strong{
  display:block;
  margin-bottom:3px;
  color:var(--muted-soft);
  font:600 .64rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:none;
}
.toolbar-copy p{
  margin:0;
  color:#eef4fd;
  font:600 .96rem/1.15 var(--display);
  letter-spacing:-.01em;
  text-transform:none;
}
.toolbar-copy p .accent{
  color:var(--lime);
}
.toolbar-copy .toolbar-subline{
  margin-top:4px;
  color:var(--muted);
  font:500 .78rem/1.38 var(--body);
  text-transform:none;
  letter-spacing:0;
}
.filters{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(146px,1fr));
  gap:10px;
}
.field{
  display:grid;
  gap:5px;
}
.field span{
  color:var(--muted-soft);
  font:600 .66rem/1 var(--display);
  letter-spacing:.02em;
  text-transform:none;
}
.field input,
.field select{
  width:100%;
  min-height:38px;
  padding:0 11px;
  color:var(--text);
  background:rgba(8,16,29,.52);
  border:1px solid rgba(84,171,238,.11);
  border-radius:11px;
  outline:none;
  box-shadow:none;
}
.field input:focus,
.field select:focus{
  border-color:rgba(84,171,238,.28);
  box-shadow:0 0 0 3px rgba(0,82,204,.11);
}
.toolbar-meta{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  flex-wrap:wrap;
}
.toolbar-meta > *{
  min-width:0;
}
.toolbar-summary{
  color:var(--muted);
  font-size:.83rem;
  line-height:1.35;
}
.toolbar-summary strong{
  color:var(--text);
}
.toolbar-actions{
  display:flex;
  gap:8px;
  flex-wrap:wrap;
}
.toolbar-chips{
  display:flex;
  gap:7px;
  flex-wrap:wrap;
}
.toolbar-head-right .chip{
  min-height:38px;
  padding:0 10px;
  border-radius:999px;
  border-color:rgba(84,171,238,.1);
  background:rgba(255,255,255,.022);
  color:var(--muted);
  font:600 .7rem/1 var(--body);
  text-transform:none;
  letter-spacing:.01em;
}
.toolbar-actions .btn{
  min-height:38px;
  padding:0 12px;
  border-radius:999px;
  font:600 .78rem/1 var(--body);
}
.chip.active-filter{
  background:rgba(0,82,204,.12);
  border-color:rgba(84,171,238,.22);
  color:#dff0ff;
}
.attention-grid{
  display:grid;
  grid-template-columns:1.05fr .95fr;
  gap:18px;
}
.attention-grid > *,
.metrics-grid > *,
.columns > *,
.cards-3 > *,
.cards-2 > *{
  min-width:0;
}
.overview-actions{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:14px;
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
  min-width:0;
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
  font:650 1rem/1.08 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
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
  font:600 .74rem/1 var(--body);
  text-transform:none;
  letter-spacing:.01em;
}
.chip strong{
  font:700 .76rem/1 var(--body);
  color:var(--text);
}
.alert-stack,.stack-list,.integration-grid,.cards-3{
  display:grid;
  gap:12px;
}
.cards-3{
  grid-template-columns:repeat(3,minmax(0,1fr));
}
.cards-2{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:12px;
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
  font:600 .94rem/1.2 var(--display);
  letter-spacing:-.01em;
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
  font:600 .92rem/1.2 var(--display);
  letter-spacing:-.01em;
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
  font:600 .94rem/1.2 var(--display);
  letter-spacing:-.01em;
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
.chart .uplot{
  width:100% !important;
  height:100% !important;
}
.chart .u-title,
.chart .u-legend{
  display:none;
}
.chart .u-wrap{
  width:100% !important;
  height:100% !important;
}
.chart .u-axis text{
  fill:#7f98be;
  font:500 11px/1 var(--mono);
}
.chart .u-grid line{
  stroke:rgba(84,171,238,.1);
}
.chart .u-series path{
  stroke-linecap:round;
  stroke-linejoin:round;
}
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
#view-providers{
  gap:14px;
}
#view-providers .metrics-grid{
  gap:12px;
}
#view-providers .metric-card{
  padding:16px 16px 14px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:
    linear-gradient(160deg, rgba(16,28,52,.9), rgba(10,17,32,.9)),
    radial-gradient(circle at top right, rgba(84,171,238,.1), transparent 34%);
  box-shadow:0 14px 30px rgba(2,8,19,.15);
}
#view-providers .metric-card .kicker{
  font:600 .64rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:none;
}
#view-providers .metric-card .value{
  margin:10px 0 7px;
  font:650 clamp(1.42rem, 1.78vw, 2.08rem)/1 var(--display);
  letter-spacing:-.015em;
}
#view-providers .metric-card .detail{
  font-size:.83rem;
  line-height:1.4;
}
#view-providers .columns{
  gap:14px;
}
#view-providers .panel{
  padding:17px 18px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:linear-gradient(180deg, rgba(13,23,43,.9), rgba(9,16,29,.88));
  box-shadow:0 14px 28px rgba(2,8,19,.14);
}
#view-providers .panel-header{
  margin-bottom:12px;
}
#view-providers .panel-header h3{
  font:650 .97rem/1.08 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
}
#view-providers .panel-header p{
  margin:6px 0 0;
  max-width:48ch;
  font-size:.83rem;
  line-height:1.42;
}
#view-providers .alert-stack,
#view-providers .cards-3{
  gap:10px;
}
#view-providers .alert-card,
#view-providers .catalog-card{
  padding:14px;
  border-radius:16px;
}
#view-providers .table-wrap{
  border-radius:16px;
}
#view-providers #providers-table{
  min-width:760px;
}
#view-providers #providers-table td{
  padding:11px 12px;
}
#view-providers #providers-table td:nth-child(1) strong,
#view-providers #providers-table td:nth-child(3) strong,
#view-providers #providers-table td:nth-child(4) strong{
  display:block;
  font:600 .9rem/1.24 var(--display);
  letter-spacing:-.01em;
}
#view-providers #providers-table td:nth-child(9){
  max-width:28ch;
}
#view-providers #providers-table .tiny{
  margin-top:4px;
  font-size:.79rem;
  line-height:1.38;
}
#view-clients{
  gap:14px;
}
#view-clients .metrics-grid{
  gap:12px;
}
#view-clients .metric-card{
  padding:16px 16px 14px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:
    linear-gradient(160deg, rgba(16,28,52,.9), rgba(10,17,32,.9)),
    radial-gradient(circle at top right, rgba(84,171,238,.1), transparent 34%);
  box-shadow:0 14px 30px rgba(2,8,19,.15);
}
#view-clients .metric-card .kicker{
  font:600 .64rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:none;
}
#view-clients .metric-card .value{
  margin:10px 0 7px;
  font:650 clamp(1.42rem, 1.78vw, 2.08rem)/1 var(--display);
  letter-spacing:-.015em;
}
#view-clients .metric-card .detail{
  font-size:.83rem;
  line-height:1.4;
}
#view-clients .cards-3{
  gap:10px;
}
#view-clients .catalog-card{
  padding:13px 14px;
  border-radius:16px;
  background:rgba(9,17,31,.42);
  border-color:rgba(84,171,238,.08);
  box-shadow:none;
}
#view-clients .catalog-card strong{
  margin-bottom:6px;
  font:600 .88rem/1.22 var(--display);
  letter-spacing:-.01em;
}
#view-clients .catalog-card p{
  font-size:.84rem;
  line-height:1.42;
}
#view-clients .panel{
  padding:17px 18px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:linear-gradient(180deg, rgba(13,23,43,.9), rgba(9,16,29,.88));
  box-shadow:0 14px 28px rgba(2,8,19,.14);
}
#view-clients .panel-header{
  margin-bottom:12px;
}
#view-clients .panel-header h3{
  font:650 .97rem/1.08 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
}
#view-clients .panel-header p{
  margin:6px 0 0;
  max-width:48ch;
  font-size:.83rem;
  line-height:1.42;
}
#view-clients .table-wrap{
  border-radius:16px;
}
#view-clients #clients-table td{
  padding:11px 12px;
}
#view-clients #clients-table td:first-child strong{
  display:block;
  font:600 .9rem/1.24 var(--display);
  letter-spacing:-.01em;
}
#view-clients #clients-table td:last-child{
  max-width:24ch;
}
#view-routes{
  gap:14px;
}
#view-routes .metrics-grid{
  gap:12px;
}
#view-routes .metric-card{
  padding:16px 16px 14px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:
    linear-gradient(160deg, rgba(16,28,52,.9), rgba(10,17,32,.9)),
    radial-gradient(circle at top right, rgba(84,171,238,.1), transparent 34%);
  box-shadow:0 14px 30px rgba(2,8,19,.15);
}
#view-routes .metric-card .kicker{
  font:600 .64rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:none;
}
#view-routes .metric-card .value{
  margin:10px 0 7px;
  font:650 clamp(1.42rem, 1.78vw, 2.08rem)/1 var(--display);
  letter-spacing:-.015em;
}
#view-routes .metric-card .detail{
  font-size:.83rem;
  line-height:1.4;
}
#view-routes .columns{
  gap:14px;
}
#view-routes .panel{
  padding:17px 18px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:linear-gradient(180deg, rgba(13,23,43,.9), rgba(9,16,29,.88));
  box-shadow:0 14px 28px rgba(2,8,19,.14);
}
#view-routes .panel-header{
  margin-bottom:12px;
}
#view-routes .panel-header h3{
  font:650 .97rem/1.08 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
}
#view-routes .panel-header p{
  margin:6px 0 0;
  max-width:48ch;
  font-size:.83rem;
  line-height:1.42;
}
#view-routes .bar-list{
  gap:10px;
}
#view-routes .bar-item{
  gap:6px;
}
#view-routes .table-wrap{
  border-radius:16px;
}
#view-routes #routes-table td{
  padding:11px 12px;
}
#view-routes #routes-table td:nth-child(2),
#view-routes #routes-table td:nth-child(3),
#view-routes #routes-table td:nth-child(5){
  font-size:.89rem;
  line-height:1.34;
}
#view-routes #routes-table td:nth-child(2){
  font-family:var(--display);
  font-weight:600;
  letter-spacing:-.01em;
}
#view-catalog{
  gap:14px;
}
#view-catalog .metrics-grid{
  gap:12px;
}
#view-catalog .metric-card{
  padding:16px 16px 14px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:
    linear-gradient(160deg, rgba(16,28,52,.9), rgba(10,17,32,.9)),
    radial-gradient(circle at top right, rgba(84,171,238,.1), transparent 34%);
  box-shadow:0 14px 30px rgba(2,8,19,.15);
}
#view-catalog .metric-card .kicker{
  font:600 .64rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:none;
}
#view-catalog .metric-card .value{
  margin:10px 0 7px;
  font:650 clamp(1.42rem, 1.78vw, 2.08rem)/1 var(--display);
  letter-spacing:-.015em;
}
#view-catalog .metric-card .detail{
  font-size:.83rem;
  line-height:1.4;
}
#view-catalog .cards-3,
#view-catalog .columns,
#view-catalog .alert-stack,
#view-catalog .bar-list{
  gap:10px;
}
#view-catalog .catalog-card,
#view-catalog .alert-card{
  padding:14px;
  border-radius:16px;
}
#view-catalog .catalog-card{
  background:rgba(9,17,31,.42);
  border-color:rgba(84,171,238,.08);
  box-shadow:none;
}
#view-catalog .catalog-card strong{
  margin-bottom:6px;
  font:600 .88rem/1.22 var(--display);
  letter-spacing:-.01em;
}
#view-catalog .catalog-card p,
#view-catalog .alert-body{
  font-size:.84rem;
  line-height:1.42;
}
#view-catalog .panel{
  padding:17px 18px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:linear-gradient(180deg, rgba(13,23,43,.9), rgba(9,16,29,.88));
  box-shadow:0 14px 28px rgba(2,8,19,.14);
}
#view-catalog .panel-header{
  margin-bottom:12px;
}
#view-catalog .panel-header h3{
  font:650 .97rem/1.08 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
}
#view-catalog .panel-header p{
  margin:6px 0 0;
  max-width:48ch;
  font-size:.83rem;
  line-height:1.42;
}
#view-catalog .table-wrap{
  border-radius:16px;
}
#view-catalog #catalog-table td{
  padding:11px 12px;
}
#view-catalog #catalog-table td:first-child strong{
  display:block;
  font:600 .9rem/1.24 var(--display);
  letter-spacing:-.01em;
}
#view-catalog #catalog-table td:last-child{
  max-width:30ch;
}
#view-catalog #catalog-table .tiny{
  font-size:.8rem;
  line-height:1.4;
}
#view-integrations{
  gap:14px;
}
#view-integrations .metrics-grid,
#view-integrations .integration-grid,
#view-integrations .cards-3,
#view-integrations .alert-stack{
  gap:10px;
}
#view-integrations .metric-card{
  padding:16px 16px 14px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:
    linear-gradient(160deg, rgba(16,28,52,.9), rgba(10,17,32,.9)),
    radial-gradient(circle at top right, rgba(84,171,238,.1), transparent 34%);
  box-shadow:0 14px 30px rgba(2,8,19,.15);
}
#view-integrations .metric-card .kicker{
  font:600 .64rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:none;
}
#view-integrations .metric-card .value{
  margin:10px 0 7px;
  font:650 clamp(1.42rem, 1.78vw, 2.08rem)/1 var(--display);
  letter-spacing:-.015em;
}
#view-integrations .metric-card .detail{
  font-size:.83rem;
  line-height:1.4;
}
#view-integrations .integration-card{
  padding:16px;
  border-radius:18px;
  border-color:rgba(84,171,238,.09);
  background:linear-gradient(180deg, rgba(13,23,43,.88), rgba(9,16,29,.84));
  box-shadow:0 12px 26px rgba(2,8,19,.12);
}
#view-integrations .integration-card strong{
  margin-bottom:6px;
  font:600 .94rem/1.2 var(--display);
  letter-spacing:-.01em;
}
#view-integrations .integration-card p{
  font-size:.84rem;
  line-height:1.42;
}
#view-integrations .columns{
  gap:14px;
}
#view-integrations .panel{
  padding:17px 18px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:linear-gradient(180deg, rgba(13,23,43,.9), rgba(9,16,29,.88));
  box-shadow:0 14px 28px rgba(2,8,19,.14);
}
#view-integrations .panel-header{
  margin-bottom:12px;
}
#view-integrations .panel-header h3{
  font:650 .97rem/1.08 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
}
#view-integrations .panel-header p{
  margin:6px 0 0;
  max-width:46ch;
  font-size:.83rem;
  line-height:1.42;
}
#view-integrations .focus-card{
  padding:13px 14px;
  border-radius:16px;
}
#view-integrations .focus-card strong{
  margin-bottom:6px;
  font:600 .88rem/1.22 var(--display);
  letter-spacing:-.01em;
}
#view-integrations .focus-card p{
  font-size:.84rem;
  line-height:1.42;
}
#view-integrations .code{
  margin-top:10px;
  padding:12px 14px;
  border-radius:14px;
  border-color:rgba(84,171,238,.14);
  background:#07101c;
  font-size:.8rem;
  line-height:1.55;
  white-space:pre;
}
#view-integrations .foot-note{
  margin-top:10px;
  font-size:.8rem;
  line-height:1.46;
}
#view-analytics{
  gap:14px;
}
#view-analytics .metrics-grid,
#view-analytics .columns{
  gap:14px;
}
#view-analytics .metric-card{
  padding:16px 16px 14px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:
    linear-gradient(160deg, rgba(16,28,52,.9), rgba(10,17,32,.9)),
    radial-gradient(circle at top right, rgba(84,171,238,.1), transparent 34%);
  box-shadow:0 14px 30px rgba(2,8,19,.15);
}
#view-analytics .metric-card .kicker{
  font:600 .64rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:none;
}
#view-analytics .metric-card .value{
  margin:10px 0 7px;
  font:650 clamp(1.42rem, 1.78vw, 2.08rem)/1 var(--display);
  letter-spacing:-.015em;
}
#view-analytics .metric-card .detail{
  font-size:.83rem;
  line-height:1.4;
}
#view-analytics .panel{
  padding:17px 18px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:linear-gradient(180deg, rgba(13,23,43,.9), rgba(9,16,29,.88));
  box-shadow:0 14px 28px rgba(2,8,19,.14);
}
#view-analytics .panel-header{
  margin-bottom:12px;
}
#view-analytics .panel-header h3{
  font:650 .97rem/1.08 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
}
#view-analytics .panel-header p{
  margin:6px 0 0;
  max-width:48ch;
  font-size:.83rem;
  line-height:1.42;
}
#view-analytics .trend-card{
  padding:15px 16px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:rgba(9,17,31,.48);
}
#view-analytics .trend-top{
  margin-bottom:10px;
}
#view-analytics .trend-top strong{
  font-size:.92rem;
}
#view-analytics .trend-top span{
  font-size:.8rem;
}
#view-analytics .chart{
  height:164px;
  border-radius:14px;
  border-color:rgba(84,171,238,.07);
  background:
    linear-gradient(180deg, rgba(255,255,255,.014), rgba(255,255,255,0)),
    linear-gradient(rgba(84,171,238,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(84,171,238,.03) 1px, transparent 1px);
  background-size:auto, auto 34px, 56px auto;
}
#view-analytics .chart-empty{
  font-size:.84rem;
}
#view-analytics .table-wrap{
  border-radius:16px;
}
#view-analytics #analytics-modalities,
#view-analytics #analytics-operators{
  min-width:520px;
}
#view-analytics #analytics-modalities td,
#view-analytics #analytics-operators td{
  padding:11px 12px;
}
#view-overview{
  gap:14px;
}
#view-overview .metrics-grid{
  gap:12px;
}
#view-overview .metric-card{
  padding:16px 16px 14px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:
    linear-gradient(160deg, rgba(16,28,52,.9), rgba(10,17,32,.9)),
    radial-gradient(circle at top right, rgba(84,171,238,.11), transparent 34%);
  box-shadow:0 14px 30px rgba(2,8,19,.16);
}
#view-overview .metric-card .kicker{
  font:600 .64rem/1 var(--display);
  letter-spacing:.04em;
  text-transform:none;
}
#view-overview .metric-card .value{
  margin:10px 0 7px;
  font:650 clamp(1.42rem, 1.78vw, 2.08rem)/1 var(--display);
  letter-spacing:-.015em;
}
#view-overview .metric-card .detail{
  font-size:.83rem;
  line-height:1.4;
}
#view-overview .attention-grid,
#view-overview .columns{
  gap:14px;
}
#view-overview > .columns:first-of-type{
  grid-template-columns:repeat(2,minmax(0,1fr));
}
#view-overview .panel{
  padding:17px 18px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
  background:linear-gradient(180deg, rgba(13,23,43,.9), rgba(9,16,29,.88));
  box-shadow:0 14px 28px rgba(2,8,19,.14);
}
#view-overview .panel-header{
  margin-bottom:12px;
}
#view-overview .panel-header h3{
  font:650 .97rem/1.08 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
}
#view-overview .panel-header p{
  margin:6px 0 0;
  max-width:48ch;
  font-size:.83rem;
  line-height:1.42;
}
#view-overview .alert-stack,
#view-overview .priority-list,
#view-overview .stats-rack,
#view-overview .bar-list,
#view-overview .cards-2{
  gap:10px;
}
#view-overview .overview-actions,
#view-overview .priority-actions{
  gap:8px;
  margin-top:12px;
}
#view-overview .priority-title{
  margin-bottom:10px;
}
#view-overview .priority-title strong{
  font-size:.97rem;
  letter-spacing:-.01em;
}
#view-overview .priority-title .state{
  padding:4px 7px;
  font-size:.64rem;
  letter-spacing:.08em;
}
#view-overview .priority-path{
  font:650 .98rem/1.12 var(--display);
  text-transform:none;
  letter-spacing:-.01em;
}
#view-overview .priority-why{
  margin-top:8px;
  font-size:.86rem;
  line-height:1.45;
}
#view-overview .priority-item{
  font-size:.86rem;
  line-height:1.42;
}
#view-overview .rack-row{
  padding:10px 11px;
  border-radius:13px;
}
#view-overview .rack-row strong{
  font:650 .92rem/1 var(--display);
}
#view-overview .trend-card{
  padding:15px 16px;
  border-radius:18px;
  border-color:rgba(84,171,238,.1);
}
#view-overview .trend-top{
  margin-bottom:10px;
}
#view-overview .trend-top strong{
  font-size:.92rem;
}
#view-overview .trend-top span{
  font-size:.8rem;
}
#view-overview .table-wrap{
  border-radius:16px;
}
#view-overview .recent-log{
  display:grid;
  gap:10px;
}
#view-overview .recent-log .empty{
  padding:18px 16px;
}
#view-overview .recent-item{
  display:grid;
  grid-template-columns:minmax(0, 1fr) auto;
  gap:10px 14px;
  align-items:start;
  padding:13px 14px;
  border-radius:14px;
  border:1px solid rgba(84,171,238,.08);
  background:rgba(7,16,29,.34);
}
#view-overview .recent-main{
  min-width:0;
  display:grid;
  gap:5px;
}
#view-overview .recent-title{
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:8px;
}
#view-overview .recent-title strong{
  font:600 .9rem/1.2 var(--display);
  letter-spacing:-.01em;
}
#view-overview .recent-meta{
  color:var(--muted);
  font-size:.82rem;
  line-height:1.4;
  word-break:break-word;
}
#view-overview .recent-side{
  display:grid;
  gap:5px;
  justify-items:end;
  text-align:right;
}
#view-overview .recent-side .mono{
  font-size:.8rem;
}
#view-overview .recent-side .tiny{
  font-size:.77rem;
}
#view-overview .focus-card,
#view-overview .alert-card{
  padding:14px;
  border-radius:16px;
}
#view-overview .focus-card strong{
  margin-bottom:6px;
  font-size:.9rem;
}
#view-overview .focus-card p,
#view-overview .alert-body{
  font-size:.87rem;
  line-height:1.46;
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
  min-width:0;
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
  gap:6px;
  justify-items:start;
  padding:22px 18px;
  color:var(--muted-soft);
  font-size:.9rem;
  border-radius:16px;
  background:rgba(9,17,31,.4);
  border:1px dashed rgba(84,171,238,.16);
}
.empty strong{
  color:var(--text);
  font-size:.95rem;
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
  .columns,.cards-3,.cards-2,.attention-grid{grid-template-columns:1fr}
}
@media (max-width: 1480px){
  #view-analytics .metrics-grid{
    grid-template-columns:repeat(3,minmax(0,1fr));
  }
  #view-analytics > .columns:last-of-type{
    grid-template-columns:1fr;
  }
}
@media (max-width: 1100px){
  .hero p{
    max-width:100%;
  }
}
@media (max-width: 720px){
  .shell{padding:14px}
  .hero{padding:14px}
  .toolbar,.panel{padding:16px}
  .metrics-grid{grid-template-columns:1fr}
  .nav{grid-template-columns:1fr 1fr}
  .hero-actions{justify-content:flex-start}
}
</style>
</head>
<body>
<div class="shell">
  <aside class="rail">
    <div class="brand">
      <div class="brand-lockup">
        <div class="brand-wordmark" aria-label="fusionAIze">__BRAND_LOGO__</div>
        <div class="brand-product">
          <span class="brand-gate">GATE</span>
          <span class="brand-version">v__FAIGATE_VERSION__</span>
        </div>
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
      Trust the lane, inspect the route, and spend premium budget only where needed.
    </div>
  </aside>

  <main class="content">
    <section class="hero">
      <div class="hero-top">
        <div class="hero-head">
          <div class="eyebrow"><span class="pulse" id="status-pulse"></span><span id="hero-status">Gateway health is loading</span></div>
          <h2 id="page-title"><span class="title-line">Operator</span><span class="title-line accent">Cockpit</span></h2>
          <p id="page-subtitle">Health, spend, and route guidance.</p>
        </div>
        <div class="hero-actions">
          <button class="btn primary" type="button" id="refresh-btn">Refresh now</button>
          <button class="btn secondary" type="button" id="apply-btn">Apply filters</button>
          <button class="btn ghost" type="button" id="clear-btn">Clear filters</button>
          <span class="chip">Updated <strong id="ago">—</strong></span>
        </div>
      </div>
    </section>

    <section class="toolbar">
      <div class="toolbar-head">
        <div class="toolbar-copy">
          <strong>Command bar</strong>
          <p>Operator scope</p>
          <div class="toolbar-subline">Filter by provider, client, layer, or status.</div>
        </div>
        <div class="toolbar-head-right">
          <label class="field">
            <span>Saved view</span>
            <select id="saved-view">
              <option value="">Saved view</option>
              <option value="all-traffic">All traffic</option>
              <option value="claude-coding">Claude coding</option>
              <option value="premium-pressure">Premium pressure</option>
              <option value="catalog-review">Catalog review</option>
              <option value="fallback-inspection">Fallback inspection</option>
            </select>
          </label>
          <span class="chip" id="scope-chip">All traffic</span>
        </div>
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
        <div class="toolbar-chips" id="active-filter-chips"></div>
        <div class="toolbar-actions">
          <button class="btn secondary" type="button" data-target-view="providers">Go to providers</button>
          <button class="btn secondary" type="button" data-target-view="integrations">Open integrations</button>
        </div>
      </div>
    </section>

    <section class="view-panel active" id="view-overview">
      <div class="metrics-grid" id="overview-cards"></div>
      <div class="attention-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>What needs attention</h3>
              <p>Start with the top risk or cost signal.</p>
            </div>
            <span class="chip" id="focus-chip">Loading</span>
          </div>
          <div class="alert-stack" id="overview-alerts"></div>
          <div class="overview-actions">
            <button class="btn secondary" type="button" data-target-view="providers">Open providers</button>
            <button class="btn secondary" type="button" data-target-view="routes">Inspect route pressure</button>
            <button class="btn secondary" type="button" data-target-view="catalog">Review catalog drift</button>
          </div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Priority next</h3>
              <p>One next move and the evidence behind it.</p>
            </div>
          </div>
          <div class="priority-title">
            <strong id="priority-ribbon">Operator focus</strong>
            <span class="state" id="priority-state">loading</span>
          </div>
          <div class="priority-path" id="priority-path">Loading priority path</div>
          <div class="priority-why" id="priority-why">Calculating next action.</div>
          <div class="priority-list" id="priority-list"></div>
          <div class="priority-actions">
            <button class="btn secondary" type="button" id="priority-action-primary" data-target-view="providers">Open providers</button>
            <button class="btn secondary" type="button" id="priority-action-secondary" data-target-view="routes">Inspect routes</button>
          </div>
          <div class="stats-rack" id="snapshot-rack"></div>
        </div>
      </div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Spend and traffic</h3>
              <p>Cost and request pulse.</p>
            </div>
          </div>
          <div id="overview-trends"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Recent request log</h3>
              <p>Recent requests with route, client, latency, and cost.</p>
            </div>
          </div>
          <div id="overview-recent" class="recent-log"></div>
        </div>
      </div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Lane families</h3>
              <p>Volume and fallback pressure by family.</p>
            </div>
          </div>
          <div class="bar-list" id="overview-families"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Operator evidence</h3>
              <p>Checks for cost posture and fallback drift.</p>
            </div>
          </div>
          <div class="cards-2" id="overview-evidence"></div>
        </div>
      </div>
    </section>

    <section class="view-panel" id="view-providers">
      <div class="metrics-grid" id="providers-kpis"></div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Provider warnings</h3>
              <p>Readiness, health, and premium risk.</p>
            </div>
          </div>
          <div class="alert-stack" id="providers-alerts"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Remediation guidance</h3>
              <p>Fix health, keys, then quota.</p>
            </div>
          </div>
          <div class="cards-3" id="providers-summary"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
              <h3>Provider fleet</h3>
              <p>Sorted by readiness, health, quota, spend, and latency.</p>
          </div>
          <span class="chip" id="providers-chip">Inventory</span>
        </div>
        <div class="table-wrap"><table id="providers-table"><thead><tr><th>Provider</th><th>Status</th><th>Lane</th><th>Route</th><th>Billing + quota</th><th>Requests</th><th>Cost</th><th>Latency</th><th>Operator note</th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <section class="view-panel" id="view-clients">
      <div class="metrics-grid" id="clients-kpis"></div>
      <div class="cards-3" id="clients-highlights"></div>
      <div class="panel">
        <div class="panel-header">
          <div>
              <h3>Client posture</h3>
              <p>Clients carrying spend, failures, or latency.</p>
          </div>
        </div>
        <div class="table-wrap"><table id="clients-table"><thead><tr><th>Client</th><th>Profile</th><th>Requests</th><th>Success</th><th>Tokens</th><th>Cost</th><th>Cost / req</th><th>Latency</th><th>Providers</th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <section class="view-panel" id="view-routes">
      <div class="metrics-grid" id="routes-kpis"></div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Selection paths</h3>
              <p>Selected path and fallback availability.</p>
            </div>
          </div>
          <div class="bar-list" id="routes-selection"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Route pressure</h3>
              <p>Cooldown, degradation, and recovery pressure.</p>
            </div>
          </div>
          <div class="bar-list" id="routes-pressure"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
              <h3>Routing breakdown</h3>
            <p>Layer, rule, provider, family, and selected path.</p>
          </div>
        </div>
        <div class="table-wrap"><table id="routes-table"><thead><tr><th>Layer</th><th>Rule</th><th>Provider</th><th>Lane family</th><th>Selection path</th><th>Requests</th><th>Cost</th><th>Latency</th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <section class="view-panel" id="view-analytics">
      <div class="metrics-grid" id="analytics-kpis"></div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>30-day cost trend</h3>
              <p>Requests and spend over 30 days.</p>
            </div>
          </div>
          <div id="analytics-daily"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>24-hour traffic pulse</h3>
              <p>Traffic for spikes, fallbacks, and cold periods.</p>
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
              <p>Request types by provider and layer.</p>
            </div>
          </div>
          <div class="table-wrap"><table id="analytics-modalities"><thead><tr><th>Modality</th><th>Provider</th><th>Layer</th><th>Requests</th><th>Cost</th><th>Latency</th></tr></thead><tbody></tbody></table></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Operator actions</h3>
              <p>Update checks and local operator events.</p>
            </div>
          </div>
          <div class="table-wrap"><table id="analytics-operators"><thead><tr><th>Event</th><th>Action</th><th>Status</th><th>Target</th><th>Eligible</th><th>Events</th></tr></thead><tbody></tbody></table></div>
        </div>
      </div>
    </section>

    <section class="view-panel" id="view-catalog">
      <div class="metrics-grid" id="catalog-kpis"></div>
      <div class="cards-3" id="catalog-summary"></div>
      <div class="columns">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Catalog alerts</h3>
              <p>Freshness, evidence, and model mismatch risk.</p>
            </div>
          </div>
          <div class="alert-stack" id="catalog-alerts"></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Refresh guidance</h3>
              <p>What to review now and what is still safe to trust.</p>
            </div>
          </div>
          <div class="bar-list" id="catalog-guidance"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3>Priority clusters</h3>
            <p>Catalog health areas needing attention.</p>
          </div>
        </div>
        <div class="bar-list" id="catalog-priority-clusters"></div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3>Recommendations</h3>
            <p>Actionable guidance based on catalog health.</p>
          </div>
        </div>
        <div class="alert-stack" id="catalog-recommendations"></div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
              <h3>Tracked provider assumptions</h3>
            <p>Configured vs recommended model, freshness, volatility, and notes.</p>
          </div>
        </div>
        <div class="table-wrap"><table id="catalog-table"><thead><tr><th>Provider</th><th>Status</th><th>Configured</th><th>Recommended</th><th>Offer track</th><th>Volatility</th><th>Reviewed</th><th>Why it matters</th></tr></thead><tbody></tbody></table></div>
      </div>
    </section>

    <section class="view-panel" id="view-integrations">
      <div class="metrics-grid" id="integrations-kpis"></div>
      <div class="integration-grid">
        <div class="integration-card">
              <strong>Claude Code</strong>
          <p>Point Claude Code at the local Anthropic endpoint. Default to `coding-auto` unless you need a premium lane.</p>
          <code class="code">export ANTHROPIC_BASE_URL=http://127.0.0.1:8090
export ANTHROPIC_AUTH_TOKEN=dummy-local-token
claude --model coding-auto</code>
        </div>
        <div class="integration-card">
              <strong>OpenAI-compatible tools</strong>
          <p>Point Cursor, Continue, Cline, scripts, and shells at one local endpoint. Use Gate modes instead of raw provider ids.</p>
          <code class="code">export OPENAI_BASE_URL=http://127.0.0.1:8090/v1
export OPENAI_API_KEY=dummy-local-token
# models: auto, coding-auto, coding-fast, coding-premium, eco, premium</code>
        </div>
        <div class="integration-card">
              <strong>Agent-native clients</strong>
          <p>Keep `opencode`, `openclaw`, and automation clients on named entry modes for clear routing and pricing.</p>
          <code class="code">Recommended entry modes

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
              <h3>Quick connect posture</h3>
              <p>Connect, validate, then route through intent modes.</p>
            </div>
          </div>
          <div class="cards-3">
            <div class="focus-card">
              <strong>Local-first security</strong>
              <p>Keys, routes, and traces stay local unless you wire in remote services.</p>
            </div>
            <div class="focus-card">
              <strong>Agent-native routing</strong>
              <p>Different clients have different economics. Keep client identity visible.</p>
            </div>
            <div class="focus-card">
              <strong>Explainable by default</strong>
              <p>Lane family, selection path, route type, quota coupling, and freshness stay visible.</p>
            </div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>Troubleshooting shortcuts</h3>
              <p>Fast checks for common integration failures.</p>
            </div>
          </div>
          <div class="alert-stack" id="integration-alerts"></div>
          <p class="foot-note">If a model is unexpectedly expensive, check the client model id, then the lane, then the route type.</p>
        </div>
      </div>
    </section>
  </main>
</div>

<script>
/*__UPLOT_JS__*/
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const VIEW_IDS = ['overview','providers','clients','routes','analytics','catalog','integrations'];
const SAVED_VIEWS = {
  'all-traffic': {view: 'overview'},
  'claude-coding': {view: 'clients', client_profile: 'claude'},
  'premium-pressure': {view: 'clients', client_profile: 'premium'},
  'catalog-review': {view: 'catalog'},
  'fallback-inspection': {view: 'routes'},
};
let currentView = 'overview';
const chartRegistry = new Map();
let latestBundle = null;
let loadTimer = null;

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
    saved_view: $('#saved-view').value.trim(),
    view: currentView,
  };
  Object.entries(mapping).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params;
}

function updateHeaderForView() {
  $('#page-title').innerHTML = '<span class="title-line">Operator</span><span class="title-line accent">Cockpit</span>';
  $('#page-subtitle').textContent = 'Routing health, spend pressure, and operator guidance.';
}

function syncStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  $('#filter-provider').value = params.get('provider') || '';
  $('#filter-modality').value = params.get('modality') || '';
  $('#filter-profile').value = params.get('client_profile') || '';
  $('#filter-client').value = params.get('client_tag') || '';
  $('#filter-layer').value = params.get('layer') || '';
  $('#filter-success').value = params.get('success') || '';
  $('#saved-view').value = params.get('saved_view') || '';
  setView(params.get('view') || 'overview', false);
}

function describeFilters(params) {
  const parts = [];
  const chips = [];
  const labels = {
    provider: 'Provider',
    modality: 'Modality',
    client_profile: 'Profile',
    client_tag: 'Client',
    layer: 'Layer',
    success: 'Status',
  };
  for (const [key, value] of params.entries()) {
    if (key === 'view' || key === 'saved_view') continue;
    const label = labels[key] || key;
    parts.push(label.toLowerCase() + ' ' + value);
    chips.push('<span class="chip active-filter">' + esc(label) + ' <strong>' + esc(value) + '</strong></span>');
  }
  $('#filter-summary').innerHTML = parts.length ? '<strong>Scope:</strong> ' + esc(parts.join(' · ')) : 'No active filters';
  $('#active-filter-chips').innerHTML = chips.join('');
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
  updateHeaderForView();
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

function scheduleLoad() {
  window.clearTimeout(loadTimer);
  loadTimer = window.setTimeout(() => load(), 220);
}

function applySavedView(name) {
  const preset = SAVED_VIEWS[name];
  if (!preset) return;
  ['#filter-provider', '#filter-modality', '#filter-profile', '#filter-client', '#filter-layer', '#filter-success'].forEach(sel => { $(sel).value = ''; });
  if (preset.provider) $('#filter-provider').value = preset.provider;
  if (preset.modality) $('#filter-modality').value = preset.modality;
  if (preset.client_profile) $('#filter-profile').value = preset.client_profile;
  if (preset.client_tag) $('#filter-client').value = preset.client_tag;
  if (preset.layer) $('#filter-layer').value = preset.layer;
  if (preset.success) $('#filter-success').value = preset.success;
  setView(preset.view || 'overview', false);
  scheduleLoad();
}

function clearFilters() {
  ['#filter-provider', '#filter-modality', '#filter-profile', '#filter-client', '#filter-layer', '#filter-success'].forEach(sel => { $(sel).value = ''; });
  $('#saved-view').value = '';
  load();
}

function pill(label, kind = 'subtle') {
  return '<span class="pill ' + kind + '">' + esc(label) + '</span>';
}

function empty(label, suggestion = 'Try All traffic or clear filters.') {
  return '<div class="empty"><strong>' + esc(label) + '</strong><span>' + esc(suggestion) + '</span></div>';
}

function tableEmpty(colspan, label, suggestion = 'Clear filters or switch to All traffic.') {
  return '<tr><td colspan="' + colspan + '"><div class="empty"><strong>' + esc(label) + '</strong><span>' + esc(suggestion) + '</span></div></td></tr>';
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

function destroyPlot(id) {
  const chart = chartRegistry.get(id);
  if (chart) {
    chart.destroy();
    chartRegistry.delete(id);
  }
}

function trendCard(id, values, opts = {}) {
  const nums = values.map(v => Number(v) || 0);
  const labels = (opts.labels || []).filter(Boolean);
  const nonZero = nums.some(v => v !== 0);
  const last = nums.length ? nums[nums.length - 1] : 0;
  const peak = nums.length ? Math.max(...nums) : 0;
  const avg = nums.length ? (nums.reduce((sum, value) => sum + value, 0) / nums.length) : 0;
  return `
    <div class="trend-card">
      <div class="trend-top">
        <div>
          <strong>${esc(opts.title || 'Trend')}</strong>
          <span>${esc(opts.subtitle || '')}</span>
        </div>
        <div class="tiny mono">last ${esc(opts.format ? opts.format(last) : fmt(last, 0))} · avg ${esc(opts.format ? opts.format(avg) : fmt(avg, 0))} · peak ${esc(opts.format ? opts.format(peak) : fmt(peak, 0))}</div>
      </div>
      <div class="chart" id="${esc(id)}">${nonZero ? '' : '<div class="chart-empty">No trend data in this scope</div>'}</div>
      ${labels.length ? '<div class="tiny" style="margin-top:10px">' + esc(labels[0]) + ' → ' + esc(labels[labels.length - 1]) + '</div>' : ''}
    </div>
  `;
}

function renderTrendPlot(id, values, opts = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  destroyPlot(id);
  const nums = values.map(v => Number(v) || 0);
  if (!nums.length || nums.every(v => v === 0) || typeof uPlot === 'undefined') {
    if (!el.querySelector('.chart-empty')) {
      el.innerHTML = '<div class="chart-empty">No trend data in this scope</div>';
    }
    return;
  }
  const labels = opts.labels || [];
  const x = nums.map((_, index) => index);
  const width = Math.max(280, Math.floor(el.clientWidth || 720));
  const height = opts.height || 180;
  const stroke = opts.tone || '#54ABEE';
  const fill = opts.fill || 'rgba(84,171,238,.12)';
  const formatTick = opts.tickFormat || ((value, index) => labels[index] || '');
  el.innerHTML = '';
  const chart = new uPlot({
    width,
    height,
    padding: [10, 10, 10, 10],
    cursor: {drag: {x: false, y: false}},
    scales: {x: {time: false}, y: {auto: true}},
    axes: [
      {
        grid: {show: false},
        stroke: 'rgba(84,171,238,.16)',
        values: (_self, ticks) => ticks.map(tick => formatTick(tick, tick)),
      },
      {
        stroke: 'rgba(84,171,238,.16)',
        grid: {stroke: 'rgba(84,171,238,.08)', width: 1},
        values: (_self, ticks) => ticks.map(value => opts.format ? opts.format(value) : fmt(value, 0)),
      },
    ],
    series: [
      {},
      {
        stroke,
        width: 3,
        fill,
        points: {show: false},
      },
    ],
  }, [x, nums], el);
  chartRegistry.set(id, chart);
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
      headline: 'Release update',
      detail: bundle.update.recommended_action || 'Review the current release channel.',
      suggestion: bundle.update.latest_version ? 'Review ' + bundle.update.latest_version + ' before the next tuning pass.' : 'Review the release channel.',
    });
  }
  (bundle.catalog.alerts || []).slice(0, 2).forEach(alert => {
    alerts.push({
      level: alert.severity || 'notice',
      headline: alert.provider ? alert.provider + ': ' + (alert.code || 'catalog alert') : (alert.code || 'catalog alert'),
      detail: alert.message || 'Catalog drift detected.',
      suggestion: alert.recommended_model ? 'Check recommended model ' + alert.recommended_model + '.' : 'Refresh the catalog or review the source trail.',
    });
  });
  const unhealthy = (bundle.inventory.providers || []).filter(row => row.healthy === false);
  if (unhealthy.length) {
    const top = unhealthy[0];
    alerts.unshift({
      level: 'warning',
      headline: top.name + ' is currently unhealthy',
      detail: top.last_error || 'The route is failing health or readiness checks.',
      suggestion: ((top.request_readiness || {}).operator_hint) || 'Inspect provider detail and recent route traces.',
    });
  }
  if (!alerts.length) {
    alerts.push({
      level: 'notice',
      headline: 'No active alert',
      detail: 'No active risk in this scope.',
      suggestion: 'Check the highest-cost client and confirm its entry mode.',
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
  let why = 'Tighten entry intents so cheap-capable traffic does not land on premium routes.';
  if ((readiness.providers_not_ready || 0) > 0) {
    state = 'guard';
    priorityPath = 'Providers → request-readiness';
    why = 'At least one route is not request-ready. Check health, cooldown, and quota coupling.';
  } else if (alerts[0] && (alerts[0].level === 'critical' || alerts[0].level === 'warning')) {
    state = alerts[0].level;
    priorityPath = 'Review top alert';
    why = alerts[0].detail || why;
  } else if (topCost && Number(topCost.cost_usd || 0) > 0.5) {
    state = 'spend';
    priorityPath = 'Clients → highest-cost profile';
    why = (topCost.client_tag || topCost.client_profile || 'The top-cost client') + ' is carrying real spend. Confirm it belongs on a premium entry mode.';
  } else if (fallbackRequests > 0) {
    state = 'fallback';
    priorityPath = 'Routes → selection paths';
    why = 'Fallback traffic is present. Confirm whether the share is expected or a default-path issue.';
  }
  const list = [
    'Use client entry modes, not provider strings, for cheapest-capable routing.',
    'If a route is premium, make the reason visible in route and client views.',
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

function recentLogItems(rows, limit = 8) {
  if (!rows.length) {
    return '<div class="empty"><strong>No requests for the current scope</strong><span>Clear filters or switch to All traffic.</span></div>';
  }
  return rows.slice(0, limit).map(row => `
    <div class="recent-item">
      <div class="recent-main">
        <div class="recent-title">
          <strong>${esc(row.provider || '—')}</strong>
          ${row.success ? pill('success', 'ready') : pill('failure', 'fail')}
        </div>
        <div class="recent-meta">${esc(row.canonical_model || row.rule_name || '—')} · ${esc(row.client_tag || row.client_profile || 'generic')}</div>
      </div>
      <div class="recent-side">
        <div class="mono">${esc(ago(row.timestamp))}</div>
        <div class="tiny">${fmtMs(row.latency_ms || 0)} · ${fmtUsd(row.cost_usd || 0)}</div>
      </div>
    </div>
  `).join('');
}

function render(bundle) {
  latestBundle = bundle;
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
  const costTruth = bundle.catalog.cost_truth || {};
  const priorityClusters = bundle.catalog.priority_clusters || [];
  const recommendations = bundle.catalog.recommendations || [];
  const trackedProviders = bundle.catalog.tracked_providers || 0;
  const catalogAlerts = (bundle.catalog.alerts || []).concat(bundle.catalog.source_alerts || []);
  const operatorRows = bundle.operators.events || [];
  const modalityRows = bundle.stats.modalities || [];
  const priority = derivePriority(bundle);
  const alerts = topAlertBundle(bundle);
  const readiness = bundle.inventory.request_readiness || {};
  const topCost = bundle.stats.client_highlights ? bundle.stats.client_highlights.top_cost : null;
  const slowest = bundle.stats.client_highlights ? bundle.stats.client_highlights.slowest_client : null;
  const failureHeavy = bundle.stats.client_highlights ? bundle.stats.client_highlights.highest_failure_rate : null;
  const fallbackShare = (selectionPaths.filter(row => String(row.selection_path || '').includes('fallback')).reduce((sum, row) => sum + (Number(row.requests) || 0), 0) / Math.max(1, Number(totals.total_requests || 1))) * 100;
  const unhealthyProviders = providers.filter(row => row.healthy === false);
  const unresolvedProviders = providers.filter(row => (row.request_readiness || {}).status && !String((row.request_readiness || {}).status).startsWith('ready'));
  const premiumRoutes = providers.filter(row => ['premium', 'subscription'].includes(((row.transport || {}).billing_mode || '').toLowerCase()));
  const quotaCoupled = providers.filter(row => (row.transport || {}).quota_group);
  const sortedProviders = [...providers].sort((a, b) => {
    const aBlocked = String(((a.request_readiness || {}).status || '')).startsWith('ready') ? 0 : 1;
    const bBlocked = String(((b.request_readiness || {}).status || '')).startsWith('ready') ? 0 : 1;
    const aUnhealthy = a.healthy === false ? 1 : 0;
    const bUnhealthy = b.healthy === false ? 1 : 0;
    const aCost = Number((providerMetrics[a.name] || {}).cost_usd || 0);
    const bCost = Number((providerMetrics[b.name] || {}).cost_usd || 0);
    return (bBlocked - aBlocked) || (bUnhealthy - aUnhealthy) || (bCost - aCost) || String(a.name || '').localeCompare(String(b.name || ''));
  });
  const sortedClients = [...clientTotals].sort((a, b) => (Number(b.cost_usd || 0) - Number(a.cost_usd || 0)) || (Number(b.failures || 0) - Number(a.failures || 0)) || (Number(b.requests || 0) - Number(a.requests || 0)));
  const sortedRouting = [...routing].sort((a, b) => (Number(b.cost_usd || 0) - Number(a.cost_usd || 0)) || (Number(b.requests || 0) - Number(a.requests || 0)));

  let primaryAction = {target: 'providers', label: 'Open providers'};
  let secondaryAction = {target: 'routes', label: 'Inspect routes'};
  if (priority.path.startsWith('Clients')) {
    primaryAction = {target: 'clients', label: 'Open clients'};
    secondaryAction = {target: 'routes', label: 'Inspect route pressure'};
  } else if (priority.path.startsWith('Routes')) {
    primaryAction = {target: 'routes', label: 'Inspect routes'};
    secondaryAction = {target: 'providers', label: 'Open providers'};
  } else if (priority.path.startsWith('Catalog') || priority.path.startsWith('Review top alert')) {
    primaryAction = {target: 'catalog', label: 'Review catalog'};
    secondaryAction = {target: 'providers', label: 'Open providers'};
  }

  $('#hero-status').textContent = (bundle.health.summary && bundle.health.summary.providers_unhealthy === 0) ? 'System healthy. Safe to review cost posture.' : 'Risk or drift detected. Start with attention.';
  $('#ago').textContent = ago(totals.last_request);
  $('#priority-ribbon').textContent = priority.ribbon || 'Operator focus';
  $('#priority-state').textContent = priority.state;
  $('#priority-path').textContent = priority.path;
  $('#priority-why').textContent = priority.why;
  $('#priority-list').innerHTML = priority.list.map(item => '<div class="priority-item">' + esc(item) + '</div>').join('');
  $('#priority-action-primary').dataset.targetView = primaryAction.target;
  $('#priority-action-primary').textContent = primaryAction.label;
  $('#priority-action-secondary').dataset.targetView = secondaryAction.target;
  $('#priority-action-secondary').textContent = secondaryAction.label;
  $('#rail-readiness').textContent = (readiness.providers_ready || 0) + '/' + (readiness.providers_total || providers.length) + ' ready';
  $('#rail-pressure').textContent = alerts[0] ? alerts[0].headline : 'No active pressure';
  $('#rail-next').textContent = priority.path;
  $('#snapshot-rack').innerHTML = [
    ['Request-ready', (readiness.providers_ready || 0) + ' / ' + (readiness.providers_total || providers.length)],
    ['Healthy providers', (bundle.health.summary ? bundle.health.summary.providers_healthy : providers.filter(row => row.healthy).length) + ' / ' + providers.length],
    ['Fallback share', fmtPct(fallbackShare)],
    ['Top lane family', laneFamilies.length ? (laneFamilies[0].lane_family || 'unclassified') : '—'],
    ['Top cost client', topCost ? (topCost.client_tag || topCost.client_profile || 'generic') : '—'],
    ['Catalog due', String(sourceCatalog.due_sources || 0)],
  ].map(([label, value]) => `<div class="rack-row"><div class="label">${esc(label)}</div><strong>${esc(value)}</strong></div>`).join('');

  $('#overview-cards').innerHTML = [
    {kicker:'Request-ready', value:(readiness.providers_ready || 0) + '/' + (readiness.providers_total || providers.length), detail:String(readiness.providers_not_ready || 0) + ' need review', tone:'blue'},
    {kicker:'Healthy providers', value:(bundle.health.summary ? bundle.health.summary.providers_healthy : providers.filter(row => row.healthy).length) + '/' + providers.length, detail:String(unhealthyProviders.length) + ' unhealthy', tone:'green'},
    {kicker:'Active alerts', value:String(alerts.length), detail:alerts[0] ? alerts[0].headline : 'No active alert', tone:alerts.length ? 'orange' : 'lime'},
    {kicker:'Fallback share', value:fmtPct(fallbackShare), detail:'Traffic that routed through fallback', tone:fallbackShare > 10 ? 'danger' : 'blue'},
    {kicker:'Estimated spend', value:fmtUsd(totals.total_cost_usd || 0), detail:fmtTok((totals.total_prompt_tokens || 0) + (totals.total_compl_tokens || 0)) + ' tokens', tone:'orange'},
    {kicker:'Avg latency', value:fmtMs(totals.avg_latency_ms || 0), detail:'Last request ' + ago(totals.last_request), tone:'green'},
    {kicker:'Catalog drift', value:String(bundle.catalog.alert_count || 0), detail:String(sourceCatalog.due_sources || 0) + ' reviews due', tone:'orange'},
    {kicker:'Top client', value:esc(bundle.stats.client_highlights && bundle.stats.client_highlights.top_requests ? (bundle.stats.client_highlights.top_requests.client_tag || bundle.stats.client_highlights.top_requests.client_profile || 'generic') : '—'), detail:'Highest request volume', tone:'lime'},
  ].map(metricCard).join('');

  $('#focus-chip').innerHTML = alerts.length ? '<strong>' + esc(alerts.length) + '</strong> active issues' : 'No active alert';
  $('#overview-alerts').innerHTML = alerts.map(alertCard).join('');
  $('#overview-evidence').innerHTML = [
    {title:'Cost pressure', body:topCost ? 'Top spend is coming from ' + (topCost.client_tag || topCost.client_profile || 'one client') + '. Confirm the entry mode.' : 'No client spend pressure in this scope.'},
    {title:'Fallback pressure', body:fallbackShare > 0 ? 'Fallback is active in ' + fmtPct(fallbackShare) + ' of scoped traffic. Confirm it is expected.' : 'No fallback pressure in this scope.'},
  ].map(card => `<div class="focus-card"><strong>${esc(card.title)}</strong><p>${esc(card.body)}</p></div>`).join('');

  const overviewDailyLabels = (bundle.stats.daily || []).map(row => row.day || '');
  const overviewHourlyLabels = (bundle.stats.hourly || []).map(row => row.hour_offset || '');
  $('#overview-trends').innerHTML = [
    trendCard('overview-cost-plot', (bundle.stats.daily || []).map(row => row.cost_usd || 0), {title:'Daily cost', subtitle:'30 day spend', tone:'#FFAA19', format:fmtUsd, labels:overviewDailyLabels}),
    trendCard('overview-hourly-plot', (bundle.stats.hourly || []).map(row => row.requests || 0), {title:'Hourly requests', subtitle:'24 hour traffic', tone:'#54ABEE', format:value => fmt(value, 0), labels:overviewHourlyLabels}),
  ].join('');
  renderTrendPlot('overview-cost-plot', (bundle.stats.daily || []).map(row => row.cost_usd || 0), {
    tone:'#FFAA19',
    fill:'rgba(255,170,25,.14)',
    format:fmtUsd,
    labels:overviewDailyLabels,
    tickFormat: (value, index) => overviewDailyLabels[index] || '',
  });
  renderTrendPlot('overview-hourly-plot', (bundle.stats.hourly || []).map(row => row.requests || 0), {
    tone:'#54ABEE',
    fill:'rgba(84,171,238,.16)',
    format:value => fmt(value, 0),
    labels:overviewHourlyLabels,
    tickFormat: (value, index) => {
      const label = overviewHourlyLabels[index];
      return index % 4 === 0 ? (label != null ? String(label) : '') : '';
    },
  });

  $('#overview-families').innerHTML = barList(laneFamilies.slice(0, 6), {
    label: row => row.lane_family || 'unclassified',
    detail: row => (row.providers || 0) + ' providers · ' + (row.cooldown_requests || 0) + ' cooldown req · ' + (row.recovered_requests || 0) + ' recovered',
    value: row => row.requests || 0,
    format: value => fmtTok(value),
    tone: 'blue',
    empty: 'No lane family data in this scope',
  });
  $('#overview-recent').innerHTML = recentLogItems(recent);

  $('#providers-kpis').innerHTML = [
    {kicker:'Healthy vs total', value:(bundle.health.summary ? bundle.health.summary.providers_healthy : providers.filter(row => row.healthy).length) + '/' + providers.length, detail:String(unhealthyProviders.length) + ' unhealthy', tone:unhealthyProviders.length ? 'orange' : 'green'},
    {kicker:'Request-ready', value:(readiness.providers_ready || 0) + '/' + (readiness.providers_total || providers.length), detail:String(readiness.providers_not_ready || 0) + ' blocked or degraded', tone:(readiness.providers_not_ready || 0) ? 'danger' : 'green'},
    {kicker:'Unresolved keys', value:String(providers.filter(row => String(((row.request_readiness || {}).operator_hint || '')).toLowerCase().includes('key')).length), detail:'Runtime key and auth blockers', tone:'orange'},
    {kicker:'Quota-coupled', value:String(quotaCoupled.length), detail:'Shared quota domains visible', tone:'blue'},
    {kicker:'Aggregator-backed', value:String(providers.filter(row => ((row.lane || {}).route_type || '') === 'aggregator').length), detail:'Aggregator transport surfaces', tone:'blue'},
    {kicker:'Premium-risk', value:String(premiumRoutes.length), detail:'Premium or subscription-backed', tone:'orange'},
  ].map(metricCard).join('');
  $('#providers-alerts').innerHTML = [
    ...(unresolvedProviders.slice(0, 2).map(row => ({
      level: 'critical',
      headline: row.name + ' is not request-ready',
      detail: ((row.request_readiness || {}).operator_hint) || 'The route is configured but cannot safely accept requests yet.',
      suggestion: 'Review health, unresolved keys, and quota coupling.',
    }))),
    ...(unhealthyProviders.slice(0, 2).map(row => ({
      level: 'warning',
      headline: row.name + ' is unhealthy',
      detail: row.last_error || 'The route is failing live checks.',
      suggestion: 'Check provider health and recent traces before sending more traffic.',
    }))),
  ].slice(0, 4).map(alertCard).join('') || empty('No provider warnings in this scope', 'Open All traffic if you expected a readiness or health issue.');
  $('#providers-summary').innerHTML = [
    {title:'Healthy vs total', body:(bundle.health.summary ? bundle.health.summary.providers_healthy : providers.filter(row => row.healthy).length) + ' healthy routes across ' + providers.length + ' providers.'},
    {title:'Request-readiness', body:(readiness.providers_ready || 0) + ' routes are request-ready; ' + (readiness.providers_not_ready || 0) + ' need review.'},
    {title:'Quota coupling', body:quotaCoupled.length + ' providers share a visible quota domain.'},
  ].map(card => `<div class="catalog-card"><strong>${esc(card.title)}</strong><p>${esc(card.body)}</p></div>`).join('');
  $('#providers-chip').textContent = providers.length + ' providers';
  $('#providers-table tbody').innerHTML = sortedProviders.length ? sortedProviders.map(row => providerRow(row, providerMetrics)).join('') : tableEmpty(9, 'No provider inventory available', 'Open All traffic or check the provider inventory endpoint.');

  $('#clients-kpis').innerHTML = [
    {kicker:'Active clients', value:String(clientTotals.length), detail:'Distinct client tags or profiles in scope', tone:'blue'},
    {kicker:'Premium drift', value:topCost ? fmtUsd(topCost.cost_usd || 0) : '$0.00', detail:topCost ? (topCost.client_tag || topCost.client_profile || 'top client') : 'No spend signal', tone:'orange'},
    {kicker:'Failure-heavy', value:failureHeavy ? fmtPct(100 - (failureHeavy.success_pct || 0)) : '0.0%', detail:failureHeavy ? (failureHeavy.client_tag || failureHeavy.client_profile || 'client') : 'No failure signal', tone:failureHeavy ? 'danger' : 'green'},
    {kicker:'Slowest client', value:slowest ? fmtMs(slowest.avg_latency_ms || 0) : '—', detail:slowest ? (slowest.client_tag || slowest.client_profile || 'client') : 'No latency signal', tone:'blue'},
    {kicker:'Highest spend', value:topCost ? (topCost.client_tag || topCost.client_profile || 'client') : '—', detail:topCost ? fmtUsd(topCost.cost_usd || 0) + ' total' : 'No spend signal', tone:'orange'},
    {kicker:'Fallback-active', value:String(selectionPaths.filter(row => String(row.selection_path || '').includes('fallback')).length), detail:'Clients that used fallback paths', tone:'lime'},
  ].map(metricCard).join('');
  $('#clients-highlights').innerHTML = [
    {title:'Cost posture', body:topCost ? (topCost.client_tag || topCost.client_profile || 'generic') + ' is carrying ' + fmtUsd(topCost.cost_usd || 0) + ' in this scope.' : 'No client spend signal in this scope.'},
    {title:'Latency posture', body:slowest ? (slowest.client_tag || slowest.client_profile || 'generic') + ' averages ' + fmtMs(slowest.avg_latency_ms || 0) + '.' : 'No client latency signal in this scope.'},
    {title:'Reliability posture', body:failureHeavy ? (failureHeavy.client_tag || failureHeavy.client_profile || 'generic') + ' is failing ' + fmtPct(100 - (failureHeavy.success_pct || 0)) + ' of requests.' : 'No reliability issue in this scope.'},
  ].map(card => `<div class="catalog-card"><strong>${esc(card.title)}</strong><p>${esc(card.body)}</p></div>`).join('');
  $('#clients-table tbody').innerHTML = sortedClients.length ? sortedClients.map(row => `
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
  `).join('') : tableEmpty(9, 'No client traffic in this scope', 'Clear filters or switch to All traffic.');

  $('#routes-kpis').innerHTML = [
    {kicker:'Active routes', value:String(routing.length), detail:'Routing rows in scope', tone:'blue'},
    {kicker:'Request-ready', value:(readiness.providers_ready || 0) + '/' + (readiness.providers_total || providers.length), detail:'Ready providers behind current routes', tone:'green'},
    {kicker:'Under cooldown', value:String(laneFamilies.reduce((sum, row) => sum + (row.cooldown_requests || 0), 0)), detail:'Requests under cooldown', tone:'orange'},
    {kicker:'Premium routes', value:String(premiumRoutes.length), detail:'Premium or subscription-backed', tone:'orange'},
    {kicker:'Fallback-active', value:fmtPct(fallbackShare), detail:'Traffic routed through fallback', tone:fallbackShare > 10 ? 'danger' : 'blue'},
    {kicker:'Recovery events', value:String(laneFamilies.reduce((sum, row) => sum + (row.recovered_requests || 0), 0)), detail:'Recovered requests', tone:'lime'},
  ].map(metricCard).join('');
  $('#routes-selection').innerHTML = barList(selectionPaths.slice(0, 6), {
    label: row => row.selection_path || 'unclassified',
    detail: row => (row.lane_family || 'no family') + ' · ' + (row.runtime_window_state || 'clear'),
    value: row => row.requests || 0,
    format: value => fmtTok(value),
    tone: 'lime',
    empty: 'No selected path data in this scope',
  });
  $('#routes-pressure').innerHTML = barList((laneFamilies || []).slice(0, 6), {
    label: row => row.lane_family || 'unclassified',
    detail: row => (row.cooldown_requests || 0) + ' cooldown req · ' + (row.degraded_requests || 0) + ' degraded req · ' + (row.recovered_requests || 0) + ' recovered',
    value: row => (row.cooldown_requests || 0) + (row.degraded_requests || 0) + (row.recovered_requests || 0),
    format: value => fmtTok(value),
    tone: 'orange',
    empty: 'No route pressure in this scope',
  });
  $('#routes-table tbody').innerHTML = sortedRouting.length ? sortedRouting.map(row => `
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
  `).join('') : tableEmpty(8, 'No routing rows in this scope', 'Clear filters or switch to All traffic.');

  const analyticsDailyLabels = (bundle.stats.daily || []).map(row => row.day || '');
  const analyticsHourlyLabels = (bundle.stats.hourly || []).map(row => row.hour_offset || '');
  $('#analytics-kpis').innerHTML = [
    {kicker:'Requests', value:fmtTok(totals.total_requests || 0), detail:'Filtered volume', tone:'blue'},
    {kicker:'Input tokens', value:fmtTok(totals.total_prompt_tokens || 0), detail:'Prompt-side tokens', tone:'blue'},
    {kicker:'Output tokens', value:fmtTok(totals.total_compl_tokens || 0), detail:'Completion-side tokens', tone:'lime'},
    {kicker:'Est. cost', value:fmtUsd(totals.total_cost_usd || 0), detail:'Estimated scoped spend', tone:'orange'},
    {kicker:'Avg latency', value:fmtMs(totals.avg_latency_ms || 0), detail:'Observed request latency', tone:'green'},
    {kicker:'Cache hit rate', value:fmtPct(totals.cache_hit_pct || 0), detail:'Requests served from cache', tone:'lime'},
  ].map(metricCard).join('');
  $('#analytics-daily').innerHTML = trendCard('analytics-requests-plot', (bundle.stats.daily || []).map(row => row.requests || 0), {
    title:'Requests by day',
    subtitle:'30 day request flow',
    tone:'#54ABEE',
    format:value => fmt(value, 0),
    labels:analyticsDailyLabels,
  }) + trendCard('analytics-cost-plot', (bundle.stats.daily || []).map(row => row.cost_usd || 0), {
    title:'Cost by day',
    subtitle:'30 day spend',
    tone:'#FFAA19',
    format:fmtUsd,
    labels:analyticsDailyLabels,
  });
  $('#analytics-hourly').innerHTML = trendCard('analytics-hourly-plot', (bundle.stats.hourly || []).map(row => (row.tokens || 0)), {
    title:'Tokens by hour',
    subtitle:'24 hour token pulse',
    tone:'#C4D900',
    format:fmtTok,
    labels:analyticsHourlyLabels,
  });
  renderTrendPlot('analytics-requests-plot', (bundle.stats.daily || []).map(row => row.requests || 0), {
    tone:'#54ABEE',
    fill:'rgba(84,171,238,.16)',
    format:value => fmt(value, 0),
    labels:analyticsDailyLabels,
    tickFormat: (value, index) => analyticsDailyLabels[index] || '',
  });
  renderTrendPlot('analytics-cost-plot', (bundle.stats.daily || []).map(row => row.cost_usd || 0), {
    tone:'#FFAA19',
    fill:'rgba(255,170,25,.14)',
    format:fmtUsd,
    labels:analyticsDailyLabels,
    tickFormat: (value, index) => analyticsDailyLabels[index] || '',
  });
  renderTrendPlot('analytics-hourly-plot', (bundle.stats.hourly || []).map(row => (row.tokens || 0)), {
    tone:'#C4D900',
    fill:'rgba(196,217,0,.16)',
    format:fmtTok,
    labels:analyticsHourlyLabels,
    tickFormat: (value, index) => {
      const label = analyticsHourlyLabels[index];
      return index % 4 === 0 ? (label != null ? String(label) : '') : '';
    },
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
  `).join('') : tableEmpty(6, 'No modality data in this scope', 'Widen the scope or wait for requests with provider and layer coverage.');
  $('#analytics-operators tbody').innerHTML = operatorRows.length ? operatorRows.map(row => `
    <tr>
      <td>${pill(row.event_type || 'update', 'subtle')}</td>
      <td>${esc(row.action || 'update-check')}</td>
      <td>${esc(row.status || '—')}</td>
      <td>${esc(row.target_version || row.update_type || '—')}</td>
      <td>${row.eligible ? pill('eligible', 'ready') : pill('blocked', 'degraded')}</td>
      <td class="mono">${fmtTok(row.events || 0)}</td>
    </tr>
  `).join('') : tableEmpty(6, 'No operator actions in this scope', 'Expected if no updates or local operator events were recorded.');

  $('#catalog-kpis').innerHTML = [
    {kicker:'Tracked providers', value:String(bundle.catalog.tracked_providers || 0), detail:'Providers covered by the catalog', tone:'blue'},
    {kicker:'Refresh due', value:String(sourceCatalog.due_sources || 0), detail:'Source reviews due next', tone:(sourceCatalog.due_sources || 0) ? 'orange' : 'green'},
    {kicker:'Evidence issues', value:String(sourceCatalog.error_sources || 0), detail:'Refresh or parsing errors', tone:(sourceCatalog.error_sources || 0) ? 'danger' : 'green'},
    {kicker:'Volatile offers', value:String(catalogItems.filter(row => String(row.volatility || '').toLowerCase().includes('high')).length), detail:'Offers flagged as highly volatile', tone:'orange'},
    {kicker:'Untracked providers', value:String(Math.max(0, (bundle.catalog.total_providers || providers.length) - (bundle.catalog.tracked_providers || 0))), detail:'Configured providers outside coverage', tone:'blue'},
    {kicker:'Recent changes', value:String(sourceCatalog.recent_changes || 0), detail:'Source updates in the review window', tone:'lime'},
    {kicker:'Pricing coverage', value:String(costTruth.tracked_with_pricing || 0) + '/' + trackedProviders, detail:'Providers with pricing metadata', tone:'blue'},
    {kicker:'Numeric rates', value:String(costTruth.tracked_with_numeric_rates || 0) + '/' + trackedProviders, detail:'Providers with numeric rates', tone:'green'},
    {kicker:'Fresh pricing', value:String((costTruth.pricing_freshness || {}).fresh || 0) + '/' + (costTruth.tracked_with_pricing || 0), detail:'Pricing metadata updated within freshness window', tone:'lime'},
  ].map(metricCard).join('');
  $('#catalog-summary').innerHTML = [
    {title:'Tracked providers', body:String(bundle.catalog.tracked_providers || 0) + ' of ' + String(bundle.catalog.total_providers || providers.length) + ' configured routes are covered.'},
    {title:'Source freshness', body:String(sourceCatalog.due_sources || 0) + ' reviews are due and ' + String(sourceCatalog.error_sources || 0) + ' sources have evidence issues.'},
    {title:'Alert count', body:String(catalogAlerts.length) + ' catalog or source alerts are active.'},
  ].map(card => `<div class="catalog-card"><strong>${esc(card.title)}</strong><p>${esc(card.body)}</p></div>`).join('');
  $('#catalog-alerts').innerHTML = catalogAlerts.length ? catalogAlerts.slice(0, 5).map(alert => alertCard({
    level: alert.severity || 'notice',
    headline: alert.provider ? alert.provider + ': ' + (alert.code || 'catalog alert') : (alert.code || 'source alert'),
    detail: alert.message || alert.headline || 'Catalog drift alert',
    suggestion: alert.recommended_model ? 'Check ' + alert.recommended_model + ' and refresh evidence.' : 'Review the relevant source and refresh the catalog trail.',
  })).join('') : empty('No catalog alerts in this scope', 'No freshness, evidence, or model-mismatch issues are visible.');
  const sourceItems = sourceCatalog.items || [];
  $('#catalog-guidance').innerHTML = barList(sourceItems.slice(0, 6), {
    label: row => row.provider_id || row.provider || 'source',
    detail: row => (row.status || 'unknown') + ' · models ' + (row.models_count || 0) + ' · pricing ' + (row.pricing_count || 0),
    value: row => (row.models_count || 0) + (row.pricing_count || 0),
    format: value => fmt(value, 0),
    tone: 'green',
    empty: 'No refresh guidance in this scope',
  });
  $('#catalog-priority-clusters').innerHTML = barList(priorityClusters.slice(0, 6), {
    label: cluster => cluster.name,
    detail: cluster => cluster.description,
    value: cluster => cluster.item_count,
    format: (value, cluster) => value + '/' + cluster.total_items,
    tone: cluster => cluster.priority === 'high' ? 'orange' : cluster.priority === 'medium' ? 'blue' : 'green',
    empty: 'No priority clusters to display',
  });
  $('#catalog-recommendations').innerHTML = recommendations.length ? recommendations.slice(0, 5).map(rec => alertCard({
    level: rec.priority || 'medium',
    headline: rec.title || rec.id,
    detail: rec.description || '',
    suggestion: rec.action || '',
  })).join('') : empty('No recommendations in this scope', 'Catalog health is fully aligned.');
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
  `).join('') : tableEmpty(8, 'No tracked provider assumptions in this scope', 'Widen the scope or check whether provider catalog coverage is enabled.');

  $('#integrations-kpis').innerHTML = [
    {kicker:'Claude-ready', value:(readiness.providers_ready || 0) ? 'Yes' : 'No', detail:'Anthropic endpoint reachable', tone:(readiness.providers_ready || 0) ? 'green' : 'orange'},
    {kicker:'OpenAI-ready', value:providers.length ? 'Yes' : 'No', detail:'OpenAI endpoint reachable locally', tone:providers.length ? 'green' : 'orange'},
    {kicker:'Agent-native modes', value:'3', detail:'coding-auto, coding-fast, coding-premium', tone:'blue'},
    {kicker:'Saved views', value:String(Object.keys(SAVED_VIEWS).length), detail:'Scope shortcuts', tone:'lime'},
    {kicker:'Providers visible', value:String(providers.length), detail:'Visible in runtime inventory', tone:'blue'},
    {kicker:'Validation posture', value:unhealthyProviders.length ? 'Review' : 'Clear', detail:unhealthyProviders.length ? 'Check provider health before rollout' : 'No blocker visible', tone:unhealthyProviders.length ? 'orange' : 'green'},
  ].map(metricCard).join('');
  $('#integration-alerts').innerHTML = [
    integrationAlert('Model not found', 'Usually means the client used the wrong model id or an alias still points at a raw provider instead of a Gate mode.'),
    integrationAlert('Provider unhealthy', 'Check Providers first, then Routes. Cooldown and quota coupling should be visible before you chase client config.'),
    integrationAlert('Unexpected premium spend', 'If Sonnet or Opus spend spikes, confirm the client is using coding-auto or eco where appropriate and not bypassing route intent.'),
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
$('#saved-view').addEventListener('change', event => {
  const value = event.target.value;
  if (!value) {
    scheduleLoad();
    return;
  }
  applySavedView(value);
});
['#filter-provider', '#filter-modality', '#filter-profile', '#filter-client', '#filter-layer', '#filter-success'].forEach(sel => {
  const el = $(sel);
  if (!el) return;
  const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
  el.addEventListener(eventName, scheduleLoad);
});
syncStateFromUrl();
updateHeaderForView();
load();
setInterval(load, 30000);
let resizeTimer = null;
window.addEventListener('resize', () => {
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    if (latestBundle) render(latestBundle);
  }, 120);
});
</script>
</body>
</html>
"""

DASHBOARD_HTML = (
    DASHBOARD_HTML.replace("/*__UPLOT_CSS__*/", _read_vendor_asset("uPlot.min.css"))
    .replace("/*__UPLOT_JS__*/", _read_vendor_asset("uplot.iife.min.js"))
    .replace("__BRAND_LOGO__", _inline_svg("fusionaize-logo.svg"))
    .replace("__FAIGATE_VERSION__", __version__)
)
