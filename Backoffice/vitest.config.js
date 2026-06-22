import { defineConfig } from 'vitest/config';

export default defineConfig({
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
