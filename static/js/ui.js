/* Dianna : comportements de l'interface (module ES, sans framework).
 * Thème, tiroir de navigation, menus déroulants, fenêtres modales <dialog>, notifications
 * visuelles, erreurs serveur et réseau HTMX, filtres et zone de fichier.
 * Compatible CSP stricte : aucun style en ligne, aucun eval, aucun attribut hx-on. */

const THEME_KEY = "dianna.theme";
const TOAST_LIFE = 5000;
const TOAST_LIFE_WITH_ACTION = 8000;
const TOAST_RESUME = 3000;
const TOAST_MAX = 3;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/* ---------- Thème : clair, sombre, système ---------- */
const media = window.matchMedia("(prefers-color-scheme: dark)");

function storedTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || "system";
  } catch {
    return "system";
  }
}

function applyTheme(pref) {
  const dark = pref === "dark" || (pref === "system" && media.matches);
  const root = document.documentElement;
  root.setAttribute("data-theme", dark ? "dark" : "light");
  root.setAttribute("data-theme-pref", pref);
  $$("[data-theme-switch] input[name=theme]").forEach((input) => {
    input.checked = input.value === pref;
  });
}

function setTheme(pref) {
  try {
    localStorage.setItem(THEME_KEY, pref);
  } catch {
    /* stockage indisponible : le choix vaut pour la page */
  }
  applyTheme(pref);
  document.dispatchEvent(new CustomEvent("dianna:theme", { detail: { theme: pref } }));
}

media.addEventListener("change", () => {
  if (storedTheme() === "system") applyTheme("system");
});

document.addEventListener("change", (event) => {
  const input = event.target.closest("[data-theme-switch] input[name=theme]");
  if (!input) return;
  setTheme(input.value);
  // Compte connecté : le choix est enregistré dans User.theme.
  const url = input.closest("[data-theme-switch]").dataset.themeUrl;
  if (url && window.htmx) {
    window.htmx.ajax("POST", url, { source: document.body, values: { theme: input.value }, swap: "none" });
  }
});

/* ---------- Tiroir de navigation (sous 1 024 px) ---------- */
function navApp() {
  return $("[data-app]");
}

function setNav(open) {
  const app = navApp();
  const toggle = $("[data-nav-toggle]");
  if (!app || !toggle) return;
  app.classList.toggle("nav-open", open);
  toggle.setAttribute("aria-expanded", String(open));
  if (open) {
    const first = $(".side a, .side button", app);
    if (first) first.focus();
  } else {
    toggle.focus();
  }
}

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-nav-toggle]")) {
    setNav(!navApp().classList.contains("nav-open"));
    return;
  }
  const app = navApp();
  // Clic sur le fond assombri (pseudo-élément de .app) : ferme le tiroir.
  if (app && app.classList.contains("nav-open") && event.target === app) setNav(false);
});

/* ---------- Menus déroulants ---------- */
function closeMenus(except) {
  $$("[data-dropdown]").forEach((dropdown) => {
    if (dropdown === except) return;
    const toggle = $("[data-dropdown-toggle]", dropdown);
    const menu = toggle && document.getElementById(toggle.getAttribute("aria-controls"));
    if (menu && !menu.hidden) {
      menu.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }
  });
}

document.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-dropdown-toggle]");
  if (toggle) {
    const dropdown = toggle.closest("[data-dropdown]");
    const menu = document.getElementById(toggle.getAttribute("aria-controls"));
    closeMenus(dropdown);
    menu.hidden = !menu.hidden;
    toggle.setAttribute("aria-expanded", String(!menu.hidden));
    if (!menu.hidden) {
      const first = $("a, button, input", menu);
      if (first) first.focus();
    }
    return;
  }
  if (!event.target.closest("[data-dropdown]")) closeMenus();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const openMenu = $$("[data-dropdown] .menu").find((menu) => !menu.hidden);
  if (openMenu) {
    const dropdown = openMenu.closest("[data-dropdown]");
    closeMenus();
    $("[data-dropdown-toggle]", dropdown).focus();
    event.preventDefault();
    return;
  }
  const app = navApp();
  if (app && app.classList.contains("nav-open") && !$("dialog[open]")) setNav(false);
});

