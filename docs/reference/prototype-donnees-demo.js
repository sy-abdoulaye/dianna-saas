'use strict';
/* ===== Dates et utilitaires ===== */
const TODAY = '2026-10-19';
const MONTHS = ['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'];
const MS = ['janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];
const DN = ['dim.','lun.','mar.','mer.','jeu.','ven.','sam.'];
const pad = n => String(n).padStart(2, '0');
const iso = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
const parse = s => { const a = s.split('-').map(Number); return new Date(a[0], a[1] - 1, a[2]); };
const addDays = (s, n) => { const d = parse(s); d.setDate(d.getDate() + n); return iso(d); };
const dow = s => parse(s).getDay();
const isWE = s => { const w = dow(s); return w === 0 || w === 6; };
const mondayOf = s => addDays(s, -((dow(s) + 6) % 7));
const fmt = s => { const d = parse(s); return d.getDate() + (d.getDate() === 1 ? 'er' : '') + ' ' + MONTHS[d.getMonth()] + ' ' + d.getFullYear(); };
const fmtS = s => { const d = parse(s); return d.getDate() + ' ' + MS[d.getMonth()]; };
const fmtD = s => { const d = parse(s); return DN[d.getDay()] + ' ' + d.getDate() + ' ' + MS[d.getMonth()]; };
const fmtR = (a, b) => a === b ? fmt(a) : fmtS(a) + ' au ' + fmt(b);
const daysBetween = (a, b) => Math.round((parse(b) - parse(a)) / 86400000);
const workdays = (a, b) => { let n = 0; for (let d = a; d <= b; d = addDays(d, 1)) if (!isWE(d)) n++; return n; };
const slug = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z]/g, '');

/* ===== Profils ===== */
const ROLES = { employe: 'Salarié', mgr: 'Manager', rh: 'Ressources humaines', admin: 'Administrateur' };
const ROLE_USER = { employe: 'p1', mgr: 'p5', rh: 'p9', admin: 'p10' };

const SERVICES0 = ['Support client', 'Produit et technique', 'Finance', 'Moyens généraux', 'Ressources humaines', 'Ventes'];
const SITES0 = ['Lyon', 'Paris', 'Nantes'];

function seedPeople() {
  // prénom, nom, poste, service, site, manager, profil, statut, arrivée, contrat
  const T = [
    ['Camille','Durand','Conseillère support','Support client','Lyon','p5','employe','actif','2022-03-14','CDI'],
    ['Mehdi','Benali','Développeur','Produit et technique','Paris','p6','employe','actif','2023-09-04','CDI'],
    ['Thomas','Roux','Chargé de support','Support client','Lyon','p5','employe','actif','2021-01-18','CDI'],
    ['Inès','Garcia','Cheffe de projet','Produit et technique','Paris','p6','employe','actif','2020-06-01','CDI'],
    ['Louise','Martin','Responsable support','Support client','Lyon','p9','mgr','actif','2019-02-11','CDI'],
    ['Paul','Lefèvre','Directeur technique','Produit et technique','Paris','p9','mgr','actif','2018-05-07','CDI'],
    ['Sofia','Nunes','Comptable','Finance','Nantes','p21','employe','arrivee','2026-11-03','CDI'],
    ['Antoine','Bernard','Technicien matériel','Moyens généraux','Lyon','p9','employe','actif','2022-10-03','CDI'],
    ['Hélène','Faure','Directrice des ressources humaines','Ressources humaines','Paris','','rh','actif','2017-09-01','CDI'],
    ['Marc','Diallo','Administrateur de la plateforme','Moyens généraux','Paris','p9','admin','actif','2021-04-12','CDI'],
    ['Yasmine','Kaci','Chargée de recrutement','Ressources humaines','Paris','p9','rh','actif','2024-01-08','CDI'],
    ['Julien','Petit','Commercial','Ventes','Nantes','p17','employe','parti','2020-11-02','CDI'],
    ['Nina','Lambert','Conseillère support','Support client','Lyon','p5','employe','actif','2023-03-20','CDD'],
    ['Hugo','Fabre','Conseiller support','Support client','Lyon','p5','employe','actif','2024-05-06','CDI'],
    ['Léa','Fontaine','Développeuse','Produit et technique','Paris','p6','employe','actif','2022-01-24','CDI'],
    ['Karim','Haddad','Développeur','Produit et technique','Nantes','p6','employe','actif','2021-09-13','CDI'],
    ['Claire','Dubois','Responsable ventes','Ventes','Nantes','p9','mgr','actif','2019-10-14','CDI'],
    ['Bastien','Moreau','Commercial','Ventes','Nantes','p17','employe','actif','2023-02-27','CDI'],
    ['Amélie','Chevalier','Commerciale','Ventes','Paris','p17','employe','actif','2022-08-29','CDI'],
    ['Romain','Girard','Comptable','Finance','Nantes','p21','employe','actif','2020-03-02','CDI'],
    ['Élodie','Vidal','Responsable finance','Finance','Nantes','p9','mgr','actif','2018-11-19','CDI'],
    ['Samuel','Perrin','Analyste financier','Finance','Nantes','p21','employe','actif','2024-09-02','CDI'],
    ['Chloé','Renard','Designer produit','Produit et technique','Paris','p6','employe','actif','2023-06-12','CDI'],
    ['Pierre','Blanc','Conseiller support','Support client','Lyon','p5','employe','actif','2025-02-03','CDI']
  ];
  return T.map((t, i) => ({
    id: 'p' + (i + 1), first: t[0], last: t[1], poste: t[2], service: t[3], site: t[4], mgr: t[5] || null, role: t[6], status: t[7],
    arrival: t[8], contrat: t[9], temps: 'Temps plein, 35 h', matricule: String(210 + i * 7).padStart(5, '0'),
    email: slug(t[0]) + '.' + slug(t[1]) + '@exemple.fr', tel: '04 72 00 00 ' + pad(10 + i), bureau: 'Étage ' + (1 + i % 4) + ', B-' + (10 + i), ttDays: 2
  }));
}

