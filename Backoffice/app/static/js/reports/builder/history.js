/** Simple undo/redo stack for report definition snapshots. */

export class HistoryStack {
    constructor(limit) {
        this.limit = limit || 40;
        this.undoStack = [];
        this.redoStack = [];
    }

    snapshot(definition) {
        return JSON.stringify(definition);
    }

    push(definition) {
        const snap = this.snapshot(definition);
        if (this.undoStack.length && this.undoStack[this.undoStack.length - 1] === snap) return;
        this.undoStack.push(snap);
        if (this.undoStack.length > this.limit) this.undoStack.shift();
        this.redoStack = [];
    }

    canUndo() {
        return this.undoStack.length > 1;
    }

    canRedo() {
        return this.redoStack.length > 0;
    }

    undo(currentDefinition) {
        if (!this.canUndo()) return null;
        const current = this.snapshot(currentDefinition);
        this.redoStack.push(current);
        this.undoStack.pop();
        return JSON.parse(this.undoStack[this.undoStack.length - 1]);
    }

    redo() {
        if (!this.canRedo()) return null;
        const next = this.redoStack.pop();
        this.undoStack.push(next);
        return JSON.parse(next);
    }
}
