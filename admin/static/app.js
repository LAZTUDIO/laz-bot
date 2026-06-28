'use strict';

let currentSession = null;
let vuWs = null;
let templates = [];
let editingCategory = '';
let editingName = '';

// ── DOM Ready ──
document.addEventListener('DOMContentLoaded', () => {
  // 加载超时兜底——5秒后无论如何隐藏 spinner
  const timeoutId = setTimeout(() => {
    const cards = document.getElementById('dashboardCards');
    if (cards && cards.querySelector('.loading')) {
      cards.innerHTML = '<div class="card"><h3>⚠️ 加载超时</h3><p>API 响应超时，请检查服务状态。<br><button onclick="location.reload()" style="margin-top:8px">🔄 重试</button></p></div>';
    }
  }, 5000);

  loadDashboard().then(() => clearTimeout(timeoutId)).catch(() => clearTimeout(timeoutId));
  checkHealth();
  setInterval(checkHealth, 15000);
});

// ── Toast ──
function toast(msg, type = 'info') {
  let c = document.querySelector('.toast-container');
  if (!c) { c = document.createElement('div'); c.className = 'toast-container'; document.body.appendChild(c); }
  const t = document.createElement('div'); t.className = `toast ${type}`; t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 3000);
}

// ── Page Switch ──
function switchPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
  document.getElementById(`page-${name}`).classList.add('active');
  document.querySelector(`nav a[data-page="${name}"]`).classList.add('active');
  switch(name) {
    case 'chat': loadSessions(); updateContextBar(); break;
    case 'audio': loadAudioConfig(); initAudioPage(); break;
    case 'models': loadModelPage(); break;
    case 'memory': loadMemoryStats(); break;
    case 'settings': loadGeneralConfig(); break;
  }
}

// ── API Helper ──
async function api(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);
  try {
    const resp = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      signal: controller.signal,
      ...options
    });
    clearTimeout(timeoutId);
    if (!resp.ok) {
      const body = await resp.text();
      let msg = body;
      try { msg = JSON.parse(body).detail || body; } catch(e) {}
      throw new Error(msg.slice(0, 100));
    }
    return resp.json();
  } catch(e) {
    clearTimeout(timeoutId);
    if (e.name === 'AbortError') throw new Error('请求超时');
    throw e;
  }
}

// ── Health Check ──
async function checkHealth() {
  try {
    const h = await api('/health');
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    dot.className = h.status === 'ok' ? 'dot green' : 'dot yellow';
    txt.textContent = h.status === 'ok' ? '系统运行中' : '初始化中...';
  } catch(e) {
    document.getElementById('statusDot').className = 'dot red';
    document.getElementById('statusText').textContent = '连接失败';
  }
}

// ════════════════════════════════════════
//  DASHBOARD
// ════════════════════════════════════════

async function loadDashboard() {
  const container = document.getElementById('dashboardCards');
  try {
    const [health, system, config, personality] = await Promise.all([
      api('/health'), api('/api/system'), api('/api/config'),
      api('/api/personality').catch(() => null)
    ]);
    container.innerHTML = `
      <div class="card">
        <h3>服务状态</h3>
        <div class="stat-grid">
          <div class="stat-item">
            <div class="stat-value" style="color:${health.status === 'ok' ? '#00d4aa' : '#ffd93d'}">
              ${health.status === 'ok' ? '✅ 运行中' : '⏳ 初始化'}
            </div>
            <div class="stat-label">LAZ-Bot API</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">${health.memory_count}</div>
            <div class="stat-label">长期记忆</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">${health.graph.nodes || 0}</div>
            <div class="stat-label">脑图节点</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">${health.sessions.length}</div>
            <div class="stat-label">活跃会话</div>
          </div>
        </div>
      </div>
      <div class="card" id="systemCard">
        <h3>系统资源 <span style="font-size:10px;color:var(--text2);font-weight:normal">实时</span></h3>
        <div class="stat-grid" id="systemStats">
          ${renderSystemStats(system)}
        </div>
      </div>
      <div class="card">
        <h3>模型信息</h3>
        <div class="stat-row"><span class="label">LLM</span><span class="value">${getActiveModelLabel(config, 'llm')}</span></div>
        <div class="stat-row"><span class="label">STT</span><span class="value">${getActiveModelLabel(config, 'stt')}</span></div>
        <div class="stat-row"><span class="label">TTS</span><span class="value">${getActiveModelLabel(config, 'tts')}</span></div>
        <div class="stat-row"><span class="label">Embedding</span><span class="value">${getActiveModelLabel(config, 'embedding')}</span></div>
      </div>
      <div class="card">
        <h3>快速操作</h3>
        <div style="display:flex;flex-direction:column;gap:8px">
          <button onclick="switchPage('chat')">💬 打开聊天</button>
          <button onclick="switchPage('models')">🧠 配置模型</button>
          <button onclick="switchPage('audio')">🎤 配置音频</button>
          <button onclick="switchPage('settings')">⚙️ 系统设置</button>
        </div>
      </div>
      ${personality ? `
      <div class="card">
        <h3>🧠 当前人格</h3>
        <div style="font-size:24px;margin:4px 0">${personality.personality.emoji} ${personality.personality.name}</div>
        <div style="font-size:11px;color:var(--accent);font-family:monospace">${personality.personality.current} · ${personality.personality.pattern}</div>
        <div style="font-size:12px;color:var(--text2);margin-top:4px">${personality.personality.description}</div>
        <div class="stat-row"><span class="label">情绪</span><span class="value">${personality.emotional_state.label}</span></div>
        <div class="stat-row"><span class="label">演化</span><span class="value">${personality.personality.evolution_enabled ? '✅ 开启' : '⏸ 关闭'}</span></div>
        <button style="margin-top:8px" onclick="switchPage('personality')">🧠 切换人格</button>
      </div>` : ''}
    `;
    document.getElementById('appVersion').textContent = `v${config.app?.version || '0.1'}`;

    // 项目介绍
    renderProjectIntro(config);
  } catch(e) {
    container.innerHTML = '<div class="card"><h3>⚠️ 加载失败</h3><p>无法连接 API</p></div>';
  }

  // Start real-time refresh for system resources
  startDashboardRefresh();
}

let dashboardRefreshTimer = null;
function startDashboardRefresh() {
  if (dashboardRefreshTimer) clearInterval(dashboardRefreshTimer);
  dashboardRefreshTimer = setInterval(refreshSystemCard, 3000);
}

async function refreshSystemCard() {
  try {
    const system = await api('/api/system');
    const statsDiv = document.getElementById('systemStats');
    if (statsDiv) {
      statsDiv.innerHTML = renderSystemStats(system);
    }
  } catch(e) { /* ignore */ }
}

function renderProjectIntro(config) {
  const container = document.getElementById('projectIntro');
  if (!container) return;
  const ver = config?.app?.version || '0.5.0';
  container.innerHTML = `
    <div class="card" style="grid-column: 1 / -1">
      <h3>🚀 关于 LAZ-Bot v${ver}</h3>
      <p style="font-size:13px;line-height:1.7;color:var(--text2);margin:8px 0">
        <strong>LAZ-Bot</strong> 不是一个普通聊天机器人——它是一个<strong>有性格的树莓派融合智能体</strong>。
        基于 SBTI 人格体系（27 种人格类型 × 15 维度评分 × PAD 三维情绪模型），
        LAZ-Bot 不只是"回答问题"，而是<strong>以某种人格的身份与你对话</strong>。
      </p>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:12px">
        <div style="background:var(--bg);border-radius:8px;padding:12px">
          <div style="font-size:16px">🧬</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0">SBTI 人格引擎</div>
          <div style="font-size:11px;color:var(--text2)">27种人格 · 15维度 · PAD情绪</div>
        </div>
        <div style="background:var(--bg);border-radius:8px;padding:12px">
          <div style="font-size:16px">🧠</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0">三层记忆融合</div>
          <div style="font-size:11px;color:var(--text2)">短期+长期+脑图 · 艾宾浩斯遗忘</div>
        </div>
        <div style="background:var(--bg);border-radius:8px;padding:12px">
          <div style="font-size:16px">🎤</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0">语音交互</div>
          <div style="font-size:11px;color:var(--text2)">唤醒词 · VAD · STT · TTS</div>
        </div>
        <div style="background:var(--bg);border-radius:8px;padding:12px">
          <div style="font-size:16px">🔧</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0">工具执行引擎</div>
          <div style="font-size:11px;color:var(--text2)">AST安全沙箱 · 3个内置工具</div>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text2);margin-top:12px;text-align:center">
        🍓 运行在树莓派 5 · Open WebUI 中转 · 硅基流动云端 API · 
        <a href="https://github.com/laztudio/laz-bot" target="_blank" style="color:var(--accent)">GitHub</a>
      </div>
    </div>
  `;
}

