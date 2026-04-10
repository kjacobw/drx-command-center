/* DRX Command Center — frontend logic */

async function processRequest() {
  const brainDump = document.getElementById('brain-dump').value.trim();
  if (!brainDump) {
    alert('Please describe what you need done.');
    return;
  }

  setLoading(true);
  clearResults();
  showSection('progress-section', true);
  showSection('pdf-summary', false);
  showSection('results-section', false);
  document.getElementById('progress-log').innerHTML = '';
  addProgress('pending', 'Sending request...');

  const formData = new FormData();
  formData.append('brain_dump', brainDump);
  formData.append('carrier_override', document.getElementById('carrier-select').value);
  formData.append('write_to_jobtread', document.getElementById('write-to-jt').checked ? 'true' : 'false');

  const pdfFile = document.getElementById('pdf-upload').files[0];
  if (pdfFile) {
    formData.append('pdf_file', pdfFile);
  }

  try {
    const response = await fetch('/api/process', {
      method: 'POST',
      body: formData,
    });

    const data = await response.json();

    // Clear the "Sending request..." item
    document.getElementById('progress-log').innerHTML = '';

    // Show log entries
    if (data.log && data.log.length) {
      data.log.forEach(msg => addProgress('done', msg));
    }

    if (!data.success) {
      addProgress('error', data.error || 'An error occurred.');
      if (data.detail) {
        addProgress('error', data.detail);
      }
      setLoading(false);
      return;
    }

    // PDF summary
    if (data.roofr_summary) {
      document.getElementById('pdf-summary-text').textContent = data.roofr_summary;
      showSection('pdf-summary', true);
    }

    // Token count
    if (data.total_tokens) {
      document.getElementById('token-count').textContent = `${data.total_tokens.toLocaleString()} tokens used`;
    }

    // Render results
    if (data.results && data.results.length) {
      renderResults(data.results);
      showSection('results-section', true);
    }

  } catch (err) {
    document.getElementById('progress-log').innerHTML = '';
    addProgress('error', `Request failed: ${err.message}`);
  }

  setLoading(false);
}

function renderResults(results) {
  const tabBar = document.getElementById('tab-bar');
  const tabContent = document.getElementById('tab-content');
  tabBar.innerHTML = '';
  tabContent.innerHTML = '';

  results.forEach((result, i) => {
    const btn = document.createElement('button');
    btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = result.title || result.agent;
    btn.onclick = () => switchTab(i);
    tabBar.appendChild(btn);

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
  const item = document.createElement('div');
  item.className = `progress-item ${type}`;
  item.innerHTML = `<span class="progress-icon"></span><span>${message}</span>`;
  log.appendChild(item);
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
  document.getElementById('tab-bar').innerHTML = '';
  document.getElementById('tab-content').innerHTML = '';
  document.getElementById('token-count').textContent = '';
}

function escapeAttr(str) {
  return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/\n/g, '\\n');
}

async function saveToJT(noteText) {
  const jobId = prompt('Enter the JobTread Job ID to save this note to:');
  if (!jobId) return;

  const fd = new FormData();
  fd.append('job_id', jobId);
  fd.append('note_text', noteText);

  const resp = await fetch('/api/jobtread/write-note', { method: 'POST', body: fd });
  const data = await resp.json();
  alert(data.written ? 'Note saved to JobTread!' : 'Failed to save. Check your grant key.');
}
