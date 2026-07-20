'use strict';

// Static watchlist — mirrors config.py WATCHLIST
const WATCHLIST = [
  "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "AMD", "GOOGL",
  "NFLX", "COIN", "PLTR", "SOFI", "MARA", "RIOT", "SPY", "QQQ",
  "TQQQ", "SQQQ", "SNAP", "UBER", "HOOD", "BABA", "MU", "INTC",
];

// ─── State ────────────────────────────────────────────────────
let stocksData = [];          // latest screener results
let activeSymbol = null;
let chart = null;
let candleSeries = null;
let ema9Series = null;
let ema21Series = null;
let vwapSeries = null;
let volSeries = null;
let wsRetryDelay = 1000;
let knownSignalKeys = new Set();
let fetchingSymbol = null;    // prevent duplicate on-demand fetches

// ─── WebSocket ────────────────────────────────────────────────
function connectWs() {
  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${wsProto}//${location.host}/ws`);
  ws.onopen = () => { setWsStatus(true); wsRetryDelay = 1000; };
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === 'update') handleUpdate(msg.data);
  };
  ws.onclose = ws.onerror = () => {
    setWsStatus(false);
    setTimeout(connectWs, wsRetryDelay);
    wsRetryDelay = Math.min(wsRetryDelay * 2, 30000);
  };
}

function setWsStatus(connected) {
  const dot = document.getElementById('ws-dot');
  const txt = document.getElementById('ws-text');
  dot.className = `w-2 h-2 rounded-full inline-block ${connected ? 'bg-green-500' : 'bg-red-500'}`;
  txt.textContent = connected ? 'Live' : 'מתחבר...';
  txt.className = connected ? 'text-green-400' : 'text-yellow-400';
}

// ─── Data Handler ─────────────────────────────────────────────
function handleUpdate(data) {
  stocksData = data.stocks || [];
  const allSignals = data.signals || [];

  document.getElementById('last-scan').textContent = data.last_scan || '--';
  document.getElementById('signal-count').textContent = allSignals.length;
  document.getElementById('stock-count').textContent = stocksData.length;

  const badge = document.getElementById('market-badge');
  if (data.market_open) {
    badge.className = 'px-2 py-0.5 rounded text-xs font-bold bg-green-900 text-green-400';
    badge.textContent = '● MARKET OPEN';
  } else {
    badge.className = 'px-2 py-0.5 rounded text-xs font-bold bg-gray-700 text-gray-400';
    badge.textContent = '○ MARKET CLOSED';
  }

  renderWatchlist();
  renderSignals(allSignals);

  // Refresh chart for active stock if screener has fresh data
  if (activeSymbol) {
    const stock = stocksData.find(s => s.symbol === activeSymbol);
    if (stock) loadChart(stock);
  }

  updateRiskCalc();
}

// ─── Watchlist — always shows ALL 24 symbols ──────────────────
function renderWatchlist() {
  const el = document.getElementById('watchlist');
  const stockMap = new Map(stocksData.map(s => [s.symbol, s]));

  el.innerHTML = WATCHLIST.map(symbol => {
    const s = stockMap.get(symbol);
    const activeClass = symbol === activeSymbol ? 'active' : '';

    if (!s) {
      // No screener data yet — show placeholder, still clickable
      return `
        <div class="wl-item ${activeClass}" onclick="selectSymbol('${symbol}')">
          <div>
            <span class="wl-symbol">${symbol}</span>
            <div class="wl-rsi text-gray-700">טוען...</div>
          </div>
          <div class="text-right">
            <div class="wl-price" style="color:#374151">--</div>
            <div class="wl-change" style="color:#374151">--</div>
          </div>
        </div>`;
    }

    const hasBuy  = s.signals.some(sig => sig.signal_type === 'BUY');
    const hasSell = s.signals.some(sig => sig.signal_type === 'SELL');
    const sigClass  = hasBuy ? 'has-signal buy' : hasSell ? 'has-signal sell' : '';
    const chClass   = s.change_pct >= 0 ? 'up' : 'down';
    const chSign    = s.change_pct >= 0 ? '+' : '';
    const rsiClass  = s.rsi > 70 ? 'rsi-hot' : s.rsi < 30 ? 'rsi-cold' : 'rsi-warm';
    const sigDot    = s.signals.length > 0
      ? `<span style="font-size:9px;color:${hasBuy ? '#10b981' : '#ef4444'}">●</span>` : '';

    return `
      <div class="wl-item ${sigClass} ${activeClass}" onclick="selectSymbol('${symbol}')">
        <div>
          <div style="display:flex;align-items:center;gap:3px">
            <span class="wl-symbol">${symbol}</span>${sigDot}
          </div>
          <div class="wl-rsi ${rsiClass}">RSI ${s.rsi} · ${s.rvol}x vol</div>
        </div>
        <div class="text-right">
          <div class="wl-price">$${s.price}</div>
          <div class="wl-change ${chClass}">${chSign}${s.change_pct.toFixed(1)}%</div>
        </div>
      </div>`;
  }).join('');
}