function seedRequests() {
  const R = [];
  let n = 0;
  const add = (kind, pid, status, data, by) => {
    n++;
    const created = addDays(TODAY, -(2 + (n % 9)));
    const hist = [{ at: created, by: pid, txt: 'Demande envoyée' }];
    if (status === 'valide') hist.push({ at: addDays(created, 1), by: by || 'p5', txt: 'Demande validée' });
    if (status === 'refuse') hist.push({ at: addDays(created, 1), by: by || 'p5', txt: 'Demande refusée', note: 'Effectif insuffisant ce jour-là.' });
    R.push({ id: 'r' + n, kind, pid, status, created, data, hist });
  };
  const wk = mondayOf(TODAY);
  // Télétravail cette semaine et la suivante
  add('teletravail', 'p1', 'valide', { date: addDays(wk, 2), motif: '' });
  add('teletravail', 'p1', 'en_attente', { date: addDays(wk, 7 + 2), motif: 'Travaux dans l\'immeuble' });
  add('teletravail', 'p3', 'valide', { date: addDays(wk, 1), motif: '' });
  add('teletravail', 'p3', 'valide', { date: addDays(wk, 3), motif: '' });
  add('teletravail', 'p13', 'en_attente', { date: addDays(wk, 4), motif: '' });
  add('teletravail', 'p24', 'refuse', { date: addDays(wk, 2), motif: 'Rendez-vous médical' });
  add('teletravail', 'p2', 'valide', { date: addDays(wk, 0), motif: '' }, 'p6');
  add('teletravail', 'p4', 'valide', { date: addDays(wk, 4), motif: '' }, 'p6');
  add('teletravail', 'p15', 'valide', { date: addDays(wk, 1), motif: '' }, 'p6');
  add('teletravail', 'p14', 'en_attente', { date: addDays(wk, 7 + 1), motif: '' });
  // Congés estivaux 2027
  add('conges', 'p1', 'en_attente', { start: '2027-08-02', end: '2027-08-13', type: 'Congés d\'été', note: 'Deux semaines en famille' });
  add('conges', 'p3', 'valide', { start: '2027-07-19', end: '2027-07-30', type: 'Congés d\'été', note: '' });
  add('conges', 'p13', 'en_attente', { start: '2027-08-02', end: '2027-08-20', type: 'Congés d\'été', note: '' });
  add('conges', 'p24', 'valide', { start: '2027-08-09', end: '2027-08-27', type: 'Congés d\'été', note: '' });
  add('conges', 'p14', 'en_attente', { start: '2027-07-26', end: '2027-08-06', type: 'Congés d\'été', note: '' });
  add('conges', 'p2', 'valide', { start: '2027-08-02', end: '2027-08-20', type: 'Congés d\'été', note: '' }, 'p6');
  add('conges', 'p4', 'en_attente', { start: '2027-07-12', end: '2027-07-23', type: 'Congés d\'été', note: '' });
  add('conges', 'p5', 'valide', { start: '2027-08-16', end: '2027-08-27', type: 'Congés d\'été', note: '' }, 'p9');
  // Congés ponctuels cette semaine / semaine suivante pour le planning
  add('conges', 'p14', 'valide', { start: addDays(wk, 7), end: addDays(wk, 11), type: 'Autre absence', note: '' });
  // Astreintes
  add('astreinte', 'p3', 'valide', { start: addDays(wk, 4), end: addDays(wk, 6), type: 'Astreinte', heures: 0, note: 'Week-end d\'astreinte' });
  add('astreinte', 'p24', 'en_attente', { start: addDays(wk, 11), end: addDays(wk, 13), type: 'Astreinte', heures: 0, note: '' });
  add('astreinte', 'p3', 'valide', { start: addDays(wk, -3), end: addDays(wk, -3), type: 'Intervention', heures: 2.5, note: 'Incident serveur de messagerie' });
  add('astreinte', 'p16', 'en_attente', { start: addDays(wk, 5), end: addDays(wk, 6), type: 'Astreinte', heures: 0, note: '' }, 'p6');
  // Transport
  add('transport', 'p1', 'valide', { mois: '2026-09', type: 'Abonnement mensuel', montant: 84.1, fichier: 'abonnement-septembre.pdf' }, 'p9');
  add('transport', 'p1', 'en_attente', { mois: '2026-10', type: 'Abonnement mensuel', montant: 84.1, fichier: 'abonnement-octobre.pdf' });
  add('transport', 'p3', 'en_attente', { mois: '2026-10', type: 'Abonnement mensuel', montant: 84.1, fichier: 'justificatif-tcl.pdf' });
  add('transport', 'p2', 'refuse', { mois: '2026-09', type: 'Titre unique', montant: 12.4, fichier: 'ticket.jpg' }, 'p9');
  add('transport', 'p15', 'en_attente', { mois: '2026-10', type: 'Abonnement mensuel', montant: 86.4, fichier: 'navigo-oct.pdf' });
  // Matériel
  add('materiel', 'p1', 'en_attente', { type: 'Casque audio', motif: 'Casque actuel défectueux (micro)' });
  add('materiel', 'p13', 'valide', { type: 'Écran', motif: 'Deuxième écran pour le suivi des tickets' }, 'p9');
  add('materiel', 'p2', 'en_attente', { type: 'Ordinateur portable', motif: 'Renouvellement (4 ans)' });
  return R;
}

