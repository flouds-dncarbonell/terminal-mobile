"use strict";
const $ = (id) => document.getElementById(id);
const decoder = new TextDecoder();
const encoder = new TextEncoder();
const FONT_SIZE_KEY = "terminalFontSize";
// Official marks: Claude from Simple Icons, Codex from LobeHub Icons.
const AGENT_LOGOS = {
  claude: '<svg class="agent-logo logo-claude" viewBox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z"/></svg>',
  codex: '<svg class="agent-logo logo-codex" viewBox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="M8.086.457a6.105 6.105 0 013.046-.415c1.333.153 2.521.72 3.564 1.7a.117.117 0 00.107.029c1.408-.346 2.762-.224 4.061.366l.063.03.154.076c1.357.703 2.33 1.77 2.918 3.198.278.679.418 1.388.421 2.126a5.655 5.655 0 01-.18 1.631.167.167 0 00.04.155 5.982 5.982 0 011.578 2.891c.385 1.901-.01 3.615-1.183 5.14l-.182.22a6.063 6.063 0 01-2.934 1.851.162.162 0 00-.108.102c-.255.736-.511 1.364-.987 1.992-1.199 1.582-2.962 2.462-4.948 2.451-1.583-.008-2.986-.587-4.21-1.736a.145.145 0 00-.14-.032c-.518.167-1.04.191-1.604.185a5.924 5.924 0 01-2.595-.622 6.058 6.058 0 01-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74 7.74 0 01-.495-1.283 6.11 6.11 0 01-.017-3.064.166.166 0 00.008-.074.115.115 0 00-.037-.064 5.958 5.958 0 01-1.38-2.202 5.196 5.196 0 01-.333-1.589 6.915 6.915 0 01.188-2.132c.45-1.484 1.309-2.648 2.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129 0 00.087-.087A6.016 6.016 0 015.635 2.31C6.315 1.464 7.132.846 8.086.457zm-.804 7.85a.848.848 0 00-1.473.842l1.694 2.965-1.688 2.848a.849.849 0 001.46.864l1.94-3.272a.849.849 0 00.007-.854l-1.94-3.393zm5.446 6.24a.849.849 0 000 1.695h4.848a.849.849 0 000-1.696h-4.848z"/></svg>',
};
function agentLogo(agent) {
  const holder = document.createElement("span");
  holder.className = "agent-mark";
  holder.setAttribute("aria-hidden", "true");
  if (AGENT_LOGOS[agent]) holder.innerHTML = AGENT_LOGOS[agent];
  else holder.textContent = ">_";
  return holder;
}
let projects = [],
  selectedProject = localStorage.getItem("project") || "",
  selectedWindow = "";
let socket,
  retryTimer,
  toastTimer,
  stopped = false,
  connecting = false,
  pendingInstall,
  folderPath = "";
let terminalReady = false,
  terminalGeneration = 0,
  opening = false,
  directoryGeneration = 0;
let alerts = [], alertSignature = "";
let quotaVisible = false, quotaSnapshot = null, quotaBusy = false, quotaSaving = false,
  quotaFetchedAt = 0, quotaDrag = null;
let dismissedAlerts;
try {
  dismissedAlerts = new Set(JSON.parse(localStorage.getItem("dismissedAlerts") || "[]"));
} catch {
  dismissedAlerts = new Set();
}

function pendingAlerts() {
  return alerts.filter((alert) => !dismissedAlerts.has(alert.id));
}
function alertLabel(alert) {
  const project = projects.find((project) => project.path === alert.project);
  const window = project?.windows.find((window) => window.id === alert.window);
  const siblings = project?.windows.filter((item) => item.name === alert.name) || [];
  const number = siblings.length > 1 ? " " + (siblings.indexOf(window) + 1) : "";
  return `${alert.name}${number} · ${project?.name || alert.project.split("/").pop()}`;
}
function alertDot(label) {
  const dot = document.createElement("span");
  dot.className = "attention-dot";
  dot.setAttribute("role", "img");
  dot.setAttribute("aria-label", label);
  return dot;
}
function renderAlerts() {
  const pending = pendingAlerts();
  const signature = JSON.stringify(pending.map((alert) => [alert.id, alert.message, alertLabel(alert)]));
  $("attention-summary").hidden = !pending.length;
  document.title = (pending.length ? `(${pending.length}) ` : "") + "Terminais · local";
  if (signature === alertSignature) return;
  alertSignature = signature;
  $("attention-announcement").textContent = pending.length
    ? `${pending.length} alerta${pending.length > 1 ? "s" : ""}. ${alertLabel(pending[0])}: ${pending[0].message}`
    : "Nenhum alerta pendente.";
  if (pending.length) {
    $("attention-title").textContent = alertLabel(pending[0]);
    $("attention-preview").textContent = pending[0].message;
    $("attention-count").textContent = pending.length > 1 ? `+${pending.length - 1}` : "Ver";
  }
  $("attention-list").replaceChildren();
  if (!pending.length) {
    const empty = document.createElement("p");
    empty.textContent = "Nenhum alerta pendente.";
    $("attention-list").append(empty);
  }
  for (const alert of pending) {
    const row = document.createElement("article");
    row.className = "attention-item";
    row.dataset.alertId = alert.id;
    const title = document.createElement("strong"), message = document.createElement("p");
    title.textContent = alertLabel(alert);
    message.textContent = alert.message;
    const actions = document.createElement("div");
    actions.className = "attention-actions";
    if (projects.some((project) => project.windows.some((window) => window.id === alert.window))) {
      const open = document.createElement("button");
      open.textContent = "Abrir terminal";
      open.onclick = () => {
        selectedProject = alert.project;
        localStorage.setItem("project", selectedProject);
        selectWindow(alert.window);
        $("attention-dialog").close();
      };
      actions.append(open);
    }
    const dismiss = document.createElement("button");
    dismiss.textContent = "Dispensar";
    dismiss.onclick = () => {
      dismissedAlerts.add(alert.id);
      dismissedAlerts = new Set([...dismissedAlerts].slice(-300));
      localStorage.setItem("dismissedAlerts", JSON.stringify([...dismissedAlerts]));
      render();
      if ($("project-dialog").open) renderProjects();
    };
    actions.append(dismiss);
    row.append(title, message, actions);
    $("attention-list").append(row);
  }
}
$("attention-summary").onclick = () => $("attention-dialog").showModal();
const terminal = new Terminal({
  fontFamily: "Plex, monospace",
  fontSize: Math.max(
    8,
    Math.min(28, Number(localStorage.getItem(FONT_SIZE_KEY)) || 8),
  ),
  lineHeight: 1.15,
  cursorBlink: true,
  scrollback: 12000,
  convertEol: false,
  disableStdin: true,
  theme: {
    background: "#10110e",
    foreground: "#f0eee5",
    cursor: "#edaa64",
    selectionBackground: "#4d4939",
    // Saturated ANSI palette: the agents' diffs and status colors must read
    // clearly on the olive background, not as pastel tints.
    black: "#1d1f1a",
    red: "#f0524f",
    green: "#5fd15f",
    yellow: "#f2c641",
    blue: "#4f9cff",
    magenta: "#d57bff",
    cyan: "#3fd4d4",
    white: "#d9d6cb",
    brightBlack: "#7d7f72",
    brightRed: "#ff7a73",
    brightGreen: "#86ec7c",
    brightYellow: "#ffdc6b",
    brightBlue: "#7cb8ff",
    brightMagenta: "#e6a2ff",
    brightCyan: "#6ee8e6",
    brightWhite: "#ffffff",
  },
});
const fit = new FitAddon.FitAddon();
terminal.loadAddon(fit);
terminal.open($("terminal"));
for (const [name, value] of Object.entries({
  autocapitalize: "off",
  autocorrect: "off",
  autocomplete: "off",
  spellcheck: "false",
  enterkeyhint: "enter",
  "aria-label": "Digitar no terminal",
}))
  terminal.textarea.setAttribute(name, value);