// ─── Select symbol — fetch on-demand if not in screener cache ──
async function selectSymbol(symbol) {
  activeSymbol = symbol;
  renderWatchlist();  // Update active highlight immediately

  const stock = stocksData.find(s => s.symbol === symbol);
  if (stock) {
    loadChart(stock);
    return;
  }

  // On-demand fetch for stocks not yet in screener results
  if (fetchingSymbol === symbol) return;
  fetchingSymbol = symbol;

  setChartLoading(symbol);
  try {
    const resp = await fetch(`/api/stock/${symbol}`);
    if (resp.ok && activeSymbol === symbol) {
      const data = await resp.json();
      if (!data.error) loadChart(data);
    }
  } catch (_) {}
  fetchingSymbol = null;
}

function setChartLoading(symbol) {
  document.getElementById('chart-symbol').textContent = symbol;
  document.getElementById('chart-price').textContent = 'טוען...';
  document.getElementById('chart-change').textContent = '';
  document.getElementById('c-rsi').textContent = '--';
  document.getElementById('c-rvol').textContent = '--';
  document.getElementById('c-atr').textContent = '--';
  document.getElementById('c-vwap').textContent = '--';
}

// ─── Signals Panel ────────────────────────────────────────────
const STRATEGY_LABELS = {
  EMA_CROSS:    'EMA Cross 9/21',
  VWAP_BREAK:   'VWAP Breakout',
  ORB:          'Opening Range Breakout',
  RSI_REVERSAL: 'RSI Reversal',
  MACD_CROSS:   'MACD Crossover',
  BB_BREAK:     'Bollinger Band Breakout',
};

function renderSignals(signals) {
  const el = document.getElementById('signals-panel');
  const timeEl = document.getElementById('signals-time');

  if (!signals.length) {
    el.innerHTML = '<div class="text-gray-600 text-xs text-center py-8">ממתין לסיגנלים...</div>';
    timeEl.textContent = '--';
    return;
  }

  timeEl.textContent = new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' });

  el.innerHTML = signals.map(sig => {
    const isNew = !knownSignalKeys.has(sigKey(sig));
    const cls   = sig.signal_type === 'BUY' ? 'buy' : 'sell';
    const emoji = sig.signal_type === 'BUY' ? '🟢' : '🔴';
    const label = sig.signal_type === 'BUY' ? 'קנייה' : 'מכירה';
    const strat = STRATEGY_LABELS[sig.strategy] || sig.strategy;
    const ts    = sig.timestamp.slice(11, 16);

    return `
      <div class="signal-card ${cls} ${isNew ? 'new' : ''}" onclick="selectSymbol('${sig.symbol}')">
        <div class="signal-header">
          <span class="signal-symbol">${emoji} ${sig.symbol}</span>
          <span class="signal-badge ${cls}">${label}</span>
        </div>
        <div class="signal-strategy">${strat}</div>
        <div class="signal-row entry"><span>כניסה</span><span>$${sig.entry_price}</span></div>
        <div class="signal-row stop"><span>Stop Loss</span><span>$${sig.stop_loss}</span></div>
        <div class="signal-row t1"><span>יעד 1 (2R)</span><span>$${sig.target_1}</span></div>
        <div class="signal-row t2"><span>יעד 2 (3R)</span><span>$${sig.target_2}</span></div>
        <div class="signal-row rr"><span>יחס רווח:סיכון</span><span>1:${sig.risk_reward}</span></div>
        <div class="signal-meta">
          <span>RSI ${sig.rsi} · RVOL ${sig.rvol}x</span>
          <span>${sig.position_size} מניות · ${ts}</span>
        </div>
      </div>`;
  }).join('');

  setTimeout(() => signals.forEach(sig => knownSignalKeys.add(sigKey(sig))), 200);
}

function sigKey(sig) {
  return `${sig.symbol}_${sig.strategy}_${sig.timestamp.slice(0, 13)}`;
}

