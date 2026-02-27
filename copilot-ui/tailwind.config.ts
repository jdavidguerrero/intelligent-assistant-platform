import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        push: {
          bg:           '#0F0F0F',
          surface:      '#1A1A1A',
          elevated:     '#222222',
          border:       '#2E2E2E',
          text:         '#FFFFFF',
          muted:        '#888888',
          orange:       '#FF7700',
          'orange-dim': '#993300',
          green:        '#7EB13D',
          red:          '#E53935',
          yellow:       '#E5C020',
          meter: {
            green:  '#3D8D40',
            yellow: '#B5A020',
            red:    '#B02020',
          },
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Consolas', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

export default config
