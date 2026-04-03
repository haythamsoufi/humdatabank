import { debugLog } from './debug.js';
import { initDataAvailability } from './data-availability.js';
import { setupNumberInputFormatting } from './formatting.js';
import { copyFormElementValues } from './form-item-utils.js';

// Test debug message
debugLog('layout', '🔍 DEBUG TEST: Layout module loaded');

export function initLayout() {
    debugLog('layout', '\n=== INITIALIZING LAYOUT ===');
    initializeFlexibleLayout();
    setupRepeatObserver();
}

function initializeFlexibleLayout() {
    debugLog('layout', 'Starting flexible layout initialization...');

    // Skip layout on mobile screens (less than 768px)
    if (window.innerWidth < 768) {
        debugLog('layout', '📱 Mobile screen detected - skipping dynamic layout');
        return;
    }

    // Prefer the main sections container; fall back intelligently
    let container = document.getElementById('sections-container');
    if (container) {
        debugLog('layout', '✅ Found #sections-container');
    } else {
        // Prefer the main data entry form if present
        container = document.getElementById('focalDataEntryForm');
        if (container) {
            debugLog('layout', '✅ Found #focalDataEntryForm');
        } else {
            // As a last resort, pick a form that actually contains sections; otherwise use body
            const candidateForms = Array.from(document.querySelectorAll('form'));
            container = candidateForms.find(f => f.querySelector('[id^="section-container-"]')) || document.body;
            debugLog('layout', container === document.body ? '⚠️ No suitable form found, using document body' : '✅ Found a form containing sections');
        }
    }

    // Find all sections that contain form items
    const sections = container.querySelectorAll('[id^="section-container-"]');
    debugLog('layout', `Found ${sections.length} sections with id starting with 'section-container-'`);

    sections.forEach((section, index) => {
        debugLog('layout', `\nProcessing section ${index + 1}/${sections.length}`);
        debugLog('layout', `Section ID: ${section.id}`);

        // Skip repeat sections - they handle their own layout
        const sectionType = section.getAttribute('data-section-type');
        if (sectionType === 'repeat') {
            debugLog('layout', `⏭️ Skipping repeat section ${section.id} - will handle layout in repeat entries`);
            return;
        }

        // Find the space-y-6 container within the section
        const container = section.querySelector('.space-y-6');
        if (!container) {
            debugLog('layout', `❌ No .space-y-6 container found in section ${section.id}`);
            return;
        }
        debugLog('layout', '✅ Found .space-y-6 container');

        // Find all form items before layout (excluding repeat interface elements)
        const beforeFields = container.querySelectorAll('.form-item-block:not(.repeat-template .form-item-block):not(.layout-ignore .form-item-block):not(.layout-ignore)');
        debugLog('layout', `Found ${beforeFields.length} form items before layout`);

        // Log layout attributes for each field
        beforeFields.forEach((field, fieldIndex) => {
            const width = field.getAttribute('data-layout-width');
            const break_ = field.hasAttribute('data-layout-break');
            const itemType = field.getAttribute('data-item-type') || 'unknown';
            debugLog('layout', `Field ${fieldIndex + 1}: type=${itemType}, width=${width || '12 (default)'}, break=${break_}`);
        });
        applyFlexibleLayoutToSection(container);
    });
}

