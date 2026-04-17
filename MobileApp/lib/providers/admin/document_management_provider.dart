import 'package:flutter/foundation.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../config/app_config.dart';
import '../../models/shared/document.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

class DocumentManagementProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<Document> _documents = [];
  bool _isLoading = false;
  String? _error;

  List<Document> get documents => _documents;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadDocuments({
    String? search,
    String? statusFilter,
    String? typeFilter,
    String? countryFilter,
  }) async {
    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      notifyListeners();
      return;
    }
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final queryParams = <String, String>{};
      if (search != null && search.isNotEmpty) {
        queryParams['search'] = search;
      }
      if (statusFilter != null && statusFilter.isNotEmpty) {
        queryParams['status'] = statusFilter;
      }
      if (typeFilter != null && typeFilter.isNotEmpty) {
        queryParams['type'] = typeFilter;
      }
      if (countryFilter != null && countryFilter.isNotEmpty) {
        queryParams['country'] = countryFilter;
      }

      final response =
          await _errorHandler.executeWithErrorHandling<http.Response>(
        apiCall: () => _api.get(
          AppConfig.mobileDocumentsEndpoint,
          queryParams: queryParams.isNotEmpty ? queryParams : null,
        ),
        context: 'Load Documents',
        defaultValue: null,
        maxRetries: 1,
        handleAuthErrors: true,
      );

      if (response == null) {
        _error = 'Unable to load documents. Please try again.';
        _documents = [];
        _isLoading = false;
        notifyListeners();
        return;
      }

      if (response.statusCode == 200) {
        try {
          // Try to parse as JSON first
          try {
            final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
            if (jsonData['success'] == true) {
              final rawData = jsonData['data'];
              final List<dynamic>? documentsList = rawData is List
                  ? rawData
                  : rawData is Map ? (rawData['documents'] as List<dynamic>?) : (jsonData['documents'] as List<dynamic>?);
              if (documentsList != null) {
                _documents = documentsList
                    .map((json) => Document.fromJson(json as Map<String, dynamic>))
                    .toList();
              } else {
                _documents = [];
              }
              _error = null;
            } else {
              // Fallback to HTML parsing for backward compatibility
              _documents = _parseDocumentsFromHtml(response.body);
              _error = null;
            }
          } catch (e) {
            // If JSON parsing fails, try HTML parsing as fallback
            DebugLogger.logWarn('DOCUMENTS', 'JSON parse failed, trying HTML: $e');
            _documents = _parseDocumentsFromHtml(response.body);
            _error = null;
          }
        } catch (e, stackTrace) {
          final error = _errorHandler.parseError(
            error: e,
            stackTrace: stackTrace,
            context: 'Parse Documents',
          );
          _error = error.getUserMessage();
          _documents = [];
        }
      } else {
        final error = _errorHandler.parseError(
          error: Exception('HTTP ${response.statusCode}'),
          response: response,
          context: 'Load Documents',
        );
        _error = error.getUserMessage();
        _documents = [];
      }
    } catch (e, stackTrace) {
      final error = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Load Documents',
      );
      _error = error.getUserMessage();
      _documents = [];
      _errorHandler.logError(error);
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  List<Document> _parseDocumentsFromHtml(String html) {
    final documents = <Document>[];

    // Parse HTML table rows
    final rowPattern = RegExp(
      r'<tr[^>]*>([\s\S]*?)</tr>',
      caseSensitive: false,
    );

    final rows = rowPattern.allMatches(html);
    int index = 0;

    for (final row in rows) {
      final rowHtml = row.group(1) ?? '';

      // Skip header rows
      if (rowHtml.contains('<th') || rowHtml.contains('thead')) {
        continue;
      }

      // Extract cells
      final cells = RegExp(
        r'<td[^>]*>([\s\S]*?)</td>',
        caseSensitive: false,
      ).allMatches(rowHtml).toList();

      if (cells.length >= 3) {
        // Extract country from first cell
        final countryHtml = cells[0].group(1) ?? '';
        final countryName = _extractText(countryHtml);

        // Extract filename from second cell
        final fileNameHtml = cells.length > 1 ? cells[1].group(1) ?? '' : '';
        final fileName = _extractText(fileNameHtml);

        // Extract document type from third cell
        final typeHtml = cells.length > 2 ? cells[2].group(1) ?? '' : '';
        final documentType = _extractText(typeHtml);

        // Extract status from fourth cell (if exists)
        final statusHtml = cells.length > 3 ? cells[3].group(1) ?? '' : '';
        final status = _extractText(statusHtml);

        // Extract uploaded date from fifth cell (if exists)
        final dateHtml = cells.length > 4 ? cells[4].group(1) ?? '' : '';
        final dateText = _extractText(dateHtml);

        // Try to extract document ID from edit/delete links
        final idMatch = RegExp(
          r'/admin/documents/(?:edit|delete|serve|download)/(\d+)',
          caseSensitive: false,
        ).firstMatch(rowHtml);

        final id = idMatch != null
            ? int.tryParse(idMatch.group(1) ?? '0') ?? index
            : index;

        DateTime? uploadedAt;
        try {
          if (dateText.isNotEmpty) {
            // Try to parse various date formats
            uploadedAt = DateTime.parse(dateText);
          }
        } catch (e) {
          // Keep null if parsing fails
        }

        documents.add(Document(
          id: id,
          fileName: fileName.isNotEmpty ? fileName : null,
          countryName: countryName.isNotEmpty ? countryName : null,
          documentType: documentType.isNotEmpty ? documentType : null,
          status: status.isNotEmpty ? status : null,
          uploadedAt: uploadedAt,
        ));

        index++;
      }
    }

    return documents;
  }

  String _extractText(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]+>'), '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  Future<bool> deleteDocument(int documentId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post(
        '${AppConfig.mobileDocumentsEndpoint}/$documentId/delete',
      ),
      context: 'Delete Document',
      defaultValue: null,
      maxRetries: 0,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to delete document. Please try again.';
      notifyListeners();
      return false;
    }

    if (response.statusCode == 200 || response.statusCode == 302) {
      await loadDocuments();
      return true;
    } else {
      final error = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Delete Document',
      );
      _error = error.getUserMessage();
      notifyListeners();
      return false;
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
