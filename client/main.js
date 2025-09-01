import './style.css'

// DOM elements
const searchForm = document.getElementById('unifiedSearchForm');
const keywordsInput = document.getElementById('keywords');
const locationInput = document.getElementById('location');
const dateFilterSelect = document.getElementById('dateFilter');
const loadingDiv = document.getElementById('loading');
const resultsDiv = document.getElementById('results');

// Global state for pagination
let currentJobs = [];
let currentPage = 1;
const jobsPerPage = 30;
let lastCheckTime = null;
let pollingInterval = null;
let isManualSearchActive = false; // Track if we just did a manual search

// Initialize the app
document.addEventListener('DOMContentLoaded', () => {
    attachEventListeners();
    loadScheduledSearches();
    startAutomatedPolling(); // Only polls for automated searches
});

// FIXED: Polling that ONLY works for automated searches
function startAutomatedPolling() {
    // Clear any existing interval
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
    
    // Only poll for automated searches every 30 seconds
    pollingInterval = setInterval(async () => {
        if (!isManualSearchActive) {
            await checkForNewAutomatedSearches();
        }
    }, 30000);
    
    // Do an initial check only if no manual search is active
    if (!isManualSearchActive) {
        checkForNewAutomatedSearches();
    }
}

// FIXED: Only check for automated searches, ignore manual searches
async function checkForNewAutomatedSearches() {
    try {
        // Don't poll if we just did a manual search
        if (isManualSearchActive) {
            return;
        }
        
        // Get recent AUTOMATED searches since last check
        const checkTime = lastCheckTime || new Date(Date.now() - 5 * 60 * 1000);
        const response = await fetch(`/api/recent-automated-searches?since=${encodeURIComponent(checkTime.toISOString())}`);
        
        if (!response.ok) {
            console.error('Failed to check for automated searches');
            return;
        }

        const data = await response.json();
        
        if (data.searches && data.searches.length > 0) {
            console.log(`Found ${data.searches.length} new automated searches`);
            
            // Display each new automated search result
            data.searches.forEach((searchData, index) => {
                displayAutomatedSearchResults(searchData.search, searchData.jobs, true);
                
                // Auto-populate the main results with the most recent automated search
                // ONLY if no manual search results are showing
                if (index === data.searches.length - 1 && !hasManualSearchResults()) {
                    autoPopulateResults(searchData.search, searchData.jobs);
                }
            });
        }
        
        // Update last check time
        lastCheckTime = new Date();
        
    } catch (error) {
        console.error('Error checking for automated searches:', error);
    }
}

// Check if current results are from a manual search
function hasManualSearchResults() {
    return isManualSearchActive || document.querySelector('.manual-search-results') !== null;
}

// Load scheduled searches
async function loadScheduledSearches() {
    try {
        const response = await fetch('/api/scheduled');
        const data = await response.json();
        
        const schedules = data.scheduled_searches || [];
        displayScheduledSearches(schedules);
        
    } catch (error) {
        console.error('Error loading scheduled searches:', error);
    }
}

