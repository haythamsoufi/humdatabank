#!/usr/bin/env python3
"""Rebuild matrix-handler.js and phase-2 mixins from the committed monolith."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX_DIR = ROOT / "app/static/js/forms/modules/matrix"
HANDLER = ROOT / "app/static/js/forms/modules/matrix-handler.js"

MONOLITH = subprocess.check_output(
    ["git", "show", "HEAD:Backoffice/app/static/js/forms/modules/matrix-handler.js"],
    text=True,
    encoding="utf-8",
)

HANDLER_METHODS = {
    "constructor",
    "_registerMatrixFromDom",
    "extractRowId",
    "sanitizeMatrixData",
    "init",
    "getInitStatus",
    "_canEditMatrix",
    "_applyMatrixInputEditability",
    "_lockMatrixContainerIfReadOnly",
    "_lockAllReadOnlyMatrices",
    "setupEventListeners",
    "initializeMatrices",
    "parseExistingData",
    "handleMatrixInputChange",
    "updateMatrixData",
    "handleDataAvailabilityChange",
    "syncMatrixDataFromInputs",
    "collectMatrixData",
    "resetMatrix",
    "getMatrixData",
    "setMatrixData",
    "handleKeyboardNavigation",
    "getCurrentLanguage",
    "resolveMetadataVariablesInText",
    "getColumnDisplayName",
    "cleanupMatrix",
    "syncFromDraftRestore",
}

PHASE2_MIXINS: dict[str, set[str]] = {
    "search-ui.js": {
        "_findResultsContainer",
        "_findSearchInput",
        "showSearchDropdown",
        "_positionAndShowDropdown",
        "_refreshDropdownResults",
        "hideSearchDropdown",
        "repositionVisibleDropdowns",
        "loadInitialSearchResults",
        "handleSearchInput",
        "renderSearchResults",
        "_escapeHtml",
        "showDropdownMessage",
        "selectRowOption",
    },
    "variables.js": {
        "getVariableTooltipLabels",
        "applyVariableLookupComparison",
        "applyVariableLookupComparisonForInput",
        "updateVariableModificationIndicator",
        "escapeHtml",
    },
    "dynamic-rows.js": {
        "addDynamicRow",
        "_matrixHasVariableColumns",
        "cleanupRowTooltips",
        "handleRemoveRowClick",
        "getExistingRows",
        "extractRowInfoFromData",
        "restoreRowData",
        "restoreStaticMatrixValues",
        "restoreDynamicRows",
        "sortMatrixRows",
        "applyDuplicateEntityHighlighting",
        "applyManualRowHighlighting",
        "updateLegendVisibility",
    },
    "auto-load.js": {"autoLoadEntities"},
}

MIXIN_EXPORT = {
    "search-ui.js": "matrixSearchUiMixin",
    "variables.js": "matrixVariablesMixin",
    "dynamic-rows.js": "matrixDynamicRowsMixin",
    "auto-load.js": "matrixAutoLoadMixin",
}

IMPORTS = {
    "search-ui.js": """\
/** Matrix search dropdown UI for dynamic row selection. */
import { debugLog, debugWarn } from '../debug.js';
import { _t } from './shared.js';""",
    "variables.js": """\
/** Variable column lookup comparison, tooltips, and modification indicators. */
import { debugLog } from '../debug.js';
import { _t } from './shared.js';
import {
    __formatLookupValueForInput,
    __formatNumberForDisplay,
    __getSavedMatrixCellScalar,
    __persistVariableCellScalar,
    __readMatrixMaxDecimals,
    __resolveMatrixLocalizedLabel,
    __serializeMatrixData,
    __setMatrixNumericCellDisplay,
    __variableCellDiffersFromLookup,
} from './formatting.js';
import { __inputValueForMatrixCompare } from './carry-forward.js';""",
    "dynamic-rows.js": """\
/** Dynamic matrix rows: add, remove, restore, sort, and legend highlighting. */
import { debugLog, debugError, debugWarn } from '../debug.js';
import { _t, __canEditMatrixContainer, ROW_TOTAL_COLUMN_NAME } from './shared.js';
import {
    __configFlag,
    __getSavedMatrixCellScalar,
    __parseMatrixCellKey,
    __resolveColumnMaxDecimals,
    __serializeMatrixData,
    __setMatrixNumericCellDisplay,
} from './formatting.js';
import {
    __ROW_TOTAL_INPUT_CLASS,
    __ROW_TOTAL_INPUT_WRAPPER_CLASS,
    __createRowTotalConflictIndicator,
    __rowTotalCellKey,
    __rowTotalManualEnabled,
    __rowTotalValidation,
} from './totals.js';""",
    "auto-load.js": """\
