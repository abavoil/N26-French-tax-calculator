const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileList = document.getElementById('file-list');
const fileItems = document.getElementById('file-items');
const fileCount = document.getElementById('file-count');
const submitBtn = document.getElementById('submit-btn');
const clearBtn = document.getElementById('clear-btn');
const progressContainer = document.getElementById('progress-container');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');

let selectedFiles = [];

// Drag and drop
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '#007bff';
    dropZone.style.backgroundColor = '#e7f1ff';
});

dropZone.addEventListener('dragleave', () => {
    dropZone.style.borderColor = '#ccc';
    dropZone.style.backgroundColor = 'transparent';
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '#ccc';
    dropZone.style.backgroundColor = 'transparent';
    fileInput.files = e.dataTransfer.files;
    handleFiles();
});

fileInput.addEventListener('change', handleFiles);

function handleFiles() {
    const rawFiles = Array.from(fileInput.files);
    const validPrefixes = ['buy_order_', 'sell_order_', 'income_distribution_'];

    // Silent filter: only keep PDFs that start with valid prefixes
    selectedFiles = rawFiles.filter(f => {
        const isPdf = f.name.toLowerCase().endsWith('.pdf');
        const matchesPattern = validPrefixes.some(p => f.name.startsWith(p));
        return isPdf && matchesPattern;
    });

    if (selectedFiles.length === 0) {
        fileList.style.display = 'none';
        dropZone.style.display = 'block';
        return;
    }

    // Update accordion and file list
    fileCount.textContent = selectedFiles.length;
    updateFileList();

    fileList.style.display = 'block';
    dropZone.style.display = 'none';
}

function updateFileList() {
    fileCount.textContent = selectedFiles.length;
    fileItems.innerHTML = selectedFiles
        .map((f, i) => `
            <li class="list-group-item d-flex justify-content-between align-items-center">
                <span class="text-truncate" style="max-width: 80%;">📄 ${f.name} (${(f.size / 1024 / 1024).toFixed(1)}MB)</span>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeFile(${i})">Remove</button>
            </li>
        `)
        .join('');
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    if (selectedFiles.length === 0) {
        fileList.style.display = 'none';
        dropZone.style.display = 'block';
        fileInput.value = '';
    } else {
        updateFileList();
    }
}

clearBtn.addEventListener('click', () => {
    selectedFiles = [];
    fileList.style.display = 'none';
    dropZone.style.display = 'block';
    fileInput.value = '';
});

submitBtn.addEventListener('click', uploadFiles);

async function uploadFiles() {
    if (selectedFiles.length === 0) {
        alert('No files selected');
        return;
    }

    fileList.style.display = 'none';
    progressContainer.style.display = 'block';
    submitBtn.disabled = true;
    clearBtn.disabled = true;

    try {
        // Step 1: Initialize the session on the server
        updateProgress(0, 'Initializing session container...');
        const initResponse = await fetch('/api/session/init', { method: 'POST' });
        if (!initResponse.ok) {
            throw new Error('Could not initialize session on the server.');
        }
        const { session_id } = await initResponse.json();

        // Step 2: Upload files sequentially (0-10%)
        const total = selectedFiles.length;
        for (let idx = 0; idx < total; idx++) {
            const file = selectedFiles[idx];

            const percent = Math.round((idx / total) * 10);
            updateProgress(percent, `Uploading ${idx + 1}/${total} - ${file.name}`);

            const fileFormData = new FormData();
            fileFormData.append('file', file);

            const uploadResponse = await fetch(`/api/session/${session_id}/upload-file`, {
                method: 'POST',
                body: fileFormData
            });

            if (!uploadResponse.ok) {
                const errData = await uploadResponse.json();
                throw new Error(errData.message || errData.error || `Error processing ${file.name}`);
            }
        }

        // Step 3: Stream processing progress via SSE
        const processResponse = await fetch(`/api/session/${session_id}/process`, {
            method: 'POST'
        });

        if (!processResponse.ok) {
            const errData = await processResponse.json();
            throw new Error(errData.message || errData.error || 'Tax calculations compilation failed.');
        }

        const reader = processResponse.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = '';
        let hasFailedFiles = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            sseBuffer += decoder.decode(value, { stream: true });
            const parts = sseBuffer.split('\n\n');
            sseBuffer = parts.pop();

            for (const block of parts) {
                if (!block.trim()) continue;
                const evt = parseSSEBlock(block);
                if (!evt) continue;

                switch (evt.type) {
                    case 'progress':
                        const pct = 10 + Math.round((evt.data.current / evt.data.total) * 80);
                        updateProgress(pct, `Processing file ${evt.data.current}/${evt.data.total} - ${evt.data.file}`);
                        break;
                    case 'file_error':
                        hasFailedFiles = true;
                        break;
                    case 'phase':
                        updateProgress(90, `Compiling tax report...`);
                        break;
                    case 'complete':
                        updateProgress(100, 'All reports successfully generated!');
                        localStorage.setItem('lastSessionId', evt.data.session_id);
                        if (hasFailedFiles) {
                            showFailedFiles(evt.data.failed_files);
                        }
                        setTimeout(() => window.location.href = evt.data.results_url, 500);
                        break;
                    case 'fatal_error':
                        throw new Error(evt.data.message || evt.data.error || 'Processing failed');
                }
            }
        }

    } catch (error) {
        alert(error.message);
        resetUI();
    }
}

function parseSSEBlock(block) {
    const lines = block.trim().split('\n');
    let type = 'message';
    let data = '';
    for (const line of lines) {
        if (line.startsWith('event: ')) type = line.slice(7);
        else if (line.startsWith('data: ')) data = line.slice(6);
    }
    if (!data) return null;
    try { data = JSON.parse(data); } catch {}
    return { type, data };
}

function showFailedFiles(files) {
    const container = document.getElementById('failed-files');
    if (!container || !files || files.length === 0) return;
    const list = files.map(f => `<li><strong>${f.file}</strong>: ${f.error}</li>`).join('');
    container.innerHTML = `
        <div class="alert alert-warning mt-3">
            <h6 class="alert-heading">Some files could not be processed</h6>
            <ul class="mb-0 small">${list}</ul>
        </div>
    `;
    container.style.display = 'block';
}

function updateProgress(percent, status) {
    progressBar.style.width = percent + '%';
    progressText.textContent = status;
}

function resetUI() {
    fileList.style.display = 'block';
    progressContainer.style.display = 'none';
    submitBtn.disabled = false;
    clearBtn.disabled = false;
}
