import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/public/indicator_bank_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/constants.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_checkbox_list_tile.dart';
import '../../l10n/app_localizations.dart';

/// Full-screen form to propose a new indicator for the indicator bank.
class ProposeIndicatorScreen extends StatefulWidget {
  const ProposeIndicatorScreen({super.key});

  @override
  State<ProposeIndicatorScreen> createState() => _ProposeIndicatorScreenState();
}

class _ProposeIndicatorScreenState extends State<ProposeIndicatorScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _indicatorNameController = TextEditingController();
  final _definitionController = TextEditingController();
  final _typeController = TextEditingController();
  final _unitController = TextEditingController();
  final _sectorPrimaryController = TextEditingController();
  final _sectorSecondaryController = TextEditingController();
  final _sectorTertiaryController = TextEditingController();
  final _subSectorPrimaryController = TextEditingController();
  final _subSectorSecondaryController = TextEditingController();
  final _subSectorTertiaryController = TextEditingController();
  final _reasonController = TextEditingController();
  final _additionalNotesController = TextEditingController();
  bool _emergencyContext = false;
  bool _submittingProposal = false;
  bool _submitSuccess = false;
  /// When true, name/email come from the signed-in profile and cannot be edited.
  bool _lockContactFields = false;
  AuthProvider? _authForListener;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final auth = Provider.of<AuthProvider>(context, listen: false);
      _authForListener = auth;
      _applyContactFromAuth(auth);
      auth.addListener(_onAuthChanged);
    });
  }

  void _onAuthChanged() {
    if (!mounted || _lockContactFields) return;
    _applyContactFromAuth(_authForListener!);
  }

  void _applyContactFromAuth(AuthProvider auth) {
    if (_lockContactFields) return;
    if (!auth.isAuthenticated || auth.user == null) return;
    final user = auth.user!;
    _nameController.text = user.displayName;
    _emailController.text = user.email;
    setState(() => _lockContactFields = true);
  }

  @override
  void dispose() {
    _authForListener?.removeListener(_onAuthChanged);
    _nameController.dispose();
    _emailController.dispose();
    _indicatorNameController.dispose();
    _definitionController.dispose();
    _typeController.dispose();
    _unitController.dispose();
    _sectorPrimaryController.dispose();
    _sectorSecondaryController.dispose();
    _sectorTertiaryController.dispose();
    _subSectorPrimaryController.dispose();
    _subSectorSecondaryController.dispose();
    _subSectorTertiaryController.dispose();
    _reasonController.dispose();
    _additionalNotesController.dispose();
    super.dispose();
  }

  Future<void> _submitProposal() async {
    final localizations = AppLocalizations.of(context)!;

    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() => _submittingProposal = true);

    final provider = Provider.of<IndicatorBankProvider>(context, listen: false);
    final success = await provider.proposeNewIndicator({
      'submitter_name': _nameController.text,
      'submitter_email': _emailController.text,
      'suggestion_type': 'new_indicator',
      'indicator_id': null,
      'indicator_name': _indicatorNameController.text,
      'definition': _definitionController.text,
      'type': _typeController.text,
      'unit': _unitController.text,
      'sector': {
        'primary': _sectorPrimaryController.text,
        'secondary': _sectorSecondaryController.text,
        'tertiary': _sectorTertiaryController.text,
      },
      'sub_sector': {
        'primary': _subSectorPrimaryController.text,
        'secondary': _subSectorSecondaryController.text,
        'tertiary': _subSectorTertiaryController.text,
      },
      'emergency': _emergencyContext,
      'reason': _reasonController.text,
      'additional_notes': _additionalNotesController.text,
    });

    if (!mounted) return;

    setState(() {
      _submittingProposal = false;
      if (success) {
        _submitSuccess = true;
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(localizations.indicatorBankProposeFailed),
            backgroundColor: const Color(AppConstants.errorColor),
          ),
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.indicatorBankProposeTitle,
      ),
      body: SafeArea(
        child: _submitSuccess ? _buildSuccessView(localizations) : _buildForm(localizations),
      ),
    );
  }

  Widget _buildSuccessView(AppLocalizations localizations) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          const Icon(
            Icons.check_circle,
            color: Color(AppConstants.successColor),
            size: 64,
          ),
          const SizedBox(height: 16),
          Text(
            localizations.indicatorBankProposeThankYou,
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            localizations.indicatorBankProposeSuccess,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () => Navigator.of(context).pop(),
              style: ElevatedButton.styleFrom(
                backgroundColor: Color(AppConstants.ifrcRed),
                foregroundColor: Theme.of(context).colorScheme.onPrimary,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
              child: Text(localizations.close),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildForm(AppLocalizations localizations) {
    final theme = Theme.of(context);
    final contactFill = _lockContactFields
        ? theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.65)
        : null;

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              localizations.indicatorBankProposeContactInfo,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _nameController,
              readOnly: _lockContactFields,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeYourName,
                border: const OutlineInputBorder(),
                filled: _lockContactFields,
                fillColor: contactFill,
              ),
              validator: (value) => value?.isEmpty ?? true
                  ? localizations.indicatorBankNameRequired
                  : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _emailController,
              readOnly: _lockContactFields,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeEmail,
                border: const OutlineInputBorder(),
                filled: _lockContactFields,
                fillColor: contactFill,
              ),
              keyboardType: TextInputType.emailAddress,
              validator: (value) => value?.isEmpty ?? true
                  ? localizations.indicatorBankEmailRequired
                  : null,
            ),
            const SizedBox(height: 24),
            Text(
              localizations.indicatorBankProposeIndicatorInfo,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _indicatorNameController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeIndicatorName,
                border: const OutlineInputBorder(),
              ),
              validator: (value) => value?.isEmpty ?? true
                  ? localizations.indicatorBankIndicatorNameRequired
                  : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _definitionController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeDefinition,
                border: const OutlineInputBorder(),
              ),
              maxLines: 4,
              validator: (value) => value?.isEmpty ?? true
                  ? localizations.indicatorBankDefinitionRequired
                  : null,
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _typeController,
                    decoration: InputDecoration(
                      labelText: localizations.indicatorBankProposeType,
                      border: const OutlineInputBorder(),
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: TextFormField(
                    controller: _unitController,
                    decoration: InputDecoration(
                      labelText: localizations.indicatorBankProposeUnit,
                      border: const OutlineInputBorder(),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            Text(
              localizations.indicatorBankProposeSector,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _sectorPrimaryController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposePrimarySector,
                border: const OutlineInputBorder(),
              ),
              validator: (value) => value?.isEmpty ?? true
                  ? localizations.indicatorBankPrimarySectorRequired
                  : null,
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _sectorSecondaryController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeSecondarySector,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _sectorTertiaryController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeTertiarySector,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              localizations.indicatorBankProposeSubsector,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _subSectorPrimaryController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposePrimarySubsector,
                border: const OutlineInputBorder(),
              ),
              validator: (value) => value?.isEmpty ?? true
                  ? localizations.indicatorBankPrimarySubsectorRequired
                  : null,
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _subSectorSecondaryController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeSecondarySubsector,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _subSectorTertiaryController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeTertiarySubsector,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            AppCheckboxListTile(
              title: localizations.indicatorBankProposeEmergency,
              value: _emergencyContext,
              onChanged: (value) {
                setState(() => _emergencyContext = value ?? false);
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _reasonController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeReason,
                border: const OutlineInputBorder(),
              ),
              maxLines: 3,
              validator: (value) => value?.isEmpty ?? true
                  ? localizations.indicatorBankReasonRequired
                  : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _additionalNotesController,
              decoration: InputDecoration(
                labelText: localizations.indicatorBankProposeAdditionalNotes,
                border: const OutlineInputBorder(),
              ),
              maxLines: 3,
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _submittingProposal ? null : _submitProposal,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Color(AppConstants.ifrcRed),
                  foregroundColor: Theme.of(context).colorScheme.onPrimary,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                child: _submittingProposal
                    ? SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(
                            Theme.of(context).colorScheme.onPrimary,
                          ),
                        ),
                      )
                    : Text(localizations.indicatorBankProposeSubmit),
              ),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}