// ─── Chart ────────────────────────────────────────────────────
function initChart() {
  const wrap = document.getElementById('tv-chart');
  chart = LightweightCharts.createChart(wrap, {
    autoSize: true,   // fills parent automatically, handles resize
    layout: { background: { color: '#0a0e1a' }, textColor: '#9ca3af' },
    grid: { vertLines: { color: '#1a2235' }, horzLines: { color: '#1a2235' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#1f2937' },
    timeScale: { borderColor: '#1f2937', timeVisible: true, secondsVisible: false },
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: '#10b981', downColor: '#ef4444',
    borderUpColor: '#10b981', borderDownColor: '#ef4444',
    wickUpColor: '#10b981', wickDownColor: '#ef4444',
  });

  ema9Series = chart.addLineSeries({
    color: '#60a5fa', lineWidth: 1,
    priceLineVisible: false, lastValueVisible: false,
  });

  ema21Series = chart.addLineSeries({
    color: '#a78bfa', lineWidth: 1,
    priceLineVisible: false, lastValueVisible: false,
  });

  vwapSeries = chart.addLineSeries({
    color: '#fbbf24', lineWidth: 1, lineStyle: 1,
    priceLineVisible: false, lastValueVisible: true,
  });

  volSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'vol',
    lastValueVisible: false, priceLineVisible: false,
  });
  chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
}

function loadChart(stock) {
  const empty = document.getElementById('chart-empty');

  // Header stats
  document.getElementById('chart-symbol').textContent = stock.symbol;
  document.getElementById('chart-price').textContent = `$${stock.price}`;
  const chEl = document.getElementById('chart-change');
  chEl.textContent = `${stock.change_pct >= 0 ? '+' : ''}${stock.change_pct.toFixed(2)}%`;
  chEl.className = `text-sm font-mono ${stock.change_pct >= 0 ? 'text-green-400' : 'text-red-400'}`;
  const rsiEl = document.getElementById('c-rsi');
  rsiEl.textContent = stock.rsi;
  rsiEl.className = `font-mono ${stock.rsi > 70 ? 'text-red-400' : stock.rsi < 30 ? 'text-blue-400' : 'text-green-400'}`;
  document.getElementById('c-rvol').textContent = stock.rvol;
  document.getElementById('c-atr').textContent = stock.atr;
  document.getElementById('c-vwap').textContent = `$${stock.vwap}`;

  empty.style.display = 'none';

  const chartData = stock.chart_data || [];
  if (!chartData.length) return;

  if (!chart) initChart();

  const candles = [], e9 = [], e21 = [], vwap = [], vols = [];

  chartData.forEach(row => {
    if (row.time == null || row.Close == null) return;
    const t = row.time;
    candles.push({ time: t, open: row.Open, high: row.High, low: row.Low, close: row.Close });
    if (row.EMA_9  != null) e9.push({ time: t, value: row.EMA_9 });
    if (row.EMA_21 != null) e21.push({ time: t, value: row.EMA_21 });
    if (row.VWAP   != null) vwap.push({ time: t, value: row.VWAP });
    if (row.Volume != null) {
      vols.push({ time: t, value: row.Volume, color: row.Close >= row.Open ? '#064e3b' : '#450a0a' });
    }
  });

  try {
    candleSeries.setData(candles);
    ema9Series.setData(e9);
    ema21Series.setData(e21);
    vwapSeries.setData(vwap);
    volSeries.setData(vols);

    // Set bar spacing so candles are visible (min 4px, ideal 8px per bar)
    const barSpacing = Math.max(4, Math.min(12, Math.floor(900 / candles.length)));
    chart.timeScale().applyOptions({ barSpacing });
    chart.timeScale().fitContent();
  } catch (err) {
    console.warn('Chart setData error:', err);
  }

  // Signal markers
  const markers = (stock.signals || []).map(sig => ({
    time: candles[candles.length - 1]?.time,
    position: sig.signal_type === 'BUY' ? 'belowBar' : 'aboveBar',
    color: sig.signal_type === 'BUY' ? '#10b981' : '#ef4444',
    shape: sig.signal_type === 'BUY' ? 'arrowUp' : 'arrowDown',
    text: STRATEGY_LABELS[sig.strategy] || sig.strategy,
    size: 2,
  })).filter(m => m.time != null);

  candleSeries.setMarkers(markers);
}

// ─── Risk Calculator ──────────────────────────────────────────
function updateRiskCalc() {
  const account  = parseFloat(document.getElementById('account-input').value) || 10000;
  const riskPct  = parseFloat(document.getElementById('risk-input').value) || 1;
  document.getElementById('risk-amount').textContent = `$${(account * riskPct / 100).toFixed(0)}`;
  document.getElementById('daily-limit').textContent = `$${(account * 0.05).toFixed(0)}`;
}

document.getElementById('account-input').addEventListener('input', updateRiskCalc);
document.getElementById('risk-input').addEventListener('input', updateRiskCalc);

// ─── Init ─────────────────────────────────────────────────────
updateRiskCalc();
connectWs();
