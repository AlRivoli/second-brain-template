// La mappa della home: nodi (progetti, argomenti) con i task a raggiera, la prossima azione e il dettaglio nel pannello.
// Tutto in un IIFE: gli helper hanno il nome di quelli di dashboard.js (che carica dopo) e non devono scontrarsi.
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const STATI = ['da_fare', 'in_corso', 'fatto'];
  const NOME_STATO = { da_fare: 'da fare', in_corso: 'in corso', fatto: 'fatto' };
  const FILTRI = [['tutto', 'Tutto'], ['aperti', 'Aperti'], ['progetti', 'Progetti'], ['argomenti', 'Argomenti'], ['obiettivi', 'Obiettivi']];
  // What the map shows: four states derived from the dependency graph. The selector above still writes the raw three.
  const VISIVI = ['fatto', 'in_corso', 'pronto', 'in_attesa'];   // ring order
  const NOME_VISIVO = { pronto: 'pronto', in_corso: 'in corso', in_attesa: 'in attesa', fatto: 'fatto' };
  const GRUPPI = [['pronto', 'Pronti da avviare'], ['in_corso', 'In corso'], ['in_attesa', 'In attesa'], ['fatto', 'Fatti']];
  const DA_DERIVATO = { pronto: 'pronto', in_corso: 'in_corso', incoerente: 'in_corso', in_attesa: 'in_attesa', errore: 'in_attesa', fatto: 'fatto' };
  // A task without `derivato` (e.g. the one built by avviaVoce) falls back to its raw state, «da fare» reading as ready.
  const statoVisivo = t => DA_DERIVATO[t.derivato] || (t.stato === 'da_fare' ? 'pronto' : t.stato);
  // The server refuses to launch anything else (409): incoerente reads as «in corso» but is not launchable.
  const avviabile = t => !t.bozza && t.chi !== 'te' && (t.derivato === 'pronto' || t.derivato === 'in_corso');

  let dati = null;          // l'ultima risposta di /api/mappa
  let progetti = [];        // /api/stato, per «Dove sono» e l'ultimo commit
  let giorni = [];          // /api/oggi, voci con data
  let impronta = '';        // per non ridisegnare (e non interrompere un hover) se nulla è cambiato
  let filtro = 'tutto';
  let aperto = null;        // UN solo nodo aperto: nome del nodo sotto il puntatore o col fuoco
  let fissato = null;       // nome del nodo fissato con un clic, oppure 'obiettivo:' + slug (a goal slug may equal a node name)
  let selezione = null;     // task scelto (clic su un satellite)
  let filtroRepo = null;    // { nodo, repo }: the per-repo filter of the fixed node's panel, dropped when another node is fixed
  let nodiSvg = new Map();  // nome -> gruppo SVG
  let obiettiviSvg = new Map();   // slug -> { G, linee }: kept apart from nodiSvg so apri/filo never see a goal
  let pos = new Map();      // nome -> {x, y, r}
  let dimensione = '';
  let vista = { k: 1, x: 0, y: 0 };   // zoom e spostamento: si conservano a ogni ridisegno

  const $ = id => document.getElementById(id);
  function h(tag, classe, figli, attr) {
    const n = document.createElement(tag);
    if (classe) n.className = classe;
    (figli || []).forEach(f => f && n.appendChild(typeof f === 'string' ? document.createTextNode(f) : f));
    for (const k in attr || {}) n.setAttribute(k, attr[k]);
    return n;
  }
  function s(tag, attr, figli) {
    const n = document.createElementNS(NS, tag);
    for (const k in attr || {}) n.setAttribute(k, attr[k]);
    (figli || []).forEach(f => n.appendChild(typeof f === 'string' ? document.createTextNode(f) : f));
    return n;
  }
  function bottone(testo, classe, onclick) {
    const b = h('button', classe, [testo], { type: 'button' });
    b.addEventListener('click', onclick);
    return b;
  }
  const K_MIN = 0.6, K_MAX = 3;       // oltre questi limiti le etichette si toccano o i nodi escono dal riquadro
  // Le bozze con «Progetto:» stanno anche sul nodo del progetto come satelliti, ma il suo numero resta quello del piano.
  const delNodo = n => n.task.filter(t => n.nome === 'Social' || !t.bozza);
  const aperti = n => n.task.filter(t => t.stato !== 'fatto' && (n.nome === 'Social' || !t.bozza)).length;
  const pronti = n => delNodo(n).filter(t => statoVisivo(t) === 'pronto').length;
  const puoAggiungere = n => n.haCartella && n.tipo !== 'senza' && /^[A-Za-z][\p{L}\p{N}_-]*$/u.test(n.nome);   // il nome del nodo è il tag: deve essere un tag valido
  // Cosa dice il numero sul nodo, a parole: lo stesso testo va nel tooltip, nell'etichetta per i lettori di schermo, nel pannello e nella lista.
  // Social conta bozze (content/), gli altri nodi task di piano.md: pronti sempre (è il numero), in corso e in attesa se ci sono.
  function contoAperti(n) {
    const k = aperti(n);
    if (n.nome === 'Social') return k ? k + (k === 1 ? ' bozza da pubblicare' : ' bozze da pubblicare') : 'nessuna bozza da pubblicare';
    const b = n.task.filter(t => t.bozza && t.stato !== 'fatto').length, nelPiano = n.task.length - n.task.filter(t => t.bozza).length;
    const bozze = b ? ' · ' + b + (b === 1 ? ' bozza da pubblicare' : ' bozze da pubblicare') : '';
    if (!k) return (nelPiano ? 'nessun task aperto' : 'nessun task nel piano con questo tag') + bozze;
    const quanti = st => delNodo(n).filter(t => statoVisivo(t) === st).length, p = pronti(n), c = quanti('in_corso'), a = quanti('in_attesa');
    return [p + (p === 1 ? ' pronto' : ' pronti'), c ? c + ' in corso' : '', a ? a + ' in attesa' : ''].filter(Boolean).join(' · ') + bozze;
  }
  const haPiu = n => aperti(n) === 0 && puoAggiungere(n);   // nodo senza task da fare: un «+» per scriverne uno
  // Il «+» sta due volte: sul nodo, e sopra la zona dei satelliti quando il nodo è aperto (la zona copre il bordo del disco).
  function piu(n, p) {
    const A = s('g', { class: 'azione', transform: `translate(${(p.x + p.r * 0.78).toFixed(1)} ${(p.y - p.r * 0.78).toFixed(1)})`, tabindex: 0, role: 'button', 'aria-label': 'Aggiungi un task a ' + n.nome });
    A.append(s('title', {}, ['Aggiungi un task']), s('g', { class: 'azione-dentro' }, [s('circle', { r: 12 }), s('text', { dy: '0.35em' }, ['+'])]));
    A.addEventListener('click', e => { e.stopPropagation(); nuovoTask(n); });
    A.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); nuovoTask(n); } });
    return A;
  }
  const nodoPer = nome => dati && dati.nodi.find(n => n.nome === nome);
  const PREFISSO_OBIETTIVO = 'obiettivo:';
  const obiettiviDi = () => (dati && dati.obiettivi) || [];   // the empty fixture and an older server send no goals
  const obiettivoPer = chiave => typeof chiave === 'string' && chiave.startsWith(PREFISSO_OBIETTIVO) ? obiettiviDi().find(o => PREFISSO_OBIETTIVO + o.slug === chiave) : undefined;
  // The same words in the aria-label, the tooltip, the panel and the list.
  function contoObiettivo(o) {
    const c = o.conteggi;
    return [c.pronti + (c.pronti === 1 ? ' pronto' : ' pronti'), c.in_corso + ' in corso', c.in_attesa + ' in attesa', c.fatti + (c.fatti === 1 ? ' fatto' : ' fatti')].join(' · ');
  }
  const NESSUN_OBIETTIVO = 'Nessun obiettivo nel piano: aggiungi obiettivo:<slug> a un task di docs/piano.md.';
  const NESSUN_PASSO = 'Nessun passo nel piano con questo obiettivo.';
  function taglia(testo, max) {
    if (testo.length <= max) return testo;
    const t = testo.slice(0, max), i = t.lastIndexOf(' ');
    return (i > max / 2 ? t.slice(0, i) : t).replace(/[\s,;:.]+$/, '') + '…';
  }
  function giornoBreve(iso) {
    return new Date(iso + 'T12:00').toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }).replace('.', '');
  }
  // What a task waits for, in words: one line per blocker (or the error), the same in the panel and in the list.
  const bloccante = (a, n) => a.chi === 'te' ? 'te — ' + a.vista : a.vista + (a.nodo !== n.nome ? ' · ' + a.nodo : '');
  // A late task that is blocked is never the next action, so the late signal travels with the reason instead.
  function motivi(t, n) {
    const tardi = t.ritardo && (t.derivato === 'in_attesa' || t.derivato === 'errore') ? ['in ritardo e bloccato'] : [];
    if (t.derivato === 'errore') {
      return [...tardi, t.errore === 'riferimento' ? 'riferimento rotto: ' + t.mancanti.join(', ') : t.errore === 'ciclo' ? 'ciclo di dipendenze' : 'id doppio: ' + t.id];
    }
    if (t.derivato !== 'in_attesa' && t.derivato !== 'incoerente') return [];
    return [...tardi, ...t.aspetta.map(a => (t.derivato === 'incoerente' ? 'aspetta ancora: ' : 'aspetta: ') + bloccante(a, n))];
  }
  // Tasks split by visual state, in panel order; «Fatti» folded (open only if it holds the selected task, so the scroll finds it).
  function gruppi(ts, riga, titolo) {
    return GRUPPI.flatMap(([st, nome]) => {
      const g = ts.filter(t => statoVisivo(t) === st);
      if (!g.length) return [];
      const ul = h('ul', 'task-elenco', g.map(riga));
      if (st !== 'fatto') return [h(titolo, 'gruppo', [nome]), ul];
      const conScelto = g.some(t => selezione && selezione.testo === t.testo && selezione.data === t.data);
      return [h('details', 'gruppo-fatti', [h('summary', '', [h(titolo, 'gruppo', [nome + ' (' + g.length + ')'])]), ul], conScelto ? { open: '' } : {})];
    });
  }
  // A task with no valid repo may touch any repo of its project, so a per-repo filter keeps it
  const tocca = (t, repo) => !(t.repo || []).length || t.repo.includes(repo);
  // What a row says about its repos, the same in the panel and in the list: a chip per valid repo, then the warnings in words.
  // `filtrato`: under a repo filter a task with no `repo:` at all says so (one naming only unknown repos already says it).
  function segniRepo(t, filtrato) {
    const nomi = [...new Set(t.repo || [])], ignoti = t.repoIgnoti || [];
    return [
      nomi.length ? h('span', 'repo-elenco', ['repo', ...nomi.map(r => h('span', 'repo', [taglia(r, 24)]))]) : null,
      ...ignoti.map(r => h('span', 'sub motivo', ['repo sconosciuto: ' + taglia(r, 24)])),
      (t.stessoRepo || []).length ? h('span', 'stato attenzione avviso-repo', ['stesso repo di un task in corso']) : null,
      filtrato && !nomi.length && !ignoti.length && !t.bozza ? h('span', 'sub', ['repo non indicato']) : null,
    ];
  }

  // ---- dati di prova (?prova=vuoto o ?prova=pieno): servono solo a verificare l'aspetto ----
  function prova(tipo) {
    if (tipo === 'vuoto') {
      return { nodi: ['alfa', 'beta', 'gamma'].map(nome => ({ nome, tipo: 'progetto', priorita: 'da definire', haCartella: true, task: [] })), obiettivi: [], prossima: null, conteggi: { da_fare: 0, in_corso: 0, in_ritardo: 0, pronti: 0, in_attesa: 0 } };
    }
    const nomi = ['Verificare il centralino con sessioni reali', 'Unire la PR della CI', 'Taratura del radar sui progetti attivi', 'Scrivere i test del parser', 'Inoltro email in configurazione', 'Aprire ai primi Club', 'Cron esterno per le notifiche', 'Pagare il dominio', 'Ridisegnare la pagina di accesso', 'Controllare i log del giovedì', 'Rispondere a chi ha scritto', 'Pubblicare le sei bozze', 'Conferma prima del voto', 'Android installa', 'Hardening del vault'];
    const stati = ['in_corso', 'da_fare', 'da_fare', 'da_fare', 'in_corso', 'da_fare', 'da_fare', 'da_fare', 'da_fare', 'da_fare', 'da_fare', 'da_fare', 'fatto', 'fatto', 'fatto'];
    // every state and error: a blocker in the same node (1), one in another node (linkedin), one of yours (7), a broken reference and a cycle
    const blocco = { ci: { id: 'pr-ci', vista: nomi[1], nodo: 'Prova piena', chi: null }, li: { id: 'bozze-li', vista: 'Pubblicare 6 bozze', nodo: 'linkedin', chi: null }, te: { id: 'dominio', vista: nomi[7], nodo: 'Prova piena', chi: 'te' } };
    const extra = { 1: { id: 'pr-ci' }, 2: { derivato: 'in_attesa', aspetta: [blocco.ci] }, 4: { derivato: 'incoerente', aspetta: [blocco.ci] }, 5: { derivato: 'in_attesa', aspetta: [blocco.li] },
      6: { derivato: 'errore', errore: 'riferimento', mancanti: ['cron-vecchio'] }, 7: { id: 'dominio', chi: 'te' }, 8: { derivato: 'in_attesa', aspetta: [blocco.te] }, 9: { derivato: 'errore', errore: 'ciclo' } };
    // goals: «club» spans three nodes and every state, «linkedin» is defined with no task (and shares a node's name), «radar» is undefined
    const obiettivoDi = { 0: 'club', 5: 'club', 13: 'club', 2: 'radar' };
    const task = nomi.map((testo, i) => ({ data: '2026-11-' + String(10 + i).padStart(2, '0'), testo, vista: testo, stato: stati[i], ritardo: i === 3,
      id: null, chi: null, derivato: stati[i] === 'da_fare' ? 'pronto' : stati[i], errore: null, mancanti: [], aspetta: [], obiettivo: obiettivoDi[i] || null, ...extra[i] }));
    const nodi = [{ nome: 'Prova piena', tipo: 'progetto', priorita: 'alta', haCartella: true, task },
      { nome: 'linkedin', tipo: 'argomento', priorita: null, haCartella: true, task: [{ data: '2026-11-12', testo: 'Pubblicare 6 bozze', vista: 'Pubblicare 6 bozze', stato: 'da_fare', ritardo: false, id: 'bozze-li', chi: null, derivato: 'pronto', errore: null, mancanti: [], aspetta: [], obiettivo: 'club' }] }];
    // repos, as the server sends them: valid names (duplicates kept), unknown ones apart, the same-repo warning only on ready tasks
    const conRepo = (i, testo, stato, campi) => ({ data: '2026-11-' + String(10 + i).padStart(2, '0'), testo, vista: testo, stato, ritardo: false, id: null, chi: null,
      derivato: stato === 'da_fare' ? 'pronto' : stato, errore: null, mancanti: [], aspetta: [], obiettivo: null, repo: [], repoIgnoti: [], stessoRepo: [], ...campi });
    nodi.push({ nome: 'Prova repo', tipo: 'progetto', priorita: 'media', haCartella: true, repo: ['api', 'web', 'app-mobile'], task: [
      conRepo(1, 'Migrare le API di accesso', 'in_corso', { repo: ['api'] }),
      conRepo(2, 'Limitare i tentativi di accesso', 'da_fare', { repo: ['api'], stessoRepo: ['api'] }),
      conRepo(3, 'Nuova pagina del profilo', 'da_fare', { repo: ['web'] }),
      conRepo(4, 'Allineare API e pagina del profilo', 'da_fare', { repo: ['api', 'web', 'web'], stessoRepo: ['api'], obiettivo: 'club' }),
      conRepo(5, 'Notifiche sul telefono', 'da_fare', { repoIgnoti: ['mobile'] }),
      conRepo(6, 'Rivedere la guida del progetto', 'da_fare'),
      conRepo(7, 'Icona della app', 'fatto', { repo: ['app-mobile'] }),
    ] }, { nome: 'Prova un repo', tipo: 'progetto', priorita: 'bassa', haCartella: true, repo: ['sito'], task: [
      conRepo(8, 'Rifare la home del sito', 'in_corso'),
      conRepo(9, 'Aggiornare i testi del sito', 'da_fare', { stessoRepo: ['sito'] }),
    ] });
    // the same shape the server builds: task copies with their node, counts by visual state
    const obiettivo = (slug, titolo, definito) => {
      const ts = nodi.flatMap(n => n.task.filter(t => t.obiettivo === slug).map(t => ({ ...t, nodo: n.nome })));
      const quanti = st => ts.filter(t => statoVisivo(t) === st).length;
      return { slug, titolo, definito, progetti: [...new Set(ts.map(t => t.nodo))], task: ts, conteggi: { pronti: quanti('pronto'), in_corso: quanti('in_corso'), in_attesa: quanti('in_attesa'), fatti: quanti('fatto') } };
    };
    return {
      nodi, obiettivi: [obiettivo('club', 'Aprire ai primi Club <beta> & "amici" 🚀', true), obiettivo('linkedin', 'Pubblicare con costanza', true), obiettivo('radar', 'radar', false)],
      prossima: { nodo: 'Prova piena', ...task[0], motivo: 'in corso' }, conteggi: { da_fare: 11, in_corso: 2, in_ritardo: 1, pronti: 6, in_attesa: 5 },
    };
  }

  // ---- saluto ----
  // 32 caratteri al massimo, mai a metà parola (se non c'è uno spazio si tengono i 32), senza punteggiatura finale: il punto lo mette il saluto.
  const PAROLE_FUNZIONE = ['a', 'al', 'il', 'lo', 'la', 'le', 'i', 'gli', 'un', 'una', 'di', 'del', 'da', 'in', 'su', 'per', 'con', 'e', 'o', 'ma', 'che', 'nel', 'sul', 'dei', 'delle'];
  function brevePerSaluto(t) {
    if (t.length > 32) {
      const c = t.slice(0, 32);
      t = t[32] !== ' ' && c.includes(' ') ? c.slice(0, c.lastIndexOf(' ')) : c;
    }
    t = t.replace(/[\s,;:.…]+$/, '');
    const w = t.split(' ');
    while (w.length > 1 && PAROLE_FUNZIONE.includes(w[w.length - 1].toLowerCase())) w.pop();
    return w.join(' ').replace(/[\s,;:.…]+$/, '');
  }
  function saluto(ora) {
    const g = ora.getHours();
    const parola = g < 13 ? 'Buongiorno' : g < 18 ? 'Buon pomeriggio' : 'Buonasera';
    const p = dati && dati.prossima;
    const h1 = h('h1', 'saluto', [parola + (dati && dati.nome ? ', ' + dati.nome : '') + '. ' + (p ? 'Prossimo: ' + brevePerSaluto(p.vista) + '.' : 'Niente di aperto.')]);
    const c = dati ? dati.conteggi : { da_fare: 0, in_corso: 0, in_ritardo: 0, pronti: 0, in_attesa: 0 };
    const punto = (cl, n, testo) => h('span', 'conteggio', [h('i', 'punto ' + cl), h('b', '', [String(n)]), ' ' + testo]);
    $('mappa-saluto').replaceChildren(h1, h('p', 'saluto-sub', [
      ora.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' }),
      punto('st-pronto', c.pronti, c.pronti === 1 ? 'pronto' : 'pronti'), punto('st-in_corso', c.in_corso, 'in corso'), punto('st-in_attesa', c.in_attesa, 'in attesa'), punto('ritardo', c.in_ritardo, 'in ritardo'),
    ]));
  }

  // ---- layout a forze, deterministico: stessi dati, stessa mappa (angolo aureo, niente numeri casuali) ----
  // `alto`: the height taken by the goal band, the nodes stay below it
  function layout(nodi, W, H, alto) {
    const cy = (H + alto) / 2;
    const N = nodi.map((n, i) => {
      const a = i * 2.399, q = Math.min(W, H - alto) * 0.4 * Math.sqrt((i + 0.5) / nodi.length);
      return { n, x: W / 2 + Math.cos(a) * q, y: cy + Math.sin(a) * q, r: Math.min(60, 30 + 5 * aperti(n)) };
    });
    for (let passo = 0; passo < 300; passo++) {
      for (const a of N) {
        a.x += (W / 2 - a.x) * 0.004; a.y += (cy - a.y) * 0.004;
        for (const b of N) {
          if (a === b) continue;
          const dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy) || 1, min = a.r + b.r + 120;
          if (d < min) { const f = (min - d) / d * 0.25; a.x += dx * f; a.y += dy * f; }
        }
        a.x = Math.max(a.r + 40, Math.min(W - a.r - 40, a.x));
        a.y = Math.max(a.r + 70 + alto, Math.min(H - a.r - ((a.n.repo || []).length > 1 ? 72 : 56), a.y));   // the repo line needs room too
      }
    }
    return N;
  }
  function arco(cx, cy, r, a0, a1) {
    const p = a => `${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`;
    return `M${p(a0)}A${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${p(a1)}`;
  }

  // ---- zoom e spostamento: una trasformazione sul gruppo del mondo; il testo non scala (vedi --k nel CSS) ----
  let trascinato = false;   // vero dopo un trascinamento: il clic che lo segue non deve deselezionare
  function applicaVista() {
    const m = $('mappa-mondo');
    if (!m) return;
    m.setAttribute('transform', `translate(${vista.x.toFixed(1)} ${vista.y.toFixed(1)}) scale(${vista.k.toFixed(3)})`);
    $('mappa-svg').style.setProperty('--k', vista.k.toFixed(3));
  }
  function limita() {       // lascia sempre almeno 80px di mappa in vista
    const svg = $('mappa-svg'), W = svg.clientWidth, H = svg.clientHeight, m = 80;
    vista.x = Math.max(m - W * vista.k, Math.min(W - m, vista.x));
    vista.y = Math.max(m - H * vista.k, Math.min(H - m, vista.y));
  }
  function zoomA(fattore, cx, cy) {   // cx, cy: punto fermo, in pixel dell'SVG
    const k = Math.max(K_MIN, Math.min(K_MAX, vista.k * fattore)), f = k / vista.k;
    vista = { k, x: cx - (cx - vista.x) * f, y: cy - (cy - vista.y) * f };
    limita(); applicaVista();
  }
  function sposta(dx, dy) { vista.x += dx; vista.y += dy; limita(); applicaVista(); }
  function adatta() { vista = { k: 1, x: 0, y: 0 }; applicaVista(); }
  function zoomCentro(fattore) { const svg = $('mappa-svg'); zoomA(fattore, svg.clientWidth / 2, svg.clientHeight / 2); }
  function portaInVista(nome) {       // un nodo che prende il fuoco fuori dal riquadro viene portato al centro
    const p = pos.get(nome), svg = $('mappa-svg');
    if (!p) return;
    const x = p.x * vista.k + vista.x, y = p.y * vista.k + vista.y, W = svg.clientWidth, H = svg.clientHeight;
    if (x < p.r || x > W - p.r || y < p.r || y > H - p.r) { vista.x += W / 2 - x; vista.y += H / 2 - y; limita(); applicaVista(); }
  }
  function gesti(svg) {
    const punti = new Map();           // dita o mouse attivi: id -> ultimo punto
    let spostato = 0, daSfondo = false;
    svg.addEventListener('wheel', e => {
      if (!e.ctrlKey && (e.deltaY < 0 ? vista.k >= K_MAX : vista.k <= K_MIN)) return;   // al limite la rotella fa scorrere la pagina
      e.preventDefault();
      const r = svg.getBoundingClientRect(), d = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      zoomA(Math.exp(-d * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX - r.left, e.clientY - r.top);   // ctrlKey: pizzico sul trackpad
    }, { passive: false });
    svg.addEventListener('pointerdown', e => {
      if (e.button > 0) return;
      const sfondo = !e.target.closest('.nodo, .sat, .azione, .obiettivo');
      if (!punti.size) { trascinato = false; spostato = 0; daSfondo = sfondo; }
      if (!punti.size && !sfondo) return;   // un clic su un nodo resta un clic
      punti.set(e.pointerId, { x: e.clientX, y: e.clientY });
    });
    svg.addEventListener('pointermove', e => {
      const p = punti.get(e.pointerId);
      if (!p) return;
      const r = svg.getBoundingClientRect();
      if (punti.size === 1) {
        if (!daSfondo) return;
        const dx = e.clientX - p.x, dy = e.clientY - p.y;
        spostato += Math.abs(dx) + Math.abs(dy);
        p.x = e.clientX; p.y = e.clientY;
        if (spostato <= 4) return;        // sotto soglia è ancora un clic
        if (!trascinato) { trascinato = true; try { svg.setPointerCapture(e.pointerId); } catch (x) { /* puntatore già finito */ } }
        sposta(dx, dy);
      } else if (punti.size === 2) {      // pizzico: zoom sulla distanza, spostamento sul punto medio
        const a = [...punti.values()].find(q => q !== p), d0 = Math.hypot(p.x - a.x, p.y - a.y);
        const m0 = [(p.x + a.x) / 2 - r.left, (p.y + a.y) / 2 - r.top];
        p.x = e.clientX; p.y = e.clientY;
        const d1 = Math.hypot(p.x - a.x, p.y - a.y), m1 = [(p.x + a.x) / 2 - r.left, (p.y + a.y) / 2 - r.top];
        trascinato = true;
        sposta(m1[0] - m0[0], m1[1] - m0[1]);
        if (d0 > 0 && d1 > 0) zoomA(d1 / d0, m1[0], m1[1]);
      }
    });
    const fine = e => { punti.delete(e.pointerId); };
    svg.addEventListener('pointerup', fine);
    svg.addEventListener('pointercancel', fine);
    svg.addEventListener('lostpointercapture', fine);
    svg.addEventListener('keydown', e => {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === '+' || e.key === '=') zoomCentro(1.25);
      else if (e.key === '-' || e.key === '_') zoomCentro(0.8);
      else if (e.key === '0') adatta();
      else if (e.target === svg && e.key.startsWith('Arrow')) sposta(e.key === 'ArrowLeft' ? 60 : e.key === 'ArrowRight' ? -60 : 0, e.key === 'ArrowUp' ? 60 : e.key === 'ArrowDown' ? -60 : 0);   // sui nodi le frecce restano quelle di prima
      else return;
      e.preventDefault();
    });
  }

  // ---- filtri ----
  function visibili() {
    const toccati = filtro === 'obiettivi' ? new Set(obiettiviDi().flatMap(o => o.progetti)) : null;   // only the nodes a goal touches
    return dati.nodi.filter(n => filtro === 'progetti' ? n.tipo === 'progetto' : filtro === 'argomenti' ? n.tipo === 'argomento' : filtro === 'aperti' ? aperti(n) > 0 : toccati ? toccati.has(n.nome) : true);
  }
  const obiettiviVisibili = () => ['tutto', 'aperti', 'obiettivi'].includes(filtro) ? obiettiviDi() : [];

  // ---- disegno ----
  function disegna() {
    const svg = $('mappa-svg');
    if (!dati || !svg) return;
    const W = svg.clientWidth, H = svg.clientHeight;
    dimensione = W + 'x' + H;
    nodiSvg = new Map(); pos = new Map(); obiettiviSvg = new Map();
    const sfondo = s('rect', { class: 'mappa-sfondo', x: 0, y: 0, width: W, height: H });
    sfondo.addEventListener('pointerenter', () => { if (!fuocoNeiSatelliti()) apri(fissato); });
    sfondo.addEventListener('click', () => { if (!trascinato) deseleziona(); });
    // arrowhead of the dependency thread: a marker, so the path stays one element
    const freccia = s('marker', { id: 'mappa-freccia', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto' }, [s('path', { d: 'M0 0L10 5L0 10z' })]);
    svg.replaceChildren(s('defs', {}, [freccia]), sfondo);
    if (W < 2) return;                       // sotto i 760px l'SVG è nascosto: c'è la lista
    const mondo = s('g', { id: 'mappa-mondo' });   // tutto ciò che si zooma: nodi e satelliti
    svg.appendChild(mondo);
    const prossimo = dati.prossima && dati.prossima.nodo;
    // Goal band under the header: rounded boxes in rows, as many per row as the width allows; the nodes are laid out below it
    const obiettivi = obiettiviVisibili(), OB = { h: 58, gap: 12, min: 150, max: 220 };
    const testa = document.querySelector('.mappa-testa'), y0 = 26 + (testa ? testa.offsetHeight : 36);
    const colonne = Math.max(1, Math.floor((W - 40 + OB.gap) / (OB.min + OB.gap))), k = Math.min(obiettivi.length, colonne);
    const largo = k ? Math.min(OB.max, (W - 40 - (k - 1) * OB.gap) / k) : 0, x0 = (W - k * largo - (k - 1) * OB.gap) / 2;
    const fondoFascia = y0 + Math.ceil(obiettivi.length / colonne) * (OB.h + OB.gap) - OB.gap;
    const strato = s('g', { id: 'mappa-obiettivi' });   // first child of the world: the goal lines run under the nodes
    mondo.appendChild(strato);
    if (filtro === 'obiettivi' && !obiettiviDi().length) mondo.appendChild(s('text', { class: 'mappa-vuota', x: W / 2, y: H / 2 }, [NESSUN_OBIETTIVO]));
    // 70 is the room the layout already keeps for the header; past the band, 24 more for the halo
    for (const o of layout(visibili(), W, H, obiettivi.length ? fondoFascia + 24 - 70 : 0)) {
      const { n, x, y, r } = o;
      pos.set(n.nome, { x, y, r });
      const daDecidere = !!(n.harness && n.harness.stato === 'da decidere');   // contorno tratteggiato: manca la decisione sull'harness
      const repo = n.repo || [];
      const nota = (n.harness && n.harness.stato !== 'senza repo' ? ', harness ' + n.harness.stato : '') + (repo.length > 1 ? ', repo: ' + repo.join(', ') : '');
      const G = s('g', { class: 'nodo' + (n.nome === prossimo ? ' prossimo' : '') + (daDecidere ? ' harness-da-decidere' : ''), tabindex: 0, role: 'button', 'aria-label': n.nome + ', ' + contoAperti(n) + nota });
      G.append(s('title', {}, [n.nome + ': ' + contoAperti(n) + nota]), s('circle', { class: 'alone', cx: x, cy: y, r: r + 9 }), s('circle', { class: 'disco', cx: x, cy: y, r }));
      const tot = n.task.length;
      if (tot) {
        let a0 = -Math.PI / 2;
        for (const st of VISIVI) {
          const c = n.task.filter(t => statoVisivo(t) === st).length;
          if (!c) continue;
          if (c === tot) { G.append(s('circle', { class: 'arco st-' + st, cx: x, cy: y, r: r - 5 })); break; }
          const a1 = a0 + c / tot * 2 * Math.PI;
          G.append(s('path', { class: 'arco st-' + st, d: arco(x, y, r - 5, a0 + 0.03, a1 - 0.03), 'stroke-linecap': 'round' }));
          a0 = a1;
        }
      }
      // scarti in em: il testo non scala con lo zoom, quindi la distanza dal disco deve seguire la sua grandezza
      G.append(s('text', { class: 'num', x, y, dy: '0.35em' }, [String(pronti(n))]),
        s('text', { class: 'nome', x, y: y + r, dy: '1.55em' }, [taglia(n.nome, 22)]),
        s('text', { class: 'tipo', x, y: y + r, dy: '3.2em' }, [n.tipo === 'senza' ? 'da etichettare' : n.tipo]));
      // a node with more than one repo names them: three at most, the rest as «+k» (all of them are in the tooltip)
      if (repo.length > 1) G.append(s('text', { class: 'repo-nodo', x, y: y + r, dy: '4.8em' }, [repo.slice(0, 3).map(nomeRepo => taglia(nomeRepo, 14)).join(' · ') + (repo.length > 3 ? ' +' + (repo.length - 3) : '')]));
      if (haPiu(n)) G.append(piu(n, pos.get(n.nome)));
      G.addEventListener('pointerenter', () => apri(n.nome));
      G.addEventListener('focus', () => { if (G.matches(':focus-visible')) portaInVista(n.nome); apri(n.nome); });   // solo dalla tastiera: al clic il nodo si sposterebbe sotto il puntatore
      G.addEventListener('click', () => scegli(n.nome));
      G.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); scegli(n.nome); }
        if (e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); apri(n.nome); const primo = document.querySelector('#mappa-satelliti .sat[tabindex]'); if (primo) primo.focus(); }
      });
      nodiSvg.set(n.nome, G);
      mondo.appendChild(G);
    }
    const linee = [], scatole = [];
    obiettivi.forEach((o, i) => {
      const x = x0 + (i % colonne) * (largo + OB.gap), y = y0 + Math.floor(i / colonne) * (OB.h + OB.gap), ax = x + largo / 2, ay = y + OB.h;
      const sue = o.progetti.filter(nome => pos.has(nome)).map(nome => {   // a node hidden by the filter gets no line: the panel still lists its steps
        const p = pos.get(nome), d = Math.hypot(ax - p.x, ay - p.y) || 1;
        return s('line', { class: 'obiettivo-linea', x1: ax.toFixed(1), y1: ay.toFixed(1), x2: (p.x + (ax - p.x) / d * (p.r + 6)).toFixed(1), y2: (p.y + (ay - p.y) / d * (p.r + 6)).toFixed(1) });
      });
      const c = o.conteggi, tot = c.fatti + c.in_corso + c.pronti + c.in_attesa;
      const etichetta = o.titolo + ', obiettivo: ' + contoObiettivo(o) + (o.definito ? '' : ', non definito');
      const G = s('g', { class: 'obiettivo' + (o.definito ? '' : ' non-definito'), tabindex: 0, role: 'button', 'aria-label': etichetta });
      G.append(s('title', {}, [etichetta]), s('rect', { class: 'obiettivo-box', x, y, width: largo, height: OB.h, rx: 10 }),
        s('text', { class: 'obiettivo-titolo', x: x + 12, y: y + 21 }, [taglia(o.titolo, Math.floor((largo - 24) / 6.3))]));
      // progress: done, in progress, ready, waiting, with the strokes of the node rings (waiting dashed); the line below says it in words
      const bx = x + 12, bw = largo - 24, by = y + 33;
      G.append(s('path', { class: 'obiettivo-traccia', d: `M${bx} ${by}H${bx + bw}` }));
      let da = bx;
      for (const [st, quanti] of [['fatto', c.fatti], ['in_corso', c.in_corso], ['pronto', c.pronti], ['in_attesa', c.in_attesa]]) {
        if (!quanti) continue;
        const a = da + quanti / tot * bw;
        G.append(s('path', { class: 'arco st-' + st, d: `M${(da + 1).toFixed(1)} ${by}H${Math.max(da + 1, a - 1).toFixed(1)}` }));
        da = a;
      }
      G.append(s('text', { class: 'obiettivo-sub', x: x + 12, y: y + 50 }, [(o.definito ? '' : 'non definito · ') + (tot ? c.fatti + ' di ' + tot + ' fatti' : 'nessun passo')]));
      G.addEventListener('click', () => scegliObiettivo(o.slug));
      G.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); scegliObiettivo(o.slug); } });
      obiettiviSvg.set(o.slug, { G, linee: sue });
      linee.push(...sue); scatole.push(G);
    });
    strato.append(...linee, ...scatole);
    mondo.appendChild(s('g', { id: 'mappa-dipendenze' }));  // the thread of the selected waiting task, under the satellites
    mondo.appendChild(s('g', { id: 'mappa-satelliti' }));   // sempre ultimo: sta sopra tutti i nodi
    limita(); applicaVista();
    evidenziaObiettivo();
    const da = aperto; aperto = null; apri(da, true);
  }
  // A selected goal: its lines turn solid and the nodes it does not touch fade. Only classes, so the keyboard focus stays put.
  function evidenziaObiettivo() {
    const svg = $('mappa-svg');
    if (!svg) return;
    // Dim only when the selected goal is drawn: with a filter that hides goals the panel stays but the map must not stay faded
    const o = obiettiviVisibili().includes(obiettivoPer(fissato)) ? obiettivoPer(fissato) : undefined;
    svg.classList.toggle('con-obiettivo', !!o);
    for (const [slug, { G, linee }] of obiettiviSvg) {
      const su = !!o && o.slug === slug;
      G.classList.toggle('scelto', su);
      linee.forEach(l => l.classList.toggle('scelta', su));
    }
    for (const [nome, G] of nodiSvg) G.classList.toggle('coinvolto', !!o && o.progetti.includes(nome));
  }

  // satelliti del nodo aperto: tutti gli aperti, gli ultimi 2 fatti (in ordine di file) e «+k fatti»
  function voci(n) {
    const v = n.task.filter(t => t.stato !== 'fatto').map(t => ({ t, stato: statoVisivo(t) }));
    if (filtro === 'aperti') return v;
    const fatti = n.task.filter(t => t.stato === 'fatto');
    fatti.slice(-2).forEach(t => v.push({ t, stato: 'fatto' }));
    if (fatti.length > 2) v.push({ extra: fatti.length - 2, stato: 'fatto' });
    return v;
  }
  // Dove mettere i satelliti: a raggiera se c'è spazio per le etichette da entrambi i lati, altrimenti in colonna sul lato libero.
  function posizioni(m, p, W, H) {
    const out = [], libero = [p.x - p.r - 20, W - p.x - p.r - 20].map(v => v >= 200);   // [sinistra, destra]
    if (m <= 7 && libero[0] && libero[1]) {
      const R = p.r + 52;
      for (let i = 0; i < m; i++) { const a = -Math.PI / 2 + (i + 0.5) * 2 * Math.PI / m; out.push({ x: p.x + Math.cos(a) * R, y: p.y + Math.sin(a) * R, lato: Math.cos(a) >= 0 ? 1 : -1 }); }
    } else {                                  // colonne ad arco: le etichette non si toccano
      const lati = libero[0] === libero[1] ? [1, -1] : [libero[1] ? 1 : -1];
      const passo = Math.min(22, (H - 60) / Math.ceil(m / lati.length));
      const per = Math.ceil(m / lati.length);
      for (let i = 0; i < m; i++) {
        const lato = lati[Math.floor(i / per)], k = Math.min(per, m - Math.floor(i / per) * per), j = i % per;
        const dy = (j - (k - 1) / 2) * passo, Rs = Math.max(p.r + 70, (k - 1) * passo / 2 + 45);
        out.push({ x: p.x + lato * Math.sqrt(Math.max(Rs * Rs - dy * dy, 400)), y: p.y + dy, lato });
      }
    }
    const su = Math.min(...out.map(o => o.y)), giu = Math.max(...out.map(o => o.y));
    const sposta = su < 22 ? 22 - su : giu > H - 22 ? H - 22 - giu : 0;
    for (const o of out) { o.y += sposta; o.x = Math.max(16, Math.min(W - 16, o.x)); o.spazio = o.lato > 0 ? W - 8 - o.x - 13 : o.x - 8 - 13; }
    return out;
  }
  function disegnaSatelliti(nome) {
    const strato = $('mappa-satelliti'), n = nodoPer(nome), p = pos.get(nome);
    if (!strato) return;
    if (!n || !p) { strato.replaceChildren(); return; }
    const lista = voci(n), svg = $('mappa-svg');
    const posiz = posizioni(lista.length, p, svg.clientWidth, svg.clientHeight);
    const fili = [], sat = [], zona = s('g', { class: 'zona' });
    const R0 = p.r + 14;
    zona.append(s('path', { 'fill-rule': 'evenodd', d: `M${p.x - R0} ${p.y}a${R0} ${R0} 0 1 0 ${2 * R0} 0a${R0} ${R0} 0 1 0 ${-2 * R0} 0M${p.x - p.r + 1} ${p.y}a${p.r - 1} ${p.r - 1} 0 1 0 ${2 * p.r - 2} 0a${p.r - 1} ${p.r - 1} 0 1 0 ${-2 * p.r + 2} 0` }));
    lista.forEach((v, i) => {
      const q = posiz[i], d = Math.hypot(q.x - p.x, q.y - p.y) || 1;
      fili.push(s('line', { class: 'filo', x1: p.x + (q.x - p.x) / d * (p.r + 6), y1: p.y + (q.y - p.y) / d * (p.r + 6), x2: q.x, y2: q.y }));
      const testo = v.t ? v.t.vista : '+' + v.extra + ' fatti', perche = v.t ? motivi(v.t, n) : [];
      const G = s('g', { class: 'sat st-' + v.stato + (v.t && v.t.ritardo ? ' ritardo' : '') + (v.t && v.t.derivato === 'errore' ? ' errore' : ''), transform: `translate(${q.x.toFixed(1)} ${q.y.toFixed(1)})` });
      const dentro = s('g', { class: 'sat-dentro' });
      const etichetta = taglia(testo, Math.max(6, Math.min(26, Math.floor(q.spazio / 6.3)))), larg = 18 + etichetta.length * 6.3;
      zona.append(s('line', { x1: p.x + (q.x - p.x) / d * p.r, y1: p.y + (q.y - p.y) / d * p.r, x2: q.x, y2: q.y, 'stroke-width': 28 }), s('rect', { x: q.lato > 0 ? q.x - 12 : q.x - larg, y: q.y - 12, width: larg + 12, height: 24 }));
      dentro.append(s('circle', { class: 'sat-punto', r: v.t ? 7 : 5 }),
        s('text', { dx: (q.lato * 1.1) + 'em', dy: '0.33em', 'text-anchor': q.lato > 0 ? 'start' : 'end' }, [etichetta]));
      G.append(s('title', {}, [[testo, ...perche].join('\n')]), dentro);
      if (v.t) {
        G.setAttribute('tabindex', 0); G.setAttribute('role', 'button'); G.setAttribute('aria-label', [testo, NOME_VISIVO[v.stato], ...perche].join(', '));
        if (v.t.id) G.setAttribute('data-id', v.t.id);   // the thread finds a blocker in the same node by id
        G.addEventListener('click', e => { e.stopPropagation(); scegliTask(nome, v.t); });
        G.addEventListener('keydown', e => {
          const tutti = [...strato.querySelectorAll('.sat[tabindex]')], k = tutti.indexOf(G);
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); scegliTask(nome, v.t); }
          else if (e.key === 'ArrowLeft' || e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); nodiSvg.get(nome).focus(); }
          else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); const a = tutti[k + (e.key === 'ArrowDown' ? 1 : -1)]; if (a) a.focus(); }
        });
      }
      sat.push(G);
    });
    strato.replaceChildren(zona, ...fili, ...sat, ...(haPiu(n) ? [piu(n, p)] : []));   // la zona trasparente tiene aperto il nodo finché il puntatore va verso i satelliti
    filo();
  }

  // Thread of the selected waiting task: an arrow from every other node it waits on, and `bloccante` on the blockers
  // in its own node. Never all threads at once. Redrawn from scratch on every selection change and redraw: O(blockers).
  function filo() {
    for (const el of document.querySelectorAll('#mappa-svg .bloccante')) el.classList.remove('bloccante');
    const strato = $('mappa-dipendenze');
    if (!strato) return;                     // narrow screen: no SVG, the panel and the list say it in words
    strato.replaceChildren();
    const n = selezione && nodoPer(fissato), t = n && n.task.find(x => x.testo === selezione.testo && x.data === selezione.data);
    const q = t && statoVisivo(t) !== 'fatto' && pos.get(n.nome);
    if (!q) return;
    const sat = aperto === n.nome ? [...document.querySelectorAll('#mappa-satelliti .sat[data-id]')] : [];
    const altri = new Set();
    for (const a of t.aspetta) {
      if (a.nodo !== n.nome) { altri.add(a.nodo); continue; }
      const g = sat.find(x => x.getAttribute('data-id') === a.id);
      if (g) g.classList.add('bloccante');
    }
    for (const nome of altri) {
      const p = pos.get(nome);
      if (!p) continue;                      // node filtered out: the panel still names it
      nodiSvg.get(nome).classList.add('bloccante');
      const dx = q.x - p.x, dy = q.y - p.y, cx = (p.x + q.x) / 2 - dy * 0.2, cy = (p.y + q.y) / 2 + dx * 0.2;   // a gentle bend
      const bordo = (o, r) => { const ex = cx - o.x, ey = cy - o.y, e = Math.hypot(ex, ey) || 1; return (o.x + ex / e * r).toFixed(1) + ' ' + (o.y + ey / e * r).toFixed(1); };
      strato.append(s('path', { class: 'dipendenza', d: `M${bordo(p, p.r + 6)}Q${cx.toFixed(1)} ${cy.toFixed(1)} ${bordo(q, q.r + 10)}`, 'marker-end': 'url(#mappa-freccia)' }));
    }
  }

  const fuocoNeiSatelliti = () => { const e = document.activeElement; return !!(e && e.closest && e.closest('#mappa-satelliti')); };

  // un solo nodo aperto: aprirne uno chiude il precedente; i satelliti si disegnano una volta sola
  function apri(nome, forza) {
    if (!forza && aperto === nome) return;
    if (aperto && nodiSvg.has(aperto)) nodiSvg.get(aperto).classList.remove('aperto');
    aperto = nodiSvg.has(nome) ? nome : null;
    $('mappa-svg').classList.toggle('focus', !!aperto);
    if (aperto) nodiSvg.get(aperto).classList.add('aperto');
    disegnaSatelliti(aperto);
  }
  function scegli(nome) { if (fissato !== nome) filtroRepo = null; fissato = nome; selezione = null; apri(nome); pannello(); }
  function scegliObiettivo(slug) { fissato = PREFISSO_OBIETTIVO + slug; selezione = null; apri(null); pannello(); }
  // fissa il nodo, seleziona il task e porta il pannello su di lui: la lista dei task può essere più lunga del pannello
  function scegliTask(nome, t) {
    if (fissato !== nome || (filtroRepo && !tocca(t, filtroRepo.repo))) filtroRepo = null;   // a task the filter hides could not be scrolled to
    fissato = nome; selezione = t; apri(nome); pannello();
    const d = $('mappa-dettaglio'), el = d.querySelector('.task.scelto');
    if (el) d.scrollTop += el.getBoundingClientRect().top - d.getBoundingClientRect().top - (d.clientHeight - el.offsetHeight) / 2;
  }
  function deseleziona() { fissato = null; selezione = null; apri(null); pannello(); }

  // ---- lista equivalente (lettori di schermo; sotto i 760px prende il posto della mappa) ----
  // one task of the list, for nodes and goals alike; under a goal the row also names its node
  function rigaLista(n, t, conNodo) {
    return h('li', 'task-lista st-' + statoVisivo(t) + (t.derivato === 'errore' ? ' errore' : ''), [
      h('i', 'punto st-' + statoVisivo(t)), bottone(t.vista, 'link' + (t.ritardo ? ' ritardo' : ''), () => { scegliTask(n.nome, t); $('mappa-dettaglio').scrollIntoView({ block: 'nearest' }); }),
      h('span', 'sub', [NOME_VISIVO[statoVisivo(t)] + (t.data ? ' · ' + giornoBreve(t.data) : '') + (conNodo ? ' · ' + n.nome : '')]),
      ...motivi(t, n).map(m => h('span', 'sub motivo', [m])),
      ...segniRepo(t),
    ]);
  }
  function lista() {
    const ul = $('mappa-lista');
    if (!ul || !dati) return;
    const daMostrare = ts => filtro === 'aperti' ? ts.filter(t => t.stato !== 'fatto') : ts;
    const obiettivi = obiettiviVisibili().map(o => h('li', '', [
      h('h3', '', [o.titolo, h('span', 'tipo-nodo', [o.definito ? 'obiettivo' : 'obiettivo non definito']), h('span', 'sub', [contoObiettivo(o)])]),
      ...(o.task.length ? gruppi(daMostrare(o.task), t => rigaLista(nodoPer(t.nodo), t, true), 'h4') : [h('p', 'vuoto', [NESSUN_PASSO])]),
    ]));
    const senza = filtro === 'obiettivi' && !obiettiviDi().length ? [h('li', 'vuoto', [NESSUN_OBIETTIVO])] : [];
    ul.replaceChildren(...obiettivi, ...senza, ...visibili().map(n => h('li', '', [
      h('h3', '', [n.nome, h('span', 'tipo-nodo', [n.tipo === 'senza' ? 'da etichettare' : n.tipo]), h('span', 'sub', [contoAperti(n)])]),
      ...gruppi(daMostrare(n.task), t => rigaLista(n, t), 'h4'),
    ])));
  }

  // ---- pannello: prossima azione oppure dettaglio del nodo fissato ----
  function selettore(n, t) {
    return h('span', 'stati', STATI.map(st => {
      const b = bottone(NOME_STATO[st], 'stato st-' + st, () => cambia(n, t, st));
      b.setAttribute('aria-pressed', String(t.stato === st));
      return b;
    }));
  }
  const apriPost = () => { const b = document.querySelector('.schede button[data-vista="post"]'); if (b) b.click(); };   // le bozze si decidono in Post, non da qui
  // `conNodo`: in a goal panel the row names its node; `n` is always the task's own node, so «Avvia» picks among that project's repos
  function rigaTask(n, t, conNodo) {
    const sel = selezione && selezione.testo === t.testo && selezione.data === t.data;
    const vis = statoVisivo(t), tuo = t.chi === 'te' && (t.derivato === 'pronto' || t.derivato === 'in_corso');
    const li = h('li', 'task st-' + vis + (t.derivato === 'incoerente' ? ' incoerente' : '') + (t.derivato === 'errore' ? ' errore' : '') + (sel ? ' scelto' : ''), [
      h('span', 'task-testo' + (t.ritardo ? ' ritardo' : ''), [h('i', 'punto st-' + vis), t.vista, t.data ? h('span', 'sub', [' ' + (t.ritardo ? 'dal ' : '') + giornoBreve(t.data)]) : null]),
      conNodo ? h('span', 'sub', [n.nome]) : null,
      ...motivi(t, n).map(m => h('span', 'sub motivo', [m])),
      ...segniRepo(t, !conNodo && !!repoFiltrato(n)),
      h('span', 'riga-azioni', t.bozza ? [bottone('Apri in Post', '', apriPost)] : [selettore(n, t),
        n.haCartella && avviabile(t) ? bottone(t.derivato === 'in_corso' ? 'Riavvia' : 'Avvia', '', () => conferma(n, t)) : tuo ? h('span', 'sub tocca-a-te', ['Tocca a te']) : null]),
    ]);
    if (sel) li.setAttribute('aria-current', 'true');
    return li;
  }
  // The repo the fixed node's panel is filtered on, or null: a filter of another node, or on a repo that is gone, does not apply
  const repoFiltrato = n => filtroRepo && filtroRepo.nodo === n.nome && (n.repo || []).includes(filtroRepo.repo) ? filtroRepo.repo : null;
  // «tutti / <repo>…» above the tasks of a node with more than one repo; the redraw keeps the focus on the pressed button
  function filtroPerRepo(n, attivo) {
    return h('div', 'scelta minore filtro-repo', [null, ...n.repo].map(r => {
      const b = bottone(r === null ? 'tutti' : taglia(r, 24), '', () => {
        filtroRepo = r === null ? null : { nodo: n.nome, repo: r };
        pannello();
        const su = document.querySelector('#mappa-dettaglio .filtro-repo [aria-pressed="true"]');
        if (su) su.focus();
      });
      b.setAttribute('aria-pressed', String(r === attivo));
      return b;
    }), { role: 'group', 'aria-label': 'Filtro per repo' });
  }
  function dettaglioNodo(n) {
    const p = n.tipo === 'progetto' ? progetti.find(x => x.nome.toLowerCase() === n.nome.toLowerCase()) : null;
    const repo = repoFiltrato(n), mostrati = repo ? n.task.filter(t => tocca(t, repo)) : n.task;
    const c = p && p.attivita && p.attivita.commit && p.attivita.commit[0];
    const avviabili = n.task.filter(avviabile), da = avviabili.find(t => t.derivato === 'in_corso') || avviabili.find(t => t.derivato === 'pronto');   // «Avvia» parte dal passo già in corso, poi dal primo pronto non tuo
    const fermo = !da && n.task.find(t => t.derivato === 'in_attesa' && t.aspetta.length);   // nothing to launch: say what the node waits for
    return [
      h('h2', '', [n.nome, h('span', 'sub', [n.tipo === 'senza' ? 'da etichettare' : n.tipo + (n.priorita ? ' · priorità ' + n.priorita : '')])]),
      n.task.length ? h('p', 'sub conto-nodo', [contoAperti(n)]) : null,   // con zero task lo dice già il paragrafo vuoto sotto
      n.tipo === 'progetto' && n.haCartella ? sceltaPriorita(n) : null,   // i progetti del lavoro non hanno cartella: la loro riga non si tocca
      n.tipo === 'progetto' && n.haCartella && n.harness ? bloccoHarness(n) : null,   // solo se il modulo dell'harness è acceso: senza, il server non manda il campo
      p && p.doveSono ? h('p', 'dove-sono', [h('b', '', ['Dove sono ']), taglia(p.doveSono, 260)]) : null,
      c ? h('p', 'sub', ['Ultimo commit: ' + taglia(c.messaggio, 80) + (c.ramo ? ' (' + c.ramo + ')' : '')]) : null,
      n.task.length && (n.repo || []).length > 1 ? filtroPerRepo(n, repo) : null,
      ...(n.task.length ? gruppi(mostrati, t => rigaTask(n, t), 'h3') : [h('p', 'vuoto', [n.nome === 'Social' ? 'Nessuna bozza da pubblicare.' : 'Nessun task nel piano con questo tag.'])]),
      n.task.length && !mostrati.length ? h('p', 'vuoto', ['Nessun task per ' + repo + '.']) : null,
      fermo ? h('p', 'sub', ['Niente da avviare: aspetta ' + bloccante(fermo.aspetta[0], n) + '.']) : null,
      h('div', 'riga-azioni', [
        da && n.haCartella ? bottone(da.stato === 'in_corso' ? 'Riavvia in Claude' : 'Avvia in Claude', 'primario', () => conferma(n, da)) : null,
        puoAggiungere(n) ? bottone('Aggiungi un task', '', () => nuovoTask(n)) : null,
        bottone('Torna alla prossima azione', '', deseleziona),
      ]),
    ];
  }
  // Panel of a goal: its steps across projects, in the same groups as a node
  function dettaglioObiettivo(o) {
    return [
      h('h2', '', [o.titolo, h('span', 'sub', ['obiettivo' + (o.progetti.length ? ' · ' + o.progetti.join(', ') : '')])]),
      o.task.length ? h('p', 'sub conto-nodo', [contoObiettivo(o)]) : null,
      o.definito ? null : h('p', 'sub', ['Obiettivo non definito. Aggiungilo in docs/obiettivi.md con la riga «- ' + o.slug + ': <titolo>».']),
      ...(o.task.length ? gruppi(o.task, t => rigaTask(nodoPer(t.nodo), t, true), 'h3') : [h('p', 'vuoto', [NESSUN_PASSO])]),
      h('div', 'riga-azioni', [bottone('Torna alla prossima azione', '', deseleziona)]),
    ];
  }
  function prossimaAzione() {
    const p = dati.prossima;
    if (!p) return [h('h2', '', ['Prossima azione']), h('p', 'vuoto', ['Niente di aperto.'])].concat(harnessDaDecidere());
    const n = nodoPer(p.nodo);
    const t = n && n.task.find(x => x.testo === p.testo && x.data === p.data);
    return [
      h('h2', '', ['Prossima azione']),
      h('div', 'dove', [h('i', 'punto st-' + (p.stato === 'da_fare' ? 'pronto' : p.stato)), p.nodo + ' · ' + p.motivo]),
      h('p', 'titolo-azione', [p.vista]),
      t ? h('div', 'riga-azioni', [
        n.haCartella && avviabile(t) ? bottone(t.derivato === 'in_corso' ? 'Riavvia in Claude' : 'Avvia in Claude', 'primario', () => conferma(n, t)) : null,
        bottone('Fatto', '', () => cambia(n, t, 'fatto')),
      ]) : null,
    ].concat(harnessDaDecidere());
  }
  // ---- harness per agenti: la decisione sta nello STATE del progetto, lo stato lo legge il server dal repo ----
  // I progetti con un repo e senza una decisione restano qui finché non rispondi: un silenzio non vale come un no.
  function harnessDaDecidere() {
    const nomi = dati.harness && dati.harness.attivo ? dati.harness.daDecidere || [] : [];
    if (!nomi.length) return [];
    return [
      h('h2', 'harness-titolo', ['Harness da decidere']),
      h('p', 'sub', ['Progetti con un repo e senza una decisione: adeguarli all\'harness per agenti, oppure no.']),
      h('ul', 'harness-elenco', nomi.map(nome => h('li', '', [bottone(nome, 'link', () => scegli(nome))]))),
    ];
  }
  function bloccoHarness(n) {
    const a = n.harness, r = a.report;
    if (a.stato === 'senza repo') return null;   // senza un repo non c'è niente da adeguare
    const testo = 'Harness: ' + a.stato
      + (r ? ' · ' + r.pass + ' PASS, ' + r.fail + ' FAIL (' + r.fail_alta + ' alti), report del ' + giornoBreve(r.data) : '')
      + (a.stato === 'escluso' && a.data ? ' dal ' + giornoBreve(a.data) : '');
    return h('div', 'harness', [
      h('p', 'sub harness-stato', [testo]),
      a.decisione === 'adeguare' ? h('p', 'sub', ['Nel repo del progetto lancia /ai-native-harness:audit per misurarlo.']) : null,
      h('div', 'scelta minore', [
        a.decisione !== 'adeguare' ? bottone('Adegua all\'harness', '', () => decidiHarness(n, 'adeguare')) : null,
        a.decisione !== 'non adeguare' ? bottone('Non adeguare questo progetto', '', () => decidiHarness(n, 'non adeguare')) : null,
      ], { role: 'group', 'aria-label': 'Harness del progetto' }),
    ]);
  }
  // scrive la riga `- **Harness:**` nello STATE del progetto; il server controlla di nuovo progetto e valore
  function decidiHarness(n, decisione) {
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    const adegua = decisione === 'adeguare';
    const d = dialogo('mappa-harness', 'Harness del progetto');
    const ok = bottone(adegua ? 'Adegua' : 'Non adeguare', 'primario', async () => {
      ok.disabled = true;
      try {
        const r = await invia('/api/mappa/harness', { nome: n.nome, decisione });
        d.close();
        if (!r.ok) return errore(r);
        toast(adegua ? 'Segnato. Nel repo lancia /ai-native-harness:audit.' : n.nome + ': non verrà adeguato all\'harness.');
        await carica();
      } catch (e) { d.close(); toast('Non è andata: ' + e.message); }
    });
    d.replaceChildren(h('form', '', [
      h('h2', '', [adegua ? 'Adegua all\'harness' : 'Non adeguare questo progetto']),
      h('p', 'sub', ['Progetto: ' + n.nome]),
      h('p', 'sub', [adegua
        ? 'Segno la decisione nello STATE del progetto. L\'audit lo lanci tu nel repo con /ai-native-harness:audit: esegue i check del progetto, quindi solo su un repo di cui ti fidi.'
        : 'Segno il rifiuto nello STATE, con la data di oggi. Il progetto esce dall\'elenco di quelli da decidere. Puoi cambiare idea da qui quando vuoi.']),
      h('div', 'riga-azioni', [ok, bottone('Annulla', '', () => d.close())]),
    ], { method: 'dialog' }));
    d.showModal();
  }
  function pannello() {
    if (!dati || !$('mappa-dettaglio')) return;
    const o = obiettivoPer(fissato), n = fissato && nodoPer(fissato);
    $('mappa-dettaglio').replaceChildren(...(o ? dettaglioObiettivo(o) : n ? dettaglioNodo(n) : prossimaAzione()).filter(Boolean));
    // le righe in ritardo dei prossimi giorni
    const g = giorni.slice(0, 5);
    $('prossimi-giorni').replaceChildren(...(g.length ? [h('h2', '', ['Prossimi giorni']), h('ul', 'prossimi', g.map(v => h('li', '', [
      h('span', '', [v.vista || v.testo]), h('span', 'quando' + (v.inRitardo ? ' ritardo' : ''), [v.inRitardo ? 'dal ' + giornoBreve(v.data) : giornoBreve(v.data)]),
    ])))] : []));
    filo(); evidenziaObiettivo();
  }

  // ---- azioni ----
  let timerToast = null;
  function toast(testo) {
    let t = $('mappa-toast');
    if (!t) { t = h('div', 'toast', [], { id: 'mappa-toast', role: 'status' }); document.body.appendChild(t); }
    t.textContent = testo; t.hidden = false;
    clearTimeout(timerToast);
    timerToast = setTimeout(() => { t.hidden = true; }, 4500);
  }
  async function invia(percorso, corpo) {
    const r = await fetch(percorso, { method: 'POST', headers: { 'X-Azione': 'conferma', 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
    let json = {};
    try { json = await r.json(); } catch (e) { /* risposta senza corpo */ }
    return { ok: r.ok, stato: r.status, json };
  }
  const ERRORI_409 = {
    doppia: 'Due voci uguali in piano.md: correggi in Obsidian.',
    cartella: 'Cartella non valida per questo task.',
    repo: 'Quel repo non è tra quelli del progetto.',
    scegli_repo: 'Scegli il repo in cui avviare.',
    ripetuto: 'Già avviato: guarda il Terminale.',
    in_attesa: 'Questo task aspetta altri task: si avvia quando sono fatti.',
    tuo: 'Questo task tocca a te: Claude non lo avvia.',
    apertura: 'Non sono riuscito ad aprire il Terminale.',
    esiste: 'Esiste già un progetto con questo nome.',
    template: 'Mancano templates/STATE.md o templates/project-index-row.md.',
    riga: 'La riga del progetto in INDEX.md non si legge: correggi in Obsidian.',
    errore: 'Non è andata: riprova o guarda il log della dashboard.',
    spento: 'Il modulo dell\'harness non è attivo in config.json.',
    'senza-repo': 'Questo progetto non ha un repo: non c\'è niente da adeguare.',
    righe: 'Lo STATE del progetto è già a 20 righe: accorcialo, poi riprova.',
  };
  function errore(r) {
    if (r.stato === 404) { toast('La voce è cambiata, ricarico.'); carica(); }
    else if (r.stato === 409) toast(ERRORI_409[r.json && r.json.errore] || ERRORI_409.doppia);
    else if (r.stato === 501) toast('Avvio disponibile solo su macOS e Windows.');
    else toast('Non è andata: errore ' + r.stato + '.');
  }
  const inProva = () => !!new URLSearchParams(location.search).get('prova');
  async function cambia(n, t, stato) {
    if (t.stato === stato) return;
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    try {
      const r = await invia('/api/mappa/stato', { data: t.data, testo: t.testo, stato });
      if (!r.ok) return errore(r);
      toast(stato === 'fatto' ? (n.tipo === 'senza' ? 'Fatto. Era senza nodo.' : 'Fatto.') : stato === 'in_corso' ? 'In corso.' : 'Da fare.');
      if (stato === 'fatto' && selezione === t) selezione = null;
      await carica();
    } catch (e) { toast('Non è andata: ' + e.message); }
  }
  function dialogo(id, etichetta) {
    let d = $(id);
    if (!d) { d = h('dialog', '', [], { id, 'aria-label': etichetta }); document.body.appendChild(d); }
    return d;
  }
  // aggiunge `- [ ] #<nome del nodo> testo` a piano.md; il server controlla di nuovo lunghezza, a capo e < >
  const TESTO_MASSIMO = 200;
  function nuovoTask(n) {
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    const d = dialogo('mappa-nuovo', 'Aggiungi un task');
    const campo = h('input', '', [], { type: 'text', maxlength: String(TESTO_MASSIMO), required: '', autocomplete: 'off', 'aria-label': 'Testo del task' });
    const aggiungi = bottone('Aggiungi', 'primario', () => {});
    aggiungi.type = 'submit';
    campo.addEventListener('input', () => campo.setCustomValidity(/[<>]/.test(campo.value) ? 'Niente < e >.' : ''));
    const form = h('form', '', [
      h('h2', '', ['Aggiungi un task']),
      h('p', 'sub', ['Nodo: ' + n.nome + '. Si scrive in docs/piano.md come #' + n.nome + '.']),
      campo,
      h('div', 'riga-azioni', [aggiungi, bottone('Annulla', '', () => d.close())]),
    ]);
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const testo = campo.value.trim();
      if (!testo || !form.reportValidity()) return;
      aggiungi.disabled = true;
      try {
        const r = await invia('/api/mappa/nuovo', { tag: n.nome, testo });
        d.close();
        if (r.stato === 409) return toast('C\'è già un task uguale.');
        if (r.stato === 400) return toast('Testo non valido: niente a capo né < >, al massimo ' + TESTO_MASSIMO + ' caratteri.');
        if (!r.ok) return errore(r);
        toast('Aggiunto a ' + n.nome + '.');
        await carica();
        const nuovo = nodoPer(n.nome), grezzo = String(r.json.riga || '').slice(6);
        const t = nuovo && nuovo.task.find(x => x.data === null && x.testo === grezzo);
        if (t) scegliTask(n.nome, t);
      } catch (x) { d.close(); toast('Non è andata: ' + x.message); }
    });
    d.replaceChildren(form);
    d.showModal();
    campo.focus();
  }
  // scrive alta, media o bassa nella riga del progetto in projects/INDEX.md
  const PRIORITA = ['alta', 'media', 'bassa'];
  function sceltaPriorita(n) {
    return h('div', 'scelta minore', PRIORITA.map(p => {
      const b = bottone(p, '', () => cambiaPriorita(n, p));
      b.setAttribute('aria-pressed', String(n.priorita === p));
      return b;
    }), { role: 'group', 'aria-label': 'Priorità del progetto' });
  }
  async function cambiaPriorita(n, priorita) {
    if (n.priorita === priorita) return;
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    try {
      const r = await invia('/api/mappa/priorita', { nome: n.nome, priorita });
      if (!r.ok) return errore(r);
      toast('Priorità di ' + n.nome + ': ' + priorita + '.');
      await carica();
    } catch (e) { toast('Non è andata: ' + e.message); }
  }
  // crea projects/<nome>/STATE.md e la riga in INDEX.md, come /nuovo-progetto; il server controlla di nuovo ogni campo
  const CAMPO_NON_VALIDO = {
    nome: 'Nome non valido: solo lettere minuscole, cifre e trattini.',
    repo: 'Repo non valido: serve il percorso assoluto di una cartella con un repo git.',
    stack: 'Stack non valido: una riga sola, senza | < >.',
    priorita: 'Priorità non valida.',
    harness: 'Con un repo va scelto cosa fare dell\'harness: anche «da decidere» è una risposta.',
  };
  function nuovoProgetto() {
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    const d = dialogo('mappa-progetto', 'Nuovo progetto');
    const campo = (etichetta, attr) => {
      const i = h('input', '', [], Object.assign({ type: 'text', autocomplete: 'off' }, attr));
      return [h('label', '', [etichetta, i]), i];
    };
    const [rigaNome, nome] = campo('Nome', { required: '', maxlength: '60', pattern: '[a-z0-9][a-z0-9-]*', title: 'Lettere minuscole, cifre e trattini', placeholder: 'il-mio-progetto' });
    const [rigaRepo, repo] = campo('Repo (facoltativo)', { maxlength: '400', placeholder: 'Percorso assoluto della cartella del repo' });
    const [rigaStack, stack] = campo('Stack (facoltativo)', { maxlength: String(TESTO_MASSIMO), placeholder: 'TypeScript, Fastify, Postgres' });
    const priorita = h('select', '', [h('option', '', ['da decidere'], { value: '' })].concat(PRIORITA.map(p => h('option', '', [p], { value: p }))));
    // Con il modulo dell'harness acceso un progetto con un repo nasce con una decisione: il rifiuto si sceglie per esteso
    const conHarness = !!(dati && dati.harness && dati.harness.attivo);
    const harness = h('select', '', [
      h('option', '', ['scegli…'], { value: '' }),
      h('option', '', ['Adegua all\'harness'], { value: 'adeguare' }),
      h('option', '', ['Non adeguare questo progetto'], { value: 'non adeguare' }),
      h('option', '', ['Da decidere più avanti'], { value: 'da decidere' }),
    ]);
    const crea = bottone('Crea', 'primario', () => {});
    crea.type = 'submit';
    const form = h('form', '', [
      h('h2', '', ['Nuovo progetto']),
      h('p', 'sub', ['Crea projects/<nome>/STATE.md e la riga in INDEX.md. Non per i progetti di lavoro.']),
      rigaNome, rigaRepo, rigaStack, h('label', '', ['Priorità', priorita]),
      conHarness ? h('label', '', ['Harness (se indichi un repo)', harness]) : null,
      h('div', 'riga-azioni', [crea, bottone('Annulla', '', () => d.close())]),
    ]);
    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (!form.reportValidity()) return;
      if (conHarness && repo.value.trim() && !harness.value) { harness.focus(); return toast(CAMPO_NON_VALIDO.harness); }
      crea.disabled = true;
      try {
        const r = await invia('/api/mappa/progetto', { nome: nome.value.trim(), repo: repo.value.trim(), stack: stack.value.trim(), priorita: priorita.value, harness: harness.value || null });
        if (r.stato === 400) { crea.disabled = false; return toast(CAMPO_NON_VALIDO[r.json && r.json.errore] || 'Dati non validi.'); }   // il dialogo resta aperto: si corregge il campo
        d.close();
        if (!r.ok) return errore(r);
        toast('Progetto ' + r.json.nome + ' creato.');
        await carica();
        if (nodoPer(r.json.nome)) scegli(r.json.nome);
      } catch (x) { d.close(); toast('Non è andata: ' + x.message); }
    });
    d.replaceChildren(form);
    d.showModal();
    nome.focus();
  }
  // Where «Avvia» opens, mirroring the server: the task's distinct valid repos, else every repo of its project. One is used
  // as it is, more ask for a choice, none keeps the node's folder. The dialog shows repo names only, never a path.
  // `ripresa`: the server asked for a choice this data did not foresee (the plan changed): with fewer than two, offer the project's repos.
  function conferma(n, t, ripresa) {
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    t = n.task.find(x => x.data === t.data && x.testo === t.testo) || t;   // the Agenda passes a bare task: the node's own has the repos
    const validi = [...new Set(t.repo || [])];
    let candidati = validi.length ? validi : n.repo || [];
    if (ripresa && candidati.length < 2) candidati = n.repo || [];
    const d = dialogo('mappa-avvia', 'Avvia in Claude');
    const radio = candidati.length > 1 ? candidati.map(r => h('input', '', [], { type: 'radio', name: 'repo', value: r })) : [];
    const avvia = bottone('Avvia', 'primario', async () => {
      const repo = radio.length ? (radio.find(x => x.checked) || {}).value : candidati[0];
      if (radio.length && !repo) return;
      avvia.disabled = true;
      try {
        const r = await invia('/api/mappa/avvia', { data: t.data, testo: t.testo, repo: repo || null });
        if (r.stato === 409 && r.json && r.json.errore === 'scegli_repo' && !ripresa) {   // ask on fresh data instead of a dead toast
          d.close(); toast(ERRORI_409.scegli_repo);
          await carica();
          return conferma(nodoPer(n.nome) || n, t, true);
        }
        d.close();
        if (!r.ok) return errore(r);
        toast(r.json && r.json.avviso ? 'Terminale aperto, ma non ho potuto segnare «in corso».' : 'Claude avviato nel Terminale.');
        await carica();
      } catch (e) { d.close(); toast('Non è andata: ' + e.message); }
    });
    const annulla = bottone('Annulla', '', () => d.close());
    avvia.disabled = radio.length > 0;   // nothing is picked for you
    radio.forEach(x => x.addEventListener('change', () => { avvia.disabled = false; }));
    d.replaceChildren(h('form', '', [
      h('h2', '', ['Avvia in Claude']),
      h('p', 'sub', ['Si apre il Terminale con una sessione di Claude.']),
      h('p', 'sub', ['Nodo: ' + n.nome]),
      candidati.length === 1 ? h('p', 'sub', ['Repo: ' + candidati[0]]) : !candidati.length && n.cartella ? h('p', 'sub', ['Cartella: ' + n.cartella]) : null,
      h('p', 'titolo-dialogo', [t.vista]),
      radio.length ? h('fieldset', 'scelta-repo', [h('legend', '', ['Repo in cui avviare']), ...radio.map(x => h('label', '', [x, x.value]))]) : null,
      h('div', 'riga-azioni', [avvia, annulla]),
    ], { method: 'dialog' }));
    d.showModal();
  }

  // ---- struttura fissa (una volta) ----
  function struttura() {
    if ($('mappa-svg')) return;
    const filtri = h('div', 'scelta', FILTRI.map(([k, nome]) => {
      const b = bottone(nome, '', () => { filtro = k; for (const x of filtri.children) x.setAttribute('aria-pressed', String(x === b)); disegna(); lista(); });
      b.setAttribute('aria-pressed', String(k === filtro));
      return b;
    }), { role: 'group', 'aria-label': 'Filtro della mappa' });
    const svg = s('svg', { id: 'mappa-svg', role: 'group', tabindex: 0, 'aria-label': 'Mappa dei progetti e dei loro task: la stessa lista è sotto. Frecce per spostarla, più e meno per lo zoom, zero per la vista intera' });
    gesti(svg);
    const zoom = h('div', 'mappa-zoom', [
      bottone('+', '', () => zoomCentro(1.25)), bottone('−', '', () => zoomCentro(0.8)), bottone('Adatta', '', adatta),
    ], { role: 'group', 'aria-label': 'Zoom della mappa' });
    [['Ingrandisci', 0], ['Riduci', 1], ['Adatta alla vista', 2]].forEach(([nome, i]) => zoom.children[i].setAttribute('aria-label', nome));
    svg.addEventListener('pointerleave', () => { if (!fuocoNeiSatelliti()) apri(fissato); });
    const legenda = h('div', 'legenda', GRUPPI.map(([st]) => h('span', '', [h('i', 'punto st-' + st), NOME_VISIVO[st]])));
    $('mappa-area').replaceChildren(h('div', 'mappa-box', [
      h('div', 'mappa-testa', [h('h2', '', ['Mappa del lavoro']), h('div', 'mappa-testa-azioni', [filtri, bottone('Nuovo progetto', '', nuovoProgetto)])]), svg, legenda, zoom,
      h('ul', 'mappa-lista', [], { id: 'mappa-lista', 'aria-label': 'Nodi e task, in elenco' }),
    ]), h('p', 'nota-mappa', ['Il numero sul nodo = task pronti da avviare. Social: bozze da pubblicare.']));
    new ResizeObserver(() => {
      const q = svg.clientWidth + 'x' + svg.clientHeight;
      if (dati && q !== dimensione) disegna();
    }).observe(svg);
  }

  async function prendi(percorso) {
    try { const r = await fetch(percorso, { cache: 'no-store' }); return r.ok ? await r.json() : null; } catch (e) { return null; }
  }
  async function carica() {
    struttura();
    const p = new URLSearchParams(location.search).get('prova');
    const m = p ? prova(p) : await prendi('/api/mappa');
    if (!m) { $('mappa-saluto').replaceChildren(h('h1', 'saluto', ['Non riesco a leggere la mappa.'])); return; }
    applica(m);
  }
  // /api/stato e /api/oggi le legge già dashboard.js (aggiorna) e le passa con imposta: la mappa non le chiede due volte
  function imposta(st, o) {
    progetti = st && st.progetti || [];
    giorni = o && o.conData || [];
    if (dati) applica(dati);
  }
  function applica(m) {
    const nuova = JSON.stringify([m, giorni]);
    dati = m;
    saluto(new Date());
    if (nuova === impronta) return;           // niente è cambiato: non interrompo hover e animazioni
    impronta = nuova;
    const scelto = nodoPer(fissato) || obiettivoPer(fissato);   // a goal that is gone (or a node) drops the stale key
    if (!scelto) fissato = null;
    if (selezione && !(scelto && scelto.task.some(t => t.testo === selezione.testo && t.data === selezione.data))) selezione = null;
    disegna(); lista(); pannello();
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !document.querySelector('dialog[open]') && !$('mappa-vista').hidden && (fissato || aperto)) deseleziona();
  });
  // un clic fuori dal task evidenziato (e dai satelliti, dalla lista e dai dialog) toglie l'evidenziazione
  document.addEventListener('click', e => {
    const dopoTrascinamento = trascinato; trascinato = false;   // il clic che segue uno spostamento non conta
    if (dopoTrascinamento || !selezione || $('mappa-vista').hidden || e.target.closest('#mappa-dettaglio .task, #mappa-dettaglio summary, #mappa-satelliti .sat, #mappa-lista, .mappa-zoom, dialog')) return;
    selezione = null; pannello();
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !$('mappa-vista').hidden) carica(); });

  // Dall'Agenda: stesso dialogo di conferma, per una voce del piano con #tag (il nodo è il tag).
  // Il nodo si cerca nei dati della mappa (case-insensitive: il tag è minuscolo); se non sono ancora arrivati li carica, una volta sola.
  let caricamento = null;
  async function nodoDi(tag) {
    if (!dati) await (caricamento = caricamento || carica().finally(() => { caricamento = null; }));
    return dati && dati.nodi.find(n => n.nome.toLowerCase() === String(tag).toLowerCase());
  }
  async function avviaVoce(v) {
    const { testo, tag } = window.Comp.senzaTag(v.testo);  // v.titolo is already without the tag
    const n = await nodoDi(tag);
    if (!n) return toast('Nodo «' + tag + '» non trovato.');
    conferma(n, { data: v.data, testo: v.testo, vista: v.vista || testo });
  }

  window.Mappa = { carica, imposta, avviaVoce, nodoDi };
})();
