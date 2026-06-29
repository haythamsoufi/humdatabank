/**
 * Campaign email HTML / Visual editor for Communication Center compose form.
 */
(function (global) {
    'use strict';

    const EDITOR_KEY = 'campaign-email-compose';
    const state = { config: null, editor: null };

    function getTemplateBaseHtml(key) {
        const tpl = state.config?.campaignEmailTemplates?.[key];
        if (!tpl || typeof tpl !== 'object') return '';
        if (typeof tpl.en === 'string' && tpl.en.trim()) return tpl.en;
        const langs = Object.keys(tpl);
        for (let i = 0; i < langs.length; i += 1) {
            const html = tpl[langs[i]];
            if (typeof html === 'string' && html.trim()) return html;
        }
        return '';
    }

    function getSelectedCampaignTemplateKey() {
        return document.getElementById('campaign-email-template-select')?.value?.trim() || '';
    }

    function syncVisibility() {
        const wrap = document.getElementById('campaign-email-compose-editor');
        const sendEmail = document.getElementById('send-email')?.checked;
        const key = getSelectedCampaignTemplateKey();
        if (!wrap) return;
        const visible = !!(sendEmail && key);
        wrap.classList.toggle('hidden', !visible);
        if (!visible && state.editor) {
            state.editor.setViewMode('edit');
        }
    }

    function loadTemplate(key, htmlOverride) {
        if (!state.editor) return;
        if (!key) {
            state.editor.setHtml('');
            syncVisibility();
            return;
        }
        const override = (htmlOverride || '').trim();
        state.editor.setHtml(override || getTemplateBaseHtml(key));
        syncVisibility();
    }

    function resetToTemplateDefault() {
        const key = getSelectedCampaignTemplateKey();
        if (!key) return;
        loadTemplate(key, '');
    }

    function getHtmlForPayload() {
        const key = getSelectedCampaignTemplateKey();
        if (!key || !state.editor) return null;
        const html = state.editor.getHtml();
        const base = getTemplateBaseHtml(key).trim();
        if (!html || html === base) return '';
        return html;
    }

    function init(config) {
        state.config = config || {};
        const rootEl = document.getElementById('campaign-email-compose-editor');
        if (!rootEl || typeof global.EmailTemplateEditorCore === 'undefined') return;

        state.editor = global.EmailTemplateEditorCore.createEditor({
            editorKey: EDITOR_KEY,
            rootEl,
            tinymceBaseUrl: state.config.urls?.tinymceBase || '',
            previewUrl: state.config.urls?.campaignEmailComposePreview || '',
            getApiTemplateKey: getSelectedCampaignTemplateKey,
            getPreviewExtraFields: () => ({
                title: document.getElementById('admin-notification-title')?.value?.trim() || '',
                message: document.getElementById('admin-notification-message')?.value?.trim() || '',
            }),
            labels: {
                tinymceVarTip: state.config.t?.tinymceVarTip || '',
                variables: state.config.t?.variables || 'Var',
                couldNotLoadSampleValues: state.config.t?.couldNotLoadSampleValues || '',
                addContentFirst: state.config.t?.addContentFirst || '',
            },
        });

        document.getElementById('campaign-email-reset-html-btn')?.addEventListener('click', resetToTemplateDefault);

        syncVisibility();
    }

    global.CampaignEmailComposeEditor = {
        init,
        syncVisibility,
        loadTemplate,
        getHtmlForPayload,
        resetToTemplateDefault,
    };
})(window);
