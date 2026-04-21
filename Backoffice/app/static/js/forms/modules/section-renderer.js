/**
 * Section Renderer Module
 *
 * Provides consistent rendering utilities for form sections and subsections.
 * Eliminates duplication between main sections, subsections, and repeat entries.
 */

import { debugLog, debugWarn, debugError } from './debug.js';
import { applyLayoutToContainer } from './layout.js';
import { initializeFieldListeners } from './form-item-utils.js';

/**
 * Render a complete section with consistent styling and behavior
 * @param {Object} sectionData - Section configuration
 * @param {Element} container - Container to render into
 * @param {Object} options - Rendering options
 */
export function renderSection(sectionData, container, options = {}) {
    const {
        isSubSection = false,
        isRepeatEntry = false,
        parentSectionOrder = '',
        existingData = {},
        templateStructure = {}
    } = options;

    debugLog('section-renderer', `Rendering section ${sectionData.id} (sub: ${isSubSection}, repeat: ${isRepeatEntry})`);

    // Create section element
    const sectionElement = createSectionElement(sectionData, isSubSection, isRepeatEntry);

    // Create section header
    const headerElement = createSectionHeader(sectionData, isSubSection, parentSectionOrder, templateStructure);
    sectionElement.appendChild(headerElement);

    // Create fields container
    const fieldsContainer = createFieldsContainer(isSubSection);

    // Render fields
    if (sectionData.fields && sectionData.fields.length > 0) {
        renderSectionFields(sectionData.fields, fieldsContainer, {
            sectionOrder: isSubSection ? parentSectionOrder : sectionData.display_order,
            isSubSection,
            existingData,
            templateStructure
        });
    }

    sectionElement.appendChild(fieldsContainer);

    // Render subsections if any
    if (sectionData.subsections && sectionData.subsections.length > 0) {
        renderSubSections(sectionData.subsections, fieldsContainer, {
            parentSectionOrder: sectionData.display_order,
            existingData,
            templateStructure
        });
    }

    // Add to container
    container.appendChild(sectionElement);

    // Apply layout if not a repeat entry (repeat entries handle their own layout)
    if (!isRepeatEntry) {
        applyLayoutToContainer(sectionElement);
    }

    // Initialize field listeners
    initializeFieldListeners(sectionElement);

    debugLog('section-renderer', `Section ${sectionData.id} rendered successfully`);

    return sectionElement;
}

/**
 * Create the main section element with appropriate classes and attributes
 */
function createSectionElement(sectionData, isSubSection, isRepeatEntry) {
    const sectionElement = document.createElement('div');

    // Base ID and classes
    sectionElement.id = `section-container-${sectionData.id}`;

    if (isSubSection) {
        sectionElement.className = 'bg-blue-50 p-4 rounded-lg border border-blue-200 mb-4 scroll-mt-20';
    } else if (isRepeatEntry) {
        sectionElement.className = 'bg-green-50 p-4 rounded-lg border border-green-200 mb-4';
    } else {
        sectionElement.className = 'bg-gray-50 p-6 rounded-lg border border-gray-200 mb-6 scroll-mt-20';
    }

    // Add data attributes
    sectionElement.setAttribute('data-section-type', sectionData.section_type || 'standard');
    sectionElement.setAttribute('data-page-number', sectionData.page_id || 1);

    if (sectionData.page && sectionData.page.display_name) {
        sectionElement.setAttribute('data-page-name', sectionData.page.display_name);
    } else if (sectionData.page && sectionData.page.name) {
        sectionElement.setAttribute('data-page-name', sectionData.page.name);
    }

    // Special attributes for dynamic indicators
    if (sectionData.section_type === 'dynamic_indicators' && sectionData.max_dynamic_indicators) {
        sectionElement.setAttribute('data-max-dynamic-indicators', sectionData.max_dynamic_indicators);
    }

    const aesIdVal = sectionData.aes_id;
    if (aesIdVal) {
        sectionElement.setAttribute('data-aes-id', aesIdVal);
    }

    return sectionElement;
}

/**
 * Create section header with consistent styling
 */
function createSectionHeader(sectionData, isSubSection, parentSectionOrder, templateStructure) {
    const headerElement = document.createElement('h' + (isSubSection ? '4' : '3'));
    headerElement.className = `text-xl font-semibold mb-4 pb-4 border-b ${isSubSection ? 'text-blue-700 border-blue-300' : 'text-gray-700'} flex items-center`;

    // Create header content
    const iconClass = isSubSection ? 'fas fa-chevron-right' : 'fas fa-layer-group';
    const iconElement = document.createElement('i');
    iconElement.className = `${iconClass} w-5 h-5 mr-2 ${isSubSection ? 'text-blue-500' : 'text-gray-500'}`;

    headerElement.appendChild(iconElement);

    // Add section order if display order is visible
    if (templateStructure.display_order_visible) {
        const orderSpan = document.createElement('span');
        orderSpan.className = 'text-xl font-semibold text-gray-700 mr-1';

        if (isSubSection && parentSectionOrder) {
            orderSpan.textContent = `${parentSectionOrder}.${sectionData.display_order}.`;
        } else {
            orderSpan.textContent = `${sectionData.display_order}.`;
        }

        headerElement.appendChild(orderSpan);
    }

    // Add section name
    const nameSpan = document.createElement('span');
    nameSpan.textContent =
        sectionData.display_name_resolved ||
        sectionData._display_name_resolved ||
        sectionData.display_name ||
        sectionData.name ||
        `Section ${sectionData.id}`;
    headerElement.appendChild(nameSpan);

    return headerElement;
}

