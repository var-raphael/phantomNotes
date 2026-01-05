// Theme Toggle
const themeToggle = document.getElementById('themeToggle');
const html = document.documentElement;

// Load saved theme
const currentTheme = localStorage.getItem('theme') || 'light';
html.setAttribute('data-theme', currentTheme);
updateThemeIcon(currentTheme);

themeToggle.addEventListener('click', () => {
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
    
    // Add animation
    themeToggle.style.transform = 'rotate(360deg)';
    setTimeout(() => {
        themeToggle.style.transform = '';
    }, 300);
});

function updateThemeIcon(theme) {
    const icon = themeToggle.querySelector('i');
    if (theme === 'dark') {
        icon.className = 'fas fa-sun';
    } else {
        icon.className = 'fas fa-moon';
    }
}

// File Input Display
const fileInput = document.getElementById('files');
const fileNamesDisplay = document.getElementById('fileNames');

fileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files.length > 0) {
        if (files.length === 1) {
            fileNamesDisplay.innerHTML = `<i class="fas fa-check-circle"></i> ${files[0].name}`;
        } else {
            fileNamesDisplay.innerHTML = `<i class="fas fa-check-circle"></i> ${files.length} files selected`;
        }
        fileNamesDisplay.style.color = 'var(--success)';
    } else {
        fileNamesDisplay.innerHTML = 'Choose PDF or Images (Max 5)';
        fileNamesDisplay.style.color = '';
    }
});

// Store current summary globally
let currentSummary = null;

// Handle HTMX response
document.body.addEventListener('htmx:afterRequest', (event) => {
    if (event.detail.xhr.status === 200) {
        try {
            const response = JSON.parse(event.detail.xhr.responseText);
            
            // Check if it's an error response
            if (response.error) {
                displayError(response.error);
                return;
            }
            
            // Store the summary
            currentSummary = response;
            
            // Display the results
            displayResults(response);
        } catch (error) {
            displayError('Error parsing response');
        }
    } else {
        displayError('Error processing request. Please try again.');
    }
});

// Handle HTMX errors
document.body.addEventListener('htmx:responseError', (event) => {
    try {
        const response = JSON.parse(event.detail.xhr.responseText);
        displayError(response.error || 'An error occurred');
    } catch {
        displayError('Network error. Please check your connection.');
    }
});

function displayResults(data) {
    const container = document.getElementById('resultContainer');
    
    container.innerHTML = `
        <div class="card summary-results">
            <div class="summary-box">
                <h3>
                    <i class="fas fa-book-open"></i>
                    Chapter/Section Summaries
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
                    Export Summary
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
    
    // Scroll to results
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function displayError(message) {
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
    
    // Scroll to error
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function downloadFile(format) {
    if (!currentSummary) {
        displayError('No summary available to export');
        return;
    }
    
    // Find the clicked button and show loading state
    const clickedBtn = event.target.closest('.export-btn');
    const originalContent = clickedBtn.innerHTML;
    clickedBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Exporting...';
    clickedBtn.disabled = true;
    
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
        
        // Show success feedback
        clickedBtn.innerHTML = '<i class="fas fa-check"></i> Downloaded!';
        setTimeout(() => {
            clickedBtn.innerHTML = originalContent;
            clickedBtn.disabled = false;
        }, 2000);
        
    } catch (error) {
        displayError(`Error downloading ${format.toUpperCase()}: ${error.message}`);
        clickedBtn.innerHTML = originalContent;
        clickedBtn.disabled = false;
    }
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Drag and drop support
const fileUploadDisplay = document.querySelector('.file-upload-display');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    fileUploadDisplay.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    fileUploadDisplay.addEventListener(eventName, () => {
        fileUploadDisplay.style.borderColor = 'var(--accent)';
        fileUploadDisplay.style.background = 'var(--bg-secondary)';
    }, false);
});

['dragleave', 'drop'].forEach(eventName => {
    fileUploadDisplay.addEventListener(eventName, () => {
        fileUploadDisplay.style.borderColor = '';
        fileUploadDisplay.style.background = '';
    }, false);
});

fileUploadDisplay.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    
    fileInput.files = files;
    
    // Trigger change event
    const event = new Event('change', { bubbles: true });
    fileInput.dispatchEvent(event);
}, false);