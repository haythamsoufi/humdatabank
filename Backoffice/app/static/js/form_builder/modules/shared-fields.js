// Shared fields synchronization helpers

export const SharedFields = {
	init(modalElement) {
		this.modalElement = modalElement;
		this.sharedFields = {
			label: '#item-modal-shared-label',
			description: '#item-modal-shared-description',
			label_translations: '#item-modal-shared-label-translations',
			description_translations: '#item-modal-shared-description-translations'
		};
	},

	syncSharedToUI() {
		// Scope all queries to the modal to avoid syncing from/to unrelated fields elsewhere on the page.
		const root = this.modalElement || document;
		const sharedLabel = root.querySelector(this.sharedFields.label);
		const sharedDescription = root.querySelector(this.sharedFields.description);

		// Prefer item-type-specific fields to avoid accidentally syncing to the wrong
		// `data-field-type="label"` input (e.g. matrix row headers) when multiple exist.
		const resolveActiveLabelField = () => {
			const t = (window.ItemModal && window.ItemModal.currentItemType) ? window.ItemModal.currentItemType : null;
			if (t === 'indicator') return root.querySelector('#item-indicator-label');
			if (t === 'question') return root.querySelector('#item-question-label');
			if (t === 'document_field') return root.querySelector('#item-document-label');
			if (t === 'matrix') return root.querySelector('#item-matrix-label');
			if (t && String(t).startsWith('plugin_')) return root.querySelector('#item-plugin-label');
			return root.querySelector(`[data-field-type="label"]:not(.hidden)`);
		};
		const resolveActiveDescriptionField = () => {
			const t = (window.ItemModal && window.ItemModal.currentItemType) ? window.ItemModal.currentItemType : null;
			if (t === 'document_field') return root.querySelector('#item-document-description');
			if (t === 'matrix') return root.querySelector('#item-matrix-description');
			if (t && String(t).startsWith('plugin_')) return root.querySelector('#item-plugin-description');
			// Indicator/question "description" is represented by other specific fields (definition etc),
			// so only sync generic description fields when present.
			return root.querySelector(`[data-field-type="description"]:not(.hidden)`);
		};

		const labelField = resolveActiveLabelField();
		if (labelField && sharedLabel) {
			labelField.value = sharedLabel.value;
		}
		const descField = resolveActiveDescriptionField();
		if (descField && sharedDescription) {
			descField.value = sharedDescription.value;
		}
	},

	syncUIToShared() {
		// Scope to the modal to ensure we read the currently visible modal field (not other page inputs).
		const root = this.modalElement || document;
		const sharedLabel = root.querySelector(this.sharedFields.label);
		const sharedDescription = root.querySelector(this.sharedFields.description);

		const resolveActiveLabelField = () => {
			const t = (window.ItemModal && window.ItemModal.currentItemType) ? window.ItemModal.currentItemType : null;
			if (t === 'indicator') return root.querySelector('#item-indicator-label:not([disabled])');
			if (t === 'question') return root.querySelector('#item-question-label:not([disabled])');
			if (t === 'document_field') return root.querySelector('#item-document-label:not([disabled])');
			if (t === 'matrix') return root.querySelector('#item-matrix-label:not([disabled])');
			if (t && String(t).startsWith('plugin_')) return root.querySelector('#item-plugin-label:not([disabled])');
			return root.querySelector(`[data-field-type="label"]:not(.hidden):not([disabled])`);
		};
		const resolveActiveDescriptionField = () => {
			const t = (window.ItemModal && window.ItemModal.currentItemType) ? window.ItemModal.currentItemType : null;
			if (t === 'document_field') return root.querySelector('#item-document-description:not([disabled])');
			if (t === 'matrix') return root.querySelector('#item-matrix-description:not([disabled])');
			if (t && String(t).startsWith('plugin_')) return root.querySelector('#item-plugin-description:not([disabled])');
			return root.querySelector(`[data-field-type="description"]:not(.hidden):not([disabled])`);
		};

		const activeLabelField = resolveActiveLabelField();
		if (activeLabelField && sharedLabel) {
			sharedLabel.value = activeLabelField.value;
		}
		// Indicator custom label override: keep explicit override field in sync so AJAX form snapshots
		// always include it (independent of submit-handler ordering).
		try {
			const t = (window.ItemModal && window.ItemModal.currentItemType) ? window.ItemModal.currentItemType : null;
			if (t === 'indicator') {
				const override = root.querySelector('#item-modal-indicator-label-override');
				if (override && activeLabelField) {
					override.value = activeLabelField.value || '';
					// Ensure it submits under the expected name
					override.setAttribute('name', 'indicator_label_override');
				}
			}
		} catch (_e) {}
		const activeDescriptionField = resolveActiveDescriptionField();
		if (activeDescriptionField && sharedDescription) {
			sharedDescription.value = activeDescriptionField.value;
		}
	},

	setupFieldSync(modalElement) {
		// Always update reference to the current modal element
		this.init(modalElement);

		// Attach global listeners only once (safe if setupFieldSync is called multiple times)
		if (this._handlersAttached) {
			return;
		}
		this._handlersAttached = true;

		document.addEventListener('input', (e) => {
			if (!this.modalElement || !this.modalElement.contains(e.target)) return;
			if (e.target && e.target.hasAttribute && e.target.hasAttribute('data-field-type')) {
				this.syncUIToShared();
			}
		});

		document.addEventListener('change', (e) => {
			if (!this.modalElement || !this.modalElement.contains(e.target)) return;
			if (e.target && e.target.name === 'item_type') {
				setTimeout(() => {
					this.syncSharedToUI();
				}, 50);
			}
		});
	}
};

export default SharedFields;