/**
 * Create fields container with appropriate spacing
 */
function createFieldsContainer(isSubSection) {
    const container = document.createElement('div');
    container.className = isSubSection ? 'space-y-4' : 'space-y-6';
    return container;
}

/**
 * Render all fields in a section
 */
function renderSectionFields(fields, container, options) {
    const { sectionOrder, isSubSection, existingData, templateStructure } = options;

    debugLog('section-renderer', `Rendering ${fields.length} fields for section`);

    fields.forEach((field, index) => {
        const fieldElement = renderField(field, {
            sectionOrder,
            isSubSection,
            fieldIndex: index,
            existingData,
            templateStructure
        });

        if (fieldElement) {
            container.appendChild(fieldElement);
        }
    });
}

/**
 * Render a single field with consistent structure
 */
function renderField(field, options) {
    const { sectionOrder, isSubSection, fieldIndex, existingData, templateStructure } = options;

    // Use the reusable form item renderer template
    // This would integrate with the Jinja2 template macro we created
    // For now, create a simplified version in JavaScript

    const fieldElement = document.createElement('div');
    fieldElement.className = `form-group form-item-block border p-4 rounded-md bg-white ${isSubSection ? 'ml-6 border-l-4 border-l-blue-200 bg-blue-50' : ''}`;

    // Set field attributes
    fieldElement.setAttribute('data-item-id', field.item_id || field.id);
    fieldElement.setAttribute('data-item-type', field.item_type || 'question');
    fieldElement.setAttribute('data-layout-width', field.layout_column_width || 12);
    fieldElement.setAttribute('data-layout-break', field.layout_break_after ? 'true' : 'false');

    if (field.conditions) {
        fieldElement.setAttribute('data-relevance-condition', JSON.stringify(field.conditions));
    }

    // Create field content
    const fieldContent = createFieldContent(field, { sectionOrder, isSubSection, templateStructure });
    fieldElement.appendChild(fieldContent);

    // Set existing value if available
    if (existingData && existingData[field.item_id || field.id]) {
        setFieldValue(fieldElement, existingData[field.item_id || field.id]);
    }

    return fieldElement;
}

/**
 * Create field content based on field type
 */
function createFieldContent(field, options) {
    const { sectionOrder, isSubSection, templateStructure } = options;

    const container = document.createElement('div');
    container.className = 'flex items-start justify-between';

    // Main field area
    const mainArea = document.createElement('div');
    mainArea.className = 'flex-1 pr-2';

    // Field label
    const label = document.createElement('label');
    label.setAttribute('for', `field-${field.item_id || field.id}`);
    label.className = 'block text-md font-semibold text-gray-800 mb-1';

    // Label content with order
    let labelText = '';
    if (templateStructure.display_order_visible && sectionOrder) {
        labelText += `${sectionOrder}.${field.display_order}. `;
    }
    if (isSubSection) {
        labelText = `↳ ${field.display_label || field.label}`;
        const span = document.createElement('span');
        span.className = 'text-gray-600';
        span.textContent = labelText;
        label.appendChild(span);
    } else {
        labelText += field.display_label || field.label;
        label.textContent = labelText;
    }

    if (field.is_required) {
        const required = document.createElement('span');
        required.className = 'text-red-500';
        required.textContent = '*';
        label.appendChild(required);
    }

    mainArea.appendChild(label);

    // Field definition
    if (field.display_definition || field.definition) {
        const definition = document.createElement('p');
        definition.className = 'text-sm text-gray-600 mb-2 leading-relaxed';
        definition.textContent = field.display_definition || field.definition;
        mainArea.appendChild(definition);
    }

    // Field input
    const input = createFieldInput(field);
    mainArea.appendChild(input);

    container.appendChild(mainArea);

    // Data availability controls
    if (field.allow_data_not_available || field.allow_not_applicable) {
        const dataAvailability = createDataAvailabilityControls(field);
        container.appendChild(dataAvailability);
    }

    return container;
}

/**
 * Create appropriate input element based on field type
 */
