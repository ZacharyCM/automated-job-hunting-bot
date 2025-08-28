import './style.css'

// DOM elements
const searchForm = document.getElementById('jobSearchForm');
const keywordsInput = document.getElementById('keywords');
const locationInput = document.getElementById('location');
const loadingDiv = document.getElementById('loading');
const resultsDiv = document.getElementById('results');

// Search form handler
searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const keywords = keywordsInput.value.trim();
    const location = locationInput.value.trim();
    
    if (!keywords) {
        showError('Please enter job keywords');
        return;
    }
    
    showLoading(true);
    clearResults();
    
    try {
        const params = new URLSearchParams({
            keywords: keywords,
            ...(location && { location: location })
        });
        
        const response = await fetch(`/api/jobs?${params}`);
        const data = await response.json();
        
        showLoading(false);
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to fetch jobs');
        }
        
        if (data.jobs && data.jobs.length > 0) {
            displayJobs(data.jobs);
            showSuccess(`Found ${data.jobs.length} jobs`);
        } else {
            showNoResults();
        }
    } catch (error) {
        showLoading(false);
        showError(`Error fetching jobs: ${error.message}`);
        console.error('Search error:', error);
    }
});



// Display jobs function
function displayJobs(jobs) {
    const jobCards = jobs.map(job => createJobCard(job)).join('');
    resultsDiv.innerHTML = `
        <div class="jobs-grid">
            ${jobCards}
        </div>
    `;
}

// Create individual job card
function createJobCard(job) {
    const datePosted = job.date_posted ? new Date(job.date_posted).toLocaleDateString() : 'Recently';
    const salary = job.salary_range ? `<p><strong>Salary:</strong> ${job.salary_range}</p>` : '';
    
    return `
        <div class="job-card">
            <div class="job-header">
                <h3 class="job-title">${escapeHtml(job.title)}</h3>
                <span class="job-date">${datePosted}</span>
            </div>
            <div class="job-details">
                <p><strong>Company:</strong> ${escapeHtml(job.company)}</p>
                <p><strong>Location:</strong> ${escapeHtml(job.location)}</p>
                ${salary}
                ${job.description ? `<p class="job-description">${escapeHtml(job.description.slice(0, 150))}...</p>` : ''}
            </div>
            <div class="job-actions">
                <a href="${job.apply_link}" target="_blank" rel="noopener noreferrer" class="apply-btn">
                    Apply Now →
                </a>
            </div>
        </div>
    `;
}

// Utility functions
function showLoading(show) {
    loadingDiv.classList.toggle('hidden', !show);
}

function clearResults() {
    resultsDiv.innerHTML = '';
}

function showError(message) {
    resultsDiv.innerHTML = `
        <div class="message error">
            <p>❌ ${message}</p>
        </div>
    `;
}

function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'message success';
    successDiv.innerHTML = `<p>✅ ${message}</p>`;
    resultsDiv.insertBefore(successDiv, resultsDiv.firstChild);
}

function showNoResults() {
    resultsDiv.innerHTML = `
        <div class="message info">
            <p>🔍 No jobs found. Try different keywords or location.</p>
        </div>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Hot reload indicator
if (import.meta.hot) {
    console.log('🔥 Vite hot reload is active!');
}

console.log('Job Hunting Bot loaded successfully!');