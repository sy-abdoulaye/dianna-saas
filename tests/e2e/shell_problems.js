(margin) => {
  const problems = [];
  const root = document.documentElement;
  if (root.scrollHeight > innerHeight + 1) problems.push(`document haut de ${root.scrollHeight} px`);
  if (root.scrollWidth > innerWidth + 1) problems.push(`document large de ${root.scrollWidth} px`);
  const main = document.querySelector('[data-main]');
  const side = document.getElementById('side');
  const name = (e) => `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}${[...e.classList].map(c => '.' + c).join('')}`;
  const scrollsHorizontally = (e) => e.matches('.tabs') || (e.querySelector('table') && e.querySelectorAll('table').length);
  for (const e of document.querySelectorAll('body *')) {
    if (e.matches('textarea, select, input, option, dialog, dialog *')) continue;
    const style = getComputedStyle(e);
    const vertical = ['auto', 'scroll'].includes(style.overflowY) && e.scrollHeight > e.clientHeight + 1;
    const horizontal = ['auto', 'scroll'].includes(style.overflowX) && e.scrollWidth > e.clientWidth + 1;
    if (vertical && e !== main && !e.querySelector('table')) problems.push(`barre verticale sur ${name(e)}`);
    if (horizontal && !scrollsHorizontally(e)) problems.push(`barre horizontale sur ${name(e)}`);
  }
  const content = document.getElementById('content');
  const last = content.lastElementChild;
  if (last) {
    const contentBottom = last.getBoundingClientRect().bottom - main.getBoundingClientRect().top + main.scrollTop;
    const limit = Math.max(main.clientHeight, contentBottom + margin);
    if (main.scrollHeight > limit) problems.push(`zone principale défilable sur ${main.scrollHeight} px pour ${Math.round(contentBottom)} px de contenu`);
  }
  if (getComputedStyle(side).visibility !== 'hidden' && side.getBoundingClientRect().bottom < innerHeight - 1) {
    problems.push(`menu latéral arrêté à ${Math.round(side.getBoundingClientRect().bottom)} px`);
  }
  if (side.scrollHeight > side.clientHeight + 1) problems.push(`menu latéral à défiler (${side.scrollHeight} px pour ${side.clientHeight})`);
  // Recherche : au bord droit du menu déplié (à la marge du contenu), après le nom quand il est
  // replié, jamais sur le logo.
  const search = document.querySelector('.topbar .global-search');
  const brand = document.querySelector('.topbar .brand');
  if (search && brand) {
    const left = search.getBoundingClientRect().left;
    const brandRight = brand.getBoundingClientRect().right;
    if (left < brandRight + 8) problems.push(`recherche à ${Math.round(left)} px sur le logo (${Math.round(brandRight)} px)`);
    const pad = parseFloat(getComputedStyle(document.querySelector('.app')).getPropertyValue('--page-pad'));
    const expanded = innerWidth >= 1024 && document.documentElement.getAttribute('data-nav') !== 'collapsed';
    const sideRight = side.getBoundingClientRect().right;
    if (expanded && Math.abs(left - (sideRight + pad)) > 1) problems.push(`recherche à ${Math.round(left)} px au lieu de ${Math.round(sideRight + pad)} px`);
  }
  // Contenu : largeur maximale de 1 600 px et marge intérieure de la mise en page commune.
  const page = content.getBoundingClientRect();
  if (page.width > 1601) problems.push(`contenu large de ${Math.round(page.width)} px`);
  return problems;
}
