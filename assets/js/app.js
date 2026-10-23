// PJM Build Ledger: loads the three CSVs that scripts/build_site_data.py writes and
// draws the page from them. No figure is hard-coded here.
(() => {
  const DATA = './output/site/';
  const TECH_ORDER = ['Gas combined cycle', 'Gas & oil peaking', 'Solar', 'Wind', 'Storage', 'Other'];
  const TECH_VAR = {
    'Gas combined cycle': '--tech-gas-cc', 'Gas & oil peaking': '--tech-gas-peak', Solar: '--tech-solar',
    Wind: '--tech-wind', Storage: '--tech-storage', Other: '--tech-other',
  };
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmtInt = d3.format(',');
  const fmt1 = d3.format(',.1f');
  const num = (x) => (x === '' || x == null || isNaN(+x) ? null : +x);
  const n0 = (x) => num(x) ?? 0;
  const monthName = (ym) => new Date(ym + '-01T00:00:00Z').toLocaleString('en', { month: 'long', year: 'numeric', timeZone: 'UTC' });

  const S = { mode: 'tech', q: '', tech: '', site: '', owner: '', sort: 'nameplate_mw', dir: -1, picked: null };
  let plants = [], coverage = [], rec = [], yearCols = [], owners = [];

  // ------------------------------------------------------------------ summary
  function summarize() {
    const full = coverage.filter((c) => +c.months === 12).map((c) => +c.year);
    const lastFull = Math.max(...full);
    const mw = d3.sum(plants, (p) => n0(p.nameplate_mw));
    const researched = d3.sum(plants.filter((p) => String(p.owner_basis).startsWith('researched')), (p) => n0(p.nameplate_mw));
    const twh = d3.sum(plants, (p) => n0(p.gen_total_gwh)) / 1000;
    const twhLast = d3.sum(plants, (p) => n0(p['gen_' + lastFull + '_gwh'])) / 1000;
    const cods = plants.map((p) => p.first_unit_online).sort();
    const partial = coverage.filter((c) => +c.months < 12).sort((a, b) => b.year - a.year)[0];

    const set = (id, html) => { document.getElementById(id).innerHTML = html; };
    set('t-plants', fmtInt(plants.length));
    set('t-gw', fmt1(mw / 1000) + '<small>GW</small>');
    set('t-twh', fmtInt(Math.round(twh)) + '<small>TWh</small>');
    document.getElementById('t-last-k').textContent = 'Generated in ' + lastFull;
    set('t-last', fmt1(twhLast) + '<small>TWh</small>');
    set('t-own', Math.round(100 * researched / mw) + '<small>%</small>');

    const lede = document.getElementById('lede');
    lede.replaceChildren();
    const b = (t) => { const e = document.createElement('b'); e.textContent = t; return e; };
    const txt = (t) => document.createTextNode(t);
    lede.append(b(fmtInt(plants.length)), txt(' new power plants came online in the PJM grid between '),
      txt(monthName(cods[0]) + ' and ' + monthName(cods[cods.length - 1])), txt(', adding '),
      b(fmt1(mw / 1000) + ' GW'), txt(' of capacity. They have generated '), b(fmtInt(Math.round(twh)) + ' TWh'),
      txt(' since, '), b(fmt1(twhLast) + ' TWh'), txt(' of it in ' + lastFull + '.'));

    if (partial) {
      const lastM = new Date(Date.UTC(+partial.year, +partial.months - 1, 1)).toLocaleString('en', { month: 'long', timeZone: 'UTC' });
      document.getElementById('gen-foot').textContent =
        `* ${partial.year} runs January to ${lastM}, and ${partial.pct_mw_reporting}% of online capacity has reported so far, ` +
        'because small plants report to EIA once a year. Battery output is net of charging, so storage reads slightly negative and is left off the bars.';
      document.getElementById('vintage').textContent = `EIA-860M Sep 2026 · EIA-923 through ${lastM} ${partial.year}`;
    }
  }

  // ------------------------------------------------------------------ chart
  function series() {
    const by = new Map();
    for (const c of yearCols) {
      const y = +c.slice(4, 8);
      for (const p of plants) {
        const g = S.mode === 'tech' ? p.tech_group : String(p.cod_year);
        const k = y + '|' + g;
        by.set(k, (by.get(k) || 0) + n0(p[c]));
      }
    }
    const years = yearCols.map((c) => +c.slice(4, 8));
    let keys = [...new Set(plants.map((p) => (S.mode === 'tech' ? p.tech_group : String(p.cod_year))))];
    keys = S.mode === 'tech'
      ? TECH_ORDER.filter((k) => keys.includes(k)).concat(keys.filter((k) => !TECH_ORDER.includes(k)))
      : keys.sort((a, b) => a - b);
    const wide = years.map((y) => {
      const o = { year: y };
      for (const k of keys) o[k] = (by.get(y + '|' + k) || 0) / 1000;
      return o;
    });
    const color = new Map();
    if (S.mode === 'tech') keys.forEach((k) => color.set(k, css(TECH_VAR[k] || '--tech-other')));
    else {
      const ramp = d3.interpolateRgb(css('--cohort-old'), css('--cohort-new'));
      keys.forEach((k, i) => color.set(k, ramp(keys.length > 1 ? i / (keys.length - 1) : 0)));
    }
    return { years, keys, wide, color };
  }

  const box = document.getElementById('gen-chart');
  const legend = document.getElementById('gen-legend');
  const tip = document.createElement('div');
  tip.className = 'tip'; tip.hidden = true;

  function drawChart() {
    const { years, keys, wide, color } = series();
    const months = new Map(coverage.map((c) => [+c.year, +c.months]));
    const label = (k) => (S.mode === 'tech' ? k : 'Online ' + k);
    box.replaceChildren();
    legend.replaceChildren();
    for (const k of keys) {
      const s = document.createElement('span');
      const i = document.createElement('i'); i.style.background = color.get(k);
      s.append(i, document.createTextNode(label(k)));
      legend.append(s);
    }

    const W = Math.max(300, box.clientWidth), H = 360, bottom = 26, top = 18;
    const pos = (o) => keys.reduce((s, k) => s + Math.max(0, o[k]), 0);
    const svg = d3.select(box).append('svg').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([0, d3.max(wide, pos) || 1], [H - bottom, top]).nice();
    const probe = svg.append('text').text(fmtInt(y.domain()[1]));
    const left = Math.ceil(probe.node().getComputedTextLength()) + 10;
    probe.remove();
    const x = d3.scaleBand(years, [left, W]).paddingInner(0.24).paddingOuter(0.06);

    for (const t of y.ticks(5)) {
      svg.append('line').attr('x1', left).attr('x2', W).attr('y1', y(t)).attr('y2', y(t))
        .attr('stroke', t === 0 ? css('--rule-strong') : css('--rule')).attr('stroke-width', 1);
      svg.append('text').attr('x', left - 8).attr('y', y(t)).attr('dy', '0.32em').attr('text-anchor', 'end').text(fmtInt(t));
    }
    svg.append('text').attr('x', 0).attr('y', 4).attr('dy', '0.32em').text('TWh');

    const every = x.bandwidth() < 30 ? 2 : 1;
    years.forEach((yr, i) => {
      if (i % every && i !== years.length - 1) return;
      svg.append('text').attr('x', x(yr) + x.bandwidth() / 2).attr('y', H - 7).attr('text-anchor', 'middle')
        .text((months.get(yr) ?? 12) < 12 ? yr + '*' : String(yr));
    });

    const bw = Math.min(x.bandwidth(), 64), off = (x.bandwidth() - bw) / 2;
    const stack = d3.stack().keys(keys).value((o, k) => Math.max(0, o[k]))(wide);
    for (const layer of stack) {
      svg.append('g').attr('fill', color.get(layer.key)).selectAll('rect').data(layer).join('rect')
        .attr('x', (s) => x(s.data.year) + off).attr('width', bw)
        .attr('y', (s) => y(s[1])).attr('height', (s) => Math.max(0, y(s[0]) - y(s[1])));
    }
    if (bw >= 24) {
      for (const o of wide) {
        const tot = keys.reduce((s, k) => s + o[k], 0);
        svg.append('text').attr('class', 'total').attr('x', x(o.year) + x.bandwidth() / 2).attr('y', y(pos(o)) - 6)
          .attr('text-anchor', 'middle').text(fmtInt(Math.round(tot)));
      }
    }

    const hi = svg.append('rect').attr('fill', 'none').attr('stroke', css('--ink-strong')).attr('stroke-width', 1.5).attr('rx', 2).attr('visibility', 'hidden');
    svg.append('g').selectAll('rect').data(wide).join('rect')
      .attr('x', (o) => x(o.year)).attr('width', x.bandwidth()).attr('y', 0).attr('height', H - bottom).attr('fill', 'transparent')
      .on('mousemove', (event, o) => {
        hi.attr('visibility', 'visible').attr('x', x(o.year) + off - 1.5).attr('width', bw + 3)
          .attr('y', y(pos(o)) - 1.5).attr('height', Math.max(0, y(0) - y(pos(o))) + 3);
        tip.replaceChildren();
        const h = document.createElement('div'); h.className = 'tip__h';
        const m = months.get(o.year) ?? 12;
        h.textContent = m < 12
          ? `${o.year}, January to ${new Date(Date.UTC(o.year, m - 1, 1)).toLocaleString('en', { month: 'long', timeZone: 'UTC' })}`
          : String(o.year);
        tip.append(h);
        for (const k of [...keys].reverse()) {
          if (Math.abs(o[k]) < 0.05) continue;
          const r = document.createElement('div'); r.className = 'tip__r';
          const i = document.createElement('i'); i.style.background = color.get(k);
          const v = document.createElement('b'); v.textContent = fmt1(o[k]) + ' TWh';
          r.append(i, document.createTextNode(label(k)), v);
          tip.append(r);
        }
        const t = document.createElement('div'); t.className = 'tip__r tip__r--total';
        const tv = document.createElement('b'); tv.textContent = fmt1(keys.reduce((s, k) => s + o[k], 0)) + ' TWh';
        t.append(document.createTextNode('Total'), tv);
        tip.append(t);
        tip.hidden = false;
        const [px, py] = d3.pointer(event, box);
        const tw = tip.offsetWidth, th = tip.offsetHeight;
        const lx = px + 16 + tw > box.clientWidth ? px - tw - 16 : px + 16;
        tip.style.left = Math.max(0, lx) + 'px';
        tip.style.top = Math.max(0, Math.min(box.clientHeight - th, py - th / 2)) + 'px';
      })
      .on('mouseleave', () => { tip.hidden = true; hi.attr('visibility', 'hidden'); });
    box.append(tip);
  }

  function setMode(m) {
    S.mode = m;
    document.getElementById('mode-tech').setAttribute('aria-pressed', String(m === 'tech'));
    document.getElementById('mode-cohort').setAttribute('aria-pressed', String(m === 'cohort'));
    drawChart();
  }
  document.getElementById('mode-tech').addEventListener('click', () => setMode('tech'));
  document.getElementById('mode-cohort').addEventListener('click', () => setMode('cohort'));

  // ------------------------------------------------------------------ owners
  function buildOwners() {
    const by = d3.rollup(plants, (v) => ({
      plants: v.length, mw: d3.sum(v, (p) => n0(p.nameplate_mw)), gwh: d3.sum(v, (p) => n0(p.gen_total_gwh)),
    }), (p) => p.parent_owner);
    owners = [...by].map(([name, o]) => ({ name, ...o })).sort((a, b) => b.mw - a.mw);
  }
  function drawOwners() {
    const tb = document.querySelector('#owner-table tbody');
    const frag = document.createDocumentFragment();
    for (const o of owners) {
      const tr = document.createElement('tr');
      tr.dataset.key = o.name;
      if (S.owner === o.name) tr.className = 'on';
      for (const [v, cls] of [[o.name, 'wrap-cell'], [fmtInt(o.plants), 'num'], [fmtInt(Math.round(o.mw)), 'num'], [fmt1(o.gwh / 1000), 'num']]) {
        const td = document.createElement('td'); td.className = cls; td.textContent = v; tr.append(td);
      }
      frag.append(tr);
    }
    tb.replaceChildren(frag);
  }
  document.querySelector('#owner-table tbody').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-key]');
    if (!tr) return;
    S.owner = S.owner === tr.dataset.key ? '' : tr.dataset.key;
    S.picked = null;
    drawOwners(); drawPlants();
    if (S.owner) document.getElementById('plants').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  function drawRec() {
    const tb = document.querySelector('#rec-table tbody');
    tb.replaceChildren(...rec.map((r) => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'default';
      for (const [v, cls] of [[r.step, 'num'], [r.basis, 'wrap-cell'], [fmtInt(+r.units), 'num'], [fmt1(+r.gw), 'num']]) {
        const td = document.createElement('td'); td.className = cls; td.textContent = v; tr.append(td);
      }
      return tr;
    }));
  }

  // ------------------------------------------------------------------ plants
  const head = document.getElementById('plant-head');
  const techSel = document.getElementById('plant-tech');
  const ownerBtn = document.getElementById('plant-owner');
  const detail = document.getElementById('plant-detail');
  let cols = [];

  function buildHead() {
    cols = [
      ['plant_name', 'Plant', 'wrap-cell', 'text'],
      ['parent_owner', 'Parent owner', 'wrap-cell', 'text'],
      ['tech_group', 'Technology', '', 'text'],
      ['first_unit_online', 'Online', '', 'text'],
      ['nameplate_mw', 'MW', 'num', 'num'],
      ['state', 'State', '', 'text'],
      ['pjm_zone', 'Zone', '', 'text'],
      ...yearCols.map((c) => [c, c.slice(4, 8), 'num', 'num']),
      ['gen_total_gwh', 'Total GWh', 'num', 'num'],
    ];
    head.replaceChildren(...cols.map(([field, label, cls, kind]) => {
      const th = document.createElement('th');
      if (cls === 'num') th.className = 'num';
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'sort'; b.textContent = label; b.dataset.field = field;
      b.addEventListener('click', () => {
        if (S.sort === field) S.dir = -S.dir; else { S.sort = field; S.dir = kind === 'num' ? -1 : 1; }
        drawPlants();
      });
      th.append(b);
      return th;
    }));
    const groups = [...new Set(plants.map((p) => p.tech_group))];
    for (const g of TECH_ORDER.filter((k) => groups.includes(k)).concat(groups.filter((k) => !TECH_ORDER.includes(k)))) techSel.append(new Option(g, g));
  }

  function drawPlants() {
    head.querySelectorAll('.sort').forEach((b) => b.setAttribute('aria-sort', b.dataset.field === S.sort ? (S.dir > 0 ? 'ascending' : 'descending') : 'none'));
    ownerBtn.hidden = !S.owner;
    ownerBtn.textContent = S.owner ? S.owner + '  ×' : '';
    const q = S.q.trim().toLowerCase();
    const kind = new Map(cols.map((c) => [c[0], c[3]]));
    const list = plants.filter((r) => (!S.tech || r.tech_group === S.tech) && (!S.site || r.site === S.site) &&
      (!S.owner || r.parent_owner === S.owner) &&
      (!q || [r.plant_name, r.parent_owner, r.ownership_detail, r.eia_operator, r.county, r.state, r.pjm_zone].join(' ').toLowerCase().includes(q)))
      .sort((a, b) => {
        const k = S.sort;
        if (kind.get(k) === 'num') {
          const av = num(a[k]), bv = num(b[k]);
          if (av == null && bv == null) return 0; if (av == null) return 1; if (bv == null) return -1;
          return S.dir * (av - bv);
        }
        return S.dir * String(a[k] ?? '').localeCompare(String(b[k] ?? ''));
      });
    document.getElementById('plant-count').textContent =
      `${fmtInt(list.length)} plants · ${fmtInt(Math.round(d3.sum(list, (r) => n0(r.nameplate_mw))))} MW`;

    const frag = document.createDocumentFragment();
    for (const r of list) {
      const tr = document.createElement('tr');
      tr.dataset.key = r.eia_plant_id;
      if (S.picked === r.eia_plant_id) tr.className = 'on';
      for (const [field, , cls, k] of cols) {
        const td = document.createElement('td');
        if (cls) td.className = cls;
        if (k === 'num') { const v = num(r[field]); td.textContent = v == null ? '' : fmt1(v); }
        else td.textContent = r[field] ?? '';
        tr.append(td);
      }
      frag.append(tr);
    }
    document.querySelector('#plant-table tbody').replaceChildren(frag);
    drawDetail();
  }

  function drawDetail() {
    const r = S.picked && plants.find((p) => p.eia_plant_id === S.picked);
    detail.hidden = !r;
    detail.replaceChildren();
    if (!r) return;
    const items = [
      ['plant_name', 'Plant'], ['parent_owner', 'Parent owner'], ['ownership_detail', 'Ownership'],
      ['owner_basis', 'How the owner was found'], ['owner_source_url', 'Ownership source'],
      ['eia_operator', 'EIA operating entity'], ['technology', 'EIA technology'], ['site', 'Site'],
      ['status', 'Status'], ['county', 'County'], ['interconnecting_utility', 'Interconnecting utility'],
      ['net_summer_mw', 'Net summer MW'], ['eia_plant_id', 'EIA plant ID'],
    ];
    for (const [field, label] of items) {
      const v = r[field];
      if (v == null || v === '') continue;
      const d = document.createElement('div');
      const k = document.createElement('span'); k.className = 'k'; k.textContent = label;
      const val = document.createElement('span'); val.className = 'v';
      if (field === 'owner_source_url' && /^https?:\/\//.test(v)) {
        const a = document.createElement('a'); a.href = v; a.target = '_blank'; a.rel = 'noopener'; a.textContent = v;
        val.append(a);
      } else val.textContent = v;
      d.append(k, val);
      detail.append(d);
    }
  }

  document.querySelector('#plant-table tbody').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-key]');
    if (!tr) return;
    S.picked = S.picked === tr.dataset.key ? null : tr.dataset.key;
    drawPlants();
    if (S.picked) detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  let qt;
  document.getElementById('plant-q').addEventListener('input', (e) => {
    clearTimeout(qt); qt = setTimeout(() => { S.q = e.target.value; drawPlants(); }, 150);
  });
  techSel.addEventListener('change', () => { S.tech = techSel.value; drawPlants(); });
  document.getElementById('plant-site').addEventListener('change', (e) => { S.site = e.target.value; drawPlants(); });
  ownerBtn.addEventListener('click', () => { S.owner = ''; drawOwners(); drawPlants(); });

  // ------------------------------------------------------------------ load
  Promise.all([d3.csv(DATA + 'plants.csv'), d3.csv(DATA + 'coverage.csv'), d3.csv(DATA + 'reconciliation.csv')])
    .then(([p, c, r]) => {
      plants = p; coverage = c; rec = r;
      yearCols = p.columns.filter((k) => /^gen_\d{4}_gwh$/.test(k)).sort();
      summarize();
      drawChart();
      buildOwners(); drawOwners();
      drawRec();
      buildHead(); drawPlants();
      let rw;
      new ResizeObserver(() => { clearTimeout(rw); rw = setTimeout(drawChart, 120); }).observe(box);
    })
    .catch((err) => {
      document.getElementById('lede').textContent = 'The data files did not load (' + err.message + '). Reload the page to try again.';
    });
})();
