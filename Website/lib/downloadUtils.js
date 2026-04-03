// Download utilities for CSV and PNG export

/**
 * Download data as CSV file
 * @param {Object} data - The data to export
 * @param {string} filename - The filename for the downloaded file
 * @param {string} indicatorName - The name of the indicator being exported
 * @param {string} selectedYear - The selected year
 * @param {string} regionName - The selected region name
 */
export const downloadCSV = (data, filename, indicatorName, selectedYear, regionName) => {
  try {
    // Convert data object to CSV format
    const csvContent = convertToCSV(data, indicatorName, selectedYear, regionName);

    // Create blob and download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');

    if (link.download !== undefined) {
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute('download', filename);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  } catch (error) {
    console.error('Error downloading CSV:', error);
    alert('Error downloading CSV file. Please try again.');
  }
};

/**
 * Convert data object to CSV format
 * @param {Object} data - The data to convert
 * @param {string} indicatorName - The name of the indicator
 * @param {string} selectedYear - The selected year
 * @param {string} regionName - The selected region name
 * @returns {string} CSV content
 */
const convertToCSV = (data, indicatorName, selectedYear, regionName) => {
  // Create header row
  const headers = ['Country Code', 'Country Name', indicatorName, 'Year', 'Region'];
  const csvRows = [headers.join(',')];

  // Add data rows
  Object.entries(data).forEach(([countryCode, countryData]) => {
    const row = [
      countryCode,
      countryData.name || 'Unknown',
      countryData.value || 0,
      selectedYear || 'All Years',
      regionName || 'Global'
    ];
    csvRows.push(row.join(','));
  });

  return csvRows.join('\n');
};

/**
 * Download current map visualization as PNG
 * @param {string} filename - The filename for the downloaded file
 * @param {string} mapContainerId - The ID of the map container element
 */
export const downloadPNG = async (filename, mapContainerId = 'map-container') => {
  try {
    // Import html2canvas dynamically to avoid SSR issues
    const html2canvas = (await import('html2canvas')).default;

    const mapContainer = document.getElementById(mapContainerId);
    if (!mapContainer) {
      throw new Error('Map container not found');
    }

    // Show loading state
    const loadingElement = document.createElement('div');
    loadingElement.innerHTML = 'Generating PNG...';
    loadingElement.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: rgba(0, 0, 0, 0.8);
      color: white;
      padding: 20px;
      border-radius: 8px;
      z-index: 10000;
    `;
    document.body.appendChild(loadingElement);

    // Configure html2canvas options for better quality
    const canvas = await html2canvas(mapContainer, {
      scale: 2, // Higher resolution
      useCORS: true,
      allowTaint: true,
      backgroundColor: '#ffffff',
      width: mapContainer.offsetWidth,
      height: mapContainer.offsetHeight,
      scrollX: 0,
      scrollY: 0
    });

    // Remove loading element
    document.body.removeChild(loadingElement);

    // Convert canvas to blob and download
    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }, 'image/png');

  } catch (error) {
    console.error('Error downloading PNG:', error);
    alert('Error downloading PNG file. Please try again.');
  }
};

/**
 * Generate filename based on current data
 * @param {string} indicatorName - The name of the indicator
 * @param {string} selectedYear - The selected year
 * @param {string} regionName - The selected region name
 * @param {string} fileType - The file type (csv or png)
 * @returns {string} Generated filename
 */
export const generateFilename = (indicatorName, selectedYear, regionName, fileType) => {
  const timestamp = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
  const indicatorSlug = indicatorName.toLowerCase().replace(/\s+/g, '-');
  const yearSlug = selectedYear || 'all-years';
  const regionSlug = regionName ? regionName.toLowerCase().replace(/\s+/g, '-') : 'global';

  return `ngodb-${indicatorSlug}-${regionSlug}-${yearSlug}-${timestamp}.${fileType}`;
};

/**
 * Download JSON data as an Excel (.xlsx) file
 * - Dynamically imports exceljs to avoid SSR issues
 * - Flattens nested objects for a clean tabular sheet
 * @param {Array|Object} jsonData - Array of records or object containing an array
 * @param {string} filename - e.g. 'ngodb-api-data.xlsx'
 */
export const downloadExcelFromJson = async (jsonData, filename = 'ngodb-api-data.xlsx') => {
  try {
    const ExcelJS = (await import('exceljs')).default;

    const records = normalizeToArray(jsonData).map((rec) => {
      // Guard against top-level array records creating numeric column headers
      if (Array.isArray(rec)) {
        return { data: JSON.stringify(rec) };
      }
      return flattenRecord(rec);
    });
    if (records.length === 0) {
      alert('No data to export.');
      return;
    }

    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Data');

    const columns = Object.keys(records[0]);
    worksheet.columns = columns.map((key) => ({ header: key, key }));
    records.forEach((record) => worksheet.addRow(record));

    const buffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Error exporting Excel:', error);
    alert('Error exporting Excel file. Please try again.');
  }
};

// Helpers
const normalizeToArray = (data) => {
  const coerceNumericKeyedObjectToArray = (obj) => {
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null;
    const keys = Object.keys(obj);
    if (keys.length === 0) return null;
    if (keys.every((k) => /^\d+$/.test(k))) {
      return keys
        .map((k) => parseInt(k, 10))
        .sort((a, b) => a - b)
        .map((k) => obj[String(k)]);
    }
    return null;
  };

  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.data)) return data.data;
  if (data && Array.isArray(data.items)) return data.items;
  if (data && Array.isArray(data.results)) return data.results;

  const coercedTop = coerceNumericKeyedObjectToArray(data);
  if (coercedTop) return coercedTop;
  if (data && data.data) {
    const coercedData = coerceNumericKeyedObjectToArray(data.data);
    if (coercedData) return coercedData;
  }
  if (data && data.items) {
    const coercedItems = coerceNumericKeyedObjectToArray(data.items);
    if (coercedItems) return coercedItems;
  }
  return [];
};

const flattenRecord = (record, parentKey = '', result = {}) => {
  Object.entries(record || {}).forEach(([key, value]) => {
    const newKey = parentKey ? `${parentKey}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flattenRecord(value, newKey, result);
    } else {
      result[newKey] = Array.isArray(value) ? JSON.stringify(value) : value;
    }
  });
  return result;
};
