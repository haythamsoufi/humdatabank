import UIKit
import Flutter

@main
@objc(AppDelegate)
class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // Create the Flutter view controller
    let controller: FlutterViewController = window?.rootViewController as! FlutterViewController

    // Register plugins
    GeneratedPluginRegistrant.register(with: self)

    // Call super to complete Flutter setup
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}