// FIXED: Auto-populate only if no manual search results
function autoPopulateResults(search, jobs) {
    // Only auto-populate if:
    // 1. No manual search is active
    // 2. No current results OR current results are from automated searches
    const shouldAutoPopulate = !isManualSearchActive && 
                               (currentJobs.length === 0 || 
                                document.querySelector('.automated-results') !== null);
    
    if (shouldAutoPopulate && jobs.length > 0) {
        console.log(`Auto-populating interface with ${jobs.length} jobs from automated search`);
        
        // Clear existing results
        clearJobResults();
        
        // Set the new jobs as current
        currentJobs = jobs;
        currentPage = 1;
        
        // Display the jobs
        displayCurrentPage();
        setupPagination();
        
        // Add a header indicating these are automated results
        const automatedHeader = document.createElement('div');
        automatedHeader.className = 'automated-results-header';
        automatedHeader.innerHTML = `
            <div class="message info auto-populated">
                <p class="main-message">Auto-populated with latest automated search results</p>
                <p class="search-details">
                    <strong>Keywords:</strong> "${search.keywords}" | 
                    <strong>Location:</strong> ${search.location || 'Any location'} | 
                    <strong>Time:</strong> ${search.created_at}
                </p>
                <p class="automation-note">
                    <small>This happened because you have active scheduled searches. Do a manual search to see fresh results.</small>
                </p>
            </div>
        `;
        
        // Insert before the jobs grid
        const jobsGrid = resultsDiv.querySelector('.jobs-grid');
        if (jobsGrid) {
            resultsDiv.insertBefore(automatedHeader, jobsGrid);
        }
        
        // Smooth scroll to show the new results
        setTimeout(() => {
            automatedHeader.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 500);
    }
}

// Enhanced automated search display
function displayAutomatedSearchResults(search, jobs, isNewResult = false) {
    const searchTime = search.created_at;
    const resultId = `automated-result-${search.id || Date.now()}`;
    
    // Count job sources
    const dbJobs = jobs.filter(job => job.source === 'database').length;
    const apiJobs = jobs.filter(job => job.source === 'api' || !job.source).length;
    
    // Create the automated result element
    const automatedResultsDiv = document.createElement('div');
    automatedResultsDiv.className = 'automated-results';
    automatedResultsDiv.id = resultId;
    
    const messageClass = isNewResult ? 'success' : 'info';
    const messageText = isNewResult ? 
        `New automated search completed! Found ${jobs.length} jobs` :
        `Automated search results from ${searchTime}`;
    
    let sourceBreakdown = '';
    if (dbJobs > 0 && apiJobs > 0) {
        sourceBreakdown = `<span class="source-breakdown">(${dbJobs} from database + ${apiJobs} fresh from API)</span>`;
    } else if (dbJobs > 0) {
        sourceBreakdown = `<span class="source-breakdown">(all from database)</span>`;
    } else {
        sourceBreakdown = `<span class="source-breakdown">(all fresh from API)</span>`;
    }
    
    automatedResultsDiv.innerHTML = `
        <div class="message ${messageClass} automated-search-header">
            <div class="automated-search-info">
                <p class="automated-main-message">${messageText}</p>
                <p class="automated-details">
                    <strong>Keywords:</strong> "${search.keywords}" | 
                    <strong>Location:</strong> ${search.location || 'Any location'} | 
                    <strong>Time:</strong> ${searchTime} ${sourceBreakdown}
                </p>
                <div class="automated-actions">
                    <button class="view-jobs-btn" onclick="viewAutomatedJobs('${resultId}', ${JSON.stringify(jobs).replace(/"/g, '&quot;')})">
                        View ${jobs.length} Jobs
                    </button>
                    <button class="dismiss-btn" onclick="dismissAutomatedResult('${resultId}')">
                        Dismiss
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // Add animation class if it's a new result
    if (isNewResult) {
        automatedResultsDiv.classList.add('new-result');
    }
    
    // Insert at the top of results, but after any existing automated results
    const existingAutomated = resultsDiv.querySelectorAll('.automated-results');
    if (existingAutomated.length > 0) {
        const lastAutomated = existingAutomated[existingAutomated.length - 1];
        lastAutomated.insertAdjacentElement('afterend', automatedResultsDiv);
    } else {
        resultsDiv.insertBefore(automatedResultsDiv, resultsDiv.firstChild);
    }
    
    // Auto-dismiss notification after 30 seconds for new results
    if (isNewResult) {
        setTimeout(() => {
            const element = document.getElementById(resultId);
            if (element) {
                element.classList.add('fading-out');
                setTimeout(() => {
                    if (element.parentNode) {
                        element.remove();
                    }
                }, 500);
            }
        }, 30000);
    }
    
    // Limit to maximum 3 automated notifications visible at once
    const allAutomatedResults = resultsDiv.querySelectorAll('.automated-results');
    if (allAutomatedResults.length > 3) {
        for (let i = 3; i < allAutomatedResults.length; i++) {
            allAutomatedResults[i].remove();
        }
    }
}

// Delete scheduled search
async function deleteScheduledSearch(scheduleId) {
    if (!confirm('Are you sure you want to delete this scheduled search?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/scheduled/${scheduleId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to delete scheduled search');
        }
        
        showSuccess('Scheduled search deleted successfully!');
        await loadScheduledSearches();
        
    } catch (error) {
        showError(`Error deleting scheduled search: ${error.message}`);
        console.error('Delete error:', error);
    }
}

// Attach all event listeners
function attachEventListeners() {
    // Search form submission
    searchForm.addEventListener('submit', handleSearchSubmit);
    
    // Modal handlers
    const scheduleBtn = document.getElementById('scheduleBtn');
    const recentJobsBtn = document.getElementById('recentJobsBtn');
    
    scheduleBtn.addEventListener('click', () => openModal('scheduleModal'));
    recentJobsBtn.addEventListener('click', () => openModal('recentJobsModal'));
    
    // Confirm buttons
    document.getElementById('confirmSchedule').addEventListener('click', handleScheduleConfirm);
    document.getElementById('confirmRecentJobs').addEventListener('click', handleRecentJobsConfirm);
    
    // Modal close handlers
    document.querySelectorAll('.modal .close, .cancel-btn').forEach(btn => {
        btn.addEventListener('click', closeModals);
    });
    
    // Close modal when clicking outside
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModals();
            }
        });
    });
}

// FIXED: Handle search form submission
async function handleSearchSubmit(e) {
    e.preventDefault();
    
    const keywords = keywordsInput.value.trim();
    const location = locationInput.value.trim();
    const dateFilter = dateFilterSelect.value;
    
    if (!keywords) {
        showError('Please enter job keywords');
        return;
    }
    
    // Mark that a manual search is starting
    isManualSearchActive = true;
    
    await performManualSearch(keywords, location, dateFilter);
}

// FIXED: Perform manual search that returns complete results immediately
async function performManualSearch(keywords, location, dateFilterDays) {
    showLoading(true);
    clearResults();
    currentJobs = [];
    currentPage = 1;
    
    try {
        const requestBody = {
            keywords: keywords,
            location: location || null,
            date_filter_days: dateFilterDays ? parseInt(dateFilterDays) : null,
            schedule: false // This is a manual search
        };
        
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        showLoading(false);
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to fetch jobs');
        }
        
        if (data.jobs && data.jobs.length > 0) {
            // Set the complete results immediately
            currentJobs = data.jobs;
            displayCurrentPage();
            setupPagination();
            
            // Add manual search header to prevent auto-population
            addManualSearchHeader(data);
            
            // Show enhanced success message with breakdown
            if (data.result_breakdown) {
                const breakdown = data.result_breakdown;
                showEnhancedSuccess(`Found ${data.jobs.length} jobs total`, breakdown);
            } else {
                showSuccess(`Found ${data.jobs.length} jobs`);
            }
        } else {
            showNoResults();
        }
        
        // Manual search stays active until user takes another action
        // No arbitrary timer - user controls when automation resumes
        
    } catch (error) {
        showLoading(false);
        isManualSearchActive = false;
        showError(`Error fetching jobs: ${error.message}`);
        console.error('Search error:', error);
    }
}

// Add manual search header to prevent auto-population
function addManualSearchHeader(data) {
    const manualHeader = document.createElement('div');
    manualHeader.className = 'manual-search-results';
    manualHeader.innerHTML = `
        <div class="message success manual-search-header">
            <p class="main-message">Manual Search Results</p>
            <p class="search-details">
                Complete results with ${data.result_breakdown.from_database} from database + ${data.result_breakdown.new_from_api} fresh from API
            </p>
            <p class="automation-note">
                <small>Automated search notifications are paused. Schedule a search or refresh the page to resume automation.</small>
            </p>
        </div>
    `;
    
    // Insert before the jobs grid
    const jobsGrid = resultsDiv.querySelector('.jobs-grid');
    if (jobsGrid) {
        resultsDiv.insertBefore(manualHeader, jobsGrid);
    }
}

// Enhanced success message with result breakdown
function showEnhancedSuccess(message, breakdown) {
    const successDiv = document.createElement('div');
    successDiv.className = 'message success enhanced-success';
    
    let breakdownText = '';
    if (breakdown) {
        breakdownText = `
            <div class="result-breakdown">
                <div class="breakdown-item">
                    <span class="breakdown-number">${breakdown.from_database}</span>
                    <span class="breakdown-label">from database</span>
                </div>
                <div class="breakdown-separator">+</div>
                <div class="breakdown-item">
                    <span class="breakdown-number">${breakdown.new_from_api}</span>
                    <span class="breakdown-label">new from API</span>
                </div>
                <div class="breakdown-separator">=</div>
                <div class="breakdown-item total">
                    <span class="breakdown-number">${breakdown.total}</span>
                    <span class="breakdown-label">total jobs</span>
                </div>
            </div>
        `;
    }
    
    successDiv.innerHTML = `
        <p class="main-message">${message}</p>
        ${breakdownText}
    `;
    
    resultsDiv.insertBefore(successDiv, resultsDiv.firstChild);
    
    // Auto-remove success message after 5 seconds
    setTimeout(() => {
        if (successDiv.parentNode) {
            successDiv.remove();
        }
    }, 5000);
}

// Handle schedule confirmation
async function handleScheduleConfirm() {
    const keywords = keywordsInput.value.trim();
    const location = locationInput.value.trim();
    const frequency = document.getElementById('frequency').value;
    const dateFilter = dateFilterSelect.value;
    
    if (!keywords) {
        showError('Please enter keywords for scheduled search');
        return;
    }
    
    try {
        const requestBody = {
            keywords: keywords,
            location: location || null,
            frequency: frequency,
            date_filter_days: dateFilter ? parseInt(dateFilter) : null,
            schedule: true
        };
        
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to schedule search');
        }
        
        showSuccess('Search scheduled successfully! Automated search will start running and you\'ll see notifications.');
        closeModals();
        await loadScheduledSearches();
        
        // FIXED: Re-enable automated polling immediately when user creates a scheduled search
        isManualSearchActive = false;
        console.log('Automated polling re-enabled after scheduling search');
        
    } catch (error) {
        showError(`Error scheduling search: ${error.message}`);
        console.error('Schedule error:', error);
    }
}

// Handle recent jobs confirmation
async function handleRecentJobsConfirm() {
    const searchesBack = document.getElementById('searchesBack').value;
    closeModals();
    await loadRecentJobs(searchesBack);
}

// Load recent jobs
async function loadRecentJobs(searchesBack) {
    showLoading(true);
    clearResults();
    currentJobs = [];
    currentPage = 1;
    isManualSearchActive = true; // Prevent auto-population
    
    try {
        const response = await fetch(`/api/recent-jobs?searches_back=${searchesBack}`);
        const data = await response.json();
        
        showLoading(false);
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to fetch recent jobs');
        }
        
        if (data.jobs && data.jobs.length > 0) {
            currentJobs = data.jobs;
            displayCurrentPage();
            setupPagination();
            displayRecentJobsHeader(data.searches);
            showSuccess(`Found ${data.total_jobs} jobs from ${data.searches.length} recent searches`);
        } else {
            showNoResults();
        }
        
        // Recent jobs view stays active until user takes another action
        
    } catch (error) {
        showLoading(false);
        isManualSearchActive = false;
        showError(`Error fetching recent jobs: ${error.message}`);
        console.error('Recent jobs error:', error);
    }
}

// Display recent jobs header
function displayRecentJobsHeader(searches) {
    const searchInfo = searches.map((search, index) => 
        `${index + 1}. "${search.keywords}" in "${search.location || 'Any'}" (${search.results_count} results) - ${new Date(search.created_at).toLocaleString()}`
    ).join('<br>');
    
    const recentJobsHeader = `
        <div class="recent-jobs-header manual-search-results">
            <h3>Recent Jobs from ${searches.length} searches:</h3>
            <div class="search-details">${searchInfo}</div>
        </div>
    `;
    
    resultsDiv.insertAdjacentHTML('afterbegin', recentJobsHeader);
}

// Display current page of jobs
function displayCurrentPage() {
    const startIndex = (currentPage - 1) * jobsPerPage;
    const endIndex = startIndex + jobsPerPage;
    const jobsToShow = currentJobs.slice(startIndex, endIndex);
    
    const jobCards = jobsToShow.map(job => createEnhancedJobCard(job)).join('');
    const jobsGrid = `<div class="jobs-grid">${jobCards}</div>`;
    
    // Remove existing jobs grid but preserve headers
    const existingGrid = resultsDiv.querySelector('.jobs-grid');
    if (existingGrid) {
        existingGrid.remove();
    }
    
    // Add new jobs grid
    resultsDiv.insertAdjacentHTML('beforeend', jobsGrid);
}

// Enhanced job card creation
function createEnhancedJobCard(job) {
    const datePosted = job.date_posted_formatted || 
                      (job.date_posted ? new Date(job.date_posted).toLocaleDateString() : 'Recently');
    const salary = job.salary_range ? `<p><strong>Salary:</strong> ${job.salary_range}</p>` : '';
    
    // Determine job source and create appropriate indicator
    const source = job.source || 'api';
    const sourceClass = source === 'database' ? 'database-job' : 'api-job';
    const sourceLabel = source === 'database' ? 'From Database' : 'Fresh from API';
    
    // Check if this is a recent job (has search info)
    const searchInfo = job.search_keywords ? 
        `<p class="search-source"><strong>From search:</strong> "${job.search_keywords}" in "${job.search_location || 'Any location'}"</p>` : '';
    
    return `
        <div class="job-card ${sourceClass} ${job.search_keywords ? 'recent-job-card' : ''}">
            <div class="job-header">
                <h3 class="job-title">${escapeHtml(job.title)}</h3>
                <div class="job-meta">
                    <span class="job-date">${datePosted}</span>
                    <span class="job-source-indicator ${source}">${sourceLabel}</span>
                </div>
            </div>
            <div class="job-details">
                <p><strong>Company:</strong> ${escapeHtml(job.company)}</p>
                <p><strong>Location:</strong> ${escapeHtml(job.location)}</p>
                ${salary}
                ${searchInfo}
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

// Setup pagination
function setupPagination() {
    const paginationDiv = document.getElementById('pagination');
    const totalPages = Math.ceil(currentJobs.length / jobsPerPage);
    
    if (totalPages <= 1) {
        paginationDiv.classList.add('hidden');
        return;
    }
    
    paginationDiv.classList.remove('hidden');
    
    let paginationHTML = '<div class="pagination-controls">';
    
    // Previous button
    if (currentPage > 1) {
        paginationHTML += `<button class="pagination-btn" data-page="${currentPage - 1}">← Previous</button>`;
    }
    
    // Page numbers
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    if (startPage > 1) {
        paginationHTML += `<button class="pagination-btn" data-page="1">1</button>`;
        if (startPage > 2) {
            paginationHTML += '<span class="pagination-ellipsis">...</span>';
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        const activeClass = i === currentPage ? 'active' : '';
        paginationHTML += `<button class="pagination-btn ${activeClass}" data-page="${i}">${i}</button>`;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            paginationHTML += '<span class="pagination-ellipsis">...</span>';
        }
        paginationHTML += `<button class="pagination-btn" data-page="${totalPages}">${totalPages}</button>`;
    }
    
    // Next button
    if (currentPage < totalPages) {
        paginationHTML += `<button class="pagination-btn" data-page="${currentPage + 1}">Next →</button>`;
    }
    
    paginationHTML += '</div>';
    
    // Enhanced pagination info with source breakdown
    if (currentJobs.length > 0) {
        const dbJobs = currentJobs.filter(job => job.source === 'database').length;
        const apiJobs = currentJobs.filter(job => job.source === 'api' || !job.source).length;
        
        paginationHTML += `
            <div class="pagination-info enhanced">
                <span>Showing ${((currentPage - 1) * jobsPerPage) + 1}-${Math.min(currentPage * jobsPerPage, currentJobs.length)} of ${currentJobs.length} jobs</span>
                <div class="pagination-stat">
                    <span class="stat-indicator database"></span>
                    <span>${dbJobs} from database</span>
                </div>
                <div class="pagination-stat">
                    <span class="stat-indicator api"></span>
                    <span>${apiJobs} from API</span>
                </div>
            </div>
        `;
    }
    
    paginationDiv.innerHTML = paginationHTML;
    
    // Attach click handlers to pagination buttons
    paginationDiv.querySelectorAll('.pagination-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const newPage = parseInt(e.target.dataset.page);
            if (newPage !== currentPage) {
                currentPage = newPage;
                displayCurrentPage();
                setupPagination();
                
                // Scroll to top of results
                resultsDiv.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
}

// Global functions for automated result interactions
window.viewAutomatedJobs = function(resultId, jobs) {
    // Only allow viewing automated jobs if no manual search is active
    if (isManualSearchActive) {
        return;
    }
    
    currentJobs = jobs;
    currentPage = 1;
    
    // Clear any existing job results but keep automated headers
    clearJobResults();
    
    displayCurrentPage();
    setupPagination();
    
    // Scroll to jobs
    const jobsGridNew = resultsDiv.querySelector('.jobs-grid');
    if (jobsGridNew) {
        jobsGridNew.scrollIntoView({ behavior: 'smooth' });
    }
};

window.dismissAutomatedResult = function(resultId) {
    const element = document.getElementById(resultId);
    if (element) {
        element.classList.add('fading-out');
        setTimeout(() => {
            if (element.parentNode) {
                element.remove();
            }
        }, 300);
    }
};

// Display scheduled searches
function displayScheduledSearches(scheduledSearches) {
    const scheduledGrid = document.querySelector('.scheduled-grid');
    
    if (scheduledSearches.length === 0) {
        scheduledGrid.innerHTML = '<p class="no-schedules">No scheduled searches yet.</p>';
        return;
    }
    
    const scheduleCards = scheduledSearches.map(schedule => createScheduleCard(schedule)).join('');
    scheduledGrid.innerHTML = scheduleCards;
    
    // Attach delete handlers
    scheduledGrid.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const scheduleId = e.target.dataset.scheduleId;
            await deleteScheduledSearch(scheduleId);
        });
    });
}

