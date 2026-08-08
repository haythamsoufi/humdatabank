/** GridStack wrapper for section widget layouts. */

export class GridEngine {
    constructor(options) {
        this.options = options || {};
        this.instances = new Map();
    }

    async ensureLibrary() {
        if (window.GridStack) return window.GridStack;
        const src = this.options.scriptSrc || '/static/libs/gridstack/gridstack-all.js';
        await new Promise(function (resolve, reject) {
            if (document.querySelector('script[src="' + src + '"]') && window.GridStack) {
                resolve();
                return;
            }
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
        return window.GridStack;
    }

    async mount(host, section, handlers) {
        const GridStack = await this.ensureLibrary();
        host.innerHTML = '';
        host.classList.add('rb-grid-host');
        const grid = GridStack.init({
            column: section.grid?.columns || 12,
            cellHeight: section.grid?.row_height || 80,
            margin: 8,
            float: false,
            disableOneColumnMode: false,
            animate: true,
            draggable: { handle: '.rb-editor-slot-toolbar' },
            rtl: !!this.options.rtl
        }, host);
        this.instances.set(section.id, grid);

        (section.widgets || []).forEach(function (widget) {
            const item = document.createElement('div');
            item.className = 'grid-stack-item rb-editor-slot';
            item.dataset.widgetId = widget.id;
            item.dataset.sectionId = section.id;
            item.innerHTML = '<div class="grid-stack-item-content"></div>';
            const layout = widget.layout || { x: 0, y: 0, w: 12, h: 4 };
            grid.addWidget(item, {
                x: layout.x,
                y: layout.y,
                w: layout.w,
                h: layout.h,
                id: widget.id
            });
            handlers.renderSlotContent(item.querySelector('.grid-stack-item-content'), widget, section);
        });

        grid.on('change', function (_event, items) {
            handlers.onLayoutChange(section.id, items || []);
        });
        return grid;
    }

    destroy(sectionId) {
        const grid = this.instances.get(sectionId);
        if (grid) {
            grid.destroy(false);
            this.instances.delete(sectionId);
        }
    }

    destroyAll() {
        this.instances.forEach(function (grid) { grid.destroy(false); });
        this.instances.clear();
    }
}
