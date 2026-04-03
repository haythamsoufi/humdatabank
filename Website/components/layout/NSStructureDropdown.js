import { useState, useMemo, useEffect, forwardRef } from 'react';
import { useTranslation } from '../../lib/useTranslation';
import { TranslationSafe } from '../ClientOnly';
import { getNSStructure } from '../../lib/apiService';

const NSStructureDropdown = forwardRef(({ countryId, onClose }, ref) => {
  const { t } = useTranslation();

  const [branches, setBranches] = useState([]);
  const [selectedBranch, setSelectedBranch] = useState(null);
  const [subbranches, setSubbranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [subbranchSearchQuery, setSubbranchSearchQuery] = useState('');

  // Fetch NS structure when component mounts or countryId changes
  // This fetches both branches and sub-branches in one call
  useEffect(() => {
    if (!countryId) {
      setBranches([]);
      setSubbranches([]);
      setLoading(false);
      return;
    }

    let mounted = true;
    const fetchStructure = async () => {
      try {
        setLoading(true);
        // Fetch branches and all sub-branches in one call
        const data = await getNSStructure(countryId);
        if (!mounted) return;

        setBranches(data.branches || []);
        // Set all sub-branches initially (will be filtered when branch is selected)
        setSubbranches(data.subbranches || []);
        setSelectedBranch(null);
      } catch (error) {
        console.error('Error fetching NS structure:', error);
        if (!mounted) return;
        setBranches([]);
        setSubbranches([]);
      } finally {
        if (!mounted) return;
        setLoading(false);
      }
    };

    fetchStructure();
    return () => {
      mounted = false;
    };
  }, [countryId]);

  // Filter sub-branches based on selected branch (client-side filtering)
  // No need to make another API call - we already have all sub-branches
  const displayedSubbranches = useMemo(() => {
    if (!selectedBranch) {
      return subbranches; // Show all sub-branches when no branch is selected
    }
    // Filter to show only sub-branches for the selected branch
    return subbranches.filter(sb => sb.branch_id === selectedBranch);
  }, [subbranches, selectedBranch]);

  // Count sub-branches for each branch
  const branchSubbranchCounts = useMemo(() => {
    const counts = {};
    subbranches.forEach(sb => {
      if (sb.branch_id) {
        counts[sb.branch_id] = (counts[sb.branch_id] || 0) + 1;
      }
    });
    return counts;
  }, [subbranches]);

  // Filter branches based on search query
  const filteredBranches = useMemo(() => {
    if (!searchQuery.trim()) {
      return branches;
    }

    const query = searchQuery.toLowerCase();
    return branches.filter(branch =>
      branch.name?.toLowerCase().includes(query)
    );
  }, [branches, searchQuery]);

  // Filter sub-branches based on sub-branch search query and selected branch
  const filteredSubbranches = useMemo(() => {
    let filtered = displayedSubbranches;

    if (subbranchSearchQuery.trim()) {
      const query = subbranchSearchQuery.toLowerCase();
      filtered = filtered.filter(subbranch =>
        subbranch.name?.toLowerCase().includes(query)
      );
    }

    return filtered;
  }, [displayedSubbranches, subbranchSearchQuery]);

  if (loading) {
    return (
      <div
        ref={ref}
        className="absolute top-full -left-32 mt-1 w-[50rem] bg-white border border-gray-300 rounded-md shadow-lg z-50"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-ngodb-red"></div>
            <span className="ml-2 text-gray-600">
              <TranslationSafe fallback="Loading organizational structure...">
                {t('nsStructure.loading.title')}
              </TranslationSafe>
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className="absolute top-full left-0 sm:-left-32 mt-1 bg-white border border-gray-300 rounded-md shadow-lg z-50 sm:w-[50rem] sm:ml-0 mobile-full-width"
      style={{
        width: typeof window !== 'undefined' && window.innerWidth <= 640 ? 'calc(100vw - 2rem)' : undefined,
        left: typeof window !== 'undefined' && window.innerWidth <= 640 ? '1rem' : undefined,
        right: typeof window !== 'undefined' && window.innerWidth <= 640 ? '1rem' : undefined,
        maxWidth: typeof window !== 'undefined' && window.innerWidth <= 640 ? 'calc(100vw - 2rem)' : undefined
      }}
      onClick={(e) => e.stopPropagation()}
      data-ns-structure-dropdown
    >
      <div className="flex flex-col sm:flex-row h-auto sm:h-96 max-h-96" onClick={(e) => e.stopPropagation()}>
        {/* Branches List - Left Side */}
        <div className="w-full sm:w-1/3 border-b sm:border-b-0 sm:border-r border-gray-300 overflow-y-auto max-h-48 sm:max-h-none" onClick={(e) => e.stopPropagation()}>
          <div className="p-3 border-b border-gray-300">
            <h3 className="text-sm font-semibold text-gray-800">
              <TranslationSafe fallback="Branches">
                {t('nsStructure.branches')}
              </TranslationSafe>
            </h3>
          </div>

          {/* Search */}
          <div className="p-2 border-b border-gray-200">
            <input
              type="text"
              placeholder="Search branches..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-2 py-1 text-xs text-gray-900 border border-gray-300 rounded focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
            />
          </div>

          {/* Branches List */}
          <div className="py-1">
            {filteredBranches.length > 0 ? (
              filteredBranches.map((branch) => (
                <button
                  key={branch.id}
                  onClick={() => setSelectedBranch(branch.id)}
                  className={`w-full text-left px-3 py-2 text-sm transition-colors duration-150 ease-in-out
                    ${
                      selectedBranch === branch.id
                        ? 'bg-ngodb-red text-white'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{branch.name}</span>
                    {branchSubbranchCounts[branch.id] > 0 && (
                      <span className="text-xs text-gray-500 ml-2">
                        ({branchSubbranchCounts[branch.id]})
                      </span>
                    )}
                  </div>
                </button>
              ))
            ) : (
              <div className="px-3 py-4 text-center text-sm text-gray-500">
                <TranslationSafe fallback="No branches found">
                  {t('nsStructure.noBranches')}
                </TranslationSafe>
              </div>
            )}
          </div>
        </div>

        {/* Sub-branches List - Right Side */}
        <div className="w-full sm:w-2/3 flex flex-col max-h-64 sm:max-h-none" onClick={(e) => e.stopPropagation()}>
          <div className="p-3 border-b border-gray-300">
            <h3 className="text-sm font-semibold text-gray-800">
              <TranslationSafe fallback="Sub-branches">
                {t('nsStructure.subbranches')}
              </TranslationSafe>
            </h3>
          </div>

          {/* Search for Sub-branches */}
          <div className="p-2 border-b border-gray-200">
            <input
              type="text"
              placeholder="Search sub-branches..."
              value={subbranchSearchQuery}
              onChange={(e) => setSubbranchSearchQuery(e.target.value)}
              className="w-full px-2 py-1 text-xs text-gray-900 border border-gray-300 rounded focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
            />
          </div>

          {/* Sub-branches List */}
          <div className="flex-1 overflow-y-auto p-2 px-4 sm:px-2">
            {filteredSubbranches.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 divide-x divide-gray-200">
                {filteredSubbranches.map((subbranch) => (
                  <div
                    key={subbranch.id}
                    className="px-2 py-1.5 text-sm text-gray-700 hover:bg-gray-100 rounded transition-colors duration-150 ease-in-out"
                  >
                    <div className="font-medium">{subbranch.name}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500 text-sm">
                  <TranslationSafe fallback="No sub-branches found">
                    {t('nsStructure.noSubbranches')}
                  </TranslationSafe>
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

NSStructureDropdown.displayName = 'NSStructureDropdown';

export default NSStructureDropdown;
