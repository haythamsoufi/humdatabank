// Advanced PDF Export Module - Professional IFRC Document Generation
import { debugLog } from '../modules/debug.js';

const MODULE_NAME = 'pdf-export';

/**
 * PDF / validation export URLs must stay in the same WebView when the Humanitarian Databank
 * mobile app embeds the form: window.open(..., '_blank') opens the system browser, which has
 * no session cookie and gets bounced to the login page.
 */
function openAssignmentExportUrl(url, popupFeatures) {
    try {
        const root = document.documentElement;
        const ua = (typeof navigator !== 'undefined' && navigator.userAgent) ? navigator.userAgent : '';
        const looksEmbeddedWebView = /\bwv\b/i.test(ua) || ua.includes('Flutter');
        const inMobileAppShell = window.isMobileApp === true
            || window.humdatabankMobileApp === true
            || window.IFRCMobileApp === true
            || (root && root.getAttribute('data-mobile-app') === 'true')
            || (root && root.classList && root.classList.contains('mobile-app'));
        if (inMobileAppShell || looksEmbeddedWebView) {
            window.location.assign(url);
            return;
        }
    } catch (_e) {
        /* fall through */
    }
    if (popupFeatures) {
        window.open(url, '_blank', popupFeatures);
    } else {
        window.open(url, '_blank');
    }
}

// Professional color palette and branding
const IFRC_BRANDING = {
    colors: {
        primary: [204, 0, 0],          // IFRC Red
        secondary: [227, 35, 35],       // Light IFRC Red
        accent: [153, 153, 153],        // Gray accent
        text: {
            primary: [44, 62, 80],      // Dark navy for body text
            secondary: [108, 117, 125],  // Medium gray for secondary text
            muted: [134, 142, 150]       // Light gray for muted text
        },
        background: {
            light: [248, 249, 250],     // Very light gray
            medium: [233, 236, 239],    // Light gray
            white: [255, 255, 255]      // Pure white
        },
        status: {
            success: [40, 167, 69],     // Green
            warning: [255, 193, 7],     // Yellow
            danger: [220, 53, 69],      // Red
            info: [23, 162, 184]        // Blue
        }
    },
    fonts: {
        primary: 'helvetica',
        monospace: 'courier',
        sizes: {
            h1: 24,
            h2: 18,
            h3: 14,
            h4: 12,
            body: 10,
            small: 8,
            tiny: 6
        },
        weights: {
            light: 'normal',
            normal: 'normal',
            bold: 'bold'
        }
    },
    layout: {
        margin: {
            top: 25,
            bottom: 25,
            left: 20,
            right: 20
        },
        spacing: {
            section: 12,
            paragraph: 6,
            line: 4,
            field: 8
        },
        borders: {
            thin: 0.1,
            medium: 0.3,
            thick: 0.5
        }
    }
};

// Advanced PDF Document Class
class ProfessionalPDFDocument {
    constructor(title, metadata = {}) {
        this.title = title;
        const orgName = window.ORG_NAME || 'Humanitarian Databank';
        this.metadata = {
            author: metadata.author || orgName,
            subject: metadata.subject || 'Data Collection Report',
            keywords: metadata.keywords || 'humanitarian, data, report',
            creator: `${orgName} System`,
            ...metadata
        };
        this.currentPage = 1;
        this.totalPages = 0;
        this.yPosition = IFRC_BRANDING.layout.margin.top;
        this.tableOfContents = [];
        this.statistics = {
            totalFields: 0,
            completedFields: 0,
            sections: 0,
            tables: 0,
            charts: 0
        };
        this.doc = null;
    }

    initialize() {
        this.doc = new jsPDF({
            orientation: 'portrait',
            unit: 'mm',
            format: 'a4'
        });

        // Set document metadata
        this.doc.setProperties({
            title: this.title,
            subject: this.metadata.subject,
            author: this.metadata.author,
            keywords: this.metadata.keywords,
            creator: this.metadata.creator
        });

        this.pageHeight = this.doc.internal.pageSize.height;
        this.pageWidth = this.doc.internal.pageSize.width;
        this.contentWidth = this.pageWidth - IFRC_BRANDING.layout.margin.left - IFRC_BRANDING.layout.margin.right;
        this.contentHeight = this.pageHeight - IFRC_BRANDING.layout.margin.top - IFRC_BRANDING.layout.margin.bottom;
    }

    // Advanced page management
    addPage() {
        this.doc.addPage();
        this.currentPage++;
        this.yPosition = IFRC_BRANDING.layout.margin.top;
        this.addPageHeader();
        this.addPageFooter();
        return this.yPosition;
    }

    checkPageBreak(neededHeight = 20, forceBreak = false) {
        // More conservative page break with better margins
        const bottomMargin = IFRC_BRANDING.layout.margin.bottom + 15; // Extra space for footer
        const availableHeight = this.pageHeight - bottomMargin - this.yPosition;

        if (availableHeight < neededHeight || forceBreak) {
            this.addPage();
            return true;
        }
        return false;
    }

    // Professional typography system
    setTextStyle(style = 'body', weight = 'normal', color = null) {
        const fontSize = IFRC_BRANDING.fonts.sizes[style] || IFRC_BRANDING.fonts.sizes.body;
        const textColor = color || IFRC_BRANDING.colors.text.primary;

        this.doc.setFontSize(fontSize);
        this.doc.setFont(IFRC_BRANDING.fonts.primary, weight);
        this.doc.setTextColor(textColor[0], textColor[1], textColor[2]);

        return fontSize;
    }

    // Advanced text rendering with enhanced typography and proper character spacing
    addText(text, x, y, options = {}) {
        const {
            style = 'body',
            weight = 'normal',
            color = null,
            maxWidth = null,
            align = 'left',
            indent = 0,
            lineSpacing = 1.2,
            charSpacing = 0
        } = options;

        if (!text || text.trim() === '') return y;

        // Clean and encode text to handle special characters
        const cleanText = this.cleanTextForPDF(text);
        if (!cleanText || cleanText.trim() === '') return y;

        const fontSize = this.setTextStyle(style, weight, color);
        const textWidth = maxWidth || (this.contentWidth - indent);

        // Set character spacing if specified (helps with spacing issues)
        if (charSpacing !== 0) {
            try {
                this.doc.setCharSpace(charSpacing);
            } catch (error) {
                // Character spacing not supported in this jsPDF version
                debugLog(MODULE_NAME, '⚠️ Character spacing not supported');
            }
        }

        // Improved line splitting with better spacing
        const lines = this.doc.splitTextToSize(cleanText, textWidth - 10); // More margin for cleaner appearance
        const lineHeight = fontSize * lineSpacing * 0.35; // Adjusted for better vertical spacing

        let currentY = y;

        lines.forEach((line, index) => {
            const trimmedLine = line.trim();
            if (trimmedLine) { // Only render non-empty lines
                try {
                    // Text alignment with better positioning
                    if (align === 'center') {
                        this.doc.text(trimmedLine, x + (textWidth / 2), currentY, {
                            align: 'center',
                            baseline: 'top'
                        });
                    } else if (align === 'right') {
                        this.doc.text(trimmedLine, x + textWidth, currentY, {
                            align: 'right',
                            baseline: 'top'
                        });
                    } else {
                        this.doc.text(trimmedLine, x + indent, currentY, {
                            baseline: 'top'
                        });
                    }
                } catch (textError) {
                    debugLog(MODULE_NAME, `⚠️ Text rendering error for "${trimmedLine}":`, textError.message);
                    // Fallback to basic text rendering
                    this.doc.text(trimmedLine, x + indent, currentY);
                }

                currentY += lineHeight;
            }
        });

        // Reset character spacing
        if (charSpacing !== 0) {
            try {
                this.doc.setCharSpace(0);
            } catch (error) {
                // Character spacing not supported
            }
        }

        return currentY + 3; // Add spacing after text block
    }

