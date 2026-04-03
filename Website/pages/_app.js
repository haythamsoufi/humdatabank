// pages/_app.js
import '../styles/globals.css'; // Import global styles
import Layout from '../components/layout/Layout'; // Import the main Layout component

// This default export is required in a new `pages/_app.js` file.
function MyApp({ Component, pageProps }) {
  return (
    <Layout>
      <Component {...pageProps} />
    </Layout>
  );
}

export default MyApp;
