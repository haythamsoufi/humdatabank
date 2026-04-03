/**
 * Form Builder Initialization Scripts
 * Handles initialization of various UI components in the form builder
 */

// Submit a builder form in the most reliable way:
// - Prefer the AJAX helper when available (covers cases where form.submit() bypasses submit events)
// - Fall back to requestSubmit (fires submit events + native validation)
// - Finally fall back to submit()
function submitBuilderForm(form) {
    if (!form) return;
    try {
        if (window.FormBuilderAjax && typeof window.FormBuilderAjax.submit === 'function') {
            return window.FormBuilderAjax.submit(form);
        }
    } catch (_e) {}
    try {
        if (typeof form.requestSubmit === 'function') {
            return form.requestSubmit();
        }
    } catch (_e) {}
    try { return form.submit(); } catch (_e) {}
}

/**
 * Initialize versions modal functionality
 */
export function initVersionsModal() {
    document.addEventListener('DOMContentLoaded', function() {
        const versionsModalBtn = document.getElementById('versions-modal-btn');
        const versionsModal = document.getElementById('versions-modal');

        // Show modal when button is clicked
        if (versionsModalBtn && versionsModal) {
            versionsModalBtn.addEventListener('click', function() {
                versionsModal.classList.remove('hidden');
            });
        }

        // Close modal handlers
        if (versionsModal) {
            const closeModalBtns = versionsModal.querySelectorAll('.close-modal');
            closeModalBtns.forEach(btn => {
                btn.addEventListener('click', function() {
                    versionsModal.classList.add('hidden');
                });
            });

            // Close modal when clicking outside
            versionsModal.addEventListener('click', function(e) {
                if (e.target === versionsModal) {
                    versionsModal.classList.add('hidden');
                }
            });
        }

        // Deploy version handlers for all versions in table
        document.querySelectorAll('[class*="deploy-version-btn-"]').forEach(btn => {
            btn.addEventListener('click', function() {
                const form = this.closest('form');
                const deployMessage = window.formBuilderMessages?.deployVersion ||
                    'Deploy this version? This will publish it as the live version.';
                const doDeploy = () => { if (form) submitBuilderForm(form); };
                if (form) {
                    if (window.showConfirmation) {
                        window.showConfirmation(deployMessage, doDeploy, null, 'Deploy', 'Cancel', 'Deploy Version?');
                    }
                }
            });
        });

        // Delete version handlers for all versions in table
        document.querySelectorAll('[class*="delete-version-btn-"]').forEach(btn => {
            btn.addEventListener('click', function() {
                const form = this.closest('form');
                const deleteMessage = window.formBuilderMessages?.deleteVersion ||
                    'Delete this version? This cannot be undone.';
                const doDelete = () => { if (form) submitBuilderForm(form); };
                if (window.showDangerConfirmation) {
                    window.showDangerConfirmation(deleteMessage, doDelete, null, 'Delete', 'Cancel', 'Delete Version?');
                } else if (window.showConfirmation) {
                    window.showConfirmation(deleteMessage, doDelete, null, 'Delete', 'Cancel', 'Delete Version?');
                }
            });
        });

        // Handle note field editing - show save button when user starts editing
        document.querySelectorAll('.version-note-input').forEach(input => {
            const versionId = input.getAttribute('data-version-id');
            const saveBtn = document.getElementById('version-note-save-btn-' + versionId);
            const originalValue = input.getAttribute('data-original-value') || '';

            if (saveBtn) {
                // Show save button when value changes
                input.addEventListener('input', function() {
                    if (this.value !== originalValue) {
                        saveBtn.classList.remove('hidden');
                    } else {
                        saveBtn.classList.add('hidden');
                    }
                });

                // Also check on focus to handle paste operations
                input.addEventListener('focus', function() {
                    // Delay check to allow paste to complete
                    setTimeout(() => {
                        if (this.value !== originalValue) {
                            saveBtn.classList.remove('hidden');
                        }
                    }, 100);
                });

                // Hide save button if user reverts to original value
                input.addEventListener('blur', function() {
                    if (this.value === originalValue) {
                        saveBtn.classList.add('hidden');
                    }
                });
            }
        });

        // Convert UTC datetimes to user's local timezone
        document.querySelectorAll('.version-datetime').forEach(element => {
            const utcDatetimeStr = element.getAttribute('data-datetime');
            if (utcDatetimeStr) {
                try {
                    // Ensure the datetime string has timezone info (add 'Z' for UTC if missing)
                    let isoString = utcDatetimeStr.trim();
                    // Check if it has timezone info (Z, +, or - after the time portion)
                    if (!isoString.endsWith('Z') && !isoString.match(/[+-]\d{2}:\d{2}$/)) {
                        // If no timezone indicator, assume UTC (naive datetime from Python)
                        // Add 'Z' to indicate UTC
                        isoString = isoString + (isoString.includes('T') ? 'Z' : 'T00:00:00Z');
                    }

                    // Parse UTC datetime string - JavaScript Date automatically converts to local timezone
                    const date = new Date(isoString);
                    if (!isNaN(date.getTime())) {
                        // Format in user's local timezone using toLocaleString or manual formatting
                        const year = date.getFullYear();
                        const month = String(date.getMonth() + 1).padStart(2, '0');
                        const day = String(date.getDate()).padStart(2, '0');
                        const hours = String(date.getHours()).padStart(2, '0');
                        const minutes = String(date.getMinutes()).padStart(2, '0');
                        element.textContent = `${year}-${month}-${day} ${hours}:${minutes}`;
                    }
                } catch (e) {
                    // If conversion fails, keep the original UTC time
                    console.warn('Failed to convert datetime to local timezone:', e);
                }
            }
        });
    });
}