function seedEquipment() {
  const E = [
    ['Ordinateur portable','Dell Latitude 5440','p1','attribue'],['Écran','Dell U2723QE 27"','p1','attribue'],
    ['Ordinateur portable','Dell Latitude 5440','p3','attribue'],['Casque audio','Jabra Evolve2 55','p3','attribue'],
    ['Ordinateur portable','MacBook Pro 14"','p2','attribue'],['Ordinateur portable','MacBook Pro 14"','p4','attribue'],
    ['Ordinateur portable','Dell Latitude 5440','p5','attribue'],['Téléphone','iPhone 14','p5','attribue'],
    ['Écran','Dell U2723QE 27"','p13','attribue'],['Ordinateur portable','Dell Latitude 5440','p13','attribue'],
    ['Ordinateur portable','Dell Latitude 5440',null,'stock'],['Écran','Dell U2723QE 27"',null,'stock'],
    ['Casque audio','Jabra Evolve2 55',null,'stock'],['Ordinateur portable','Lenovo ThinkPad T14',null,'repar'],
    ['Téléphone','iPhone 13',null,'stock']
  ];
  return E.map((e, i) => ({ id: 'e' + (i + 1), type: e[0], model: e[1], serial: 'DN-' + String(1040 + i * 13).padStart(5, '0'), holder: e[2], status: e[3], since: e[2] ? addDays(TODAY, -(40 + i * 23)) : null }));
}

