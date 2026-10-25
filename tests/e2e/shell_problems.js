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
    if (vertical && e !== main && e !== side && !e.querySelector('table')) problems.push(`barre verticale sur ${name(e)}`);
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
  return problems;
}
