/* Auto-generated from user_form.html — DO NOT edit template inline JS */
/* Config is bootstrapped via window.userFormConfig in the template */

(function () {
    'use strict';
    var cfg = window.userFormConfig || {};

    // --- Block 1 (original lines 660-1313) ---
                    (function () {
                      const READ_ONLY = cfg.readOnly;
                      if (READ_ONLY) return;

                      const form = document.querySelector('form');
                      if (!form) return;

                      const roleInputs = Array.from(form.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'));
                      if (!roleInputs.length) return;

                      // Track what the user explicitly wants (vs auto-checked due to implication)
                      for (const input of roleInputs) {
                        input.dataset.userWanted = input.checked ? '1' : '0';
                        input.dataset.userTouched = '0';
                        input.addEventListener('change', function () {
                          if (this.disabled) return;

                          this.dataset.userWanted = this.checked ? '1' : '0';
                          this.dataset.userTouched = '1';

                          // If the user is adjusting a Core child checkbox, allow the Core umbrella to sync again.
                          if (coreEssentialsInputRef && isEssentialsChild(this)) {
                            delete coreEssentialsInputRef.dataset.manualOverride;
                          }

                          // If the user is adjusting an Admin role checkbox (not Full itself), allow Full umbrella to sync again.
                          if (fullAdminInputRef && adminGroup && adminGroup.contains(this) && this !== fullAdminInputRef) {
                            delete fullAdminInputRef.dataset.manualOverride;
                          }

                          // Umbrella checkboxes have their own handlers that call recomputeLocks()
                          if (this === fullAdminInputRef || this === coreEssentialsInputRef) return;

                          recomputeLocks();
                        });
                      }

                      const coreGroup = document.getElementById('roles-core-group'); // Admin Roles: Presets + Categorized Admin Roles
                      const adminGroup = coreGroup; // Admin roles are now merged into roles-core-group
                      const assignmentGroup = document.getElementById('roles-assignment-group');

                      // Role Type Selector Handler
                      const roleTypeSelect = document.getElementById('role_type_select');
                      const adminSectionsContainer = document.getElementById('admin-sections');

                      function getAssignmentRoleInputs() {
                        if (!assignmentGroup) return { viewer: null, editorSubmitter: null, approver: null, all: [] };
                        const aInputs = Array.from(
                          assignmentGroup.querySelectorAll('input[type="checkbox"][name="rbac_roles"]')
                        );
                        let viewer = null;
                        let editorSubmitter = null;
                        let approver = null;
                        for (const input of aInputs) {
                          const txt = (getLabelSpanText(input) || '').toLowerCase();
                          if (txt === 'viewer') viewer = input;
                          if (txt === 'editor & submitter' || txt === 'editor and submitter') editorSubmitter = input;
                          if (txt === 'approver') approver = input;
                        }
                        return { viewer, editorSubmitter, approver, all: aInputs };
                      }

                      function ensureMinimumFocalPointAssignmentRoles() {
                        const { viewer, all } = getAssignmentRoleInputs();
                        const hasAnyAssignmentRole = all.some(function (input) { return input.checked; });
                        if (!hasAnyAssignmentRole && viewer && !viewer.disabled) {
                          viewer.checked = true;
                          viewer.dataset.userWanted = '1';
                          if (typeof markAutoChecked === 'function') markAutoChecked(viewer, false);
                        }
                      }

                      function syncRoleTypeUi() {
                        const selectedType = roleTypeSelect?.value || 'admin';
                        const isFocalPoint = selectedType === 'focal_point';

                        if (adminSectionsContainer) {
                          adminSectionsContainer.classList.toggle('hidden', isFocalPoint);
                        }

                        if (assignmentGroup) {
                          const approverRoles = assignmentGroup.querySelectorAll('.assignment-approver-role');
                          approverRoles.forEach(function(role) {
                            role.classList.toggle('hidden', isFocalPoint);
                          });
                        }
                      }

                      function handleRoleTypeChangeFromUser() {
                        const selectedType = roleTypeSelect?.value || 'admin';
                        const isFocalPoint = selectedType === 'focal_point';

                        syncRoleTypeUi();

                        // If switching to Focal Point, clear ALL admin roles (including Full/Core/System Manager presets).
                        // This keeps the submitted form aligned with what the UI is showing.
                        if (isFocalPoint) {
                          clearAdminRolesForFocalPoint();
                          ensureMinimumFocalPointAssignmentRoles();
                        }

                        try { recomputeLocks(); } catch (e) {}
                      }

                      function clearAdminRolesForFocalPoint() {
                        const adminInputs = adminGroup
                          ? Array.from(adminGroup.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'))
                          : [];
                        for (const input of adminInputs) {
                          setLocked(input, false);
                          input.checked = false;
                          input.dataset.userWanted = '0';
                          input.dataset.userTouched = '1';
                          delete input.dataset.manualOverride;
                          try { markAutoChecked(input, false); } catch (e) {}
                        }
                        // Approver is admin-only in the UI: clear it too (independent of adminGroup).
                        if (assignmentGroup) {
                          const approverRoles = assignmentGroup.querySelectorAll('.assignment-approver-role');
                          approverRoles.forEach(function (role) {
                            const checkbox = role.querySelector('input[type="checkbox"]');
                            if (checkbox) {
                              checkbox.checked = false;
                              checkbox.dataset.userWanted = '0';
                            }
                          });
                        }
                      }

                      // Add event listener to role type dropdown
                      if (roleTypeSelect) {
                        roleTypeSelect.addEventListener('change', handleRoleTypeChangeFromUser);
                        syncRoleTypeUi();
                        if (roleTypeSelect.value === 'focal_point') {
                          ensureMinimumFocalPointAssignmentRoles();
                        }
                        try { recomputeLocks(); } catch (e) {}
                      }

                      function normalize(s) {
                        return String(s || '').trim().toLowerCase();
                      }

                      function findAdminRoleInput(featureName, actionName) {
                        if (!adminGroup) return null;
                        const f = normalize(featureName);
                        const a = normalize(actionName);
                        for (const card of adminGroup.querySelectorAll('.js-role-feature-card')) {
                          const featureTitle = normalize(card.querySelector('.text-sm.font-medium')?.textContent);
                          if (!featureTitle || featureTitle !== f) continue;
                          for (const input of card.querySelectorAll('input[type="checkbox"][name="rbac_roles"]')) {
                            const action = normalize(getLabelSpanText(input));
                            if (action === a) return input;
                          }
                        }
                        return null;
                      }

                      // Find System Manager, Full, and Core in Admin Roles section
                      let fullAdminInputRef = null;
                      let coreEssentialsInputRef = null;
                      let systemManagerInputRef = null;
                      // Check in coreGroup (Admin Roles section where System Manager, Full, and Core are)
                      if (coreGroup) {
                        const coreInputs = Array.from(coreGroup.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'));
                        for (const input of coreInputs) {
                          const label = getLabelSpanText(input);
                          const normalizedLabel = normalize(label);
                          if (normalizedLabel.includes('system manager')) {
                            systemManagerInputRef = input;
                          } else if (normalizedLabel.includes('full') || normalizedLabel.includes('all admin roles')) {
                            fullAdminInputRef = input;
                          } else if (normalizedLabel.includes('core') || normalizedLabel.includes('essentials')) {
                            coreEssentialsInputRef = input;
                          }
                        }
                      }
                      // Fallback: try finding in admin group if not found in core group
                      if (!fullAdminInputRef) {
                        fullAdminInputRef = findAdminRoleInput('full', 'all admin roles');
                      }
                      if (!coreEssentialsInputRef) {
                        coreEssentialsInputRef = findAdminRoleInput('core', 'essentials only');
                      }

                      // Matches admin_core permissions in rbac_seed_service.py exactly (view-only).
                      const essentialsSpecs = [
                        { feature: 'Docs', action: 'View' },
                        { feature: 'Users', action: 'View' },
                        { feature: 'Templates', action: 'View' },
                        { feature: 'Assignments', action: 'View' },
                        { feature: 'Countries & Organization', action: 'View' },
                        { feature: 'Indicator Bank', action: 'View' },
                      ];

                      function getEssentialsChildren() {
                        const inputs = [];
                        for (const spec of essentialsSpecs) {
                          const inp = findAdminRoleInput(spec.feature, spec.action);
                          if (inp) inputs.push(inp);
                        }
                        return inputs;
                      }

                      // Cache Core child inputs for quick checks.
                      const essentialsChildrenSet = new Set(getEssentialsChildren());
                      function isEssentialsChild(input) {
                        return essentialsChildrenSet.has(input);
                      }

                      function getLabelSpanText(input) {
                        const label = input.closest('label');
                        if (!label) return '';
                        const span = label.querySelector('span');
                        return (span ? span.textContent : label.textContent).trim();
                      }

                      function getFeatureTitleForInput(input) {
                        const card = input.closest('.js-role-feature-card');
                        if (!card) return '';
                        return (card.querySelector('.text-sm.font-medium')?.textContent || '').trim();
                      }

                      // Full (All admin roles) should NOT include Settings or Plugins.
                      function isExcludedFromFull(input) {
                        const featureTitle = getFeatureTitleForInput(input);
                        return featureTitle === 'Settings' || featureTitle === 'Plugins';
                      }

                      function getFullEligibleAdminInputs() {
                        if (!adminGroup) return [];
                        return Array.from(adminGroup.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'))
                          .filter((i) => !systemManagerInputRef || i !== systemManagerInputRef)
                          // Never treat the Full checkbox itself as a child role (otherwise it can get locked).
                          .filter((i) => !fullAdminInputRef || i !== fullAdminInputRef)
                          .filter((i) => !isExcludedFromFull(i));
                      }

                      function setLocked(input, locked) {
                        const label = input.closest('label');
                        if (locked) {
                          input.disabled = true;
                          input.dataset.locked = '1';
                          if (label) {
                            label.classList.add('opacity-60', 'cursor-not-allowed');
                          }
                        } else {
                          if (input.dataset.locked === '1') {
                            input.disabled = false;
                          }
                          input.dataset.locked = '0';
                          if (label) {
                            label.classList.remove('opacity-60', 'cursor-not-allowed');
                          }
                        }
                      }

                      function markAutoChecked(input, autoChecked) {
                        input.dataset.autoChecked = autoChecked ? '1' : '0';
                      }

                      function isAutoChecked(input) {
                        return input.dataset.autoChecked === '1';
                      }

                      function userWants(input) {
                        return input.dataset.userWanted === '1';
                      }

                      // Special behavior: Full (All admin roles) is a select-all umbrella for Admin roles.
                      // - Checking it selects all Admin roles.
                      // - Unchecking it clears all Admin roles.
                      if (fullAdminInputRef) {
                        fullAdminInputRef.addEventListener('change', function () {
                          if (this.disabled) return;
                          if (!adminGroup) return;

                          // Clear indeterminate state when manually toggled
                          this.indeterminate = false;

                          const adminInputs = getFullEligibleAdminInputs();

                          if (this.checked) {
                            delete this.dataset.manualOverride;
                            this.dataset.userWanted = '1';
                            this.dataset.userTouched = '1';
                            for (const input of adminInputs) {
                              if (input === this) continue;
                              if (!input.checked) {
                                input.checked = true;
                                // This is a bulk user action via the preset, not an implied/locked state.
                                markAutoChecked(input, false);
                              }
                              // Treat selections made by the preset as explicit user intent so they don't get auto-cleared.
                              input.dataset.userWanted = '1';
                              input.dataset.userTouched = '1';
                            }
                          } else {
                            // Prevent snap-back: if admin roles remain checked due to other implications,
                            // keep Full unchecked until the user explicitly changes an admin role box.
                            this.dataset.manualOverride = 'cleared';
                            this.dataset.userWanted = '0';
                            for (const input of adminInputs) {
                              input.checked = false;
                              input.dataset.userWanted = '0';
                              input.dataset.userTouched = '0';
                              markAutoChecked(input, false);
                            }
                          }

                          recomputeLocks();
                        });
                      }

                      // Special behavior: Core (Essentials only) is an umbrella for its child boxes.
                      // - Checking it checks all child boxes.
                      // - Unchecking it clears all child boxes.
                      if (coreEssentialsInputRef) {
                        coreEssentialsInputRef.addEventListener('change', function () {
                          if (this.disabled) return;
                          const children = getEssentialsChildren();

                          // Clear indeterminate state when manually toggled
                          this.indeterminate = false;

                          if (this.checked) {
                            delete this.dataset.manualOverride;
                            this.dataset.userWanted = '1';
                            this.dataset.userTouched = '1';
                            for (const child of children) {
                              if (!child.checked) {
                                child.checked = true;
                                markAutoChecked(child, true);
                                // Mark as user-wanted since Core umbrella was explicitly checked
                                child.dataset.userWanted = '1';
                              }
                            }
                          } else {
                            // Prevent snap-back: if children remain checked due to other implications,
                            // keep Core unchecked until the user explicitly changes a child box.
                            this.dataset.manualOverride = 'cleared';
                            this.dataset.userWanted = '0';
                            for (const child of children) {
                              child.checked = false;
                              child.dataset.userWanted = '0';
                              child.dataset.userTouched = '0';
                              markAutoChecked(child, false);
                            }
                          }
                          recomputeLocks();
                        });
                      }

                      function recomputeLocks() {
                        // Clear previous locks (only those we applied)
                        for (const input of roleInputs) {
                          setLocked(input, false);
                        }

                        const implied = new Set(); // inputs that must be checked
                        const lockSet = new Set(); // inputs that must be read-only

                        // 1) System Manager implies everything (read-only)
                        const systemManagerInput = systemManagerInputRef;
                        const systemManagerChecked = Boolean(systemManagerInput && systemManagerInput.checked);
                        if (systemManagerChecked) {
                          // Clear manual overrides when System Manager is active since it overrides everything
                          if (fullAdminInputRef) {
                            delete fullAdminInputRef.dataset.manualOverride;
                          }
                          if (coreEssentialsInputRef) {
                            delete coreEssentialsInputRef.dataset.manualOverride;
                          }
                          for (const input of roleInputs) {
                            if (input === systemManagerInput) continue;
                            // Translator is an opt-in-only role: System Manager should not
                            // auto-enable it (it toggles a UI most admins don't need).
                            if (input.classList.contains('translator-role-checkbox')) continue;
                            implied.add(input);
                            lockSet.add(input);
                          }
                        }

                        // 2) Admin: Full (All admin roles) is a bulk preset only.
                        // It should NOT lock roles or keep re-imposing selections after the click.
                        const fullAdminInput = fullAdminInputRef;
                        const fullChecked = Boolean(fullAdminInput && fullAdminInput.checked);
                        const fullManuallyCleared = Boolean(fullAdminInput && fullAdminInput.dataset.manualOverride === 'cleared');

                        // 2a) Handle Full checkbox state: checked, unchecked, or indeterminate
                        if (!systemManagerChecked && fullAdminInput && adminGroup) {
                          // Only consider admin roles that Full is allowed to include (excludes Settings + Plugins).
                          const adminInputsEligible = getFullEligibleAdminInputs();
                          const checkedCount = adminInputsEligible.filter((i) => i.checked).length;
                          const totalCount = adminInputsEligible.length;
                          const allAdminRolesChecked = totalCount > 0 && checkedCount === totalCount;

                          // Only show "-" (indeterminate) for Full when the selection includes any NON-essential admin role.
                          // If the user has only Core (Essentials only) and/or its essential children, Full should stay plain unchecked.
                          const essentialsSet = new Set([
                            ...(coreEssentialsInputRef ? [coreEssentialsInputRef] : []),
                            ...getEssentialsChildren(),
                          ]);
                          const checkedNonEssentialCount = adminInputsEligible
                            .filter((i) => i.checked && !essentialsSet.has(i)).length;
                          const someNonEssentialChecked = checkedNonEssentialCount > 0 && checkedCount < totalCount;

                          // Set indeterminate state when some (but not all) admin roles are checked
                          if (someNonEssentialChecked) {
                            fullAdminInput.indeterminate = true;
                            fullAdminInput.checked = false;
                          } else {
                            fullAdminInput.indeterminate = false;
                            // Only auto-check Full when all admin roles are checked and not manually cleared
                            if (allAdminRolesChecked && !fullChecked && !fullManuallyCleared) {
                              implied.add(fullAdminInput);
                            }
                          }
                        } else if (fullAdminInput) {
                          // Clear indeterminate state when System Manager is active
                          fullAdminInput.indeterminate = false;
                        }

                        // 2c) Core (Essentials only) implies its children (not read-only).
                        const coreEssentialsInput = coreEssentialsInputRef;
                        const coreChecked = Boolean(coreEssentialsInput && coreEssentialsInput.checked);
                        const essentialsChildren = getEssentialsChildren();
                        const checkedEssentialsCount = essentialsChildren.filter((i) => i.checked).length;
                        const totalEssentialsCount = essentialsChildren.length;
                        const allEssentialsChildrenChecked = totalEssentialsCount > 0 && checkedEssentialsCount === totalEssentialsCount;
                        const someEssentialsChildrenChecked = checkedEssentialsCount > 0 && checkedEssentialsCount < totalEssentialsCount;
                        const coreManuallyCleared = Boolean(coreEssentialsInput && coreEssentialsInput.dataset.manualOverride === 'cleared');

                        // Handle Core checkbox state: checked, unchecked, or indeterminate
                        if (!systemManagerChecked && !fullChecked && coreEssentialsInput) {
                          // Set indeterminate state when some (but not all) essentials children are checked
                          if (someEssentialsChildrenChecked) {
                            coreEssentialsInput.indeterminate = true;
                            coreEssentialsInput.checked = false;
                          } else {
                            coreEssentialsInput.indeterminate = false;
                            // If Core is checked, add all its children to the implied set.
                            if (coreChecked && !coreManuallyCleared) {
                              for (const child of essentialsChildren) {
                                implied.add(child);
                              }
                            }
                            // If all child boxes are checked, check Core (Essentials only).
                            if (allEssentialsChildrenChecked && !coreChecked && !coreManuallyCleared) {
                              implied.add(coreEssentialsInput);
                            }
                            // If Core is checked but any child is unchecked, uncheck Core.
                            if (coreChecked && !allEssentialsChildrenChecked) {
                              coreEssentialsInput.checked = false;
                              coreEssentialsInput.indeterminate = false;
                              coreEssentialsInput.dataset.userWanted = '0';
                              markAutoChecked(coreEssentialsInput, false);
                            }
                          }
                        } else if (coreEssentialsInput) {
                          // Clear indeterminate state when System Manager or Full is active
                          coreEssentialsInput.indeterminate = false;
                        }

                        // Note: we do NOT force Core children to stay checked when Core is checked.
                        // Core is an umbrella toggle + derived indicator:
                        // - clicking Core checks children
                        // - unchecking any child clears Core
                        // - Core does not lock children

                        // 3) "Manage" implies "View" within each Admin feature row
                        if (adminGroup) {
                          for (const card of adminGroup.querySelectorAll('.js-role-feature-card')) {
                            const featureTitle = (card.querySelector('.text-sm.font-medium')?.textContent || '').trim();
                            if (!featureTitle) continue;

                            const inputs = Array.from(card.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'));
                            if (!inputs.length) continue;

                            const byAction = new Map(); // actionLabel(lower) -> input
                            for (const input of inputs) {
                              const action = getLabelSpanText(input).toLowerCase();
                              if (action) byAction.set(action, input);
                            }

                            const manage = byAction.get('manage');
                            const view = byAction.get('view');
                            if (manage && view && manage.checked) {
                              implied.add(view);
                              lockSet.add(view);
                            }
                          }
                        }

                        // 4) Assignment roles: Approver / Editor & Submitter imply Viewer
                        if (assignmentGroup) {
                          const aInputs = Array.from(assignmentGroup.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'));
                          let viewer = null;
                          let editorSubmitter = null;
                          let approver = null;
                          for (const input of aInputs) {
                            const txt = getLabelSpanText(input).toLowerCase();
                            if (txt === 'viewer') viewer = input;
                            if (txt === 'editor & submitter' || txt === 'editor and submitter') editorSubmitter = input;
                            if (txt === 'approver') approver = input;
                          }
                          if (viewer && ((editorSubmitter && editorSubmitter.checked) || (approver && approver.checked))) {
                            implied.add(viewer);
                            lockSet.add(viewer);
                          }
                        }

                        // Apply implied checks
                        for (const input of implied) {
                          if (!input.checked) {
                            input.checked = true;
                            markAutoChecked(input, true);
                          }
                        }

                        // Uncheck auto-checked roles that are no longer implied and not explicitly wanted
                        for (const input of roleInputs) {
                          const stillImplied = implied.has(input);
                          if (!stillImplied && isAutoChecked(input) && !userWants(input)) {
                            input.checked = false;
                            markAutoChecked(input, false);
                          }
                          if (!stillImplied && !input.checked) {
                            // once off, clear auto marker
                            markAutoChecked(input, false);
                          }
                        }

                        // Apply locks (read-only)
                        for (const input of lockSet) {
                          setLocked(input, true);
                        }
                      }

                      // Visual highlighting: Core vs Full.
                      function applyRoleHighlights() {
                        const CORE_CARD_CLASSES = ['border-blue-200', 'bg-blue-50'];
                        const FULL_CARD_CLASSES = ['border-purple-200', 'bg-purple-50'];
                        const CORE_PILL_CLASSES = ['px-2', 'py-0.5', 'rounded', 'border', 'border-blue-200', 'bg-blue-50', 'text-blue-900'];
                        const FULL_PILL_CLASSES = ['px-2', 'py-0.5', 'rounded', 'border', 'border-purple-200', 'bg-purple-50', 'text-purple-900'];

                        function addCardClasses(input, classes) {
                          if (!input) return;
                          const card = input.closest('.js-role-feature-card');
                          if (!card) return;
                          for (const c of classes) card.classList.add(c);
                        }

                        function addPillClasses(input, classes) {
                          if (!input) return;
                          const label = input.closest('label');
                          if (!label) return;
                          const span = label.querySelector('span');
                          if (!span) return;
                          for (const c of classes) span.classList.add(c);
                        }

                        // Core / Full umbrella boxes
                        addCardClasses(coreEssentialsInputRef, CORE_CARD_CLASSES);
                        addPillClasses(coreEssentialsInputRef, CORE_PILL_CLASSES);
                        addCardClasses(fullAdminInputRef, FULL_CARD_CLASSES);
                        addPillClasses(fullAdminInputRef, FULL_PILL_CLASSES);

                        // Core "child" boxes get blue styling
                        const essentialsChildren = getEssentialsChildren();
                        const essentialsChildrenSet = new Set(essentialsChildren);
                        for (const child of essentialsChildren) {
                          addPillClasses(child, CORE_PILL_CLASSES);
                        }

                        // All other admin roles (not Core children, not Full) get purple styling like Full
                        if (adminGroup) {
                          const allAdminInputs = Array.from(adminGroup.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'))
                            .filter((i) => !systemManagerInputRef || i !== systemManagerInputRef);
                          const processedCards = new Set();

                          for (const input of allAdminInputs) {
                            // Skip Full umbrella and Core children
                            if (input === fullAdminInputRef || input === coreEssentialsInputRef || essentialsChildrenSet.has(input)) {
                              continue;
                            }

                            // Apply purple styling to the pill
                            addPillClasses(input, FULL_PILL_CLASSES);

                            // Apply purple styling to the card (only once per card)
                            const card = input.closest('.js-role-feature-card');
                            if (card && !processedCards.has(card)) {
                              processedCards.add(card);
                              // Only apply purple card classes if this card doesn't already have Core card classes
                              if (!card.classList.contains('border-blue-200')) {
                                for (const c of FULL_CARD_CLASSES) {
                                  card.classList.add(c);
                                }
                              }
                            }
                          }
                        }
                      }

                      // Ensure disabled/locked checked roles are submitted (disabled inputs don't submit)
                      form.addEventListener('submit', function () {
                        if (roleTypeSelect && roleTypeSelect.value === 'admin') {
                          const adminCheckboxes = adminGroup
                            ? Array.from(adminGroup.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'))
                            : [];
                          const checkedAdminBoxes = adminCheckboxes.filter(function (inp) { return inp.checked; });
                          const hasAdminRole = checkedAdminBoxes.length > 0;

                          let hasApprover = false;
                          if (assignmentGroup) {
                            const aInputs = Array.from(
                              assignmentGroup.querySelectorAll('input[type="checkbox"][name="rbac_roles"]')
                            );
                            for (const inp of aInputs) {
                              const txt = String(getLabelSpanText(inp) || '').trim().toLowerCase();
                              if (txt === 'approver' && inp.checked) { hasApprover = true; }
                            }
                          }

                          if (!hasAdminRole && !hasApprover) {
                            roleTypeSelect.value = 'focal_point';
                          }
                        }

                        const isFocalPointSubmit = roleTypeSelect && roleTypeSelect.value === 'focal_point';

                        // Belt-and-suspenders: hidden admin sections can still submit checked boxes.
                        // Always strip admin (+ approver) roles when saving as Focal Point.
                        if (isFocalPointSubmit) {
                          clearAdminRolesForFocalPoint();
                          ensureMinimumFocalPointAssignmentRoles();
                        }

                        // Clean previous hidden mirrors
                        for (const el of Array.from(form.querySelectorAll('input[type="hidden"][data-implied-rbac="1"]'))) {
                          el.remove();
                        }
                        for (const input of roleInputs) {
                          if (isFocalPointSubmit && adminGroup && adminGroup.contains(input)) {
                            continue;
                          }
                          if (input.disabled && input.checked) {
                            const hidden = document.createElement('input');
                            hidden.type = 'hidden';
                            hidden.name = input.name;
                            hidden.value = input.value;
                            hidden.dataset.impliedRbac = '1';
                            form.appendChild(hidden);
                          }
                        }
                      });

                      function initTranslatorLanguagePanel() {
                        const panel = document.getElementById('translator-languages-panel');
                        if (!panel) return;

                        const roleId = cfg.translatorRoleId;
                        const roleInputs = roleId
                          ? Array.from(document.querySelectorAll('input[type="checkbox"][name="rbac_roles"]'))
                              .filter(function (input) { return String(input.value) === String(roleId); })
                          : Array.from(document.querySelectorAll('.translator-role-checkbox'));

                        function syncPanel() {
                          const roleChecked = roleInputs.some(function (input) { return input.checked; });
                          const langChecked = Array.from(document.querySelectorAll('.translator-language-checkbox'))
                            .some(function (input) { return input.checked; });
                          panel.classList.toggle('hidden', !(roleChecked || langChecked));
                          if (!roleChecked && !READ_ONLY) {
                            document.querySelectorAll('.translator-language-checkbox').forEach(function (input) {
                              if (!input.disabled) input.checked = false;
                            });
                          }
                        }

                        roleInputs.forEach(function (input) {
                          input.addEventListener('change', syncPanel);
                        });
                        syncPanel();
                      }

                      applyRoleHighlights();
                      // After helpers exist: if Focal Point is selected (including after a failed
                      // save), strip any leftover checked admin roles that are only hidden in the UI.
                      if (roleTypeSelect && roleTypeSelect.value === 'focal_point') {
                        clearAdminRolesForFocalPoint();
                        ensureMinimumFocalPointAssignmentRoles();
                      }
                      recomputeLocks();
                      initTranslatorLanguagePanel();
                    })();

    // --- Block 2 (original lines 1906-2060) ---
(function() {
    if (window.__userFormActionHandlersBound) return;
    window.__userFormActionHandlersBound = true;

    const archiveBtn = document.getElementById('archiveUserBtn');
    const archiveForm = document.getElementById('archiveUserForm');
    const deleteBtn = document.getElementById('deleteUserBtn');
    const deleteForm = document.getElementById('deleteUserForm');
    const deleteModal = document.getElementById('deleteUserModal');
    const cancelBtn = document.getElementById('cancelDeleteUser');
    const confirmBtn = document.getElementById('confirmDeleteUser');
    const backdrop = document.getElementById('deleteUserModalBackdrop');
    const previewContainer = document.getElementById('delete-preview-container');
    const unassignContainer = document.getElementById('unassign-preview-container');
    const userForm = document.getElementById('userForm');
    const userDeletionPreviewUrl = cfg.urls.deletionPreview;

    window.__clientLog && window.__clientLog('[user_form] actions bootstrap', {
        hasArchiveBtn: !!archiveBtn,
        hasArchiveForm: !!archiveForm,
        hasDeleteBtn: !!deleteBtn,
        hasDeleteForm: !!deleteForm,
        hasDeleteModal: !!deleteModal
    });

    // Allow admin to leave Name blank by defaulting it to Email on submit.
    if (userForm) {
        userForm.addEventListener('submit', function() {
            const nameInput = userForm.querySelector('input[name="name"]');
            const emailInput = userForm.querySelector('input[type="hidden"][name="email"]') || userForm.querySelector('input[name="email"]');
            if (!nameInput || nameInput.disabled) return;

            const currentName = (nameInput.value || '').trim();
            const emailValue = (emailInput && emailInput.value ? emailInput.value : '').trim();
            if (!currentName && emailValue) {
                nameInput.value = emailValue;
            }
        });
    }

    if (archiveBtn && archiveForm) {
        archiveBtn.addEventListener('click', function(e) {
            e.preventDefault();
            window.__clientLog && window.__clientLog('[user_form] archive button clicked');
            const isActive = cfg.isActive;
            const msg = isActive
                ? cfg.t.deactivateConfirm
                : cfg.t.reactivateConfirm;

            if (isActive && window.showDangerConfirmation) {
                window.showDangerConfirmation(
                    msg,
                    function() { window.__clientLog && window.__clientLog('[user_form] archive confirmed via danger modal'); archiveForm.submit(); },
                    null,
                    cfg.t.deactivate,
                    cfg.t.cancel,
                    cfg.t.deactivateUser
                );
            } else if (window.showConfirmation) {
                window.showConfirmation(msg, function() {
                    window.__clientLog && window.__clientLog('[user_form] archive confirmed via confirmation modal');
                    archiveForm.submit();
                });
            } else {
                const accepted = confirm(msg);
                window.__clientLog && window.__clientLog('[user_form] archive native confirm result', accepted);
                if (accepted) archiveForm.submit();
            }
        });
    }

    if (deleteBtn && deleteForm && deleteModal && confirmBtn) {
        function closeModal() { deleteModal.classList.add('hidden'); }

        function loadPreview() {
            if (!previewContainer) return;
            if (!userDeletionPreviewUrl) {
                previewContainer.innerHTML = '<div class="text-red-600">' + cfg.t.couldNotLoadPreview + '</div>';
                confirmBtn.disabled = false;
                return;
            }
            previewContainer.innerHTML = '<div>' + cfg.t.loadingText + '</div>';
            if (unassignContainer) unassignContainer.innerHTML = '';
            confirmBtn.disabled = true;

            const doFetch = (window.getFetch && window.getFetch()) || fetch;
            doFetch(userDeletionPreviewUrl)
                .then(function(r) {
                    window.__clientLog && window.__clientLog('[user_form] delete preview status', r.status);
                    if (!r.ok) throw new Error('Preview request failed with status ' + r.status);
                    return r.json();
                })
                .then(function(resp) {
                    window.__clientLog && window.__clientLog('[user_form] delete preview payload', resp);
                    if (!resp.success) {
                        previewContainer.innerHTML = '<div class="text-red-600">' + escapeHtml(resp.error || cfg.t.couldNotLoadPreview) + '</div>';
                        confirmBtn.disabled = false;
                        return;
                    }

                    var del = (resp.preview && resp.preview.will_delete) || {};
                    var unassign = (resp.preview && resp.preview.will_unassign) || {};
                    var listHtml = '<ul class="list-disc pl-5 space-y-1">';
                    var hasItems = false;
                    for (var k in del) {
                        if (del[k] && del[k] > 0) {
                            hasItems = true;
                            listHtml += '<li>' + escapeHtml(String(k).replaceAll('_', ' ')) + ': ' + escapeHtml(String(del[k])) + '</li>';
                        }
                    }
                    if (!hasItems) listHtml += '<li>' + cfg.t.noRelatedDeletions + '</li>';
                    listHtml += '</ul>';
                    previewContainer.innerHTML = listHtml;

                    if (unassignContainer) {
                        var unHtml = '';
                        var hasUnassign = false;
                        for (var u in unassign) {
                            if (unassign[u] && unassign[u] > 0) {
                                hasUnassign = true;
                                unHtml += '<li>' + escapeHtml(String(u).replaceAll('_', ' ')) + ': ' + escapeHtml(String(unassign[u])) + ' ' + cfg.t.willBeUnassigned + '</li>';
                            }
                        }
                        unassignContainer.innerHTML = hasUnassign
                            ? '<div class="font-medium mb-1">' + cfg.t.followingUnassigned + '</div><ul class="list-disc pl-5 space-y-1">' + unHtml + '</ul>'
                            : '';
                    }
                    confirmBtn.disabled = false;
                })
                .catch(function(err) {
                    console.error('[user_form] delete preview failed', err);
                    previewContainer.innerHTML = '<div class="text-red-600">' + cfg.t.failedToLoadPreview + '</div>';
                    confirmBtn.disabled = false;
                });
        }

        deleteBtn.addEventListener('click', function() {
            window.__clientLog && window.__clientLog('[user_form] delete button clicked');
            deleteModal.classList.remove('hidden');
            loadPreview();
        });

        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
        if (backdrop) backdrop.addEventListener('click', closeModal);
        confirmBtn.addEventListener('click', function() {
            window.__clientLog && window.__clientLog('[user_form] delete confirm clicked, submitting form');
            confirmBtn.disabled = true;
            confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>' + cfg.t.deletingText;
            closeModal();
            deleteForm.submit();
        });
    }
})();

    // --- Block 3 (original lines 2146-3147) ---
    document.addEventListener('DOMContentLoaded', function() {
        // Get all "Select All" checkboxes for regions
        const regionSelectAllCheckboxes = document.querySelectorAll('.region-select-all');
        // Get all individual country checkboxes
        const countryCheckboxes = document.querySelectorAll('.country-checkbox');
        // Get the global "Select All" checkbox
        const globalSelectAllCheckbox = document.getElementById('select-all-countries');

        // Function to update the state of a region "Select All" checkbox
        function updateRegionSelectAll(region) {
            const regionSelectAllCheckbox = document.querySelector(`.region-select-all[data-region="${region}"]`);
            const countriesInRegion = document.querySelectorAll(`.region-countries[data-region="${region}"] .country-checkbox`);
            // Check if all countries in the region are checked, but only if there are countries in the region
            const allChecked = countriesInRegion.length > 0 && Array.from(countriesInRegion).every(cb => cb.checked);
            if (regionSelectAllCheckbox) {
                regionSelectAllCheckbox.checked = allChecked;
            }
        }

         // Function to update the state of the global "Select All" checkbox
        function updateGlobalSelectAll() {
            const allCountryCheckboxes = document.querySelectorAll('.country-checkbox');
             // Check if all countries are checked, but only if there are countries
            const allChecked = allCountryCheckboxes.length > 0 && Array.from(allCountryCheckboxes).every(cb => cb.checked);
            if (globalSelectAllCheckbox) {
                globalSelectAllCheckbox.checked = allChecked;
            }
        }

        // Add event listener to the global "Select All" checkbox
        if (globalSelectAllCheckbox) {
            globalSelectAllCheckbox.addEventListener('change', function() {
                const isChecked = this.checked;
                // Set the checked state of all country checkboxes
                countryCheckboxes.forEach(countryCheckbox => {
                    countryCheckbox.checked = isChecked;
                });
                // Update the state of all region "Select All" checkboxes
                regionSelectAllCheckboxes.forEach(regionCheckbox => {
                    regionCheckbox.checked = isChecked;
                });
            });
        }

        // Add event listener to each region "Select All" checkbox
        regionSelectAllCheckboxes.forEach(regionCheckbox => {
            regionCheckbox.addEventListener('change', function() {
                const region = this.dataset.region;
                const isChecked = this.checked;
                // Get all country checkboxes within this region
                const countriesInRegion = document.querySelectorAll(`.region-countries[data-region="${region}"] .country-checkbox`);
                // Set the checked state of country checkboxes based on the region checkbox
                countriesInRegion.forEach(countryCheckbox => {
                    countryCheckbox.checked = isChecked;
                });
                 // After updating countries in the region, update the global select all checkbox
                updateGlobalSelectAll();
            });
        });

        // Add event listener to individual country checkboxes
        countryCheckboxes.forEach(countryCheckbox => {
            countryCheckbox.addEventListener('change', function() {
                // Find the parent region container
                const regionContainer = this.closest('.region-countries');
                if (regionContainer) {
                    const region = regionContainer.dataset.region;
                    // Update the state of the region "Select All" checkbox
                    updateRegionSelectAll(region);
                }
                // Update the state of the global "Select All" checkbox
                updateGlobalSelectAll();
            });
        });

        if (cfg.userId) {
        // --- Initial state setup for edit mode ---
        // For edit mode, we need to set up the initial state based on existing user assignments
        const userAssignedCountryIds = new Set(cfg.userCountryIds || []);

        countryCheckboxes.forEach(countryCheckbox => {
            const countryId = parseInt(countryCheckbox.value);
            // Country checkboxes are already pre-checked via template logic, but ensure consistency
            countryCheckbox.checked = userAssignedCountryIds.has(countryId);
        });
        }

        // Update the state of the global and region "Select All" checkboxes based on initial state
        updateGlobalSelectAll();
        regionSelectAllCheckboxes.forEach(regionCheckbox => {
             const region = regionCheckbox.dataset.region;
             updateRegionSelectAll(region);
        });

        // Main tab switching + URL query sync (?tab=…&entity_tab=…&secretariat_tab=…)
        const underlineTabs = window.AdminUnderlineTabs;
        const USER_FORM_TAB = {
            PARAM_TO_MAIN: {
                details: 'user-details',
                user_details: 'user-details',
                entity: 'entity',
                entity_permissions: 'entity',
                notifications: 'notifications',
                notification_preferences: 'notifications',
                devices: 'devices',
                registered_devices: 'devices',
                analytics: 'analytics'
            },
            MAIN_TO_PARAM: {
                'user-details': 'details',
                entity: 'entity',
                notifications: 'notifications',
                devices: 'devices',
                analytics: 'analytics'
            },
            PARAM_TO_ENTITY: {
                countries: 'countries',
                ns: 'ns-structure',
                ns_structure: 'ns-structure',
                secretariat: 'secretariat'
            },
            ENTITY_TO_PARAM: {
                countries: 'countries',
                'ns-structure': 'ns_structure',
                secretariat: 'secretariat'
            },
            PARAM_TO_SEC: {
                divisions: 'divisions',
                departments: 'divisions',
                regions: 'regions'
            },
            SEC_TO_PARAM: {
                divisions: 'divisions',
                regions: 'regions'
            }
        };

        const LEGACY_MAIN_TAB_MAP = {
            'user-details-panel': 'user-details',
            'entity-permissions-panel': 'entity',
            'notification-preferences-panel': 'notifications',
            'registered-devices-panel': 'devices',
            'analytics-panel': 'analytics'
        };

        const LEGACY_ENTITY_TAB_MAP = {
            'countries-panel': 'countries',
            'ns-structure-panel': 'ns-structure',
            'secretariat-panel': 'secretariat'
        };

        const LEGACY_SEC_TAB_MAP = {
            'secretariat-divisions-panel': 'divisions',
            'secretariat-regions-panel': 'regions'
        };

        const KNOWN_MAIN_TAB_IDS = [
            'user-details',
            'entity',
            'notifications',
            'devices',
            'analytics'
        ];

        function mainPanelIdForTab(tabId) {
            return 'panel-' + tabId;
        }

        function normalizeMainTabId(raw) {
            if (!raw) return null;
            return LEGACY_MAIN_TAB_MAP[raw] || raw;
        }

        function normalizeEntityTabId(raw) {
            if (!raw) return null;
            return LEGACY_ENTITY_TAB_MAP[raw] || raw;
        }

        function normalizeSecretariatTabId(raw) {
            if (!raw) return null;
            return LEGACY_SEC_TAB_MAP[raw] || raw;
        }

        function getActiveMainTabId() {
            for (let i = 0; i < KNOWN_MAIN_TAB_IDS.length; i++) {
                const tabId = KNOWN_MAIN_TAB_IDS[i];
                const el = document.getElementById(mainPanelIdForTab(tabId));
                if (el && !el.classList.contains('hidden')) return tabId;
            }
            return 'user-details';
        }

        function getActiveEntityTabId() {
            const panels = document.querySelectorAll('.entity-form-panel');
            for (let i = 0; i < panels.length; i++) {
                const p = panels[i];
                if (p && !p.classList.contains('hidden') && p.id && p.id.indexOf('panel-') === 0) {
                    return p.id.slice('panel-'.length);
                }
            }
            return null;
        }

        function getActiveSecretariatTabId() {
            const panels = document.querySelectorAll('.secretariat-form-panel');
            for (let i = 0; i < panels.length; i++) {
                const p = panels[i];
                if (p && !p.classList.contains('hidden') && p.id && p.id.indexOf('panel-secretariat-') === 0) {
                    return p.id.slice('panel-secretariat-'.length);
                }
            }
            return 'divisions';
        }

        function syncUserFormTabUrl() {
            const mainId = getActiveMainTabId();
            const mainKey = USER_FORM_TAB.MAIN_TO_PARAM[mainId] || 'details';
            const params = new URLSearchParams();
            params.set('tab', mainKey);

            if (mainId === 'entity') {
                const eid = getActiveEntityTabId();
                if (eid && USER_FORM_TAB.ENTITY_TO_PARAM[eid]) {
                    params.set('entity_tab', USER_FORM_TAB.ENTITY_TO_PARAM[eid]);
                    if (eid === 'secretariat') {
                        const sid = getActiveSecretariatTabId();
                        if (sid && USER_FORM_TAB.SEC_TO_PARAM[sid]) {
                            params.set('secretariat_tab', USER_FORM_TAB.SEC_TO_PARAM[sid]);
                        }
                    }
                }
            }

            const qs = params.toString();
            const next = window.location.pathname + (qs ? '?' + qs : '') + window.location.hash;
            const cur = window.location.pathname + window.location.search + window.location.hash;
            if (next !== cur) {
                history.replaceState(null, '', next);
            }
        }

        function parseMainTabIdFromUrl() {
            const p = new URLSearchParams(window.location.search);
            const raw = p.get('tab');
            if (raw === null || raw === '') return null;
            const key = String(raw).toLowerCase().replace(/-/g, '_');
            const id = USER_FORM_TAB.PARAM_TO_MAIN[key];
            if (!id || !document.getElementById(mainPanelIdForTab(id))) return null;
            return id;
        }

        function parseEntityTabIdFromUrl() {
            const p = new URLSearchParams(window.location.search);
            const raw = p.get('entity_tab');
            if (raw === null || raw === '') return null;
            const key = String(raw).toLowerCase().replace(/-/g, '_');
            const id = USER_FORM_TAB.PARAM_TO_ENTITY[key];
            if (!id || !document.getElementById('panel-' + id)) return null;
            return id;
        }

        function parseSecretariatTabIdFromUrl() {
            const p = new URLSearchParams(window.location.search);
            const raw = p.get('secretariat_tab');
            if (raw === null || raw === '') return null;
            const key = String(raw).toLowerCase().replace(/-/g, '_');
            const id = USER_FORM_TAB.PARAM_TO_SEC[key];
            if (!id || !document.getElementById('panel-secretariat-' + id)) return null;
            return id;
        }

        function resolveInitialMainTabId() {
            const fromUrl = parseMainTabIdFromUrl();
            if (fromUrl) return fromUrl;
            try {
                const ls = normalizeMainTabId(localStorage.getItem('selectedMainTab'));
                if (ls && document.getElementById(mainPanelIdForTab(ls))) return ls;
            } catch (e) { /* ignore */ }
            return 'user-details';
        }

        // Main tab switching functionality
        const mainTabButtons = document.querySelectorAll('#main-tabs .settings-tab');

        function activateMainTab(tabId, options) {
            options = options || {};
            tabId = normalizeMainTabId(tabId) || 'user-details';

            if (underlineTabs) {
                underlineTabs.activateStripTab('#main-tabs', tabId, {
                    panelSelector: '.user-form-panel',
                    panelIdPrefix: 'panel-'
                });
            } else {
                document.querySelectorAll('.user-form-panel').forEach(function (panel) {
                    panel.classList.toggle('hidden', panel.id !== mainPanelIdForTab(tabId));
                });
            }

            const targetPanel = document.getElementById(mainPanelIdForTab(tabId));
            if (targetPanel) {
                const hasHidden = targetPanel.classList.contains('hidden');
                const computedDisplay = window.getComputedStyle(targetPanel).display;
                if (hasHidden || computedDisplay === 'none') {
                    targetPanel.classList.remove('hidden');
                    if (computedDisplay === 'none') {
                        targetPanel.style.display = 'block';
                    }
                }
            }

            try {
                localStorage.setItem('selectedMainTab', tabId);
            } catch (e) { /* ignore */ }

            if (!options.skipUrl) {
                syncUserFormTabUrl();
            }
        }

        mainTabButtons.forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                const tabId = this.getAttribute('data-tab');
                if (tabId) activateMainTab(tabId);
            });
        });

        // Initial main tab: URL query > localStorage > User Details
        activateMainTab(resolveInitialMainTabId(), { skipUrl: true });

        // Lazy-load Analytics tab content on first activation
        (function() {
            var analyticsTab = document.getElementById('analytics-tab');
            var analyticsPanel = document.getElementById('panel-analytics');
            if (!analyticsTab || !analyticsPanel) return;

            var analyticsUrl = analyticsPanel.dataset.analyticsUrl;
            var loaded = false;

            function fetchAnalytics(days) {
                var url = analyticsUrl;
                if (days) {
                    url = url.replace(/([?&])days=\d+/, '$1days=' + days);
                    if (url === analyticsUrl) {
                        url += (url.indexOf('?') !== -1 ? '&' : '?') + 'days=' + days;
                    }
                }
                analyticsPanel.innerHTML = '<div class="rounded-lg border border-dashed border-gray-300 bg-gray-50 flex flex-col items-center justify-center py-14 px-4"><i class="fas fa-spinner fa-spin text-blue-600 text-2xl mb-3"></i><span class="text-sm text-gray-600">' + cfg.t.loadingAnalytics + '</span></div>';
                var fetchFn = (window.getFetch && window.getFetch()) || fetch;
                fetchFn(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
                    .then(function(r) {
                        // Redirect means the session expired and Flask-Login returned the login page.
                        if (r.redirected || !r.ok) {
                            var err = new Error(r.redirected ? 'session_expired' : 'http_error');
                            err.status = r.status;
                            throw err;
                        }
                        return r.text();
                    })
                    .then(function(html) { analyticsPanel.innerHTML = window.SafeDom.sanitizeHtml(html); })
                    .catch(function(err) {
                        if (err && err.message === 'session_expired') {
                            analyticsPanel.innerHTML = [
                                '<div class="rounded-lg border border-yellow-200 bg-yellow-50 text-center py-10 px-4">',
                                  '<i class="fas fa-lock text-yellow-500 text-2xl mb-3"></i>',
                                  '<p class="text-sm font-semibold text-yellow-800 mb-1">' + cfg.t.sessionExpired + '</p>',
                                  '<p class="text-xs text-yellow-700 mb-4">' + cfg.t.pleaseLogIn + '</p>',
                                  '<a href="' + cfg.urls.loginUrl + '" target="_blank" rel="noopener"',
                                  '   class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-yellow-600 text-white rounded hover:bg-yellow-700 transition-colors">',
                                  '  <i class="fas fa-sign-in-alt"></i> ' + cfg.t.logIn,
                                  '</a>',
                                '</div>'
                            ].join('');
                        } else {
                            analyticsPanel.innerHTML = '<div class="rounded-lg border border-red-200 bg-red-50 text-center py-10 px-4"><i class="fas fa-exclamation-circle text-red-500 text-2xl mb-2"></i><p class="text-sm text-red-800">' + cfg.t.failedToLoadAnalytics + '</p></div>';
                        }
                    });
            }

            analyticsTab.addEventListener('click', function() {
                if (loaded) return;
                loaded = true;
                fetchAnalytics();
            });

            analyticsPanel.addEventListener('click', function(ev) {
                var btn = ev.target.closest('[data-analytics-days]');
                if (!btn || !analyticsPanel.contains(btn)) return;
                var days = parseInt(btn.getAttribute('data-analytics-days'), 10);
                if (!isFinite(days) || days <= 0) return;
                ev.preventDefault();
                fetchAnalytics(days);
            });

            window.ensureUserFormAnalyticsLoaded = function() {
                if (loaded) return;
                loaded = true;
                fetchAnalytics();
            };
        })();

        // Initialize entity sub-tab switching functionality (within Entity Permissions tab)
        const entityTabButtons = document.querySelectorAll('#entity-tabs .tab-button');

        function activateEntityTab(tabId, options) {
            options = options || {};
            tabId = normalizeEntityTabId(tabId);
            if (!tabId) return;

            if (underlineTabs) {
                entityTabButtons.forEach(function (btn) {
                    var isActive = btn.getAttribute('data-tab') === tabId;
                    underlineTabs.setSubTabButton(btn, isActive);
                    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
                });
                document.querySelectorAll('.entity-form-panel').forEach(function (panel) {
                    panel.classList.toggle('hidden', panel.id !== 'panel-' + tabId);
                });
            }

            try {
                localStorage.setItem('selectedEntityTab', tabId);
            } catch (e) { /* ignore */ }

            if (!options.skipUrl) {
                syncUserFormTabUrl();
            }
        }

        entityTabButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                const tabId = this.getAttribute('data-tab');
                if (tabId) activateEntityTab(tabId);
            });
        });

        function getDefaultEntityTab() {
            const firstTabButton = document.querySelector('#entity-tabs .tab-button');
            if (firstTabButton) {
                return firstTabButton.getAttribute('data-tab');
            }
            return null;
        }

        // Entity sub-tab: URL entity_tab > localStorage > first tab
        (function initEntitySubTab() {
            if (!document.getElementById('entity-tabs-content')) return;
            let tabId = parseEntityTabIdFromUrl();
            if (!tabId) {
                try {
                    const ls = normalizeEntityTabId(localStorage.getItem('selectedEntityTab'));
                    if (ls && document.getElementById('panel-' + ls)) tabId = ls;
                } catch (e) { /* ignore */ }
            }
            if (!tabId) tabId = getDefaultEntityTab();
            if (tabId) activateEntityTab(tabId, { skipUrl: true });
        })();

        // ---------------------------------------------------------------------
        // Freeze hierarchy columns (NS Structure and Secretariat tabs)
        // Distribute top-level items into fixed columns once, based on initial
        // viewport width, and never reshuffle columns on expansion.
        // ---------------------------------------------------------------------
        function computeInitialColumnCount() {
            const w = window.innerWidth || document.documentElement.clientWidth || 0;
            if (w >= 1280) return 5; // xl
            if (w >= 1024) return 4; // lg
            if (w >= 768) return 3;  // md
            if (w >= 640) return 2;  // sm
            return 1;
        }

        function freezeHierarchyColumns(container) {
            if (!container) return;
            // Avoid re-freezing if grid already exists
            if (container.querySelector(':scope > .fc-grid')) return;

            const topLevelUl = container.querySelector(':scope > ul');
            if (!topLevelUl) return;
            const items = Array.from(topLevelUl.children).filter(node => node && node.nodeName === 'LI');
            if (items.length === 0) return;

            const colCount = computeInitialColumnCount();
            const grid = document.createElement('div');
            grid.className = 'fc-grid';
            grid.style.setProperty('--fc-col-count', String(colCount));

            const columns = [];
            for (let i = 0; i < colCount; i++) {
                const colUl = document.createElement('ul');
                colUl.className = 'fc-col';
                columns.push(colUl);
                grid.appendChild(colUl);
            }

            items.forEach((li, index) => {
                const targetCol = columns[index % colCount];
                targetCol.appendChild(li);
            });

            // Remove original UL and attach the frozen grid
            topLevelUl.remove();
            container.appendChild(grid);
        }

        function initFixedColumnsObserver(containerId) {
            const container = document.getElementById(containerId);
            if (!container) return;

            // Try immediately if content already present
            freezeHierarchyColumns(container);

            // Observe for first-time hierarchy load/reload
            const observer = new MutationObserver(() => {
                // If a direct UL appears and we haven't frozen yet, freeze now
                const hasGrid = !!container.querySelector(':scope > .fc-grid');
                const hasTopUl = !!container.querySelector(':scope > ul');
                if (!hasGrid && hasTopUl) {
                    freezeHierarchyColumns(container);
                }
            });
            observer.observe(container, { childList: true });
        }

        // Attach to all hierarchical containers
        initFixedColumnsObserver('ns-structure-hierarchy-container');
        initFixedColumnsObserver('secretariat-divisions-container');
        initFixedColumnsObserver('secretariat-regions-container');

        // Hierarchical entity selectors — deferred until Entity Permissions tab is first opened
        // so hierarchy/entity fetches are not paid on every user-form page load.
        let nsStructureSelector = null;
        let secretariatDivisionsSelector = null;
        let secretariatRegionsSelector = null;
        let entityPermissionsLoaded = false;

        function initEntityPermissionsTab() {
            if (entityPermissionsLoaded) return;
            entityPermissionsLoaded = true;

            // Initialize NS Structure hierarchical selector
            if (document.getElementById('ns-structure-hierarchy-container')) {
                nsStructureSelector = new HierarchicalEntitySelector({
                    containerId: 'ns-structure-hierarchy-container',
                    apiBaseUrl: '', // Empty since blueprint already has /admin prefix
                    targetUserId: cfg.userId,
                    entityTypes: ['ns_branch', 'ns_subbranch', 'ns_localunit'],
                    onChange: function(data) {
                        // Just update hidden form fields - no need to reload from server
                        // Changes will be saved when form is submitted
                    }
                });

                // Country select wiring for NS Structure
                const nsCountrySelect = document.getElementById('ns-country-select');
                const nsContainer = document.getElementById('ns-structure-hierarchy-container');
                function loadNsForCountry(countryId) {
                    if (!countryId) {
                        nsContainer.innerHTML = `
                        <div class="text-center py-4">
                            <i class="fas fa-info-circle text-gray-400"></i>
                            <p class="text-sm text-gray-500 mt-2">Select a country to view NS structure.</p>
                        </div>`;
                        return;
                    }
                    nsContainer.innerHTML = `
                    <div class=\"text-center py-4\">\n                        <i class=\"fas fa-spinner fa-spin text-gray-400\"></i>\n                        <p class=\"text-sm text-gray-500 mt-2\">Loading NS structure...</p>\n                    </div>`;
                    nsStructureSelector.loadHierarchy(`/admin/structure/ns-hierarchy?country_id=${countryId}`);
                }
                if (nsCountrySelect) {
                    nsCountrySelect.addEventListener('change', function() {
                        loadNsForCountry(this.value);
                    });
                    // If editing a user and they have countries, preselect the first
                    const defaultCountryId = cfg.defaultCountryId;
                    if (defaultCountryId) {
                        nsCountrySelect.value = String(defaultCountryId);
                        loadNsForCountry(defaultCountryId);
                    }
                }

                // Add search functionality
                const nsSearchInput = document.getElementById('ns-structure-search');
                if (nsSearchInput) {
                    let searchTimeout;
                    nsSearchInput.addEventListener('input', (e) => {
                        clearTimeout(searchTimeout);
                        searchTimeout = setTimeout(() => {
                            nsStructureSelector.filterHierarchy(e.target.value);
                        }, 300);
                    });
                }
            }
            if (cfg.userId) {
                // Initialize Secretariat Divisions & Departments selector
                if (document.getElementById('secretariat-divisions-container')) {
                    secretariatDivisionsSelector = new HierarchicalEntitySelector({
                        containerId: 'secretariat-divisions-container',
                        apiBaseUrl: '',
                        targetUserId: cfg.userId,
                        entityTypes: ['division', 'department'],
                        onChange: function(data) {}
                    });

                    secretariatDivisionsSelector.loadHierarchy('/admin/structure/secretariat-hierarchy');

                    const secretariatDivisionsSearchInput = document.getElementById('secretariat-divisions-search');
                    if (secretariatDivisionsSearchInput) {
                        let searchTimeout;
                        secretariatDivisionsSearchInput.addEventListener('input', (e) => {
                            clearTimeout(searchTimeout);
                            searchTimeout = setTimeout(() => {
                                secretariatDivisionsSelector.filterHierarchy(e.target.value);
                            }, 300);
                        });
                    }
                }

                // Initialize Secretariat Regions selector
                if (document.getElementById('secretariat-regions-container')) {
                    secretariatRegionsSelector = new HierarchicalEntitySelector({
                        containerId: 'secretariat-regions-container',
                        apiBaseUrl: '',
                        targetUserId: cfg.userId,
                        entityTypes: ['regional_office', 'cluster_office'],
                        onChange: function(data) {}
                    });

                    secretariatRegionsSelector.loadHierarchy('/admin/structure/secretariat-regions-hierarchy');

                    const secretariatRegionsSearchInput = document.getElementById('secretariat-regions-search');
                    if (secretariatRegionsSearchInput) {
                        let searchTimeout;
                        secretariatRegionsSearchInput.addEventListener('input', (e) => {
                            clearTimeout(searchTimeout);
                            searchTimeout = setTimeout(() => {
                                secretariatRegionsSelector.filterHierarchy(e.target.value);
                            }, 300);
                        });
                    }
                }

                // Store selectors globally for debugging
                window.nsStructureSelector = nsStructureSelector;
                window.secretariatDivisionsSelector = secretariatDivisionsSelector;
                window.secretariatRegionsSelector = secretariatRegionsSelector;
            }
        }

        const entityPermissionsTabBtn = document.getElementById('entity-permissions-tab');
        if (entityPermissionsTabBtn) {
            entityPermissionsTabBtn.addEventListener('click', initEntityPermissionsTab);
        }
        // If Entity Permissions is the initial active tab (URL/localStorage), load immediately.
        if (resolveInitialMainTabId() === 'entity') {
            initEntityPermissionsTab();
        }

        // Secretariat sub-tabs behavior
        const secretariatSubtabButtons = document.querySelectorAll('#secretariat-subtabs .tab-button');
        function activateSecretariatSubtab(tabId, options) {
            options = options || {};
            tabId = normalizeSecretariatTabId(tabId) || 'divisions';

            if (underlineTabs) {
                secretariatSubtabButtons.forEach(function (btn) {
                    var isActive = btn.getAttribute('data-tab') === tabId;
                    underlineTabs.setSubTabButton(btn, isActive);
                    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
                });
                document.querySelectorAll('.secretariat-form-panel').forEach(function (panel) {
                    panel.classList.toggle('hidden', panel.id !== 'panel-secretariat-' + tabId);
                });
            }

            try {
                localStorage.setItem('selectedSecretariatSubtab', tabId);
            } catch (e) { /* ignore */ }

            if (!options.skipUrl) {
                syncUserFormTabUrl();
            }
        }
        secretariatSubtabButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                const tabId = this.getAttribute('data-tab');
                if (tabId) activateSecretariatSubtab(tabId);
            });
        });
        (function initSecretariatSubTab() {
            if (!document.getElementById('secretariat-subtabs')) return;
            let sid = parseSecretariatTabIdFromUrl();
            if (!sid) {
                try {
                    const ls = normalizeSecretariatTabId(localStorage.getItem('selectedSecretariatSubtab'));
                    if (ls && document.getElementById('panel-secretariat-' + ls)) sid = ls;
                } catch (e) { /* ignore */ }
            }
            if (!sid) sid = 'divisions';
            if (document.getElementById('panel-secretariat-' + sid)) {
                activateSecretariatSubtab(sid, { skipUrl: true });
            } else {
                activateSecretariatSubtab('divisions', { skipUrl: true });
            }
        })();

        // Normalize / persist tab state in the address bar (bookmarkable / refresh-safe)
        syncUserFormTabUrl();

        if (typeof window.ensureUserFormAnalyticsLoaded === 'function') {
            var ap = document.getElementById('panel-analytics');
            if (ap && !ap.classList.contains('hidden')) {
                window.ensureUserFormAnalyticsLoaded();
            }
        }

        // Notification preferences select all functionality
        const selectAllEmailAdmin = document.getElementById('select-all-email-admin');
        const selectAllPushAdmin = document.getElementById('select-all-push-admin');
        const emailCheckboxesAdmin = document.querySelectorAll('.notification-type-email-admin');
        const pushCheckboxesAdmin = document.querySelectorAll('.notification-type-push-admin');

        if (selectAllEmailAdmin) {
            selectAllEmailAdmin.addEventListener('change', function() {
                emailCheckboxesAdmin.forEach(cb => cb.checked = this.checked);
            });

            // Update select all state when individual checkboxes change
            emailCheckboxesAdmin.forEach(cb => {
                cb.addEventListener('change', function() {
                    const allChecked = Array.from(emailCheckboxesAdmin).every(c => c.checked);
                    selectAllEmailAdmin.checked = allChecked;
                });
            });

            // Set initial state
            const allEmailChecked = emailCheckboxesAdmin.length > 0 && Array.from(emailCheckboxesAdmin).every(c => c.checked);
            selectAllEmailAdmin.checked = allEmailChecked;
        }

        if (selectAllPushAdmin) {
            selectAllPushAdmin.addEventListener('change', function() {
                pushCheckboxesAdmin.forEach(cb => cb.checked = this.checked);
            });

            // Update select all state when individual checkboxes change
            pushCheckboxesAdmin.forEach(cb => {
                cb.addEventListener('change', function() {
                    const allChecked = Array.from(pushCheckboxesAdmin).every(c => c.checked);
                    selectAllPushAdmin.checked = allChecked;
                });
            });

            // Set initial state
            const allPushChecked = pushCheckboxesAdmin.length > 0 && Array.from(pushCheckboxesAdmin).every(c => c.checked);
            selectAllPushAdmin.checked = allPushChecked;
        }

        // Digest schedule toggle for admin form
        const notificationFrequencyAdmin = document.getElementById('notification_frequency');
        const digestScheduleGroupAdmin = document.getElementById('digest-schedule-group-admin');
        const digestDayGroupAdmin = document.getElementById('digest-day-group-admin');

        function toggleDigestScheduleAdmin(frequency) {
            if (frequency === 'daily' || frequency === 'weekly') {
                if (digestScheduleGroupAdmin) digestScheduleGroupAdmin.style.display = 'grid';
                if (digestDayGroupAdmin) {
                    digestDayGroupAdmin.style.display = frequency === 'weekly' ? 'block' : 'none';
                }
            } else {
                if (digestScheduleGroupAdmin) digestScheduleGroupAdmin.style.display = 'none';
            }
        }

        if (notificationFrequencyAdmin) {
            // Set initial state
            toggleDigestScheduleAdmin(notificationFrequencyAdmin.value);

            // Handle changes
            notificationFrequencyAdmin.addEventListener('change', function() {
                toggleDigestScheduleAdmin(this.value);
            });
        }

        // Convert all device timestamps to viewer's local timezone using DateTimeUtils
        // DateTimeUtils is loaded from datetime-utils.js and handles timezone conversion automatically
        document.querySelectorAll('.device-created-date').forEach(element => {
            DateTimeUtils.convertElement(element, 'dateISO');
        });

        document.querySelectorAll('.device-created-time').forEach(element => {
            DateTimeUtils.convertElement(element, 'timeFull');
        });

        document.querySelectorAll('.device-last-active-date').forEach(element => {
            DateTimeUtils.convertElement(element, 'dateISO');
        });

        document.querySelectorAll('.device-last-active-time').forEach(element => {
            DateTimeUtils.convertElement(element, 'timeFull');
        });

        document.querySelectorAll('.device-logged-out-date').forEach(element => {
            DateTimeUtils.convertElement(element, 'datetime');
        });

        // Device kickout functionality
        document.querySelectorAll('.kickout-device-btn').forEach(button => {
            button.addEventListener('click', async function() {
                const deviceId = this.getAttribute('data-device-id');
                const userId = this.getAttribute('data-user-id');

                if (!deviceId || !userId) {
                    if (window.showAlert) window.showAlert('Error: Missing device or user information.', 'error');
                    else window.__clientWarn && window.__clientWarn('Missing device or user information');
                    return;
                }

                const kickMsg = 'Are you sure you want to end this device\'s session? The user will be logged out on this device, but the device will remain registered.';
                const kickBtn = this;
                async function doKickout() {
                // Disable button and show loading state
                const originalContent = kickBtn.innerHTML;
                kickBtn.disabled = true;
                kickBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1.5"></i>Kicking Out...';

                try {
                    const _apiFetch = (window.getFetch && window.getFetch()) || fetch;
                    const response = await _apiFetch(`/admin/users/${userId}/devices/${deviceId}/kickout`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        credentials: 'same-origin'
                    });

                    const data = await response.json();

                    if (response.ok && data.success) {
                        // Find the row containing this button
                        const row = kickBtn.closest('tr');

                        // Update status cell
                        const statusCell = row.querySelector('td:nth-last-child(2)');
                        if (statusCell) {
                            const now = new Date();
                            const formattedDate = DateTimeUtils.format(now, 'datetime');

                            statusCell.innerHTML = (
                                (window.StatusLabels
                                    ? window.StatusLabels.render('Logged Out', 'danger')
                                    : '<span class="status-label status-label--danger">Logged Out</span>') +
                                `<div class="text-xs text-gray-500 mt-1">${formattedDate}</div>`
                            );
                        }

                        // Update actions cell - remove kickout button, keep remove button
                        const actionsCell = row.querySelector('td:last-child');
                        if (actionsCell) {
                            const removeBtn = actionsCell.querySelector('.remove-device-btn');
                            if (removeBtn) {
                                actionsCell.innerHTML = `
                                    <div class="flex items-center space-x-2">
                                        <button type="button"
                                                class="remove-device-btn inline-flex items-center px-3 py-1.5 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                                data-device-id="${deviceId}"
                                                data-user-id="${userId}"
                                                title="Remove this device from registry">
                                            <i class="fas fa-trash mr-1.5"></i>
                                            Remove
                                        </button>
                                    </div>
                                `;
                                // Re-attach event listener to the new remove button
                                attachRemoveDeviceListener(actionsCell.querySelector('.remove-device-btn'));
                            }
                        }

                        // Muted row background for logged-out state (avoid opacity-60 on tr — it greys out action buttons)
                        row.classList.remove('hover:bg-gray-50');
                        row.classList.add('bg-gray-50', 'hover:bg-gray-100');

                        if (typeof window.showFlashMessage === 'function') {
                            window.showFlashMessage('Device session ended successfully.', 'success');
                        }
                    } else {
                        throw new Error(data.error || 'Failed to kick out device');
                    }
                } catch (error) {
                    console.error('Error kicking out device:', error);

                    // Re-enable button
                    kickBtn.disabled = false;
                    kickBtn.innerHTML = originalContent;

                    // Show error message
                    var m = 'Error: ' + (error.message || 'Failed to end device session. Please try again.');
                    if (window.showAlert) window.showAlert(m, 'error');
                    else console.error(m);
                }
                }
                if (window.showConfirmation) {
                    window.showConfirmation(kickMsg, doKickout, null, 'End Session', 'Cancel', 'End Device Session?');
                } else {
                    doKickout();
                }
            });
        });

        // Helper function to attach remove device listener
        function attachRemoveDeviceListener(button) {
            if (!button) return;

            button.addEventListener('click', async function() {
                const deviceId = this.getAttribute('data-device-id');
                const userId = this.getAttribute('data-user-id');

                if (!deviceId || !userId) {
                    if (window.showAlert) window.showAlert('Error: Missing device or user information.', 'error');
                    else window.__clientWarn && window.__clientWarn('Missing device or user information');
                    return;
                }

                const removeMsg = 'Are you sure you want to remove this device from the registry? This will permanently delete the device record and the user will need to register again to receive push notifications on this device.';
                const removeBtn = this;
                async function doRemove() {
                // Disable button and show loading state
                const originalContent = removeBtn.innerHTML;
                removeBtn.disabled = true;
                removeBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1.5"></i>Removing...';

                try {
                    const _apiFetch = (window.getFetch && window.getFetch()) || fetch;
                    const response = await _apiFetch(`/admin/users/${userId}/devices/${deviceId}/remove`, {
                        method: 'DELETE',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        credentials: 'same-origin'
                    });

                    const data = await response.json();

                    if (response.ok && data.success) {
                        // Find the row containing this button
                        const row = removeBtn.closest('tr');

                        // Remove the entire row with animation
                        row.style.transition = 'opacity 0.3s ease-out';
                        row.style.opacity = '0';

                        setTimeout(() => {
                            row.remove();

                            // Check if table is now empty
                            const tbody = document.querySelector('#panel-devices tbody');
                            if (tbody && tbody.children.length === 0) {
                                // Reload page to show empty state
                                location.reload();
                            }
                        }, 300);

                        if (typeof window.showFlashMessage === 'function') {
                            window.showFlashMessage('Device removed successfully.', 'success');
                        }
                    } else {
                        throw new Error(data.error || 'Failed to remove device');
                    }
                } catch (error) {
                    console.error('Error removing device:', error);

                    // Re-enable button
                    removeBtn.disabled = false;
                    removeBtn.innerHTML = originalContent;

                    // Show error message
                    var m = 'Error: ' + (error.message || 'Failed to remove device. Please try again.');
                    if (window.showAlert) window.showAlert(m, 'error');
                    else console.error(m);
                }
                }
                if (window.showDangerConfirmation) {
                    window.showDangerConfirmation(removeMsg, doRemove, null, 'Remove', 'Cancel', 'Remove Device?');
                } else if (window.showConfirmation) {
                    window.showConfirmation(removeMsg, doRemove, null, 'Remove', 'Cancel', 'Remove Device?');
                } else {
                    doRemove();
                }
            });
        }

        // Device remove functionality
        document.querySelectorAll('.remove-device-btn').forEach(button => {
            attachRemoveDeviceListener(button);
        });
    });

    // --- Block 4 (original lines 3182-3253) ---
