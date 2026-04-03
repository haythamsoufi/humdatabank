// pages/api/download-app.js
import fs from 'fs';
import path from 'path';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { filename } = req.query;

  // Validate filename to prevent directory traversal
  if (!filename || typeof filename !== 'string') {
    return res.status(400).json({ error: 'Filename is required' });
  }

  // Only allow APK and IPA files
  const allowedExtensions = ['.apk', '.ipa'];
  const ext = path.extname(filename).toLowerCase();
  if (!allowedExtensions.includes(ext)) {
    return res.status(400).json({ error: 'Invalid file type' });
  }

  // Sanitize filename - only allow alphanumeric, dots, hyphens, and underscores
  if (!/^[a-zA-Z0-9._-]+$/.test(filename)) {
    return res.status(400).json({ error: 'Invalid filename' });
  }

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
    const contentType = ext === '.apk'
      ? 'application/vnd.android.package-archive'
      : 'application/octet-stream';

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