function applyFlexibleLayoutToSection(container) {
    if (!container) {
        debugLog('layout', '❌ Container is null in applyFlexibleLayoutToSection');
        return;
    }

    // Replace Tailwind vertical spacing utility to reduce gaps between rows
    if (container.classList.contains('space-y-6')) {
        container.classList.replace('space-y-6', 'space-y-3');
    }

    // Get only the direct form items of the parent section (not those in sub-sections)
    // We need to exclude form items that are inside sub-section containers
    const allFormItems = Array.from(container.querySelectorAll('.form-item-block:not(.repeat-template .form-item-block):not(.layout-ignore .form-item-block):not(.layout-ignore)'));

    // Filter out form items that are inside sub-section containers
    // A field belongs to the parent section if it's not inside any nested section-container div
    const mainSectionId = container.closest('[id^="section-container-"]')?.id;
    debugLog('layout', `Main section ID: ${mainSectionId}`);

    const parentFields = allFormItems.filter(field => {
        // Find the closest section container
        let currentElement = field.parentElement;
        while (currentElement && currentElement !== container) {
            // If we encounter a section-container div that's not the main container, this field is in a sub-section
            if (currentElement.id && currentElement.id.startsWith('section-container-') && currentElement.id !== mainSectionId) {
                return false;
            }
            currentElement = currentElement.parentElement;
        }
        return true;
    });

    debugLog('layout', `Found ${allFormItems.length} total form items, ${parentFields.length} belong to parent section`);

    if (!parentFields.length) {
        debugLog('layout', '❌ No parent section fields found to layout');
        return;
    }

    // Extract sub-sections to preserve them
    // Sub-sections are direct children of the space-y-6 container with section-container- IDs
    const subSections = Array.from(container.children).filter(child =>
        child.id && child.id.startsWith('section-container-') &&
        child.id !== mainSectionId
    );
    debugLog('layout', `Found ${subSections.length} sub-sections to preserve`);
    subSections.forEach((subSection, index) => {
        debugLog('layout', `Sub-section ${index + 1}: ${subSection.id}`);
    });

    // Store sub-sections temporarily
    const preservedSubSections = subSections.map(subSection => {
        const clone = subSection.cloneNode(true);
        // Apply layout to sub-sections that have their own form items
        const subSectionContainer = clone.querySelector('.space-y-4');
        if (subSectionContainer) {
            applyLayoutToSubSection(subSectionContainer);
        }
        return clone;
    });

    // Preserve other direct children that are not form fields and not sub-sections.
    // These include dynamic section controls like "Add Indicator" UI, repeat interfaces, helper text, etc.
    // Without preserving them, they can get re-inserted outside the collapsible content area by other modules.
    const preservedExtras = Array.from(container.children).filter(child => {
        // Skip sub-sections (handled above)
        if (child.id && child.id.startsWith('section-container-') && child.id !== mainSectionId) return false;
        // Skip form item blocks (they get rebuilt into the flex layout)
        if (child.classList && child.classList.contains('form-item-block')) return false;
        // Keep everything else (including dynamic indicator interface)
        return true;
    });

    // Group parent fields by their layout properties
    const fieldGroups = groupFieldsByLayout(parentFields);
    debugLog('layout', `Created ${fieldGroups.length} field groups for parent section`);

    // Log group details
    fieldGroups.forEach((group, groupIndex) => {
        debugLog('layout', `Group ${groupIndex + 1}: ${group.length} fields`);
        group.forEach(field => {
            const width = getFieldLayoutWidth(field);
            debugLog('layout', `Field width: ${width} (from attribute: ${field.getAttribute('data-layout-width')})`);
        });
        const totalWidth = group.reduce((sum, field) => sum + getFieldLayoutWidth(field), 0);
        debugLog('layout', `Group ${groupIndex + 1} total width: ${totalWidth}/12`);
    });

    // Create and apply the new layout for parent fields
    const newContainer = createFlexibleLayoutContainer(fieldGroups);
    debugLog('layout', 'Created new layout container for parent section');

    // Clear the container
    container.replaceChildren();

    // Add the parent fields with layout
    Array.from(newContainer.children).forEach(child => {
        container.appendChild(child);
    });

    // Add back preserved "extra" blocks (e.g., dynamic indicators interface) before sub-sections.
    preservedExtras.forEach(extra => {
        container.appendChild(extra);
    });

    // Add back the preserved sub-sections
    preservedSubSections.forEach(subSection => {
        container.appendChild(subSection);
    });

    // Re-initialize data availability after layout changes
    initDataAvailability();

    debugLog('layout', `After layout: ${container.querySelectorAll('.form-item-block').length} total fields in the DOM`);
    debugLog('layout', `✅ Layout applied successfully - ${parentFields.length} parent fields + ${subSections.length} sub-sections preserved`);
}

function setupRepeatObserver() {
    debugLog('layout', '\nSetting up repeat section observer...');

    // Watch for changes in repeat sections to reapply layout
    const observer = new MutationObserver((mutations) => {
        mutations.forEach(mutation => {
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === 1 && node.classList.contains('repeat-entry')) {
                        debugLog('layout', '\nRepeat entry added - updating layout');
                        const section = node.closest('[id^="section-container-"]');
                        if (section) {
                            debugLog('layout', `Found parent section: ${section.id}`);
                            const container = section.querySelector('.space-y-6');
                            if (container) {
                                debugLog('layout', 'Found .space-y-6 container, refreshing layout');
                                refreshSectionLayout(container);
                            } else {
                                debugLog('layout', '❌ No .space-y-6 container found in repeat section');
                            }
                        } else {
                            debugLog('layout', '❌ No parent section found for repeat entry');
                        }
                    }
                });
            }
        });
    });

    const repeatContainers = document.querySelectorAll('.repeat-entries-container');
    debugLog('layout', `Found ${repeatContainers.length} repeat containers to observe`);

    repeatContainers.forEach(container => {
        observer.observe(container, { childList: true });
    });
}

