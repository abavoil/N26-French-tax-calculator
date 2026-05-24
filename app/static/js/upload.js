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

        // Step 3: Call final computation and Excel generation
        // NOTE: The server runs in single-threaded mode (threaded=False, see
        // run.py) because macOS Vision's livetext framework stalls from background
        // threads.  This means /process-progress polling DOES NOT WORK during the
        // /process request — the bar will not advance until OCR completes.
        // The polling code below is kept for reference (dead code with threaded=False).
        updateProgress(10, 'Processing documents with OCR... (this may take a minute)');
        const processResponse = await fetch(`/api/session/${session_id}/process`, {
            method: 'POST'
        });

        if (!processResponse.ok) {
            const errData = await processResponse.json();
            throw new Error(errData.message || errData.error || 'Tax calculations compilation failed.');
        }

        updateProgress(100, 'All reports successfully generated!');

        // Save session for navigation
        localStorage.setItem('lastSessionId', session_id);

        // Wait briefly for the completed progress state to render
        setTimeout(() => {
            window.location.href = `/results/${session_id}`;
        }, 500);

    } catch (error) {
        alert(error.message);
        resetUI();
    }
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
