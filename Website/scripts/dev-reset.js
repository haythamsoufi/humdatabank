#!/usr/bin/env node

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🧹 Clearing Next.js cache and node_modules...');

// Remove .next directory
const nextDir = path.join(__dirname, '..', '.next');
if (fs.existsSync(nextDir)) {
  fs.rmSync(nextDir, { recursive: true, force: true });
  console.log('✅ Removed .next directory');
}

// Remove node_modules
const nodeModulesDir = path.join(__dirname, '..', 'node_modules');
if (fs.existsSync(nodeModulesDir)) {
  fs.rmSync(nodeModulesDir, { recursive: true, force: true });
  console.log('✅ Removed node_modules directory');
}

console.log('📦 Reinstalling dependencies...');
execSync('npm install', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });

console.log('🚀 Starting development server...');
execSync('npm run dev', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