function renderSystemStats(system) {
  const used = formatBytes(system.memory?.used || 0);
  const total = formatBytes(system.memory?.total || 0);
  const cpuPct = Math.round(system.cpu?.percent || 0);
  const memPct = Math.round(system.memory?.percent || 0);
  const diskPct = Math.round(system.disk?.percent || 0);
  return `
    <div class="stat-item">
      <div class="stat-value">${cpuPct}%</div>
      <div class="stat-label">CPU</div>
      <div style="height:3px;background:#222;border-radius:2px;margin-top:4px">
        <div style="height:100%;width:${cpuPct}%;background:${cpuPct>80?'#f44':cpuPct>50?'#fa0':'#0f0'};border-radius:2px;transition:width 0.5s"></div>
      </div>
    </div>
    <div class="stat-item">
      <div class="stat-value">${used}</div>
      <div class="stat-label">内存 /${total}</div>
      <div style="height:3px;background:#222;border-radius:2px;margin-top:4px">
        <div style="height:100%;width:${memPct}%;background:${memPct>80?'#f44':memPct>50?'#fa0':'#0f0'};border-radius:2px;transition:width 0.5s"></div>
      </div>
    </div>
    <div class="stat-item">
      <div class="stat-value">${diskPct}%</div>
      <div class="stat-label">磁盘</div>
      <div style="height:3px;background:#222;border-radius:2px;margin-top:4px">
        <div style="height:100%;width:${diskPct}%;background:${diskPct>80?'#f44':diskPct>50?'#fa0':'#0f0'};border-radius:2px;transition:width 0.5s"></div>
      </div>
    </div>
  `;
}

function formatBytes(b) {
  if (!b) return '0B';
  const u = ['B','KB','MB','GB']; let i=0;
  while (b >= 1024 && i < u.length-1) { b/=1024; i++; }
  return `${Math.round(b)}${u[i]}`;
}

function getActiveModelLabel(config, category) {
  const cat = config?.models?.[category];
  if (!cat || !cat.entries) return '未配置';
  const active = cat.active;
  const entry = cat.entries.find(e => e.name === active);
  return entry ? (entry.label || entry.name) + ' ✅' : '未配置';
}

// ════════════════════════════════════════
//  PERSONALITY
// ════════════════════════════════════════

async function loadPersonality() {
  const container = document.getElementById('personalityContent');
  if (!container) return;
  container.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const data = await api('/api/personality');
    const p = data.personality;
    const e = data.emotional_state;
    const pList = Object.entries(data.personalities || {});

    let html = `
      <div class="cards" style="margin-bottom:16px">
        <div class="card" style="text-align:center">
          <div style="font-size:48px">${p.emoji}</div>
          <h3>${p.name}</h3>
          <div style="font-size:12px;color:var(--text2);margin-bottom:4px">${p.current}</div>
          <div style="font-size:12px;color:var(--accent);font-family:monospace">${p.pattern || ''}</div>
          <div style="font-size:13px;color:var(--text2);margin:8px 0">${p.description}</div>
          <div style="font-size:12px;color:var(--text);background:var(--bg);border-radius:8px;padding:8px 12px;margin:8px auto;max-width:500px">
            ${escapeHtml(p.dim_short || '')}
          </div>

          <div style="display:flex;gap:16px;justify-content:center;margin:12px 0;flex-wrap:wrap">
            <div style="background:var(--bg);border-radius:8px;padding:8px 16px;text-align:center">
              <div style="font-size:11px;color:var(--text2)">愉悦 P</div>
              <div style="font-size:18px;font-weight:bold;color:${e.pleasure > 0 ? '#34d399' : '#f87171'}">${e.pleasure.toFixed(2)}</div>
            </div>
            <div style="background:var(--bg);border-radius:8px;padding:8px 16px;text-align:center">
              <div style="font-size:11px;color:var(--text2)">唤醒 A</div>
              <div style="font-size:18px;font-weight:bold;color:${e.arousal > 0 ? '#facc15' : '#60a5fa'}">${e.arousal.toFixed(2)}</div>
            </div>
            <div style="background:var(--bg);border-radius:8px;padding:8px 16px;text-align:center">
              <div style="font-size:11px;color:var(--text2)">支配 D</div>
              <div style="font-size:18px;font-weight:bold;color:${e.dominance > 0 ? '#a78bfa' : '#f472b6'}">${e.dominance.toFixed(2)}</div>
            </div>
          </div>
          <div style="font-size:13px;color:var(--text2)">情绪状态: <strong>${e.label}</strong> (强度 ${e.magnitude})</div>

          <div class="form-group" style="margin-top:12px">
            <label>切换人格</label>
            <select id="personalitySelect" onchange="switchPersonality(this.value)" style="font-size:13px">
              ${pList.map(([code, t]) =>
                `<option value="${code}" ${code === p.current ? 'selected' : ''}>${t.emoji} ${t.name} (${code})</option>`
              ).join('')}
            </select>
          </div>

          <div class="form-group" style="margin-top:8px">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
              <input type="checkbox" id="evolutionToggle" ${p.evolution_enabled ? 'checked' : ''}
                     onchange="toggleEvolution(this.checked)">
              自动人格演化
            </label>
          </div>

          <div style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px">
            <h4 style="font-size:13px;margin:0 0 8px 0">人格影响开关</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;text-align:left">
              ${Object.entries(p.impacts || {}).map(([key, val]) => `
                <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                  <input type="checkbox" ${val ? 'checked' : ''}
                         onchange="toggleImpact('${key}', this.checked)">
                  ${IMPACT_LABELS[key] || key}
                </label>
              `).join('')}
            </div>
          </div>
        </div>
      </div>

      <div class="cards">
        <div class="card">
          <h3>所有人格 (${pList.length} 种)</h3>
          <div class="personality-grid">
            ${pList.map(([code, t]) => `
              <div class="personality-card ${code === p.current ? 'active' : ''}"
                   onclick="switchPersonality('${code}')">
                <div class="pc-top">
                  <span class="pc-emoji">${t.emoji}</span>
                  <span class="pc-name">${t.name}</span>
                  <span class="pc-code">${code}</span>
                </div>
                <div class="pc-pattern">${t.pattern}</div>
                <div class="pc-desc">${t.description}</div>
                <div class="pc-dims">${escapeHtml(t.dim_short || '')}</div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;

    container.innerHTML = html;
  } catch(e) {
    container.innerHTML = `<div class="error" style="padding:20px;text-align:center;color:var(--warn)">
      ❌ 加载人格信息失败: ${e.message}</div>`;
  }
}

async function switchPersonality(code) {
  try {
    await api('/api/personality/switch', {
      method: 'POST',
      body: JSON.stringify({ code })
    });
    toast(`✅ 已切换至 ${code}`, 'success');
    loadPersonality();
    loadDashboard();
  } catch(e) {
    toast('切换失败: ' + e.message, 'error');
  }
}

async function toggleEvolution(enabled) {
  try {
    await api('/api/personality/evolution', {
      method: 'POST',
      body: JSON.stringify({ enabled, rate: 0.02 })
    });
    toast(enabled ? '✅ 人格演化已开启' : '⏸ 人格演化已暂停', 'success');
  } catch(e) {
    toast('设置失败: ' + e.message, 'error');
  }
}

const IMPACT_LABELS = {
  llm_prompt: '🧠 人格注入提示',
  pad_baseline: '💖 情绪基线偏移',
  hebbian_lr: '🔗 概念强化速度',
  importance_bias: '⚖️ 记忆重要性偏置',
  reply_length: '📝 回复长度',
  memory_decay: '⏳ 遗忘速度',
  warmth_tone: '🌡 语气温度',
  tts_speed: '🎙 语音语速',
};

