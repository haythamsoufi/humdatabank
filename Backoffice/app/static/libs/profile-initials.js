/**
 * Two-letter profile avatar initials (matches user form colour preview JS).
 * Two or more tokens: first letter of first two tokens. One token: up to two
 * letters from it. Otherwise first two of email local-part.
 */
(function (global) {
    'use strict';
    function profileDisplayInitials(name, email) {
        var n = (name || '').trim();
        if (n) {
            var parts = n.split(/\s+/).filter(function (p) {
                return p;
            });
            if (parts.length >= 2) {
                return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase().slice(0, 2);
            }
            return n.slice(0, 2).toUpperCase();
        }
        if (email) {
            var at = email.indexOf('@');
            var local = (at >= 0 ? email.slice(0, at) : email).slice(0, 2).toUpperCase();
            return local || '?';
        }
        return '?';
    }
    global.profileDisplayInitials = profileDisplayInitials;
})(typeof window !== 'undefined' ? window : this);
