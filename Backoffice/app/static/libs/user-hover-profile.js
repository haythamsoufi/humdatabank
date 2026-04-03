/**
 * User Hover Profile — centralized
 * Any element with class .ag-user-hover-trigger (tables, dashboard, etc.) shows
 * a user profile popup on hover/click. Configure via window.UserHoverProfileConfig.
 */
(function() {
    'use strict';

    var HOVER_DELAY_MS = 180;
    var HIDE_DELAY_MS = 160;
    var profileCacheById = {};
    var profileCacheByEmail = {};
    var activeTrigger = null;
    var popupEl = null;
    var showTimer = null;
    var hideTimer = null;

    function getClosestTrigger(target) {
        if (!target) return null;
        var el = target;
        if (el.nodeType === 3) {
            el = el.parentElement;
        }
        if (!el || !el.closest) return null;
        return el.closest('.ag-user-hover-trigger');
    }

    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function parseBoolean(value, fallback) {
        if (value === true || value === 'true' || value === 1 || value === '1') return true;
        if (value === false || value === 'false' || value === 0 || value === '0') return false;
        return fallback;
    }

    function toNumber(value, fallback) {
        var num = Number(value);
        return isFinite(num) ? num : fallback;
    }

    function getPopupElement() {
        if (popupEl) return popupEl;

        popupEl = document.createElement('div');
        popupEl.className = 'ag-user-hover-popup';
        popupEl.setAttribute('role', 'tooltip');

        popupEl.style.cssText = [
            'display: none',
            'position: fixed',
            'z-index: 99999',
            'width: 300px',
            'max-width: calc(100vw - 16px)',
            'background: #ffffff',
            'border: 2px solid #3B82F6',
            'border-radius: 8px',
            'box-shadow: 0 10px 30px rgba(0,0,0,0.25)',
            'padding: 12px',
            'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            'font-size: 13px',
            'color: #111827',
            'pointer-events: auto'
        ].join('; ');

        popupEl.addEventListener('mouseenter', function() {
            clearTimeout(hideTimer);
        });
        popupEl.addEventListener('mouseleave', function() {
            scheduleHide();
        });
        document.body.appendChild(popupEl);
        return popupEl;
    }

    function hidePopup() {
        clearTimeout(showTimer);
        clearTimeout(hideTimer);
        activeTrigger = null;
        if (!popupEl) return;
        popupEl.style.display = 'none';
        popupEl.innerHTML = '';
    }

    function scheduleHide() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(hidePopup, HIDE_DELAY_MS);
    }

    function parseInlineProfile(trigger) {
        var raw = trigger.getAttribute('data-user-inline');
        if (!raw) {
            return {};
        }
        try {
            return JSON.parse(decodeURIComponent(raw));
        } catch (e) {
            return {};
        }
    }

    function normalizeProfile(profile, fallbackEmail) {
        var result = profile || {};
        if (!result.email && fallbackEmail) result.email = fallbackEmail;
        if (result.user_email && !result.email) result.email = result.user_email;
        if (result.user_name && !result.name) result.name = result.user_name;
        if (result.countries_count === undefined && result.country_count !== undefined) {
            result.countries_count = result.country_count;
        }
        if (result.entity_summary === undefined && result.entity_counts && typeof result.entity_counts === 'object') {
            var pieces = [];
            Object.keys(result.entity_counts).forEach(function(key) {
                var value = Number(result.entity_counts[key] || 0);
                if (value > 0) pieces.push(key.replace(/_/g, ' ') + ': ' + value);
            });
            result.entity_summary = pieces.join(', ');
        }
        return result;
    }

    function cacheProfile(profile) {
        if (!profile) return;
        if (profile.id !== null && profile.id !== undefined && profile.id !== '') {
            profileCacheById[String(profile.id)] = profile;
        }
        if (profile.email) {
            profileCacheByEmail[String(profile.email).toLowerCase()] = profile;
        }
    }

    function readCachedProfile(userId, email) {
        if (userId !== null && userId !== undefined && userId !== '') {
            var byId = profileCacheById[String(userId)];
            if (byId) return byId;
        }
        if (email) {
            var byEmail = profileCacheByEmail[String(email).toLowerCase()];
            if (byEmail) return byEmail;
        }
        return null;
    }

    function fetchProfileSummary(userId, email) {
        var queryParts = [];
        if (userId !== null && userId !== undefined && userId !== '') {
            queryParts.push('user_ids=' + encodeURIComponent(String(userId)));
        }
        if (email) {
            queryParts.push('emails=' + encodeURIComponent(String(email)));
        }
        if (!queryParts.length) return Promise.resolve(null);

        var config = window.UserHoverProfileConfig || window.AgGridUserHoverProfileConfig || {};
        var configuredBase = config.profileSummaryUrl;
        var defaultBase = window.location.pathname.indexOf('/admin') === 0
            ? '/admin/api/users/profile-summary'
            : '/api/users/profile-summary';
        var url = (configuredBase || defaultBase) + '?' + queryParts.join('&');

        return fetch(url, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' }
        })
            .then(function(resp) {
                if (!resp.ok) return null;
                return resp.json();
            })
            .then(function(payload) {
                if (!payload) return null;
                var profiles = payload.profiles || (payload.data && payload.data.profiles) || [];
                if (!Array.isArray(profiles) || !profiles.length) return null;
                var profile = normalizeProfile(profiles[0], email);
                cacheProfile(profile);
                return profile;
            })
            .catch(function(err) {
                console.error('[UserHoverProfile] Fetch error:', err);
                return null;
            });
    }

    function formatPresenceDate(isoString) {
        if (!isoString) return null;
        try {
            var d = new Date(isoString);
            if (isNaN(d.getTime())) return null;
            var now = new Date();
            var diffMs = now - d;
            var diffMins = Math.floor(diffMs / 60000);
            var diffHours = Math.floor(diffMs / 3600000);
            var diffDays = Math.floor(diffMs / 86400000);

            var relative;
            if (diffMins < 1) relative = 'Just now';
            else if (diffMins < 60) relative = diffMins + 'm ago';
            else if (diffHours < 24) relative = diffHours + 'h ago';
            else if (diffDays < 7) relative = diffDays + 'd ago';
            else if (diffDays < 30) relative = Math.floor(diffDays / 7) + 'w ago';
            else relative = d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });

            var full = d.toLocaleString(undefined, {
                day: 'numeric', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });
            return { relative: relative, full: full, isRecent: diffMins < 15 };
        } catch (e) {
            return null;
        }
    }

    function normalizeRoleToken(roleValue) {
        return String(roleValue || '')
            .toLowerCase()
            .replace(/[\s\-]+/g, '_')
            .trim();
    }

    function resolveRoleTheme(roles) {
        var roleList = Array.isArray(roles) ? roles : [];
        var normalized = roleList.map(normalizeRoleToken);
        var hasSystemManager = normalized.some(function(role) {
            return role.indexOf('system_manager') !== -1;
        });
        var hasAdmin = normalized.some(function(role) {
            return role.indexOf('admin') !== -1;
        });
        var hasFocalPoint = normalized.some(function(role) {
            return role.indexOf('focal_point') !== -1;
        });
        var hasAssignmentRole = normalized.some(function(role) {
            return role.indexOf('assignment_') !== -1;
        });

        if (hasSystemManager) {
            return {
                key: 'system_manager',
                label: 'System Manager',
                labelColor: '#4c1d95',
                badgeBackground: '#ede9fe',
                badgeColor: '#5b21b6',
                popupBackground: 'linear-gradient(180deg, #faf5ff 0%, #ffffff 55%)',
                popupBorder: '#7c3aed',
                popupShadow: '0 14px 34px rgba(76,29,149,0.35)'
            };
        }
        if (hasAdmin) {
            return {
                key: 'admin',
                label: 'Administrator',
                labelColor: '#92400e',
                badgeBackground: '#fef3c7',
                badgeColor: '#b45309',
                popupBackground: '#fffaf0',
                popupBorder: '#f59e0b',
                popupShadow: '0 12px 28px rgba(180,83,9,0.24)'
            };
        }
        if (hasFocalPoint || hasAssignmentRole) {
            return {
                key: 'focal_point',
                label: 'Focal Point',
                labelColor: '#1e3a8a',
                badgeBackground: '#dbeafe',
                badgeColor: '#1d4ed8',
                popupBackground: '#ffffff',
                popupBorder: '#3B82F6',
                popupShadow: '0 10px 30px rgba(0,0,0,0.25)'
            };
        }
        return {
            key: 'default',
            label: 'User',
            labelColor: '#374151',
            badgeBackground: '#f3f4f6',
            badgeColor: '#4b5563',
            popupBackground: '#ffffff',
            popupBorder: '#9ca3af',
            popupShadow: '0 10px 30px rgba(0,0,0,0.22)'
        };
    }

    function applyPopupTheme(theme) {
        if (!popupEl || !theme) return;
        popupEl.style.background = theme.popupBackground || '#ffffff';
        popupEl.style.border = '2px solid ' + (theme.popupBorder || '#3B82F6');
        popupEl.style.boxShadow = theme.popupShadow || '0 10px 30px rgba(0,0,0,0.25)';
    }

    function getUserDetailUrl(profile) {
        var config = window.UserHoverProfileConfig || {};
        var pattern = config.userDetailUrlPattern;
        if (!pattern) return null;
        var userId = profile && profile.id;
        if (userId === null || userId === undefined || userId === '') return null;
        return pattern.replace('{id}', encodeURIComponent(String(userId)));
    }

    function buildPopupHtml(profile) {
        var displayName = profile.name || profile.email || 'Unknown user';
        var email = profile.email || '';
        var title = profile.title || '';
        var profileColor = profile.profile_color || '#3B82F6';
        var initials = displayName.split(' ').map(function(part) {
            return part ? part.charAt(0) : '';
        }).join('').toUpperCase().slice(0, 2) || 'U';
        var roles = Array.isArray(profile.rbac_roles) ? profile.rbac_roles : [];
        var countriesCount = toNumber(profile.countries_count, 0);
        var entitySummary = profile.entity_summary || '';
        var presence = formatPresenceDate(profile.last_presence);
        var roleTheme = resolveRoleTheme(roles);

        /* Row 1: avatar + (name/email col) + (date/status col). Row 2: role badge full width */
        var html = '<div style="display:flex;flex-direction:column;gap:6px;">';
        html += '<div style="display:flex;align-items:flex-start;gap:10px;">';
        html += '<div style="width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:700;flex-shrink:0;background-color:' + escapeHtml(profileColor) + ';">' + escapeHtml(initials) + '</div>';
        html += '<div style="min-width:0;flex:1;">';
        html += '<div style="font-size:14px;font-weight:600;color:#111827;">' + escapeHtml(displayName) + '</div>';
        if (email) {
            html += '<div style="color:#6b7280;font-size:12px;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + escapeHtml(email) + '</div>';
        }
        if (title) {
            html += '<div style="color:#6b7280;font-size:12px;margin-top:2px;">' + escapeHtml(title) + '</div>';
        }
        html += '</div>';

        if (presence) {
            var dotColor = presence.isRecent ? '#22c55e' : '#9ca3af';
            html += '<div style="flex-shrink:0;text-align:right;">';
            html += '<div style="display:flex;align-items:center;gap:4px;justify-content:flex-end;">';
            html += '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:' + dotColor + ';"></span>';
            html += '<span style="font-size:11px;font-weight:600;color:#374151;">' + escapeHtml(presence.relative) + '</span>';
            html += '</div>';
            html += '<div style="font-size:10px;color:#9ca3af;margin-top:1px;" title="' + escapeHtml(presence.full) + '">' + escapeHtml(presence.full) + '</div>';
            html += '</div>';
        }
        html += '</div>';

        html += '<div style="margin-top:2px;">';
        html += '<span style="display:inline-flex;align-items:center;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:700;white-space:nowrap;background:' + escapeHtml(roleTheme.badgeBackground) + ';color:' + escapeHtml(roleTheme.badgeColor) + ';">';
        if (roleTheme.key === 'system_manager') {
            html += '<i class="fas fa-crown" aria-hidden="true" style="font-size:10px;margin-right:5px;"></i>';
        } else if (roleTheme.key === 'admin') {
            html += '<i class="fas fa-user-shield" aria-hidden="true" style="font-size:10px;margin-right:5px;"></i>';
        } else if (roleTheme.key === 'focal_point') {
            html += '<i class="fas fa-map-marker-alt" aria-hidden="true" style="font-size:10px;margin-right:5px;"></i>';
        }
        html += escapeHtml(roleTheme.label) + '</span>';
        html += '</div>';
        html += '</div>';

        var showAssignmentMeta = roleTheme.key !== 'system_manager';
        if (showAssignmentMeta && (roles.length || countriesCount > 0 || entitySummary)) {
            html += '<div style="margin-top:10px;border-top:1px solid #f3f4f6;padding-top:8px;font-size:12px;color:#374151;display:grid;gap:4px;">';
            if (roles.length) {
                html += '<div><span style="font-weight:600;color:#6b7280;">Roles:</span> ' + escapeHtml(roles.slice(0, 3).join(', ')) + '</div>';
            }
            if (countriesCount > 0) {
                html += '<div><span style="font-weight:600;color:#6b7280;">Countries:</span> ' + escapeHtml(countriesCount) + '</div>';
            }
            if (entitySummary) {
                html += '<div><span style="font-weight:600;color:#6b7280;">Entities:</span> ' + escapeHtml(entitySummary) + '</div>';
            }
            html += '</div>';
        }

        if (email) {
            var encodedEmail = encodeURIComponent(String(email));
            var mailtoHref = 'mailto:' + String(email);
            var teamsDeepLink = 'msteams:/l/chat/0/0?users=' + encodedEmail;
            var teamsWebLink = 'https://teams.microsoft.com/l/chat/0/0?users=' + encodedEmail;

            html += '<div style="margin-top:10px;border-top:1px solid #f3f4f6;padding-top:8px;display:flex;gap:8px;align-items:center;">';
            html += '<a href="' + escapeHtml(mailtoHref) + '" title="Email" aria-label="Email" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border:1px solid #d1d5db;border-radius:9999px;background:#ffffff;color:#374151;font-size:13px;text-decoration:none;">';
            html += '<i class="fas fa-envelope" aria-hidden="true"></i>';
            html += '</a>';
            html += '<a href="' + escapeHtml(teamsDeepLink) + '" data-teams-web-link="' + escapeHtml(teamsWebLink) + '" class="ag-user-teams-link" title="Teams Chat" aria-label="Teams Chat" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border:1px solid #bfdbfe;border-radius:9999px;background:#eff6ff;color:#1d4ed8;font-size:13px;text-decoration:none;">';
            html += '<span aria-hidden="true" style="display:block;width:14px;height:14px;background-image:url(\'/static/images/teams-icon.svg\');background-repeat:no-repeat;background-position:center;background-size:contain;"></span>';
            html += '</a>';

            var detailUrl = getUserDetailUrl(profile);
            if (detailUrl) {
                html += '<a href="' + escapeHtml(detailUrl) + '" title="User Details" aria-label="User Details" style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border:1px solid #93c5fd;border-radius:9999px;background:#eff6ff;color:#2563eb;font-size:13px;text-decoration:none;margin-left:auto;">';
                html += '<i class="fas fa-user-cog" aria-hidden="true"></i>';
                html += '</a>';
            }

            html += '</div>';
        }
        return html;
    }

    function positionPopup(trigger) {
        if (!popupEl || !trigger) return;
        var triggerRect = trigger.getBoundingClientRect();
        var spacing = 10;

        var wasHidden = popupEl.style.display === 'none';
        if (wasHidden) popupEl.style.display = 'block';
        popupEl.style.visibility = 'hidden';
        var popupWidth = popupEl.offsetWidth || 300;
        var popupHeight = popupEl.offsetHeight || 200;
        popupEl.style.visibility = '';
        if (wasHidden) popupEl.style.display = 'none';

        var left = triggerRect.left;
        var top = triggerRect.bottom + spacing;

        if (left + popupWidth > window.innerWidth - spacing) {
            left = window.innerWidth - popupWidth - spacing;
        }
        if (left < spacing) left = spacing;
        if (top + popupHeight > window.innerHeight - spacing) {
            top = triggerRect.top - popupHeight - spacing;
        }
        if (top < spacing) top = spacing;

        popupEl.style.left = Math.round(left) + 'px';
        popupEl.style.top = Math.round(top) + 'px';
    }

    function showForTrigger(trigger) {
        var inlineProfile = normalizeProfile(parseInlineProfile(trigger), trigger.getAttribute('data-user-email') || '');
        var userId = inlineProfile.id !== undefined ? inlineProfile.id : trigger.getAttribute('data-user-id');
        var email = inlineProfile.email || trigger.getAttribute('data-user-email') || '';
        var cached = readCachedProfile(userId, email);
        var effectiveProfile = cached || inlineProfile;

        if (!effectiveProfile || (!effectiveProfile.name && !effectiveProfile.email)) {
            return;
        }

        activeTrigger = trigger;

        function renderProfile(profileToRender) {
            var popup = getPopupElement();
            applyPopupTheme(resolveRoleTheme(profileToRender.rbac_roles));
            popup.innerHTML = buildPopupHtml(profileToRender);
            positionPopup(trigger);
            popup.style.display = 'block';
        }

        if (!cached && userId !== null && userId !== undefined && userId !== '') {
            fetchProfileSummary(userId, email).then(function(fetched) {
                if (activeTrigger !== trigger) return;
                var profileToRender = fetched ? normalizeProfile(fetched, email) : effectiveProfile;
                renderProfile(profileToRender);
            });
            return;
        }

        renderProfile(effectiveProfile);
    }

    function scheduleShow(trigger) {
        clearTimeout(showTimer);
        showTimer = setTimeout(function() {
            showForTrigger(trigger);
        }, HOVER_DELAY_MS);
    }

    function setupListeners() {
        document.addEventListener('mouseover', function(event) {
            var trigger = getClosestTrigger(event.target);
            if (!trigger) return;

            if (activeTrigger && activeTrigger !== trigger) {
                hidePopup();
            }
            clearTimeout(hideTimer);
            scheduleShow(trigger);
        });

        document.addEventListener('mouseout', function(event) {
            var trigger = getClosestTrigger(event.target);
            if (!trigger) return;

            var related = event.relatedTarget;
            if (related && popupEl && (popupEl.contains(related) || trigger.contains(related))) {
                return;
            }
            scheduleHide();
        });

        document.addEventListener('click', function(event) {
            var teamsLink = event.target && event.target.closest ? event.target.closest('.ag-user-teams-link') : null;
            if (teamsLink) {
                // Try Teams deep link first; if blocked/unavailable, fall back to web Teams.
                setTimeout(function() {
                    try {
                        var fallbackUrl = teamsLink.getAttribute('data-teams-web-link');
                        if (fallbackUrl) {
                            window.open(fallbackUrl, '_blank', 'noopener,noreferrer');
                        }
                    } catch (e) {
                        // Ignore fallback errors and keep default link behavior
                    }
                }, 700);
            }

            if (popupEl && popupEl.style.display !== 'none' && popupEl.contains(event.target)) {
                return;
            }

            var trigger = getClosestTrigger(event.target);
            if (!trigger) {
                if (popupEl && popupEl.style.display !== 'none') {
                    hidePopup();
                }
                return;
            }

            if (activeTrigger === trigger && popupEl && popupEl.style.display !== 'none') {
                hidePopup();
                return;
            }
            showForTrigger(trigger);
        });

        window.addEventListener('scroll', function() {
            if (activeTrigger && popupEl && popupEl.style.display !== 'none') {
                positionPopup(activeTrigger);
            }
        }, true);

        window.addEventListener('resize', function() {
            if (activeTrigger && popupEl && popupEl.style.display !== 'none') {
                positionPopup(activeTrigger);
            }
        });
    }

    setupListeners();

    window.UserHoverProfiles = {
        hide: hidePopup,
        cacheProfile: cacheProfile
    };

    /* Backward compatibility */
    window.AgGridUserHoverProfiles = window.UserHoverProfiles;
})();