async function toggleImpact(key, enabled) {
  try {
    const data = await api('/api/personality/impacts', {
      method: 'POST',
      body: JSON.stringify({ impacts: { [key]: enabled } })
    });
    const label = IMPACT_LABELS[key] || key;
    toast(enabled ? `✅ ${label} 已开启` : `⏸ ${label} 已关闭`, 'success');
    // Refresh to show new PAD/forgetting values
    loadPersonality();
  } catch(e) {
    toast('设置失败: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════
//  CHAT
// ════════════════════════════════════════

async function loadSessions() {
  try {
    const data = await api('/api/sessions');
    const list = document.getElementById('sessionList');
    const msgs = document.getElementById('chatMessages');
    if (!data.sessions || data.sessions.length === 0) {
      list.innerHTML = '<div class="session-empty">暂无会话，点击上方新建</div>';
      msgs.innerHTML = '<div class="msg system">💬 点击"新建对话"开始聊天</div>';
      currentSession = null;
      return;
    }
    list.innerHTML = data.sessions.map(s => {
      const date = new Date((s.last_active || s.created_at) * 1000);
      const dateStr = `${date.getMonth()+1}/${date.getDate()} ${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}`;
      const isActive = s.id === currentSession;
      return `
        <div class="session-item ${isActive ? 'active' : ''}" onclick="selectSession('${s.id}')">
          <div class="session-title">${escapeHtml(s.title || '新对话')}</div>
          <div class="session-meta">
            <span>${s.msg_count || 0} 条</span>
            <span>${dateStr}</span>
          </div>
          <button class="session-del" onclick="event.stopPropagation();deleteSession('${s.id}')" title="删除">✕</button>
        </div>`;
    }).join('');

    // If no current session, auto-select first
    if (!currentSession) selectSession(data.sessions[0].id);
    updateContextBar();
  } catch(e) { toast('加载会话失败', 'error'); }
}

async function selectSession(id) {
  currentSession = id;
  // Update active visual
  document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
  const items = document.querySelectorAll('.session-item');
  for (const el of items) {
    if (el.getAttribute('onclick')?.includes(`'${id}'`)) {
      el.classList.add('active');
      break;
    }
  }

  try {
    const data = await api(`/api/session/${id}`);
    const msgs = document.getElementById('chatMessages');
    msgs.innerHTML = '';
    if (data.messages) {
      data.messages.forEach(m => addMessage(m.role, m.content));
    }
  } catch(e) { toast('加载会话详情失败', 'error'); }
}

async function deleteSession(id) {
  if (!confirm(`确定删除此会话？`)) return;
  try {
    await api(`/api/session/${id}`, { method: 'DELETE' });
    if (currentSession === id) currentSession = null;
    toast('会话已删除', 'success');
    loadSessions();
  } catch(e) { toast('删除失败', 'error'); }
}

function addMessage(role, content) {
  const msgs = document.getElementById('chatMessages');
  if (!msgs) return;
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const time = new Date().toLocaleTimeString();

  // Format content
  const formatted = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);

  // Actions (for assistant messages)
  let actions = '';
  if (role === 'assistant') {
    actions = `<div class="msg-actions">
      <button onclick="copyMsg(this)" title="复制">📋</button>
      <button onclick="speakMsg('${escapeHtml(content.replace(/'/g, "\\'"))}')" title="朗读">🔊</button>
      <button onclick="retryMsg('${escapeHtml(content.replace(/'/g, "\\'"))}')" title="重新生成">🔄</button>
    </div>`;
  }

  div.innerHTML = `${actions}${formatted}<div class="time">${time}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function renderMarkdown(text) {
  if (!text) return '';
  let html = escapeHtml(text);
  // Code blocks (```...```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre style="background:#1a1a2e;padding:10px;border-radius:8px;overflow-x:auto;font-size:12px;margin:8px 0"><code>${code.trim()}</code></pre>`;
  });
  // Inline code (`...`)
  html = html.replace(/`([^`]+)`/g, '<code style="background:#1a1a2e;padding:2px 5px;border-radius:4px;font-size:12px">$1</code>');
  // Bold (**...**)
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic (*...*)
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--accent)">$1</a>');
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  return html;
}

function copyMsg(btn) {
  const msg = btn.closest('.msg');
  const text = msg.textContent.replace(/📋🔊🔄\d{1,2}:\d{2}:\d{2}(AM|PM)?/, '').trim();
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '✅';
    setTimeout(() => btn.textContent = '📋', 1500);
  });
}

async function speakMsg(text) {
  try {
    // Use TTS endpoint
    const reply = await fetch('/api/config', { method: 'GET' }).then(r => r.json());
    // ... We'd need a dedicated TTS endpoint here
    toast('🔊 TTS 播放 (需语音管线启动)', 'success');
  } catch(e) { toast('朗读失败', 'error'); }
}

function retryMsg(text) {
  // Re-send the last user message before this assistant response
  const msgs = document.getElementById('chatMessages');
  const allMsgs = msgs.querySelectorAll('.msg');
  let userMsg = '';
  for (let i = allMsgs.length - 1; i >= 0; i--) {
    if (allMsgs[i].classList.contains('user')) {
      userMsg = allMsgs[i].textContent.trim();
      break;
    }
  }
  if (userMsg) {
    // Remove the last assistant response + thinking
    const last = msgs.lastChild;
    if (last && last.classList.contains('assistant')) last.remove();
    sendChatWithText(userMsg);
  }
}

function filterSessions(query) {
  const items = document.querySelectorAll('.session-item');
  const q = query.toLowerCase().trim();
  items.forEach(el => {
    const title = el.querySelector('.session-title')?.textContent?.toLowerCase() || '';
    el.style.display = (!q || title.includes(q)) ? '' : 'flex';
  });
}

function exportChat() {
  const msgs = document.getElementById('chatMessages');
  if (!msgs) return;
  const lines = [];
  msgs.querySelectorAll('.msg').forEach(m => {
    if (m.classList.contains('system')) return;
    const role = m.classList.contains('user') ? '🧑 你' : '🤖 AI';
    // Get text content without action buttons and time
    const text = m.textContent.replace(/📋🔊🔄/g, '').replace(/\d{1,2}:\d{2}:\d{2}(AM|PM)?/g, '').trim();
    if (text) lines.push(`${role}: ${text}`);
  });
  if (lines.length === 0) { toast('没有可导出的消息', 'warn'); return; }
  const blob = new Blob([lines.join('\n\n')], { type: 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `chat-${new Date().toISOString().slice(0,10)}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
  toast('✅ 对话已导出', 'success');
}

async function sendChat() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;
  sendChatWithText(text);
  input.value = '';
}

async function sendChatWithText(text) {
  addMessage('user', text);
  // Thinking animation
  const msgs = document.getElementById('chatMessages');
  const thinkDiv = document.createElement('div');
  thinkDiv.className = 'msg system';
  thinkDiv.innerHTML = '<div class="thinking-dots"><span></span><span></span><span></span></div>';
  msgs.appendChild(thinkDiv);
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const data = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ text, session_id: currentSession || '' })
    });
    // Remove thinking
    if (thinkDiv.parentNode) thinkDiv.remove();

    addMessage('assistant', data.response || '(空回复)');
    currentSession = data.session_id;
    loadSessions();
    updateContextBar();
  } catch(e) {
    if (thinkDiv.parentNode) thinkDiv.remove();
    addMessage('system', '❌ 请求失败: ' + e.message);
  }
}

async function updateContextBar() {
  try {
    const pers = await api('/api/personality');
    const p = pers.personality;
    const e = pers.emotional_state;
    const config = await api('/api/config');
    const llmLabel = getActiveModelLabel(config, 'llm');
    document.getElementById('ctxPersonality').textContent = `${p.emoji} ${p.name}`;
    document.getElementById('ctxEmotion').textContent = `💖 ${e.label}`;
    document.getElementById('ctxModel').textContent = `🔌 ${llmLabel}`;
  } catch(e) { /* ignore */ }
}

