function getSecureConfirmMessage(key, fallback = 'Are you sure?') {
    try {
        if (typeof confirmMessages === 'object' && confirmMessages !== null) {
            const message = confirmMessages[key];
            if (typeof message === 'string') {
                // Basic XSS prevention for confirm messages
                return message.replace(/[<>"']/g, function(match) {
                    const htmlEntities = {
                        '<': '&lt;',
                        '>': '&gt;',
                        '"': '&quot;',
                        "'": '&#39;'
                    };
                    return htmlEntities[match];
                });
            }
        }
        console.warn(`Confirm message not found for key: ${key}`);
        return fallback;
    } catch (error) {
        console.error('Error accessing confirm message:', error);
        return fallback;
    }
}

// SECURITY: Sanitize text content before DOM manipulation
function sanitizeTextContent(text) {
    if (typeof text !== 'string') return '';
    // Remove HTML tags and encode dangerous characters
    return text.replace(/<[^>]*>/g, '') // Strip HTML tags
               .replace(/[<>"'&]/g, function(match) {
                   const htmlEntities = {
                       '<': '&lt;',
                       '>': '&gt;',
                       '"': '&quot;',
                       "'": '&#39;',
                       '&': '&amp;'
                   };
                   return htmlEntities[match];
               });
}

// Set background colors for profile avatars from data attributes
document.addEventListener('DOMContentLoaded', function() {
    const avatars = document.querySelectorAll('[data-bg-color]');
    avatars.forEach(avatar => {
        const bgColor = avatar.dataset.bgColor;
        if (bgColor) {
            avatar.style.backgroundColor = bgColor;
        }
    });
});

// Function to toggle additional changes visibility
function toggleAdditionalChanges(button, activityIndex) {
    const container = document.querySelector(`.additional-changes-${activityIndex}`);
    const showMoreText = button.querySelector('.show-more-text');
    const showLessText = button.querySelector('.show-less-text');
    const isExpanded = button.getAttribute('aria-expanded') === 'true';

    // Toggle visibility
    container.classList.toggle('hidden');
    showMoreText.classList.toggle('hidden');
    showLessText.classList.toggle('hidden');

    // Update aria-expanded state
    button.setAttribute('aria-expanded', !isExpanded);

    // Smooth scroll to show newly revealed content if expanding
    if (!isExpanded) {
        container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// Function to render the Completion Rate Line Chart
function renderCompletionRateChart() {
    const ctx = document.getElementById('completionRateChart');

    if (!ctx) {
        console.error("Completion Rate Chart canvas element not found!");
        return;
    }

    // Fake data for demonstration
    const data = {
        labels: ['Period 1', 'Period 2', 'Period 3', 'Period 4', 'Period 5'], // Example periods
        datasets: [{
            label: 'Completion Rate (%)',
            data: [65, 72, 78, 85, 90], // Example completion rates
            borderColor: 'rgb(59, 130, 246)', // Blue color
            tension: 0.1,
            fill: false
        }]
    };

    new Chart(ctx, {
        type: 'line',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false, // Allow height to be controlled by container
            plugins: {
                title: {
                    display: true,
                    text: getSecureConfirmMessage('completionRateOverTime', 'Completion Rate Over Time')
                },
                legend: {
                    display: false // Hide legend if only one dataset
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: 'Completion (%)'
                    }
                }
            }
        }
    });
}

