import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { cpSync, existsSync, rmSync, readFileSync, writeFileSync } from 'fs'

// Custom plugin to copy public assets and fix HTML location
function postBuildPlugin() {
  return {
    name: 'post-build-plugin',
    closeBundle() {
      const distDir = resolve(__dirname, 'dist')
      const publicDir = resolve(__dirname, 'public')
      
      // Move HTML from src/sidepanel to sidepanel
      const srcHtmlDir = resolve(distDir, 'src/sidepanel')
      const destHtmlDir = resolve(distDir, 'sidepanel')
      
      if (existsSync(srcHtmlDir)) {
        // Copy HTML to correct location
        cpSync(srcHtmlDir, destHtmlDir, { recursive: true })
        // Remove src directory
        rmSync(resolve(distDir, 'src'), { recursive: true, force: true })
        console.log('Fixed HTML location')
      }
      
      // Fix paths in index.html
      const htmlPath = resolve(destHtmlDir, 'index.html')
      if (existsSync(htmlPath)) {
        let html = readFileSync(htmlPath, 'utf-8')
        // Fix the relative paths - they were calculated from src/sidepanel
        html = html.replace(/\.\.\/\.\.\/sidepanel\//g, './')
        html = html.replace(/\.\.\/\.\.\/assets\//g, '../assets/')
        writeFileSync(htmlPath, html)
        console.log('Fixed HTML paths')
      }
      
      // Copy public assets to dist
      if (existsSync(publicDir)) {
        cpSync(publicDir, distDir, { recursive: true })
        console.log('Copied public assets to dist')
      }
    }
  }
}

export default defineConfig({
  plugins: [react(), postBuildPlugin()],
  base: './',  // Use relative paths for Chrome extension
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    minify: true,
    rollupOptions: {
      input: {
        sidepanel: resolve(__dirname, 'src/sidepanel/index.html'),
        'service-worker': resolve(__dirname, 'src/background/service-worker.ts'),
        'codegen-recorder': resolve(__dirname, 'src/content/codegen-recorder.ts'),
      },
      output: {
        entryFileNames: (chunkInfo) => {
          if (chunkInfo.name === 'service-worker') {
            return 'background/service-worker.js'
          }
          if (chunkInfo.name === 'codegen-recorder') {
            return 'content/codegen-recorder.js'
          }
          return 'sidepanel/[name].js'
        },
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith('.css')) {
            return 'sidepanel/[name][extname]'
          }
          return 'assets/[name]-[hash][extname]'
        },
        // Prevent code splitting for service worker and content script
        manualChunks: undefined,
      },
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
