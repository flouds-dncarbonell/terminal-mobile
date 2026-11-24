"use strict";
(() => {
  const dialog = $("attachment-dialog");
  const limit = 20 * 1024 * 1024;
  let entries = [], destination = null, busy = false, uploaded = null, inserted = 0;
  const size = (bytes) => bytes < 1048576 ? `${Math.max(1, Math.ceil(bytes / 1024))} KB` : `${(bytes / 1048576).toFixed(1)} MB`;

  function status(message = "", error = false) {
    $("attachment-status").textContent = message;
    $("attachment-status").hidden = !message;
    $("attachment-status").classList.toggle("file-error", error);
  }
  function reset() {
    for (const entry of entries) if (entry.preview) URL.revokeObjectURL(entry.preview);
    entries = [];
    uploaded = null;
    inserted = 0;
    destination = null;
    $("attachment-input").value = "";
    $("attachment-clipboard").replaceChildren();
    $("attachment-clipboard").hidden = true;
  }
  function render() {
    $("attachment-list").replaceChildren();
    for (const entry of entries) {
      const row = document.createElement("div");
      row.className = "attachment-row";
      let preview;
      if (entry.preview) {
        preview = document.createElement("img");
        preview.src = entry.preview;
        preview.alt = "";
      } else {
        preview = document.createElement("span");
        preview.className = "attachment-file-mark";
        preview.textContent = "↗";
        preview.setAttribute("aria-hidden", "true");
      }
      const copy = document.createElement("div"), name = document.createElement("strong"), meta = document.createElement("small");
      name.textContent = entry.file.name;
      name.title = entry.file.name;
      meta.textContent = size(entry.file.size);
      copy.append(name, meta);
      const remove = document.createElement("button");
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Remover ${entry.file.name}`);
      remove.disabled = busy || Boolean(uploaded);
      remove.onclick = () => {
        if (entry.preview) URL.revokeObjectURL(entry.preview);
        entries = entries.filter((item) => item !== entry);
        status();
        render();
      };
      row.append(preview, copy, remove);
      $("attachment-list").append(row);
    }
    $("attachment-choose").disabled = busy || Boolean(uploaded);
    $("attachment-paste").disabled = busy || Boolean(uploaded);
    $("attachment-input").disabled = busy || Boolean(uploaded);
    dialog.querySelector("[data-close]").disabled = busy;
    $("attachment-clipboard").contentEditable = String(!busy && !uploaded);
    $("attachment-insert").disabled = busy || !entries.length;
    $("attachment-insert").textContent = busy ? "Adicionando…" : uploaded ? "Continuar na conversa" : `Adicionar à conversa${entries.length ? ` · ${entries.length}` : ""}`;
    dialog.setAttribute("aria-busy", String(busy));
  }
  function open() {
    const window = currentProject()?.windows.find((item) => item.id === selectedWindow);
    if (!window || !["codex", "claude"].includes(window.agent) || !terminalReady || quotaVisible || opening) {
      toast("Abra uma conversa conectada do Codex ou Claude para anexar.");
      return false;
    }
    if (!dialog.open) {
      reset();
      destination = { id: window.id, agent: window.agent, project: selectedProject };
      $("attachment-target").textContent = `${window.name} · ${currentProject().name}`;
      terminal.blur();
      setFontMenu(false);
      status();
      dialog.showModal();
      updateInputState();
      render();
    }
    return true;
  }
  function add(files) {
    if (busy || uploaded) return;
    const incoming = [...files];
    if (!incoming.length) return;
    if (entries.length + incoming.length > 8) return status("Adicione até 8 arquivos por vez.", true);
    if ([...entries.map((entry) => entry.file), ...incoming].reduce((total, file) => total + file.size, 0) > limit)
      return status("Os anexos podem somar até 20 MB.", true);
    if (incoming.some((file) => !file.size)) return status("Um dos arquivos está vazio. Escolha outro arquivo.", true);
    for (const file of incoming) entries.push({ file, preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null });
    status();
    render();
  }
  function clipboardFallback(message) {
    status(message, true);
    $("attachment-clipboard").hidden = false;
    $("attachment-clipboard").focus();
  }
  $("attachment-toggle").onclick = open;
  $("attachment-choose").onclick = () => $("attachment-input").click();
  $("attachment-input").onchange = () => {
    add($("attachment-input").files);
    $("attachment-input").value = "";
  };
  $("attachment-paste").onclick = async () => {
    if (!window.isSecureContext || !navigator.clipboard?.read) {
      return clipboardFallback(window.isSecureContext
        ? "Este navegador não oferece leitura da área de transferência. Cole no campo abaixo ou escolha um arquivo."
        : "Para ler a área de transferência, use o app em HTTPS. Você também pode colar no campo abaixo ou escolher um arquivo.");
    }
    const current = destination;
    try {
      // Start in the click handler: mobile browsers require a user gesture.
      const items = await navigator.clipboard.read();
      const files = [];
      for (const item of items) {
        const type = item.types.find((type) => type === "image/png") || item.types.find((type) => type.startsWith("image/"));
        if (type) {
          const blob = await item.getType(type);
          const extension = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif" }[type] || "png";
          files.push(new File([blob], `imagem-colada-${Date.now()}-${files.length + 1}.${extension}`, { type }));
        }
      }
      if (current !== destination || !dialog.open) return;
      if (!files.length) return clipboardFallback("Não encontrei uma imagem na área de transferência. Copie uma imagem ou escolha um arquivo.");
      add(files);
    } catch {
      if (current === destination && dialog.open)
        clipboardFallback("O navegador não liberou a área de transferência. Cole no campo abaixo ou use Escolher arquivos.");
    }
  };
  document.addEventListener("paste", (event) => {
    if (busy || (dialog.open && uploaded)) {
      if (dialog.open) { event.preventDefault(); event.stopImmediatePropagation(); }
      return;
    }
    if (!dialog.open && !$("terminal").contains(event.target)) return;
    const files = [...(event.clipboardData?.files || [])];
    if (!files.length) {
      if (dialog.open && event.target === $("attachment-clipboard")) {
        event.preventDefault();
        status("A área de transferência não trouxe uma imagem. Use Escolher arquivos.", true);
      }
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    if (open()) add(files);
  }, true);
  $("attachment-clipboard").addEventListener("input", () => { $("attachment-clipboard").replaceChildren(); });

  $("attachment-insert").onclick = async () => {
    if (busy || !entries.length) return;
    const current = destination, generation = terminalGeneration, ws = socket;
    const connected = () => current === destination && selectedWindow === current.id && selectedProject === current.project
      && generation === terminalGeneration && terminalReady && ws === socket && ws?.readyState === WebSocket.OPEN;
    if (!connected()) return status("Volte à conversa original e aguarde a conexão para adicionar os anexos.", true);
    busy = true;
    status("Enviando anexos ao computador…");
    render();
    try {
      if (!uploaded) {
        const data = new FormData();
        for (const entry of entries) data.append("files", entry.file, entry.file.name);
        const response = await fetch(`/api/windows/${encodeURIComponent(current.id)}/attachments`, { method: "POST", body: data, cache: "no-store" });
        let result;
        try { result = await response.json(); } catch { throw new Error("O computador não respondeu ao envio. Tente novamente."); }
        if (!response.ok) throw new Error(result.error || "Não foi possível enviar os anexos.");
        if (result.window !== current.id || result.agent !== current.agent) throw new Error("A conversa mudou. Abra os anexos novamente.");
        uploaded = result.files;
      }
      status("Adicionando os anexos ao campo da mensagem…");
      for (; inserted < uploaded.length; inserted++) {
        if (!connected()) throw new Error("A conexão mudou. Os arquivos foram salvos; reconecte para continuar.");
        const file = uploaded[inserted];
        // An isolated bracketed paste of an image path becomes a native image chip
        // in both CLIs. Documents remain readable local file references.
        const image = /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.path);
        if (!sendInput(`\u001b[200~${image ? file.path : " " + file.path + " "}\u001b[201~`, true))
          throw new Error("Aguarde a conexão para adicionar os anexos.");
        await inputQueue;
        await new Promise((resolve) => setTimeout(resolve, 180));
      }
      dialog.close();
      terminal.focus();
      toast("Anexos adicionados. Escreva sua mensagem e toque em Enter.");
    } catch (error) {
      status(error.message, true);
    } finally {
      busy = false;
      if (dialog.open) render();
      updateInputState();
    }
  };
  dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
  // The shared sheet backdrop handler also calls close(); ignore that while uploading.
  dialog.addEventListener("click", (event) => {
    if (busy && event.target === dialog) event.stopImmediatePropagation();
  }, true);
  dialog.addEventListener("close", () => {
    // close is queued by the browser; a quick new paste may already have reopened it.
    if (dialog.open) return;
    reset();
    updateInputState();
  });
})();
