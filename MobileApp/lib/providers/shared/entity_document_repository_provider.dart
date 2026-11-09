import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../../config/app_config.dart';
import '../../models/shared/document.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';
import '../shared/async_operation_mixin.dart';

class EntityDocumentSaveResult {
  final Document? document;
  final String? error;

  const EntityDocumentSaveResult({this.document, this.error});
}

class EntityDocumentLanguageOption {
  final String code;
  final String name;
  final String englishName;

  const EntityDocumentLanguageOption({
    required this.code,
    required this.name,
    this.englishName = '',
  });
}

class EntityDocumentRepositoryProvider with ChangeNotifier, AsyncOperationMixin {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<Document> _documents = [];
  List<String> _documentTypes = [];
  List<EntityDocumentLanguageOption> _languages = [];
  bool _isLoading = false;
  String? _error;

  List<Document> get documents => _documents;
  List<String> get documentTypes => List.unmodifiable(_documentTypes);
  List<EntityDocumentLanguageOption> get languages => List.unmodifiable(_languages);
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadDocuments({
    required String entityType,
    required int entityId,
    String? search,
    String? statusFilter,
    String? typeFilter,
  }) async {
    await runAsyncOperation(() async {
      if (shouldDeferRemoteFetch) {
        _isLoading = false;
        _error = 'Unable to load documents. Please check your connection.';
        notifyListeners();
        return;
      }
      _isLoading = true;
      _error = null;
      notifyListeners();

      final queryParams = <String, String>{
        'entity_type': entityType,
        'entity_id': '$entityId',
      };
      if (search != null && search.isNotEmpty) {
        queryParams['search'] = search;
      }
      if (statusFilter != null && statusFilter.isNotEmpty) {
        queryParams['status'] = statusFilter;
      }
      if (typeFilter != null && typeFilter.isNotEmpty) {
        queryParams['type'] = typeFilter;
      }

      final collected = <Document>[];
      var page = 1;
      var totalPages = 1;
      http.Response? response;
      try {
        while (page <= totalPages && page <= 25) {
          final pageParams = {
            ...queryParams,
            'page': '$page',
            'per_page': '200',
          };
          response = await _errorHandler.executeWithErrorHandling<http.Response>(
            apiCall: () => _api.get(
              AppConfig.mobileEntityDocumentsEndpoint,
              queryParams: pageParams,
            ),
            context: 'Load entity documents',
            defaultValue: null,
            maxRetries: 1,
            handleAuthErrors: true,
          );
          if (response == null || response.statusCode != 200) break;
          final jsonData = decodeJsonObject(response.body);
          if (jsonData['success'] != true) break;
          final typeRows = mobileMetaList(jsonData, 'document_types');
          if (typeRows.isNotEmpty) {
            _documentTypes = typeRows
                .map((item) => item?.toString().trim() ?? '')
                .where((item) => item.isNotEmpty)
                .toList();
          }
          final languageRows = mobileMetaList(jsonData, 'languages');
          if (languageRows.isNotEmpty) {
            _languages = _languageOptionsFrom(languageRows);
          }
          collected.addAll(mobileDataMaps(jsonData).map(Document.fromJson));
          totalPages = mobileTotalPages(jsonData);
          page += 1;
        }
      } catch (e, stackTrace) {
        final err = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Parse entity documents',
        );
        _error = err.getUserMessage();
        _documents = collected;
        _isLoading = false;
        notifyListeners();
        return;
      }

      if (response == null && collected.isEmpty) {
        _error = 'Unable to load documents. Please try again.';
        _documents = [];
      } else if (collected.isNotEmpty ||
          (response != null && response.statusCode == 200)) {
        _documents = collected;
        _error = null;
      } else if (response != null && response.statusCode == 403) {
        _error = 'Access denied.';
        _documents = [];
      } else {
        _error = 'Unable to load documents. Please try again.';
        _documents = [];
      }
      _isLoading = false;
      notifyListeners();
    });
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  /// Loads every document type and language for the edit form.
  ///
  /// Keeps the lists already loaded from the repository when the request fails.
  Future<void> loadEditCatalog() async {
    if (shouldDeferRemoteFetch) return;
    try {
      final response = await _api.get(
        '${AppConfig.mobileEntityDocumentsEndpoint}/catalog',
      );
      if (response.statusCode != 200) return;
      final jsonData = decodeJsonObject(response.body);
      if (jsonData['success'] != true) return;
      final data = jsonData['data'];
      if (data is! Map) return;
      final typeRows = data['document_types'];
      if (typeRows is List && typeRows.isNotEmpty) {
        _documentTypes = typeRows
            .map((item) => item?.toString().trim() ?? '')
            .where((item) => item.isNotEmpty)
            .toList();
      }
      final languageRows = data['languages'];
      if (languageRows is List && languageRows.isNotEmpty) {
        _languages = _languageOptionsFrom(languageRows);
      }
      notifyListeners();
    } catch (_) {
      // The repository list may already have a catalog.
    }
  }