function seedAnnonces() {
  return [
    { id: 'a1', title: 'Fermeture du site de Lyon le 24 décembre', cat: 'Vie du site', body: 'Le site de Lyon sera fermé le jeudi 24 décembre. Les équipes support passent en astreinte renforcée. Merci de poser vos congés avant le 20 novembre.', by: 'p9', date: addDays(TODAY, -2), pinned: true, read: ['p3'] },
    { id: 'a2', title: 'Campagne des entretiens individuels 2026', cat: 'RH', body: 'La campagne est ouverte du 5 octobre au 18 décembre. Chaque salarié complète son auto-évaluation, puis son manager planifie l\'entretien.', by: 'p9', date: addDays(TODAY, -7), pinned: true, read: ['p1', 'p3', 'p5'] },
    { id: 'a3', title: 'Nouvelle politique de télétravail', cat: 'Entreprise', body: 'Deux jours de télétravail par semaine, à déclarer dans Dianna au plus tard la veille. Les demandes sont validées par le manager.', by: 'p9', date: addDays(TODAY, -15), pinned: false, read: ['p1', 'p5'] },
    { id: 'a4', title: 'Rappel : exercice d\'évacuation à Paris', cat: 'Sécurité', body: 'Un exercice d\'évacuation aura lieu le jeudi 5 novembre à 10 h. Le point de rassemblement est devant l\'entrée principale.', by: 'p10', date: addDays(TODAY, -21), pinned: false, read: ['p1'] },
    { id: 'a5', title: 'Bienvenue à Sofia Nunes', cat: 'Entreprise', body: 'Sofia rejoindra l\'équipe finance à Nantes le 3 novembre en tant que comptable.', by: 'p9', date: addDays(TODAY, -3), pinned: false, read: [] }
  ];
}

function seedQuestionnaires() {
  let seed = 7;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const COMS = { 2: ['Les pics de charge reviennent chaque fin de mois.', 'Peu d\'échanges avec les autres équipes.'], 3: ['Correct, mais les outils sont parfois lents.', 'Ça dépend des semaines.'], 4: ['Bonne entente, réunions utiles.', 'Le télétravail aide beaucoup.'], 5: ['Très bonne ambiance dans l\'équipe.', 'Matériel récent et adapté.'] };
  const resp = (qs, n, ids) => ids.slice(0, n).map(pid => { const answers = qs.map(q => q.t === 'scale' ? 2 + Math.floor(rnd() * 4) : (rnd() > 0.5 ? 'Plus de visibilité sur le planning de l\'équipe.' : '')); const comments = {}; answers.forEach((a, i) => { if (qs[i].t === 'scale' && rnd() > 0.6) comments[i] = COMS[a][Math.floor(rnd() * 2)]; }); return { pid, answers, comments }; });
  const q1 = [{ t: 'scale', l: 'Je me sens bien dans mon équipe.' }, { t: 'scale', l: 'Ma charge de travail est soutenable.' }, { t: 'scale', l: 'Je dispose des outils nécessaires pour travailler.' }, { t: 'text', l: 'Qu\'est-ce qui pourrait améliorer votre quotidien ?' }];
  const q2 = [{ t: 'scale', l: 'Mon accueil s\'est bien passé.' }, { t: 'scale', l: 'Je comprends mes objectifs.' }, { t: 'text', l: 'Un point à améliorer dans l\'intégration ?' }];
  const q3 = [{ t: 'scale', l: 'Le télétravail m\'aide à mieux organiser ma semaine.' }, { t: 'scale', l: 'Je reste en contact avec mon équipe.' }];
  const ids = ['p2', 'p3', 'p4', 'p6', 'p8', 'p11', 'p13', 'p14', 'p15', 'p16', 'p18', 'p19', 'p20', 'p22', 'p23', 'p24', 'p17', 'p21'];
  return [
    { id: 'q1', title: 'Baromètre de qualité de vie au travail 2026', status: 'ouvert', audience: 'Tous les salariés', due: '2026-11-13', qs: q1, resp: resp(q1, 14, ids) },
    { id: 'q2', title: 'Retour sur l\'intégration des nouveaux arrivants', status: 'ouvert', audience: 'Arrivés depuis moins d\'un an', due: '2026-11-30', qs: q2, resp: resp(q2, 3, ['p24', 'p22', 'p14']) },
    { id: 'q3', title: 'Enquête télétravail 2025', status: 'clos', audience: 'Tous les salariés', due: '2025-12-12', qs: q3, resp: resp(q3, 18, ids.concat(['p1', 'p5'])) },
    { id: 'q4', title: 'Besoins de formation 2027', status: 'brouillon', audience: 'Tous les salariés', due: '', qs: [{ t: 'text', l: 'Quelle formation vous aiderait le plus en 2027 ?' }], resp: [] }
  ];
}