/**
 * Initialize page sections toggle functionality
 */
export function initPageSectionsToggle() {
    document.addEventListener('DOMContentLoaded', function() {
        // Initialize page toggle buttons
        const pageToggleButtons = document.querySelectorAll('.page-toggle-btn');

        const runPageToggle = function(button) {
            const pageId = button.getAttribute('data-page-id');
            const sectionsContainer = document.querySelector(`.page-sections-container[data-page-id="${pageId}"]`);
            const icon = button.querySelector('i');
            const text = button.querySelector('span');
            if (sectionsContainer) {
                const isHidden = sectionsContainer.style.display === 'none';
                if (isHidden) {
                    sectionsContainer.style.display = 'block';
                    sectionsContainer.style.opacity = '1';
                    sectionsContainer.style.maxHeight = 'none';
                    if (icon) icon.style.transform = 'rotate(0deg)';
                    if (text) text.textContent = 'Hide Sections';
                } else {
                    sectionsContainer.style.display = 'none';
                    sectionsContainer.style.opacity = '0';
                    sectionsContainer.style.maxHeight = '0';
                    if (icon) icon.style.transform = 'rotate(-90deg)';
                    if (text) text.textContent = 'Show Sections';
                }
            }
        };

        pageToggleButtons.forEach(button => {
            button.addEventListener('click', function() {
                runPageToggle(this);
            });
        });

        // Click on page banner (title area) also toggles; avoid double-fire when clicking the button
        document.querySelectorAll('.page-banner-row').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('.page-toggle-btn')) return;
                const btn = this.querySelector('.page-toggle-btn');
                if (btn) runPageToggle(btn);
            });
        });
    });
}

/**
 * Initialize Excel modal functionality
 */
