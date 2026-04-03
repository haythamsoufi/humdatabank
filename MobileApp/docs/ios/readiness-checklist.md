# iOS Build Readiness Checklist

This checklist verifies if your iOS setup is ready for generating an IPA file in Xcode.

## ✅ Configuration Files - READY

- [x] **Bundle Identifier**: `com.ifrc.databank` (configured in project.pbxproj)
- [x] **iOS Deployment Target**: 13.0 (configured in Podfile and project.pbxproj)
- [x] **Info.plist**: Properly configured with:
  - Deep linking URL scheme: `ifrcdatabank`
  - Network security settings
  - App display name: "IFRC Data"
- [x] **AppDelegate.swift**: Deep linking handlers implemented
- [x] **GoogleService-Info.plist**: Firebase configuration present
- [x] **Podfile**: Correctly configured for iOS 13.0

## ⚠️ Required Actions Before Building

### 1. Install CocoaPods Dependencies (REQUIRED)
**Status**: ❌ NOT DONE - No `Podfile.lock` or `Runner.xcworkspace` found

**Action Required** (ON YOUR MAC):
```bash
cd ios
pod install
```

This will:
- Install all Flutter plugin dependencies
- Create `Runner.xcworkspace` (you MUST open this, not `.xcodeproj`)
- Generate `Podfile.lock`

**⚠️ CRITICAL**: 
- This command **MUST** be run on macOS (CocoaPods is macOS-only)
- If you're on Windows/Linux, you'll run this when you switch to your Mac
- CocoaPods must be installed: `sudo gem install cocoapods`

### 2. Configure Code Signing in Xcode (REQUIRED)
**Status**: ⚠️ MUST BE DONE IN XCODE

**Action Required**:
1. Open `Runner.xcworkspace` in Xcode (NOT `.xcodeproj`)
2. Select the `Runner` target
3. Go to "Signing & Capabilities" tab
4. Select your **Development Team**
5. Xcode will automatically manage provisioning profiles

**Requirements**:
- Valid Apple Developer account (free account works for device testing)
- Your Apple ID signed into Xcode

### 3. Firebase Setup Clarification
**Status**: ⚠️ POTENTIAL CONFUSION

The `SETUP_IOS.md` mentions adding Firebase via Xcode Package Manager, but **Flutter uses CocoaPods for Firebase**. 

**Action**: 
- ✅ **DO NOT** add Firebase manually via Xcode Package Manager
- ✅ **DO** run `pod install` - this will install Firebase dependencies automatically via CocoaPods
- The Firebase plugins (`firebase_core`, `firebase_messaging`) are already in `pubspec.yaml` and will be handled by CocoaPods

### 4. Verify Flutter Dependencies
**Status**: ✅ Should be ready, but verify

**Action** (if needed):
```bash
cd MobileApp
flutter pub get
```

## 📋 Step-by-Step Build Process

Once the above actions are complete:

1. **On your Mac**:
   ```bash
   cd MobileApp/ios
   pod install
   ```

2. **Open in Xcode**:
   ```bash
   open Runner.xcworkspace
   ```
   ⚠️ **CRITICAL**: Always open `.xcworkspace`, never `.xcodeproj`

3. **Configure Signing**:
   - Select `Runner` target → "Signing & Capabilities"
   - Select your Development Team
   - Ensure Bundle Identifier is `com.ifrc.databank`

4. **Connect Your Device**:
   - Connect iPhone via USB
   - Trust the computer on your device
   - Select your device in Xcode's device list

5. **Build for Device**:
   - Select your device from the device dropdown
   - Click Run (⌘R) or Product → Run

6. **Trust Developer Certificate on Device**:
   - On your iPhone: Settings → General → Device Management
   - Trust your developer certificate

7. **Generate IPA for Testing**:
   - Product → Archive
   - Window → Organizer
   - Select your archive → Distribute App
   - Choose "Ad Hoc" or "Development" distribution
   - Follow the wizard to export IPA

## 🔍 Current Project Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Bundle ID | ✅ Ready | `com.ifrc.databank` |
| iOS Version | ✅ Ready | 13.0 |
| Info.plist | ✅ Ready | Deep linking configured |
| AppDelegate | ✅ Ready | Deep linking handlers present |
| Firebase Config | ✅ Ready | GoogleService-Info.plist present |
| CocoaPods | ❌ **NOT DONE** | Must run `pod install` |
| Code Signing | ⚠️ **TODO** | Configure in Xcode |
| Workspace | ❌ **MISSING** | Created by `pod install` |

## 🚨 Critical Issues to Resolve

1. **Run `pod install`** - This is the most critical step. Without it, you cannot build.
2. **Configure code signing in Xcode** - Required for device testing.
3. **Open `.xcworkspace` not `.xcodeproj`** - Opening the wrong file will cause build failures.

## ✅ You're Ready When:

- [ ] `ios/Podfile.lock` exists
- [ ] `ios/Runner.xcworkspace` exists
- [ ] Development team is selected in Xcode
- [ ] Bundle identifier matches in Xcode (`com.ifrc.databank`)
- [ ] Device is connected and trusted
- [ ] Xcode shows no signing errors

## 📝 Additional Notes

- The project supports both iPhone and iPad
- Deep linking is configured for Azure AD B2C authentication
- Network security allows arbitrary loads (for development)
- Minimum iOS version 13.0 is required for Firebase Core
