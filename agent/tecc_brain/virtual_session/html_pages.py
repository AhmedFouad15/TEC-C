"""HTML UI Templates for Laptop Admin Screen (Section 8.4) & Phone Browser (Section 8.5).

Follows modern, clean, responsive design with zero external CDN dependencies.
"""

from __future__ import annotations

import json
from typing import Any


def render_laptop_admin_html(sessions: list[dict[str, Any]], audit_log: list[dict[str, Any]]) -> str:
    """Section 8.4: Laptop UI ('Virtual Sessions' screen)."""
    sessions_json = json.dumps(sessions)
    audit_json = json.dumps(audit_log)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tec-C PegGuard | Virtual Sessions</title>
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: #1f2937;
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      padding: 24px;
      line-height: 1.5;
    }}
    .container {{ max-width: 1100px; margin: 0 auto; }}
    .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
    .title {{ font-size: 24px; font-weight: 700; }}
    .subtitle {{ font-size: 14px; color: var(--text-muted); }}
    
    .banner {{
      background: #1e1b4b;
      border: 1px solid #4338ca;
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .banner-text {{ font-size: 14px; color: #c7d2fe; }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .badge-pending {{ background: #78350f; color: #fde68a; }}
    .badge-active {{ background: #064e3b; color: #a7f3d0; }}
    .badge-relink {{ background: #7c2d12; color: #fed7aa; }}
    .badge-revoked {{ background: #450a0a; color: #fca5a5; }}

    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 24px;
    }}
    .card-title {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; }}
    
    .form-group {{ margin-bottom: 16px; }}
    label {{ display: block; font-size: 14px; color: var(--text-muted); margin-bottom: 6px; }}
    input[type="text"] {{
      width: 100%;
      background: #1f2937;
      border: 1px solid #374151;
      color: #fff;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 14px;
    }}
    .checkbox-group {{ display: flex; align-items: center; gap: 8px; font-size: 14px; }}
    
    .btn {{
      padding: 8px 16px;
      border-radius: 6px;
      border: none;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }}
    .btn-primary {{ background: var(--primary); color: #fff; }}
    .btn-primary:hover {{ background: var(--primary-hover); }}
    .btn-danger {{ background: var(--danger); color: #fff; }}
    .btn-danger:hover {{ background: #dc2626; }}
    .btn-secondary {{ background: #374151; color: #f3f4f6; }}
    .btn-secondary:hover {{ background: #4b5563; }}
    .btn-success {{ background: var(--success); color: #fff; }}

    .pair-card {{
      background: #172554;
      border: 1px solid #1e40af;
      border-radius: 8px;
      padding: 16px;
      margin-top: 16px;
    }}
    .code-display {{
      font-family: monospace;
      font-size: 28px;
      font-weight: 700;
      letter-spacing: 4px;
      color: #93c5fd;
      margin: 8px 0;
    }}
    
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--card-border); font-size: 14px; }}
    th {{ color: var(--text-muted); font-weight: 600; }}
    
    .qr-container {{
      display: flex;
      flex-direction: column;
      align-items: center;
      background: #ffffff;
      padding: 16px;
      border-radius: 8px;
      width: fit-content;
      margin: 16px 0;
    }}
    .qr-container svg {{ display: block; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <div class="title">Virtual Session Manager</div>
        <div class="subtitle">Secure remote phone access via Cloudflare Quick-Tunnel & Face ID / Touch ID</div>
      </div>
      <div>
        <button class="btn btn-danger" onclick="triggerKillswitch()">Kill Switch (Revoke All)</button>
      </div>
    </div>

    <div class="banner">
      <div class="banner-text">
        <strong>Keep this laptop awake:</strong> Sleep prevention is active while virtual sessions exist. Closing the laptop terminates the tunnel.
      </div>
    </div>

    <!-- Create Session -->
    <div class="card">
      <div class="card-title">Create Virtual Session</div>
      <div style="display: grid; grid-template-columns: 2fr 1fr auto; gap: 16px; align-items: flex-end;">
        <div class="form-group" style="margin-bottom:0;">
          <label for="sessName">Device Name</label>
          <input type="text" id="sessName" value="My iPhone" placeholder="e.g. My iPhone 16 Pro">
        </div>
        <div class="form-group" style="margin-bottom:0;">
          <label>Trading Permission</label>
          <div class="checkbox-group">
            <input type="checkbox" id="allowTrade">
            <label for="allowTrade" style="margin-bottom:0; color:#fff;">Allow Trading</label>
          </div>
        </div>
        <div>
          <button class="btn btn-primary" onclick="createSession()">Create Session</button>
        </div>
      </div>

      <div id="newSessionBox" style="display: none; margin-top: 20px; border-top: 1px solid var(--card-border); padding-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 8px;">Scan with Phone Camera or Open Link:</div>
        <div style="display: flex; gap: 24px; align-items: center;">
          <div id="qrPlaceholder" class="qr-container"></div>
          <div>
            <div style="margin-bottom: 8px;">
              <input type="text" id="sessionLinkInput" readonly style="width: 380px;">
              <button class="btn btn-secondary" onclick="copyLink()">Copy</button>
            </div>
            <div style="font-size: 13px; color: var(--text-muted);">
              Pairing Code: <strong id="sessionPairCode" style="font-size: 16px; color: #60a5fa;"></strong>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Active & Pending Sessions List -->
    <div class="card">
      <div class="card-title">Configured Sessions</div>
      <div id="sessionsTableContainer">
        <!-- Rendered by JS -->
      </div>
    </div>

    <!-- Audit Log -->
    <div class="card">
      <div class="card-title">Audit Log</div>
      <div style="max-height: 250px; overflow-y: auto;">
        <table id="auditTable">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Session ID</th>
              <th>Event</th>
              <th>IP / Country</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody id="auditTableBody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    let sessions = {sessions_json};
    let auditLog = {audit_json};

    function renderSessions() {{
      const container = document.getElementById('sessionsTableContainer');
      if (sessions.length === 0) {{
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 14px;">No virtual sessions created yet.</div>';
        return;
      }}
      let html = '<table><thead><tr><th>Name</th><th>State</th><th>Device</th><th>Last Seen</th><th>IP / Country</th><th>Trade</th><th>Actions</th></tr></thead><tbody>';
      for (const s of sessions) {{
        const badgeClass = 'badge badge-' + (s.state === 'PENDING' ? 'pending' : s.state === 'ACTIVE' ? 'active' : s.state === 'RELINK_REQUIRED' ? 'relink' : 'revoked');
        const lastSeen = s.last_seen_at ? new Date(s.last_seen_at * 1000).toLocaleTimeString() : 'Never';
        const loc = (s.last_ip || '—') + (s.last_country ? ' (' + s.last_country + ')' : '');
        html += '<tr>';
        html += '<td><strong>' + s.name + '</strong></td>';
        html += '<td><span class="' + badgeClass + '">' + s.state + '</span></td>';
        html += '<td>' + (s.user_agent ? s.user_agent.substring(0, 30) + '...' : 'Unpaired') + '</td>';
        html += '<td>' + lastSeen + '</td>';
        html += '<td>' + loc + '</td>';
        html += '<td>' + (s.can_trade ? 'Allowed' : 'Read-only') + '</td>';
        html += '<td>';
        if (s.state === 'PENDING') {{
          html += '<button class="btn btn-success" style="padding:4px 8px; font-size:12px; margin-right:4px;" onclick="promptApprove(\\'' + s.id + '\\', \\'' + (s.pair_code || '') + '\\')">Approve (' + s.pair_code + ')</button>';
        }}
        if (s.state === 'RELINK_REQUIRED') {{
          html += '<button class="btn btn-primary" style="padding:4px 8px; font-size:12px; margin-right:4px;" onclick="reconnectSession(\\'' + s.id + '\\')">Reconnect</button>';
        }}
        if (s.state !== 'REVOKED') {{
          html += '<button class="btn btn-danger" style="padding:4px 8px; font-size:12px;" onclick="deleteSession(\\'' + s.id + '\\')">Delete</button>';
        }}
        html += '</td>';
        html += '</tr>';
      }}
      html += '</tbody></table>';
      container.innerHTML = html;
    }}

    function renderAudit() {{
      const tbody = document.getElementById('auditTableBody');
      tbody.innerHTML = '';
      for (const row of auditLog) {{
        const tr = document.createElement('tr');
        const timeStr = new Date(row.ts * 1000).toLocaleTimeString();
        tr.innerHTML = '<td>' + timeStr + '</td><td><code>' + (row.session_id ? row.session_id.substring(0, 8) + '...' : 'global') + '</code></td><td>' + row.event + '</td><td>' + (row.ip || '—') + ' ' + (row.country || '') + '</td><td><small>' + (row.detail || '') + '</small></td>';
        tbody.appendChild(tr);
      }}
    }}

    async function createSession() {{
      const name = document.getElementById('sessName').value.trim() || 'My iPhone';
      const canTrade = document.getElementById('allowTrade').checked;
      try {{
        const res = await fetch('/admin/sessions', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ name, can_trade: canTrade }})
        }});
        if (!res.ok) throw new Error('Create session failed: ' + res.statusText);
        const data = await res.json();
        document.getElementById('sessionLinkInput').value = data.link;
        document.getElementById('sessionPairCode').textContent = data.pair_code;
        document.getElementById('qrPlaceholder').innerHTML = data.qr_svg;
        document.getElementById('newSessionBox').style.display = 'block';
        await refreshData();
      }} catch (err) {{
        alert(err.message);
      }}
    }}

    async function promptApprove(id, defaultCode) {{
      const code = prompt('Enter 6-digit pairing confirmation code shown on phone:', defaultCode);
      if (!code) return;
      try {{
        const res = await fetch('/admin/sessions/' + id + '/approve', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ code }})
        }});
        if (!res.ok) throw new Error('Approve failed: ' + await res.text());
        await refreshData();
      }} catch (err) {{
        alert(err.message);
      }}
    }}

    async function reconnectSession(id) {{
      try {{
        const res = await fetch('/admin/sessions/' + id + '/reconnect', {{ method: 'POST' }});
        if (!res.ok) throw new Error('Reconnect failed');
        const data = await res.json();
        alert('Reconnected! New pairing link: ' + data.link + '\\nPairing Code: ' + data.pair_code);
        await refreshData();
      }} catch (err) {{
        alert(err.message);
      }}
    }}

    async function deleteSession(id) {{
      if (!confirm('Revoke and delete this session?')) return;
      try {{
        const res = await fetch('/admin/sessions/' + id, {{ method: 'DELETE' }});
        if (!res.ok) throw new Error('Delete failed');
        await refreshData();
      }} catch (err) {{
        alert(err.message);
      }}
    }}

    async function triggerKillswitch() {{
      if (!confirm('KILL SWITCH: Stop tunnel, revoke all sessions, and delete all credentials?')) return;
      try {{
        const res = await fetch('/admin/killswitch', {{ method: 'POST' }});
        if (!res.ok) throw new Error('Kill switch failed');
        alert('Kill switch executed. All mobile sessions revoked.');
        await refreshData();
      }} catch (err) {{
        alert(err.message);
      }}
    }}

    async function refreshData() {{
      const [sRes, aRes] = await Promise.all([
        fetch('/admin/sessions'),
        fetch('/admin/audit')
      ]);
      if (sRes.ok) sessions = await sRes.json();
      if (aRes.ok) auditLog = await aRes.json();
      renderSessions();
      renderAudit();
    }}

    function copyLink() {{
      const input = document.getElementById('sessionLinkInput');
      input.select();
      navigator.clipboard.writeText(input.value);
      alert('Copied to clipboard!');
    }}

    renderSessions();
    renderAudit();
    setInterval(refreshData, 3000);
  </script>
</body>
</html>
"""


def render_phone_ui_html(session: dict[str, Any]) -> str:
    """Phone UI: Pairs mobile device with Command Center and launches full mobile Command Center."""
    session_json = json.dumps(session)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="theme-color" content="#080c09">
  <title>Tec-C · Mobile Command Center</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Instrument+Serif:ital@0;1&family=Manrope:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #080c09;
      --card-bg: rgba(18, 26, 20, 0.82);
      --card-border: rgba(205, 227, 138, 0.16);
      --text: #eef2ea;
      --text-muted: #8a9a86;
      --lime: #cde38a;
      --moss: #3a5d38;
      --primary: #3a5d38;
      --success: #6fd39a;
      --danger: #ff6b5e;
      --font: 'Manrope', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --mono: 'JetBrains Mono', monospace;
      --display: 'Bebas Neue', sans-serif;
      --serif: 'Instrument Serif', Georgia, serif;
      --ease: cubic-bezier(.16, 1, .3, 1);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: radial-gradient(ellipse 70% 50% at 20% 0%, rgba(58, 93, 56, 0.38), transparent 75%),
                  radial-gradient(ellipse 60% 40% at 80% 100%, rgba(30, 48, 32, 0.45), transparent 75%),
                  var(--bg);
      color: var(--text);
      font-family: var(--font);
      min-height: 100vh;
      padding: 18px 16px 32px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }}
    .container {{ max-width: 480px; margin: 0 auto; }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 16px;
      margin-bottom: 20px;
      border-bottom: 1px solid rgba(205, 227, 138, 0.1);
    }}
    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      text-decoration: none;
      color: var(--text);
    }}
    .brand-mark {{ width: 28px; height: 28px; color: var(--text); }}
    .brand-title {{
      font-family: var(--display);
      font-size: 24px;
      letter-spacing: .06em;
      line-height: 1;
    }}
    .chip-session {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 5px 12px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 700;
      letter-spacing: .04em;
      text-transform: uppercase;
      background: rgba(205, 227, 138, 0.08);
      border: 1px solid var(--card-border);
      color: var(--lime);
    }}
    .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 8px var(--success); }}
    .dot.offline {{ background: var(--danger); box-shadow: 0 0 8px var(--danger); }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 26px;
      padding: 26px 20px;
      margin-bottom: 18px;
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      box-shadow: 0 24px 50px -15px rgba(0, 0, 0, 0.7);
    }}
    .section-label {{
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .12em;
      text-transform: uppercase;
      color: var(--lime);
      margin-bottom: 6px;
    }}
    .card-title {{
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -.02em;
      margin-bottom: 6px;
      line-height: 1.25;
    }}
    .card-title em {{ font-family: var(--serif); font-style: italic; color: var(--lime); font-weight: 400; }}
    .caption {{ font-size: 13.5px; color: var(--text-muted); line-height: 1.5; }}
    .code-box {{
      font-family: var(--mono);
      font-size: 36px;
      font-weight: 700;
      letter-spacing: 8px;
      color: var(--lime);
      text-align: center;
      padding: 16px 12px;
      background: rgba(0, 0, 0, 0.45);
      border: 1px solid rgba(205, 227, 138, 0.28);
      border-radius: 18px;
      margin: 20px 0;
      box-shadow: inset 0 2px 10px rgba(0,0,0,.5), 0 0 24px rgba(205,227,138,0.15);
      text-shadow: 0 0 12px rgba(205, 227, 138, 0.4);
    }}
    .btn {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      padding: 15px 18px;
      border-radius: 14px;
      border: none;
      font-family: var(--font);
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      text-align: center;
      text-decoration: none;
      transition: all .3s var(--ease);
    }}
    .btn-primary {{
      background: linear-gradient(135deg, #3a5d38, #253a24);
      color: #fff;
      border: 1px solid rgba(205, 227, 138, 0.45);
      box-shadow: 0 12px 28px -6px rgba(58, 93, 56, 0.55);
    }}
    .btn-primary:active {{ transform: scale(0.98); }}
    .btn-white {{
      background: var(--text);
      color: #0c120e;
      border: none;
      box-shadow: 0 12px 24px -6px rgba(255, 255, 255, 0.25);
    }}
    .btn-danger {{ background: rgba(255, 107, 94, 0.15); color: var(--danger); border: 1px solid rgba(255, 107, 94, 0.35); }}
    .divider {{
      display: flex;
      align-items: center;
      gap: 14px;
      margin: 22px 0 16px;
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .1em;
      text-transform: uppercase;
    }}
    .divider::before, .divider::after {{
      content: "";
      flex: 1;
      height: 1px;
      background: rgba(205, 227, 138, 0.12);
    }}
    .pin-row {{ display: flex; gap: 10px; }}
    .pin-input {{
      flex: 1;
      padding: 13px 14px;
      border-radius: 14px;
      border: 1px solid var(--card-border);
      background: rgba(0, 0, 0, 0.35);
      color: #fff;
      font-size: 17px;
      text-align: center;
      letter-spacing: 5px;
      font-family: var(--mono);
      outline: none;
      transition: border-color .3s;
    }}
    .pin-input:focus {{ border-color: rgba(205, 227, 138, 0.6); box-shadow: 0 0 0 3px rgba(205, 227, 138, 0.1); }}
    .pulse-ring {{
      width: 72px;
      height: 72px;
      border-radius: 50%;
      background: rgba(205, 227, 138, 0.08);
      border: 2px solid var(--lime);
      display: grid;
      place-items: center;
      margin: 14px auto 20px;
      position: relative;
      animation: pulse-ring 2s infinite var(--ease);
    }}
    .pulse-ring i {{ width: 22px; height: 22px; border-radius: 50%; background: var(--lime); box-shadow: 0 0 16px var(--lime); }}
    @keyframes pulse-ring {{
      0% {{ box-shadow: 0 0 0 0 rgba(205, 227, 138, 0.4); }}
      70% {{ box-shadow: 0 0 0 20px rgba(205, 227, 138, 0); }}
      100% {{ box-shadow: 0 0 0 0 rgba(205, 227, 138, 0); }}
    }}
    .hint-box {{
      font-size: 13px;
      padding: 12px 14px;
      border-radius: 12px;
      margin-top: 14px;
      text-align: center;
      line-height: 1.45;
    }}
    .hint-amber {{ background: rgba(232, 166, 75, 0.12); border: 1px solid rgba(232, 166, 75, 0.35); color: #fbd38d; }}
    .hint-red {{ background: rgba(255, 107, 94, 0.12); border: 1px solid rgba(255, 107, 94, 0.35); color: #fca5a5; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">
        <svg viewBox="0 0 40 40" class="brand-mark" aria-hidden="true">
          <path d="M6 14 Q20 2 34 14 Q30 28 20 34 Q10 28 6 14Z" fill="none" stroke="currentColor" stroke-width="2.2"/>
          <ellipse cx="14" cy="17" rx="3.2" ry="2" fill="#E8A64B"/><ellipse cx="26" cy="17" rx="3.2" ry="2" fill="#E8A64B"/>
        </svg>
        <span class="brand-title">Tec-C</span>
      </div>
      <div class="chip-session">
        <span id="connDot" class="dot"></span>
        <span>Mobile Session</span>
      </div>
    </div>

    <div id="contentArea"></div>
  </div>

  <script>
    const session = {session_json};

    function b64urlToBuffer(b64) {{
      const bin = atob(b64.replace(/-/g, '+').replace(/_/g, '/'));
      const buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      return buf.buffer;
    }}

    function bufferToB64url(buf) {{
      const bytes = new Uint8Array(buf);
      let bin = '';
      for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
      return btoa(bin).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
    }}

    function launchCommandCenter() {{
      try {{
        localStorage.setItem('tecc_api', location.origin);
      }} catch (e) {{}}
      const area = document.getElementById('contentArea');
      if (area) {{
        area.innerHTML = `
          <div class="card" style="text-align: center; padding: 36px 20px;">
            <div class="pulse-ring"><i></i></div>
            <div class="section-label">AUTHORIZED OWNER ACCESS</div>
            <h2 class="card-title" style="margin-top: 8px;">Pairing <em>Confirmed</em></h2>
            <p class="caption" style="margin-bottom: 24px;">Launching your full Command Center with real-time portfolio, review, opportunities, and biometric controls…</p>
            <a href="/app.html?api=${{encodeURIComponent(location.origin)}}#home" class="btn btn-white">Open Command Center Now</a>
          </div>
        `;
      }}
      setTimeout(() => {{
        location.replace('/app.html?api=' + encodeURIComponent(location.origin) + '#home');
      }}, 500);
    }}

    async function init() {{
      if (session.state === 'REVOKED') {{
        renderRevoked('This virtual session was revoked. Generate a new session link from your laptop Command Center.');
        return;
      }}
      if (session.state === 'RELINK_REQUIRED') {{
        renderRevoked('The tunnel connection was reconnected. Click Reconnect on your laptop to get a fresh link.');
        return;
      }}
      if (session.state === 'ACTIVE') {{
        launchCommandCenter();
        return;
      }}
      if (session.state === 'PENDING' && session.has_credential) {{
        renderAwaitingApproval();
        return;
      }}
      renderPairing();
    }}

    function renderPairing(hintText) {{
      const area = document.getElementById('contentArea');
      const hintHtml = hintText
        ? `<div class="hint-box hint-amber">${{hintText}}</div>`
        : '';

      area.innerHTML = `
        <div class="card">
          <div class="section-label">DEVICE PAIRING</div>
          <h1 class="card-title">Pair with Laptop &amp; <em>Command Center</em></h1>
          <p class="caption">Check that this 6-digit confirmation code matches the code on your laptop screen:</p>
          <div class="code-box">${{session.pair_code}}</div>

          <button id="btnBio" class="btn btn-primary" onclick="registerBiometric()">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0 0-10 10v2a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-4a6 6 0 1 1 12 0v4a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-2a10 10 0 0 0-10-10z"/><circle cx="9" cy="11" r="1"/><circle cx="15" cy="11" r="1"/></svg>
            <span>Authenticate with Face ID / Fingerprint</span>
          </button>

          <div class="divider"><span>OR AUTHENTICATE WITH PIN</span></div>

          <div class="pin-row">
            <input type="password" id="pinInput" class="pin-input" maxlength="16" inputmode="numeric" placeholder="Enter Security PIN"
              onkeydown="if(event.key==='Enter') authenticateWithPin()">
            <button class="btn btn-white" style="width: auto; padding: 12px 22px;" onclick="authenticateWithPin()">Verify</button>
          </div>
          ${{hintHtml}}
        </div>
      `;
    }}

    async function authenticateWithPin() {{
      const pin = (document.getElementById('pinInput')?.value || '').trim();
      if (!pin) {{
        renderPairing('Please enter your Security PIN (configured in Settings) or the 6-digit code above.');
        return;
      }}
      try {{
        const res = await fetch('/webauthn/pin/verify', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ session_id: session.id, pin: pin }})
        }});
        const data = await res.json().catch(() => ({{}}));
        if (!res.ok) throw new Error(data.detail || 'PIN verification failed');
        renderAwaitingApproval();
      }} catch (err) {{
        renderPairing(err.message);
      }}
    }}

    function renderAwaitingApproval() {{
      const area = document.getElementById('contentArea');
      area.innerHTML = `
        <div class="card" style="text-align: center; padding: 32px 20px;">
          <div class="pulse-ring"><i></i></div>
          <div class="section-label">CREDENTIALS REGISTERED</div>
          <h2 class="card-title">Waiting for <em>Laptop Approval</em></h2>
          <p class="caption" style="margin-bottom: 16px;">
            Credentials registered! Click <strong>Approve phone</strong> on your laptop screen to unlock full access.
          </p>
          <div class="code-box" style="margin: 12px 0 20px;">${{session.pair_code}}</div>
          <p class="caption" style="font-size: 12px;">Waiting for confirmation signal from Command Center…</p>
        </div>
      `;

      // Poll every 1.2s until approved
      const poll = setInterval(async () => {{
        try {{
          const res = await fetch('/s/' + session.id + '/status');
          if (res.ok) {{
            const data = await res.json();
            if (data.state === 'ACTIVE') {{
              clearInterval(poll);
              launchCommandCenter();
              return;
            }}
          }}
          // Fallback check on dashboard API
          const dash = await fetch('/api/dashboard');
          if (dash.ok) {{
            clearInterval(poll);
            launchCommandCenter();
            return;
          }}
        }} catch (e) {{}}
      }}, 1200);
    }}

    async function registerBiometric() {{
      try {{
        const optRes = await fetch('/webauthn/register/options', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ session_id: session.id }})
        }});
        if (!optRes.ok) throw new Error('Failed to get registration options');
        const options = await optRes.json();
        
        options.challenge = b64urlToBuffer(options.challenge);
        options.user.id = b64urlToBuffer(options.user.id);
        
        const cred = await navigator.credentials.create({{ publicKey: options }});
        if (!cred) throw new Error('Biometric verification cancelled or unavailable');
        
        const regPayload = {{
          session_id: session.id,
          credential_id: bufferToB64url(cred.rawId),
          authenticator_data: bufferToB64url(cred.response.authenticatorData),
          client_data_json: bufferToB64url(cred.response.clientDataJSON),
          attestation_object: bufferToB64url(cred.response.attestationObject)
        }};
        
        const vRes = await fetch('/webauthn/register/verify', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(regPayload)
        }});
        if (!vRes.ok) throw new Error('Passkey registration failed');
        renderAwaitingApproval();
      }} catch (err) {{
        renderPairing('Biometric prompt cancelled or unavailable on this device. You can enter your Security PIN or the 6-digit code above to authenticate.');
      }}
    }}

    function renderRevoked(msg) {{
      const area = document.getElementById('contentArea');
      area.innerHTML = `
        <div class="card" style="text-align: center; padding: 36px 20px;">
          <div class="section-label" style="color: var(--danger);">DISCONNECTED</div>
          <h2 class="card-title" style="margin-top: 8px;">Session <em>Revoked</em></h2>
          <p class="caption" style="margin-top: 8px;">${{msg}}</p>
        </div>
      `;
    }}

    init();
  </script>
</body>
</html>
"""