  List<EntityDocumentLanguageOption> _languageOptionsFrom(List<dynamic> rows) {
    return rows
        .whereType<Map>()
        .map((item) {
          final code = item['code']?.toString().trim() ?? '';
          final name = item['name']?.toString().trim() ?? '';
          final english = item['english_name']?.toString().trim() ?? '';
          return EntityDocumentLanguageOption(
            code: code,
            name: name.isEmpty ? code : name,
            englishName: english,
          );
        })
        .where((item) => item.code.isNotEmpty)
        .toList();
  }

  /// Saves field edits. When [fileBytes] is set, the stored file is replaced.
  ///
  /// [EntityDocumentSaveResult.document] is set on success. [error] is a message
  /// to show the user.
  Future<EntityDocumentSaveResult> saveDocument({
    required int documentId,
    required String documentType,
    required String? language,
    required String? period,
    required bool isPublic,
    required String filename,
    String? status,
    Uint8List? fileBytes,
    String? fileName,
  }) async {
    if (shouldDeferRemoteFetch) {
      return const EntityDocumentSaveResult(
        error: 'Unable to update the document. Please check your connection.',
      );
    }

    final fields = <String, String>{
      'document_type': documentType,
      'language': language ?? '',
      'period': period ?? '',
      'is_public': isPublic ? 'true' : 'false',
      'filename': filename,
      if (status != null && status.isNotEmpty) 'status': status,
    };

    try {
      final endpoint = '${AppConfig.mobileEntityDocumentsEndpoint}/$documentId';
      final http.Response response;
      if (fileBytes != null && fileName != null && fileName.isNotEmpty) {
        response = await _api.postMultipart(
          endpoint,
          fields: fields,
          files: [
            http.MultipartFile.fromBytes(
              'document',
              fileBytes,
              filename: fileName,
            ),
          ],
        );
      } else {
        response = await _api.post(
          endpoint,
          body: Map<String, dynamic>.from(fields),
        );
      }

      final jsonData = decodeJsonObject(response.body);
      if (response.statusCode == 200 && jsonData['success'] == true) {
        Document? updated;
        final data = jsonData['data'];
        if (data is Map<String, dynamic>) {
          updated = Document.fromJson(data);
          final index = _documents.indexWhere((item) => item.id == updated!.id);
          if (index >= 0) {
            _documents[index] = updated;
          }
        }
        notifyListeners();
        return EntityDocumentSaveResult(document: updated);
      }
      final message = jsonData['error']?.toString().trim();
      if (message != null && message.isNotEmpty) {
        return EntityDocumentSaveResult(error: message);
      }
      return const EntityDocumentSaveResult(
        error: 'Could not update the document.',
      );
    } on AuthenticationException catch (e) {
      return EntityDocumentSaveResult(error: e.message);
    } catch (e, stackTrace) {
      final err = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Update entity document',
      );
      return EntityDocumentSaveResult(error: err.getUserMessage());
    }
  }
}
