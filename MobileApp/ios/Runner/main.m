#import <UIKit/UIKit.h>

// Forward declare to ensure Swift runtime is aware
@class AppDelegate;

int main(int argc, char * argv[]) {
  @autoreleasepool {
    // Use explicit class name string to avoid needing Swift headers here.
    // For sideloading compatibility, dynamically resolve the class
    Class appDelegateClass = NSClassFromString(@"AppDelegate");
    NSString *delegateClassName = appDelegateClass ? NSStringFromClass(appDelegateClass) : @"AppDelegate";
    return UIApplicationMain(argc, argv, nil, delegateClassName);
  }
}
