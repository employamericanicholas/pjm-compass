// PJM Build Ledger: loads the three CSVs that scripts/build_site_data.py writes and
// draws the page from them. No figure is hard-coded here.
//
// Two tabs split the plants at 5 MW (#large, #small). Every card on the page
// redraws from the current tab's plants; the map and the plant table share one set
// of filters. Plant names come from EIA and enter the DOM through textContent only.
(() => {
  const DATA = './output/site/';
  const TABS = {
    large: { cls: '5 MW and up', label: 'plants of 5 MW or more' },
    small: { cls: 'under 5 MW', label: 'plants under 5 MW' },
    treemap: { cls: null, label: 'all new plants' },
  };
  const FUEL_ORDER = ['Natural gas', 'Solar', 'Wind', 'Hydro', 'Biomass', 'Petroleum', 'Other gases', 'Battery storage'];
  const FUEL_VAR = {
    'Natural gas': '--fuel-gas', Solar: '--fuel-solar', Wind: '--fuel-wind', Hydro: '--fuel-hydro',
    Biomass: '--fuel-biomass', Petroleum: '--fuel-petroleum', Coal: '--fuel-coal', Nuclear: '--fuel-nuclear',
    'Battery storage': '--fuel-storage', 'Other gases': '--fuel-other',
  };
  const fuelColor = (f) => css(FUEL_VAR[f] || '--fuel-other');
  const TECH_ORDER = ['Gas combined cycle', 'Gas & oil peaking', 'Solar', 'Wind', 'Storage', 'Other'];
  const TECH_VAR = {
    'Gas combined cycle': '--tech-gas-cc', 'Gas & oil peaking': '--tech-gas-peak', Solar: '--tech-solar',
    Wind: '--tech-wind', Storage: '--tech-storage', Other: '--tech-other',
  };
  // the PJM footprint, northern Illinois to the Delmarva coast
  const PJM_BOUNDS = [[35.2, -90.6], [42.6, -74.0]];
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmtInt = d3.format(',');
  const fmt1 = d3.format(',.1f');
  const num = (x) => (x === '' || x == null || isNaN(+x) ? null : +x);
  const n0 = (x) => num(x) ?? 0;
  const monthName = (ym) => new Date(ym + '-01T00:00:00Z').toLocaleString('en', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const techOrder = (groups) => TECH_ORDER.filter((k) => groups.includes(k)).concat(groups.filter((k) => !TECH_ORDER.includes(k)));

  const S = { tab: 'large', mode: 'tech', q: '', tech: '', site: '', owner: '', sort: 'nameplate_mw', dir: -1, picked: null };
  let ALL = [], plants = [], coverage = [], rec = [], yearCols = [], owners = [], lastFull = null, partial = null;

  // ------------------------------------------------------------------ summary
  function summarize() {
    const mw = d3.sum(plants, (p) => n0(p.nameplate_mw));
    const twh = d3.sum(plants, (p) => n0(p.gen_total_gwh)) / 1000;
    const twhLast = d3.sum(plants, (p) => n0(p['gen_' + lastFull + '_gwh'])) / 1000;
    const cods = plants.map((p) => p.first_unit_online).sort();
    const big = (v) => (v >= 100 ? fmtInt(Math.round(v)) : fmt1(v));
    const set = (id, value, unit) => {
      const t = document.getElementById(id);
      t.replaceChildren(document.createTextNode(value));
      if (unit) t.append(el('small', null, unit));
    };

    document.getElementById('t-plants-k').textContent = S.tab === 'large' ? 'Plants of 5 MW and up' : 'Plants under 5 MW';
    set('t-plants', fmtInt(plants.length));
    set('t-gw', mw >= 10000 ? fmt1(mw / 1000) : fmtInt(Math.round(mw)), mw >= 10000 ? 'GW' : 'MW');
    set('t-twh', big(twh), 'TWh');
    document.getElementById('t-last-k').textContent = 'Generated in ' + lastFull;
    set('t-last', big(twhLast), 'TWh');

    const lede = document.getElementById('lede');
    const b = (t) => el('b', null, t);
    const txt = (t) => document.createTextNode(t);
    lede.replaceChildren();
    if (S.tab === 'large') {
      const researched = d3.sum(plants.filter((p) => String(p.owner_basis).startsWith('researched')), (p) => n0(p.nameplate_mw));
      document.getElementById('t-five-k').textContent = 'Capacity with a researched owner';
      set('t-five', String(Math.round(100 * researched / mw)), '%');
      const over20 = plants.filter((p) => n0(p.nameplate_mw) >= 20).length;
      const huge = plants.filter((p) => n0(p.nameplate_mw) >= 500);
      const hugeShare = d3.sum(huge, (p) => n0(p.gen_total_gwh)) / (twh * 1000);
      lede.append(b(fmtInt(plants.length)), txt(` power plants of 5 MW or more came online in the PJM grid between ${monthName(cods[0])} and ${monthName(cods[cods.length - 1])}, `),
        txt('adding '), b(fmt1(mw / 1000) + ' GW'), txt(' of capacity. '), b(fmtInt(over20)), txt(' of them are 20 MW or larger. They have generated '),
        b(fmtInt(Math.round(twh)) + ' TWh'), txt(' since, '), b(fmt1(twhLast) + ' TWh'), txt(` of it in ${lastFull}, and the `),
        b(String(huge.length)), txt(` plants of 500 MW or more produced ${Math.round(100 * hugeShare)}% of it.`));
    } else {
      const solar = plants.filter((p) => p.tech_group === 'Solar').length;
      document.getElementById('t-five-k').textContent = 'Of them, solar';
      set('t-five', String(Math.round(100 * solar / plants.length)), '%');
      lede.append(b(fmtInt(plants.length)), txt(` plants under 5 MW came online in PJM between ${monthName(cods[0])} and ${monthName(cods[cods.length - 1])}, `),
        txt('most of them community and commercial solar. Together they add '), b(fmtInt(Math.round(mw)) + ' MW'),
        txt(' and have generated '), b(fmt1(twh) + ' TWh'), txt(' since, '), b(fmt1(twhLast) + ' TWh'), txt(` of it in ${lastFull}.`));
    }

    document.getElementById('owners-sub').textContent = S.tab === 'large'
      ? 'Parent owners ranked by capacity added. Plants of 20 MW or more were researched one by one; smaller ones show the owner EIA lists. Click an owner to see their plants.'
      : 'Owners as EIA lists them, usually the operating company. Plants this small were not researched one by one. Click an owner to see their plants.';
    document.getElementById('reconciliation').hidden = S.tab !== 'large';
  }

  // Coverage of the partial year is measured on this tab's own plants: small plants
  // report to EIA once a year, so the small tab's latest year is close to empty.
  function footnote() {
    if (!partial) return;
    const lastM = new Date(Date.UTC(+partial.year, +partial.months - 1, 1)).toLocaleString('en', { month: 'long', timeZone: 'UTC' });
    const col = 'gen_' + partial.year + '_gwh';
    const online = plants.filter((p) => p.first_unit_online < partial.year + '-' + String(partial.months).padStart(2, '0'));
    const mw = d3.sum(online, (p) => n0(p.nameplate_mw));
    const pct = mw ? Math.round(100 * d3.sum(online.filter((p) => num(p[col]) != null), (p) => n0(p.nameplate_mw)) / mw) : 0;
    document.getElementById('gen-foot').textContent =
      `* ${partial.year} runs January to ${lastM}, and ${pct}% of this tab's online capacity has reported for it so far, ` +
      'because smaller plants report to EIA once a year; the bar will grow when EIA publishes annual data. ' +
      'Battery output is net of charging, so storage reads slightly negative and is left off the bars.';
  }

  // ------------------------------------------------------------------ chart
  function series() {
    const by = new Map();
    for (const c of yearCols) {
      const y = +c.slice(4, 8);
      for (const p of plants) {
        const k = y + '|' + (S.mode === 'tech' ? p.tech_group : String(p.cod_year));
        by.set(k, (by.get(k) || 0) + n0(p[c]));
      }
    }
    const years = yearCols.map((c) => +c.slice(4, 8));
    let keys = [...new Set(plants.map((p) => (S.mode === 'tech' ? p.tech_group : String(p.cod_year))))];
    keys = S.mode === 'tech' ? techOrder(keys) : keys.sort((a, b) => a - b);
    const gwh = years.map((y) => d3.sum(keys, (k) => by.get(y + '|' + k) || 0));
    // the small-plant tab totals a few TWh a year at most, which reads better in GWh
    const unit = d3.max(gwh) >= 10000 ? 'TWh' : 'GWh';
    const div = unit === 'TWh' ? 1000 : 1;
    const wide = years.map((y) => {
      const o = { year: y };
      for (const k of keys) o[k] = (by.get(y + '|' + k) || 0) / div;
      return o;
    });
    const color = new Map();
    if (S.mode === 'tech') keys.forEach((k) => color.set(k, css(TECH_VAR[k] || '--tech-other')));
    else {
      const ramp = d3.interpolateRgb(css('--cohort-old'), css('--cohort-new'));
      keys.forEach((k, i) => color.set(k, ramp(keys.length > 1 ? i / (keys.length - 1) : 0)));
    }
    return { years, keys, wide, color, unit };
  }

  const box = document.getElementById('gen-chart');
  const legend = document.getElementById('gen-legend');
  const tip = el('div', 'tip'); tip.hidden = true;

  function drawChart() {
    const { years, keys, wide, color, unit } = series();
    const months = new Map(coverage.map((c) => [+c.year, +c.months]));
    const label = (k) => (S.mode === 'tech' ? k : 'Online ' + k);
    box.replaceChildren();
    legend.replaceChildren(...keys.map((k) => {
      const s = el('span'); const i = el('i'); i.style.background = color.get(k);
      s.append(i, document.createTextNode(label(k)));
      return s;
    }));

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
    svg.append('text').attr('x', 0).attr('y', 4).attr('dy', '0.32em').text(unit);

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
        const m = months.get(o.year) ?? 12;
        const rows = [el('div', 'tip__h', m < 12
          ? `${o.year}, January to ${new Date(Date.UTC(o.year, m - 1, 1)).toLocaleString('en', { month: 'long', timeZone: 'UTC' })}`
          : String(o.year))];
        for (const k of [...keys].reverse()) {
          if (Math.abs(o[k]) < 0.05) continue;
          const r = el('div', 'tip__r'); const i = el('i'); i.style.background = color.get(k);
          r.append(i, document.createTextNode(label(k)), el('b', null, fmt1(o[k]) + ' ' + unit));
          rows.push(r);
        }
        const t = el('div', 'tip__r tip__r--total');
        t.append(document.createTextNode('Total'), el('b', null, fmt1(keys.reduce((s, k) => s + o[k], 0)) + ' ' + unit));
        rows.push(t);
        tip.replaceChildren(...rows);
        tip.hidden = false;
        const [px, py] = d3.pointer(event, box);
        const tw = tip.offsetWidth, th = tip.offsetHeight;
        tip.style.left = Math.max(0, px + 16 + tw > box.clientWidth ? px - tw - 16 : px + 16) + 'px';
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

  // ------------------------------------------------------------------ map
  const mapHost = document.getElementById('plant-map');
  let map = null, layer = null;
  const markers = new Map();

  function initMap() {
    const L = window.L;
    if (!L) {
      mapHost.classList.add('plantmap--failed');
      mapHost.textContent = 'The map library did not load. The plant table below has every plant.';
      return;
    }
    map = L.map(mapHost, { preferCanvas: true, zoomSnap: 0.5, minZoom: 4, maxZoom: 15, scrollWheelZoom: false, dragging: !L.Browser.mobile });
    map.fitBounds(PJM_BOUNDS);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    // scroll-to-zoom only after the map is clicked, so page scrolling never gets caught
    map.on('click focus', () => map.scrollWheelZoom.enable());
    map.on('mouseout blur', () => map.scrollWheelZoom.disable());
    layer = L.layerGroup().addTo(map);
    // opened on the treemap tab the map starts hidden at zero size; fit it once it shows
    mapNeedsFit = mapHost.offsetWidth === 0;
  }
  let mapNeedsFit = false;

  function sparkline(p) {
    const NS = 'http://www.w3.org/2000/svg';
    const vals = yearCols.map((c) => ({ y: +c.slice(4, 8), v: num(p[c]) }));
    const W = 250, H = 58, top = 4, bottom = 14;
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'pop__spark');
    const max = d3.max(vals, (d) => Math.max(0, d.v ?? 0)) || 1;
    const x = d3.scaleBand(vals.map((d) => d.y), [0, W]).paddingInner(0.2);
    const y = d3.scaleLinear([0, max], [H - bottom, top]);
    const fill = css(TECH_VAR[p.tech_group] || '--tech-other');
    for (const d of vals) {
      if (d.v == null || d.v <= 0) continue;
      const r = document.createElementNS(NS, 'rect');
      r.setAttribute('x', x(d.y)); r.setAttribute('width', x.bandwidth());
      r.setAttribute('y', y(d.v)); r.setAttribute('height', Math.max(1, y(0) - y(d.v)));
      r.setAttribute('fill', fill); r.setAttribute('rx', 1.5);
      svg.append(r);
    }
    for (const d of [vals[0], vals[vals.length - 1]]) {
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', x(d.y) + (d === vals[0] ? 0 : x.bandwidth())); t.setAttribute('y', H - 2);
      t.setAttribute('text-anchor', d === vals[0] ? 'start' : 'end');
      t.textContent = d.y + ((d.y === +partial?.year) ? '*' : '');
      svg.append(t);
    }
    return svg;
  }

  function popup(p) {
    const box = el('div', 'pop');
    box.append(el('div', 'pop__name', p.plant_name));
    box.append(el('div', 'pop__meta', `${p.tech_group} · ${fmt1(n0(p.nameplate_mw))} MW · online ${monthName(p.first_unit_online)}`));
    const row = (k, v) => { const r = el('div', 'pop__row'); r.append(el('span', null, k), el('span', null, v)); return r; };
    box.append(row('Owner', p.parent_owner));
    box.append(row('Location', `${p.county}${/county|city/i.test(p.county) ? '' : ' County'}, ${p.state}`));
    if (p.pjm_zone) box.append(row('PJM zone', p.pjm_zone));
    if (p.interconnection_flag) box.append(el('div', 'pop__flag', 'Note: ' + p.interconnection_flag));
    if (num(p.gen_total_gwh) != null) {
      box.append(el('div', 'pop__meta', `Generated ${fmt1(n0(p.gen_total_gwh))} GWh since it came online` +
        (num(p['gen_' + lastFull + '_gwh']) != null ? `, ${fmt1(n0(p['gen_' + lastFull + '_gwh']))} GWh in ${lastFull}` : '') + ':'));
      box.append(sparkline(p));
    } else box.append(el('div', 'pop__meta', 'No generation reported to EIA-923 yet.'));
    const go = el('button', null, 'Year-by-year figures and ownership source');
    go.type = 'button';
    go.addEventListener('click', () => {
      S.picked = p.eia_plant_id;
      drawPlants();
      document.querySelector(`#plant-table tr[data-key="${CSS.escape(p.eia_plant_id)}"]`)?.scrollIntoView({ block: 'nearest' });
      detail.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    box.append(go);
    return box;
  }

  function drawMap(list) {
    const mapLegend = document.getElementById('map-legend');
    const groups = techOrder([...new Set(plants.map((p) => p.tech_group))]);
    mapLegend.replaceChildren(...groups.map((g) => {
      const s = el('span'); const i = el('i'); i.style.background = css(TECH_VAR[g] || '--tech-other'); i.style.borderRadius = '50%';
      s.append(i, document.createTextNode(g));
      return s;
    }));
    if (!map) return;
    const L = window.L;
    layer.clearLayers();
    markers.clear();
    const maxMw = d3.max(plants, (p) => n0(p.nameplate_mw)) || 1;
    // dot area tracks MW within the tab; small plants get a tighter range so they don't pile up
    const [rMin, rMax] = S.tab === 'large' ? [3, 18] : [2.5, 7];
    const radius = (mw) => rMin + (rMax - rMin) * Math.sqrt(Math.max(0, mw) / maxMw);
    const ink = css('--ink-strong');
    // largest first, so small plants draw on top and stay clickable
    for (const p of [...list].sort((a, b) => n0(b.nameplate_mw) - n0(a.nameplate_mw))) {
      const lat = num(p.latitude), lon = num(p.longitude);
      if (lat == null || lon == null) continue;
      const m = L.circleMarker([lat, lon], {
        radius: radius(n0(p.nameplate_mw)), color: p.interconnection_flag ? css('--accent') : ink,
        weight: p.interconnection_flag ? 1.5 : 0.6, opacity: 0.7,
        fillColor: css(TECH_VAR[p.tech_group] || '--tech-other'), fillOpacity: 0.82,
      });
      m.bindPopup(() => popup(p), { maxWidth: 300 });
      m.on('click', () => { S.picked = p.eia_plant_id; markRow(); });
      m.addTo(layer);
      markers.set(p.eia_plant_id, m);
    }
    const out = list.filter((p) => num(p.latitude) != null && !map.getBounds().pad(0.6).contains([+p.latitude, +p.longitude])).length;
    document.getElementById('map-note').textContent =
      `${fmtInt(markers.size)} plants shown.` + (out ? ` ${out} sit outside this view; zoom out to see them.` : '') +
      ' Dots with an orange outline report connecting to a utility outside PJM.';
  }

  // ------------------------------------------------------------------ owners
  function buildOwners() {
    const by = d3.rollup(plants, (v) => ({
      plants: v.length, mw: d3.sum(v, (p) => n0(p.nameplate_mw)), gwh: d3.sum(v, (p) => n0(p.gen_total_gwh)),
    }), (p) => p.parent_owner);
    owners = [...by].map(([name, o]) => ({ name, ...o })).sort((a, b) => b.mw - a.mw);
  }
  function drawOwners() {
    const tb = document.querySelector('#owner-table tbody');
    tb.replaceChildren(...owners.map((o) => {
      const tr = el('tr');
      tr.dataset.key = o.name;
      if (S.owner === o.name) tr.className = 'on';
      for (const [v, cls] of [[o.name, 'wrap-cell'], [fmtInt(o.plants), 'num'], [fmt1(o.mw), 'num'], [fmtInt(Math.round(o.gwh)), 'num']]) tr.append(el('td', cls, v));
      return tr;
    }));
  }
  document.querySelector('#owner-table tbody').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-key]');
    if (!tr) return;
    S.owner = S.owner === tr.dataset.key ? '' : tr.dataset.key;
    S.picked = null;
    drawOwners(); drawPlants();
    if (S.owner) document.getElementById('map').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  function drawRec() {
    document.querySelector('#rec-table tbody').replaceChildren(...rec.map((r) => {
      const tr = el('tr'); tr.style.cursor = 'default';
      for (const [v, cls] of [[r.step, 'num'], [r.basis, 'wrap-cell'], [fmtInt(+r.units), 'num'], [fmt1(+r.gw), 'num']]) tr.append(el('td', cls, v));
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
      const th = el('th', cls === 'num' ? 'num' : '');
      const b = el('button', 'sort', label);
      b.type = 'button'; b.dataset.field = field;
      b.addEventListener('click', () => {
        if (S.sort === field) S.dir = -S.dir; else { S.sort = field; S.dir = kind === 'num' ? -1 : 1; }
        drawPlants();
      });
      th.append(b);
      return th;
    }));
  }

  function techOptions() {
    techSel.replaceChildren(new Option('All technologies', ''),
      ...techOrder([...new Set(plants.map((p) => p.tech_group))]).map((g) => new Option(g, g)));
    techSel.value = S.tech;
  }

  function filtered() {
    const q = S.q.trim().toLowerCase();
    return plants.filter((r) => (!S.tech || r.tech_group === S.tech) && (!S.site || r.site === S.site) &&
      (!S.owner || r.parent_owner === S.owner) &&
      (!q || [r.plant_name, r.parent_owner, r.ownership_detail, r.eia_operator, r.county, r.state, r.pjm_zone].join(' ').toLowerCase().includes(q)));
  }

  function drawPlants() {
    head.querySelectorAll('.sort').forEach((b) => b.setAttribute('aria-sort', b.dataset.field === S.sort ? (S.dir > 0 ? 'ascending' : 'descending') : 'none'));
    ownerBtn.hidden = !S.owner;
    ownerBtn.textContent = S.owner ? S.owner + '  ×' : '';
    const kind = new Map(cols.map((c) => [c[0], c[3]]));
    const list = filtered().sort((a, b) => {
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
      const tr = el('tr');
      tr.dataset.key = r.eia_plant_id;
      for (const [field, , cls, k] of cols) {
        const v = k === 'num' ? (num(r[field]) == null ? '' : fmt1(num(r[field]))) : (r[field] ?? '');
        tr.append(el('td', cls, v));
      }
      frag.append(tr);
    }
    document.querySelector('#plant-table tbody').replaceChildren(frag);
    markRow();
    drawMap(list);
  }

  function markRow() {
    document.querySelectorAll('#plant-table tbody tr.on').forEach((tr) => tr.classList.remove('on'));
    if (S.picked) document.querySelector(`#plant-table tr[data-key="${CSS.escape(S.picked)}"]`)?.classList.add('on');
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
      ['interconnection_flag', 'Interconnection note'], ['net_summer_mw', 'Net summer MW'], ['eia_plant_id', 'EIA plant ID'],
    ];
    for (const [field, label] of items) {
      const v = r[field];
      if (v == null || v === '') continue;
      const d = el('div');
      const val = el('span', 'v');
      if (field === 'owner_source_url' && /^https?:\/\//.test(v)) {
        const a = el('a', null, v); a.href = v; a.target = '_blank'; a.rel = 'noopener';
        val.append(a);
      } else val.textContent = v;
      d.append(el('span', 'k', label), val);
      detail.append(d);
    }
  }

  document.querySelector('#plant-table tbody').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-key]');
    if (!tr) return;
    S.picked = S.picked === tr.dataset.key ? null : tr.dataset.key;
    markRow();
    const m = S.picked && markers.get(S.picked);
    if (m && map) { map.panTo(m.getLatLng()); m.openPopup(); }
    if (S.picked) detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  let qt;
  document.getElementById('plant-q').addEventListener('input', (e) => {
    clearTimeout(qt); qt = setTimeout(() => { S.q = e.target.value; drawPlants(); }, 200);
  });
  techSel.addEventListener('change', () => { S.tech = techSel.value; drawPlants(); });
  document.getElementById('plant-site').addEventListener('change', (e) => { S.site = e.target.value; drawPlants(); });
  ownerBtn.addEventListener('click', () => { S.owner = ''; drawOwners(); drawPlants(); });

  // ------------------------------------------------------------------ fuel treemap
  // Every plant of any size, nested fuel -> plant, as 50 States of Electricity's mix
  // treemap does by source. A treemap cannot show a negative area, so fuels that net
  // negative over the period (batteries, which are net of charging) go in the table
  // and the footnote instead.
  const tmBox = document.getElementById('tm-chart');
  const tmPeriod = document.getElementById('tm-period');
  const tmTip = el('div', 'tip'); tmTip.hidden = true;
  let pendingPick = null;
  const inkOn = (c) => { const r = d3.rgb(c); return (0.2126 * r.r + 0.7152 * r.g + 0.0722 * r.b) / 255 > 0.55 ? '#1c1c1c' : '#ffffff'; };
  const energy = (gwh) => (Math.abs(gwh) >= 1000 ? fmt1(gwh / 1000) + ' TWh' : fmtInt(Math.round(gwh)) + ' GWh');
  const pctOf = (v, t) => { const x = 100 * v / t; return x >= 10 ? Math.round(x) + '%' : x >= 0.1 ? x.toFixed(1) + '%' : '<0.1%'; };

  function periodOptions() {
    const lastM = partial ? new Date(Date.UTC(+partial.year, +partial.months - 1, 1)).toLocaleString('en', { month: 'short', timeZone: 'UTC' }) : 'Dec';
    const lastY = yearCols.length ? yearCols[yearCols.length - 1].slice(4, 8) : '';
    tmPeriod.replaceChildren(new Option(`All years, Jan 2015 – ${lastM} ${lastY}`, 'gen_total_gwh'),
      ...[...yearCols].reverse().map((c) => {
        const y = c.slice(4, 8);
        return new Option(partial && +y === +partial.year ? `${y} (Jan – ${lastM})` : y, c);
      }));
  }

  function fuelTotals(col) {
    const by = d3.rollup(ALL, (v) => ({
      plants: v.length, mw: d3.sum(v, (p) => n0(p.nameplate_mw)), gwh: d3.sum(v, (p) => n0(p[col])),
    }), (p) => p.fuel);
    const order = (f) => { const i = FUEL_ORDER.indexOf(f); return i < 0 ? 99 : i; };
    return [...by].map(([fuel, o]) => ({ fuel, ...o })).sort((a, b) => b.gwh - a.gwh || order(a.fuel) - order(b.fuel));
  }

  function drawTreemap() {
    const col = tmPeriod.value || 'gen_total_gwh';
    const fuels = fuelTotals(col);
    const pos = fuels.filter((f) => f.gwh > 0);
    const neg = fuels.filter((f) => f.gwh <= 0 && ALL.some((p) => p.fuel === f.fuel && num(p[col]) != null));
    const total = d3.sum(pos, (f) => f.gwh);
    const period = tmPeriod.selectedOptions[0]?.textContent || '';

    // lede and title follow the period
    const lede = document.getElementById('lede');
    const b = (t) => el('b', null, t);
    const txt = (t) => document.createTextNode(t);
    const [f1, f2, f3] = pos;
    lede.replaceChildren(txt('The '), b(fmtInt(ALL.length)), txt(' power plants that came online in PJM since January 2015 generated '),
      b(energy(total)), txt(col === 'gen_total_gwh' ? ` through ${period.split('– ')[1] || 'the latest month'}. ` : ` in ${period}. `));
    if (f1) lede.append(b(f1.fuel), txt(` plants produced ${pctOf(f1.gwh, total)} of it`));
    if (f2) lede.append(txt(', '), b(f2.fuel.toLowerCase()), txt(' ' + pctOf(f2.gwh, total)));
    if (f3) lede.append(txt(' and '), b(f3.fuel.toLowerCase()), txt(' ' + pctOf(f3.gwh, total)));
    lede.append(txt('.'));

    // legend
    document.getElementById('tm-legend').replaceChildren(...pos.map((f) => {
      const li = el('li'); const i = el('i'); i.style.background = fuelColor(f.fuel);
      li.append(i, txt(f.fuel + ' '), b(pctOf(f.gwh, total)));
      return li;
    }));

    // layout
    const data = {
      children: pos.map((f) => ({
        fuel: f.fuel,
        children: ALL.filter((p) => p.fuel === f.fuel && n0(p[col]) > 0).map((p) => ({ p, value: n0(p[col]) })),
      })),
    };
    const root = d3.hierarchy(data).sum((d) => d.value || 0).sort((a, b) => b.value - a.value);
    const W = Math.max(300, tmBox.clientWidth);
    const H = W < 640 ? Math.round(W * 1.4) : Math.max(480, Math.round(W * 0.5));
    // a fuel block big enough to label gets a header strip, so its name never sits on a plant's
    const HEAD = 24;
    const headed = (n) => n.depth === 1 && n.x1 - n.x0 > 80 && n.y1 - n.y0 > 70;
    d3.treemap().size([W, H]).tile(d3.treemapSquarify)
      .paddingInner((n) => (n.depth === 0 ? 3 : 0.75))
      .paddingTop((n) => (headed(n) ? HEAD : 0))(root);

    tmBox.replaceChildren();
    const svg = d3.select(tmBox).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
    const fuelOf = new Map(pos.map((f) => [f.fuel, f]));

    for (const group of root.children || []) {
      const base = d3.color(fuelColor(group.data.fuel));
      const g = svg.append('g');
      group.leaves().forEach((leaf, i) => {
        // neighbouring plants alternate a step lighter and darker so the tiles read apart
        const fill = base.brighter(((i % 3) - 1) * 0.18).formatHex();
        const w = leaf.x1 - leaf.x0, h = leaf.y1 - leaf.y0;
        g.append('rect').attr('class', 'tile-plant').attr('x', leaf.x0).attr('y', leaf.y0)
          .attr('width', Math.max(0, w)).attr('height', Math.max(0, h)).attr('fill', fill)
          .datum(leaf.data.p)
          .on('mousemove', (event, p) => tmTooltip(event, p, col, total, fuelOf.get(p.fuel)))
          .on('mouseleave', () => { tmTip.hidden = true; })
          .on('click', (event, p) => openPlant(p));
        if (w > 84 && h > 34) {
          const ink = inkOn(fill);
          const name = g.append('text').attr('class', 'lbl-plant').attr('x', leaf.x0 + 6).attr('y', leaf.y0 + 15).attr('fill', ink).text(leaf.data.p.plant_name);
          // shorten a name that does not fit rather than let it spill out of its tile
          let t = leaf.data.p.plant_name;
          while (t.length > 3 && name.node().getComputedTextLength() > w - 12) { t = t.slice(0, -2); name.text(t.trimEnd() + '…'); }
          if (h > 50) g.append('text').attr('class', 'lbl-plant').attr('x', leaf.x0 + 6).attr('y', leaf.y0 + 29)
            .attr('fill', ink).attr('opacity', 0.8).text(energy(leaf.value));
        }
      });
      // the fuel's name and total in its header strip, in a darker step of its colour
      if (headed(group)) {
        const gw = group.x1 - group.x0;
        const strip = base.darker(0.35).formatHex();
        svg.append('rect').attr('x', group.x0).attr('y', group.y0).attr('width', gw).attr('height', HEAD - 1).attr('fill', strip);
        const ink = inkOn(strip);
        const t = svg.append('text').attr('x', group.x0 + 8).attr('y', group.y0 + 16.5).attr('fill', ink);
        t.append('tspan').attr('class', 'lbl-fuel').text(group.data.fuel);
        const v = t.append('tspan').attr('class', 'lbl-fuel-v').attr('dx', 8).text(`${energy(group.value)} · ${pctOf(group.value, total)}`);
        if (t.node().getComputedTextLength() > gw - 14) v.remove();
        if (t.node().getComputedTextLength() > gw - 14) t.remove();
      }
    }
    tmBox.append(tmTip);

    // the table twin and the footnote
    document.querySelector('#fuel-table tbody').replaceChildren(...fuels.map((f) => {
      const tr = el('tr'); tr.style.cursor = 'default';
      const name = el('td', 'wrap-cell'); const i = el('i'); i.className = 'sw';
      i.style.cssText = `display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:8px;background:${fuelColor(f.fuel)}`;
      name.append(i, txt(f.fuel));
      tr.append(name, el('td', 'num', fmtInt(f.plants)), el('td', 'num', fmtInt(Math.round(f.mw))),
        el('td', 'num', Math.abs(f.gwh) >= 100 ? fmt1(f.gwh / 1000) : (f.gwh / 1000).toFixed(3)),
        el('td', 'num', f.gwh > 0 ? pctOf(f.gwh, total) : 'net negative'));
      return tr;
    }));
    document.getElementById('fuel-sub').textContent = `The same totals as a table, for ${col === 'gen_total_gwh' ? 'all years' : period}. Shares are of positive generation.`;
    const notes = [];
    if (neg.length) notes.push(`${neg.map((f) => f.fuel).join(' and ')} ${neg.length > 1 ? 'net' : 'nets'} negative for this period (batteries draw more power charging than they return), so ${neg.length > 1 ? 'they are' : 'it is'} in the table but not the treemap.`);
    if (partial && (col === 'gen_total_gwh' || +col.slice(4, 8) === +partial.year))
      notes.push(`${partial.year} runs only through ${new Date(Date.UTC(+partial.year, +partial.months - 1, 1)).toLocaleString('en', { month: 'long', timeZone: 'UTC' })}, and small plants have not yet reported it.`);
    notes.push('A plant with more than one technology, such as solar with a battery, is placed under its largest one by capacity.');
    document.getElementById('tm-note').textContent = notes.join(' ');
  }

  function tmTooltip(event, p, col, total, fuel) {
    const v = n0(p[col]);
    const row = (k, val) => { const r = el('div', 'tip__r'); r.append(txt2(k), el('b', null, val)); return r; };
    const txt2 = (t) => document.createTextNode(t);
    tmTip.replaceChildren(
      el('div', 'tip__h', p.plant_name),
      el('div', 'tip__r', `${p.fuel} · ${p.tech_group} · ${fmt1(n0(p.nameplate_mw))} MW`),
      el('div', 'tip__r', `${p.parent_owner}`),
      el('div', 'tip__r', `${p.county}, ${p.state} · online ${monthName(p.first_unit_online)}`),
      row('Generated', energy(v)),
      row('Share of all new plants', pctOf(v, total)),
      row('Share of ' + p.fuel.toLowerCase(), pctOf(v, fuel.gwh)),
    );
    tmTip.hidden = false;
    const [px, py] = d3.pointer(event, tmBox);
    const tw = tmTip.offsetWidth, th = tmTip.offsetHeight;
    tmTip.style.left = Math.max(0, px + 16 + tw > tmBox.clientWidth ? px - tw - 16 : px + 16) + 'px';
    tmTip.style.top = Math.max(0, Math.min(tmBox.clientHeight - th, py + 12)) + 'px';
  }

  // a treemap tile opens the plant on its own size tab, selected in the table and on the map
  function openPlant(p) {
    pendingPick = p.eia_plant_id;
    location.hash = p.size_class === 'under 5 MW' ? 'small' : 'large';
  }

  tmPeriod.addEventListener('change', drawTreemap);

  // ------------------------------------------------------------------ tabs
  function showTab(tab) {
    if (!TABS[tab]) tab = 'large';
    S.tab = tab;
    S.tech = ''; S.owner = ''; S.picked = null;
    document.querySelectorAll('.sitenav a').forEach((a) => {
      if (a.dataset.tab === tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    const isTm = tab === 'treemap';
    document.querySelectorAll('.ledger-only').forEach((n) => { n.hidden = isTm; });
    document.querySelectorAll('.tm-only').forEach((n) => { n.hidden = !isTm; });
    if (isTm) {
      if (map) map.closePopup();
      drawTreemap();
      return;
    }
    tmTip.hidden = true;
    plants = ALL.filter((p) => p.size_class === TABS[tab].cls);
    document.getElementById('gen-title').textContent = `Electricity generated by ${TABS[tab].label} built since 2015`;
    if (map) map.closePopup();
    summarize();
    footnote();
    drawChart();
    buildOwners(); drawOwners();
    techOptions();
    drawPlants();
    if (map) {
      map.invalidateSize();
      if (mapNeedsFit) { map.fitBounds(PJM_BOUNDS); mapNeedsFit = false; drawMap(filtered()); }
    }
    if (pendingPick) {
      S.picked = pendingPick;
      pendingPick = null;
      markRow();
      document.querySelector(`#plant-table tr[data-key="${CSS.escape(S.picked)}"]`)?.scrollIntoView({ block: 'nearest' });
      const m = markers.get(S.picked);
      if (m && map) { map.setView(m.getLatLng(), Math.max(map.getZoom(), 8)); m.openPopup(); }
      document.getElementById('map').scrollIntoView({ block: 'start' });
    }
  }
  window.addEventListener('hashchange', () => showTab(location.hash.slice(1)));

  // ------------------------------------------------------------------ load
  Promise.all([d3.csv(DATA + 'plants.csv'), d3.csv(DATA + 'coverage.csv'), d3.csv(DATA + 'reconciliation.csv')])
    .then(([p, c, r]) => {
      ALL = p; coverage = c; rec = r;
      yearCols = p.columns.filter((k) => /^gen_\d{4}_gwh$/.test(k)).sort();
      lastFull = Math.max(...coverage.filter((x) => +x.months === 12).map((x) => +x.year));
      partial = coverage.filter((x) => +x.months < 12).sort((a, b) => b.year - a.year)[0] || null;
      drawRec();
      buildHead();
      if (partial) {
        const lastM = new Date(Date.UTC(+partial.year, +partial.months - 1, 1)).toLocaleString('en', { month: 'long', timeZone: 'UTC' });
        document.getElementById('vintage').textContent = `EIA-860M Sep 2026 · EIA-923 through ${lastM} ${partial.year}`;
      }
      initMap();
      periodOptions();
      showTab(location.hash.slice(1));
      let rw, rt;
      new ResizeObserver(() => { clearTimeout(rw); rw = setTimeout(() => { if (S.tab !== 'treemap') drawChart(); }, 120); }).observe(box);
      new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(() => { if (S.tab === 'treemap') drawTreemap(); }, 120); }).observe(tmBox);
    })
    .catch((err) => {
      document.getElementById('lede').textContent = 'The data files did not load (' + err.message + '). Reload the page to try again.';
    });
})();