// Function to render the Data Quality Bar Chart
function renderDataQualityChart() {
    const ctx = document.getElementById('dataQualityChart');

     if (!ctx) {
        console.error("Data Quality Chart canvas element not found!");
        return;
    }

    // Fake data for demonstration
    const data = {
        labels: ['Period 1', 'Period 2', 'Period 3', 'Period 4', 'Period 5'], // Example periods
        datasets: [{
            label: getSecureConfirmMessage('dataQualityIndex', 'Data Quality Index'),
            data: [7.5, 8.0, 8.5, 8.8, 9.1], // Example quality scores (out of 10)
            backgroundColor: 'rgb(168, 85, 247)', // Purple color
            borderColor: 'rgb(147, 51, 234)', // Darker purple
            borderWidth: 1
        }]
    };

    new Chart(ctx, {
        type: 'bar',
        data: data,
         options: {
            responsive: true,
            maintainAspectRatio: false, // Allow height to be controlled by container
            plugins: {
                title: {
                    display: true,
                    text: getSecureConfirmMessage('dataQualityIndexTrend', 'Data Quality Index Trend')
                },
                 legend: {
                    display: false // Hide legend if only one dataset
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 10, // Assuming index is out of 10
                     title: {
                        display: true,
                        text: getSecureConfirmMessage('qualityIndex', 'Quality Index')
                    }
                }
            }
        }
    });
}