/* ---------- Fenêtres modales ---------- */
let modalOpener = null;

function openModal(dialog, opener) {
  modalOpener = opener || document.activeElement;
  // La modale est dans la couche supérieure et rend le reste inerte : la zone des
  // notifications y est déplacée pour rester visible et cliquable (« Annuler »).
  const toasts = $("#toasts");
  if (toasts) dialog.append(toasts);
  dialog.addEventListener("close", () => {
    if (toasts) document.body.append(toasts);
    dialog.remove();
    if (modalOpener && document.body.contains(modalOpener)) modalOpener.focus();
    modalOpener = null;
  });
  // Clic sur le fond : en dehors de la boîte de la modale.
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    const inside =
      event.clientX >= box.left && event.clientX <= box.right &&
      event.clientY >= box.top && event.clientY <= box.bottom;
    if (!inside) dialog.close();
  });
  dialog.showModal();
  focusFirstField(dialog);
}

function closeModal() {
  const dialog = $("dialog[data-modal][open]");
  if (dialog) dialog.close();
}

function focusFirstField(root) {
  const target =
    $("[aria-invalid=true]", root) ||
    $("[autofocus]", root) ||
    $("input:not([type=hidden]):not([disabled]), select, textarea", root) ||
    $(".modal-foot .btn-primary, .modal-foot .btn-danger", root);
  if (target) target.focus();
}

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-modal-close]")) {
    const dialog = event.target.closest("dialog");
    if (dialog) dialog.close();
  }
});

document.body.addEventListener("closeModal", closeModal);

/* ---------- Notifications visuelles ---------- */
const BADGE_ICON = { ok: "check", info: "info", warn: "alert", err: "alert" };

function fillMessage(node, message, emphasis) {
  node.textContent = "";
  const index = emphasis ? message.indexOf(emphasis) : -1;
  if (index < 0) {
    node.textContent = message;
    return;
  }
  const bold = document.createElement("b");
  bold.textContent = emphasis;
  node.append(message.slice(0, index), bold, message.slice(index + emphasis.length));
}

function scheduleRemoval(toast, life) {
  let timer = setTimeout(() => toast.remove(), life);
  const pause = () => clearTimeout(timer);
  const resume = () => {
    clearTimeout(timer);
    if (!toast.matches(":hover, :focus-within")) timer = setTimeout(() => toast.remove(), TOAST_RESUME);
  };
  toast.addEventListener("mouseenter", pause);
  toast.addEventListener("focusin", pause);
  toast.addEventListener("mouseleave", resume);
  toast.addEventListener("focusout", resume);
}

function trimToasts(region) {
  const toasts = $$("[data-toast]", region);
  toasts.slice(0, Math.max(0, toasts.length - TOAST_MAX)).forEach((toast) => toast.remove());
}