function seedEvals() {
  const O = (a, b) => [{ t: a, e: '2027-06-30' }, { t: b, e: '2027-12-31' }];
  return [
    { id: 'v1', pid: 'p1', kind: 'individuel', step: 'manager', self: { bilan: 'J\'ai réduit notre délai de première réponse et formé deux nouveaux arrivants. La certification ITIL est en cours : l\'examen est prévu en novembre.' }, mgr: null, obj: [], date: null, sign: {} },
    { id: 'v2', pid: 'p3', kind: 'individuel', step: 'entretien', self: { bilan: 'Année chargée mais satisfaisante. J\'ai pris la responsabilité de la base de connaissances.' }, mgr: { bilan: 'Thomas est fiable et très apprécié des clients. Il doit déléguer davantage.', rel: 4, aut: 3, eq: 3, out: 4, forts: 'Fiabilité, expertise produit.', axes: 'Déléguer, prendre la parole en réunion.' }, obj: O('Animer un atelier trimestriel de partage', 'Devenir référent de la base de connaissances'), date: addDays(TODAY, 9), sign: {} },
    { id: 'v3', pid: 'p13', kind: 'individuel', step: 'auto', self: null, mgr: null, obj: [], date: null, sign: {} },
    { id: 'v4', pid: 'p24', kind: 'individuel', step: 'auto', self: null, mgr: null, obj: [], date: null, sign: {} },
    { id: 'v5', pid: 'p14', kind: 'individuel', step: 'signature', self: { bilan: 'Très bonne première année. Je souhaite évoluer vers le support de niveau 2.' }, mgr: { bilan: 'Belle progression, bon esprit d\'équipe.', rel: 3, aut: 3, eq: 4, out: 3, forts: 'Esprit d\'équipe.', axes: 'Gagner en autonomie sur les cas complexes.' }, obj: O('Passer au support de niveau 2', 'Suivre la formation ITIL 4'), date: addDays(TODAY, -4), sign: { emp: true } },
    { id: 'v6', pid: 'p2', kind: 'individuel', step: 'clos', self: { bilan: 'Livraison du module de planning dans les temps.' }, mgr: { bilan: 'Excellente année technique.', rel: 3, aut: 4, eq: 3, out: 4, forts: 'Qualité du code.', axes: 'Documentation.' }, obj: O('Écrire la documentation technique', 'Encadrer un alternant'), date: addDays(TODAY, -12), sign: { emp: true, mgr: true } },
    { id: 'v7', pid: 'p4', kind: 'individuel', step: 'manager', self: { bilan: 'Trois projets livrés, dont la refonte de l\'espace client.' }, mgr: null, obj: [], date: null, sign: {} },
    { id: 'v8', pid: 'p1', kind: 'professionnel', step: 'clos', self: { bilan: 'Accueil des nouveaux arrivants et formation à la relation client difficile.', projet: 'Devenir référente support d\'ici deux ans.' }, mgr: { cr: 'Évolution positive. Formation à l\'animation accordée, ITIL à valider.' }, obj: [], date: '2026-03-14', sign: { emp: true, mgr: true }, formations: ['Animer un atelier (2 jours)', 'ITIL 4 Foundation (3 jours)'] },
    { id: 'v9', pid: 'p3', kind: 'professionnel', step: 'auto', self: null, mgr: null, obj: [], date: null, sign: {}, formations: [] },
    { id: 'v10', pid: 'p13', kind: 'professionnel', step: 'entretien', self: { bilan: 'Premier bilan depuis mon arrivée en 2023.', projet: 'Évoluer vers la formation interne.' }, mgr: { cr: '' }, obj: [], date: addDays(TODAY, 14), sign: {}, formations: [] }
  ];
}