$("terminal").addEventListener("click", () => {
  if (touchMoved) return;
  if (terminalReady && !opening && !window.getSelection()?.toString())
    terminal.focus();
});
function updateInputState() {
  const disabled = quotaVisible || $("files-dialog").open || $("attachment-dialog").open || !terminalReady || opening || !selectedWindow;
  terminal.options.disableStdin = disabled;
  document
    .querySelectorAll("[data-key], [data-command], #shift-key")
    .forEach((button) => (button.disabled = disabled));
  if (disabled && shiftArmed) setShift(false);
  const agent = currentProject()?.windows.find((item) => item.id === selectedWindow)?.agent;
  $("attachment-toggle").disabled = disabled || !["codex", "claude"].includes(agent);
}
document.fonts.ready.then(() => fitTerminal());
function fitTerminal() {
  if ($("terminal").clientHeight > 0) {
    try {
      fit.fit();
    } catch {}
  }
}
new ResizeObserver(fitTerminal).observe($("terminal"));
terminal.onResize(({ cols, rows }) => {
  if (terminalReady && socket?.readyState === WebSocket.OPEN)
    socket.send(encoder.encode("1" + JSON.stringify({ columns: cols, rows })));
});
terminal.onData((data) => {
  // Typing a single letter with Shift armed sends it in upper case. Mouse
  // reports and automatic replies (they start with Esc) leave Shift alone.
  if (shiftArmed && !data.startsWith("\u001b")) {
    if (data.length === 1) data = data.toUpperCase();
    setShift(false);
  }
  sendInput(data);
});
function sendInput(data, attachment = false) {
  if (quotaVisible || $("files-dialog").open || ($("attachment-dialog").open && !attachment) || opening || !terminalReady || socket?.readyState !== WebSocket.OPEN) {
    toast("O terminal ainda está conectando.");
    return false;
  }
  const ws = socket;
  // Mouse/focus reports (the swipe's own wheel events) and xterm's automatic
  // replies to queries are not typing: leaving tmux copy mode on them would
  // undo the scroll at once (Codex has no mouse mode, so it relies on tmux).
  if (scrolledBack && !/^\x1b(\[(<\d+;\d+;\d+[Mm]|[IO]|[?>][\d;]*c)|\][^]*\x1b\\)$/.test(data)) leaveScrollback();
  inputQueue = inputQueue.then(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send(encoder.encode("0" + data));
  });
  return true;
}
// Swipes become wheel events: tmux scrolls its history (or the agent scrolls
// its own view) instead of the browser, which has nothing to scroll.
let touchY = null,
  touchMoved = false,
  scrolledBack = false,
  inputQueue = Promise.resolve();