export function initExcelModal() {
    document.addEventListener('DOMContentLoaded', function() {
        const excelBtn = document.getElementById('excel-options-btn');
        const excelModal = document.getElementById('excel-options-modal');
        const importForm = document.getElementById('import-excel-form');

        if (excelBtn && excelModal) {
            // Open modal
            excelBtn.addEventListener('click', function() {
                excelModal.classList.remove('hidden');
            });

            // Close modal handlers
            const closeButtons = excelModal.querySelectorAll('.close-modal');
            closeButtons.forEach(function(btn) {
                btn.addEventListener('click', function() {
                    excelModal.classList.add('hidden');
                    if (importForm) {
                        importForm.reset();
                    }
                });
            });

            // Close on background click
            excelModal.addEventListener('click', function(e) {
                if (e.target === excelModal) {
                    excelModal.classList.add('hidden');
                    if (importForm) {
                        importForm.reset();
                    }
                }
            });

            // Auto-submit form when file is selected
            const excelFileInput = document.getElementById('excel_file');
            if (excelFileInput && importForm) {
                excelFileInput.addEventListener('change', function() {
                    if (this.files.length > 0) {
                        submitBuilderForm(importForm);
                    }
                });
            }

            // Drag and drop handling
            const dropZone = excelModal.querySelector('.file-upload-wrapper');
            if (dropZone && excelFileInput) {
                ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                    dropZone.addEventListener(eventName, function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                    }, false);
                });

                ['dragenter', 'dragover'].forEach(eventName => {
                    dropZone.addEventListener(eventName, function() {
                        dropZone.classList.add('border-blue-500', 'bg-blue-50');
                    }, false);
                });

                ['dragleave', 'drop'].forEach(eventName => {
                    dropZone.addEventListener(eventName, function() {
                        dropZone.classList.remove('border-blue-500', 'bg-blue-50');
                    }, false);
                });

                dropZone.addEventListener('drop', function(e) {
                    const dt = e.dataTransfer;
                    const file = dt.files[0];

                    if (file && (file.name.endsWith('.xlsx') || file.name.endsWith('.xls'))) {
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(file);
                        excelFileInput.files = dataTransfer.files;
                        excelFileInput.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }, false);
            }
        }
    });
}

/**
 * Initialize archived items toggle functionality
 */
export function initArchivedItemsToggle() {
    document.addEventListener('DOMContentLoaded', function() {
        const toggleBtn = document.getElementById('toggle-archived-items-btn');
        const toggleText = document.getElementById('toggle-archived-text');
        const toggleIcon = document.getElementById('toggle-archived-icon');
        const toggleIndicator = document.getElementById('toggle-archived-indicator');
        const toggleSlider = document.getElementById('toggle-archived-slider');
        const toggleRipple = document.getElementById('toggle-archived-ripple');

        if (toggleBtn && toggleText && toggleIcon && toggleIndicator && toggleSlider) {
            let archivedVisible = false; // Default: hide archived items

            // Hide archived items and sections by default on page load
            const archivedRows = document.querySelectorAll('tr.archived-item-row[data-archived="true"]');
            archivedRows.forEach(function(row) {
                row.style.display = 'none';
            });

            const archivedSections = document.querySelectorAll('.archived-section-container[data-archived="true"]');
            archivedSections.forEach(function(section) {
                section.style.display = 'none';
            });

            // Function to update toggle visual state
            function updateToggleState(isVisible) {
                if (isVisible) {
                    // Toggle ON state - active blue theme
                    toggleBtn.classList.remove('from-gray-50', 'to-gray-100');
                    toggleBtn.classList.add('from-blue-50', 'to-indigo-50');

                    // Icon changes to eye (visible)
                    toggleIcon.classList.remove('fa-eye-slash', 'text-gray-500');
                    toggleIcon.classList.add('fa-eye', 'text-blue-600');

                    // Indicator turns blue
                    toggleIndicator.classList.remove('bg-gray-300');
                    toggleIndicator.classList.add('bg-blue-500');

                    // Slider moves to right
                    toggleSlider.style.transform = 'translateX(1.125rem)';

                    // Update text
                    toggleText.textContent = 'Archived Shown';
                    toggleText.classList.remove('text-gray-700');
                    toggleText.classList.add('text-blue-700');
                } else {
                    // Toggle OFF state - inactive gray theme
                    toggleBtn.classList.remove('from-blue-50', 'to-indigo-50');
                    toggleBtn.classList.add('from-gray-50', 'to-gray-100');

                    // Icon changes to eye-slash (hidden)
                    toggleIcon.classList.remove('fa-eye', 'text-blue-600');
                    toggleIcon.classList.add('fa-eye-slash', 'text-gray-500');

                    // Indicator turns gray
                    toggleIndicator.classList.remove('bg-blue-500');
                    toggleIndicator.classList.add('bg-gray-300');

                    // Slider moves to left
                    toggleSlider.style.transform = 'translateX(0)';

                    // Update text
                    toggleText.textContent = 'Archived Hidden';
                    toggleText.classList.remove('text-blue-700');
                    toggleText.classList.add('text-gray-700');
                }
            }

            // Ripple effect on click
            function createRipple(event) {
                if (toggleRipple) {
                    toggleRipple.style.opacity = '0.3';
                    toggleRipple.style.transform = 'scale(0)';

                    // Trigger reflow
                    toggleRipple.offsetHeight;

                    // Animate
                    requestAnimationFrame(function() {
                        toggleRipple.style.transition = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
                        toggleRipple.style.opacity = '0';
                        toggleRipple.style.transform = 'scale(1.5)';

                        setTimeout(function() {
                            toggleRipple.style.transition = 'all 0.3s ease-in-out';
                        }, 400);
                    });
                }
            }

            toggleBtn.addEventListener('click', function(e) {
                archivedVisible = !archivedVisible;
                const archivedRows = document.querySelectorAll('tr.archived-item-row[data-archived="true"]');
                const archivedSections = document.querySelectorAll('.archived-section-container[data-archived="true"]');

                // Create ripple effect
                createRipple(e);

                archivedRows.forEach(function(row) {
                    if (archivedVisible) {
                        row.style.display = ''; // Show
                    } else {
                        row.style.display = 'none'; // Hide
                    }
                });

                archivedSections.forEach(function(section) {
                    if (archivedVisible) {
                        section.style.display = ''; // Show
                    } else {
                        section.style.display = 'none'; // Hide
                    }
                });

                // Update toggle visual state
                updateToggleState(archivedVisible);
            });
        }
    });
}