// Render charts and set up event listeners when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    renderCompletionRateChart();
    renderDataQualityChart();

    // Initialize filtering and pagination for Past Assignments
    initializeFilteringAndPagination();

    // NEW: JavaScript for the Self-Report Templates button and dropdown
    const selfReportButton = document.getElementById('self-report-templates-button');
    const selfReportDropdown = document.getElementById('self-report-templates-dropdown');

    if (selfReportButton && selfReportDropdown) {
        selfReportButton.addEventListener('click', function() {
            const isExpanded = selfReportButton.getAttribute('aria-expanded') === 'true';
            selfReportButton.setAttribute('aria-expanded', !isExpanded);
            selfReportDropdown.classList.toggle('hidden');
        });

        // Close the dropdown if the user clicks outside of it
        document.addEventListener('click', function(event) {
            if (!selfReportButton.contains(event.target) && !selfReportDropdown.contains(event.target)) {
                selfReportDropdown.classList.add('hidden');
                selfReportButton.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // NEW: JavaScript for the Past Assignments section toggle
    const approvedAssignmentsHeader = document.getElementById('approved-assignments-header');
    const approvedAssignmentsContent = document.getElementById('approved-assignments-content');
    const toggleApprovedAssignmentsButton = document.getElementById('toggle-approved-assignments');
    const approvedAssignmentsHint = document.getElementById('approved-assignments-hint');
    const approvedAssignmentsToggleText = document.getElementById('approved-assignments-toggle-text');

    if (approvedAssignmentsHeader && approvedAssignmentsContent && toggleApprovedAssignmentsButton) {
        function setExpandedState(isExpanded) {
            // aria-expanded on both header (role=button) and the actual button
            approvedAssignmentsHeader.setAttribute('aria-expanded', String(isExpanded));
            toggleApprovedAssignmentsButton.setAttribute('aria-expanded', String(isExpanded));

            // Rotate only the arrow icon (not the Show/Hide text)
            const chevron = document.getElementById('approved-assignments-chevron');
            if (chevron) {
                if (isExpanded) {
                    chevron.classList.remove('rotate-0');
                    chevron.classList.add('rotate-180'); // Rotate up when expanded
                } else {
                    chevron.classList.remove('rotate-180');
                    chevron.classList.add('rotate-0'); // Rotate down when collapsed
                }
            }

            // Update microcopy (optional elements)
            if (approvedAssignmentsHint) {
                approvedAssignmentsHint.textContent = isExpanded ? 'Click to collapse' : 'Click to expand';
            }
            if (approvedAssignmentsToggleText) {
                approvedAssignmentsToggleText.textContent = isExpanded ? 'Hide' : 'Show';
            }
            toggleApprovedAssignmentsButton.title = isExpanded ? 'Hide past assignments' : 'Show past assignments';
        }

        function toggleApprovedAssignments() {
            const isHidden = approvedAssignmentsContent.classList.contains('hidden');
            // if it was hidden, we're expanding; if it was visible, we're collapsing
            approvedAssignmentsContent.classList.toggle('hidden');
            setExpandedState(isHidden);
        }

        // Click anywhere on the header row toggles
        approvedAssignmentsHeader.addEventListener('click', function() {
            toggleApprovedAssignments();
        });

        // Keyboard support for the header "button"
        approvedAssignmentsHeader.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                toggleApprovedAssignments();
            }
        });

        // Also make the chevron/button itself clickable (without double-triggering)
        toggleApprovedAssignmentsButton.addEventListener('click', function(event) {
            event.stopPropagation();
            toggleApprovedAssignments();
        });

        // Ensure initial state is consistent
        setExpandedState(!approvedAssignmentsContent.classList.contains('hidden'));
    }

    // NEW: JavaScript for filtering and pagination of Past Assignments
    function initializeFilteringAndPagination() {
        const periodSlicer = document.getElementById('period-slicer');
        const templateSlicer = document.getElementById('template-slicer');
        const statusSlicer = document.getElementById('status-slicer');
        const approvedAssignmentsList = document.getElementById('approved-assignments-list'); // Get the table

        // Pagination variables
        let currentPage = 1;
        const recordsPerPage = 10;

        if (periodSlicer && templateSlicer && statusSlicer && approvedAssignmentsList) {



            // Function to get all visible rows after filtering
            function getVisibleRows() {
                const allRows = approvedAssignmentsList.querySelectorAll('tbody tr.approved-assignment-item');
                const visibleRows = [];

                allRows.forEach((row, index) => {
                    const itemPeriod = row.getAttribute('data-period') || '';
                    const itemTemplate = row.getAttribute('data-template') || '';
                    const itemStatus = row.getAttribute('data-status') || '';
                    const selectedPeriod = periodSlicer.value;
                    const selectedTemplate = templateSlicer.value;
                    const selectedStatus = statusSlicer.value;

                    // Check if the item matches the selected filters
                    const periodMatch = (selectedPeriod === '' || itemPeriod === selectedPeriod);
                    const templateMatch = (selectedTemplate === '' || itemTemplate === selectedTemplate);
                    const statusMatch = (selectedStatus === '' || itemStatus === selectedStatus);

                    if (periodMatch && templateMatch && statusMatch) {
                        visibleRows.push(row);
                    }
                });

                return visibleRows;
            }

            // Function to show/hide rows based on current page
            function showPage(page) {
                const visibleRows = getVisibleRows();
                const totalPages = Math.ceil(visibleRows.length / recordsPerPage);

                // Ensure page is within valid range
                if (page < 1) page = 1;
                if (page > totalPages) page = totalPages;

                currentPage = page;

                // First, hide all rows
                const allRows = approvedAssignmentsList.querySelectorAll('tbody tr.approved-assignment-item');
                allRows.forEach(row => {
                    row.style.display = 'none';
                });

                // Then show only the filtered rows for current page
                const startIndex = (currentPage - 1) * recordsPerPage;
                const endIndex = startIndex + recordsPerPage;

                for (let i = startIndex; i < endIndex && i < visibleRows.length; i++) {
                    visibleRows[i].style.display = '';
                }

                // Update pagination controls
                updatePaginationControls(visibleRows.length, totalPages);
            }

            // Function to update pagination controls
            function updatePaginationControls(totalRecords, totalPages) {
                const startRecord = totalRecords > 0 ? (currentPage - 1) * recordsPerPage + 1 : 0;
                const endRecord = Math.min(currentPage * recordsPerPage, totalRecords);

                // Update record count display
                document.getElementById('start-record').textContent = startRecord;
                document.getElementById('end-record').textContent = endRecord;
                document.getElementById('total-records').textContent = totalRecords;

                // Update previous/next buttons
                const prevButtons = document.querySelectorAll('#prev-page, #prev-page-mobile');
                const nextButtons = document.querySelectorAll('#next-page, #next-page-mobile');

                prevButtons.forEach(btn => {
                    btn.disabled = currentPage <= 1;
                });

                nextButtons.forEach(btn => {
                    btn.disabled = currentPage >= totalPages;
                });

                // Generate page numbers
                const pageNumbersContainer = document.getElementById('page-numbers');
                pageNumbersContainer.replaceChildren();

                const maxVisiblePages = 5;
                let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
                let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

                if (endPage - startPage + 1 < maxVisiblePages) {
                    startPage = Math.max(1, endPage - maxVisiblePages + 1);
                }

                for (let i = startPage; i <= endPage; i++) {
                    const pageButton = document.createElement('button');
                    pageButton.className = `relative inline-flex items-center px-4 py-2 border text-sm font-medium ${
                        i === currentPage
                            ? 'z-10 bg-blue-50 border-blue-500 text-blue-600'
                            : 'bg-white border-gray-300 text-gray-500 hover:bg-gray-50'
                    }`;
                    pageButton.textContent = i;
                    pageButton.addEventListener('click', () => showPage(i));
                    pageNumbersContainer.appendChild(pageButton);
                }
            }

            // Function to apply filters and reset pagination
            function applyFilters() {
                currentPage = 1; // Reset to first page when filters change
                showPage(currentPage);
            }

            // Add event listeners to the slicers
            try {
                periodSlicer.addEventListener('change', function(e) {
                    applyFilters();
                });
                templateSlicer.addEventListener('change', function(e) {
                    applyFilters();
                });
                statusSlicer.addEventListener('change', function(e) {
                    applyFilters();
                });
            } catch (error) {
                console.error('Error attaching event listeners:', error);
            }

            // Add event listeners to pagination buttons
            try {
                document.getElementById('prev-page').addEventListener('click', () => {
                    if (currentPage > 1) showPage(currentPage - 1);
                });

                document.getElementById('next-page').addEventListener('click', () => {
                    const visibleRows = getVisibleRows();
                    const totalPages = Math.ceil(visibleRows.length / recordsPerPage);
                    if (currentPage < totalPages) showPage(currentPage + 1);
                });

                document.getElementById('prev-page-mobile').addEventListener('click', () => {
                    if (currentPage > 1) showPage(currentPage - 1);
                });

                document.getElementById('next-page-mobile').addEventListener('click', () => {
                    const visibleRows = getVisibleRows();
                    const totalPages = Math.ceil(visibleRows.length / recordsPerPage);
                    if (currentPage < totalPages) showPage(currentPage + 1);
                });
            } catch (error) {
                console.error('Error attaching pagination event listeners:', error);
            }

            // Initialize pagination on page load
            showPage(1);
        }
    }

    // Initialize Enhanced Search Dropdown for Countries (only if elements exist)
    if (typeof EnhancedSearchDropdown !== 'undefined') {
        const searchInput = document.getElementById('search_input');
        const searchDropdown = document.getElementById('search_dropdown');
        if (searchInput && searchDropdown) {
            new EnhancedSearchDropdown({
                searchInputId: 'search_input',
                dropdownId: 'search_dropdown',
                listId: 'search_list',
                noResultsId: 'no_results',
                formId: 'search_form',
                selectId: 'search_select',
                clearSearchId: 'clear_search'
            });
        }
    }

    // Handle form confirmations
    function resetSubmitGuardState(form) {
        if (window.FormSubmitGuard && typeof window.FormSubmitGuard.reset === 'function') {
            window.FormSubmitGuard.reset(form);
        }
    }

    document.addEventListener('submit', function(event) {
        const form = event.target;

        if (form.classList.contains('delete-self-report-form')) {
            if (form.dataset.confirmed === 'true') { delete form.dataset.confirmed; return; }
            event.preventDefault();
            resetSubmitGuardState(form);
            const msg = getSecureConfirmMessage('deleteSelfReport', 'Are you sure you want to delete this self-report?');
            if (window.showDangerConfirmation) {
                window.showDangerConfirmation(msg, () => { form.dataset.confirmed = 'true'; form.requestSubmit ? form.requestSubmit() : form.submit(); }, null, 'Delete', 'Cancel', 'Confirm Delete');
            } else if (window.showConfirmation) {
                window.showConfirmation(msg, () => { form.dataset.confirmed = 'true'; form.requestSubmit ? form.requestSubmit() : form.submit(); }, null, 'Delete', 'Cancel', 'Confirm Delete');
            } else {
                console.warn('Confirmation dialog not available:', msg);
                return false;
            }
            return false;
        }

        if (form.classList.contains('approve-assignment-form')) {
            if (form.dataset.confirmed === 'true') { delete form.dataset.confirmed; return; }
            event.preventDefault();
            resetSubmitGuardState(form);
            const msg = getSecureConfirmMessage('approveAssignment', 'Are you sure you want to approve this assignment?');
            if (window.showConfirmation) {
                window.showConfirmation(msg, () => { form.dataset.confirmed = 'true'; form.requestSubmit ? form.requestSubmit() : form.submit(); }, null, 'Approve', 'Cancel', 'Approve Assignment?');
            } else {
                console.warn('Confirmation dialog not available:', msg);
                return false;
            }
            return false;
        }

        if (form.classList.contains('reopen-assignment-form')) {
            if (form.dataset.confirmed === 'true') { delete form.dataset.confirmed; return; }
            event.preventDefault();
            resetSubmitGuardState(form);
            const msg = getSecureConfirmMessage('reopenAssignment', 'Are you sure you want to reopen this assignment?');
            if (window.showConfirmation) {
                window.showConfirmation(msg, () => { form.dataset.confirmed = 'true'; form.requestSubmit ? form.requestSubmit() : form.submit(); }, null, 'Reopen', 'Cancel', 'Reopen Assignment?');
            } else {
                console.warn('Confirmation dialog not available:', msg);
                return false;
            }
            return false;
        }
    });

    // Handle submission dropdown menus
    document.addEventListener('click', function(event) {
        // Close all dropdowns when clicking outside
        if (!event.target.closest('.relative.inline-block.text-left')) {
            document.querySelectorAll('[id^="submission-dropdown-menu-"]').forEach(menu => {
                menu.classList.add('hidden');
            });
            document.querySelectorAll('[id^="submission-dropdown-"]').forEach(button => {
                button.setAttribute('aria-expanded', 'false');
            });
        }
    });

    // Handle dropdown button clicks
    document.querySelectorAll('[id^="submission-dropdown-"]').forEach(button => {
        button.addEventListener('click', function(event) {
            event.stopPropagation();
            const menuId = this.id.replace('submission-dropdown-', 'submission-dropdown-menu-');
            const menu = document.getElementById(menuId);
            const isOpen = !menu.classList.contains('hidden');

            // Close all other dropdowns
            document.querySelectorAll('[id^="submission-dropdown-menu-"]').forEach(otherMenu => {
                if (otherMenu.id !== menuId) {
                    otherMenu.classList.add('hidden');
                }
            });
            document.querySelectorAll('[id^="submission-dropdown-"]').forEach(otherButton => {
                if (otherButton.id !== this.id) {
                    otherButton.setAttribute('aria-expanded', 'false');
                }
            });

            // Toggle current dropdown
            if (isOpen) {
                menu.classList.add('hidden');
                this.setAttribute('aria-expanded', 'false');
            } else {
                menu.classList.remove('hidden');
                this.setAttribute('aria-expanded', 'true');
            }
        });
    });

    // Handle toggle additional changes buttons (replaced inline onclick handlers for CSP compliance)
    document.querySelectorAll('.toggle-additional-changes').forEach(button => {
        button.addEventListener('click', function(event) {
            const activityIndex = this.getAttribute('data-activity-index');
            toggleAdditionalChanges(this, activityIndex);
        });
    });

});
