import path from 'path';
import { fileURLToPath } from 'url';
import { defineConfig } from 'vitest/config';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
    resolve: {
        alias: {
            '/static': path.resolve(rootDir, 'app/static'),
        },
    },
    test: {
        environment: 'jsdom',
        globals: true,
        include: ['tests/js/**/*.test.js'],
        exclude: ['tests/js/data-exploration-analysis-core.test.js'],
        coverage: {
            provider: 'v8',
            include: ['app/static/js/form_builder/**/*.js'],
            reporter: ['text', 'html'],
        },
    },
});