function refreshSectionLayout(container) {
    debugLog('layout', '\nRefreshing section layout...');
    if (!container) {
        debugLog('layout', '❌ Container is null in refreshSectionLayout');
        return;
    }
    applyFlexibleLayoutToSection(container);
}

function applyLayoutToSubSection(subSectionContainer) {
    debugLog('layout', '\nApplying layout to sub-section...');
    if (!subSectionContainer) {
        debugLog('layout', '❌ Sub-section container is null');
        return;
    }

    // Replace Tailwind vertical spacing utility to reduce gaps between rows inside sub-sections
    if (subSectionContainer.classList.contains('space-y-4')) {
        subSectionContainer.classList.replace('space-y-4', 'space-y-2');
    }

    // Get all form items in the sub-section
    const subSectionFields = Array.from(subSectionContainer.querySelectorAll('.form-item-block:not(.repeat-template .form-item-block):not(.layout-ignore .form-item-block):not(.layout-ignore)'));
    debugLog('layout', `Found ${subSectionFields.length} fields in sub-section`);

    if (!subSectionFields.length) {
        debugLog('layout', '❌ No fields found in sub-section to layout');
        return;
    }

    // Group fields by their layout properties
    const fieldGroups = groupFieldsByLayout(subSectionFields);
    debugLog('layout', `Created ${fieldGroups.length} field groups for sub-section`);

    // Create and apply the new layout
    const newContainer = createFlexibleLayoutContainer(fieldGroups);
    debugLog('layout', 'Created new layout container for sub-section');

    // Clear and update the sub-section container
    subSectionContainer.replaceChildren();
    Array.from(newContainer.children).forEach(child => {
        subSectionContainer.appendChild(child);
    });

    debugLog('layout', '✅ Sub-section layout applied successfully');
}

function groupFieldsByLayout(fields) {
    const groups = [];
    let currentGroup = [];

    fields.forEach(field => {
        const width = getFieldLayoutWidth(field);
        const shouldBreak = getFieldLayoutBreak(field);

        // Start a new group if:
        // 1. Current field has a break attribute
        // 2. Adding this field would exceed 12 columns
        const currentWidth = currentGroup.reduce((sum, f) => sum + getFieldLayoutWidth(f), 0);
        if (shouldBreak || currentWidth + width > 12) {
            if (currentGroup.length > 0) {
                groups.push([...currentGroup]);
                currentGroup = [];
            }
        }

        currentGroup.push(field);

        // If this field fills up to 12 columns or has a break, start a new group
        const newWidth = currentGroup.reduce((sum, f) => sum + getFieldLayoutWidth(f), 0);
        if (newWidth === 12 || shouldBreak) {
            groups.push([...currentGroup]);
            currentGroup = [];
        }
    });

    // Add any remaining fields
    if (currentGroup.length > 0) {
        groups.push(currentGroup);
    }

    return groups;
}

function getFieldLayoutWidth(field) {
    const width = field.getAttribute('data-layout-width');
    const result = width ? parseInt(width, 10) : 12;
    debugLog('layout', `Field width: ${result} (from attribute: ${width})`);
    return result;
}

function getFieldLayoutBreak(field) {
    const breakValue = field.getAttribute('data-layout-break');
    const hasBreak = breakValue === 'true';
    debugLog('layout', `Field break: ${hasBreak}`);
    return hasBreak;
}

