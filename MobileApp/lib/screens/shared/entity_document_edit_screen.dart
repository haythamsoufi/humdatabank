import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/shared/document.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/entity_document_repository_provider.dart';
import '../../utils/constants.dart';
import '../../utils/ios_constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/mobile_screen_scaffold.dart';

const String _coverImageType = 'Cover Image';
const int _maxAttachmentBytes = 50 * 1024 * 1024;
const Set<String> _allowedExtensions = {
  'pdf',
  'doc',
  'docx',
  'xls',
  'xlsx',
  'ppt',
  'pptx',
  'txt',
  'csv',
  'jpg',
  'jpeg',
  'png',
  'gif',
  'webp',
};

/// Extensions for Windows, MIME types for Android, UTIs for iOS.
/// A group that sets only extensions throws on iOS before the picker opens.
const XTypeGroup _replacementTypeGroup = XTypeGroup(
  label: 'documents',
  extensions: [
    'pdf',
    'doc',
    'docx',
    'xls',
    'xlsx',
    'ppt',
    'pptx',
    'txt',
    'csv',
    'jpg',
    'jpeg',
    'png',
    'gif',
    'webp',
  ],
  mimeTypes: [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain',
    'text/csv',
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'application/octet-stream',
  ],
  uniformTypeIdentifiers: [
    'public.data',
    'public.content',
    'com.adobe.pdf',
    'public.image',
    'public.plain-text',
    'public.comma-separated-values-text',
    'com.microsoft.word.doc',
    'org.openxmlformats.wordprocessingml.document',
    'com.microsoft.excel.xls',
    'org.openxmlformats.spreadsheetml.sheet',
    'com.microsoft.powerpoint.ppt',
    'org.openxmlformats.presentationml.presentation',
  ],
);

class EntityDocumentEditScreen extends StatefulWidget {
  final Document document;

  const EntityDocumentEditScreen({super.key, required this.document});

  @override
  State<EntityDocumentEditScreen> createState() => _EntityDocumentEditScreenState();
}