function renderProjectIntro(config) {
  const container = document.getElementById('projectIntro');
  if (!container) return;
  const ver = config?.app?.version || '0.5.0';
  container.innerHTML = `
    <div class="card" style="grid-column: 1 / -1">
      <h3>🚀 关于 LAZ-Bot v${ver}</h3>
      <p style="font-size:13px;line-height:1.7;color:var(--text2);margin:8px 0">
        <strong>LAZ-Bot</strong> 不是一个普通聊天机器人——它是一个<strong>有性格的树莓派融合智能体</strong>。
        基于 SBTI 人格体系（27 种人格类型 × 15 维度评分 × PAD 三维情绪模型），
        LAZ-Bot 不只是"回答问题"，而是<strong>以某种人格的身份与你对话</strong>。
      </p>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:12px">
        <div style="background:var(--bg);border-radius:8px;padding:12px">
          <div style="font-size:16px">🧬</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0">SBTI 人格引擎</div>
          <div style="font-size:11px;color:var(--text2)">27种人格 · 15维度 · PAD情绪</div>
        </div>
        <div style="background:var(--bg);border-radius:8px;padding:12px">
          <div style="font-size:16px">🧠</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0">三层记忆融合</div>
          <div style="font-size:11px;color:var(--text2)">短期+长期+脑图 · 艾宾浩斯遗忘</div>
        </div>
        <div style="background:var(--bg);border-radius:8px;padding:12px">
          <div style="font-size:16px">🎤</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0">语音交互</div>
          <div style="font-size:11px;color:var(--text2)">唤醒词 · VAD · STT · TTS</div>
        </div>
        <div style="background:var(--bg);border-radius:8px;padding:12px">
          <div style="font-size:16px">🔧</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0">工具执行引擎</div>
          <div style="font-size:11px;color:var(--text2)">AST安全沙箱 · 3个内置工具</div>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text2);margin-top:12px;text-align:center">
        🍓 运行在树莓派 5 · Open WebUI 中转 · 硅基流动云端 API · 
        <a href="https://github.com/laztudio/laz-bot" target="_blank" style="color:var(--accent)">GitHub</a>
      </div>
    </div>
  `;
}

function newSession() {
  currentSession = null;
  document.getElementById('chatMessages').innerHTML = '<div class="msg system">💬 新对话 — 输入消息开始</div>';
  document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
  updateContextBar();
}

// ════════════════════════════════════════
//  MODELS  —  Template-based model management
// ════════════════════════════════════════

const MODEL_CATEGORIES = [
  { key: 'llm', icon: '🧠', label: '大语言模型 (LLM)', extra: 'timeout', extraLabel: '超时 (秒)', ttsExtra: false },
  { key: 'stt', icon: '🎤', label: '语音识别 (STT)', extra: '', extraLabel: '', ttsExtra: false },
  { key: 'tts', icon: '🔊', label: '语音合成 (TTS)', extra: '', extraLabel: '', ttsExtra: true },
  { key: 'embedding', icon: '📐', label: '嵌入模型 (Embedding)', extra: 'dim', extraLabel: '向量维度', ttsExtra: false },
];

async function loadModelPage() {
  const container = document.getElementById('modelCategories');
  container.innerHTML = '<div class="loading">加载中...</div>';
  // Load templates
  try {
    const tResp = await api('/api/models/templates');
    templates = tResp.templates || [];
  } catch(e) { templates = []; }

  try {
    let html = '';
    for (const cat of MODEL_CATEGORIES) {
      const data = await api(`/api/models/${cat.key}`);
      html += renderCategory(cat, data);
    }
    container.innerHTML = html;
  } catch(e) {
    container.innerHTML = `<div style="color:var(--warn)">加载失败: ${e.message}</div>`;
  }
}

function renderCategory(cat, data) {
  const entries = data.entries || [];
  const active = data.active || '';
  let listHtml = entries.map(e => {
    const isActive = e.name === active;
    const tmpl = templates.find(t => t.id === e.provider);
    return `
      <div class="model-entry ${isActive ? 'active' : ''}">
        <div class="info">
          <div class="name">
            ${escapeHtml(e.label || e.name)}
            ${isActive ? '<span class="badge">使用中</span>' : ''}
            <span class="provider-tag">${tmpl ? escapeHtml(tmpl.name) : escapeHtml(e.provider || '自定义')}</span>
          </div>
          <div class="model-id">${escapeHtml(e.model_id)} @ ${escapeHtml(e.base_url)}</div>
          ${cat.key === 'tts' && e.voice ? `<div class="notes">🎤 ${escapeHtml(e.voice)} | ⚡ ${e.speed || 1.0}x</div>` : ''}
          ${e.notes ? `<div class="notes">${escapeHtml(e.notes)}</div>` : ''}
        </div>
        <div class="actions">
          ${isActive ? '' : `<button onclick="activateModel('${cat.key}','${e.name}')">启用</button>`}
          <button onclick="editModelEntry('${cat.key}','${e.name}')" class="icon-btn" title="编辑">✏️</button>
          <button onclick="deleteModelEntry('${cat.key}','${e.name}')" class="icon-btn" title="删除" style="color:var(--warn)">🗑️</button>
        </div>
      </div>
    `;
  }).join('');

  if (!listHtml) {
    listHtml = '<div style="color:var(--text2);padding:8px;font-size:12px">暂无模型，点击上方按钮添加</div>';
  }

  return `
    <div class="models-category-card">
      <div class="cat-header">
        <h3>${cat.icon} ${cat.label}</h3>
        <button onclick="addModelEntry('${cat.key}')" class="btn-sm">+ 添加模型</button>
      </div>
      ${listHtml}
    </div>
  `;
}

// ── Open model edit modal ──

function addModelEntry(category) {
  editingCategory = category;
  editingName = '';
  document.getElementById('modalTitle').textContent = '添加模型';
  openModelModal(category);
}

async function editModelEntry(category, name) {
  editingCategory = category;
  editingName = name;
  document.getElementById('modalTitle').textContent = '编辑模型';
  try {
    const data = await api(`/api/models/${category}`);
    const entry = (data.entries || []).find(e => e.name === name);
    if (!entry) { toast('模型未找到', 'error'); return; }
    openModelModal(category, entry);
  } catch(e) { toast('加载失败', 'error'); }
}

function openModelModal(category, entry) {
  // Populate provider dropdown
  const sel = document.getElementById('modProvider');
  sel.innerHTML = '<option value="custom">自定义</option>';
  const relevant = templates.filter(t => t.category && t.category.includes(category));
  relevant.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.id;
    opt.textContent = t.name + (t.notes ? ` — ${t.notes}` : '');
    sel.appendChild(opt);
  });

  if (entry) {
    sel.value = entry.provider || 'custom';
    document.getElementById('modLabel').value = entry.label || '';
    document.getElementById('modName').value = entry.name || '';
    document.getElementById('modName').readOnly = true;
    // Put model_id in manual input (select won't have this value)
    const modelSel = document.getElementById('modModelId');
    modelSel.innerHTML = '<option value="">— 选择模型 —</option>';
    modelSel.style.display = 'none';
    const manual = document.getElementById('modModelIdManual');
    manual.style.display = '';
    manual.value = entry.model_id || '';
    document.getElementById('modBaseUrl').value = entry.base_url || '';
    document.getElementById('modApiKey').value = entry.api_key || '';
    document.getElementById('modNotes').value = entry.notes || '';

    // TTS extra fields
    const ttsExtra = document.getElementById('ttsExtraFields');
    const genExtra = document.getElementById('modExtraField');
    if (category === 'tts') {
      ttsExtra.style.display = 'block';
      genExtra.style.display = 'none';
      document.getElementById('modTtsVoice').value = entry.voice || '';
      document.getElementById('modTtsSpeed').value = entry.speed || 1.0;
      document.getElementById('modTtsFormat').value = entry.response_format || 'mp3';
    } else {
      ttsExtra.style.display = 'none';
      const cat = MODEL_CATEGORIES.find(c => c.key === category);
      if (cat && cat.extra) {
        genExtra.style.display = 'block';
        document.getElementById('modExtraLabel').textContent = cat.extraLabel;
        document.getElementById('modExtraValue').value = entry[cat.extra] || '';
      } else {
        genExtra.style.display = 'none';
      }
    }
  } else {
    sel.value = 'custom';
    document.getElementById('modLabel').value = '';
    document.getElementById('modName').value = '';
    document.getElementById('modName').readOnly = false;
    document.getElementById('modModelId').value = '';
    document.getElementById('modBaseUrl').value = '';
    document.getElementById('modApiKey').value = '';
    document.getElementById('modNotes').value = '';

    const ttsExtra = document.getElementById('ttsExtraFields');
    const genExtra = document.getElementById('modExtraField');
    if (category === 'tts') {
      ttsExtra.style.display = 'block';
      genExtra.style.display = 'none';
      document.getElementById('modTtsVoice').value = 'fnlp/MOSS-TTSD-v0.5:alex';
      document.getElementById('modTtsSpeed').value = 1.0;
      document.getElementById('modTtsFormat').value = 'mp3';
    } else {
      ttsExtra.style.display = 'none';
      const cat = MODEL_CATEGORIES.find(c => c.key === category);
      if (cat && cat.extra) {
        genExtra.style.display = 'block';
        document.getElementById('modExtraLabel').textContent = cat.extraLabel;
        document.getElementById('modExtraValue').value = cat.extra === 'timeout' ? '30' : '1024';
      } else {
        genExtra.style.display = 'none';
      }
    }
  }

  document.getElementById('modTestResult').textContent = '';
  document.getElementById('modelEditModal').style.display = 'flex';
}