/**
 * Initialize section and subsection expand/collapse toggles
 */
export function initSectionSubsectionToggle() {
    document.addEventListener('DOMContentLoaded', function() {
        // Section toggle: collapse/expand section body
        document.querySelectorAll('.section-toggle').forEach(btn => {
            btn.addEventListener('click', function() {
                const sectionItem = this.closest('.section-item');
                if (!sectionItem) return;
                const icon = this.querySelector('i');
                const isCollapsed = sectionItem.classList.toggle('section-collapsed');
                if (icon) icon.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
                btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
                btn.setAttribute('title', isCollapsed ? 'Expand section' : 'Collapse section');
            });
        });

        // Section banner (title + chevron): click toggles; don't toggle when clicking action buttons
        document.querySelectorAll('.section-header-banner').forEach(banner => {
            banner.addEventListener('click', function(e) {
                if (e.target.closest('.section-toggle')) return;
                const btn = this.querySelector('.section-toggle');
                if (btn) btn.click();
            });
        });

        // Subsection toggle: collapse/expand subsection content rows
        document.querySelectorAll('.subsection-toggle').forEach(btn => {
            btn.addEventListener('click', function() {
                const headerRow = this.closest('tr.subsection-header-row');
                if (!headerRow) return;
                const subsectionId = headerRow.getAttribute('data-subsection-id');
                const table = headerRow.closest('table');
                if (!subsectionId || !table) return;
                const contentRows = table.querySelectorAll(`tr.subsection-content-row[data-parent-subsection-id="${subsectionId}"]`);
                const icon = this.querySelector('i');
                const isCollapsed = headerRow.classList.toggle('subsection-collapsed');
                contentRows.forEach(row => {
                    row.style.display = isCollapsed ? 'none' : '';
                });
                if (icon) icon.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
                btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
                btn.setAttribute('title', isCollapsed ? 'Expand subsection' : 'Collapse subsection');
            });
        });

        // Subsection banner row: click toggles except when clicking action buttons (last cell)
        document.querySelectorAll('tr.subsection-header-row').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('td:last-child')) return;
                if (e.target.closest('.subsection-toggle')) return;
                const btn = this.querySelector('.subsection-toggle');
                if (btn) btn.click();
            });
        });
    });
}

