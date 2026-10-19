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
    """Section 8.5: Phone UI (Pairing page or Read-only dashboard with WebSocket updates & Disconnect)."""
    session_json = json.dumps(session)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="theme-color" content="#090d16">
  <title>Tec-C PegGuard</title>
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: #1f2937;
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --primary: #3b82f6;
      --success: #10b981;
      --danger: #ef4444;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      padding: 16px;
      line-height: 1.5;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 16px;
    }}
    .title {{ font-size: 18px; font-weight: 700; }}
    .status-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--success);
      display: inline-block;
      margin-right: 6px;
    }}
    .status-dot.offline {{ background: var(--danger); }}
    .offline-banner {{
      display: none;
      background: #7f1d1d;
      color: #fecaca;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 13px;
      text-align: center;
      margin-bottom: 12px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    .btn {{
      display: block;
      width: 100%;
      padding: 14px;
      border-radius: 10px;
      border: none;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
      text-align: center;
    }}
    .btn-primary {{ background: var(--primary); color: #fff; }}
    .btn-danger {{ background: var(--danger); color: #fff; }}
    .code-box {{
      font-family: monospace;
      font-size: 32px;
      letter-spacing: 6px;
      color: #60a5fa;
      text-align: center;
      padding: 16px;
      background: #172554;
      border-radius: 8px;
      margin: 16px 0;
    }}
    .metric-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .metric-box {{
      background: #1e293b;
      padding: 12px;
      border-radius: 8px;
    }}
    .metric-label {{ font-size: 12px; color: var(--text-muted); }}
    .metric-val {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
  </style>
</head>
<body>
  <div class="header">
    <div style="display: flex; align-items: center;">
      <span id="connDot" class="status-dot"></span>
      <span class="title">PegGuard Mobile</span>
    </div>
    <div>
      <button id="disconnectBtn" class="btn btn-danger" style="display: none; width: auto; padding: 6px 12px; font-size: 13px;" onclick="disconnect()">Disconnect</button>
    </div>
  </div>

  <div id="offlineBanner" class="offline-banner">Laptop offline. Reconnecting…</div>

  <div id="contentArea"></div>

  <script>
    const session = {session_json};
    let ws = null;

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

    async function init() {{
      if (session.state === 'REVOKED') {{
        renderRevoked('Session ended. Ask for a new link on your laptop.');
        return;
      }}
      if (session.state === 'RELINK_REQUIRED') {{
        renderRevoked('Tunnel URL changed. Click Reconnect on your laptop to get a fresh link.');
        return;
      }}
      if (session.state === 'PENDING' && !session.has_credential) {{
        renderPairing();
        return;
      }}
      // Active or awaiting laptop approval
      if (session.state === 'PENDING' && session.has_credential) {{
        renderAwaitingApproval();
        return;
      }}
      renderDashboard();
      connectWebSocket();
    }}

    function renderPairing(hint) {{
      const area = document.getElementById('contentArea');
      const hintHtml = hint
        ? '<div id="pinHint" style="font-size: 13px; color: #fbbf24; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; padding: 10px; margin-top: 12px; text-align: center;">' + hint + '</div>'
        : '<div id="pinHint" style="font-size: 12px; color: var(--text-muted); margin-top: 10px; text-align: center;">Enter your Security PIN (set in Settings) or the 6-digit code above.</div>';

      area.innerHTML = `
        <div class="card">
          <div style="font-weight: 600; font-size: 18px; margin-bottom: 8px;">Pair with Laptop</div>
          <div style="font-size: 14px; color: var(--text-muted);">Confirm this 6-digit code matches the code on your laptop screen:</div>
          <div class="code-box">${{session.pair_code}}</div>

          <button id="btnBio" class="btn btn-primary" onclick="registerBiometric()">Authenticate with Face ID / Fingerprint</button>

          <div style="text-align: center; margin: 18px 0 12px; font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.5px;">
            — Or authenticate with PIN —
          </div>

          <div style="display: flex; gap: 8px;">
            <input type="password" id="pinInput" maxlength="16" inputmode="numeric" placeholder="Enter PIN or pairing code"
              style="flex: 1; padding: 12px; border-radius: 8px; border: 1px solid var(--card-border); background: #1e293b; color: #fff; font-size: 16px; text-align: center; letter-spacing: 4px;"
              onkeydown="if(event.key==='Enter') authenticateWithPin()">
            <button class="btn btn-primary" style="width: auto; padding: 12px 20px;" onclick="authenticateWithPin()">Verify</button>
          </div>
          ` + hintHtml + `
        </div>
      `;
    }}

    async function authenticateWithPin() {{
      const pin = (document.getElementById('pinInput')?.value || '').trim();
      const hint = document.getElementById('pinHint');
      if (!pin) {{
        if (hint) {{
          hint.style.color = '#f87171';
          hint.textContent = 'Please enter your Security PIN or the 6-digit pairing code.';
        }}
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
        if (hint) {{
          hint.style.color = '#f87171';
          hint.textContent = err.message;
        }} else {{
          alert(err.message);
        }}
      }}
    }}

    function renderAwaitingApproval() {{
      const area = document.getElementById('contentArea');
      area.innerHTML = `
        <div class="card" style="text-align: center;">
          <div style="font-weight: 600; font-size: 18px; margin-bottom: 8px;">Waiting for Laptop Approval</div>
          <div style="font-size: 14px; color: var(--text-muted); margin-bottom: 16px;">
            Credentials registered! Click <strong>Approve</strong> on your laptop to complete setup.
          </div>
          <div class="code-box">${{session.pair_code}}</div>
        </div>
      `;
      // Poll until approved
      const poll = setInterval(async () => {{
        const res = await fetch('/api/dashboard');
        if (res.ok) {{
          clearInterval(poll);
          renderDashboard();
          connectWebSocket();
        }}
      }}, 1500);
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
        
        // Convert to WebAuthn browser format
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
        renderPairing('Biometric prompt cancelled or device PIN missing. You can enter your Security PIN or the 6-digit code above to authenticate.');
      }}
    }}

    function renderDashboard() {{
      document.getElementById('disconnectBtn').style.display = 'block';
      const area = document.getElementById('contentArea');
      area.innerHTML = `
        <div class="card">
          <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 4px;">PegGuard Engine Status</div>
          <div style="font-size: 20px; font-weight: 700; color: #34d399;">Autonomous Scanner Active</div>
        </div>
        <div class="card">
          <div class="metric-grid">
            <div class="metric-box">
              <div class="metric-label">Monitored Assets</div>
              <div id="mAssets" class="metric-val">25</div>
            </div>
            <div class="metric-box">
              <div class="metric-label">Depegs Found</div>
              <div id="mDepegs" class="metric-val">0</div>
            </div>
          </div>
        </div>
        <div class="card">
          <div style="font-size: 14px; font-weight: 600; margin-bottom: 8px;">Live Signals</div>
          <div id="signalList" style="font-size: 13px; color: var(--text-muted);">Monitoring Arbitrum & Ethereum L1 liquidity pools...</div>
        </div>
        ${{session.can_trade ? '<button class="btn btn-primary" onclick="triggerTrade()">Execute Step-Up Trade Action</button>' : ''}}
      `;
    }}

    function renderRevoked(msg) {{
      document.getElementById('disconnectBtn').style.display = 'none';
      const area = document.getElementById('contentArea');
      area.innerHTML = `
        <div class="card" style="text-align: center; padding: 32px 16px;">
          <div style="font-size: 20px; font-weight: 700; color: #f87171; margin-bottom: 8px;">Disconnected</div>
          <div style="font-size: 14px; color: var(--text-muted);">${{msg}}</div>
        </div>
      `;
    }}

    async function disconnect() {{
      if (!confirm('Disconnect this phone? You will need a new link from your laptop to reconnect.')) return;
      try {{
        await fetch('/api/disconnect', {{ method: 'POST' }});
      }} catch (e) {{}}
      renderRevoked('Disconnected. Ask for a new link on your laptop.');
    }}

    function connectWebSocket() {{
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(proto + '//' + location.host + '/ws');
      ws.onopen = () => {{
        document.getElementById('connDot').classList.remove('offline');
        document.getElementById('offlineBanner').style.display = 'none';
      }};
      ws.onclose = () => {{
        document.getElementById('connDot').classList.add('offline');
        document.getElementById('offlineBanner').style.display = 'block';
        setTimeout(connectWebSocket, 3000);
      }};
      ws.onmessage = (evt) => {{
        try {{
          const data = JSON.parse(evt.data);
          if (data.type === 'dashboard' && data.signals) {{
            document.getElementById('signalList').innerHTML = data.signals.map(s => '<div>• ' + s + '</div>').join('');
          }}
        }} catch(e) {{}}
      }};
    }}

    init();
  </script>
</body>
</html>
"""