// ── Provider change ──

function onProviderChange() {
  const id = document.getElementById('modProvider').value;
  const tmpl = templates.find(t => t.id === id);
  // Reset model select
  const sel = document.getElementById('modModelId');
  sel.innerHTML = '<option value="">— 先测试连接以获取模型列表 —</option>';
  document.getElementById('modModelIdManual').style.display = 'none';
  document.getElementById('modModelIdManual').value = '';
  document.getElementById('modLabel').value = '';
  document.getElementById('modName').value = '';
  if (tmpl) {
    document.getElementById('modBaseUrl').value = tmpl.base_url;
    document.getElementById('modTestResult').textContent = `📌 ${tmpl.name}: ${tmpl.notes || ''}`;
  } else {
    document.getElementById('modTestResult').textContent = '自定义配置：手动填写 URL';
  }
}

function onLabelChange() {
  // Only used if user manually edits label
  const label = document.getElementById('modLabel').value.trim();
  const name = label
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '') || '';
  document.getElementById('modName').value = name || 'my-model';
}

// When user picks from model select dropdown
function onModelIdChange(selectEl) {
  const val = selectEl.value;
  if (val === '__manual__') {
    document.getElementById('modModelId').style.display = 'none';
    document.getElementById('modModelIdManual').style.display = '';
    document.getElementById('modModelIdManual').value = '';
    document.getElementById('modModelIdManual').focus();
  } else if (val) {
    document.getElementById('modModelIdManual').style.display = 'none';
    onModelIdSet(val);
  }
}

// ── Test connection ──

async function testConnection() {
  const btn = document.getElementById('btnTestConn');
  const result = document.getElementById('modTestResult');
  const url = document.getElementById('modBaseUrl').value.trim();
  const key = document.getElementById('modApiKey').value.trim();
  const model = document.getElementById('modModelId').value.trim();
  const id = document.getElementById('modProvider').value;
  const tmpl = templates.find(t => t.id === id);

  if (!url) { result.textContent = '⚠️ 请先选择提供商或填入 URL'; result.style.color = 'var(--warn)'; return; }
  btn.textContent = '⏳ 测试中...';
  btn.disabled = true;
  result.textContent = '⏳ 连接中...';
  result.style.color = 'var(--text2)';

  try {
    const resp = await api('/api/models/test-connection', {
      method: 'POST',
      body: JSON.stringify({ base_url: url, api_key: key, model_id: model, need_key: tmpl ? tmpl.need_key : true })
    });
    if (resp.ok) {
      let msg = `✅ 连接成功`;
      if (resp.models && resp.models.length > 0) {
        msg += `（发现 ${resp.models.length} 个模型）`;
        populateModelSelect(resp.models);
      }
      result.textContent = msg + ` (${resp.elapsed || '<1s'})`;
      result.style.color = '#00d4aa';
      toast('连接成功', 'success');
    } else {
      result.textContent = `❌ 失败: ${resp.error || '未知错误'}`;
      result.style.color = '#ff6b6b';
    }
  } catch(e) {
    result.textContent = `❌ 失败: ${e.message}`;
    result.style.color = '#ff6b6b';
  }
  btn.textContent = '🔗 测试连接';
  btn.disabled = false;
}

// When test finds models, populate the select dropdown
function populateModelSelect(models) {
  const sel = document.getElementById('modModelId');
  sel.innerHTML = '<option value="">— 选择模型 —</option>' +
    models.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('') +
    '<option value="__manual__">✏️ 手动输入...</option>';
  sel.style.display = '';
  document.getElementById('modModelIdManual').style.display = 'none';
  document.getElementById('modModelIdManual').value = '';
}