// Create individual schedule card
function createScheduleCard(schedule) {
    const nextRun = schedule.next_run ? new Date(schedule.next_run).toLocaleString() : 'Soon';
    const lastRun = schedule.last_run ? new Date(schedule.last_run).toLocaleString() : 'Never';
    
    return `
        <div class="scheduled-card">
            <div class="scheduled-header">
                <h4>${escapeHtml(schedule.keywords)}</h4>
                <button class="delete-btn" data-schedule-id="${schedule.id}" title="Delete scheduled search">×</button>
            </div>
            <div class="scheduled-details">
                <p><strong>Location:</strong> ${escapeHtml(schedule.location || 'Any')}</p>
                <p><strong>Frequency:</strong> ${formatFrequency(schedule.frequency)}</p>
                <p><strong>Date Filter:</strong> ${schedule.date_filter_days ? `Last ${schedule.date_filter_days} days` : 'All time'}</p>
                <p><strong>Status:</strong> <span class="status ${schedule.is_active ? 'active' : 'inactive'}">${schedule.is_active ? 'Active' : 'Inactive'}</span></p>
                <p><strong>Next Run:</strong> ${nextRun}</p>
                <p><strong>Last Run:</strong> ${lastRun}</p>
            </div>
        </div>
    `;
}

// Format frequency for display
function formatFrequency(frequency) {
    const frequencyMap = {
        '1min': 'Every Minute',
        'hourly': 'Every Hour',
        '2hours': 'Every 2 Hours',
        '3hours': 'Every 3 Hours', 
        '6hours': 'Every 6 Hours',
        'daily': 'Daily',
        'weekly': 'Weekly'
    };
    return frequencyMap[frequency] || frequency;
}