function seedSuivi() {
  return [
    { id: 'n1', pid: 'p1', at: '2026-10-28', by: 'p5', kind: 'Entretien individuel', txt: 'Entretien prévu : objectifs 2027 à définir.', priv: false },
    { id: 'n2', pid: 'p1', at: '2026-09-12', by: 'p5', kind: 'Point de suivi', txt: 'Charge élevée en période de congés, renfort demandé sur les astreintes.', priv: false },
    { id: 'n3', pid: 'p1', at: '2026-09-12', by: 'p5', kind: 'Note privée', txt: 'À surveiller : risque de surcharge à l\'approche de l\'examen ITIL.', priv: true },
    { id: 'n4', pid: 'p1', at: '2026-06-03', by: 'p1', kind: 'Souhait salarié', txt: 'Souhait d\'évoluer vers un rôle de référente support. Formation à l\'animation demandée.', priv: false },
    { id: 'n5', pid: 'p1', at: '2026-03-14', by: 'p9', kind: 'Entretien professionnel', txt: 'Projet de formation validé, deux jours de formation planifiés.', priv: false },
    { id: 'n6', pid: 'p3', at: '2026-08-20', by: 'p5', kind: 'Point de suivi', txt: 'Très bon retour des clients sur la base de connaissances.', priv: false }
  ];
}

function seedNotifs() {
  return [
    { id: 'n1', to: 'p5', txt: 'Camille Durand a demandé un jour de télétravail le ' + fmtD(addDays(mondayOf(TODAY), 9)), route: 'teletravail', at: 'Il y a 2 h', read: false },
    { id: 'n2', to: 'p5', txt: 'Nina Lambert a demandé un jour de télétravail', route: 'teletravail', at: 'Hier', read: false },
    { id: 'n3', to: 'p1', txt: 'Votre télétravail du ' + fmtD(addDays(mondayOf(TODAY), 2)) + ' a été validé', route: 'teletravail', at: 'Hier', read: false },
    { id: 'n4', to: 'p1', txt: 'Louise Martin a ouvert votre auto-évaluation pour relecture', route: 'carriere/v1', at: 'Il y a 3 j', read: true },
    { id: 'n5', to: 'role:rh', txt: '2 justificatifs de transport sont à valider', route: 'transport', at: 'Aujourd\'hui', read: false },
    { id: 'n6', to: 'role:admin', txt: 'Sofia Nunes a été invitée sur Dianna', route: 'admin', at: 'Hier', read: false },
    { id: 'n7', to: 'p1', txt: 'Nouvelle annonce : Fermeture du site de Lyon le 24 décembre', route: 'annonces', at: 'Il y a 2 j', read: false }
  ];
}

function seedAudit() {
  return [
    { at: 'Aujourd\'hui 09:12', who: 'Hélène Faure', txt: 'a publié l\'annonce « Fermeture du site de Lyon »' },
    { at: 'Hier 16:40', who: 'Marc Diallo', txt: 'a invité Sofia Nunes (profil Salarié)' },
    { at: 'Hier 11:05', who: 'Louise Martin', txt: 'a validé le télétravail de Thomas Roux' },
    { at: 'Il y a 3 jours', who: 'Hélène Faure', txt: 'a modifié la fiche de Karim Haddad' }
  ];
}