    // Advanced text cleaning for PDF rendering
    cleanTextForPDF(text) {
        if (!text) return '';

        let cleanedText = text.toString().trim();

        // Remove or replace corrupted encoding patterns
        cleanedText = cleanedText
            // Remove common encoding corruption patterns
            .replace(/Ø=Ý"/g, '')           // Remove specific corruption pattern
            .replace(/Ã¢â‚¬Å¡/g, '')       // Remove UTF-8 corruption
            .replace(/â€™/g, "'")          // Fix smart apostrophes
            .replace(/â€œ/g, '"')          // Fix smart quotes opening
            .replace(/â€\u009D/g, '"')     // Fix smart quotes closing
            .replace(/â€"/g, '-')          // Fix em dashes
            .replace(/Â /g, ' ')           // Remove non-breaking space corruption
            .replace(/\u00A0/g, ' ')       // Replace non-breaking spaces
            .replace(/\u2013/g, '-')       // En dash
            .replace(/\u2014/g, '-')       // Em dash
            .replace(/\u2018/g, "'")       // Left single quotation mark
            .replace(/\u2019/g, "'")       // Right single quotation mark
            .replace(/\u201C/g, '"')       // Left double quotation mark
            .replace(/\u201D/g, '"')       // Right double quotation mark
            .replace(/\u2026/g, '...')     // Horizontal ellipsis

            // Remove control characters and other problematic bytes
            .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '')

            // Replace problematic characters with safe alternatives
            .replace(/[""]/g, '"')         // Smart quotes
            .replace(/['']/g, "'")         // Smart apostrophes
            .replace(/[–—]/g, '-')         // Em/en dashes
            .replace(/…/g, '...')          // Ellipsis

            // Handle remaining non-ASCII characters
            .replace(/[^\x00-\x7F]/g, (char) => {
                // Extended character mapping
                const charMap = {
                    // Latin characters
                    'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a', 'å': 'a', 'æ': 'ae',
                    'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
                    'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
                    'ò': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o', 'ø': 'o',
                    'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
                    'ý': 'y', 'ÿ': 'y',
                    'ñ': 'n', 'ç': 'c', 'ß': 'ss',

                    // Uppercase variants
                    'À': 'A', 'Á': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A', 'Å': 'A', 'Æ': 'AE',
                    'È': 'E', 'É': 'E', 'Ê': 'E', 'Ë': 'E',
                    'Ì': 'I', 'Í': 'I', 'Î': 'I', 'Ï': 'I',
                    'Ò': 'O', 'Ó': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O', 'Ø': 'O',
                    'Ù': 'U', 'Ú': 'U', 'Û': 'U', 'Ü': 'U',
                    'Ý': 'Y', 'Ÿ': 'Y',
                    'Ñ': 'N', 'Ç': 'C',

                    // Currency and symbols
                    '€': 'EUR', '£': 'GBP', '¥': 'YEN', '$': 'USD',
                    '©': '(C)', '®': '(R)', '™': '(TM)',
                    '°': ' degrees', '%': '%', '±': '+/-',

                    // Mathematical symbols
                    '×': 'x', '÷': '/', '²': '2', '³': '3',
                    '½': '1/2', '¼': '1/4', '¾': '3/4',

                    // Misc
                    '§': 'section', '¶': 'paragraph'
                };

                const replacement = charMap[char];
                if (replacement) {
                    return replacement;
                }

                // If no mapping found, try to get the character code and handle it
                const charCode = char.charCodeAt(0);
                if (charCode > 127 && charCode < 256) {
                    // Return empty string for problematic extended ASCII
                    debugLog(MODULE_NAME, `⚠️ Removing problematic character: ${char} (code: ${charCode})`);
                    return '';
                }

                return char; // Keep character if it seems safe
            })

            // Clean up multiple spaces and trim
            .replace(/\s+/g, ' ')
            .trim();

        // Log if we cleaned up corruption
        if (cleanedText !== text.toString().trim()) {
            debugLog(MODULE_NAME, `🧹 Cleaned text: "${text}" -> "${cleanedText}"`);
        }

        return cleanedText;
    }

    // Professional header with text-based IFRC branding
    addPageHeader() {
        const headerStartY = 10;

        // Organization Logo/Brand (text-based)
        const orgName = window.ORG_NAME || 'Humanitarian Databank';
        this.yPosition = this.addText(
            orgName,
            IFRC_BRANDING.layout.margin.left,
            headerStartY,
            {
                style: 'h4',
                weight: 'bold',
                color: IFRC_BRANDING.colors.primary
            }
        );

        // Document title in header (text-based)
        const cleanTitle = this.cleanTextForPDF(this.title);
        this.addText(
            cleanTitle,
            IFRC_BRANDING.layout.margin.left,
            headerStartY,
            {
                style: 'small',
                weight: 'normal',
                color: IFRC_BRANDING.colors.text.secondary,
                align: 'center',
                maxWidth: this.contentWidth
            }
        );

        // Date in header (text-based)
        const currentDate = new Date().toLocaleDateString('en-GB');
        this.addText(
            currentDate,
            IFRC_BRANDING.layout.margin.left,
            headerStartY,
            {
                style: 'small',
                weight: 'normal',
                color: IFRC_BRANDING.colors.text.muted,
                align: 'right',
                maxWidth: this.contentWidth
            }
        );

        // Simple text-based separator line
        this.yPosition = this.addText(
            '─'.repeat(80), // Text-based line
            IFRC_BRANDING.layout.margin.left,
            this.yPosition + 2,
            {
                style: 'tiny',
                color: IFRC_BRANDING.colors.accent
            }
        );

        this.yPosition += 3;
    }

    // Professional footer with text-based page numbering
    addPageFooter() {
        const footerY = this.pageHeight - 15;

        // Text-based footer separator line
        this.addText(
            '─'.repeat(80), // Text-based line
            IFRC_BRANDING.layout.margin.left,
            footerY - 2,
            {
                style: 'tiny',
                color: IFRC_BRANDING.colors.accent
            }
        );

        // Footer text (left)
        const orgName = window.ORG_NAME || 'Humanitarian Databank';
        this.addText(
            `Generated by ${orgName}`,
            IFRC_BRANDING.layout.margin.left,
            footerY + 5,
            {
                style: 'tiny',
                color: IFRC_BRANDING.colors.text.muted
            }
        );

        // Page number (right)
        const pageText = `Page ${this.currentPage}`;
        this.addText(
            pageText,
            IFRC_BRANDING.layout.margin.left,
            footerY + 5,
            {
                style: 'tiny',
                color: IFRC_BRANDING.colors.text.muted,
                align: 'right',
                maxWidth: this.contentWidth
            }
        );

        // Report generation timestamp (center)
        const timestamp = new Date().toLocaleString('en-GB');
        this.addText(
            `Generated: ${timestamp}`,
            IFRC_BRANDING.layout.margin.left,
            footerY + 5,
            {
                style: 'tiny',
                color: IFRC_BRANDING.colors.text.muted,
                align: 'center',
                maxWidth: this.contentWidth
            }
        );
    }

    // Advanced box drawing with shadows and gradients
    drawAdvancedBox(x, y, width, height, options = {}) {
        const {
            fillColor = null,
            borderColor = IFRC_BRANDING.colors.accent,
            borderWidth = IFRC_BRANDING.layout.borders.thin,
            shadow = false,
            rounded = false,
            gradient = false
        } = options;

        // Shadow effect
        if (shadow) {
            this.doc.setFillColor(220, 220, 220);
            this.doc.rect(x + 1, y + 1, width, height, 'F');
        }

        // Main box
        if (fillColor) {
            this.doc.setFillColor(fillColor[0], fillColor[1], fillColor[2]);
            this.doc.rect(x, y, width, height, 'F');
        }

        // Border
        this.doc.setDrawColor(borderColor[0], borderColor[1], borderColor[2]);
        this.doc.setLineWidth(borderWidth);
        this.doc.rect(x, y, width, height, 'S');
    }

    // Calculate field height based on content with responsive width support
    calculateFieldHeight(label, value, fieldWidth = 12) {
        const baseHeight = 16; // Increased base height
        const lineHeight = 4; // Standard line height
        const padding = 8; // Top and bottom padding

        // Clean text before measuring
        const cleanLabel = this.cleanTextForPDF(label || '');
        const cleanValue = this.cleanTextForPDF(value || '');

        // Calculate available width based on field layout width
        const fieldWidthRatio = fieldWidth / 12; // Convert to ratio
        const availableWidth = (this.contentWidth * fieldWidthRatio) - 25;

        const labelLines = this.doc.splitTextToSize(cleanLabel, availableWidth).length;
        const valueLines = cleanValue ? this.doc.splitTextToSize(cleanValue, availableWidth).length : 1;

        // Calculate total height with proper spacing
        const totalLines = labelLines + valueLines;
        return baseHeight + (totalLines * lineHeight) + padding;
    }

    // Get field layout width similar to layout.js
    getFieldLayoutWidth(field) {
        const width = field.getAttribute('data-layout-width');
        return width ? parseInt(width, 10) : 12;
    }

    // Render fields with responsive layout
    renderFieldsWithLayout(fields, analyzer) {
        if (!fields || fields.length === 0) return;

        // Group fields by their layout properties (similar to layout.js)
        const fieldGroups = this.groupFieldsByLayout(fields);

        fieldGroups.forEach(group => {
            this.checkPageBreak(40); // Check for page break before each group

            const startY = this.yPosition;
            let maxHeight = 0;
            const fieldData = [];

            // First pass: calculate all field data
            group.forEach(field => {
                const fieldWidth = this.getFieldLayoutWidth(field);
                const label = field.querySelector('label');
                if (!label) return;

                const labelText = this.cleanTextForPDF(label.textContent.trim());
                if (!labelText) return;

                // Get field value
                let value = '';
                let fieldType = 'text';
                const input = field.querySelector('input, select, textarea');

                if (input) {
                    fieldType = input.type || input.tagName.toLowerCase();
                    if (input.type === 'checkbox' || input.type === 'radio') {
                        value = input.checked ? (input.value || 'Yes') : 'No';
                        fieldType = 'boolean';
                    } else if (input.tagName === 'SELECT') {
                        const selectedOption = input.options[input.selectedIndex];
                        value = selectedOption ? selectedOption.text : '';
                        fieldType = 'select';
                    } else if (input.type === 'number') {
                        value = input.value || '';
                        fieldType = 'number';
                    } else {
                        value = this.cleanTextForPDF(input.value || '');
                    }
                }

                analyzer.analyzeField(labelText, value, fieldType);

                const fieldHeight = this.calculateFieldHeight(labelText, value, fieldWidth);
                maxHeight = Math.max(maxHeight, fieldHeight);

                fieldData.push({
                    field,
                    labelText,
                    value,
                    fieldType,
                    fieldWidth,
                    fieldHeight
                });
            });

            if (fieldData.length === 0) return;

            // Second pass: render fields side by side
            let currentX = IFRC_BRANDING.layout.margin.left + 5;
            const availableWidth = this.contentWidth - 10;

            fieldData.forEach((data, index) => {
                const fieldWidthRatio = data.fieldWidth / 12;
                const fieldPxWidth = availableWidth * fieldWidthRatio;

                // Text-based field container (no vector boxes)
                // Just add a simple text-based border if needed
                if (fieldData.length > 1) { // Only add separators when multiple fields
                    // Add a subtle text-based separator
                    this.addText(
                        '│', // Vertical separator
                        currentX - 2,
                        startY + 2,
                        {
                            style: 'small',
                            color: IFRC_BRANDING.colors.accent
                        }
                    );
                }

                // Render field content
                const fieldIcon = getFieldTypeIcon(data.fieldType);
                let fieldY = startY + 4;

                fieldY = this.addText(
                    `${fieldIcon} ${data.labelText}`,
                    currentX + 3,
                    fieldY,
                    {
                        style: 'body',
                        weight: 'bold',
                        color: IFRC_BRANDING.colors.text.primary,
                        maxWidth: fieldPxWidth - 10
                    }
                );

                // Field value
                if (data.value && data.value.toString().trim()) {
                    const valueColor = getValueColor(data.value, data.fieldType);
                    const formattedValue = formatFieldValue(data.value, data.fieldType);

                    fieldY = this.addText(
                        formattedValue,
                        currentX + 3,
                        fieldY + 1,
                        {
                            style: 'body',
                            color: valueColor,
                            maxWidth: fieldPxWidth - 10
                        }
                    );
                } else {
                    fieldY = this.addText(
                        '[No data provided]',
                        currentX + 3,
                        fieldY + 1,
                        {
                            style: 'small',
                            color: IFRC_BRANDING.colors.text.muted,
                            maxWidth: fieldPxWidth - 10
                        }
                    );
                }

                currentX += fieldPxWidth;
            });

            this.yPosition = startY + maxHeight + IFRC_BRANDING.layout.spacing.field;
        });
    }

    // Group fields by layout (similar to layout.js)
    groupFieldsByLayout(fields) {
        const groups = [];
        let currentGroup = [];

        fields.forEach(field => {
            const width = this.getFieldLayoutWidth(field);
            const shouldBreak = field.getAttribute('data-layout-break') === 'true';

            // Start a new group if:
            // 1. Current field has a break attribute
            // 2. Adding this field would exceed 12 columns
            const currentWidth = currentGroup.reduce((sum, f) => sum + this.getFieldLayoutWidth(f), 0);
            if (shouldBreak || currentWidth + width > 12) {
                if (currentGroup.length > 0) {
                    groups.push([...currentGroup]);
                    currentGroup = [];
                }
            }

            currentGroup.push(field);

            // If this field fills up to 12 columns or has a break, start a new group
            const newWidth = currentGroup.reduce((sum, f) => sum + this.getFieldLayoutWidth(f), 0);
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

    // Enhanced disaggregation table rendering (only visible/selected modes)
    renderDisaggregationTable(disaggregationElement, analyzer) {
        // Skip if this disaggregation container is not currently visible/selected
        if (disaggregationElement.style.display === 'none' ||
            disaggregationElement.classList.contains('hidden') ||
            window.getComputedStyle(disaggregationElement).display === 'none') {
            debugLog(MODULE_NAME, '⏭️ Skipping hidden disaggregation table');
            return;
        }

        // Check if this is the selected reporting mode
        const parentFieldId = disaggregationElement.getAttribute('data-parent-id');
        const mode = disaggregationElement.getAttribute('data-mode');

        if (parentFieldId && mode) {
            // Find the reporting mode selection for this field
            const reportingModeInput = document.querySelector(`input[name="${parentFieldId}_reporting_mode"]:checked`);
            if (reportingModeInput && reportingModeInput.value !== mode) {
                debugLog(MODULE_NAME, `⏭️ Skipping disaggregation table - mode ${mode} not selected (selected: ${reportingModeInput.value})`);
                return;
            }
        }

        this.checkPageBreak(30);

        // Get table title
        const titleElement = disaggregationElement.querySelector('p, label, h5');
        const tableTitle = titleElement ? this.cleanTextForPDF(titleElement.textContent.trim()) : 'Disaggregated Data';

        // Table header with enhanced styling
        this.drawAdvancedBox(
            IFRC_BRANDING.layout.margin.left + 10,
            this.yPosition,
            this.contentWidth - 20,
            8,
            {
                fillColor: IFRC_BRANDING.colors.status.info,
                shadow: true
            }
        );

        this.yPosition = this.addText(
            `📊 ${tableTitle}`,
            IFRC_BRANDING.layout.margin.left + 13,
            this.yPosition + 6,
            {
                style: 'body',
                weight: 'bold',
                color: IFRC_BRANDING.colors.background.white
            }
        );

        // Extract and render table data
        const table = disaggregationElement.querySelector('table');
        if (table && this.isTableVisible(table)) {
            this.renderProfessionalTable(table, analyzer);
        } else {
            // Handle simple input fields
            const inputs = disaggregationElement.querySelectorAll('input[type="number"]:not([style*="display: none"])');
            if (inputs.length > 0) {
                this.renderSimpleDisaggregation(inputs);
            }
        }

        this.yPosition += 8;
        this.statistics.tables++;
    }

    // Check if table has visible content
    isTableVisible(table) {
        if (!table || table.style.display === 'none' || table.classList.contains('hidden')) {
            return false;
        }

        // Check if table has any visible rows with data
        const rows = table.querySelectorAll('tr');
        let hasVisibleData = false;

        rows.forEach(row => {
            const cells = row.querySelectorAll('td, th');
            cells.forEach(cell => {
                const input = cell.querySelector('input');
                if (input && input.value && input.value.trim()) {
                    hasVisibleData = true;
                }
                if (!input && cell.textContent.trim()) {
                    hasVisibleData = true;
                }
            });
        });

        return hasVisibleData;
    }

    // Professional table rendering with enhanced styling
    renderProfessionalTable(table, analyzer) {
        this.checkPageBreak(40);

        const rows = table.querySelectorAll('tr');
        if (rows.length === 0) return;

        const tableData = [];
        const tableStats = { total: 0, filled: 0, sum: 0 };

        // Extract table data and calculate statistics
        rows.forEach((row, rowIndex) => {
            const cells = row.querySelectorAll('th, td');
            const rowData = [];

            cells.forEach((cell, cellIndex) => {
                const input = cell.querySelector('input');
                let cellText = '';

                if (input && input.value) {
                    cellText = input.value;
                    tableStats.filled++;
                    if (!isNaN(parseFloat(input.value))) {
                        tableStats.sum += parseFloat(input.value);
                    }
                } else if (!input) {
                    cellText = cell.textContent.trim();
                }

                if (input) tableStats.total++;
                rowData.push(cellText || '');
            });

            if (rowData.some(cell => cell.trim())) {
                tableData.push(rowData);
            }
        });

        if (tableData.length === 0) return;

        // Calculate table dimensions
        const maxCols = Math.max(...tableData.map(row => row.length));
        const tableWidth = this.contentWidth - 30;
        const colWidth = tableWidth / maxCols;
        const rowHeight = 7;

        // Render table with professional styling and better page break handling
        tableData.forEach((row, rowIndex) => {
            const isHeader = rowIndex === 0;

            // More conservative page break for tables
            this.checkPageBreak(rowHeight + 5); // Extra margin for table content

            row.forEach((cell, colIndex) => {
                const cellX = IFRC_BRANDING.layout.margin.left + 15 + (colIndex * colWidth);
                const cellY = this.yPosition;

                // Enhanced cell styling
                const cellOptions = {
                    fillColor: isHeader
                        ? IFRC_BRANDING.colors.primary
                        : (rowIndex % 2 === 0 ? IFRC_BRANDING.colors.background.white : IFRC_BRANDING.colors.background.light),
                    borderColor: IFRC_BRANDING.colors.accent,
                    borderWidth: IFRC_BRANDING.layout.borders.thin
                };

                this.drawAdvancedBox(cellX, cellY, colWidth, rowHeight, cellOptions);

                // Enhanced cell text rendering
                if (cell && cell.trim()) {
                    const cellColor = isHeader
                        ? IFRC_BRANDING.colors.background.white
                        : (isNaN(parseFloat(cell)) ? IFRC_BRANDING.colors.text.primary : IFRC_BRANDING.colors.status.success);

                    const formattedCell = isNaN(parseFloat(cell)) ? cell : new Intl.NumberFormat('en-US').format(parseFloat(cell));

                    this.doc.setFontSize(8);
                    this.doc.setFont(IFRC_BRANDING.fonts.primary, isHeader ? 'bold' : 'normal');
                    this.doc.setTextColor(cellColor[0], cellColor[1], cellColor[2]);

                    const lines = this.doc.splitTextToSize(formattedCell, colWidth - 2);
                    this.doc.text(lines[0] || '', cellX + 1, cellY + 4.5);
                }
            });

            this.yPosition += rowHeight;
        });

        // Add table statistics
        if (tableStats.total > 0) {
            this.yPosition += 3;
            const completionRate = (tableStats.filled / tableStats.total * 100).toFixed(1);
            const statsText = `Completion: ${completionRate}% (${tableStats.filled}/${tableStats.total}) | Sum: ${new Intl.NumberFormat('en-US').format(tableStats.sum)}`;

            this.yPosition = this.addText(
                statsText,
                IFRC_BRANDING.layout.margin.left + 15,
                this.yPosition + 4,
                {
                    style: 'small',
                    color: IFRC_BRANDING.colors.text.secondary
                }
            );
        }
    }

    // Simple disaggregation inputs rendering
    renderSimpleDisaggregation(inputs) {
        const values = [];
        inputs.forEach(input => {
            if (input.value) {
                const label = input.previousElementSibling;
                const labelText = label ? label.textContent.trim() : 'Value';
                values.push(`${labelText}: ${new Intl.NumberFormat('en-US').format(parseFloat(input.value))}`);
            }
        });

        if (values.length > 0) {
            this.yPosition = this.addText(
                values.join(' | '),
                IFRC_BRANDING.layout.margin.left + 15,
                this.yPosition + 5,
                {
                    style: 'body',
                    color: IFRC_BRANDING.colors.status.success
                }
            );
        }
    }

    // Comprehensive statistics page
    renderStatisticsPage(statistics, numericSummary) {
        // Page title
        this.yPosition = this.addText(
            '📊 Report Analytics & Statistics',
            IFRC_BRANDING.layout.margin.left,
            this.yPosition + 10,
            {
                style: 'h1',
                weight: 'bold',
                color: IFRC_BRANDING.colors.primary,
                align: 'center'
            }
        );

        this.yPosition += 15;

        // Completion Overview
        this.renderCompletionOverview(statistics);

        // Numeric Data Analysis
        if (numericSummary) {
            this.yPosition += 10;
            this.renderNumericAnalysis(numericSummary);
        }

        // Field Type Distribution
        this.yPosition += 10;
        this.renderFieldTypeDistribution(statistics);

        // Response Quality Metrics
        this.yPosition += 10;
        this.renderQualityMetrics(statistics);
    }

    // Completion overview with visual indicators
    renderCompletionOverview(statistics) {
        this.checkPageBreak(40);

        // Section header
        this.drawAdvancedBox(
            IFRC_BRANDING.layout.margin.left,
            this.yPosition,
            this.contentWidth,
            12,
            {
                fillColor: IFRC_BRANDING.colors.status.info,
                shadow: true
            }
        );

        this.yPosition = this.addText(
            'Form Completion Overview',
            IFRC_BRANDING.layout.margin.left + 5,
            this.yPosition + 8,
            {
                style: 'h2',
                weight: 'bold',
                color: IFRC_BRANDING.colors.background.white
            }
        );

        this.yPosition += 8;

        // Completion rate visualization (text-based progress bar)
        const completionRate = parseFloat(statistics.completionRate);
        const progressBarWidth = 120;
        const filledWidth = (completionRate / 100) * progressBarWidth;

        // Progress bar background
        this.drawAdvancedBox(
            IFRC_BRANDING.layout.margin.left + 5,
            this.yPosition,
            progressBarWidth,
            6,
            {
                fillColor: IFRC_BRANDING.colors.background.medium
            }
        );

        // Progress bar fill
        const progressColor = completionRate >= 80
            ? IFRC_BRANDING.colors.status.success
            : completionRate >= 50
            ? IFRC_BRANDING.colors.status.warning
            : IFRC_BRANDING.colors.status.danger;

        this.drawAdvancedBox(
            IFRC_BRANDING.layout.margin.left + 5,
            this.yPosition,
            filledWidth,
            6,
            {
                fillColor: progressColor
            }
        );

        // Progress percentage
        this.yPosition = this.addText(
            `${completionRate}% Complete`,
            IFRC_BRANDING.layout.margin.left + progressBarWidth + 10,
            this.yPosition + 4,
            {
                style: 'body',
                weight: 'bold',
                color: progressColor
            }
        );

        // Detailed statistics
        const statsText = [
            `Total Fields: ${statistics.totalFields}`,
            `Completed Fields: ${statistics.completedFields}`,
            `Empty Fields: ${statistics.totalFields - statistics.completedFields}`,
            `Sections Processed: ${this.statistics.sections}`
        ];

        this.yPosition += 6;
        statsText.forEach(stat => {
            this.yPosition = this.addText(
                `• ${stat}`,
                IFRC_BRANDING.layout.margin.left + 10,
                this.yPosition + 4,
                {
                    style: 'body'
                }
            );
        });
    }

    // Numeric data analysis with charts
    renderNumericAnalysis(numericSummary) {
        this.checkPageBreak(50);

        // Section header
        this.drawAdvancedBox(
            IFRC_BRANDING.layout.margin.left,
            this.yPosition,
            this.contentWidth,
            12,
            {
                fillColor: IFRC_BRANDING.colors.status.success,
                shadow: true
            }
        );

        this.yPosition = this.addText(
            'Numeric Data Analysis',
            IFRC_BRANDING.layout.margin.left + 5,
            this.yPosition + 8,
            {
                style: 'h2',
                weight: 'bold',
                color: IFRC_BRANDING.colors.background.white
            }
        );

        this.yPosition += 15;

        // Summary statistics
        const summaryStats = [
            `Fields with Numeric Data: ${numericSummary.count}`,
            `Total Sum: ${new Intl.NumberFormat('en-US').format(numericSummary.sum)}`,
            `Average Value: ${numericSummary.average}`,
            `Minimum Value: ${new Intl.NumberFormat('en-US').format(numericSummary.minimum)}`,
            `Maximum Value: ${new Intl.NumberFormat('en-US').format(numericSummary.maximum)}`
        ];

        summaryStats.forEach(stat => {
            this.yPosition = this.addText(
                `📈 ${stat}`,
                IFRC_BRANDING.layout.margin.left + 5,
                this.yPosition + 4,
                {
                    style: 'body'
                }
            );
        });

        // Simple bar chart representation (top 5 values)
        if (numericSummary.fields.length > 0) {
            this.yPosition += 10;
            this.yPosition = this.addText(
                'Top 5 Numeric Values:',
                IFRC_BRANDING.layout.margin.left + 5,
                this.yPosition + 5,
                {
                    style: 'body',
                    weight: 'bold'
                }
            );

            const sortedFields = [...numericSummary.fields]
                .sort((a, b) => b.value - a.value)
                .slice(0, 5);

            const maxValue = Math.max(...sortedFields.map(f => f.value));

            sortedFields.forEach((field, index) => {
                const barWidth = (field.value / maxValue) * 80;

                // Draw bar
                this.drawAdvancedBox(
                    IFRC_BRANDING.layout.margin.left + 10,
                    this.yPosition + 3,
                    barWidth,
                    4,
                    {
                        fillColor: IFRC_BRANDING.colors.status.success
                    }
                );

                // Label and value
                this.yPosition = this.addText(
                    `${field.label.substring(0, 30)}...: ${new Intl.NumberFormat('en-US').format(field.value)}`,
                    IFRC_BRANDING.layout.margin.left + 95,
                    this.yPosition + 6,
                    {
                        style: 'small'
                    }
                );
            });
        }
    }

    // Field type distribution
    renderFieldTypeDistribution(statistics) {
        this.checkPageBreak(30);

        const distribution = {
            'Numeric Fields': statistics.numericFields.length,
            'Text Fields': statistics.textFields.length,
            'Choice Fields': Object.keys(statistics.choices).length,
            'Tables': this.statistics.tables
        };

        // Section header
        this.drawAdvancedBox(
            IFRC_BRANDING.layout.margin.left,
            this.yPosition,
            this.contentWidth,
            12,
            {
                fillColor: IFRC_BRANDING.colors.status.warning,
                shadow: true
            }
        );

        this.yPosition = this.addText(
            'Field Type Distribution',
            IFRC_BRANDING.layout.margin.left + 5,
            this.yPosition + 8,
            {
                style: 'h2',
                weight: 'bold',
                color: IFRC_BRANDING.colors.background.white
            }
        );

        this.yPosition += 15;

        Object.entries(distribution).forEach(([type, count]) => {
            if (count > 0) {
                this.yPosition = this.addText(
                    `${getFieldTypeIcon(type.toLowerCase())}: ${count}`,
                    IFRC_BRANDING.layout.margin.left + 5,
                    this.yPosition + 5,
                    {
                        style: 'body'
                    }
                );
            }
        });
    }

    // Quality metrics
    renderQualityMetrics(statistics) {
        this.checkPageBreak(25);

        const avgTextLength = statistics.textFields.length > 0
            ? (statistics.textFields.reduce((sum, field) => sum + field.length, 0) / statistics.textFields.length).toFixed(1)
            : 0;

        const qualityScore = this.calculateQualityScore(statistics);

        // Section header
        this.drawAdvancedBox(
            IFRC_BRANDING.layout.margin.left,
            this.yPosition,
            this.contentWidth,
            12,
            {
                fillColor: IFRC_BRANDING.colors.primary,
                shadow: true
            }
        );

        this.yPosition = this.addText(
            'Data Quality Assessment',
            IFRC_BRANDING.layout.margin.left + 5,
            this.yPosition + 8,
            {
                style: 'h2',
                weight: 'bold',
                color: IFRC_BRANDING.colors.background.white
            }
        );

        this.yPosition += 15;

        const metrics = [
            `Overall Quality Score: ${qualityScore}/100`,
            `Average Text Field Length: ${avgTextLength} characters`,
            `Data Completeness: ${statistics.completionRate}%`,
            `Response Consistency: ${this.calculateConsistencyScore(statistics)}%`
        ];

        metrics.forEach(metric => {
            this.yPosition = this.addText(
                `✓ ${metric}`,
                IFRC_BRANDING.layout.margin.left + 5,
                this.yPosition + 5,
                {
                    style: 'body'
                }
            );
        });
    }

    // Calculate overall quality score
    calculateQualityScore(statistics) {
        let score = 0;

        // Completion rate (40% weight)
        score += parseFloat(statistics.completionRate) * 0.4;

        // Data diversity (30% weight)
        const diversity = (statistics.numericFields.length + statistics.textFields.length + Object.keys(statistics.choices).length) / statistics.totalFields * 100;
        score += diversity * 0.3;

        // Response depth (30% weight)
        const avgTextLength = statistics.textFields.length > 0
            ? statistics.textFields.reduce((sum, field) => sum + field.length, 0) / statistics.textFields.length
            : 0;
        const depthScore = Math.min(avgTextLength / 50 * 100, 100); // Cap at 100
        score += depthScore * 0.3;

        return Math.round(score);
    }

    // Calculate consistency score
    calculateConsistencyScore(statistics) {
        // Simple consistency based on completion patterns
        const consistencyRate = statistics.totalFields > 0
            ? (statistics.completedFields / statistics.totalFields) * 100
            : 0;
        return Math.round(consistencyRate);
    }

    // Insert table of contents
    insertTableOfContents(tocEntries, pageNumber) {
        // Store current position
        const currentPage = this.currentPage;
        const currentY = this.yPosition;

        // Go to TOC page
        this.doc.setPage(pageNumber);
        this.yPosition = IFRC_BRANDING.layout.margin.top + 30;

        // TOC title
        this.yPosition = this.addText(
            'Table of Contents',
            IFRC_BRANDING.layout.margin.left,
            this.yPosition,
            {
                style: 'h1',
                weight: 'bold',
                color: IFRC_BRANDING.colors.primary,
                align: 'center'
            }
        );

        this.yPosition += 15;

        // TOC entries
        tocEntries.forEach(entry => {
            const indent = entry.level === 2 ? 10 : 0;
            const prefix = entry.number ? `${entry.number}. ` : '• ';

            // Create dotted line to page number
            const titleText = `${prefix}${entry.title}`;
            const pageText = `${entry.page}`;

            this.yPosition = this.addText(
                titleText,
                IFRC_BRANDING.layout.margin.left + indent,
                this.yPosition + 5,
                {
                    style: entry.level === 1 ? 'body' : 'small',
                    weight: entry.level === 1 ? 'bold' : 'normal'
                }
            );

            // Page number aligned to right
            this.doc.text(
                pageText,
                this.pageWidth - IFRC_BRANDING.layout.margin.right,
                this.yPosition - 1,
                { align: 'right' }
            );
        });

        // Return to original position
        this.doc.setPage(currentPage);
        this.yPosition = currentY;
    }

    // Add document security features
    addDocumentSecurity() {
        try {
            // Add watermark (commented out for now - can be enabled later)
            // this.addWatermark();

            // Set document properties for security (with error handling)
            try {
                this.doc.setProperties({
                    title: this.title,
                    subject: this.metadata.subject,
                    author: this.metadata.author,
                    keywords: this.metadata.keywords,
                    creator: this.metadata.creator,
                    producer: `${window.ORG_NAME || 'Humanitarian Databank'} - Secure PDF Generator`
                });
            } catch (propError) {
                debugLog(MODULE_NAME, '⚠️ Could not set all document properties:', propError.message);
                // Continue without full properties if there's an error
            }
        } catch (securityError) {
            debugLog(MODULE_NAME, '⚠️ Security features partially applied:', securityError.message);
            // Continue without security features if there's an error
        }
    }

    // Calculate overall quality score
    calculateQualityScore(statistics) {
        try {
            let score = 0;

            // Completion rate (40% weight)
            score += parseFloat(statistics.completionRate || 0) * 0.4;

            // Data diversity (30% weight)
            const totalDataFields = (statistics.numericFields?.length || 0) +
                                  (statistics.textFields?.length || 0) +
                                  (Object.keys(statistics.choices || {}).length);
            const diversity = statistics.totalFields > 0 ? (totalDataFields / statistics.totalFields * 100) : 0;
            score += diversity * 0.3;

            // Response depth (30% weight)
            const avgTextLength = (statistics.textFields?.length || 0) > 0
                ? (statistics.textFields.reduce((sum, field) => sum + (field.length || 0), 0) / statistics.textFields.length)
                : 0;
            const depthScore = Math.min(avgTextLength / 50 * 100, 100); // Cap at 100
            score += depthScore * 0.3;

            return Math.round(Math.max(0, Math.min(100, score))); // Ensure 0-100 range
        } catch (error) {
            debugLog(MODULE_NAME, '⚠️ Quality score calculation error:', error.message);
            return Math.round(parseFloat(statistics.completionRate || 0)); // Fallback
        }
    }

    /* Watermark functionality - commented out for now, can be enabled later
    addWatermark() {
        const totalPages = this.currentPage;

        for (let i = 1; i <= totalPages; i++) {
            this.doc.setPage(i);

            // Use light gray color instead of opacity for compatibility
            this.doc.setFontSize(36);
            this.doc.setFont(IFRC_BRANDING.fonts.primary, 'bold');
            this.doc.setTextColor(240, 240, 240); // Very light gray

            // Add diagonal watermark text
            const watermarkText = 'IFRC CONFIDENTIAL';
            const pageCenter = {
                x: this.pageWidth / 2,
                y: this.pageHeight / 2
            };

            // Add watermark text (simplified for compatibility)
            this.doc.text(
                watermarkText,
                pageCenter.x,
                pageCenter.y,
                {
                    align: 'center'
                }
            );

            // Add smaller watermark in bottom corner
            this.doc.setFontSize(8);
            this.doc.setTextColor(220, 220, 220);
            const orgName = window.ORG_NAME || 'Humanitarian Databank';
            this.doc.text(
                `Generated by ${orgName}`,
                this.pageWidth - 5,
                this.pageHeight - 5,
                {
                    align: 'right'
                }
            );
        }
    }
    */
}

// Statistical analysis helper
class FormDataAnalyzer {
    constructor() {
        this.statistics = {
            totalFields: 0,
            completedFields: 0,
            numericFields: [],
            textFields: [],
            choices: {},
            tables: [],
            completionRate: 0
        };
    }

    analyzeField(label, value, fieldType = 'text') {
        this.statistics.totalFields++;

        if (value && value.toString().trim()) {
            this.statistics.completedFields++;

            if (fieldType === 'number' && !isNaN(parseFloat(value))) {
                this.statistics.numericFields.push({
                    label: label,
                    value: parseFloat(value)
                });
            } else if (fieldType === 'select') {
                if (!this.statistics.choices[label]) {
                    this.statistics.choices[label] = {};
                }
                this.statistics.choices[label][value] = (this.statistics.choices[label][value] || 0) + 1;
            } else {
                this.statistics.textFields.push({
                    label: label,
                    value: value,
                    length: value.toString().length
                });
            }
        }
    }

    generateSummary() {
        this.statistics.completionRate = this.statistics.totalFields > 0
            ? (this.statistics.completedFields / this.statistics.totalFields * 100).toFixed(1)
            : 0;

        return this.statistics;
    }

    getNumericSummary() {
        if (this.statistics.numericFields.length === 0) return null;

        const values = this.statistics.numericFields.map(f => f.value);
        const sum = values.reduce((a, b) => a + b, 0);
        const avg = sum / values.length;
        const min = Math.min(...values);
        const max = Math.max(...values);

        return {
            count: values.length,
            sum: sum,
            average: avg.toFixed(2),
            minimum: min,
            maximum: max,
            fields: this.statistics.numericFields
        };
    }
}

// Export Progress Tracker
class ExportProgressTracker {
    constructor() {
        this.currentProgress = 0;
        this.currentStage = '';
        this.startTime = Date.now();
        this.stages = [
            'Initializing PDF export...',
            'Loading jsPDF library...',
            'Analyzing form structure...',
            'Extracting form data...',
            'Generating document layout...',
            'Processing sections...',
            'Creating data visualizations...',
            'Generating statistics...',
            'Building table of contents...',
            'Finalizing document...',
            'Saving PDF file...'
        ];
    }

    updateProgress(percentage, stage = null) {
        this.currentProgress = Math.min(percentage, 100);
        if (stage) this.currentStage = stage;

        const elapsed = Date.now() - this.startTime;
        const estimatedTotal = elapsed / (percentage / 100);
        const remaining = Math.max(0, estimatedTotal - elapsed);

        debugLog(MODULE_NAME, `📊 Progress: ${percentage}% - ${this.currentStage}`);

        // Update UI if progress element exists
        this.updateProgressUI(percentage, this.currentStage, remaining);
    }

    updateProgressUI(percentage, stage, remainingMs) {
        const progressElement = document.getElementById('pdf-export-progress');
        if (progressElement) {
            const remainingSeconds = Math.ceil(remainingMs / 1000);
            progressElement.replaceChildren();
            const progressBar = document.createElement('div');
            progressBar.className = 'progress-bar';
            progressBar.style.width = `${percentage}%`;
            const progressText = document.createElement('div');
            progressText.className = 'progress-text';
            progressText.textContent = `${stage} (${percentage}%) - Est. ${remainingSeconds}s remaining`;
            progressElement.appendChild(progressBar);
            progressElement.appendChild(progressText);
        }
    }

    complete() {
        this.updateProgress(100, 'PDF export completed!');
        debugLog(MODULE_NAME, `✅ Export completed in ${Date.now() - this.startTime}ms`);
    }
}

// Multilingual Support Helper
class MultilingualPDFHelper {
    constructor() {
        this.currentLanguage = this.detectLanguage();
        this.isRTL = ['ar', 'he', 'fa', 'ur'].includes(this.currentLanguage);
        this.textDirections = new Map();
    }

    detectLanguage() {
        // Try to detect language from page
        const htmlLang = document.documentElement.lang || 'en';
        const metaLang = document.querySelector('meta[name="language"]')?.content;
        return (metaLang || htmlLang).substring(0, 2).toLowerCase();
    }

    getTextDirection(text) {
        // Simple RTL detection for Arabic, Hebrew, etc.
        const rtlRegex = /[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F]/;
        return rtlRegex.test(text) ? 'rtl' : 'ltr';
    }

    formatTextForPDF(text, isLabel = false) {
        if (!text) return text;

        const direction = this.getTextDirection(text);
        this.textDirections.set(text, direction);

        // Handle RTL text rendering
        if (direction === 'rtl') {
            // Reverse text for proper PDF rendering (simplified approach)
            return text;
        }

        return text;
    }

    getAlignmentForText(text, defaultAlign = 'left') {
        const direction = this.textDirections.get(text) || this.getTextDirection(text);

        if (direction === 'rtl') {
            return defaultAlign === 'left' ? 'right' : defaultAlign === 'right' ? 'left' : defaultAlign;
        }

        return defaultAlign;
    }

    getLanguageSpecificFont() {
        const fontMap = {
            'ar': 'helvetica', // Would use Amiri or similar for Arabic
            'zh': 'helvetica', // Would use Chinese font
            'ja': 'helvetica', // Would use Japanese font
            'ko': 'helvetica', // Would use Korean font
            'hi': 'helvetica', // Would use Devanagari font
            'ru': 'helvetica', // Cyrillic support
            'default': 'helvetica'
        };

        return fontMap[this.currentLanguage] || fontMap.default;
    }
}

// Image and Attachment Handler
class PDFImageHandler {
    constructor() {
        this.supportedFormats = ['jpg', 'jpeg', 'png', 'gif', 'svg'];
        this.maxImageSize = 500; // Max width/height in PDF units
    }

    async processImages(formElement, pdfDoc) {
        const images = formElement.querySelectorAll('img');
        const processedImages = [];

        for (const img of images) {
            try {
                if (img.src && !img.src.startsWith('data:')) {
                    const processedImg = await this.convertImageToBase64(img);
                    if (processedImg) {
                        processedImages.push({
                            element: img,
                            data: processedImg,
                            position: this.getImagePosition(img)
                        });
                    }
                }
            } catch (error) {
                debugLog(MODULE_NAME, '⚠️ Failed to process image:', error);
            }
        }

        return processedImages;
    }

    async convertImageToBase64(imgElement) {
        return new Promise((resolve) => {
            try {
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');

                canvas.width = Math.min(imgElement.width, this.maxImageSize);
                canvas.height = Math.min(imgElement.height, this.maxImageSize);

                ctx.drawImage(imgElement, 0, 0, canvas.width, canvas.height);
                resolve(canvas.toDataURL('image/jpeg', 0.8));
            } catch (error) {
                debugLog(MODULE_NAME, '❌ Image conversion failed:', error);
                resolve(null);
            }
        });
    }

    getImagePosition(imgElement) {
        const rect = imgElement.getBoundingClientRect();
        return {
            x: rect.left,
            y: rect.top,
            width: rect.width,
            height: rect.height
        };
    }

    renderImageInPDF(pdfDoc, imageData, x, y, maxWidth, maxHeight) {
        try {
            // Calculate aspect ratio and fit within bounds
            const img = new Image();
            img.src = imageData.data;

            const aspectRatio = img.width / img.height;
            let width = Math.min(maxWidth, img.width);
            let height = width / aspectRatio;

            if (height > maxHeight) {
                height = maxHeight;
                width = height * aspectRatio;
            }

            pdfDoc.doc.addImage(imageData.data, 'JPEG', x, y, width, height);
            return y + height + 5;
        } catch (error) {
            debugLog(MODULE_NAME, '❌ Failed to render image in PDF:', error);
            return y;
        }
    }
}

// Performance Optimizer
class PDFPerformanceOptimizer {
    constructor() {
        this.batchSize = 10; // Process elements in batches
        this.memoryThreshold = 100 * 1024 * 1024; // 100MB
    }

    async processInBatches(items, processor) {
        const results = [];
        for (let i = 0; i < items.length; i += this.batchSize) {
            const batch = items.slice(i, i + this.batchSize);
            const batchResults = await Promise.all(batch.map(processor));
            results.push(...batchResults);

            // Check memory usage and garbage collect if needed
            if (this.shouldGarbageCollect()) {
                this.forceGarbageCollection();
            }

            // Small delay to prevent UI blocking
            await this.delay(1);
        }
        return results;
    }

    shouldGarbageCollect() {
        return (performance.memory?.usedJSHeapSize || 0) > this.memoryThreshold;
    }

    forceGarbageCollection() {
        if (window.gc) {
            window.gc();
        }
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Function to load jsPDF directly for text-based PDFs
function loadJsPDF() {
    return new Promise((resolve, reject) => {
        debugLog(MODULE_NAME, '📦 Loading jsPDF script for text-based PDF...');

        // Check if already loaded (try different global variable names)
        if (typeof window.jsPDF !== 'undefined') {
            debugLog(MODULE_NAME, '✅ jsPDF already available on window.jsPDF');
            resolve(window.jsPDF);
            return;
        }
        if (typeof window.jspdf !== 'undefined' && window.jspdf.jsPDF) {
            debugLog(MODULE_NAME, '✅ jsPDF already available on window.jspdf.jsPDF');
            resolve(window.jspdf.jsPDF);
            return;
        }

        // Create script element for jsPDF (using local file)
        const script = document.createElement('script');
            script.src = (window.getStaticUrl && window.getStaticUrl('js/forms/lib/jspdf.umd.min.js')) || '/static/js/forms/lib/jspdf.umd.min.js';
        script.onload = function() {
            debugLog(MODULE_NAME, '✅ jsPDF script loaded successfully');

            // Check different possible global variable names
            if (typeof window.jsPDF !== 'undefined') {
                debugLog(MODULE_NAME, '✅ Found jsPDF on window.jsPDF');
                resolve(window.jsPDF);
            } else if (typeof window.jspdf !== 'undefined' && window.jspdf.jsPDF) {
                debugLog(MODULE_NAME, '✅ Found jsPDF on window.jspdf.jsPDF');
                resolve(window.jspdf.jsPDF);
            } else if (typeof jsPDF !== 'undefined') {
                debugLog(MODULE_NAME, '✅ Found jsPDF in global scope');
                window.jsPDF = jsPDF;
                resolve(jsPDF);
            } else if (typeof jspdf !== 'undefined' && jspdf.jsPDF) {
                debugLog(MODULE_NAME, '✅ Found jsPDF in global jspdf object');
                window.jsPDF = jspdf.jsPDF;
                resolve(jspdf.jsPDF);
            } else {
                debugLog(MODULE_NAME, '❌ jsPDF not found after script load');
                debugLog(MODULE_NAME, 'Available globals:', Object.keys(window).filter(k => k.toLowerCase().includes('pdf')));
                reject(new Error('jsPDF not available after script load'));
            }
        };
        script.onerror = function() {
            debugLog(MODULE_NAME, '❌ Failed to load jsPDF script');
            reject(new Error('Failed to load jsPDF script'));
        };

        document.head.appendChild(script);
    });
}

/**
 * Advanced Professional PDF Export with IFRC Branding and Analytics
 * Features: Professional styling, statistics, charts, TOC, multilingual, progress tracking
 */
export async function exportToPDF(formId, title) {
    // Initialize progress tracking
    const progressTracker = new ExportProgressTracker();

    try {
        debugLog(MODULE_NAME, '📄 Starting advanced PDF export with professional formatting...');
        console.log('Starting sophisticated PDF export for form:', formId);
        progressTracker.updateProgress(5, 'Initializing PDF export...');

        // Load jsPDF for text-based PDF generation
        let jsPDF;
        try {
            progressTracker.updateProgress(10, 'Loading jsPDF library...');
            jsPDF = await loadJsPDF();
            debugLog(MODULE_NAME, '✅ jsPDF loaded successfully');
            // Make jsPDF available globally for our classes
            window.jsPDF = jsPDF;
        } catch (error) {
            debugLog(MODULE_NAME, '❌ jsPDF loading failed:', error.message);
            throw new Error('PDF library could not be loaded. Please check your internet connection and try again.');
        }

        // Get the form element or a suitable fallback container in read-only views
        let formElement = document.getElementById(formId);
        if (!formElement) {
            // Fallbacks for submitted/validated (read-only) pages where the <form> is not rendered
            const fallbackContainer = document.getElementById('sections-container')
                || document.querySelector('[id^="section-container-"]')
                || document.body;
            formElement = fallbackContainer;
            debugLog(MODULE_NAME, `ℹ️ Using fallback container for PDF export (no form present).`);
        }

        progressTracker.updateProgress(15, 'Analyzing form structure...');
        debugLog(MODULE_NAME, '🔄 Initializing professional PDF document...');

        // Initialize advanced components
        const pdfDoc = new ProfessionalPDFDocument(title);
        const analyzer = new FormDataAnalyzer();
        const multilingualHelper = new MultilingualPDFHelper();
        const imageHandler = new PDFImageHandler();
        const performanceOptimizer = new PDFPerformanceOptimizer();

        pdfDoc.initialize();

        // Process images if any
        progressTracker.updateProgress(20, 'Processing images and attachments...');
        const processedImages = await imageHandler.processImages(formElement, pdfDoc);

        // Start with first page header and footer
        pdfDoc.addPageHeader();
        pdfDoc.addPageFooter();

        // Add document title page (text-based)
        pdfDoc.checkPageBreak(50);

        // Title page decorative border (text-based)
        pdfDoc.yPosition = pdfDoc.addText(
            '╔' + '═'.repeat(60) + '╗',
            IFRC_BRANDING.layout.margin.left,
            pdfDoc.yPosition + 15,
            {
                style: 'body',
                color: IFRC_BRANDING.colors.primary,
                align: 'center'
            }
        );

        // Get country name from form or page context
        const countryName = getCountryNameForReport();
        const fullTitle = countryName
            ? `${title || 'IFRC Data Collection Report'} - ${countryName}`
            : (title || 'IFRC Data Collection Report');

        pdfDoc.yPosition = pdfDoc.addText(
            fullTitle,
            IFRC_BRANDING.layout.margin.left,
            pdfDoc.yPosition + 8,
            {
                style: 'h1',
                weight: 'bold',
                color: IFRC_BRANDING.colors.primary,
                align: 'center',
                charSpacing: 0.2 // Better spacing for main title
            }
        );

        // Close decorative border (text-based)
        pdfDoc.yPosition = pdfDoc.addText(
            '╚' + '═'.repeat(60) + '╝',
            IFRC_BRANDING.layout.margin.left,
            pdfDoc.yPosition + 5,
            {
                style: 'body',
                color: IFRC_BRANDING.colors.primary,
                align: 'center'
            }
        );

        // Add report metadata
        const reportDate = new Date().toLocaleDateString('en-GB', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });

        pdfDoc.yPosition = pdfDoc.addText(
            `Report Generated: ${reportDate}`,
            IFRC_BRANDING.layout.margin.left,
            pdfDoc.yPosition + 10,
            {
                style: 'body',
                align: 'center',
                color: IFRC_BRANDING.colors.text.secondary
            }
        );

        // Add assignment details with professional styling
        const assignmentDetails = document.querySelector('.bg-white.p-6.rounded-lg.shadow.border.border-gray-200.mb-6');
        if (assignmentDetails) {
            pdfDoc.checkPageBreak(40);
            pdfDoc.yPosition += 20;

            // Create text-based executive summary section
            pdfDoc.yPosition = pdfDoc.addText(
                '┌' + '─'.repeat(50) + '┐',
                IFRC_BRANDING.layout.margin.left,
                pdfDoc.yPosition,
                {
                    style: 'small',
                    color: IFRC_BRANDING.colors.primary
                }
            );

            pdfDoc.yPosition = pdfDoc.addText(
                '│  📋 EXECUTIVE SUMMARY' + ' '.repeat(26) + '│',
                IFRC_BRANDING.layout.margin.left,
                pdfDoc.yPosition + 1,
                {
                    style: 'h3',
                    weight: 'bold',
                    color: IFRC_BRANDING.colors.primary
                }
            );

            pdfDoc.yPosition = pdfDoc.addText(
                '├' + '─'.repeat(50) + '┤',
                IFRC_BRANDING.layout.margin.left,
                pdfDoc.yPosition + 1,
                {
                    style: 'small',
                    color: IFRC_BRANDING.colors.primary
                }
            );

            const titleElement = assignmentDetails.querySelector('h2');
            if (titleElement) {
                pdfDoc.yPosition = pdfDoc.addText(
                    `│  ${multilingualHelper.formatTextForPDF(titleElement.textContent.trim())}`,
                    IFRC_BRANDING.layout.margin.left,
                    pdfDoc.yPosition + 2,
                    {
                        style: 'body',
                        weight: 'bold'
                    }
                );
            }

            const details = assignmentDetails.querySelectorAll('p');
            details.forEach(detail => {
                if (!detail.querySelector('button')) {
                    const cleanDetail = multilingualHelper.formatTextForPDF(detail.textContent.trim());
                    pdfDoc.yPosition = pdfDoc.addText(
                        `│  ${cleanDetail}`,
                        IFRC_BRANDING.layout.margin.left,
                        pdfDoc.yPosition + 1,
                        {
                            style: 'body',
                            color: IFRC_BRANDING.colors.text.secondary
                        }
                    );
                }
            });

            // Close the executive summary box
            pdfDoc.yPosition = pdfDoc.addText(
                '└' + '─'.repeat(50) + '┘',
                IFRC_BRANDING.layout.margin.left,
                pdfDoc.yPosition + 2,
                {
                    style: 'small',
                    color: IFRC_BRANDING.colors.primary
                }
            );

            pdfDoc.yPosition += 10;
        }

        // Table of Contents preparation
        const tocEntries = [];
        let currentPageForToc = pdfDoc.currentPage;

        // Add new page for content
        pdfDoc.addPage();

        // Process ALL form sections including hidden paginated sections
        progressTracker.updateProgress(40, 'Discovering all form sections...');

        // First, make all sections visible to capture complete form data
        const allSections = document.querySelectorAll('[id^="section-container-"]');
        const sectionStates = new Map(); // Store original visibility states

        // Store original states and make all sections visible
        allSections.forEach(section => {
            const originalDisplay = section.style.display;
            const originalVisibility = window.getComputedStyle(section).display;
            sectionStates.set(section.id, {
                display: originalDisplay,
                computedDisplay: originalVisibility,
                wasHidden: originalDisplay === 'none' || section.classList.contains('hidden')
            });

            // Make section visible for data extraction
            section.style.display = '';
            section.classList.remove('hidden');
        });

        debugLog(MODULE_NAME, `📄 Found ${allSections.length} total sections (including paginated sections)`);
        progressTracker.updateProgress(45, 'Processing all form sections...');

        let sectionCounter = 1;
        let processedSections = 0;

        // Process sections synchronously due to PDF positioning requirements
        for (let i = 0; i < allSections.length; i++) {
            const section = allSections[i];
            processedSections++;

            // Update progress
            const sectionProgress = 45 + (processedSections / allSections.length) * 25;
            progressTracker.updateProgress(sectionProgress, `Processing section ${processedSections}/${allSections.length}...`);

            // Skip repeat sections as they may have complex structures
            const sectionType = section.getAttribute('data-section-type');
            if (sectionType === 'repeat') {
                debugLog(MODULE_NAME, `⏭️ Skipping repeat section ${section.id} - will be processed separately`);
                continue;
            }

            // Section title with enhanced styling
            const sectionTitle = section.querySelector('h3, h4');
            if (sectionTitle) {
                const isMainSection = section.querySelector('h3') !== null;
                let sectionText = multilingualHelper.formatTextForPDF(sectionTitle.textContent.trim());

                // Add to table of contents
                tocEntries.push({
                    title: sectionText,
                    page: pdfDoc.currentPage,
                    level: isMainSection ? 1 : 2,
                    number: isMainSection ? sectionCounter++ : null
                });

                pdfDoc.checkPageBreak(30);

                // Create text-based section header with enhanced typography
                pdfDoc.checkPageBreak(20);

                const sectionNumber = isMainSection ? `${sectionCounter - 1}. ` : '';
                const sectionPrefix = isMainSection ? '■ ' : '▪ '; // Text-based bullets

                // Add text-based section divider line above main sections
                if (isMainSection) {
                    pdfDoc.yPosition = pdfDoc.addText(
                        '═'.repeat(60), // Double line for main sections
                        IFRC_BRANDING.layout.margin.left,
                        pdfDoc.yPosition + 3,
                        {
                            style: 'small',
                            color: IFRC_BRANDING.colors.primary
                        }
                    );
                }

                // Section title (text-based, no vector boxes)
                pdfDoc.yPosition = pdfDoc.addText(
                    `${sectionPrefix}${sectionNumber}${sectionText}`,
                    IFRC_BRANDING.layout.margin.left,
                    pdfDoc.yPosition + 2,
                    {
                        style: isMainSection ? 'h2' : 'h3',
                        weight: 'bold',
                        color: isMainSection ? IFRC_BRANDING.colors.primary : IFRC_BRANDING.colors.secondary,
                        align: multilingualHelper.getAlignmentForText(sectionText, 'left'),
                        charSpacing: 0.1 // Slightly increased character spacing for headers
                    }
                );

                // Add underline for main sections (text-based)
                if (isMainSection) {
                    pdfDoc.yPosition = pdfDoc.addText(
                        '─'.repeat(Math.min(sectionText.length + 10, 60)), // Underline
                        IFRC_BRANDING.layout.margin.left,
                        pdfDoc.yPosition,
                        {
                            style: 'tiny',
                            color: IFRC_BRANDING.colors.primary
                        }
                    );
                }

                pdfDoc.yPosition += IFRC_BRANDING.layout.spacing.section;
                pdfDoc.statistics.sections++;
            }

            // Process form fields with responsive layout (like layout.js)
            const fieldsContainer = section.querySelector('.space-y-6, .space-y-4');
            if (fieldsContainer) {
                const fields = Array.from(fieldsContainer.querySelectorAll('.form-item-block'));
                const visibleFields = fields.filter(field =>
                    field.style.display !== 'none' &&
                    !field.classList.contains('hidden') &&
                    field.querySelector('label') // Must have a label
                );

                if (visibleFields.length > 0) {
                    // Use responsive layout rendering
                    pdfDoc.renderFieldsWithLayout(visibleFields, analyzer);

                    // Handle disaggregation tables separately after field rendering
                    visibleFields.forEach(field => {
                        const disaggregationInputs = field.querySelectorAll('.disaggregation-inputs');
                        disaggregationInputs.forEach(disaggregation => {
                            pdfDoc.renderDisaggregationTable(disaggregation, analyzer);
                        });
                    });
                }
            } else {
                // Fallback to old method if no container found
                const fields = section.querySelectorAll('.form-item-block');
                const fieldArray = Array.from(fields).filter(field =>
                    field.style.display !== 'none' &&
                    !field.classList.contains('hidden') &&
                    field.querySelector('label')
                );

                if (fieldArray.length > 0) {
                    pdfDoc.renderFieldsWithLayout(fieldArray, analyzer);
                }
            }

            pdfDoc.yPosition += IFRC_BRANDING.layout.spacing.section + 5; // Extra spacing between sections

            // Small delay to prevent UI blocking
            await performanceOptimizer.delay(1);
        }

        // Restore original section visibility states
        progressTracker.updateProgress(70, 'Restoring form state...');
        allSections.forEach(section => {
            const state = sectionStates.get(section.id);
            if (state) {
                if (state.wasHidden) {
                    section.style.display = 'none';
                    if (!section.classList.contains('hidden')) {
                        section.classList.add('hidden');
                    }
                } else {
                    section.style.display = state.display || '';
                }
            }
        });

        debugLog(MODULE_NAME, '🔄 Restored original section visibility states');

        // Generate comprehensive statistics page
        progressTracker.updateProgress(75, 'Generating statistics and analytics...');
        const statistics = analyzer.generateSummary();
        const numericSummary = analyzer.getNumericSummary();

        pdfDoc.addPage();
        pdfDoc.renderStatisticsPage(statistics, numericSummary);

        // Insert Table of Contents at the beginning
        progressTracker.updateProgress(85, 'Building table of contents...');
        if (tocEntries.length > 0) {
            pdfDoc.insertTableOfContents(tocEntries, currentPageForToc);
        }

        // Process and embed images
        progressTracker.updateProgress(90, 'Processing embedded content...');
        if (processedImages.length > 0) {
            debugLog(MODULE_NAME, `📷 Processing ${processedImages.length} images...`);
            // Note: Images would be embedded at appropriate positions during section rendering
        }

        // Generate enhanced filename with metadata and quality indicators
        progressTracker.updateProgress(95, 'Finalizing document...');
        const now = new Date();
        const timestamp = now.toISOString().slice(0, 19).replace(/:/g, '-');
        const completionRate = Math.round(statistics.completionRate);
        let qualityScore;
        try {
            qualityScore = pdfDoc.calculateQualityScore ? pdfDoc.calculateQualityScore(statistics) : completionRate;
        } catch (qualityError) {
            debugLog(MODULE_NAME, '⚠️ Quality score calculation failed:', qualityError.message);
            qualityScore = completionRate; // Fallback to completion rate
        }

        // Generate enhanced filename with country and metadata
        const countryForFilename = getCountryNameForReport();
        const cleanTitle = title?.replace(/[^a-zA-Z0-9\s]/g, '') || 'Form_Export';
        const cleanCountry = countryForFilename?.replace(/[^a-zA-Z0-9\s]/g, '') || '';

        let filename;
        if (cleanCountry) {
            filename = `IFRC_${cleanCountry.replace(/\s+/g, '_')}_${cleanTitle.replace(/\s+/g, '_')}_${completionRate}pct_Q${qualityScore}_${timestamp}.pdf`;
        } else {
            filename = `IFRC_${cleanTitle.replace(/\s+/g, '_')}_${completionRate}pct_Q${qualityScore}_${timestamp}.pdf`;
        }

        debugLog(MODULE_NAME, '💾 Saving professional PDF as:', filename);
        debugLog(MODULE_NAME, '📊 Document statistics:', statistics);

        // Add document security, watermarks and metadata (with error handling)
        try {
            pdfDoc.addDocumentSecurity();
        } catch (securityError) {
            debugLog(MODULE_NAME, '⚠️ Security features could not be applied:', securityError.message);
            // Continue without security features
        }

        // Update final progress
        progressTracker.updateProgress(100, 'Saving PDF file...');
        pdfDoc.doc.save(filename);

        // Complete progress tracking
        progressTracker.complete();

        debugLog(MODULE_NAME, '✅ Professional PDF export completed successfully');

        // Show comprehensive completion summary
        const exportSummary = {
            filename: filename,
            title: title,
            country: countryForFilename,
            pages: pdfDoc.currentPage,
            totalFields: statistics.totalFields,
            completedFields: statistics.completedFields,
            completionRate: statistics.completionRate,
            sections: pdfDoc.statistics.sections,
            tables: pdfDoc.statistics.tables,
            numericFields: statistics.numericFields.length,
            textFields: statistics.textFields.length,
            choiceFields: Object.keys(statistics.choices).length,
            images: processedImages.length,
            language: multilingualHelper.currentLanguage,
            isRTL: multilingualHelper.isRTL,
            qualityScore: qualityScore,
            exportTime: Date.now() - progressTracker.startTime
        };

        console.log('🎉 Advanced PDF Export Completed Successfully!');
        console.log('📊 Export Summary:', exportSummary);

        // Return summary for potential use by calling code
        return exportSummary;

    } catch (error) {
        debugLog(MODULE_NAME, '❌ Professional PDF export failed:', error.message);
        console.error('Advanced PDF Export Error:', error);

        // Update progress tracker with error
        if (progressTracker) {
            progressTracker.updateProgress(0, `Export failed: ${error.message}`);
        }

        throw error;
    }
}

// Helper function to extract country name from various sources
function getCountryNameForReport() {
    // Try multiple sources to find the country name

    // 1. Check form context or assignment details
    const assignmentDetails = document.querySelector('.bg-white.p-6.rounded-lg.shadow.border.border-gray-200.mb-6');
    if (assignmentDetails) {
        // Look for country information in assignment details
        const detailParagraphs = assignmentDetails.querySelectorAll('p');
        for (const p of detailParagraphs) {
            const text = p.textContent.trim();
            // Look for patterns like "Country: X" or "Country Name: X"
            const countryMatch = text.match(/(?:country|country name):\s*([^,\n]+)/i);
            if (countryMatch && countryMatch[1]) {
                return countryMatch[1].trim();
            }
        }
    }

    // 2. Check URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const countryParam = urlParams.get('country') || urlParams.get('country_id');
    if (countryParam) {
        return countryParam;
    }

    // 3. Check form fields for country selection
    const countrySelects = document.querySelectorAll('select[name*="country"], select[name*="Country"]');
    for (const select of countrySelects) {
        const selectedOption = select.options[select.selectedIndex];
        if (selectedOption && selectedOption.text && selectedOption.text !== '' && selectedOption.text !== 'Select...') {
            return selectedOption.text;
        }
    }

    // 4. Check hidden inputs or data attributes
    const countryInputs = document.querySelectorAll('input[name*="country"], input[data-country]');
    for (const input of countryInputs) {
        const value = input.value || input.getAttribute('data-country');
        if (value && value.trim() && !value.match(/^\d+$/)) { // Avoid country IDs
            return value.trim();
        }
    }

    // 5. Check page title or breadcrumbs
    const pageTitle = document.title;
    const titleCountryMatch = pageTitle.match(/([A-Za-z\s]+)\s*-\s*IFRC/);
    if (titleCountryMatch && titleCountryMatch[1]) {
        return titleCountryMatch[1].trim();
    }

    // 6. Check breadcrumbs or navigation
    const breadcrumbs = document.querySelectorAll('.breadcrumb a, .breadcrumb span, nav a');
    for (const breadcrumb of breadcrumbs) {
        const text = breadcrumb.textContent.trim();
        // Skip common navigation terms
        if (text && !text.match(/^(home|dashboard|forms|admin|back|edit|view|submit)$/i) && text.length > 2) {
            // If it looks like a country name (capitalized, not too long)
            if (text.match(/^[A-Z][a-z\s]+$/) && text.length < 50) {
                return text;
            }
        }
    }

    // 7. Check for country in assignment or form metadata
    const metaTags = document.querySelectorAll('meta[name*="country"], meta[property*="country"]');
    for (const meta of metaTags) {
        const content = meta.getAttribute('content');
        if (content && content.trim()) {
            return content.trim();
        }
    }

    // 8. Check data attributes on main containers
    const mainContainers = document.querySelectorAll('#main, #content, .container, .main-content');
    for (const container of mainContainers) {
        const country = container.getAttribute('data-country') || container.getAttribute('data-country-name');
        if (country && country.trim()) {
            return country.trim();
        }
    }

    debugLog(MODULE_NAME, '⚠️ Could not determine country name for report title');
    return null;
}

// Helper functions for enhanced field rendering
function getFieldTypeIcon(fieldType) {
    const icons = {
        'text': '📝',
        'number': '🔢',
        'select': '📋',
        'boolean': '☑️',
        'date': '📅',
        'email': '📧',
        'url': '🔗',
        'tel': '📞',
        'textarea': '📄'
    };
    return icons[fieldType] || '📝';
}

function getValueColor(value, fieldType) {
    if (fieldType === 'number' && !isNaN(parseFloat(value))) {
        const num = parseFloat(value);
        if (num > 0) return IFRC_BRANDING.colors.status.success;
        if (num < 0) return IFRC_BRANDING.colors.status.warning;
    }

    if (fieldType === 'boolean') {
        return value.toLowerCase().includes('yes') || value.toLowerCase().includes('true')
            ? IFRC_BRANDING.colors.status.success
            : IFRC_BRANDING.colors.status.danger;
    }

    return IFRC_BRANDING.colors.text.primary;
}

function formatFieldValue(value, fieldType) {
    if (fieldType === 'number' && !isNaN(parseFloat(value))) {
        const num = parseFloat(value);
        return new Intl.NumberFormat('en-US').format(num);
    }

    if (fieldType === 'date') {
        try {
            const date = new Date(value);
            return date.toLocaleDateString('en-GB');
        } catch {
            return value;
        }
    }

    return value;
}

/**
 * Initialize PDF export functionality
 */
export function initPDFExport(formId, buttonId, title) {
    debugLog(MODULE_NAME, '🔧 Initializing PDF export...');

    const button = document.getElementById(buttonId);
    if (!button) {
        debugLog(MODULE_NAME, '❌ PDF export button not found:', buttonId);
        return;
    }

    function initializeExport() {
        debugLog(MODULE_NAME, '📎 Setting up server-side PDF export click handler');

        button.addEventListener('click', (e) => {
            e.preventDefault();
            // Store original child nodes as a DocumentFragment
            const originalNodes = document.createDocumentFragment();
            Array.from(button.childNodes).forEach(node => {
                originalNodes.appendChild(node.cloneNode(true));
            });
            button.disabled = true;
            button.replaceChildren();
            const spinner = document.createElement('i');
            spinner.className = 'fas fa-spinner fa-spin mr-2';
            button.appendChild(spinner);
            button.appendChild(document.createTextNode('Exporting...'));

            try {
                // Build URL from data on the page when available
                const container = document.querySelector('[data-aes-id]');
                const aesId = container ? container.getAttribute('data-aes-id') : null;
                if (!aesId) {
                    throw new Error('Missing assignment id');
                }

                // Collect current relevance-hidden sections/fields from the DOM so the server-side PDF export
                // can match what the user is seeing right now (including unsaved UI state).
                const root = document.getElementById(formId) || document;
                const hiddenSectionIds = Array
                    .from(root.querySelectorAll('.relevance-hidden[id^="section-container-"]'))
                    .map(el => (el.id || '').replace('section-container-', ''))
                    .filter(id => id && /^\d+$/.test(id));

                const hiddenFieldIds = Array
                    .from(root.querySelectorAll('.relevance-hidden[data-item-id]'))
                    // Section containers may also have data-item-id; exclude them to avoid double-counting
                    .filter(el => !(el.id && el.id.startsWith('section-container-')))
                    .map(el => el.getAttribute('data-item-id'))
                    .filter(id => id && /^\d+$/.test(id));

                const params = new URLSearchParams();
                if (hiddenSectionIds.length) {
                    params.set('hidden_sections', hiddenSectionIds.join(','));
                }
                if (hiddenFieldIds.length) {
                    params.set('hidden_fields', hiddenFieldIds.join(','));
                }

                const qs = params.toString();
                const url = `/forms/assignment_status/${aesId}/export_pdf${qs ? `?${qs}` : ''}`;
                // New tab on desktop; same WebView on mobile app / Android WebView (session cookie)
                openAssignmentExportUrl(url);
            } catch (err) {
                if (window.showAlert) {
                    window.showAlert('Failed to start PDF export.', 'error');
                } else {
                    console.warn('Failed to start PDF export.');
                }
            } finally {
                button.disabled = false;
                button.replaceChildren();
                // Clone and append original nodes
                Array.from(originalNodes.childNodes).forEach(node => {
                    button.appendChild(node.cloneNode(true));
                });
            }
        });

        debugLog(MODULE_NAME, '✅ PDF export (server-side) initialized successfully');
    }

    // Initialize immediately
    initializeExport();
}

/**
 * Initialize Validation Summary PDF export functionality.
 *
 * Mirrors the server-side PDF export click handler, but targets the validation summary endpoint.
 */
export function initValidationSummaryExport(formId, buttonId) {
    debugLog(MODULE_NAME, '🔧 Initializing validation summary export...');

    const button = document.getElementById(buttonId);
    if (!button) {
        debugLog(MODULE_NAME, '❌ Validation summary button not found:', buttonId);
        return;
    }

    button.addEventListener('click', (e) => {
        e.preventDefault();

        // Store original child nodes as a DocumentFragment
        const originalNodes = document.createDocumentFragment();
        Array.from(button.childNodes).forEach(node => {
            originalNodes.appendChild(node.cloneNode(true));
        });

        button.disabled = true;
        button.replaceChildren();
        const spinner = document.createElement('i');
        spinner.className = 'fas fa-spinner fa-spin mr-2';
        button.appendChild(spinner);
        button.appendChild(document.createTextNode('Generating...'));

        try {
            const container = document.querySelector('[data-aes-id]');
            const aesId = container ? container.getAttribute('data-aes-id') : null;
            if (!aesId) {
                throw new Error('Missing assignment id');
            }

            // Match the user's current relevance-hidden state (like export_pdf)
            const root = document.getElementById(formId) || document;
            const hiddenSectionIds = Array
                .from(root.querySelectorAll('.relevance-hidden[id^="section-container-"]'))
                .map(el => (el.id || '').replace('section-container-', ''))
                .filter(id => id && /^\d+$/.test(id));

            const hiddenFieldIds = Array
                .from(root.querySelectorAll('.relevance-hidden[data-item-id]'))
                .filter(el => !(el.id && el.id.startsWith('section-container-')))
                .map(el => el.getAttribute('data-item-id'))
                .filter(id => id && /^\d+$/.test(id));

            const params = new URLSearchParams();
            if (hiddenSectionIds.length) {
                params.set('hidden_sections', hiddenSectionIds.join(','));
            }
            if (hiddenFieldIds.length) {
                params.set('hidden_fields', hiddenFieldIds.join(','));
            }
            // Bulk run missing validations with progress UI
            params.set('run', '1');
            params.set('run_mode', 'missing');
            // Default tuned for PostgreSQL deployments; server applies a safety cap.
            params.set('concurrency', '8');

            const qs = params.toString();
            const url = `/forms/assignment_status/${aesId}/validation_summary${qs ? `?${qs}` : ''}`;

            openAssignmentExportUrl(url, 'noopener,noreferrer');
        } catch (err) {
            if (window.showAlert) {
                window.showAlert('Failed to generate validation summary.', 'error');
            } else {
                // eslint-disable-next-line no-console
                console.warn('Failed to generate validation summary.');
            }
        } finally {
            button.disabled = false;
            button.replaceChildren();
            Array.from(originalNodes.childNodes).forEach(node => {
                button.appendChild(node.cloneNode(true));
            });
        }
    });

    debugLog(MODULE_NAME, '✅ Validation summary export initialized successfully');
}
