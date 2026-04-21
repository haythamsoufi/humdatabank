import { useTranslation } from '../lib/useTranslation';
import Link from 'next/link';

export default function NotFound() {
  const { t } = useTranslation();

  return (
    <div style={{ padding: 24 }}>
      <h1>{t('errors.404.title')}</h1>
      <p>{t('errors.404.message')}</p>
      <Link href="/">
        <a>{t('common.backToHome')}</a>
      </Link>
    </div>
  );
}
