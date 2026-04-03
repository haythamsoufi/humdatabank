#!/usr/bin/env node

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🔄 Restarting development server...');

// Clear Next.js cache
const nextDir = path.join(__dirname, '..', '.next');
if (fs.existsSync(nextDir)) {
  fs.rmSync(nextDir, { recursive: true, force: true });
  console.log('✅ Cleared .next cache');
}

// Start development server
try {
  execSync('npm run dev', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
} catch (error) {
  console.log('❌ Failed to start development server:', error.message);
}
