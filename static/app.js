/* DRX Command Center — frontend logic */

let activeResults = [];

async function processRequest() {
  const brainDump = document.getElementById('brain-dump').value.trim();
  if (!brainDump) {
    alert('Please describe what you need done.');
    return;
  }

  // UI state: loading
  setLoading(true);
  clearResults();
  showSection('progress-section', true);
  showSection('pdf-summary', false);
  showSection('results-section', false);
  document.getElementById('progress-log').innerHTML = '';

  const formData = new FormData();
  formData.append('brain_dump', brainDump);
  formData.append('carrier_override', document.getElementById('carrier-select').value);
  formData.append('write_to_jobtread', document.getElementById('write-to-jt').checked ? 'true' : 'false');

  const pdfFile = document.getElementById('pdf-upload').files[0];
  if (pdfFile) {
    formData.append('pdf_file', pdfFile);
  }

  try {
    const evtSource = await streamProcess(formData);
  } catch (err) {
    addProgress('error', `Request failed: ${err.message}`);
    setLoading(false);
  }
}

async function streamProcess(formData) {
  // We POST then read the SSE stream via fetch + ReadableStream
  const response = await fetch('/api/process', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Server error ${response.status}: ${text}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by double newlines
    const frames = buffer.split('\n\n');
    buffer = frames.pop(); // last partial frame stays in buffer

    for (const frame of frames) {
      if (!frame.trim()) continue;
      const lines = frame.split('\n');
      let event = 'message';
      let data = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) event = line.slice(7).trim();
        if (line.startsWith('data: ')) data = line.slice(6).trim();
      }
      handleEvent(event, data);
    }
  }

  setLoading(false);
}

function handleEvent(event, data) {
  switch (event) {
    case 'progress':
      addProgress('pending', data);
      break;

    case 'warning':
      addProgress('warn', data);
      break;

    case 'pdf_parsed':
      addProgress('done', 'PDF parsed successfully');
      document.getElementById('pdf-summary-text').textContent = data;
      showSection('pdf-summary', true);
      break;

    case 'routed': {
      const r = JSON.parse(data);
      const details = [
        r.intents && r.intents.length ? `Tasks: ${r.intents.join(', ')}` : '',
        r.carrier ? `Carrier: ${r.carrier.replace('_', ' ')}` : '',
        r.job_id ? `Job ID: ${r.job_id}` : (r.job_name ? `Job: ${r.job_name}` : ''),
      ].filter(Boolean).join(' | ');
      addProgress('done', `Routing complete — ${details}`);
      break;
    }

    case 'agent_done': {
      const a = JSON.parse(data);
      const label = { estimate: 'Estimate', insurance: 'Insurance letter', jobtread: 'JobTread update', sales: 'Sales document' }[a.agent] || a.agent;
      addProgress('done', `${label} complete`);
      break;
    }

    case 'complete': {
      const payload = JSON.parse(data);
      activeResults = payload.results || [];
      if (payload.total_tokens) {
        document.getElementById('token-count').textContent = `${payload.total_tokens.toLocaleString()} tokens used`;
      }
      renderResults(activeResults);
      showSection('results-section', true);
      addProgress('done', 'All tasks complete');
      break;
    }

    case 'error':
      addProgress('error', data);
      setLoading(false);
      break;
  }
}

function renderResults(results) {
  const tabBar = document.getElementById('tab-bar');
  const tabContent = document.getElementById('tab-content');
  tabBar.innerHTML = '';
  tabContent.innerHTML = '';

  results.forEach((result, i) => {
    // Tab button
    const btn = document.createElement('button');
    btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = result.title || result.agent;
    btn.onclick = () => switchTab(i);
    tabBar.appendChild(btn);

    // Tab pane
    const pane = document.createElement('div');
    pane.className = 'tab-pane' + (i === 0 ? ' active' : '');
    pane.id = `tab-${i}`;

    let html = result.html || '';

    // Download bar
    const downloads = [];
    if (result.docx_url) {
      downloads.push(`<a href="${result.docx_url}" download class="btn-download">⬇ Download .docx</a>`);
    }
    if (result.agent === 'jobtread' && result.note_text) {
      const jobId = ''; // Would need job_id from routing — pass through in result for write
      if (result.written_to_jt) {
        downloads.push(`<span class="btn-download btn-jt">✓ Saved to JobTread</span>`);
      } else {
        downloads.push(`<button class="btn-download btn-jt" onclick="saveToJT('${escapeAttr(result.note_text)}')">Save to JobTread</button>`);
      }
    }
    if (downloads.length) {
      html += `<div class="download-bar">${downloads.join('')}</div>`;
    }

    pane.innerHTML = html;
    tabContent.appendChild(pane);
  });
}

function switchTab(index) {
  document.querySelectorAll('.tab-btn').forEach((btn, i) => btn.classList.toggle('active', i === index));
  document.querySelectorAll('.tab-pane').forEach((pane, i) => pane.classList.toggle('active', i === index));
}

function addProgress(type, message) {
  const log = document.getElementById('progress-log');

  // Mark previous pending items as done
  if (type === 'done') {
    log.querySelectorAll('.progress-item.pending').forEach(el => {
      el.classList.remove('pending');
      el.classList.add('done');
    });
  }

  const item = document.createElement('div');
  item.className = `progress-item ${type}`;
  item.innerHTML = `<span class="progress-icon"></span><span>${message}</span>`;
  log.appendChild(item);
  item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function setLoading(loading) {
  const btn = document.getElementById('process-btn');
  const btnText = document.getElementById('btn-text');
  const spinner = document.getElementById('btn-spinner');
  btn.disabled = loading;
  btnText.textContent = loading ? 'Processing...' : 'Process Request';
  spinner.classList.toggle('hidden', !loading);
}

function showSection(id, visible) {
  document.getElementById(id).classList.toggle('hidden', !visible);
}

function clearResults() {
  activeResults = [];
  document.getElementById('tab-bar').innerHTML = '';
  document.getElementById('tab-content').innerHTML = '';
  document.getElementById('token-count').textContent = '';
}

function escapeAttr(str) {
  return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/\n/g, '\\n');
}

async function saveToJT(noteText) {
  // Show a simple prompt for job ID if we don't have it
  const jobId = prompt('Enter the JobTread Job ID to save this note to:');
  if (!jobId) return;

  const fd = new FormData();
  fd.append('job_id', jobId);
  fd.append('note_text', noteText);

  const resp = await fetch('/api/jobtread/write-note', { method: 'POST', body: fd });
  const data = await resp.json();
  if (data.written) {
    alert('Note saved to JobTread successfully!');
  } else {
    alert('Failed to save note to JobTread. Check your grant key configuration.');
  }
}
