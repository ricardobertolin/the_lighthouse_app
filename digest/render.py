"""Stage 7-8: Build digest.html and open in default browser."""
from __future__ import annotations

import json
import webbrowser
from datetime import date, datetime
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent.parent / "index.html"

# ---------------------------------------------------------------------------
# HTML template — __DATA_JSON__ is replaced at render time.
# Newsprint design: 1-bit dithered newspaper aesthetic.
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Lighthouse</title>
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#20201c">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="The Lighthouse">
<link rel="icon" type="image/png" href="the_lighthouse2.png">
<link rel="apple-touch-icon" href="the_lighthouse2.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=UnifrakturCook:wght@700&family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=PT+Serif:ital,wght@0,400;0,700;1,400&family=Oswald:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
html,body{min-height:100%;}
:root{
  --desk:#ccc4ad;--paper:#efe9d8;--ink:#20201c;--ink-soft:#3a382f;
  --m1:#5a564a;--m2:#6a6557;--m3:#7a7464;
  --hair:#c4bda6;--meter:#d8d1bb;
}
body{background:var(--desk);font-family:'PT Serif',Georgia,serif;color:var(--ink);}
::selection{background:var(--ink);color:var(--paper);}
a{color:inherit;text-decoration:none;}

/* ── Sheet ── */
.desk{padding:34px 16px 56px;}
.sheet{
  max-width:840px;margin:0 auto;background:var(--paper);
  border:1px solid var(--ink);
  box-shadow:0 2px 0 var(--ink),0 22px 44px rgba(40,36,24,.34);
  padding:30px 38px 40px;
}

/* ── Masthead ── */
.mast-vol{
  display:flex;justify-content:space-between;align-items:center;
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:1.5px;
  font-size:11px;color:var(--ink-soft);border-bottom:1px solid var(--ink);padding-bottom:6px;
}
.mast-title{
  display:flex;align-items:center;gap:14px;margin:12px 0 6px;
}
.mast-title-text{
  font-family:'UnifrakturCook','Playfair Display',serif;
  font-size:74px;line-height:.96;letter-spacing:1px;white-space:nowrap;flex:none;
}
.mast-rule{flex:1;display:flex;align-items:center;gap:8px;}
.mast-rule-l{justify-content:flex-end;}
.mast-rule-r{justify-content:flex-start;}
.mast-rule-line{flex:1;height:1px;background:var(--ink);}
.mast-rule-gem{font-size:10px;color:var(--ink);line-height:1;}
.mast-date{
  display:flex;justify-content:space-between;align-items:center;
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:1.5px;
  font-size:11px;color:var(--ink-soft);
  border-top:3px double var(--ink);border-bottom:3px double var(--ink);padding:6px 0;
}
.mast-date-center{font-weight:600;letter-spacing:2px;color:var(--ink);}

/* ── Lang toggle ── */
.lang-toggle{display:flex;gap:0;}
.lang-btn{
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:1px;
  font-size:10px;padding:2px 7px;cursor:pointer;border:1px solid var(--ink);
  background:transparent;color:var(--m1);font-weight:400;
}
.lang-btn:first-child{border-right:none;}
.lang-btn.active{background:var(--ink);color:var(--paper);font-weight:600;}

