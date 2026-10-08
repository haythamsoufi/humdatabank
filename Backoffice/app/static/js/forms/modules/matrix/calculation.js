/**
 * Per-row matrix formulas. Keep this in step with app/utils/matrix_calculation.py.
 *
 * Presets compile to one formula. Blank number cells stay blank. Tick cells are
 * 0 or 1. SUM, AVERAGE, MIN, MAX, and COUNT skip blanks. Arithmetic treats
 * blanks as zero unless blank_as_zero is false. IF short-circuits.
 */

const BLANK = Object.freeze({ blank: true });

export const CALCULATION_OPERATIONS = [
    'sum',
    'average',
    'min',
    'max',
    'count',
    'count_filled',
    'difference',
    'percentage',
    'product',
    'formula',
];

function isBlank(value) {
    return value === BLANK || value == null;
}

export function columnCountsTowardRowTotal(column) {
    if (!column || typeof column !== 'object') return true;
    if (column.type === 'calculated') return column.include_in_row_total === true;
    return column.include_in_row_total !== false;
}

export function calculationIsReadonly(column) {
    if (!column || typeof column !== 'object' || column.type !== 'calculated') return true;
    return column.calculation_readonly !== false;
}

export function calculationSavesValue(column) {
    return !!(column && typeof column === 'object' && column.type === 'calculated' && column.calculation_save_value === true);
}

function cleanNames(raw) {
    if (!Array.isArray(raw)) return [];
    return raw
        .filter((item) => typeof item === 'string' && item.trim())
        .map((item) => item.trim().slice(0, 200));
}

function columnRef(name) {
    return /^[A-Za-z_][A-Za-z0-9_]*$/.test(name || '') ? name : `{${name}}`;
}

function refList(names) {
    return names.map((name) => columnRef(name)).join(', ');
}

function sumExpr(names) {
    if (!names.length) return '0';
    return `SUM(${refList(names)})`;
}

export function compileCalculation(calculation) {
    const calc = calculation && typeof calculation === 'object' ? calculation : {};
    const operation = String(calc.operation || 'formula').trim().toLowerCase();
    const sources = cleanNames(calc.sources);
    const subtrahends = cleanNames(calc.subtrahends);
    const denominators = cleanNames(calc.denominators);
    if (operation === 'formula') return String(calc.formula || '').trim();
    if (operation === 'sum') return sumExpr(sources);
    if (operation === 'average') return sources.length ? `AVERAGE(${refList(sources)})` : '';
    if (operation === 'min') return sources.length ? `MIN(${refList(sources)})` : '';
    if (operation === 'max') return sources.length ? `MAX(${refList(sources)})` : '';
    if (operation === 'count') return sources.length ? `COUNT(${refList(sources)})` : '0';
    if (operation === 'count_filled') return sources.length ? `COUNTA(${refList(sources)})` : '0';
    if (operation === 'difference') return `${sumExpr(sources)} - ${sumExpr(subtrahends)}`;
    if (operation === 'percentage') {
        return `IF(${sumExpr(denominators)} = 0, BLANK(), ${sumExpr(sources)} / ${sumExpr(denominators)} * 100)`;
    }
    if (operation === 'product') {
        if (!sources.length) return '';
        if (sources.length === 1) return columnRef(sources[0]);
        return sources.map((name) => columnRef(name)).join(' * ');
    }
    return String(calc.formula || '').trim();
}

export function roundHalfAway(value, digits) {
    const factor = 10 ** digits;
    const scaled = value * factor;
    const sign = scaled < 0 ? -1 : 1;
    return (sign * Math.round(Math.abs(scaled))) / factor;
}

export function formatFormulaNumber(value, decimals) {
    if (value == null || !Number.isFinite(Number(value))) return '';
    const digits = decimals == null ? null : Math.max(0, Math.min(6, Number(decimals) || 0));
    const rounded = digits == null ? Number(value) : roundHalfAway(Number(value), digits);
    if (!Number.isFinite(rounded)) return '';
    let text = digits == null
        ? rounded.toFixed(6).replace(/\.?0+$/, '')
        : rounded.toFixed(digits);
    if (text === '-0' || (text.startsWith('-0.') && Number(text) === 0)) {
        text = text.slice(1);
    }
    return text === '' ? '0' : text;
}

