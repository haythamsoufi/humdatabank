// pages/api/download-app/[platform].js
import fs from 'fs';
import path from 'path';

const PLATFORM_FILES = {
  android: 'databank.apk',
  ios: 'databank.ipa'
};

const CONTENT_TYPES = {
  android: 'application/vnd.android.package-archive',
  ios: 'application/octet-stream'
};

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { platform } = req.query;

  // Validate platform
  if (!platform || !PLATFORM_FILES[platform]) {
    return res.status(400).json({ error: 'Invalid platform. Use "android" or "ios"' });
  }

  const filename = PLATFORM_FILES[platform];

  try {
    // Path to the apps directory in public folder
    const filePath = path.join(process.cwd(), 'public', 'apps', filename);

    // Check if file exists
    if (!fs.existsSync(filePath)) {
      return res.status(404).json({ error: 'File not found' });
    }

    // Read file stats
    const stats = fs.statSync(filePath);

    // Set appropriate content type
    const contentType = CONTENT_TYPES[platform];

    // Set headers to force download
    res.setHeader('Content-Type', contentType);
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    res.setHeader('Content-Length', stats.size);
    res.setHeader('Cache-Control', 'no-cache');

    // Stream the file
    const fileStream = fs.createReadStream(filePath);
    fileStream.pipe(res);
  } catch (error) {
    console.error('Error serving app file:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
}
