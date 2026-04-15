// Guided Tour for Entry Form (Intro.js)
// Helps focal points understand the data entry form interface

(function() {
	// Toggle this flag to force the tour to show every time during development
	const TOUR_DEV_MODE = false;
	let tourAnimationTimeouts = [];
	let introAssetsLoading = false;
	let overlayObserver = null;
	let sidebarExpandedByTour = false;

	function clearAnimationTimeouts() {
		while (tourAnimationTimeouts.length) {
			const t = tourAnimationTimeouts.pop();
			try { clearTimeout(t); } catch (_) {}
		}
	}

	function ensureIntroJsLoaded(callback) {
		if (typeof introJs !== 'undefined') {
			callback();
			return;
		}
		if (introAssetsLoading) {
			const check = setInterval(() => {
				if (typeof introJs !== 'undefined') {
					clearInterval(check);
					callback();
				}
			}, 100);
			tourAnimationTimeouts.push(check);
			return;
		}
		introAssetsLoading = true;
		if (!document.querySelector('link[href*="introjs"]')) {
			const link = document.createElement('link');
			link.rel = 'stylesheet';
			link.href = (window.getStaticUrl && window.getStaticUrl('libs/introjs.min.css')) || '/static/libs/introjs.min.css';
			document.head.appendChild(link);
		}
		const script = document.createElement('script');
		script.src = (window.getStaticUrl && window.getStaticUrl('libs/intro.min.js')) || '/static/libs/intro.min.js';
		script.onload = function() {
			introAssetsLoading = false;
			callback();
		};
		script.onerror = function() {
			introAssetsLoading = false;
			console.error('Failed to load Intro.js');
		};
		document.head.appendChild(script);
	}

	function buildEntryFormTourSteps() {
		const steps = [];
		const isRTL = document.documentElement.getAttribute('dir') === 'rtl';

		// Get entry form translations
		const tourSteps = window.TOUR_I18N && window.TOUR_I18N.entry_form_steps || {};
		const t = (key) => tourSteps[key] || '';

		const addStep = (element, intro, position) => {
			if (element && element.offsetParent !== null) {
				steps.push({ element, intro, position });
			}
		};

		// 1. Assignment Details Section
		const assignmentHeader = document.querySelector('.bg-white.p-6.rounded-lg.shadow.border.border-gray-200.mb-6.relative h2');
		if (assignmentHeader) {
			addStep(assignmentHeader, t('assignmentHeader') || 'This section shows your assignment details including the template name, period, country, due date, and submission status.', 'bottom');
		}

		// 2. Excel Import/Export button
		const excelBtn = document.getElementById('excel-options-btn');
		if (excelBtn) {
			addStep(excelBtn, t('excelButton') || 'Use this button to import data from Excel or export a template. This is useful for bulk data entry or working offline.', 'bottom');
		}

		// 3. Export PDF button
		const pdfBtn = document.getElementById('export-pdf-btn');
		if (pdfBtn) {
			addStep(pdfBtn, t('pdfButton') || 'Export the completed form as a PDF document for record-keeping or sharing.', 'bottom');
		}

		// 4. Section Navigation Sidebar
		const sectionNav = document.getElementById('section-navigation-sidebar');
		if (sectionNav) {
			addStep(sectionNav, t('sectionNav') || 'Navigate between form sections here. The icons show section completion status: ✓ (completed), ✎ (in progress), ○ (not started). On mobile, use the floating menu button to access this sidebar.', isRTL ? 'left' : 'right');
		}

		// 5. First Section in the main form area
		const firstSection = document.querySelector('[id^="section-container-"]');
		if (firstSection) {
			addStep(firstSection, t('formSection') || 'Each section groups related fields together. Click the collapse button (△) to hide/show section content. Fill in all required fields marked with a red asterisk (*).', 'right');
		}

		// 6. A field example (if exists)
		const firstField = document.querySelector('.form-item-block');
		if (firstField) {
			addStep(firstField, t('formField') || 'Form fields may include text inputs, numbers, dates, dropdowns, or file uploads. Some fields show tooltips (ℹ) with additional information. Yellow-highlighted fields contain prefilled values you can review and modify.', 'top');
		}

		// 7. Save button in sidebar
		const saveBtn = document.querySelector('button[name="action"][value="save"]');
		if (saveBtn) {
			addStep(saveBtn, t('saveButton') || 'Save your progress at any time. Your data is preserved and you can return to continue editing later.', 'left');
		}

		// 8. Submit button in sidebar
		const submitBtn = document.querySelector('button[name="action"][value="submit"]');
		if (submitBtn) {
			addStep(submitBtn, t('submitButton') || 'When you\'re finished, click Submit to finalize your form. Warning: After submission, you cannot edit the form unless an admin reopens it.', 'left');
		}

		// 9. Prefilled Values Notice (if visible)
		const prefilledNotice = document.querySelector('.bg-yellow-50.border-l-4.border-yellow-400');
		if (prefilledNotice && prefilledNotice.textContent.includes('Prefilled')) {
			addStep(prefilledNotice, t('prefilledNotice') || 'This notice indicates that some fields have prefilled values (shown in yellow). These are suggested values that you can review and change as needed.', 'bottom');
		}

		// 10. Presence Bar (if visible)
		const presenceBar = document.getElementById('presence-bar');
		if (presenceBar && presenceBar.style.display !== 'none') {
			addStep(presenceBar, t('presenceBar') || 'See who else is currently working on this form. This helps avoid conflicts when multiple people are editing.', 'top');
		}

		// 11. Mobile navigation toggle (only on mobile)
		if (window.innerWidth <= 768) {
			const mobileNavBtn = document.getElementById('mobile-nav-toggle-button');
			if (mobileNavBtn) {
				addStep(mobileNavBtn, t('mobileNav') || 'On mobile, use this button to open the sections menu and access save/submit buttons.', 'top');
			}
		}

		// 12. Dynamic Indicators Section (if exists)
		const dynamicSection = document.querySelector('[data-section-type="dynamic_indicators"]');
		if (dynamicSection) {
			const addIndicatorBtn = dynamicSection.querySelector('.add-indicator-btn, button[data-action="add-indicator"]');
			if (addIndicatorBtn) {
				addStep(addIndicatorBtn, t('dynamicIndicators') || 'This is a dynamic section where you can add custom indicators from the indicator bank. Use this to report on additional metrics relevant to your country.', 'top');
			}
		}

		return steps;
	}

	function applyOverlayStrength() {
		try {
			const overlays = document.querySelectorAll('div[class*="introjs-overlay"], .introjs-overlay');
			overlays.forEach((overlay) => {
				overlay.style.background = 'rgba(0, 0, 0, 0.4)';
				overlay.style.backdropFilter = 'none';
				overlay.style.webkitBackdropFilter = 'none';
			});

			const helperLayers = document.querySelectorAll('.introjs-helperLayer');
			helperLayers.forEach((helper) => {
				helper.style.background = 'transparent';
				helper.style.border = '2px solid rgba(197, 48, 48, 0.8)';
				helper.style.borderRadius = '8px';
				helper.style.boxShadow = '0 0 0 9999px rgba(0, 0, 0, 0.4)';
			});
		} catch (_) {}
	}

	function startOverlayObserver() {
		try {
			stopOverlayObserver();
			overlayObserver = new MutationObserver(() => {
				applyOverlayStrength();
			});
			overlayObserver.observe(document.documentElement || document.body, { childList: true, subtree: true });
			applyOverlayStrength();
		} catch (_) {}
	}

	function stopOverlayObserver() {
		try {
			if (overlayObserver) {
				overlayObserver.disconnect();
				overlayObserver = null;
			}
		} catch (_) {}
	}

	function startEntryFormTour(force, startAtStep) {
		const tourKey = 'humdb_entry_form_tour_status';
		const isRTL = document.documentElement.getAttribute('dir') === 'rtl';
		const status = localStorage.getItem(tourKey);
		const i18n = window.TOUR_I18N || {};
		const isChatbotTriggered = typeof startAtStep === 'number' && startAtStep >= 0;

		// Only start tour if explicitly forced (manual trigger from profile menu)
		// Don't auto-start on page load
		if (!force && !TOUR_DEV_MODE) return;

		let steps = buildEntryFormTourSteps();

		// Validate startAtStep parameter
		if (typeof startAtStep === 'number') {
			if (startAtStep < 0 || startAtStep >= steps.length) {
				console.warn('Invalid step index:', startAtStep, 'Valid range: 0 -', steps.length - 1);
				startAtStep = 0; // Default to first step
			}

			// If chatbot triggered with specific step, show only that step
			if (isChatbotTriggered && steps[startAtStep]) {
				steps = [steps[startAtStep]]; // Show only the requested step
				startAtStep = 0; // Reset to first position since we have only one step now
			}
		}

		if (!steps.length) {
			// Fallback if no steps found
			const fallbackText = (window.TOUR_I18N && window.TOUR_I18N.entry_form_steps && (window.TOUR_I18N.entry_form_steps.welcome || 'Welcome to the data entry form! This tour will guide you through the key features.')) || 'Welcome to the data entry form! This tour will guide you through the key features.';
			steps = [{ intro: fallbackText }];
		}

		const start = function() {
			if (typeof introJs === 'undefined') {
				console.warn('Intro.js not available after load attempt.');
				return;
			}

			let instance;
			if (introJs.tour) {
				instance = introJs.tour();
			} else if (typeof introJs === 'function') {
				instance = introJs();
			} else {
				console.error('introJs API not found');
				return;
			}

			if (!instance || typeof instance.setOptions !== 'function') {
				console.error('Invalid introJs instance');
				return;
			}

			try {
				// If triggered by chatbot to specific step, show single-step mode
				const isSingleStepMode = isChatbotTriggered && typeof startAtStep === 'number';

				instance.setOptions({
					steps,
					showProgress: !isSingleStepMode, // Hide progress in single-step mode
					showStepNumbers: !isSingleStepMode, // Hide step numbers in single-step mode
					showBullets: false,
					exitOnEsc: true,
					exitOnOverlayClick: false,
					disableInteraction: false,
					nextLabel: i18n.next || 'Next',
					prevLabel: i18n.back || 'Back',
					skipLabel: '', // Hide skip button
					doneLabel: i18n.gotIt || i18n.done || 'Got it!',
					rtl: isRTL,
					overlayOpacity: 0.4,
					tooltipClass: isSingleStepMode ? 'humdb-intro single-step-mode' : 'humdb-intro',
					highlightClass: 'humdb-intro-highlight',
					scrollTo: 'tooltip',
					scrollToElement: true,
					showButtons: true,
					showSkip: false
				});

				// Customize buttons for first step - replace Back with Cancel
				function updateButtonsForCurrentStep() {
					const currentStepIndex = typeof instance.currentStep === 'function' ? instance.currentStep() : 0;
					const prevButton = document.querySelector('.introjs-prevbutton');
					const nextButton = document.querySelector('.introjs-nextbutton');
					const doneButton = document.querySelector('.introjs-donebutton');

					// Single-step mode: Hide Back/Next buttons, only show "Got it!" button
					if (isSingleStepMode) {
						if (prevButton) {
							prevButton.style.display = 'none';
						}
						if (nextButton) {
							nextButton.style.display = 'none';
						}
						// Change Done button to "Got it!" and make it more prominent
						if (doneButton) {
							doneButton.textContent = i18n.gotIt || 'Got it!';
							doneButton.style.display = 'inline-block';
						}
					} else {
						// Normal tour mode
						if (prevButton) {
							prevButton.style.display = 'inline-block';
							if (currentStepIndex === 0) {
								// First step - change to Cancel button
								prevButton.textContent = i18n.cancel || 'Cancel';
								prevButton.setAttribute('data-action', 'cancel');
								prevButton.onclick = function() {
									instance.exit();
									return false;
								};
							} else {
								// Other steps - restore Back button
								prevButton.textContent = i18n.back || 'Back';
								prevButton.removeAttribute('data-action');
								prevButton.onclick = null; // Let Intro.js handle it
							}
						}
						if (nextButton) {
							nextButton.style.display = 'inline-block';
						}
					}
				}

				// Prevent overlay click from closing tour
				setTimeout(() => {
					try {
						const overlay = document.querySelector('.introjs-overlay');
						if (overlay) {
							overlay.addEventListener('click', function(e) {
								e.preventDefault();
								e.stopPropagation();
								return false;
							}, true);
						}
						startOverlayObserver();
					} catch (_) {}
				}, 0);

				if (typeof instance.onbeforechange === 'function') {
					instance.onbeforechange(function(targetElement) {
						clearAnimationTimeouts();
						applyOverlayStrength();
						// Update buttons when changing steps
						setTimeout(updateButtonsForCurrentStep, 50);
					});
				}

				if (typeof instance.onafterchange === 'function') {
					instance.onafterchange(function(targetElement) {
						const tooltip = document.querySelector('.humdb-intro');
						if (tooltip) {
							tooltip.classList.add('tour-adjusting');

							// Add chatbot indicator if tour was triggered by chatbot
							if (isChatbotTriggered && !tooltip.querySelector('.chatbot-tour-badge')) {
								const badge = document.createElement('div');
								badge.className = 'chatbot-tour-badge';
								badge.textContent = 'Guided by AI Assistant';

								// Insert at the very beginning of the tooltip text
								const tooltipText = tooltip.querySelector('.introjs-tooltiptext');
								if (tooltipText) {
									tooltipText.insertBefore(badge, tooltipText.firstChild);
								}
							}
						}
						applyOverlayStrength();

						setTimeout(() => {
							applyOverlayStrength();
							// Update buttons after step change is complete
							updateButtonsForCurrentStep();
						}, 50);

						setTimeout(() => {
							if (tooltip) {
								tooltip.classList.remove('tour-adjusting');
							}
						}, 600);
					});
				}

				if (typeof instance.oncomplete === 'function') {
					instance.oncomplete(() => {
						stopOverlayObserver();
						if (!TOUR_DEV_MODE) {
							localStorage.setItem(tourKey, 'completed');
						}
						clearAnimationTimeouts();
					});
				}

				if (typeof instance.onexit === 'function') {
					instance.onexit(() => {
						stopOverlayObserver();
						if (!TOUR_DEV_MODE) {
							if (localStorage.getItem(tourKey) !== 'completed') {
								localStorage.setItem(tourKey, 'skipped');
							}
						}
						clearAnimationTimeouts();
					});
				}

				if (typeof instance.start === 'function') {
					instance.start();

					// If starting at a specific step in normal tour mode (not single-step), go to that step
					if (typeof startAtStep === 'number' && startAtStep > 0 && !isSingleStepMode) {
						setTimeout(() => {
							if (typeof instance.goToStep === 'function') {
								instance.goToStep(startAtStep + 1); // Intro.js uses 1-based indexing
							}
						}, 200);
					}
					// In single-step mode, we've already filtered to show only one step, so no need to navigate

					setTimeout(() => {
						applyOverlayStrength();
						startOverlayObserver();
						// Update buttons on first step
						updateButtonsForCurrentStep();

						// Add chatbot badge if triggered by chatbot
						if (isChatbotTriggered) {
							const tooltip = document.querySelector('.humdb-intro');
							if (tooltip && !tooltip.querySelector('.chatbot-tour-badge')) {
								const badge = document.createElement('div');
								badge.className = 'chatbot-tour-badge';
								badge.textContent = 'Guided by AI Assistant';

								// Insert at the very beginning of the tooltip text
								const tooltipText = tooltip.querySelector('.introjs-tooltiptext');
								if (tooltipText) {
									tooltipText.insertBefore(badge, tooltipText.firstChild);
								}
							}
						}
					}, 100);
				} else {
					console.error('introJs instance missing start method');
				}
			} catch (error) {
				console.error('Error starting entry form tour:', error);
			}
		};

		if (typeof introJs === 'undefined') {
			ensureIntroJsLoaded(start);
		} else {
			start();
		}
	}

	function initEntryFormTourBindings() {
		// Check if we're in the mobile app - disable tour if so
		const isMobileApp = window.isMobileApp === true ||
		                   window.IFRCMobileApp === true ||
		                   document.documentElement.getAttribute('data-mobile-app') === 'true' ||
		                   (navigator.userAgent && navigator.userAgent.includes('wv'));

		if (isMobileApp) {
			// Disable tour in mobile app - hide the "Start Tour" link if it exists
			const startTourLink = document.getElementById('startTourLink');
			if (startTourLink) {
				startTourLink.style.display = 'none';
			}
			return; // Don't initialize tour bindings in mobile app
		}

		// Bind to the profile menu "Start Tour" link
		const startTourLink = document.getElementById('startTourLink');
		if (startTourLink) {
			// Remove any existing event listeners by cloning the element
			const newStartTourLink = startTourLink.cloneNode(true);
			startTourLink.parentNode.replaceChild(newStartTourLink, startTourLink);

			// Add our entry form tour handler
			newStartTourLink.addEventListener('click', function(e) {
				e.preventDefault();
				e.stopPropagation();
				// Close profile popup
				const profilePopup = document.getElementById('profile-popup');
				if (profilePopup) {
					profilePopup.classList.add('hidden');
				}
				// Start entry form tour
				startEntryFormTour(true);
			});
		}
	}

	// Wait for DOM and ensure this only runs on entry form pages
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', function() {
			// Check if we're on an entry form page
			const isEntryForm = document.querySelector('#focalDataEntryForm') ||
			                    document.querySelector('[data-is-public-submission]');
			if (isEntryForm) {
				// Delay initialization to ensure we override any other tour bindings
				setTimeout(initEntryFormTourBindings, 100);
			}
		});
	} else {
		// DOM already loaded
		const isEntryForm = document.querySelector('#focalDataEntryForm') ||
		                    document.querySelector('[data-is-public-submission]');
		if (isEntryForm) {
			// Delay initialization to ensure we override any other tour bindings
			setTimeout(initEntryFormTourBindings, 100);
		}
	}

	// Expose for manual triggering and chatbot integration
	window.startEntryFormTour = function(startAtStep) {
		// Check if we're in the mobile app - disable tour if so
		const isMobileApp = window.isMobileApp === true ||
		                   window.IFRCMobileApp === true ||
		                   document.documentElement.getAttribute('data-mobile-app') === 'true' ||
		                   (navigator.userAgent && navigator.userAgent.includes('wv'));

		if (isMobileApp) {
			console.log('Tour disabled in mobile app');
			return; // Don't start tour in mobile app
		}

		if (typeof startAtStep === 'number') {
			// Start at specific step (0-indexed)
			startEntryFormTour(true, startAtStep);
		} else {
			// Start from beginning
			startEntryFormTour(true);
		}
	};

	// Expose tour steps metadata for chatbot
	window.getEntryFormTourSteps = function() {
		const tourSteps = window.TOUR_I18N && window.TOUR_I18N.entry_form_steps || {};
		return [
			{ id: 'assignment_header', name: 'Assignment Details', description: tourSteps.assignmentHeader || 'Assignment header with details' },
			{ id: 'excel_button', name: 'Excel Import/Export', description: tourSteps.excelButton || 'Excel import/export functionality' },
			{ id: 'pdf_button', name: 'PDF Export', description: tourSteps.pdfButton || 'Export form as PDF' },
			{ id: 'section_nav', name: 'Section Navigation Pane', description: tourSteps.sectionNav || 'Navigate between form sections' },
			{ id: 'form_section', name: 'Form Sections', description: tourSteps.formSection || 'How sections work' },
			{ id: 'form_field', name: 'Form Fields', description: tourSteps.formField || 'Different field types' },
			{ id: 'save_button', name: 'Save Button', description: tourSteps.saveButton || 'Save your progress' },
			{ id: 'submit_button', name: 'Submit Button', description: tourSteps.submitButton || 'Submit your form' },
			{ id: 'prefilled_notice', name: 'Prefilled Values', description: tourSteps.prefilledNotice || 'Understanding prefilled values' },
			{ id: 'presence_bar', name: 'Presence Bar', description: tourSteps.presenceBar || 'See who is editing' },
			{ id: 'mobile_nav', name: 'Mobile Navigation', description: tourSteps.mobileNav || 'Mobile menu button' },
			{ id: 'dynamic_indicators', name: 'Dynamic Indicators', description: tourSteps.dynamicIndicators || 'Add custom indicators' }
		];
	};
})();
