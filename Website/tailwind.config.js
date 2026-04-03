    /** @type {import('tailwindcss').Config} */
    module.exports = {
      content: [
        './pages/**/*.{js,ts,jsx,tsx,mdx}',
        './components/**/*.{js,ts,jsx,tsx,mdx}',
        './app/**/*.{js,ts,jsx,tsx,mdx}', // If using App Router
      ],
      theme: {
        extend: {
          colors: {
            'ngodb-red': '#ED1C24', // Primary brand red
            'ngodb-red-dark': '#C91A20',
            'ngodb-red-light': '#FDE9E9',
            'ngodb-gray': {
              100: '#F7FAFC', // Lightest gray for backgrounds
              200: '#EDF2F7',
              300: '#E2E8F0',
              400: '#CBD5E0',
              500: '#A0AEC0', // Medium gray for text
              600: '#718096',
              700: '#4A5568', // Darker gray for text/elements
              800: '#2D3748',
              900: '#1A202C', // Darkest gray
            },
            'ngodb-blue': { // Accent blue
                50: '#eff6ff',
                100: '#dbeafe',
                200: '#bfdbfe',
                300: '#93c5fd',
                400: '#60a5fa',
                500: '#3b82f6',
                600: '#2563eb',
                700: '#1d4ed8',
                800: '#1e40af',
                900: '#1e3a8a',
                950: '#172554',
            },
            'ngodb-green': '#28A745', // Success green
            'ngodb-green-dark': '#1E7E34',
            'ngodb-blue-dark': '#1E40AF',
             // Brand navy (from site theme)
            'ngodb-navy': '#011E41',
            'ngodb-black': '#000000', // Added black
            'ngodb-white': '#FFFFFF', // Added white
          },
          fontFamily: {
            sans: ['Inter', 'sans-serif'], // Using Inter as a modern, clean font
            tajawal: ['Tajawal', 'Inter', 'sans-serif'], // Arabic font
          },
        },
      },
      plugins: [
        require('@tailwindcss/typography'),
        require('@tailwindcss/forms'),
        require('@tailwindcss/aspect-ratio'),
        // line-clamp is now built-in to Tailwind CSS 3.3+
      ],
    };