/** Display form of a calculated result, with the same thousands grouping as other matrix numbers. */
export function formatFormulaNumberForDisplay(value, decimals) {
    const plain = formatFormulaNumber(value, decimals);
    if (!plain) return '';
    const num = Number(plain);
    if (!Number.isFinite(num)) return plain;
    const digits = decimals == null || decimals === ''
        ? 6
        : Math.max(0, Math.min(6, Number(decimals) || 0));
    try {
        return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(num);
    } catch (e) {
        return plain;
    }
}

function unwrapCell(raw) {
    if (raw && typeof raw === 'object' && ('original' in raw || 'modified' in raw)) {
        if (raw.isModified) return raw.modified;
        if (raw.modified != null && raw.modified !== '') return raw.modified;
        return raw.original;
    }
    return raw;
}

function parseNumber(raw) {
    if (raw == null || raw === BLANK) return BLANK;
    if (typeof raw === 'boolean') return raw ? 1 : 0;
    if (typeof raw === 'number') return Number.isFinite(raw) ? raw : BLANK;
    const text = String(raw).trim().replace(/,/g, '').replace(/\u00a0/g, '').replace(/\u202f/g, '');
    if (!text) return BLANK;
    const lowered = text.toLowerCase();
    if (lowered === 'true') return 1;
    if (lowered === 'false') return 0;
    const number = Number(text);
    return Number.isFinite(number) ? number : BLANK;
}

export function cellFormulaInput(raw, columnType) {
    if (columnType === 'tick') {
        const value = unwrapCell(raw);
        if (value === true || value === 1 || value === '1' || value === 'true' || value === 'True' || value === 'yes' || value === 'Yes') {
            return 1;
        }
        return 0;
    }
    return parseNumber(unwrapCell(raw));
}

function formulaRefs(formula) {
    let tokens;
    try {
        tokens = tokenize(formula || '');
    } catch (e) {
        return braceRefs(formula);
    }
    const refs = [];
    tokens.forEach((token, index) => {
        if (token[0] === 'ref') {
            refs.push(token[1]);
        } else if (token[0] === 'id') {
            const next = tokens[index + 1];
            if (!(next && next[0] === 'punct' && next[1] === '(')) refs.push(token[1]);
        }
    });
    return refs;
}

function braceRefs(formula) {
    const refs = [];
    let index = 0;
    const text = formula || '';
    while (index < text.length) {
        const start = text.indexOf('{', index);
        if (start < 0) break;
        const end = text.indexOf('}', start + 1);
        if (end < 0) break;
        const name = text.slice(start + 1, end).trim();
        if (name) refs.push(name);
        index = end + 1;
    }
    return refs;
}

function tokenize(formula) {
    const tokens = [];
    let index = 0;
    const length = formula.length;
    while (index < length) {
        const char = formula[index];
        if (/\s/.test(char)) {
            index += 1;
            continue;
        }
        if (char === '{') {
            const end = formula.indexOf('}', index + 1);
            if (end < 0) throw new Error('Unclosed {');
            const name = formula.slice(index + 1, end).trim();
            if (!name) throw new Error('Empty column reference');
            tokens.push(['ref', name]);
            index = end + 1;
            continue;
        }
        if ('(),'.includes(char)) {
            tokens.push(['punct', char]);
            index += 1;
            continue;
        }
        const pair = formula.slice(index, index + 2);
        if (pair === '>=' || pair === '<=' || pair === '<>' || pair === '!=') {
            tokens.push(['op', pair === '!=' ? '<>' : pair]);
            index += 2;
            continue;
        }
        if ('+-*/><='.includes(char)) {
            tokens.push(['op', char]);
            index += 1;
            continue;
        }
        if (/\d/.test(char) || (char === '.' && index + 1 < length && /\d/.test(formula[index + 1]))) {
            let end = index;
            let seenDot = false;
            while (end < length && (/\d/.test(formula[end]) || (formula[end] === '.' && !seenDot))) {
                if (formula[end] === '.') seenDot = true;
                end += 1;
            }
            tokens.push(['num', Number(formula.slice(index, end))]);
            index = end;
            continue;
        }
        if (/[A-Za-z_]/.test(char)) {
            let end = index;
            while (end < length && /[A-Za-z0-9_]/.test(formula[end])) end += 1;
            tokens.push(['id', formula.slice(index, end)]);
            index = end;
            continue;
        }
        throw new Error(`Unexpected character '${char}'`);
    }
    tokens.push(['eof', null]);
    return tokens;
}

class Parser {
    constructor(tokens, values, blankAsZero, known) {
        this.tokens = tokens;
        this.i = 0;
        this.values = values;
        this.blankAsZero = blankAsZero;
        this.known = known;
    }

