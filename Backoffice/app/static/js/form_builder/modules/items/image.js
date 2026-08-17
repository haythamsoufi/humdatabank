/**
 * Form-builder Image item module.
 * Supports per-locale upload or URL sources stored in config.image.sources.
 */

import { setHiddenField } from '../rules/form-serialization.js';

function getSupportedLanguages() {
    try {
        const el = document.getElementById('translation-data');
        if (!el) return ['en'];
        const data = JSON.parse(el.textContent || '{}');
        return Array.isArray(data.supportedLanguages) ? data.supportedLanguages : ['en'];
    } catch (_e) {
        return ['en'];
    }
}

function defaultImageConfig() {
    return {
        image: {
            alignment: 'center',
            max_width: '100%',
            sources: {},
        },
    };
}

function parseConfig(raw) {
    if (!raw) return defaultImageConfig();
    try {
        const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
        if (!parsed || typeof parsed !== 'object') return defaultImageConfig();
        if (!parsed.image) parsed.image = defaultImageConfig().image;
        if (!parsed.image.sources) parsed.image.sources = {};
        return parsed;
    } catch (_e) {
        return defaultImageConfig();
    }
}

function getTemplateContext(modalElement) {
    const templateId = modalElement?.dataset?.templateId
        || window.templateId
        || window.formBuilderTemplateId;
    const versionInput = document.querySelector('input[name="version_id"]');
    const versionId = versionInput ? versionInput.value : (window.formBuilderVersionId || window.activeVersionId || '');
    const itemId = window.ItemModal?.currentItemId || null;
    return { templateId, versionId, itemId };
}

function resolvePreviewUrl(source, templateId) {
    if (!source || typeof source !== 'object') return '';
    if (source.source_type === 'url') return source.url || '';
    if (source.source_type === 'upload' && source.storage_path && templateId) {
        return `/admin/templates/${templateId}/image-assets/${source.storage_path}`;
    }
    return '';
}

const CLIPBOARD_IMAGE_MIME_RE = /^image\/(png|jpe?g|webp|gif)$/i;

function normalizePastedFilename(file) {
    if (file.name && String(file.name).trim()) return file;
    const ext = (file.type || 'image/png').split('/')[1] || 'png';
    return new File([file], `pasted-image.${ext}`, { type: file.type || 'image/png' });
}

function pickClipboardImage(files) {
    if (!files || files.length <= 1) return files?.[0] || null;
    const preferredTypes = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];
    for (const mime of preferredTypes) {
        const matches = files.filter((f) => String(f.type || '').toLowerCase() === mime);
        if (matches.length) {
            return matches.sort((a, b) => (b.size || 0) - (a.size || 0))[0];
        }
    }
    return files.sort((a, b) => (b.size || 0) - (a.size || 0))[0];
}

function collectClipboardImageFile(clipboardData) {
    const items = clipboardData?.items;
    if (!items) return null;
    const imageFiles = [];
    for (const item of items) {
        if (item.type && CLIPBOARD_IMAGE_MIME_RE.test(item.type)) {
            const file = item.getAsFile();
            if (file) imageFiles.push(normalizePastedFilename(file));
        }
    }
    return pickClipboardImage(imageFiles);
}

function isTextPasteTarget(target) {
    if (!target || !(target instanceof Element)) return false;
    const tag = target.tagName?.toLowerCase();
    if (tag === 'textarea') return true;
    if (tag !== 'input') return false;
    const type = (target.getAttribute('type') || 'text').toLowerCase();
    return type === 'text' || type === 'url' || type === 'search' || type === 'email';
}

