(() => {
  const state = { dismissed: sessionStorage.getItem('censorarr-update-dismissed') || '' };

  async function request(path, options) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      ...(options || {}),
    });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    return data;
  }

  function removeBanner() {
    const old = document.getElementById('censorarr-update-banner');
    if (old) old.remove();
  }

  function button(text, primary = false) {
    const el = document.createElement('button');
    el.textContent = text;
    el.style.cssText = [
      'border:1px solid rgba(255,255,255,.32)',
      'border-radius:8px',
      'padding:7px 11px',
      'font-weight:700',
      'cursor:pointer',
      primary ? 'background:#fff;color:#151515' : 'background:rgba(255,255,255,.10);color:#fff',
    ].join(';');
    return el;
  }

  async function saveAutoInstall(enabled, checkbox) {
    if (checkbox) checkbox.disabled = true;
    try {
      const result = await request('/api/update/preferences', {
        method: 'POST',
        body: JSON.stringify({ auto_install: !!enabled }),
      });
      if (checkbox) checkbox.checked = !!result.auto_install;
      return !!result.auto_install;
    } catch (err) {
      if (checkbox) checkbox.checked = !enabled;
      throw err;
    } finally {
      if (checkbox) checkbox.disabled = false;
    }
  }

  async function installNow(status, control, messageTarget) {
    if (!confirm(`Install Censorarr ${status.latest_version} now?\n\nThe Docker/Synology app source will be backed up and the container will restart automatically.`)) return;
    if (control) {
      control.disabled = true;
      control.textContent = 'Installing…';
    }
    try {
      const result = await request('/api/update/install', { method: 'POST', body: '{}' });
      if (!result.updated) {
        if (control) control.textContent = 'Already current';
        return;
      }
      if (messageTarget) messageTarget.textContent = `Update installed. Restarting Censorarr…`;
      let tries = 0;
      const poll = setInterval(async () => {
        tries += 1;
        try {
          const health = await request('/api/health');
          if (String(health.version || '') === String(result.to || '')) {
            clearInterval(poll);
            location.reload();
          }
        } catch (_) {}
        if (tries > 90) clearInterval(poll);
      }, 2000);
    } catch (err) {
      if (control) {
        control.disabled = false;
        control.textContent = 'Update now';
      }
      alert(`Censorarr update failed:\n\n${err.message || err}`);
    }
  }

  function renderSettings(status) {
    const page = document.querySelector('.settings-page[data-settings="backup"]');
    if (!page || !status) return;

    let section = document.getElementById('censorarrUpdateSettings');
    if (!section) {
      section = document.createElement('div');
      section.className = 'section';
      section.id = 'censorarrUpdateSettings';
      section.innerHTML = `
        <h3>Updates</h3>
        <div class="statline"><span>Current version</span><b id="censorarrUpdateCurrent">—</b></div>
        <div class="statline"><span>Latest stable release</span><b id="censorarrUpdateLatest">—</b></div>
        <div class="field" style="margin-top:12px"><label class="checkrow"><input id="censorarrAutoUpdate" type="checkbox"> Automatically install safe updates</label><div class="footer-note" id="censorarrAutoUpdateHelp"></div></div>
        <div class="toolbar"><button id="censorarrCheckUpdate">Check for updates</button><button class="good hidden" id="censorarrInstallUpdate">Update now</button><button class="hidden" id="censorarrReleaseNotes">Release notes</button></div>
        <div class="footer-note" id="censorarrUpdateState"></div>
      `;
      page.appendChild(section);
      document.getElementById('censorarrCheckUpdate').onclick = () => check(true);
    }

    const current = document.getElementById('censorarrUpdateCurrent');
    const latest = document.getElementById('censorarrUpdateLatest');
    const auto = document.getElementById('censorarrAutoUpdate');
    const autoHelp = document.getElementById('censorarrAutoUpdateHelp');
    const installButton = document.getElementById('censorarrInstallUpdate');
    const notesButton = document.getElementById('censorarrReleaseNotes');
    const message = document.getElementById('censorarrUpdateState');

    current.textContent = status.current_version || 'Unknown';
    latest.textContent = status.latest_version || (status.ok ? status.current_version || 'Unknown' : 'Unavailable');
    auto.checked = !!status.auto_install_enabled;

    const docker = status.platform === 'docker';
    auto.disabled = !docker;
    autoHelp.textContent = docker
      ? 'When enabled, Censorarr checks periodically and installs verified source-only updates once the media worker is idle. Updates that require a container rebuild are never installed automatically.'
      : status.platform === 'development'
        ? 'Automatic stable updates are disabled while the experimental development branch is running.'
        : 'Automatic installer replacement is not yet enabled on this platform; Censorarr will still alert you when a release is available.';
    auto.onchange = async () => {
      try {
        await saveAutoInstall(auto.checked, auto);
      } catch (err) {
        alert(`Could not save update preference:\n\n${err.message || err}`);
      }
    };

    installButton.classList.toggle('hidden', !(status.update_available && status.install && status.install.supported));
    installButton.onclick = () => installNow(status, installButton, message);

    notesButton.classList.toggle('hidden', !status.release_url);
    notesButton.onclick = () => status.release_url && window.open(status.release_url, '_blank', 'noopener');

    if (!status.ok) {
      message.textContent = `Update check failed: ${status.error || 'unknown error'}`;
    } else if (!status.update_available) {
      message.textContent = 'Censorarr is up to date.';
    } else if (status.install && status.install.supported) {
      message.textContent = `Censorarr ${status.latest_version} is available and can be installed safely from this screen.`;
    } else {
      message.textContent = `Censorarr ${status.latest_version} is available. ${status.install?.reason || 'Manual update required.'}`;
    }
  }

  function show(status) {
    renderSettings(status);
    if (!status || !status.update_available) {
      removeBanner();
      return;
    }
    if (state.dismissed === String(status.latest_version || '')) return;
    removeBanner();

    const banner = document.createElement('div');
    banner.id = 'censorarr-update-banner';
    banner.style.cssText = [
      'position:sticky', 'top:0', 'z-index:99999', 'display:flex', 'gap:12px',
      'align-items:center', 'justify-content:center', 'flex-wrap:wrap',
      'padding:11px 14px', 'background:#222', 'color:#fff',
      'border-bottom:1px solid rgba(255,255,255,.18)', 'box-shadow:0 4px 16px rgba(0,0,0,.25)',
      'font-family:system-ui,-apple-system,Segoe UI,sans-serif', 'font-size:14px'
    ].join(';');

    const text = document.createElement('span');
    const strong = document.createElement('strong');
    strong.textContent = `Censorarr ${String(status.latest_version || '')} is available.`;
    text.append(strong, document.createTextNode(` You are running ${String(status.current_version || '')}.`));
    banner.appendChild(text);

    const install = status.install || {};
    if (install.supported) {
      const now = button('Update now', true);
      now.onclick = () => installNow(status, now, text);
      banner.appendChild(now);
    } else {
      const reason = document.createElement('span');
      reason.textContent = install.reason || 'Manual update required.';
      reason.style.opacity = '.78';
      reason.style.fontSize = '12px';
      banner.appendChild(reason);
    }

    if (status.release_url) {
      const notes = button('Release notes');
      notes.onclick = () => window.open(status.release_url, '_blank', 'noopener');
      banner.appendChild(notes);
    }

    if (status.platform === 'docker') {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;white-space:nowrap';
      const auto = document.createElement('input');
      auto.type = 'checkbox';
      auto.checked = !!status.auto_install_enabled;
      auto.onchange = async () => {
        try {
          const value = await saveAutoInstall(auto.checked, auto);
          const settingsAuto = document.getElementById('censorarrAutoUpdate');
          if (settingsAuto) settingsAuto.checked = value;
        } catch (err) {
          alert(`Could not save update preference:\n\n${err.message || err}`);
        }
      };
      label.append(auto, document.createTextNode('Auto-install safe updates'));
      banner.appendChild(label);
    }

    const later = button('Later');
    later.onclick = () => {
      state.dismissed = String(status.latest_version || '');
      sessionStorage.setItem('censorarr-update-dismissed', state.dismissed);
      removeBanner();
    };
    banner.appendChild(later);

    document.body.prepend(banner);
  }

  async function check(force = false) {
    try {
      const status = await request(`/api/update/status${force ? '?force=true' : ''}`);
      show(status);
      return status;
    } catch (err) {
      console.debug('Censorarr update check failed:', err);
      const fallback = { ok: false, error: String(err.message || err), current_version: 'Unknown', platform: 'unknown' };
      renderSettings(fallback);
      return fallback;
    }
  }

  window.CensorarrUpdater = { check };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(() => check(false), 1200));
  } else {
    setTimeout(() => check(false), 1200);
  }
})();
