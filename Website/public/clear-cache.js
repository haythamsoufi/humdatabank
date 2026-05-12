// Clear cache and service worker script
// Prevent service worker registration to avoid local network permission prompts
(function() {
  'use strict';

  if ('serviceWorker' in navigator) {
    // Immediately unregister any existing service workers
    navigator.serviceWorker.getRegistrations().then(function(registrations) {
      for(let registration of registrations) {
        registration.unregister().catch(function(err) {
          console.warn('Service worker unregistration failed:', err);
        });
      }
    }).catch(function(err) {
      console.warn('Failed to get service worker registrations:', err);
    });

    // Also try to unregister by common service worker paths
    ['/sw.js', '/service-worker.js'].forEach(function(path) {
      navigator.serviceWorker.getRegistration(path).then(function(registration) {
        if (registration) {
          registration.unregister().catch(function(err) {
            console.warn('Failed to unregister service worker at ' + path + ':', err);
          });
        }
      }).catch(function(err) {
        // Ignore errors if registration doesn't exist
      });
    });
  }
})();

// Clear all caches
if ('caches' in window) {
  caches.keys().then(function(names) {
    for (let name of names) {
      caches.delete(name);
    }
  });
}

// Clear localStorage and sessionStorage, but preserve dataviz cache
const datavizKeys = [
  'dataviz_selected_sector',
  'dataviz_selected_indicator',
  'dataviz_selected_countries',
  'dataviz_selected_chart_type',
  'dataviz_selected_years',
  'dataviz_chart_data',
  'dataviz_summary_stats'
];

// Store dataviz data temporarily
const datavizData = {};
datavizKeys.forEach(key => {
  const value = localStorage.getItem(key);
  if (value !== null) {
    datavizData[key] = value;
  }
});

// Clear all localStorage
localStorage.clear();

// Restore dataviz data
Object.entries(datavizData).forEach(([key, value]) => {
  localStorage.setItem(key, value);
});

sessionStorage.clear();

console.log('Cache and service worker cleared');
