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

  function show(status) {
    if (!status || !status.update_available) return;
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
    text.innerHTML = `<strong>Censorarr ${String(status.latest_version || '')} is available.</strong> You are running ${String(status.current_version || '')}.`;
    banner.appendChild(text);

    const install = status.install || {};
    if (install.supported) {
      const now = button('Update now', true);
      now.onclick = async () => {
        if (!confirm(`Install Censorarr ${status.latest_version} now?\n\nThe Docker/Synology app source will be backed up and the container will restart automatically.`)) return;
        now.disabled = true;
        now.textContent = 'Installing…';
        try {
          const result = await request('/api/update/install', { method: 'POST', body: '{}' });
          if (!result.updated) {
            now.textContent = 'Already current';
            return;
          }
          text.innerHTML = `<strong>Update installed.</strong> Restarting Censorarr…`;
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
          now.disabled = false;
          now.textContent = 'Update now';
          alert(`Censorarr update failed:\n\n${err.message || err}`);
        }
      };
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
        auto.disabled = true;
        try {
          const result = await request('/api/update/preferences', {
            method: 'POST',
            body: JSON.stringify({ auto_install: auto.checked }),
          });
          auto.checked = !!result.auto_install;
        } catch (err) {
          auto.checked = !auto.checked;
          alert(`Could not save update preference:\n\n${err.message || err}`);
        } finally {
          auto.disabled = false;
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
    } catch (err) {
      console.debug('Censorarr update check failed:', err);
    }
  }

  window.CensorarrUpdater = { check };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(() => check(false), 1200));
  } else {
    setTimeout(() => check(false), 1200);
  }
})();