/* ── Forecast ── */
.forecast{border:1px solid var(--ink);margin-top:18px;overflow:hidden;}
.fx-canvas{
  position:relative;overflow:hidden;
  filter:url(#ditherBig);
  background:#888;
}
.fx-canvas img{width:100%;height:auto;display:block;}
.fx-panel{
  padding:12px 20px;
  background:#141412;
  display:flex;align-items:center;justify-content:space-between;gap:16px;
}
.fx-panel-left{display:flex;flex-direction:column;gap:2px;}
.fx-kicker{font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:3px;font-size:10px;color:#b0a898;}
.fx-condition{font-family:'Playfair Display',serif;font-weight:900;font-size:28px;line-height:1;color:#efe9d8;}
.fx-strapline{font-style:italic;font-size:13px;color:#8a8070;}
.fx-stats{display:flex;gap:20px;font-family:'Oswald',sans-serif;font-size:13px;letter-spacing:.5px;color:#efe9d8;}
.fx-stats b{font-weight:600;color:#b0a898;}

/* ── Section nav ── */
.section-nav{
  display:flex;margin-top:22px;
  border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);
  overflow-x:auto;-webkit-overflow-scrolling:touch;
}
.section-nav::-webkit-scrollbar{height:0;}
.nav-divider{width:1px;flex:none;background:var(--ink);}
.nav-btn{
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:2px;
  font-size:13px;padding:11px 18px;cursor:pointer;border:none;
  background:transparent;color:var(--m1);font-weight:400;white-space:nowrap;flex:none;
}
.nav-btn:hover{background:rgba(32,32,28,.06);}
.nav-btn.active{background:var(--ink);color:var(--paper);font-weight:600;}
.dispatch-line{text-align:center;font-style:italic;font-size:14px;color:var(--m1);margin-top:8px;}

/* ── Filter strip ── */
.filter-strip{
  border-top:1px solid var(--hair);border-bottom:1px solid var(--hair);
  padding:10px 0;margin-top:14px;
  display:flex;flex-wrap:wrap;align-items:center;gap:16px;
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:1px;
  font-size:11px;color:var(--m1);
}
.flt-group{display:flex;align-items:center;gap:8px;}
.flt-label{font-weight:600;letter-spacing:1.5px;white-space:nowrap;}
.flt-val{color:var(--ink);min-width:28px;}
.flt-range{
  -webkit-appearance:none;appearance:none;
  width:90px;height:3px;background:var(--meter);border:1px solid var(--ink);
  cursor:pointer;outline:none;
}
.flt-range::-webkit-slider-thumb{
  -webkit-appearance:none;width:10px;height:10px;
  background:var(--ink);border-radius:0;cursor:pointer;
}
.flt-range::-moz-range-thumb{
  width:10px;height:10px;background:var(--ink);
  border-radius:0;border:none;cursor:pointer;
}
.flt-check-lbl{display:flex;align-items:center;gap:5px;cursor:pointer;}
.flt-check{cursor:pointer;accent-color:var(--ink);}
.flt-div{width:1px;height:18px;background:var(--hair);}

/* ── Briefing ── */
.briefing{margin-top:20px;border-top:3px double var(--ink);border-bottom:1px solid var(--ink);padding:14px 0;}
.briefing-label{
  text-align:center;font-family:'Oswald',sans-serif;text-transform:uppercase;
  letter-spacing:4px;font-size:12px;color:var(--ink-soft);margin-bottom:8px;
}
.briefing-body{
  font-size:16px;line-height:1.5;text-align:justify;
  column-count:2;column-gap:30px;
}
.drop-cap{
  float:left;font-family:'Playfair Display',serif;font-weight:900;
  font-size:56px;line-height:.78;padding:4px 8px 0 0;
}

/* ── Stats ── */
.edition-stats{
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:1px;
  font-size:10px;color:var(--m2);text-align:right;
  margin-top:12px;padding-bottom:6px;border-bottom:1px solid var(--hair);
}

/* ── Article rows ── */
.art-row{
  display:flex;gap:18px;align-items:flex-start;
  padding:18px 0;border-bottom:1px solid var(--hair);
}
.art-row.hidden{display:none;}
.art-row.low-sig{opacity:.45;}
.art-thumb-col{width:96px;flex:none;}
.art-thumb-frame{border:1px solid var(--ink);background:var(--paper);padding:3px;}
.art-thumb{width:90px;height:90px;object-fit:cover;display:block;filter:url(#dither);}
.art-thumb-empty{
  width:90px;height:90px;background:var(--meter);
  display:flex;align-items:center;justify-content:center;
  font-family:'Oswald',sans-serif;font-size:8px;letter-spacing:1px;
  text-transform:uppercase;color:var(--m2);text-align:center;padding:4px;
}
.art-source-cap{
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:.5px;
  font-size:8.5px;color:var(--m2);text-align:center;margin-top:4px;
}
.art-content-col{flex:1;min-width:0;}
.art-kicker-row{
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:2px;
  font-size:11px;color:var(--ink-soft);
  border-bottom:1px solid var(--hair);padding-bottom:4px;margin-bottom:6px;
  display:flex;justify-content:space-between;
}
.art-rank-no{color:var(--m3);}
.art-headline{
  font-family:'Playfair Display',serif;font-weight:700;font-size:23px;line-height:1.12;
  color:var(--ink);display:block;
}
.art-headline:hover{text-decoration:underline;}
.art-deck{font-size:15.5px;line-height:1.4;margin-top:6px;text-align:justify;color:var(--ink);}
.art-note{font-style:italic;font-size:14px;color:var(--m2);line-height:1.4;margin-top:4px;}
.art-meta{
  display:flex;align-items:center;gap:12px;margin-top:12px;flex-wrap:wrap;
  font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:1px;
  font-size:10px;color:var(--m1);
}
.meta-div{width:1px;height:11px;background:#9a937e;flex:none;}
.rel-wrap{display:inline-flex;align-items:center;gap:6px;}
.rel-bg{width:54px;height:7px;background:var(--meter);border:1px solid var(--ink);display:inline-block;}
.rel-fill{display:block;height:100%;background:var(--ink);}

/* ── Footer ── */
.edition-footer{
  text-align:center;font-family:'Oswald',sans-serif;text-transform:uppercase;
  letter-spacing:4px;font-size:11px;color:var(--m3);padding:18px 0 2px;
}
.gen-footer{
  text-align:center;font-family:'Oswald',sans-serif;font-size:10px;
  letter-spacing:1px;text-transform:uppercase;color:var(--m3);margin-top:20px;
  padding-bottom:4px;
}
.made-by{
  text-align:center;font-family:'Oswald',sans-serif;font-size:10px;
  letter-spacing:1px;text-transform:uppercase;color:var(--m3);
  padding-bottom:14px;
}

/* ── Weather animations ── */
@keyframes rainfall {
  0%   { transform:translate(0,-25px);opacity:0; }
  12%  { opacity:1; }
  88%  { opacity:.85; }
  100% { transform:translate(10px,200px);opacity:0; }
}
@keyframes snowfall {
  0%   { transform:translate(0,-10px) scale(1);opacity:0; }
  15%  { opacity:1; }
  85%  { opacity:.9; }
  100% { transform:translate(-8px,200px) scale(.7);opacity:0; }
}
@keyframes lightning-flash {
  0%,82%     { opacity:0; }
  83%        { opacity:.88; }
  84%        { opacity:0; }
  85.5%      { opacity:.55; }
  87%,100%   { opacity:0; }
}
.fx-rain-streak {
  position:absolute;width:2px;background:#1c1c1c;border-radius:1px;
  animation:rainfall linear infinite;
}
.fx-snow-dot {
  position:absolute;width:5px;height:5px;border-radius:50%;background:#d8d8d8;
  animation:snowfall linear infinite;
}
.fx-lightning-flash {
  position:absolute;inset:0;background:#d8eaf8;pointer-events:none;
  animation:lightning-flash 3.5s ease-in infinite;
}

/* ── Share button ── */
.art-actions{display:flex;justify-content:flex-end;margin-top:8px;}
.art-share-btn{
  background:none;border:1px solid var(--hair);color:var(--m2);
  padding:4px 6px;cursor:pointer;border-radius:2px;
  display:inline-flex;align-items:center;
  transition:background .15s,color .15s,border-color .15s;
}
.art-share-btn:hover{background:var(--ink);color:var(--paper);border-color:var(--ink);}

/* ── Responsive ── */
@media(max-width:680px){
  .sheet{padding:20px 18px 28px;}
  .mast-title-text{font-size:44px;}
  .briefing-body{column-count:1;}
  .fx-panel{flex-direction:column;align-items:flex-start;gap:8px;}
  .desk{padding:16px 8px 32px;}
}
</style>
</head>
<body>

<svg aria-hidden="true" width="0" height="0" style="position:absolute;width:0;height:0;overflow:hidden;">
  <filter id="dither" color-interpolation-filters="sRGB" x="0" y="0" width="100%" height="100%">
    <feColorMatrix type="matrix" values="0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0 0 0 1 0" result="g"/>
    <feComponentTransfer in="g" result="c">
      <feFuncR type="linear" slope="1.5" intercept="-0.24"/>
      <feFuncG type="linear" slope="1.5" intercept="-0.24"/>
      <feFuncB type="linear" slope="1.5" intercept="-0.24"/>
    </feComponentTransfer>
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="11" stitchTiles="stitch" result="t"/>
    <feColorMatrix in="t" type="matrix" values="1 0 0 0 0  1 0 0 0 0  1 0 0 0 0  0 0 0 0 1" result="n"/>
    <feComposite in="c" in2="n" operator="arithmetic" k1="0" k2="1" k3="1" k4="-0.5" result="s"/>
    <feComponentTransfer in="s" result="bw">
      <feFuncR type="discrete" tableValues="0 1"/>
      <feFuncG type="discrete" tableValues="0 1"/>
      <feFuncB type="discrete" tableValues="0 1"/>
    </feComponentTransfer>
    <feComponentTransfer in="bw">
      <feFuncR type="linear" slope="0.812" intercept="0.125"/>
      <feFuncG type="linear" slope="0.789" intercept="0.125"/>
      <feFuncB type="linear" slope="0.737" intercept="0.110"/>
    </feComponentTransfer>
  </filter>
  <filter id="ditherBig" color-interpolation-filters="sRGB" x="0" y="0" width="100%" height="100%">
    <feColorMatrix type="matrix" values="0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0 0 0 1 0" result="g"/>
    <feComponentTransfer in="g" result="c">
      <feFuncR type="linear" slope="1.35" intercept="-0.16"/>
      <feFuncG type="linear" slope="1.35" intercept="-0.16"/>
      <feFuncB type="linear" slope="1.35" intercept="-0.16"/>
    </feComponentTransfer>
    <feTurbulence type="fractalNoise" baseFrequency="0.5" numOctaves="2" seed="6" stitchTiles="stitch" result="t"/>
    <feColorMatrix in="t" type="matrix" values="1 0 0 0 0  1 0 0 0 0  1 0 0 0 0  0 0 0 0 1" result="n"/>
    <feComposite in="c" in2="n" operator="arithmetic" k1="0" k2="1" k3="1" k4="-0.5" result="s"/>
    <feComponentTransfer in="s" result="bw">
      <feFuncR type="discrete" tableValues="0 1"/>
      <feFuncG type="discrete" tableValues="0 1"/>
      <feFuncB type="discrete" tableValues="0 1"/>
    </feComponentTransfer>
    <feComponentTransfer in="bw">
      <feFuncR type="linear" slope="0.812" intercept="0.125"/>
      <feFuncG type="linear" slope="0.789" intercept="0.125"/>
      <feFuncB type="linear" slope="0.737" intercept="0.110"/>
    </feComponentTransfer>
  </filter>
</svg>

<div class="desk">
<div class="sheet">

  <!-- MASTHEAD -->
  <div class="mast-vol">
    <span id="j-vol">Vol. CXXVI &middot; No. 168</span>
    <span id="j-digital-daily">Digital Daily</span>
    <div class="lang-toggle">
      <button id="j-lang-en" class="lang-btn active" onclick="setLang('en')">EN</button>
      <button id="j-lang-pt" class="lang-btn" onclick="setLang('pt')">PT</button>
    </div>
  </div>
  <div class="mast-title">
    <span class="mast-rule mast-rule-l"><span class="mast-rule-line"></span><span class="mast-rule-gem">&#9670;</span></span>
    <span class="mast-title-text">The Lighthouse</span>
    <span class="mast-rule mast-rule-r"><span class="mast-rule-gem">&#9670;</span><span class="mast-rule-line"></span></span>
  </div>
  <div class="mast-date">
    <span>Curitiba, Paran&aacute;</span>
    <span class="mast-date-center" id="j-date"></span>
    <span id="j-price-free">Price: Free</span>
  </div>

  <!-- FORECAST STRIP -->
  <div class="forecast">
    <div class="fx-canvas" id="j-fx-canvas"></div>
    <div class="fx-panel">
      <div class="fx-panel-left">
        <span class="fx-kicker" id="j-fx-kicker">The Weather</span>
        <span class="fx-condition" id="j-wx-cond">Overcast Skies</span>
        <span class="fx-strapline" id="j-fx-strapline">Curitiba &amp; the Paran&aacute; highlands</span>
      </div>
      <div class="fx-stats" id="j-wx-stats">
        <span><b>HIGH</b> --&deg;</span><span><b>LOW</b> --&deg;</span><span><b>WIND</b> --</span>
      </div>
    </div>
  </div>

  <!-- SECTION NAV -->
  <div class="section-nav" id="j-nav"></div>
  <div class="dispatch-line" id="j-dispatch"></div>

  <!-- FILTER STRIP -->
  <div class="filter-strip">
    <div class="flt-group">
      <span class="flt-label" id="j-flt-rel-lbl">Min Relevance</span>
      <input type="range" id="j-rel" class="flt-range" min="0" max="100" value="0">
      <span class="flt-val" id="j-rel-val">0%</span>
    </div>
    <div class="flt-div"></div>
    <div class="flt-group">
      <span class="flt-label" id="j-flt-corr-lbl">Min Corroboration</span>
      <input type="range" id="j-corr" class="flt-range" min="1" max="10" value="1">
      <span class="flt-val" id="j-corr-val">1</span>
    </div>
    <div class="flt-div"></div>
    <label class="flt-check-lbl">
      <input type="checkbox" id="j-hide-low" class="flt-check" checked>
      <span id="j-flt-low-lbl">Hide Low-Signal</span>
    </label>
  </div>

  <!-- BRIEFING -->
  <div class="briefing" id="j-briefing" style="display:none;">
    <div class="briefing-label" id="j-briefing-label">Today&#8217;s Briefing</div>
    <p class="briefing-body" id="j-briefing-body"></p>
  </div>

  <!-- STATS -->
  <div class="edition-stats" id="j-stats"></div>

  <!-- ARTICLE LIST -->
  <div id="j-list"></div>

  <!-- EDITION FOOTER -->
  <div class="edition-footer" id="j-end-edition">&sect; End of Edition &sect;</div>

</div><!-- .sheet -->
</div><!-- .desk -->

<div class="gen-footer" id="j-gen-time"></div>
<div class="made-by" id="j-made-by">Made by ricardobertolin</div>

<script>
const DATA = __DATA_JSON__;

// ── i18n ──────────────────────────────────────────────────────────────
const STRINGS = {
  en: {
    digital_daily:      'Digital Daily',
    price_free:         'Price: Free',
    the_weather:        'The Weather',
    curitiba_region:    'Curitiba & the Paraná highlands',
    high: 'HIGH', low: 'LOW', wind: 'WIND',
    min_relevance:      'Min Relevance',
    min_corroboration:  'Min Corroboration',
    hide_low_signal:    'Hide Low-Signal',
    todays_briefing:    'Today’s Briefing',
    end_of_edition:     '§ End of Edition §',
    tab_world:          'Worldwide',
    tab_brazil:         'My Country',
    tab_curitiba:       'My City',
    blurb_world:        'Dispatches from across the world',
    blurb_brazil:       'The national desk, from Brazil',
    blurb_curitiba:     'Local pages, near Curitiba',
    fair_sunny:         'Fair & Sunny',
    partly_cloudy:      'Partly Cloudy',
    overcast:           'Overcast Skies',
    foggy:              'Foggy',
    steady_rain:        'Steady Rain',
    light_snow:         'Light Snow',
    rain_showers:       'Rain Showers',
    thunderstorms:      'Thunderstorms',
    showing:            'Showing',
    of:                 'of',
    dispatches:         'dispatches',
    dispatch:           'dispatch',
    via:                'via',
    relevance:          'Relevance',
    sources:            'sources',
    just_now:           'just now',
    ago_m:              'm ago',
    ago_h:              'h ago',
    ago_d:              'd ago',
    generated:          'Generated',
    made_by:            'Made by ricardobertolin',
    save_img:           'Save image',
  },
  pt: {
    digital_daily:      'Jornal Digital',
    price_free:         'Preço: Gratuito',
    the_weather:        'O Tempo',
    curitiba_region:    'Curitiba & região serrana do Paraná',
    high: 'MÁX', low: 'MÍN', wind: 'VENTO',
    min_relevance:      'Relevância Mínima',
    min_corroboration:  'Corroboração Mínima',
    hide_low_signal:    'Ocultar Baixo Sinal',
    todays_briefing:    'Resumo do Dia',
    end_of_edition:     '§ Fim da Edição §',
    tab_world:          'Mundial',
    tab_brazil:         'Meu País',
    tab_curitiba:       'Minha Cidade',
    blurb_world:        'Despachos de todo o mundo',
    blurb_brazil:       'A editoria nacional, do Brasil',
    blurb_curitiba:     'Páginas locais, próximo a Curitiba',
    fair_sunny:         'Sol & Céu Aberto',
    partly_cloudy:      'Parcialmente Nublado',
    overcast:           'Céu Encoberto',
    foggy:              'Neblina',
    steady_rain:        'Chuva Constante',
    light_snow:         'Neve Leve',
    rain_showers:       'Pancadas de Chuva',
    thunderstorms:      'Tempestade',
    showing:            'Exibindo',
    of:                 'de',
    dispatches:         'despachos',
    dispatch:           'despacho',
    via:                'via',
    relevance:          'Relevância',
    sources:            'fontes',
    just_now:           'agora mesmo',
    ago_m:              'min atrás',
    ago_h:              'h atrás',
    ago_d:              'd atrás',
    generated:          'Gerado em',
    made_by:            'Feito por ricardobertolin',
    save_img:           'Salvar imagem',
  }
};
let lang = 'en';
function t(key) { return (STRINGS[lang] && STRINGS[lang][key]) || STRINGS['en'][key] || key; }

// ── Helpers ──────────────────────────────────────────────────────────
function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function timeAgo(iso) {
  if (!iso) return '';
  const d = new Date(iso), now = new Date(), ms = now - d;
  if (isNaN(ms)) return '';
  const m = Math.floor(ms / 60000);
  if (m < 2)  return t('just_now');
  if (m < 60) return m + t('ago_m');
  const h = Math.floor(m / 60);
  if (h < 24) return h + t('ago_h');
  const days = Math.floor(h / 24);
  if (days < 7) return days + t('ago_d');
  return d.toLocaleDateString();
}

function fmtDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso + 'T12:00:00');
    const loc = lang === 'pt' ? 'pt-BR' : 'en-US';
    return d.toLocaleDateString(loc, { weekday:'long', year:'numeric', month:'long', day:'numeric' });
  } catch(_) { return iso; }
}

function dayOfYear(iso) {
  if (!iso) return 1;
  const d = new Date(iso + 'T12:00:00');
  return Math.floor((d - new Date(d.getFullYear(), 0, 0)) / 86400000);
}

function toRoman(n) {
  const v=[1000,900,500,400,100,90,50,40,10,9,5,4,1];
  const s=['M','CM','D','CD','C','XC','L','XL','X','IX','V','IV','I'];
  let r='';
  for(let i=0;i<v.length;i++) while(n>=v[i]){r+=s[i];n-=v[i];}
  return r;
}

function wxLabel(code) {
  if (code===0||code===1) return t('fair_sunny');
  if (code===2)           return t('partly_cloudy');
  if (code===3)           return t('overcast');
  if (code<=48)           return t('foggy');
  if (code<=67)           return t('steady_rain');
  if (code<=77)           return t('light_snow');
  if (code<=82)           return t('rain_showers');
  if (code>=95)           return t('thunderstorms');
  return t('overcast');
}

function imgError(img) {
  img.onerror = null;
  img.src = 'the_lighthouse2.png';
}

// ── State ────────────────────────────────────────────────────────────
const TABS = [
  { id: 'world',    lk: 'tab_world',    bk: 'blurb_world' },
  { id: 'brazil',   lk: 'tab_brazil',   bk: 'blurb_brazil' },
  { id: 'curitiba', lk: 'tab_curitiba', bk: 'blurb_curitiba' }
];
let activeTab = 'world';
let minRel = 0, minCorr = 1, hideLow = true;

// ── Language switch ───────────────────────────────────────────────────
function setLang(l) {
  lang = l;
  document.getElementById('j-lang-en').classList.toggle('active', l === 'en');
  document.getElementById('j-lang-pt').classList.toggle('active', l === 'pt');
  updateStaticLabels();
  renderMasthead();
  renderWeather();
  renderNav();
  renderBriefing();
  renderArticles();
  applyFilters();
  updateGenFooter();
}

function updateStaticLabels() {
  document.getElementById('j-digital-daily').textContent    = t('digital_daily');
  document.getElementById('j-price-free').textContent       = t('price_free');
  document.getElementById('j-fx-kicker').textContent        = t('the_weather');
  document.getElementById('j-fx-strapline').textContent     = t('curitiba_region');
  document.getElementById('j-flt-rel-lbl').textContent      = t('min_relevance');
  document.getElementById('j-flt-corr-lbl').textContent     = t('min_corroboration');
  document.getElementById('j-flt-low-lbl').textContent      = t('hide_low_signal');
  document.getElementById('j-briefing-label').textContent   = t('todays_briefing');
  document.getElementById('j-end-edition').textContent      = t('end_of_edition');
  document.getElementById('j-made-by').textContent          = t('made_by');
}

// ── Masthead ─────────────────────────────────────────────────────────
function renderMasthead() {
  const iso = DATA.date || new Date().toISOString().slice(0,10);
  const year = new Date(iso + 'T12:00:00').getFullYear();
  const vol  = toRoman(year - 1900);
  const doy  = dayOfYear(iso);
  document.getElementById('j-vol').textContent  = 'Vol. ' + vol + ' · No. ' + doy;
  document.getElementById('j-date').textContent = fmtDate(iso);
}

// ── Weather scene builders ────────────────────────────────────────────
function wxImageFor(type) {
  if (type === 'Sunny')                         return '01_sunny.png';
  if (type === 'Thunderstorm' || type === 'Rainy') return '03_storm.png';
  return '02_cloudy.png';
}

function buildScene(type) {
  const imgSrc = wxImageFor(type);
  const img = '<img src="' + imgSrc + '" alt="">';

  let overlay = '';

  if (type === 'Foggy') {
    overlay =
      '<div style="position:absolute;left:-5%;top:18%;width:110%;height:14%;background:rgba(195,195,195,.68);border-radius:6px;"></div>' +
      '<div style="position:absolute;left:-5%;top:38%;width:110%;height:11%;background:rgba(210,210,210,.58);border-radius:5px;"></div>' +
      '<div style="position:absolute;left:-5%;top:56%;width:110%;height:9%;background:rgba(222,222,222,.48);border-radius:4px;"></div>';

  } else if (type === 'Snow') {
    const ps = [3,11,20,28,37,46,54,63,71,80,88,95];
    const ds = [0,.4,.7,.15,.55,.9,.25,.65,.3,.75,.1,.5];
    const sz = [5,4,6,5,4,5,6,4,5,4,6,5];
    ps.forEach((p,i) => {
      overlay += '<div class="fx-snow-dot" style="left:' + p + '%;top:-12px;width:' + sz[i] + 'px;height:' + sz[i] + 'px;animation-delay:' + ds[i] + 's;animation-duration:' + (1.2 + ds[i]*0.4) + 's;"></div>';
    });

  } else if (type === 'Rainy' || type === 'Thunderstorm') {
    const ps  = [2,10,18,27,35,43,51,59,67,76,84,93];
    const ds  = [0,.28,.62,.08,.45,.82,.18,.55,.35,.72,.1,.48];
    const hs  = [18,22,16,20,24,18,22,16,20,22,18,20];
    const drs = [.72,.88,.65,.8,.7,.84,.68,.76,.9,.62,.78,.7];
    ps.forEach((p,i) => {
      overlay += '<div class="fx-rain-streak" style="left:' + p + '%;top:-26px;height:' + hs[i] + 'px;animation-delay:' + ds[i] + 's;animation-duration:' + drs[i] + 's;"></div>';
    });
    if (type === 'Thunderstorm') {
      overlay += '<div class="fx-lightning-flash"></div>';
    }
  }

  return img + overlay;
}

function wxSceneType(code, precip) {
  if (code === 0 || code === 1) return 'Sunny';
  if (code >= 95) return 'Thunderstorm';
  if (code >= 71 && code <= 77) return 'Snow';
  if (code >= 51 || precip > 0) return 'Rainy';
  if (code >= 45) return 'Foggy';
  return 'Overcast';
}

// ── Weather ──────────────────────────────────────────────────────────
function renderWeather() {
  const w = DATA.weather || {};
  const code   = w.wmo_code != null ? w.wmo_code : 3;
  const precip = w.precipitation_mm || 0;
  const type   = wxSceneType(code, precip);

  const canvas = document.getElementById('j-fx-canvas');
  canvas.innerHTML = buildScene(type);

  document.getElementById('j-wx-cond').textContent = wxLabel(code);

  const hi   = w.temp_max  != null ? w.temp_max  + '°' : '--';
  const lo   = w.temp_min  != null ? w.temp_min  + '°' : '--';
  const wind = w.wind_max_kmh      ? '≤' + Math.round(w.wind_max_kmh) + 'km/h' : '--';
  document.getElementById('j-wx-stats').innerHTML =
    '<span><b>' + t('high') + '</b> ' + esc(hi)   + '</span>' +
    '<span><b>' + t('low')  + '</b> ' + esc(lo)   + '</span>' +
    '<span><b>' + t('wind') + '</b> ' + esc(wind) + '</span>';
}

// ── Nav ──────────────────────────────────────────────────────────────
function tabVisible(region) {
  if (activeTab === 'world')    return true;
  if (activeTab === 'brazil')   return region === 'brazil' || region === 'curitiba';
  if (activeTab === 'curitiba') return region === 'curitiba';
  return true;
}

function renderNav() {
  const nav = document.getElementById('j-nav');
  let html  = '';
  TABS.forEach((tb, i) => {
    if (i > 0) html += '<span class="nav-divider"></span>';
    const active = activeTab === tb.id ? ' active' : '';
    html += '<button class="nav-btn' + active + '" data-tab="' + tb.id + '">' + t(tb.lk) + '</button>';
  });
  nav.innerHTML = html;
  nav.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      activeTab = btn.dataset.tab;
      renderNav();
      applyFilters();
    });
  });
}

function updateDispatch() {
  const visible = DATA.articles.filter(a => {
    if (!tabVisible(a.region || 'world')) return false;
    if (Math.round((a.relevance_score || 0) * 100) < minRel) return false;
    if ((a.corroboration || 1) < minCorr) return false;
    if (hideLow && a.low_signal) return false;
    return true;
  }).length;
  const tab = TABS.find(tb => tb.id === activeTab) || TABS[0];
  document.getElementById('j-dispatch').textContent =
    t(tab.bk) + ' — ' + visible + ' ' + (visible === 1 ? t('dispatch') : t('dispatches'));
}

// ── Briefing ─────────────────────────────────────────────────────────
function renderBriefing() {
  const intro = (lang === 'pt' ? DATA.intro_pt : DATA.intro_en) || DATA.intro || '';
  if (!intro) { document.getElementById('j-briefing').style.display = 'none'; return; }
  document.getElementById('j-briefing').style.display = '';
  const first = intro.charAt(0);
  const rest  = esc(intro.slice(1));
  document.getElementById('j-briefing-body').innerHTML =
    '<span class="drop-cap">' + esc(first) + '</span>' + rest;
}

// ── Articles ─────────────────────────────────────────────────────────
function renderArticles() {
  let html = '';
  DATA.articles.forEach((art, i) => {
    const relPct = Math.round((art.relevance_score || 0) * 100);
    const corr   = art.corroboration || 1;
    const cat    = art.category || 'Other';
    const origin = art.origin === 'feed' ? 'RSS' : 'Search';
    const age    = timeAgo(art.published_at);
    const low    = art.low_signal ? 'true' : 'false';
    const headline = lang === 'pt'
      ? (art.headline_pt || art.title)
      : (art.headline_en || art.title);
    const liner  = lang === 'pt'
      ? (art.one_liner_pt || art.one_liner_en || art.one_liner || art.title)
      : (art.one_liner_en || art.one_liner || art.title);

    const thumb = '<img class="art-thumb" src="' + esc(art.image_url || 'the_lighthouse2.png') + '" alt="" loading="lazy" onerror="imgError(this)">';

    const note = art.rationale
      ? '<div class="art-note">' + esc(art.rationale) + '</div>' : '';

    const corrMeta = corr > 1
      ? '<span class="meta-div"></span><span>' + corr + ' ' + t('sources') + '</span>' : '';

    const region = art.region || 'world';
    html +=
      '<div class="art-row' + (art.low_signal ? ' low-sig' : '') + '"' +
      ' data-region="' + esc(region) + '" data-rel="' + relPct + '" data-corr="' + corr + '" data-low="' + low + '">' +
      '<div class="art-thumb-col">' +
        '<div class="art-thumb-frame">' + thumb + '</div>' +
        '<div class="art-source-cap">' + esc(art.source_domain || '') + '</div>' +
      '</div>' +
      '<div class="art-content-col">' +
        '<div class="art-kicker-row">' +
          '<span>' + esc(cat) + '</span>' +
          '<span class="art-rank-no">No.&nbsp;' + (i + 1) + '</span>' +
        '</div>' +
        '<a class="art-headline" href="' + esc(art.url) + '" target="_blank" rel="noopener noreferrer"' +
          ' onclick="trackClick(' + JSON.stringify(art.url) + ',' + JSON.stringify(art.source_domain) + ')">' +
          esc(headline) +
        '</a>' +
        '<div class="art-deck">' + esc(liner) + '</div>' +
        note +
        '<div class="art-meta">' +
          '<span>' + t('via') + ' ' + esc(origin) + '</span>' +
          '<span class="meta-div"></span>' +
          '<span class="rel-wrap">' + t('relevance') + ' ' +
            '<span class="rel-bg"><span class="rel-fill" style="width:' + relPct + '%"></span></span>' +
            relPct + '%' +
          '</span>' +
          corrMeta +
          '<span class="meta-div"></span>' +
          '<span>' + esc(age) + '</span>' +
        '</div>' +
        '<div class="art-actions">' +
          '<button class="art-share-btn" onclick="shareCard(event,' + i + ')" title="' + t('save_img') + '">' +
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
          '</button>' +
        '</div>' +
      '</div>' +
      '</div>';
  });
  document.getElementById('j-list').innerHTML = html;
}

// ── Filters ──────────────────────────────────────────────────────────
function applyFilters() {
  let visible = 0;
  document.querySelectorAll('.art-row').forEach(row => {
    const ok =
      tabVisible(row.dataset.region) &&
      parseInt(row.dataset.rel)  >= minRel &&
      parseInt(row.dataset.corr) >= minCorr &&
      (!hideLow || row.dataset.low !== 'true');
    row.classList.toggle('hidden', !ok);
    if (ok) visible++;
  });
  document.getElementById('j-stats').textContent =
    t('showing') + ' ' + visible + ' ' + t('of') + ' ' + DATA.articles.length + ' ' + t('dispatches');
  updateDispatch();
}

// ── Share as image ───────────────────────────────────────────────────
function wrapText(ctx, text, maxW) {
  const words = (text || '').split(' ');
  const lines = [];
  let cur = '';
  for (const w of words) {
    const test = cur ? cur + ' ' + w : w;
    if (ctx.measureText(test).width > maxW && cur) { lines.push(cur); cur = w; }
    else cur = test;
  }
  if (cur) lines.push(cur);
  return lines;
}

function _drawCard(ctx, W, H, headline, liner, cat, src, artImg) {
  const SPLIT = artImg ? 510 : W;
  const textW  = SPLIT - 48;

  // paper background
  ctx.fillStyle = '#efe9d8';
  ctx.fillRect(0, 0, W, H);

  // article image — right column, clipped
  if (artImg) {
    const iX = SPLIT, iY = 54, iW = W - SPLIT, iH = H - 54 - 38;
    const scale = Math.max(iW / artImg.width, iH / artImg.height);
    const sw = iW / scale, sh = iH / scale;
    const sx = (artImg.width - sw) / 2, sy = (artImg.height - sh) / 2;
    ctx.save();
    ctx.beginPath(); ctx.rect(iX, iY, iW, iH); ctx.clip();
    ctx.drawImage(artImg, sx, sy, sw, sh, iX, iY, iW, iH);
    ctx.restore();
    // column separator
    ctx.fillStyle = 'rgba(32,32,28,.18)';
    ctx.fillRect(SPLIT, 54, 1, H - 54 - 38);
  }

  // border
  ctx.strokeStyle = '#20201c';
  ctx.lineWidth = 2;
  ctx.strokeRect(1, 1, W - 2, H - 2);

  // top bar
  ctx.fillStyle = '#20201c';
  ctx.fillRect(0, 0, W, 54);

  // brand
  ctx.fillStyle = '#efe9d8';
  ctx.font = 'bold 18px Georgia, serif';
  ctx.textAlign = 'left';
  ctx.fillText('THE LIGHTHOUSE', 24, 35);

  // source
  ctx.font = '12px Georgia, serif';
  ctx.textAlign = 'right';
  ctx.fillText(src, W - 24, 35);
  ctx.textAlign = 'left';

  // category pill
  ctx.fillStyle = '#20201c';
  ctx.font = 'bold 11px Arial, sans-serif';
  var catW = ctx.measureText(cat).width + 20;
  ctx.fillRect(24, 72, catW, 22);
  ctx.fillStyle = '#efe9d8';
  ctx.fillText(cat, 34, 87);

  // headline
  ctx.fillStyle = '#20201c';
  ctx.font = 'bold 26px Georgia, serif';
  var headLines = wrapText(ctx, headline, textW);
  var y = 124;
  headLines.slice(0, 4).forEach(function(line) { ctx.fillText(line, 24, y); y += 34; });

  // divider
  y += 6;
  ctx.fillStyle = '#c4bda6';
  ctx.fillRect(24, y, textW, 1);
  y += 16;

  // one-liner
  ctx.fillStyle = '#3a382f';
  ctx.font = '15px Georgia, serif';
  var linerLines = wrapText(ctx, liner, textW);
  linerLines.slice(0, 3).forEach(function(line) { ctx.fillText(line, 24, y); y += 23; });

  // footer bar
  ctx.fillStyle = '#20201c';
  ctx.fillRect(0, H - 38, W, 38);
  ctx.fillStyle = '#efe9d8';
  ctx.font = '12px Arial, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText(DATA.date, 24, H - 14);
  ctx.textAlign = 'right';
  ctx.fillText('ricardobertolin.github.io/the_lighthouse_app', W - 24, H - 14);
  ctx.textAlign = 'left';
}

function shareCard(evt, idx) {
  var btn = evt ? evt.currentTarget : null;
  var art = DATA.articles[idx];
  var ispt = lang === 'pt';
  var headline = ispt ? (art.headline_pt || art.title) : (art.headline_en || art.title);
  var liner    = ispt ? (art.one_liner_pt || art.one_liner_en || '') : (art.one_liner_en || '');
  var cat      = (art.category || 'News').toUpperCase();
  var src      = art.source_domain || '';
  var W = 800, H = 440;

  function dispatch(cv) {
    var filename = 'lighthouse-' + (idx + 1) + '.png';
    cv.toBlob(function(blob) {
      var file = new File([blob], filename, { type: 'image/png' });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        navigator.share({ files: [file] }).catch(function() { _copyBlob(blob, btn); });
      } else {
        _copyBlob(blob, btn);
      }
    }, 'image/png');
  }

  function makeCanvas() {
    var cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    return cv;
  }

  if (art.image_url) {
    var img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function() {
      var cv = makeCanvas();
      _drawCard(cv.getContext('2d'), W, H, headline, liner, cat, src, img);
      try {
        dispatch(cv);
      } catch(e) {
        // canvas tainted by CORS — retry without image
        var cv2 = makeCanvas();
        _drawCard(cv2.getContext('2d'), W, H, headline, liner, cat, src, null);
        dispatch(cv2);
      }
    };
    img.onerror = function() {
      var cv = makeCanvas();
      _drawCard(cv.getContext('2d'), W, H, headline, liner, cat, src, null);
      dispatch(cv);
    };
    img.src = art.image_url;
  } else {
    var cv = makeCanvas();
    _drawCard(cv.getContext('2d'), W, H, headline, liner, cat, src, null);
    dispatch(cv);
  }
}