export const ImageItem = {
    _config: null,
    _activeLang: 'en',

    setup(modalElement) {
        this.modalElement = modalElement;
        this._config = defaultImageConfig();
        this._activeLang = 'en';
        this._bindEvents();
        this._renderLocaleTabs();
        this._syncPanelFromConfig('en');
    },

    teardown(modalElement) {
        const root = modalElement || this.modalElement;
        if (!root) return;
        root.querySelectorAll('.image-locale-panel').forEach((el) => el.remove());
        if (this._onPaste) {
            root.removeEventListener('paste', this._onPaste, true);
            this._onPaste = null;
        }
        delete root.dataset.imageEventsBound;
    },

    populateForm(modalElement, itemData) {
        this.modalElement = modalElement;
        this._config = parseConfig(itemData?.config || {});

        const labelInput = modalElement.querySelector('#item-image-caption');
        const altInput = modalElement.querySelector('#item-image-alt');
        const alignSelect = modalElement.querySelector('#item-image-alignment');
        const widthSelect = modalElement.querySelector('#item-image-max-width');

        if (labelInput) labelInput.value = itemData.label || '';
        if (altInput) altInput.value = itemData.description || '';
        if (alignSelect) alignSelect.value = this._config.image.alignment || 'center';
        if (widthSelect) widthSelect.value = this._config.image.max_width || '100%';

        this._activeLang = 'en';
        this._renderLocaleTabs();
        this._syncPanelFromConfig('en');
    },

    updateConfig(modalElement) {
        const root = modalElement || this.modalElement;
        if (!root) return;
        this._captureActivePanel();

        const alignSelect = root.querySelector('#item-image-alignment');
        const widthSelect = root.querySelector('#item-image-max-width');
        if (alignSelect) this._config.image.alignment = alignSelect.value || 'center';
        if (widthSelect) this._config.image.max_width = widthSelect.value || '100%';

        const form = root.querySelector('#item-modal-form');
        if (form) {
            setHiddenField(form, 'image_config', JSON.stringify(this._config), { id: 'item-image-config' });
        }
    },

    _bindEvents() {
        const root = this.modalElement;
        if (!root || root.dataset.imageEventsBound) return;
        root.dataset.imageEventsBound = '1';

        root.addEventListener('change', (e) => {
            if (!root.contains(e.target)) return;
            if (e.target.matches('.image-source-type-radio')) {
                this._toggleSourceInputs(this._activeLang);
            }
            if (e.target.id === 'item-image-file-input') {
                this._handleFileSelected(e.target.files?.[0]);
            }
        });

        root.addEventListener('click', (e) => {
            const tab = e.target.closest('.image-locale-tab');
            if (tab && root.contains(tab)) {
                e.preventDefault();
                this._captureActivePanel();
                this._activeLang = tab.dataset.lang || 'en';
                this._renderLocaleTabs();
                this._syncPanelFromConfig(this._activeLang);
            }
            const applyUrlBtn = e.target.closest('#item-image-apply-url-btn');
            if (applyUrlBtn && root.contains(applyUrlBtn)) {
                e.preventDefault();
                this._applyUrlSource();
            }
            const pasteZone = e.target.closest('#item-image-paste-zone');
            if (pasteZone && root.contains(pasteZone)) {
                pasteZone.focus();
            }
        });

        this._onPaste = (e) => {
            if (!root.contains(e.target)) return;
            if (isTextPasteTarget(e.target)) return;
            if (!this._isUploadModeActive()) return;

            const file = collectClipboardImageFile(e.clipboardData);
            if (!file) return;

            e.preventDefault();
            this._ensureUploadModeSelected();
            this._handleFileSelected(file);
        };
        root.addEventListener('paste', this._onPaste, true);
    },

    _isUploadModeActive() {
        const root = this.modalElement;
        if (!root) return false;
        const checked = root.querySelector('.image-source-type-radio:checked');
        return !checked || checked.value === 'upload';
    },

    _ensureUploadModeSelected() {
        const root = this.modalElement;
        if (!root) return;
        const uploadRadio = root.querySelector('.image-source-type-radio[value="upload"]');
        if (uploadRadio && !uploadRadio.checked) {
            uploadRadio.checked = true;
            this._toggleSourceInputs(this._activeLang);
        }
    },

    _renderLocaleTabs() {
        const container = this.modalElement?.querySelector('#item-image-locale-tabs');
        if (!container) return;
        const langs = getSupportedLanguages();
        container.innerHTML = langs.map((lang) => {
            const active = lang === this._activeLang;
            return `<button type="button" class="image-locale-tab px-3 py-1 text-xs rounded-md border ${active ? 'bg-teal-100 border-teal-400 text-teal-800' : 'bg-white border-gray-300 text-gray-700'}" data-lang="${lang}">${lang.toUpperCase()}</button>`;
        }).join('');
    },

    _syncPanelFromConfig(lang) {
        const root = this.modalElement;
        if (!root) return;
        const sources = this._config.image.sources || {};
        const src = sources[lang] || {};
        const sourceType = src.source_type || 'upload';

        root.querySelectorAll('.image-source-type-radio').forEach((radio) => {
            radio.checked = radio.value === sourceType;
        });
        this._toggleSourceInputs(lang);

        const urlInput = root.querySelector('#item-image-url-input');
        if (urlInput) urlInput.value = src.url || '';

        const fileLabel = root.querySelector('#item-image-file-name');
        if (fileLabel) fileLabel.textContent = src.filename || (src.storage_path ? src.storage_path.split('/').pop() : '');

        const preview = root.querySelector('#item-image-preview');
        const { templateId } = getTemplateContext(root);
        if (preview) {
            const url = resolvePreviewUrl(src, templateId);
            if (url) {
                preview.src = url;
                preview.classList.remove('hidden');
            } else {
                preview.removeAttribute('src');
                preview.classList.add('hidden');
            }
        }
    },

    _toggleSourceInputs(lang) {
        const root = this.modalElement;
        if (!root) return;
        const checked = root.querySelector('.image-source-type-radio:checked');
        const mode = checked ? checked.value : 'upload';
        const uploadBlock = root.querySelector('#item-image-upload-block');
        const urlBlock = root.querySelector('#item-image-url-block');
        if (uploadBlock) uploadBlock.classList.toggle('hidden', mode !== 'upload');
        if (urlBlock) urlBlock.classList.toggle('hidden', mode !== 'url');
    },

    _captureActivePanel() {
        const lang = this._activeLang || 'en';
        const root = this.modalElement;
        if (!root) return;
        const checked = root.querySelector('.image-source-type-radio:checked');
        const mode = checked ? checked.value : 'upload';
        if (!this._config.image.sources) this._config.image.sources = {};
        const existing = this._config.image.sources[lang] || {};

        if (mode === 'url') {
            const url = (root.querySelector('#item-image-url-input')?.value || '').trim();
            if (url) {
                this._config.image.sources[lang] = { source_type: 'url', url };
            } else {
                delete this._config.image.sources[lang];
            }
        } else if (existing.source_type === 'upload' && existing.storage_path) {
            this._config.image.sources[lang] = { ...existing, source_type: 'upload' };
        } else if (!existing.storage_path) {
            delete this._config.image.sources[lang];
        }
    },

    _applyUrlSource() {
        this._captureActivePanel();
        this._syncPanelFromConfig(this._activeLang);
    },

    async _handleFileSelected(file) {
        if (!file) return;
        const root = this.modalElement;
        const pasteZone = root?.querySelector('#item-image-paste-zone');
        const fileLabel = root?.querySelector('#item-image-file-name');
        if (pasteZone) pasteZone.classList.add('opacity-60');
        if (fileLabel) fileLabel.textContent = file.name || 'Uploading…';

        const { templateId, versionId, itemId } = getTemplateContext(root);
        if (!templateId || !versionId) {
            try { (window.__clientWarn || console.warn)('[ImageItem] Missing template/version for upload'); } catch (_e) {}
            return;
        }

        const lang = this._activeLang || 'en';
        const existing = (this._config.image.sources || {})[lang] || {};
        const formData = new FormData();
        formData.append('file', file);
        formData.append('language', lang);
        formData.append('version_id', versionId);
        if (itemId) formData.append('item_id', String(itemId));
        if (existing.storage_path) formData.append('current_storage_path', existing.storage_path);

        const csrf = document.querySelector('meta[name="csrf-token"]')?.content
            || document.querySelector('input[name="csrf_token"]')?.value;

        try {
            const resp = await fetch(`/admin/templates/${templateId}/image-assets/upload`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    ...(csrf ? { 'X-CSRFToken': csrf } : {}),
                },
                credentials: 'same-origin',
            });
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                throw new Error(data.message || 'Upload failed');
            }
            if (!this._config.image.sources) this._config.image.sources = {};
            this._config.image.sources[lang] = {
                source_type: 'upload',
                storage_path: data.storage_path,
                filename: data.filename,
            };
            this._syncPanelFromConfig(lang);
        } catch (err) {
            try { (window.__clientWarn || console.warn)('[ImageItem] upload failed', err); } catch (_e) {}
            alert(err.message || 'Image upload failed');
        } finally {
            if (pasteZone) pasteZone.classList.remove('opacity-60');
        }
    },
};

export default ImageItem;
