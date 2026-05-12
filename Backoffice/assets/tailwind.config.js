/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js"
  ],
  safelist: [
    'bg-yellow-600',
    'bg-yellow-700',
    'hover:bg-yellow-700',
    'focus:ring-yellow-600',
    'bg-teal-600',
    'hover:bg-teal-700',
    'bg-amber-600',
    'bg-amber-700',
    'hover:bg-amber-700',
    'focus:ring-amber-500'
  ],
  theme: {
    extend: {
      /* Use theme.css variables so button colors can be changed globally (primary = teal) */
      colors: {
        blue: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: 'var(--btn-primary, #0d9488)',
          700: 'var(--btn-primary-hover, #0f766e)',
          800: 'var(--btn-primary-active, #115e59)',
          900: '#134e4a',
        },
        teal: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: 'var(--btn-primary, #0d9488)',
          700: 'var(--btn-primary-hover, #0f766e)',
          800: 'var(--btn-primary-active, #115e59)',
          900: '#134e4a',
        },
        green: {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#22c55e',
          600: 'var(--btn-success, #16a34a)',
          700: 'var(--btn-success-hover, #15803d)',
          800: 'var(--btn-success-active, #166534)',
          900: '#14532d',
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms')
  ],
}