function _copyBlob(blob, btn) {
  if (navigator.clipboard && navigator.clipboard.write) {
    navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      .then(function() { _flashBtn(btn); })
      .catch(function() { _dlBlob(blob, 'lighthouse.png'); });
  } else {
    _dlBlob(blob, 'lighthouse.png');
  }
}

function _dlBlob(blob, name) {
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(function() { URL.revokeObjectURL(a.href); }, 1000);
}

function _flashBtn(btn) {
  if (!btn) return;
  var el = btn.closest ? (btn.closest('.art-share-btn') || btn) : btn;
  el.style.background = 'var(--ink)';
  el.style.color = 'var(--paper)';
  setTimeout(function() { el.style.background = ''; el.style.color = ''; }, 900);
}

// ── Click tracking ────────────────────────────────────────────────────
function trackClick(url, domain) {
  try {
    const key = 'tl_clicks';
    const clicks = JSON.parse(localStorage.getItem(key) || '[]');
    clicks.push({ url, domain, ts: new Date().toISOString() });
    if (clicks.length > 500) clicks.splice(0, clicks.length - 500);
    localStorage.setItem(key, JSON.stringify(clicks));
  } catch(_) {}
}

// ── Gen footer ───────────────────────────────────────────────────────
function updateGenFooter() {
  const genAt = DATA.generated_at ? new Date(DATA.generated_at).toLocaleString() : '';
  document.getElementById('j-gen-time').textContent =
    genAt ? t('generated') + ' ' + genAt + ' — The Lighthouse' : 'The Lighthouse';
}

