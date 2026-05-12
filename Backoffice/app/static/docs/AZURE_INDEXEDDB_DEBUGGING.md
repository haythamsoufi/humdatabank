# Debugging IndexedDB Issues in Azure App Service Container

This guide helps you understand and diagnose why IndexedDB might be failing in Azure Container environments.

## Quick Diagnosis

### In Browser Console

1. **Quick Check:**
```javascript
quickIndexedDBCheck()
```

2. **Full Diagnostic:**
```javascript
diagnoseIndexedDB()
```

3. **Or add to URL:**
```
https://your-app.azurewebsites.net/admin/templates?diagnoseIndexedDB=true
```

## Common Causes in Azure Container Environments

### 1. **Secure Context Requirement**

IndexedDB requires a secure context (HTTPS or localhost). Azure App Services typically use HTTPS, but check:

**Symptoms:**
- IndexedDB is `undefined` or `null`
- Errors about secure context

**Check:**
```javascript
window.isSecureContext  // Should be true
window.location.protocol  // Should be "https:"
```

**Solution:**
- Ensure your Azure App Service is configured for HTTPS
- Check if you're being redirected to HTTP
- Verify SSL certificate is valid

### 2. **Storage Quota Exceeded**

Azure containers may have storage limitations or quota restrictions.

**Symptoms:**
- `QuotaExceededError`
- Database open fails silently
- Transaction errors

**Check:**
```javascript
navigator.storage.estimate().then(estimate => {
  console.log('Quota:', estimate.quota);
  console.log('Usage:', estimate.usage);
  console.log('Available:', estimate.quota - estimate.usage);
});
```

**Solution:**
- Clear old databases: `indexedDB.databases().then(dbs => dbs.forEach(db => indexedDB.deleteDatabase(db.name)))`
- Implement database cleanup routines
- Request storage persistence: `navigator.storage.persist()`

### 3. **Private/Incognito Mode**

Some browsers restrict IndexedDB in private mode, which may be triggered by certain Azure proxy configurations.

**Symptoms:**
- Storage works initially but fails later
- `NotFoundError` when trying to access databases
- Quota shows as very small (e.g., ~120MB)

**Check:**
```javascript
navigator.storage.persist().then(persistent => {
  console.log('Persistent storage:', persistent);
});
```

**Solution:**
- Check if user is in private/incognito mode
- Implement fallback to sessionStorage or memory storage
- Warn users about storage limitations in private mode

### 4. **Third-Party Proxy/CDN Interference**

Azure's CDN or proxy layers might interfere with IndexedDB operations.

**Symptoms:**
- Intermittent failures
- Timeout errors
- Errors only in production, not locally

**Check:**
- Compare behavior in localhost vs Azure
- Check Azure Front Door/CDN settings
- Review Azure App Service proxy configuration

**Solution:**
- Bypass CDN for IndexedDB operations (if possible)
- Add retry logic with exponential backoff
- Use Service Workers carefully (they can interfere)

### 5. **Content Security Policy (CSP)**

CSP headers might block IndexedDB operations.

**Symptoms:**
- Errors in console about CSP violations
- IndexedDB works in some pages but not others

**Check:**
```javascript
const metaCSP = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
console.log('CSP:', metaCSP ? metaCSP.getAttribute('content') : 'None');
```

**Solution:**
- Review CSP headers in Azure App Service configuration
- Ensure CSP allows IndexedDB operations
- Check for `unsafe-eval` or other restrictive policies

### 6. **Service Worker Conflicts**

Service Workers registered on Azure might conflict with IndexedDB.

**Symptoms:**
- Errors only after page load
- Database blocked errors
- Multiple tabs causing issues

**Check:**
```javascript
navigator.serviceWorker.getRegistrations().then(regs => {
  console.log('Service Workers:', regs.length);
});
```

**Solution:**
- Unregister service workers on admin pages (already implemented)
- Ensure service workers don't interfere with IndexedDB
- Use unique database names per page/feature

### 7. **Browser Compatibility**

Some browsers or versions may have IndexedDB issues.

**Symptoms:**
- Works in Chrome but not Firefox (or vice versa)
- Works on desktop but not mobile
- Specific browser version issues

**Check:**
```javascript
console.log('User Agent:', navigator.userAgent);
console.log('IndexedDB available:', typeof indexedDB !== 'undefined');
```

**Solution:**
- Implement feature detection
- Provide fallbacks for unsupported browsers
- Use polyfills if necessary (but beware of polyfill bugs)