// When model_id is set (typed or picked), auto-generate label and name
function onModelIdSet(modelId) {
  if (!modelId) return;
  // Generate a human-friendly label from the model ID
  const label = modelId
    .replace(/^[\w-]+\//, '') // remove org/ prefix like "deepseek-ai/"
    .replace(/-/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, c => c.toUpperCase());
  document.getElementById('modLabel').value = label;
  // Generate name (slug)
  const name = label
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  document.getElementById('modName').value = name || 'my-model';
}

function showModelPicker(models, onSelect) {
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:2000;';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

  const box = document.createElement('div');
  box.style.cssText = 'background:var(--surface,#1a1a2e);border:1px solid var(--border,#2a2a4a);border-radius:16px;width:420px;max-height:60vh;overflow:hidden;display:flex;flex-direction:column;';

  const header = document.createElement('div');
  header.style.cssText = 'padding:14px 16px;border-bottom:1px solid var(--border,#2a2a4a);font-size:14px;font-weight:600;color:var(--text,#e0e0f0);';
  header.textContent = '选择模型'; box.appendChild(header);

  const searchInput = document.createElement('input');
  searchInput.placeholder = '搜索模型...';
  searchInput.style.cssText = 'margin:8px 12px;padding:8px 12px;background:var(--bg,#0f0f23);border:1px solid var(--border,#2a2a4a);border-radius:8px;color:var(--text,#e0e0f0);font-size:13px;';
  box.appendChild(searchInput);

  const listDiv = document.createElement('div');
  listDiv.style.cssText = 'overflow-y:auto;flex:1;padding:4px 12px 12px;';
  box.appendChild(listDiv);

  function renderList(filtered) {
    listDiv.innerHTML = filtered.map(m =>
      `<div class="model-picker-item" style="padding:10px 12px;font-size:13px;cursor:pointer;border-radius:8px;color:var(--text,#e0e0f0);border-bottom:1px solid var(--border,#2a2a4a);"
           onmouseover="this.style.background='var(--surface2,#16213e)'"
           onmouseout="this.style.background=''"
           onclick="document.getElementById('modelPickerOverlay').remove();(${onSelect.toString()})('${m.replace(/'/g, "\'")}')">
        ${escapeHtml(m)}
      </div>
    `).join('');
  }

  searchInput.oninput = () => {
    const q = searchInput.value.toLowerCase();
    renderList(models.filter(m => m.toLowerCase().includes(q)));
  };
  renderList(models);

  overlay.appendChild(box);
  document.body.appendChild(overlay);
  setTimeout(() => searchInput.focus(), 100);
}

// ── Save model ──

function closeModelModal() {
  document.getElementById('modelEditModal').style.display = 'none';
}

async function saveModelEntry() {
  const sel = document.getElementById('modModelId');
    const manual = document.getElementById('modModelIdManual');
    const modelId = sel.value === '__manual__' || !sel.value ? manual.value.trim() : sel.value.trim();
    const entry = {
      name: document.getElementById('modName').value.trim(),
      label: document.getElementById('modLabel').value.trim(),
      provider: document.getElementById('modProvider').value,
      model_id: modelId,
    base_url: document.getElementById('modBaseUrl').value.trim(),
    api_key: document.getElementById('modApiKey').value.trim(),
    notes: document.getElementById('modNotes').value.trim()
  };

  const cat = MODEL_CATEGORIES.find(c => c.key === editingCategory);
  if (cat && cat.extra) {
    const v = document.getElementById('modExtraValue').value.trim();
    if (v) entry[cat.extra] = cat.extra === 'timeout' ? parseInt(v) : parseInt(v);
  }
  // TTS extra fields
  if (editingCategory === 'tts') {
    entry.voice = document.getElementById('modTtsVoice').value.trim();
    entry.speed = parseFloat(document.getElementById('modTtsSpeed').value) || 1.0;
    entry.response_format = document.getElementById('modTtsFormat').value;
  }

  if (!entry.name || !entry.model_id || !entry.base_url) {
    toast('模型 ID 和 Base URL 为必填项', 'error');
    return;
  }

  try {
    if (editingName) {
      await api(`/api/models/${editingCategory}/${editingName}`, {
        method: 'PUT', body: JSON.stringify(entry)
      });
      toast('模型已更新', 'success');
    } else {
      await api(`/api/models/${editingCategory}`, {
        method: 'POST', body: JSON.stringify(entry)
      });
      toast('模型已添加', 'success');
    }
    closeModelModal();
    loadModelPage();
  } catch(e) { toast('保存失败: ' + e.message, 'error'); }
}

async function activateModel(category, name) {
  try {
    await api(`/api/models/${category}/activate/${name}`, { method: 'POST' });
    toast(`✅ 已切换至 ${name}`, 'success');
    loadModelPage();
  } catch(e) { toast('切换失败', 'error'); }
}

async function deleteModelEntry(category, name) {
  if (!confirm(`确定删除模型 "${name}"？`)) return;
  try {
    await api(`/api/models/${category}/${name}`, { method: 'DELETE' });
    toast('模型已删除', 'success');
    loadModelPage();
  } catch(e) { toast('删除失败', 'error'); }
}

// ════════════════════════════════════════
//  MEMORY
// ════════════════════════════════════════

async function loadMemoryStats() {
  const card = document.getElementById('memoryStatsCard');
  try {
    const data = await api('/api/memory/stats');
    card.innerHTML = `
      <h3>记忆统计</h3>
      <div class="stat-grid">
        <div class="stat-item">
          <div class="stat-value">${data.long_term_count || 0}</div>
          <div class="stat-label">长期记忆</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">${data.graph?.nodes || 0}</div>
          <div class="stat-label">概念节点</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">${data.graph?.edges || 0}</div>
          <div class="stat-label">关联边</div>
        </div>
        <div class="stat-item">
          <div class="stat-value ${data.initialized ? '' : 'warn'}">
            ${data.initialized ? '✅ 已初始化' : '❌ 未初始化'}
          </div>
          <div class="stat-label">状态</div>
        </div>
      </div>
    `;
  } catch(e) {
    card.innerHTML = '<h3>记忆统计</h3><p style="color:var(--warn)">加载失败</p>';
  }
}

async function searchMemory() {
  const q = document.getElementById('memorySearchQuery').value.trim();
  const container = document.getElementById('memoryResults');
  if (!q) { container.innerHTML = ''; return; }
  container.innerHTML = '<div class="loading">搜索中...</div>';
  try {
    const data = await api(`/api/memory/search?q=${encodeURIComponent(q)}&top_k=10`);
    if (!data.results || data.results.length === 0) {
      container.innerHTML = '<div style="color:var(--text2);padding:8px">未找到匹配的记忆</div>';
      return;
    }
    container.innerHTML = data.results.map((r, i) => `
      <div class="memory-item">
        <span class="delete" onclick="deleteMemory(${r.id || i})">✕</span>
        <div class="content">${escapeHtml(r.content || r.text || '')}</div>
        <div class="meta">
          相似度: ${(r.score || r.distance || 0).toFixed(3)}
          ${r.created_at ? '· ' + new Date(r.created_at * 1000).toLocaleString() : ''}
        </div>
      </div>
    `).join('');
  } catch(e) {
    container.innerHTML = '<div style="color:var(--warn)">搜索失败</div>';
  }
}

async function deleteMemory(id) {
  if (!confirm('确定删除这条记忆？')) return;
  try {
    await api(`/api/memory/forget/${id}`, { method: 'POST' });
    toast('记忆已删除', 'success');
    searchMemory();
  } catch(e) { toast('删除失败', 'error'); }
}

async function saveMemoryConfig() {
  const cfg = {
    memory: {
      retrieval: {
        vector_weight: parseFloat(document.getElementById('memVecWeight').value) || 0.4,
        keyword_weight: parseFloat(document.getElementById('memKwWeight').value) || 0.3,
        recency_weight: parseFloat(document.getElementById('memRecencyWeight').value) || 0.3,
        knn_top_k: parseInt(document.getElementById('memTopK').value) || 10,
        fts_top_k: parseInt(document.getElementById('memTopK').value) || 10,
        rrf_final_k: parseInt(document.getElementById('memFinalK').value) || 5,
      },
      forgetting: {
        halflife_base: parseInt(document.getElementById('memHalflife').value) || 7
      }
    }
  };
  try {
    await api('/api/config', { method: 'PUT', body: JSON.stringify(cfg) });
    toast('记忆配置已保存', 'success');
  } catch(e) { toast('保存失败', 'error'); }
}

// ════════════════════════════════════════
//  AUDIO PIPELINE
// ════════════════════════════════════════

let audioWs = null;
let audioActive = false;

async function loadAudioConfig() {
  try {
    const cfg = await api('/api/config');
    const v = cfg.voice || {};

    // Basic
    document.getElementById('vadSilenceTimeout').value = v.silence_timeout ?? 0.5;
    document.getElementById('vadSilenceTimeoutVal').textContent = (v.silence_timeout ?? 0.5) + 's';

    // Advanced VAD
    document.getElementById('vadSpeechThresh').value = v.speech_threshold ?? 0.02;
    document.getElementById('vadSpeechThreshVal').textContent = (v.speech_threshold ?? 0.02).toFixed(3);
    document.getElementById('vadSilenceThresh').value = v.silence_threshold ?? 0.008;
    document.getElementById('vadSilenceThreshVal').textContent = (v.silence_threshold ?? 0.008).toFixed(3);
    document.getElementById('vadMaxRecording').value = v.max_recording_sec ?? 15;
    document.getElementById('vadPreSpeech').value = v.pre_speech_sec ?? 0.4;
    document.getElementById('vadNoiseAdapt').checked = v.noise_adapt !== false;

    // Gain
    document.getElementById('inputGainSlider').value = v.input_gain ?? 1.0;
    document.getElementById('inputGainVal').textContent = (v.input_gain ?? 1.0) + 'x';
    document.getElementById('outputGainSlider').value = v.output_gain ?? 1.0;
    document.getElementById('outputGainVal').textContent = (v.output_gain ?? 1.0) + 'x';

    // Wake words — loaded asynchronously via loadWakeWords()
    loadWakeWords();

    // Audio devices
    try {
      const devs = await api('/api/audio/devices');
      const inSel = document.getElementById('audioInputDevice');
      const outSel = document.getElementById('audioOutputDevice');
      if (devs.devices) {
        [inSel, outSel].forEach(sel => {
          if (!sel) return;
          sel.innerHTML = '<option value="">— 自动检测 (plughw:2,0) —</option>';
          devs.devices.forEach(d => {
            const alsaDev = d.alsa_device || '';
            const label = `${d.name} [${alsaDev || 'unknown'}]`;
            sel.innerHTML += `<option value="${alsaDev}">${label}</option>`;
          });
        });
        if (v.input_device) inSel.value = v.input_device;
        if (v.output_device) outSel.value = v.output_device;
      }
    } catch(e) { /* devices failed silently */ }
  } catch(e) { toast('加载音频配置失败', 'error'); }
}

async function saveAudioConfig() {
  const cfg = {
    voice: {
      silence_timeout: parseFloat(document.getElementById('vadSilenceTimeout').value) || 0.5,
      speech_threshold: parseFloat(document.getElementById('vadSpeechThresh').value) || 0.02,
      silence_threshold: parseFloat(document.getElementById('vadSilenceThresh').value) || 0.008,
      max_recording_sec: parseInt(document.getElementById('vadMaxRecording').value) || 15,
      pre_speech_sec: parseFloat(document.getElementById('vadPreSpeech').value) || 0.4,
      noise_adapt: document.getElementById('vadNoiseAdapt').checked,
      input_gain: parseFloat(document.getElementById('inputGainSlider').value) || 1.0,
      output_gain: parseFloat(document.getElementById('outputGainSlider').value) || 1.0,
      input_device: document.getElementById('audioInputDevice')?.value || '',
      output_device: document.getElementById('audioOutputDevice')?.value || '',
    }
  };
  try {
    await api('/api/config', { method: 'PUT', body: JSON.stringify(cfg) });
    toast('音频配置已保存', 'success');
  } catch(e) { toast('保存失败', 'error'); }
}

// ═══ VU Meter (Cyberpunk Needle Gauge) ═══

const VU_COLORS = ['#00ff88','#88ff00','#ccff00','#ffff00','#ffcc00','#ff8800','#ff4400','#ff0000'];

function dbToY(db, h) { return h - Math.max(0, (db + 60) / 60 * h); }

function drawVuMeter(canvasId, db, peakDb) {
  const c = document.getElementById(canvasId);
  if (!c) return;
  const w = c.width, h = c.height;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, w, h);

  const cx = w / 2, cy = h * 0.75;
  const radius = Math.min(w, h) * 0.55;
  const startAngle = Math.PI * 0.75, endAngle = Math.PI * 2.25;

  // Outer glow ring
  const glow = ctx.createRadialGradient(cx, cy, radius * 0.85, cx, cy, radius * 1.08);
  glow.addColorStop(0, 'rgba(0,255,136,0)');
  glow.addColorStop(0.7, 'rgba(0,255,136,0.08)');
  glow.addColorStop(1, 'rgba(0,255,136,0.15)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 1.08, 0, Math.PI * 2);
  ctx.fill();

  // Tick marks
  for (let i = 0; i <= 60; i += 5) {
    const angle = startAngle + (endAngle - startAngle) * (i / 60);
    const inner = radius * 0.78, outer = radius * 0.88;
    const color = i < 30 ? '#00ff88' : i < 45 ? '#ffcc00' : '#ff3333';
    ctx.strokeStyle = color;
    ctx.lineWidth = i % 10 === 0 ? 2 : 1;
    ctx.globalAlpha = i % 10 === 0 ? 1 : 0.5;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * inner, cy + Math.sin(angle) * inner);
    ctx.lineTo(cx + Math.cos(angle) * outer, cy + Math.sin(angle) * outer);
    ctx.stroke();
    if (i % 10 === 0) {
      const labelR = radius * 0.68;
      const lx = cx + Math.cos(angle) * labelR, ly = cy + Math.sin(angle) * labelR;
      ctx.fillStyle = color;
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(-i, lx, ly + 3);
    }
  }
  ctx.globalAlpha = 1;

  // Arc background
  const arcGrad = ctx.createConicalGradient ? null : null;
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.82, startAngle, endAngle);
  ctx.stroke();

  // Colored arc segments
  const rawAngle = startAngle + (endAngle - startAngle) * Math.min(1, Math.max(0, (db + 60) / 60));
  // Green → Yellow → Red gradient arc
  const segments = [
    { from: 0, to: 0.5, color: 'rgba(0,255,136,0.3)' },
    { from: 0.5, to: 0.75, color: 'rgba(255,204,0,0.3)' },
    { from: 0.75, to: 1.0, color: 'rgba(255,51,51,0.3)' },
  ];
  segments.forEach(seg => {
    const segStart = Math.max(seg.from, Math.min(seg.to, (db + 60) / 60));
    // Actually draw full segments up to current level
  });

  // Active arc up to current level
  if (db > -59) {
    const activeAngle = startAngle + (endAngle - startAngle) * Math.min(1, (db + 60) / 60);
    const hue = db > -20 ? 0 : db > -35 ? 40 : 130;
    ctx.strokeStyle = `hsl(${hue}, 100%, 60%)`;
    ctx.lineWidth = 4;
    ctx.shadowColor = `hsl(${hue}, 100%, 50%)`;
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.82, startAngle, activeAngle);
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // Needle
  const needleAngle = startAngle + (endAngle - startAngle) * Math.min(1, (db + 60) / 60);
  const needleLen = radius * 0.7;
  const nx = cx + Math.cos(needleAngle) * needleLen;
  const ny = cy + Math.sin(needleAngle) * needleLen;
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(nx, ny);
  ctx.stroke();

  // Needle dot
  ctx.fillStyle = '#0ff';
  ctx.shadowColor = '#0ff';
  ctx.shadowBlur = 6;
  ctx.beginPath();
  ctx.arc(cx, cy, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Digital readout
  ctx.fillStyle = '#0f0';
  ctx.font = 'bold 14px monospace';
  ctx.textAlign = 'center';
  ctx.shadowColor = '#0f0';
  ctx.shadowBlur = 4;
  ctx.fillText((db > -59 ? db.toFixed(1) : '-\u221E') + ' dB', cx, cy - radius * 0.55);
  ctx.shadowBlur = 0;
}