    peek() {
        return this.tokens[this.i];
    }

    is(kind, value) {
        const token = this.peek();
        if (token[0] !== kind) return false;
        return value == null || token[1] === value;
    }

    asNumber(value) {
        if (value === BLANK) return this.blankAsZero ? 0 : BLANK;
        return value;
    }

    arith(left, op, right) {
        const a = this.asNumber(left);
        const b = this.asNumber(right);
        if (a === BLANK || b === BLANK) return BLANK;
        if (op === '+') return a + b;
        if (op === '-') return a - b;
        if (op === '*') return a * b;
        if (op === '/') {
            if (b === 0) throw new Error('Division by zero');
            return a / b;
        }
        throw new Error(`Unexpected operator ${op}`);
    }

    compare(left, op, right) {
        const a = this.asNumber(left);
        const b = this.asNumber(right);
        if (a === BLANK || b === BLANK) return BLANK;
        const checks = {
            '>': a > b,
            '<': a < b,
            '>=': a >= b,
            '<=': a <= b,
            '=': a === b,
            '<>': a !== b,
        };
        return checks[op] ? 1 : 0;
    }

    parse() {
        if (this.is('eof')) throw new Error('Empty formula');
        const value = this.comparison();
        if (!this.is('eof')) throw new Error('Unexpected input');
        return value;
    }

    comparison() {
        let left = this.additive();
        while (this.is('op') && ['>', '<', '>=', '<=', '=', '<>'].includes(this.peek()[1])) {
            const op = this.tokens[this.i][1];
            this.i += 1;
            const right = this.additive();
            left = this.compare(left, op, right);
        }
        return left;
    }

    additive() {
        let left = this.multiplicative();
        while (this.is('op') && (this.peek()[1] === '+' || this.peek()[1] === '-')) {
            const op = this.tokens[this.i][1];
            this.i += 1;
            const right = this.multiplicative();
            left = this.arith(left, op, right);
        }
        return left;
    }

    multiplicative() {
        let left = this.unary();
        while (this.is('op') && (this.peek()[1] === '*' || this.peek()[1] === '/')) {
            const op = this.tokens[this.i][1];
            this.i += 1;
            const right = this.unary();
            left = this.arith(left, op, right);
        }
        return left;
    }

    unary() {
        if (this.is('op', '-')) {
            this.i += 1;
            const value = this.unary();
            const coerced = this.asNumber(value);
            if (coerced === BLANK) return BLANK;
            return -coerced;
        }
        return this.primary();
    }

    skipExpr() {
        let depth = 0;
        while (true) {
            const token = this.peek();
            if (token[0] === 'eof') throw new Error("Expected ')'");
            if (token[0] === 'punct' && token[1] === '(') depth += 1;
            else if (token[0] === 'punct' && token[1] === ')') {
                if (depth === 0) return;
                depth -= 1;
            } else if (token[0] === 'punct' && token[1] === ',' && depth === 0) {
                return;
            }
            this.i += 1;
        }
    }

    args(fname) {
        if (!this.is('punct', '(')) throw new Error(`Expected ( after ${fname}`);
        this.i += 1;
        const collected = [];
        if (this.is('punct', ')')) {
            this.i += 1;
            return collected;
        }
        while (true) {
            collected.push(this.comparison());
            if (this.is('punct', ',')) {
                this.i += 1;
                continue;
            }
            break;
        }
        if (!this.is('punct', ')')) throw new Error("Expected ')'");
        this.i += 1;
        return collected;
    }

    callIf() {
        if (!this.is('punct', '(')) throw new Error('Expected ( after IF');
        this.i += 1;
        const condition = this.comparison();
        if (!this.is('punct', ',')) throw new Error('IF needs 2 or 3 arguments');
        this.i += 1;
        const condNum = condition === BLANK ? 0 : condition;
        const taken = condNum !== 0;
        let value;
        if (taken) {
            value = this.comparison();
            if (this.is('punct', ',')) {
                this.i += 1;
                this.skipExpr();
            }
        } else {
            this.skipExpr();
            value = BLANK;
            if (this.is('punct', ',')) {
                this.i += 1;
                value = this.comparison();
            }
        }
        if (!this.is('punct', ')')) throw new Error("Expected ')'");
        this.i += 1;
        return value;
    }

    numericArgs(args) {
        return args.filter((arg) => arg !== BLANK).map((arg) => Number(arg));
    }

