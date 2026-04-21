import React, { useState, useRef, useEffect } from 'react';

const MultiSelectDropdown = ({
  options,
  selectedOptions,
  onSelectionChange,
  placeholder = "Select options...",
  groupBy = null,
  searchable = true,
  maxHeight = "300px"
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Filter options based on search term
  const filteredOptions = options.filter(option =>
    option.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    option.code.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Group options if groupBy is provided
  const groupedOptions = groupBy
    ? filteredOptions.reduce((groups, option) => {
        const group = option[groupBy];
        if (!groups[group]) {
          groups[group] = [];
        }
        groups[group].push(option);
        return groups;
      }, {})
    : { 'All': filteredOptions };

  const toggleOption = (option) => {
    const isSelected = selectedOptions.find(selected => selected.code === option.code);
    if (isSelected) {
      onSelectionChange(selectedOptions.filter(selected => selected.code !== option.code));
    } else {
      onSelectionChange([...selectedOptions, option]);
    }
  };

  const selectAllInGroup = (groupName) => {
    const groupOptions = groupedOptions[groupName];
    const groupSelectedCodes = groupOptions.map(opt => opt.code);
    const currentSelectedCodes = selectedOptions.map(opt => opt.code);

    const newSelectedCodes = [...new Set([...currentSelectedCodes, ...groupSelectedCodes])];
    const newSelectedOptions = options.filter(opt => newSelectedCodes.includes(opt.code));
    onSelectionChange(newSelectedOptions);
  };

  const deselectAllInGroup = (groupName) => {
    const groupOptions = groupedOptions[groupName];
    const groupSelectedCodes = groupOptions.map(opt => opt.code);
    const newSelectedOptions = selectedOptions.filter(opt => !groupSelectedCodes.includes(opt.code));
    onSelectionChange(newSelectedOptions);
  };

  const isGroupFullySelected = (groupName) => {
    const groupOptions = groupedOptions[groupName];
    const groupSelectedCodes = groupOptions.map(opt => opt.code);
    const currentSelectedCodes = selectedOptions.map(opt => opt.code);
    return groupOptions.every(opt => currentSelectedCodes.includes(opt.code));
  };

  const isGroupPartiallySelected = (groupName) => {
    const groupOptions = groupedOptions[groupName];
    const groupSelectedCodes = groupOptions.map(opt => opt.code);
    const currentSelectedCodes = selectedOptions.map(opt => opt.code);
    const selectedInGroup = groupOptions.filter(opt => currentSelectedCodes.includes(opt.code));
    return selectedInGroup.length > 0 && selectedInGroup.length < groupOptions.length;
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 border border-humdb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-humdb-red focus:border-transparent bg-white text-left flex items-center justify-between"
      >
        <div className="flex-1 min-w-0">
          {selectedOptions.length === 0 ? (
            <span className="text-humdb-gray-500">{placeholder}</span>
          ) : (
            <span className="text-humdb-gray-900">
              {selectedOptions.length} selected
            </span>
          )}
        </div>
        <svg
          className={`w-4 h-4 text-humdb-gray-400 transition-transform duration-200 ${
            isOpen ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-humdb-gray-200 rounded-lg shadow-lg">
          {/* Search Input */}
          {searchable && (
            <div className="p-3 border-b border-humdb-gray-200">
              <input
                type="text"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full px-3 py-2 border border-humdb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-humdb-red focus:border-transparent text-sm"
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          )}

          {/* Options List */}
          <div className="max-h-64 overflow-y-auto" style={{ maxHeight }}>
            {Object.entries(groupedOptions).map(([groupName, groupOptions]) => (
              <div key={groupName}>
                {/* Group Header */}
                <div className="px-3 py-2 bg-humdb-gray-50 border-b border-humdb-gray-200 flex items-center justify-between">
                  <span className="text-sm font-semibold text-humdb-navy">{groupName}</span>
                  <div className="flex space-x-1">
                    <button
                      type="button"
                      onClick={() => selectAllInGroup(groupName)}
                      className="text-xs px-2 py-1 text-humdb-red hover:bg-humdb-red hover:text-white rounded transition-colors"
                    >
                      All
                    </button>
                    <button
                      type="button"
                      onClick={() => deselectAllInGroup(groupName)}
                      className="text-xs px-2 py-1 text-humdb-gray-600 hover:bg-humdb-gray-200 rounded transition-colors"
                    >
                      None
                    </button>
                  </div>
                </div>

                {/* Group Options */}
                {groupOptions.map((option) => {
                  const isSelected = selectedOptions.find(selected => selected.code === option.code);
                  return (
                    <div
                      key={option.code}
                      className="px-3 py-2 hover:bg-humdb-gray-50 cursor-pointer flex items-center"
                      onClick={() => toggleOption(option)}
                    >
                      <div className={`w-4 h-4 border-2 rounded mr-3 flex items-center justify-center ${
                        isSelected
                          ? 'bg-humdb-red border-humdb-red'
                          : 'border-humdb-gray-300'
                      }`}>
                        {isSelected && (
                          <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        )}
                      </div>
                      <div className="flex-1">
                        <div className="text-sm font-medium text-humdb-gray-900">{option.name}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}

            {/* No results message */}
            {filteredOptions.length === 0 && (
              <div className="px-3 py-4 text-center text-humdb-gray-500 text-sm">
                No options found
              </div>
            )}
          </div>

          {/* Footer with select all/none */}
          <div className="p-3 border-t border-humdb-gray-200 bg-humdb-gray-50 flex justify-between items-center">
            <div className="flex space-x-3">
              <button
                type="button"
                onClick={() => onSelectionChange(options)}
                className="text-sm text-humdb-red hover:text-humdb-red-dark font-medium transition-colors"
              >
                Select all
              </button>
              <button
                type="button"
                onClick={() => onSelectionChange([])}
                className="text-sm text-humdb-gray-600 hover:text-humdb-red transition-colors"
              >
                Clear all
              </button>
            </div>
            <span className="text-sm text-humdb-gray-500">
              {selectedOptions.length} of {options.length} selected
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default MultiSelectDropdown;
