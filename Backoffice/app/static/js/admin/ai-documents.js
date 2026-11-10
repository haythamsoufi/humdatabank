/**
 * AI Knowledge Base page entry.
 *
 * This used to be one IIFE so a classic script tag would not put every helper
 * on window. ES modules keep that privacy per file and can be imported by
 * tests. The knowledge-base import map (static_import_map.knowledge_base_import_map)
 * cache-busts these relative imports the same way the entry form does.
 * Job progress stays a classic script on window.AiDocsJobProgress because the
 * floating banner script loads before this module.
 */

import { initAskAi } from './ai-documents/ask.js';
import { initDocumentsBulkActions } from './ai-documents/bulk.js';
import { initDocumentsGrid } from './ai-documents/grid.js';
import { initGuidanceDocumentsTab } from './ai-documents/guidance.js';
import { initIfrcImport } from './ai-documents/import-ifrc.js';
import { initImportSystem } from './ai-documents/import-system.js';
import { initAiDocsJobProgress } from './ai-documents/jobs.js';
import { initUploadModal } from './ai-documents/modal.js';
import { onReady } from './ai-documents/shared.js';
import { initUploadForm } from './ai-documents/upload.js';

onReady(function () {
    initDocumentsGrid();
    initAiDocsJobProgress();
    initDocumentsBulkActions();
    initUploadForm();
    initUploadModal();
    initImportSystem();
    initIfrcImport();
    initGuidanceDocumentsTab();
    initAskAi();
});