class _EntityDocumentEditScreenState extends State<EntityDocumentEditScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _filenameController;
  late final TextEditingController _periodController;
  late String? _documentType;
  late String? _language;
  late String _status;
  late bool _isPublic;
  Uint8List? _replacementBytes;
  String? _replacementName;
  bool _saving = false;
  bool _loadingChoices = true;

  @override
  void initState() {
    super.initState();
    final document = widget.document;
    _filenameController = TextEditingController(text: document.fileName ?? '');
    _periodController = TextEditingController(
      text: document.period ?? document.assignmentPeriod ?? '',
    );
    _documentType = document.documentType;
    _language = document.language;
    _status = _normalizeStatus(document.status);
    _isPublic = document.isPublic || document.documentType == _coverImageType;
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadChoices());
  }

  Future<void> _loadChoices() async {
    if (!mounted) return;
    await context.read<EntityDocumentRepositoryProvider>().loadEditCatalog();
    if (mounted) setState(() => _loadingChoices = false);
  }

  @override
  void dispose() {
    _filenameController.dispose();
    _periodController.dispose();
    super.dispose();
  }

  bool get _isCoverImage => _documentType == _coverImageType;

  bool get _canChangeStatus {
    if (widget.document.canChangeStatus) return true;
    final user = context.read<AuthProvider>().user;
    return user?.isAdmin ?? false;
  }

  String _normalizeStatus(String? raw) {
    final value = raw?.trim().toLowerCase();
    if (value == 'approved' || value == 'rejected') return value!;
    return 'pending';
  }

  String _statusLabel(AppLocalizations loc, String status) {
    switch (status) {
      case 'approved':
        return loc.approved;
      case 'rejected':
        return loc.rejected;
      default:
        return loc.pendingReview;
    }
  }

  InputDecoration _decoration(BuildContext context, String label, {String? hint}) {
    return InputDecoration(
      labelText: label,
      hintText: hint,
      filled: true,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(
          IOSDimensions.borderRadiusLargeOf(context),
        ),
        borderSide: BorderSide.none,
      ),
    );
  }

  Future<void> _pickReplacement(AppLocalizations loc) async {
    try {
      final file = await openFile(
        acceptedTypeGroups: const [_replacementTypeGroup],
      );
      if (file == null || !mounted) return;
      final name = _attachmentName(file);
      final dot = name.lastIndexOf('.');
      final ext = dot >= 0 ? name.substring(dot + 1).toLowerCase() : '';
      if (!_allowedExtensions.contains(ext)) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(loc.fileTypeNotAllowed)),
        );
        return;
      }
      final bytes = await file.readAsBytes();
      if (!mounted) return;
      if (bytes.length > _maxAttachmentBytes) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(loc.fileTooLarge)),
        );
        return;
      }
      setState(() {
        _replacementBytes = bytes;
        _replacementName = name;
      });
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.couldNotOpenFiles)),
      );
    }
  }

  String _attachmentName(XFile file) {
    final fromName = file.name.trim();
    final raw = fromName.isNotEmpty ? fromName : file.path.trim();
    final parts = raw.split(RegExp(r'[\\/]'));
    final base = parts.isEmpty ? raw : parts.last.trim();
    return base.isEmpty ? 'document' : base;
  }

  Future<void> _save(AppLocalizations loc) async {
    if (_saving) return;
    if (_formKey.currentState?.validate() != true) return;
    final documentType = _documentType?.trim() ?? '';
    if (documentType.isEmpty) return;

    setState(() => _saving = true);
    final provider = Provider.of<EntityDocumentRepositoryProvider>(
      context,
      listen: false,
    );
    final result = await provider.saveDocument(
      documentId: widget.document.id,
      documentType: documentType,
      language: _isCoverImage ? null : _language,
      period: _isCoverImage ? null : _periodController.text.trim(),
      isPublic: _isCoverImage || _isPublic,
      filename: _filenameController.text.trim(),
      status: _canChangeStatus ? _status : null,
      fileBytes: _replacementBytes,
      fileName: _replacementName,
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (result.error == null) {
      Navigator.of(context).pop(result.document ?? widget.document);
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(result.error!)));
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final provider = context.watch<EntityDocumentRepositoryProvider>();
    final types = _typeOptions(provider.documentTypes);
    final languages = _languageOptions(provider.languages);

    return MobileScreenScaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(title: loc.editDocument),
      bottomNavigationBar: AppBottomNavigationBar.shellTabBar,
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            if (types.isEmpty && !_loadingChoices)
              TextFormField(
                initialValue: _documentType ?? '',
                enabled: !_saving,
                decoration: _decoration(context, loc.documentType),
                onChanged: (value) {
                  final wasCover = _isCoverImage;
                  _documentType = value;
                  if (wasCover != (value == _coverImageType)) {
                    setState(() {
                      if (value == _coverImageType) _isPublic = true;
                    });
                  }
                },
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return loc.selectDocumentType;
                  }
                  return null;
                },
              )
            else
              _choiceField(
                label: loc.documentType,
                value: _documentType,
                display: _documentType,
                enabled: !_saving && !_loadingChoices && types.isNotEmpty,
                loading: _loadingChoices && types.isEmpty,
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return loc.selectDocumentType;
                  }
                  return null;
                },
                onPick: () => _pickChoice(
                  title: loc.documentType,
                  options: [
                    for (final type in types) (value: type, label: type, hint: ''),
                  ],
                ).then((value) {
                  if (value == null || !mounted) return;
                  setState(() {
                    _documentType = value;
                    if (value == _coverImageType) _isPublic = true;
                  });
                }),
              ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _filenameController,
              enabled: !_saving,
              decoration: _decoration(context, loc.filename),
              textInputAction: TextInputAction.next,
              validator: (value) {
                if (value == null || value.trim().isEmpty) return loc.filename;
                return null;
              },
            ),
            if (!_isCoverImage) ...[
              const SizedBox(height: 12),
              if (languages.isEmpty && !_loadingChoices)
                TextFormField(
                  initialValue: _language ?? '',
                  enabled: !_saving,
                  decoration: _decoration(context, loc.language),
                  onChanged: (value) => _language = value.trim(),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) return loc.language;
                    return null;
                  },
                )
              else
                _choiceField(
                  label: loc.language,
                  value: _language,
                  display: _languageLabel(languages),
                  enabled: !_saving && !_loadingChoices && languages.isNotEmpty,
                  loading: _loadingChoices && languages.isEmpty,
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) return loc.language;
                    return null;
                  },
                  onPick: () => _pickChoice(
                    title: loc.language,
                    options: [
                      for (final item in languages)
                        (
                          value: item.code,
                          label: item.name,
                          hint: item.englishName,
                        ),
                    ],
                  ).then((value) {
                    if (value == null || !mounted) return;
                    setState(() => _language = value);
                  }),
                ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _periodController,
                enabled: !_saving,
                decoration: _decoration(context, loc.period, hint: loc.periodHint),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) return loc.period;
                  return null;
                },
              ),
            ],
            if (_isCoverImage)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  loc.coverImageAlwaysPublic,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: context.textSecondaryColor,
                  ),
                ),
              ),
            if (_canChangeStatus) ...[
              const SizedBox(height: 12),
              _choiceField(
                label: loc.documentStatus,
                value: _status,
                display: _statusLabel(loc, _status),
                enabled: !_saving,
                loading: false,
                validator: (value) => null,
                onPick: () => _pickChoice(
                  title: loc.documentStatus,
                  options: [
                    (value: 'pending', label: loc.pendingReview, hint: ''),
                    (value: 'approved', label: loc.approved, hint: ''),
                    (value: 'rejected', label: loc.rejected, hint: ''),
                  ],
                ).then((value) {
                  if (value == null || !mounted) return;
                  setState(() => _status = value);
                }),
              ),
            ],
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(loc.publicDocument),
              value: _isCoverImage || _isPublic,
              onChanged: _saving || _isCoverImage
                  ? null
                  : (value) => setState(() => _isPublic = value),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _saving ? null : () => _pickReplacement(loc),
              icon: const Icon(Icons.attach_file),
              label: Text(loc.replaceAttachment),
            ),
            if (_replacementName != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${loc.newFileSelected}: $_replacementName',
                      style: theme.textTheme.bodySmall,
                    ),
                  ),
                  TextButton(
                    onPressed: _saving
                        ? null
                        : () {
                            setState(() {
                              _replacementBytes = null;
                              _replacementName = null;
                            });
                          },
                    child: Text(loc.clearSelection),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _saving ? null : () => _save(loc),
              style: FilledButton.styleFrom(
                backgroundColor: Color(AppConstants.ifrcRed),
                foregroundColor: Colors.white,
                minimumSize: const Size.fromHeight(48),
              ),
              child: _saving
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : Text(loc.save),
            ),
          ],
        ),
      ),
    );
  }

  List<String> _typeOptions(List<String> fromServer) {
    final options = <String>[...fromServer];
    final current = _documentType?.trim();
    if (current != null && current.isNotEmpty && !options.contains(current)) {
      options.insert(0, current);
    }
    return options;
  }

  List<EntityDocumentLanguageOption> _languageOptions(
    List<EntityDocumentLanguageOption> fromServer,
  ) {
    final options = <EntityDocumentLanguageOption>[...fromServer];
    final current = _language?.trim();
    if (current != null &&
        current.isNotEmpty &&
        !options.any((item) => item.code == current)) {
      options.insert(
        0,
        EntityDocumentLanguageOption(code: current, name: current),
      );
    }
    return options;
  }

  String? _languageLabel(List<EntityDocumentLanguageOption> languages) {
    final code = _language?.trim();
    if (code == null || code.isEmpty) return null;
    for (final item in languages) {
      if (item.code == code) return item.name;
    }
    return code;
  }

  Widget _choiceField({
    required String label,
    required String? value,
    required String? display,
    required bool enabled,
    required bool loading,
    required String? Function(String?) validator,
    required VoidCallback onPick,
  }) {
    return FormField<String>(
      key: ValueKey<String>('$label-${value ?? ''}'),
      initialValue: value,
      validator: validator,
      builder: (state) {
        return InkWell(
          onTap: enabled ? onPick : null,
          borderRadius: BorderRadius.circular(
            IOSDimensions.borderRadiusLargeOf(context),
          ),
          child: InputDecorator(
            decoration: _decoration(context, label).copyWith(
              errorText: state.errorText,
              suffixIcon: loading
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    )
                  : const Icon(Icons.arrow_drop_down),
            ),
            child: Text(
              (display == null || display.isEmpty) ? label : display,
              overflow: TextOverflow.ellipsis,
              style: (display == null || display.isEmpty)
                  ? TextStyle(color: context.textSecondaryColor)
                  : null,
            ),
          ),
        );
      },
    );
  }

  Future<String?> _pickChoice({
    required String title,
    required List<({String value, String label, String hint})> options,
  }) {
    final loc = AppLocalizations.of(context)!;
    return showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) {
        final height = MediaQuery.sizeOf(sheetContext).height * 0.85;
        return SizedBox(
          height: height,
          child: _OptionPickerSheet(
            title: title,
            searchHint: loc.searchPlaceholder,
            emptyLabel: loc.noResultsFound,
            options: options,
          ),
        );
      },
    );
  }
}

