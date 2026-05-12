import React from 'react';
import { useTranslation } from '../lib/useTranslation';
import Link from 'next/link';

function ErrorPage({ statusCode }) {
  const { t } = useTranslation();

  return (
    <div style={{ padding: 24 }}>
      <h1>{t('errors.error.title')}</h1>
      <p>
        {statusCode
          ? t('errors.error.server', { statusCode })
          : t('errors.error.client')}
      </p>
      <Link href="/">
        <a>{t('common.backToHome')}</a>
      </Link>
    </div>
  );
}

ErrorPage.getInitialProps = ({ res, err }) => {
  const statusCode = res ? res.statusCode : err ? err.statusCode : 404;
  return { statusCode };
};

export default ErrorPage;
