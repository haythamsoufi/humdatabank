import UIKit
import Flutter

@main
@objc(AppDelegate)
class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)

    // One capsule behind the floating tab bar. iOS 26 uses Liquid Glass;
    // earlier versions use the system ultra-thin material.
    guard let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "GlassCapsuleView") else {
      return
    }
    registrar.register(
      GlassCapsuleViewFactory(),
      withId: GlassCapsuleViewFactory.viewType
    )
  }
}

/// Flutter platform view for the floating tab bar's system glass capsule.
private final class GlassCapsuleViewFactory: NSObject, FlutterPlatformViewFactory {
  static let viewType = "hum_databank/glass_capsule"

  func create(
    withFrame frame: CGRect,
    viewIdentifier viewId: Int64,
    arguments args: Any?
  ) -> FlutterPlatformView {
    GlassCapsulePlatformView(frame: frame, arguments: args)
  }

  func createArgsCodec() -> FlutterMessageCodec & NSObjectProtocol {
    FlutterStandardMessageCodec.sharedInstance()
  }
}

private final class GlassCapsulePlatformView: NSObject, FlutterPlatformView {
  private let capsule: GlassCapsuleView

  init(frame: CGRect, arguments args: Any?) {
    let params = args as? [String: Any]
    let dark = params?["dark"] as? Bool ?? false
    capsule = GlassCapsuleView(frame: frame, dark: dark)
    super.init()
  }

  func view() -> UIView {
    capsule
  }
}

/// Capsule of system glass. Touches pass through so the Flutter icons stay tappable.
private final class GlassCapsuleView: UIView {
  private let effectView: UIVisualEffectView
  private let usesLiquidGlass: Bool

  init(frame: CGRect, dark: Bool) {
    if #available(iOS 26.0, *) {
      // Glass views get a small fixed corner radius unless the shape is set;
      // layer.cornerRadius is ignored for UIGlassEffect.
      let glass = UIVisualEffectView(effect: UIGlassEffect())
      glass.cornerConfiguration = .capsule()
      effectView = glass
      usesLiquidGlass = true
    } else {
      let blur = UIVisualEffectView(effect: UIBlurEffect(style: .systemUltraThinMaterial))
      blur.clipsToBounds = true
      effectView = blur
      usesLiquidGlass = false
    }
    super.init(frame: frame)
    isUserInteractionEnabled = false
    backgroundColor = .clear
    let style: UIUserInterfaceStyle = dark ? .dark : .light
    overrideUserInterfaceStyle = style
    effectView.isUserInteractionEnabled = false
    effectView.overrideUserInterfaceStyle = style
    effectView.backgroundColor = .clear
    effectView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
    effectView.frame = bounds
    addSubview(effectView)
  }

  required init?(coder: NSCoder) {
    return nil
  }

  override func layoutSubviews() {
    super.layoutSubviews()
    effectView.frame = bounds
    if !usesLiquidGlass {
      effectView.layer.cornerRadius = min(bounds.width, bounds.height) / 2
    }
  }
}
