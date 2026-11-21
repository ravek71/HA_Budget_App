"""The budget panel — a single static HTML page; all data via /api/*."""

PAGE = r"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Budżet domowy</title>
<style>
:root{--bg:#f6f7fb;--card:#fff;--text:#1c1e26;--muted:#6b7280;--line:#e5e7eb;--green:#16a34a;--red:#dc2626;--accent:#4f46e5}
@media (prefers-color-scheme: dark){:root{--bg:#14151a;--card:#1e2027;--text:#e5e7eb;--muted:#9ca3af;--line:#2e313c;--green:#4ade80;--red:#f87171;--accent:#818cf8}}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);font-size:15px}
header{display:flex;align-items:center;gap:6px;padding:10px 14px;background:var(--card);border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:17px;margin:0 14px 0 0;font-weight:650}
.tab{padding:7px 14px;border-radius:8px;border:1px solid transparent;background:none;color:var(--muted);cursor:pointer;font-size:14px}
.tab.active{background:var(--accent);color:#fff}
main{padding:14px;max-width:880px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat .lbl{font-size:12.5px;color:var(--muted)}
.stat .val{font-size:21px;font-weight:650;margin-top:3px}
.val.pos{color:var(--green)}.val.neg{color:var(--red)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
label{font-size:13px;color:var(--muted);display:block;margin-bottom:3px}
input,select,button{font:inherit}
input,select{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--text);width:100%}
input[type=checkbox]{width:auto}
.f{flex:1;min-width:120px}
button{padding:9px 16px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;font-weight:550}
button.ghost{background:none;color:var(--accent);border-color:var(--line)}
button.danger{background:none;color:var(--red);border-color:var(--line)}
.small{font-size:12.5px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}
td.num,th.num{text-align:right}
.bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden;min-width:80px;flex:1}
.bar i{display:block;height:100%;background:var(--green)}
.bar i.over{background:var(--red)}
.catrow{display:grid;grid-template-columns:1fr 130px 76px 62px;gap:8px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line)}
.catrow:last-child{border-bottom:none}
.chart{display:flex;align-items:flex-end;gap:5px;height:140px;padding-top:6px}
.chart .m{flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%}
.chart .b{display:flex;gap:2px;align-items:flex-end;flex:1;min-height:0}
.chart .b i{flex:1;border-radius:3px 3px 0 0;min-height:2px}
.chart .b i.in{background:var(--green)}.chart .b i.ex{background:var(--red)}
.chart .lbl{font-size:10.5px;color:var(--muted);text-align:center;margin-top:3px}
#msg{min-height:20px;font-size:13.5px;margin-bottom:6px}
#msg.ok{color:var(--green)}#msg.err{color:var(--red)}
.hidden{display:none}
.navrow{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;gap:8px}
@media (max-width:600px){.catrow{grid-template-columns:1fr 110px}.catrow button{grid-column:span 1}}
</style>
</head>
<body>
<header>
  <h1>Budżet domowy</h1>
  <button class="tab active" data-view="pulpit">Pulpit</button>
  <button class="tab" data-view="dodaj">Dodaj</button>
  <button class="tab" data-view="kategorie">Kategorie</button>
  <button class="tab" data-view="historia">Historia</button>
  <button class="tab" data-view="paragony">Paragony</button>
</header>
<main>
  <div id="msg"></div>

  <section id="view-pulpit">
    <div class="card">
      <div class="navrow">
        <button class="ghost" id="prev-m" style="padding:4px 12px">&larr;</button>
        <b id="mtitle"></b>
        <button class="ghost" id="next-m" style="padding:4px 12px">&rarr;</button>
      </div>
      <div class="grid">
        <div class="stat"><div class="lbl">Wpływy</div><div class="val pos" id="s-in">–</div></div>
        <div class="stat"><div class="lbl">Wydatki</div><div class="val neg" id="s-ex">–</div></div>
        <div class="stat"><div class="lbl">Bilans</div><div class="val" id="s-bal">–</div></div>
        <div class="stat"><div class="lbl">Pozostało z budżetu</div><div class="val" id="s-rem">–</div></div>
        <div class="stat"><div class="lbl">Budżet miesięczny (plan)</div>
          <div class="row" style="margin-top:3px">
            <input id="tb-in" type="number" step="0.01" min="0" style="padding:4px 8px">
            <button id="tb-save" class="ghost" style="padding:4px 10px">OK</button>
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <b>Miesięcznie — ostatnie 12 miesięcy</b>
      <div class="chart" id="chart"></div>
      <div class="small" style="margin-top:6px"><span style="color:var(--green)">■</span> wpływy&nbsp;&nbsp;<span style="color:var(--red)">■</span> wydatki</div>
    </div>
    <div class="card">
      <b>Rozbicie na kategorie</b>
      <div id="bcat"></div>
    </div>
  </section>

  <section id="view-dodaj" class="hidden">
    <div class="card">
      <b id="t-title">Dodaj transakcję</b>
      <div class="row" style="margin-top:10px">
        <div class="f"><label>Kategoria</label><select id="t-cat"></select></div>
        <div style="width:150px"><label>Kwota (zł)</label><input id="t-amt" type="number" step="0.01" min="0.01" placeholder="0.00"></div>
        <div style="width:170px"><label>Data</label><input id="t-date" type="date"></div>
      </div>
      <div style="margin-top:10px"><label>Notatka</label><input id="t-note" type="text" placeholder="np. Biedronka"></div>
      <div class="row" style="margin-top:12px">
        <button id="t-add">Dodaj transakcję</button>
        <button id="t-cancel" class="ghost hidden" style="margin-left:8px">Anuluj</button>
      </div>
      <p class="small" style="margin-bottom:0">Kwota zawsze dodatnia — kierunek (wpływ/wydatek) wynika z typu kategorii.</p>
    </div>
  </section>

  <section id="view-kategorie" class="hidden">
    <div class="card">
      <b>Nowa kategoria</b>
      <div class="row" style="margin-top:10px">
        <div class="f"><label>Nazwa</label><input id="c-name" type="text" placeholder="np. Czynsz"></div>
        <div style="width:130px"><label>Typ</label><select id="c-kind"><option value="expense">wydatek</option><option value="income">wpływ</option></select></div>
        <div style="width:140px"><label>Budżet (zł)</label><input id="c-budget" type="number" step="0.01" min="0" value="0"></div>
        <label class="small" style="display:flex;align-items:center;gap:6px;min-width:150px"><input id="c-rec" type="checkbox"> stała (auto 1. dnia miesiąca)</label>
      </div>
      <button id="c-add" style="margin-top:12px">Dodaj kategorię</button>
    </div>
    <div class="card">
      <b>Kategorie</b>
      <div class="small" style="margin:4px 0 8px">„Stała” + budżet &gt; 0 → automatycznie księgowana 1. dnia miesiąca (dotyczy wpływów i wydatków).</div>
      <button class="ghost" id="rec-run" style="margin-top:8px;padding:5px 12px">Zaksięguj stałe (teraz)</button>
      <div id="cl"></div>
    </div>
  </section>

  <section id="view-historia" class="hidden">
    <div class="card">
      <b>Ostatnie 12 miesięcy</b>
      <table id="htab"><thead><tr><th>Miesiąc</th><th class="num">Wpływy</th><th class="num">Wydatki</th><th class="num">Bilans</th></tr></thead><tbody></tbody></table>
    </div>
    <div class="card">
      <div class="navrow">
        <b>Transakcje: <span id="ht-title"></span></b>
        <span class="row"><button class="ghost" id="ht-prev" style="padding:4px 12px">&larr;</button><button class="ghost" id="ht-next" style="padding:4px 12px">&rarr;</button></span>
      </div>
      <table id="ttx"><thead><tr><th>Data</th><th>Kategoria</th><th class="num">Kwota</th><th>Notatka</th><th></th></tr></thead><tbody></tbody></table>
    </div>
  </section>

  <section id="view-paragony" class="hidden">
    <div class="card">
      <b>Paragony Lidl Plus</b>
      <div id="r-meta" class="small" style="margin:8px 0 4px">Ładowanie...</div>
      <div class="row" style="margin-top:8px">
        <button id="r-sync">Synchronizuj z Lidl Plus</button>
      </div>
      <p class="small" style="margin:10px 0 0">Przy pierwszym razie: ustaw <code>lidl_refresh_token</code> w opcjach add-onu (jak go zdobyć: plik <code>tools/get_lidl_token.py</code> w repo — patrz README). Paragon otwiera się w nowej karcie — tam „Drukuj → Zapisz jako PDF”. Usunięcie paragonu kasuje tylko kopię lokalną (w Lidl Plus zostaje).</p>
    </div>
    <div class="card">
      <table id="rtab"><thead><tr><th>Data</th><th>Sklep</th><th class="num">Pozycje</th><th class="num">Kwota</th><th></th></tr></thead><tbody></tbody></table>
    </div>
  </section>
</main>
<script>
const MIES = ["Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec","Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"];
const $ = (id) => document.getElementById(id);
// HA ingress serves this panel at /api/hassio_ingress/<token>/ and strips
// that prefix when proxying to the app — so every API call must stay inside
// the panel's own directory (absolute /api/... hits HA core and 404s).
const API_DIR = (location.pathname.endsWith("/") ? location.pathname : location.pathname.replace(/[^/]*$/, ""));
let view = "pulpit";
let catYear = new Date().getFullYear(), catMonth = new Date().getMonth() + 1;
let histY = catYear, histM = catMonth;
let cats = [];
let editTx = null;

function setEdit(tx) {
  editTx = tx;
  $("t-title").textContent = tx ? "Edytuj transakcję" : "Dodaj transakcję";
  $("t-add").textContent = tx ? "Zapisz zmiany" : "Dodaj transakcję";
  $("t-cancel").classList.toggle("hidden", !tx);
}

function money(x) {
  return (x < 0 ? "-" : "") + Math.abs(x).toFixed(2).replace(".", ",") + " zł";
}
async function api(path, opts) {
  const url = API_DIR + path.replace(/^\//, "");
  const r = await fetch(url, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("błąd " + r.status));
  return j;
}
function msg(text, cls) {
  const el = $("msg");
  el.textContent = text || "";
  el.className = cls || "";
  if (text) setTimeout(() => { el.textContent = ""; el.className = ""; }, 4000);
}

function show(v) {
  view = v;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.view === v));
  ["pulpit", "dodaj", "kategorie", "historia", "paragony"].forEach(x => $("view-" + x).classList.toggle("hidden", x !== v));
  if (v === "pulpit") loadPulpit();
  else if (v === "dodaj") loadAdd();
  else if (v === "kategorie") loadCats();
  else if (v === "historia") loadHist();
  else if (v === "paragony") loadReceipts();
}
document.querySelectorAll(".tab").forEach(t => { t.onclick = () => { if (t.dataset.view === "dodaj") setEdit(null); show(t.dataset.view); }; });

async function loadCats() {
  cats = (await api("/api/categories")).categories;
  const sel = $("t-cat");
  sel.innerHTML = "";
  const grp = (label, kind) => {
    const g = document.createElement("optgroup");
    g.label = label;
    cats.filter(c => c.kind === kind).forEach(c => {
      const o = document.createElement("option");
      o.value = c.key; o.textContent = c.name;
      g.appendChild(o);
    });
    if (g.children.length) sel.appendChild(g);
  };
  grp("Wpływy", "income");
  grp("Wydatki", "expense");
  if (!cats.length) sel.innerHTML = '<option value="">— brak kategorii —</option>';
  $("t-date").value = new Date().toISOString().slice(0, 10);

  const l = $("cl");
  l.innerHTML = "";
  if (!cats.length) l.innerHTML = '<p class="small">Brak kategorii — dodaj pierwszą powyżej.</p>';
  cats.forEach(c => {
    const d = document.createElement("div");
    d.className = "catrow";
    d.innerHTML =
      '<div><b></b><div class="small"></div></div>' +
      '<input data-b="' + c.key + '" type="number" step="0.01" min="0" value="' + c.monthly_budget + '">' +
      '<button class="ghost" data-s="' + c.key + '" style="padding:5px 8px">Zapisz</button>' +
      '<button class="danger" data-d="' + c.key + '" style="padding:5px 8px">Usuń</button>';
    d.children[0].children[0].textContent = c.name;
    d.children[0].children[1].textContent = (c.kind === "income" ? "wpływ" : "wydatek") + (c.recurring ? " · stała" : "");
    l.appendChild(d);
  });
  l.querySelectorAll("[data-s]").forEach(b => {
    b.onclick = async () => {
      const key = b.dataset.s;
      const val = parseFloat(l.querySelector('[data-b="' + key + '"]').value || "0");
      try {
        await api("/api/categories/" + key, { method: "PUT", body: JSON.stringify({ monthly_budget: isNaN(val) ? 0 : val }) });
        msg("Zapisano", "ok"); loadCats();
      } catch (e) { msg(e.message, "err"); }
    };
  });
  l.querySelectorAll("[data-d]").forEach(b => {
    b.onclick = async () => {
      const key = b.dataset.d;
      if (!confirm("Usunąć kategorię?")) return;
      try {
        await api("/api/categories/" + key, { method: "DELETE" });
        msg("Usunięto", "ok"); loadCats();
      } catch (e) { msg(e.message, "err"); }
    };
  });
}

$("c-add").onclick = async () => {
  const name = $("c-name").value.trim();
  if (!name) return msg("Podaj nazwę kategorii", "err");
  const body = {
    name: name,
    kind: $("c-kind").value,
    recurring: $("c-rec").checked,
    monthly_budget: parseFloat($("c-budget").value || "0") || 0
  };
  try {
    await api("/api/categories", { method: "POST", body: JSON.stringify(body) });
    msg("Dodano kategorię", "ok");
    $("c-name").value = ""; $("c-budget").value = "0"; $("c-rec").checked = false;
    loadCats();
  } catch (e) { msg(e.message, "err"); }
};

$("rec-run").onclick = async () => {
  try {
    const j = await api("/api/recurring", { method: "POST" });
    msg(j.added ? "Zaksięgowano " + j.added + " transakcje stałe" : "Nic do zaksięgowania (brak stałych lub już zaksięgowane w tym miesiącu)", "ok");
  } catch (e) { msg(e.message, "err"); }
};

$("t-add").onclick = async () => {
  const body = {
    category: $("t-cat").value,
    amount: parseFloat($("t-amt").value),
    date: $("t-date").value || null,
    note: $("t-note").value.trim()
  };
  if (!body.category) return msg("Wybierz kategorię (zakładka Kategorie)", "err");
  if (!(body.amount > 0)) return msg("Podaj kwotę większą od zera", "err");
  if (editTx) {
    if (!body.date) return msg("Podaj datę", "err");
    try {
      await api("/api/transactions/" + editTx.id, { method: "PUT", body: JSON.stringify(body) });
      msg("Zaktualizowano transakcję", "ok");
      setEdit(null);
      $("t-amt").value = ""; $("t-note").value = "";
      show("historia");
    } catch (e) { msg(e.message, "err"); }
    return;
  }
  try {
    await api("/api/transactions", { method: "POST", body: JSON.stringify(body) });
    msg("Zapisano transakcję", "ok");
    $("t-amt").value = ""; $("t-note").value = "";
    show("pulpit");
  } catch (e) { msg(e.message, "err"); }
};

$("t-cancel").onclick = () => {
  setEdit(null);
  $("t-amt").value = ""; $("t-note").value = "";
  show("historia");
};

async function loadAdd() {
  await loadCats();
  if (editTx) {
    $("t-cat").value = editTx.category_key;
    $("t-amt").value = editTx.amount;
    $("t-date").value = editTx.date;
    $("t-note").value = editTx.note || "";
  }
}
async function loadPulpit() {
  const s = await api("/api/summary?year=" + catYear + "&month=" + catMonth);
  $("mtitle").textContent = MIES[catMonth - 1] + " " + catYear;
  $("s-in").textContent = money(s.income);
  $("s-ex").textContent = money(s.expenses);
  const bal = $("s-bal");
  bal.textContent = money(s.balance);
  bal.className = "val " + (s.balance >= 0 ? "pos" : "neg");
  const rem = $("s-rem");
  rem.textContent = money(s.remaining);
  rem.className = "val " + (s.remaining >= 0 ? "pos" : "neg");
  $("tb-in").value = s.total_budget;

  const h = await api("/api/history");
  const max = Math.max(1, ...h.months.map(m => Math.max(m.income, m.expenses)));
  const ch = $("chart");
  ch.innerHTML = "";
  h.months.forEach(m => {
    const d = document.createElement("div");
    d.className = "m";
    d.title = MIES[m.month - 1] + " " + m.year + ": wpływy " + money(m.income) + ", wydatki " + money(m.expenses);
    d.innerHTML =
      '<div class="b"><i class="in" style="height:' + (m.income / max * 100).toFixed(1) + '%"></i>' +
      '<i class="ex" style="height:' + (m.expenses / max * 100).toFixed(1) + '%"></i></div>' +
      '<div class="lbl">' + m.month + '</div>';
    ch.appendChild(d);
  });

  const bc = $("bcat");
  bc.innerHTML = "";
  if (!s.by_category.length) bc.innerHTML = '<p class="small">Brak transakcji w tym miesiącu.</p>';
  s.by_category.forEach(c => {
    const d = document.createElement("div");
    d.className = "row";
    d.style.margin = "8px 0";
    const isIncome = c.kind === "income";
    const pct = c.budget > 0 ? Math.min(100, c.amount / c.budget * 100) : (c.amount > 0 ? 100 : 0);
    const over = c.budget > 0 && c.amount > c.budget;
    const barHtml = isIncome
      ? '<span></span>'
      : '<div class="bar"><i class="' + (over ? "over" : "") + '" style="width:' + pct.toFixed(1) + '%"></i></div>';
    d.innerHTML =
      '<span style="flex:1.2"></span>' + barHtml +
      '<span class="small" style="width:220px;text-align:right"></span>';
    d.children[0].innerHTML = c.name + (isIncome ? ' <span class="small">(wpływ)</span>' : "");
    d.children[2].innerHTML = money(c.amount) + (c.budget > 0 && !isIncome ? " / " + money(c.budget) : "");
    bc.appendChild(d);
  });
}

$("prev-m").onclick = () => { catMonth--; if (catMonth < 1) { catMonth = 12; catYear--; } loadPulpit(); };
$("next-m").onclick = () => { catMonth++; if (catMonth > 12) { catMonth = 1; catYear++; } loadPulpit(); };

$("tb-save").onclick = async () => {
  const v = parseFloat($("tb-in").value || "0");
  if (isNaN(v) || v < 0) return msg("Podaj budżet &gt;= 0", "err");
  try {
    await api("/api/total_budget", { method: "PUT", body: JSON.stringify({ amount: v }) });
    msg("Zapisano budżet miesięczny", "ok");
    loadPulpit();
  } catch (e) { msg(e.message, "err"); }
};

async function loadHist() {
  const h = await api("/api/history");
  const tb = $("htab").querySelector("tbody");
  tb.innerHTML = "";
  h.months.forEach(m => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td>' + MIES[m.month - 1] + ' ' + m.year + '</td>' +
      '<td class="num">' + money(m.income) + '</td>' +
      '<td class="num">' + money(m.expenses) + '</td>' +
      '<td class="num ' + (m.balance >= 0 ? "pos" : "neg") + '">' + money(m.balance) + '</td>';
    tb.appendChild(tr);
  });
  await loadTx();
}

async function loadTx() {
  const [s, c] = await Promise.all([
    api("/api/summary?year=" + histY + "&month=" + histM),
    api("/api/categories")
  ]);
  $("ht-title").textContent = MIES[histM - 1] + " " + histY;
  const catsMap = {};
  c.categories.forEach(x => { catsMap[x.key] = x; });
  const tb = $("ttx").querySelector("tbody");
  tb.innerHTML = "";
  if (!s.transactions.length) tb.innerHTML = '<tr><td colspan="5" class="small">Brak transakcji w tym miesiącu.</td></tr>';
  s.transactions.forEach(t => {
    const cc = catsMap[t.category_key] || { name: t.category_key, kind: "expense", recurring: 0 };
    const auto = cc.recurring && /stał/.test(t.note || "");
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td>' + t.date + '</td>' +
      '<td></td>' +
      '<td class="num ' + (cc.kind === "income" ? "pos" : "neg") + '"></td>' +
      '<td class="small"></td>' +
      '<td style="text-align:right;white-space:nowrap"><button class="ghost" data-edit="' + t.id + '" style="padding:3px 9px">edytuj</button> <button class="danger" data-del="' + t.id + '" style="padding:3px 9px">usuń</button></td>';
    tr.children[1].innerHTML = cc.name + (auto ? ' <span class="small">(auto)</span>' : "");
    tr.children[2].textContent = (cc.kind === "income" ? "+" : "−") + money(t.amount);
    tr.children[3].textContent = t.note || "";
    tb.appendChild(tr);
  });
  tb.querySelectorAll("[data-del]").forEach(b => {
    b.onclick = async () => {
      if (!confirm("Usunąć transakcję?")) return;
      try {
        await api("/api/transactions/" + b.dataset.del, { method: "DELETE" });
        msg("Usunięto", "ok");
        loadTx();
      } catch (e) { msg(e.message, "err"); }
    };
  });
  tb.querySelectorAll("[data-edit]").forEach(b => {
    b.onclick = () => {
      const t = s.transactions.find(x => x.id === parseInt(b.dataset.edit, 10));
      if (t) { setEdit(t); show("dodaj"); }
    };
  });
}

$("ht-prev").onclick = () => { histM--; if (histM < 1) { histM = 12; histY--; } loadTx(); };
$("ht-next").onclick = () => { histM++; if (histM > 12) { histM = 1; histY++; } loadTx(); };

let rTimer = null;
async function loadReceipts() {
  clearTimeout(rTimer);
  rTimer = null;
  let r;
  try {
    r = await api("/api/receipts");
  } catch (e) { msg(e.message, "err"); return; }
  const meta = $("r-meta");
  if (!r.configured) meta.textContent = "Nie skonfigurowano — ustaw lidl_refresh_token w opcjach add-onu (patrz README → Paragony Lidl Plus).";
  else if (r.syncing) meta.textContent = "Synchronizacja: " + (r.phase || "w trakcie") + " ...";
  else meta.textContent =
    (r.last_sync ? "Ostatnia synchronizacja: " + r.last_sync + " (nowych paragonów: " + (r.last_new ?? "?") + ")" : "Jeszcze nie synchronizowano") +
    (r.last_error ? " · Błąd: " + r.last_error : "");
  const tb = $("rtab").querySelector("tbody");
  tb.innerHTML = "";
  if (!r.receipts.length) {
    tb.innerHTML = '<tr><td colspan="5" class="small">Brak paragonów w lokalnej bazie — kliknij „Synchronizuj z Lidl Plus”.</td></tr>';
    return;
  }
  r.receipts.forEach(x => {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td></td><td></td><td class="num"></td><td class="num neg"></td><td style="text-align:right;white-space:nowrap"></td>';
    tr.children[0].textContent = x.date;
    tr.children[1].textContent = x.store || "";
    tr.children[2].textContent = x.articles ? String(x.articles) : "";
    tr.children[3].textContent = "−" + money(x.total);
    tr.children[4].innerHTML =
      '<button class="ghost" data-rv="' + x.id + '" style="padding:3px 9px">pokaż</button> ' +
      '<button class="danger" data-rd="' + x.id + '" style="padding:3px 9px">usuń</button>';
    tb.appendChild(tr);
  });
  tb.querySelectorAll("[data-rv]").forEach(b => {
    b.onclick = () => window.open(API_DIR + "api/receipts/" + b.dataset.rv + "/print", "_blank");
  });
  tb.querySelectorAll("[data-rd]").forEach(b => {
    b.onclick = async () => {
      if (!confirm("Usunąć paragon z lokalnej bazy? (w Lidl Plus zostaje)")) return;
      try {
        await api("/api/receipts/" + b.dataset.rd, { method: "DELETE" });
        msg("Usunięto", "ok"); loadReceipts();
      } catch (e) { msg(e.message, "err"); }
    };
  });
  if (r.syncing) rTimer = setTimeout(loadReceipts, 3000);
}

$("r-sync").onclick = async () => {
  try {
    await api("/api/receipts/sync", { method: "POST" });
    msg("Synchronizacja rozpoczęta — status poniżej", "ok");
    loadReceipts();
  } catch (e) { msg(e.message, "err"); }
};

show("pulpit");
</script>
</body>
</html>
"""