// ── Init ─────────────────────────────────────────────────────────────
function init() {
  const maxCorr = Math.max(...DATA.articles.map(a => a.corroboration || 1), 1);
  document.getElementById('j-corr').max = maxCorr;

  renderMasthead();
  renderWeather();
  renderNav();
  renderBriefing();
  renderArticles();
  applyFilters();
  updateGenFooter();

  document.getElementById('j-rel').addEventListener('input', function() {
    minRel = parseInt(this.value);
    document.getElementById('j-rel-val').textContent = minRel + '%';
    applyFilters();
  });
  document.getElementById('j-corr').addEventListener('input', function() {
    minCorr = parseInt(this.value);
    document.getElementById('j-corr-val').textContent = minCorr;
    applyFilters();
  });
  document.getElementById('j-hide-low').addEventListener('change', function() {
    hideLow = this.checked;
    applyFilters();
  });
}

init();
</script>
<script>
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js');
}
</script>
</body>
</html>
"""


def render(
    articles: list[dict],
    synthesis: dict,
    weather: dict,
    output_path: Path = OUTPUT_PATH,
) -> Path:
    today = date.today().isoformat()

    syn_by_idx = {a["index"]: a for a in synthesis.get("articles", [])}
    enriched: list[dict] = []
    for i, art in enumerate(articles):
        syn = syn_by_idx.get(i, {})
        enriched.append(
            {
                **art,
                "headline_en": syn.get("headline_en", art.get("title", "")),
                "headline_pt": syn.get("headline_pt", art.get("title", "")),
                "one_liner_en": syn.get("one_liner_en", syn.get("one_liner", art.get("title", ""))),
                "one_liner_pt": syn.get("one_liner_pt", syn.get("one_liner_en", art.get("title", ""))),
                "category": syn.get("category", "Other"),
                "region": syn.get("region", "world"),
                "rationale": syn.get("rationale", ""),
                "low_signal": bool(syn.get("low_signal", False)),
            }
        )

    page_data = {
        "date": today,
        "intro_en": synthesis.get("intro_en", synthesis.get("intro", "")),
        "intro_pt": synthesis.get("intro_pt", ""),
        "weather": weather,
        "articles": enriched,
        "generated_at": datetime.now().isoformat(),
    }

    data_json = json.dumps(page_data, ensure_ascii=False)
    data_json = data_json.replace("</", "<\\/")

    html = _HTML.replace("__DATA_JSON__", data_json)
    output_path.write_text(html, encoding="utf-8")
    return output_path


_BROWSER_CANDIDATES: dict[str, list[str]] = {
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        "/Applications/Firefox.app/Contents/MacOS/firefox",
        "/usr/bin/firefox",
    ],
}


def open_browser(path: Path, browser: str = "default") -> None:
    url = path.as_uri()
    name = browser.strip().lower()

    if name == "default":
        webbrowser.open(url)
        return

    if name not in _BROWSER_CANDIDATES:
        try:
            webbrowser.register("custom", None, webbrowser.BackgroundBrowser(browser))
            webbrowser.get("custom").open(url)
        except Exception:
            webbrowser.open(url)
        return

    for exe in _BROWSER_CANDIDATES[name]:
        if Path(exe).exists():
            try:
                webbrowser.register(name, None, webbrowser.BackgroundBrowser(exe))
                webbrowser.get(name).open(url)
                return
            except Exception:
                break

    try:
        webbrowser.get(name).open(url)
    except Exception:
        webbrowser.open(url)