export function showToast(data) {
  const region = $("#toasts");
  const template = $("#tpl-toast");
  if (!region || !template) return null;
  const kind = BADGE_ICON[data.kind] ? data.kind : "ok";
  const toast = template.content.firstElementChild.cloneNode(true);
  toast.className = `toast toast-${kind}`;
  toast.setAttribute("role", kind === "err" ? "alert" : "status");
  const use = $("[data-toast-badge] use", toast);
  if (use) use.setAttribute("href", use.getAttribute("href").replace(/#.*$/, `#i-${BADGE_ICON[kind]}`));
  $("[data-toast-title]", toast).textContent = data.title || "";
  const message = $("[data-toast-message]", toast);
  if (data.message) {
    fillMessage(message, data.message, data.emphasis);
    message.hidden = false;
  }
  const actions = $("[data-toast-actions]", toast);
  if (data.action_url && data.action_label) {
    const link = document.createElement("a");
    link.href = data.action_url;
    link.textContent = data.action_label;
    actions.append(link);
  }
  if (data.undo_url) {
    const undo = document.createElement("button");
    undo.type = "button";
    undo.className = "toast-undo";
    undo.textContent = "Annuler";
    undo.addEventListener("click", () => {
      undo.disabled = true;
      window.htmx.ajax("POST", data.undo_url, { source: document.body, swap: "none" });
      toast.remove();
    });
    actions.append(undo);
  }
  actions.hidden = !actions.childElementCount;
  region.append(toast);
  trimToasts(region);
  scheduleRemoval(toast, actions.hidden ? TOAST_LIFE : TOAST_LIFE_WITH_ACTION);
  return toast;
}

document.body.addEventListener("toast", (event) => showToast(event.detail || {}));

// Notifications rendues côté serveur (messages Django) : mêmes durées.
$$("#toasts [data-toast]").forEach((toast) => scheduleRemoval(toast, TOAST_LIFE));

/* ---------- HTMX : erreurs serveur et réseau ---------- */
function errorHost(elt) {
  if (!elt || !elt.closest) return null;
  const dialog = elt.closest("dialog");
  if (dialog) return $(".modal-body", dialog) || dialog;
  return elt.closest("form");
}

function showServerError(elt) {
  const host = errorHost(elt);
  const template = $("#tpl-server-error");
  if (!host || !template) {
    showToast({ kind: "err", title: "Le serveur n'a pas répondu", message: "Vos saisies sont conservées, vous pouvez réessayer." });
    return;
  }
  $$("[data-server-error]", host).forEach((node) => node.remove());
  host.prepend(template.content.firstElementChild.cloneNode(true));
  host.scrollTop = 0;
}

document.body.addEventListener("htmx:responseError", (event) => {
  if (event.detail.xhr.status >= 500) showServerError(event.detail.elt);
});
document.body.addEventListener("htmx:sendError", (event) => showServerError(event.detail.elt));

document.body.addEventListener("htmx:afterRequest", (event) => {
  if (!event.detail.successful) return;
  const host = errorHost(event.detail.elt);
  if (host) $$("[data-server-error]", host).forEach((node) => node.remove());
});

document.body.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail.target;
  if (target && target.id === "modal-root") {
    const dialog = $("dialog[data-modal]", target);
    if (dialog) openModal(dialog, event.detail.requestConfig && event.detail.requestConfig.elt);
    return;
  }
  // Formulaire renvoyé avec des erreurs (422) : focus sur le premier champ à corriger.
  if (event.detail.xhr && event.detail.xhr.status === 422) focusFirstField(event.detail.elt.isConnected ? event.detail.elt : target);
});

/* ---------- Filtres : « Réinitialiser » vide aussi les champs ---------- */
document.addEventListener("click", (event) => {
  const reset = event.target.closest("[data-filters-reset]");
  if (!reset) return;
  const form = reset.closest("form");
  $$("input[type=search], input[type=text]", form).forEach((input) => (input.value = ""));
  $$("select", form).forEach((select) => (select.selectedIndex = 0));
});

/* ---------- Zone de fichier ---------- */
document.addEventListener("change", (event) => {
  const input = event.target;
  const zone = input.closest && input.closest("[data-dropzone]");
  if (!zone || input.type !== "file") return;
  const name = $("[data-dropzone-name]", zone);
  const file = input.files && input.files[0];
  zone.classList.toggle("has-file", Boolean(file));
  if (name) name.textContent = file ? file.name : "Choisir un fichier";
});
["dragenter", "dragover"].forEach((type) =>
  document.addEventListener(type, (event) => {
    const zone = event.target.closest && event.target.closest("[data-dropzone]");
    if (zone) zone.classList.add("is-dragover");
  }),
);
["dragleave", "drop"].forEach((type) =>
  document.addEventListener(type, (event) => {
    const zone = event.target.closest && event.target.closest("[data-dropzone]");
    if (zone) zone.classList.remove("is-dragover");
  }),
);

/* ---------- Initialisation ---------- */
applyTheme(storedTheme());