// Modal functions
function openModal(modalId) {
    document.getElementById(modalId).classList.remove('hidden');
}

function closeModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.add('hidden');
    });
}

// Utility functions
function showLoading(show) {
    loadingDiv.classList.toggle('hidden', !show);
}

function clearResults() {
    resultsDiv.innerHTML = '';
    document.getElementById('pagination').classList.add('hidden');
}

// Clear only job results but keep notifications
function clearJobResults() {
    const jobsGrid = resultsDiv.querySelector('.jobs-grid');
    if (jobsGrid) {
        jobsGrid.remove();
    }
    
    const automatedHeader = resultsDiv.querySelector('.automated-results-header');
    if (automatedHeader) {
        automatedHeader.remove();
    }
    
    const manualHeader = resultsDiv.querySelector('.manual-search-results');
    if (manualHeader) {
        manualHeader.remove();
    }
    
    document.getElementById('pagination').classList.add('hidden');
}

function showError(message) {
    resultsDiv.innerHTML = `
        <div class="message error">
            <p>${message}</p>
        </div>
    `;
}

function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'message success';
    successDiv.innerHTML = `<p>${message}</p>`;
    resultsDiv.insertBefore(successDiv, resultsDiv.firstChild);
    
    // Auto-remove success message after 3 seconds
    setTimeout(() => {
        if (successDiv.parentNode) {
            successDiv.remove();
        }
    }, 3000);
}

function showNoResults() {
    resultsDiv.innerHTML = `
        <div class="message info">
            <p>No jobs found. Try different keywords or location.</p>
        </div>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
});

// Hot reload indicator
if (import.meta.hot) {
    console.log('Vite hot reload is active!');
}

console.log('Fixed Job Hunting Bot - Manual vs Automated Search Handling loaded successfully!');