"use strict";
// Keep browsing independent from the terminal connection and its current tab.
(() => {
  const dialog = $("files-dialog");
  let project = "", projectName = "", requestedPath = ".", folder = null, file = null, showHidden = false, source = false;
  let directoryGeneration = 0, fileGeneration = 0, libraries;
  let uploadJob = null, uploadTarget = null;
  const folderIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg>';
  const documentIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Zm0 0v6h6M8 13h8M8 17h5"/></svg>';
  const rawURL = (token, path) => `/api/files/raw/${token}/${path.split("/").map(encodeURIComponent).join("/")}`;
  const query = (path) => new URLSearchParams({ project, path });
  const downloadURL = (path) => `/api/files/download?${query(path)}`;
  const mediaURL = (path) => `/api/files/media?${query(path)}`;
  const MEDIA = {
    image: ["png", "jpg", "jpeg", "gif", "webp", "avif", "svg", "bmp", "ico", "heic", "heif"],
    video: ["mp4", "m4v", "mov", "webm", "ogv", "mkv", "3gp"],
    audio: ["mp3", "m4a", "aac", "wav", "ogg", "oga", "opus", "flac", "weba"],
  };
  const mediaKind = (name) => {
    const extension = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
    return Object.keys(MEDIA).find((kind) => MEDIA[kind].includes(extension)) || null;
  };
  const mediaIcons = {
    image: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m4 18 5-5 4 4 3-3 4 4"/></svg>',
    video: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3Z"/></svg>',
    audio: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/></svg>',
  };
  const size = (bytes) => bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;

  function status(id, message, error = false) {
    $(id).textContent = message;
    $(id).classList.toggle("file-error", error);
    $(id).hidden = !message;
  }

  function clearMedia() {
    // Stop playback and release the connection before dropping the element.
    for (const element of $("file-media").querySelectorAll("video, audio, img")) {
      if (element.pause) element.pause();
      element.removeAttribute("src");
      if (element.load) element.load();
    }
    $("file-media").replaceChildren();
    $("file-media").hidden = true;
  }

  function clearFile() {
    ++fileGeneration;
    file = null;
    clearMedia();
    $("file-html").removeAttribute("src");
    $("file-html").hidden = true;
    $("file-source").textContent = "";
    $("file-markdown").replaceChildren();
    $("file-viewer").hidden = true;
    $("files-layout").classList.remove("viewing-file");
    renderRows();
  }

  function renderRows() {
    $("files-list").replaceChildren();
    if (!folder) return;
    const filter = $("files-filter").value.toLocaleLowerCase();
    const entries = folder.entries.filter((entry) => entry.name.toLocaleLowerCase().includes(filter));
    for (const entry of entries) {
      const button = document.createElement("button");
      button.className = "file-row";
      button.classList.toggle("selected", file?.path === entry.path);
      const icon = document.createElement("span");
      const kind = entry.directory ? null : mediaKind(entry.name);
      icon.className = entry.directory ? "file-icon folder-icon" : kind ? "file-icon media-icon" : "file-icon";
      icon.innerHTML = entry.directory ? folderIcon : mediaIcons[kind] || documentIcon;
      const name = document.createElement("span"), meta = document.createElement("small");
      name.textContent = entry.name;
      meta.textContent = entry.directory ? "›" : size(entry.size);
      button.append(icon, name, meta);
      button.title = entry.name;
      button.onclick = () => entry.directory ? browse(entry.path) : openFile(entry.path);
      const row = document.createElement("div");
      row.className = "file-entry";
      row.append(button);
      if (!entry.directory) {
        const download = document.createElement("a");
        download.className = "file-download";
        download.href = downloadURL(entry.path);
        download.download = entry.name;
        download.textContent = "↓";
        download.setAttribute("aria-label", `Baixar ${entry.name}`);
        download.title = `Baixar ${entry.name}`;
        row.append(download);
      }
      $("files-list").append(row);
    }
    status("files-status", !entries.length ? (filter ? "Nenhum arquivo com esse nome." : "Esta pasta está vazia.") : folder.truncated ? "Mostrando os primeiros 2.000 itens desta pasta." : "");
  }

  async function browse(path = ".") {
    const generation = ++directoryGeneration;
    requestedPath = path;
    clearFile();
    folder = null;
    $("files-filter").value = "";
    $("files-list").replaceChildren();
    $("files-path").textContent = projectName + (path === "." ? "" : "/" + path);
    $("files-up").disabled = true;
    $("files-refresh").disabled = true;
    $("files-upload").disabled = true;
    $("files-list").setAttribute("aria-busy", "true");
    status("files-status", "Carregando arquivos…");
    try {
      const info = await api(`/api/files?${query(path)}&hidden=${showHidden ? 1 : 0}`);
      if (generation !== directoryGeneration || !dialog.open) return;
      folder = info;
      $("files-path").textContent = info.name + (info.path === "." ? "" : "/" + info.path);
      $("files-path").title = info.project + (info.path === "." ? "" : "/" + info.path);
      $("files-up").disabled = info.parent === null;
      renderRows();
    } catch (error) {
      if (generation === directoryGeneration) status("files-status", error.message, true);
    } finally {
      if (generation === directoryGeneration) {
        $("files-refresh").disabled = false;
        $("files-upload").disabled = !folder || Boolean(uploadJob);
        $("files-list").setAttribute("aria-busy", "false");
      }
    }
  }

  function loadLibraries() {
    if (!libraries) {
      libraries = Promise.all(["marked.min.js", "purify.min.js"].map((name) => new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "/assets/vendor/" + name;
        script.onload = resolve;
        script.onerror = () => { script.remove(); reject(new Error("Não foi possível formatar o Markdown. Veja o código ou tente novamente.")); };
        document.head.append(script);
      }))).catch((error) => { libraries = null; throw error; });
    }
    return libraries;
  }

  function localPath(href) {
    try {
      if (href.startsWith("/") && !href.startsWith("//")) href = rawURL(file.token, href.slice(1));
      const resolved = new URL(href, location.origin + rawURL(file.token, file.path));
      const prefix = `/api/files/raw/${file.token}/`;
      if (resolved.origin !== location.origin || !resolved.pathname.startsWith(prefix)) return null;
      return decodeURIComponent(resolved.pathname.slice(prefix.length));
    } catch { return null; }
  }

  async function renderFile(generation) {
    for (const id of ["file-source", "file-markdown", "file-html"]) $(id).hidden = true;
    $("file-mode").hidden = !file || file.kind === "text";
    $("file-mode").textContent = source ? "Prévia" : "Código";
    $("file-mode").setAttribute("aria-pressed", String(source));
    if (!file) return;
    if (source || file.kind === "text") {
      $("file-source").textContent = file.content;
      $("file-source").hidden = false;
    } else if (file.kind === "html") {
      $("file-html").src = rawURL(file.token, file.path);
      $("file-html").hidden = false;
    } else {
      try {
        await loadLibraries();
        if (generation !== fileGeneration || !dialog.open || source) return;
        const article = $("file-markdown");
        article.innerHTML = DOMPurify.sanitize(marked.parse(file.content, { gfm: true }), {
          USE_PROFILES: { html: true }, FORBID_TAGS: ["style", "form", "input", "button", "textarea", "select"],
          FORBID_ATTR: ["style", "srcset"], SANITIZE_NAMED_PROPS: true,
        });
        for (const heading of article.querySelectorAll("h1, h2, h3, h4, h5, h6")) {
          if (!heading.id) heading.id = heading.textContent.toLowerCase().trim().replace(/[^\p{L}\p{N}\s-]/gu, "").replace(/\s+/g, "-");
        }
        for (const image of article.querySelectorAll("img")) {
          const path = localPath(image.getAttribute("src") || "");
          if (path !== null) image.src = rawURL(file.token, path);
          image.loading = "lazy";
          image.referrerPolicy = "no-referrer";
        }
        for (const link of article.querySelectorAll("a")) {
          link.rel = "noopener noreferrer";
          link.target = "_blank";
          link.addEventListener("click", (event) => {
            const href = link.getAttribute("href") || "";
            if (href.startsWith("#")) {
              event.preventDefault();
              const target = article.querySelector(`[id="${CSS.escape(href.slice(1))}"]`);
              target?.scrollIntoView({ block: "start" });
              return;
            }
            const path = localPath(href);
            if (path !== null) { event.preventDefault(); openFile(path); }
          });
        }
        article.hidden = false;
      } catch (error) {
        if (generation !== fileGeneration) return;
        $("file-source").textContent = file.content;
        $("file-source").hidden = false;
        status("file-status", error.message, true);
      }
    }
  }

  async function openFile(path) {
    const generation = ++fileGeneration;
    file = null;
    source = false;
    $("file-html").removeAttribute("src");
    $("file-viewer").hidden = false;
    $("files-layout").classList.add("viewing-file");
    $("file-name").textContent = path.split("/").pop();
    $("file-download").href = downloadURL(path);
    $("file-download").download = path.split("/").pop();
    $("file-meta").textContent = "";
    $("file-mode").hidden = true;
    for (const id of ["file-source", "file-markdown", "file-html"]) $(id).hidden = true;
    clearMedia();
    $("file-back").focus({ preventScroll: true });
    const kind = mediaKind(path);
    if (kind) return openMedia(path, kind, generation);
    status("file-status", "Abrindo arquivo…");
    try {
      const info = await api(`/api/files/read?${query(path)}`);
      if (generation !== fileGeneration || !dialog.open) return;
      file = info;
      $("file-name").textContent = info.name;
      $("file-meta").textContent = size(info.size) + (info.kind === "html" ? " · Prévia HTML" : "");
      $("file-name").title = info.path;
      status("file-status", "");
      $("file-content").scrollTop = 0;
      renderRows();
      await renderFile(generation);
    } catch (error) {
      if (generation === fileGeneration) status("file-status", error.message, true);
    }
  }

  function openMedia(path, kind, generation) {
    const name = path.split("/").pop();
    const entry = folder?.entries.find((item) => item.path === path);
    const label = { image: "Imagem", video: "Vídeo", audio: "Áudio" }[kind];
    file = { path, name, kind };
    $("file-meta").textContent = (entry ? size(entry.size) + " · " : "") + label;
    $("file-name").title = path;
    renderRows();
    const element = document.createElement(kind === "image" ? "img" : kind);
    element.className = "file-media-" + kind;
    if (kind === "image") {
      element.alt = name;
      element.decoding = "async";
      element.onload = () => {
        if (generation !== fileGeneration) return;
        $("file-meta").textContent = (entry ? size(entry.size) + " · " : "") + `${element.naturalWidth}×${element.naturalHeight}`;
        status("file-status", "");
      };
      // Tap toggles fit-to-screen and original size (pan by scrolling).
      element.onclick = () => $("file-media").classList.toggle("zoomed");
    } else {
      element.controls = true;
      element.preload = "metadata";
      element.playsInline = true;
      element.setAttribute("playsinline", "");
      element.onloadedmetadata = () => {
        if (generation !== fileGeneration) return;
        status("file-status", "");
        if (kind === "video" && element.videoWidth) $("file-meta").textContent = (entry ? size(entry.size) + " · " : "") + `${element.videoWidth}×${element.videoHeight} · ${duration(element.duration)}`;
        else if (Number.isFinite(element.duration)) $("file-meta").textContent = (entry ? size(entry.size) + " · " : "") + duration(element.duration);
      };
    }
    element.onerror = () => {
      if (generation !== fileGeneration) return;
      status("file-status", `Este navegador não consegue mostrar este ${label.toLowerCase()} (formato ou codec sem suporte). Use ↓ para baixar.`, true);
      $("file-media").hidden = true;
    };
    status("file-status", "Carregando…");
    element.src = mediaURL(path);
    $("file-media").classList.remove("zoomed");
    $("file-media").dataset.kind = kind;
    $("file-media").append(element);
    $("file-media").hidden = false;
    $("file-content").scrollTop = 0;
  }

  function duration(seconds) {
    if (!Number.isFinite(seconds)) return "";
    const total = Math.round(seconds), h = Math.floor(total / 3600), m = Math.floor(total / 60) % 60, s = total % 60;
    return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + ":" + String(s).padStart(2, "0");
  }

  function sendFile(job, item, index, count) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      job.xhr = xhr;
      xhr.open("POST", `/api/files/upload?${new URLSearchParams(job.target.params)}`);
      const update = (percentage) => {
        if (uploadJob === job && dialog.open) status("files-transfer-status", `Enviando ${index + 1}/${count}: ${item.name} · ${percentage}%\nDestino: ${job.target.label}`);
      };
      xhr.upload.onprogress = (event) => { if (event.lengthComputable) update(Math.floor(event.loaded / event.total * 100)); };
      xhr.onload = () => {
        let result;
        try { result = JSON.parse(xhr.responseText); } catch {}
        if (xhr.status >= 200 && xhr.status < 300 && result?.name) resolve(result);
        else reject(new Error(result?.error || "Não foi possível enviar. Tente novamente."));
      };
      xhr.onerror = () => reject(new Error("Conexão interrompida. Tente enviar novamente."));
      xhr.onabort = () => reject(new Error("Envio cancelado."));
      update(0);
      const body = new FormData();
      body.append("file", item, item.name);
      xhr.send(body);
    });
  }

  async function uploadFiles(items, target) {
    if (!items.length || !target || uploadJob) return;
    const job = { target, cancelled: false, xhr: null };
    uploadJob = job;
    $("files-upload").disabled = true;
    $("files-upload-cancel").hidden = false;
    const sent = [], failures = [], renamed = [];
    try {
      for (const [index, item] of items.entries()) {
        if (job.cancelled) break;
        try {
          if (item.size > target.limit) throw new Error(`O limite por arquivo é ${size(target.limit)}.`);
          const result = await sendFile(job, item, index, items.length);
          sent.push(result);
          if (result.name !== item.name) renamed.push(`${item.name} → ${result.name}`);
        } catch (error) {
          if (job.cancelled) break;
          failures.push(`${item.name}: ${error.message}`);
        }
      }
      if (dialog.open && uploadJob === job) {
        const summary = `${sent.length} de ${items.length} arquivo(s) enviado(s) para ${target.label}.`;
        status("files-transfer-status", [job.cancelled ? "Envio cancelado." : "", summary, ...renamed, ...failures].filter(Boolean).join("\n"), failures.length > 0);
        if (sent.length && project === target.params.project && folder?.path === target.params.path) await browse(folder.path);
      }
    } finally {
      if (uploadJob === job) {
        uploadJob = null;
        $("files-upload").disabled = !folder;
        $("files-upload-cancel").hidden = true;
      }
    }
  }

  $("files-upload").onclick = () => {
    if (!folder || uploadJob) return;
    uploadTarget = { params: { project, path: folder.path }, label: $("files-path").textContent, limit: folder.uploadLimit };
    $("files-upload-input").value = "";
    $("files-upload-input").click();
  };
  $("files-upload-input").onchange = () => {
    if (dialog.open) uploadFiles(Array.from($("files-upload-input").files), uploadTarget);
  };
  $("files-upload-cancel").onclick = () => {
    if (uploadJob) { uploadJob.cancelled = true; uploadJob.xhr?.abort(); }
  };

  $("files-toggle").onclick = () => {
    const current = currentProject();
    if (!current) return toast("Escolha um projeto primeiro.");
    project = current.path;
    projectName = current.name;
    $("files-project").textContent = current.name;
    status("files-transfer-status", "");
    terminal.blur();
    setFontMenu(false);
    dialog.showModal();
    updateInputState();
    browse();
  };
  $("files-up").onclick = () => { if (folder?.parent !== null && folder) browse(folder.parent); };
  $("files-refresh").onclick = () => browse(requestedPath);
  $("files-filter").oninput = renderRows;
  $("files-hidden").onclick = () => {
    showHidden = !showHidden;
    $("files-hidden").setAttribute("aria-pressed", String(showHidden));
    $("files-hidden").setAttribute("aria-label", showHidden ? "Ocultar arquivos ocultos" : "Mostrar arquivos ocultos");
    browse(folder?.path || ".");
  };
  $("file-back").onclick = () => { clearFile(); $("files-filter").focus({ preventScroll: true }); };
  $("file-mode").onclick = () => {
    source = !source;
    status("file-status", "");
    renderFile(fileGeneration);
  };
  dialog.addEventListener("close", () => {
    uploadTarget = null;
    if (uploadJob) {
      uploadJob.cancelled = true;
      uploadJob.xhr?.abort();
      uploadJob = null;
    }
    $("files-upload-cancel").hidden = true;
    ++directoryGeneration;
    clearFile();
    updateInputState();
  });
})();
