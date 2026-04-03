#!/usr/bin/env node

const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🚀 Starting safe development server...');

// Function to clear all caches
function clearCaches() {
  const cacheDirs = [
    path.join(__dirname, '..', '.next'),
    path.join(__dirname, '..', 'node_modules', '.cache'),
    path.join(__dirname, '..', '.next', 'cache'),
  ];

  cacheDirs.forEach(dir => {
    if (fs.existsSync(dir)) {
      try {
        fs.rmSync(dir, { recursive: true, force: true });
        console.log(`✅ Cleared cache: ${path.basename(dir)}`);
      } catch (error) {
        console.log(`⚠️ Could not clear ${dir}: ${error.message}`);
      }
    }
  });
}

// Function to start development server with retry logic
function startDevServer() {
  console.log('🏗️ Starting Next.js development server...');

  const devProcess = spawn('npm', ['run', 'dev'], {
    cwd: path.join(__dirname, '..'),
    stdio: 'inherit',
    shell: true
  });

  devProcess.on('error', (error) => {
    console.log('❌ Development server failed to start:', error.message);
    console.log('🔄 Clearing caches and retrying...');
    clearCaches();
    setTimeout(() => startDevServer(), 2000);
  });

  devProcess.on('exit', (code) => {
    if (code !== 0) {
      console.log(`❌ Development server exited with code ${code}`);
      console.log('🔄 Clearing caches and retrying...');
      clearCaches();
      setTimeout(() => startDevServer(), 2000);
    }
  });

  // Handle Ctrl+C gracefully
  process.on('SIGINT', () => {
    console.log('\n🛑 Shutting down development server...');
    devProcess.kill('SIGINT');
    process.exit(0);
  });
}

// Initial cache clear
clearCaches();

// Start the development server
startDevServer();
