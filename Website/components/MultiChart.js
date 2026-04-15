import React, { useEffect, useState, useRef } from 'react';
import html2canvas from 'html2canvas';

const MultiChart = ({ data, type = 'bar', title, height = 200, onSummaryStats, stackedMode = null, disaggregationToggle = null }) => {
  const [showFullValues, setShowFullValues] = useState(false);
  const [tooltip, setTooltip] = useState({ show: false, content: '', x: 0, position: 'above' });
  const [tooltipTimeout, setTooltipTimeout] = useState(null);
  const [containerWidth, setContainerWidth] = useState(800);
  const [disaggregationView, setDisaggregationView] = useState('sex'); // 'sex', 'age', or 'combined'
  const previousStatsRef = useRef(null);
  const containerRef = useRef(null);

  // Color schemes for different disaggregation types - softer, eye-friendly colors
  const colorSchemes = {
    sex: {
      'Male': '#7DD3FC', // Soft sky blue
      'Female': '#F9A8D4', // Soft pink
      'Other': '#C4B5FD' // Soft purple
    },
    age: {
      '0-17': '#FCA5A5', // Soft red
      '18-49': '#FCD34D', // Soft amber
      '50+': '#86EFAC', // Soft green
      'Under 18': '#FCA5A5', // Soft red
      '18-49 years': '#FCD34D', // Soft amber
      '50+ years': '#86EFAC', // Soft green
      'Children (0-17)': '#FCA5A5',
      'Adults (18-49)': '#FCD34D',
      'Seniors (50+)': '#86EFAC'
    }
  };

  // Helper function to get color for a category
  const getColor = (category, type) => {
    const scheme = colorSchemes[type];
    return scheme[category] || `hsl(${Math.abs(category.split('').reduce((a, b) => a + b.charCodeAt(0), 0)) % 360}, 45%, 75%)`; // Softer fallback colors
  };

  // Helper function to format numbers with K, M, B units
  const formatNumber = (num, showFull = false) => {
    // Handle undefined, null, or NaN values
    if (num === undefined || num === null || isNaN(num)) {
      return '0';
    }

    if (showFull) {
      return num.toLocaleString();
    }
    if (num >= 1000000000) {
      return (num / 1000000000).toFixed(1) + 'B';
    } else if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
  };

  // Helper function to generate tooltip content for ARCS volunteers
  const getTooltipContent = (item, index) => {
    if (title && title.includes('ARCS Volunteers')) {
      const explanations = {
        2019: "Baseline year with 23,440 active volunteers across Afghanistan",
        2020: "Growth due to increased community engagement and disaster response needs",
        2021: "Expansion following humanitarian crisis and conflict-related emergencies",
        2022: "Major increase to 393,077 volunteers - Everyone Counts Report shows extensive mobilization for earthquake response and health services",
        2023: "Continued growth with 425,000 volunteers supporting ongoing humanitarian operations"
      };

      const year = item.label;
      const explanation = explanations[year] || "Volunteer engagement in humanitarian activities";

      return {
        title: `${year}: ${formatNumber(item.value, showFullValues)} volunteers`,
        explanation: explanation
      };
    }

    // Default tooltip for other charts
    return {
      title: `${item.label}: ${formatNumber(item.value, showFullValues)}`,
      explanation: "Data point from chart"
    };
  };

  // Helper function to calculate optimal tooltip position
  const getTooltipPosition = (index, dataLength) => {
    const xPercent = (index / (data.length - 1)) * 100;

    // Always show tooltips below the x-axis items
    const shouldShowAbove = false;

    // Adjust horizontal position to prevent overflow
    let adjustedX = xPercent;
    if (xPercent < 15) {
      adjustedX = 15; // Minimum left margin
    } else if (xPercent > 85) {
      adjustedX = 85; // Maximum right margin
    }

    return {
      x: adjustedX,
      position: 'below'
    };
  };

  // Calculate summary stats for line charts using useEffect to avoid render-phase updates
  useEffect(() => {
    if (onSummaryStats && data && data.length > 1 && type === 'line') {
      // Filter out undefined/null values for summary calculations
      const validDataForStats = data.filter(item => item.value !== undefined && item.value !== null && !isNaN(item.value));

      if (validDataForStats.length > 1) {
        const totalGrowth = ((validDataForStats[validDataForStats.length - 1].value - validDataForStats[0].value) / validDataForStats[0].value) * 100;
        const currentTotal = validDataForStats[validDataForStats.length - 1].value;
        const avgAnnualGrowth = (Math.pow(validDataForStats[validDataForStats.length - 1].value / validDataForStats[0].value, 1 / (validDataForStats.length - 1)) - 1) * 100;

        const newStats = {
          totalGrowth: totalGrowth.toFixed(1),
          currentTotal: formatNumber(currentTotal, false), // Always use abbreviated format for consistency
          avgAnnualGrowth: avgAnnualGrowth.toFixed(1)
        };

        // Only call onSummaryStats if the stats have actually changed
        const statsChanged = !previousStatsRef.current ||
          previousStatsRef.current.totalGrowth !== newStats.totalGrowth ||
          previousStatsRef.current.currentTotal !== newStats.currentTotal ||
          previousStatsRef.current.avgAnnualGrowth !== newStats.avgAnnualGrowth;

        if (statsChanged) {
          previousStatsRef.current = newStats;
          onSummaryStats(newStats);
        }
      }
    }
  }, [data, type, onSummaryStats]); // Now safe to include onSummaryStats since we prevent unnecessary calls

  // Measure container width and update chart dimensions
  useEffect(() => {
    const updateContainerWidth = () => {
      if (containerRef.current) {
        const width = containerRef.current.offsetWidth;
        setContainerWidth(Math.max(width, 400)); // Minimum width of 400px
      }
    };

    updateContainerWidth();
    window.addEventListener('resize', updateContainerWidth);

    return () => {
      window.removeEventListener('resize', updateContainerWidth);
    };
  }, []);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (tooltipTimeout) {
        clearTimeout(tooltipTimeout);
      }
    };
  }, [tooltipTimeout]);

  if (!data || data.length === 0) {
    return <div className="text-humdb-gray-500 text-center py-4">No data available</div>;
  }

  // Filter out undefined/null values and ensure we have valid numbers
  const validData = data.filter(item => item.value !== undefined && item.value !== null && !isNaN(item.value));

  if (validData.length === 0) {
    return <div className="text-humdb-gray-500 text-center py-4">No valid data available</div>;
  }

  const maxValue = Math.max(...validData.map(item => item.value));
  const minValue = Math.min(...validData.map(item => item.value));

  const renderStackedBarChart = () => {
    // Check if we have disaggregation data
    const hasDisaggregationData = validData.some(item =>
      (item.bySex && item.bySex.length > 0) ||
      (item.byAge && item.byAge.length > 0)
    );

    if (!hasDisaggregationData) {
      return renderBarChart(); // Fall back to regular bar chart
    }

    // Get disaggregation data based on current view
    const getDisaggregationData = (item) => {
      if (disaggregationView === 'sex' && item.bySex) {
        return item.bySex;
      } else if (disaggregationView === 'age' && item.byAge) {
        return item.byAge;
      }
      return [];
    };

    return (
      <div className="space-y-4 mt-8">
        {/* Disaggregation Toggle */}
        <div className="flex justify-center mb-6">
          <div className="bg-gray-100 rounded-lg p-1 flex">
            <button
              onClick={() => setDisaggregationView('sex')}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                disaggregationView === 'sex'
                  ? 'bg-white text-humdb-navy shadow-sm'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              By Sex
            </button>
            <button
              onClick={() => setDisaggregationView('age')}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                disaggregationView === 'age'
                  ? 'bg-white text-humdb-navy shadow-sm'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              By Age
            </button>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap justify-center gap-4 mb-4">
          {(() => {
            const allCategories = new Set();
            validData.forEach(item => {
              const disaggData = getDisaggregationData(item);
              disaggData.forEach(d => allCategories.add(d.label));
            });
            return Array.from(allCategories).map(category => (
              <div key={category} className="flex items-center space-x-2">
                <div
                  className="w-3 h-3 rounded"
                  style={{ backgroundColor: getColor(category, disaggregationView) }}
                />
                <span className="text-sm text-gray-700">{category}</span>
              </div>
            ));
          })()}
        </div>

        {/* Stacked Bars */}
        {validData.map((item, index) => {
          const disaggData = getDisaggregationData(item);
          const total = disaggData.reduce((sum, d) => sum + d.value, 0);

          if (total === 0) return null;

          return (
            <div key={index} className="flex items-start space-x-4 mb-6">
              <div className="w-48 text-sm text-humdb-gray-600 leading-tight" title={item.label}>
                <div className="break-words" style={{ lineHeight: '1.3', maxHeight: '2.6em', overflow: 'hidden' }}>
                  {item.label}
                </div>
              </div>
              <div className="flex-1">
                {/* Stacked bar */}
                <div className="bg-humdb-gray-200 rounded-full h-10 relative overflow-hidden mb-2">
                  {/* Stacked segments */}
                  {(() => {
                    let currentPosition = 0;
                    return disaggData.map((segment, segIndex) => {
                      const percentage = (segment.value / total) * 100;
                      const segmentElement = (
                        <div
                          key={segIndex}
                          className="absolute h-full transition-all duration-500 hover:opacity-90 flex items-center justify-center"
                          style={{
                            left: `${currentPosition}%`,
                            width: `${percentage}%`,
                            backgroundColor: getColor(segment.label, disaggregationView)
                          }}
                          title={`${segment.label}: ${formatNumber(segment.value, showFullValues)} (${percentage.toFixed(1)}%)`}
                        >
                          {/* Data label - only show if segment is wide enough */}
                          {percentage > 8 && (
                            <span className="text-xs font-medium text-gray-800 drop-shadow-sm px-1 truncate">
                              {percentage.toFixed(1)}%
                            </span>
                          )}
                        </div>
                      );
                      currentPosition += percentage;
                      return segmentElement;
                    });
                  })()}

                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderBarChart = () => {
    // Handle single value or all values are the same
    if (maxValue === minValue) {
      const singleValue = validData[0];
      return (
        <div className="text-center py-8">
          <div className="bg-humdb-gray-50 rounded-lg p-6 max-w-md mx-auto">
            <div className="text-2xl font-bold text-humdb-red mb-2">
              {formatNumber(singleValue.value, showFullValues)}
            </div>
            <div className="text-lg text-humdb-navy">
              {singleValue.label}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-2 mt-8">
        {validData.map((item, index) => {
          const widthPercentage = ((item.value - minValue) / (maxValue - minValue)) * 100;
          const validWidth = isNaN(widthPercentage) ? 0 : Math.max(0, Math.min(100, widthPercentage));

          return (
            <div key={index} className="flex items-center space-x-3">
              <div className="w-24 text-sm text-humdb-gray-600 truncate">{item.label}</div>
              <div className="flex-1 bg-humdb-gray-200 rounded-full h-6 relative">
                <div
                  className="bg-humdb-red h-6 rounded-full transition-all duration-500"
                  style={{
                    width: `${validWidth}%`
                  }}
                />
                <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-humdb-gray-800">
                  {formatNumber(item.value, showFullValues)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderLineChart = () => {
    // Calculate chart dimensions with proper padding for labels
    const chartHeight = height - 80; // Reserve space for labels
    const chartWidth = containerWidth; // Use dynamic container width
    const labelHeight = 60; // Height reserved for labels

    // Handle single value or all values are the same
    if (maxValue === minValue) {
      const singleValue = validData[0];
      return (
        <div className="text-center py-8">
          <div className="bg-humdb-gray-50 rounded-lg p-6 max-w-md mx-auto">
            <div className="text-2xl font-bold text-humdb-red mb-2">
              {formatNumber(singleValue.value, showFullValues)}
            </div>
            <div className="text-lg text-humdb-navy">
              {singleValue.label}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="relative" style={{ height: `${height}px` }}>
        {/* Chart SVG with reduced height to accommodate labels */}
        <svg className="w-full" style={{ height: `${chartHeight}px` }} viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="xMidYMid meet">
          {/* Grid lines */}
          {[0, 25, 50, 75, 100].map((y, index) => (
            <line
              key={index}
              x1="0"
              y1={y}
              x2={chartWidth}
              y2={y}
              stroke="#E2E8F0"
              strokeWidth="0.5"
              strokeDasharray="2,2"
            />
          ))}

          {/* Area fill */}
          <defs>
            <linearGradient id="areaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#ED1C24" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#ED1C24" stopOpacity="0.05" />
            </linearGradient>
          </defs>

          {/* Area fill path */}
          <path
            d={`M 0,${chartHeight} ${validData.map((item, index) => {
              const x = (index / (validData.length - 1)) * chartWidth;
              const y = chartHeight - ((item.value - minValue) / (maxValue - minValue)) * chartHeight;
              // Validate coordinates to prevent NaN
              const validX = isNaN(x) ? 0 : x;
              const validY = isNaN(y) ? chartHeight : y;
              return `${index === 0 ? '' : 'L'} ${validX},${validY}`;
            }).join(' ')} L ${chartWidth},${chartHeight} Z`}
            fill="url(#areaGradient)"
          />

          {/* Main line */}
          <polyline
            fill="none"
            stroke="#ED1C24"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={validData.map((item, index) => {
              const x = (index / (validData.length - 1)) * chartWidth;
              const y = chartHeight - ((item.value - minValue) / (maxValue - minValue)) * chartHeight;
              // Validate coordinates to prevent NaN
              const validX = isNaN(x) ? 0 : x;
              const validY = isNaN(y) ? chartHeight : y;
              return `${validX},${validY}`;
            }).join(' ')}
          />

          {/* Data points with glow effect */}
          {validData.map((item, index) => {
            const x = (index / (validData.length - 1)) * chartWidth;
            const y = chartHeight - ((item.value - minValue) / (maxValue - minValue)) * chartHeight;
            // Validate coordinates to prevent NaN
            const validX = isNaN(x) ? 0 : x;
            const validY = isNaN(y) ? chartHeight : y;
            return (
              <g key={index}>
                {/* Invisible larger hit area */}
                <circle
                  cx={validX}
                  cy={validY}
                  r="12"
                  fill="transparent"
                />
                {/* Glow effect */}
                <circle
                  cx={validX}
                  cy={validY}
                  r="6"
                  fill="#ED1C24"
                  opacity="0.3"
                  filter="blur(2px)"
                />
                {/* Main circle */}
                <circle
                  cx={validX}
                  cy={validY}
                  r="4"
                  fill="#ED1C24"
                  stroke="#FFFFFF"
                  strokeWidth="2"
                />
              </g>
            );
          })}
        </svg>

        {/* Tooltip */}
        {tooltip.show && (
          <div
            className={`absolute z-50 bg-humdb-navy text-white px-3 py-2 rounded-lg shadow-lg text-sm max-w-xs ${
              tooltip.position === 'above' ? 'bottom-full mb-1' : 'top-full mt-1'
            }`}
            style={{
              left: `${tooltip.x}%`,
              transform: 'translateX(-50%)'
            }}
          >
            <div className="font-semibold mb-1">{tooltip.content.title}</div>
            <div className="text-humdb-gray-200 text-xs">{tooltip.content.explanation}</div>
            <div
              className={`absolute w-0 h-0 border-l-4 border-r-4 border-transparent ${
                tooltip.position === 'above'
                  ? 'top-full border-t-4 border-t-humdb-navy'
                  : 'bottom-full border-b-4 border-b-humdb-navy'
              }`}
              style={{ left: '50%', transform: 'translateX(-50%)' }}
            ></div>
          </div>
        )}

        {/* X-axis labels positioned below the chart with precise alignment */}
        <div className="relative text-xs mt-2" style={{ height: `${labelHeight}px` }}>
          {validData.map((item, index) => {
            const labelPosition = (index / (validData.length - 1)) * 100;
            return (
              <div
                key={index}
                className="absolute text-center cursor-pointer"
                style={{
                  left: `${labelPosition}%`,
                  transform: 'translateX(-50%)',
                  width: `${100 / validData.length}%`
                }}
                onMouseEnter={(e) => {
                  // Clear any existing timeout
                  if (tooltipTimeout) {
                    clearTimeout(tooltipTimeout);
                    setTooltipTimeout(null);
                  }

                  const tooltipContent = getTooltipContent(item, index);
                  const position = getTooltipPosition(index, validData.length);
                  setTooltip({
                    show: true,
                    content: tooltipContent,
                    x: position.x,
                    position: position.position
                  });
                }}
                onMouseLeave={() => {
                  // Add a small delay before hiding the tooltip
                  const timeout = setTimeout(() => {
                    setTooltip({ show: false, content: '', x: 0, position: 'above' });
                  }, 150);
                  setTooltipTimeout(timeout);
                }}
              >
                <div className="font-semibold text-humdb-navy mb-1 text-xs leading-tight">{item.label}</div>
                                 <div className="text-humdb-red font-bold text-xs">{formatNumber(item.value, showFullValues)}</div>
                {index > 0 && (
                  <div className="text-xs text-humdb-gray-500 mt-1">
                    {item.value > validData[index - 1].value ? '↗' : '↘'}
                    {Math.abs(((item.value - validData[index - 1].value) / validData[index - 1].value) * 100).toFixed(1)}%
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderPieChart = () => {
    const total = validData.reduce((sum, item) => sum + item.value, 0);

    // Early return if total is 0 or invalid
    if (total === 0 || isNaN(total)) {
      return (
        <div className="text-center py-8">
          <div className="text-humdb-gray-500">No valid data to display</div>
        </div>
      );
    }

    let currentAngle = 0;

    return (
      <div className="flex items-center space-x-6">
        <div className="relative" style={{ width: `${height}px`, height: `${height}px` }}>
          <svg className="w-full h-full" viewBox="0 0 100 100">
            {validData.map((item, index) => {
              // Ensure item.value is a valid number
              const value = isNaN(item.value) ? 0 : item.value;
              const percentage = (value / total) * 100;
              const angle = (percentage / 100) * 360;

              // Ensure angle is a valid number
              if (isNaN(angle) || angle <= 0) {
                return null; // Skip this segment if angle is invalid
              }

              // Calculate coordinates with proper validation
              const currentAngleRad = (currentAngle * Math.PI) / 180;
              const endAngleRad = ((currentAngle + angle) * Math.PI) / 180;

              const x1 = 50 + 40 * Math.cos(currentAngleRad);
              const y1 = 50 + 40 * Math.sin(currentAngleRad);
              const x2 = 50 + 40 * Math.cos(endAngleRad);
              const y2 = 50 + 40 * Math.sin(endAngleRad);

              // Validate coordinates
              if (isNaN(x1) || isNaN(y1) || isNaN(x2) || isNaN(y2)) {
                return null; // Skip this segment if coordinates are invalid
              }

              const largeArcFlag = angle > 180 ? 1 : 0;

              const pathData = [
                `M 50 50`,
                `L ${x1} ${y1}`,
                `A 40 40 0 ${largeArcFlag} 1 ${x2} ${y2}`,
                'Z'
              ].join(' ');

              currentAngle += angle;

              return (
                <path
                  key={index}
                  d={pathData}
                  fill={`hsl(${(index * 137.5) % 360}, 70%, 50%)`}
                  stroke="#fff"
                  strokeWidth="1"
                />
              );
            }).filter(Boolean)} {/* Remove null entries */}
          </svg>
        </div>
        <div className="space-y-2">
          {validData.map((item, index) => (
            <div key={index} className="flex items-center space-x-2">
              <div
                className="w-3 h-3 rounded"
                style={{ backgroundColor: `hsl(${(index * 137.5) % 360}, 70%, 50%)` }}
              />
              <span className="text-sm text-humdb-gray-700">{item.label}</span>
              <span className="text-sm text-humdb-gray-500">
                ({((item.value / total) * 100).toFixed(1)}%)
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="bg-white p-8 border border-humdb-gray-300 relative chart-container" ref={containerRef}>
      {/* Copy Data Button */}
      <button
        onClick={() => {
          // Convert data to CSV format
          const csvHeader = 'Label,Value\n';
          const csvData = validData.map(item => `${item.label},${item.value}`).join('\n');
          const csvContent = csvHeader + csvData;

          // Copy to clipboard
          navigator.clipboard.writeText(csvContent).then(() => {
            // Show success feedback
            const button = document.querySelector('.copy-data-btn');
            const saveButton = document.querySelector('.save-chart-btn');
            const formatButton = document.querySelector('.format-toggle-btn');

            if (button) {
              const originalText = button.innerHTML;
              const originalClass = button.className;

              // Expand button to the left and change text
              button.innerHTML = '✓ Copied!';
              button.className = 'absolute top-4 right-4 px-4 py-1 bg-green-500 text-white rounded-md text-xs font-medium transition-all duration-200 z-30';

              // Push other buttons to the left
              if (saveButton) {
                saveButton.className = 'absolute top-4 right-24 px-3 py-1 bg-humdb-red text-white rounded-md text-xs font-medium transition-all duration-200 z-30 hover:bg-humdb-red-dark save-chart-btn';
              }
              if (formatButton) {
                formatButton.className = 'absolute top-4 right-36 px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 z-30 bg-gray-100 text-gray-700 hover:bg-gray-200 format-toggle-btn';
              }

              setTimeout(() => {
                // Restore original state
                button.innerHTML = originalText;
                button.className = originalClass;

                // Restore other buttons to original positions
                if (saveButton) {
                  saveButton.className = 'absolute top-4 right-16 px-3 py-1 bg-humdb-red text-white rounded-md text-xs font-medium transition-all duration-200 z-30 hover:bg-humdb-red-dark save-chart-btn';
                }
                if (formatButton) {
                  formatButton.className = 'absolute top-4 right-28 px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 z-30 bg-gray-100 text-gray-700 hover:bg-gray-200 format-toggle-btn';
                }
              }, 2000);
            }
          });
        }}
        className="absolute top-4 right-4 px-3 py-1 bg-humdb-red text-white rounded-md text-xs font-medium transition-all duration-200 z-30 hover:bg-humdb-red-dark copy-data-btn"
        title="Copy data as CSV"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      </button>

      {/* Save Chart Button */}
      <button
        onClick={() => {
          // Create a canvas element to capture the chart
          const chartContainer = document.querySelector('.chart-container');
          if (chartContainer) {
            html2canvas(chartContainer).then(canvas => {
              const link = document.createElement('a');
              link.download = `${title || 'chart'}.png`;
              link.href = canvas.toDataURL();
              link.click();
            });
          }
        }}
        className="absolute top-4 right-16 px-3 py-1 bg-humdb-red text-white rounded-md text-xs font-medium transition-all duration-200 z-30 hover:bg-humdb-red-dark save-chart-btn"
        title="Save chart as PNG"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      </button>

      {/* Format Toggle Button */}
      <button
        onClick={() => setShowFullValues(!showFullValues)}
        className={`absolute top-4 right-28 px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 z-30 format-toggle-btn ${
          showFullValues
            ? 'bg-blue-500 text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        }`}
        title={showFullValues ? "Show abbreviated values (K, M, B)" : "Show full values (1,234,567)"}
      >
        {showFullValues ? '1.2K' : '1,234'}
      </button>

      {title && (
        <div className="mb-6">
          <h3 className="text-xl font-bold text-humdb-navy mb-2">{title}</h3>
          <p className="text-xs text-humdb-gray-500 mb-2">
            Data source: Humanitarian Databank
          </p>
          <div className="w-12 h-1 bg-humdb-red rounded-full"></div>
        </div>
      )}
      {type === 'bar' && (stackedMode ? renderStackedBarChart() : renderBarChart())}
      {type === 'line' && renderLineChart()}
      {type === 'pie' && renderPieChart()}
    </div>
  );
};

export default MultiChart;
