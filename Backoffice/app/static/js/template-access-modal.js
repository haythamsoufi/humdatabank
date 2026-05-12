// Template Access Management Modal
// Modal for managing template ownership and shared access, styled like confirm-dialogs.js

/**
 * Show template access management modal
 * @param {Object} options - Configuration options for the modal
 * @param {string} options.title - Title for the modal (default: "Template Access Management")
 * @param {string} options.ownerFieldName - Name of the owner field
 * @param {string} options.sharedFieldName - Name of the shared access field
 * @param {Array} options.ownerChoices - Array of owner choices
 * @param {Array} options.sharedChoices - Array of shared access choices
 * @param {string} options.currentOwner - Currently selected owner
 * @param {Array} options.currentShared - Currently selected shared users
 * @param {function} options.onSave - Callback function when user saves changes
 * @param {function} options.onCancel - Optional callback function when user cancels
 */
function showTemplateAccessModal(options = {}) {
    const {
        title = 'Template Access Management',
        ownerFieldName = 'owned_by',
        sharedFieldName = 'shared_with_admins',
        ownerChoices = [],
        sharedChoices = [],
        currentOwner = '',
        currentShared = [],
        currentUserId = null,
        templateOwnerId = null,
        onSave = null,
        onCancel = null
    } = options;

    // Debug logging
    console.log('Template Access Modal Data:', {
        currentOwner,
        currentShared,
        ownerChoices,
        sharedChoices,
        currentUserId,
        templateOwnerId
    });

    // Determine if current user is the template owner
    const isTemplateOwner = currentUserId && templateOwnerId && (currentUserId === templateOwnerId);
    const isNewTemplate = templateOwnerId === null;

    // Helper function to generate profile icon DOM node
    const generateProfileIcon = (userId, userName, userEmail, size = 'sm') => {
        const initials = profileDisplayInitials(userName, userEmail);
        const displayName = userName || userEmail || 'Unknown';

        // Generate a consistent color based on user ID
        const colors = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#06B6D4', '#84CC16'];
        const colorIndex = userId ? (parseInt(userId) % colors.length) : 0;
        const profileColor = colors[colorIndex];

        const iconDiv = document.createElement('div');
        iconDiv.className = 'w-6 h-6 rounded-full text-white text-xs font-semibold flex items-center justify-center mr-2 flex-shrink-0';
        iconDiv.style.backgroundColor = profileColor;
        iconDiv.textContent = initials;
        return iconDiv;
    };

    // Create modal using centralized createModalShell (from confirm-dialogs.js)
    const { modal, modalContent, innerDiv, contentDiv, closeModal } = window.createModalShell(title, { iconType: 'users', maxWidth: '2xl', onCancel: onCancel || null });
    contentDiv.className = 'space-y-6';

    // Template Owner Section
    if (isTemplateOwner || isNewTemplate) {
        const ownerSection = document.createElement('div');
        const ownerLabel = document.createElement('label');
        ownerLabel.className = 'block text-sm font-medium text-gray-700 mb-2';
        ownerLabel.textContent = 'Template Owner';
        const ownerSelect = document.createElement('select');
        ownerSelect.id = 'template-owner-select';
        ownerSelect.className = 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm';
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'Select owner...';
        ownerSelect.appendChild(defaultOption);
        ownerChoices.forEach(choice => {
            const option = document.createElement('option');
            option.value = choice[0];
            option.textContent = choice[1];
            if (String(choice[0]) === String(currentOwner)) {
                option.selected = true;
            }
            ownerSelect.appendChild(option);
        });
        ownerSection.appendChild(ownerLabel);
        ownerSection.appendChild(ownerSelect);
        contentDiv.appendChild(ownerSection);
    } else {
        const ownerSection = document.createElement('div');
        const ownerLabel = document.createElement('label');
        ownerLabel.className = 'block text-sm font-medium text-gray-700 mb-2';
        ownerLabel.textContent = 'Template Owner';
        const ownerDisplay = document.createElement('div');
        ownerDisplay.className = 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-gray-50 rounded-md text-sm text-gray-600';
        const ownerDisplayFlex = document.createElement('div');
        ownerDisplayFlex.className = 'flex items-center';
        const ownerChoice = ownerChoices.find(choice => String(choice[0]) === String(currentOwner));
        const profileIcon = ownerChoice ? generateProfileIcon(currentOwner, ownerChoice[1], '') : generateProfileIcon(null, 'Unknown Owner', '');
        ownerDisplayFlex.appendChild(profileIcon);
        const ownerNameSpan = document.createElement('span');
        ownerNameSpan.textContent = ownerChoice ? ownerChoice[1] : 'Unknown Owner';
        ownerDisplayFlex.appendChild(ownerNameSpan);
        ownerDisplay.appendChild(ownerDisplayFlex);
        const ownerNote = document.createElement('p');
        ownerNote.className = 'mt-1 text-xs text-gray-500';
        ownerNote.textContent = 'Only the template owner can change ownership';
        ownerSection.appendChild(ownerLabel);
        ownerSection.appendChild(ownerDisplay);
        ownerSection.appendChild(ownerNote);
        contentDiv.appendChild(ownerSection);
    }

    // Shared Access Section
    const sharedSection = document.createElement('div');
    const sharedLabel = document.createElement('label');
    sharedLabel.className = 'block text-sm font-medium text-gray-700 mb-2';
    sharedLabel.textContent = 'Shared Access';

    const searchContainer = document.createElement('div');
    searchContainer.className = 'mb-3 relative';
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.id = 'shared-access-search';
    searchInput.placeholder = 'Search users...';
    searchInput.className = 'w-full px-3 py-2 pr-8 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500';
    const clearSearchBtn = document.createElement('button');
    clearSearchBtn.type = 'button';
    clearSearchBtn.id = 'clear-search-btn';
    clearSearchBtn.className = 'absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 hidden';
    const clearSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    clearSvg.setAttribute('class', 'w-4 h-4');
    clearSvg.setAttribute('fill', 'none');
    clearSvg.setAttribute('stroke', 'currentColor');
    clearSvg.setAttribute('viewBox', '0 0 24 24');
    const clearPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    clearPath.setAttribute('stroke-linecap', 'round');
    clearPath.setAttribute('stroke-linejoin', 'round');
    clearPath.setAttribute('stroke-width', '2');
    clearPath.setAttribute('d', 'M6 18L18 6M6 6l12 12');
    clearSvg.appendChild(clearPath);
    clearSearchBtn.appendChild(clearSvg);
    searchContainer.appendChild(searchInput);
    searchContainer.appendChild(clearSearchBtn);

    const sharedListContainer = document.createElement('div');
    sharedListContainer.className = 'max-h-60 overflow-auto border border-gray-300 rounded-md p-3 bg-gray-50';
    const sharedList = document.createElement('div');
    sharedList.id = 'shared-access-list';
    sharedChoices.forEach(choice => {
        const isChecked = currentShared.includes(String(choice[0]));
        const isOwner = String(choice[0]) === String(currentOwner);
        const displayName = isOwner ? `${choice[1]} (Owner)` : choice[1];
        const isDisabled = isOwner;

        const label = document.createElement('label');
        label.className = `flex items-center px-3 py-2 ${isDisabled ? 'bg-gray-50 cursor-not-allowed' : 'hover:bg-gray-100 cursor-pointer'} rounded shared-access-item`;
        label.setAttribute('data-search-text', choice[1].toLowerCase());

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = sharedFieldName;
        checkbox.value = choice[0];
        checkbox.className = `shared-access-checkbox rounded border-gray-300 text-blue-600 focus:ring-blue-500 ${isDisabled ? 'opacity-50' : ''}`;
        checkbox.checked = isChecked || isOwner;
        checkbox.disabled = isDisabled;

        const checkboxDiv = document.createElement('div');
        checkboxDiv.className = 'ml-2 flex items-center';
        checkboxDiv.appendChild(generateProfileIcon(choice[0], choice[1], ''));
        const nameSpan = document.createElement('span');
        nameSpan.className = `text-sm ${isDisabled ? 'text-gray-500' : 'text-gray-900'}`;
        nameSpan.textContent = displayName;
        checkboxDiv.appendChild(nameSpan);

        label.appendChild(checkbox);
        label.appendChild(checkboxDiv);
        sharedList.appendChild(label);
    });
    const noResultsMessage = document.createElement('div');
    noResultsMessage.id = 'no-results-message';
    noResultsMessage.className = 'hidden text-center py-4 text-gray-500 text-sm';
    noResultsMessage.textContent = 'No users found matching your search.';
    sharedListContainer.appendChild(sharedList);
    sharedListContainer.appendChild(noResultsMessage);

    const sharedNote = document.createElement('p');
    sharedNote.className = 'mt-2 text-xs text-gray-500';
    sharedNote.textContent = 'Select users who should have access to this template';

    sharedSection.appendChild(sharedLabel);
    sharedSection.appendChild(searchContainer);
    sharedSection.appendChild(sharedListContainer);
    sharedSection.appendChild(sharedNote);
    contentDiv.appendChild(sharedSection);

    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'flex justify-end space-x-3 mt-6';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.id = 'template-access-cancel';
    cancelBtn.className = 'px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500';
    cancelBtn.textContent = 'Cancel';

    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.id = 'template-access-save';
    saveBtn.className = 'px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500';
    saveBtn.textContent = 'Save Changes';

    buttonsDiv.appendChild(cancelBtn);
    buttonsDiv.appendChild(saveBtn);

    innerDiv.appendChild(buttonsDiv);

    // Handle clicks (buttons and inputs are already created above, no need to query)
    const ownerSelect = modalContent.querySelector('#template-owner-select');
    const sharedCheckboxes = modalContent.querySelectorAll('.shared-access-checkbox');
    const sharedAccessItems = modalContent.querySelectorAll('.shared-access-item');

    cancelBtn.addEventListener('click', () => {
        closeModal();
        if (onCancel) onCancel();
    });

    saveBtn.addEventListener('click', () => {
        // Collect form data
        const selectedOwner = (isTemplateOwner || isNewTemplate) ? ownerSelect.value : currentOwner;
        const selectedShared = Array.from(sharedCheckboxes)
            .filter(checkbox => checkbox.checked)
            .map(checkbox => checkbox.value);

        // Ensure the owner is always included in shared access
        if (selectedOwner && !selectedShared.includes(selectedOwner)) {
            selectedShared.push(selectedOwner);
        }

        // Call the save callback with the data
        if (onSave) {
            onSave({
                owner: selectedOwner,
                shared: selectedShared,
                ownerFieldName: ownerFieldName,
                sharedFieldName: sharedFieldName
            });
        }

        closeModal();
    });

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
            if (onCancel) onCancel();
        }
    });

    // Close on Escape key
    const handleEscape = (e) => {
        if (e.key === 'Escape') {
            closeModal();
            if (onCancel) onCancel();
            document.removeEventListener('keydown', handleEscape);
        }
    };
    document.addEventListener('keydown', handleEscape);

    // Search functionality for shared access
    if (searchInput && sharedAccessItems.length > 0) {
        const performSearch = () => {
            const searchTerm = searchInput.value.toLowerCase().trim();
            let visibleCount = 0;

            sharedAccessItems.forEach(item => {
                const searchText = item.getAttribute('data-search-text') || '';
                const matches = searchText.includes(searchTerm);

                if (matches) {
                    item.style.display = 'flex';
                    visibleCount++;
                } else {
                    item.style.display = 'none';
                }
            });

            // Show/hide "no results" message
            if (noResultsMessage) {
                if (visibleCount === 0 && searchTerm.length > 0) {
                    noResultsMessage.classList.remove('hidden');
                } else {
                    noResultsMessage.classList.add('hidden');
                }
            }

            // Show/hide clear button
            if (clearSearchBtn) {
                if (searchTerm.length > 0) {
                    clearSearchBtn.classList.remove('hidden');
                } else {
                    clearSearchBtn.classList.add('hidden');
                }
            }
        };

        searchInput.addEventListener('input', performSearch);

        // Clear search button functionality
        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', function() {
                searchInput.value = '';
                performSearch();
                searchInput.focus();
            });
        }

        // Clear search when modal opens
        searchInput.value = '';
        if (noResultsMessage) {
            noResultsMessage.classList.add('hidden');
        }
        if (clearSearchBtn) {
            clearSearchBtn.classList.add('hidden');
        }
    }

    // Focus the save button for better accessibility
    setTimeout(() => {
        saveBtn.focus();
    }, 100);
}

// Make function globally available
window.showTemplateAccessModal = showTemplateAccessModal;
