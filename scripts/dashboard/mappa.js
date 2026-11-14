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
  let banda = { altri: false, completati: false };   // the goal band's folded groups, opened by their pill
  let rivela = null;        // the group a pill just opened: its goals fade in once

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
  // Every node that can take a task has a «+», at the top right of the disc (clear of the count in the middle), twice:
  // on the node, and above the satellite zone when the node is open (the zone covers the edge of the disc).
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
  // A label cut to `max` keeps its whole text in the tooltip and for screen readers: a plain span has no accessible name of its
  // own (aria-label is not read there), so the cut text is hidden from them and the whole one is read instead. Uncut: the text.
  function tagliata(testo, max) {
    const corto = taglia(testo, max);
    if (corto === testo) return testo;
    return h('span', '', [h('span', '', [corto], { 'aria-hidden': 'true' }), h('span', 'solo-lettori', [testo])], { title: testo });
  }
  function giornoBreve(iso) {
    return new Date(iso + 'T12:00').toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }).replace('.', '');
  }
  // A goal's deadline in words, the same on the box, in the panel and in the list. Empty without a deadline: never a blank date.
  // `aRischio` is also true when `scaduto`, so one word and «scaduto» wins.
  const scade = o => o.scadenza ? 'scade ' + giornoBreve(o.scadenza) : '';
  const rischio = o => !o.scadenza ? '' : o.scaduto ? 'scaduto' : o.aRischio ? 'a rischio' : '';
  const etichettaRischio = o => rischio(o) ? h('span', 'stato ' + (o.scaduto ? 'errore' : 'attenzione'), [rischio(o)]) : null;
  const PARALLELO = 'Le date ipotizzano che i task indipendenti procedano in parallelo.';
  // A row's computed due date and missing estimate, the same in the panel and in the list. A hand-written date is shown by the
  // row itself (the server copies it into `entro`), so «entro il» only for a computed one; once past it says so in words, not only red.
  function segniScadenza(t) {
    return [
      t.entroCalcolato && t.entro ? h('span', 'sub' + (t.ritardo ? ' ritardo' : ''), [(t.ritardo ? 'in ritardo, ' : '') + 'entro il ' + giornoBreve(t.entro)]) : null,
      t.senzaStima ? h('span', 'sub', ['senza stima']) : null,
    ];
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
      nomi.length ? h('span', 'repo-elenco', ['repo', ...nomi.map(r => h('span', 'repo', [tagliata(r, 24)]))]) : null,
      ...ignoti.map(r => h('span', 'sub motivo', ['repo sconosciuto: ', tagliata(r, 24)])),
      (t.stessoRepo || []).length ? h('span', 'stato attenzione avviso-repo', ['stesso repo di un task in corso']) : null,
      filtrato && !nomi.length && !ignoti.length && !t.bozza ? h('span', 'sub', ['repo non indicato']) : null,
    ];
  }
  // A task's goal as a button in its row, the same in the panel and in the list: it fixes the goal, which the band then shows
  // even if a pill had folded it, and opens its panel. The panel redraw drops the pressed button, so the focus moves to the
  // goal's box; with no box drawn (narrow screen, a filter without goals) the panel comes into view instead.
  function segnoObiettivo(t) {
    const o = t.obiettivo && obiettivoPer(PREFISSO_OBIETTIVO + t.obiettivo);
    if (!o) return null;
    // one span: as separate flex items of the button, the space after «obiettivo:» would collapse
    const b = bottone(h('span', '', ['obiettivo: ', tagliata(o.titolo, 24)]), 'chip-obiettivo', () => {
      if (!obiettiviVisibili().includes(o)) impostaFiltro('tutto');   // «Progetti»/«Argomenti» draw no band to reveal it in
      scegliObiettivo(o.slug);
      const box = obiettiviSvg.get(o.slug);
      if (box) box.G.focus();
      else if (!b.isConnected) fuocoAlPannello();   // the redraw took the pressed chip away: never leave the focus on the page
      else $('mappa-dettaglio').scrollIntoView({ block: 'nearest' });
    });
    return b;
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
    // deadlines: a computed date has no hand-written one; a ready task past its computed date, one without an estimate, a goal all done
    Object.assign(task[5], { data: null, stima: null, entro: '2026-11-24', entroCalcolato: true, senzaStima: true });
    Object.assign(task[7], { data: null, stima: 3, entro: '2026-11-04', entroCalcolato: true, ritardo: true, obiettivo: 'dominio' });
    Object.assign(task[8], { data: null, stima: 6, entro: '2026-11-05', entroCalcolato: true, obiettivo: 'dominio' });
    task[12].obiettivo = task[14].obiettivo = 'voto';
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
    const obiettivo = (slug, titolo, definito, scadenze) => {
      const ts = nodi.flatMap(n => n.task.filter(t => t.obiettivo === slug).map(t => ({ ...t, nodo: n.nome })));
      const quanti = st => ts.filter(t => statoVisivo(t) === st).length;
      return { slug, titolo, definito, progetti: [...new Set(ts.map(t => t.nodo))], task: ts, conteggi: { pronti: quanti('pronto'), in_corso: quanti('in_corso'), in_attesa: quanti('in_attesa'), fatti: quanti('fatto') },
        scadenza: null, giorniNecessari: null, giorniDisponibili: null, aRischio: false, scaduto: false, piano: null, ...scadenze };
    };
    // enough goals to fold the band past two rows at any width; some with a safe deadline, the others without one
    const riempitivi = ['Sito nuovo online', 'Newsletter mensile', 'Corso per i soci', 'Bilancio in ordine', 'App per Android', 'Archivio delle foto',
      'Guida per i volontari', 'Calendario condiviso', 'Backup automatici', 'Modulo di iscrizione', 'Pagina dei contatti', 'Report trimestrale']
      .map((titolo, i) => obiettivo('extra-' + i, titolo, true, i % 3 ? {} : { scadenza: '2027-0' + (1 + i / 3) + '-15', giorniNecessari: 0, giorniDisponibili: 40 + i }));
    return {
      nodi, obiettivi: [
        obiettivo('club', 'Aprire ai primi Club <beta> & "amici" 🚀', true, { scadenza: '2026-11-27', giorniNecessari: 9, giorniDisponibili: 6, aRischio: true, piano: 'docs/piani/club.md' }),
        obiettivo('linkedin', 'Pubblicare con costanza', true), obiettivo('radar', 'radar', false),
        obiettivo('dominio', 'Dominio rinnovato', true, { scadenza: '2026-11-06', giorniNecessari: 2, giorniDisponibili: 0, aRischio: true, scaduto: true }),
        obiettivo('voto', 'Votazioni sicure', true, { scadenza: '2026-11-30', giorniNecessari: 0, giorniDisponibili: 13 }), ...riempitivi],
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

  // ---- grafo dell'obiettivo: impaginazione pura (niente DOM né stato del modulo: la prova la esegue in node) ----
  // A task is known by its date and text everywhere in this file: an id is optional
  const chiaveTask = t => (t.data || '') + '|' + t.testo;
  // The ids a task waits on: every resolved one from the server, done blockers too; else the open ones (fixture, older server)
  const dopoDi = t => t.dopo || (t.aspetta || []).map(a => a.id).filter(Boolean);
  // The nodes of a goal's graph: its tasks, plus as ghosts a blocker outside the goal and a task outside it that waits on one of
  // ours (a ghost is never expanded further). `tutti`: every task of the map with its `nodo`. Done tasks only `conFatti`: their
  // links are met. An id held by two tasks is no edge, as on the server. `ordine` is plan order, a ghost next to its first link.
  // O(N + E) time and space.
  function nodiGrafo(o, tutti, conFatti) {
    const perId = new Map(), doppi = new Set();
    for (const t of tutti) if (t.id) { if (perId.has(t.id)) doppi.add(t.id); else perId.set(t.id, t); }
    const di = id => doppi.has(id) ? undefined : perId.get(id);
    const mostra = t => conFatti || t.stato !== 'fatto';
    const fantasma = t => t.obiettivo ? 'altro obiettivo' : 'senza obiettivo';
    const nodi = new Map();
    const nodo = (t, ordine, f) => {
      const k = chiaveTask(t);
      if (!nodi.has(k)) nodi.set(k, { chiave: k, t, dopo: [], ordine, fantasma: f });
      return nodi.get(k);
    };
    const lega = (n, k) => { if (!n.dopo.includes(k)) n.dopo.push(k); };
    o.task.filter(mostra).forEach((t, i) => nodo(t, i, null));
    for (const n of [...nodi.values()]) {
      for (const id of dopoDi(n.t)) {
        const b = di(id);
        if (!b || !mostra(b)) continue;
        const k = b.obiettivo === o.slug ? chiaveTask(b) : nodo(b, n.ordine - 0.5, fantasma(b)).chiave;
        if (nodi.has(k)) lega(n, k);
      }
    }
    for (const t of tutti) {
      if (t.obiettivo === o.slug || !mostra(t)) continue;
      const su = dopoDi(t).map(di).filter(b => b && b.obiettivo === o.slug && nodi.has(chiaveTask(b))).map(chiaveTask);
      if (!su.length) continue;
      const n = nodo(t, Math.max(...su.map(k => nodi.get(k).ordine)) + 0.5, fantasma(t));
      su.forEach(k => lega(n, k));
    }
    return [...nodi.values()];
  }
  // Rows by dependency depth: row 0 without a shown blocker, else one past the deepest blocker (Kahn: O(V + E) time and space).
  // Tasks in one row can run in parallel. A ghost blocker then moves down to just above its first waiter. What a cycle leaves
  // unordered (the cycle and everything after it) gets a last row of its own.
  function stratiGrafo(nodi) {
    const per = new Map(nodi.map(n => [n.chiave, { figli: [], attese: n.dopo.length, strato: 0 }]));
    for (const n of nodi) for (const k of n.dopo) per.get(k).figli.push(n.chiave);
    const coda = nodi.filter(n => !n.dopo.length).map(n => n.chiave);
    for (let i = 0; i < coda.length; i++) {
      const a = per.get(coda[i]);
      for (const f of a.figli) {
        const b = per.get(f);
        b.strato = Math.max(b.strato, a.strato + 1);
        if (!--b.attese) coda.push(f);
      }
    }
    const avanzo = new Set(nodi.filter(n => per.get(n.chiave).attese > 0).map(n => n.chiave));
    for (const n of nodi) {
      const a = per.get(n.chiave), giu = a.figli.filter(f => !avanzo.has(f)).map(f => per.get(f).strato);
      if (n.fantasma && !n.dopo.length && giu.length) a.strato = Math.min(...giu) - 1;
    }
    let ultimo = -1;
    for (const n of nodi) if (!avanzo.has(n.chiave)) ultimo = Math.max(ultimo, per.get(n.chiave).strato);
    const strato = new Map(nodi.map(n => [n.chiave, avanzo.has(n.chiave) ? ultimo + 1 : per.get(n.chiave).strato]));
    return { strato, avanzo, quanti: avanzo.size ? ultimo + 2 : ultimo + 1 };
  }
  // Geometry in px: a gutter on the left for the bracket of a wrapped row, the root (the goal) on top, then the rows centred,
  // as many boxes per line as `W` holds; a row with more wraps onto more lines and stays one row.
  const GRAFO = { lato: 32, margine: 16, min: 180, max: 240, gap: 20, passo: 44, cima: 16, radice: 380, altoRadice: 74, scosta: 6 };
  // `alto`: the height of a task box. Order in a row: one barycenter pass (mean x of the blockers already placed) against crossings,
  // ties and tasks with no placed blocker in plan order. Arrows run orthogonally from the blocker's bottom to the waiter's top:
  // down, across, down; one that skips lines detours through a lane free of every box on them (a side margin always is).
  // O(V log V + E * B log B) time for B boxes on the skipped lines (sorted per arrow), O(V + E) space.
  function impaginaGrafo(nodi, W, alto) {
    const { strato, avanzo, quanti } = stratiGrafo(nodi);
    const usabile = Math.max(GRAFO.min, W - GRAFO.lato - GRAFO.margine);
    const perRiga = Math.max(1, Math.floor((usabile + GRAFO.gap) / (GRAFO.min + GRAFO.gap)));
    const righe = Array.from({ length: quanti }, () => []);
    for (const n of nodi) righe[strato.get(n.chiave)].push(n);
    const k = Math.min(perRiga, Math.max(1, ...righe.map(r => r.length)));
    const largo = Math.min(GRAFO.max, (usabile - (k - 1) * GRAFO.gap) / k);
    const rw = Math.min(GRAFO.radice, usabile);
    const radice = { x: GRAFO.lato + (usabile - rw) / 2, y: GRAFO.cima, w: rw, h: GRAFO.altoRadice };
    const posti = new Map(), linee = [], strati = [];
    let y = radice.y + radice.h + GRAFO.passo;
    righe.forEach((riga, s) => {
      const media = n => {
        const xs = n.dopo.map(c => posti.get(c)).filter(Boolean).map(p => p.x + p.w / 2);
        return xs.length ? xs.reduce((a, b) => a + b) / xs.length : Infinity;
      };
      const ordinati = riga.map(n => [n, media(n)]).sort((a, b) => (a[1] - b[1]) || a[0].ordine - b[0].ordine).map(([n]) => n);
      const y0 = y;
      for (let i = 0; i < ordinati.length; i += perRiga) {
        const pezzo = ordinati.slice(i, i + perRiga), x0 = GRAFO.lato + (usabile - pezzo.length * largo - (pezzo.length - 1) * GRAFO.gap) / 2;
        const linea = { y, scatole: pezzo.map((n, j) => ({ chiave: n.chiave, x: x0 + j * (largo + GRAFO.gap), y, w: largo, h: alto, strato: s })) };
        linea.scatole.forEach(p => posti.set(p.chiave, p));
        linee.push(linea);
        y += alto + GRAFO.passo;
      }
      strati.push({ strato: s, y0, y1: y - GRAFO.passo, linee: Math.ceil(ordinati.length / perRiga), avanzo: ordinati.some(n => avanzo.has(n.chiave)), chiavi: ordinati.map(n => n.chiave) });
    });
    // a free x across the lines strictly between two y (the gaps and margins no box, plus `scosta`, covers): the blocker's own x
    // when free, so the arrow drops straight; else the one nearest to the waiter's x
    const corsia = (y0, y1, xb, x) => {
      const pieni = linee.filter(l => l.y > y0 && l.y < y1).flatMap(l => l.scatole.map(b => [b.x - GRAFO.scosta, b.x + b.w + GRAFO.scosta])).sort((a, b) => a[0] - b[0]);
      const liberi = [];
      let da = GRAFO.lato + 2;   // the gutter holds the «in parallelo» bracket
      for (const [a, b] of pieni) { if (a > da) liberi.push([da, a]); da = Math.max(da, b); }
      if (W - 4 > da) liberi.push([da, W - 4]);
      if (liberi.some(([a, b]) => a <= xb && xb <= b)) return xb;
      let meglio = null;
      for (const [a, b] of liberi) { const c = Math.max(a, Math.min(b, x)); if (meglio === null || Math.abs(c - x) < Math.abs(meglio - x)) meglio = c; }
      return meglio === null ? x : meglio;
    };
    const f = v => +v.toFixed(1);
    const via = (p, q) => {
      const xb = f(p.x + p.w / 2), yb = f(p.y + p.h), xa = f(q.x + q.w / 2), ya = f(q.y);
      if (!linee.some(l => l.y > p.y && l.y < q.y)) return `M${xb} ${yb}V${f((yb + ya) / 2)}H${xa}V${ya}`;
      // ponytail: arrows that share a lane or a channel overlap there; offset lanes if a real plan gets hard to read
      return `M${xb} ${yb}V${f(yb + GRAFO.passo / 2)}H${f(corsia(p.y, q.y, xb, xa))}V${f(ya - GRAFO.passo / 2)}H${xa}V${ya}`;
    };
    const archi = [];
    for (const n of nodi) {
      const q = posti.get(n.chiave);
      for (const c of n.dopo) { const p = posti.get(c); if (q.y > p.y) archi.push({ da: c, a: n.chiave, d: via(p, q) }); }   // none inside the cycle's own row
    }
    // the tree: from the goal to its own tasks on the first line of the first row (the bracket ties a wrapped row's other lines
    // to it: links threading down to them only crowded the lanes)
    const radici = (righe[0] || []).filter(n => !n.fantasma && !avanzo.has(n.chiave) && linee.length && posti.get(n.chiave).y === linee[0].y).map(n => ({ da: null, a: n.chiave, d: via(radice, posti.get(n.chiave)), radice: true }));
    return { radice, posti, strati, archi: [...radici, ...archi], largo, perRiga, alto: (linee.length ? y - GRAFO.passo : radice.y + radice.h) + 24 };
  }

  // ---- zoom e spostamento: una trasformazione sul gruppo del mondo; il testo non scala (vedi --k nel CSS) ----
  let trascinato = false;   // vero dopo un trascinamento: il clic che lo segue non deve deselezionare
  function applicaVista() {
    const m = $('mappa-mondo');
    if (!m) return;
    m.setAttribute('transform', `translate(${vista.x.toFixed(1)} ${vista.y.toFixed(1)}) scale(${vista.k.toFixed(3)})`);
    $('mappa-svg').style.setProperty('--k', vista.k.toFixed(3));
  }
  function limita(v = vista) {       // lascia sempre almeno 80px di mappa in vista
    const svg = $('mappa-svg'), W = svg.clientWidth, H = svg.clientHeight, m = 80;
    v.x = Math.max(m - W * v.k, Math.min(W - m, v.x));
    v.y = Math.max(m - H * v.k, Math.min(H - m, v.y));
    return v;
  }
  function zoomA(fattore, cx, cy) {   // cx, cy: punto fermo, in pixel dell'SVG
    cancelAnimationFrame(volo);
    const k = Math.max(K_MIN, Math.min(K_MAX, vista.k * fattore)), f = k / vista.k;
    vista = { k, x: cx - (cx - vista.x) * f, y: cy - (cy - vista.y) * f };
    limita(); applicaVista();
  }
  function sposta(dx, dy) { cancelAnimationFrame(volo); vista.x += dx; vista.y += dy; limita(); applicaVista(); }
  function adatta() { cancelAnimationFrame(volo); ritorno = null; vista = { k: 1, x: 0, y: 0 }; applicaVista(); }   // the view you chose: deselecting stays here
  function zoomCentro(fattore) { const svg = $('mappa-svg'); zoomA(fattore, svg.clientWidth / 2, svg.clientHeight / 2); }
  // A fixed node is framed: the view flies so the node and its satellites sit in the middle; unfixing flies back to the view
  // from before. A user gesture (wheel, drag, pinch, + − 0, «Adatta») stops a flight where it is. Reduced motion: a jump.
  const MOTO_RIDOTTO = window.matchMedia('(prefers-reduced-motion: reduce)');
  let volo = 0, ritorno = null;   // the running flight (rAF id) and the view to fly back to, null when nothing was framed
  function vola(meta) {
    cancelAnimationFrame(volo);
    if (MOTO_RIDOTTO.matches) { vista = meta; applicaVista(); return; }
    const da = { ...vista }, t0 = performance.now(), DURATA = 300;
    const passo = ora => {
      const t = Math.min(1, (ora - t0) / DURATA), e = 1 - Math.pow(1 - t, 5);   // ease-out quint: a strong ease-out, in closed form
      vista = { k: da.k + (meta.k - da.k) * e, x: da.x + (meta.x - da.x) * e, y: da.y + (meta.y - da.y) * e };
      applicaVista();
      if (t < 1) volo = requestAnimationFrame(passo);
    };
    volo = requestAnimationFrame(passo);
  }
  function inquadra(nome) {
    const svg = $('mappa-svg'), p = pos.get(nome);
    if (!p || svg.clientWidth < 2) return;   // under 760px the list replaces the map: nothing to zoom
    if (!ritorno) ritorno = { ...vista };
    // the node with its name below and its satellites (drawn by apri just before), in world units
    const b = $('mappa-satelliti').getBBox(), con = b.width > 0;
    const x0 = Math.min(con ? b.x : Infinity, p.x - p.r - 9), x1 = Math.max(con ? b.x + b.width : -Infinity, p.x + p.r + 9);
    const y0 = Math.min(con ? b.y : Infinity, p.y - p.r - 9), y1 = Math.max(con ? b.y + b.height : -Infinity, p.y + p.r + 60);
    const testa = document.querySelector('.mappa-testa'), su = 26 + (testa ? testa.offsetHeight : 36), giu = 44;   // header and legend
    const W = svg.clientWidth, H = svg.clientHeight;
    // the text keeps its size on screen at any zoom, so up to 1.5 the satellites only spread out
    const k = Math.max(K_MIN, Math.min(K_MAX, 1.5, 0.9 * W / (x1 - x0), 0.9 * (H - su - giu) / (y1 - y0)));
    vola(limita({ k, x: W / 2 - (x0 + x1) / 2 * k, y: (su + H - giu) / 2 - (y0 + y1) / 2 * k }));
  }
  function torna() {
    // on the narrow list the map is hidden (no size to fit or fly in): the view simply goes back as it was
    if (ritorno) { if ($('mappa-svg').clientWidth < 2) vista = ritorno; else vola(limita(ritorno)); }
    ritorno = null;
  }
  // Motion only for a change the user just caused: WAAPI, called from the handlers, so a redraw (the first paint included)
  // never replays it. transform and opacity only (the thread's dash too), a strong ease-out, nothing under reduced motion.
  const EASE_OUT = 'cubic-bezier(0.23, 1, 0.32, 1)';
  function anima(el, fotogrammi, ms, ritardo) {
    if (el && el.animate && !MOTO_RIDOTTO.matches) el.animate(fotogrammi, { duration: ms, delay: ritardo || 0, easing: EASE_OUT, fill: 'backwards' });
  }
  // What leaves fades out where it was, faster than it came: a copy, never the live elements, which keep their listeners and
  // can hold the focus. The copy is hidden from screen readers, out of the tab order and of the pointer, then removed.
  function esce(nodi, prima) {
    if (MOTO_RIDOTTO.matches || !nodi.length || !prima || !prima.parentNode) return;
    const g = s('g', { class: 'uscita', 'aria-hidden': 'true' });
    for (const n of nodi) {
      const c = n.cloneNode(true);
      for (const x of [c, ...c.querySelectorAll('[tabindex]')]) x.removeAttribute('tabindex');
      g.appendChild(c);
    }
    prima.parentNode.insertBefore(g, prima);
    const a = g.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120, easing: EASE_OUT, fill: 'forwards' });
    a.finished.then(() => g.remove(), () => g.remove());
  }
  function portaInVista(nome) {       // un nodo che prende il fuoco fuori dal riquadro viene portato al centro
    cancelAnimationFrame(volo);
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
      const sfondo = !e.target.closest('.nodo, .sat, .azione, .obiettivo, .pastiglia');
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
  // The goal band as drawn: open goals in at most two rows, the rest behind «+k altri»; goals with every task done behind
  // «+k completati». A pill opens and closes its group. The fixed goal is never folded away, so selecting a goal reveals it.
  // Returns the slots in order: open goals, «+k altri», done goals, «+k completati» (each pill closes its own group). O(G) time and space.
  function fascia(colonne) {
    const scelto = obiettivoPer(fissato), finito = o => o.task.length > 0 && o.conteggi.fatti === o.task.length;   // no task is not done
    const tutti = obiettiviVisibili(), aperti = tutti.filter(o => !finito(o)), finiti = tutti.filter(finito);
    const posto = Math.max(1, 2 * colonne - (finiti.length ? 1 : 0));   // two rows, one slot kept for «+k completati»
    const pieghe = [['altri', aperti.length > posto ? aperti.slice(posto - 1) : []], ['completati', finiti]];   // «+k altri» takes a slot too
    const nascosti = new Set(pieghe.flatMap(([g, os]) => banda[g] ? [] : os.filter(o => o !== scelto)));
    const nuovi = new Set(pieghe.flatMap(([g, os]) => g === rivela ? os : []));
    const piegaDi = new Map(pieghe.flatMap(([g, os]) => os.filter(o => o !== scelto).map(o => [o, g])));   // what each pill would fold away
    const mostra = os => os.filter(o => !nascosti.has(o)).map(o => ({ o, rivelato: nuovi.has(o), piega: piegaDi.get(o) }));
    // an open group keeps its pill to close it; a folded one shows it only if it hides something
    const pastiglia = ([g, os]) => os.length && (banda[g] || os.some(o => nascosti.has(o))) ? [{ pastiglia: g, k: os.filter(o => nascosti.has(o)).length }] : [];
    return [...mostra(aperti), ...pastiglia(pieghe[0]), ...mostra(finiti), ...pastiglia(pieghe[1])];
  }

  // ---- disegno ----
  function disegna() {
    const svg = $('mappa-svg');
    if (!dati || !svg) return;
    const W = svg.clientWidth, H = svg.clientHeight;
    dimensione = W + 'x' + H;
    nodiSvg = new Map(); pos = new Map(); obiettiviSvg = new Map();
    const sfondo = s('rect', { class: 'mappa-sfondo', x: 0, y: 0, width: W, height: H });
    sfondo.addEventListener('pointerenter', () => { if (!fuocoNeiSatelliti()) apri(fissato, false, true); });
    sfondo.addEventListener('click', () => { if (!trascinato) deseleziona(); });
    // arrowhead of the dependency thread: a marker, so the path stays one element
    const freccia = s('marker', { id: 'mappa-freccia', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto' }, [s('path', { d: 'M0 0L10 5L0 10z' })]);
    svg.replaceChildren(s('defs', {}, [freccia]), sfondo);
    if (W < 2) return;                       // sotto i 760px l'SVG è nascosto: c'è la lista
    const mondo = s('g', { id: 'mappa-mondo' });   // tutto ciò che si zooma: nodi e satelliti
    svg.appendChild(mondo);
    const prossimo = dati.prossima && dati.prossima.nodo;
    // Goal band under the header: rounded boxes in rows, as many per row as the width allows; the nodes are laid out below the
    // rows actually drawn (folded goals take no room). A deadline adds a line to every box, so the rows stay even.
    const OB = { gap: 12, min: 150, max: 220 };
    const testa = document.querySelector('.mappa-testa'), y0 = 26 + (testa ? testa.offsetHeight : 36);
    const colonne = Math.max(1, Math.floor((W - 40 + OB.gap) / (OB.min + OB.gap))), obiettivi = fascia(colonne), k = Math.min(obiettivi.length, colonne);
    OB.h = obiettivi.some(v => v.o && v.o.scadenza) ? 74 : 58;
    const largo = k ? Math.min(OB.max, (W - 40 - (k - 1) * OB.gap) / k) : 0, x0 = (W - k * largo - (k - 1) * OB.gap) / 2;
    const strato = s('g', { id: 'mappa-obiettivi' });   // first child of the world: the goal lines run under the nodes
    mondo.appendChild(strato);
    // «scade <giorno> · a rischio» wider than its box: the state word goes on a line of its own and only that box grows by it;
    // the row pitch grows too, so no box reaches the row below. Measured on a probe in the live SVG before anything is placed,
    // since the width depends on the font and the nodes are laid out below the band. O(G) measures.
    const sonda = s('text', { class: 'obiettivo-sub' });
    strato.appendChild(sonda);
    const lunghi = new Set(obiettivi.filter(({ o }) => o && scade(o) && rischio(o)).filter(({ o }) => {
      sonda.replaceChildren(scade(o), s('tspan', { class: 'obiettivo-rischio' }, [' · ' + rischio(o)]));
      return sonda.getComputedTextLength() > largo - 24;
    }).map(({ o }) => o));
    sonda.remove();
    const RIGA = 16, passo = OB.h + (lunghi.size ? RIGA : 0) + OB.gap;
    const fondoFascia = y0 + Math.ceil(obiettivi.length / colonne) * passo - OB.gap;
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
      if (repo.length > 1) G.append(s('text', { class: 'repo-nodo', x, y: y + r, dy: '4.8em' }, [s('title', {}, ['repo: ' + repo.join(', ')]), repo.slice(0, 3).map(nomeRepo => taglia(nomeRepo, 14)).join(' · ') + (repo.length > 3 ? ' +' + (repo.length - 3) : '')]));
      if (puoAggiungere(n)) G.append(piu(n, pos.get(n.nome)));
      G.addEventListener('pointerenter', () => apri(n.nome, false, true));
      G.addEventListener('focus', () => { if (G.matches(':focus-visible')) portaInVista(n.nome); apri(n.nome); });   // solo dalla tastiera: al clic il nodo si sposterebbe sotto il puntatore
      G.addEventListener('click', () => { scegli(n.nome); anima(G.querySelector('.alone'), [{ opacity: 0, transform: 'scale(.94)' }, { transform: 'none' }], 250); });   // the ring of the node just fixed
      G.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); scegli(n.nome); }
        if (e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); apri(n.nome); const primo = document.querySelector('#mappa-satelliti .sat[tabindex]'); if (primo) primo.focus(); }
      });
      nodiSvg.set(n.nome, G);
      mondo.appendChild(G);
    }
    const linee = [], scatole = [];
    let nRivelati = 0;
    obiettivi.forEach(({ o, rivelato, piega, pastiglia, k: piegati }, i) => {
      const lungo = lunghi.has(o), alto = OB.h + (lungo ? RIGA : 0);
      const x = x0 + (i % colonne) * (largo + OB.gap), y = y0 + Math.floor(i / colonne) * passo, ax = x + largo / 2, ay = y + alto;
      if (pastiglia) {   // «+k altri» / «+k completati»: a button that opens its group, and closes it again
        const aperta = banda[pastiglia], uno = !aperta && piegati === 1;   // «+1 altro», «+1 completato»: singular for one
        const testo = aperta ? (pastiglia === 'altri' ? 'nascondi gli altri' : 'nascondi i completati') : '+' + piegati + (pastiglia === 'altri' ? (uno ? ' altro' : ' altri') : (uno ? ' completato' : ' completati'));
        const P = s('g', { class: 'pastiglia', tabindex: 0, role: 'button', 'aria-expanded': String(aperta), 'data-pastiglia': pastiglia,
          'aria-label': testo + (pastiglia === 'altri' ? (uno ? ' obiettivo' : ' obiettivi') : (uno ? ': obiettivo' : ': obiettivi') + ' con tutti i task fatti') });   // starts with the visible words, so voice control finds it
        P.append(s('title', {}, [aperta ? testo : 'mostra ' + testo.slice(1)]), s('rect', { class: 'pastiglia-box', x, y: y + (OB.h - 32) / 2, width: largo, height: 32, rx: 16 }),
          s('text', { class: 'pastiglia-testo', x: ax, y: y + OB.h / 2, dy: '0.35em' }, [testo]));
        const premi = () => {
          const via = aperta ? [...document.querySelectorAll('#mappa-obiettivi [data-piega="' + pastiglia + '"]')] : [];   // what this press folds away
          banda[pastiglia] = !aperta; rivela = aperta ? null : pastiglia;
          disegna();
          esce(via, $('mappa-dipendenze'));   // the folded goals fade out where they were, over the new band
          const nuova = document.querySelector('#mappa-obiettivi [data-pastiglia="' + pastiglia + '"]');   // the redraw replaced the pressed pill
          if (nuova) { nuova.focus(); anima(nuova.querySelector('.pastiglia-box'), [{ transform: 'scale(.97)' }, { transform: 'none' }], 150); }
        };
        P.addEventListener('click', premi);
        P.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); premi(); } });
        scatole.push(P);
        return;
      }
      const sue = o.progetti.filter(nome => pos.has(nome)).map(nome => {   // a node hidden by the filter gets no line: the panel still lists its steps
        const p = pos.get(nome), d = Math.hypot(ax - p.x, ay - p.y) || 1;
        return s('line', { class: 'obiettivo-linea', x1: ax.toFixed(1), y1: ay.toFixed(1), x2: (p.x + (ax - p.x) / d * (p.r + 6)).toFixed(1), y2: (p.y + (ay - p.y) / d * (p.r + 6)).toFixed(1) });
      });
      const c = o.conteggi, tot = c.fatti + c.in_corso + c.pronti + c.in_attesa;
      const scadenza = scade(o), stato = rischio(o);
      const etichetta = o.titolo + ', obiettivo: ' + contoObiettivo(o) + (o.definito ? '' : ', non definito') + (scadenza ? ', ' + scadenza : '') + (stato ? ', ' + stato : '');
      const G = s('g', { class: 'obiettivo' + (o.definito ? '' : ' non-definito') + (stato === 'scaduto' ? ' scaduto' : stato ? ' a-rischio' : '') + (rivelato ? ' rivelato' : ''),
        tabindex: 0, role: 'button', 'aria-label': etichetta, ...(piega ? { 'data-piega': piega } : {}) });
      if (rivelato) anima(G, [{ opacity: 0, transform: 'translateY(-6px)' }, { transform: 'none' }], 200, Math.min(nRivelati++, 6) * 30);   // a pill just opened them
      G.append(s('title', {}, [etichetta]), s('rect', { class: 'obiettivo-box', x, y, width: largo, height: alto, rx: 10 }),
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
      // the risk is a word in bold next to the date, and the outline changes too: never colour alone
      if (scadenza) G.append(s('text', { class: 'obiettivo-sub', x: x + 12, y: y + 66 }, [scadenza, ...(stato && !lungo ? [s('tspan', { class: 'obiettivo-rischio' }, [' · ' + stato])] : [])]));
      if (lungo) G.append(s('text', { class: 'obiettivo-sub', x: x + 12, y: y + 66 + RIGA }, [s('tspan', { class: 'obiettivo-rischio' }, [stato])]));
      G.addEventListener('click', () => apriGrafo(o.slug));   // the goal opens as a graph; the panel chip only selects it
      G.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); apriGrafo(o.slug); } });
      obiettiviSvg.set(o.slug, { G, linee: sue });
      linee.push(...sue); scatole.push(G);
    });
    strato.append(...linee, ...scatole);
    rivela = null;   // the reveal plays once, not on every redraw
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
    for (const [nome, G] of nodiSvg) { G.classList.toggle('coinvolto', !!o && o.progetti.includes(nome)); G.classList.toggle('fissato', nome === fissato); }
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
  // `conMoto`: opened by the pointer, so the old satellites fade out and the new ones fan out of the node, staggered.
  // Never from keyboard focus or a redraw: moving through nodes with Tab, or a refresh, must not keep animating.
  function disegnaSatelliti(nome, conMoto) {
    const strato = $('mappa-satelliti'), n = nodoPer(nome), p = pos.get(nome);
    if (!strato) return;
    if (conMoto) esce([...strato.querySelectorAll(':scope > .sat, :scope > .filo')], strato);
    if (!n || !p) { strato.replaceChildren(); return; }
    const lista = voci(n), svg = $('mappa-svg');
    const posiz = posizioni(lista.length, p, svg.clientWidth, svg.clientHeight);
    const fili = [], sat = [], entrate = [], zona = s('g', { class: 'zona' });
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
      entrate.push([dentro, (p.x - q.x) / d * 10, (p.y - q.y) / d * 10]);   // starts 10px towards its node
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
    strato.replaceChildren(zona, ...fili, ...sat, ...(puoAggiungere(n) ? [piu(n, p)] : []));   // la zona trasparente tiene aperto il nodo finché il puntatore va verso i satelliti
    if (conMoto) {
      fili.forEach(f => anima(f, [{ opacity: 0 }, { opacity: 1 }], 150));
      entrate.forEach(([dentro, ux, uy], i) => anima(dentro, [{ opacity: 0, transform: `translate(${ux.toFixed(1)}px, ${uy.toFixed(1)}px) scale(.95)` }, { opacity: 1, transform: 'none' }], 150, Math.min(i, 6) * 30));
    }
    filo();
  }

  // Thread of the selected waiting task: an arrow from every other node it waits on, and `bloccante` on the blockers
  // in its own node. Never all threads at once. Redrawn from scratch on every selection change and redraw: O(blockers).
  let ultimoFilo = '';
  function filo() {
    for (const el of document.querySelectorAll('#mappa-svg .bloccante')) el.classList.remove('bloccante');
    const strato = $('mappa-dipendenze');
    if (!strato) return;                     // narrow screen: no SVG, the panel and the list say it in words
    strato.replaceChildren();
    const n = selezione && nodoPer(fissato), t = n && n.task.find(x => x.testo === selezione.testo && x.data === selezione.data);
    const q = t && statoVisivo(t) !== 'fatto' && pos.get(n.nome);
    const chiave = q ? t.testo + ' | ' + t.data : '', nuovo = chiave !== ultimoFilo;   // draws in only for a newly selected task
    ultimoFilo = chiave;
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
      const traccia = s('path', { class: 'dipendenza', d: `M${bordo(p, p.r + 6)}Q${cx.toFixed(1)} ${cy.toFixed(1)} ${bordo(q, q.r + 10)}`, 'marker-end': 'url(#mappa-freccia)' });
      strato.append(traccia);
      if (nuovo) { const L = traccia.getTotalLength(); anima(traccia, [{ strokeDasharray: L, strokeDashoffset: L, opacity: 0 }, { strokeDasharray: L, strokeDashoffset: 0, opacity: 1 }], 250); }
    }
  }

  const fuocoNeiSatelliti = () => { const e = document.activeElement; return !!(e && e.closest && e.closest('#mappa-satelliti')); };

  // un solo nodo aperto: aprirne uno chiude il precedente; i satelliti si disegnano una volta sola
  function apri(nome, forza, conMoto) {
    if (!forza && aperto === nome) return;
    if (aperto && nodiSvg.has(aperto)) nodiSvg.get(aperto).classList.remove('aperto');
    aperto = nodiSvg.has(nome) ? nome : null;
    $('mappa-svg').classList.toggle('focus', !!aperto);
    if (aperto) nodiSvg.get(aperto).classList.add('aperto');
    disegnaSatelliti(aperto, conMoto);
  }
  function scegli(nome) { if (fissato !== nome) filtroRepo = null; fissato = nome; selezione = null; apri(nome); pannello(); inquadra(nome); }
  function scegliObiettivo(slug) {
    fissato = PREFISSO_OBIETTIVO + slug; selezione = null; apri(null); pannello();
    if (!grafo) torna();   // the band may be out of a framed view; under the graph the map keeps its view for when it closes
    if (!obiettiviSvg.has(slug)) disegna();   // a folded goal: the band always draws the fixed one
  }
  // fissa il nodo, seleziona il task e porta il pannello su di lui: la lista dei task può essere più lunga del pannello
  function scegliTask(nome, t) {
    if (fissato !== nome || (filtroRepo && !tocca(t, filtroRepo.repo))) filtroRepo = null;   // a task the filter hides could not be scrolled to
    fissato = nome; selezione = t; apri(nome); pannello(); scorriAlScelto();
  }
  function scorriAlScelto() {
    const d = $('mappa-dettaglio'), el = d.querySelector('.task.scelto');
    if (el) d.scrollTop += el.getBoundingClientRect().top - d.getBoundingClientRect().top - (d.clientHeight - el.offsetHeight) / 2;
  }
  function deseleziona() { fissato = null; selezione = null; apri(null); pannello(); torna(); }

  // ---- grafo dell'obiettivo: la vista ----
  // A goal box of the band opens its graph over the map. The map underneath is only hidden (visibility, so it keeps its size and
  // its view and zoom), and comes back as it was. The graph shows the fixed goal: whatever unfixes it (another node, «Torna alla
  // prossima azione», a refresh where the goal is gone) closes it too. Below 760px it is never drawn: the list groups by row.
  let grafo = false;           // the fixed goal is shown as a graph
  let grafoFatti = false;      // «Mostra fatti»: off again for every other goal
  let grafoSlug = null, grafoChiave = '', grafoImpronta = null, grafoMoto = false;
  let grafoScatole = new Map(), grafoArchi = [];   // chiave -> box; arrows { da, a, radice, P }
  const tuttiITask = () => dati.nodi.flatMap(n => n.task.filter(t => !t.bozza).map(t => ({ ...t, nodo: n.nome })));
  function apriGrafo(slug) {
    if (fissato !== PREFISSO_OBIETTIVO + slug) grafoFatti = false;
    grafo = true; grafoMoto = true;   // motion only for this open, never for a refresh or a resize
    scegliObiettivo(slug);            // pannello() draws the graph
    const radice = document.querySelector('#mappa-grafo .grafo-radice');
    if (radice) radice.focus({ preventScroll: true });   // the pressed box is now under the graph
  }
  function chiudiGrafo() {
    const o = grafo && obiettivoPer(fissato);
    grafo = false; aggiornaGrafo();
    const box = o && obiettiviSvg.get(o.slug);
    if (box) box.G.focus();
  }
  // A box of the graph picks its task in the goal's panel (state buttons, «Avvia»): the goal stays fixed, so the graph stays
  function scegliNelGrafo(t) { selezione = t; pannello(); scorriAlScelto(); }
  // A ghost leads where its task lives: the graph of its goal, or the task in its node (which closes the graph)
  function vaiAlFantasma(t) {
    if (t.obiettivo && obiettivoPer(PREFISSO_OBIETTIVO + t.obiettivo)) return apriGrafo(t.obiettivo);
    const n = nodoPer(t.nodo), suo = n && n.task.find(x => chiaveTask(x) === chiaveTask(t));
    if (!suo) return;
    scegliTask(n.nome, suo);
    fuocoAlPannello();
  }
  // Called by pannello() and on resize: shows or hides the view, redraws only when the goal, the toggle, the width or the data
  // changed (so a pick keeps the focus on its box), then marks the selection.
  function aggiornaGrafo() {
    const box = $('mappa-grafo');
    if (!box || !dati) return;
    const o = grafo ? obiettivoPer(fissato) : undefined;
    if (!o) grafo = false;
    box.hidden = !o;
    box.parentNode.classList.toggle('con-grafo', !!o);
    if (!o) {
      const dentro = box.contains(document.activeElement);   // e.g. a refresh where the goal is gone: never leave the focus on the page
      grafoSlug = null; grafoChiave = ''; grafoScatole = new Map(); grafoArchi = []; box.replaceChildren();
      if (dentro) fuocoAlPannello();
      return;
    }
    const chiave = o.slug + '|' + grafoFatti + '|' + box.clientWidth;
    if (chiave !== grafoChiave || grafoImpronta !== impronta) {
      const nuovo = grafoSlug !== o.slug;
      grafoChiave = chiave; grafoImpronta = impronta; grafoSlug = o.slug;
      disegnaGrafo(o, nuovo);
    }
    evidenziaGrafo();
  }
  function disegnaGrafo(o, nuovo) {
    const box = $('mappa-grafo'), testa = document.querySelector('.mappa-testa');
    const prima = document.activeElement && document.activeElement.closest && document.activeElement.closest('#mappa-grafo [data-chiave], #mappa-grafo .grafo-radice');
    const fuoco = prima && prima.getAttribute('data-chiave');
    const conMoto = grafoMoto; grafoMoto = false;
    grafoScatole = new Map(); grafoArchi = [];
    if (testa) box.style.top = (testa.offsetTop + testa.offsetHeight + 10) + 'px';   // just under the header's solid strip
    const W = box.clientWidth;
    if (W < 2) { box.replaceChildren(); return; }   // narrow screen: the list says it
    if (nuovo) box.scrollTop = 0;
    const fatti = o.task.filter(t => t.stato === 'fatto').length, interruttore = document.querySelector('.grafo-fatti');
    interruttore.hidden = !fatti;
    interruttore.textContent = 'Mostra fatti (' + fatti + ')';
    interruttore.setAttribute('aria-pressed', String(grafoFatti));
    const nodi = nodiGrafo(o, tuttiITask(), grafoFatti), per = new Map(nodi.map(n => [n.chiave, n]));
    // The real plans repeat their title before each task («Piano · Task 3: …»): a leading «X · » two boxes share is dropped on
    // the box, so the cut title still says something. The whole title stays in the tooltip and in the accessible name.
    const testaDi = v => { const i = v.indexOf(' · '); return i > 0 ? v.slice(0, i + 3) : ''; };
    const quante = new Map();
    for (const n of nodi) { const p = testaDi(n.t.vista); if (p) quante.set(p, (quante.get(p) || 0) + 1); }
    const breve = v => { const p = testaDi(v); return p && quante.get(p) > 1 && v.length > p.length ? v.slice(p.length) : v; };
    // the warnings are words on a third line; one box with them gives every box that line, so the rows stay even
    const avvisi = t => [t.ritardo ? ['in ritardo', 'grafo-ritardo'] : null, (t.stessoRepo || []).length ? ['stesso repo di un task in corso', 'grafo-avviso'] : null,
      t.chi === 'te' ? ['tocca a te', ''] : null].filter(Boolean);
    const alto = nodi.some(n => !n.fantasma && avvisi(n.t).length) ? 90 : 72;
    // the title on two lines (a box is narrow and the words are what tell tasks apart), the second cut with an ellipsis;
    // the line below cut by characters, so the project shows as far as it fits
    const dueRighe = (v, max) => {
      if (v.length <= max) return [v];
      const i = v.slice(0, max + 1).lastIndexOf(' '), a = i > max / 2 ? v.slice(0, i) : v.slice(0, max);
      return [a, taglia(v.slice(a.length).trim(), max)];
    };
    const corto = (v, max) => v.length > max ? v.slice(0, max - 1).trimEnd() + '…' : v;
    const g = impaginaGrafo(nodi, W, alto), r = g.radice;
    const dipendenti = new Map();
    for (const n of nodi) for (const k of n.dopo) dipendenti.set(k, [...(dipendenti.get(k) || []), n.chiave]);
    const freccia = (id) => s('marker', { id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto' }, [s('path', { d: 'M0 0L10 5L0 10z' })]);
    const svg = s('svg', { class: 'grafo-svg', width: W, height: g.alto }, [s('defs', {}, [freccia('grafo-freccia'), freccia('grafo-freccia-forte')])]);
    // arrows first: a box is opaque, so nothing reads as running through it
    for (const a of g.archi) {
      const da = a.da && per.get(a.da), verso = per.get(a.a);
      const P = s('path', { class: 'grafo-arco' + (a.radice ? ' radice' : '') + ((da && da.fantasma) || verso.fantasma ? ' fantasma' : '') + (da && da.t.stato === 'fatto' ? ' fatto' : ''), d: a.d,
        ...(a.radice ? {} : { 'marker-end': 'url(#grafo-freccia)' }) });
      svg.appendChild(P);
      grafoArchi.push({ ...a, P });
    }
    // a row wrapped onto more lines: a bracket in the left gutter says it is still one row
    for (const st of g.strati) {
      if (st.avanzo) svg.appendChild(s('text', { class: 'grafo-nota', x: GRAFO.lato, y: st.y0 - 12 }, ['fuori ordine: dipendenze in ciclo']));
      if (st.linee < 2) continue;
      const m = (st.y0 + st.y1) / 2;
      svg.append(s('path', { class: 'grafo-parentesi', d: `M${GRAFO.lato - 4} ${st.y0}H${GRAFO.lato - 10}V${st.y1}H${GRAFO.lato - 4}` }, [s('title', {}, ['Passo ' + (st.strato + 1) + ': ' + st.chiavi.length + ' task in parallelo'])]),
        s('text', { class: 'grafo-parallelo', x: 12, y: m, transform: `rotate(-90 12 ${m})` }, ['in parallelo']));
    }
    // the root: the goal itself, the same words as its band box; pressing it leaves the graph
    const scadenza = scade(o), stato = rischio(o);
    const R = s('g', { class: 'grafo-radice' + (stato === 'scaduto' ? ' scaduto' : stato ? ' a-rischio' : ''), tabindex: 0, role: 'button',
      'aria-label': o.titolo + ', obiettivo: ' + contoObiettivo(o) + (scadenza ? ', ' + scadenza : '') + (stato ? ', ' + stato : '') + '. Premi per tornare alla mappa' });
    R.append(s('title', {}, [o.titolo + '\n' + contoObiettivo(o)]), s('rect', { class: 'grafo-anello', x: r.x - 4, y: r.y - 4, width: r.w + 8, height: r.h + 8, rx: 13 }),
      s('rect', { class: 'grafo-box', x: r.x, y: r.y, width: r.w, height: r.h, rx: 10 }),
      s('text', { class: 'grafo-titolo', x: r.x + 14, y: r.y + 22 }, [taglia(o.titolo, Math.floor((r.w - 28) / 6.6))]),
      s('text', { class: 'grafo-sub', x: r.x + 14, y: r.y + 42 }, [taglia(contoObiettivo(o), Math.floor((r.w - 28) / 5.6))]));
    if (scadenza) R.append(s('text', { class: 'grafo-sub', x: r.x + 14, y: r.y + 60 }, [scadenza, ...(stato ? [s('tspan', { class: 'obiettivo-rischio' }, [' · ' + stato])] : [])]));
    R.addEventListener('click', e => { e.stopPropagation(); chiudiGrafo(); });   // as a satellite: the page's click never undoes it
    R.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); chiudiGrafo(); } });
    svg.appendChild(R);
    if (!nodi.length) svg.appendChild(s('text', { class: 'mappa-vuota', x: W / 2, y: r.y + r.h + 48 }, [o.task.length ? 'Tutti i task sono fatti: «Mostra fatti» li mostra.' : NESSUN_PASSO]));
    // the boxes in reading order, row by row and left to right: that is also the Tab order
    for (const st of g.strati) for (const k of st.chiavi) {
      const n = per.get(k), t = n.t, p = g.posti.get(k), suo = nodoPer(t.nodo);
      const vis = statoVisivo(t), parola = t.derivato === 'errore' ? 'errore' : NOME_VISIVO[vis];
      const stima = !n.fantasma && t.stima ? String(Math.round(t.stima * 10) / 10).replace('.', ',') + 'h' : '';
      const sotto = [n.fantasma, parola, stima, t.nodo].filter(Boolean).join(' · '), segni = n.fantasma ? [] : avvisi(t);
      const nomi = ks => ks.map(c => breve(per.get(c).t.vista)).join('; ');
      const etichetta = [t.vista, n.fantasma, parola, t.nodo, st.avanzo ? 'fuori ordine: dipendenze in ciclo' : 'passo ' + (st.strato + 1), ...segni.map(([w]) => w),
        n.dopo.length ? 'aspetta: ' + nomi(n.dopo) : '', (dipendenti.get(k) || []).length ? 'sblocca: ' + nomi(dipendenti.get(k)) : '',
        n.fantasma ? (t.obiettivo ? 'apre il suo obiettivo' : 'apre il suo nodo') : ''].filter(Boolean).join(', ');
      const G = s('g', { class: 'grafo-nodo st-' + vis + (t.derivato === 'errore' || st.avanzo ? ' errore' : '') + (n.fantasma ? ' fantasma' : '') + (t.ritardo ? ' ritardo' : ''),
        tabindex: 0, role: 'button', 'aria-label': etichetta, 'data-chiave': k });
      G.append(s('title', {}, [[t.vista, ...(suo ? motivi(t, suo) : [])].join('\n')]),
        s('rect', { class: 'grafo-anello', x: p.x - 4, y: p.y - 4, width: p.w + 8, height: p.h + 8, rx: 13 }),
        s('rect', { class: 'grafo-box', x: p.x, y: p.y, width: p.w, height: p.h, rx: 10 }),
        s('circle', { class: 'grafo-punto', cx: p.x + 16, cy: p.y + 17, r: 4 }),
        s('text', { class: 'grafo-titolo', x: p.x + 28, y: p.y + 21 }, dueRighe(breve(t.vista), Math.floor((p.w - 40) / 6.6)).map((v, i) => s('tspan', { x: p.x + 28, dy: i ? 17 : 0 }, [v]))),
        s('text', { class: 'grafo-sub', x: p.x + 12, y: p.y + 58 }, [s('tspan', { class: 'grafo-stato' }, [corto(sotto, Math.floor((p.w - 24) / 5.6))])]));
      if (segni.length) G.append(s('text', { class: 'grafo-sub', x: p.x + 12, y: p.y + 76 }, segni.flatMap(([w, c], i) => [i ? ' · ' : '', s('tspan', { class: c }, [w])]).filter(Boolean)));
      const premi = () => n.fantasma ? vaiAlFantasma(t) : scegliNelGrafo(t);
      G.addEventListener('click', e => { e.stopPropagation(); premi(); });   // a ghost may have redrawn this box away before the page saw it
      G.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); premi(); } });
      grafoScatole.set(k, G);
      svg.appendChild(G);
    }
    box.setAttribute('aria-label', 'Grafo dell\'obiettivo ' + o.titolo + ': un passo per riga, i task della stessa riga possono procedere in parallelo, le frecce vanno da ciò che blocca a ciò che aspetta. La stessa lista è sotto.');
    box.replaceChildren(svg);
    const ancora = fuoco && grafoScatole.get(fuoco);
    if (ancora) ancora.focus({ preventScroll: true });   // a refresh redrew the box that had the focus
    else if (prima) R.focus({ preventScroll: true });
    if (!conMoto) return;
    anima(box, [{ opacity: 0, transform: 'scale(.98)' }, { opacity: 1, transform: 'none' }], 200);
    for (const a of grafoArchi) {
      const L = a.P.getTotalLength(), riga = g.posti.get(a.a).strato;
      anima(a.P, [{ strokeDasharray: L, strokeDashoffset: L }, { strokeDasharray: L, strokeDashoffset: 0 }], 250, 120 + Math.min(riga, 6) * 40);
    }
  }
  // The selected box, and its blockers and dependents with their arrows, stand out; the rest dims a little. Classes only.
  function evidenziaGrafo() {
    const box = $('mappa-grafo'), k = selezione && chiaveTask(selezione), su = !!k && grafoScatole.has(k);
    if (!box) return;
    const legato = a => su && !a.radice && (a.da === k || a.a === k), vicini = new Set();
    for (const a of grafoArchi) if (legato(a)) { vicini.add(a.da); vicini.add(a.a); }
    box.classList.toggle('con-scelta', su);
    for (const [c, G] of grafoScatole) {
      G.classList.toggle('scelto', su && c === k);
      G.classList.toggle('vicino', su && c !== k && vicini.has(c));
      if (su && c === k) G.setAttribute('aria-current', 'true'); else G.removeAttribute('aria-current');
    }
    for (const a of grafoArchi) {
      a.P.classList.toggle('vicino', legato(a));
      if (!a.radice) a.P.setAttribute('marker-end', legato(a) ? 'url(#grafo-freccia-forte)' : 'url(#grafo-freccia)');
    }
  }

  // ---- lista equivalente (lettori di schermo; sotto i 760px prende il posto della mappa) ----
  // one task of the list, for nodes and goals alike; under a goal the row also names its node
  function rigaLista(n, t, conNodo) {
    return h('li', 'task-lista st-' + statoVisivo(t) + (t.derivato === 'errore' ? ' errore' : ''), [
      h('i', 'punto st-' + statoVisivo(t)), bottone(t.vista, 'link' + (t.ritardo ? ' ritardo' : ''), () => { scegliTask(n.nome, t); $('mappa-dettaglio').scrollIntoView({ block: 'nearest' }); }),
      h('span', 'sub', [NOME_VISIVO[statoVisivo(t)] + (t.data ? ' · ' + giornoBreve(t.data) : '') + (conNodo ? ' · ' + n.nome : '')]),
      ...segniScadenza(t),
      ...motivi(t, n).map(m => h('span', 'sub motivo', [m])),
      ...segniRepo(t),
      conNodo ? null : segnoObiettivo(t),   // under a goal the row already sits in its goal
    ]);
  }
  // A goal in the list: its open tasks by row, the same rows as the graph (a ghost is a row too, named as such), then «Fatti»
  // folded as in the other groups (not under «Aperti»). Below 760px this is the goal graph.
  function passiLista(o) {
    const nodi = nodiGrafo(o, tuttiITask(), false), { strato, avanzo, quanti } = stratiGrafo(nodi);
    const righe = Array.from({ length: quanti }, () => []);
    for (const n of nodi.slice().sort((a, b) => a.ordine - b.ordine)) righe[strato.get(n.chiave)].push(n);
    const riga = t => rigaLista(nodoPer(t.nodo), t, true);
    return [
      ...righe.flatMap((r, i) => [
        h('h4', 'gruppo', [r.some(n => avanzo.has(n.chiave)) ? 'Fuori ordine — dipendenze in ciclo: ' + r.length + ' task'
          : 'Passo ' + (i + 1) + ' — ' + (r.length > 1 ? 'in parallelo: ' + r.length + ' task' : '1 task')]),
        h('ul', 'task-elenco', r.map(n => { const li = riga(n.t); if (n.fantasma) li.append(h('span', 'sub', [n.fantasma])); return li; })),
      ]),
      ...(filtro === 'aperti' ? [] : gruppi(o.task.filter(t => t.stato === 'fatto'), riga, 'h4')),
    ];
  }
  function lista() {
    const ul = $('mappa-lista');
    if (!ul || !dati) return;
    const daMostrare = ts => filtro === 'aperti' ? ts.filter(t => t.stato !== 'fatto') : ts;
    const obiettivi = obiettiviVisibili().map(o => h('li', '', [
      h('h3', '', [o.titolo, h('span', 'tipo-nodo', [o.definito ? 'obiettivo' : 'obiettivo non definito']), h('span', 'sub', [contoObiettivo(o) + (scade(o) ? ' · ' + scade(o) : '')]), etichettaRischio(o)]),
      ...(o.task.length ? passiLista(o) : [h('p', 'vuoto', [NESSUN_PASSO])]),
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
      h('span', 'task-testo' + (t.ritardo ? ' ritardo' : ''), [h('span', 'titolo-task', [h('i', 'punto st-' + vis), t.vista]), t.data ? h('span', 'sub', [' ' + (t.ritardo ? 'dal ' : '') + giornoBreve(t.data)]) : null, ...segniScadenza(t)]),
      conNodo ? h('span', 'sub', [n.nome]) : null,
      ...motivi(t, n).map(m => h('span', 'sub motivo', [m])),
      ...segniRepo(t, !conNodo && !!repoFiltrato(n)),
      conNodo ? null : segnoObiettivo(t),   // in a goal panel the row already sits in its goal
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
      const b = bottone(r === null ? 'tutti' : tagliata(r, 24), '', () => {
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
      // the project itself: only a project of the index with its own folder, under a name the server accepts
      n.tipo === 'progetto' && n.haCartella && NOME_PROGETTO.test(n.nome) ? h('div', 'riga-azioni azioni-progetto', [
        n.senzaRepo ? bottone('Imposta cartella', '', () => impostaCartella(n)) : null,   // no Repo line names a folder yet
        bottone('Archivia progetto', '', () => archivia(n)),
      ]) : null,
    ];
  }
  // Panel of a goal: its steps across projects, in the same groups as a node
  function dettaglioObiettivo(o) {
    return [
      h('h2', '', [o.titolo, h('span', 'sub', ['obiettivo' + (o.progetti.length ? ' · ' + o.progetti.join(', ') : '')])]),
      o.task.length ? h('p', 'sub conto-nodo', [contoObiettivo(o)]) : null,
      // the deadline lines only with a deadline: the day counts are checked integers, so an older server never prints «NaN»
      ...(o.scadenza ? [
        h('p', 'scadenza-obiettivo', [scade(o), etichettaRischio(o)]),
        Number.isInteger(o.giorniNecessari) && Number.isInteger(o.giorniDisponibili) ? h('p', 'sub', [
          (o.giorniNecessari === 1 ? 'serve 1 giorno' : 'servono ' + o.giorniNecessari + ' giorni') + ', ' + (o.giorniDisponibili === 1 ? 'ne resta 1' : 'ne restano ' + o.giorniDisponibili)]) : null,
        h('p', 'sub', [PARALLELO]),
      ] : []),
      o.piano ? h('p', 'sub', ['Piano: ', h('span', 'repo', [o.piano])]) : null,   // a path in the project's repo, shown as text only
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
  // Archives a project: the row leaves projects/INDEX.md and the folder moves to projects/_archivio/<nome> (the server picks a
  // free name and checks everything again). Reversible, but it changes the vault: always behind this dialog, «Annulla» focused.
  const NOME_PROGETTO = /^[a-z0-9][a-z0-9-]{0,59}$/;   // the server's rule (NOME_PROGETTO): other names are never offered
  function archivia(n) {
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    const d = dialogo('mappa-archivia', 'Archivia progetto');
    const ok = bottone('Archivia', 'primario', async () => {
      ok.disabled = true;
      try {
        const r = await invia('/api/mappa/archivia', { nome: n.nome });
        d.close();
        if (r.stato === 400) return toast(CAMPO_NON_VALIDO[r.json && r.json.errore] || 'Dati non validi.');
        if (!r.ok) return errore(r);
        toast('Archiviato: ' + n.nome + '. La cartella è in ' + r.json.archivio + '.');
        deseleziona();
        await carica();
        fuocoAlPannello();   // the dialog gave the focus back to «Archivia progetto», which is gone with the project
      } catch (e) { d.close(); toast('Non è andata: ' + e.message); }
    });
    const annulla = bottone('Annulla', '', () => d.close());
    d.replaceChildren(h('form', '', [
      h('h2', '', ['Archivia progetto']),
      h('p', '', ['Archiviare ' + n.nome + '? La riga sparisce da INDEX e la cartella va in projects/_archivio/' + n.nome + '. I task del piano restano.']),
      h('p', 'sub', ['Si può annullare: rimetti la cartella in projects/ e la riga in INDEX.md. Nessun repo viene toccato.']),
      h('div', 'riga-azioni', [ok, annulla]),
    ], { method: 'dialog' }));
    d.showModal();
    annulla.focus();   // the safe choice is the one under Enter
  }
  // The folder of a project with no repo: a `- **Repo:**` line in its STATE. The server checks the path as for a new project
  // (a local git repo, not a network or reserved path, not a disk root, not inside projects/) and answers with a code only.
  function impostaCartella(n) {
    if (inProva()) return toast('Modalità prova: nessuna modifica.');
    const d = dialogo('mappa-cartella', 'Imposta cartella');
    const campo = h('input', '', [], { type: 'text', maxlength: '400', required: '', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Percorso della cartella del repo' });
    const salva = bottone('Imposta', 'primario', () => {});
    salva.type = 'submit';
    const form = h('form', '', [
      h('h2', '', ['Imposta cartella']),
      h('p', 'sub', ['Progetto: ' + n.nome + '. Il percorso assoluto della cartella di un repo git su questo computer: si scrive nello STATE come riga Repo, e «Avvia» si apre lì.']),
      campo,
      h('div', 'riga-azioni', [salva, bottone('Annulla', '', () => d.close())]),
    ]);
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const cartella = campo.value.trim();
      if (!cartella || !form.reportValidity()) return;
      salva.disabled = true;
      try {
        const r = await invia('/api/mappa/cartella', { nome: n.nome, cartella });
        if (r.stato === 400) { salva.disabled = false; campo.focus(); return toast(CAMPO_NON_VALIDO[r.json && r.json.errore] || 'Dati non validi.'); }   // stays open: fix the path
        d.close();
        if (!r.ok) return errore(r);
        toast('Cartella impostata per ' + n.nome + '.');
        await carica();
      } catch (x) { d.close(); toast('Non è andata: ' + x.message); }
    });
    d.replaceChildren(form);
    d.showModal();
    campo.focus();
  }
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
  let chiavePannello;   // what the panel showed last: undefined before the first paint
  // The focus to the panel's title (focusable by script only), and the panel into view: for an action that removed the button
  // that had the focus, so a keyboard or screen reader user goes on from what changed instead of from the top of the page
  function fuocoAlPannello() {
    const titolo = $('mappa-dettaglio') && $('mappa-dettaglio').querySelector('h2');
    if (!titolo) return;
    titolo.setAttribute('tabindex', '-1');
    titolo.focus();
  }
  function pannello() {
    if (!dati || !$('mappa-dettaglio')) return;
    const o = obiettivoPer(fissato), n = fissato && nodoPer(fissato);
    $('mappa-dettaglio').replaceChildren(...(o ? dettaglioObiettivo(o) : n ? dettaglioNodo(n) : prossimaAzione()).filter(Boolean));
    // another node or goal (or none): the new content fades in; a refresh or a task picked in the same panel does not
    if (chiavePannello !== undefined && chiavePannello !== fissato) anima($('mappa-dettaglio'), [{ opacity: 0, transform: 'translateY(4px)' }, { opacity: 1, transform: 'none' }], 180);
    chiavePannello = fissato;
    // le righe in ritardo dei prossimi giorni
    const g = giorni.slice(0, 5);
    $('prossimi-giorni').replaceChildren(...(g.length ? [h('h2', '', ['Prossimi giorni']), h('ul', 'prossimi', g.map(v => h('li', '', [
      h('span', '', [v.vista || v.testo]), h('span', 'quando' + (v.inRitardo ? ' ritardo' : ''), [v.inRitardo ? 'dal ' + giornoBreve(v.data) : giornoBreve(v.data)]),
    ])))] : []));
    filo(); evidenziaObiettivo(); aggiornaGrafo();
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
    config: 'config.json non leggibile o non valido: l\'avvio è sospeso finché non lo correggi.',
    esiste: 'Esiste già un progetto con questo nome.',
    template: 'Mancano templates/STATE.md o templates/project-index-row.md.',
    riga: 'La riga del progetto in INDEX.md non si legge: correggi in Obsidian.',
    errore: 'Non è andata: riprova o guarda il log della dashboard.',
    spento: 'Il modulo dell\'harness non è attivo in config.json.',
    'senza-repo': 'Questo progetto non ha un repo: non c\'è niente da adeguare.',
    righe: 'Lo STATE del progetto è già a 20 righe: accorcialo, poi riprova.',
    'ha-repo': 'Questo progetto ha già un repo: per cambiarlo modifica la riga Repo del suo STATE.',
    archivio: 'La cartella del progetto non è una cartella semplice dentro projects/ (o lo è projects/_archivio): non la sposto.',
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
    lavoro: 'I progetti di lavoro e la cartella riservata non si toccano dalla dashboard.',
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
    // Two Repo lines with the same short name: without a valid repo: on the task the server refuses (409 cartella), so the
    // dialog says why instead of offering a choice that would fail. `t.repo` never holds a twin: the server left it out.
    const doppi = validi.length ? [] : n.repoDoppi || [];
    let candidati = doppi.length ? [] : validi.length ? validi : n.repo || [];
    if (ripresa && !doppi.length && candidati.length < 2) candidati = n.repo || [];
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
    avvia.disabled = radio.length > 0 || doppi.length > 0;   // nothing is picked for you; with twins nothing can start
    radio.forEach(x => x.addEventListener('change', () => { avvia.disabled = false; }));
    d.replaceChildren(h('form', '', [
      h('h2', '', ['Avvia in Claude']),
      h('p', 'sub', ['Si apre il Terminale con una sessione di Claude.']),
      h('p', 'sub', ['Nodo: ' + n.nome]),
      doppi.length ? h('p', 'sub motivo', ['Due repo di questo progetto hanno lo stesso nome (' + doppi.join(', ') + '): rinomina una delle cartelle o togli una riga Repo dallo STATE.'])
        : candidati.length === 1 ? h('p', 'sub', ['Repo: ' + candidati[0]]) : !candidati.length && n.cartella ? h('p', 'sub', ['Cartella: ' + n.cartella]) : null,
      h('p', 'titolo-dialogo', [t.vista]),
      radio.length ? h('fieldset', 'scelta-repo', [h('legend', '', ['Repo in cui avviare']), ...radio.map(x => h('label', '', [x, x.value]))]) : null,
      h('div', 'riga-azioni', [avvia, annulla]),
    ], { method: 'dialog' }));
    d.showModal();
  }

  // The map filter, from its buttons and from a goal chip: the pressed button follows, the map and the list are redrawn
  function impostaFiltro(k) {
    filtro = k;
    for (const b of document.querySelectorAll('.filtri-mappa [data-filtro]')) b.setAttribute('aria-pressed', String(b.getAttribute('data-filtro') === k));
    disegna(); lista();
  }

  // ---- struttura fissa (una volta) ----
  function struttura() {
    if ($('mappa-svg')) return;
    const filtri = h('div', 'scelta filtri-mappa', FILTRI.map(([k, nome]) => {
      const b = bottone(nome, '', () => impostaFiltro(k));
      b.setAttribute('aria-pressed', String(k === filtro));
      b.setAttribute('data-filtro', k);
      return b;
    }), { role: 'group', 'aria-label': 'Filtro della mappa' });
    const svg = s('svg', { id: 'mappa-svg', role: 'group', tabindex: 0, 'aria-label': 'Mappa dei progetti e dei loro task: la stessa lista è sotto. Frecce per spostarla, più e meno per lo zoom, zero per la vista intera' });
    gesti(svg);
    const zoom = h('div', 'mappa-zoom', [
      bottone('+', '', () => zoomCentro(1.25)), bottone('−', '', () => zoomCentro(0.8)), bottone('Adatta', '', adatta),
    ], { role: 'group', 'aria-label': 'Zoom della mappa' });
    [['Ingrandisci', 0], ['Riduci', 1], ['Adatta alla vista', 2]].forEach(([nome, i]) => zoom.children[i].setAttribute('aria-label', nome));
    svg.addEventListener('pointerleave', () => { if (!fuocoNeiSatelliti()) apri(fissato, false, true); });
    const legenda = h('div', 'legenda', GRUPPI.map(([st]) => h('span', '', [h('i', 'punto st-' + st), NOME_VISIVO[st]])));
    // shown only with the goal graph open, in place of the filters: the done toggle keeps its focus across the redraw
    const fatti = bottone('Mostra fatti', 'grafo-fatti', () => { grafoFatti = !grafoFatti; aggiornaGrafo(); });
    const grafoAzioni = h('div', 'grafo-azioni', [fatti, bottone('Mappa', '', chiudiGrafo)]);
    $('mappa-area').replaceChildren(h('div', 'mappa-box', [
      h('div', 'mappa-testa', [h('h2', '', ['Mappa del lavoro']), h('div', 'mappa-testa-azioni', [filtri, bottone('Nuovo progetto', '', nuovoProgetto), grafoAzioni])]), svg, legenda, zoom,
      h('div', 'mappa-grafo', [], { id: 'mappa-grafo', role: 'group', hidden: '' }),
      h('ul', 'mappa-lista', [], { id: 'mappa-lista', 'aria-label': 'Nodi e task, in elenco' }),
    ]), h('p', 'nota-mappa', ['Il numero sul nodo = task pronti da avviare. Social: bozze da pubblicare.']));
    new ResizeObserver(() => {
      const q = svg.clientWidth + 'x' + svg.clientHeight;
      if (dati && q !== dimensione) disegna();
      aggiornaGrafo();   // a new width lays the graph out again
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
    if (e.key !== 'Escape' || document.querySelector('dialog[open]') || $('mappa-vista').hidden) return;
    if (grafo && $('mappa-grafo').clientWidth) chiudiGrafo();   // first out of the graph, the goal still fixed; then as before
    else if (fissato || aperto) deseleziona();
  });
  // un clic fuori dal task evidenziato (e dai satelliti, dalla lista e dai dialog) toglie l'evidenziazione
  document.addEventListener('click', e => {
    const dopoTrascinamento = trascinato; trascinato = false;   // il clic che segue uno spostamento non conta
    if (dopoTrascinamento || !selezione || $('mappa-vista').hidden || e.target.closest('#mappa-dettaglio .task, #mappa-dettaglio summary, #mappa-satelliti .sat, .grafo-azioni, #mappa-lista, .mappa-zoom, dialog')) return;
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