function leaveScrollback() {
  scrolledBack = false;
  $("scroll-bottom").hidden = true;
  const identity = selectedWindow;
  inputQueue = inputQueue.then(() =>
    api("/api/windows/" + encodeURIComponent(identity) + "/bottom", {
      method: "POST",
      body: "{}",
    }).catch(() => {}),
  );
}
function wheel(deltaY, touch) {
  terminal.element.dispatchEvent(
    new WheelEvent("wheel", {
      deltaY,
      deltaMode: WheelEvent.DOM_DELTA_PIXEL,
      clientX: touch.clientX,
      clientY: touch.clientY,
      bubbles: true,
      cancelable: true,
    }),
  );
  if (deltaY < 0 && !scrolledBack) {
    scrolledBack = true;
    $("scroll-bottom").hidden = false;
  }
}
$("terminal").addEventListener(
  "touchstart",
  (event) => {
    touchY = event.touches.length === 1 ? event.touches[0].clientY : null;
    touchMoved = false;
  },
  { passive: true, capture: true },
);
$("terminal").addEventListener(
  "touchmove",
  (event) => {
    if (touchY === null || event.touches.length !== 1 || !terminalReady) return;
    const touch = event.touches[0];
    const delta = touchY - touch.clientY;
    if (!touchMoved && Math.abs(delta) < 8) return;
    touchMoved = true;
    touchY = touch.clientY;
    event.preventDefault();
    event.stopPropagation();
    wheel(delta, touch);
  },
  { passive: false, capture: true },
);
$("terminal").addEventListener(
  "touchend",
  (event) => {
    if (touchMoved) {
      event.preventDefault();
      event.stopPropagation();
    } else if (event.changedTouches.length === 1) {
      // A plain tap on a URL opens it; the agents' own mouse mode and tmux
      // would otherwise swallow the click.
      const url = linkAt(event.changedTouches[0]);
      if (url) {
        event.preventDefault();
        event.stopPropagation();
        openLink(url);
      }
    }
    touchY = null;
  },
  { passive: false, capture: true },
);
// Desktop: Ctrl/Cmd+click opens the link (plain click stays a terminal click).
$("terminal").addEventListener(
  "mousedown",
  (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.button !== 0) return;
    const url = linkAt(event);
    if (!url) return;
    event.preventDefault();
    event.stopPropagation();
    openLink(url);
  },
  { capture: true },
);
const URL_PATTERN = /\b(?:https?:\/\/|www\.)[^\s<>"'`│┃|]+/gi;
function lineText(index) {
  return terminal.buffer.active.getLine(index)?.translateToString(false) ?? "";
}
// Finds the URL under a screen point. Lines the terminal soft-wrapped are
// joined, and so are lines an agent hard-wrapped when the URL fills the row
// to the last column and the next row carries straight on (indent ignored).
function linkAt(point) {
  if (!terminalReady) return null;
  const screen = terminal.element?.querySelector(".xterm-screen");
  if (!screen) return null;
  const rect = screen.getBoundingClientRect();
  const col = Math.floor(((point.clientX - rect.left) / rect.width) * terminal.cols);
  const row = Math.floor(((point.clientY - rect.top) / rect.height) * terminal.rows);
  if (col < 0 || row < 0 || col >= terminal.cols || row >= terminal.rows) return null;
  const target = terminal.buffer.active.viewportY + row;
  const found = linkAtCell(target, col);
  if (found) return found;
  // Tapped the continuation of a hard-wrapped URL: retry from the row above
  // when that row runs to the right edge and the tap is inside the leading run.
  const lead = lineText(target).match(/^(\s*)([^\s<>"'`│┃|]+)/);
  if (!lead || col < lead[1].length || col >= lead[0].length) return null;
  for (let above = target - 1; above >= Math.max(0, target - 5); above--) {
    const text = lineText(above).trimEnd();
    if (text.length < terminal.cols - 1) break;
    const url = linkAtCell(above, text.length - 1);
    if (url) return url;
  }
  return null;
}
function linkAtCell(target, col) {
  const buffer = terminal.buffer.active;
  let first = target;
  while (first > 0 && buffer.getLine(first)?.isWrapped) first--;
  let last = target;
  while (buffer.getLine(last + 1)?.isWrapped) last++;
  // Text of the logical line, and where the tapped cell falls in it.
  let text = "";
  let offset = 0;
  for (let index = first; index <= last; index++) {
    if (index === target) offset = text.length + col;
    text += lineText(index);
  }
  for (const match of text.matchAll(URL_PATTERN)) {
    const start = match.index;
    let url = match[0];
    let end = start + url.length;
    if (offset < start || offset > end) continue;
    // Hard-wrapped continuation: the URL touches the right edge.
    let next = last + 1;
    while (end >= text.length - 1 && next < buffer.length && next - last < 6) {
      const more = lineText(next).trimStart().match(/^[^\s<>"'`│┃|]+/)?.[0];
      if (!more || /^[-─━=*•>#]/.test(more)) break;
      url += more;
      text = text + more;
      end = text.length;
      if (lineText(next).trimEnd().length < terminal.cols - 1) break;
      next++;
    }
    // Trailing punctuation is prose, except a ")" closing a "(" in the URL.
    while (/[.,;:!?)\]}'"]$/.test(url)) {
      if (url.endsWith(")") && (url.match(/\(/g) || []).length >= (url.match(/\)/g) || []).length) break;
      url = url.slice(0, -1);
    }
    if (/^www\./i.test(url)) url = "https://" + url;
    return url;
  }
  return null;
}
function openLink(url) {
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.click();
}
$("scroll-bottom").addEventListener("pointerdown", (e) => e.preventDefault());
$("scroll-bottom").onclick = () => {
  // Agents that take the mouse (Claude) scroll their own view: Ctrl+End jumps
  // back. Otherwise the scrollback is tmux's, left by leaveScrollback.
  if (terminal.modes.mouseTrackingMode !== "none") sendInput("\u001b[1;5F");
  else leaveScrollback();
  scrolledBack = false;
  $("scroll-bottom").hidden = true;
  terminal.focus();
};
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 5500);
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    let message = "Não foi possível conectar ao computador.";
    try {
      message = (await response.json()).error || message;
    } catch {}
    throw new Error(message);
  }
  return response.json();
}

const quotaNumber = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
function quotaElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function quotaReset(quota) {
  if (quota.neverExpires) return "Não expira";
  const date = quota.resetAt ? new Date(quota.resetAt) : null;
  if (!date || !Number.isFinite(date.getTime())) return "Renovação não informada";
  const minutes = Math.ceil((date.getTime() - Date.now()) / 60000);
  const absolute = date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  if (minutes <= 0) return `Aguardando renovação · ${absolute}`;
  const days = Math.floor(minutes / 1440), hours = Math.floor((minutes % 1440) / 60), rest = minutes % 60;
  const duration = [days ? `${days} d` : "", hours ? `${hours} h` : "", !days && rest ? `${rest} min` : ""].filter(Boolean).join(" ");
  return `${quota.recurring === false ? "Expira" : "Renova"} em ${duration} · ${absolute}`;
}
// Codex/Claude reset credits expire unused; the top bar counts down to the nearest one
// only in its last 2 hours (the panel always lists every expiry).
const RESET_COUNTDOWN_WINDOW = 2 * 3600000;
function nearestResetCredit() {
  let nearest = null;
  for (const account of quotaSnapshot?.accounts || []) {
    for (const credit of account.resetCredits?.credits || []) {
      const time = new Date(credit.expiresAt).getTime();
      if (Number.isFinite(time) && time > Date.now() && (!nearest || time < nearest.time)) nearest = { time, account, credit };
    }
  }
  return nearest;
}
function resetCreditName(account, credit) {
  if (account.providerId === "codex") return "Redefinição de limites do Codex";
  if (credit.clears?.includes("seven_day")) return "Redefinição completa do Claude";
  if (/fable/i.test(`${credit.label || ""} ${credit.grantId || ""}`)) return "Crédito de lançamento do Fable";
  return "Redefinição de limites do Claude";
}
function resetCreditScope(account, credit) {
  if (account.providerId === "codex") return "O provedor não informa quais modelos ou limites este crédito redefine.";
  const names = { five_hour: "sessão de 5 horas", seven_day: "limite semanal geral", seven_day_overage_included: "uso semanal adicional incluído" };
  const clears = credit.clears || [];
  const limits = clears.map((key) => names[key]).filter(Boolean);
  if (!limits.length) return "O provedor não informou quais limites este crédito redefine.";
  return `Zera: ${limits.join("; ")}.${clears.includes("five_hour") && !clears.includes("seven_day") ? " Não zera o limite semanal geral." : ""}`;
}
const openCreditGroups = new Set();
function resetCreditShortName(account, credit) {
  if (account.providerId === "codex") return "Codex";
  if (credit.clears?.includes("seven_day")) return "Redefinição completa";
  if (/fable/i.test(`${credit.label || ""} ${credit.grantId || ""}`)) return "Fable";
  return "Redefinição de limites";
}
function resetCreditEffect(credit) {
  const names = { five_hour: "Sessão de 5h", seven_day: "semana geral", seven_day_overage_included: "uso adicional" };
  return (credit.clears || []).map((key) => names[key]).filter(Boolean).join(" + ") || "Escopo não informado pelo provedor";
}
function renderCreditGroups(account, credits) {
  const section = quotaElement("section", "quota-row reset-credits");
  const heading = quotaElement("div", "credit-section-heading");
  heading.append(quotaElement("h4", "", "Créditos de redefinição"), quotaElement("span", "", String(account.resetCredits.available)));
  section.append(heading);
  if (!credits.length) section.append(quotaElement("p", "credit-empty", account.resetCredits.available ? "Validade não informada pelo provedor" : "Nenhum disponível"));
  const groups = new Map();
  for (const credit of credits) {
    const name = resetCreditShortName(account, credit);
    const key = JSON.stringify([account.id, name, [...(credit.clears || [])].sort(), credit.expiresAt, credit.usableNow]);
    if (!groups.has(key)) groups.set(key, { name, credit, count: 0 });
    groups.get(key).count++;
  }
  for (const [key, { name, credit, count }] of groups) {
    const details = quotaElement("details", "credit-group");
    details.open = openCreditGroups.has(key);
    details.addEventListener("toggle", () => {
      if (details.isConnected) {
        if (details.open) openCreditGroups.add(key);
        else openCreditGroups.delete(key);
      }
    });
    const summary = quotaElement("summary", "credit-summary");
    summary.append(quotaElement("span", "credit-name", name), quotaElement("span", "credit-count", `${count} crédito${count > 1 ? "s" : ""}`));
    summary.append(quotaElement("span", "credit-effect", resetCreditEffect(credit)));
    const date = new Date(credit.expiresAt);
    const left = date.getTime() - Date.now();
    const validDate = Number.isFinite(date.getTime());
    const absolute = validDate ? date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).replaceAll(" de ", " ").replaceAll(".", "") : null;
    const validity = quotaElement("span", "credit-validity", !validDate ? "Validade não informada" : left <= 0 ? `Venceu em ${absolute}` : `${count > 1 ? "Válidos" : "Válido"} até ${absolute}`);
    if (validDate) {
      validity.dataset.expiresAt = credit.expiresAt;
      validity.dataset.validUntil = absolute;
      updateCreditValidity(validity);
    }
    summary.append(validity);
    const body = quotaElement("div", "credit-details");
    body.append(quotaElement("p", "", resetCreditScope(account, credit)));
    if (credit.usableNow === false) body.append(quotaElement("p", "", "O provedor ainda não permite usar este crédito."));
    if (validDate && left > 0) {
      const time = date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
      body.append(quotaElement("p", "", `Prazo para usar: ${absolute}, às ${time} (horário deste dispositivo).`));
      body.append(quotaElement("p", "", "Tentativa de uso automático 5 minutos antes de vencer. A validade do crédito é diferente da renovação normal da cota."));
    }
    details.append(summary, body);
    section.append(details);
  }
  const cooldown = new Date(account.resetCredits.cooldownUntil);
  if (cooldown.getTime() > Date.now()) section.append(quotaElement("p", "credit-empty", `Novo uso disponível em ${countdownText(cooldown.getTime() - Date.now())}`));
  return section;
}
function updateCreditValidity(element) {
  const left = new Date(element.dataset.expiresAt).getTime() - Date.now();
  element.textContent = left > 0
    ? `Expira em ${countdownText(left)} · ${element.dataset.validUntil}`
    : `Expirado · ${element.dataset.validUntil}`;
  element.classList.toggle("expiring", left <= 86400000);
}
function countdownText(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const days = Math.floor(seconds / 86400), hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60), rest = seconds % 60;
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}
function renderResetCountdown() {
  let nearest = nearestResetCredit();
  if (nearest && nearest.time - Date.now() > RESET_COUNTDOWN_WINDOW) nearest = null;
  const badge = $("quota-countdown"), button = $("quota-tab");
  badge.hidden = !nearest;
  button.classList.toggle("has-countdown", !!nearest);
  if (!nearest) {
    button.setAttribute("aria-label", "Quotas");
    button.title = "Quotas";
    return;
  }
  const left = nearest.time - Date.now();
  const absolute = new Date(nearest.time).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  badge.replaceChildren(agentLogo(nearest.account.providerId === "claude" ? "claude" : "codex"), countdownText(left));
  const label = `Quotas · ${resetCreditName(nearest.account, nearest.credit)} (${nearest.account.name}) · prazo para usar: ${absolute}`;
  button.setAttribute("aria-label", label);
  button.title = label;
}
function quotaAccounts(provider) {
  return (quotaSnapshot?.accounts || []).filter((account) => account.providerId === provider)
    .sort((a, b) => a.priority - b.priority);
}
function quotaStatus() {
  $("quota-refresh").disabled = quotaBusy || quotaSaving || !!quotaDrag;
  $("quota-refresh").textContent = quotaBusy ? "Consultando…" : "Atualizar";
  $("quota-accounts").setAttribute("aria-busy", String(quotaBusy || quotaSaving));
  $("quota-status").textContent = quotaSaving ? "Salvando ordem no 9router…"
    : quotaBusy ? "Consultando o 9router…"
    : quotaSnapshot ? "Última consulta · " + new Date(quotaSnapshot.updatedAt).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "Consulte as quotas para ver o saldo disponível.";
  document.querySelectorAll(".quota-handle, .quota-move button").forEach((button) => {
    button.disabled = quotaBusy || quotaSaving || button.dataset.edge === "true";
  });
}
function renderQuotaAccounts() {
  if (quotaDrag) return;
  const area = $("quota-accounts");
  area.replaceChildren();
  const providers = [...new Set((quotaSnapshot?.accounts || []).map((account) => account.providerId))];
  providers.sort((a, b) => (["codex", "claude", "antigravity"].indexOf(a) < 0 ? 99 : ["codex", "claude", "antigravity"].indexOf(a))
    - (["codex", "claude", "antigravity"].indexOf(b) < 0 ? 99 : ["codex", "claude", "antigravity"].indexOf(b)));
  if (quotaSnapshot && !providers.length) {
    area.append(quotaElement("p", "quota-note", "Nenhuma conta conectada no 9router."));
  }
  for (const provider of providers) {
    const accounts = quotaAccounts(provider);
    const section = quotaElement("section", "quota-provider");
    const heading = quotaElement("div", "quota-provider-heading");
    const providerName = quotaElement("h2", "");
    providerName.append(agentLogo(provider), accounts[0].provider);
    heading.append(providerName, quotaElement("span", "", `${accounts.length} conta${accounts.length > 1 ? "s" : ""}`));
    const rotation = accounts.some((account) => account.strategy === "round-robin");
    const note = quotaElement("p", "quota-provider-note", rotation
      ? "Rodízio ativo no 9router. A posição define a prioridade de fallback."
      : "Uso por prioridade. A primeira conta disponível é utilizada antes das seguintes.");
    const list = quotaElement("div", "quota-account-list");
    list.dataset.provider = provider;
    for (const [index, account] of accounts.entries()) {
      const card = quotaElement("article", "quota-account");
      card.dataset.accountId = account.id;
      const header = quotaElement("div", "quota-account-heading");
      const handle = quotaElement("button", "quota-handle", "⠿");
      handle.setAttribute("aria-label", `Arrastar ${account.name} para mudar a ordem. Use também as setas para cima e para baixo.`);
      handle.title = "Arrastar para reordenar";
      handle.disabled = accounts.length < 2;
      handle.dataset.edge = String(accounts.length < 2);
      handle.onpointerdown = (event) => startQuotaDrag(event, list, card);
      handle.onkeydown = (event) => {
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        event.preventDefault();
        moveQuotaAccount(provider, account.id, event.key === "ArrowUp" ? -1 : 1);
      };
      const name = quotaElement("div", "quota-account-name");
      const title = quotaElement("h3", "");
      // Long e-mails truncate the domain instead of breaking mid-word.
      const at = account.name.indexOf("@");
      const accountName = quotaElement("span", "quota-name", at > 0 ? account.name.slice(0, at) : account.name);
      if (at > 0) accountName.append(quotaElement("span", "quota-domain", account.name.slice(at)));
      title.title = account.name;
      title.append(quotaElement("span", "quota-position", `${index + 1}º`), accountName);
      const activity = account.active ? "Ativa" : account.autoDisabled ? "Desativada · quota total esgotada" : "Desativada";
      name.append(title, quotaElement("p", "", [account.plan, activity, account.quotaState === "session" ? "Sessão esgotada · fim da fila" : ""].filter(Boolean).join(" · ")));
      const moves = quotaElement("div", "quota-move");
      for (const [step, label, symbol] of [[-1, "Subir", "↑"], [1, "Descer", "↓"]]) {
        const button = quotaElement("button", "", symbol);
        button.setAttribute("aria-label", `${label} ${account.name}`);
        button.dataset.edge = String(index + step < 0 || index + step >= accounts.length);
        button.onclick = () => moveQuotaAccount(provider, account.id, step);
        moves.append(button);
      }
      header.append(handle, name, moves);
      card.append(header);
      if (account.error) card.append(quotaElement("p", "quota-account-error", account.error));
      for (const quota of account.quotas) {
        const row = quotaElement("div", "quota-row");
        const remaining = quota.remainingPercent;
        const available = typeof remaining === "number" && Number.isFinite(remaining);
        const value = quota.unlimited ? "Sem limite" : available ? `${quotaNumber.format(remaining)}% livre` : "Não informado";
        const label = quotaElement("div", "quota-label");
        const quotaName = quota.name.replace(/^weekly (.+) \(7d\)$/i, (_, model) => `${model.charAt(0).toUpperCase()}${model.slice(1)} · semanal`);
        label.append(quotaElement("span", "", quotaName), quotaElement("strong", "", value));
        row.append(label);
        if (available && !quota.unlimited) {
          row.classList.add(remaining <= 10 ? "low" : remaining <= 25 ? "warning" : "healthy");
          const bar = quotaElement("div", "quota-bar");
          bar.setAttribute("role", "progressbar");
          bar.setAttribute("aria-label", `Saldo disponível: ${quota.name}`);
          bar.setAttribute("aria-valuenow", String(remaining));
          bar.setAttribute("aria-valuemin", "0");
          bar.setAttribute("aria-valuemax", "100");
          bar.style.setProperty("--quota-percent", `${remaining}%`);
          bar.append(quotaElement("span", ""));
          row.append(bar);
        }
        row.append(quotaElement("p", "quota-reset", quotaReset(quota)));
        card.append(row);
      }
      if (account.resetCredits) card.append(renderCreditGroups(account, account.resetCredits.credits || []));
      list.append(card);
    }
    section.append(heading, note, list);
    area.append(section);
  }
  quotaStatus();
}
async function refreshQuotas(force = false) {
  if (quotaBusy || quotaSaving || quotaDrag || (!force && Date.now() - quotaFetchedAt < 60000)) return;
  quotaBusy = true;
  quotaStatus();
  try {
    quotaSnapshot = await api("/api/quotas" + (force ? "?refresh=1" : ""));
    quotaFetchedAt = Date.now();
    $("quota-error").hidden = true;
    renderQuotaAccounts();
    renderResetCountdown();
  } catch (error) {
    $("quota-error").textContent = error.message + (quotaSnapshot ? " Os valores abaixo são da última consulta." : "");
    $("quota-error").hidden = false;
  } finally {
    quotaBusy = false;
    quotaStatus();
  }
}
async function saveQuotaOrder(provider, order, previous) {
  if (quotaSaving || quotaBusy) return;
  const focusIdentity = document.activeElement?.closest(".quota-account")?.dataset.accountId;
  quotaSaving = true;
  quotaStatus();
  let failure;
  try {
    const saved = await api("/api/quotas/order", { method: "POST", body: JSON.stringify({ provider, order, previous }) });
    for (const account of quotaSnapshot.accounts) {
      if (account.providerId === provider) account.priority = saved.order.indexOf(account.id) + 1;
    }
    toast(saved.adjusted ? "Contas sem quota permanecem no fim da fila." : "Ordem de uso salva no 9router.");
  } catch (error) {
    failure = error.message;
  } finally {
    quotaSaving = false;
    renderQuotaAccounts();
    if (focusIdentity) {
      document.querySelector(`[data-account-id="${CSS.escape(focusIdentity)}"] .quota-handle`)?.focus({ preventScroll: true });
    }
  }
  if (failure) {
    await refreshQuotas(true);
    $("quota-error").textContent = failure;
    $("quota-error").hidden = false;
  }
}
function moveQuotaAccount(provider, identity, step) {
  if (quotaBusy || quotaSaving || quotaDrag) return;
  const previous = quotaAccounts(provider).map((account) => account.id);
  const index = previous.indexOf(identity), target = index + step;
  if (index < 0 || target < 0 || target >= previous.length) return;
  const order = [...previous];
  [order[index], order[target]] = [order[target], order[index]];
  saveQuotaOrder(provider, order, previous);
}
function positionQuotaDrag(clientY) {
  if (!quotaDrag) return;
  const { list, card } = quotaDrag;
  const siblings = [...list.children].filter((element) => element !== card);
  const next = siblings.find((element) => {
    const rect = element.getBoundingClientRect();
    return clientY < rect.top + rect.height / 2;
  });
  if (card.nextElementSibling !== (next || null)) list.insertBefore(card, next || null);
}
function startQuotaDrag(event, list, card) {
  if (event.button !== 0 || quotaBusy || quotaSaving || quotaDrag || list.children.length < 2) return;
  event.preventDefault();
  quotaDrag = { pointer: event.pointerId, list, card, y: event.clientY, previous: [...list.children].map((element) => element.dataset.accountId) };
  card.classList.add("dragging");
  $("quota-panel").setPointerCapture(event.pointerId);
  quotaStatus();
  const scroll = () => {
    if (!quotaDrag) return;
    const panel = $("quota-panel"), rect = panel.getBoundingClientRect(), y = quotaDrag.y;
    const delta = y < rect.top + 64 ? -Math.min(12, (rect.top + 64 - y) / 4)
      : y > rect.bottom - 64 ? Math.min(12, (y - rect.bottom + 64) / 4) : 0;
    if (delta) { panel.scrollTop += delta; positionQuotaDrag(y); }
    quotaDrag.frame = requestAnimationFrame(scroll);
  };
  quotaDrag.frame = requestAnimationFrame(scroll);
}
document.addEventListener("pointermove", (event) => {
  if (!quotaDrag || quotaDrag.pointer !== event.pointerId) return;
  event.preventDefault();
  quotaDrag.y = event.clientY;
  positionQuotaDrag(event.clientY);
}, { passive: false });
function finishQuotaDrag(event, cancelled = false) {
  if (!quotaDrag || quotaDrag.pointer !== event.pointerId) return;
  const { list, card, previous, frame } = quotaDrag;
  cancelAnimationFrame(frame);
  quotaDrag = null;
  card.classList.remove("dragging");
  if ($("quota-panel").hasPointerCapture(event.pointerId)) $("quota-panel").releasePointerCapture(event.pointerId);
  const order = [...list.children].map((element) => element.dataset.accountId);
  if (!cancelled && order.some((identity, index) => identity !== previous[index])) saveQuotaOrder(list.dataset.provider, order, previous);
  else renderQuotaAccounts();
}
document.addEventListener("pointerup", (event) => finishQuotaDrag(event));
document.addEventListener("pointercancel", (event) => finishQuotaDrag(event, true));
$("quota-tab").onclick = () => {
  quotaVisible = !quotaVisible;
  if (quotaVisible) {
    terminal.blur();
    $("font-popover").hidden = true;
    $("font-toggle").setAttribute("aria-expanded", "false");
    refreshQuotas();
  }
  render();
};
$("quota-refresh").onclick = () => refreshQuotas(true);
function currentProject() {
  return projects.find((p) => p.path === selectedProject);
}
function render() {
  const project = currentProject();
  $("project-name").textContent = project?.name || "Escolha um projeto";
  $("tabs").replaceChildren();
  const counts = {};
  for (const window of project?.windows || []) {
    counts[window.name] = (counts[window.name] || 0) + 1;
  }
  const indices = {};
  for (const window of project?.windows || []) {
    const button = document.createElement("button");
    button.className = "tab" + (!quotaVisible && selectedWindow === window.id ? " active" : "");
    button.setAttribute(
      "aria-current",
      !quotaVisible && selectedWindow === window.id ? "page" : "false",
    );
    button.append(agentLogo(window.agent), window.name);
    if (counts[window.name] > 1) {
      const number = document.createElement("span");
      number.className = "tab-number";
      indices[window.name] = (indices[window.name] || 0) + 1;
      number.textContent = indices[window.name];
      button.append(number);
    }
    if (pendingAlerts().some((alert) => alert.window === window.id))
      button.append(alertDot("Alerta neste terminal"));
    // A second tap on the open tab offers to close it.
    if (!quotaVisible && selectedWindow === window.id) {
      const more = document.createElement("span");
      more.className = "tab-more";
      more.setAttribute("aria-hidden", "true");
      more.textContent = "⌄";
      button.append(more);
      button.setAttribute("aria-haspopup", "dialog");
      button.setAttribute("aria-label", button.textContent.replace("⌄", "") + ", opções do terminal");
    }
    const label = window.name + (counts[window.name] > 1 ? " " + indices[window.name] : "");
    button.addEventListener("click", () =>
      !quotaVisible && selectedWindow === window.id ? openWindowSheet(window, label) : selectWindow(window.id),
    );
    $("tabs").append(button);
  }
  const empty = !project?.windows.length;
  $("empty").hidden = quotaVisible || !empty;
  $("terminal").hidden = quotaVisible || empty;
  $("quota-panel").hidden = !quotaVisible;
  $("quota-tab").setAttribute("aria-pressed", String(quotaVisible));
  document.querySelector(".controls").hidden = quotaVisible;
  document.querySelector(".font-menu").hidden = quotaVisible;
  $("scroll-bottom").hidden = quotaVisible || !scrolledBack;
  $("reconnect").hidden = quotaVisible || empty || terminalReady;
  updateInputState();
  if (empty) {
    $("reconnect").hidden = true;
    $("connection").textContent = "Sem terminal";
    $("connection").classList.remove("online");
  }
  fitTerminal();
  renderAlerts();
}
let closingWindow = null;
function openWindowSheet(window, label) {
  closingWindow = window.id;
  $("window-project").textContent = (currentProject()?.name || "").toUpperCase();
  $("window-heading").textContent = label;
  $("window-close-copy").textContent =
    window.agent === "shell"
      ? "O shell e qualquer comando em execução nesta aba serão encerrados."
      : `O ${window.name} desta aba será fechado e o que estiver em execução, interrompido. A conversa fica salva e pode ser retomada depois com ${window.agent === "codex" ? "codex resume" : "claude --continue"}.`;
  $("window-close").disabled = false;
  $("window-dialog").showModal();
}
$("window-close").onclick = async () => {
  const identity = closingWindow;
  $("window-close").disabled = true;
  try {
    await api("/api/windows/" + encodeURIComponent(identity), { method: "DELETE" });
    $("window-dialog").close();
    if (selectedWindow === identity) {
      disconnect();
      selectedWindow = "";
    }
    await refresh();
    toast("Terminal encerrado.");
  } catch (error) {
    $("window-close").disabled = false;
    toast(error.message);
  }
};
function renderProjects() {
  $("projects").replaceChildren();
  for (const project of projects) {
    const button = document.createElement("button");
    button.className =
      "project-row" + (project.path === selectedProject ? " active" : "");
    const text = document.createElement("span"),
      name = document.createElement("strong"),
      path = document.createElement("small"),
      count = document.createElement("span");
    name.textContent = project.name;
    path.textContent = project.path.replace(/^\/home\/[^/]+/, "~");
    text.append(name, path);
    count.className = "project-count";
    count.textContent = project.windows.length + " abas";
    const pending = pendingAlerts().filter((alert) => alert.project === project.path).length;
    if (pending) {
      count.append(document.createElement("br"), document.createTextNode(`${pending} alerta${pending > 1 ? "s" : ""}`));
    }
    button.append(text, count);
    button.onclick = () => {
      selectProject(project.path);
      $("project-dialog").close();
    };
    $("projects").append(button);
  }
}
function selectProject(path) {
  quotaVisible = false;
  selectedProject = path;
  localStorage.setItem("project", path);
  const project = currentProject();
  const remembered = localStorage.getItem("window:" + path);
  const window =
    project?.windows.find((w) => w.id === remembered) || project?.windows[0];
  if (window) selectWindow(window.id);
  else {
    disconnect();
    selectedWindow = "";
    render();
  }
}
function disconnect() {
  terminalReady = false;
  updateInputState();
  connecting = false;
  terminalGeneration++;
  clearTimeout(retryTimer);
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
}
function selectWindow(identity) {
  quotaVisible = false;
  if (identity === selectedWindow && (terminalReady || connecting)) {
    render();
    return;
  }
  disconnect();
  selectedWindow = identity;
  scrolledBack = false;
  $("scroll-bottom").hidden = true;
  localStorage.setItem("window:" + selectedProject, identity);
  terminal.reset();
  render();
  connect();
  $("tabs")
    .querySelector(".active")
    ?.scrollIntoView({ block: "nearest", inline: "nearest" });
}
function connect() {
  if (!selectedWindow || stopped) return;
  clearTimeout(retryTimer);
  connecting = true;
  terminalReady = false;
  const generation = ++terminalGeneration;
  $("connection").textContent = "Conectando";
  $("connection").classList.remove("online");
  updateInputState();
  const ws = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/terminal/ws?window=${encodeURIComponent(selectedWindow)}`,
  );
  socket = ws;
  ws.binaryType = "arraybuffer";
  ws.onopen = () => {
    if (generation !== terminalGeneration) {
      ws.close();
      return;
    }
    fitTerminal();
    ws.send(
      encoder.encode(
        JSON.stringify({
          AuthToken: "",
          columns: terminal.cols,
          rows: terminal.rows,
        }),
      ),
    );
  };
  ws.onmessage = (event) => {
    if (generation !== terminalGeneration) return;
    const data =
      typeof event.data === "string"
        ? encoder.encode(event.data)
        : new Uint8Array(event.data);
    const command = String.fromCharCode(data[0]);
    if (command === "0") {
      terminal.write(data.subarray(1));
      terminalReady = true;
      connecting = false;
      $("connection").textContent = "Conectado";
      $("connection").classList.add("online");
      $("reconnect").hidden = true;
      updateInputState();
    } else if (command === "2") {
      /* Font and layout preferences belong to the mobile client. */
    }
  };
  ws.onclose = () => {
    if (generation !== terminalGeneration) return;
    connecting = false;
    terminalReady = false;
    updateInputState();
    $("connection").textContent = navigator.onLine
      ? "Reconectando"
      : "Sem conexão";
    $("connection").classList.remove("online");
    $("reconnect").hidden = quotaVisible;
    retryTimer = setTimeout(async () => {
      await refresh(false);
      if (selectedWindow) connect();
    }, 2500);
  };
  ws.onerror = () => ws.close();
}
async function refresh(initial = false) {
  try {
    const state = await api("/api/state");
    projects = state.projects;
    alerts = state.alerts || [];
    if (!projects.some((p) => p.path === selectedProject))
      selectedProject = projects[0]?.path || "";
    const current = currentProject();
    if (initial || !current?.windows.some((w) => w.id === selectedWindow)) {
      const showingQuotas = quotaVisible;
      selectProject(selectedProject);
      quotaVisible = showingQuotas;
      render();
    } else render();
    if ($("project-dialog").open) renderProjects();
  } catch (error) {
    if (initial) {
      $("project-name").textContent = "Computador indisponível";
      $("reconnect").hidden = false;
      toast(error.message);
    }
  }
}
async function launch(agent) {
  const path = selectedProject;
  if (!path) return toast("Escolha uma pasta primeiro.");
  opening = true;
  updateInputState();
  const buttons = [...document.querySelectorAll("[data-launch]")];
  buttons.forEach((b) => (b.disabled = true));
  try {
    const result = await api("/api/windows", {
      method: "POST",
      body: JSON.stringify({ path, agent }),
    });
    $("agent-dialog").close();
    const state = await api("/api/state");
    projects = state.projects;
    alerts = state.alerts || [];
    selectedProject = path;
    selectWindow(result.id);
  } catch (error) {
    toast(error.message);
  } finally {
    opening = false;
    buttons.forEach((b) => (b.disabled = false));
    render();
  }
}
document
  .querySelectorAll("[data-launch]")
  .forEach((button) =>
    button.addEventListener("click", () => launch(button.dataset.launch)),
  );
$("project-picker").onclick = () => {
  renderProjects();
  $("project-dialog").showModal();
};
$("add-tab").onclick = () => {
  $("agent-project").textContent = currentProject()?.name || "PROJETO";
  $("agent-dialog").showModal();
};
document
  .querySelectorAll("[data-close]")
  .forEach(
    (button) => (button.onclick = () => button.closest("dialog").close()),
  );
document.querySelectorAll("dialog").forEach((dialog) =>
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (
        event.clientX < r.left ||
        event.clientX > r.right ||
        event.clientY < r.top ||
        event.clientY > r.bottom
      )
        dialog.close();
    }
  }),
);
// Shift is sticky: one tap arms it for the next key (keybar or typed), a
// second tap disarms. Shift+Tab is back-tab (Claude's mode toggle) and
// Shift+Enter sends Esc+CR, the newline agents accept without terminal setup.
var shiftArmed = false;
function setShift(on) {
  shiftArmed = on;
  $("shift-key").setAttribute("aria-pressed", String(on));
}
$("shift-key").addEventListener("pointerdown", (e) => e.preventDefault());
$("shift-key").onclick = () => {
  setShift(!shiftArmed);
  terminal.focus();
};
document.querySelectorAll("[data-key]").forEach((button) => {
  button.addEventListener("pointerdown", (e) => e.preventDefault());
  button.onclick = () => {
    const raw = shiftArmed && button.dataset.shiftKey ? button.dataset.shiftKey : button.dataset.key;
    setShift(false);
    if (sendInput(JSON.parse('"' + raw + '"'))) terminal.focus();
  };
});
// Agents treat text and Enter arriving together as a paste, so the command is
// typed first and submitted a moment later.
document.querySelectorAll("[data-command]").forEach((button) => {
  button.addEventListener("pointerdown", (e) => e.preventDefault());
  button.onclick = () => {
    if (!sendInput(button.dataset.command)) return;
    terminal.focus();
    setTimeout(() => sendInput("\r"), 150);
  };
});
function changeFont(delta) {
  const size = Math.max(8, Math.min(28, terminal.options.fontSize + delta));
  terminal.options.fontSize = size;
  localStorage.setItem(FONT_SIZE_KEY, size);
  fitTerminal();
  showFontSize();
}
function showFontSize() {
  const size = terminal.options.fontSize;
  $("font-size").textContent = size + " px";
  $("font-down").disabled = size <= 8;
  $("font-up").disabled = size >= 28;
}
// Rarely changed, so it sits behind a small toggle in the header.
function setFontMenu(open) {
  $("font-popover").hidden = !open;
  $("font-toggle").setAttribute("aria-expanded", String(open));
  if (open) {
    $("app-menu").open = false;
    showFontSize();
  }
}
$("app-menu").addEventListener("toggle", () => {
  if ($("app-menu").open) setFontMenu(false);
});
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".app-menu")) $("app-menu").open = false;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("app-menu").open) {
    $("app-menu").open = false;
    $("app-menu-toggle").focus();
  }
});
function closeAppMenu() {
  $("app-menu").open = false;
  $("app-menu-toggle").focus({ preventScroll: true });
}
$("font-toggle").onclick = () => setFontMenu($("font-popover").hidden);
document.addEventListener("pointerdown", (event) => {
  if (!$("font-popover").hidden && !event.target.closest(".font-menu"))
    setFontMenu(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("font-popover").hidden) {
    setFontMenu(false);
    $("font-toggle").focus();
  }
});
document
  .querySelectorAll("#font-toggle, #font-down, #font-up")
  .forEach((button) =>
    button.addEventListener("pointerdown", (event) => event.preventDefault()),
  );
$("font-down").onclick = () => changeFont(-1);
$("font-up").onclick = () => changeFont(1);
async function browse(path) {
  const generation = ++directoryGeneration;
  $("folder-path").disabled = true;
  $("choose-folder").disabled = true;
  try {
    const info = await api(
      "/api/directories" + (path ? "?path=" + encodeURIComponent(path) : ""),
    );
    if (generation !== directoryGeneration) return;
    folderPath = info.path;
    $("folder-path").value = info.path;
    $("directories").replaceChildren();
    const rows = [
      { name: "↑ Pasta anterior", path: info.parent, parent: true },
      ...info.directories,
    ];
    for (const row of rows) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = row.name;
      if (row.parent) button.className = "parent";
      else {
        const arrow = document.createElement("span");
        arrow.textContent = "›";
        button.append(arrow);
      }
      button.onclick = () => browse(row.path);
      $("directories").append(button);
    }
  } catch (error) {
    toast(error.message);
  } finally {
    if (generation === directoryGeneration) {
      $("folder-path").disabled = false;
      $("choose-folder").disabled = false;
    }
  }
}
$("browse-project").onclick = () => {
  $("project-dialog").close();
  $("folder-dialog").showModal();
  browse(selectedProject ? selectedProject.replace(/\/[^/]+$/, "") : undefined);
};
$("path-form").onsubmit = (event) => {
  event.preventDefault();
  browse($("folder-path").value);
};
$("choose-folder").onclick = async () => {
  try {
    const result = await api("/api/projects", {
      method: "POST",
      body: JSON.stringify({ path: folderPath }),
    });
    await refresh();
    selectProject(result.path);
    $("folder-dialog").close();
    toast("Projeto adicionado. Abra Codex, Claude ou um terminal.");
  } catch (error) {
    toast(error.message);
  }
};
$("retry").onclick = () => {
  disconnect();
  connect();
};
function viewport() {
  const view = window.visualViewport;
  $("app").style.height = (view ? view.height : window.innerHeight) + "px";
  window.scrollTo(0, 0);
  fitTerminal();
}
window.visualViewport?.addEventListener("resize", viewport);
window.addEventListener("resize", viewport);
viewport();
window.addEventListener("online", () => {
  if (!terminalReady) {
    disconnect();
    connect();
  }
  refresh();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    refresh();
    if (quotaVisible) refreshQuotas();
    if (!terminalReady && !connecting) {
      disconnect();
      connect();
    }
    fitTerminal();
  }
});
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  pendingInstall = event;
});
$("install-button").onclick = async () => {
  closeAppMenu();
  if (pendingInstall) {
    await pendingInstall.prompt();
    pendingInstall = null;
    return;
  }
  const area = $("install-instructions");
  area.replaceChildren();
  if (!window.isSecureContext) {
    let config;
    try {
      config = await api("/api/config");
    } catch (error) {
      return toast(error.message);
    }
    const intro = document.createElement("p");
    intro.textContent =
      "Para instalar o app, primeiro ative a conexão segura neste celular.";
    const list = document.createElement("ol");
    for (const text of [
      "Baixe e instale o certificado local nas configurações do celular.",
      "No iPhone: em Ajustes → Geral → Sobre → Confiança de Certificados, ative a confiança para “Terminal Local CA”. No Android: instale como certificado de CA nas configurações de segurança.",
      "Abra a versão HTTPS abaixo. Depois use “Instalar aplicativo” no Chrome ou Compartilhar → Adicionar à Tela de Início no Safari.",
    ]) {
      const item = document.createElement("li");
      item.textContent = text;
      list.append(item);
    }
    const cert = document.createElement("a");
    cert.href = "/ca.crt";
    cert.textContent = "1. Baixar certificado local";
    const secure = document.createElement("a");
    secure.href = `https://${config.ip}:${config.tls_port}/`;
    secure.textContent = "2. Abrir conexão segura";
    area.append(intro, cert, list, secure);
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = matchMedia("(display-mode:standalone)").matches
      ? "O app já está instalado neste dispositivo."
      : "No iPhone, toque em Compartilhar → Adicionar à Tela de Início. No Android, abra o menu do Chrome → Instalar aplicativo ou Adicionar à tela inicial.";
    area.append(paragraph);
  }
  $("install-dialog").showModal();
};
function lockAppOrientation() {
  const installed = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  if (!installed || typeof screen.orientation?.lock !== "function") return;
  // Also cover existing installations waiting for the new manifest to apply.
  // Some platforms do not support orientation locking in installed web apps.
  try {
    screen.orientation.lock("portrait-primary").catch(() => {});
  } catch {}
}
lockAppOrientation();
window.addEventListener("pageshow", lockAppOrientation);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) lockAppOrientation();
});

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
// Push needs the installed app over HTTPS (on iOS, only from the home screen).
const pushSupported =
  window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
