import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import '../../models/admin/admin_assignment.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';

class AssignmentsProvider with ChangeNotifier {
  final ApiService _api = ApiService();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<AdminAssignment> _assignments = [];
  bool _isLoading = false;
  String? _error;

  List<AdminAssignment> get assignments => _assignments;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadAssignments() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get('/admin/assignments'),
      context: 'Load Assignments',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load assignments. Please try again.';
      _assignments = [];
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
            final assignmentsList = jsonData['assignments'] as List<dynamic>?;
            if (assignmentsList != null) {
              _assignments = assignmentsList
                  .map((json) => AdminAssignment.fromJson(json as Map<String, dynamic>))
                  .toList();
            } else {
              _assignments = [];
            }
            _error = null;
          } else {
            // Fallback to HTML parsing for backward compatibility
            final html = response.body;
            _assignments = _parseAssignmentsFromHtml(html);
            _error = null;
          }
        } catch (e) {
          // If JSON parsing fails, try HTML parsing as fallback
          print('[ASSIGNMENTS] JSON parse failed, trying HTML: $e');
          final html = response.body;
          _assignments = _parseAssignmentsFromHtml(html);
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
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Load Assignments',
      );
      _error = error.getUserMessage();
      _assignments = [];
    }

    _isLoading = false;
    notifyListeners();
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

  Future<bool> deleteAssignment(int assignmentId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post(
        '/admin/assignments/delete-assignment/$assignmentId',
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
        '/admin/assignments/generate-public-url/$assignmentId',
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
        '/admin/assignments/toggle-public-access/$assignmentId',
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