/**
 * Enhance (re-bind) DOM interactions after an AJAX partial refresh.
 * Uses per-element dataset flags to avoid duplicating handlers.
 */
function enhance() {
    // Page toggle buttons
    document.querySelectorAll('.page-toggle-btn').forEach((button) => {
        if (button.dataset.fbWired === '1') return;
        button.dataset.fbWired = '1';
        button.addEventListener('click', function() {
            const pageId = button.getAttribute('data-page-id');
            const sectionsContainer = document.querySelector(`.page-sections-container[data-page-id="${pageId}"]`);
            const icon = button.querySelector('i');
            const text = button.querySelector('span');
            if (sectionsContainer) {
                const isHidden = sectionsContainer.style.display === 'none';
                if (isHidden) {
                    sectionsContainer.style.display = 'block';
                    sectionsContainer.style.opacity = '1';
                    sectionsContainer.style.maxHeight = 'none';
                    if (icon) icon.style.transform = 'rotate(0deg)';
                    if (text) text.textContent = 'Hide Sections';
                } else {
                    sectionsContainer.style.display = 'none';
                    sectionsContainer.style.opacity = '0';
                    sectionsContainer.style.maxHeight = '0';
                    if (icon) icon.style.transform = 'rotate(-90deg)';
                    if (text) text.textContent = 'Show Sections';
                }
            }
        });
    });

    // Click on page banner also toggles (wire once)
    document.querySelectorAll('.page-banner-row').forEach((row) => {
        if (row.dataset.fbWired === '1') return;
        row.dataset.fbWired = '1';
        row.addEventListener('click', function(e) {
            if (e.target.closest('.page-toggle-btn')) return;
            const btn = row.querySelector('.page-toggle-btn');
            if (btn) btn.click();
        });
    });

    // Section toggle + banner toggle
    document.querySelectorAll('.section-toggle').forEach((btn) => {
        if (btn.dataset.fbWired === '1') return;
        btn.dataset.fbWired = '1';
        btn.addEventListener('click', function() {
            const sectionItem = btn.closest('.section-item');
            if (!sectionItem) return;
            const icon = btn.querySelector('i');
            const isCollapsed = sectionItem.classList.toggle('section-collapsed');
            if (icon) icon.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
            btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
            btn.setAttribute('title', isCollapsed ? 'Expand section' : 'Collapse section');
        });
    });

    document.querySelectorAll('.section-header-banner').forEach((banner) => {
        if (banner.dataset.fbWired === '1') return;
        banner.dataset.fbWired = '1';
        banner.addEventListener('click', function(e) {
            if (e.target.closest('.section-toggle')) return;
            if (e.target.closest('button, a, form')) return;
            const btn = banner.querySelector('.section-toggle');
            if (btn) btn.click();
        });
    });

    // Subsection toggle + row click toggle
    document.querySelectorAll('.subsection-toggle').forEach((btn) => {
        if (btn.dataset.fbWired === '1') return;
        btn.dataset.fbWired = '1';
        btn.addEventListener('click', function() {
            const headerRow = btn.closest('tr.subsection-header-row');
            if (!headerRow) return;
            const subsectionId = headerRow.getAttribute('data-subsection-id');
            const table = headerRow.closest('table');
            if (!subsectionId || !table) return;
            const contentRows = table.querySelectorAll(`tr.subsection-content-row[data-parent-subsection-id="${subsectionId}"]`);
            const icon = btn.querySelector('i');
            const isCollapsed = headerRow.classList.toggle('subsection-collapsed');
            contentRows.forEach(row => {
                row.style.display = isCollapsed ? 'none' : '';
            });
            if (icon) icon.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
            btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
            btn.setAttribute('title', isCollapsed ? 'Expand subsection' : 'Collapse subsection');
        });
    });

    document.querySelectorAll('tr.subsection-header-row').forEach((row) => {
        if (row.dataset.fbWired === '1') return;
        row.dataset.fbWired = '1';
        row.addEventListener('click', function(e) {
            if (e.target.closest('td:last-child')) return;
            if (e.target.closest('.subsection-toggle')) return;
            if (e.target.closest('button, a, form')) return;
            const btn = row.querySelector('.subsection-toggle');
            if (btn) btn.click();
        });
    });
}

