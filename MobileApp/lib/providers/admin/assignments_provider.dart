import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../../config/app_config.dart';
import '../../models/admin/admin_assignment.dart';
import '../../models/admin/admin_assignment_detail.dart';
import '../../utils/mobile_api_json.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';
import '../shared/async_operation_mixin.dart';

class AssignmentsProvider with ChangeNotifier, AsyncOperationMixin {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<AdminAssignment> _assignments = [];
  bool _isLoading = false;
  String? _error;

  List<AdminAssignment> get assignments => _assignments;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadAssignments() async {
    await runAsyncOperation(() async {
      if (shouldDeferRemoteFetch) {
        _isLoading = false;
        notifyListeners();
        return;
      }
      _isLoading = true;
      _error = null;
      notifyListeners();

      final collected = <AdminAssignment>[];
      var page = 1;
      var totalPages = 1;
      http.Response? response;
      try {
      while (page <= totalPages && page <= 25) {
        response = await _errorHandler.executeWithErrorHandling<http.Response>(
          apiCall: () => _api.get(
            AppConfig.mobileAssignmentsEndpoint,
            queryParams: {'page': '$page', 'per_page': '200'},
          ),
          context: 'Load Assignments',
          defaultValue: null,
          maxRetries: 1,
          handleAuthErrors: true,
        );
        if (response == null || response.statusCode != 200) break;
        final jsonData = decodeJsonObject(response.body);
        if (jsonData['success'] != true) break;
        collected.addAll(
          mobileDataMaps(jsonData).map(AdminAssignment.fromJson),
        );
        totalPages = mobileTotalPages(jsonData);
        page += 1;
      }
      } catch (e, stackTrace) {
        final error = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Parse Assignments',
        );
        _error = error.getUserMessage();
        _assignments = collected;
        _isLoading = false;
        notifyListeners();
        return;
      }

      if (response == null && collected.isEmpty) {
        _error = 'Unable to load assignments. Please try again.';
        _assignments = [];
        _isLoading = false;
        notifyListeners();
        return;
      }

      if (collected.isNotEmpty || (response != null && response.statusCode == 200)) {
        try {
          if (collected.isNotEmpty || (response != null && response.body.trimLeft().startsWith('{'))) {
            _assignments = collected;
            _error = null;
          } else if (response != null) {
            _assignments = _parseAssignmentsFromHtml(response.body);
            _error = null;
          }
        } catch (e, stackTrace) {
          final error = _errorHandler.parseError(
            error: e,
            stackTrace: stackTrace,
            context: 'Parse Assignments',
          );
          _error = error.getUserMessage();
          _assignments = [];
        }
      } else {
        final error = _errorHandler.parseError(
          error: Exception('HTTP ${response?.statusCode ?? 'unknown'}'),
          response: response,
          context: 'Load Assignments',
        );
        _error = error.getUserMessage();
        _assignments = [];
      }

      _isLoading = false;
      notifyListeners();
    });
  }

  List<AdminAssignment> _parseAssignmentsFromHtml(String html) {
    final assignments = <AdminAssignment>[];

    // Parse assignments from HTML table
    final rowPattern = RegExp(
      r'<tr[^>]*class="[^"]*bg-white[^"]*"[^>]*>([\s\S]*?)</tr>',
      caseSensitive: false,
    );

    final rows = rowPattern.allMatches(html);
    int index = 0;

    for (final row in rows) {
      final rowHtml = row.group(1) ?? '';

      // Extract cells
      final cells = RegExp(
        r'<td[^>]*>([\s\S]*?)</td>',
        caseSensitive: false,
      ).allMatches(rowHtml).toList();

      if (cells.length < 4) continue;

      // Period name (first cell)
      final periodHtml = cells[0].group(1) ?? '';
      final periodName = periodHtml.replaceAll(RegExp(r'<[^>]+>'), '').trim();

      // Template name (second cell)
      final templateHtml = cells[1].group(1) ?? '';
      final templateName =
          templateHtml.replaceAll(RegExp(r'<[^>]+>'), '').trim();

      // Public URL status (third cell)
      final publicUrlHtml = cells[2].group(1) ?? '';
      final hasPublicUrl = !publicUrlHtml.contains('Not Generated');
      final isPublicActive = publicUrlHtml.contains('Active');

      // Extract assignment ID from edit link
      final editLinkMatch = RegExp(
        r'/admin/assignments/edit-assignment/(\d+)',
        caseSensitive: false,
      ).firstMatch(rowHtml);

      final id = editLinkMatch != null
          ? int.tryParse(editLinkMatch.group(1) ?? '0') ?? index
          : index;

      // Extract public URL if available
      String? publicUrl;
      final urlMatch = RegExp(
        r'data-copy-url="([^"]+)"',
        caseSensitive: false,
      ).firstMatch(publicUrlHtml);
      if (urlMatch != null) {
        publicUrl = urlMatch.group(1);
      }

      assignments.add(AdminAssignment(
        id: id,
        periodName: periodName,
        templateName: templateName.isNotEmpty ? templateName : null,
        hasPublicUrl: hasPublicUrl,
        isPublicActive: isPublicActive,
        publicUrl: publicUrl,
      ));

      index++;
    }

    return assignments;
  }

  /// Loads full assignment detail (entities, deadlines, flags). Returns null on failure.
  Future<AdminAssignmentDetail?> fetchAssignmentDetail(int assignmentId) async {
    if (shouldDeferRemoteFetch) {
      return null;
    }
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
        AppConfig.mobileAssignmentDetailEndpoint(assignmentId),
      ),
      context: 'Load Assignment Detail',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null || response.statusCode != 200) {
      return null;
    }
    try {
      final root = decodeJsonObject(response.body);
      final data = unwrapMobileDataMap(root);
      if (data == null) return null;
      return AdminAssignmentDetail.fromJson(data);
    } catch (e, stackTrace) {
      _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Parse Assignment Detail',
      );
      return null;
    }
  }

  Future<bool> deleteAssignment(int assignmentId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post(
        '${AppConfig.mobileAssignmentsEndpoint}/$assignmentId/delete',
        body: {},
      ),
      context: 'Delete Assignment',
      defaultValue: null,
      maxRetries: 0,
      handleAuthErrors: true,
    );

    if (response == null) return false;
    return response.statusCode == 200 || response.statusCode == 302;
  }

  Future<bool> generatePublicUrl(int assignmentId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post(
        '${AppConfig.mobileAssignmentsEndpoint}/$assignmentId/generate-url',
        body: {},
      ),
      context: 'Generate Public URL',
      defaultValue: null,
      maxRetries: 0,
      handleAuthErrors: true,
    );

    if (response == null) return false;
    return response.statusCode == 200 || response.statusCode == 302;
  }

  Future<bool> togglePublicAccess(int assignmentId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post(
        '${AppConfig.mobileAssignmentsEndpoint}/$assignmentId/toggle-public',
        body: {},
      ),
      context: 'Toggle Public Access',
      defaultValue: null,
      maxRetries: 0,
      handleAuthErrors: true,
    );

    if (response == null) return false;
    return response.statusCode == 200 || response.statusCode == 302;
  }
}