### 8. **Database Version Conflicts**

Multiple versions of your app trying to open different database versions.

**Symptoms:**
- `VersionError`
- Database upgrade failures
- Intermittent errors

**Check:**
```javascript
indexedDB.databases().then(dbs => {
  console.log('All databases:', dbs);
});
```

**Solution:**
- Implement proper version migration
- Close old database connections
- Use unique database names per app version

### 9. **Azure App Service Configuration**

Azure-specific settings might affect IndexedDB.

**Check Azure Settings:**
- Storage account configuration
- App Service plan limitations
- Resource quotas
- Proxy/load balancer settings
- SSL/TLS configuration

**Common Azure Issues:**
- **Storage Account Quota**: Check if storage quota is reached
- **App Service Plan**: Free/shared tiers may have limitations
- **Regional Restrictions**: Some regions may have different policies
- **VNet/Network Restrictions**: Network policies might interfere

### 10. **Third-Party Library Interference**

Libraries or polyfills might be interfering.

**Symptoms:**
- Errors from polyfill.js or other libraries
- Works after removing certain scripts
- Errors mention specific library names

**Solution:**
- Check console for library errors
- Temporarily disable third-party scripts
- Review library documentation for IndexedDB compatibility
- Use library-specific error handling (already implemented)

## Step-by-Step Debugging Process

### Step 1: Run Full Diagnostic

```javascript
const results = await diagnoseIndexedDB();
console.table(results);
```

### Step 2: Check Environment

```javascript
console.log('Environment:', {
  isAzure: window.location.hostname.includes('azure'),
  isSecure: window.isSecureContext,
  protocol: window.location.protocol,
  userAgent: navigator.userAgent
});
```

### Step 3: Test Basic IndexedDB

```javascript
const testDB = indexedDB.open('test_db', 1);
testDB.onsuccess = () => console.log('✅ IndexedDB works!');
testDB.onerror = (e) => console.error('❌ IndexedDB failed:', e.target.error);
```

### Step 4: Check Storage Quota

```javascript
navigator.storage.estimate().then(estimate => {
  const mb = (bytes) => (bytes / 1024 / 1024).toFixed(2) + ' MB';
  console.log({
    quota: mb(estimate.quota),
    usage: mb(estimate.usage),
    available: mb(estimate.quota - estimate.usage),
    percent: ((estimate.usage / estimate.quota) * 100).toFixed(2) + '%'
  });
});
```

### Step 5: Check for Blocked Databases

```javascript
indexedDB.databases().then(dbs => {
  console.log('All databases:', dbs);
  dbs.forEach(db => {
    console.log(`Database: ${db.name}, Version: ${db.version}`);
  });
});
```

### Step 6: Monitor Network Tab

- Open Developer Tools → Network tab
- Look for failed requests related to storage
- Check for CORS or CSP violations
- Monitor service worker activity

### Step 7: Check Console for Errors

- Look for IndexedDB-specific errors
- Check for polyfill errors
- Review CSP violations
- Check for service worker errors

## Solutions Already Implemented

1. **Graceful Degradation**: The app handles IndexedDB failures gracefully
2. **Error Handling**: Comprehensive error handling in `public-drafts.js`
3. **Global Error Handlers**: Catches and suppresses non-critical IndexedDB errors
4. **Feature Detection**: Checks for IndexedDB availability before use
5. **Fallback Storage**: Falls back to sessionStorage or memory when IndexedDB fails

## Testing in Azure

### Local Testing

```bash
# Test locally first
py -m flask run

# Check console: diagnoseIndexedDB()
```

### Azure Deployment

1. Deploy to Azure
2. Open browser console
3. Run: `diagnoseIndexedDB()`
4. Review results
5. Check Azure App Service logs

### Azure App Service Logs

```bash
# View logs
az webapp log tail --name <app-name> --resource-group <resource-group>

# Or in Azure Portal:
# App Service → Log stream
```

## Additional Resources

- [MDN: IndexedDB API](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API)
- [MDN: Using IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB)
- [Azure App Service Documentation](https://docs.microsoft.com/en-us/azure/app-service/)
- [Browser Storage Limits](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)

## Reporting Issues

When reporting IndexedDB issues, include:

1. Full diagnostic output: `diagnoseIndexedDB()`
2. Browser and version
3. Azure App Service configuration
4. Error messages from console
5. Network tab screenshots
6. Steps to reproduce
