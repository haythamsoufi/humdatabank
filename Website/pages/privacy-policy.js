// pages/privacy-policy.js
import Head from 'next/head';
import { useTranslation } from '../lib/useTranslation';
import { TranslationSafe } from '../components/ClientOnly';

export default function PrivacyPolicyPage() {
  const { t, isLoaded } = useTranslation();

  return (
    <TranslationSafe>
      <Head>
        <title>Privacy Policy - NGO Databank</title>
        <meta name="description" content="Privacy Policy for the NGO Databank mobile application" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto bg-white shadow-lg rounded-lg p-8 md:p-12">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2">
            Privacy Policy
          </h1>
          <p className="text-sm text-gray-600 mb-8">
            Last Updated: {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
          </p>

          <div className="prose prose-lg max-w-none">
            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Introduction</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                The NGO Databank mobile application ("the App") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, store, and protect your personal information when you use our mobile application.
              </p>
              <p className="text-gray-700 leading-relaxed">
                By using the App, you agree to the collection and use of information in accordance with this policy. If you do not agree with our policies and practices, please do not use the App.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. Information We Collect</h2>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">2.1 Account Information</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                When you create an account or log in, we collect:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>Email address</li>
                <li>Password (stored securely using encryption)</li>
                <li>Name and job title (if provided)</li>
                <li>Profile preferences (including profile color customization)</li>
                <li>Chatbot preferences</li>
              </ul>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">2.2 Device Information</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                We automatically collect certain device information to provide and improve our services:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>Device type and model</li>
                <li>Operating system version</li>
                <li>Device identifiers</li>
                <li>Network connectivity status</li>
              </ul>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">2.3 Usage Data</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                We collect information about how you use the App:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>App features accessed and used</li>
                <li>Time spent in the App</li>
                <li>User activity and interactions</li>
                <li>Performance metrics (startup time, response times)</li>
              </ul>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">2.4 Push Notifications</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                To send you push notifications, we collect:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>Firebase Cloud Messaging (FCM) token</li>
                <li>Device registration information</li>
                <li>Notification preferences</li>
              </ul>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">2.5 Error and Crash Data</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                To improve app stability and fix bugs, we may collect:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>Error logs and crash reports</li>
                <li>Stack traces</li>
                <li>Device information at the time of error</li>
                <li>App version and build information</li>
              </ul>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">2.6 Session and Authentication Data</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                We store session information to maintain your login state:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>Session cookies and tokens</li>
                <li>Authentication state</li>
                <li>Session expiration timestamps</li>
              </ul>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">2.7 Offline Cache Data</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                To enable offline functionality, we cache certain data locally on your device:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>Cached API responses</li>
                <li>Dashboard data</li>
                <li>User profile information</li>
                <li>Entity lists and assignments</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. How We Use Your Information</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                We use the collected information for the following purposes:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li><strong>To provide and maintain the App:</strong> Authenticate users, deliver app features, and manage your account</li>
                <li><strong>To send notifications:</strong> Deliver push notifications about assignments, updates, and important information</li>
                <li><strong>To improve the App:</strong> Analyze usage patterns, fix bugs, and enhance performance</li>
                <li><strong>To ensure security:</strong> Detect and prevent fraud, unauthorized access, and other security threats</li>
                <li><strong>To provide offline functionality:</strong> Cache data locally to enable app usage without internet connection</li>
                <li><strong>To comply with legal obligations:</strong> Meet regulatory requirements and respond to legal requests</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">4. Data Storage and Security</h2>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">4.1 Local Storage</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                Some data is stored locally on your device using:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li><strong>SQLite database:</strong> For offline cache and app data</li>
                <li><strong>Secure storage:</strong> For encrypted storage of sensitive information like session tokens</li>
                <li><strong>Shared preferences:</strong> For app settings and user preferences</li>
              </ul>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">4.2 Server Storage</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                Your account information and app data are stored on secure servers operated by your organization or its service providers. We implement appropriate technical and organizational measures to protect your data, including:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>Encryption of data in transit (HTTPS/TLS)</li>
                <li>Encryption of sensitive data at rest</li>
                <li>Access controls and authentication</li>
                <li>Regular security assessments</li>
              </ul>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">4.3 Data Retention</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                We retain your personal information for as long as necessary to provide the App and fulfill the purposes outlined in this Privacy Policy, unless a longer retention period is required or permitted by law. When you delete your account, we will delete or anonymize your personal information, except where we are required to retain it for legal or regulatory purposes.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">5. Third-Party Services</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                The App uses the following third-party services that may collect information:
              </p>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">5.1 Firebase (Google)</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                We use Firebase services for:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li><strong>Firebase Cloud Messaging:</strong> To send push notifications to your device</li>
                <li><strong>Firebase Analytics:</strong> To understand app usage and improve user experience</li>
              </ul>
              <p className="text-gray-700 leading-relaxed mb-4">
                Firebase may collect device information, usage data, and analytics. For more information, please review <a href="https://firebase.google.com/support/privacy" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">Google's Privacy Policy</a>.
              </p>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">5.2 Sentry</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                We use Sentry (if enabled) for error tracking and crash reporting. Sentry collects:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>Error logs and crash reports</li>
                <li>Stack traces</li>
                <li>Device and app version information</li>
                <li>User context (anonymized)</li>
              </ul>
              <p className="text-gray-700 leading-relaxed mb-4">
                For more information, please review <a href="https://sentry.io/privacy/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">Sentry's Privacy Policy</a>.
              </p>

              <h3 className="text-xl font-semibold text-gray-800 mb-3">5.3 Azure AD B2C</h3>
              <p className="text-gray-700 leading-relaxed mb-4">
                For single sign-on authentication, we may use Microsoft Azure AD B2C. This service handles authentication and may collect login information. For more information, please review <a href="https://privacy.microsoft.com/en-us/privacystatement" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">Microsoft's Privacy Statement</a>.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">6. Data Sharing and Disclosure</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                We do not sell your personal information. We may share your information only in the following circumstances:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li><strong>Within your organization:</strong> With authorized staff and partners as needed to provide the App's services</li>
                <li><strong>Service Providers:</strong> With third-party service providers (Firebase, Sentry) who assist us in operating the App, subject to confidentiality agreements</li>
                <li><strong>Legal Requirements:</strong> When required by law, court order, or government regulation</li>
                <li><strong>Protection of Rights:</strong> To protect the rights, property, or safety of the organization, our users, or others</li>
                <li><strong>With Your Consent:</strong> When you have explicitly consented to the sharing</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">7. Your Rights and Choices</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                Depending on your location, you may have the following rights regarding your personal information:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li><strong>Access:</strong> Request access to your personal information</li>
                <li><strong>Correction:</strong> Request correction of inaccurate or incomplete information</li>
                <li><strong>Deletion:</strong> Request deletion of your personal information</li>
                <li><strong>Data Portability:</strong> Request a copy of your data in a portable format</li>
                <li><strong>Opt-Out:</strong> Opt-out of certain data collection, such as analytics (where available)</li>
                <li><strong>Push Notifications:</strong> Control push notification preferences in the App settings</li>
              </ul>
              <p className="text-gray-700 leading-relaxed mb-4">
                To exercise these rights, please contact us using the information provided in the "Contact Us" section below.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">8. Children's Privacy</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                The App is not intended for use by children under the age of 13 (or the applicable age of consent in your jurisdiction). We do not knowingly collect personal information from children. If you believe we have collected information from a child, please contact us immediately.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">9. International Data Transfers</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                Your information may be transferred to and processed in countries other than your country of residence. These countries may have data protection laws that differ from those in your country. By using the App, you consent to the transfer of your information to these countries. We take appropriate measures to ensure your information is protected in accordance with this Privacy Policy.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">10. Changes to This Privacy Policy</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page and updating the "Last Updated" date. You are advised to review this Privacy Policy periodically for any changes. Changes to this Privacy Policy are effective when they are posted on this page.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">11. Contact Us</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                If you have any questions, concerns, or requests regarding this Privacy Policy or our data practices, please contact us:
              </p>
              <div className="bg-gray-50 p-4 rounded-lg mb-4">
                <p className="text-gray-700 mb-2">
                  <strong>NGO Databank</strong>
                </p>
                <p className="text-gray-700 mb-2">
                  Email: <a href="mailto:haythamsoufi@outlook.com" className="text-blue-600 hover:text-blue-800 underline">haythamsoufi@outlook.com</a>
                </p>
                <p className="text-gray-700">
                  Replace this block with your organization&apos;s legal name and contact details.
                </p>
              </div>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">12. Compliance</h2>
              <p className="text-gray-700 leading-relaxed mb-4">
                This Privacy Policy is designed to comply with applicable data protection laws, including:
              </p>
              <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-2">
                <li>General Data Protection Regulation (GDPR) - European Union</li>
                <li>California Consumer Privacy Act (CCPA) - United States</li>
                <li>Other applicable privacy laws in jurisdictions where the App is used</li>
              </ul>
            </section>
          </div>
        </div>
      </div>
    </TranslationSafe>
  );
}