let pushBusy = false;
function base64Key(text) {
  const raw = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}
async function pushSubscription() {
  return (await navigator.serviceWorker.ready).pushManager.getSubscription();
}
async function showPushState() {
  if (!pushSupported) return;
  $("push-button").hidden = false;
  const subscription = await pushSubscription();
  let active = false;
  if (subscription && Notification.permission === "granted") {
    const info = await api("/api/push?endpoint=" + encodeURIComponent(subscription.endpoint));
    // The computer may have lost it; register this device again silently.
    if (!info.subscribed)
      await api("/api/push/subscribe", { method: "POST", body: JSON.stringify(subscription) });
    active = true;
  }
  $("push-button").setAttribute("aria-pressed", String(active));
  $("push-button").title = active ? "Notificações ativas" : "Ativar notificações";
  $("push-label").textContent = active ? "Notificações ativas" : "Ativar notificações";
}
$("push-button").onclick = async () => {
  closeAppMenu();
  if (pushBusy) return;
  pushBusy = true;
  try {
    const current = await pushSubscription();
    if (current && $("push-button").getAttribute("aria-pressed") === "true") {
      await api("/api/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: current.endpoint }) });
      await current.unsubscribe();
      toast("Notificações desativadas neste aparelho.");
    } else {
      if ((await Notification.requestPermission()) !== "granted")
        return toast("Permita notificações nas configurações do app para ativar.");
      const { key } = await api("/api/push");
      const registration = await navigator.serviceWorker.ready;
      const subscription =
        current || (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: base64Key(key) }));
      await api("/api/push/subscribe", { method: "POST", body: JSON.stringify(subscription) });
      const { sent } = await api("/api/push/test", { method: "POST" });
      toast(sent ? "Notificações ativas. Um aviso de teste foi enviado." : "Inscrição salva, mas o aviso de teste não foi entregue.");
    }
  } catch (error) {
    toast(error.message || "Não foi possível ativar as notificações.");
  } finally {
    pushBusy = false;
    showPushState().catch(() => {});
  }
};
// Notification links: /?project=…&window=… or /?view=quotas.
function openTarget(href) {
  const params = new URL(href, location.href).searchParams;
  if (params.get("view") === "quotas") {
    if (!quotaVisible) $("quota-tab").click();
    return;
  }
  const project = params.get("project"), window = params.get("window");
  if (!project) return;
  selectedProject = project;
  localStorage.setItem("project", project);
  if (window && currentProject()?.windows.some((w) => w.id === window)) selectWindow(window);
  else selectProject(project);
}
navigator.serviceWorker?.addEventListener("message", (event) => {
  if (event.data?.type === "open") refresh().then(() => openTarget(event.data.url));
});
// Looking at a terminal (or the quotas) makes its notification redundant.
async function closeSeenNotifications() {
  if (!pushSupported || document.hidden) return;
  const registration = await navigator.serviceWorker.ready;
  const seen = (await registration.getNotifications()).filter((n) =>
    quotaVisible ? n.tag.startsWith("quota:") : selectedWindow && n.tag === "term:" + selectedWindow,
  );
  if (!seen.length) return;
  seen.forEach((n) => n.close());
  await api("/api/push/seen", { method: "POST", body: JSON.stringify({ tags: seen.map((n) => n.tag) }) });
}
setInterval(() => closeSeenNotifications().catch(() => {}), 3000);
showPushState().catch(() => {});
const launchTarget = location.search ? location.href : "";
if (launchTarget) history.replaceState(null, "", "/");
refresh(true).then(() => launchTarget && openTarget(launchTarget));
setInterval(() => {
  if (!document.hidden) refresh();
}, 5000);
// Hidden panel: refresh slowly, only to keep the reset-credit countdown current.
let quotaBackgroundAt = Date.now();
setInterval(() => {
  if (document.hidden) return;
  if (quotaVisible || Date.now() - quotaBackgroundAt >= 600000) {
    quotaBackgroundAt = Date.now();
    refreshQuotas();
  }
}, 60000);
setInterval(() => {
  if (!document.hidden) {
    renderResetCountdown();
    if (quotaVisible) document.querySelectorAll(".credit-validity[data-expires-at]").forEach(updateCreditValidity);
  }
}, 1000);
refreshQuotas();