class _OptionPickerSheet extends StatefulWidget {
  final String title;
  final String searchHint;
  final String emptyLabel;
  final List<({String value, String label, String hint})> options;

  const _OptionPickerSheet({
    required this.title,
    required this.searchHint,
    required this.emptyLabel,
    required this.options,
  });

  @override
  State<_OptionPickerSheet> createState() => _OptionPickerSheetState();
}

class _OptionPickerSheetState extends State<_OptionPickerSheet> {
  final _query = TextEditingController();

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final needle = _query.text.trim().toLowerCase();
    final visible = needle.isEmpty
        ? widget.options
        : widget.options.where((option) {
            return option.label.toLowerCase().contains(needle) ||
                option.hint.toLowerCase().contains(needle) ||
                option.value.toLowerCase().contains(needle);
          }).toList();

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: Text(widget.title, style: Theme.of(context).textTheme.titleMedium),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
          child: TextField(
            controller: _query,
            autofocus: true,
            decoration: InputDecoration(
              hintText: widget.searchHint,
              prefixIcon: const Icon(Icons.search),
              border: const OutlineInputBorder(),
              isDense: true,
            ),
            onChanged: (_) => setState(() {}),
          ),
        ),
        Expanded(
          child: visible.isEmpty
              ? Center(child: Text(widget.emptyLabel))
              : ListView.builder(
                  itemCount: visible.length,
                  itemBuilder: (context, index) {
                    final option = visible[index];
                    return ListTile(
                      title: Text(option.label),
                      subtitle: option.hint.isNotEmpty &&
                              option.hint.toLowerCase() != option.label.toLowerCase()
                          ? Text(option.hint)
                          : null,
                      onTap: () => Navigator.of(context).pop(option.value),
                    );
                  },
                ),
        ),
      ],
    );
  }
}
