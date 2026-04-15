#!/usr/bin/env node

/**
 * Optimized build script for the Humanitarian Databank Website
 * This script implements better connection management to prevent database
 * connection pool exhaustion during the build process.
 */

const { spawn } = require('child_process');
const path = require('path');

console.log('🚀 Starting optimized build process...');

// Set environment variables for optimized build
process.env.BUILD_TIME = 'true';
process.env.NEXT_TELEMETRY_DISABLED = '1';

// Reduce concurrent processing to prevent database connection exhaustion
process.env.NODE_OPTIONS = '--max-old-space-size=4096';

console.log('📊 Build configuration:');
console.log('- BUILD_TIME:', process.env.BUILD_TIME);
console.log('- NODE_OPTIONS:', process.env.NODE_OPTIONS);
console.log('- NODE_ENV:', process.env.NODE_ENV);

// Function to run build with retry logic
function runBuild(retryCount = 0) {
  return new Promise((resolve, reject) => {
    console.log(`\n🔨 Starting build attempt ${retryCount + 1}...`);

    const buildProcess = spawn('npx', ['next', 'build'], {
      stdio: 'inherit',
      env: { ...process.env },
      cwd: __dirname
    });

    buildProcess.on('close', (code) => {
      if (code === 0) {
        console.log('\n✅ Build completed successfully!');
        resolve();
      } else {
        console.error(`\n❌ Build failed with exit code ${code}`);

        if (retryCount < 2) {
          console.log(`\n🔄 Retrying build in 10 seconds... (attempt ${retryCount + 2}/3)`);
          setTimeout(() => {
            runBuild(retryCount + 1).then(resolve).catch(reject);
          }, 10000);
        } else {
          reject(new Error(`Build failed after ${retryCount + 1} attempts`));
        }
      }
    });

    buildProcess.on('error', (error) => {
      console.error('\n💥 Build process error:', error);
      reject(error);
    });
  });
}

// Main execution
async function main() {
  try {
    await runBuild();
    console.log('\n🎉 Optimized build completed successfully!');
    process.exit(0);
  } catch (error) {
    console.error('\n💥 Build failed:', error.message);
    process.exit(1);
  }
}

// Handle process termination
process.on('SIGINT', () => {
  console.log('\n⚠️  Build interrupted by user');
  process.exit(1);
});

process.on('SIGTERM', () => {
  console.log('\n⚠️  Build terminated');
  process.exit(1);
});

main();
