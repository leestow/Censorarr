(() => {
  function $(id) { return document.getElementById(id); }

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

  function makePanel() {
    if ($('dialogueEnhancementSection')) return;
    const page = document.querySelector('.settings-page[data-settings="detection"]');
    if (!page) return;

    const section = document.createElement('div');
    section.className = 'section';
    section.id = 'dialogueEnhancementSection';
    section.innerHTML = `
      <h3>Dialogue Enhancement <span class="optional-label">Experimental</span></h3>
      <div class="setting-callout">
        Creates an additional speech-focused stereo audio track while preserving CLEAN and original audio.
        Surround sources emphasize the center/dialogue channel; all sources receive speech EQ, dynamic compression,
        and peak limiting. This first version does not use AI voice separation.
      </div>
      <div class="field">
        <label>Create Dialogue Enhanced track</label>
        <select id="sDialogueEnabled"><option value="false">Disabled</option><option value="true">Enabled</option></select>
      </div>
      <div class="split">
        <div class="field"><label>Enhancement strength</label><select id="sDialogueStrength"><option value="light">Light</option><option value="medium">Medium</option><option value="strong">Strong</option></select></div>
        <div class="field"><label>Track name</label><input id="sDialogueTitle" value="English - DIALOGUE ENHANCED"></div>
      </div>
      <div class="split">
        <div class="field"><label>Language tag</label><input id="sDialogueLanguage" value="eng"></div>
        <div class="field"><label>Audio codec</label><select id="sDialogueCodec"><option value="aac">AAC</option><option value="ac3">AC3</option><option value="eac3">E-AC3</option></select></div>
      </div>
      <div class="split">
        <div class="field"><label>Bitrate</label><select id="sDialogueBitrate"><option value="128k">128k</option><option value="160k">160k</option><option value="192k">192k</option><option value="256k">256k</option><option value="320k">320k</option><option value="384k">384k</option></select></div>
        <div class="field"><label>Replace an existing track with the same name</label><select id="sDialogueReplace"><option value="true">Yes</option><option value="false">No</option></select></div>
      </div>
      <div class="field"><label>Make Dialogue Enhanced the default audio track</label><select id="sDialogueDefault"><option value="false">No — keep CLEAN default</option><option value="true">Yes — Dialogue Enhanced becomes default</option></select></div>
      <div class="footer-note">Medium is the recommended starting point. The enhanced track is stereo for broad Plex/device compatibility.</div>
      <div class="toolbar" style="margin-top:10px"><button class="good" id="saveDialogueEnhancement">Save Dialogue Enhancement</button><span class="footer-note" id="dialogueEnhancementStatus"></span></div>
    `;
    page.appendChild(section);
    $('saveDialogueEnhancement').addEventListener('click', save);
  }

  async function load() {
    makePanel();
    if (!$('dialogueEnhancementSection')) return;
    try {
      const s = await request('/api/dialogue-enhancement/settings');
      $('sDialogueEnabled').value = String(!!s.enabled);
      $('sDialogueStrength').value = s.strength || 'medium';
      $('sDialogueTitle').value = s.title || 'English - DIALOGUE ENHANCED';
      $('sDialogueLanguage').value = s.language || 'eng';
      $('sDialogueCodec').value = s.codec || 'aac';
      const bitrate = s.bitrate || '192k';
      if (![...$('sDialogueBitrate').options].some(o => o.value === bitrate)) {
        const option = document.createElement('option'); option.value = bitrate; option.textContent = bitrate; $('sDialogueBitrate').appendChild(option);
      }
      $('sDialogueBitrate').value = bitrate;
      $('sDialogueReplace').value = String(s.replace_existing !== false);
      $('sDialogueDefault').value = String(!!s.make_default);
      $('dialogueEnhancementStatus').textContent = s.enabled ? 'Enabled for future processed media.' : 'Currently disabled.';
    } catch (err) {
      $('dialogueEnhancementStatus').textContent = `Could not load: ${err.message || err}`;
    }
  }

  async function save() {
    const btn = $('saveDialogueEnhancement');
    btn.disabled = true;
    $('dialogueEnhancementStatus').textContent = 'Saving…';
    try {
      const body = {
        enabled: $('sDialogueEnabled').value === 'true',
        strength: $('sDialogueStrength').value,
        title: $('sDialogueTitle').value.trim(),
        language: $('sDialogueLanguage').value.trim(),
        codec: $('sDialogueCodec').value,
        bitrate: $('sDialogueBitrate').value,
        replace_existing: $('sDialogueReplace').value === 'true',
        make_default: $('sDialogueDefault').value === 'true',
      };
      const result = await request('/api/dialogue-enhancement/settings', { method: 'POST', body: JSON.stringify(body) });
      $('dialogueEnhancementStatus').textContent = result.message || 'Saved.';
    } catch (err) {
      $('dialogueEnhancementStatus').textContent = `Save failed: ${err.message || err}`;
    } finally {
      btn.disabled = false;
    }
  }

  function install() {
    makePanel();
    const original = window.openSettingsNav;
    if (typeof original === 'function' && !original.__dialogueWrapped) {
      const wrapped = async function(section, el) {
        const result = await original(section, el);
        if (section === 'detection') await load();
        return result;
      };
      wrapped.__dialogueWrapped = true;
      window.openSettingsNav = wrapped;
    }
    const detection = document.querySelector('.settings-page[data-settings="detection"].active');
    if (detection) load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
