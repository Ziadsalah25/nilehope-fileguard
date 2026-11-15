// ==================== 1. Dark Mode Management ====================
(function initTheme() {
  const saved = localStorage.getItem("nh_theme");
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  if (saved === "dark" || (!saved && prefersDark)) {
    document.body.classList.add("dark-theme");
  }
})();

document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.getElementById("themeToggle");
  const icon = document.getElementById("themeIcon");

  function updateIcon() {
    if (document.body.classList.contains("dark-theme")) {
      if (icon) icon.textContent = "☀️";
    } else {
      if (icon) icon.textContent = "🌙";
    }
  }

  updateIcon();

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      document.body.classList.toggle("dark-theme");
      const isDark = document.body.classList.contains("dark-theme");
      localStorage.setItem("nh_theme", isDark ? "dark" : "light");
      updateIcon();
    });
  }

  // ==================== 2. Auto-Submit & Sliders ====================
  document.querySelectorAll("select[data-autosubmit]").forEach(s => {
    s.addEventListener("change", () => s.form.submit());
  });

  document.querySelectorAll("input[data-show]").forEach(i => {
    i.addEventListener("input", () => {
      const el = document.getElementById(i.dataset.show);
      if (el) el.textContent = i.value;
    });
  });

  // ==================== 3. 10-Second Live Polling ====================
  const live = document.getElementById("live");
  if (live) {
    setInterval(async () => {
      try {
        const r = await fetch(live.dataset.url, { credentials: "same-origin" });
        if (r.status === 401) { location.href = "/login"; return; }
        if (r.ok) live.innerHTML = await r.text();
      } catch (e) { /* ignore connection glitch */ }
    }, 10000);
  }
});

// Explicitly name disruptive effects before an administrator sends a command.
document.querySelectorAll("form[data-command-confirm]").forEach(form => {
  form.addEventListener("submit", event => {
    const command = form.querySelector("select[name=command]").value;
    const messages = {
      isolate_smb: "Disconnect ALL active SMB sessions on this server? Open files and hospital workflows may be interrupted. Clients may reconnect afterward.",
      lock_usb: "Disable the USB storage driver on this device? Existing connected devices may require reconnect/reboot.",
      restore_usb: "Restore this device's USB storage startup setting saved by the agent? Domain policy may override it.",
      sync_policy: "Refresh computer Group Policy on this device?",
      collect_logs: "Collect recent file-share audit event metadata from this device?"
    };
    if (!window.confirm(messages[command] || "Send this command?")) event.preventDefault();
  });
});