// Expose for AJAX refresh calls
window.FormBuilderEnhance = window.FormBuilderEnhance || {};
window.FormBuilderEnhance.enhance = enhance;

/**
 * Initialize "Collapse all / Expand all" controls for pages and sections.
 * - Pages: toggles visibility of `.page-sections-container` (same behavior as `.page-toggle-btn`)
 * - Sections: toggles `.section-collapsed` on `.section-item` AND hides/shows subsection content rows
 */
export function initBulkCollapseExpandControls() {
    function run() {
        const pagesBtn = document.getElementById('toggle-all-pages-btn');
        const sectionsBtn = document.getElementById('toggle-all-sections-btn');

        const getIsHidden = (el) => {
            if (!el) return true;
            try {
                // Prefer inline style (fast path), fallback to computed.
                if (el.style && el.style.display) return el.style.display === 'none';
                return window.getComputedStyle(el).display === 'none';
            } catch (_e) {
                return false;
            }
        };

        const setButtonState = ({ btn, mode, iconUp = true }) => {
            if (!btn) return;
            const collapseText = btn.getAttribute('data-collapse-text') || 'Collapse';
            const expandText = btn.getAttribute('data-expand-text') || 'Expand';
            const textEl = btn.querySelector('span');
            const iconEl = btn.querySelector('i');

            const isCollapseMode = mode === 'collapse';
            if (textEl) textEl.textContent = isCollapseMode ? collapseText : expandText;
            if (iconEl) {
                // Keep it minimal: up arrow for collapse, down arrow for expand.
                iconEl.classList.toggle('fa-angle-double-up', isCollapseMode);
                iconEl.classList.toggle('fa-angle-double-down', !isCollapseMode);
            }
            btn.dataset.mode = isCollapseMode ? 'collapse' : 'expand';
            btn.setAttribute('aria-pressed', isCollapseMode ? 'false' : 'true');
        };

        const setAllPagesCollapsed = (collapsed) => {
            const pageToggles = Array.from(document.querySelectorAll('.page-toggle-btn'));
            if (pageToggles.length === 0) return;

            pageToggles.forEach((toggle) => {
                const pageId = toggle.getAttribute('data-page-id');
                const container = document.querySelector(`.page-sections-container[data-page-id="${pageId}"]`);
                const icon = toggle.querySelector('i');
                const text = toggle.querySelector('span');
                if (!container) return;

                if (collapsed) {
                    container.style.display = 'none';
                    container.style.opacity = '0';
                    container.style.maxHeight = '0';
                    if (icon) icon.style.transform = 'rotate(-90deg)';
                    if (text) text.textContent = 'Show Sections';
                } else {
                    container.style.display = 'block';
                    container.style.opacity = '1';
                    container.style.maxHeight = 'none';
                    if (icon) icon.style.transform = 'rotate(0deg)';
                    if (text) text.textContent = 'Hide Sections';
                }
            });
        };

        const setAllSectionsCollapsed = (collapsed) => {
            // Collapse/expand main section bodies.
            document.querySelectorAll('.section-item').forEach((sectionItem) => {
                if (!sectionItem) return;
                sectionItem.classList.toggle('section-collapsed', !!collapsed);

                const toggleBtn = sectionItem.querySelector('.section-toggle');
                const icon = toggleBtn ? toggleBtn.querySelector('i') : null;
                if (icon) icon.style.transform = collapsed ? 'rotate(-90deg)' : '';
                if (toggleBtn) {
                    toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                    toggleBtn.setAttribute('title', collapsed ? 'Expand section' : 'Collapse section');
                }
            });

            // Collapse/expand all subsections (header + content rows).
            document.querySelectorAll('tr.subsection-header-row').forEach((headerRow) => {
                const subsectionId = headerRow.getAttribute('data-subsection-id');
                const table = headerRow.closest('table');
                if (!subsectionId || !table) return;

                headerRow.classList.toggle('subsection-collapsed', !!collapsed);
                const contentRows = table.querySelectorAll(`tr.subsection-content-row[data-parent-subsection-id="${subsectionId}"]`);
                contentRows.forEach((row) => {
                    row.style.display = collapsed ? 'none' : '';
                });

                const toggleBtn = headerRow.querySelector('.subsection-toggle');
                const icon = toggleBtn ? toggleBtn.querySelector('i') : null;
                if (icon) icon.style.transform = collapsed ? 'rotate(-90deg)' : '';
                if (toggleBtn) {
                    toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                    toggleBtn.setAttribute('title', collapsed ? 'Expand subsection' : 'Collapse subsection');
                }
            });
        };

        const syncButtons = () => {
            // Pages button: only relevant if there are paginated page toggles.
            if (pagesBtn) {
                const pageToggles = Array.from(document.querySelectorAll('.page-toggle-btn'));
                if (pageToggles.length === 0) {
                    pagesBtn.disabled = true;
                    pagesBtn.setAttribute('title', 'No pages to collapse/expand');
                } else {
                    pagesBtn.disabled = false;
                    const allHidden = pageToggles.every((toggle) => {
                        const pageId = toggle.getAttribute('data-page-id');
                        const container = document.querySelector(`.page-sections-container[data-page-id="${pageId}"]`);
                        return container ? getIsHidden(container) : true;
                    });
                    setButtonState({ btn: pagesBtn, mode: allHidden ? 'expand' : 'collapse' });
                }
            }

            if (sectionsBtn) {
                const sectionItems = Array.from(document.querySelectorAll('.section-item'));
                if (sectionItems.length === 0) {
                    sectionsBtn.disabled = true;
                    sectionsBtn.setAttribute('title', 'No sections to collapse/expand');
                } else {
                    sectionsBtn.disabled = false;
                    const allCollapsed = sectionItems.every((s) => s.classList.contains('section-collapsed'));

                    // Also consider subsections: if any subsection header isn't collapsed, treat as not fully collapsed.
                    const subsectionHeaders = Array.from(document.querySelectorAll('tr.subsection-header-row'));
                    const allSubCollapsed = subsectionHeaders.every((r) => r.classList.contains('subsection-collapsed'));
                    const everythingCollapsed = allCollapsed && allSubCollapsed;

                    setButtonState({ btn: sectionsBtn, mode: everythingCollapsed ? 'expand' : 'collapse' });
                }
            }
        };

        if (pagesBtn) {
            pagesBtn.addEventListener('click', function () {
                const mode = (pagesBtn.dataset.mode || 'collapse');
                const shouldCollapse = mode === 'collapse';
                setAllPagesCollapsed(shouldCollapse);
                syncButtons();
            });
        }

        if (sectionsBtn) {
            sectionsBtn.addEventListener('click', function () {
                const mode = (sectionsBtn.dataset.mode || 'collapse');
                const shouldCollapse = mode === 'collapse';
                setAllSectionsCollapsed(shouldCollapse);
                syncButtons();
            });
        }

        // Keep bulk buttons in sync when the user toggles individual items.
        document.addEventListener('click', function (e) {
            if (
                e.target.closest('.page-toggle-btn') ||
                e.target.closest('.section-toggle') ||
                e.target.closest('.subsection-toggle')
            ) {
                setTimeout(syncButtons, 0);
            }
        });

        // Initial state.
        syncButtons();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run);
    } else {
        run();
    }
}

/**
 * Initialize all form builder components
 */
export function initFormBuilder() {
    initVersionsModal();
    initPageSectionsToggle();
    initSectionSubsectionToggle();
    initBulkCollapseExpandControls();
    initExcelModal();
    initArchivedItemsToggle();
}