function createFlexibleLayoutContainer(fieldGroups) {
    debugLog('layout', '\nCreating flexible layout container...');
    const container = document.createElement('div');
    container.className = 'space-y-6';

    fieldGroups.forEach((group, groupIndex) => {
        debugLog('layout', `Creating row for group ${groupIndex + 1} with ${group.length} fields`);
        const rowDiv = document.createElement('div');
        // Use flex with negative margins for the row
        rowDiv.className = 'flex flex-wrap -mx-3 w-full';

        group.forEach((field, fieldIndex) => {
            const width = getFieldLayoutWidth(field);
            const percentWidth = (width / 12) * 100;
            debugLog('layout', `Adding field ${fieldIndex + 1} to row ${groupIndex + 1} with width ${width} (${percentWidth}%)`);

            // Detect blank spacer blocks
            const isBlank = field.getAttribute('data-item-type') === 'blank';

            // Create a wrapper div with percentage-based width
            const wrapper = document.createElement('div');
            // Add padding and set both class-based and inline width for better browser support
            // Use a smaller bottom margin to reduce vertical spacing between form items
            wrapper.className = `px-3 ${isBlank ? '' : 'mb-0'} min-w-0 flex-shrink-0`;
            wrapper.style.width = `${percentWidth}%`;
            wrapper.style.flexBasis = `${percentWidth}%`;
            wrapper.style.maxWidth = `${percentWidth}%`; // Add max-width to prevent flex-grow

            // Clone the field
            const fieldClone = field.cloneNode(true);

            // Sanitize any numeric and date/datetime inputs that may carry invalid string attributes like "None"
            try {
                const inputsToSanitize = fieldClone.querySelectorAll('input');
                inputsToSanitize.forEach(inp => {
                    const t = (inp.getAttribute('type') || inp.type || '').toLowerCase();
                    if (t === 'number' || t === 'date' || t === 'datetime-local') {
                        const attrVal = inp.getAttribute('value');
                        if (attrVal && (attrVal === 'None' || attrVal === 'null' || attrVal === 'undefined')) {
                            inp.value = '';
                            inp.setAttribute('value', '');
                        }
                    }
                });
            } catch (e) {
                debugLog('layout', `Sanitize error: ${e && e.message}`);
            }
            fieldClone.className = `${fieldClone.className} w-full`; // Ensure field takes full width of wrapper

            // Detect if the field should start hidden (covers various mechanisms)
            const isFieldInitiallyHidden = (
                fieldClone.classList.contains('hidden') ||
                fieldClone.classList.contains('relevance-hidden') ||
                field.style.display === 'none' ||
                window.getComputedStyle(field).display === 'none'
            );

            // If hidden, also hide its wrapper to remove vertical space
            if (isFieldInitiallyHidden) {
                wrapper.classList.add('hidden'); // Tailwind's hidden sets display:none
            }

            // Copy form element values and attributes
            debugLog('layout', '\nCopying form element values and attributes...');
            copyFormElementValues(field, fieldClone);

            // Add the cloned field to the wrapper
            wrapper.appendChild(fieldClone);
            rowDiv.appendChild(wrapper);
        });

        // If every wrapper inside the row is hidden, hide the entire row to avoid the gap produced by `space-y-*` utility
        const allWrappersHidden = Array.from(rowDiv.children).every(child => child.classList.contains('hidden'));
        if (allWrappersHidden) {
            rowDiv.classList.add('hidden');
        }

        container.appendChild(rowDiv);
    });

    debugLog('layout', '✅ Layout container created successfully');
    return container;
}

// Remove local copyFormElementValues function - now using unified version from form-item-utils.js

// Helper function to get event listeners
function getEventListeners(element, type) {
    // This is a simplified version since we can't actually get the listeners
    // We'll rely on the modules to reattach their listeners
    return [];
}

// Helper function to get all parent elements up to a certain point
function getParentChain(element, stopAt) {
    const parents = [];
    let current = element;

    while (current && current !== stopAt && current !== document.body) {
        parents.push(current);
        current = current.parentElement;
    }

    return parents;
}

export function applyLayoutToContainer(container) {
    debugLog('layout', `\n=== APPLYING LAYOUT TO REPEAT ENTRY ===`);
    debugLog('layout', `Container ID: ${container.id || 'unknown'}`);

    // Skip layout on mobile screens (less than 768px)
    if (window.innerWidth < 768) {
        debugLog('layout', '📱 Mobile screen detected - skipping repeat entry layout');
        return;
    }

    // Check if this container has fields that need layout
    const fieldsContainer = container.querySelector('.space-y-4');
    if (!fieldsContainer) {
        debugLog('layout', 'No .space-y-4 container found, skipping layout');
        return;
    }

    const formItems = Array.from(fieldsContainer.querySelectorAll('.form-item-block'));
    if (formItems.length === 0) {
        debugLog('layout', 'No form items found, skipping layout');
        return;
    }

    debugLog('layout', `Found ${formItems.length} form items to layout`);

    // Apply the same layout logic as in the main layout system
    const fieldGroups = groupFieldsByLayout(formItems);
    debugLog('layout', `Created ${fieldGroups.length} field groups for repeat entry`);

    const newContainer = createFlexibleLayoutContainer(fieldGroups);
    debugLog('layout', 'Created new layout container for repeat entry');

    // Replace the content
    fieldsContainer.replaceChildren();
    Array.from(newContainer.children).forEach(child => {
        fieldsContainer.appendChild(child);
    });

    // Re-initialize data availability for the new content
    initDataAvailability();

    debugLog('layout', `✅ Layout applied to repeat entry successfully`);
}

export function applyLayoutToSection(sectionContainer) {
    if (!sectionContainer) {
        return;
    }

    const fieldsContainer = sectionContainer.querySelector('.space-y-6');
    if (!fieldsContainer) {
        return;
    }

    applyFlexibleLayoutToSection(fieldsContainer);
}
