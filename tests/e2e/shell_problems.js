(margin) => {
  const problems = [];
  const root = document.documentElement;
  const main = document.querySelector('[data-main]');
  const side = document.getElementById('side');
  const content = document.getElementById('content');
  const name = (e) => `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}${[...e.classList].map(c => '.' + c).join('')}`;
  if (root.scrollWidth > innerWidth + 1) problems.push(`document large de ${root.scrollWidth} px`);
  // Le document défile ; il s'arrête au contenu (plus la marge prévue), sans zone vide dessous.
  const last = content.lastElementChild;
  if (last) {
    const contentBottom = last.getBoundingClientRect().bottom + scrollY;
    const limit = Math.max(innerHeight, contentBottom + margin);
    if (root.scrollHeight > limit + 1) problems.push(`document haut de ${root.scrollHeight} px pour ${Math.round(contentBottom)} px de contenu`);
  }
  // Aucun autre défilement que le document, le menu, les tableaux et les barres d'onglets.
  for (const e of document.querySelectorAll('body *')) {
    if (e.matches('textarea, select, input, option, dialog, dialog *') || e === side) continue;
    const style = getComputedStyle(e);
    const vertical = ['auto', 'scroll'].includes(style.overflowY) && e.scrollHeight > e.clientHeight + 1;
    const horizontal = ['auto', 'scroll'].includes(style.overflowX) && e.scrollWidth > e.clientWidth + 1;
    const table = e.querySelector('table') !== null;
    if (vertical && !table) problems.push(`barre verticale sur ${name(e)}`);
    if (horizontal && !table && !e.matches('.tabs')) problems.push(`barre horizontale sur ${name(e)}`);
  }
  if (getComputedStyle(main).overflowY !== 'visible') problems.push('zone principale avec un défilement propre');
  // Menu : sans barre visible, en haut et en bas de l'écran quelle que soit la position du document.
  const shown = getComputedStyle(side).visibility !== 'hidden';
  if (getComputedStyle(side).scrollbarWidth !== 'none') problems.push('barre de défilement visible dans le menu');
  if (side.scrollWidth > side.clientWidth + 1) problems.push('menu plus large que sa colonne');
  if (shown) {
    for (const y of [0, root.scrollHeight]) {
      scrollTo(0, y);
      const box = side.getBoundingClientRect();
      if (box.bottom < innerHeight - 1) problems.push(`menu arrêté à ${Math.round(box.bottom)} px (document à ${Math.round(scrollY)} px)`);
    }
    scrollTo(0, 0);
    const more = side.scrollTop + side.clientHeight < side.scrollHeight - 1;
    if (more !== side.classList.contains('fade-bottom')) problems.push(`dégradé du bas ${more ? 'absent' : 'en trop'}`);
  }
  // Recherche : au bord droit du menu déplié (à la marge du contenu), après le nom quand il est
  // replié, jamais sur le logo.
  const search = document.querySelector('.topbar .global-search');
  const brand = document.querySelector('.topbar .brand');
  if (search && brand) {
    const left = search.getBoundingClientRect().left;
    const brandRight = brand.getBoundingClientRect().right;
    if (left < brandRight + 8) problems.push(`recherche à ${Math.round(left)} px sur le logo (${Math.round(brandRight)} px)`);
    const pad = parseFloat(getComputedStyle(document.querySelector('.app')).getPropertyValue('--page-pad'));
    const expanded = innerWidth >= 1024 && root.getAttribute('data-nav') !== 'collapsed';
    const sideRight = side.getBoundingClientRect().right;
    if (expanded && Math.abs(left - (sideRight + pad)) > 1) problems.push(`recherche à ${Math.round(left)} px au lieu de ${Math.round(sideRight + pad)} px`);
  }
  // Contenu : largeur maximale de 1 600 px.
  if (content.getBoundingClientRect().width > 1601) problems.push(`contenu large de ${Math.round(content.getBoundingClientRect().width)} px`);
  return problems;
}
