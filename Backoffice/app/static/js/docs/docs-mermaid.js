/**
 * Mermaid.js integration for documentation pages
 * Handles initialization and rendering of Mermaid diagrams
 */

(function() {
    'use strict';

    // Initialize Mermaid with GitHub-like theme
    function initializeMermaid() {
        if (typeof mermaid === 'undefined') {
            console.warn('Mermaid.js not loaded');
            return false;
        }

        mermaid.initialize({
            startOnLoad: false, // We'll render manually
            theme: 'default',
            themeVariables: {
                primaryColor: '#3b82f6',
                primaryTextColor: '#fff',
                primaryBorderColor: '#2563eb',
                lineColor: '#64748b',
                secondaryColor: '#f1f5f9',
                tertiaryColor: '#e2e8f0',
                background: '#ffffff',
                mainBkg: '#ffffff',
                textColor: '#1e293b',
                border1: '#e2e8f0',
                border2: '#cbd5e1',
                noteBkgColor: '#fef3c7',
                noteTextColor: '#78350f',
                noteBorderColor: '#fbbf24',
                actorBorder: '#64748b',
                actorBkg: '#f8fafc',
                actorTextColor: '#1e293b',
                actorLineColor: '#64748b',
                labelBoxBkgColor: '#ffffff',
                labelBoxBorderColor: '#64748b',
                labelTextColor: '#1e293b',
                loopTextColor: '#1e293b',
                activationBorderColor: '#3b82f6',
                activationBkgColor: '#dbeafe',
                sequenceNumberColor: '#ffffff',
                sectionBkgColor: '#f1f5f9',
                altSectionBkgColor: '#ffffff',
                sectionBorderColor: '#cbd5e1',
                excludeBkgColor: '#fee2e2',
                excludeBorderColor: '#ef4444',
                critBorderColor: '#dc2626',
                critBkgColor: '#fee2e2',
                doneBkgColor: '#dbeafe',
                doneBorderColor: '#3b82f6',
                taskBorderColor: '#64748b',
                taskBkgColor: '#ffffff',
                taskTextLightColor: '#ffffff',
                taskTextColor: '#1e293b',
                taskTextDarkColor: '#0f172a',
                taskTextOutsideColor: '#64748b',
                taskTextClickableColor: '#3b82f6',
                activeTaskBorderColor: '#3b82f6',
                activeTaskBkgColor: '#dbeafe',
                gridColor: '#e2e8f0',
                doneTaskBkgColor: '#dbeafe',
                doneTaskBorderColor: '#3b82f6',
                crossLineColor: '#64748b',
                titleColor: '#1e293b',
                edgeLabelBackground: '#ffffff',
                clusterBkg: '#f8fafc',
                clusterBorder: '#cbd5e1',
                defaultLinkColor: '#3b82f6',
                errorBkgColor: '#fee2e2',
                errorTextColor: '#991b1b'
            },
            flowchart: {
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            },
            gantt: {
                useMaxWidth: true
            },
            sequence: {
                useMaxWidth: true,
                diagramMarginX: 50,
                diagramMarginY: 10,
                actorMargin: 50,
                width: 150,
                height: 65,
                boxMargin: 10,
                boxTextMargin: 5,
                noteMargin: 10,
                messageMargin: 35,
                mirrorActors: true,
                bottomMarginAdj: 1,
                useMaxWidth: true,
                rightAngles: false,
                showSequenceNumbers: false
            },
            class: {
                useMaxWidth: true
            },
            state: {
                useMaxWidth: true
            },
            journey: {
                useMaxWidth: true
            },
            pie: {
                useMaxWidth: true
            },
            gitgraph: {
                useMaxWidth: true
            },
            er: {
                useMaxWidth: true
            },
            requirement: {
                useMaxWidth: true
            }
        });

        return true;
    }

    /**
     * Render Mermaid diagrams in the given container
     * @param {HTMLElement} container - Container element to search for mermaid code blocks
     */
    function renderMermaidDiagrams(container) {
        if (typeof mermaid === 'undefined') {
            console.warn('Mermaid.js not loaded');
            return;
        }

        if (!container) {
            container = document;
        }

        // Find all code blocks - check for mermaid language in various formats
        const allCodeBlocks = container.querySelectorAll('pre code, code');
        const mermaidBlocks = [];

        allCodeBlocks.forEach(function(codeBlock) {
            // Skip if already processed
            if (codeBlock.classList.contains('mermaid-processed') ||
                (codeBlock.parentElement && codeBlock.parentElement.classList.contains('mermaid-processed'))) {
                return;
            }

            // Check for mermaid language class
            const classList = codeBlock.classList;
            const isMermaid = classList.contains('language-mermaid') ||
                             classList.contains('lang-mermaid') ||
                             classList.contains('mermaid');

            // Also check parent pre element
            const preElement = codeBlock.parentElement;
            const preIsMermaid = preElement && preElement.tagName === 'PRE' &&
                               (preElement.classList.contains('language-mermaid') ||
                                preElement.classList.contains('lang-mermaid') ||
                                preElement.classList.contains('mermaid'));

            if (isMermaid || preIsMermaid) {
                mermaidBlocks.push({ codeBlock: codeBlock, preElement: preElement });
            }
        });

        // Process each mermaid block
        mermaidBlocks.forEach(function(item, index) {
            const codeBlock = item.codeBlock;
            const preElement = item.preElement;

            const mermaidCode = codeBlock.textContent || codeBlock.innerText;
            if (!mermaidCode.trim()) {
                return;
            }

            // Create a new div for Mermaid to render into
            const mermaidDiv = document.createElement('div');
            mermaidDiv.className = 'mermaid';
            mermaidDiv.textContent = mermaidCode.trim();
            mermaidDiv.setAttribute('data-mermaid-index', index);

            // Replace the pre element (which contains the code block) with the mermaid div
            if (preElement && preElement.tagName === 'PRE') {
                preElement.replaceWith(mermaidDiv);
            } else {
                codeBlock.replaceWith(mermaidDiv);
            }
        });

        // Render all mermaid diagrams that were just created
        const mermaidDivs = container.querySelectorAll('.mermaid:not([data-mermaid-rendered])');
        if (mermaidDivs.length > 0) {
            try {
                // Mark as rendered to avoid double-processing
                mermaidDivs.forEach(function(div) {
                    div.setAttribute('data-mermaid-rendered', 'true');
                });

                // Use mermaid.run() API (available in Mermaid v10+)
                if (typeof mermaid.run === 'function') {
                    mermaid.run({
                        nodes: Array.from(mermaidDivs)
                    }).catch(function(err) {
                        console.error('Error rendering Mermaid diagrams:', err);
                    });
                } else {
                    // Fallback for older Mermaid versions
                    mermaidDivs.forEach(function(div) {
                        try {
                            const id = 'mermaid-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
                            div.id = id;
                            mermaid.init(undefined, div);
                        } catch (e) {
                            console.error('Error rendering individual Mermaid diagram:', e);
                        }
                    });
                }
            } catch (err) {
                console.error('Error rendering Mermaid diagrams:', err);
            }
        }
    }

    // Initialize Mermaid when library is loaded
    if (typeof mermaid !== 'undefined') {
        initializeMermaid();
    } else {
        // Wait for Mermaid to load
        window.addEventListener('load', function() {
            if (typeof mermaid !== 'undefined') {
                initializeMermaid();
            }
        });
    }

    // Make function globally available for AJAX navigation
    window.renderMermaidDiagrams = renderMermaidDiagrams;

    // Render diagrams on initial page load
    function renderOnLoad() {
        const proseEl = document.querySelector('.docs-prose');
        if (proseEl) {
            renderMermaidDiagrams(proseEl);
        }
    }

    document.addEventListener('DOMContentLoaded', renderOnLoad);

    // Also render immediately if DOM is already loaded
    if (document.readyState !== 'loading') {
        renderOnLoad();
    }
})();