(function () {
    var modal   = document.getElementById('user-profile-color-modal');
    var openBtn = document.getElementById('user-profile-color-open');
    var hidden  = document.getElementById('user_profile_color_input');
    var preview = document.getElementById('user-profile-color-preview');
    var nameInput = document.getElementById('user_form_name');
    if (!modal || !openBtn || !hidden || !preview) return;

    function initialsFromName(name) {
        name = (name || '').trim();
        if (!name) return '?';
        var parts = name.split(/\s+/).filter(Boolean);
        if (parts.length >= 2) {
            return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase().slice(0, 2);
        }
        return name.slice(0, 2).toUpperCase();
    }

    function syncPreview() {
        var v = (hidden.value || '#3B82F6').trim();
        preview.style.backgroundColor = v;
        modal.querySelectorAll('.user-profile-color-swatch').forEach(function (btn) {
            var active = (btn.getAttribute('data-hex') || '').toLowerCase() === v.toLowerCase();
            btn.classList.toggle('is-selected', active);
        });
    }

    function openModal() {
        modal.style.display = 'flex';
        openBtn.setAttribute('aria-expanded', 'true');
        syncPreview();
        var sel = modal.querySelector('.user-profile-color-swatch.is-selected') ||
                  modal.querySelector('.user-profile-color-swatch');
        if (sel) sel.focus();
    }

    function closeModal() {
        modal.style.display = 'none';
        openBtn.setAttribute('aria-expanded', 'false');
        openBtn.focus();
    }

    openBtn.addEventListener('click', openModal);

    modal.querySelectorAll('[data-user-profile-color-dismiss="1"]').forEach(function (el) {
        el.addEventListener('click', closeModal);
    });

    modal.querySelectorAll('.user-profile-color-swatch').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var hex = (btn.getAttribute('data-hex') || '').trim();
            if (!hex) return;
            hidden.value = hex;
            syncPreview();
            closeModal();
        });
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.style.display !== 'none') closeModal();
    });

    if (nameInput) {
        nameInput.addEventListener('input', function () {
            preview.textContent = initialsFromName(nameInput.value);
        });
    }

    syncPreview();
})();

}());