    call(fname, args) {
        if (fname === 'BLANK') {
            if (args.length) throw new Error('BLANK takes no arguments');
            return BLANK;
        }
        if (['SUM', 'AVERAGE', 'MIN', 'MAX', 'COUNT', 'COUNTA'].includes(fname)) {
            if (!args.length) throw new Error(`${fname} needs at least 1 argument`);
            if (fname === 'SUM') return this.numericArgs(args).reduce((sum, n) => sum + n, 0);
            if (fname === 'COUNT') return this.numericArgs(args).length;
            if (fname === 'COUNTA') return args.filter((arg) => arg !== BLANK).length;
            const numbers = this.numericArgs(args);
            if (!numbers.length) return BLANK;
            if (fname === 'AVERAGE') return numbers.reduce((sum, n) => sum + n, 0) / numbers.length;
            if (fname === 'MIN') return Math.min(...numbers);
            return Math.max(...numbers);
        }
        if (fname === 'ABS') {
            if (args.length !== 1) throw new Error('ABS needs 1 argument');
            const value = this.asNumber(args[0]);
            if (value === BLANK) return BLANK;
            return Math.abs(value);
        }
        if (fname === 'ROUND') {
            if (args.length !== 1 && args.length !== 2) throw new Error('ROUND needs 1 or 2 arguments');
            const value = this.asNumber(args[0]);
            if (value === BLANK) return BLANK;
            let digits = 0;
            if (args.length === 2) {
                const digitValue = this.asNumber(args[1]);
                digits = digitValue === BLANK ? 0 : Math.trunc(digitValue);
            }
            digits = Math.max(0, Math.min(6, digits));
            return roundHalfAway(value, digits);
        }
        throw new Error(`Unknown function ${fname}`);
    }

    primary() {
        const token = this.peek();
        if (token[0] === 'num') {
            this.i += 1;
            return Number(token[1]);
        }
        if (token[0] === 'ref') {
            this.i += 1;
            const name = token[1];
            if (Object.prototype.hasOwnProperty.call(this.values, name)) return this.values[name];
            if (!this.known.has(name)) throw new Error(`Unknown column {${name}}`);
            return BLANK;
        }
        if (token[0] === 'id') {
            const name = String(token[1]);
            const next = this.tokens[this.i + 1];
            if (next && next[0] === 'punct' && next[1] === '(') {
                const fname = name.toUpperCase();
                this.i += 1;
                if (fname === 'IF') return this.callIf();
                return this.call(fname, this.args(fname));
            }
            this.i += 1;
            if (Object.prototype.hasOwnProperty.call(this.values, name)) return this.values[name];
            if (!this.known.has(name)) throw new Error(`Unknown column ${name}`);
            return BLANK;
        }
        if (token[0] === 'punct' && token[1] === '(') {
            this.i += 1;
            const value = this.comparison();
            if (!this.is('punct', ')')) throw new Error("Expected ')'");
            this.i += 1;
            return value;
        }
        throw new Error('Unexpected input');
    }
}

function toResult(value, error) {
    if (error) return { value: null, error };
    if (value === BLANK || value == null) return { value: null, error: null };
    const number = Number(value);
    if (!Number.isFinite(number)) return { value: null, error: 'Not a number' };
    return { value: number, error: null };
}

export function evaluateFormula(formula, values, { blankAsZero = true, known = null } = {}) {
    const text = String(formula || '').trim();
    if (!text) throw new Error('Empty formula');
    const knownNames = new Set(known || Object.keys(values || {}));
    const parser = new Parser(tokenize(text), { ...(values || {}) }, blankAsZero, knownNames);
    return parser.parse();
}

export function checkFormulaSyntax(formula, knownNames) {
    try {
        const known = new Set(knownNames || []);
        const values = {};
        known.forEach((name) => {
            values[name] = 0;
        });
        evaluateFormula(formula, values, { blankAsZero: true, known });
        return null;
    } catch (error) {
        return error && error.message ? error.message : 'Invalid formula';
    }
}

function formulaText(column) {
    const calc = column && column.calculation;
    if (!calc || typeof calc !== 'object') return '';
    const operation = String(calc.operation || 'formula').trim().toLowerCase();
    if (operation === 'formula') return String(calc.formula || '').trim();
    return compileCalculation(calc);
}

function blankAsZero(column) {
    const calc = column && column.calculation;
    if (!calc || typeof calc !== 'object' || calc.blank_as_zero == null) return true;
    return calc.blank_as_zero !== false;
}