/** Auto-load matrix rows from variable entity resolution. */
import { debugLog, debugError, debugWarn } from '../debug.js';
import { __configFlag } from './formatting.js';
import { mhFetch } from './api.js';""",
}

HANDLER_HEADER = '''\
/**
 * Matrix Handler Module
 * Handles matrix table interactions, calculations, and data management
 */

import { debugLog, debugError, debugWarn } from './debug.js';
import { _t, __canEditMatrixContainer } from './matrix/shared.js';
import {
    __formatInteger,
    __integerInputValue,
    __setMatrixNumericInputValue,
    __setMatrixNumericCellDisplay,
    __syncWholeNumberViolationHighlight,
    __parseMatrixNumericCellValue,
    __configFlag,
    __normalizeVariableCompareValue,
    __getSavedMatrixCellScalar,
    __savedVariableCellIsUserModified,
    __savedVariableCellIsStaleLookupMirror,
    __formatLookupValueForInput,
    __formatSavedScalarForInput,
    __persistVariableCellScalar,
    __variableCellDiffersFromLookup,
    __resolveMatrixLocalizedLabel,
    __serializeMatrixData,
    __getMatrixColumnNames,
    __parseMatrixCellKey,
    __readMatrixMaxDecimals,
    __rawValueHasNonZeroFraction,
    __cellValueToNumber,
    __reorderMatrixData,
    __normalizeVariableNumericValue,
    __toVariableTickValue,
    __formatNumberForDisplay,
    __resolveColumnMaxDecimals,
    __parseMatrixNumericValue,
    __isEmptyVariableValue,
} from './matrix/formatting.js';
import {
    __parseCarryForwardRef,
    __matrixCellValuesMatch,
    __inputValueForMatrixCompare,
    matrixCarryForwardMixin,
} from './matrix/carry-forward.js';
import {
    ROW_TOTAL_COLUMN_NAME,
    __rowTotalManualEnabled,
    __rowTotalValidation,
    __updateRowTotalConflict,
    __storedRowTotalManualScalar,
    __effectiveRowTotalValue,
    __ROW_TOTAL_INPUT_WRAPPER_CLASS,
    __ROW_TOTAL_INPUT_CLASS,
    __createRowTotalConflictIndicator,
    __rowTotalCellKey,
    __computedRowTotalFromData,
    __parseRowTotalManualValue,
    matrixTotalsMixin,
} from './matrix/totals.js';
import { matrixValidationMixin } from './matrix/validation.js';
import { mhFetch, MATRIX_SEARCH_OPTIONS_FETCH_LIMIT, MATRIX_SEARCH_OPTIONS_DISPLAY_LIMIT, matrixApiMixin } from './matrix/api.js';
import { matrixSearchUiMixin } from './matrix/search-ui.js';
import { matrixVariablesMixin } from './matrix/variables.js';
import { matrixDynamicRowsMixin } from './matrix/dynamic-rows.js';
import { matrixAutoLoadMixin } from './matrix/auto-load.js';
'''


def parse_class_methods(source: str) -> dict[str, str]:
    """Return method name -> source text (including decorators/comments immediately above)."""
    class_start = source.index("class MatrixHandler")
    lines = source[class_start:].splitlines(keepends=True)
    # Drop trailing export/window code after class closing brace at column 0
    body_lines: list[str] = []
    depth = 0
    started = False
    for line in lines:
        if line.startswith("class MatrixHandler"):
            started = True
            body_lines.append(line)
            depth += line.count("{") - line.count("}")
            continue
        if not started:
            continue
        body_lines.append(line)
        depth += line.count("{") - line.count("}")
        if started and depth == 0:
            break

    class_text = "".join(body_lines)
    method_pattern = re.compile(r"^    (?:(async )?([a-zA-Z_][a-zA-Z0-9_]*)\(|constructor\()", re.M)

    matches = list(method_pattern.finditer(class_text))
    methods: dict[str, str] = {}
    for i, match in enumerate(matches):
        name = match.group(2) or "constructor"
        start = match.start()
        # Include docblock/comments above method
        prev = class_text.rfind("\n", 0, start)
        chunk_start = prev + 1
        while chunk_start > 0:
            line_start = class_text.rfind("\n", 0, chunk_start - 1) + 1
            segment = class_text[line_start:chunk_start]
            if segment.strip().startswith(("/**", "*", "//")) or segment.strip() == "":
                chunk_start = line_start
            else:
                break
        end = matches[i + 1].start() if i + 1 < len(matches) else len(class_text)
        chunk = class_text[chunk_start:end].rstrip()
        if i + 1 == len(matches):
            chunk = re.sub(r"\n}\s*$", "", chunk)
        methods[name] = chunk.rstrip() + "\n"
    return methods


def class_method_to_mixin(method_src: str) -> str:
    lines = method_src.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        if line.startswith("    "):
            out.append(line[4:])
        else:
            out.append(line)
    text = "".join(out).rstrip()
    if not text.endswith(","):
        text += ","
    return text + "\n"


def build_mixin_file(filename: str, method_names: set[str], methods: dict[str, str]) -> str:
    chunks = [class_method_to_mixin(methods[name]) for name in methods if name in method_names]
    body = "\n".join(chunks)
    export = MIXIN_EXPORT[filename]
    return f"{IMPORTS[filename]}\n\nexport const {export} = {{\n{body}}};\n"


def build_handler(methods: dict[str, str]) -> str:
    handler_methods = [methods[n] for n in methods if n in HANDLER_METHODS]
    class_body = "".join(handler_methods)
    footer = '''
Object.assign(
    MatrixHandler.prototype,
    matrixTotalsMixin,
    matrixValidationMixin,
    matrixCarryForwardMixin,
    matrixApiMixin,
    matrixSearchUiMixin,
    matrixVariablesMixin,
    matrixDynamicRowsMixin,
    matrixAutoLoadMixin,
);
// Create and export singleton instance
export const matrixHandler = new MatrixHandler();

// Make it available globally for debugging
window.matrixHandler = matrixHandler;

// Add global test function
window.testMatrixCalculation = () => {
    debugLog('MatrixHandler: Manual test calculation triggered');
    matrixHandler.calculateAllMatrices();
};

// Add function to check what's actually visible on the page
window.checkMatrixTotals = () => {
    (window.__clientLog || console.log)('=== MATRIX TOTALS CHECK ===');
    document.querySelectorAll('.matrix-row-total, .matrix-column-total').forEach((el, index) => {
        (window.__clientLog || console.log)(`Element ${index + 1}:`, {
            className: el.className,
            textContent: el.textContent,
            innerHTML: el.innerHTML,
            dataRow: el.dataset.row,
            dataColumn: el.dataset.column,
            visible: el.offsetParent !== null,
            computedStyle: window.getComputedStyle(el).display
        });
    });
    (window.__clientLog || console.log)('=== END CHECK ===');
};

// Do NOT auto-initialize here. Layout (initLayout) replaces section content via
// replaceChildren(), so matrix containers are recreated. Initialization must
// happen only from main.js after initLayout() so we bind to the final DOM.
// Otherwise we store refs to pre-layout nodes that get detached, causing
// stale refs and broken matrix behavior.
'''
    return HANDLER_HEADER + "\nclass MatrixHandler {\n" + class_body + "}\n\n" + footer


def main() -> None:
    methods = parse_class_methods(MONOLITH)
    assigned = set(HANDLER_METHODS)
    for names in PHASE2_MIXINS.values():
        assigned |= names

    unassigned = set(methods) - assigned
    if unassigned:
        print("Warning: unassigned methods (left in monolith mixins already):", sorted(unassigned))

    for filename, names in PHASE2_MIXINS.items():
        path = MATRIX_DIR / filename
        path.write_text(build_mixin_file(filename, names, methods), encoding="utf-8")
        print(f"Wrote {path}")

    handler_text = build_handler(methods)
    HANDLER.write_text(handler_text, encoding="utf-8")
    print(f"Wrote {HANDLER} ({handler_text.count(chr(10)) + 1} lines)")


if __name__ == "__main__":
    main()
