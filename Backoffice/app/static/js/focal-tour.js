// Guided Tour for Focal Points (Intro.js)
// Depends on introJs and window.TOUR_I18N injected from layout
// Focuses on focal point dashboard sections and functionality

(function() {
	// Toggle this flag to force the tour to show every time during development
	// Set to false for production
	const TOUR_DEV_MODE = false;
	let tourAnimationTimeouts = [];
	let introAssetsLoading = false;
	let languageMenuOpenedByTour = false;
	let overlayObserver = null;
	let languageStepIndex = null;
	let sidebarStepIndex = null;
	let chatbotStepIndex = null;
	let assignmentsSectionStepIndex = null;
	let pastSubmissionsStepIndex = null;
	let metricsStepIndex = null;
	let recentActivitiesStepIndex = null;
	let createReportStepIndex = null;
	let sidebarExpandedByTour = false;
	let sidebarWasCollapsedInitially = false;

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
			// Poll until loaded
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
		// Inject CSS if missing
		if (!document.querySelector('link[href*="introjs"]')) {
			const link = document.createElement('link');
			link.rel = 'stylesheet';
			link.href = (window.getStaticUrl && window.getStaticUrl('libs/introjs.min.css')) || '/static/libs/introjs.min.css';
			document.head.appendChild(link);
		}
		// Inject script
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

	function buildTourSteps() {
		const steps = [];
		const isRTL = document.documentElement.getAttribute('dir') === 'rtl';

		// Get focal point translations
		const tourSteps = window.TOUR_I18N && window.TOUR_I18N.focal_steps || {};
		const t = (key) => tourSteps[key] || '';

		const addStep = (element, intro, position) => {
			steps.push({ element, intro, position });
		};

		// Brand and title - focal point perspective
		const brand = document.querySelector('#navContainer a[href]');
		if (brand) addStep(brand, t('brand') || '', isRTL ? 'left' : 'right');

		// Dashboard button in top navigation (focal point specific)
		const dashboardBtn = document.querySelector('a[href*="dashboard"][title="Dashboard"], a[title="Dashboard"]');
		if (dashboardBtn && dashboardBtn.offsetParent !== null) {
			addStep(dashboardBtn, t('dashboardButton') || 'Access your main dashboard to view assignments, metrics, and recent activities for your country.', 'bottom');
		}

		// Document Management button in top navigation (focal point specific)
		const docManagementBtn = document.querySelector('a[href*="manage_documents"][title*="Document"], a[title*="Document Management"]');
		if (docManagementBtn && docManagementBtn.offsetParent !== null) {
			addStep(docManagementBtn, t('documentManagement') || 'Manage and access documents, publications, and other resources for your country.', 'bottom');
		}

		// Sidebar: MERGED step (toggle + sidebar usage)
		const sidebarToggleEl = document.getElementById('sidebarToggle');
		if (sidebarToggleEl) {
			const mergedIntro = [t('sidebarToggle'), t('sidebar')].filter(Boolean).join(' ');
			addStep(sidebarToggleEl, mergedIntro, isRTL ? 'left' : 'right');
			sidebarStepIndex = steps.length - 1;
		}

		// Country Selection (if visible)
		const countrySelect = document.getElementById('country_select');
		if (countrySelect && countrySelect.offsetParent !== null) {
			addStep(countrySelect, t('countrySelect') || 'Select your country to view your assignments and data.', isRTL ? 'right' : 'left');
		}

		// Create a Report button (self-reporting)
		const createReportBtn = document.getElementById('self-report-templates-button');
		if (createReportBtn && createReportBtn.offsetParent !== null) {
			addStep(createReportBtn, t('createReport') || 'Click here to create a new report using available templates for your country.', isRTL ? 'left' : 'right');
			createReportStepIndex = steps.length - 1;
		}

		// Current Assignments Section
		const assignmentHeadings = Array.from(document.querySelectorAll('h2')).filter(h =>
			h.textContent.includes('Assignments') || h.textContent.includes('assignments'));
		if (assignmentHeadings.length > 0) {
			addStep(assignmentHeadings[0], t('assignments') || 'This section shows your current assignments. Click on any assignment to enter or view data.', 'bottom');
			assignmentsSectionStepIndex = steps.length - 1;
		}

		// Past Submissions section
		const pastSubmissionsHeader = document.getElementById('approved-assignments-header');
		if (pastSubmissionsHeader) {
			addStep(pastSubmissionsHeader, t('pastSubmissions') || 'View your past submissions and approved forms here. You can filter by year and template.', 'bottom');
			pastSubmissionsStepIndex = steps.length - 1;
		}

		// Metrics/Charts section
		const metricsHeadings = Array.from(document.querySelectorAll('h2')).filter(h =>
			h.textContent.includes('Submission History') || h.textContent.includes('Performance') || h.textContent.includes('Data Quality'));
		if (metricsHeadings.length > 0) {
			addStep(metricsHeadings[0], t('metrics') || 'Monitor your data quality and submission performance with charts and statistics.', 'bottom');
			metricsStepIndex = steps.length - 1;
		}

		// Recent Activities section
		const activitiesHeadings = Array.from(document.querySelectorAll('h2')).filter(h =>
			h.textContent.includes('Recent Activities') || h.textContent.includes('activities'));
		if (activitiesHeadings.length > 0) {
			addStep(activitiesHeadings[0], t('recentActivities') || 'Stay updated with recent activities and changes made by other focal points in your country.', 'left');
			recentActivitiesStepIndex = steps.length - 1;
		}

		// Language selector
		const langBtn = document.getElementById('language-selector-button');
		if (langBtn) {
			addStep(langBtn, t('language') || '', 'left');
			languageStepIndex = steps.length - 1;
		}

		// Notifications
		const notifBtn = document.getElementById('notifications-bell-button');
		if (notifBtn) addStep(notifBtn, t('notifications') || '', isRTL ? 'left' : 'right');

		// Profile menu
		const profileBtn = document.getElementById('profile-icon-button');
		if (profileBtn) addStep(profileBtn, t('profile') || '', isRTL ? 'left' : 'right');

		// Chatbot (if enabled)
		const chatbotFab = document.getElementById('aiChatbotFAB');
		if (chatbotFab) {
			addStep(chatbotFab, t('chatbot') || '', 'left');
			chatbotStepIndex = steps.length - 1;
		}

		return steps;
	}

	function applyOverlayStrength() {
		try {
			const overlays = document.querySelectorAll('div[class*="introjs-overlay"] , .introjs-overlay');
			overlays.forEach((overlay) => {
				overlay.style.background = 'rgba(0, 0, 0, 0.4)';
				overlay.style.backdropFilter = 'none';
				overlay.style.webkitBackdropFilter = 'none';
			});

			// Ensure helper layer creates proper cutout effect
			const helperLayers = document.querySelectorAll('.introjs-helperLayer');
			helperLayers.forEach((helper) => {
				helper.style.background = 'transparent';
				helper.style.border = '2px solid rgba(197, 48, 48, 0.8)';
				helper.style.borderRadius = '8px';
				helper.style.boxShadow = '0 0 0 9999px rgba(0, 0, 0, 0.4)';
			});
		} catch (_) {}
	}

	function unblurHighlightedElement() {
		try {
			// Find all possible highlighted elements using various selectors
			const selectors = [
				'.introjs-showElement',
				'.introjs-relativePosition',
				'.introjs-fixedPosition',
				'.introjs-highlighted',
				'[data-intro-group]',
				'.humdb-intro-highlight'
			];

			let highlightedElement = null;
			for (const selector of selectors) {
				highlightedElement = document.querySelector(selector);
				if (highlightedElement) break;
			}

			// Also try to find the element that's currently being targeted by the tour
			if (!highlightedElement) {
				const helperLayer = document.querySelector('.introjs-helperLayer');
				if (helperLayer) {
					// Get the element ID or selector from the helper layer
					const targetElement = helperLayer.previousElementSibling;
					if (targetElement) {
						highlightedElement = targetElement;
					}
				}
			}

			// If we found an element, unblur it and its parents
			if (highlightedElement) {
				console.log('Unblurring element:', highlightedElement);
				highlightedElement.style.filter = 'none !important';
				highlightedElement.style.webkitFilter = 'none !important';

				// Also unblur any parent containers that might be affected
				let parent = highlightedElement.parentElement;
				while (parent && parent !== document.body) {
					parent.style.filter = 'none !important';
					parent.style.webkitFilter = 'none !important';
					parent = parent.parentElement;
				}
			} else {
				console.log('No highlighted element found');
			}
		} catch (e) {
			console.error('Error unblurring element:', e);
		}
	}

	function unblurSidebar() {
		try {
			const sidebar = document.getElementById('adminSidebar');
			if (sidebar) {
				sidebar.style.filter = 'none';
				sidebar.style.webkitFilter = 'none';
			}
		} catch (_) {}
	}

	function reblurElements() {
		try {
			// Reset filter styles for highlighted elements
			const highlightedElements = document.querySelectorAll('.introjs-showElement, .introjs-relativePosition');
			highlightedElements.forEach(el => {
				el.style.filter = '';
				el.style.webkitFilter = '';
			});

			// Reset sidebar
			const sidebar = document.getElementById('adminSidebar');
			if (sidebar) {
				sidebar.style.filter = '';
				sidebar.style.webkitFilter = '';
			}
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

	function openLanguageDropdownForTour() {
		try {
			const btn = document.getElementById('language-selector-button');
			const dd = document.getElementById('language-dropdown');
			const arrow = btn ? btn.querySelector('.dropdown-arrow') : null;
			if (!dd) return;
			// Ensure visible
			if (dd.classList.contains('hidden')) dd.classList.remove('hidden');
			// Boost z-index above overlay and tooltip
			dd.dataset.prevZ = dd.style.zIndex || '';
			dd.style.zIndex = '2147483647';
			dd.style.pointerEvents = 'auto';
			languageMenuOpenedByTour = true;
			if (btn) btn.setAttribute('aria-expanded', 'true');
			if (arrow) arrow.style.transform = 'rotate(180deg)';
			// Re-apply after a short delay in case Intro re-renders
			setTimeout(() => {
				try {
					dd.style.zIndex = '2147483647';
					dd.style.pointerEvents = 'auto';
				} catch (_) {}
			}, 150);
		} catch (_) {}
	}

	function closeLanguageDropdownForTour() {
		try {
			const btn = document.getElementById('language-selector-button');
			const dd = document.getElementById('language-dropdown');
			const arrow = btn ? btn.querySelector('.dropdown-arrow') : null;
			if (dd) {
				if (!dd.classList.contains('hidden')) dd.classList.add('hidden');
				// Reset z-index
				if (dd.dataset && 'prevZ' in dd.dataset) {
					dd.style.zIndex = dd.dataset.prevZ;
					delete dd.dataset.prevZ;
				} else {
					dd.style.zIndex = '';
				}
				dd.style.pointerEvents = '';
			}
			if (btn) btn.setAttribute('aria-expanded', 'false');
			if (arrow) arrow.style.transform = 'rotate(0deg)';
			languageMenuOpenedByTour = false;
		} catch (_) {}
	}

	function startSiteTour(force) {
		const isFocalPoint = document.body.classList.contains('focal-point');
		const role = isFocalPoint ? 'focal_point' : 'admin';
		const tourKey = `humdb_tour_status_${role}`;
		const isRTL = document.documentElement.getAttribute('dir') === 'rtl';
		const status = localStorage.getItem(tourKey);
		const i18n = window.TOUR_I18N || {};

		if (!force && !TOUR_DEV_MODE && (status === 'completed' || status === 'skipped')) return;

		let steps = buildTourSteps();
		// Remove the last step on mobile view
		if (window.innerWidth <= 768 && steps.length > 0) {
			steps.pop();
		}
		if (!steps.length) {
			// Fallback generic step if nothing matched
			const fallbackText = (window.TOUR_I18N && window.TOUR_I18N.focal_steps && (window.TOUR_I18N.focal_steps.brand || 'Welcome! This tour will highlight key parts of your focal point dashboard.')) || 'Welcome! This tour will highlight key parts of your focal point dashboard.';
			steps = [{ intro: fallbackText }];
		}

		const start = function() {
			if (typeof introJs === 'undefined') {
				console.warn('Intro.js not available after load attempt.');
				return;
			}

			// Use the non-deprecated API
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

			function isCurrentStep(index, targetElement) {
				try {
					if (typeof instance.currentStep === 'function' && index !== null) {
						return instance.currentStep() === index;
					}
				} catch (_) {}
				if (targetElement && sidebarStepIndex === index && targetElement.id === 'sidebarToggle') return true;
				if (targetElement && languageStepIndex === index && targetElement.id === 'language-selector-button') return true;
				if (targetElement && chatbotStepIndex === index && targetElement.id === 'aiChatbotFAB') return true;
				return false;
			}

			try {
				instance.setOptions({
					steps,
					showProgress: true,
					showStepNumbers: true,
					showBullets: false,
					exitOnEsc: true,
					exitOnOverlayClick: false, // prevent exit on overlay click
					disableInteraction: false,
					nextLabel: i18n.next || 'Next',
					prevLabel: i18n.back || 'Back',
					skipLabel: i18n.skip || 'Skip',
					doneLabel: i18n.done || 'Done',
					rtl: isRTL,
					overlayOpacity: 0.4,
					tooltipClass: 'humdb-intro',
					highlightClass: 'humdb-intro-highlight',
					scrollTo: 'tooltip',
					scrollToElement: false, // Disable auto-scrolling to element
					showButtons: true,
					showStepNumbers: true,
					skipLabel: '', // Hide skip button by setting empty label
					showSkip: false // Explicitly disable skip button
				});

				// Fallback for older builds that still close on overlay click + enforce blur
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

						// Get current step index to determine what we're leaving
						const currentStep = typeof instance.currentStep === 'function' ? instance.currentStep() : -1;

						// Closing language dropdown when leaving the language step
						if (currentStep === languageStepIndex && languageMenuOpenedByTour) {
							closeLanguageDropdownForTour();
						}

						// Expand past submissions section when showing that step
						if (isCurrentStep(pastSubmissionsStepIndex, targetElement)) {
							const pastSubmissionsContent = document.getElementById('approved-assignments-content');
							const toggleButton = document.getElementById('toggle-approved-assignments');
							if (pastSubmissionsContent && pastSubmissionsContent.classList.contains('hidden')) {
								try {
									pastSubmissionsContent.classList.remove('hidden');
									if (toggleButton) {
										toggleButton.classList.remove('rotate-0');
										toggleButton.classList.add('rotate-180');
									}
								} catch (_) {}
							}
						}

						// Always collapse sidebar when moving to language step
						if (targetElement && targetElement.id === 'language-selector-button') {
							const adminSidebar = document.getElementById('adminSidebar');
							const toggleBtn = document.getElementById('sidebarToggle');
							if (adminSidebar && toggleBtn) {
								// Check if sidebar is currently expanded
								const isExpanded = !adminSidebar.classList.contains('collapsed') && !document.documentElement.classList.contains('sidebar-initially-collapsed');
								if (isExpanded) {
									try {
										toggleBtn.click();
										console.log('Collapsing sidebar when moving to language step');
									} catch (_) {}
								}
							}
							sidebarExpandedByTour = false;
							sidebarWasCollapsedInitially = false;
						}

						// Also collapse sidebar when leaving sidebar step (backup logic)
						if (currentStep === sidebarStepIndex && sidebarExpandedByTour) {
							const adminSidebar = document.getElementById('adminSidebar');
							const toggleBtn = document.getElementById('sidebarToggle');
							if (adminSidebar && toggleBtn && sidebarWasCollapsedInitially) {
								try {
									toggleBtn.click();
									console.log('Collapsing sidebar when leaving sidebar step (backup)');
								} catch (_) {}
							}
							sidebarExpandedByTour = false;
							sidebarWasCollapsedInitially = false;
						}
					});
				}

				if (typeof instance.onafterchange === 'function') {
					instance.onafterchange(function(targetElement) {
						// Add dynamic adjustment class to tooltip
						const tooltip = document.querySelector('.humdb-intro');
						if (tooltip) {
							tooltip.classList.add('tour-adjusting');
						}
						applyOverlayStrength();

						// Ensure proper highlighting with Intro.js system
						setTimeout(() => {
							applyOverlayStrength();
						}, 50);

						// If on language button, open dropdown (ensure above overlay)
						if (isCurrentStep(languageStepIndex, targetElement)) {
							setTimeout(openLanguageDropdownForTour, 50);
							// Position language step tooltip to the left with gap
							setTimeout(() => {
								const tooltip = document.querySelector('.introjs-tooltip.humdb-intro');
								if (tooltip) {
									tooltip.classList.add('language-step-tooltip');
									tooltip.style.position = 'fixed';
									tooltip.style.left = '50%';
									tooltip.style.top = '50%';
									tooltip.style.transform = 'translate(-80%, -50%)';
									tooltip.style.right = 'auto';
									tooltip.style.margin = '0';
									tooltip.style.zIndex = '2147483648';
								}
							}, 100);
						}

						// If on chatbot step, preserve button position and position tooltip properly
						if (isCurrentStep(chatbotStepIndex, targetElement)) {
							// Immediately fix chatbot position
							const chatbotFab = document.getElementById('aiChatbotFAB');
							if (chatbotFab) {
								// Force the chatbot button back to its correct position immediately
								chatbotFab.style.cssText = 'position: fixed !important; bottom: 2rem !important; right: 2rem !important; z-index: 9999999 !important; transform: none !important; left: auto !important; top: auto !important;';
							}

							// Position tooltip with multiple attempts to ensure it works
							setTimeout(() => {
								const tooltip = document.querySelector('.introjs-tooltip.humdb-intro');
								if (tooltip) {
									tooltip.classList.add('chatbot-step-tooltip');
									tooltip.style.cssText = 'position: fixed !important; right: 6rem !important; bottom: 2rem !important; left: auto !important; top: auto !important; transform: none !important; margin: 0 !important; z-index: 2147483647 !important;';
								}
							}, 50);

							// Additional safety checks
							setTimeout(() => {
								if (chatbotFab) {
									chatbotFab.style.cssText = 'position: fixed !important; bottom: 2rem !important; right: 2rem !important; z-index: 9999999 !important; transform: none !important; left: auto !important; top: auto !important;';
								}
							}, 200);
						}

						// Remove step-specific positioning for other steps
						if (!isCurrentStep(languageStepIndex, targetElement) && !isCurrentStep(chatbotStepIndex, targetElement)) {
							const tooltip = document.querySelector('.introjs-tooltip.humdb-intro');
							if (tooltip) {
								if (tooltip.classList.contains('language-step-tooltip')) {
									tooltip.classList.remove('language-step-tooltip');
									tooltip.style.position = '';
									tooltip.style.left = '';
									tooltip.style.top = '';
									tooltip.style.transform = '';
									tooltip.style.right = '';
									tooltip.style.margin = '';
									tooltip.style.zIndex = '';
								}
								if (tooltip.classList.contains('chatbot-step-tooltip')) {
									tooltip.classList.remove('chatbot-step-tooltip');
									tooltip.style.position = '';
									tooltip.style.left = '';
									tooltip.style.top = '';
									tooltip.style.bottom = '';
									tooltip.style.right = '';
									tooltip.style.transform = '';
									tooltip.style.margin = '';
									tooltip.style.zIndex = '';
								}
							}
						}

						// If on sidebar step, ensure expanded, but don't collapse until leaving the step
						if (isCurrentStep(sidebarStepIndex, targetElement) && window.innerWidth > 768) {
							// Prevent any unwanted scrolling
							document.body.style.overflow = 'hidden';

							const adminSidebar = document.getElementById('adminSidebar');
							const toggleBtn = document.getElementById('sidebarToggle');

							// Scroll sidebar to top to ensure toggle button is visible
							if (adminSidebar) {
								adminSidebar.scrollTop = 0;
								// Also try scrolling any scrollable containers within the sidebar
								const scrollableElements = adminSidebar.querySelectorAll('[style*="overflow"], .overflow-auto, .overflow-y-auto');
								scrollableElements.forEach(el => {
									el.scrollTop = 0;
								});
							}

							// Ensure we're targeting the correct toggle button
							if (toggleBtn && adminSidebar) {
								// Make sure the toggle button is properly positioned and visible
								toggleBtn.style.position = 'relative';
								toggleBtn.style.zIndex = '9999999';

								sidebarWasCollapsedInitially = adminSidebar.classList.contains('collapsed') || document.documentElement.classList.contains('sidebar-initially-collapsed');
								if (sidebarWasCollapsedInitially) {
									try {
										toggleBtn.click();
										// Scroll to top again after expansion and refresh tooltip position
										setTimeout(() => {
											if (adminSidebar) adminSidebar.scrollTop = 0;
											if (typeof instance.refresh === 'function') {
												instance.refresh();
											}
										}, 300);
									} catch (_) {}
									sidebarExpandedByTour = true;
								} else {
									sidebarExpandedByTour = false;
								}
							}

							// Re-enable scrolling after a delay
							setTimeout(() => {
								document.body.style.overflow = '';
							}, 500);
						}

						// Remove adjustment class after a delay
						setTimeout(() => {
							if (tooltip) {
								tooltip.classList.remove('tour-adjusting');
							}
						}, 600);
					});
				}

				if (typeof instance.oncomplete === 'function') {
					instance.oncomplete(() => {
						if (languageMenuOpenedByTour) closeLanguageDropdownForTour();
						reblurElements(); // Reset all blur effects
						stopOverlayObserver();
						if (!TOUR_DEV_MODE) {
							localStorage.setItem(tourKey, 'completed');
						}
						clearAnimationTimeouts();

						// Show profile dropdown and tooltip after completing the tour
						setTimeout(() => {
							showProfileTooltip();
						}, 500);
					});
				}

				if (typeof instance.onexit === 'function') {
					instance.onexit(() => {
						if (languageMenuOpenedByTour) closeLanguageDropdownForTour();
						// If the user exits while on the sidebar step and we expanded it, restore
						if (sidebarExpandedByTour && sidebarWasCollapsedInitially) {
							const toggleBtn = document.getElementById('sidebarToggle');
							try { toggleBtn.click(); } catch (_) {}
						}
						sidebarExpandedByTour = false;
						sidebarWasCollapsedInitially = false;
						reblurElements(); // Reset all blur effects
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
					// Ensure overlay strength right after start
					setTimeout(() => {
						applyOverlayStrength();
						startOverlayObserver();
					}, 0);
				} else {
					console.error('introJs instance missing start method');
				}
			} catch (error) {
				console.error('Error starting tour:', error);
			}
		};

		if (typeof introJs === 'undefined') {
			ensureIntroJsLoaded(start);
		} else {
			start();
		}
	}

	function showProfileTooltip() {
		try {
			const profileButton = document.getElementById('profile-icon-button');
			const profilePopup = document.getElementById('profile-popup');
			const startTourLink = document.getElementById('startTourLink');

			if (!profileButton || !profilePopup || !startTourLink) return;

			// Open the profile dropdown
			profilePopup.classList.remove('hidden');

			// Add pulse animation to the tour link
			startTourLink.classList.add('tour-link-pulse');

			// Create tooltip
			const tooltip = document.createElement('div');
			tooltip.className = 'tour-tooltip';
			tooltip.textContent = 'You can start the tour anytime by clicking here!';

			// Position tooltip relative to the tour link
			document.body.appendChild(tooltip);

			// Calculate position
			const linkRect = startTourLink.getBoundingClientRect();
			const tooltipRect = tooltip.getBoundingClientRect();

			tooltip.style.left = `${linkRect.left + (linkRect.width / 2) - (tooltipRect.width / 2)}px`;
			tooltip.style.top = `${linkRect.top - tooltipRect.height - 12}px`;

			// Show tooltip with animation
			setTimeout(() => {
				tooltip.classList.add('show');
			}, 100);

			// Auto-hide after 5 seconds
			setTimeout(() => {
				if (tooltip.parentNode) {
					tooltip.classList.remove('show');
					setTimeout(() => {
						if (tooltip.parentNode) {
							tooltip.parentNode.removeChild(tooltip);
						}
					}, 300);
				}
				startTourLink.classList.remove('tour-link-pulse');
			}, 5000);

			// Hide on click elsewhere
			const hideTooltip = (e) => {
				if (!startTourLink.contains(e.target) && !tooltip.contains(e.target)) {
					if (tooltip.parentNode) {
						tooltip.classList.remove('show');
						setTimeout(() => {
							if (tooltip.parentNode) {
								tooltip.parentNode.removeChild(tooltip);
							}
						}, 300);
					}
					startTourLink.classList.remove('tour-link-pulse');
					document.removeEventListener('click', hideTooltip);
				}
			};

			setTimeout(() => {
				document.addEventListener('click', hideTooltip);
			}, 1000);

		} catch (error) {
			console.error('Error showing profile tooltip:', error);
		}
	}

	function initTourBindings() {
		// Manual start from profile popup
		const startTourLink = document.getElementById('startTourLink');
		if (startTourLink) {
			startTourLink.addEventListener('click', function(e) {
				e.preventDefault();
				startSiteTour(true);
			});
		}

		// Pre-tour modal logic
		const isFocalPoint = document.body.classList.contains('focal-point');
		const role = isFocalPoint ? 'focal_point' : 'admin';
		const tourKey = `humdb_tour_status_${role}`;
		const status = localStorage.getItem(tourKey);
		const modal = document.getElementById('tourPreModal');
		const modalScrim = document.getElementById('tourPreModalScrim');
		const modalStartBtn = document.getElementById('tourModalStartBtn');
		const modalSkipBtn = document.getElementById('tourModalSkipBtn');

		function openPreTourModal() {
			if (!modal) return;
			modal.classList.remove('hidden');
			// Prevent body scroll behind modal
			document.body.style.overflow = 'hidden';
		}

		function closePreTourModal() {
			if (!modal) return;
			modal.classList.add('hidden');
			document.body.style.overflow = '';
		}

		if (modalStartBtn) {
			modalStartBtn.addEventListener('click', function() {
				closePreTourModal();
				setTimeout(() => {
					// Ensure Intro.js is present before starting
					ensureIntroJsLoaded(() => startSiteTour(true));
				}, 100);
			});
		}
		if (modalSkipBtn) {
			modalSkipBtn.addEventListener('click', function() {
				closePreTourModal();
				localStorage.setItem(tourKey, 'skipped');

				// Show profile dropdown and tooltip after a short delay
				setTimeout(() => {
					showProfileTooltip();
				}, 500);
			});
		}
		if (modalScrim) {
			modalScrim.addEventListener('click', function() {
				closePreTourModal();
				localStorage.setItem(tourKey, 'skipped');
			});
		}

		// Check if we're in the mobile app - disable tour modal if so
		const isMobileApp = window.isMobileApp === true ||
		                   window.IFRCMobileApp === true ||
		                   document.documentElement.getAttribute('data-mobile-app') === 'true' ||
		                   (navigator.userAgent && navigator.userAgent.includes('wv'));

		// Welcome / pre-tour modal disabled – tour only via profile "Take a quick tour"
		setTimeout(function() {
			if (isMobileApp && modal) {
				modal.classList.add('hidden');
			}
			// No automatic welcome modal or auto-start
		}, 600);
	}

	document.addEventListener('DOMContentLoaded', initTourBindings);

	// Expose for debugging/manual triggering if needed
	window.startIFRCTour = function() { startSiteTour(true); };
})();