export function evaluateMatrixRow(columns, inputs) {
    const columnList = (columns || []).filter((col) => col && typeof col === 'object' && col.name);
    const known = new Set(columnList.map((col) => String(col.name)));
    const values = {};
    columnList.forEach((col) => {
        if (col.type === 'calculated') return;
        values[String(col.name)] = cellFormulaInput(inputs ? inputs[col.name] : undefined, col.type);
    });

    const pending = new Map();
    columnList.forEach((col) => {
        if (col.type === 'calculated') pending.set(String(col.name), col);
    });

    const results = {};
    let guard = 0;
    const limit = pending.size + 1;
    while (pending.size && guard < limit) {
        guard += 1;
        let progressed = false;
        Array.from(pending.entries()).forEach(([name, col]) => {
            if (!pending.has(name)) return;
            const formula = formulaText(col);
            const refs = formulaRefs(formula);
            if (refs.some((ref) => pending.has(ref))) return;
            progressed = true;
            try {
                const raw = evaluateFormula(formula, values, {
                    blankAsZero: blankAsZero(col),
                    known,
                });
                results[name] = toResult(raw);
            } catch (error) {
                results[name] = toResult(null, error && error.message ? error.message : 'Invalid formula');
            }
            values[name] = results[name].error == null && results[name].value != null
                ? results[name].value
                : BLANK;
            pending.delete(name);
        });
        if (!progressed) {
            Array.from(pending.keys()).forEach((name) => {
                results[name] = { value: null, error: 'Circular reference' };
                values[name] = BLANK;
                pending.delete(name);
            });
            break;
        }
    }
    return results;
}

function cssEscape(value) {
    const text = String(value);
    if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') return CSS.escape(text);
    return text.replace(/["\\]/g, '\\$&');
}

function calculationDecimals(column) {
    const calc = column && column.calculation;
    if (!calc || calc.decimals == null || calc.decimals === '') return 2;
    const digits = Number(calc.decimals);
    if (!Number.isFinite(digits)) return 2;
    return Math.max(0, Math.min(6, digits));
}

/**
 * Evaluate calculated columns for the given row ids.
 * Returns Map<rowId, { values: {name: number|null}, errors: {name: string} }>.
 */
export function evaluateCalculatedForRows(columns, data, rowIds) {
    const byRow = new Map();
    (rowIds || []).forEach((rowId) => {
        if (rowId == null || rowId === '') return;
        const inputs = {};
        (columns || []).forEach((col) => {
            if (!col || typeof col !== 'object' || !col.name || col.type === 'calculated') return;
            inputs[col.name] = data ? data[`${rowId}_${col.name}`] : undefined;
        });
        const results = evaluateMatrixRow(columns || [], inputs);
        const pack = { values: {}, errors: {} };
        Object.keys(results).forEach((name) => {
            const result = results[name];
            if (result && result.error) {
                pack.errors[name] = result.error;
                pack.values[name] = null;
            } else {
                pack.values[name] = result && result.value != null ? result.value : null;
            }
        });
        byRow.set(String(rowId), pack);
    });
    return byRow;
}

export function paintCalculatedCells(container, columns, byRow) {
    if (!container || !byRow) return;
    container.querySelectorAll('tr.matrix-data-row').forEach((tr) => {
        const rowId = tr.getAttribute('data-row-id');
        const pack = byRow.get(String(rowId));
        if (!pack) return;
        tr.querySelectorAll('[data-calculated="true"]').forEach((cell) => {
            const isInput = cell.tagName === 'INPUT';
            if (isInput && cell.dataset.userEdited === '1') return;
            const name = cell.getAttribute('data-column');
            const col = (columns || []).find((item) => item && item.name === name);
            const error = pack.errors[name];
            const blank = () => {
                if (isInput) {
                    cell.value = '';
                    cell.title = error || '';
                } else {
                    cell.textContent = '—';
                    cell.title = error || '';
                }
            };
            if (error) {
                blank();
                return;
            }
            const value = pack.values[name];
            if (value == null) {
                blank();
                return;
            }
            const shown = formatFormulaNumberForDisplay(value, calculationDecimals(col));
            if (isInput) {
                cell.value = shown;
                cell.title = '';
            } else {
                cell.textContent = shown;
                cell.title = '';
            }
        });
    });
}

export function cssEscapeColumn(value) {
    return cssEscape(value);
}
