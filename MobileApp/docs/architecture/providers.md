# Provider Architecture Documentation

## Overview

The IFRC Network Databank mobile app uses the **Provider** pattern for state management. This document outlines the provider hierarchy, dependencies, and architectural decisions.

## Provider Hierarchy

```
MyApp (root)
  ├── Core Providers (always loaded at startup)
  │   ├── AuthProvider
  │   ├── DashboardProvider (uses DashboardRepository)
  │   ├── NotificationProvider
  │   ├── LanguageProvider
  │   ├── ThemeProvider
  │   ├── OfflineProvider
  │   └── IndicatorBankProvider
  │
  └── Admin Providers (loaded but lightweight until first use)
      ├── AdminDashboardProvider
      ├── TemplatesProvider
      ├── AssignmentsProvider
      ├── UsersProvider
      ├── DocumentManagementProvider
      ├── TranslationManagementProvider
      ├── PluginManagementProvider
      ├── ResourcesManagementProvider
      ├── OrganizationalStructureProvider
      ├── IndicatorBankAdminProvider
      ├── UserAnalyticsProvider
      ├── AuditTrailProvider
      └── ApiManagementProvider
```

## Core Providers

### AuthProvider (`providers/shared/auth_provider.dart`)
**Purpose:** Manages user authentication state

**Responsibilities:**
- User login/logout
- User profile management
- Session state tracking

**Dependencies:**
- `AuthService` - Authentication logic
- `StorageService` - Secure credential storage
- `UserProfileService` - Profile updates

**Used By:**
- Most providers (via context) for checking authentication status
- All authenticated screens

---

### DashboardProvider (`providers/shared/dashboard_provider.dart`)
**Purpose:** Manages dashboard data state

**Responsibilities:**
- Loading state management
- Error state management
- Notifying UI of state changes

**Data Access:**
- Delegates to `DashboardRepository` for:
  - API calls
  - Caching
  - Data parsing

**Dependencies:**
- `DashboardRepository` - Data access layer

**State:**
- `currentAssignments` - List of current assignments
- `pastAssignments` - List of past assignments
- `entities` - List of available entities
- `selectedEntity` - Currently selected entity
- `isLoading` - Loading state
- `error` - Error message

**Methods:**
- `loadDashboard(forceRefresh)` - Load dashboard data
- `selectEntity(entity)` - Select and update entity
- `loadEntities()` - Load entities from cache
- `clearCache()` - Clear cached data

**Architecture:**
- Follows **Repository Pattern** - business logic extracted to `DashboardRepository`
- Provider focuses on UI state management only

---

### NotificationProvider (`providers/shared/notification_provider.dart`)
**Purpose:** Manages notification state

**Responsibilities:**
- Notification list management
- Unread count tracking
- Mark as read operations

**Dependencies:**
- `NotificationService` - Notification data access

---

### LanguageProvider (`providers/shared/language_provider.dart`)
**Purpose:** Manages app language selection

**Responsibilities:**
- Current language state
- Language switching
- Locale management

**Dependencies:**
- `StorageService` - Language preference persistence

---

### ThemeProvider (`providers/shared/theme_provider.dart`)
**Purpose:** Manages app theme (light/dark mode)

**Responsibilities:**
- Theme state management
- Theme switching

**Dependencies:**
- `StorageService` - Theme preference persistence

---

### OfflineProvider (`providers/shared/offline_provider.dart`)
**Purpose:** Manages offline state and sync operations

**Responsibilities:**
- Network status monitoring
- Queued request management
- Sync operations

**Dependencies:**
- `ConnectivityService` - Network status
- `OfflineQueueService` - Request queuing
- `OfflineCacheService` - Response caching

---

### IndicatorBankProvider (`providers/public/indicator_bank_provider.dart`)
**Purpose:** Manages indicator bank data

**Responsibilities:**
- Indicator list management
- Search and filtering
- Loading state

**Dependencies:**
- `ApiService` - Indicator data access

---

## Admin Providers

Admin providers follow a **lazy loading** pattern:
- Created at app startup (lightweight)
- Data loaded on-demand via `load*` methods
- Persist for app lifetime but don't consume resources until used

### AdminDashboardProvider
**Purpose:** Admin dashboard statistics

**Dependencies:**
- `ApiService` - Stats data access

---

### TemplatesProvider
**Purpose:** Template management

**Dependencies:**
- `ApiService` - Template data access

---

### AssignmentsProvider
**Purpose:** Assignment management

**Dependencies:**
- `ApiService` - Assignment data access

---

### UsersProvider
**Purpose:** User management

**Dependencies:**
- `ApiService` - User data access

---

(Similar pattern for other admin providers)

---

## Architecture Patterns

### 1. Repository Pattern

