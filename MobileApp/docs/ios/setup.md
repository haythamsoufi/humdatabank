# iOS Setup Guide

This guide will help you set up and build the iOS app for IFRC Network Databank.

## Prerequisites

1. **macOS**: iOS development requires macOS and Xcode
2. **Xcode**: Install Xcode from the App Store (latest version recommended)
3. **CocoaPods**: Install CocoaPods if not already installed:
   ```bash
   sudo gem install cocoapods
   ```
4. **Flutter**: Ensure Flutter is installed and configured

## Initial Setup

**⚠️ Important**: All iOS setup steps must be performed on macOS. CocoaPods and Xcode are macOS-only tools.

1. **Navigate to the iOS directory** (on your Mac):
   ```bash
   cd ios
   ```

2. **Install CocoaPods dependencies** (on your Mac):
   ```bash
   pod install
   ```
   This will:
   - Install all Flutter plugin dependencies via CocoaPods
   - Create `Runner.xcworkspace` (required for building)
   - Generate `Podfile.lock`
   
   **Note**: If you're developing on Windows/Linux, you'll need to run this command when you switch to your Mac.

3. **Open the project in Xcode**:
   ```bash
   open Runner.xcworkspace
   ```
   ⚠️ **CRITICAL**: Always open `.xcworkspace`, never `.xcodeproj`. Opening `.xcodeproj` will cause build failures.

## Configuration

### Bundle Identifier

The bundle identifier is set to `com.ifrc.databank` in the Xcode project. If you need to change it:

1. Open `Runner.xcworkspace` in Xcode
2. Select the `Runner` target
3. Go to the "Signing & Capabilities" tab
4. Update the Bundle Identifier

### Signing & Capabilities

1. In Xcode, select the `Runner` target
2. Go to "Signing & Capabilities"
3. Select your development team
4. Xcode will automatically manage provisioning profiles

### Deep Linking Configuration

The app is configured to handle deep links for Azure AD B2C authentication:
- URL Scheme: `ifrcdatabank`
- This is already configured in `Info.plist`

### Network Security

The app allows arbitrary network loads (configured in `Info.plist`) for development. For production, you should restrict this to specific domains.

## Building and Running

### From Xcode

1. Open `Runner.xcworkspace` in Xcode
2. Select a target device (simulator or physical device)
3. Click the Run button (⌘R)

### From Command Line

```bash
# From the project root
flutter run -d ios
```

Or to build for a specific device:

```bash
flutter run -d <device-id>
```

To list available devices:

```bash
flutter devices
```

## Troubleshooting

### CocoaPods Issues

If you encounter CocoaPods-related errors:

```bash
cd ios
pod deintegrate
pod install
```

### Xcode Version Issues

If you see build errors related to Xcode version:
- Update Xcode to the latest version
- Run `flutter clean` and rebuild

### Signing Issues

If you see code signing errors:
- Ensure you have a valid Apple Developer account
- Check that your development team is selected in Xcode
- Verify the bundle identifier matches your provisioning profile

### Flutter Plugin Issues

If plugins aren't working:
```bash
flutter clean
flutter pub get
cd ios
pod install
```

## Testing on Physical Device

1. Connect your iOS device via USB
2. Trust the computer on your device if prompted
3. In Xcode, select your device from the device list
4. Click Run
5. On your device, go to Settings > General > Device Management and trust the developer certificate

## App Store Deployment

For App Store deployment:

1. Update version numbers in `pubspec.yaml`
2. Configure App Store Connect settings in Xcode
3. Archive the app: Product > Archive
4. Upload to App Store Connect: Window > Organizer > Distribute App

## Additional Notes

- The minimum iOS version is set to 13.0 (required for Firebase Core)
- The app supports both iPhone and iPad
- Deep linking is configured for Azure AD B2C authentication callbacks

### Firebase Configuration

**Important**: Firebase is automatically managed by CocoaPods when you run `pod install`. The Firebase plugins (`firebase_core`, `firebase_messaging`) are already configured in `pubspec.yaml` and will be installed via CocoaPods.

**Do NOT** manually add Firebase via Xcode Package Manager - this will conflict with Flutter's CocoaPods integration.

### Cross-Platform Development Workflow

If you're developing on Windows/Linux:

1. **On Windows/Linux**: Develop and test on Android, make code changes
2. **On Mac**: When ready to build iOS:
   - Ensure your code is synced (git, etc.)
   - Run `pod install` in the `ios` directory
   - Open `Runner.xcworkspace` in Xcode
   - Configure signing and build