function createFieldInput(field) {
    const fieldId = field.item_id || field.id;
    const fieldType = field.field_type || field.question_type || 'text';

    let input;

    switch (fieldType) {
        case 'number':
            input = document.createElement('input');
            input.type = 'number';
            input.className = 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm';
            break;

        case 'select':
        case 'single_choice':
            input = document.createElement('select');
            input.className = 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm';

            // Add options
            const defaultOption = document.createElement('option');
            defaultOption.value = '';
            defaultOption.textContent = 'Please select...';
            input.appendChild(defaultOption);

            if (field.options) {
                field.options.forEach(option => {
                    const optionElement = document.createElement('option');
                    optionElement.value = option;
                    optionElement.textContent = option;
                    input.appendChild(optionElement);
                });
            }
            break;

        case 'checkbox':
        case 'yes_no':
            input = createCheckboxGroup(field);
            break;

        default:
            input = document.createElement('input');
            input.type = 'text';
            input.className = 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm';
    }

    if (input.tagName === 'INPUT' || input.tagName === 'SELECT') {
        input.id = `field-${fieldId}`;
        input.name = `field_value[${fieldId}]`;

        if (field.is_required) {
            input.required = true;
        }
    }

    return input;
}

/**
 * Create checkbox group for yes/no or multi-choice fields
 */
function createCheckboxGroup(field) {
    const container = document.createElement('div');
    const fieldId = field.item_id || field.id;

    if (field.options && field.options.length > 2) {
        // Multi-choice checkboxes
        container.className = 'checkbox-field-container';

        field.options.forEach(option => {
            const label = document.createElement('label');
            label.className = 'inline-flex items-center mr-4 mb-2';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.name = `field_value[${fieldId}]`;
            checkbox.value = option;
            checkbox.className = 'form-checkbox h-4 w-4 text-blue-600';

            const span = document.createElement('span');
            span.className = 'ml-2 text-sm text-gray-700';
            span.textContent = option;

            label.appendChild(checkbox);
            label.appendChild(span);
            container.appendChild(label);
        });
    } else {
        // Yes/No checkboxes
        container.className = 'flex gap-4';

        ['yes', 'no'].forEach(value => {
            const label = document.createElement('label');
            label.className = 'inline-flex items-center';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.name = `field_value[${fieldId}]`;
            checkbox.value = value;
            checkbox.className = 'form-checkbox h-4 w-4 text-blue-600';

            const span = document.createElement('span');
            span.className = 'ml-2 text-sm text-gray-700';
            span.textContent = value.charAt(0).toUpperCase() + value.slice(1);

            label.appendChild(checkbox);
            label.appendChild(span);
            container.appendChild(label);
        });
    }

    return container;
}

/**
 * Create data availability controls
 */
function createDataAvailabilityControls(field) {
    const container = document.createElement('div');
    container.className = 'flex flex-col gap-2 ml-4';

    const fieldId = field.item_id || field.id;

    if (field.allow_data_not_available) {
        const label = document.createElement('label');
        label.className = 'inline-flex items-center text-sm';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = `field_${fieldId}_data_not_available`;
        checkbox.value = '1';
        checkbox.className = 'form-checkbox h-4 w-4 text-gray-600 data-availability-checkbox';

        const span = document.createElement('span');
        span.className = 'ml-2 text-gray-600';
        span.textContent = 'Data not available';

        label.appendChild(checkbox);
        label.appendChild(span);
        container.appendChild(label);
    }

    if (field.allow_not_applicable) {
        const label = document.createElement('label');
        label.className = 'inline-flex items-center text-sm';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = `field_${fieldId}_not_applicable`;
        checkbox.value = '1';
        checkbox.className = 'form-checkbox h-4 w-4 text-gray-600 data-availability-checkbox';

        const span = document.createElement('span');
        span.className = 'ml-2 text-gray-600';
        span.textContent = 'Not applicable';

        label.appendChild(checkbox);
        label.appendChild(span);
        container.appendChild(label);
    }

    return container;
}

/**
 * Render subsections within a parent section
 */
function renderSubSections(subsections, container, options) {
    const { parentSectionOrder, existingData, templateStructure } = options;

    debugLog('section-renderer', `Rendering ${subsections.length} subsections`);

    subsections.forEach(subsection => {
        renderSection(subsection, container, {
            isSubSection: true,
            parentSectionOrder,
            existingData,
            templateStructure
        });
    });
}

/**
 * Set field value from existing data
 */
function setFieldValue(fieldElement, value) {
    const input = fieldElement.querySelector('input, select, textarea');
    if (!input) return;

    switch (input.type) {
        case 'checkbox':
            if (value === 'yes' || value === 'no') {
                // Yes/no checkbox
                const group = fieldElement.querySelectorAll(`input[name="${input.name}"]`);
                group.forEach(cb => {
                    cb.checked = (cb.value === value);
                });
            } else if (Array.isArray(value)) {
                // Multi-choice checkboxes
                const group = fieldElement.querySelectorAll(`input[name="${input.name}"]`);
                group.forEach(cb => {
                    cb.checked = value.includes(cb.value);
                });
            }
            break;

        case 'radio':
            if (value) {
                const targetRadio = fieldElement.querySelector(`input[name="${input.name}"][value="${value}"]`);
                if (targetRadio) {
                    targetRadio.checked = true;
                }
            }
            break;

        default:
            input.value = value || '';
    }
}

// Export for use by other modules
export {
    renderField,
    createFieldInput,
    createCheckboxGroup,
    setFieldValue
};
