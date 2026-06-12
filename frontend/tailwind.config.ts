import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        void: '#030305',
        ink: '#0c0c16',
        slate: {
          925: '#0f0f1a',
          950: '#0a0a12',
        },
        indigo: {
          450: '#7c84f5',
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'mesh-1': 'radial-gradient(ellipse at 20% 50%, rgba(99,102,241,0.15) 0%, transparent 50%)',
        'mesh-2': 'radial-gradient(ellipse at 80% 20%, rgba(168,85,247,0.1) 0%, transparent 50%)',
        'mesh-3': 'radial-gradient(ellipse at 60% 80%, rgba(236,72,153,0.07) 0%, transparent 50%)',
      },
      animation: {
        'fade-up': 'fadeUp 0.6s ease-out forwards',
        'fade-in': 'fadeIn 0.4s ease-out forwards',
        'glow-pulse': 'glowPulse 3s ease-in-out infinite',
        'shimmer': 'shimmer 1.5s ease-in-out infinite',
        'cursor-blink': 'cursorBlink 1s step-end infinite',
        'float': 'float 6s ease-in-out infinite',
        'gradient-x': 'gradientX 4s ease infinite',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        glowPulse: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '0.8' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        cursorBlink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        gradientX: {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      boxShadow: {
        'glow-sm': '0 0 20px rgba(99,102,241,0.15)',
        'glow-md': '0 0 40px rgba(99,102,241,0.2)',
        'glow-lg': '0 0 80px rgba(99,102,241,0.25)',
        'glass': '0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)',
      },
    },
  },
  plugins: [],
};

export default config;