function updateVuDisplay(type, data) {
  const db = Math.max(-60, Math.min(0, data.db || -60));
  const peak = data.peak !== undefined ? 20 * Math.log10(Math.max(data.peak, 1e-6)) : db;
  const canvasId = type === 'vu_input' ? 'vuInput' : 'vuOutput';
  const labelId = type === 'vu_input' ? 'vuInputDb' : 'vuOutputDb';
  const rmsId = type === 'vu_input' ? 'vuInputRms' : 'vuOutputRms';
  drawVuMeter(canvasId, db, peak);
  const label = document.getElementById(labelId);
  if (label) label.textContent = (db > -59 ? db.toFixed(1) : '-\u221E') + ' dB';
  const rmsEl = document.getElementById(rmsId);
  if (rmsEl) rmsEl.textContent = 'RMS: ' + data.rms.toFixed(5);
}

// ═══ Independent VU Monitor (always-on mic level) ═══

function toggleVuMonitor() {
  const btn = document.getElementById('vuToggleBtn');
  const status = document.getElementById('vuStatus');
  if (vuWs) {
    vuWs.close();
    vuWs = null;
    btn.textContent = '🔴 启动监听';
    btn.className = 'btn-sm';
    if (status) status.textContent = '⚫ 已停止';
    return;
  }

  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/vu`;
  vuWs = new WebSocket(url);
  btn.textContent = '⏹ 停止';
  btn.className = 'btn-sm btn-warn';
  if (status) status.textContent = '🟡 连接中...';

  vuWs.onopen = () => {
    if (status) status.textContent = '🟢 监听中';
  };

  vuWs.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'vu_input') {
      updateVuDisplay('vu_input', msg.data);
    } else if (msg.type === 'vu_ready') {
      if (status) status.textContent = '🟢 ' + msg.data;
    } else if (msg.type === 'vu_error') {
      if (status) status.textContent = '🔴 ' + msg.data;
      btn.textContent = '🔴 启动监听';
      btn.className = 'btn-sm';
    }
  };

  vuWs.onclose = () => {
    vuWs = null;
    btn.textContent = '🔴 启动监听';
    btn.className = 'btn-sm';
    if (status) status.textContent = '⚫ 已断开';
  };

  vuWs.onerror = () => {
    if (status) status.textContent = '🔴 连接失败';
    if (vuWs) vuWs.close();
  };
}

// ═══ Audio Page Init ═══

function initAudioPage() {
  // Init VU meters
  drawVuMeter('vuInput', -60);
  drawVuMeter('vuOutput', -60);

  // Load config
  loadAudioConfig();

  // Auto-connect VU monitor when entering page
  // User clicks the button manually
}

// ═══ Wake Word Management ═══

async function loadWakeWords() {
  try {
    const data = await api('/api/audio/wakewords');
    const models = data.models || [];
    const active = data.active || [];
    const threshold = data.wake_threshold ?? 0.5;

    document.getElementById('wwThreshold').value = threshold;
    document.getElementById('wwThresholdVal').textContent = threshold.toFixed(2);

    renderWakeWordList(models, active);

    const status = document.getElementById('wakeStatus');
    if (status) {
      if (models.length === 0) status.textContent = '📭 尚未上传唤醒词模型';
      else if (active.length === 0) status.textContent = `⚠️ 已上传 ${models.length} 个模型，但未激活任何唤醒词`;
      else status.textContent = `✅ 激活: ${active.join(', ')} (共 ${models.length} 个模型)`;
    }
  } catch(e) {
    console.error('loadWakeWords failed', e);
  }
}

function renderWakeWordList(models, active) {
  const container = document.getElementById('wwModelList');
  if (!container) return;

  if (models.length === 0) {
    container.innerHTML = '<div class="ww-empty">📭 尚无唤醒词模型 — 上传 .onnx 文件开始</div>';
    return;
  }

  container.innerHTML = models.map(m => {
    const isActive = active.includes(m.name);
    return `
      <div class="ww-model-row ${isActive ? 'active' : ''}">
        <label class="ww-check-label">
          <input type="checkbox" ${isActive ? 'checked' : ''}
                 onchange="toggleWakeWord('${m.name}', this.checked)">
          <span class="ww-model-name">🎯 ${escapeHtml(m.name)}</span>
        </label>
        <span class="ww-model-size">${m.size_str}</span>
        <button class="btn-sm btn-danger-sm" onclick="deleteWakeWordFile('${m.filename}')"
                title="删除文件">🗑</button>
      </div>`;
  }).join('');
}

async function uploadWakeWordFiles(files) {
  if (!files || files.length === 0) return;

  const formData = new FormData();
  for (const f of files) {
    if (!f.name.endsWith('.onnx')) {
      toast(`跳过非 ONNX 文件: ${f.name}`, 'warn');
      continue;
    }
    formData.append('files', f);
  }

  try {
    const resp = await fetch('/api/audio/wakewords/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await resp.json();

    if (data.uploaded && data.uploaded.length > 0) {
      const names = data.uploaded.map(u => u.name).join(', ');
      toast(`✅ 已上传: ${names}`, 'success');
    }
    if (data.errors && data.errors.length > 0) {
      data.errors.forEach(e => toast(e, 'error'));
    }
    if (!data.uploaded && !data.errors) {
      toast(data.error || '上传失败', 'error');
    }

    // Clear file input
    document.getElementById('wwFileInput').value = '';
    // Reload
    await loadWakeWords();
  } catch(e) {
    toast('上传失败: ' + e.message, 'error');
  }
}

async function toggleWakeWord(name, checked) {
  try {
    // Get current state
    const data = await api('/api/audio/wakewords');
    let active = data.active || [];

    if (checked) {
      if (!active.includes(name)) active.push(name);
    } else {
      active = active.filter(a => a !== name);
    }

    // Update wake_model_path to first active model
    let wakeModelPath = '';
    if (active.length > 0) {
      wakeModelPath = `wake_words/${active[0]}.onnx`;
    }

    await api('/api/audio/wakewords/activate', {
      method: 'POST',
      body: JSON.stringify({
        active: active,
        wake_threshold: parseFloat(document.getElementById('wwThreshold').value) || 0.5,
        wake_model_path: wakeModelPath,
      }),
    });

    toast(`唤醒词已更新: ${active.join(', ') || '(无)'}`, 'success');
    await loadWakeWords();
  } catch(e) {
    toast('更新失败: ' + e.message, 'error');
    // Re-render to undo checkbox
    await loadWakeWords();
  }
}

async function saveWakeWordConfig() {
  const data = await api('/api/audio/wakewords');
  const active = data.active || [];
  const threshold = parseFloat(document.getElementById('wwThreshold').value) || 0.5;

  let wakeModelPath = '';
  if (active.length > 0) {
    wakeModelPath = `wake_words/${active[0]}.onnx`;
  }

  await api('/api/audio/wakewords/activate', {
    method: 'POST',
    body: JSON.stringify({ active, wake_threshold: threshold, wake_model_path: wakeModelPath }),
  });
  toast('唤醒阈值已保存', 'success');
}

async function deleteWakeWordFile(filename) {
  if (!confirm(`确定删除唤醒词文件 "${filename}"？\n此操作不可恢复。`)) return;

  try {
    await api(`/api/audio/wakewords/${filename}`, { method: 'DELETE' });
    toast(`已删除: ${filename}`, 'success');
    await loadWakeWords();
  } catch(e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

// Drag-and-drop for wake word upload zone
document.addEventListener('DOMContentLoaded', () => {
  const zone = document.getElementById('wwUploadZone');
  if (!zone) return;

  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    zone.classList.add('ww-dragover');
  });
  zone.addEventListener('dragleave', () => {
    zone.classList.remove('ww-dragover');
  });
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('ww-dragover');
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      uploadWakeWordFiles(files);
    }
  });
});

// ═══ WebSocket ═══

function startVoicePipeline() {
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/audio`;
  audioWs = new WebSocket(url);
  audioActive = true;

  const statusEl = document.getElementById('voiceStatus');
  const btn = document.getElementById('voiceStartBtn');

  audioWs.onopen = () => {
    if (statusEl) statusEl.innerText = '🟢 已连接 — 正在监听...';
    if (btn) { btn.textContent = '⏹ 停止'; btn.className = 'btn-warn'; btn.onclick = stopVoicePipeline; }
  };

  audioWs.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    const log = document.getElementById('voiceLog');

    switch(msg.type) {
      case 'vu_output':
        updateVuDisplay(msg.type, msg.data);
        break;
      case 'transcript':
        if (log) log.innerHTML += `<div class="voice-user">🗣 ${escapeHtml(msg.data)}</div>`;
        break;
      case 'response':
        if (log) log.innerHTML += `<div class="voice-assistant">🤖 ${escapeHtml(msg.data)}</div>`;
        break;
      case 'status':
        if (statusEl) statusEl.innerText = '🟢 ' + msg.data;
        break;
      case 'error':
        if (log) log.innerHTML += `<div class="voice-error">❌ ${escapeHtml(msg.data)}</div>`;
        break;
    }
    if (log) log.scrollTop = log.scrollHeight;
  };

  audioWs.onclose = () => {
    audioActive = false;
    if (statusEl) statusEl.innerText = '⚫ 已断开';
    if (btn) { btn.textContent = '▶ 启动语音'; btn.className = 'btn'; btn.onclick = startVoicePipeline; }
  };

  audioWs.onerror = () => {
    if (statusEl) statusEl.innerText = '🔴 连接失败';
    toast('语音管道连接失败', 'error');
  };
}