function seedDB() {
  return {
    people: seedPeople(), requests: seedRequests(), equipment: seedEquipment(), annonces: seedAnnonces(), quests: seedQuestionnaires(),
    evals: seedEvals(), suivi: seedSuivi(), notifs: seedNotifs(), audit: seedAudit(),
    services: SERVICES0.slice(), sites: SITES0.slice(), modules: { interventions: true, annuaire: true, carriere: true, questionnaires: true, teletravail: true, astreinte: true, transport: true, materiel: true, conges: true, annonces: true, planning: true },
    interventions: seedInterventions(),
    company: { name: 'Exemple SAS', ttMax: 2, estival: 'Été 2027', estivalDue: '2027-02-28' }
  };
}

function seedInterventions() {
  const D = (desc, diff, sol, pct, delai, com) => ({ desc, diff, sol, pct, delai, com });
  const N = (desc, pct, delai, com) => ({ desc, pct, delai, com });
  return [
    { id: 'w1', pid: 'p1', mission: 'Support niveau 2 · contrat Atlas', periode: '2026-09', status: 'valide',
      done: [D('Traitement des tickets de niveau 2 sur la messagerie', 'Volume élevé en début de mois', 'Tri quotidien avec l\'équipe niveau 1', 100, '2026-09-30', ''), D('Rédaction de 6 fiches de la base de connaissances', '', '', 75, '2026-10-15', 'Deux fiches en relecture')],
      next: [N('Terminer les fiches de la base de connaissances', 100, '2026-10-15', ''), N('Former Pierre Blanc au niveau 2', 50, '2026-10-31', '')],
      vis: { etat: 'Prolongation probable', fin: '2026-12-31', prolong: 'oui', jusqu: '2027-06-30', suivi: 'Le client souhaite prolonger le contrat de six mois.' }, mgrNote: 'Très bon suivi, merci.', hist: [{ at: '2026-10-01', by: 'p1', txt: 'Compte rendu envoyé' }, { at: '2026-10-02', by: 'p5', txt: 'Compte rendu validé' }] },
    { id: 'w2', pid: 'p1', mission: 'Support niveau 2 · contrat Atlas', periode: '2026-10', status: 'brouillon',
      done: [D('Finalisation des fiches de la base de connaissances', 'Validation client plus lente que prévu', 'Relance hebdomadaire du référent client', 90, '2026-10-15', '')],
      next: [N('Mise à jour des procédures d\'astreinte', 30, '2026-11-20', '')],
      vis: { etat: 'Prolongation probable', fin: '2026-12-31', prolong: 'oui', jusqu: '2027-06-30', suivi: '' }, mgrNote: '', hist: [] },
    { id: 'w3', pid: 'p3', mission: 'Migration de la messagerie · Groupe Horizon', periode: '2026-10', status: 'envoye',
      done: [D('Migration de 420 boîtes aux lettres', 'Quotas dépassés sur 12 boîtes', 'Archivage préalable avec les utilisateurs concernés', 80, '2026-10-24', 'Reste le site de Nantes'), D('Plan de communication aux utilisateurs', '', '', 100, '2026-10-10', '')],
      next: [N('Migration du site de Nantes (85 boîtes)', 100, '2026-11-07', 'Créneau validé avec le client'), N('Bilan et clôture du projet', 0, '2026-11-21', '')],
      vis: { etat: 'Fin prévue', fin: '2026-11-21', prolong: 'non', jusqu: '', suivi: 'Prévoir un point de clôture avec le client.' }, mgrNote: '', hist: [{ at: '2026-10-17', by: 'p3', txt: 'Compte rendu envoyé' }] },
    { id: 'w4', pid: 'p2', mission: 'Refonte de l\'espace client', periode: '2026-10', status: 'revoir',
      done: [D('Développement du module de paiement', 'Dépendance à l\'API bancaire', 'Bouchon de test en attendant l\'accès', 60, '2026-10-31', '')],
      next: [N('Tests de bout en bout', 0, '2026-11-15', '')],
      vis: { etat: 'Incertaine', fin: '2026-11-30', prolong: 'non', jusqu: '', suivi: '' }, mgrNote: 'Précise le risque de retard lié à l\'API bancaire et la date de fin réaliste.', hist: [{ at: '2026-10-16', by: 'p2', txt: 'Compte rendu envoyé' }, { at: '2026-10-17', by: 'p6', txt: 'Complément demandé' }] }
  ];
}
