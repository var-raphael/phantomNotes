const themeToggle = document.getElementById('themeToggle');
const html = document.documentElement;
const fileInput = document.getElementById('file');
const fileNameDisplay = document.getElementById('fileName');
const textInput = document.getElementById('textInput');
const charCount = document.getElementById('charCount');
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

let currentSummary = null;

// Theme management
const savedTheme = localStorage.getItem('theme') || 'dark';
html.setAttribute('data-theme', savedTheme);
updateThemeIcon(savedTheme);

themeToggle.addEventListener('click', () => {
    const current = html.getAttribute('data-theme');
    const newTheme = current === 'light' ? 'dark' : 'light';
    
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
    
    themeToggle.style.transform = 'rotate(360deg)';
    setTimeout(() => {
        themeToggle.style.transform = '';
    }, 300);
});

function updateThemeIcon(theme) {
    const icon = themeToggle.querySelector('i');
    icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
}

// Tab switching
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.getAttribute('data-tab');
        
        tabBtns.forEach(b => b.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        
        btn.classList.add('active');
        document.getElementById(`${tabName}-tab`).classList.add('active');
        
        // Clear inputs when switching tabs
        if (tabName === 'pdf') {
            textInput.value = '';
            updateCharCount();
        } else {
            fileInput.value = '';
            resetFileDisplay();
        }
    });
});

// File input handling
fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        fileNameDisplay.innerHTML = `<i class="fas fa-file-pdf"></i> ${file.name}`;
        fileNameDisplay.style.color = 'var(--success)';
    } else {
        resetFileDisplay();
    }
});

function resetFileDisplay() {
    fileNameDisplay.innerHTML = 'Drop your PDF here or click to browse';
    fileNameDisplay.style.color = '';
}

// Text input character counter
textInput.addEventListener('input', updateCharCount);

function updateCharCount() {
    const count = textInput.value.length;
    charCount.textContent = count.toLocaleString();
}

// Form validation before submit
document.getElementById('uploadForm').addEventListener('submit', (e) => {
    const activeTab = document.querySelector('.tab-btn.active').getAttribute('data-tab');
    
    if (activeTab === 'pdf') {
        if (!fileInput.files.length) {
            e.preventDefault();
            showError('Please upload a PDF file');
            return false;
        }
        // Clear text input to avoid sending both
        textInput.value = '';
    } else {
        if (!textInput.value.trim()) {
            e.preventDefault();
            showError('Please enter some text to summarize');
            return false;
        }
        // Clear file input to avoid sending both
        fileInput.value = '';
    }
});

// HTMX response handling
document.body.addEventListener('htmx:afterRequest', (event) => {
    if (event.detail.xhr.status === 200) {
        try {
            const response = JSON.parse(event.detail.xhr.responseText);
            
            if (response.error) {
                showError(response.error);
                return;
            }
            
            currentSummary = response;
            showResults(response);
        } catch (error) {
            showError('Failed to parse response');
        }
    } else {
        showError('Request failed. Please try again.');
    }
});

document.body.addEventListener('htmx:responseError', (event) => {
    try {
        const response = JSON.parse(event.detail.xhr.responseText);
        showError(response.error || 'An error occurred');
    } catch {
        showError('Network error. Check your connection.');
    }
});

function showResults(data) {
    const container = document.getElementById('resultContainer');
    
    container.innerHTML = `
        <div class="card summary-results">
            <div class="summary-box">
                <h3>
                    <i class="fas fa-book-open"></i>
                    Chapter Summaries
                </h3>
                <div class="summary-content">${escapeHtml(data.chapter_summaries)}</div>
            </div>
            
            <div class="summary-box">
                <h3>
                    <i class="fas fa-compress-alt"></i>
                    Overall Summary
                </h3>
                <div class="summary-content">${escapeHtml(data.overall_summary)}</div>
            </div>
            
            <div class="export-section">
                <h3>
                    <i class="fas fa-download"></i>
                    Export Options
                </h3>
                <div class="export-buttons">
                    <button class="export-btn" onclick="downloadFile('txt')">
                        <i class="fas fa-file-alt"></i>
                        TXT
                    </button>
                    <button class="export-btn" onclick="downloadFile('json')">
                        <i class="fas fa-file-code"></i>
                        JSON
                    </button>
                    <button class="export-btn" onclick="downloadFile('html')">
                        <i class="fas fa-globe"></i>
                        HTML
                    </button>
                    <button class="export-btn" onclick="downloadFile('pdf')">
                        <i class="fas fa-file-pdf"></i>
                        PDF
                    </button>
                    <button class="export-btn" onclick="downloadFile('jpg')">
                        <i class="fas fa-image"></i>
                        JPG
                    </button>
                </div>
            </div>
        </div>
    `;
    
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showError(message) {
    const container = document.getElementById('resultContainer');
    
    container.innerHTML = `
        <div class="card">
            <div class="error-message">
                <i class="fas fa-exclamation-triangle"></i>
                <div>
                    <strong>Error:</strong> ${escapeHtml(message)}
                </div>
            </div>
        </div>
    `;
    
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function downloadFile(format) {
    if (!currentSummary) {
        showError('No summary available');
        return;
    }
    
    const btn = event.target.closest('.export-btn');
    const originalContent = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Exporting...';
    btn.disabled = true;
    
    try {
        const response = await fetch(`/export/${format}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(currentSummary)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Export failed');
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `phantomnotes_${Date.now()}.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        btn.innerHTML = '<i class="fas fa-check"></i> Done!';
        setTimeout(() => {
            btn.innerHTML = originalContent;
            btn.disabled = false;
        }, 2000);
        
    } catch (error) {
        showError(`Export failed: ${error.message}`);
        btn.innerHTML = originalContent;
        btn.disabled = false;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Drag and drop
const fileDisplay = document.querySelector('.file-upload-display');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => {
    fileDisplay.addEventListener(evt, e => {
        e.preventDefault();
        e.stopPropagation();
    });
});

['dragenter', 'dragover'].forEach(evt => {
    fileDisplay.addEventListener(evt, () => {
        fileDisplay.style.borderColor = 'var(--accent)';
        fileDisplay.style.background = 'var(--bg-card)';
    });
});

['dragleave', 'drop'].forEach(evt => {
    fileDisplay.addEventListener(evt, () => {
        fileDisplay.style.borderColor = '';
        fileDisplay.style.background = '';
    });
});

fileDisplay.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
});