**Used in:** `DashboardProvider`

**Benefits:**
- Separates data access from state management
- Easier to test (repository can be mocked)
- Clear separation of concerns
- Reusable data access logic

**Example:**
```dart
// Provider focuses on UI state
class DashboardProvider with ChangeNotifier {
  final DashboardRepository _repository = DashboardRepository();
  
  Future<void> loadDashboard() async {
    _isLoading = true;
    notifyListeners();
    
    final data = await _repository.loadDashboardFromApi();
    // Update state
    _updateStateFromData(data);
    
    _isLoading = false;
    notifyListeners();
  }
}

// Repository handles data access
class DashboardRepository {
  Future<DashboardData?> loadDashboardFromApi() async {
    // API calls, parsing, caching logic
  }
}
```

---

### 2. Single Responsibility Principle

Each provider has a clear, single responsibility:
- **AuthProvider**: Authentication only
- **DashboardProvider**: Dashboard UI state only (delegates data access)
- **NotificationProvider**: Notifications only
- etc.

---

### 3. Dependency Injection

Providers inject services rather than creating them directly:
```dart
class DashboardProvider {
  final DashboardRepository _repository = DashboardRepository();
  // Repository handles its own dependencies (ApiService, StorageService, etc.)
}
```

---

### 4. Lazy Loading (Admin Providers)

Admin providers are created at startup but don't load data until needed:
```dart
// Provider created at startup (lightweight)
ChangeNotifierProvider(create: (_) => AdminDashboardProvider()),

// Data loaded on-demand when screen is accessed
class AdminDashboardProvider {
  Future<void> loadDashboardStats() async {
    // Load data here (not in constructor)
  }
}
```

---

## Provider Lifecycle

### Initialization
1. **App Startup**: All providers created in `main.dart`
2. **Core Providers**: Initialize immediately (lightweight operations)
3. **Admin Providers**: Created but don't initialize until first use

### State Updates
1. User action triggers provider method
2. Provider updates internal state
3. Provider calls `notifyListeners()`
4. UI rebuilds via `Consumer<T>` or `Provider.of<T>(context)`

### Cleanup
- Providers automatically disposed when app is removed from widget tree
- Resources cleaned up via `dispose()` method (if needed)

---

## Best Practices

### 1. Keep Providers Focused
- Each provider should have a single responsibility
- Extract business logic to services or repositories
- Use providers for UI state management only

### 2. Use Repositories for Data Access
- Move data access logic (API calls, caching, parsing) to repositories
- Providers should delegate to repositories
- Makes code more testable and maintainable

### 3. Avoid Circular Dependencies
- Providers should not depend on each other directly
- Use `ProxyProvider` for dependent state (if needed)
- Access other providers via context when needed

### 4. Minimize Provider Count
- Only create providers for state that needs to be shared
- Use local state (`StatefulWidget`) for screen-specific state
- Don't create providers for simple data passing

### 5. Handle Loading and Error States
- Always track loading state
- Provide error messages for failures
- Handle offline scenarios gracefully

---

## Future Improvements

### 1. ProxyProvider for Dependent State
If providers depend on each other, use `ProxyProvider`:
```dart
ProxyProvider<AuthProvider, DashboardProvider>(
  update: (context, authProvider, previous) {
    return DashboardProvider(authProvider: authProvider);
  },
)
```

### 2. Repository Pattern for Other Providers
Apply repository pattern to other large providers:
- `NotificationProvider` → `NotificationRepository`
- `IndicatorBankProvider` → `IndicatorRepository`
- etc.

### 3. Provider Composition
Break down large providers into smaller, focused ones:
- `DashboardProvider` could be split into:
  - `AssignmentsProvider` (assignments only)
  - `EntitiesProvider` (entities only)
  - Use `ProxyProvider` to compose them

---

## Testing Considerations

### Unit Testing
- Mock repositories in provider tests
- Test state management logic only
- Keep business logic in repositories (easier to test)

### Integration Testing
- Test provider + repository together
- Test state updates and notifications

---

## Migration Guide

### Refactoring DashboardProvider (Example)

**Before:**
```dart
class DashboardProvider {
  final ApiService _api = ApiService();
  final StorageService _storage = StorageService();
  
  Future<void> loadDashboard() async {
    // API call, parsing, caching all in provider
    final response = await _api.get(...);
    // ... parsing logic ...
    // ... caching logic ...
  }
}
```

**After:**
```dart
class DashboardProvider {
  final DashboardRepository _repository = DashboardRepository();
  
  Future<void> loadDashboard() async {
    // Delegate to repository
    final data = await _repository.loadDashboardFromApi();
    // Update state only
    _updateStateFromData(data);
  }
}
```

---

**Last Updated:** 2024  
**Maintained By:** Development Team
