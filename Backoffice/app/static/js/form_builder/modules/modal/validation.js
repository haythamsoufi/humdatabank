export const ValidationMixin = {
    clearValidationErrors: function() {
        if (this.formElement) {
            const errorElements = this.formElement.querySelectorAll('.field-error, .text-red-500');
            errorElements.forEach(element => {
                element.remove();
            });
        }
    },

    displayValidationErrors: function(errors, formPrefix) {
        for (const [fieldName, errorMessages] of Object.entries(errors)) {
            const unprefixedFieldName = fieldName.replace(formPrefix, '');
            const fieldElement = this.formElement.querySelector(`[name="${unprefixedFieldName}"], [id*="${unprefixedFieldName}"]`);

            if (fieldElement) {
                const errorElement = document.createElement('p');
                errorElement.className = 'mt-1 text-red-500 text-xs italic field-error';
                errorElement.textContent = Array.isArray(errorMessages) ? errorMessages.join(', ') : errorMessages;

                fieldElement.parentNode.insertBefore(errorElement, fieldElement.nextSibling);
            }
        }
    },
};