function stopVoicePipeline() {
  if (audioWs) {
    audioWs.close();
    audioWs = null;
  }
  audioActive = false;
}

// ════════════════════════════════════════
//  SETTINGS
// ════════════════════════════════════════

async function loadGeneralConfig() {
  try {
    const cfg = await api('/api/config');
    const exec = cfg.executor || {};

    document.getElementById('execTimeout').value = exec.tool_timeout || 30;
    document.getElementById('execMaxRounds').value = exec.max_tool_rounds || 3;
  } catch(e) { toast('加载设置失败', 'error'); }
}

async function saveGeneralConfig() {
  const cfg = {
    executor: {
      tool_timeout: parseInt(document.getElementById('execTimeout').value) || 30,
      max_tool_rounds: parseInt(document.getElementById('execMaxRounds').value) || 3
    }
  };
  try {
    await api('/api/config', { method: 'PUT', body: JSON.stringify(cfg) });
    toast('设置已保存', 'success');
  } catch(e) { toast('保存失败', 'error'); }
}

async function restartService() {
  if (!confirm('⚠️ 确定要重启 LAZ-Bot 服务？Web 界面将暂时断开连接。')) return;
  try {
    await api('/api/service/restart', { method: 'POST' });
    toast('🔄 服务正在重启...', 'info');
    let attempts = 0;
    const wait = setInterval(async () => {
      attempts++;
      try {
        const h = await api('/health');
        if (h.status === 'ok') {
          clearInterval(wait);
          toast('✅ 服务已重启完成', 'success');
          loadDashboard();
          checkHealth();
        }
      } catch(e) {
        if (attempts > 30) { clearInterval(wait); toast('重启超时，请手动检查', 'error'); }
      }
    }, 2000);
  } catch(e) { toast('重启失败', 'error'); }
}

async function viewLogs() {
  const viewer = document.getElementById('logViewer');
  const content = document.getElementById('logContent');
  if (viewer.style.display === 'none') {
    viewer.style.display = 'block';
    content.textContent = '正在获取日志...';
    try {
      const data = await api('/api/service/logs?lines=60');
      content.textContent = data.logs || data.error || '无日志';
    } catch(e) {
      content.textContent = '日志获取失败: ' + e.message + '\n\n提示: 通过 SSH 执行 sudo journalctl -u laz-bot -n 50 --no-pager';
    }
  } else {
    viewer.style.display = 'none';
  }
}

function openWebUI() {
  // Open Open WebUI in same host
  const host = location.hostname;
  window.open(`http://${host}:3000`, '_blank');
}

// ════════════════════════════════════════
//  UTILITIES
// ════════════════════════════════════════

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
